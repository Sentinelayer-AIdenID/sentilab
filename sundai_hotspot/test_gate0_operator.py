"""The operator supervisor's cap path (SLAB-049, root #57395). When the cumulative CPU cap fires, every process group
the call owns is killed and reaped, the solver's own session included, and the call is charged the CPU read after
that reap. The tests use synthetic processes only: Python stand-ins for validate-reference and for the solver, which
starts in its own session and ignores SIGTERM. There is no HotSpot, no grant, no tag and no network.

Each run happens in a fresh helper process that acts as the supervisor (gate0_operator.run_call). Its child-subreaper
flag and its reaping therefore never touch the test runner's own children, and the test checks the outcome from
outside.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]

# validate-reference's stand-in. It launches the solver the way reference_validation launches HotSpot (in its own
# session, with its output going to files), waits until the solver is up, and then either waits for it ("waits") or
# dies without settling ("dies"). With "preexisting" it starts nothing.
PARENT = r'''
import os, pathlib, subprocess, sys, time
here, solver_code, mode = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3]
if mode == "preexisting":
    sys.exit(0)
solver = subprocess.Popen([sys.executable, "-c", solver_code, str(here)], start_new_session=True,
                          stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
deadline = time.monotonic() + 10
while not (here / "solver.pid").exists() and time.monotonic() < deadline:
    time.sleep(0.005)
if mode == "dies":
    os._exit(9)
solver.wait()
'''

# The solver's stand-in. It runs in its own session (it records pid, session and group), ignores SIGTERM and spins,
# recording the CPU it has used. It is bounded on its own (RLIMIT_CPU 5 s, a 10 s wall deadline) in case nothing
# kills it.
SOLVER = r'''
import os, pathlib, resource, signal, sys, time
resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
signal.signal(signal.SIGTERM, signal.SIG_IGN)
here = pathlib.Path(sys.argv[1])
(here / "solver.pid.tmp").write_text(f"{os.getpid()} {os.getsid(0)} {os.getpgrp()}")
os.replace(here / "solver.pid.tmp", here / "solver.pid")
end, last = time.monotonic() + 10, 0.0
while time.monotonic() < end:
    for _ in range(20000):
        pass
    used = time.process_time()
    if used - last >= 0.02:
        last = used
        (here / "solver.cpu.tmp").write_text(repr(used))
        os.replace(here / "solver.cpu.tmp", here / "solver.cpu")
'''

# The supervisor: gate0_operator.run_call on the stand-in. It is metered by its own process tree here; in production
# the meter is the container's cgroup. With meter_failure set, reads start failing once the solver is up: one read only
# ("transient"; later reads would succeed), or every read from then on, including the one after the reap
# ("persistent"). The supervisor then reports whether any child or descendant is left, and whether a next run would
# start.
SUPERVISOR = r'''
import json, os, pathlib, subprocess, sys
from sundai_controller import process_budget
from sundai_hotspot import gate0_operator
spec = json.loads(sys.argv[1])
here = pathlib.Path(spec["dir"])
gate0_operator.CPU_FILE = here / "cpu-used.json"
failed = []


def meter():
    if spec["meter_failure"] and (here / "solver.pid").exists():
        if spec["meter_failure"] == "persistent" or not failed:
            failed.append(1)
            raise OSError(5, "synthetic cpu.stat read failure")
    return process_budget.tree_snapshot()[0]


out = here / "run"
out.mkdir()
call = {"id": "synthetic", "accounting": {"reserved_cpu_s": spec["envelope"]}}
argv = [sys.executable, "-c", spec["parent"], str(here), spec["solver"], spec["mode"]]
if spec["mode"] == "preexisting":
    other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        gate0_operator.run_call(call, argv, out, {"cap": 600.0, "carried": 0.0}, meter=meter, cwd=str(here))
        result = {"refused": None}
    except RuntimeError as exc:
        result = {"refused": str(exc)}
    result.update(other_alive=other.poll() is None, launched=(here / "run.stdout").exists())
    other.kill()
    other.wait()
else:
    budget = {"cap": spec["cap"], "carried": spec["carried"] - meter()}
    result = gate0_operator.run_call(call, argv, out, budget, meter=meter, cwd=str(here), poll_s=0.02, stop_s=2.0)
    try:
        os.waitpid(-1, os.WNOHANG)
        result["children_left"] = True
    except ChildProcessError:
        result["children_left"] = False
    result["descendants_left"] = sorted(process_budget.tree_snapshot()[1])
    try:
        result["next_run"] = gate0_operator.carried_cpu_s()
    except SystemExit as exc:
        result["next_run"] = f"refused: {exc}"
(here / "result.json").write_text(json.dumps(result))
'''


@unittest.skipUnless(sys.platform.startswith("linux"), "the operator supervisor is Linux: a child subreaper, /proc "
                     "and cgroup v2")
class CapPathTests(unittest.TestCase):
    def supervise(self, mode: str, *, cap: float = 600.0, carried: float = 0.0, envelope: float = 58.5,
                  meter_failure: str | None = None) -> tuple:
        """One run_call in a fresh supervisor process: (its result, the run's directory, the solver's pid, session and
        group, when a solver started)."""
        temporary = tempfile.TemporaryDirectory(prefix="gate0-operator-")
        self.addCleanup(temporary.cleanup)
        here = Path(temporary.name)
        self.addCleanup(self.kill_leftover_solver, here)
        spec = {"dir": str(here), "mode": mode, "cap": cap, "carried": carried, "envelope": envelope,
                "meter_failure": meter_failure, "parent": PARENT, "solver": SOLVER}
        done = subprocess.run([sys.executable, "-c", SUPERVISOR, json.dumps(spec)], cwd=REPO, timeout=60,
                              capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr[-2000:])
        result = json.loads((here / "result.json").read_text(encoding="utf-8"))
        marker = here / "solver.pid"
        solver = dict(zip(("pid", "session", "group"), map(int, marker.read_text().split()))) if marker.exists() else {}
        return result, here, solver

    @staticmethod
    def kill_leftover_solver(here: Path) -> None:
        """Bounds a failing run: a solver stand-in that outlived its supervisor is killed here. It is identified by its
        pid file and by its command line, which names this run's directory."""
        marker = here / "solver.pid"
        if not marker.exists():
            return
        pid = int(marker.read_text().split()[0])
        try:
            if str(here) in Path(f"/proc/{pid}/cmdline").read_bytes().decode(errors="replace"):
                os.kill(pid, signal.SIGKILL)
        except (FileNotFoundError, ProcessLookupError):
            pass

    def assert_nothing_owned_is_left(self, result: dict, solver: dict) -> None:
        self.assertEqual((solver["session"], solver["group"]), (solver["pid"], solver["pid"]))  # its own session
        self.assertEqual(result["survivors"], [])
        self.assertIn(solver["pid"], result["reaped"])  # adopted by the supervisor, killed and reaped there
        self.assertEqual((result["descendants_left"], result["children_left"]), ([], False))  # the reap completed
        self.assertFalse(Path(f"/proc/{solver['pid']}").exists())  # no process and no zombie

    @staticmethod
    def solver_cpu(here: Path) -> float:
        """The CPU the stand-in solver last recorded (0 if it was killed before its first record)."""
        record = here / "solver.cpu"
        return float(record.read_text()) if record.exists() else 0.0

    def test_the_cap_kills_and_reaps_every_group_the_call_owns_and_charges_the_call(self):
        """root (#57395): the cap fires while the solver runs in its own session, ignoring SIGTERM."""
        result, here, solver = self.supervise("waits", cap=0.6, carried=0.2, envelope=0.25)
        self.assertRegex(result["killed"] or "", r"^cumulative CPU \d+\.\d\d s passed the cap 0\.6 s$")
        self.assertEqual(result["exit"], -signal.SIGKILL)  # validate-reference's stand-in, killed at the cap
        self.assert_nothing_owned_is_left(result, solver)
        # The accounting: the CPU read after the reap, the solver's included, is charged, settled and saved.
        burned = float((here / "solver.cpu").read_text())
        self.assertGreater(burned, 0.0)
        self.assertGreaterEqual(result["cpu_s_this_call"], burned - 0.05)  # /proc counts whole clock ticks
        self.assertGreater(result["cumulative_cpu_s"], 0.6)
        self.assertEqual((result["meter_errors"], result["usage"]), ([], "measured"))
        self.assertEqual(result["settlement"], {"status": "supervisor_cap", "usage": "measured",
                                                "charged_cpu_s": round(max(0.25, result["cpu_s_this_call"]), 3)})
        self.assertGreater(result["settlement"]["charged_cpu_s"], 0.25)  # the measured CPU, above the envelope
        saved = json.loads((here / "cpu-used.json").read_text(encoding="utf-8"))["used_cpu_s"]
        self.assertAlmostEqual(saved, result["cumulative_cpu_s"], delta=0.001)
        self.assertAlmostEqual(result["next_run"], result["cumulative_cpu_s"], delta=0.001)  # carried into the next run

    def test_a_validate_reference_that_dies_leaves_nothing_running_and_is_charged_its_envelope(self):
        """Contract item 6: validate-reference dies without settling (exit 9 here; SIGKILL or OOM alike) while its
        solver runs in its own session. The supervisor kills and reaps the solver too."""
        result, here, solver = self.supervise("dies")
        self.assertIsNone(result["killed"])
        self.assertEqual(result["exit"], 9)
        self.assert_nothing_owned_is_left(result, solver)
        self.assertEqual(result["meter_errors"], [])
        self.assertEqual(result["settlement"], {"status": "supervisor_unknown", "charged_cpu_s": 58.5,
                                                "usage": "measured"})

    def test_a_meter_read_that_fails_while_the_call_runs_stops_it_at_once_and_settles_it_as_failed(self):
        """root (#57472): one read of the meter fails after launch, while the solver runs; later reads would succeed.
        The error is kept, every group the call owns is killed and reaped at once on the cap's path, and the call is
        settled as failed, charged its envelope or the measured CPU if larger. Without the stop, nothing would end the
        call before the solver's own 5 CPU-s limit: the cap here is 600 CPU-s."""
        result, here, solver = self.supervise("waits", envelope=0.25, meter_failure="transient")
        error = {"where": "while the call ran", "type": "OSError",
                 "message": "[Errno 5] synthetic cpu.stat read failure"}
        self.assertEqual(result["meter_errors"], [error])
        self.assertEqual(result["killed"], "the CPU meter failed while the call ran (OSError: [Errno 5] synthetic "
                                           "cpu.stat read failure)")
        self.assertEqual(result["exit"], -signal.SIGKILL)  # killed, not finished
        self.assert_nothing_owned_is_left(result, solver)
        self.assertLess(self.solver_cpu(here), 1.0)  # stopped at once, far from its own 5 CPU-s limit
        self.assertLess(result["cpu_s_this_call"], 2.0)
        self.assertEqual(result["usage"], "measured")  # the read after the reap succeeded
        self.assertEqual(result["settlement"], {"status": "supervisor_meter_failed", "usage": "measured",
                                                "charged_cpu_s": round(max(0.25, result["cpu_s_this_call"]), 3),
                                                "meter_errors": [error]})
        self.assertAlmostEqual(result["next_run"], result["cumulative_cpu_s"], delta=0.001)

    def test_a_meter_that_stays_broken_leaves_usage_unknown_and_the_reservation_consumed(self):
        """root (#57472): from just after launch every read fails, including the read after the reap. The call is
        still stopped and reaped. Its usage is unknown, so it is charged its full envelope: the reservation stays
        consumed, never zero, never refunded. The cumulative total is recorded as unknown, not as a number, and the
        next run refuses until the operator reconciles it, so nothing retries on its own."""
        result, here, solver = self.supervise("waits", envelope=58.5, meter_failure="persistent")
        self.assertEqual([(error["where"], error["type"]) for error in result["meter_errors"]],
                         [("while the call ran", "OSError"), ("after the reap", "OSError")])
        self.assertRegex(result["killed"] or "", "^the CPU meter failed while the call ran")
        self.assert_nothing_owned_is_left(result, solver)
        self.assertLess(self.solver_cpu(here), 1.0)  # stopped at once
        self.assertEqual((result["usage"], result["cpu_s_this_call"], result["cumulative_cpu_s"]),
                         ("unknown", None, None))
        self.assertEqual(result["settlement"], {"status": "supervisor_meter_failed", "usage": "unknown",
                                                "charged_cpu_s": 58.5, "meter_errors": result["meter_errors"]})
        saved = json.loads((here / "cpu-used.json").read_text(encoding="utf-8"))
        self.assertEqual((saved["used_cpu_s"], saved["usage"]), (None, "unknown"))
        self.assertGreaterEqual(saved["lower_bound_cpu_s"], 0.0)
        self.assertRegex(str(result["next_run"]), "^refused: the cumulative CPU used is unknown")

    def test_a_supervisor_that_already_has_a_child_refuses_and_leaves_it_alone(self):
        """A call's cleanup never reaches other work: with a child already running, run_call refuses before it
        launches anything, and that child is not killed."""
        result, here, solver = self.supervise("preexisting")
        self.assertRegex(result["refused"] or "", "already has child processes")
        self.assertEqual((result["other_alive"], result["launched"], solver), (True, False, {}))


if __name__ == "__main__":
    unittest.main()
