"""Finite synthetic PR55 review. Audit hook forbids process/network launches."""
from pathlib import Path
import asyncio
import hashlib
import io
import json
import os
import resource
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[2]
REPO=ROOT/'.sentinelayer/pr55-profile-review'
sys.path.insert(0,str(REPO))
os.chdir(REPO)
blocked=[]
def audit(event,args):
    if event in ('subprocess.Popen','os.system','os.posix_spawn','socket.connect','socket.getaddrinfo'):
        blocked.append(event)
        raise RuntimeError('PR55 review forbids native/process/network launch: '+event)
sys.addaudithook(audit)

names=['sundai_controller.test_evidence_profile',
       'sundai_controller.test_headroom.GateFunctionTests',
       'sundai_controller.test_headroom.GatePassDynamicTests',
       'sundai_controller.test_headroom.MeshValidationTests',
       'sundai_controller.test_headroom_evidence.EvidenceRunnerTests']
stream=io.StringIO()
start=time.perf_counter()
result=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromNames(names))
(OUT/'FIXTURE-TESTS.log').write_text(stream.getvalue(),encoding='utf-8')
test_result={'testsRun':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'successful':result.wasSuccessful(),'wallSeconds':time.perf_counter()-start,'modules':names,'blockedForbiddenAttempts':blocked,'python':sys.version,'cpuSelfSeconds':resource.getrusage(resource.RUSAGE_SELF).ru_utime+resource.getrusage(resource.RUSAGE_SELF).ru_stime}
(OUT/'FIXTURE-TESTS.json').write_text(json.dumps(test_result,indent=2)+'\n',encoding='utf-8')
print(json.dumps(test_result),flush=True)
if not result.wasSuccessful():
    print(stream.getvalue(),flush=True)
    raise SystemExit(1)

from sundai_controller import evidence_profile as ep, headroom as h, headroom_evidence as e
from sundai_controller.test_evidence_profile import identity, record, prereg
from sundai_controller.test_headroom import CountingOracle

current=dict(identity(),fixture='ascend910',problem_hash='current-ascend-problem')
foreign=record()
foreign['result'].update(problem_hash='foreign-micro150-problem',fixture='micro150',grid=64)
foreign['identity']=dict(identity(),fixture='micro150',grid=64)
foreign_profile=ep.build_profile([foreign],current)
declaration=dict(prereg(),fixture='ascend910')
foreign_admission=ep.admission(declaration,foreign_profile,90,identity=current)
findings={'foreignRecordRelabel':{'admitted':foreign_admission['admitted'],'declaredIdentity':current,'embeddedForeignIdentity':foreign['identity'],'embeddedForeignResult':foreign['result'],'profileIdentity':foreign_profile['identity'],'exclusions':foreign_profile['excluded_records']}}

async def run_counterexample():
    class SyntheticProduction(CountingOracle):
        requires_evidence_profile=True
    with tempfile.TemporaryDirectory(prefix='pr55-synthetic-') as temp:
        tmp=Path(temp)
        measured=tmp/'PROFILE.json'
        measured.write_text(json.dumps(ep.build_profile([record()],current)))
        reg={'schema':'slab-039-prereg-v3','fixture':'ascend910','grid':32,'rule':{'k':5},
             'reducer_methods':{'methods':['random'],'seeds':[0],'search_evaluations_per_method':3,'reproduction_evaluations_per_method':1},
             'long_sa':{'seeds':[100],'max_evaluations_per_restart':5,'search_evaluations_per_restart':4,'reproduction_evaluations_per_restart':1,'max_cpu_minutes':1},
             'evidence_profile':{'path':str(measured),'sha256':hashlib.sha256(measured.read_bytes()).hexdigest(),'reserve_cpu_seconds':2,'reserve_reason':'synthetic test only','declared_calls':9}}
        path=tmp/'PREREG.json'
        path.write_text(json.dumps(reg))
        with patch.object(e,'execution_identity',return_value=current),patch.object(h.os,'fsync'):
            outcome=await h.run_headroom('ascend910',0,path,tmp/'output',oracle_factory=SyntheticProduction)
        spend=json.loads((tmp/'SPEND.json').read_bytes())
        lane=outcome['long_sa_results'][0]
        return {'admission':outcome['evidence_profile_admission'],'declaredLong':reg['long_sa'],'observedLong':{k:lane.get(k) for k in ('evaluation_count','search_evaluation_count','reproduction_evaluation_count','complete','stop_reason')},'verdict':outcome['verdict'],'passed':outcome['passed'],'aggregateEvaluations':outcome['aggregate_evaluations'],'persistedAttempt':spend['attempts'][-1],'allAttemptStatuses':[x['status'] for x in spend['attempts']]}
findings['declaredReproductionMismatch']=asyncio.run(run_counterexample())
findings['scope']='Synthetic numeric oracle only; not a thermal result or granted experiment.'
findings['blockedForbiddenAttempts']=blocked
(OUT/'ADVERSARIAL-FIXTURES.json').write_text(json.dumps(findings,indent=2)+'\n',encoding='utf-8')
print(json.dumps(findings),flush=True)
