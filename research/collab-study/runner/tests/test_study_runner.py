"""Offline tests exercise the shipped runner, never packet code."""
import builtins
import importlib.util
import json
from pathlib import Path
import sys

import pytest

RUNNER = Path(__file__).resolve().parents[1] / "study_runner.py"
spec = importlib.util.spec_from_file_location("study_runner", RUNNER)
runner = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = runner
spec.loader.exec_module(runner)


def packet(root, name="case-one", model="raise AssertionError('packet executed')"):
    case = root / name
    case.mkdir(parents=True)
    for filename in runner.PACKET_FILES:
        (case / filename).write_text(model if filename == "model.py" else filename + "\n", encoding="utf-8")
    return case


def test_packet_is_text_and_never_executed(tmp_path, monkeypatch):
    case = packet(tmp_path)
    original_exec = builtins.exec
    original_import = builtins.__import__
    seen = []

    def exec_spy(source, *args, **kwargs):
        seen.append(source)
        raise AssertionError("runner executed packet code")

    def import_spy(name, *args, **kwargs):
        assert name != "model", "runner imported packet code"
        return original_import(name, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(builtins, "exec", exec_spy)
        patch.setattr(builtins, "__import__", import_spy)
        message, hashes = runner.read_packet(case)
    assert seen == []
    assert "raise AssertionError('packet executed')" in message
    assert list(hashes) == list(runner.PACKET_FILES)
    offsets = [message.index("### " + name + "\n") for name in runner.PACKET_FILES]
    assert offsets == sorted(offsets)
    assert builtins.exec is original_exec


def test_malformed_final_is_retained_without_repair():
    good = {"file": "model.py", "location": "12", "defect": "wrong axis", "evidence": "axis=0"}
    malformed = '{"file":"model.py",}'
    text = "FINAL\n" + json.dumps(good) + "\n" + malformed + "\n" + json.dumps({"file": "x"})
    result = runner.parse_final(text)
    assert result["findings"] == [good]
    assert result["malformed"] == [
        {"line": 2, "text": malformed},
        {"line": 3, "text": '{"file": "x"}'},
    ]
    assert runner.parse_final("thinking\nFINAL\n" + json.dumps(good)) is None
    limited = runner.parse_final("FINAL\n" + "\n".join([json.dumps(good)] * 22))
    assert len(limited["findings"]) == 20
    assert limited["discarded"] == 2


def test_output_directory_must_start_empty(tmp_path):
    occupied = tmp_path / "out"
    occupied.mkdir()
    marker = occupied / "existing"
    marker.write_text("untouched", encoding="utf-8")
    with pytest.raises(runner.InputError, match="empty"):
        runner.claim_output(occupied)
    assert marker.read_text() == "untouched"
    fresh = tmp_path / "fresh"
    runner.claim_output(fresh)
    with pytest.raises(runner.InputError, match="empty"):
        runner.claim_output(fresh)


def test_packet_rejects_extra_files_and_symlinks(tmp_path):
    case = packet(tmp_path)
    extra = case / "unexpected.txt"
    extra.write_text("extra", encoding="utf-8")
    with pytest.raises(runner.InputError):
        runner.read_packet(case)
    extra.unlink()
    (case / "model.py").unlink()
    (case / "model.py").symlink_to(case / "README.md")
    with pytest.raises(runner.InputError):
        runner.read_packet(case)


def test_freeze_binds_runner_protocol_prompts_order_and_packet_bytes(tmp_path):
    packets = tmp_path / "packets"
    case = packet(packets)
    protocol = tmp_path / "protocol.json"
    protocol.write_text('{"model":"deepseek-v4-pro","deployment":"fake-deployment"}', encoding="utf-8")
    order = tmp_path / "order.json"
    order.write_text('[{"job_id":"one","arm":"A","packet":"case-one","repeat":1}]', encoding="utf-8")
    prompts = {"system": tmp_path / "system.txt", "continue": tmp_path / "continue.txt"}
    for name, path in prompts.items():
        path.write_text(name, encoding="utf-8")
    frozen = runner.snapshot_inputs(protocol, prompts, order, packets)
    seal = tmp_path / "freeze.json"
    seal.write_bytes(runner.canonical(frozen.freeze))
    runner.verify_freeze(seal, frozen.freeze)
    assert frozen.freeze["runner_sha256"] == runner.sha256(RUNNER.read_bytes())
    assert frozen.freeze["protocol"]["deployment"] == "fake-deployment"
    assert frozen.freeze["order_sha256"] == runner.sha256(order.read_bytes())
    for path in [protocol, order, *prompts.values(), case / "model.py"]:
        original = path.read_bytes()
        path.write_bytes(original + b"\n")
        changed = runner.snapshot_inputs(protocol, prompts, order, packets)
        with pytest.raises(runner.InputError, match="freeze"):
            runner.verify_freeze(seal, changed.freeze)
        path.write_bytes(original)
    (case / "model.py").write_text("changed after snapshot", encoding="utf-8")
    assert "changed after snapshot" not in frozen.packets["case-one"]


def test_pilot_refuses_identical_sealed_packet_even_at_another_path(tmp_path):
    sealed = packet(tmp_path / "sealed")
    duplicate = packet(tmp_path / "pilot", "copy")
    _, hashes = runner.read_packet(sealed)
    with pytest.raises(runner.InputError, match="pilot"):
        runner.validate_pilot(duplicate, [hashes])
    (duplicate / "report.md").write_text("independent pilot fixture", encoding="utf-8")
    message, _ = runner.validate_pilot(duplicate, [hashes])
    assert "independent pilot fixture" in message


def test_provider_settings_usage_and_request_ids(monkeypatch):
    calls = []

    class Response:
        status_code = 200
        headers = {"x-request-id": "provider-request-one"}

        def json(self):
            return {"id": "completion-one", "choices": [{"message": {"content": "FINAL\n"}}],
                    "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120,
                              "prompt_tokens_details": {"cached_tokens": 40},
                              "completion_tokens_details": {"reasoning_tokens": 5}}}

    def post(self, endpoint, **kwargs):
        calls.append((endpoint, kwargs))
        return Response()

    monkeypatch.setenv("STUDY_ENDPOINT", "https://provider.invalid/chat/completions")
    monkeypatch.setenv("STUDY_API_KEY", "obviously-fake-credential")
    monkeypatch.setattr(runner.requests.Session, "post", post)
    model = runner.HTTPModel.from_env()
    reply = model.complete([{"role": "system", "content": "system"}], max_tokens=321, timeout=15)
    assert reply.content == "FINAL\n"
    assert reply.request_id == "provider-request-one"
    assert reply.response_id == "completion-one"
    assert runner.usage_counts(reply.usage) == (100, 40, 20, 5)
    endpoint, kwargs = calls[0]
    assert endpoint == "https://provider.invalid/chat/completions"
    assert kwargs["json"] == {"model": "deepseek-v4-pro", "temperature": 0.3, "top_p": 1,
                              "max_tokens": 321, "messages": [{"role": "system", "content": "system"}],
                              "stream": False}
    assert kwargs["headers"]["Authorization"] == "Bearer obviously-fake-credential"
    assert kwargs["allow_redirects"] is False
    assert kwargs["timeout"] == 15


