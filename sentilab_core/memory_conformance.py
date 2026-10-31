"""Required Node parity, loaded by live-conformance CI, never Docker discovery."""
import json
from pathlib import Path
import subprocess
import unittest

from sentilab_core.envelope import canonical
from sentilab_core.projection import project
from sentilab_core import test_memory
from sentilab_core.test_projection_contract import evidence_vectors


class MemoryProjectionConformance(unittest.TestCase):
    setUp = test_memory.MemoryTests.setUp
    run_record = test_memory.MemoryTests.run_record
    open_store = test_memory.MemoryTests.open_store
    write_fixture = test_memory.MemoryTests.write_fixture
    withdraw = test_memory.MemoryTests.withdraw

    def test_correction_projection_matches_reviewed_contract_without_solves(self):
        self.write_fixture()
        for withdrawn in (False, True):
            if withdrawn:
                self.withdraw()
            prefix = self.ledger.read()["prefix"]
            process = subprocess.run(["node", str(Path(__file__).with_name("projection.mjs"))],
                                     input=canonical([row["event"] for row in prefix]),
                                     capture_output=True, check=True, timeout=30)
            self.assertEqual(json.loads(process.stdout), project(prefix))

    def test_every_reviewed_vector_prefix_matches_exact_javascript(self):
        cases = []
        for vector, events in evidence_vectors():
            for end in range(len(events) + 1):
                cases.append((vector["name"], end, events[:end]))
        script = """import { project } from './contracts/contract-0.2/evidence-projection.mjs';
let s=''; for await (const c of process.stdin) s+=c;
console.log(JSON.stringify(JSON.parse(s).map(project)));"""
        result = subprocess.run(["node", "--input-type=module", "-e", script],
                                cwd=Path(__file__).resolve().parents[1],
                                input=canonical([events for _, _, events in cases]),
                                capture_output=True, check=True, timeout=30)
        reference = json.loads(result.stdout)
        self.assertEqual(len(reference), len(cases))
        for (name, end, events), expected in zip(cases, reference):
            with self.subTest(vector=name, prefix=end):
                self.assertEqual(project([{"event": event} for event in events]), expected)

    def test_signed_attack_probes_match_exact_contract(self):
        probes = [("node.create", {"id": "bad", "kind": "measurement"}, "missing_semantics"),
                  ("support.add", {"node": "claim-a", "set_id": "primary", "members": []},
                   "empty_support_set"),
                  ("support.add", {"node": "claim-a", "set_id": "primary", "members": ["measurement-b"]},
                   "duplicate_set")]
        for kind, body, code in probes:
            self.ledger.append(kind, body, event_id=code)
        self.withdraw()
        state = self.ledger.read()
        self.assertIsNone(state["error"])
        process = subprocess.run(["node", str(Path(__file__).with_name("projection.mjs"))],
                                 input=canonical([row["event"] for row in state["prefix"]]),
                                 capture_output=True, check=True, timeout=30)
        reference = json.loads(process.stdout)
        self.assertEqual(reference["rejected"], [{"event_id": code, "code": code} for _, _, code in probes])
        self.assertEqual(reference["nodes"]["claim-a"]["validity"], "stale")
        self.assertEqual(project(state["prefix"]), reference)


if __name__ == '__main__':
    unittest.main()
