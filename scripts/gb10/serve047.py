"""Fixed-root SLAB047 controller. Deployment and execution require external review.

Only the installed program is executable: start/status/stop. All policy, inputs,
request bodies and container arguments are fixed; there are no caller overrides.
"""
from contextlib import contextmanager
import datetime
import errno
import hashlib
import http.client
import json
import math
import os
from pathlib import Path
import platform
import re
import socket
import stat
import subprocess
import sys
import threading
import time
import uuid

ROOT = Path('/home/dell/sentilab/serving-20261031')
RETAINED = Path('/home/dell/sentilab/preflight-20261031')
PROGRAM = 'serve047.py'
SCHEMA = 'sentilab-gb10-serving/1'
OWNER = 'sentilab-slab047-20261031'
IMAGE = 'sha256:2e735ffeef26457f8a3ff44a62ae182870b10af37adc06ecbb08baca152365c6'
PORT = 18047
START_BY = 1793447100.0  # 2026-10-31T11:45:00Z
ABSOLUTE_STOP = 1793448000.0  # 2026-10-31T12:00:00Z
MAX_SECONDS = 900
CLEANUP_RESERVE = 60
MAX_SOURCE = 65536
MAX_RESPONSE = 1048576
POLICY = {
    'schema': 'sentilab-slab047-policy/1',
    'grant_sequence': 56496,
    'grant_source': 'bb58c601-464f-4ebc-89f1-5b6eba9aeb25',
    'ticket': '1509c616-03ee-4d35-b60c-bc70dd18b7fe',
    'max_attempts': 1, 'max_gpu_seconds_including_startup_cleanup': MAX_SECONDS,
    'start_before': '2026-10-31T11:45:00Z', 'absolute_stop': '2026-10-31T12:00:00Z',
    'max_inference_requests': 20, 'image_id': IMAGE, 'localhost_port': PORT,
    'scope': 'six repeated training-source fixture cases with labels; no generalization',
}
# Generated from committed SLAB018 model/fixture/artifact metadata, not remote claims.
INPUTS = (('model/.gitattributes', 1570, '34448b82c17d60fec9b65b1f093c115ddbaadc04beb1b0140b6bfed2e012a930'), ('model/LICENSE', 11343, '832dd9e00a68dd83b3c3fb9f5588dad7dcf337a0db50f7d9483f310cd292e92e'), ('model/README.md', 8168, '8e3dd0c3b5b11897cc71092ccfe517bb7a9783479baa3665aad73c8d1a2041cd'), ('model/config.json', 727, '5beea1a4a34c62782bfb2f911c606741a3bab8f92d80a118fa053c28af12e8ba'), ('model/generation_config.json', 238, '835fffe355c9438e7a25be099b3fccaa98350b83451f9fd2d99512e74f1ade48'), ('model/merges.txt', 1671839, '599bab54075088774b1733fde865d5bd747cbcc7a547c5bc12610e874e26f5e3'), ('model/model-00001-of-00003.safetensors', 3957900840, '75311d91bb08cf0b882913da464a1e722a31fb44db35208663487efb7a3d8ed6'), ('model/model-00002-of-00003.safetensors', 3987450520, '0b48adbb1f60e901153d91907ba11ce63bd4b8b584482e730f48808d055dfba1'), ('model/model-00003-of-00003.safetensors', 99630640, '7dd39ccca5e4de123c74c14af44c9bf2eb75df33b4614382af0134528e060d5d'), ('model/model.safetensors.index.json', 32819, 'd6c42883a895dfef5b0080ed2116a1bcd764f558406b98923d675978a1abf29c'), ('model/tokenizer.json', 11422654, 'aeb13307a71acd8fe81861d94ad54ab689df773318809eed3cbe794b4492dae4'), ('model/tokenizer_config.json', 9377, 'a62ff0a2472a0fa1b8eaabcb57c59b58afa42a22831dc141400b6e0cf2b65ce3'), ('model/vocab.json', 2776833, 'ca10d7e9fb3ed18575dd1e277a2579c16d108e32f27439684afa0e10b1440910'), ('attempt-01/adapter/adapter_model.safetensors', 66126768, '695581e310def332bd6307527eff6546d95eebb88bec7e6f6ce288a5a61c0f80'), ('attempt-01/adapter/adapter_config.json', 1035, 'ef6104b4d006baf86f90ddf1d0fc32a12a3951b70bfe3c2a0f06afcf5bdb413c'), ('attempt-01/execution-inputs.json', 2361, '230fd89ad116537c30cfd2c934d0ccae28dd4acec5d7b3361e1bd16bbecf1357'), ('fixtures/eval.jsonl', 33054, 'c2fea4f049385c6f85108d0afc4ffad1ba776be0be6319f46d9086d8564e1231'))


