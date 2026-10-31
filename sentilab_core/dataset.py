"""Deterministic dataset snapshots from authenticated PR15 event ledgers.

records.jsonl is a journal: proposals are never overwritten; subsequent facts
are correction snapshots. current.jsonl folds that history. An export directory
is content addressed and immutable, including its split/rights policy.
"""
import copy
from decimal import Decimal
import hashlib
import os
from pathlib import Path
import shutil
import tempfile

from .envelope import canonical, digest, validate_run_id
from .gate import AcceptanceGate
from .ledger import BrokenLedger, lock, replay
from .projection import board, project

VERSION = 'sentilab-dataset/1'
BOARD = {'accepted', 'non_improving_current', 'within_margin'}
NEGATIVE = {'rejected_schema', 'rejected_constraints'}
FAILURE = {'failed_run', 'reproduction_failed', 'cancelled', 'inconclusive'}
TERMINAL = BOARD | NEGATIVE | FAILURE | {'non_improving', 'tie'}


def _policy(value):
    value = {} if value is None else value
    if not isinstance(value, dict) or set(value) - {'heldout_families', 'rights'}:
        raise ValueError('invalid dataset policy')
    heldout, rights = value.get('heldout_families', []), value.get('rights', {})
    if not isinstance(heldout, list) or any(not isinstance(f, str) or not f for f in heldout):
        raise ValueError('heldout_families must be an array of family names')
    if not isinstance(rights, dict):
        raise ValueError('rights must map run IDs to grants')
    for run_id, grant in rights.items():
        validate_run_id(run_id)
        if (not isinstance(grant, dict) or set(grant) != {'status', 'reason'} or
                grant['status'] not in ('ok', 'blocked') or
                not isinstance(grant['reason'], str) or not grant['reason'].strip()):
            raise ValueError('rights require status ok/blocked and a reason')
    return {'heldout_families': sorted(set(heldout)), 'rights': copy.deepcopy(rights)}


def _split(family, policy):
    # Keep every seed/variant in one family together, including across runs.
    if family in policy['heldout_families']:
        return 'heldout'
    return 'dev' if int(digest(['family-split/1', family]), 16) % 10 == 0 else 'train'


def _ref(envelope):
    return {'run_id': envelope['run']['run_id'], 'seq': envelope['event']['seq'],
            'envelope_hash': envelope['hash']}


def _labels(row, parent):
    state = row['lifecycle']
    terminal = state in TERMINAL
    result = ('success' if state == 'accepted' else 'rejection' if state in NEGATIVE else
              'failure' if state in FAILURE else 'non_improving' if state in BOARD or state == 'non_improving'
              else 'tie' if state == 'tie' else 'pending')
    return {'source': 'verifier' if terminal else None, 'result': result,
            'reproduction': ('passed' if state in BOARD else 'failed' if state == 'reproduction_failed'
                             else 'not_confirmed'),
            'verification_scope': ('simulator' if state in BOARD else 'constraints' if state in NEGATIVE else None),
            'repair': ('verifier_confirmed' if state == 'accepted' and parent is not None and
                       parent['lifecycle'] in NEGATIVE | FAILURE else None)}


def _eligibility(row):
    reasons = []
    if row['rights']['status'] != 'ok':
        reasons.append('rights_blocked')
    if row['split'] == 'heldout':
        reasons.append('heldout_family')
    if row['validity'] in ('stale', 'withdrawn'):
        reasons.append(row['validity'])
    if row['lifecycle'] not in BOARD | NEGATIVE:
        reasons.append('no_ordered_verifier_outcome')
    if row['lifecycle'] in BOARD and row['validity'] != 'valid':
        reasons.append('unverified_support')
    if any(evidence is not None and evidence['validity'] != 'valid'
           for evidence in row['measurement_validity'].values()):
        reasons.append('invalid_measurement_support')
    return {'preference': not reasons, 'sft': not reasons and row['lifecycle'] == 'accepted',
            'reasons': reasons}


