"""Owned, bounded SLAB-018 Docker pipeline. Run on GB10 as its normal user."""
import argparse
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time
import urllib.request
import uuid

NEMO = 'nvcr.io/nvidia/nemo-automodel@sha256:70b4e9df8dd23ef451372b25952cffe24ad29c17f5b9de5fd1b244caf4e7b55a'
VLLM = 'sha256:2e735ffeef26457f8a3ff44a62ae182870b10af37adc06ecbb08baca152365c6'
DEADLINE = datetime.datetime(2026,10,31,10,tzinfo=datetime.timezone.utc).timestamp()
OWNER = 'sentilab-slab018-20261031'
STOPPING = False


def atomic(path, obj):
    temporary = path.with_suffix('.tmp')
    with temporary.open('w') as handle:
        json.dump(obj,handle,indent=2,allow_nan=False)
        handle.write('\n')
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary,path)


def command(args, timeout=15):
    result = subprocess.run(args,capture_output=True,text=True,timeout=timeout)
    if result.returncode:
        raise RuntimeError(f'Command {args[0:3]} failed: {result.stderr[-2000:]}')
    return result.stdout.strip()


def info(cid):
    return json.loads(command(['docker','inspect',cid]))[0]


def owned(cid, token):
    data=info(cid)
    labels=data['Config'].get('Labels',{})
    if labels.get('sentilab.owner') != OWNER or labels.get('sentilab.attempt') != token:
        raise RuntimeError('Refusing operation on container without exact owned identity')
    return data