class Refusal(RuntimeError):
    pass


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


POLICY_BYTES = encode(POLICY)
POLICY_SHA = digest(POLICY_BYTES)


def stamp():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise Refusal('duplicate_json_key')
            result[key] = value
        return result
    def constant(value):
        raise Refusal('nonfinite_json')
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)


def safe_read(path, limit):
    """Open every Linux path component without following links; bound bytes."""
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts:
        raise Refusal('unsafe_path')
    handles = []
    try:
        if os.name == 'posix':
            parent = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            handles.append(parent)
            for part in path.parts[1:-1]:
                parent = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                handles.append(parent)
            fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        else:  # Local fake-test portability, never remote Windows execution.
            if path.is_symlink():
                raise Refusal('unsafe_path')
            fd = os.open(path, os.O_RDONLY | os.O_BINARY)
        handles.append(fd)
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
            raise Refusal('unsafe_or_oversize_file')
        raw = bytearray()
        while chunk := os.read(fd, min(1048576, limit + 1 - len(raw))):
            raw.extend(chunk)
            if len(raw) > limit:
                raise Refusal('oversize_file')
        after = os.fstat(fd)
        if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise Refusal('file_changed')
        return bytes(raw)
    finally:
        for fd in reversed(handles):
            os.close(fd)


