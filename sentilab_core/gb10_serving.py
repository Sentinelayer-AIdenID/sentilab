"""Host bridge for the fixed SLAB047 lifecycle; caller parameters never grant access."""
import json
import re

CONTROLLER_SHA256 = '7f6a3883ecac1aac773ff5c7aa0f49cd01139db4300a67f21aa93eade8ca7c9b'
POLICY_SHA256 = '9b49f5149bcab62137dba7515c305a7079364630f74c6a0bab002a430ed944fc'
REMOTE_PATH = '/home/dell/sentilab/serving-20261031/serve047.py'
SCHEMA = 'sentilab-gb10-serving/1'


def execute(action):
    from . import gb10_backend as backend
    if not isinstance(action, str) or action not in {'start', 'status', 'stop'}:
        raise backend.ProbeError('invalid_input')
    if not re.fullmatch('[0-9a-f]{64}', CONTROLLER_SHA256):
        raise backend.ProbeError('serving_source_not_pinned')
    # The bootstrap executes exactly the verified bytes, avoiding check/reopen races.
    source = ('import os,stat,hashlib\n'
              'p=' + repr(REMOTE_PATH) + '\n'
              'parts=p.split("/")[1:]; fd=os.open("/",os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)\n'
              'for part in parts[:-1]:\n'
              ' n=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd);os.close(fd);fd=n\n'
              'n=os.open(parts[-1],os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd);os.close(fd)\n'
              'assert stat.S_ISREG(os.fstat(n).st_mode)\n'
              'with os.fdopen(n,"rb") as f:s=f.read(65537)\n'
              'assert len(s)<=65536 and hashlib.sha256(s).hexdigest()==' + repr(CONTROLLER_SHA256) + '\n'
              'exec(compile(s,p,"exec"),{"__name__":"__main__","__file__":p,"APPROVED_SOURCE":s})\n').encode()
    argv = ['ssh', '-T', '-a', '-x', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
            '-o', 'ConnectTimeout=5', '-o', 'ConnectionAttempts=1', '-o', 'ClearAllForwardings=yes',
            '-o', 'PermitLocalCommand=no', '-o', 'RemoteCommand=none', '-o', 'ControlMaster=no',
            '-o', 'ControlPath=none', '-o', 'LogLevel=ERROR', 'gb10', 'python3 -I -S -B - ' + action]
    raw = backend._capture(argv, source)
    try:
        if len(raw) > backend.MAX_OUTPUT_BYTES:
            raise ValueError()
        value = json.loads(raw.decode(), object_pairs_hook=backend._object, parse_constant=backend._constant)
        expected = {'schema', 'action', 'ok', 'scope_state', 'identity', 'policy_sha256', 'controller_sha256'}
        if not isinstance(value, dict) or type(value.get('ok')) is not bool:
            raise ValueError()
        if set(value) != expected | ({'result'} if value['ok'] else {'error'}):
            raise ValueError()
        if value['schema'] != SCHEMA or value['action'] != action or value['scope_state'] != 'staged_open' or value['identity'] != backend.EXPECTED_IDENTITY or value['controller_sha256'] != CONTROLLER_SHA256 or value['policy_sha256'] != POLICY_SHA256:
            raise ValueError()
        if value['ok'] and (not isinstance(value['result'], dict) or not isinstance(value['result'].get('phase'), str)):
            raise ValueError()
        if not value['ok'] and (not isinstance(value['error'], str) or not re.fullmatch('[A-Za-z0-9_]{1,96}', value['error'])):
            raise ValueError()
    except (ValueError, KeyError, TypeError, UnicodeError, RecursionError):
        raise backend.ProbeError('invalid_serving_response') from None
    if value['ok']:
        return backend._result('serve', ok=True, status='observed', action=action,
                               ssh_alias='gb10', identity=value['identity'], serving=value['result'],
                               controller_sha256=CONTROLLER_SHA256, policy_sha256=POLICY_SHA256,
                               final_deliverable_accepted=False)
    return backend._result('serve', ok=False, status='refused', action=action,
                           error={'code': value['error']}, controller_sha256=CONTROLLER_SHA256,
                           policy_sha256=POLICY_SHA256, final_deliverable_accepted=False)
