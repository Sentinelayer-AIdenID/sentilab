"""Independent audit harness. All process, Docker, HTTP and clock APIs are fake.

Runs the unchanged supervisor with its fixed root redirected into a temporary
audit directory. It never imports model_stage or any ML framework.
"""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types

SOURCE = Path(__file__).resolve().parents[3] / '.sentinelayer/sentilab-planning/gpt-astra-carter/slab018-worktree/scripts/gb10/supervise.py'
FIXED = '/home/dell/sentilab/preflight-20261031'
RESULTS = []


class Rig:
    def __init__(self, directory, case, initial=None, mode='run'):
        self.root = Path(directory) / case
        self.root.mkdir()
        (self.root/'input.txt').write_text('immutable fixture sentinel')
        (self.root/'execution-inputs.json').write_text(json.dumps({'files': {
            'input.txt': hashlib.sha256((self.root/'input.txt').read_bytes()).hexdigest()}}))
        if initial is not None:
            (self.root/'execution-state.json').write_text(json.dumps(initial))
        spec = importlib.util.spec_from_file_location('reviewed_supervisor_'+case, SOURCE)
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)
        self.m.Path = lambda value: self.root if str(value) == FIXED else Path(value)
        self.tick = 0.0
        self.m.time = types.SimpleNamespace(time=lambda: self.m.DEADLINE-7200,
                                          monotonic=lambda: self.tick, sleep=self.sleep)
        self.m.signal = types.SimpleNamespace(SIGTERM=15, SIGINT=2, signal=lambda *a: None)
        self.calls = []
        self.containers = {}
        self.changed = 1
        self.stop_fails = False
        self.kill_fails = False
        self.run_ambiguous = False
        self.foreign_running = False
        self.overspend = False
        self.m.command = self.command
        self.m.subprocess = types.SimpleNamespace(run=self.logs, Popen=self.client,
                                                  STDOUT=subprocess.STDOUT,
                                                  TimeoutExpired=subprocess.TimeoutExpired)
        self.m.urllib = types.SimpleNamespace(request=types.SimpleNamespace(urlopen=lambda *a, **k: Health()))
        self.argv = ['supervise.py', mode]

    def sleep(self, seconds):
        self.tick += seconds

    def command(self, args, timeout=15):
        self.calls.append(list(args))
        assert args[0] == 'docker', args
        op = args[1]
        if op == 'run':
            name = args[args.index('--name')+1]
            labels = dict(args[i+1].split('=', 1) for i, arg in enumerate(args) if arg == '--label')
            serving = name.endswith('-serve')
            item = {'Config': {'Labels': labels}, 'Image': 'fake-sha256',
                    'State': {'Running': serving, 'ExitCode': 0, 'Pid': 123, 'StartedAt': 'fake'}}
            self.containers[name] = item
            if name.endswith('-evaluate'):
                (self.root/'attempt-01/evaluation.json').write_text(json.dumps({'changed_outputs': self.changed}))
            if self.run_ambiguous:
                item['State']['Running'] = True
                raise subprocess.TimeoutExpired(args, timeout)
            return name
        if op == 'inspect':
            if args[2] not in self.containers:
                raise RuntimeError('fake container missing')
            return json.dumps([self.containers[args[2]]])
        if op in ('stop', 'kill'):
            target = args[-1]
            if (op == 'stop' and self.stop_fails) or (op == 'kill' and self.kill_fails):
                raise subprocess.TimeoutExpired(args, timeout)
            self.containers[target]['State']['Running'] = False
            if self.overspend and target.endswith('-serve'):
                self.tick += 3500
            return target
        if op == 'rm':
            assert not self.containers[args[-1]]['State']['Running']
            del self.containers[args[-1]]
            return args[-1]
        if op == 'ps':
            return 'unexpected-owned-id' if self.foreign_running else ''
        raise AssertionError(args)

    def logs(self, args, **kwargs):
        assert args[:3] == ['docker', 'logs', '--timestamps'], args
        self.calls.append(list(args))
        return types.SimpleNamespace(returncode=0, stdout='captured stdout\n', stderr='captured stderr\n')

    def client(self, args, **kwargs):
        assert args[0] == 'python3' and args[1] == str(self.root/'http_eval.py'), args
        (self.root/'attempt-01/http-result.json').write_text('{"requests":40}')
        kwargs['stdout'].close()
        return types.SimpleNamespace(poll=lambda: 0, returncode=0)

    def run(self):
        old = sys.argv
        sys.argv = self.argv
        try:
            self.m.main()
            return None
        except Exception as exc:
            return exc
        finally:
            sys.argv = old

    def state(self):
        return json.loads((self.root/'execution-state.json').read_text())


