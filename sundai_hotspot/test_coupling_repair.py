"""Inert PR83 repair controls: no native process, container, network or real operator grant."""
from __future__ import annotations

from contextlib import ExitStack, nullcontext
from datetime import datetime, timedelta, timezone
from fractions import Fraction
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from sundai_hotspot import coupling_allocation as coupling
from sundai_hotspot import gate0_anchor, gate0_operator as operator, gate_zero, reference_validation as validation


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.mount = Path(self.temp.name) / "mounted runs"
        self.runs = self.mount / "coupling"
        self.runs.mkdir(parents=True)
        self.cpu = self.runs / "cpu-used.json"
        self.cpu.write_text('{"used_cpu_s": 0}')
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        for name, value in (("RUNS_MOUNT", self.mount), ("RUNS", self.runs), ("CPU_FILE", self.cpu),
                            ("LOG", self.runs / "operator-log.jsonl")):
            self.stack.enter_context(mock.patch.object(operator, name, value))
        self.mountinfo = self.entry(self.mount, self.mount)
        read_text = Path.read_text

        def read(path, *args, **kwargs):
            return self.mountinfo if path == Path("/proc/self/mountinfo") else read_text(path, *args, **kwargs)

        self.stack.enter_context(mock.patch.object(Path, "read_text", read))

    @staticmethod
    def entry(root, destination, options="rw", filesystem="ext4"):
        def encode(path):
            return Path(path).as_posix().replace("\\", "\\134").replace(" ", "\\040")
        return f"36 25 8:1 {encode(root)} {encode(destination)} {options},relatime - {filesystem} /dev/sda1 rw\n"

    def assert_cli_refused_before_effects(self, command="run", *extra):
        argv = [command, "--manifest", "coupling", *extra]
        if command in ("run", "grant"):
            argv += ["--grant-id", "unused-test-identity"]
        with ExitStack() as stack:
            effects = [stack.enter_context(mock.patch.object(operator, name))
                       for name in ("cmd_grant", "cmd_run", "cmd_readback", "log", "run_call")]
            effects += [stack.enter_context(mock.patch.object(gate0_anchor, name))
                        for name in ("open_ledger", "_create_tag")]
            with self.assertRaises(SystemExit):
                operator.main(argv)
            for effect in effects:
                effect.assert_not_called()

    def test_valid_enclosing_mount_and_fresh_report_path(self):
        operator.require_coupling_storage(self.runs / "report.json")
        self.assertEqual(operator.carried_cpu_s(required=True), 0)

    def test_missing_or_wrong_mount_refuses_before_any_dispatch(self):
        cases = ("", self.entry(self.mount.parent, self.mount), self.entry(self.mount, self.mount, "ro"),
                 self.entry(self.mount, self.mount, filesystem="tmpfs"), "malformed\n",
                 self.entry(self.mount, self.mount) * 2,
                 self.entry(self.mount, self.mount) + self.entry(self.mount / "other", self.runs))
        for data in cases:
            with self.subTest(mountinfo=data):
                self.mountinfo = data
                self.assert_cli_refused_before_effects()
                self.assert_cli_refused_before_effects("grant")

    def test_absent_owner_directory_is_not_created(self):
        self.cpu.unlink()
        self.runs.rmdir()
        self.assert_cli_refused_before_effects()
        self.assertFalse(self.runs.exists())

    def test_missing_unknown_or_invalid_carry_never_resets_to_zero(self):
        self.cpu.unlink()
        self.assert_cli_refused_before_effects()
        self.assert_cli_refused_before_effects("grant")
        for value in (None, float("nan"), float("inf"), -1, True, "0"):
            with self.subTest(carry=value):
                self.cpu.write_text(json.dumps({"used_cpu_s": value}))
                self.assert_cli_refused_before_effects()
        self.cpu.write_text('{"used_cpu_s": 81.25}')
        self.assertEqual(operator.carried_cpu_s(required=True), 81.25)

    def test_report_outside_persistent_tree_refuses(self):
        self.assert_cli_refused_before_effects("report", "--out", str(self.mount.parent / "lost.json"))

    def test_report_cannot_overwrite_carry_log_or_call_evidence(self):
        for path in (self.cpu, self.cpu.with_suffix(".tmp"), operator.LOG, self.runs / "call" / "receipt.json"):
            with self.subTest(path=path):
                self.assert_cli_refused_before_effects("report", "--out", str(path))

    def test_escaping_file_and_directory_symlinks_refuse(self):
        outside = self.mount.parent / "outside"
        outside.mkdir()
        target = outside / "evidence"
        target.write_text("retained")
        for name in ("cpu-used.json", "cpu-used.tmp", "operator-log.jsonl", "report.json"):
            path = self.runs / name
            if path.exists():
                path.unlink()
            try:
                path.symlink_to(target)
            except OSError as exc:
                self.skipTest(f"symlink creation unavailable on this test host: {exc}")
            with self.subTest(path=name):
                self.assert_cli_refused_before_effects("report", "--out", str(self.runs / "report.json"))
            path.unlink()
        self.runs.rmdir()
        self.runs.symlink_to(outside, target_is_directory=True)
        self.assert_cli_refused_before_effects()


