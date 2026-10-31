"""Fixed, separately approved SLAB047b non-GPU scratch preflight. No caller paths."""
from contextlib import contextmanager
import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import selectors
import stat
import subprocess
import sys
import time
import uuid

ROOT = Path('/home/dell/sentilab/serving-20261031b/preflight')
PROGRAM = 'preflight047b.py'
OWNER = 'sentilab-slab047b-preflight-20261031'
GRANT = '55fe3cab-88b4-4f80-9ae7-2f5ff43c70f7'
IMAGE = 'sha256:2e735ffeef26457f8a3ff44a62ae182870b10af37adc06ecbb08baca152365c6'
TMPFS = 'rw,exec,nosuid,nodev,size=4g,mode=1777'
START_BY = 1793448900.0  # 2026-10-31T12:15:00Z; preflight must finish before GPU admission.
MAX_SECONDS = 120
CLEANUP_RESERVE = 30
LIMIT = 524288
C_SOURCE = b'int sentilab_047b(void) { return 47; }\n'
SCRIPT = b'#!/usr/bin/python3\nraise SystemExit(47)\n'


class Refusal(RuntimeError):
    pass


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def strict(raw):
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise Refusal('duplicate_json_key')
            value[key] = item
        return value
    def constant(value):
        raise Refusal('nonfinite_json')
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)


def stamp():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


@contextmanager
def root_fd():
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in ROOT.parts[1:]:
            new = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = new
        info = os.fstat(fd)
        if info.st_uid != os.geteuid() or info.st_mode & 0o077:
            raise Refusal('unsafe_preflight_root')
        yield fd
    finally:
        os.close(fd)


def read(name, limit=LIMIT):
    with root_fd() as folder:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=folder)
        with os.fdopen(fd, 'rb') as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
                raise Refusal('unsafe_or_oversized_artifact')
            raw = handle.read(limit + 1)
            if len(raw) > limit:
                raise Refusal('oversized_artifact')
            return raw


def write(name, raw):
    with root_fd() as folder:
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=folder)
        with os.fdopen(fd, 'wb') as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.fsync(folder)


def save_state(value):
    temporary = '.state-' + uuid.uuid4().hex
    write(temporary, encode(value))
    with root_fd() as folder:
        os.replace(temporary, 'state.json', src_dir_fd=folder, dst_dir_fd=folder)
        os.fsync(folder)


@contextmanager
def lock():
    import fcntl
    with root_fd() as folder:
        fd = os.open('run.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600, dir_fd=folder)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise Refusal('unsafe_lock')
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Refusal('preflight_busy') from None
        yield
    finally:
        os.close(fd)


def validate_host():
    import pwd
    if (platform.node(), platform.machine(), pwd.getpwuid(os.geteuid()).pw_name) != ('promaxgb10-9a1e', 'aarch64', 'dell'):
        raise Refusal('device_identity_mismatch')
    with root_fd():
        pass


def check(intent):
    if (ROOT / 'STOP').exists() or (ROOT.parent / 'STOP').exists():
        raise Refusal('stop_requested')
    remaining = min(intent['deadline_unix'] - time.time(), intent['deadline_monotonic'] - time.monotonic())
    if remaining <= CLEANUP_RESERVE:
        raise Refusal('preflight_cleanup_reserve')
    return remaining - CLEANUP_RESERVE


def command(args, timeout=5):
    """Only fixed Docker argv; bounded pipes; signal only the unreaped owned child."""
    argv = ['/usr/bin/docker', '--host', 'unix:///var/run/docker.sock', *args]
    process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               close_fds=True, shell=False,
                               env={'PATH': '/usr/bin:/bin', 'HOME': '/home/dell', 'LANG': 'C',
                                    'DOCKER_CONFIG': str(ROOT / 'docker-config')})
    chunks = [bytearray(), bytearray()]
    end = time.monotonic() + timeout
    try:
        with selectors.DefaultSelector() as selector:
            for index, stream in enumerate((process.stdout, process.stderr)):
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, selectors.EVENT_READ, index)
            while selector.get_map() or process.poll() is None:
                if time.monotonic() >= end:
                    raise Refusal('docker_command_timeout')
                for key, _ in selector.select(min(0.05, max(0, end - time.monotonic()))):
                    raw = os.read(key.fileobj.fileno(), 4096)
                    if not raw:
                        selector.unregister(key.fileobj)
                    else:
                        target = chunks[key.data]
                        target.extend(raw)
                        if len(target) > LIMIT:
                            raise Refusal('docker_output_limit')
        return process.returncode, bytes(chunks[0]), bytes(chunks[1])
    finally:
        if process.poll() is None:
            process.kill()
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            pass
        process.stdout.close()
        process.stderr.close()