def test_ambiguous_transport_failure_never_exposes_error_text(monkeypatch):
    secret = "obviously-fake-credential"

    def post(*args, **kwargs):
        raise runner.requests.Timeout(secret)

    monkeypatch.setattr(runner.requests.Session, "post", post)
    model = runner.HTTPModel("https://provider.invalid/chat/completions", secret)
    with pytest.raises(runner.CallFailure) as caught:
        model.complete([], max_tokens=50, timeout=1)
    assert caught.value.safe_to_retry is False
    assert caught.value.kind == "transport_unknown"
    assert secret not in str(caught.value)


def test_only_evidenced_presend_failure_is_retryable(monkeypatch):
    def post(*args, **kwargs):
        try:
            raise ConnectionRefusedError("refused")
        except ConnectionRefusedError as error:
            raise runner.requests.ConnectionError("connection failed") from error

    monkeypatch.setattr(runner.requests.Session, "post", post)
    model = runner.HTTPModel("https://provider.invalid/chat/completions", "obviously-fake-credential")
    with pytest.raises(runner.CallFailure) as caught:
        model.complete([], max_tokens=50, timeout=1)
    assert caught.value.safe_to_retry is True
    assert caught.value.kind == "presend_failure"


@pytest.mark.parametrize("status", [429, 500, 503, 401])
def test_http_failure_keeps_request_id_without_retry_or_error_body(monkeypatch, status):
    class Response:
        status_code = status
        headers = {"apim-request-id": "failed-provider-request"}

        def json(self):
            return {"error": {"message": "provider failure"}}

    monkeypatch.setattr(runner.requests.Session, "post", lambda *a, **kw: Response())
    model = runner.HTTPModel("https://provider.invalid/chat/completions", "obviously-fake-credential")
    with pytest.raises(runner.CallFailure) as caught:
        model.complete([], max_tokens=50, timeout=1)
    assert not caught.value.safe_to_retry
    assert caught.value.request_id == "failed-provider-request"
    assert caught.value.status == status
    assert caught.value.kind == "http_error"
    assert "obviously-fake-credential" not in str(caught.value)