class DeadlineTests(unittest.TestCase):
    def test_separate_deadline_and_unchanged_envelope(self):
        manifest = coupling.build_manifest()
        self.assertEqual(manifest["grant_window"]["not_after_utc"], "2026-11-02T06:00:00Z")
        self.assertEqual(len(manifest["calls"]), 4)
        self.assertEqual({key: manifest["accounting"][key] for key in
                          ("manifest_cpu_cap_s", "concurrency", "retries")},
                         {"manifest_cpu_cap_s": 234, "concurrency": 1, "retries": 0})
        self.assertEqual(validation.load_manifest()[1],
                         "23a1a74b9d4fd56e5fa192982d74d9eaa90f6aeaf81d718247d566f12612053b")

    def test_entry_and_ledger_admission_share_inclusive_deadline(self):
        manifest = coupling.build_manifest()
        call = manifest["calls"][0]
        deadline = datetime(2026, 11, 2, 6, tzinfo=timezone.utc)
        for moment in (datetime(2026, 11, 1, 13, tzinfo=timezone.utc), deadline - timedelta(microseconds=1),
                       deadline, deadline + timedelta(microseconds=1)):
            accepted = moment <= deadline
            with self.subTest(moment=moment), ExitStack() as stack:
                stack.enter_context(mock.patch.object(validation, "os", SimpleNamespace(name="posix", environ={})))
                stack.enter_context(mock.patch.object(validation, "resource", object()))
                stack.enter_context(mock.patch.object(validation.platform, "machine",
                                                     return_value=manifest["accounting"]["host_architecture"]))
                if accepted:
                    self.assertEqual(validation.admit(call["id"], manifest, timeout_s=call["timeout_s"], now=moment), call)
                else:
                    with self.assertRaises(validation.CallRefused):
                        validation.admit(call["id"], manifest, timeout_s=call["timeout_s"], now=moment)
                # Exercise the ledger's real time decision with inert authenticated-state/API doubles.
                # This control does not claim to test signatures, flock or external persistence.
                grant = {"grant_id": "test", "calls": [call["id"]], "not_before_utc": "2026-11-01T00:00:00Z",
                         "not_after_utc": manifest["grant_window"]["not_after_utc"], "cpu_cap_s": 234}
                for name, value in (("public_key_hex", "test-key"), ("_lock", nullcontext()),
                                    ("read_ledger", {"grant": grant}), ("call_entries", {}),
                                    ("admission_charge", 0)):
                    stack.enter_context(mock.patch.object(gate0_anchor, name, return_value=value))
                reader = stack.enter_context(mock.patch.object(gate0_anchor, "TagReader")).return_value
                reader.admissions.return_value = {"entries": [], "next_seq": 1, "total_cpu_s": 0, "head_sha": None}
                reader.resolve.return_value = ({}, {"tree": {"sha": "tree"}, "sha": "reserve"})
                create = stack.enter_context(mock.patch.object(gate0_anchor, "_create_tag", return_value="test-admit"))
                append = stack.enter_context(mock.patch.object(gate0_anchor, "_append_entry"))
                args = (Path("unused"), object(), "test-key", "f" * 64, call["id"], {})
                kwargs = {"request": mock.Mock(), "envelopes": {call["id"]: 58.5}, "now": moment,
                          "not_after_utc": manifest["grant_window"]["not_after_utc"]}
                if accepted:
                    gate0_anchor.admit_and_reserve(*args, **kwargs)
                    self.assertFalse(append.call_args.args[-1]["admission"]["late"])
                    create.assert_called_once()
                else:
                    with self.assertRaises(gate0_anchor.AdmissionRefused):
                        gate0_anchor.admit_and_reserve(*args, **kwargs)
                    create.assert_not_called()
                    append.assert_not_called()

    def test_grant_uses_coupling_deadline_and_refuses_excess_cap(self):
        manifest, digest = coupling.load_manifest()
        args = SimpleNamespace(manifest="coupling", key=Path("unused"), ledger_root=Path("unused"),
                               grant_id="test", cap=None)
        with mock.patch.object(operator, "load", return_value=(manifest, digest)), \
                mock.patch.object(operator, "check_key"), mock.patch.object(operator, "log"), \
                mock.patch.object(gate0_anchor, "open_ledger", return_value={}) as create, \
                mock.patch.object(gate0_anchor, "read_ledger", return_value={"dir": "unused"}):
            operator.cmd_grant(args)
            self.assertEqual(create.call_args.kwargs["not_after_utc"], "2026-11-02T06:00:00Z")
            self.assertEqual(create.call_args.kwargs["cpu_cap_s"], 234)
            create.reset_mock()
            args.cap = 234.001
            with self.assertRaises(SystemExit):
                operator.cmd_grant(args)
            create.assert_not_called()