class Health:
    status = 200
    def __enter__(self): return self
    def __exit__(self, *args): return None


def record(name, check):
    check()
    RESULTS.append({'case': name, 'passed': True})


def main():
    with tempfile.TemporaryDirectory(prefix='slab018-fake-review-') as directory:
        for name, changed, expected in [('positive_difference', 1, 'completed'),
                                        ('zero_difference', 0, 'plumbing_finished_difference_requirement_unmet')]:
            rig = Rig(directory, name)
            rig.changed = changed
            assert rig.run() is None
            state = rig.state()
            assert state['attempts'][0]['status'] == expected and state['active'] is None
            assert len([a for a in rig.calls if a[1]=='run']) == 3
            assert not rig.containers
            assert (rig.root/'attempt-01/train.stdout.log').read_text() == 'captured stdout\n'
            assert (rig.root/'attempt-01/train.stderr.log').read_text() == 'captured stderr\n'
            RESULTS.append({'case': name+'_and_log_streams_and_teardown', 'passed': True})

        base = {'attempts': [], 'active': None, 'gpu_container_wall_seconds': 180}
        guard_cases = {
            'unreconciled_active': {**base, 'active': {'name':'prior'}},
            'three_attempt_cap': {**base, 'attempts': [{}, {}, {}]},
            'already_completed': {**base, 'attempts': [{'status':'completed'}]},
            'exhausted_budget': {**base, 'gpu_container_wall_seconds': 3600},
        }
        for name, initial in guard_cases.items():
            rig = Rig(directory, name, copy.deepcopy(initial))
            assert isinstance(rig.run(), RuntimeError)
            assert not any(a[1]=='run' for a in rig.calls)
            RESULTS.append({'case': name, 'passed': True})

        for name in ['stop_file', 'expired_deadline', 'tampered_input']:
            rig = Rig(directory, name)
            if name == 'stop_file': (rig.root/'STOP').touch()
            elif name == 'expired_deadline': rig.m.time.time = lambda: rig.m.DEADLINE
            else: (rig.root/'input.txt').write_text('tampered')
            assert isinstance(rig.run(), (RuntimeError, ValueError))
            assert not any(a[1]=='run' for a in rig.calls)
            RESULTS.append({'case': name, 'passed': True})

        for name, wrong_owner in [('stop_by_name_kill_fallback', False), ('stop_wrong_owner_refused', True)]:
            active = {'name':'owned-name', 'token':'exact-token', 'container_id':None}
            rig = Rig(directory, name, {**base, 'active':active}, mode='stop')
            rig.containers['owned-name'] = {'Config': {'Labels': {
                'sentilab.owner': 'other' if wrong_owner else rig.m.OWNER,
                'sentilab.attempt':'exact-token'}}, 'State': {'Running':True}}
            rig.stop_fails = True
            error = rig.run()
            if wrong_owner:
                assert isinstance(error, RuntimeError)
                assert not any(a[1] in ('stop','kill') for a in rig.calls)
            else:
                assert error is None
                assert any(a[1]=='kill' for a in rig.calls)
                assert not rig.containers['owned-name']['State']['Running']
            assert (rig.root/'STOP').exists()
            RESULTS.append({'case': name, 'passed': True})

        for name, cleanup_fails in [('ambiguous_create_name_cleanup', False), ('ambiguous_cleanup_fail_closed', True)]:
            rig = Rig(directory, name)
            rig.run_ambiguous = True
            rig.stop_fails = cleanup_fails
            rig.kill_fails = cleanup_fails
            assert isinstance(rig.run(), subprocess.TimeoutExpired)
            state = rig.state()
            assert state['attempts'][0]['status'] == 'failed'
            if cleanup_fails:
                assert state['active'] is not None and state['gpu_container_wall_seconds'] >= 3600
            else:
                assert state['active'] is None and not rig.containers
            RESULTS.append({'case': name, 'passed': True})

        for name, budget in [('final_budget_gate', True), ('final_owned_running_gate', False)]:
            rig = Rig(directory, name)
            rig.overspend = budget
            rig.foreign_running = not budget
            error = rig.run()
            assert isinstance(error, RuntimeError), error
            assert rig.state()['attempts'][0]['status'] == 'failed'
            RESULTS.append({'case': name, 'passed': True})

    print(json.dumps({'scope':'Fake-only unchanged supervisor control-flow audit; no Docker, model, GPU or network',
                      'supervisor_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
                      'cases': RESULTS, 'passed':len(RESULTS)}, indent=2))


if __name__ == '__main__':
    main()