def _journal(prefix, policy):
    journal, rows, proposals, measurements, gates = [], {}, {}, {}, {}
    run = prefix[0]['run']
    if not run['family'] or any(e['run'] != run for e in prefix):
        raise ValueError('run context must be fixed and family nonempty')
    config = None
    for index, envelope in enumerate(prefix):
        event = envelope['event']
        kind, body = event['type'], event['body']
        node = body.get('node', body.get('id'))
        if kind == 'node.create' and body.get('id') == run['run_id'] + ':run':
            if event['actor_role'] != 'core' or config is not None or not isinstance(body.get('record'), dict):
                raise ValueError('invalid frozen run configuration')
            config = body['record']
        if kind == 'node.create' and body.get('kind') == 'candidate':
            if config is None:
                raise ValueError('candidate before frozen run configuration')
            proposal = body.get('record')
            if not isinstance(proposal, dict) or not isinstance(proposal.get('binding'), dict):
                raise ValueError('candidate requires recorded binding')
            proposals[node] = envelope
        elif kind == 'node.create' and body.get('kind') == 'measurement':
            record = body.get('record', {})
            target, phase = record.get('candidate_node'), record.get('phase')
            if target not in proposals or phase not in ('evaluate', 'reproduce') or event['actor_role'] != 'core':
                raise ValueError('invalid verifier measurement')
            if (target, phase) in measurements:
                raise ValueError('duplicate candidate measurement phase')
            measurements[target, phase] = envelope
        elif kind == 'lifecycle.transition':
            if event['actor_role'] not in ('core', 'acceptance_gate'):
                raise ValueError('lifecycle labels require verifier authority')
            if body['to'] in BOARD:
                record = body.get('record', {})
                decision, inputs = record.get('decision', {}), record.get('inputs', {})
                proposal = proposals[node]['event']['body']['record']
                if (event['actor_role'] != 'acceptance_gate' or decision.get('outcome') != body['to'] or
                        inputs.get('binding') != proposal['binding'] or
                        any(inputs.get(phase) != measurements.get((node, name), {}).get('event', {}).get('body', {}).get('record')
                            for phase, name in [('evaluation', 'evaluate'), ('reproduction', 'reproduce')]) or
                        inputs.get('evaluation') is None or inputs.get('reproduction') is None):
                    raise ValueError('gate evidence does not match recorded measurements')
                # Reproduce the pure gate calculation, not a new admission or
                # solve. A signature authenticates a decision, not its arithmetic.
                expected_inputs = {
                    'geometry_valid': proposal.get('geometry_valid'),
                    'wire_cap_mm': config.get('wire_cap_mm'), 'binding': proposal['binding'],
                    'evaluation': inputs['evaluation'], 'reproduction': inputs['reproduction'],
                    'stopped': False, 'current': board(prefix[:index])}
                verifier = AcceptanceGate(margin=config.get('margin'),
                                          reproduction_tolerance=config.get('reproduction_tolerance'))
                expected_decision = verifier.decide(**expected_inputs)
                if (canonical(inputs) != canonical(expected_inputs) or
                        canonical(decision) != canonical(expected_decision)):
                    raise ValueError('gate decision does not match frozen configuration and history')
            if body['to'] in TERMINAL:
                gates[node] = envelope
        # The shipping projection validates transitions/support and computes
        # transitive stale state, including withdrawal retractions.
        state = project(prefix[:index + 1])['nodes']
        for candidate, created in proposals.items():
            proposal = created['event']['body']['record']
            old = rows.get(candidate)
            gate = gates.get(candidate)
            record = gate['event']['body'].get('record', {}) if gate else {}
            lifecycle = state[candidate]['lifecycle']
            measured = {phase: measurements.get((candidate, name)) for phase, name in
                        [('evaluation', 'evaluate'), ('reproduction', 'reproduce')]}
            evidence = {phase: e['event']['body']['record'] if e else None for phase, e in measured.items()}
            if lifecycle == 'failed_run':
                evidence['evaluation'] = record
            parents = [p for p, e in proposals.items() if e['event']['seq'] < created['event']['seq'] and
                       e['event']['body']['record']['binding'].get('candidate_id') == proposal.get('parent_hash')]
            # PR15 records a parent design hash, not a unique proposal ID.
            # Preserve ambiguity instead of inventing an exact repair lineage.
            parent = parents[0] if len(parents) == 1 else None
            row = {'candidate': candidate, 'proposal': proposal, 'geometry': proposal.get('design'),
                   'binding': proposal['binding'], **evidence,
                   'lifecycle': lifecycle, 'gate_outcome': (record.get('decision', {}).get('outcome')
                       if lifecycle in BOARD else record.get('outcome', lifecycle) if gate else None),
                   'delta_j': record.get('decision', {}).get('improvement'),
                   'decision': record.get('decision'), 'gate_record': record if gate else None,
                   'family': run['family'], 'seed': run['seed'],
                   'context': {k: v for k, v in proposal['binding'].items() if k != 'candidate_id'},
                   'run_config': config, 'validity': state[candidate]['validity'],
                   'stale_because': state[candidate]['stale_because'],
                   # An alternative claim support set cannot replace these
                   # exact observations bound into the signed gate inputs.
                   'measurement_validity': {
                       phase: {key: state[e['event']['body']['id']][key]
                               for key in ('validity', 'stale_because')} if e else None
                       for phase, e in measured.items()},
                   'split': _split(run['family'], policy),
                   'rights': policy['rights'].get(run['run_id'], {'status': 'blocked', 'reason': 'no recorded rights grant'}),
                   'lineage': {'proposal': _ref(created), 'parent_candidate': parent,
                               'parent_hash': proposal.get('parent_hash'),
                               'evaluation': _ref(measured['evaluation']) if measured['evaluation'] else None,
                               'reproduction': _ref(measured['reproduction']) if measured['reproduction'] else None,
                               'gate': _ref(gate) if gate else None}}
            row['labels'] = _labels(row, rows.get(parent))
            row['eligibility'] = _eligibility(row)
            if old is not None and canonical(row) == canonical(old['_facts']):
                continue
            corrections = [] if old is None else old['corrections'] + [_ref(envelope)]
            row_id = digest([VERSION, candidate, _ref(envelope)])
            entry = {**row, 'schema': VERSION, 'type': 'candidate' if old is None else 'correction',
                     'record_id': row_id, 'supersedes': old['record_id'] if old else None,
                     'reason': kind, 'corrections': corrections,
                     'lineage': {**row['lineage'], **_ref(envelope)}}
            journal.append(entry)
            rows[candidate] = {**entry, '_facts': copy.deepcopy(row)}
    return journal, [{k: v for k, v in row.items() if k != '_facts'} for row in rows.values()]