@pytest.mark.parametrize("usage", [None, {}, {"prompt_tokens": True, "completion_tokens": 2},
                                  {"prompt_tokens": 5, "completion_tokens": -1},
                                  {"prompt_tokens": 5, "completion_tokens": 1, "prompt_tokens_details": {"cached_tokens": 6}}])
def test_invalid_usage_is_unknown_not_estimated(usage):
    with pytest.raises(runner.CallFailure, match="invalid_usage"):
        runner.usage_counts(usage)


def test_dollar_cap_blocks_worst_case_call_and_scopes_include_retry():
    ledger = runner.Ledger("0.0005", {"input": "1", "cached_input": "0.5", "output": "2"})
    attempt = ledger.reserve("job-one", 1, "pilot", prompt_bound=100, max_tokens=100)
    assert attempt is not None
    ledger.settle(attempt, usage={"prompt_tokens": 100, "completion_tokens": 20,
                                  "prompt_tokens_details": {"cached_tokens": 40}})
    retry = ledger.reserve("job-one", 1, "retry", prompt_bound=100, max_tokens=100)
    ledger.settle(retry, failure=runner.CallFailure("transport_unknown"))
    assert ledger.reserve("job-two", 1, "study", prompt_bound=100, max_tokens=100) is None
    result = ledger.report()
    assert result["stop_reason"] == "dollar_cap"
    assert result["grand_total_usd"] == "0.00042"
    assert result["scopes"]["pilot"]["usd"] == "0.00012"
    assert result["scopes"]["retry"]["usd"] == "0.0003"
    assert result["scopes"]["study"]["usd"] == "0"
    assert result["attempts"][1]["unknown_usage"] is True
    assert result["attempts"][1]["charged_tokens"] == 200


def test_reservations_count_inflight_calls_against_dollar_cap():
    ledger = runner.Ledger("0.0005", {"input": "1", "cached_input": "0.5", "output": "2"})
    first = ledger.reserve("first", 1, "study", prompt_bound=100, max_tokens=100)
    assert first is not None
    assert ledger.reserve("second", 1, "study", prompt_bound=100, max_tokens=100) is None
    ledger.settle(first, failure=runner.CallFailure("presend_failure", safe_to_retry=True))
    report = ledger.report()
    assert report["grand_total_usd"] == "0"
    assert report["attempts"][0]["unknown_usage"] is False
    assert report["attempts"][0]["charged_tokens"] == 0


def test_unknown_usage_is_charged_and_actual_overshoot_is_explicit():
    ledger = runner.Ledger("0.0001", {"input": "1", "cached_input": "0.5", "output": "2"})
    attempt = ledger.reserve("first", 1, "study", prompt_bound=20, max_tokens=20)
    ledger.settle(attempt, usage={"prompt_tokens": 100, "completion_tokens": 20}, request_id="known-request")
    report = ledger.report()
    assert report["grand_total_usd"] == "0.00014"
    assert report["overshoot_usd"] == "0.00004"
    assert report["attempts"][0]["over_reserved_tokens"] == 80
    assert report["attempts"][0]["request_id"] == "known-request"
    assert report["stop_reason"] == "dollar_cap"


