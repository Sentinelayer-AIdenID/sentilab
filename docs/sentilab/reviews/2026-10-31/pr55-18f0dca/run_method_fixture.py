"""Additional unknown-method counterexample; synthetic oracle, no child processes."""
from pathlib import Path
import asyncio
import hashlib
import json
import os
import sys
import tempfile
from unittest.mock import patch

OUT=Path(__file__).resolve().parent
REPO=OUT.parents[2]/'.sentinelayer/pr55-profile-review'
sys.path.insert(0,str(REPO))
os.chdir(REPO)
blocked=[]
def audit(event,args):
    if event in ('subprocess.Popen','os.system','os.posix_spawn','socket.connect','socket.getaddrinfo'):
        blocked.append(event)
        raise RuntimeError('forbidden PR55 review action '+event)
sys.addaudithook(audit)
from sundai_controller import evidence_profile as ep, headroom as h, headroom_evidence as e
from sundai_controller.test_evidence_profile import identity,record
from sundai_controller.test_headroom import CountingOracle

async def main():
    class SyntheticProduction(CountingOracle):
        requires_evidence_profile=True
    current=dict(identity(),fixture='ascend910')
    with tempfile.TemporaryDirectory(prefix='pr55-method-') as temp:
        tmp=Path(temp)
        measured=tmp/'PROFILE.json'
        measured.write_text(json.dumps(ep.build_profile([record()],current)))
        prereg={'schema':'slab-039-prereg-v3','fixture':'ascend910','grid':32,'rule':{'k':5},
                'reducer_methods':{'methods':['typo'],'seeds':[0],'search_evaluations_per_method':1,'reproduction_evaluations_per_method':1},
                'long_sa':{'seeds':[100],'max_evaluations_per_restart':2,'max_cpu_minutes':1},
                'evidence_profile':{'path':str(measured),'sha256':hashlib.sha256(measured.read_bytes()).hexdigest(),'reserve_cpu_seconds':2,'reserve_reason':'synthetic fixture only','declared_calls':4}}
        path=tmp/'PREREG.json'
        path.write_text(json.dumps(prereg))
        with patch.object(e,'execution_identity',return_value=current),patch.object(h.os,'fsync'):
            result=await h.run_headroom('ascend910',0,path,tmp/'output',oracle_factory=SyntheticProduction)
        lane=result['reducer_results'][0]
        return {'scope':'Nonphysical finite synthetic oracle, not thermal evidence','methodDeclared':'typo','admitted':result['evidence_profile_admission']['admitted'],'result':{key:result.get(key) for key in ('verdict','passed','aggregate_evaluations','reducer_methods')},'lane':{key:lane.get(key) for key in ('method','evaluation_count','search_evaluation_count','reproduction_evaluation_count','complete','stop_reason')},'blockedForbiddenAttempts':blocked}
result=asyncio.run(main())
(OUT/'UNKNOWN-METHOD-FIXTURE.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result))
