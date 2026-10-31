"""Mutation check: each mutant injects one real hazard into a fresh temporary copy; the contract tests must fail.

    python -m open_proposals.contract.mutants            # every mutant; exit 1 if any survives or fails to land

The working tree is never touched. A mutant must land (its snippet occurs exactly once and the file changes), or
it is reported as an error, never as a survivor. The two tests that pin bytes (the hash pins and the generator
check) are left out of mutant runs: they fail on any change, so a kill must come from a test of the hazard itself.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COPY = ["open_proposals", "contracts/open-proposal-v1", "contracts/HASHES.txt", "sentilab_core/__init__.py",
        "sentilab_core/envelope.py"]
FORM_TESTS = {"test_every_contract_file_is_pinned", "test_committed_files_match_the_generator"}
RUNNER = """
import json, sys, unittest
form = set(json.loads(sys.argv[1]))
def flat(suite):
    for test in suite:
        yield from (flat(test) if isinstance(test, unittest.TestSuite) else [test])
loader = unittest.defaultTestLoader
tests = [t for name in ("open_proposals.contract.test_golden", "open_proposals.contract.test_rules")
         for t in flat(loader.loadTestsFromName(name)) if t._testMethodName not in form]
result = unittest.TextTestRunner(stream=open(__import__("os").devnull, "w"), verbosity=0).run(unittest.TestSuite(tests))
print(json.dumps(sorted({t.id().rsplit(".", 1)[-1] for t, _ in result.failures + result.errors})))
"""
C, S, V, J = "open_proposals/contract/canonical.py", "open_proposals/contract/states.py", \
    "open_proposals/contract/validator.py", "contracts/open-proposal-v1/canonical.mjs"
L, K = "open_proposals/contract/labels.py", "open_proposals/contract/schemas.py"
SCH = "contracts/open-proposal-v1/schemas/"

# (id, rule, file, snippet, replacement)
MUTANTS = [
    # canonical form (JavaScript twin) and every hash binding
    ("canon-sort", "canonical: key order", J, "Object.keys(value).sort().map", "Object.keys(value).map"),
    ("canon-nonfinite", "canonical: nonfinite refused", J,
     'if (!Number.isFinite(value)) throw new Error("nonfinite JSON number");', ""),
    ("canon-surrogate", "canonical: lone surrogates refused", J,
     'if (hasLoneSurrogate(value)) throw new Error("lone surrogate");', ""),
    ("canon-negzero", "canonical: number form", J,
     '    return JSON.stringify(value);\n  }\n  if (typeof value === "string") return text(value);',
     '    return Object.is(value, -0) ? "-0" : JSON.stringify(value);\n  }\n'
     '  if (typeof value === "string") return text(value);'),
    ("js-geometry-config", "hash: geometry binds the fixture", J,
     "fixture_config_sha256: manifest.fixture.config_sha256,", 'fixture_config_sha256: "",'),
    ("js-transport-content", "hash: transport key binds content", J, "proposal_key, proposal_sha256]);",
     "proposal_key]);"),
    ("js-capability-domain", "hash: capability", J, '"sentilab-open-capability/1"', '"sentilab-open-capability/2"'),
    ("js-conductor-float", "hash: receipt geometry is exact", J, "xLL: (2 * die.x_um - w) / 2000",
     "xLL: die.x_um / 1000 - w / 2000"),
    ("py-geometry-lattice", "hash: geometry binds the declared lattice", C,
     ' "lattice_um": proposal["lattice_um"],', ""),
    ("py-geometry-config", "hash: geometry binds the fixture", C,
     '"fixture_config_sha256": manifest["fixture"]["config_sha256"],', '"fixture_config_sha256": "",'),
    ("py-proposal-whole", "hash: the whole proposal", C, "    return digest(proposal)\n",
     '    return digest({k: v for k, v in proposal.items() if k != "client"})\n'),
    ("py-body-exact", "hash: exact note bytes", C, "return sha256_hex(bytes(note))",
     "return sha256_hex(bytes(note).strip())"),
    ("py-source-prefix", "hash: source ref", C, 'SOURCE_PREFIX = "sentilab-open-source/1:"',
     'SOURCE_PREFIX = "sentilab-open-source/1"'),
    ("py-pseudonym-unkeyed", "hash: keyed pseudonym", C,
     "return hmac.new(bytes(pseudonym_key), message, hashlib.sha256).hexdigest()",
     "return hashlib.sha256(message).hexdigest()"),
    ("py-transport-slot", "hash: transport key binds the actor slot", C,
     "room, account_id, actor_slot(actor_kind, actor_agent_id), manifest_id,", "room, account_id, manifest_id,"),
    ("py-transport-room", "hash: transport key binds the room", C,
     "canonical([TRANSPORT_DOMAIN, room, account_id,", "canonical([TRANSPORT_DOMAIN, account_id,"),
    ("py-run-id", "hash: run id", C, "else participant_ref[:16]", "else participant_ref[:12]"),
    ("py-salt-domain", "hash: salt", C, 'SALT_DOMAIN = "sentilab-open-salt/1"', 'SALT_DOMAIN = "sentilab-open-salt/2"'),
    ("py-capability-key", "hash: capability keyed by the salt bytes", C, "key = bytes.fromhex(salt)",
     "key = bytes.fromhex(salt)[::-1]"),
    ("py-conductor-float", "hash: receipt geometry is exact", C, '"xLL": (2 * die["x_um"] - width) / 2000',
     '"xLL": die["x_um"] / 1000 - width / 2000'),
    ("py-ciphertext-ref", "hash: ciphertext ref is over the age bytes", V,
     "reference = hashes.ciphertext_ref(age_file)",
     'reference = hashes.ciphertext_ref(envelope["ciphertext"].encode())'),
    ("py-geometry-check", "hash: server recomputes the geometry hash", V,
     'if server_hash != proposal["geometry_sha256"]:', "if False:"),
    # transition guards and the transition table
    ("guard-reservation", "guard: reserved before launch", S, 'return "work needs a reservation before launch"',
     "pass"),
    ("guard-settled", "guard: settled on every exit", S, 'return "an attempt is recorded only after it is settled"',
     "pass"),
    ("guard-reject", "guard: rejection codes", S, "any(code not in REJECTION_CODES for code in codes)", "False"),
    ("guard-fail", "guard: failure code", S, 'frozenset(set(GROUPS["evaluation"]) - {"router_timeout"})',
     'frozenset(GROUPS["evaluation"])'),
    ("guard-fresh", "guard: fresh process", S, 'return "reproduction needs a fresh process"', "pass"),
    ("guard-not-reproduced", "guard: reproduction code", S,
     'return "a failed reproduction needs a reproduction code"', "pass"),
    ("guard-tier", "guard: cross-host or cross-build tier", S, 'TIERS = frozenset({"cross_host", "cross_build"})',
     'TIERS = frozenset({"cross_host", "cross_build", "replayed"})'),
    ("guard-not-verified", "guard: verification code", S,
     'return "a failed verification needs a verification code"', "pass"),
    ("guard-cancel", "guard: cancellation codes", S, 'return "a cancellation carries policy codes only"', "pass"),
    ("guard-operator", "guard: operator only", S, 'return "operator only"', "pass"),
    ("guard-withdrawn", "guard: no new work while withdrawn", S, 'return "withdrawn entries start no new work"',
     "pass"),
    ("guard-hide", "guard: hide reason", S, 'return "hiding needs a visibility reason"', "pass"),
    ("guard-unhide", "guard: unhide reason", S, 'return "unhiding needs a visibility reason"', "pass"),
    ("table-cancel-running", "table: cancel only before reservation", S, '"cancel": (("queued", "held"), "cancelled"),',
     '"cancel": (("queued", "held", "evaluating"), "cancelled"),'),
    ("table-verify-early", "table: verified implies reproduced", S, '"verify": (("reproduced",), "verifying"),',
     '"verify": (("reproduced", "evaluated"), "verifying"),'),
    ("table-requeue", "table: requeue only a failure", S, '"requeue": (("failed",), "queued"),',
     '"requeue": (("failed", "not_reproduced"), "queued"),'),
    ("table-restore", "overlay: restore only when withdrawn", S,
     'if event == "withdraw" and entry.withdrawn or event == "restore" and not entry.withdrawn:',
     'if event == "withdraw" and entry.withdrawn:'),
    ("table-ingest", "overlay: none before ingest", S,
     '        if entry.lifecycle is None:\n            raise TransitionRefused("not allowed from this state")\n', ""),
    # idempotency and order
    ("revision-content", "idempotency: same key and content", S,
     "if revision.proposal_key == proposal_key and revision.proposal_sha256 == proposal_sha256:",
     "if revision.proposal_key == proposal_key:"),
    ("revision-conflict", "idempotency: recorded conflict", S, 'codes.append("revision_conflict")', "pass"),
    ("revision-parent", "idempotency: parent lineage", S, 'codes.append("unknown_parent")', "pass"),
    ("revision-order", "order: decided in submission order", S,
     'raise OrderError("a submission is decided after every earlier one")', "pass"),
    ("order-offset", "order: numeric time with its offset", S,
     "calendar.timegm((year, month, day, hour, minute, second)) - offset",
     "calendar.timegm((year, month, day, hour, minute, second))"),
    ("order-text", "order: numeric, not text", S, 'return (created_at_ns(row["createdAt"]), row["id"], row["sessionId"])',
     'return (row["createdAt"], row["id"], row["sessionId"])'),
    ("order-room", "order: room tiebreak", S, 'return (created_at_ns(row["createdAt"]), row["id"], row["sessionId"])',
     'return (created_at_ns(row["createdAt"]), row["id"])'),
    ("order-dates", "order: impossible times refused", S,
     "    datetime(year, month, day, hour, minute, second)        # refuses impossible dates and times\n", ""),
    ("order-fraction", "order: exact fraction", S, '.ljust(9, "0")', '.rjust(9, "0")'),
    # size and abuse limits
    ("limit-note", "limit: 4096-byte note", V, "MAX_NOTE_BYTES = 4096", "MAX_NOTE_BYTES = 4097"),
    ("limit-depth", "limit: depth 4", V, "MAX_DEPTH = 4", "MAX_DEPTH = 5"),
    ("limit-dies", "limit: 32 dies", SCH + "proposal.schema.json", '"maxItems": 32,', '"maxItems": 33,'),
    ("limit-coordinate", "limit: coordinate range", SCH + "proposal.schema.json",
     '"x_um": {"type": "integer", "minimum": 0, "maximum": 1000000}',
     '"x_um": {"type": "integer", "minimum": 0, "maximum": 2000000}'),
    ("limit-key", "limit: 64-character ids", SCH + "common.schema.json", '"^[a-z0-9][a-z0-9_-]{0,63}$"},\n    "id_or',
     '"^[a-z0-9][a-z0-9_-]{0,127}$"},\n    "id_or'),
    ("limit-client", "limit: 32-character client fields", SCH + "proposal.schema.json",
     '"name": {"type": "string", "pattern": "^[A-Za-z0-9._-]{1,32}$"}',
     '"name": {"type": "string", "pattern": "^[A-Za-z0-9._-]{1,64}$"}'),
    ("limit-violations", "limit: 64 violations", "open_proposals/contract/codes.py", "MAX_VIOLATIONS = 64",
     "MAX_VIOLATIONS = 65"),
    ("limit-bom", "limit: strict UTF-8, no BOM", V, "bad = note.startswith(BOM)", "bad = False"),
    ("limit-utf8", "limit: strict UTF-8", V, 'note.decode("utf-8", errors="strict")',
     'note.decode("utf-8", errors="replace")'),
    ("limit-fence", "limit: only a json fence", V, 'FENCE = re.compile(r"```json', 'FENCE = re.compile(r"```(?:json)?'),
    ("limit-chat", "limit: chat is ignored, a fence is not", V,
     'return not (rest.startswith(b"{") or rest.startswith(b"```"))', 'return not rest.startswith(b"{")'),
    ("limit-integer", "limit: integer literals only", K, "return isinstance(instance, int) and not isinstance",
     "return isinstance(instance, (int, float)) and not isinstance"),
    ("limit-nonfinite", "limit: no NaN", V, '        flags.add("nonfinite_number")\n        return 0\n',
     "        return 0\n"),
    ("limit-duplicate", "limit: no duplicate keys", V, 'flags.add("duplicate_key")', "pass"),
    ("limit-closed", "limit: no unknown fields", K, 'found.append({"code": "unknown_field", "path": pointer(path)})',
     "pass"),
    ("limit-echo", "limit: never echo input", K, 'found.append({"code": "unknown_field", "path": pointer(path)})',
     'found.append({"code": "unknown_field", "path": pointer(path) + "/" + "_".join(sorted(error.instance))})'),
    ("limit-salt-public", "sealing: no salt on a public proposal", V,
     'return _outcome("rejected", [violation("salt_forbidden")])', "pass"),
    ("limit-salt-sealed", "sealing: a sealed plaintext needs its salt", V,
     'return _outcome("rejected", [violation("salt_required")])', "pass"),
    ("sealing-key", "sealing: key version", V, 'sealing["key_version"] != envelope["key_version"]', "False"),
    ("sealing-format", "sealing: age v1 only", V, "not age_file.startswith(AGE_HEADER)", "False"),
    ("sealing-faults", "sealing: only Unopenable is a code", V, "    except Unopenable:\n", "    except Exception:\n"),
    ("sealing-manifest", "sealing: plaintext names the envelope's manifest", V,
     'manifest, found = _known(manifests, target_id, value["manifest_id"])',
     "manifest, found = _known(manifests, target_id, target_id)"),
    ("sealing-epoch-py", "sealing: the capability binds its epoch", C,
     "canonical([CAPABILITY_DOMAIN, manifest_id, proposal_sha256, epoch])",
     "canonical([CAPABILITY_DOMAIN, manifest_id, proposal_sha256])"),
    ("sealing-epoch-js", "sealing: the capability binds its epoch", J, "proposalSha256_,\n    epoch])", "proposalSha256_])"),
    ("sealing-revoked", "sealing: revocation only on sealed entries", V,
     ' or (not record["sealed"] and capability != (None, None, False))', ""),
    ("admission-draft", "manifest: a draft is never open", V, 'if state != "open" or manifest["status"] != "frozen":',
     'if state != "open":'),
    ("manifest-lattice", "manifest: declared lattice", V,
     'if proposal["lattice_um"] != manifest["legality"]["lattice_um"]:', "if False:"),
    ("manifest-terms", "manifest: submission terms", V, 'if proposal["terms"] != manifest["terms"]["id"]:',
     "if False:"),
    ("geometry-lattice", "geometry: exact lattice", V, "        if off:\n", "        if off > 250:\n"),
    ("geometry-rotation", "geometry: rotation set", V, 'if die["rot_deg"] not in catalogue[index]["rot_deg"]:',
     "if False:"),
    ("geometry-seam", "seam: only stage-6 codes", V, 'item["code"] in LAYOUT_CODES and ', ""),
    # labels (SLAB-053 mirror and the rules that use it)
    ("label-case", "label: withdrawn key ignores case", L, '.split(":")[:2]).lower()', '.split(":")[:2])'),
    ("label-exact", "label: illustrative is exact", L, 'if identity in lists["illustrative"]:',
     'if any(identity.startswith(item) for item in lists["illustrative"]):'),
    ("label-order", "label: withdrawn first", L,
     '        return "unvalidated"\n    if evaluator_key(identity)',
     '        return "unvalidated"\n    if identity in lists["accepted"]:\n        return "accepted"\n'
     '    if evaluator_key(identity)'),
    ("label-empty", "label: no inputs is unvalidated", L,
     'if labels and all(label == "illustrative" for label in labels):',
     'if all(label == "illustrative" for label in labels):'),
    ("label-derived-withdrawn", "label: derived values take withdrawn", L,
     '    if "withdrawn" in labels:\n        return "withdrawn"\n', ""),
    ("label-accepted-empty", "label: nothing accepted yet", "contracts/open-proposal-v1/labels.json",
     '"accepted": []', '"accepted": ["HotSpot-6.0:a7a3286e368867c26381e0a23e36b3e273bdeda9"]'),
    ("label-required", "label: every measured value is labelled", SCH + "common.schema.json",
     '"tap_selector_c", "evaluator", "label"]', '"tap_selector_c", "evaluator"]'),
    ("rule-label-single", "label.single", V,
     'if obj is not None and obj["label"] != label_for(obj["evaluator"], lists):', "if False:"),
    ("rule-label-derived", "label.derived", V,
     'if obj is not None and obj["label"] != label_for_all(obj["evaluators"], lists):', "if False:"),
    ("rule-label-withdrawn", "label.withdrawn_comparison", V,
     'if _scored(row) and any(label_for(identity, lists) == "withdrawn" for identity in inputs):', "if False:"),
    ("rule-label-outcome", "label.claim_outcome", V,
     'if claim["outcome"] in DECIDED and claim["label"] not in ("accepted", "illustrative"):', "if False:"),
    # record rules
    ("rule-ref-source", "ref.source", V, 'if record["source_ref"] != hashes.source_ref(record["action_id"]):',
     "if False:"),
    ("rule-ref-participant", "ref.participant", V, "if key is not None and record[\"participant_ref\"] != ",
     "if False and record[\"participant_ref\"] != "),
    ("rule-ref-transport", "ref.transport", V,
     '    elif record["proposal_key"] is None or record["transport_id"] != hashes.transport_id(',
     '    elif False and record["transport_id"] != hashes.transport_id('),
    ("rule-ref-run-id", "ref.run_id", V,
     'if receipt["run_id"] != hashes.run_id(record["manifest_id"], receipt["participant_ref"]):', "if False:"),
    ("rule-record-manifest", "record.manifest", V,
     'if record["manifest_status"] != manifest["status"]:', "if False:"),
    ("rule-violation-fields", "violation.fields", "open_proposals/contract/codes.py",
     'and set(item) - {"code"} == set(FIELDS[item["code"]]))', ")"),
    ("rule-state-codes", "state.codes", V, '        return bool(names) and all(name in REJECTION_CODES for name in names)',
     "        return True"),
    ("rule-proposal-fields", "receipt.proposal_fields", V,
     'bad = [name for name in derived if record[name] is not None]', "bad = []"),
    ("rule-receipt-sealed", "receipt.sealed", V, 'if record["sealed"] != (record["ciphertext_ref"] is not None):',
     "if False:"),
    ("rule-privacy-sealed", "privacy.sealed", V, 'if ctx["audience"] == "public" and row["sealed"]:', "if False:"),
    ("rule-privacy-capability", "privacy.capability", V,
     'if kind != "private_request" and any(CAPABILITY.search(text) for text in _strings(record)):', "if False:"),
    ("rule-die-index", "manifest.die_index", V,
     '        if die["die"] != index:\n            found.append(_bad("record_inconsistent", f"/dies/{index}"',
     '        if False:\n            found.append(_bad("record_inconsistent", f"/dies/{index}"'),
    ("rule-square", "manifest.square_rotation", V, 'if sorted(die["rot_deg"]) != ([0] if fixed else [0, 90]):',
     "if False:"),
    ("rule-netlist", "manifest.netlist", V, "if not square or any(netlist[index][index] != 0 for index in range(count)):",
     "if not square:"),
    ("rule-tracks", "manifest.tracks", V, 'if len(set(track_ids)) != len(track_ids) or "strict" not in track_ids:',
     'if "strict" not in track_ids:'),
    ("rule-same-evaluator", "manifest.same_evaluator", V,
     'and reference["t_ref"]["evaluator"] != identity:', "and False:"),
    ("rule-variant", "manifest.variant", V, 'or variant["grid_um"] % record["legality"]["lattice_um"]', "or False"),
    ("rule-frozen", "manifest.frozen_pins", V, 'if thresholds["status"] != "frozen":', "if False:"),
    ("rule-check-legal", "check.legal", V, 'if record["legal"] != (not record["violations"]):', "if False:"),
    ("rule-check-routed", "check.routed", V, '(status == "skipped_illegal") == record["legal"] or ', ""),
    ("rule-fits", "check.fits_tracks", V,
     "if Decimal(repr(routed_mm)) <= Decimal(repr(track[\"factor\"])) * limit]",
     "if Decimal(repr(routed_mm)) < Decimal(repr(track[\"factor\"])) * limit]"),
    ("rule-check-charge", "check.charge", V,
     'if limits is not None and record["no_participant_charge"] != limits["check"]["no_participant_charge"]:',
     "if False:"),
    ("rule-scoring", "results.scoring", V, 'if reference["t_ref"] is None or reference["w_ref"] is None:', "if False:"),
    ("rule-results-evaluator", "results.same_evaluator", V,
     'or row["wire"]["evaluator"] != manifest["wire"]["evaluator"]):', "or False):"),
    ("rule-claim-missing", "claim.cases", V, 'allowed = {"incomplete", "unknown", "suppressed"}', "return []"),
    ("rule-claim-failed", "claim.cases (suppression)", V, 'allowed = {"unknown", "suppressed"}',
     'allowed = {"unknown", "suppressed", "incomplete", "passes_listed_cases"}'),
    ("rule-control", "control.result", V, 'return [] if row["control"]["result"] == result else [', "return [] if True else ["),
    ("rule-limits-charge", "limits.charge", V, 'if check["no_participant_charge"] and not (check["sponsored"]',
     'if check["no_participant_charge"] and not (True'),
    ("rule-limits-windows", "limits.windows", V, "if hour is not None and day is not None and day < hour:", "if False:"),
    ("rule-limits-cpu", "limits.cpu", V, 'if None not in values and Decimal', 'if False and Decimal'),
    ("rule-usage", "usage.charge", V, 'or unmeasured and record["debited_cpu_s"] != record["reserved_cpu_s"]', ""),
    ("rule-enforcement", "usage.enforcement", V, 'if record["enforcement"] == "stopped_in_flight" and (',
     "if False and ("),
    ("rule-overrun", "usage.overrun", V, 'if record["overrun"] != overrun:', "if False:"),
    ("rule-overrun-prevented", "usage.overrun: detected is not prevented", V,
     '"detected" if Decimal(repr(measured)) > reserved else "none")', '"none")'),
    ("label-diagnostic", "label: a diagnostic never changes the temperature's label", V,
     '        found += _single(row["temperature"], path + "/temperature", lists)\n',
     '        if row["temperature"] is not None and row["temperature"]["label"] != label_for_all(\n'
     '                [row["temperature"]["evaluator"]] + [d["evaluator"] for d in row["diagnostics"]], lists):\n'
     '            found.append(_bad("label_mismatch", path + "/temperature", "label.single"))\n'),
    ("rule-cursor", "cursor.created_at", V, '        created_at_ns(record["after"]["created_at"])\n', "        pass\n"),
    # schema-level rules
    ("schema-hidden", "schema: hidden needs a reason", SCH + "status.schema.json",
     '"then": {"properties": {"hidden_reason": {"type": "string"}}},',
     '"then": {"properties": {"hidden_reason": {}}},'),
    ("schema-queue", "schema: a queue place only while queued", SCH + "status.schema.json",
     '"else": {"properties": {"queue": {"type": "null"}}}}', '"else": {"properties": {"queue": {}}}}'),
    ("schema-draft", "schema: no scoring under a draft", SCH + "results.schema.json",
     '"claims": {"maxItems": 0},\n', '"claims": {},\n'),
    ("schema-strict", "schema: strict is W <= W_ref", SCH + "manifest.schema.json",
     '"then": {"properties": {"factor": {"const": 1}}},', '"then": {"properties": {"factor": {}}},'),
    ("schema-suppressed", "schema: suppression carries its code", SCH + "common.schema.json",
     '"then": {"properties": {"suppressed_by": {"type": "string"}}},', '"then": {"properties": {"suppressed_by": {}}},'),
    ("schema-relaxed-r", "schema: a relaxed claim names r", SCH + "common.schema.json",
     '"then": {"properties": {"r": {"type": "number"}}},', '"then": {"properties": {"r": {}}},'),
    ("schema-payer", "schema: a check is the sponsor's", SCH + "usage.schema.json",
     '"payer": {"const": "sponsor"}', '"payer": {}'),
    ("schema-cursor", "schema: a cursor start names no entry", SCH + "cursor.schema.json",
     '"then": {"properties": {"journal_seq": {"const": 0}', '"then": {"properties": {"journal_seq": {}'),
    ("schema-account-id", "schema: no account id in public receipts", SCH + "receipt.schema.json",
     '"sealed", "ciphertext_ref"],\n  "properties": {',
     '"sealed", "ciphertext_ref"],\n  "properties": {\n    "actor_user_id": {"type": "string"},'),
    ("schema-training", "schema: terms never permit training", SCH + "manifest.schema.json",
     '"training": {"const": false}', '"training": {"type": "boolean"}'),
    ("schema-queue-clock", "schema: the deadline clock excludes the queue", SCH + "limits.schema.json",
     '"queue_time_counted": {"const": false}', '"queue_time_counted": {"type": "boolean"}'),
]


def run_suite(root: Path) -> list:
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    result = subprocess.run([sys.executable, "-c", RUNNER, json.dumps(sorted(FORM_TESTS))], cwd=root, env=env,
                            capture_output=True, text=True, check=False)
    lines = result.stdout.strip().splitlines()
    if not lines:
        return ["<runner crashed>: " + result.stderr[-300:]]
    return json.loads(lines[-1])


def fresh_copy() -> Path:
    root = Path(tempfile.mkdtemp(prefix="op-f1-mutant-"))
    for item in COPY:
        source, target = ROOT / item, root / item
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__"))
        else:
            shutil.copy2(source, target)
    return root


def main() -> int:
    baseline_root = fresh_copy()
    try:
        baseline = run_suite(baseline_root)
    finally:
        shutil.rmtree(baseline_root, ignore_errors=True)
    if baseline:
        print("baseline fails:", baseline)
        return 1
    results = {"caught": [], "survived": [], "not_landed": []}
    for mutant_id, rule, path, old, new in MUTANTS:
        root = fresh_copy()
        try:
            target = root / path
            text = target.read_bytes().decode("utf-8")
            if text.count(old) != 1:
                results["not_landed"].append(mutant_id)
                print(f"NOT LANDED {mutant_id}: snippet occurs {text.count(old)} times")
                continue
            target.write_bytes(text.replace(old, new).encode("utf-8"))
            if target.read_bytes().decode("utf-8") == text:
                results["not_landed"].append(mutant_id)
                print(f"NOT LANDED {mutant_id}: file unchanged")
                continue
            failing = run_suite(root)
            outcome = "caught" if failing else "survived"
            results[outcome].append(mutant_id)
            print(f"{outcome.upper():9} {mutant_id:26} {rule:48} {', '.join(failing)[:120]}")
        finally:
            shutil.rmtree(root, ignore_errors=True)
    print(f"\n{len(MUTANTS)} mutants: {len(results['caught'])} caught, {len(results['survived'])} survived, "
          f"{len(results['not_landed'])} did not land")
    return 0 if not results["survived"] and not results["not_landed"] else 1


if __name__ == "__main__":
    sys.exit(main())
