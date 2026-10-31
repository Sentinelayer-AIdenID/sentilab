"""Freeze verifier-derived fixture labels. No solver, model or real-run data."""
import hashlib
import json
from pathlib import Path
import sys

SOURCE = Path(sys.argv[1]).resolve()
OUT = Path(sys.argv[2]).resolve()
sys.path.insert(0, str(SOURCE))
from sentilab_core.dataset import export

OUT.mkdir(parents=True, exist_ok=True)
fixture = SOURCE / 'docs/sentilab/evidence/SLAB-016'
ledger = OUT / 'input-ledger'
ledger.mkdir(exist_ok=True)
for name in ('fixture.jsonl', 'public-keys.json'):
    (ledger / name).write_bytes((fixture / name).read_bytes())
keys = {k: bytes.fromhex(v) for k, v in json.loads((ledger / 'public-keys.json').read_text()).items()}
result = export(ledger, ['fixture'], public_keys=keys, output_dir=OUT / 'export', policy={
    'heldout_families': [], 'rights': {'fixture': {'status': 'ok', 'reason': 'Warden56213 synthetic-fixture scaffolding grant'}}})
snapshot = Path(result['directory'])
rows = [json.loads(line) for line in (snapshot / 'current.jsonl').read_text().splitlines()]
# Train a small metadata/decision-label task, never pretend these repeated fixtures
# are 200 independent experiments or a physical placement optimization dataset.
usable = [r for r in rows if r['labels']['source'] == 'verifier']
assert usable and all(r['lineage']['run_id'] == 'fixture' for r in usable)
system = ('You label synthetic SentiLab fixture records. Return only JSON with keys '
          'result, lifecycle, repair. Copy the verifier lifecycle, map accepted to success, '
          'rejected_constraints or rejected_schema to rejection, failed_run or reproduction_failed '
          'or cancelled or inconclusive to failure, non_improving_current or within_margin '
          'or non_improving to non_improving, tie to tie. repair is the provided repair label '
          'or null. This is a fixture metadata task, not a thermal or geometry prediction.')
prompts = [
    'Label this recorded fixture move.', 'Summarize this synthetic verifier decision.',
    'Produce the label JSON for this fixture.', 'Read the fixture outcome and return its labels.',
    'Convert the recorded move result to the requested label object.',
    'Give the labels for this synthetic move record.', 'Classify this verifier-labelled fixture.',
    'Translate this recorded lifecycle into fixture labels.',
    'Return the fixture result, lifecycle and repair fields.', 'Label the following synthetic evidence record.'
]
def item(index, evaluation=False):
    row = usable[index % len(usable)]
    payload = {'candidate': row['candidate'], 'lifecycle': row['lifecycle'],
               'repair': row['labels']['repair'], 'gate_outcome': row['gate_outcome'],
               'validity': row['validity'], 'fixture': True}
    instruction = (('For this preflight label check, emit the JSON object.' if evaluation else
                    prompts[(index // len(usable)) % len(prompts)]) + '\n' +
                   json.dumps(payload, sort_keys=True, separators=(',', ':')))
    answer = json.dumps({k: v for k,v in [('result',row['labels']['result']),
                        ('lifecycle',row['lifecycle']),('repair',row['labels']['repair'])]},
                        sort_keys=True, separators=(',', ':'))
    return {'row_id': ('eval-' if evaluation else 'train-') + str(index).zfill(3),
            'fixture': True, 'family': row['family'], 'source_record_id': row['record_id'],
            'source_candidate': row['candidate'], 'source_lineage': row['lineage'],
            'instruction': instruction, 'system': system, 'output': answer}
for name, count, evaluation in [('train.jsonl',200,False),('eval.jsonl',20,True)]:
    (OUT / name).write_bytes(b''.join((json.dumps(item(i,evaluation),sort_keys=True)+'\n').encode() for i in range(count)))
manifest = {'schema': 'sentilab-slab018-fixtures/1', 'source_head': '95e4970fbcd543e26dd0da7aa926f493054c6cc0',
            'source_dataset_id': result['dataset_id'], 'source_export': result,
            'source_candidates': len(rows), 'verifier_labelled_candidates': len(usable),
            'train_rows': 200, 'eval_rows': 20, 'real_experiments': 0,
            'claim': 'Fixture metadata/label and adapter plumbing only; same-family repeated examples, no held-out scientific generalization.',
            'snapshot_files': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in snapshot.iterdir() if p.is_file()},
            'data_files': {n: hashlib.sha256((OUT/n).read_bytes()).hexdigest() for n in ('train.jsonl','eval.jsonl')},
            'code_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
(OUT / 'DATA-MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({k:manifest[k] for k in ('source_dataset_id','source_candidates','verifier_labelled_candidates','train_rows','eval_rows','data_files','claim')}))
