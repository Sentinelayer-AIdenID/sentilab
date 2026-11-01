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