def test_provider_credential_echo_is_withheld(monkeypatch):
    class Response:
        status_code = 200
        headers = {"x-request-id": "obviously-fake-credential"}

        def json(self):
            return {"choices": [{"message": {"content": "FINAL\nobviously-fake-credential"}}]}

    monkeypatch.setattr(runner.requests.Session, "post", lambda *a, **kw: Response())
    model = runner.HTTPModel("https://provider.invalid/chat/completions", "obviously-fake-credential")
    with pytest.raises(runner.CallFailure, match="credential_in_response") as caught:
        model.complete([], max_tokens=50, timeout=1)
    assert caught.value.request_id is None


@pytest.mark.parametrize('prompt,output,charged,usd', [
    (10, 2, 200, '0.0003'),
    (200, 100, 300, '0.0004'),
])
def test_ambiguous_failure_is_reserved_even_with_partial_usage(prompt, output, charged, usd):
    ledger = runner.Ledger('1', {'input': '1', 'cached_input': '0.5', 'output': '2'})
    attempt = ledger.reserve('job', 1, 'study', prompt_bound=100, max_tokens=100)
    usage = {'prompt_tokens': prompt, 'completion_tokens': output}
    failure = runner.CallFailure('http_error', status=503, usage=usage, request_id='failed-call')
    ledger.settle(attempt, usage=usage, failure=failure)
    report = ledger.report()
    recorded = report['attempts'][0]
    assert recorded['unknown_usage'] is True
    assert recorded['usage'] == usage
    assert recorded['charged_tokens'] == charged
    assert recorded['charged_usd'] == usd
    assert recorded['request_id'] == 'failed-call'
    assert recorded['http_status'] == 503


class FakeClock:
    def __init__(self):
        self.now = 0
        self.sleeps = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class ScriptedModel:
    def __init__(self, *results):
        self.results = list(results)
        self.calls = []

    def complete(self, messages, *, max_tokens, timeout):
        self.calls.append({'messages': json.loads(json.dumps(messages)), 'max_tokens': max_tokens, 'timeout': timeout})
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def response(text='thinking', prompt=100, completion=20):
    return runner.Reply(text, {'prompt_tokens': prompt, 'completion_tokens': completion}, 'request-one', 'reply-one')


def lifecycle(model, *, cap=1000, prompt_bound=100, max_usd='10'):
    clock = FakeClock()
    ledger = runner.Ledger(max_usd, {'input': '1', 'cached_input': '0.5', 'output': '2'})
    agent = runner.AgentState(1, cap, prompt_bound)
    engine = runner.RequestEngine(model, ledger, max_tokens_per_reply=100, clock=clock, sleep=clock.sleep)
    records = []
    return engine, agent, ledger, clock, records


def send(engine, agent, records, *, deadline=900, scope='study'):
    return engine.request('job-one', agent, [{'role': 'user', 'content': 'packet'}],
                          deadline=deadline, scope=scope, record=records.append)


def test_request_stops_at_cap_and_uses_previous_prompt_usage():
    model = ScriptedModel(response(prompt=150))
    engine, agent, ledger, clock, records = lifecycle(model, cap=350)
    assert send(engine, agent, records) is not None
    assert agent.charged_tokens == 170
    assert agent.prompt_bound == 150
    assert send(engine, agent, records) is None
    assert agent.stop_reason == 'token_cap'
    assert len(model.calls) == 1
    assert model.calls[0]['max_tokens'] == 100
    assert ledger.report()['scopes']['study']['charged_tokens'] == 170


def test_dollar_cap_prevents_model_call():
    model = ScriptedModel()
    engine, agent, ledger, clock, records = lifecycle(model, max_usd='0.00029')
    assert send(engine, agent, records) is None
    assert model.calls == []
    assert agent.stop_reason == 'dollar_cap'
    assert ledger.report()['stop_reason'] == 'dollar_cap'