def docker(args, timeout=5):
    code, raw, err = command(args, timeout)
    if code:
        raise Refusal('docker_command_failed')
    return raw


# Executed only inside the one authorized, non-GPU container. No model imports.
PROBE = r'''import ctypes,hashlib,json,os,pathlib,resource,subprocess
resource.setrlimit(resource.RLIMIT_FSIZE,(1048576,1048576))
base=pathlib.Path('/tmp/.triton/cache/slab047b-probe')
c=C_LITERAL
script=SCRIPT_LITERAL
proof={'schema':'sentilab-047b-scratch-proof/1','uid':os.getuid(),'gid':os.getgid(),'euid':os.geteuid(),'egid':os.getegid(),'tmp_mode':os.stat('/tmp').st_mode&0o7777,'hashes':{},'nvidia_devices':sorted(str(p) for p in pathlib.Path('/dev').glob('nvidia*')),'nvidia_visible_devices':os.environ.get('NVIDIA_VISIBLE_DEVICES'),'cuda_visible_devices':os.environ.get('CUDA_VISIBLE_DEVICES'),'error':None}
try:
 with open('/proc/self/mountinfo','rb') as f:mountinfo=f.read(131073)
 assert len(mountinfo)<=131072
 proof['mountinfo']=mountinfo.decode()
 base.parent.mkdir(parents=True,exist_ok=True)
 base.mkdir(mode=0o700)
 for name,raw in [('tiny.c',c),('tiny.py',script)]:
  with (base/name).open('xb') as f:f.write(raw)
 os.chmod(base/'tiny.py',0o700)
 with (base/'compiler.stdout').open('xb') as out,(base/'compiler.stderr').open('xb') as err:
  completed=subprocess.run(['/usr/bin/cc','-shared','-fPIC','-O0','-o',str(base/'tiny.so'),str(base/'tiny.c')],stdin=subprocess.DEVNULL,stdout=out,stderr=err,shell=False,timeout=15)
 proof['compiler_returncode']=completed.returncode
 assert completed.returncode==0
 library=ctypes.CDLL(str(base/'tiny.so'))
 function=library.sentilab_047b
 function.argtypes=[];function.restype=ctypes.c_int
 proof['library_result']=function()
 executed=subprocess.run([str(base/'tiny.py')],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,shell=False,timeout=5)
 proof['script_returncode']=executed.returncode
 assert proof['library_result']==47 and executed.returncode==47 and executed.stdout==b'' and executed.stderr==b''
except BaseException as exc:
 proof['error']=type(exc).__name__+': '+str(exc)[:4096]
finally:
 for name in ('tiny.c','tiny.py','tiny.so','compiler.stdout','compiler.stderr'):
  path=base/name
  if path.is_file():
   with path.open('rb') as f:raw=f.read(1048577)
   assert len(raw)<=1048576
   proof['hashes'][name]={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
   if name.startswith('compiler.'):proof[name+'_tail']=raw[-4096:].decode(errors='replace')
print(json.dumps(proof,sort_keys=True,separators=(',',':')),flush=True)
raise SystemExit(1 if proof['error'] else 0)
'''.replace('C_LITERAL', repr(C_SOURCE)).replace('SCRIPT_LITERAL', repr(SCRIPT))


