"""Node-assisted CI conformance. Never imported by the Python service."""
import json
import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from sentilab_core.envelope import build, canonical, canonical_size, check_caps, digest, verify
from sentilab_core.ledger import read_prefix
from sentilab_core import test_conductor
from sentilab_core import test_ledger
from sentilab_core.memory_conformance import MemoryProjectionConformance as MemoryProjectionConformance
from sentilab_core.test_history import signed_version

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

    def test_v05_canonical_sizes_match_the_reviewed_reference(self):
        vectors = json.loads((ROOT / "contracts/view-envelope-v0.5/vectors-view.json").read_text())
        values = [json.loads(case["raw"]) for case in vectors["canonical"]]
        values += vectors["chains"][0]["envelopes"]
        script = """import { canonicalSize } from './contracts/view-envelope-v0.5/view-envelope.mjs';
let s=''; for await (const c of process.stdin) s+=c;
console.log(JSON.stringify(JSON.parse(s).map(canonicalSize)));"""
        result = subprocess.run(["node", "--input-type=module", "-e", script], cwd=ROOT,
                                input=json.dumps(values), text=True, capture_output=True, check=True)
        self.assertEqual([canonical_size(value) for value in values], json.loads(result.stdout))
        self.assertEqual([canonical_size(value) for value in values], [len(canonical(value)) for value in values])

    def test_v05_replay_prefix_matches_every_reviewed_chain_vector(self):
        vectors = json.loads((ROOT / "contracts/view-envelope-v0.5/vectors-view.json").read_text())
        public = {}
        for name in vectors["test_keys"]:
            identity = Ed25519PrivateKey.from_private_bytes(hashlib.sha256(
                ("sentilab-view-test-key:" + name).encode()).digest())
            public[name] = identity.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "vector.jsonl"
            for case in vectors["chains"]:
                keys = {pin["key_id"]: public[pin["test_key"]] for pin in case["view"]["pins"]
                        if case["view"]["served_keys"].get(pin["key_id"]) == pin["test_key"]}
                orders = case["send"].get("orders", [[row["event"]["event_id"] for row in case["envelopes"]]])
                for order in orders:
                    with self.subTest(vector=case["name"], order=order):
                        rows = case["envelopes"]
                        if "orders" in case["send"]:
                            rows = [next(row for row in rows if row["event"]["event_id"] == name) for name in order]
                        lines = []
                        for row in rows:
                            raw = json.dumps(row, ensure_ascii=True, separators=(",", ":")).encode()
                            padding = case["send"].get("pad")
                            if padding and row["event"]["seq"] == padding["seq"]:
                                raw += b" " * (padding["line_bytes"] - len(raw))
                            lines.extend([raw] * (2 if case["send"].get("twice") else 1))
                        path.write_bytes(b"\n".join(lines) + b"\n")
                        result = read_prefix(path, run_id=case["view"]["run_id"], public_keys=keys)
                        self.assertEqual(result["last_seq"], case["expect"]["prefix_end"])
                        self.assertEqual(result["error"] is None, case["expect"]["chain_ok"])

    def test_exact_canonical_byte_limits_match_contract_vectors(self):
        vectors = json.loads((ROOT / "contracts/view-envelope/vectors-view.json").read_text())
        for case in vectors["caps"]:
            if "target_bytes" not in case:
                continue
            envelope = json.loads(json.dumps(vectors["chains"][0]["envelopes"][3]))
            envelope["values"]["artifact_hashes"] = ["a" * 512 for _ in range(64)]
            envelope["values"]["geometry"] = [dict(id=f"g{i}", xLL=0, yLL=0, w=1, h=1, layer=0)
                                               for i in range(64)]
            missing = case["target_bytes"] - len(canonical(envelope))
            for entry in envelope["values"]["geometry"]:
                add = min(missing, 512 - len(entry["id"]))
                entry["id"] += "x" * add
                missing -= add
            self.assertEqual(missing, 0)
            self.assertEqual(digest(envelope), case["canonical_sha256"])
            if case["expect"]:
                with self.assertRaises(ValueError):
                    check_caps(envelope)
            else:
                check_caps(envelope)

