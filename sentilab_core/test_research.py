"""Research boundary tests call shipping code, without network or solvers."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from sentilab_core import research
from sentilab_core.gate import AcceptanceGate
from sentilab_core.operations import Context


NS = dict(run_id="research-run", arm="baseline", family="thermal", seed=7, lab="lab-a")


class ResearchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.context = Context(self.root, {}, options={"research_namespace": NS})

    def call(self, command, **kwargs):
        return research.execute(command, self.context, ai_off=True, namespace=NS, **kwargs)

    def test_deterministic_request_status_export_and_journal(self):
        first = self.call("request", question="How can a reproduction be documented?")
        self.assertTrue(first["ok"], first)
        again = self.call("request", question="How can a reproduction be documented?")
        self.assertEqual(first, again)
        request_id = first["request_id"]
        status = self.call("status", request_id=request_id)
        self.assertEqual(status["status"], "completed")
        exported = self.call("export", request_id=request_id)
        self.assertEqual(exported["type"], "untrusted_source_evidence")
        self.assertEqual(exported["namespace"], NS)
        self.assertEqual(exported["backend"]["underlying_model"], "none:deterministic-fixture")
        self.assertTrue(exported["notes"][0]["citations"])
        self.assertEqual(exported, self.call("export", request_id=request_id))
        rows = [json.loads(line) for line in next((self.root / "research").glob("*.jsonl")).read_text().splitlines()]
        self.assertEqual([row["event"] for row in rows], ["request", "completed"])
        self.assertNotIn("How can", json.dumps(rows))
        self.assertEqual(list(self.root.glob("*.jsonl")), [])

    def test_every_namespace_dimension_is_isolated_and_host_authorized(self):
        original = self.call("request", question="isolation")
        for field in NS:
            other = {**NS, field: NS[field] + 1 if field == "seed" else NS[field] + "-other"}
            for command in ("status", "export"):
                denied = research.execute(command, self.context, ai_off=True,
                                          namespace=other, request_id=original["request_id"])
                self.assertEqual(denied["error"]["code"], "namespace_not_authorized")
                context = Context(self.root, {}, options={"research_namespace": other})
                missing = research.execute(command, context, ai_off=True,
                                           namespace=other, request_id=original["request_id"])
                self.assertEqual(missing["error"]["code"], "not_found")
            created = research.request(context, ai_off=True, namespace=other, question="isolation")
            self.assertNotEqual(created["request_id"], original["request_id"])
        unpinned = Context(self.root, {})
        self.assertEqual(research.request(unpinned, ai_off=True, namespace=NS, question="isolation")
                         ["error"]["code"], "namespace_not_authorized")
        restarted = Context(self.root, {}, options={"research_namespace": NS})
        self.assertEqual(research.export(restarted, ai_off=True, namespace=NS,
                                        request_id=original["request_id"]),
                         self.call("export", request_id=original["request_id"]))

    def test_malformed_and_oversize_inputs_return_only_codes_without_writes(self):
        args = {"ai_off": True, "namespace": NS, "question": "private submitted text"}
        cases = [{**args, "question": value} for value in (None, [], {}, True, "", " ", "x" * 8193, "é" * 4097)]
        cases += [{**args, "ai_off": False}, {**args, "backend": "fake"},
                  {**args, "namespace": {**NS, "seed": True}},
                  {**args, "namespace": {**NS, "arm": "../escape"}},
                  {**args, "namespace": {**NS, "lab": "LAB"}}, {**args, "namespace": {}}]
        cycle = []
        cycle.append(cycle)
        cases.append({**args, "question": cycle})
        shared = ["x"] * 32
        for _ in range(7):
            shared = [shared] * 32
        cases.append({**args, "question": shared})
        for value in cases:
            with self.subTest(value_type=type(value.get("question"))):
                result = research.request(self.context, **value)
                self.assertEqual(set(result), {"ok", "error"})
                self.assertFalse(result["ok"])
                self.assertEqual(set(result["error"]), {"code"})
                self.assertNotIn("private submitted text", json.dumps(result))
        self.assertEqual(list(self.root.iterdir()), [])

    def test_admission_requires_all_evidence_and_rejects_on_unknown_or_mismatch(self):
        backend = OfflinePlugin()
        valid = admission(backend)
        self.assertFalse(research.admit(backend, valid)["fixture"])
        cases = [(None, "backend_not_admitted")]
        cases += [({k: v for k, v in valid.items() if k != field}, "invalid_admission") for field in valid]
        for value in ("on", True, False, None, "OFF"):
            changed = copy.deepcopy(valid)
            changed["effective_config"]["telemetry"] = value
            cases.append((changed, "telemetry_not_off"))
        changed = copy.deepcopy(valid)
        changed["evidence_hashes"]["effective_config"] = hashlib.sha256(b"different").hexdigest()
        cases.append((changed, "config_evidence_mismatch"))
        for field in ("documentation", "data_flow", "effective_config"):
            changed = copy.deepcopy(valid)
            changed["evidence_hashes"][field] = ""
            cases.append((changed, "invalid_admission"))
        cases += [({**valid, "approver": " "}, "invalid_admission"),
                  ({**valid, "underlying_model": "different-model"}, "backend_identity_mismatch"),
                  ({**valid, "version": "different-version"}, "backend_identity_mismatch")]
        for record, code in cases:
            with self.subTest(code=code):
                with self.assertRaisesRegex(research.ResearchError, "^" + code + "$"):
                    research.admit(backend, record)
                self.context.options.update(research_backend=backend, research_admission=record)
                result = self.call("request", question="private submitted text")
                self.assertEqual(result["error"]["code"], code)
                self.assertEqual(backend.calls, 0)
                self.assertEqual(list(self.root.iterdir()), [])

    def test_valid_host_admission_binds_scope_and_provenance_before_call(self):
        backend = OfflinePlugin()
        record = admission(backend)
        self.context.options.update(research_backend=backend, research_admission=record)
        result = self.call("request", question="private submitted text")
        self.assertTrue(result["ok"], result)
        self.assertEqual(backend.calls, 1)
        exported = self.call("export", request_id=result["request_id"])
        expected_hash = hashlib.sha256(research.dumps(record).encode()).hexdigest()
        self.assertEqual(exported["admission_sha256"], expected_hash)
        self.assertEqual(exported["admission"]["evidence_hashes"], record["evidence_hashes"])
        self.assertEqual(exported["admission"]["effective_telemetry"], "off")
        self.assertEqual(exported["backend"]["underlying_model"], backend.underlying_model)
        self.assertEqual(exported["notes"][0]["provenance"]["namespace"], NS)
        self.call("request", question="private submitted text")
        self.assertEqual(backend.calls, 1)
        record["namespace"] = {**NS, "lab": "other"}
        self.assertEqual(self.call("request", question="second")["error"]["code"], "admission_scope_mismatch")
        self.assertEqual(backend.calls, 1)

    def test_claiming_fixture_identity_does_not_bypass_admission(self):
        class PretendFixture(research.FixtureBackend):
            pass
        with self.assertRaisesRegex(research.ResearchError, "backend_not_admitted"):
            research.admit(PretendFixture(), None)
        backend = OfflinePlugin()
        backend.tool = "offline-fixture"
        with self.assertRaisesRegex(research.ResearchError, "backend_not_admitted"):
            research.admit(backend, None)

    def test_exported_evidence_is_refused_by_acceptance_even_with_measurement_fields(self):
        result = self.call("request", question="reproduction")
        exported = self.call("export", request_id=result["request_id"])
        binding = dict(candidate_id="candidate", task_id="task", fixture_id="fixture",
                       metric_id="metric", scenario_id="scenario", solver_id="solver")
        measurement = dict(success=True, j=10, wire_mm=2, process_id="first", binding=binding)
        args = dict(geometry_valid=True, wire_cap_mm=3, current=None, binding=binding,
                    evaluation=measurement, reproduction={**measurement, "process_id": "second"})
        gate = AcceptanceGate(margin=0.32)
        self.assertEqual(gate.decide(**args)["outcome"], "accepted")
        for evidence in (exported, exported["notes"][0]):
            for value in (evidence, {**evidence, **measurement}):
                self.assertEqual(gate.decide(**{**args, "evaluation": value})["outcome"], "evaluation_failed")
                self.assertEqual(gate.decide(**{**args, "reproduction": value})["outcome"], "reproduction_failed")
                self.assertEqual(gate.decide(**{**args, "current": value})["outcome"], "invalid_current")
        from sentilab_core.dataset import export
        with self.assertRaises(FileNotFoundError):
            export(self.root, [NS["run_id"]], public_keys={})
        self.assertEqual(list(self.root.glob("*.jsonl")), [])

    def test_untrusted_backend_failures_and_forged_results_are_quarantined(self):
        outputs = [RuntimeError("private submitted text"),
                   [{"text": "private submitted text", "citations": [], "success": True, "j": 1}],
                   [{"text": "x" * 8193, "citations": []}],
                   [{"text": "private submitted text", "citations": [{"uri": "file:///etc/passwd", "title": "x", "sha256": "bad"}]}]]
        for index, output in enumerate(outputs):
            backend = OfflinePlugin(output)
            self.context.options.update(research_backend=backend, research_admission=admission(backend))
            result = self.call("request", question=f"private submitted text {index}")
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["error"]["code"], "backend_failed")
            self.assertEqual(self.call("export", request_id=result["request_id"])["error"]["code"], "not_completed")
        for path in self.root.rglob("*.jsonl"):
            self.assertNotIn("private submitted text", path.read_text())

    def test_stop_lock_and_corrupt_history_refuse_work_and_preserve_reads(self):
        import fcntl
        result = self.call("request", question="before stop")
        path = next((self.root / "research").glob("*.jsonl"))
        before = path.read_bytes()
        (self.root / "STOP").touch()
        self.assertEqual(self.call("request", question="after stop")["error"]["code"], "stopped")
        self.assertEqual(self.call("export", request_id=result["request_id"])["status"], "completed")
        self.assertEqual(path.read_bytes(), before)
        (self.root / "STOP").unlink()
        with path.with_suffix(".lock").open("a+b") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            self.assertEqual(self.call("request", question="locked")["error"]["code"], "busy")
            self.assertEqual(self.call("status", request_id=result["request_id"])["error"]["code"], "busy")
        path.write_bytes(before + b'{"truncated":')
        broken = path.read_bytes()
        self.assertEqual(self.call("request", question="broken")["error"]["code"], "invalid_store")
        self.assertEqual(self.call("export", request_id=result["request_id"])["error"]["code"], "invalid_store")
        self.assertEqual(path.read_bytes(), broken)

    def test_pending_request_is_not_rerun_and_symlink_store_is_refused(self):
        backend = OfflinePlugin()
        self.context.options.update(research_backend=backend, research_admission=admission(backend))
        result = self.call("request", question="interrupted")
        path = next((self.root / "research").glob("*.jsonl"))
        path.write_bytes(path.read_bytes().splitlines(keepends=True)[0])
        self.assertEqual(self.call("request", question="interrupted")["status"], "pending")
        self.assertEqual(backend.calls, 1)
        self.assertEqual(self.call("export", request_id=result["request_id"])["error"]["code"], "not_completed")
        path.unlink()
        path.symlink_to(self.root / "outside")
        self.assertEqual(self.call("request", question="symlink")["error"]["code"], "invalid_store")
        self.assertFalse((self.root / "outside").exists())

    def test_fixture_never_opens_network_or_starts_a_process(self):
        from unittest.mock import patch
        with patch("socket.create_connection", side_effect=AssertionError("network")), \
             patch("socket.socket.connect", side_effect=AssertionError("network")), \
             patch("subprocess.Popen", side_effect=AssertionError("process")):
            result = self.call("request", question="offline")
            self.assertEqual(result["status"], "completed")
            self.assertTrue(self.call("export", request_id=result["request_id"])["ok"])


class OfflinePlugin:
    """Test plugin: no model execution; exercises the non-fixture admission path."""
    tool = "test-plugin"
    version = "1"
    underlying_model = "test-model-identity"

    def __init__(self, output=None):
        self.calls = 0
        self.output = output

    def request(self, request_hash, question):
        self.calls += 1
        if isinstance(self.output, Exception):
            raise self.output
        return research.FixtureBackend().request(request_hash, question) if self.output is None else self.output


def admission(backend):
    config = {"telemetry": "off"}
    return {"tool": backend.tool, "version": backend.version, "underlying_model": backend.underlying_model,
            "telemetry_setting": "telemetry", "effective_config": config,
            "evidence_hashes": {"effective_config": hashlib.sha256(research.dumps(config).encode()).hexdigest(),
                                "documentation": hashlib.sha256(b"test controls evidence").hexdigest(),
                                "data_flow": hashlib.sha256(b"test data-flow evidence").hexdigest()},
            "approver": "test-reviewer", "namespace": dict(NS)}