def create_argv(intent):
    wrapper = ('import os,time,math; r=min(45,' + repr(intent['deadline_unix'] - CLEANUP_RESERVE)
               + '-time.time(),' + repr(intent['deadline_monotonic'] - CLEANUP_RESERVE)
               + '-time.monotonic()); os._exit(3) if r<=5 else None; '
               'os.execvp("timeout",["timeout","--signal=TERM","--kill-after=3s",str(math.floor(r-3))+"s",'
               '"/usr/bin/python3","-I","-S","-B","-c",' + repr(PROBE) + '])')
    args = ['create', '--init', '--pull=never', '--runtime=runc', '--name', intent['container_name']]
    for key, value in labels(intent).items():
        args += ['--label', key + '=' + value]
    return args + ['--user', '1000:1000', '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
                   '--network', 'none', '--memory', '96g', '--cpus', '12', '--shm-size', '2g', '--pids-limit', '64',
                   '--tmpfs', '/tmp:' + TMPFS, '--log-opt', 'max-size=1m', '--log-opt', 'max-file=1',
                   '-e', 'HOME=/tmp', '-e', 'HF_HOME=/tmp/hf', '-e', 'TMPDIR=/tmp',
                   '-e', 'NVIDIA_VISIBLE_DEVICES=void', '-e', 'CUDA_VISIBLE_DEVICES=-1',
                   '--entrypoint', '/usr/bin/python3', IMAGE, '-I', '-S', '-B', '-c', wrapper]


def labels(intent):
    return {'sentilab.owner': OWNER, 'sentilab.attempt': intent['token'],
            'sentilab.preflight-source': intent['preflight_sha256'], 'sentilab.grant': GRANT}


def owned(cid, intent, absent_ok=False):
    if not re.fullmatch('[0-9a-f]{64}', cid):
        raise Refusal('full_container_id_required')
    fmt = '{"Id":{{json .Id}},"Image":{{json .Image}},"Name":{{json .Name}},"Labels":{{json .Config.Labels}},"User":{{json .Config.User}},"Entrypoint":{{json .Config.Entrypoint}},"State":{{json .State}},"HostConfig":{{json .HostConfig}},"Mounts":{{json .Mounts}}}'
    code, raw, err = command(['inspect', '--format', fmt, cid], 3)
    if code:
        ids = docker(['ps', '-a', '--no-trunc', '--format', '{{.ID}}'], 3).decode().splitlines()
        if absent_ok and cid not in ids:
            return None
        raise Refusal('container_inspection_failed')
    value = strict(raw)
    if value['Id'] != cid or value['Image'] != IMAGE or value['Name'] != '/' + intent['container_name'] or any(value['Labels'].get(k) != v for k, v in labels(intent).items()):
        raise Refusal('container_identity_mismatch')
    return value


def validate_config(value):
    config = value['HostConfig']
    if (value['User'] != '1000:1000' or value['Entrypoint'] != ['/usr/bin/python3']
        or config.get('Tmpfs') != {'/tmp': TMPFS} or config.get('Runtime') != 'runc'
        or config.get('DeviceRequests') or config.get('Devices') or config.get('Binds') or config.get('Mounts')
        or config.get('Privileged') or config.get('ReadonlyRootfs') is not True or config.get('NetworkMode') != 'none'
        or config.get('PortBindings') or config.get('CapAdd') or 'ALL' not in config.get('CapDrop', [])
        or config.get('Memory') != 96 * 1024 ** 3 or config.get('NanoCpus') != 12000000000
        or config.get('ShmSize') != 2 * 1024 ** 3 or config.get('PidsLimit') != 64
        or not any(x in ('no-new-privileges', 'no-new-privileges=true') for x in config.get('SecurityOpt', []))
        or any(x.get('Type') != 'tmpfs' or x.get('Destination') != '/tmp' for x in value['Mounts'])):
        raise Refusal('unexpected_container_configuration')


def validate_proof(raw):
    proof = strict(raw)
    if (proof['schema'] != 'sentilab-047b-scratch-proof/1' or proof.get('error') is not None
        or any(proof[k] != 1000 for k in ('uid', 'gid', 'euid', 'egid'))
        or proof['tmp_mode'] != 0o1777 or proof['compiler_returncode'] != 0 or proof['library_result'] != 47
        or proof['script_returncode'] != 47 or proof['nvidia_devices']
        or proof['nvidia_visible_devices'] != 'void' or proof['cuda_visible_devices'] != '-1'
        or proof['hashes']['tiny.c'] != {'bytes': len(C_SOURCE), 'sha256': digest(C_SOURCE)}
        or proof['hashes']['tiny.py'] != {'bytes': len(SCRIPT), 'sha256': digest(SCRIPT)}
        or not re.fullmatch('[0-9a-f]{64}', proof['hashes']['tiny.so']['sha256'])
        or not 0 < proof['hashes']['tiny.so']['bytes'] <= 1048576):
        raise Refusal('scratch_execution_proof_failed')
    mounts = {}
    for line in proof['mountinfo'].splitlines():
        fields = line.split()
        if len(fields) < 10 or '-' not in fields:
            raise Refusal('invalid_mountinfo')
        if fields[4] in ('/', '/tmp'):
            if fields[4] in mounts:
                raise Refusal('ambiguous_mountinfo')
            mounts[fields[4]] = (set(fields[5].split(',')), fields[fields.index('-') + 1])
    if ('/' not in mounts or '/tmp' not in mounts or 'ro' not in mounts['/'][0]
        or mounts['/tmp'][1] != 'tmpfs' or not {'rw', 'nosuid', 'nodev'} <= mounts['/tmp'][0]
        or 'noexec' in mounts['/tmp'][0]):
        raise Refusal('effective_mount_policy_failed')
    return proof


