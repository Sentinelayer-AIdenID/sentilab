"""Lifecycle identity regressions; fake processes only, no thermal solves."""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import signal
import tempfile
import unittest
from unittest.mock import patch

from sundai_controller import headroom_supervisor as s

EVIDENCE = Path(__file__).resolve().parents[1] / 'docs/sentilab/evidence/SLAB-039'


class IdentityTests(unittest.TestCase):
    def test_reaped_leader_group_is_retired_while_owned_orphan_is_drained(self):
        tree = s.LinuxTree(s.Policy())
        tree.pid = 1234
        # Leader exits, but an adopted orphan in another session remains alive.
        with patch.object(s.os, 'waitpid', side_effect=[(1234, 0), (0, 0)]):
            self.assertFalse(tree.done())
        self.assertEqual(tree.returncode, 0)
        self.assertEqual(tree.scope.reaped_pids, [1234])
        owned = {'start': 42}
        stale = {'start': 51}
        with patch.object(s, 'tree_snapshot', return_value=(0, {2345: owned, 3456: stale})), \
                patch.object(s, '_stat', side_effect=lambda pid: owned if pid == 2345 else {'start': 52}), \
                patch.object(s.os, 'killpg') as group_kill, patch.object(s.os, 'kill') as kill:
            tree.kill()
        # The numeric PGID may now name an unrelated replacement group.
        group_kill.assert_not_called()
        kill.assert_called_once_with(2345, signal.SIGKILL)

    def test_live_leader_group_and_identity_checked_descendant_are_killed(self):
        tree = s.LinuxTree(s.Policy())
        tree.pid = 1234
        for current in ({'start': 42}, {'start': 43}, None):
            with self.subTest(current=current), \
                    patch.object(s, 'tree_snapshot', return_value=(0, {2345: {'start': 42}})), \
                    patch.object(s, '_stat', return_value=current), \
                    patch.object(s.os, 'killpg') as group_kill, patch.object(s.os, 'kill') as kill:
                tree.kill()
                group_kill.assert_called_once_with(1234, signal.SIGKILL)
                if current == {'start': 42}:
                    kill.assert_called_once_with(2345, signal.SIGKILL)
                else:
                    kill.assert_not_called()

    def test_policy_replacement_keeps_admitted_bytes_in_reservation_and_settlement(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            budget = root / 'SPEND.json'
            budget.write_bytes((EVIDENCE / 'SPEND.json').read_bytes())
            policy_path = root / 'POLICY.json'
            policy_a = {'limits': asdict(s.Policy(measured_observation_plus_kill_seconds=.6)), 'status': 'approved',
                        'approved_by': 'synthetic-test-only',
                        'latency_measurement_evidence': 'synthetic-test-only',
                        'accept_unbounded_scheduler_and_cleanup_risk': True}
            admitted = (json.dumps(policy_a, indent=2) + '\n').encode()
            policy_path.write_bytes(admitted)
            admitted_hash = hashlib.sha256(admitted).hexdigest()
            reservations = []

            def replacement(*args, **kwargs):
                reservations.append(json.loads(budget.read_text())['outer_active'])
                policy_b = dict(policy_a, approved_by='replacement-policy')
                policy_path.write_text(json.dumps(policy_b))
                return {'status': 'completed', 'returncode': 0, 'metered_cpu_seconds': .1,
                        'reaping_confirmed': True, 'latency_assumptions_met': True}

            reads = []
            read_bytes = Path.read_bytes
            def counted_read(path):
                if path == policy_path:
                    reads.append(path)
                return read_bytes(path)
            with patch.object(s, 'supervise', side_effect=replacement), \
                    patch.object(s, 'verify_cpu_max', return_value={'rate_q': 1}), \
                    patch.object(Path, 'read_bytes', counted_read), \
                    patch.object(s.LinuxTree, 'cpu', return_value=.1):
                receipt = s.run(EVIDENCE / 'PREREG-v4.json', budget, root / 'out', policy_path)
            state = json.loads(budget.read_text())
            self.assertTrue(receipt['result_accepted'])
            self.assertEqual(reads, [policy_path])
            self.assertEqual(receipt['policy_sha256'], admitted_hash)
            self.assertEqual(reservations[0]['policy_sha256'], admitted_hash)
            self.assertEqual(reservations[0]['policy'], policy_a)
            self.assertEqual(state['lifetime_settlements'][-1]['policy_sha256'], admitted_hash)
            self.assertNotEqual(hashlib.sha256(policy_path.read_bytes()).hexdigest(), admitted_hash)


if __name__ == '__main__':
    unittest.main()
