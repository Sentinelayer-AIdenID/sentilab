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
    assert descriptor['output_schema'] == 'collab-study-output-v3'
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
    assert len(manifest['files']) == 26
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


def test_output_cannot_modify_a_packet_directory(tmp_path, capsys):
    args, _, _ = fixture(tmp_path)
    output = tmp_path / 'packets/case-one/generated-output'
    args[args.index('--output') + 1] = str(output)
    _, args = freeze(tmp_path, args, capsys)
    assert runner.main(args) == 2
    assert 'outside' in capsys.readouterr().err
    assert not output.exists()
    assert len(list((tmp_path / 'packets/case-one').iterdir())) == 5


def test_live_pilot_only_needs_no_freeze_order_or_study_packets(tmp_path, monkeypatch):
    args, protocol, _ = fixture(tmp_path)
    pilot = packet(tmp_path / 'pilot')
    protocol['pilot_arms'] = ['A', 'C']
    protocol['initial_prompt_tokens'] = {'pilot-A': {'1': 100},
                                         'pilot-C': {str(n): 100 for n in (1, 2, 3)}}
    (tmp_path / 'protocol.json').write_text(json.dumps(protocol))
    for flag in ('--order', '--packets'):
        index = args.index(flag)
        del args[index:index + 2]
    args.remove('--dry-run')
    calls = []

    class Response:
        status_code = 200
        headers = {}

        def json(self):
            return {'choices': [{'message': {'content': 'FINAL\n'}}],
                    'usage': {'prompt_tokens': 100, 'completion_tokens': 20}}

    def post(self, endpoint, **kwargs):
        calls.append(kwargs['json'])
        return Response()

    monkeypatch.setenv('STUDY_ENDPOINT', 'https://provider.invalid/chat/completions')
    monkeypatch.setenv('STUDY_API_KEY', 'obviously-fake-credential')
    monkeypatch.setattr(runner.requests.Session, 'post', post)
    assert runner.main(args + ['--pilot-only', '--pilot-packet', str(pilot)]) == 0
    output = tmp_path / 'output'
    assert {path.name for path in output.iterdir() if path.is_dir()} == {'pilot-A', 'pilot-C'}
    accounting = json.loads((output / 'ACCOUNTING.json').read_text())
    assert accounting['scopes']['pilot']['attempts'] == len(calls) == 2
    assert accounting['scopes']['study']['attempts'] == 0
    assert accounting['grand_total_usd'] == '0.00028'
    assert json.loads((output / 'FREEZE.json').read_text())['pilot_only'] is True


def test_pilot_only_still_refuses_a_known_sealed_packet(tmp_path, capsys):
    args, _, _ = fixture(tmp_path)
    assert runner.main(args + ['--pilot-only', '--pilot-packet', str(tmp_path / 'packets/case-one')]) == 2
    assert 'pilot must differ' in capsys.readouterr().err
    assert not (tmp_path / 'output').exists()


def test_lone_surrogate_reply_is_escaped_in_every_output(tmp_path, capsys, monkeypatch):
    args, _, _ = fixture(tmp_path)
    _, args = freeze(tmp_path, args, capsys)
    content = 'FINAL\n' + json.dumps({'file': 'model.py', 'location': '1', 'defect': 'bad',
                                     'evidence': '\ud800'}, ensure_ascii=False)
    monkeypatch.setattr(runner.DryRunModel, 'complete', lambda *a, **kw: response(content))
    assert runner.main(args) == 0
    output = tmp_path / 'output'
    accounting = json.loads((output / 'ACCOUNTING.json').read_text())
    assert accounting['scopes']['study']['attempts'] == 10
    assert json.loads((output / 'case-one-A/findings.json').read_text())['findings'][0]['evidence'] == '\ud800'
    transcript = (output / 'case-one-A/transcript.jsonl').read_text()
    assert '\\ud800' in transcript
    for path in output.rglob('*.json*'):
        path.read_bytes().decode('utf-8')


