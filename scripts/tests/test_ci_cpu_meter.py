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
