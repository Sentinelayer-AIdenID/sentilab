"""Exercise the shipped monitor/drain logic with fake cgroup files and clocks."""
import tempfile
import unittest
from pathlib import Path

from scripts.ci_allocation import CPUAccount, read_cpu
from scripts.ci_cpu_meter import kill_group, monitor


class Process:
    def __init__(self, codes):
        self.codes = iter(codes)
    def poll(self):
        return next(self.codes)


class MeterTests(unittest.TestCase):
    def test_monitor_observes_inflight_cpu_and_stops_before_cap(self):
        usage = iter((0, 400, 870))
        clock = iter((0, .05, .1))
        result = monitor(None, Process([None, None]), CPUAccount(0, 0, 0),
                         cancelled=lambda: False, wall_clock=lambda: 1793448000, cpu=lambda _: next(usage),
                         own_cpu=lambda: 0, clock=lambda: next(clock), sleep=lambda _: None)
        self.assertEqual(result, ('cpu_exhausted', 1))

    def test_monitor_terminal_states_and_cancellation(self):
        for code, state in ((0, 'success'), (7, 'failure')):
            result = monitor(None, Process([code]), CPUAccount(0, 0, 0),
                             cancelled=lambda: False, wall_clock=lambda: 1793448000, cpu=lambda _: 12.5,
                             own_cpu=lambda: .5, clock=lambda: 1)
            self.assertEqual(result, (state, code))
        self.assertEqual(monitor(None, Process([]), CPUAccount(0, 0, 0),
                                 cancelled=lambda: True), ('cancelled', 130))

    def test_cpu_stat_is_cpu_and_missing_counter_is_not_wall_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            group = Path(directory)
            (group / 'cpu.stat').write_text('usage_usec 1250000\nuser_usec 1000000\n')
            self.assertEqual(read_cpu(group), 1.25)
            (group / 'cpu.stat').write_text('user_usec 1000000\n')
            with self.assertRaises(KeyError):
                read_cpu(group)

    def test_kill_waits_for_descendants_and_bounds_kill_overhead(self):
        with tempfile.TemporaryDirectory() as directory:
            group = Path(directory)
            (group / 'cgroup.events').write_text('populated 1\n')
            clock = iter((0, 1, 6))
            with self.assertRaisesRegex(RuntimeError, 'drain'):
                kill_group(group, clock=lambda: next(clock), sleep=lambda _: None)
            self.assertEqual((group / 'cgroup.kill').read_text(), '1')
            (group / 'cgroup.events').write_text('populated 1\n')
            def drained(_):
                (group / 'cgroup.events').write_text('populated 0\n')
            kill_group(group, clock=lambda: 0, sleep=drained)

    def test_full_runner_enters_group_and_exports_success_and_failure(self):
        # Fake kernel files replace the unavailable writable cgroup mount; process
        # launch, enter helper, broker, monitoring, drain and export are shipped code.
        import json
        import sys
        from dataclasses import asdict
        from unittest.mock import patch

        from scripts.ci_cpu_meter import run
        from scripts.tests.test_ci_allocation import IDENTITY
        for exitcode in (0, 7):
            with self.subTest(exitcode=exitcode), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                group = directory / 'group'
                (group / 'host').mkdir(parents=True)
                (group / 'cpu.stat').write_text('usage_usec 0\n')
                (group / 'cgroup.events').write_text('populated 0\n')
                admission = {'identity': asdict(IDENTITY), 'state': 'admitted',
                             'allocation_id': '56314', 'slot': 3,
                             'launch_reservation': 100, 'cpu_reservation_seconds': 900}
                command = [sys.executable, '-c',
                           ('import pathlib,sys; pathlib.Path(sys.argv[1]).write_text("usage_usec 1250000\\n"); '
                            'sys.exit(int(sys.argv[2]))'), str(group / 'cpu.stat'), str(exitcode)]
                with patch('scripts.ci_cpu_meter.create_group', return_value=group), \
                     patch('scripts.ci_cpu_meter.time.time', return_value=1793448000):
                    actual = run(directory / 'ledger', admission, command)
                self.assertEqual(actual, exitcode)
                result = json.loads((directory / 'ledger/settlement.json').read_text())
                self.assertEqual(result['state'], 'success' if exitcode == 0 else 'failure')
                self.assertEqual(result['cpu']['cgroup_cpu_seconds'], 1.25)
                self.assertGreaterEqual(result['cpu']['cpu_seconds'], 1.25)
                self.assertTrue((group / 'host/cgroup.procs').read_text().strip().isdecimal())
                self.assertEqual((group / 'cgroup.kill').read_text(), '1')

    def test_recovery_settles_orphans_without_fabricating_total_cpu(self):
        import json
        from dataclasses import asdict

        from scripts.ci_allocation import Ledger
        from scripts.ci_cpu_meter import recover
        from scripts.tests.test_ci_allocation import IDENTITY
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / 'admission.json').write_text(json.dumps({
                'state': 'admitted', 'identity': asdict(IDENTITY)}))
            ledger = Ledger(directory / 'events.jsonl', IDENTITY)
            ledger.reserve('fake')
            group = directory / 'ci-allocation-123'
            group.mkdir()
            (group / 'cpu.stat').write_text('usage_usec 1250000\n')
            (group / 'cgroup.events').write_text('populated 0\n')
            recover(directory, root=directory)
            result = json.loads((directory / 'settlement.json').read_text())
            self.assertEqual(result['state'], 'interrupted')
            self.assertEqual(result['launches_settled'], 1)
            self.assertIsNone(result['cpu']['cpu_seconds'])
            self.assertEqual(result['cpu']['charged_cpu_seconds'], 900)

    def test_monitor_expiry_and_bypass_violation_stop_without_starting_more_work(self):
        for wall, violation, state in ((1793556000, False, 'expired'),
                                        (1793448000, True, 'launch_violation')):
            result = monitor(None, Process([]), CPUAccount(0, 0, 0), cancelled=lambda: False,
                             violated=lambda value=violation: value, wall_clock=lambda value=wall: value)
            self.assertEqual(result, (state, 1))

    def test_bootstrap_uses_normal_meter_and_preserves_mode_in_settlement(self):
        import json
        import sys
        from unittest.mock import patch

        from scripts.ci_cpu_meter import recover, run
        from scripts.tests.test_ci_workflow import WorkflowTests

        # The receipt comes from the actual workflow bootstrap shell, not a copy.
        process, admission, _ = WorkflowTests().bootstrap()
        self.assertEqual(process.returncode, 0, process.stderr)
        for exitcode in (0, 7):
            with self.subTest(exitcode=exitcode), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                group = directory / 'group'
                (group / 'host').mkdir(parents=True)
                (group / 'cpu.stat').write_text('usage_usec 0\n')
                (group / 'cgroup.events').write_text('populated 0\n')
                ledger_dir = directory / 'ledger'
                ledger_dir.mkdir()
                (ledger_dir / 'admission.json').write_text(json.dumps(admission))
                command = [sys.executable, '-c',
                           ('import pathlib,sys; pathlib.Path(sys.argv[1]).write_text("usage_usec 1250000\\n"); '
                            'sys.exit(int(sys.argv[2]))'), str(group / 'cpu.stat'), str(exitcode)]
                with patch('scripts.ci_cpu_meter.create_group', return_value=group), \
                     patch('scripts.ci_cpu_meter.time.time', return_value=1793448000):
                    self.assertEqual(run(ledger_dir, admission, command), exitcode)
                result = json.loads((ledger_dir / 'settlement.json').read_text())
                self.assertEqual(result['state'], 'success' if exitcode == 0 else 'failure')
                self.assertEqual(result['cpu']['cgroup_cpu_seconds'], 1.25)
                self.assertEqual(result['admission'], admission)
                self.assertEqual((group / 'cgroup.kill').read_text(), '1')
                recover(ledger_dir, root=directory)
                self.assertEqual(json.loads((ledger_dir / 'settlement.json').read_text()), result)

    def test_bootstrap_orphan_recovery_preserves_mode_and_reserved_charge(self):
        import json
        from dataclasses import asdict

        from scripts.ci_allocation import Ledger
        from scripts.ci_cpu_meter import recover
        from scripts.tests.test_ci_allocation import IDENTITY

        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            admission = {'state': 'admitted', 'mode': 'bootstrap', 'identity': asdict(IDENTITY)}
            (directory / 'admission.json').write_text(json.dumps(admission))
            ledger = Ledger(directory / 'events.jsonl', IDENTITY)
            ledger.reserve('fake')
            recover(directory, root=directory)
            result = json.loads((directory / 'settlement.json').read_text())
            self.assertEqual(result['state'], 'interrupted')
            self.assertEqual(result['launches_settled'], 1)
            self.assertEqual(result['cpu']['charged_cpu_seconds'], 900)
            self.assertEqual(result['admission'], admission)