def sync_directory():
    if os.name == 'posix':
        fd = os.open(ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def write_exclusive(name, raw):
    fd = os.open(ROOT / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(fd, 'wb') as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    sync_directory()


def atomic(name, value):
    temporary = '.write-' + uuid.uuid4().hex
    write_exclusive(temporary, encode(value) + b'\n')
    os.replace(ROOT / temporary, ROOT / name)
    sync_directory()


@contextmanager
def lock(name, wait=3):
    import fcntl
    fd = os.open(ROOT / name, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    deadline = time.monotonic() + wait
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise Refusal('unsafe_lock')
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise Refusal('controller_busy')
                time.sleep(0.02)
        yield
    finally:
        os.close(fd)


def root_identity():
    import pwd
    return {'hostname': platform.node(), 'architecture': platform.machine(),
            'login': pwd.getpwuid(os.geteuid()).pw_name}


def validate_root():
    if root_identity() != {'hostname': 'promaxgb10-9a1e', 'architecture': 'aarch64', 'login': 'dell'}:
        raise Refusal('device_identity_mismatch')
    # Root must provision the new directory, controller and approval. No implicit installation.
    info = ROOT.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
        raise Refusal('unsafe_serving_root')
    current = ROOT.parent
    while current != current.parent:
        if current.is_symlink():
            raise Refusal('unsafe_serving_ancestor')
        current = current.parent


def command(argv, timeout=5, limit=32768):
    """Bound trusted CLI output and deadline; signal only the unreaped child."""
    environment = {'PATH': '/usr/bin:/bin', 'HOME': '/home/dell', 'LANG': 'C',
                   'DOCKER_CONFIG': str(ROOT / 'docker-config')}
    process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, shell=False, close_fds=True, env=environment)
    buffers = [bytearray(), bytearray()]
    overflow = threading.Event()
    def consume(stream, target):
        try:
            while chunk := stream.read(min(4096, limit + 1 - len(target))):
                target.extend(chunk)
                if len(target) > limit:
                    overflow.set()
                    return
        except (OSError, ValueError):
            overflow.set()
    readers = [threading.Thread(target=consume, args=(stream, target), daemon=True)
               for stream, target in zip((process.stdout, process.stderr), buffers)]
    end = time.monotonic() + timeout
    try:
        for thread in readers:
            thread.start()
        while process.poll() is None or any(thread.is_alive() for thread in readers):
            if overflow.is_set() or time.monotonic() >= end:
                raise Refusal('command_ambiguous')
            time.sleep(0.01)
        return process.returncode, bytes(buffers[0]), bytes(buffers[1])
    finally:
        if process.poll() is None:
            process.kill()
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            pass
        for stream in (process.stdout, process.stderr):
            stream.close()
        for thread in readers:
            thread.join(timeout=0.1)


def docker(*args, timeout=5):
    rc, out, err = command(docker_argv(*args), timeout=timeout)
    if rc:
        raise Refusal('docker_command_failed')
    return out


def docker_argv(*args):
    # Never inherit a cloud Docker context or caller-controlled host selection.
    return ['/usr/bin/docker', '--host', 'unix:///var/run/docker.sock', *args]


def reservation():
    value = strict_json(safe_read(ROOT / 'reservation.json', 32768))
    if value['policy_sha256'] != POLICY_SHA or value['policy_bytes'] != POLICY_BYTES.decode():
        raise Refusal('reservation_policy_mismatch')
    if not re.fullmatch('[0-9a-f]{32}', value['token']):
        raise Refusal('invalid_token')
    return value


def state():
    try:
        return strict_json(safe_read(ROOT / 'state.json', 32768))
    except FileNotFoundError:
        return {'phase': 'reserved', 'inference_requests_reserved': 0,
                'charged_seconds': MAX_SECONDS, 'charge_kind': 'unsettled_conservative_reservation',
                'cleanup_verified': False}


def update(**changes):
    with lock('state.lock'):
        value = state()
        value.update(changes)
        value['updated_at'] = stamp()
        atomic('state.json', value)
        return value


def remaining(r):
    # Same-host CLOCK_MONOTONIC spans parent/worker/container. Wall clock is an additional stop gate.
    return min(r['deadline_unix'] - time.time(), r['deadline_monotonic'] - time.monotonic())


def check(r, reserve=CLEANUP_RESERVE):
    if (ROOT / 'STOP').exists():
        raise Refusal('stop_requested')
    if remaining(r) <= reserve:
        raise Refusal('deadline_cleanup_reserve')


def owned(cid, r, *, absent_ok=False):
    if not re.fullmatch('[0-9a-f]{64}', cid):
        raise Refusal('full_container_id_required')
    fmt = '{"Id":{{json .Id}},"Image":{{json .Image}},"Name":{{json .Name}},"Labels":{{json .Config.Labels}},"State":{{json .State}}}'
    rc, raw, err = command(docker_argv('inspect', '--format', fmt, cid))
    if rc:
        # Confirm absence using daemon-successful exact ID inventory; arbitrary errors are not absence.
        ids = docker('ps', '-a', '--no-trunc', '--format', '{{.ID}}').decode().splitlines()
        if absent_ok and cid not in ids:
            return None
        raise Refusal('container_inspection_failed')
    value = strict_json(raw)
    expected = {'sentilab.owner': OWNER, 'sentilab.attempt': r['token'],
                'sentilab.source': r['controller_sha256'], 'sentilab.policy': r['policy_sha256']}
    if value['Id'] != cid or value['Image'] != IMAGE or value['Name'] != '/' + r['container_name'] or any(value['Labels'].get(k) != v for k, v in expected.items()):
        raise Refusal('container_identity_mismatch')
    return value


def port_closed():
    with socket.socket() as peer:
        peer.settimeout(0.5)
        return peer.connect_ex(('127.0.0.1', PORT)) in {errno.ECONNREFUSED, 10061}


def cleanup(r):
    """Never use a container name as a mutation target, nor kill a host PID/group."""
    with lock('docker.lock', wait=12):
        current = state()
        cid = current.get('container_id')
        if not cid:
            # Recover ambiguous CREATE by name only for inspection, then validate full immutable ID.
            raw = docker('ps', '-a', '--no-trunc', '--filter', 'name=^/' + r['container_name'] + '$', '--format', '{{.ID}}')
            ids = raw.decode().splitlines()
            if len(ids) > 1:
                raise Refusal('ambiguous_container_identity')
            cid = ids[0] if ids else None
        if cid:
            value = owned(cid, r, absent_ok=current.get('container_removed') is True)
            if value is not None:
                update(container_id=cid)
                if value['State']['Running']:
                    try:
                        docker('stop', '--time', '2', cid, timeout=5)
                    except Refusal:
                        if owned(cid, r)['State']['Running']:
                            docker('kill', cid, timeout=5)
                if owned(cid, r)['State']['Running']:
                    raise Refusal('owned_container_still_running')
                rc, out, err = command(docker_argv('logs', '--timestamps', '--tail', '200', cid), timeout=5, limit=1048576)
                if rc:
                    raise Refusal('logs_not_retained')
                # Raw Docker stdout/stderr bytes, bounded tail; never claim complete unbounded logs.
                for name, raw in [('container.stdout.log', out), ('container.stderr.log', err)]:
                    if not (ROOT / name).exists():
                        write_exclusive(name, raw)
                owned(cid, r)
                docker('rm', cid)
                if owned(cid, r, absent_ok=True) is not None:
                    raise Refusal('container_removal_unconfirmed')
        elif current.get('create_intent') and not current.get('create_returned'):
            # A timed-out daemon CREATE may appear after this inventory. Absence
            # here cannot prove closure; reserve the full attempt and reconcile later.
            raise Refusal('ambiguous_create_unresolved')
        if not port_closed():
            raise Refusal('owned_port_not_closed')
        elapsed = max(0.0, time.monotonic() - r['reserved_monotonic'])
        update(container_id=cid, container_removed=True, port_closed=True, cleanup_verified=True,
               charged_seconds=elapsed, charge_kind='reservation_to_confirmed_removal_and_port_closure',
               budget_exceeded=elapsed > MAX_SECONDS, cleanup_finished_at=stamp())


def verify_inputs(r):
    if len(INPUTS) < 16:
        raise Refusal('missing_committed_input_pins')
    receipts = []
    for relative, size, expected in INPUTS:
        check(r)
        path = RETAINED / relative
        # No path component may redirect a model read; stream pinned descriptors.
        with input_handle(path) as handle:
            before = os.fstat(handle.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_size != size:
                raise Refusal('input_size_or_type_mismatch')
            h = hashlib.sha256()
            read = 0
            while chunk := handle.read(1048576):
                check(r)
                read += len(chunk)
                if read > size:
                    raise Refusal('input_changed')
                h.update(chunk)
            after = os.fstat(handle.fileno())
        with input_handle(path) as again:
            final = os.fstat(again.fileno())
        identity = lambda info: (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
        if read != size or h.hexdigest() != expected or identity(before) != identity(after) or identity(after) != identity(final):
            raise Refusal('input_hash_or_stability_mismatch')
        receipts.append({'path': relative, 'bytes': size, 'sha256': expected})
    write_exclusive('input-verification.json', encode(receipts))
    fixture_bytes = safe_read(RETAINED / 'fixtures/eval.jsonl', 1048576)
    fixture_pin = next((size, sha) for name, size, sha in INPUTS if name == 'fixtures/eval.jsonl')
    if (len(fixture_bytes), digest(fixture_bytes)) != fixture_pin:
        raise Refusal('fixture_changed_after_verification')
    rows = [strict_json(line) for line in fixture_bytes.splitlines()]
    if len(rows) != 20 or any(not isinstance(x.get(k), str) for x in rows for k in ('row_id', 'system', 'instruction', 'output')):
        raise Refusal('fixture_shape_mismatch')
    return rows


@contextmanager
def input_handle(path):
    handles = []
    try:
        if os.name == 'posix':
            parent = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            handles.append(parent)
            for part in path.parts[1:-1]:
                parent = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                handles.append(parent)
            fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        else:
            if path.is_symlink():
                raise Refusal('unsafe_input_path')
            fd = os.open(path, os.O_RDONLY | os.O_BINARY)
        with os.fdopen(fd, 'rb') as handle:
            yield handle
    finally:
        for descriptor in reversed(handles):
            os.close(descriptor)


def container_argv(r):
    # This timeout starts from the reservation's original clocks even after a delayed Docker START.
    wrapper = ('import os,time,math; remaining=min(' + repr(r['deadline_unix'] - 35) + '-time.time(),'
               + repr(r['deadline_monotonic'] - 35) + '-time.monotonic()); '
               'os._exit(3) if remaining<=5 else None; os.execvp("timeout",["timeout","--signal=TERM",'
               '"--kill-after=5s",str(math.floor(remaining-5))+"s","python3","-m",'
               '"vllm.entrypoints.openai.api_server","--model","/model","--served-model-name","base",'
               '"--enable-lora","--lora-modules","fixture=/adapter","--max-lora-rank","8",'
               '"--max-model-len","1024","--gpu-memory-utilization","0.35","--enforce-eager",'
               '"--dtype","bfloat16","--host","0.0.0.0","--port","8000"])')
    labels = {'sentilab.owner': OWNER, 'sentilab.attempt': r['token'],
              'sentilab.source': r['controller_sha256'], 'sentilab.policy': r['policy_sha256']}
    args = ['create', '--init', '--pull=never', '--name', r['container_name']]
    for name, value in labels.items():
        args += ['--label', name + '=' + value]
    args += ['--gpus', 'all', '--user', '1000:1000', '--memory', '96g', '--cpus', '12', '--shm-size', '2g',
             '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges', '--read-only',
             '--tmpfs', '/tmp:rw,nosuid,nodev,size=4g,mode=1777', '--log-opt', 'max-size=4m', '--log-opt', 'max-file=1',
             '-e', 'HF_HUB_OFFLINE=1', '-e', 'TRANSFORMERS_OFFLINE=1', '-e', 'HF_HOME=/tmp/hf',
             '-e', 'HOME=/tmp', '-e', 'TOKENIZERS_PARALLELISM=false',
             '-e', 'VLLM_NO_USAGE_STATS=1', '-e', 'DO_NOT_TRACK=1',
             '--mount', 'type=bind,src=' + str(RETAINED / 'model') + ',dst=/model,readonly',
             '--mount', 'type=bind,src=' + str(RETAINED / 'attempt-01/adapter') + ',dst=/adapter,readonly',
             '--mount', 'type=bind,src=' + str(RETAINED / 'fixtures') + ',dst=/fixtures,readonly',
             '--publish', '127.0.0.1:' + str(PORT) + ':8000', '--entrypoint', 'python3', IMAGE, '-c', wrapper]
    return args


# Each HTTP request runs in one owned, stdlib-only child with a hard outer timeout.
# No shell/proxy/redirect/remote URL; the child cannot spawn descendants.
HTTP_CLIENT = '''import http.client,json,sys
body=sys.stdin.buffer.read(16385)
assert len(body)<=16384
path=sys.argv[1]
assert path in ('/health','/v1/chat/completions')
c=http.client.HTTPConnection('127.0.0.1',18047,timeout=float(sys.argv[2]))
c.request('POST' if body else 'GET',path,body or None,{'Content-Type':'application/json'})
r=c.getresponse(); raw=r.read(1048577); assert len(raw)<=1048576
sys.stdout.buffer.write(str(r.status).encode()+b'\\n'+raw)
c.close()
'''


def request(path, body, allowance):
    if type(allowance) not in {int, float} or not math.isfinite(allowance) or allowance <= 0:
        raise Refusal('http_deadline_expired')
    # communicate's response is bounded by the fixed child's explicit 1 MiB read.
    allowance = min(60, allowance)
    process = subprocess.Popen([sys.executable, '-I', '-S', '-B', '-c', HTTP_CLIENT, path, str(allowance)],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                               close_fds=True, shell=False)
    try:
        raw, _ = process.communicate(body, timeout=allowance)
        if process.returncode or len(raw) > MAX_RESPONSE + 4:
            raise Refusal('http_failed')
        code, separator, response = raw.partition(b'\n')
        if not separator or not re.fullmatch(b'[0-9]{3}', code):
            raise Refusal('http_invalid_response')
        return int(code), response
    finally:
        if process.poll() is None:
            process.kill()
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            pass


def inference(r, row, index):
    check(r)
    body = encode({'model': 'fixture', 'messages': [{'role': 'system', 'content': row['system']},
                  {'role': 'user', 'content': row['instruction']}], 'temperature': 0, 'seed': 818, 'max_tokens': 80})
    if len(body) > 16384 or not 0 <= index < 20:
        raise Refusal('invalid_fixed_request')
    # Durable request slot and raw bytes precede HTTP; ambiguous requests are never retried.
    write_exclusive(f'request-{index:02d}.json', body)
    update(inference_requests_reserved=index + 1)
    # STOP/deadline may have arrived during the durable reservation. Keep the
    # consumed slot and body, but recheck before creating an HTTP child.
    check(r)
    started = time.monotonic()
    allowance = min(60, remaining(r) - CLEANUP_RESERVE)
    code, raw = request('/v1/chat/completions', body, allowance)
    write_exclusive(f'response-{index:02d}.json', raw)
    parsed, parse_error = None, None
    if code == 200:
        try:
            parsed = strict_json(raw)
        except (ValueError, UnicodeError, Refusal, RecursionError) as exc:
            parse_error = type(exc).__name__
    exact = False
    if parsed is not None:
        try:
            exact = strict_json(parsed['choices'][0]['message']['content']) == strict_json(row['output'])
        except (ValueError, KeyError, IndexError, TypeError, Refusal, RecursionError):
            pass
    elapsed = time.monotonic() - started
    usage = parsed.get('usage') if isinstance(parsed, dict) else None
    counts = {key: usage.get(key) for key in ('prompt_tokens', 'completion_tokens', 'total_tokens')
              if isinstance(usage, dict) and type(usage.get(key)) is int and usage[key] >= 0}
    rate = counts['completion_tokens'] / elapsed if 'completion_tokens' in counts and elapsed > 0 else None
    receipt = {'row_id': row['row_id'], 'request_sha256': digest(body), 'response_sha256': digest(raw),
               'http_status': code, 'exact_json_match': exact, 'wall_seconds': elapsed,
               'request_timeout_seconds': allowance, 'response_parse_error': parse_error,
               'reported_usage': counts or None, 'client_observed_completion_tokens_per_second': rate,
               'timing_scope': 'one serial localhost request including client overhead; no concurrency or decoder-throughput claim',
               'policy_sha256': r['policy_sha256'], 'controller_sha256': r['controller_sha256']}
    write_exclusive(f'inference-{index:02d}.json', encode(receipt))
    if code != 200:
        raise Refusal('inference_http_failure')
    if parse_error is not None:
        raise Refusal('inference_invalid_json')


def worker(token, source):
    r = reservation()
    if token != r['token'] or digest(source) != r['controller_sha256']:
        raise Refusal('worker_identity_mismatch')
    with lock('worker.lock', wait=0):
        try:
            write_exclusive('worker-claimed.json', encode({'token': token, 'at': stamp()}))
        except FileExistsError:
            raise Refusal('worker_already_started') from None
        error = None
        try:
            check(r)
            update(phase='verifying_inputs', worker_started_at=stamp())
            rows = verify_inputs(r)
            with lock('docker.lock'):
                check(r)
                if not port_closed():
                    raise Refusal('port_already_in_use')
                # Persist intent before the daemon can create/start anything.
                update(phase='creating_container', create_intent=True, create_returned=False)
                cid = docker(*container_argv(r), timeout=10).decode().strip()
                if not re.fullmatch('[0-9a-f]{64}', cid):
                    raise Refusal('create_returned_invalid_id')
                update(container_id=cid, create_returned=True)
                owned(cid, r)
                launch_monotonic = time.monotonic()
                update(container_id=cid, phase='starting_container', launch_intent=True,
                       launch_monotonic=launch_monotonic, launch_intent_at=stamp())
                check(r)
                docker('start', cid, timeout=10)
            update(phase='waiting_ready')
            ready_by = min(time.monotonic() + 300, r['deadline_monotonic'] - CLEANUP_RESERVE)
            while time.monotonic() < ready_by:
                check(r)
                with lock('docker.lock'):
                    if not owned(cid, r)['State']['Running']:
                        raise Refusal('server_exited')
                try:
                    code, raw = request('/health', b'', min(3, remaining(r) - CLEANUP_RESERVE))
                    if code == 200:
                        break
                except (OSError, Refusal, subprocess.TimeoutExpired):
                    pass
                time.sleep(0.5)
            else:
                raise Refusal('readiness_timeout')
            update(phase='serving_fixture', ready_at=stamp(), launch_to_ready_seconds=time.monotonic()-launch_monotonic,
                   warmup_scope='Docker start intent through first successful localhost health response')
            for index, row in enumerate(rows):
                inference(r, row, index)
            update(phase='fixture_finished', inference_requests_completed=20)
        except BaseException as exc:
            error = str(exc) if isinstance(exc, Refusal) else type(exc).__name__
        finally:
            try:
                cleanup(r)
            except BaseException as exc:
                update(phase='cleanup_unresolved', error=error, cleanup_error=type(exc).__name__,
                       cleanup_verified=False, charged_seconds=max(MAX_SECONDS, time.monotonic() - r['reserved_monotonic']),
                       charge_kind='conservative_unresolved_attempt', retry_allowed=False)
            else:
                current = state()
                complete = error is None and current.get('inference_requests_completed') == 20 and not current.get('budget_exceeded')
                update(phase='completed' if complete else 'failed_closed', error=error, retry_allowed=False,
                       finished_at=stamp(), final_deliverable_accepted=False)


def approved_source(source):
    approval_raw = safe_read(ROOT / 'APPROVED.json', 8192)
    approval = strict_json(approval_raw)
    expected = {'schema', 'grant_source', 'controller_sha256', 'policy_sha256', 'decision', 'reviewer', 'review_record'}
    if set(approval) != expected or approval['schema'] != 'sentilab-slab047-review/1' or approval['grant_source'] != POLICY['grant_source'] or approval['controller_sha256'] != digest(source) or approval['policy_sha256'] != POLICY_SHA or approval['decision'] != '+1' or not isinstance(approval['reviewer'], str) or not approval['reviewer'].strip() or approval['reviewer'] in {'gpt-astra-carter', 'requirements_audit'} or not isinstance(approval['review_record'], str) or not approval['review_record'].strip():
        raise Refusal('exact_independent_review_required')
    return approval_raw


def start(source):
    if time.time() >= START_BY or time.time() >= ABSOLUTE_STOP - CLEANUP_RESERVE:
        raise Refusal('start_deadline_expired')
    if (ROOT / 'STOP').exists():
        raise Refusal('stop_requested')
    with lock('admission.lock'):
        # Re-read the actual approval only after taking the admission lock.
        # A revocation/source change while waiting cannot authorize a stale request.
        approval_raw = approved_source(source)
        if time.time() >= START_BY or (ROOT / 'STOP').exists():
            raise Refusal('admission_expired_or_stopped')
        now, monotonic = time.time(), time.monotonic()
        token = uuid.uuid4().hex
        r = {'schema': SCHEMA, 'token': token, 'attempt': 1, 'reserved_at': stamp(), 'reserved_unix': now,
             'reserved_monotonic': monotonic, 'deadline_unix': min(now + MAX_SECONDS, ABSOLUTE_STOP),
             'deadline_monotonic': monotonic + min(MAX_SECONDS, ABSOLUTE_STOP - now),
             'policy_bytes': POLICY_BYTES.decode(), 'policy_sha256': POLICY_SHA,
             'approval_bytes': approval_raw.decode(), 'approval_sha256': digest(approval_raw),
             'controller_sha256': digest(source), 'container_name': OWNER + '-' + token,
             'reserved_gpu_seconds': MAX_SECONDS, 'retry_allowed': False}
        # O_EXCL and fsync make both racing starts and interrupted starts consume at most one slot.
        try:
            write_exclusive('reservation.json', encode(r))
        except FileExistsError:
            raise Refusal('attempt_already_consumed') from None
        update(phase='reserved', inference_requests_reserved=0, charged_seconds=MAX_SECONDS,
               charge_kind='unsettled_conservative_reservation', cleanup_verified=False)
        # Embed the already checked source bytes so a later installed-file swap cannot change this worker.
        bootstrap = 's=' + repr(source) + '; exec(compile(s,' + repr(str(ROOT / PROGRAM)) + ',"exec"),{"__name__":"__main__","__file__":' + repr(str(ROOT / PROGRAM)) + ',"APPROVED_SOURCE":s})'
        try:
            process = subprocess.Popen([sys.executable, '-I', '-S', '-B', '-c', bootstrap, '_worker', token],
                                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                       start_new_session=True, close_fds=True, shell=False)
            # No PID is stored or used for later signals. Lock and current state are reported instead.
            update(worker_spawn_returned=True)
        except BaseException:
            update(phase='spawn_unresolved', charged_seconds=MAX_SECONDS, retry_allowed=False)
            raise Refusal('worker_spawn_unresolved') from None
    return {'phase': 'start_reserved', 'token': token, 'attempt': 1, 'reserved_gpu_seconds': MAX_SECONDS,
            'controller_sha256': r['controller_sha256'], 'policy_sha256': r['policy_sha256'], 'launched': 'worker_spawn_returned',
            'gpu_started': 'not_yet_observed', 'retry_allowed': False}


def observe():
    try:
        r = reservation()
    except FileNotFoundError:
        return {'phase': 'not_started', 'attempt_consumed': False, 'live_service_state': 'not_observed'}
    current = state()
    current.update(attempt_consumed=True, token=r['token'], controller_sha256=r['controller_sha256'],
                   policy_sha256=r['policy_sha256'], remaining_seconds=max(0, remaining(r)))
    try:
        with lock('worker.lock', wait=0):
            current['controller_lock_held'] = False
    except Refusal:
        current['controller_lock_held'] = True
    cid = current.get('container_id')
    if cid:
        with lock('docker.lock'):
            found = owned(cid, r, absent_ok=current.get('container_removed') is True)
        current['current_container_running'] = found['State']['Running'] if found is not None else False
        current['current_container_present'] = found is not None
    else:
        current['current_container_running'] = None
    current['current_port_closed'] = port_closed()
    current['scope'] = POLICY['scope']
    return current


def operate(action, source):
    validate_root()
    if action == 'start':
        return start(source)
    if action == 'status':
        return observe()
    if action == 'stop':
        r = reservation()  # No arbitrary STOP directory/file before a reserved session exists.
        try:
            write_exclusive('STOP', encode({'token': r['token'], 'at': stamp()}))
        except FileExistsError:
            pass
        try:
            cleanup(r)
        except (OSError, Refusal) as exc:
            update(phase='cleanup_unresolved', cleanup_verified=False, charged_seconds=max(MAX_SECONDS, time.monotonic() - r['reserved_monotonic']),
                   charge_kind='conservative_unresolved_attempt', cleanup_error=type(exc).__name__, retry_allowed=False)
        return observe()
    raise Refusal('invalid_action')


def main():
    action = sys.argv[1] if len(sys.argv) >= 2 else ''
    source = globals().get('APPROVED_SOURCE')
    if source is None:
        source = safe_read(ROOT / PROGRAM, MAX_SOURCE)
    if action == '_worker' and len(sys.argv) == 3:
        validate_root()
        worker(sys.argv[2], source)
        return
    if action not in {'start', 'status', 'stop'} or len(sys.argv) != 2:
        raise SystemExit(2)
    try:
        result = operate(action, source)
        payload = {'schema': SCHEMA, 'action': action, 'ok': True, 'scope_state': 'staged_open',
                   'identity': root_identity(), 'policy_sha256': POLICY_SHA, 'controller_sha256': digest(source), 'result': result}
    except (Refusal, OSError, ValueError, KeyError, TypeError) as exc:
        payload = {'schema': SCHEMA, 'action': action, 'ok': False, 'scope_state': 'staged_open',
                   'identity': root_identity(), 'policy_sha256': POLICY_SHA, 'controller_sha256': digest(source),
                   'error': str(exc) if isinstance(exc, Refusal) else type(exc).__name__}
    print(encode(payload).decode())


if __name__ == '__main__':
    main()
