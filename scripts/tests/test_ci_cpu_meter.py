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
    def fake_run(self, directory, *, reason='cancelled', wait_timeout=False, kill=None):
        """Drive run() with a helper paused before its entry code can execute."""
        import json
        import signal
        import subprocess
        from dataclasses import asdict
        from unittest.mock import patch

        from scripts.ci_allocation import EXPIRY
        from scripts.ci_cpu_meter import run
        from scripts.tests.test_ci_allocation import IDENTITY

        group = directory / 'ci-allocation-123'
        (group / 'host').mkdir(parents=True)
        (group / 'cpu.stat').write_text('usage_usec 1250000\n')
        (group / 'cgroup.events').write_text('populated 0\n')
        admission = {'identity': asdict(IDENTITY), 'state': 'admitted', 'allocation_id': '56314',
                     'slot': 3, 'launch_reservation': 100, 'cpu_reservation_seconds': 900}
        ledger_dir = directory / 'ledger'
        ledger_dir.mkdir()
        (ledger_dir / 'admission.json').write_text(json.dumps(admission))
        expired = [False]

        class DelayedHelper:
            pid = 4321
            alive = True
            workload_started = False
            reaped = False

            polls = 0

            def poll(self):
                self.polls += 1
                if self.polls > 10:
                    raise RuntimeError("fake helper poll bound exceeded")
                return None if self.alive else -9

            def kill(self):
                self.alive = False

            def wait(self, timeout):
                # In the old protocol, joining and exec happen after the empty
                # drain. Finite fake avoids leaving any real workload behind.
                if self.alive:
                    (group / 'cgroup.events').write_text('populated 1\n')
                    self.workload_started = True
                if wait_timeout:
                    raise subprocess.TimeoutExpired('delayed helper', timeout)
                self.reaped = True
                return -9 if not self.alive else 0

        process = DelayedHelper()

        def spawn(*args, **kwargs):
            if reason == 'cancelled':
                signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)
            else:
                expired[0] = True
            return process

        with patch('scripts.ci_cpu_meter.create_group', return_value=group), \
             patch('scripts.ci_cpu_meter.subprocess.Popen', side_effect=spawn), \
             patch('scripts.ci_cpu_meter.time.time', side_effect=lambda: EXPIRY if expired[0] else EXPIRY - 1), \
             patch('scripts.ci_cpu_meter.monitor', side_effect=lambda *args, **kwargs: monitor(
                 *args, **kwargs, wall_clock=lambda: EXPIRY if expired[0] else EXPIRY - 1)):
            if kill is None:
                code = run(ledger_dir, admission, ['fake-workload'])
            else:
                with patch('scripts.ci_cpu_meter.kill_group', side_effect=lambda g: kill(g)):
                    code = run(ledger_dir, admission, ['fake-workload'])
        return code, json.loads((ledger_dir / 'settlement.json').read_text()), process, group

    def test_early_stop_or_expiry_cannot_repopulate_after_drain(self):
        from scripts.ci_cpu_meter import populated
        for reason in ('cancelled', 'expired'):
            with self.subTest(reason=reason), tempfile.TemporaryDirectory() as temporary:
                code, result, process, group = self.fake_run(Path(temporary), reason=reason)
                self.assertNotEqual(code, 0)
                self.assertFalse(process.workload_started, 'helper started workload after cgroup drain')
                self.assertFalse(process.alive)
                self.assertTrue(process.reaped)
                self.assertEqual(result['state'], reason)
                self.assertEqual(result['cpu']['final_populated'], populated(group))
                self.assertTrue(result['cpu']['cleanup_complete'])

    def test_wait_timeout_kills_helper_and_keeps_cleanup_reconcilable(self):
        import json

        from scripts.ci_cpu_meter import recover
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            code, result, process, group = self.fake_run(directory, wait_timeout=True)
            self.assertFalse(process.alive, 'full charge must not leave helper running')
            self.assertFalse(process.workload_started)
            self.assertEqual(code, 1)
            self.assertEqual(result['state'], 'inconclusive')
            self.assertFalse(result['cpu']['cleanup_complete'])
            self.assertGreaterEqual(result['cpu']['charged_cpu_seconds'], 900)
            # Recovery must retry even though a terminal ledger already exists.
            (group / 'cgroup.kill').unlink()
            recover(directory / 'ledger', root=directory)
            self.assertEqual((group / 'cgroup.kill').read_text(), '1')
            after = json.loads((directory / 'ledger/settlement.json').read_text())
            self.assertTrue(any(row['event'] == 'cleanup' for row in after['events']))

    def test_final_population_is_observed_and_recovery_retries_terminal_ledger(self):
        import json
        from unittest.mock import patch

        from scripts.ci_cpu_meter import recover
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)

            def repopulate(group):
                (group / 'cgroup.events').write_text('populated 1\n')

            code, result, _, group = self.fake_run(directory, kill=repopulate)
            self.assertEqual(code, 1)
            self.assertEqual(result['state'], 'inconclusive')
            self.assertTrue(result['cpu']['final_populated'])
            self.assertFalse(result['cpu']['cleanup_complete'])
            write = Path.write_text

            def drain(path, *args, **kwargs):
                result = write(path, *args, **kwargs)
                if path.name == 'cgroup.kill':
                    write(group / 'cgroup.events', 'populated 0\n')
                return result

            with patch.object(Path, 'write_text', drain):
                recover(directory / 'ledger', root=directory)
            after = json.loads((directory / 'ledger/settlement.json').read_text())
            cleanup = [row for row in after['events'] if row['event'] == 'cleanup'][-1]
            self.assertFalse(cleanup['final_populated'])
            self.assertTrue(cleanup['cleanup_complete'])

    def test_late_empty_drain_preserves_cpu_sample_but_invalidates_timing(self):
        with tempfile.TemporaryDirectory() as temporary:
            def late_drain(group):
                (group / 'cpu.stat').write_text('usage_usec 2500000\n')
                ticks = iter((0, 6))
                kill_group(group, clock=lambda: next(ticks), sleep=lambda _: None)

            code, result, _, _ = self.fake_run(Path(temporary), kill=late_drain)
            self.assertEqual(code, 1)
            self.assertEqual(result['state'], 'inconclusive')
            self.assertEqual(result['cpu']['cgroup_cpu_seconds'], 1.25)
            self.assertFalse(result['cpu']['final_populated'])
            self.assertFalse(result['cpu']['kill_within_reserve'])
            self.assertGreaterEqual(result['cpu']['charged_cpu_seconds'], 900)

    def test_joint_cpu_and_launch_violations_survive_finalization_and_reconciliation(self):
        from unittest.mock import patch

        from scripts.ci_allocation import Ledger
        from scripts.ci_reconcile import reconcile
        from scripts.tests.test_ci_allocation import IDENTITY

        for seconds in (901, 910):
            with self.subTest(seconds=seconds), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)

                def joint_failure(group, seconds=seconds, directory=directory):
                    (group / 'cpu.stat').write_text(f'usage_usec {int((seconds + 1.25) * 1000000)}\n')
                    Ledger(directory / 'ledger/events.jsonl', IDENTITY).violation()

                with patch('scripts.ci_cpu_meter.supervisor_cpu', return_value=0):
                    code, result, _, _ = self.fake_run(directory, kill=joint_failure)
                self.assertEqual(code, 1)
                self.assertEqual(result['state'], 'cpu_limit_violated')
                self.assertEqual(result['violations'], ['cpu_limit_violated', 'launch_violation'])
                self.assertEqual(result['cpu']['cpu_seconds'], seconds)
                self.assertEqual(result['cpu']['charged_cpu_seconds'], seconds)
                terminal = reconcile(result['identity'], 'failure', result)
                self.assertEqual(terminal['settlement'], result)

    def test_helper_startup_debit_is_gated_before_release_and_kept_in_settlement(self):
        import json
        import sys
        from dataclasses import asdict
        from unittest.mock import patch

        from scripts.ci_cpu_meter import run
        from scripts.tests.test_ci_allocation import IDENTITY

        for startup in (.25, 870, OSError('startup counter unavailable')):
            with self.subTest(startup=startup), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                group = directory / 'group'
                (group / 'host').mkdir(parents=True)
                (group / 'cpu.stat').write_text('usage_usec 0\n')
                (group / 'cgroup.events').write_text('populated 0\n')
                marker = directory / 'released'
                admission = {'identity': asdict(IDENTITY), 'state': 'admitted', 'allocation_id': '56314',
                             'slot': 3, 'launch_reservation': 100, 'cpu_reservation_seconds': 900}
                with patch('scripts.ci_cpu_meter.create_group', return_value=group), \
                     patch('scripts.ci_cpu_meter.time.time', return_value=1793448000), \
                     patch('scripts.ci_cpu_meter.supervisor_cpu', return_value=0), \
                     patch('scripts.ci_cpu_meter.helper_startup_cpu', create=True,
                           side_effect=[startup]), \
                     patch('scripts.ci_cpu_meter.children_cpu', create=True, return_value=0):
                    code = run(directory / 'ledger', admission, [sys.executable, '-c',
                               'import pathlib,sys; pathlib.Path(sys.argv[1]).touch()', str(marker)])
                result = json.loads((directory / 'ledger/settlement.json').read_text())
                self.assertEqual(marker.exists(), startup == .25)
                if isinstance(startup, OSError):
                    self.assertEqual(code, 1)
                    self.assertEqual(result['state'], 'inconclusive')
                    self.assertEqual(result['cpu']['charged_cpu_seconds'], 900)
                else:
                    self.assertEqual(code, 0 if startup == .25 else 1)
                    self.assertEqual(result['cpu']['cpu_seconds'], startup)
                    self.assertEqual(result['cpu']['charged_cpu_seconds'], startup)
                    self.assertEqual(result['cpu']['helper_startup_cpu_seconds'], startup)
                    self.assertEqual(result['state'], 'success' if startup == .25 else 'cpu_exhausted')

    def test_cancelled_unreleased_helper_cpu_is_charged_after_reaping(self):
        from unittest.mock import patch

        for reason in ('cancelled', 'expired'):
            with self.subTest(reason=reason), tempfile.TemporaryDirectory() as temporary:
                with patch('scripts.ci_cpu_meter.children_cpu', create=True, side_effect=(10, 12.5)), \
                     patch('scripts.ci_cpu_meter.supervisor_cpu', return_value=0):
                    _, result, _, _ = self.fake_run(Path(temporary), reason=reason)
                self.assertEqual(result['state'], reason)
                self.assertEqual(result['cpu']['cpu_seconds'], 2.5)
                self.assertEqual(result['cpu']['helper_startup_cpu_seconds'], 2.5)
                self.assertEqual(result['cpu']['charged_cpu_seconds'], 2.5)

    def test_helper_startup_counter_rounding_covers_both_clock_ticks(self):
        from unittest.mock import patch

        from scripts.ci_cpu_meter import helper_startup_cpu

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / '123').mkdir()
            stat = root / '123/stat'
            stat.write_text('123 (a name) with spaces) ' + ' '.join(['0'] * 11 + ['2', '3']))
            with patch('scripts.ci_cpu_meter.os.sysconf', return_value=100):
                self.assertEqual(helper_startup_cpu(123, root), .07)
                stat.write_text('123 (python) ' + ' '.join(['0'] * 11 + ['-1', '3']))
                with self.assertRaisesRegex(RuntimeError, 'helper CPU'):
                    helper_startup_cpu(123, root)

    def test_workload_waits_for_parent_attachment_and_attach_failure_cancels_it(self):
        import json
        import sys
        import time
        from dataclasses import asdict
        from unittest.mock import patch

        from scripts.ci_cpu_meter import run
        from scripts.tests.test_ci_allocation import IDENTITY

        for attach_fails in (False, True):
            with self.subTest(attach_fails=attach_fails), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                group = directory / 'group'
                (group / 'host').mkdir(parents=True)
                (group / 'cpu.stat').write_text('usage_usec 0\n')
                (group / 'cgroup.events').write_text('populated 0\n')
                marker = directory / 'workload-started'
                attached = []
                write = Path.write_text

                def attach(path, *args, marker=marker, attached=attached,
                           fails=attach_fails, write=write, **kwargs):
                    if path.name == 'cgroup.procs':
                        time.sleep(.1)  # allow the actual nonthermal helper to reach its gate
                        self.assertFalse(marker.exists(), 'workload ran before parent attachment')
                        attached.append(True)
                        if fails:
                            raise OSError('fake attach failure')
                    return write(path, *args, **kwargs)

                admission = {'identity': asdict(IDENTITY), 'state': 'admitted', 'allocation_id': '56314',
                             'slot': 3, 'launch_reservation': 100, 'cpu_reservation_seconds': 900}
                with patch('scripts.ci_cpu_meter.create_group', return_value=group), \
                     patch('scripts.ci_cpu_meter.time.time', return_value=1793448000), \
                     patch.object(Path, 'write_text', attach):
                    code = run(directory / 'ledger', admission, [sys.executable, '-c',
                               'import pathlib,sys; pathlib.Path(sys.argv[1]).touch()', str(marker)])
                self.assertEqual(attached, [True])
                self.assertEqual(marker.exists(), not attach_fails)
                self.assertEqual(code, 1 if attach_fails else 0)
                result = json.loads((directory / 'ledger/settlement.json').read_text())
                self.assertTrue(result['cpu']['helper_reaped'])

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

    def test_kill_deadline_includes_write_and_empty_observation(self):
        from unittest.mock import patch

        for slow_operation in ('write', 'empty_read'):
            with self.subTest(slow_operation=slow_operation), tempfile.TemporaryDirectory() as temporary:
                group = Path(temporary)
                (group / 'cgroup.events').write_text('populated 0\n')
                elapsed = [0]
                write = Path.write_text
                read = Path.read_text

                def slow_write(path, *args, operation=slow_operation, elapsed=elapsed, write=write, **kwargs):
                    if path.name == 'cgroup.kill' and operation == 'write':
                        elapsed[0] += 6
                    return write(path, *args, **kwargs)

                def slow_read(path, *args, operation=slow_operation, elapsed=elapsed, read=read, **kwargs):
                    if path.name == 'cgroup.events' and operation == 'empty_read':
                        elapsed[0] += 6
                    return read(path, *args, **kwargs)

                with patch.object(Path, 'write_text', slow_write), patch.object(Path, 'read_text', slow_read), \
                     self.assertRaisesRegex(RuntimeError, 'drain'):
                    kill_group(group, clock=lambda elapsed=elapsed: elapsed[0], sleep=lambda _: None)

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
