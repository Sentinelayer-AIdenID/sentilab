"""Offline executable-runner tests with synthetic packets and sealed inputs."""
import json
import threading
import time

import pytest

from test_study_runner import packet, response, runner


def fixture(tmp_path):
    packets = tmp_path / 'packets'
    for name in ('case-one', 'case-two'):
        case = packet(packets, name)
        (case / 'report.md').write_text('fake ' + name)
    order = [{'job_id': f'{name}-{arm}', 'arm': arm, 'packet': name, 'repeat': 1}
             for name in ('case-one', 'case-two') for arm in 'ABC']
    prompts = {name: tmp_path / f'{name}.txt' for name in ('system', 'continue', 'c1', 'c2', 'c3')}
    for name, path in prompts.items():
        path.write_text('FAKE sealed prompt ' + name)
    protocol = {
        'model': 'deepseek-v4-pro', 'deployment': 'fake-deployment',
        'max_tokens_per_reply': 100, 'max_usd': '10',
        'prices_per_million': {'input': '1', 'cached_input': '0.5', 'output': '2'},
        'caps': {'A': 120000, 'B': 40000, 'C': 40000}, 'wall_seconds': 900,
        'turn_order': [1, 2, 3], 'writer': 1,
        'findings': {'fields': ['file', 'location', 'defect', 'evidence'], 'max_findings': 20, 'marker': 'FINAL'},
        'prompt_files': {name: path.name for name, path in prompts.items()},
        'pilot_arms': ['A'],
        'initial_prompt_tokens': {job['job_id']: {str(n): 100 for n in ([1] if job['arm'] == 'A' else [1, 2, 3])}
                                 for job in order} | {'pilot-A': {'1': 100}},
    }
    (tmp_path / 'protocol.json').write_text(json.dumps(protocol))
    (tmp_path / 'order.json').write_text(json.dumps(order))
    args = ['--protocol', str(tmp_path / 'protocol.json'), '--order', str(tmp_path / 'order.json'),
            '--packets', str(packets), '--output', str(tmp_path / 'output'), '--dry-run']
    for name, path in prompts.items():
        args += ['--prompt', f'{name}={path}']
    return args, protocol, order


def freeze(tmp_path, args, capsys):
    assert runner.main(args + ['--print-freeze']) == 0
    descriptor = json.loads(capsys.readouterr().out)
    path = tmp_path / 'freeze.json'
    path.write_bytes(runner.canonical(descriptor))
    return descriptor, args + ['--freeze', str(path)]


def test_print_freeze_binds_actual_request_settings_caps_prices_and_all_files(tmp_path, capsys):
    args, protocol, _ = fixture(tmp_path)
    descriptor, _ = freeze(tmp_path, args, capsys)
    assert descriptor['runner_sha256'] == runner.sha256(runner.Path(runner.__file__).read_bytes())
    assert descriptor['request_settings'] == {
        'model': 'deepseek-v4-pro', 'deployment': 'fake-deployment',
        'temperature': 0.3, 'top_p': 1, 'max_tokens_per_reply': 100, 'stream': False,
        'allow_redirects': False, 'timeout': 'remaining arm wall time'}
    assert descriptor['protocol'] == protocol
    assert descriptor['caps'] == {'tokens_per_agent': protocol['caps'], 'wall_seconds': 900,
                                  'max_usd': '10', 'parallel_arms': 6}
    assert descriptor['turn_rule'] == {'order': [1, 2, 3], 'writer': 1, 'skip_stopped_agents': True}
    assert len(descriptor['packet_files']) == 10
    assert set(descriptor['prompts']) == {'system', 'continue', 'c1', 'c2', 'c3'}
    assert descriptor['packets_tree_sha256'] == runner.sha256(runner.canonical(descriptor['packet_files']))
    assert not (tmp_path / 'output').exists()