def _pairs(rows):
    pairs = []
    for chosen in rows:
        if not chosen['eligibility']['preference'] or chosen['lifecycle'] != 'accepted':
            continue
        for rejected in rows:
            if (not rejected['eligibility']['preference'] or rejected['candidate'] == chosen['candidate'] or
                    rejected['lifecycle'] not in NEGATIVE | {'non_improving_current', 'within_margin'} or
                    any(chosen[key] != rejected[key] for key in ('family', 'seed', 'context', 'run_config', 'split')) or
                    chosen['lineage']['run_id'] != rejected['lineage']['run_id']):
                continue
            if rejected['lifecycle'] in BOARD:
                # A newer acceptance need not outrank an older valid loser.
                # Only compare decisions made against the SAME frozen incumbent.
                if chosen['decision']['current'] != rejected['decision']['current']:
                    continue
                if chosen['decision']['current'] is None:
                    continue
                # within_margin is not itself a negative label; the recorded
                # improvements must establish a strict margin between the pair.
                difference = Decimal(str(chosen['delta_j'])) - Decimal(str(rejected['delta_j']))
                if difference <= Decimal(str(chosen['decision']['margin'])):
                    continue
            sides = {name: {'candidate': row['candidate'], 'action': row['proposal'],
                            'gate_outcome': row['gate_outcome'], 'delta_j': row['delta_j'],
                            'lineage': row['lineage']['gate']} for name, row in
                     [('chosen', chosen), ('rejected', rejected)]}
            context = {key: chosen[key] for key in ('family', 'seed', 'context', 'split')}
            comparison_id = digest([VERSION, sides, context])
            pairs.append({'schema': VERSION, 'comparison_id': comparison_id,
                          'run_id': chosen['lineage']['run_id'], **context, **sides,
                          'label_source': 'verifier', 'preference': 'chosen',
                          'rubric_version': 'recorded-gate/1',
                          'rationale': ('hard_constraint_rejection' if rejected['lifecycle'] in NEGATIVE
                                        else 'same_incumbent_improvement_exceeds_margin')})
    return sorted(pairs, key=lambda pair: pair['comparison_id'])