@pytest.mark.parametrize('failure', [OSError, RuntimeError, KeyboardInterrupt])
def test_interrupted_run_checkpoints_cost_and_rerun_continues_ledger(tmp_path, capsys, monkeypatch, failure):
    args, protocol, _ = fixture(tmp_path)
    protocol['max_usd'] = '0.0005'
    (tmp_path / 'protocol.json').write_text(json.dumps(protocol))
    args += ['--parallel', '1']
    _, args = freeze(tmp_path, args, capsys)
    checkpoints = []

    def interrupted(*a, **kw):
        path = tmp_path / 'output/ACCOUNTING.json'
        checkpoints.append(json.loads(path.read_text()) if path.exists() else None)
        raise failure('synthetic interruption')

    monkeypatch.setattr(runner.DryRunModel, 'complete', interrupted)
    if failure is OSError:
        assert runner.main(args) == 2
    else:
        with pytest.raises(failure):
            runner.main(args)
    output = tmp_path / 'output'
    assert (output / 'ACCOUNTING.json').is_file()
    assert checkpoints[0]['reserved_usd'] == '0.000471'
    accounting = json.loads((output / 'ACCOUNTING.json').read_text())
    assert accounting['grand_total_usd'] == '0.000471'
    assert accounting['unknown_usage'] is True
    assert accounting['reserved_usd'] == '0'
    assert len(accounting['attempts']) == 1
    assert not (output / 'RUN-MANIFEST.json').exists()

    def no_call(*a, **kw):
        pytest.fail('rerun reset the dollar ledger or replayed the interrupted job')

    monkeypatch.setattr(runner.DryRunModel, 'complete', no_call)
    assert runner.main(args) == 0
    recovered = json.loads((output / 'ACCOUNTING.json').read_text())
    assert recovered['grand_total_usd'] == '0.000471'
    assert recovered['attempts'] == accounting['attempts']
    assert recovered['stop_reason'] == 'dollar_cap'
    job = json.loads((output / 'case-one-A/job.json').read_text())
    assert job['history_complete'] is False
    assert job['agents']['1']['stop_reason'] == 'interrupted_run'
    assert job['agents']['1']['charged_tokens'] == 371
    assert (output / 'RUN-MANIFEST.json').is_file()


def test_rerun_keeps_finished_jobs_and_previous_charges(tmp_path, capsys, monkeypatch):
    args, _, order = fixture(tmp_path)
    args += ['--parallel', '1']
    _, args = freeze(tmp_path, args, capsys)
    calls = []

    def model(*a, **kw):
        calls.append(True)
        if len(calls) > 1:
            raise OSError('synthetic interruption')
        return response('FINAL\n')

    monkeypatch.setattr(runner.DryRunModel, 'complete', model)
    assert runner.main(args) == 2
    output = tmp_path / 'output'
    first = output / order[0]['job_id']
    original = {p.name: p.read_bytes() for p in first.iterdir()}
    before = json.loads((output / 'ACCOUNTING.json').read_text())
    assert before['grand_total_usd'] == '0.001553'  # Finished A, then three interrupted B calls.
    resumed = []

    def final_model(*a, **kw):
        resumed.append(True)
        return response('FINAL\n')

    monkeypatch.setattr(runner.DryRunModel, 'complete', final_model)
    assert runner.main(args) == 0
    after = json.loads((output / 'ACCOUNTING.json').read_text())
    assert after['attempts'][:4] == before['attempts']
    assert len(resumed) == 6  # Remaining C, A, B, C jobs.
    assert after['grand_total_usd'] == '0.002393'
    assert {p.name: p.read_bytes() for p in first.iterdir()} == original
    assert json.loads((output / order[1]['job_id'] / 'job.json').read_text())['history_complete'] is False


def test_rerun_requires_matching_descriptor_and_an_inactive_output(tmp_path, capsys, monkeypatch):
    args, _, _ = fixture(tmp_path)
    args += ['--parallel', '1']
    descriptor, args = freeze(tmp_path, args, capsys)
    output = tmp_path / 'output'
    with runner.open_run(output, descriptor):
        assert runner.main(args) == 2
        assert 'still active' in capsys.readouterr().err
    runner.write_json_exclusive(output / 'FREEZE.json', {**descriptor, 'pilot_only': True})
    sentinel = b'costs must not be reset\n'
    (output / 'ACCOUNTING.json').write_bytes(sentinel)
    assert runner.main(args) == 2
    assert 'freeze' in capsys.readouterr().err
    assert (output / 'ACCOUNTING.json').read_bytes() == sentinel


