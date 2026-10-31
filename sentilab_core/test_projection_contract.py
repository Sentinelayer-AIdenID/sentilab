"""Reviewed evidence vectors exercised by the Python-only container gate."""
import json
from pathlib import Path
import unittest

from sentilab_core.projection import board, project

VECTORS = Path(__file__).resolve().parents[1] / 'contracts/contract-0.2/vectors-evidence.json'


def evidence_vectors():
    for vector in json.loads(VECTORS.read_text())["vectors"]:
        events = [{"event_id": f"e{i}", "seq": i + 1, **event}
                  for i, event in enumerate(vector["events"])]
        yield vector, events


class ProjectionContractTests(unittest.TestCase):
    def test_board_ignores_rejected_acceptance_events(self):
        events = [
            {"type": "node.create", "body": {"id": "source", "kind": "source"}},
            {"type": "node.create", "body": {"id": "candidate", "kind": "candidate"}},
            {"type": "support.add", "body": {"node": "candidate", "set_id": "primary", "members": ["source"]}},
        ]
        for state in ("validated", "simulation_pending", "evaluated", "reproduction_pending", "reproduced", "accepted"):
            events.append({"type": "lifecycle.transition", "actor_role": "acceptance_gate",
                           "body": {"node": "candidate", "to": state,
                                    "record": {"inputs": {"reproduction": {"j": 10}}}}})
        prefix = [{"seq": i + 1, "event": {"seq": i + 1, "event_id": f"e{i}", **event}}
                  for i, event in enumerate(events)]
        self.assertEqual(board(prefix), {"candidate_id": "candidate", "j": 10, "seq": 9})
        prefix.append({"seq": 10, "event": {"seq": 10, "event_id": "rejected", "type": "lifecycle.transition",
                       "actor_role": "acceptance_gate", "body": {"node": "candidate", "to": "accepted",
                       "record": {"inputs": {"reproduction": {"j": 1}}}}}})
        self.assertEqual(board(prefix), {"candidate_id": "candidate", "j": 10, "seq": 9})

    def test_reviewed_evidence_vectors_and_delivery_order(self):
        for vector, events in evidence_vectors():
            with self.subTest(vector=vector["name"]):
                actual = project([{"event": event} for event in events])
                expect = vector["expect"]
                self.assertEqual(actual["rejected"], expect.get("rejected", []))
                for node_id, fields in expect.get("nodes", {}).items():
                    for key, value in fields.items():
                        self.assertEqual(actual["nodes"][node_id][key], value, (node_id, key))
                for node_id in expect.get("absent_nodes", []):
                    self.assertNotIn(node_id, actual["nodes"])
                self.assertEqual(project([{"event": event} for event in reversed(events)]), actual)


if __name__ == '__main__':
    unittest.main()