def test_presend_retry_once_before_success_with_same_request_and_ten_second_wait():
    failure = runner.CallFailure('presend_failure', safe_to_retry=True)
    model = ScriptedModel(failure, response('verbatim\r\nreply'))
    engine, agent, ledger, clock, records = lifecycle(model)
    reply = send(engine, agent, records, scope='pilot')
    assert reply.content == 'verbatim\r\nreply'
    assert len(model.calls) == 2
    assert model.calls[0]['messages'] == model.calls[1]['messages']
    assert clock.sleeps == [10]
    attempts = ledger.report()['attempts']
    assert [a['scope'] for a in attempts] == ['pilot', 'retry']
    assert [a['job_id'] for a in attempts] == ['job-one', 'job-one']
    assert [a['charged_tokens'] for a in attempts] == [0, 120]
    assert [r['event'] for r in records] == ['request', 'failure', 'request', 'response']
    assert records[0]['messages_sha256'] == runner.sha256(runner.canonical(model.calls[0]['messages']))
    assert records[0]['messages_sha256'] == records[2]['messages_sha256']
    assert records[-1]['reply'] == 'verbatim\r\nreply'
    assert records[-1]['request_id'] == 'request-one'
    assert records[-1]['response_id'] == 'reply-one'


def test_second_presend_failure_is_not_retried():
    failure = runner.CallFailure('presend_failure', safe_to_retry=True)
    model = ScriptedModel(failure, failure)
    engine, agent, ledger, clock, records = lifecycle(model)
    assert send(engine, agent, records) is None
    assert len(model.calls) == 2
    assert clock.sleeps == [10]
    assert agent.stop_reason == 'presend_failure'
    assert len(ledger.report()['attempts']) == 2


def test_presend_failure_after_success_is_not_retried():
    model = ScriptedModel(response(), runner.CallFailure('presend_failure', safe_to_retry=True))
    engine, agent, ledger, clock, records = lifecycle(model)
    assert send(engine, agent, records) is not None
    assert send(engine, agent, records) is None
    assert len(model.calls) == 2
    assert clock.sleeps == []
    assert agent.stop_reason == 'presend_failure'


def test_ambiguous_attempt_has_no_retry_and_is_charged():
    model = ScriptedModel(runner.CallFailure('transport_unknown', request_id='ambiguous'))
    engine, agent, ledger, clock, records = lifecycle(model)
    assert send(engine, agent, records) is None
    assert len(model.calls) == 1
    assert clock.sleeps == []
    assert agent.charged_tokens == 200
    assert agent.unknown_usage_attempts == 1
    assert agent.stop_reason == 'transport_unknown'
    assert records[-1]['request_id'] == 'ambiguous'
    assert records[-1]['unknown_usage'] is True
    assert ledger.report()['grand_total_usd'] == '0.0003'


def test_invalid_usage_stops_agent_and_keeps_verbatim_reply():
    model = ScriptedModel(runner.Reply('verbatim answer', None, 'missing-usage', 'reply-two'))
    engine, agent, ledger, clock, records = lifecycle(model)
    assert send(engine, agent, records) is None
    assert agent.stop_reason == 'invalid_usage'
    assert agent.charged_tokens == 200
    assert records[-1]['reply'] == 'verbatim answer'
    assert records[-1]['request_id'] == 'missing-usage'
    assert records[-1]['usage'] is None
    assert len(model.calls) == 1


def test_token_overspend_is_reported_with_reply_bound():
    model = ScriptedModel(response(prompt=400, completion=20))
    engine, agent, ledger, clock, records = lifecycle(model, cap=200)
    assert send(engine, agent, records) is not None
    assert agent.charged_tokens == 420
    assert agent.stop_reason == 'token_cap'
    assert records[-1]['overspend_tokens'] == 220
    assert records[-1]['overspend_limit_exceeded'] is True
    assert records[-1]['max_tokens'] == 100
    assert send(engine, agent, records) is None
    assert len(model.calls) == 1


def test_deadline_checked_before_call_and_retry():
    model = ScriptedModel()
    engine, agent, ledger, clock, records = lifecycle(model)
    assert send(engine, agent, records, deadline=0) is None
    assert agent.stop_reason == 'wall_time'
    assert model.calls == []
    model = ScriptedModel(runner.CallFailure('presend_failure', safe_to_retry=True))
    engine, agent, ledger, clock, records = lifecycle(model)
    assert send(engine, agent, records, deadline=9) is None
    assert agent.stop_reason == 'wall_time'
    assert clock.sleeps == []
    assert len(model.calls) == 1