def retain_logs(cid):
    code, out, err = command(['logs', '--timestamps', '--tail', '100', cid], 3)
    if code:
        raise Refusal('logs_not_retained')
    for name, raw in [('probe.stdout.log', out), ('probe.stderr.log', err)]:
        if not (ROOT / name).exists():
            write(name, raw)
    return out


def cleanup(intent):
    state = strict(read('state.json'))
    cid = state.get('container_id')
    if not cid:
        ids = docker(['ps', '-a', '--no-trunc', '--filter', 'name=^/' + intent['container_name'] + '$', '--format', '{{.ID}}'], 3).decode().splitlines()
        if len(ids) > 1:
            raise Refusal('ambiguous_container_identity')
        cid = ids[0] if ids else None
    if not cid:
        if state.get('create_intent') and not state.get('create_returned'):
            raise Refusal('ambiguous_create_unresolved')
        return True
    value = owned(cid, intent, absent_ok=state.get('container_removed') is True)
    if value is not None:
        if value['State']['Running']:
            try:
                docker(['stop', '--time', '1', cid], 4)
            except Refusal:
                if owned(cid, intent)['State']['Running']:
                    docker(['kill', cid], 3)
        if owned(cid, intent)['State']['Running']:
            raise Refusal('container_still_running')
        retain_logs(cid)
        owned(cid, intent)
        docker(['rm', cid], 3)
        if owned(cid, intent, absent_ok=True) is not None:
            raise Refusal('container_removal_unconfirmed')
    state.update(container_id=cid, container_removed=True)
    save_state(state)
    return True


def admission(source):
    raw = read('APPROVED.json', 8192)
    approval = strict(raw)
    keys = {'schema', 'grant_source', 'preflight_sha256', 'decision', 'reviewer', 'review_record'}
    if (set(approval) != keys or approval['schema'] != 'sentilab-047b-preflight-review/1'
        or approval['grant_source'] != GRANT or approval['preflight_sha256'] != digest(source)
        or approval['decision'] != '+1' or not isinstance(approval['reviewer'], str) or not approval['reviewer'].strip()
        or approval['reviewer'] in {'gpt-astra-carter', 'science_redteam', 'requirements_audit'}
        or not isinstance(approval['review_record'], str) or not approval['review_record'].strip()):
        raise Refusal('exact_preflight_review_required')
    return raw


