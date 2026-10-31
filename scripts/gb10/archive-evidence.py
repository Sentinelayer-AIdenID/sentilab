import datetime
import hashlib
import json
from pathlib import Path
import subprocess

root=Path('/home/dell/sentilab/preflight-20261031')
state=json.loads((root/'execution-state.json').read_text())
assert state['active'] is None and state['attempts'][-1]['status']=='completed'
assert state['gpu_container_wall_seconds']<=3600
running=subprocess.check_output(['docker','ps','--filter','label=sentilab.owner=sentilab-slab018-20261031','--format','{{.ID}}'],text=True).strip()
assert not running
attempt=root/'attempt-01'
for name in ['execution-state.json','execution-inputs.json','execution.log','model_stage.py','supervise.py','http_eval.py','runtime-receipt.py','MANIFEST.verified.json','download-state.json']:
    (attempt/name).write_bytes((root/name).read_bytes())
def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as handle:
        for part in iter(lambda:handle.read(1024*1024),b''):h.update(part)
    return h.hexdigest()
receipt={'schema':'sentilab-slab018-artifact-receipt/1','at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
         'status':'completed','attempt':1,'owned_running_containers':[],
         'actual_stage_charged_seconds':sum(s['charged_container_wall_seconds'] for s in state['attempts'][0]['stages']),
         'conservative_total_seconds':state['gpu_container_wall_seconds'],
         'prior_primitive_reservation_seconds':180,'files':{}}
for file in sorted(attempt.rglob('*')):
    if file.is_file() and file.name!='REMOTE-ARTIFACT-MANIFEST.json':
        receipt['files'][str(file.relative_to(attempt))]={'bytes':file.stat().st_size,'sha256':sha(file)}
(attempt/'REMOTE-ARTIFACT-MANIFEST.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps({'files':len(receipt['files']),'bytes':sum(v['bytes'] for v in receipt['files'].values()),
                  'manifest_sha256':sha(attempt/'REMOTE-ARTIFACT-MANIFEST.json'),'state':receipt['status']}))