class OutcomeTests(unittest.TestCase):
    def synthetic_report(self, ascend, cpu, *, missing=None, mismatch=None):
        manifest = coupling.build_manifest()
        ratios = dict(zip(coupling.PERCENTAGE_REFERENCES.values(), (ascend, cpu)))

        def verify(call, *args):
            if call["id"] == missing:
                raise gate_zero.GateZeroRefusal("synthetic missing or unusable evidence")
            return {"evidence": {"directory": Path("unused"), "record": {}, "receipt": {"evaluator": {}},
                                  "output_sha256": {}}, "settlement": {}}

        def evaluate(call, *args):
            fraction = ratios[call["reference"]]
            return {"fraction_exact": str(fraction), "fraction_percent": coupling.whole_percent(fraction),
                    "threshold_met": fraction >= Fraction(17, 20),
                    "replay_byte_identical": None if call["role"] == "primary" else call["id"] != mismatch}

        with mock.patch.object(gate_zero, "verify_call", side_effect=verify), \
                mock.patch.object(coupling, "primary_directory", return_value=None), \
                mock.patch.object(coupling, "evaluate_call", side_effect=evaluate):
            return coupling.report(manifest, "test", {"grant": {"grant_id": "unused"}}, None)

    def test_mixed_names_reverse_and_exact_miss_never_displays_85(self):
        for ascend, cpu, passing, failing in ((Fraction(9, 10), Fraction(169, 200), "Ascend 910", "CPU-DRAM"),
                                             (Fraction(169, 200), Fraction(9, 10), "CPU-DRAM", "Ascend 910")):
            with self.subTest(passing=passing):
                report = self.synthetic_report(ascend, cpu)
                self.assertEqual(report["coupling"]["outcome"], "MIXED")
                self.assertEqual(report["coupling"]["wording"],
                    f"On {passing}, that one change accounts for 90% of the difference, rounded down, meeting "
                    f"the 85% we fixed. On {failing}, it accounts for 84%, rounded down, below the 85% we fixed, "
                    "so something else also contributes there. It doesn't meet the bar on both references. "
                    "It doesn't tell us what the authors intended, or which version matches hardware.")
                self.assertEqual([row["primary"]["fraction_exact"] for row in report["rows"]],
                                 [str(ascend), str(cpu)])

    def test_both_meet_and_both_miss_use_named_approved_wording(self):
        for fraction, outcome, word in ((Fraction(17, 20), "MEETS", "Both meet the 85% we fixed."),
                                         (Fraction(7, 10), "MISSES", "Both are below the 85% we fixed.")):
            result = self.synthetic_report(fraction, fraction)["coupling"]
            self.assertEqual(result["outcome"], outcome)
            self.assertIn(word, result["wording"])
            self.assertIn("Ascend 910", result["wording"])
            self.assertIn("CPU-DRAM", result["wording"])
            self.assertIn("rounded down", result["wording"])
            self.assertEqual("localizes" in result["wording"], outcome == "MEETS")

    def test_missing_or_nonidentical_replay_takes_no_claim_precedence(self):
        for call in coupling.build_manifest()["calls"]:
            result = self.synthetic_report(Fraction(7, 10), Fraction(9, 10), missing=call["id"])["coupling"]
            self.assertEqual(result["outcome"], "DOESN'T COMPLETE")
            self.assertEqual(result["wording"], "The run didn't complete, so we make no claim from it.")
            if call["role"] == "replay":
                result = self.synthetic_report(Fraction(7, 10), Fraction(9, 10), mismatch=call["id"])["coupling"]
                self.assertEqual(result["outcome"], "DOESN'T COMPLETE")

    def test_floor_preserves_tiny_residuals_and_unbounded_percentages(self):
        cases = ((Fraction(17, 20), 85), (Fraction(169, 200), 84),
                 (Fraction(16999999999999999, 20000000000000000), 84),
                 (Fraction(-1, 200), -1), (Fraction(201, 200), 100), (Fraction(11, 10), 110))
        for value, expected in cases:
            self.assertEqual(coupling.whole_percent(value), expected)


if __name__ == "__main__":
    unittest.main()
