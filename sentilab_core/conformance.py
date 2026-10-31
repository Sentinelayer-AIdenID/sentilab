"""Node-assisted CI conformance. Never imported by the Python service."""
import json
from pathlib import Path
import subprocess
import unittest
from sentilab_core.envelope import canonical, digest
from sentilab_core import test_conductor

ROOT = Path(__file__).resolve().parent.parent

class CanonicalConformance(unittest.TestCase):
    def test_canonical_matches_javascript_number_and_unicode_vectors(self):
        vectors = [{"z": 5.0, "a": 1e16, "😀": "\n\t", "\ue000": -0.0},
                   [1e-7, 1e-6, 1e20, 1e21, 1.2345678901234567, 333333333.33333329,
                    1.0, -5e-324, 0.00001230, 1.7976931348623157e308],
                   {"present": None}, {}, [True, False, "é", "𝄞"]]
        # This native JSON.stringify check is additional to the versioned aneta
        # contract vectors, which are tested when the contracts input is loaded.
        script = """let s=''; for await (const x of process.stdin) s+=x;
const c=x=>Array.isArray(x)?'['+x.map(c).join(',')+']':
x!==null&&typeof x==='object'?'{'+Object.keys(x).sort().map(k=>JSON.stringify(k)+':'+c(x[k])).join(',')+'}':JSON.stringify(x);
console.log(JSON.stringify(JSON.parse(s).map(c)));"""
        proc = subprocess.run(["node", "--input-type=module", "-e", script],
                              input=json.dumps(vectors), text=True, capture_output=True, check=True)
        self.assertEqual([canonical(v).decode() for v in vectors], json.loads(proc.stdout))
        self.assertNotEqual(digest({}), digest({"present": None}))
        for value in (float("inf"), 9007199254740993, "\ud800"):
            with self.assertRaises((ValueError, UnicodeError)):
                canonical(value)


    def test_merged_vectors_match_exact_aneta_canonical(self):
        path = ROOT / "contracts/view-envelope/vectors-view.json"
        vectors = json.loads(path.read_text())
        script = "import { canonical } from './contracts/contract-0.2/resultcheck.mjs'; let s=''; for await (const c of process.stdin) s+=c; process.stdout.write(canonical(JSON.parse(s)));"
        result = subprocess.run(["node", "--input-type=module", "-e", script], cwd=ROOT,
                                input=path.read_bytes(), capture_output=True, check=True)
        self.assertEqual(canonical(vectors), result.stdout)
        for vector in vectors["canonical"]:
            self.assertEqual(canonical(json.loads(vector["raw"])).decode(), vector["canonical"])
        self.assertEqual(canonical({"2": "b", "10": "a"}), b'{"10":"a","2":"b"}')

class ProjectionConformance(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_conductor.ConductorTests.asyncSetUp
    async def test_contract_javascript_projection_equals_real_conductor_state(self):
        result = await self.conductor.run(run_id="test-contract", max_ticks=2, interval=0)
        prefix = self.conductor.ledger.read()["prefix"]
        adapter = Path(__file__).with_name("projection.mjs")
        actual = subprocess.run(["node", str(adapter)], input=canonical([e["event"] for e in prefix]),
                                capture_output=True, timeout=30, check=True)
        self.assertEqual(json.loads(actual.stdout), result["projection"])


if __name__ == "__main__":
    unittest.main()
