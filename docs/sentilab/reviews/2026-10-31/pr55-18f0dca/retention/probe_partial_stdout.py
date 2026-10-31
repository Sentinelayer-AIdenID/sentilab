"""Bounded protocol peer; no HotSpot, model, device or network calls."""
import asyncio, hashlib, json, pathlib, sys, tempfile
from unittest.mock import patch
SOURCE=pathlib.Path(sys.argv[1]).resolve()
sys.path.insert(0,str(SOURCE))
from sundai_hotspot import tap_oracle as tap
OUT=pathlib.Path(__file__).parent

async def main():
    results=[]
    with tempfile.TemporaryDirectory(prefix='pr55-partial-peer-') as tmp:
        root=pathlib.Path(tmp)
        script=root/'protocol_peer.py'
        script.write_text('import sys,json,time,pathlib\nfor line in sys.stdin.buffer:\n r=json.loads(line)\n p=b\'{"ok":true,"result":{"partial":\'\n sys.stdout.buffer.write(p)\n sys.stdout.buffer.flush()\n pathlib.Path(r["retained_output_root"],"peer-emitted-prefix.bin").write_bytes(p)\n time.sleep(5)\n')
        retained=root/'retained'
        with patch.object(tap,'WORKER',script):
            worker=await tap._WarmWorker.start()
            try:
                try:
                    await worker.evaluate({'retained_output_root':str(retained),'bounded_call':True},worker_timeout_s=0.3)
                except Exception as e:
                    error={'type':type(e).__name__,'message':str(e)}
                else: raise AssertionError('peer unexpectedly returned')
            finally:
                await worker.close()
        emitted=(retained/'peer-emitted-prefix.bin').read_bytes()
        response=retained/'worker-response.bin'
        observed=response.read_bytes() if response.exists() else None
        for name in ['WORKER.json','worker-request.bin','worker-stderr.bin','peer-emitted-prefix.bin','worker-response.bin']:
            if (retained/name).exists(): (OUT/name).write_bytes((retained/name).read_bytes())
        results.append({'case':'timeout_after_flushed_partial_worker_stdout','emitted':emitted.decode(),'emittedBytes':len(emitted),'retainedResponseExists':response.exists(),'retainedResponseBytes':None if observed is None else len(observed),'error':error,'workerReturnCode':worker.process.returncode,'workspaceRemoved':not pathlib.Path(worker.workspace.name).exists(),'newWorkerCount':1,'realSolverCalls':0,'interpretation':'Peer witness proves bytes flushed before timeout; production exchange writes response only after complete readline'})
    result={'head':'18f0dcaea086c7817990112398d358bcd28dbe07','results':results,'sourceSha256':hashlib.sha256((SOURCE/'sundai_hotspot/tap_oracle.py').read_bytes()).hexdigest()}
    (OUT/'PARTIAL-RESULT.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))
asyncio.run(main())