def test_retry_rechecks_dollar_cap_after_delay():
    model = ScriptedModel(runner.CallFailure('presend_failure', safe_to_retry=True))
    engine, agent, ledger, clock, records = lifecycle(model)

    def spend_elsewhere(seconds):
        clock.sleep(seconds)
        ledger.reserve('other-job', 1, 'study', prompt_bound=10_000_000, max_tokens=100)

    engine.sleep = spend_elsewhere
    assert send(engine, agent, records) is None
    assert agent.stop_reason == 'dollar_cap'
    assert len(model.calls) == 1


def test_late_response_is_charged_but_cannot_finalize_after_deadline():
    engine, agent, ledger, clock, records = lifecycle(ScriptedModel())

    class LateModel:
        def complete(self, messages, *, max_tokens, timeout):
            assert timeout == 900
            clock.now = 901
            return response('FINAL\n')

    engine.model = LateModel()
    assert send(engine, agent, records) is None
    assert agent.stop_reason == 'wall_time'
    assert agent.charged_tokens == 120
    assert records[-1]['reply'] == 'FINAL\n'
    assert ledger.report()['scopes']['study']['charged_tokens'] == 120


def test_run_accounting_contains_agent_cap_overspend():
    model = ScriptedModel(response(prompt=400, completion=20))
    engine, agent, ledger, clock, records = lifecycle(model, cap=200)
    send(engine, agent, records)
    attempt = ledger.report()['attempts'][0]
    assert attempt['overspend_tokens'] == 220
    assert attempt['overspend_limit_exceeded'] is True


def job_metadata(arm='A'):
    return {'job_id': 'job-one', 'arm': arm, 'packet': 'case-one', 'repeat': 1}


def test_outputs_persist_transcript_usage_failures_and_hashes(tmp_path):
    output = tmp_path / 'output'
    runner.claim_output(output)
    model = ScriptedModel(response('verbatim\r\nanswer', prompt=400, completion=20))
    engine, agent, ledger, clock, records = lifecycle(model, cap=200)
    writer = runner.JobOutputs(output, job_metadata(), clock=clock)
    engine.request('job-one', agent, [], deadline=900, scope='study', record=writer.record)
    clock.now = 3
    findings = {'findings': [], 'malformed': [], 'discarded': 0}
    writer.finish([agent], findings, ledger)
    runner.finish_run(output, ledger)
    job = json.loads((output / 'job-one/job.json').read_text())
    assert {k: job[k] for k in job_metadata()} == job_metadata()
    assert job['wall_seconds'] == 3
    assert job['start_utc'].endswith('Z')
    assert job['end_utc'].endswith('Z')
    assert job['agents']['1']['charged_tokens'] == 420
    assert job['agents']['1']['overspend_tokens'] == 220
    assert job['agents']['1']['unknown_usage_attempts'] == 0
    assert job['agents']['1']['usage'] == [{'prompt_tokens': 400, 'completion_tokens': 20}]
    assert job['provider_request_ids'] == ['request-one']
    assert job['overspend_tokens'] == 220
    assert job['overspend_limit_exceeded'] is True
    assert job['unknown_usage'] is False
    assert json.loads((output / 'job-one/findings.json').read_text()) == findings
    transcript = [json.loads(line) for line in (output / 'job-one/transcript.jsonl').read_text().splitlines()]
    assert transcript[0]['messages_sha256'] == runner.sha256(runner.canonical([]))
    assert transcript[1]['reply'] == 'verbatim\r\nanswer'
    manifest = json.loads((output / 'RUN-MANIFEST.json').read_text())
    assert set(manifest['files']) == {'job-one/job.json', 'job-one/findings.json', 'job-one/transcript.jsonl',
                                      'job-one/emitted_sets.jsonl', 'ACCOUNTING.json'}
    for path, digest in manifest['files'].items():
        assert runner.sha256((output / path).read_bytes()) == digest
    before = (output / 'RUN-MANIFEST.json').read_bytes()
    with pytest.raises((runner.InputError, FileExistsError)):
        runner.finish_run(output, ledger)
    assert (output / 'RUN-MANIFEST.json').read_bytes() == before
    with pytest.raises(runner.InputError):
        writer.record({'event': 'late'})