class HistoryConformance(unittest.TestCase):
    setUp = test_ledger.LedgerTests.setUp
    append = test_ledger.LedgerTests.append

    def test_optional_values_preserve_existing_canonical_fields_and_history(self):
        legacy = self.ledger.append("node.create", {"id": "legacy", "kind": "candidate"},
                                    event_id="legacy")
        original = self.ledger.path.read_bytes()
        geometry = [{"id": "chip-a", "xLL": 1.25, "yLL": 2.5, "w": 6, "h": 5, "layer": 0}]
        new_candidate = self.ledger.append("node.create", {"id": "new", "kind": "candidate"},
                                           event_id="new", values={"geometry": geometry, "units": "mm"})
        old_values = {"J": {"value": 118.36, "unit": "°C"},
                      "W": {"value": 27.7, "metric_id": "weighted-manhattan-mm"}}
        measured = self.ledger.append("node.create", {"id": "measured", "kind": "measurement"},
                                      event_id="measured", values=old_values)
        for old, extra in ((legacy, {"geometry": geometry, "units": "mm"}),
                           (measured, {"center_temps": {"chip-a": 101.25}})):
            with self.subTest(fields=list(extra)):
                original_fields = {k: v for k, v in old.items() if k not in ("hash", "sig")}
                extended = build(event=old["event"], run=old["run"], actor=old["actor"],
                                 prev_hash=old["prev_hash"], ts=old["ts"], signer=self.signer,
                                 values={**old.get("values", {}), **extra})
                self.assertNotEqual(extended["hash"], old["hash"])
                verify(extended, run_id="test-run", public_keys=self.keys)
                chain = [extended] if old is legacy else [legacy, new_candidate, extended]
                checked = self.reference(b"".join(canonical(e) + b"\n" for e in chain), "view-envelope/0.5")
                self.assertTrue(checked["chain_ok"])
                self.assertEqual(checked["prefix_end"], len(chain))
                existing = {k: v for k, v in extended.items() if k not in ("hash", "sig")}
                if "values" in old:
                    existing["values"] = {k: v for k, v in existing["values"].items() if k not in extra}
                else:
                    existing.pop("values")
                self.assertEqual(canonical(existing), canonical(original_fields))
                self.assertEqual(digest(existing), old["hash"])
                tampered = {**old, "values": extended["values"]}
                with self.assertRaises(ValueError):
                    verify(tampered, run_id="test-run", public_keys=self.keys)
        raw = self.ledger.path.read_bytes()
        self.assertTrue(raw.startswith(original))
        self.assertEqual(new_candidate["prev_hash"], legacy["hash"])
        native = self.ledger.read()
        self.assertIsNone(native["error"])
        self.assertEqual(native["prefix"], [legacy, new_candidate, measured])
        for data, count in ((original, 1), (raw, 3)):
            checked = self.reference(data, "view-envelope/0.5")
            self.assertTrue(checked["chain_ok"])
            self.assertEqual(checked["prefix_end"], count)

    def reference(self, raw, version, *, run_id="test-run", keys=None):
        script = """import { createPublicKey } from 'node:crypto';
let s=''; for await (const c of process.stdin) s+=c; const data=JSON.parse(s);
const directory=data.version==='view-envelope/0.4'?'view-envelope':'view-envelope-v0.5';
const reference=await import(`./contracts/${directory}/view-envelope.mjs`);
const keys={}, pins=[];
for (const [id,hex] of Object.entries(data.keys)) {
  const key=createPublicKey({key:Buffer.concat([Buffer.from('302a300506032b6570032100','hex'),Buffer.from(hex,'hex')]),format:'der',type:'spki'});
  keys[id]=key; pins.push({key_id:id,key_sha256:reference.keySha256(key)});
}
let result;
try {
  // Preserve a leading BOM as U+FEFF so JSON.parse rejects it, and fail on
  // malformed UTF-8. Hashing/cursors operate on the original bytes separately.
  const text=new TextDecoder('utf-8',{fatal:true,ignoreBOM:true}).decode(Buffer.from(data.raw,'hex'));
  const options={runId:data.run_id,keys,pins};
  result=reference.verifyJsonl ? reference.verifyJsonl(text,options) :
    reference.verifyChain(text.trimEnd().split('\\n').map(line=>JSON.parse(line)),options);
} catch { result={prefix_end:0,chain_ok:false}; }
console.log(JSON.stringify(result));"""
        result = subprocess.run(["node", "--input-type=module", "-e", script], cwd=ROOT,
                                input=json.dumps({"version": version, "raw": raw.hex(), "run_id": run_id,
                                                  "keys": {k: v.hex() for k, v in (keys or self.keys).items()}}),
                                text=True, capture_output=True, check=True, timeout=30)
        return json.loads(result.stdout)

    def test_signed_versions_match_the_selected_exact_reference(self):
        current = self.append(1)[0]
        for version in ("view-envelope/0.4", "view-envelope/0.5", "unrecognized/999"):
            value = signed_version(current, version, self.signer)
            raw = canonical(value) + b"\n"
            self.ledger.path.write_bytes(raw)
            native = read_prefix(self.ledger.path, run_id="test-run", public_keys=self.keys)
            self.assertEqual(native["last_seq"], 0 if version == "unrecognized/999" else 1)
            for profile in ("view-envelope/0.4", "view-envelope/0.5"):
                with self.subTest(version=version, profile=profile):
                    reference = self.reference(raw, profile)
                    pinned = read_prefix(self.ledger.path, run_id="test-run", public_keys=self.keys,
                                         version=profile)
                    self.assertEqual(reference["prefix_end"], int(version == profile))
                    self.assertEqual(pinned["last_seq"], reference["prefix_end"])
                    self.assertEqual(pinned["error"] is None, reference["chain_ok"])

    def test_raw_utf8_boundary_matches_exact_v05_reference(self):
        current = self.append(1)[0]
        text = canonical(current).decode("utf-8")
        for encoding in ("utf-8", "utf-8-sig", "utf-16-le", "utf-32-be"):
            with self.subTest(encoding=encoding):
                raw = text.encode(encoding) + b"\n"
                self.ledger.path.write_bytes(raw)
                native = read_prefix(self.ledger.path, run_id="test-run", public_keys=self.keys)
                reference = self.reference(raw, "view-envelope/0.5")
                self.assertEqual(reference["prefix_end"], int(encoding == "utf-8"))
                self.assertEqual(native["last_seq"], reference["prefix_end"])
                self.assertEqual(native["error"] is None, reference["chain_ok"])

    def test_retained_history_keeps_v04_profile_and_original_hashes(self):
        proof = json.loads((ROOT / "sentilab_core/proof.json").read_text())
        directory = ROOT / proof["artifact_root"]
        for name, expected in proof["artifacts"].items():
            self.assertEqual(hashlib.sha256((directory / name).read_bytes()).hexdigest(), expected)
        pin = json.loads((directory / "public-pin.json").read_text())
        keys = {key_id: bytes.fromhex(public) for key_id, public in pin.items()}
        path = directory / "ledger/ascend910-local-proof-v2.jsonl"
        native = read_prefix(path, run_id=proof["run_id"], public_keys=keys, version="view-envelope/0.4")
        reference = self.reference(path.read_bytes(), "view-envelope/0.4", run_id=proof["run_id"], keys=keys)
        self.assertEqual(native["last_seq"], proof["seq"])
        self.assertEqual(reference["prefix_end"], proof["seq"])
        self.assertTrue(reference["chain_ok"])
        self.assertIsNone(native["error"])
        self.assertTrue(all(row["v"] == "view-envelope/0.4" for row in native["prefix"]))
        newer = self.reference(path.read_bytes(), "view-envelope/0.5", run_id=proof["run_id"], keys=keys)
        self.assertEqual(newer["prefix_end"], 0)
        self.assertIn("bad_version", newer["rows"][0]["reasons"])