def test_two_packet_dry_run_uses_no_network_and_produces_sealed_outputs(tmp_path, capsys, monkeypatch):
    args, _, order = fixture(tmp_path)
    monkeypatch.setenv('STUDY_API_KEY', 'obviously-fake-credential')

    def no_network(*args, **kwargs):
        raise AssertionError('dry run tried the network')

    monkeypatch.setattr(runner.requests.Session, 'post', no_network)
    descriptor, args = freeze(tmp_path, args, capsys)
    assert runner.main(args) == 0
    captured = capsys.readouterr()
    assert 'obviously-fake-credential' not in captured.out + captured.err
    output = tmp_path / 'output'
    accounting = json.loads((output / 'ACCOUNTING.json').read_text())
    assert accounting['scopes']['study']['attempts'] == 24
    assert accounting['scopes']['pilot']['attempts'] == 0
    manifest = json.loads((output / 'RUN-MANIFEST.json').read_text())
    assert len(manifest['files']) == 20
    assert json.loads((output / 'FREEZE.json').read_text()) == descriptor
    for relative, digest in manifest['files'].items():
        data = (output / relative).read_bytes()
        assert runner.sha256(data) == digest
        assert b'obviously-fake-credential' not in data
    starts = []
    for job in order:
        actual = json.loads((output / job['job_id'] / 'job.json').read_text())
        starts.append(actual['start_utc'])
        assert actual['arm'] == job['arm']
        assert actual['unknown_usage'] is False
        findings = json.loads((output / job['job_id'] / 'findings.json').read_text())
        sets = findings.values() if job['arm'] == 'B' else [findings]
        assert all(len(value['findings']) == 1 for value in sets)
    assert starts == sorted(starts)
    assert runner.main(args) == 2
    assert 'empty' in capsys.readouterr().err


@pytest.mark.parametrize('changed', ['prompt', 'protocol', 'packet', 'order', 'freeze'])
def test_mismatched_freeze_refuses_before_output_or_model(tmp_path, capsys, changed):
    args, _, _ = fixture(tmp_path)
    _, args = freeze(tmp_path, args, capsys)
    paths = {'prompt': tmp_path / 'system.txt', 'protocol': tmp_path / 'protocol.json',
             'packet': tmp_path / 'packets/case-one/model.py', 'order': tmp_path / 'order.json',
             'freeze': tmp_path / 'freeze.json'}
    path = paths[changed]
    if changed == 'freeze':
        value = json.loads(path.read_text())
        value['runner_sha256'] = 'different'
        path.write_text(json.dumps(value))
    else:
        path.write_bytes(path.read_bytes() + b'\n')
    assert runner.main(args) == 2
    assert 'freeze' in capsys.readouterr().err
    assert not (tmp_path / 'output').exists()


def test_pilot_requires_distinct_content_then_shares_global_ledger(tmp_path, capsys):
    args, _, _ = fixture(tmp_path)
    pilot = packet(tmp_path / 'pilot')
    (pilot / 'report.md').write_text('fake case-one')
    args += ['--pilot-packet', str(pilot)]
    assert runner.main(args + ['--print-freeze']) == 2
    assert 'pilot' in capsys.readouterr().err
    (pilot / 'report.md').write_text('separate fake pilot')
    descriptor, args = freeze(tmp_path, args, capsys)
    assert descriptor['pilot']['packet_sha256']
    assert descriptor['pilot']['arms'] == ['A']
    assert runner.main(args) == 0
    accounting = json.loads((tmp_path / 'output/ACCOUNTING.json').read_text())
    assert accounting['scopes']['pilot']['attempts'] == 2
    assert [row['scope'] for row in accounting['attempts'][:2]] == ['pilot', 'pilot']
    assert all(row['scope'] == 'study' for row in accounting['attempts'][2:])
    assert sum(runner.Decimal(value['usd']) for value in accounting['scopes'].values()) == runner.Decimal(accounting['grand_total_usd'])


def test_live_mode_refuses_two_packets_and_dry_run_still_requires_freeze(tmp_path, capsys):
    args, _, _ = fixture(tmp_path)
    assert runner.main(args) == 2
    assert 'freeze' in capsys.readouterr().err
    args.remove('--dry-run')
    assert runner.main(args + ['--print-freeze']) == 2
    assert 'ten' in capsys.readouterr().err


@pytest.mark.parametrize('field,value', [
    ('initial_prompt_tokens', {}), ('max_tokens_per_reply', 0), ('max_usd', 'NaN'),
    ('writer', 2), ('turn_order', [3, 2, 1]), ('model', 'another-model'),
    ('caps', {'A': 120000, 'B': 50000, 'C': 40000}), ('wall_seconds', 901),
])
def test_protocol_cannot_silently_change_fixed_rules_or_omit_initial_bounds(tmp_path, capsys, field, value):
    args, protocol, _ = fixture(tmp_path)
    protocol[field] = value
    (tmp_path / 'protocol.json').write_text(json.dumps(protocol))
    assert runner.main(args + ['--print-freeze']) == 2
    assert capsys.readouterr().err
    assert not (tmp_path / 'output').exists()