def export(ledger_root, run_ids, *, public_keys, output_dir=None, policy=None):
    """Export immutable files; public_keys must be independently trusted pins.

    Missing rights grants retain raw evidence but exclude training. Run IDs are
    explicit (no accidental directory discovery). A broken ledger refuses the
    entire export, rather than silently training on its surviving prefix.
    """
    if not isinstance(run_ids, (list, tuple)) or not run_ids:
        raise ValueError('run_ids must be a nonempty array')
    for run_id in run_ids:
        validate_run_id(run_id)
    policy = _policy(policy)
    records, current, sources = [], [], []
    for run_id in sorted(set(run_ids)):
        state = replay(ledger_root, run_id, public_keys=public_keys)
        if state['error'] or not state['prefix']:
            raise BrokenLedger(state['error'] or 'empty ledger')
        journal, rows = _journal(state['prefix'], policy)
        records.extend(journal)
        current.extend(rows)
        sources.append({'run_id': run_id, 'seq': state['last_seq'], 'envelope_hash': state['head_hash']})
    pairs = _pairs(current)
    files = {name: b''.join(canonical(row) + b'\n' for row in rows) for name, rows in
             [('records.jsonl', records), ('current.jsonl', current), ('rlaif.jsonl', pairs)]}
    manifest = {'schema': VERSION, 'sources': sources, 'policy': policy,
                'split_rule': 'family-split/1: sha256 modulo 10 = 0 dev; otherwise train; heldout override',
                'counts': {'records': len(records), 'candidates': len(current), 'pairs': len(pairs)},
                'sha256': {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}}
    dataset_id = digest(manifest)
    files['manifest.json'] = canonical(manifest) + b'\n'
    output = Path(output_dir) if output_dir is not None else Path(ledger_root) / 'datasets'
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    destination = output / dataset_id
    with lock(output / '.export.lock'):
        if destination.exists() or destination.is_symlink():
            if destination.is_symlink() or not destination.is_dir() or any(
                    (destination / name).is_symlink() or not (destination / name).is_file() or
                    (destination / name).read_bytes() != data for name, data in files.items()):
                raise ValueError('existing export differs from immutable snapshot')
        else:
            temporary = Path(tempfile.mkdtemp(prefix='.pending-', dir=output))
            try:
                for name, data in files.items():
                    with (temporary / name).open('wb') as handle:
                        handle.write(data)
                        handle.flush()
                        os.fsync(handle.fileno())
                _sync_directory(temporary)
                os.rename(temporary, destination)
                _sync_directory(output)
            finally:
                if temporary.exists():
                    shutil.rmtree(temporary)
    return {'dataset_id': dataset_id, 'directory': str(destination), **manifest}


def _sync_directory(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
