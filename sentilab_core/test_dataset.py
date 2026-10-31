"""Dataset proofs use signed recorded events; no oracle or model is invoked."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from sentilab_core.dataset import export
from sentilab_core.envelope import build, canonical, genesis
from sentilab_core.ledger import BrokenLedger, Ledger
from sentilab_core.test_ledger import RuntimeSigner

FIXTURE = Path(__file__).resolve().parents[1] / 'docs/sentilab/evidence/SLAB-016'


class DatasetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'ledger'
        self.root.mkdir()
        shutil.copyfile(FIXTURE / 'fixture.jsonl', self.root / 'fixture.jsonl')
        self.keys = {k: bytes.fromhex(v) for k, v in json.loads((FIXTURE / 'public-keys.json').read_text()).items()}
        self.signer = RuntimeSigner()
        self.keys[self.signer.key_id] = self.signer.public_key
        self.events = [json.loads(line) for line in (self.root / 'fixture.jsonl').read_text().splitlines()]
        self.run = self.events[0]['run']
        self.ledger = Ledger(self.root, self.run, public_keys=self.keys, signer=self.signer)
        self.policy = {'heldout_families': [], 'rights': {'fixture': {'status': 'ok', 'reason': 'synthetic fixture grant'}}}

    def export(self, **options):
        return export(self.root, ['fixture'], public_keys=self.keys, policy=self.policy, **options)

    def rows(self, result, filename='current.jsonl'):
        return [json.loads(line) for line in (Path(result['directory']) / filename).read_text().splitlines()]

    def sign_events(self, events, run_id='fixture'):
        previous, rows = genesis(run_id), []
        for old in events:
            entry = build(event=old['event'], run=old['run'], actor=old['actor'],
                          prev_hash=previous, signer=self.signer, ts=old['ts'], values=old.get('values'))
            previous = entry['hash']
            rows.append(entry)
        (self.root / (run_id + '.jsonl')).write_bytes(b''.join(canonical(e) + b'\n' for e in rows))

    def test_determinism_and_recorded_outcomes(self):
        a = self.export()
        b = self.export(output_dir=Path(self.temp.name) / 'second')
        for name in ('records.jsonl', 'current.jsonl', 'rlaif.jsonl', 'manifest.json'):
            self.assertEqual((Path(a['directory']) / name).read_bytes(), (Path(b['directory']) / name).read_bytes())
        rows = {r['candidate']: r for r in self.rows(a)}
        self.assertEqual(len(rows), 7)
        self.assertEqual(rows['fixture:accept']['gate_outcome'], 'accepted')
        self.assertEqual(rows['fixture:reject']['gate_outcome'], 'wire_cap_exceeded')
        self.assertEqual(rows['fixture:failure']['evaluation']['error'], 'recorded_worker_failure')
        self.assertEqual(rows['fixture:margin']['gate_outcome'], 'within_margin')
        self.assertEqual(rows['fixture:margin']['delta_j'], 0.1)
        self.assertEqual(rows['fixture:loser']['delta_j'], -1)
        self.assertIsNone(rows['fixture:pending']['gate_outcome'])
        self.assertFalse(rows['fixture:pending']['eligibility']['preference'])
        self.assertEqual(rows['fixture:repair']['lineage']['parent_candidate'], 'fixture:reject')
        self.assertEqual(rows['fixture:repair']['labels']['repair'], 'verifier_confirmed')
        self.assertEqual(rows['fixture:failure']['labels']['result'], 'failure')
        self.assertEqual(rows['fixture:reject']['labels']['source'], 'verifier')
        self.assertEqual(len([r for r in self.rows(a, 'records.jsonl') if r['type'] == 'candidate']), 7)

    def test_withdraw_and_retract_append_corrections_without_erasing_history(self):
        before = self.export()
        original = (Path(before['directory']) / 'records.jsonl').read_bytes()
        self.ledger.append('withdraw', {'node': 'fixture:accept', 'reason': 'bad evidence'}, event_id='withdraw-accept')
        after = self.export()
        self.assertTrue((Path(after['directory']) / 'records.jsonl').read_bytes().startswith(original))
        row = next(r for r in self.rows(after) if r['candidate'] == 'fixture:accept')
        self.assertEqual(row['gate_outcome'], 'accepted')
        self.assertEqual(row['validity'], 'withdrawn')
        self.assertFalse(row['eligibility']['preference'])
        self.assertEqual(self.rows(after, 'records.jsonl')[-1]['reason'], 'withdraw')
        self.assertFalse(any('fixture:accept' in (p['chosen']['candidate'], p['rejected']['candidate']) for p in self.rows(after, 'rlaif.jsonl')))
        self.assertEqual((Path(before['directory']) / 'records.jsonl').read_bytes(), original)
        self.ledger.append('withdraw.retract', {'node': 'fixture:accept', 'reason': 'corrected'}, event_id='retract-accept')
        restored = next(r for r in self.rows(self.export()) if r['candidate'] == 'fixture:accept')
        self.assertEqual(restored['validity'], 'valid')
        self.assertTrue(restored['eligibility']['preference'])
        self.assertGreater(len(restored['corrections']), len(row['corrections']))

    def test_measurement_withdrawal_stales_dependent_candidate(self):
        self.ledger.append('withdraw', {'node': 'fixture:accept:reproduce', 'reason': 'measurement invalid'}, event_id='withdraw-measurement')
        row = next(r for r in self.rows(self.export()) if r['candidate'] == 'fixture:accept')
        self.assertEqual(row['validity'], 'stale')
        self.assertEqual(row['stale_because'], ['fixture:accept:reproduce'])
        self.assertFalse(row['eligibility']['preference'])

    def test_alternative_claim_support_cannot_replace_exact_training_measurements(self):
        self.ledger.append('node.create', {'id': 'fixture:alternative', 'kind': 'source'},
                           event_id='alternative-source')
        self.ledger.append('support.add', {'node': 'fixture:accept', 'set_id': 'alternative',
                                          'members': ['fixture:alternative']}, event_id='alternative-support')
        self.ledger.append('node.create', {'id': 'fixture:calibration', 'kind': 'source'},
                           event_id='calibration-source')
        self.ledger.append('support.add', {'node': 'fixture:accept:reproduce', 'set_id': 'calibration',
                                          'members': ['fixture:calibration']}, event_id='calibration-support')
        for target in ('fixture:accept:evaluate', 'fixture:accept:reproduce', 'fixture:calibration'):
            with self.subTest(target=target):
                before = self.export()
                original = (Path(before['directory']) / 'records.jsonl').read_bytes()
                self.ledger.append('withdraw', {'node': target, 'reason': 'invalid exact evidence'},
                                   event_id=target + ':withdraw')
                try:
                    after = self.export()
                    row = next(r for r in self.rows(after) if r['candidate'] == 'fixture:accept')
                    self.assertEqual(row['validity'], 'valid')  # Claim-level OR support survives.
                    self.assertFalse(row['eligibility']['sft'])
                    self.assertFalse(row['eligibility']['preference'])
                    self.assertTrue((Path(after['directory']) / 'records.jsonl').read_bytes().startswith(original))
                    self.assertEqual(self.rows(after, 'records.jsonl')[-1]['reason'], 'withdraw')
                    self.assertFalse(any('fixture:accept' in (p['chosen']['candidate'], p['rejected']['candidate'])
                                         for p in self.rows(after, 'rlaif.jsonl')))
                finally:
                    self.ledger.append('withdraw.retract', {'node': target, 'reason': 'evidence corrected'},
                                       event_id=target + ':retract')
                restored = next(r for r in self.rows(self.export()) if r['candidate'] == 'fixture:accept')
                self.assertTrue(restored['eligibility']['sft'])
                self.assertTrue(restored['eligibility']['preference'])

    def test_rights_fail_closed_and_heldout_never_enters_preferences(self):
        self.policy['rights'] = {}
        blocked = self.export()
        self.assertEqual(self.rows(blocked, 'rlaif.jsonl'), [])
        self.assertTrue(all(r['rights']['status'] == 'blocked' for r in self.rows(blocked)))
        self.policy['rights'] = {'fixture': {'status': 'ok', 'reason': 'fixture grant'}}
        allowed = self.export()
        self.assertGreater(len(self.rows(allowed, 'rlaif.jsonl')), 0)
        self.policy['heldout_families'] = [self.run['family']]
        held = self.export()
        self.assertEqual(self.rows(held, 'rlaif.jsonl'), [])
        self.assertTrue(all(r['split'] == 'heldout' for r in self.rows(held)))
        self.assertTrue(all(not r['eligibility']['preference'] for r in self.rows(held)))
        self.assertEqual(len(self.rows(held)), len(self.rows(allowed)))

    def test_pairs_have_two_verifier_hashes_and_only_ordered_contexts(self):
        result = self.export()
        pairs = self.rows(result, 'rlaif.jsonl')
        self.assertTrue(pairs)
        hashes = {e['hash']: e for e in self.events}
        for pair in pairs:
            self.assertEqual(pair['label_source'], 'verifier')
            self.assertEqual(pair['run_id'], 'fixture')
            for side in ('chosen', 'rejected'):
                ref = pair[side]['lineage']
                self.assertEqual(hashes[ref['envelope_hash']]['event']['body']['node'], pair[side]['candidate'])
            self.assertEqual(pair['chosen']['gate_outcome'], 'accepted')
            self.assertIn(pair['rejected']['gate_outcome'], ('within_margin', 'non_improving_current', 'wire_cap_exceeded'))
        self.assertFalse(any('fixture:failure' in (p['chosen']['candidate'], p['rejected']['candidate']) for p in pairs))
        self.assertFalse(any('fixture:pending' in (p['chosen']['candidate'], p['rejected']['candidate']) for p in pairs))
        self.assertFalse(any(p['chosen']['candidate'] == 'fixture:accept' and
                             p['rejected']['candidate'] in ('fixture:margin', 'fixture:loser') for p in pairs))

    def test_multiple_runs_seeds_and_heldout_family_isolation(self):
        for run_id, family, seed in [('second', self.run['family'], 11),
                                      ('third', self.run['family'], 22), ('held', 'held-family', 11)]:
            entries = json.loads(json.dumps(self.events).replace('fixture:', run_id + ':'))
            for entry in entries:
                entry['run'].update(run_id=run_id, family=family, seed=seed)
                body = entry['event']['body']
                if body.get('id') == run_id + ':run':
                    body['record'].update(fixture=family, seed=seed)
            self.sign_events(entries, run_id)
            self.policy['rights'][run_id] = {'status': 'ok', 'reason': 'fixture grant'}
        self.policy['heldout_families'] = ['held-family']
        arguments = dict(public_keys=self.keys, policy=self.policy)
        a = export(self.root, ['fixture', 'second', 'third', 'held'], **arguments)
        b = export(self.root, ['held', 'third', 'second', 'fixture', 'fixture'], **arguments)
        self.assertEqual(a, b)
        rows = self.rows(a)
        self.assertEqual(len({r['split'] for r in rows if r['family'] == self.run['family']}), 1)
        self.assertEqual({r['split'] for r in rows if r['family'] == 'held-family'}, {'heldout'})
        self.assertEqual(len(rows), 28)
        for pair in self.rows(a, 'rlaif.jsonl'):
            self.assertNotEqual(pair['family'], 'held-family')
            self.assertEqual(pair['chosen']['lineage']['run_id'], pair['rejected']['lineage']['run_id'])

    def test_display_and_proposal_opinions_cannot_supply_labels_or_rights(self):
        entries = copy.deepcopy(self.events)
        for entry in entries:
            body = entry['event']['body']
            if body.get('kind') == 'candidate':
                body['record']['labels'] = {'outcome': 'accepted', 'source': 'model'}
                body['record']['rights'] = {'status': 'ok', 'reason': 'self granted'}
                entry['values'] = {'J': {'value': -999, 'unit': '°C'}}
        self.sign_events(entries)
        self.policy['rights'] = {}
        rows = {r['candidate']: r for r in self.rows(self.export())}
        self.assertEqual(rows['fixture:margin']['delta_j'], .1)
        self.assertEqual(rows['fixture:reject']['gate_outcome'], 'wire_cap_exceeded')
        self.assertEqual(rows['fixture:failure']['labels']['result'], 'failure')
        self.assertTrue(all(r['rights']['status'] == 'blocked' for r in rows.values()))

    def test_terminal_payload_cannot_promote_rejection_or_failure(self):
        for candidate, label in [('fixture:reject', 'rejection'), ('fixture:failure', 'failure')]:
            with self.subTest(candidate=candidate):
                entries = copy.deepcopy(self.events)
                terminal = next(i for i, e in enumerate(entries)
                                if e['event']['body'].get('node') == candidate and
                                e['event']['body'].get('to') in ('rejected_constraints', 'failed_run'))
                entries[terminal]['event']['body']['record']['outcome'] = 'accepted'
                self.sign_events(entries[:terminal + 1])
                result = self.export()
                rows = {row['candidate']: row for row in self.rows(result)}
                self.assertEqual(rows[candidate]['labels']['result'], label)
                self.assertFalse(rows[candidate]['eligibility']['sft'])
                self.assertFalse(any(pair['chosen']['candidate'] == candidate
                                     for pair in self.rows(result, 'rlaif.jsonl')))

    def test_signed_inconsistent_gate_or_context_refuses_export(self):
        for mutation in ('outcome', 'measurement', 'run', 'role'):
            entries = copy.deepcopy(self.events)
            gate = next(e for e in entries if e['event']['body'].get('to') == 'accepted')
            if mutation == 'outcome':
                gate['event']['body']['record']['decision']['outcome'] = 'within_margin'
            elif mutation == 'measurement':
                gate['event']['body']['record']['inputs']['evaluation']['j'] = -99
            elif mutation == 'run':
                entries[-1]['run']['seed'] += 1
            else:
                failure = next(e for e in entries if e['event']['body'].get('to') == 'failed_run')
                failure['event']['actor_role'] = 'lab'
                failure['actor']['lab'] = 'lab'
            self.sign_events(entries)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.export()

    def test_pair_abstains_when_two_improvements_are_within_margin(self):
        entries = copy.deepcopy(self.events)
        for entry in entries:
            body = entry['event']['body']
            if body.get('kind') == 'measurement' and body['record']['candidate_node'] == 'fixture:repair':
                body['record']['j'] = 99.6
            if body.get('node') == 'fixture:repair' and body.get('to') == 'accepted':
                body['record']['inputs']['evaluation']['j'] = 99.6
                body['record']['inputs']['reproduction']['j'] = 99.6
                body['record']['decision']['improvement'] = .4
        self.sign_events(entries)
        pairs = self.rows(self.export(), 'rlaif.jsonl')
        self.assertFalse(any(p['chosen']['candidate'] == 'fixture:repair' and
                             p['rejected']['candidate'] == 'fixture:margin' for p in pairs))
        self.assertTrue(any(p['chosen']['candidate'] == 'fixture:repair' and
                            p['rejected']['candidate'] == 'fixture:loser' for p in pairs))

    def test_complete_gate_decision_matches_frozen_config_and_history(self):
        for mutation in ('margin', 'improvement', 'incumbent', 'wire_cap', 'geometry',
                         'stopped', 'tolerance', 'process', 'success', 'binding', 'wire'):
            with self.subTest(mutation=mutation):
                entries = copy.deepcopy(self.events)
                record = next(e['event']['body']['record'] for e in entries
                              if e['event']['body'].get('node') == 'fixture:repair' and
                              e['event']['body'].get('to') == 'accepted')
                inputs, decision = record['inputs'], record['decision']
                measurements = [e['event']['body']['record'] for e in entries
                                if e['event']['body'].get('kind') == 'measurement' and
                                e['event']['body']['record']['candidate_node'] == 'fixture:repair']
                if mutation == 'margin':
                    # Both numerical observations really improve by .4, but the
                    # .3 gap to the within-margin candidate is below frozen .32.
                    for measured in measurements:
                        measured['j'] = 99.6
                    inputs['evaluation']['j'] = inputs['reproduction']['j'] = 99.6
                    decision.update(improvement=.4, margin=.01)
                elif mutation == 'improvement':
                    decision['improvement'] = 100
                elif mutation == 'incumbent':
                    inputs['current']['j'] = decision['current']['j'] = 200
                    decision['improvement'] = 110
                elif mutation == 'wire_cap':
                    inputs['wire_cap_mm'] = 100
                elif mutation == 'geometry':
                    inputs['geometry_valid'] = False
                elif mutation == 'stopped':
                    inputs['stopped'] = True
                else:
                    reproduction = next(m for m in measurements if m['phase'] == 'reproduce')
                    if mutation == 'tolerance':
                        reproduction['j'] = 90.01
                        decision['improvement'] = 9.99
                    elif mutation == 'process':
                        reproduction['process_id'] = inputs['evaluation']['process_id']
                    elif mutation == 'success':
                        reproduction['success'] = False
                    elif mutation == 'binding':
                        reproduction['binding']['candidate_id'] = 'another-design'
                    elif mutation == 'wire':
                        reproduction['wire_mm'] = 11
                    inputs['reproduction'] = copy.deepcopy(reproduction)
                self.sign_events(entries)
                with self.assertRaises(ValueError):
                    self.export()

    def test_later_matching_design_cannot_fabricate_parent_lineage(self):
        entries = copy.deepcopy(self.events)
        first = next(e for e in entries if e['event']['body'].get('id') == 'fixture:accept')
        first['event']['body']['record']['parent_hash'] = 'design-pending'
        self.sign_events(entries)
        row = next(r for r in self.rows(self.export()) if r['candidate'] == 'fixture:accept')
        self.assertIsNone(row['lineage']['parent_candidate'])

    def test_tampering_and_untrusted_keys_refuse_entire_export(self):
        output = Path(self.temp.name) / 'bad-export'
        with self.assertRaises(BrokenLedger):
            export(self.root, ['fixture'], public_keys={}, output_dir=output)
        self.assertFalse(output.exists())
        data = copy.deepcopy(self.events)
        data[-1]['event']['body']['record'] = {'outcome': 'accepted'}
        (self.root / 'fixture.jsonl').write_bytes(b''.join(canonical(e) + b'\n' for e in data))
        with self.assertRaises(BrokenLedger):
            self.export(output_dir=output)
        self.assertFalse(output.exists())

    def test_input_validation_and_existing_export_integrity(self):
        for run_ids in ([], 'fixture', ['../fixture'], ['fixture', 2]):
            with self.subTest(run_ids=run_ids), self.assertRaises(ValueError):
                export(self.root, run_ids, public_keys=self.keys)
        for policy in ({'rights': {'fixture': {'status': 'ok'}}}, {'heldout_families': 'family'}, {'unexpected': True}):
            with self.subTest(policy=policy), self.assertRaises(ValueError):
                export(self.root, ['fixture'], public_keys=self.keys, policy=policy)
        result = self.export()
        (Path(result['directory']) / 'rlaif.jsonl').write_text('corrupted\n')
        with self.assertRaisesRegex(ValueError, 'existing export'):
            self.export()

    def test_real_cli_and_mcp_stdio_have_identical_artifacts(self):
        output = Path(self.temp.name) / 'wire'
        policy_path = Path(self.temp.name) / 'policy.json'
        policy_path.write_bytes(canonical(self.policy))
        env = {**os.environ, 'SENTILAB_LIVE_DIR': str(self.root),
               'SENTILAB_VIEW_PUBLIC_KEYS': json.dumps({k: v.hex() for k, v in self.keys.items()})}
        cli = subprocess.run([sys.executable, '-m', 'sentilab_cli', 'dataset', 'export',
                              '--run-id', 'fixture', '--output-dir', str(output), '--policy', str(policy_path)],
                             env=env, capture_output=True, check=True)
        requests = [{'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'},
                    {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call', 'params': {
                        'name': 'sentilab_dataset_export', 'arguments': {'run_ids': ['fixture'],
                        'output_dir': str(output), 'policy': self.policy}}}]
        mcp = subprocess.run([sys.executable, '-m', 'sentilab_mcp'], env=env,
                             input=b''.join(canonical(r) + b'\n' for r in requests), capture_output=True, check=True)
        responses = [json.loads(line) for line in mcp.stdout.splitlines()]
        self.assertIn('sentilab_dataset_export', [t['name'] for t in responses[0]['result']['tools']])
        result = json.loads(responses[1]['result']['content'][0]['text'])
        self.assertEqual(json.loads(cli.stdout), result)
        self.assertTrue(self.rows(result, 'rlaif.jsonl'))


if __name__ == '__main__':
    unittest.main()