def test_parallel_jobs_are_bounded_and_start_in_sealed_order(tmp_path):
    args, protocol, order = fixture(tmp_path)
    order = [{**job, 'arm': 'A'} for job in order]
    (tmp_path / 'order.json').write_text(json.dumps(order))
    inputs = runner.snapshot_inputs(tmp_path / 'protocol.json',
                                    {name: tmp_path / path for name, path in protocol['prompt_files'].items()},
                                    tmp_path / 'order.json', tmp_path / 'packets')
    output = tmp_path / 'output'
    runner.claim_output(output)

    class Model:
        def __init__(self):
            self.barrier = threading.Barrier(2)
            self.lock = threading.Lock()
            self.ready = threading.Event()
            self.release = threading.Event()
            self.active = 0
            self.maximum = 0

        def complete(self, messages, **kwargs):
            with self.lock:
                self.active += 1
                self.maximum = max(self.maximum, self.active)
                if self.active == 2:
                    self.ready.set()
            assert self.release.wait(timeout=5)
            self.barrier.wait(timeout=5)
            with self.lock:
                self.active -= 1
            return response('FINAL')

    model = Model()
    ledger = runner.Ledger('10', protocol['prices_per_million'])
    engine = runner.RequestEngine(model, ledger, max_tokens_per_reply=100)
    errors = []

    def execute():
        try:
            runner.run_jobs(inputs, output=output, engine=engine, parallel=2)
        except BaseException as error:
            errors.append(error)

    worker = threading.Thread(target=execute)
    worker.start()
    try:
        assert model.ready.wait(timeout=5)
        time.sleep(0.05)  # Give the coordinator time to expose premature starts.
        assert len([path for path in output.iterdir() if path.is_dir()]) == 2
    finally:
        model.release.set()
        worker.join(timeout=10)
    assert not worker.is_alive()
    assert errors == []
    assert model.maximum == 2
    starts = [json.loads((output / job['job_id'] / 'job.json').read_text())['start_utc'] for job in order]
    assert starts == sorted(starts)
    assert len(ledger.report()['attempts']) == 6


def test_job_and_run_record_dollar_overshoot_and_unknown_usage_explicitly(tmp_path):
    output = tmp_path / 'output'
    runner.claim_output(output)
    ledger = runner.Ledger('0.0003', {'input': '1', 'cached_input': '0.5', 'output': '2'})
    from test_study_runner import ScriptedModel, job_metadata
    model = ScriptedModel(response('FINAL', prompt=500, completion=20))
    engine = runner.RequestEngine(model, ledger, max_tokens_per_reply=100)
    runner.run_arm(job_metadata(), output=output, engine=engine, system_prompt='system',
                   packet_message='packet', continue_prompt='continue', initial_prompt_bounds={1: 100})
    runner.finish_run(output, ledger)
    job = json.loads((output / 'job-one/job.json').read_text())
    accounting = json.loads((output / 'ACCOUNTING.json').read_text())
    assert job['charged_usd'] == '0.00054'
    assert job['run_overshoot_usd_at_end'] == accounting['overshoot_usd'] == '0.00024'
    assert job['run_stop_reason'] == 'dollar_cap'
    assert accounting['unknown_usage'] is False


def test_http_wall_deadline_is_an_unknown_cost_failure_without_waiting_for_transport(monkeypatch):
    entered, release = threading.Event(), threading.Event()

    def stalled(*args, **kwargs):
        entered.set()
        release.wait(timeout=2)
        raise runner.requests.Timeout('fake delayed failure')

    monkeypatch.setattr(runner.requests.Session, 'post', stalled)
    model = runner.HTTPModel('https://provider.invalid/chat/completions', 'obviously-fake-credential')
    start = time.monotonic()
    try:
        with pytest.raises(runner.CallFailure) as failure:
            model.complete([], max_tokens=100, timeout=0.05)
        assert entered.is_set()
        assert time.monotonic() - start < 1
        assert failure.value.kind == 'deadline_unknown'
        assert failure.value.safe_to_retry is False
    finally:
        release.set()