def signal_stop(signum, frame):
    global STOPPING
    STOPPING = True


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('mode',choices=['run','status','stop'])
    parser.add_argument('--root',default='/home/dell/sentilab/preflight-20261031')
    args=parser.parse_args()
    root=Path(args.root).resolve()
    if root != Path('/home/dell/sentilab/preflight-20261031'):
        raise ValueError('Unexpected preflight directory')
    state_path=root/'execution-state.json'
    if args.mode=='status':
        print(state_path.read_text() if state_path.exists() else '{"status":"not_started"}')
        return
    if args.mode=='stop':
        (root/'STOP').touch(exist_ok=True)
        if state_path.exists():
            state=json.loads(state_path.read_text())
            active=state.get('active')
            if active:
                target=active.get('container_id') or active['name']
                owned(target,active['token'])
                try:
                    command(['docker','stop','--time','3',target],timeout=10)
                except (RuntimeError,subprocess.TimeoutExpired):
                    owned(target,active['token'])
                    command(['docker','kill',target],timeout=10)
        print('{"stop_requested":true}')
        return
    with (root/'execution.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        signal.signal(signal.SIGTERM,signal_stop)
        signal.signal(signal.SIGINT,signal_stop)
        if state_path.exists():
            state=json.loads(state_path.read_text())
        else:
            state={'schema':'sentilab-slab018-execution/1','attempts':[], 'active':None,
                   'gpu_container_wall_seconds':180.0,
                   'initial_charge':'Conservative 180-second reservation for prior primitive GPU container checks; not a measured usage claim.',
                   'max_gpu_seconds':3600,'max_attempts':3,'absolute_stop':'2026-10-31T10:00:00Z'}
        if state.get('active'):
            raise RuntimeError('Unreconciled prior stage: inspect exact owned container and account before resuming')
        if len(state['attempts'])>=3:
            raise RuntimeError('Three-attempt cap reached')
        if any(a.get('status')=='completed' for a in state['attempts']):
            raise RuntimeError('Preflight already completed; refusing duplicate training')
        def check():
            if STOPPING or (root/'STOP').exists() or time.time()>=DEADLINE-20:
                raise RuntimeError('STOP or deadline reached')
        check()
        # Verify immutable input identity before consuming an attempt or GPU.
        inputs=json.loads((root/'execution-inputs.json').read_text())
        for rel,expected in inputs['files'].items():
            p=(root/rel).resolve()
            if not p.is_relative_to(root) or not p.is_file():
                raise ValueError('Input path escapes root or is not a file')
            if hashlib.sha256(p.read_bytes()).hexdigest()!=expected:
                raise ValueError('Input changed: '+rel)
        token=uuid.uuid4().hex
        number=len(state['attempts'])+1
        output=root/f'attempt-{number:02d}'
        output.mkdir(exist_ok=False)
        attempt={'number':number,'token':token,'started_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
                 'input_manifest_sha256':hashlib.sha256((root/'execution-inputs.json').read_bytes()).hexdigest(),
                 'status':'running','stages':[]}
        state['attempts'].append(attempt)
        atomic(state_path,state)
        def stage(name, image, argv, http=False):
            check()
            allowance=int(min(3600-state['gpu_container_wall_seconds']-20,DEADLINE-time.time()-20))
            if allowance<=0:
                raise RuntimeError('GPU wall budget exhausted')
            start=time.monotonic()
            cname=f'{OWNER}-{number}-{name}'
            entry={'stage':name,'image':image,'name':cname,'token':token,'container_id':None,
                   'allowance_seconds':allowance,'started_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
            state['active']=entry
            atomic(state_path,state)
            # Built-in timeout remains effective even if SSH/supervisor disappears.
            docker=['docker','run','--detach','--init','--pull=never','--name',cname,
                '--label','sentilab.owner='+OWNER,'--label','sentilab.attempt='+token,
                '--gpus','all','--user',('0:0' if image==NEMO else '1000:1000'),'--memory','96g','--cpus','12','--shm-size','2g',
                '--cap-drop','ALL','--security-opt','no-new-privileges',
                '-e','HF_HUB_OFFLINE=1','-e','TRANSFORMERS_OFFLINE=1','-e','HF_HOME=/tmp/hf',
                '-e','HOME=/tmp','-e','TOKENIZERS_PARALLELISM=false',
                '-v',str(root)+'/model:/model:ro','-v',str(root)+':/work',
                '--workdir','/work','--entrypoint','timeout']
            if image==NEMO:
                # Root-only NeMo sources plus dell-owned0700worktree; only the
                # two capabilities needed for this mounted workspace are added.
                docker += ['--cap-add','DAC_OVERRIDE','--cap-add','CHOWN']
            docker += ['--publish','127.0.0.1:18018:8000'] if http else ['--network','none']
            docker += [image,'--signal=TERM','--kill-after=5s',str(allowance)+'s']+argv
            cid=None
            error=None
            try:
                cid=command(docker,timeout=20)
                entry['container_id']=cid
                data=owned(cid,token)
                entry['image_id']=data['Image']
                entry['pid']=data['State']['Pid']
                entry['container_started_at']=data['State']['StartedAt']
                atomic(state_path,state)
                client=None
                while True:
                    check()
                    if time.monotonic()-start>=allowance:
                        raise RuntimeError('Stage allowance reached')
                    data=owned(cid,token)
                    if not data['State']['Running']:
                        if data['State']['ExitCode']!=0:
                            raise RuntimeError('Container exit '+str(data['State']['ExitCode']))
                        if http:
                            raise RuntimeError('Server exited before HTTP evaluation completed')
                        break
                    if http:
                        if client is None:
                            try:
                                with urllib.request.urlopen('http://127.0.0.1:18018/health',timeout=1) as response:
                                    if response.status==200:
                                        client=subprocess.Popen(['python3',str(root/'http_eval.py'),str(output)],
                                              stdout=(output/'http-client.log').open('w'),stderr=subprocess.STDOUT)
                            except (OSError,TimeoutError):
                                pass
                        elif client.poll() is not None:
                            if client.returncode!=0:
                                raise RuntimeError('HTTP evaluation failed')
                            break
                    time.sleep(1)
            except BaseException as exc:
                error=f'{type(exc).__name__}: {exc}'
                raise
            finally:
                charged=None
                if http and 'client' in locals() and client is not None and client.poll() is None:
                    client.terminate()
                    try:client.wait(timeout=3)
                    except subprocess.TimeoutExpired:client.kill();client.wait()
                # Name is deterministic and identity labels are required even if
                # docker run returned ambiguously before the ID could be saved.
                try:
                    target=cid or cname
                    data=owned(target,token)
                    if data['State']['Running']:
                        try:
                            command(['docker','stop','--time','3',target],timeout=10)
                        except (RuntimeError,subprocess.TimeoutExpired):
                            owned(target,token)
                            command(['docker','kill',target],timeout=10)
                    stopped=owned(target,token)
                    if stopped['State']['Running']:
                        raise RuntimeError('Owned container still running after stop')
                    # Charge launch-to-confirmed-stop, excluding post-stop log
                    # archival/removal CPU. GPU cannot run in a stopped container.
                    charged=time.monotonic()-start
                    logs=subprocess.run(['docker','logs','--timestamps',target],capture_output=True,text=True,timeout=10)
                    if logs.returncode:
                        raise RuntimeError('Could not preserve container logs')
                    (output/(name+'.stdout.log')).write_text(logs.stdout)
                    (output/(name+'.stderr.log')).write_text(logs.stderr)
                    final=owned(target,token)
                    entry['exit_code']=final['State']['ExitCode']
                    command(['docker','rm',target],timeout=10)
                except Exception as cleanup_error:
                    entry['cleanup_error']=str(cleanup_error)
                elapsed=time.monotonic()-start
                if charged is None:
                    charged=max(elapsed,allowance+20)
                entry.update({'charged_container_wall_seconds':charged,'supervisor_stage_seconds':elapsed,'error':error,
                              'finished_at':datetime.datetime.now(datetime.timezone.utc).isoformat()})
                state['gpu_container_wall_seconds']+=charged
                attempt['stages'].append(entry.copy())
                # An ambiguous cleanup stays active and blocks automatic retry.
                state['active']=entry if entry.get('cleanup_error') else None
                atomic(state_path,state)
            if entry.get('cleanup_error'):
                raise RuntimeError('Cleanup unresolved')
        try:
            out='/work/'+output.name
            stage('train',NEMO,['python3','/work/model_stage.py','train','--output',out])
            stage('evaluate',NEMO,['python3','/work/model_stage.py','evaluate','--output',out])
            stage('serve',VLLM,['python3','-m','vllm.entrypoints.openai.api_server',
                '--model','/model','--served-model-name','base','--enable-lora',
                '--lora-modules','fixture='+out+'/adapter','--max-lora-rank','8',
                '--max-model-len','1024','--gpu-memory-utilization','0.35','--enforce-eager',
                '--dtype','bfloat16','--host','0.0.0.0','--port','8000'],http=True)
            check()
            evaluated=json.loads((output/'evaluation.json').read_text())
            served=json.loads((output/'http-result.json').read_text())
            assert served['requests']==40
            if state['gpu_container_wall_seconds']>3600 or state['active'] is not None or time.time()>=DEADLINE:
                raise RuntimeError('Final resource/deadline/cleanup gate failed')
            if command(['docker','ps','--filter','label=sentilab.owner='+OWNER,'--format','{{.ID}}']):
                raise RuntimeError('Owned container remains running')
            attempt['status']='completed' if evaluated['changed_outputs']>0 else 'plumbing_finished_difference_requirement_unmet'
        except BaseException as exc:
            attempt['status']='failed'
            attempt['error']=f'{type(exc).__name__}: {exc}'
            raise
        finally:
            attempt['finished_at']=datetime.datetime.now(datetime.timezone.utc).isoformat()
            atomic(state_path,state)
            atomic(output/'attempt-receipt.json',attempt)


if __name__=='__main__':
    main()