def run(source):
    with lock():
        approval = admission(source)
        now, mono = time.time(), time.monotonic()
        budget = min(MAX_SECONDS, START_BY - now)
        if budget <= CLEANUP_RESERVE + 10 or (ROOT / 'STOP').exists() or (ROOT.parent / 'STOP').exists():
            raise Refusal('preflight_admission_expired_or_stopped')
        token = uuid.uuid4().hex
        intent = {'schema': 'sentilab-047b-preflight-intent/1', 'grant_source': GRANT, 'token': token, 'attempt': 1,
                  'preflight_sha256': digest(source), 'approval_bytes': approval.decode(), 'approval_sha256': digest(approval),
                  'reserved_at': stamp(), 'reserved_unix': now, 'reserved_monotonic': mono,
                  'deadline_unix': now + budget, 'deadline_monotonic': mono + budget,
                  'container_name': OWNER + '-' + token, 'max_seconds': MAX_SECONDS, 'gpu_requested': False, 'retry_allowed': False}
        try:
            write('intent.json', encode(intent))
        except FileExistsError:
            raise Refusal('preflight_attempt_consumed') from None
        state = {'create_intent': False, 'create_returned': False, 'container_id': None}
        save_state(state)
        error, cleanup_error, proof_ok, closed = None, None, False, False
        try:
            check(intent)
            state['create_intent'] = True
            save_state(state)
            check(intent)
            cid = docker(create_argv(intent), min(10, check(intent))).decode().strip()
            if not re.fullmatch('[0-9a-f]{64}', cid):
                raise Refusal('invalid_create_id')
            state.update(container_id=cid, create_returned=True)
            save_state(state)
            inspected = owned(cid, intent)
            write('inspection-created.json', encode(inspected))
            validate_config(inspected)
            docker(['start', cid], min(5, check(intent)))
            while True:
                check(intent)
                inspected = owned(cid, intent)
                if not inspected['State']['Running']:
                    break
                time.sleep(0.25)
            write('inspection-finished.json', encode(inspected))
            validate_config(inspected)
            raw = retain_logs(cid)
            # Docker timestamps prefix the single JSON line; retain the complete raw tail as well.
            lines = raw.splitlines()
            if len(lines) != 1 or b' ' not in lines[0]:
                raise Refusal('invalid_probe_output')
            proof_raw = lines[0].split(b' ', 1)[1]
            write('probe.stdout.json', proof_raw)
            if inspected['State']['ExitCode'] != 0:
                raise Refusal('probe_container_failed')
            validate_proof(proof_raw)
            proof_ok = True
        except BaseException as exc:
            error = str(exc) if isinstance(exc, Refusal) else type(exc).__name__
        finally:
            try:
                closed = cleanup(intent)
            except BaseException as exc:
                cleanup_error = str(exc) if isinstance(exc, Refusal) else type(exc).__name__
        elapsed = max(0, time.monotonic() - mono)
        hashes = {}
        for name in ('intent.json', 'inspection-created.json', 'inspection-finished.json', 'probe.stdout.json', 'probe.stdout.log', 'probe.stderr.log'):
            if (ROOT / name).is_file():
                hashes[name] = digest(read(name))
        result = {'schema': 'sentilab-047b-preflight-result/1', 'grant_source': GRANT, 'token': token,
                  'preflight_sha256': digest(source), 'image': IMAGE, 'tmpfs': TMPFS,
                  'preflight_ok': error is None and proof_ok and closed and elapsed <= MAX_SECONDS and time.time() < START_BY,
                  'probe_verified': proof_ok, 'cleanup_verified': closed, 'error': error, 'cleanup_error': cleanup_error,
                  'charged_seconds': elapsed if closed else max(MAX_SECONDS, elapsed), 'budget_exceeded': elapsed > MAX_SECONDS,
                  'finished_at': stamp(), 'gpu_requested': False, 'retry_allowed': False, 'hashes': hashes,
                  'scope': 'fixed /tmp native mapping and direct script execution only; no vLLM, JIT, GPU or inference readiness claim'}
        write('result.json', encode(result))
        return result


def operate(action, source):
    validate_host()
    if action == 'run':
        return run(source)
    if action == 'status':
        return strict(read('result.json'))
    if action == 'cleanup':
        with lock():
            intent = strict(read('intent.json'))
            if intent['preflight_sha256'] != digest(source) or intent['grant_source'] != GRANT:
                raise Refusal('cleanup_source_mismatch')
            closed = cleanup(intent)
            result = {'cleanup_verified': closed, 'token': intent['token'], 'at': stamp(),
                      'charged_seconds': max(0, time.monotonic() - intent['reserved_monotonic']),
                      'retry_allowed': False, 'preflight_ok': False}
            write('cleanup-recovery.json', encode(result))
            return result
    raise Refusal('invalid_action')


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in {'run', 'status', 'cleanup'}:
        raise SystemExit(2)
    source = globals().get('APPROVED_SOURCE')
    if source is None:
        # Freeze exactly the installed bytes before any Docker effect or intent.
        raw = read(PROGRAM, 65536)
        exec(compile(raw, str(ROOT / PROGRAM), 'exec'),
             {'__name__': '__main__', '__file__': str(ROOT / PROGRAM), 'APPROVED_SOURCE': raw})
        return
    try:
        result = operate(sys.argv[1], source)
        print(encode(result).decode())
    except (Refusal, OSError, ValueError, KeyError, TypeError) as exc:
        print(encode({'preflight_ok': False, 'error': str(exc) if isinstance(exc, Refusal) else type(exc).__name__}).decode())
        raise SystemExit(1)


if __name__ == '__main__':
    main()