def test_receipt_write_failure_keeps_settled_usage_and_marks_recovery_incomplete(tmp_path, capsys, monkeypatch):
    args, _, _ = fixture(tmp_path)
    args += ['--parallel', '1']
    _, args = freeze(tmp_path, args, capsys)
    original = runner.JobOutputs.record

    def fail_response(writer, value):
        if value['event'] == 'response':
            raise OSError('synthetic receipt failure')
        return original(writer, value)

    monkeypatch.setattr(runner.JobOutputs, 'record', fail_response)
    monkeypatch.setattr(runner.DryRunModel, 'complete', lambda *a, **kw: response('FINAL\n'))
    assert runner.main(args) == 2
    output = tmp_path / 'output'
    before = json.loads((output / 'ACCOUNTING.json').read_text())
    assert before['grand_total_usd'] == '0.00014'
    assert before['unknown_usage'] is False
    assert before['attempts'][0]['state'] == 'response'
    monkeypatch.setattr(runner.JobOutputs, 'record', original)
    assert runner.main(args) == 0
    after = json.loads((output / 'ACCOUNTING.json').read_text())
    assert after['attempts'][0] == before['attempts'][0]
    assert after['grand_total_usd'] == '0.0014'
    job = json.loads((output / 'case-one-A/job.json').read_text())
    assert job['history_complete'] is False
    assert job['wall_seconds'] is None
    assert job['start_utc'] == before['attempts'][0]['start_utc']


@pytest.mark.parametrize('name', [
    'findings.json', 'job.json', 'RUN-MANIFEST.json', 'transcript.jsonl', 'emitted_sets.jsonl',
])
def test_interruption_during_publication_leaves_only_complete_records(tmp_path, capsys, monkeypatch, name):
    args, _, _ = fixture(tmp_path)
    args += ['--parallel', '1']
    _, args = freeze(tmp_path, args, capsys)
    monkeypatch.setattr(runner.DryRunModel, 'complete', lambda *a, **kw: response('FINAL\n'))
    original = runner.Path.open
    interrupted = []

    class InterruptedWrite:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            self.stream.__enter__()
            return self

        def __exit__(self, *args):
            return self.stream.__exit__(*args)

        def __getattr__(self, attr):
            return getattr(self.stream, attr)

        def write(self, data):
            if data and not interrupted:
                interrupted.append(True)
                self.stream.write(data[:max(1, len(data) // 2)])
                self.stream.flush()
                raise OSError('synthetic interruption halfway through file write')
            return self.stream.write(data)

    def open_file(path, mode='r', *a, **kw):
        stream = original(path, mode, *a, **kw)
        if path.name.lstrip('.').removesuffix('.tmp') == name and any(flag in mode for flag in 'wxa'):
            return InterruptedWrite(stream)
        return stream

    monkeypatch.setattr(runner.Path, 'open', open_file)
    assert runner.main(args) == 2
    output = tmp_path / 'output'
    assert interrupted
    assert not (output / 'RUN-MANIFEST.json').exists()
    for path in output.rglob('*.json*'):
        if path.name.endswith('.jsonl'):
            for line in path.read_bytes().splitlines():
                json.loads(line)
        else:
            json.loads(path.read_bytes())
    before = json.loads((output / 'ACCOUNTING.json').read_text())
    # A hard kill can leave unpublished staging bytes; the locked rerun reclaims them.
    (output / 'case-one-A/.job.json.tmp').write_bytes(b'{"partial":')
    monkeypatch.setattr(runner.Path, 'open', original)
    assert runner.main(args) == 0
    after = json.loads((output / 'ACCOUNTING.json').read_text())
    assert after['attempts'][:len(before['attempts'])] == before['attempts']
    manifest = json.loads((output / 'RUN-MANIFEST.json').read_text())
    for relative, digest in manifest['files'].items():
        assert runner.sha256((output / relative).read_bytes()) == digest
    assert not list(output.rglob('.*.tmp'))