class ProjectionConformance(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_conductor.ConductorTests.asyncSetUp
    async def test_contract_javascript_projection_equals_real_conductor_state(self):
        result = await self.conductor.run(run_id="test-contract", max_ticks=2, interval=0)
        prefix = self.conductor.ledger.read()["prefix"]
        adapter = Path(__file__).with_name("projection.mjs")
        actual = subprocess.run(["node", str(adapter)], input=canonical([e["event"] for e in prefix]),
                                capture_output=True, timeout=30, check=True)
        self.assertEqual(json.loads(actual.stdout), result["projection"])
        self.assertTrue(all(row["v"] == "view-envelope/0.5" for row in prefix))
        script = """import { createPublicKey } from 'node:crypto';
import { verifyJsonl, keySha256, parseApiResponse } from './contracts/view-envelope-v0.5/view-envelope.mjs';
let s=''; for await (const c of process.stdin) s+=c; const data=JSON.parse(s);
const key=createPublicKey({key:Buffer.concat([Buffer.from('302a300506032b6570032100','hex'),Buffer.from(data.public,'hex')]),format:'der',type:'spki'});
if (!parseApiResponse(data.jsonl).ok) throw new Error('transport cap');
console.log(JSON.stringify(verifyJsonl(data.jsonl,{runId:data.run_id,pins:[{key_id:data.key_id,key_sha256:keySha256(key)}],keys:{[data.key_id]:key}})));"""
        actual = subprocess.run(["node", "--input-type=module", "-e", script], cwd=ROOT,
                                input=json.dumps({"jsonl": "".join(canonical(row).decode() + "\n" for row in prefix),
                                                  "run_id": "test-contract", "key_id": self.signer.key_id,
                                                  "public": self.signer.public_key.hex()}),
                                text=True, capture_output=True, timeout=30, check=True)
        checked = json.loads(actual.stdout)
        self.assertTrue(checked["chain_ok"])
        self.assertEqual(checked["prefix_end"], len(prefix))
        self.assertEqual(checked["projection"], result["projection"])


def load_tests(loader, tests, pattern):
    # The existing CI entry point also owns the cross-surface inventory gate.
    from sentilab_core import test_conformance
    tests.addTests(loader.loadTestsFromModule(test_conformance))
    return tests


if __name__ == "__main__":
    unittest.main()
