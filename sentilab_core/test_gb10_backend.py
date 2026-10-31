"""Offline boundary checks. Real SSH is forbidden by the harness in every test."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest import mock

from . import gb10_backend as backend
from . import gb10_readonly as readonly


REAL_POPEN = subprocess.Popen


def status_response():
    return {"schema": readonly.PROBE_SCHEMA, "operation": "status",
            "identity": dict(backend.EXPECTED_IDENTITY),
            "device": {"python": "3.12.3", "driver": "580.178.04", "gpu_model": "NVIDIA GB10",
                       "memory_bytes": 130594140160}}


def checkpoint_response():
    return {"schema": readonly.PROBE_SCHEMA, "operation": "checkpoint",
            "identity": dict(backend.EXPECTED_IDENTITY),
            "artifacts": [{"name": name, "status": "verified", "bytes": size, "sha256": digest}
                          for name, size, digest in readonly.ARTIFACTS]}


class BoundaryTests(unittest.TestCase):
    def setUp(self):
        self.no_real_process = mock.patch.object(backend.subprocess, "Popen",
                                                side_effect=AssertionError("real SSH forbidden"))
        self.no_real_process.start()
        self.addCleanup(self.no_real_process.stop)

    @contextmanager
    def fake_ssh(self, response=None, *, behavior=None):
        """The only spawned child is this interpreter, never a network client."""
        if behavior is None:
            raw = json.dumps(response).encode() if isinstance(response, dict) else response
            behavior = "import sys; source=sys.stdin.buffer.read(); assert b'def probe(' in source; sys.stdout.buffer.write(" + repr(raw) + ")"
        children, calls = [], []

        def start(argv, **kwargs):
            self.assertEqual(argv[0], "ssh")
            self.assertEqual(argv[-2], "gb10")
            self.assertIn(argv[-1], ["python3 -I -S -B - status", "python3 -I -S -B - checkpoint"])
            self.assertFalse(kwargs["shell"])
            calls.append(argv)
            process = REAL_POPEN([sys.executable, "-I", "-S", "-B", "-c", behavior], **kwargs)
            children.append(process)
            return process

        with mock.patch.object(backend.subprocess, "Popen", side_effect=start):
            yield calls
        for child in children:
            self.assertIsNotNone(child.poll(), "fake SSH must be reaped")

    def test_status_uses_fixed_hardened_command_and_preserves_scope(self):
        with self.fake_ssh(status_response()) as calls:
            result = backend.execute("status")
        self.assertTrue(result["ok"])
        self.assertEqual(result["scope_state"], "staged_open")
        self.assertEqual(result["status"], "observed")
        self.assertEqual(result["serve_state"], "not_observed")
        self.assertEqual(result["gpu_readiness"], "not_tested")
        command = calls[0]
        for value in ["BatchMode=yes", "StrictHostKeyChecking=yes", "ConnectTimeout=5",
                      "ClearAllForwardings=yes", "PermitLocalCommand=no", "RemoteCommand=none",
                      "ControlMaster=no", "ControlPath=none", "-a", "-x", "-T"]:
            self.assertIn(value, command)
        self.assertNotIn("StrictHostKeyChecking=no", command)

    def test_unknown_gpu_metadata_is_unknown_not_readiness(self):
        observed = status_response()
        observed["device"].update(gpu_model=None, driver=None)
        with self.fake_ssh(observed):
            result = backend.execute("status")
        self.assertTrue(result["ok"])
        self.assertIsNone(result["device"]["gpu_model"])
        self.assertEqual(result["gpu_readiness"], "not_tested")

    def test_actual_source_runs_as_stdin_program_with_guarded_readonly_device(self):
        # Execute the actual transmitted source. The fake host supplies only the
        # two allowed proc files; any other file open or process start fails.
        behavior = '''
import builtins, contextlib, hashlib, io, json, os, pathlib, platform, re
import signal, stat, subprocess, sys, types
source = sys.stdin.buffer.read()
def forbidden(*a, **kw):
    raise AssertionError("unexpected fake host access")
def open_proc(path, mode="r", *a, **kw):
    assert mode == "rb"
    key = path.as_posix()
    files = {
        "/proc/driver/nvidia/version": b"NVRM version: NVIDIA 580.178.04 Release Build",
        "/proc/driver/nvidia/gpus/0000:01:00.0/information": b"Model: NVIDIA GB10\\n",
    }
    assert key in files
    return io.BytesIO(files[key])
class Entries:
    def __enter__(self):
        return iter([types.SimpleNamespace(name="0000:01:00.0", path="/proc/driver/nvidia/gpus/0000:01:00.0")])
    def __exit__(self, *a):
        pass
def scandir(path):
    assert path == "/proc/driver/nvidia/gpus"
    return Entries()
platform.node = lambda: "promaxgb10-9a1e"
platform.machine = lambda: "aarch64"
platform.python_version = lambda: "3.12.3"
sys.modules["pwd"] = types.SimpleNamespace(getpwuid=lambda _: types.SimpleNamespace(pw_name="dell"))
os.geteuid = lambda: 1000
os.sysconf = lambda name: {"SC_PAGE_SIZE": 4096, "SC_PHYS_PAGES": 31883516}[name]
os.scandir = scandir
pathlib.Path.open = open_proc
builtins.open = os.open = os.write = subprocess.Popen = forbidden
signal.alarm = lambda seconds: None
sys.argv = ["-", "status"]
exec(compile(source, "<gb10-readonly-stdin>", "exec"), {"__name__": "__main__"})
'''
        with self.fake_ssh(behavior=behavior):
            result = backend.execute("status")
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["device"]["gpu_model"], "NVIDIA GB10")

    def test_grants_and_all_caller_host_path_overrides_are_rejected_without_io(self):
        for key in ["host", "ssh_alias", "ssh_options", "command", "path", "root", "pc_root",
                    "remote_root", "ssh_executable", "grant", "grant_token", "timeout"]:
            for operation in ["status", "checkpoint_verify", "serve"]:
                with self.subTest(key=key, operation=operation):
                    result = backend.execute(operation, **{key: "$(private-fixture)"})
                    self.assertFalse(result["ok"])
                    self.assertEqual(result["error"]["code"], "invalid_input")
                    self.assertNotIn("private-fixture", json.dumps(result))

    def test_invalid_operations_and_argument_types_never_start_process(self):
        for operation in [None, [], {}, 1, True, "run", "stop", "status; rm", ""]:
            self.assertEqual(backend.execute(operation)["error"]["code"], "invalid_input")
        for value in [None, [], {}, 1, True, "GB10", "../adapter", "pc; touch /tmp/x"]:
            self.assertEqual(backend.execute("checkpoint_verify", location=value)["error"]["code"], "invalid_input")
            self.assertEqual(backend.execute("serve", action=value)["error"]["code"], "invalid_input")

    def test_context_is_not_a_caller_configuration_channel(self):
        class PoisonContext:
            def __getattribute__(self, name):
                raise AssertionError("context must not be read")
        with self.fake_ssh(status_response()):
            result = backend.execute("status", PoisonContext())
        self.assertTrue(result["ok"])

    def test_serve_is_always_pending_or_refused_and_never_reuses_old_grant(self):
        for action, status, code in [("status", "pending", "prospective_gpu_grant_pending"),
                                     ("start", "refused", "gpu_grant_required"),
                                     ("stop", "refused", "no_managed_serve_session")]:
            with self.subTest(action=action):
                result = backend.execute("serve", action=action)
                self.assertFalse(result["ok"])
                self.assertFalse(result["launched"])
                self.assertEqual(result["status"], status)
                self.assertEqual(result["error"]["code"], code)
                self.assertEqual(result["scope_state"], "staged_open")
                self.assertEqual(result["live_service_state"], "not_observed")
                self.assertIsNone(result["managed_session"])

    def test_remote_checkpoint_validates_every_pin(self):
        with self.fake_ssh(checkpoint_response()):
            result = backend.execute("checkpoint_verify", location="gb10")
        self.assertTrue(result["ok"])
        self.assertEqual(result["claim"], "retained_file_integrity_only")
        self.assertFalse(result["held_out_evaluation"])
        self.assertEqual(result["scope_state"], "staged_open")

    def test_both_locations_keep_local_success_when_remote_unavailable(self):
        with mock.patch.object(readonly, "checkpoint", return_value=checkpoint_response()["artifacts"]) as local:
            with self.fake_ssh(behavior="import sys; sys.stdin.buffer.read(); sys.stderr.write('private-fixture'); sys.exit(255)"):
                result = backend.execute("checkpoint_verify")
        local.assert_called_once_with(readonly.PC_ROOT)
        self.assertFalse(result["ok"])
        self.assertEqual(result["locations"]["pc"]["artifacts"][0]["status"], "verified")
        self.assertEqual(result["locations"]["gb10"]["error"]["code"], "ssh_failed")
        self.assertNotIn("private-fixture", json.dumps(result))

    def test_pc_only_never_uses_ssh(self):
        with mock.patch.object(readonly, "checkpoint", return_value=checkpoint_response()["artifacts"]):
            result = backend.execute("checkpoint_verify", location="pc")
        self.assertTrue(result["ok"])
        self.assertEqual(set(result["locations"]), {"pc"})

    def test_missing_artifact_is_unverified(self):
        observed = checkpoint_response()
        observed["artifacts"][0].update(status="missing", bytes=None, sha256=None)
        with self.fake_ssh(observed):
            result = backend.execute("checkpoint_verify", location="gb10")
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "unverified")

    def test_ssh_failure_does_not_expose_diagnostics(self):
        with self.fake_ssh(behavior="import sys; sys.stdin.buffer.read(); sys.stderr.write('private-fixture'); sys.exit(255)"):
            result = backend.execute("status")
        self.assertEqual(result["error"]["code"], "ssh_failed")
        self.assertNotIn("private-fixture", json.dumps(result))

    def test_unavailable_executable_is_sanitized(self):
        with mock.patch.object(backend.subprocess, "Popen", side_effect=OSError("private-fixture")):
            result = backend.execute("status")
        self.assertEqual(result["error"]["code"], "ssh_unavailable")
        self.assertNotIn("private-fixture", json.dumps(result))

    def test_timeout_including_peer_not_reading_stdin(self):
        for behavior in ["import time; time.sleep(60)", "import sys,time; sys.stdin.buffer.read(); time.sleep(60)"]:
            with self.subTest(behavior=behavior), mock.patch.object(backend, "SSH_TIMEOUT_SECONDS", 0.15):
                started = time.monotonic()
                with self.fake_ssh(behavior=behavior):
                    result = backend.execute("status")
                self.assertEqual(result["error"]["code"], "ssh_timeout")
                self.assertLess(time.monotonic() - started, 3)

    def test_stdout_and_stderr_floods_are_bounded(self):
        for channel in ["stdout", "stderr"]:
            with self.subTest(channel=channel):
                behavior = "import sys; sys.stdin.buffer.read(); sys." + channel + ".buffer.write(b'x'*1000000)"
                with self.fake_ssh(behavior=behavior):
                    result = backend.execute("status")
                self.assertEqual(result["error"]["code"], "ssh_output_oversize")
                self.assertLess(len(json.dumps(result)), 500)

    def test_source_limit_precedes_spawn(self):
        with self.assertRaisesRegex(backend.ProbeError, "probe_source_oversize"):
            backend._capture(["ssh"], b"x" * (backend.MAX_SCRIPT_BYTES + 1))


class ParserTests(unittest.TestCase):
    def test_malformed_protocol_and_duplicate_keys(self):
        base = json.dumps(status_response())
        values = [b"", b"private-fixture", b"\xff", b"[]", b"null", base.encode() + b"x",
                  base.replace('"memory_bytes": 130594140160', '"memory_bytes": NaN').encode(),
                  base.replace('"memory_bytes": 130594140160', '"memory_bytes": true').encode(),
                  base.replace('"schema":', '"schema":"duplicate", "schema":').encode(),
                  b"[" * 3000 + b"]" * 3000,
                  b"x" * (backend.MAX_OUTPUT_BYTES + 1)]
        for value in values:
            with self.subTest(value=value[:40]), self.assertRaisesRegex(backend.ProbeError, "invalid_probe_response"):
                backend._parse(value, "status")

    def test_wrong_device_is_not_accepted(self):
        for key in backend.EXPECTED_IDENTITY:
            observed = status_response()
            observed["identity"][key] = "another-device"
            with self.subTest(key=key), self.assertRaisesRegex(backend.ProbeError, "device_identity_mismatch"):
                backend._parse(json.dumps(observed).encode(), "status")

    def test_extra_or_unexpected_device_fields_are_rejected(self):
        mutations = [lambda x: x.update(extra="private-fixture"),
                     lambda x: x.update(operation="checkpoint"),
                     lambda x: x["device"].update(extra="private-fixture"),
                     lambda x: x["device"].update(gpu_model="fake GPU"),
                     lambda x: x["device"].update(driver="private-fixture"),
                     lambda x: x["device"].update(python="private-fixture"),
                     lambda x: x["device"].update(memory_bytes=-1)]
        for change in mutations:
            observed = status_response()
            change(observed)
            with self.assertRaisesRegex(backend.ProbeError, "invalid_probe_response"):
                backend._parse(json.dumps(observed).encode(), "status")

    def test_inconsistent_checkpoint_success_is_rejected(self):
        mutations = [lambda a: a.pop(), lambda a: a.reverse(),
                     lambda a: a[0].update(sha256="0" * 64),
                     lambda a: a[0].update(bytes=1), lambda a: a[0].update(bytes=True),
                     lambda a: a[0].update(name="../../private-key"),
                     lambda a: a[0].update(status=[]),
                     lambda a: a[0].update(status="size_mismatch"),
                     lambda a: a[0].update(status="hash_mismatch"),
                     lambda a: a[0].update(secret="private-fixture")]
        for change in mutations:
            observed = checkpoint_response()
            change(observed["artifacts"])
            with self.assertRaisesRegex(backend.ProbeError, "invalid_probe_response"):
                backend._parse(json.dumps(observed).encode(), "checkpoint")


class FileChecks(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        # macOS /var may itself be a symlink; use the real test root explicitly.
        self.root = Path(self.directory.name).resolve()
        self.path = self.root / "adapter.safetensors"
        self.data = b"fixture adapter bytes"
        self.path.write_bytes(self.data)
        self.size = len(self.data)
        self.digest = hashlib.sha256(self.data).hexdigest()

    def check(self, path=None):
        return readonly.verify_file(self.path if path is None else path, name="fixture",
                                    size=self.size, sha256=self.digest)

    def test_positive_control_and_hash_mismatch(self):
        self.assertEqual(self.check()["status"], "verified")
        self.path.write_bytes(b"x" * self.size)
        self.assertEqual(self.check()["status"], "hash_mismatch")

    def test_missing_size_mismatch_directory_and_relative_path(self):
        self.assertEqual(self.check(self.root / "missing")["status"], "missing")
        self.assertEqual(self.check(self.root)["status"], "unsafe_path")
        self.assertEqual(self.check(Path("relative"))["status"], "unsafe_path")
        self.assertEqual(self.check(self.root / ".." / self.path.name)["status"], "unsafe_path")
        self.path.write_bytes(self.data + b"extra")
        with mock.patch.object(readonly.os, "read", side_effect=AssertionError("oversize artifact read")):
            self.assertEqual(self.check()["status"], "size_mismatch")

    def test_symlink_leaf_and_parent_are_refused(self):
        alias = self.root / "alias"
        parent = self.root / "parent"
        try:
            alias.symlink_to(self.path)
            parent.symlink_to(self.root, target_is_directory=True)
        except OSError:
            self.skipTest("platform does not permit creating test symlinks")
        self.assertEqual(self.check(alias)["status"], "unsafe_path")
        self.assertEqual(self.check(parent / self.path.name)["status"], "unsafe_path")

    def test_windows_reparse_attribute_is_refused_before_open(self):
        actual_lstat = Path.lstat

        def lstat(path, *args, **kwargs):
            info = actual_lstat(path, *args, **kwargs)
            if path == self.path:
                return SimpleNamespace(st_mode=info.st_mode, st_file_attributes=1024)
            return info

        with mock.patch.object(Path, "lstat", lstat), mock.patch.object(readonly.os, "open", side_effect=AssertionError("reparse point opened")):
            self.assertEqual(self.check()["status"], "unsafe_path")

    @unittest.skipUnless(os.name == "posix", "FIFO and openat are POSIX-specific")
    def test_fifo_is_refused_before_open(self):
        fifo = self.root / "fifo"
        os.mkfifo(fifo)
        with mock.patch.object(readonly.os, "open", side_effect=AssertionError("FIFO opened")):
            self.assertEqual(self.check(fifo)["status"], "unsafe_path")

    def test_replacement_during_hash_cannot_produce_false_success(self):
        replacement = self.root / "replacement"
        replacement.write_bytes(b"x" * self.size)
        actual_read, attempted, blocked = os.read, [], []

        def read(descriptor, size):
            data = actual_read(descriptor, size)
            if not attempted:
                attempted.append(True)
                try:
                    os.replace(replacement, self.path)
                except PermissionError:
                    blocked.append(True)  # Windows may deny replacement of an open file.
            return data

        with mock.patch.object(readonly.os, "read", read):
            observed = self.check()
        self.assertTrue(attempted)
        if blocked:
            self.assertEqual(self.path.read_bytes(), self.data)
            self.assertEqual(observed["status"], "verified")
        else:
            self.assertEqual(observed["status"], "changed_during_read")

    def test_leaf_replacement_between_check_and_open_is_detected(self):
        replacement = self.root / "replacement"
        replacement.write_bytes(self.data)
        actual_open = readonly._open_file

        def replace_then_open(path, stack):
            os.replace(replacement, self.path)
            return actual_open(path, stack)

        with mock.patch.object(readonly, "_open_file", replace_then_open):
            self.assertEqual(self.check()["status"], "changed_during_read")

    @unittest.skipUnless(os.name == "posix", "directory no-follow race is POSIX-specific")
    def test_parent_swapped_for_symlink_between_check_and_open_is_refused(self):
        parent = self.root / "parent"
        parent.mkdir()
        target = parent / self.path.name
        target.write_bytes(self.data)
        moved = self.root / "moved"
        actual_open = readonly._open_file

        def replace_then_open(path, stack):
            parent.rename(moved)
            parent.symlink_to(moved, target_is_directory=True)
            return actual_open(path, stack)

        with mock.patch.object(readonly, "_open_file", replace_then_open):
            self.assertIn(self.check(target)["status"], {"unsafe_path", "unreadable", "changed_during_read"})

    def test_growth_and_truncation_during_hash_are_refused(self):
        for replacement in [b"", self.data + b"extra"]:
            self.path.write_bytes(self.data)
            actual_read, changed = os.read, []

            def read(descriptor, size):
                data = actual_read(descriptor, size)
                if not changed:
                    changed.append(True)
                    self.path.write_bytes(replacement)
                return data

            with self.subTest(size=len(replacement)), mock.patch.object(readonly.os, "read", read):
                self.assertEqual(self.check()["status"], "changed_during_read")

    def test_io_failure_contains_no_path_or_raw_error(self):
        with mock.patch.object(readonly, "_open_file", side_effect=OSError("private-fixture")):
            result = self.check()
        self.assertEqual(result["status"], "unreadable")
        self.assertNotIn("private-fixture", json.dumps(result))

    def test_checkpoint_uses_exact_three_artifacts(self):
        with mock.patch.object(readonly, "verify_file", return_value={}) as verify:
            readonly.checkpoint(self.root)
        self.assertEqual(verify.call_count, 3)
        for call, (name, size, digest) in zip(verify.call_args_list, readonly.ARTIFACTS):
            self.assertEqual(call.args, (self.root / name,))
            self.assertEqual(call.kwargs, {"name": name, "size": size, "sha256": digest})

    def test_production_pins_match_committed_slab018_metadata(self):
        evidence = Path(__file__).resolve().parents[1] / "docs/sentilab/evidence/SLAB-018"
        manifest = json.loads((evidence / "attempt-01/REMOTE-ARTIFACT-MANIFEST.json").read_text())
        for name, size, digest in readonly.ARTIFACTS:
            self.assertEqual(manifest["files"][name], {"bytes": size, "sha256": digest})
        location = json.loads((evidence / "ADAPTER-LOCATION.json").read_text())
        self.assertEqual(str(Path(readonly.REMOTE_ROOT) / readonly.ARTIFACTS[0][0]).replace("\\", "/"), location["retainedOnGb10"])
        self.assertEqual(str(Path(readonly.PC_ROOT) / readonly.ARTIFACTS[0][0]).replace("\\", "/"), location["retainedOnPc"].replace("\\", "/"))


if __name__ == "__main__":
    unittest.main()