@pytest.mark.parametrize('job_id', ['../escape', '/tmp/escape', 'a/b', 'a\\b', '.', '..', ''])
def test_job_output_path_cannot_escape_root(tmp_path, job_id):
    output = tmp_path / 'output'
    runner.claim_output(output)
    job = {**job_metadata(), 'job_id': job_id}
    with pytest.raises(runner.InputError):
        runner.JobOutputs(output, job)
    assert sorted(path.name for path in output.iterdir()) == ['.running']


def test_unknown_cost_failure_is_explicit_in_job_and_run_outputs(tmp_path):
    output = tmp_path / 'output'
    runner.claim_output(output)
    model = ScriptedModel(runner.CallFailure('transport_unknown', request_id='failed-attempt'))
    engine, agent, ledger, clock, records = lifecycle(model)
    writer = runner.JobOutputs(output, job_metadata(), clock=clock)
    engine.request('job-one', agent, [], deadline=900, scope='study', record=writer.record)
    writer.finish([agent], {'findings': [], 'malformed': [], 'discarded': 0}, ledger)
    runner.finish_run(output, ledger)
    job = json.loads((output / 'job-one/job.json').read_text())
    accounting = json.loads((output / 'ACCOUNTING.json').read_text())
    assert job['unknown_usage'] is True
    assert job['agents']['1']['unknown_usage_attempts'] == 1
    assert job['failures'][0]['failure'] == 'transport_unknown'
    assert job['failures'][0]['request_id'] == 'failed-attempt'
    assert job['failures'][0]['charged_tokens'] == 200
    assert accounting['attempts'][0]['unknown_usage'] is True
    assert accounting['unknown_usage'] is True
    assert accounting['grand_total_usd'] == '0.0003'


def test_manifest_refuses_unfinished_requests_and_jobs(tmp_path):
    output = tmp_path / 'output'
    runner.claim_output(output)
    ledger = runner.Ledger('1', {'input': '1', 'cached_input': '1', 'output': '1'})
    attempt = ledger.reserve('job-one', 1, 'study', prompt_bound=100, max_tokens=100)
    with pytest.raises(runner.InputError, match='unfinished'):
        runner.finish_run(output, ledger)
    ledger.settle(attempt, failure=runner.CallFailure('transport_unknown'))
    writer = runner.JobOutputs(output, job_metadata())
    with pytest.raises(runner.InputError, match='unfinished'):
        runner.finish_run(output, ledger)
    assert not (output / 'RUN-MANIFEST.json').exists()
    writer.abort()


def test_credential_never_reaches_output_files(tmp_path, monkeypatch):
    secret = 'obviously-fake-credential'

    def post(*args, **kwargs):
        raise runner.requests.Timeout(secret)

    monkeypatch.setattr(runner.requests.Session, 'post', post)
    model = runner.HTTPModel('https://provider.invalid/chat/completions', secret)
    engine, agent, ledger, clock, records = lifecycle(model)
    output = tmp_path / 'output'
    runner.claim_output(output)
    writer = runner.JobOutputs(output, job_metadata(), clock=clock)
    engine.request('job-one', agent, [], deadline=900, scope='study', record=writer.record)
    writer.finish([agent], {'findings': [], 'malformed': [], 'discarded': 0}, ledger)
    runner.finish_run(output, ledger)
    for path in output.rglob('*'):
        if path.is_file():
            assert secret not in path.read_text()


def test_output_files_and_case_variants_cannot_replace_existing_job(tmp_path):
    output = tmp_path / 'output'
    runner.claim_output(output)
    writer = runner.JobOutputs(output, job_metadata())
    with pytest.raises(runner.InputError, match='duplicate'):
        runner.JobOutputs(output, {**job_metadata(), 'job_id': 'JOB-ONE'})
    writer.abort()
    path = output / 'receipt.json'
    runner.write_json_exclusive(path, {'original': True})
    with pytest.raises(FileExistsError):
        runner.write_json_exclusive(path, {'replacement': True})
    assert json.loads(path.read_text()) == {'original': True}
