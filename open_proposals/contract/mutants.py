"""Mutation check: each mutant injects one real hazard into a fresh temporary copy; the contract tests must fail.

    python -m open_proposals.contract.mutants            # every mutant; exit 1 if any survives or fails to land
    python -m open_proposals.contract.mutants --land     # only check that every mutant lands
    python -m open_proposals.contract.mutants --only=a,b # just these mutants (a spot check, not the result)

The working tree is never touched. A mutant must land (its snippet occurs exactly once and the file changes), or
it is reported as an error, never as a survivor; a mutant that stops the suite from importing or running is
broken, never a kill. The tests that pin bytes (the hash pins and the generator check)
are left out of mutant runs: they fail on any change, so a kill must come from a test of the hazard itself.
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
FORM_TESTS = {"test_every_contract_file_is_pinned", "test_the_files_match_their_generator"}
SUITES = ("open_proposals.contract.test_golden", "open_proposals.contract.test_rules",
          "open_proposals.contract.test_predicates", "open_proposals.contract.test_age")
RUNNER = """
import json, sys, unittest
form = set(json.loads(sys.argv[1]))
def flat(suite):
    for test in suite:
        yield from (flat(test) if isinstance(test, unittest.TestSuite) else [test])
loader = unittest.defaultTestLoader
tests = [t for name in json.loads(sys.argv[2]) for t in flat(loader.loadTestsFromName(name))
         if t._testMethodName not in form]
result = unittest.TextTestRunner(stream=open(__import__("os").devnull, "w"), verbosity=0).run(unittest.TestSuite(tests))
print(json.dumps(sorted({t.id().rsplit(".", 1)[-1] for t, _ in result.failures + result.errors})))
"""
PKG = "open_proposals/contract/"
C, S, V, J = PKG + "canonical.py", PKG + "states.py", PKG + "validator.py", "contracts/open-proposal-v1/canonical.mjs"
L, K, D, P, A = PKG + "labels.py", PKG + "schemas.py", PKG + "codes.py", PKG + "predicates.py", PKG + "age_tools.py"
SCH = "contracts/open-proposal-v1/schemas/"

# (id, rule, file, snippet, replacement)
MUTANTS = [
    # ── canonical form and the JavaScript twin (T1) ──
    ("js-sort", "canonical: key order", J, "Object.keys(value).sort().map", "Object.keys(value).map"),
    ("js-nonfinite", "canonical: nonfinite refused", J,
     'if (!Number.isFinite(value)) throw new Error("nonfinite JSON number");', ""),
    ("js-surrogate", "canonical: lone surrogates refused", J,
     'if (hasLoneSurrogate(value)) throw new Error("lone surrogate");', ""),
    ("js-negzero", "canonical: number form", J,
     '    return JSON.stringify(value);\n  }\n  if (typeof value === "string") return text(value);',
     '    return Object.is(value, -0) ? "-0" : JSON.stringify(value);\n  }\n'
     '  if (typeof value === "string") return text(value);'),
    ("js-geometry-config", "hash: geometry binds the fixture", J,
     "fixture_config_sha256: manifest.fixture.config_sha256,", 'fixture_config_sha256: "",'),
    ("js-geometry-problem", "hash: geometry binds the problem", J, "problem: manifest.problem,", 'problem: "x",'),
    ("js-transport-content", "transport key: binds the content", J,
     "logical_key: logicalKey(item), content_sha256: await contentSha256(item) });",
     'logical_key: logicalKey(item), content_sha256: "" });'),
    ("js-transport-hex", "transport key: 48 hex", J, ".slice(0, TRANSPORT_HEX_CHARS)", ".slice(0, 47)"),
    ("js-transport-prefix", "transport key: so1-", J, 'export const TRANSPORT_PREFIX = "so1-";',
     'export const TRANSPORT_PREFIX = "so2-";'),
    ("js-publish-key", "transport key: publish logical key", J,
     'return PUBLISH_KEY_PREFIX + item.proposal_sha256;', 'return "publish";'),
    ("js-pseudonym", "pseudonym: keyed", J, "return hmacSha256Hex(kChallenge, utf8(accountId));",
     "return sha256Hex(utf8(accountId));"),
    ("js-conductor-float", "hash: receipt geometry is exact", J, "xLL: (2 * die.x_um - w) / 2000",
     "xLL: die.x_um / 1000 - w / 2000"),
    ("js-armour-canonical", "sealing: strict armour", J, "if (bytes.length === 0 || armor(bytes) !== lines.join(LF) + LF)",
     "if (bytes.length === 0)"),
    ("js-sealed-line", "sealing: the first line", J, "([1-9][0-9]{0,5})${LF}", "([0-9]+)${LF}"),
    ("js-r-key", "q_r keys: two decimals", J, 'return r === 0 ? "0" : r.toFixed(2);', "return String(r);"),
    ("js-run-id-digest", "run id: 32 hex of the run digest", J, "(await digest(preimage)).slice(0, 32)",
     "(await digest(preimage)).slice(0, 31)"),
    ("js-run-id-account", "run id: binds the account", J, "participant_ref: participantRef_,", 'participant_ref: "",'),
    ("js-run-id-strict", "run id: full digests only (P3)", J,
     'if (typeof value !== "string" || !HEX64.test(value)) throw new Error("a run id binds',
     'if (typeof value !== "string" || value.length !== 64) throw new Error("a run id binds'),
    # ── hashes and keys (Python) ──
    ("py-geometry-config", "hash: geometry binds the fixture", C,
     '"fixture_config_sha256": manifest["fixture"]["config_sha256"],', '"fixture_config_sha256": "",'),
    ("py-geometry-problem", "hash: geometry binds the problem", C, '"problem": manifest["problem"],',
     '"problem": "x",'),
    ("py-geometry-salt", "hash: geometry excludes the salt", C,
     '"units": item["units"], "anchor": item["anchor"],',
     '"units": item["units"], "anchor": item["anchor"], "salt": item.get("salt"),'),
    ("py-content-client", "hash: the whole object", C, "    return digest(item)\n\n\nproposal_sha256",
     '    return digest({k: v for k, v in item.items() if k != "client"})\n\n\nproposal_sha256'),
    ("py-body-exact", "hash: exact note bytes", C, "return sha256_hex(bytes(note))",
     "return sha256_hex(bytes(note).strip())"),
    ("py-source-prefix", "hash: source ref", C, 'SOURCE_PREFIX = "sentilab-open-source/1:"',
     'SOURCE_PREFIX = "sentilab-open-source/1"'),
    ("py-pseudonym-unkeyed", "pseudonym: keyed", C,
     'return hmac.new(bytes(k_challenge), account_id.encode("utf-8"), hashlib.sha256).hexdigest()',
     'return hashlib.sha256(account_id.encode("utf-8")).hexdigest()'),
    ("py-pseudonym-short-key", "pseudonym: a 32-byte key", C, "len(k_challenge) < 32", "len(k_challenge) < 3"),
    ("py-transport-slot", "transport key: binds the actor slot", C,
     "actor_slot=actor_slot(actor_kind, actor_id),", 'actor_slot="human",'),
    ("py-transport-room", "transport key: binds the room", C, "return transport_key(room=room, account=account,",
     'return transport_key(room="", account=account,'),
    ("py-transport-content", "transport key: binds the content", C, "content_sha256=content_sha256(item))",
     'content_sha256=item["manifest_id"])'),
    ("py-transport-hex", "transport key: 48 hex", C, "[:TRANSPORT_HEX_CHARS]", "[:47]"),
    ("py-logical-publish", "transport key: publish logical key", C,
     'return PUBLISH_KEY_PREFIX + item["proposal_sha256"]', 'return "publish"'),
    ("py-logical-team", "transport key: team logical key", C, "        return TEAM_KEY\n",
     '        return item["name"].lower()\n'),
    ("py-run-id-digest", "run id: 32 hex of the run digest", C, "RUN_DIGEST_HEX_CHARS = 32",
     "RUN_DIGEST_HEX_CHARS = 31"),
    ("py-run-id-account", "run id: binds the account", C,
     '"manifest_id": manifest_id, "participant_ref": participant_ref,',
     '"manifest_id": manifest_id, "participant_ref": "",'),
    ("py-run-id-strict", "run id: full digests only (P3)", C,
     "        if not isinstance(value, str) or not HEX64.fullmatch(value):\n"
     "            raise ValueError(\"a run id binds three full sha256 hex digests\")",
     "        if not isinstance(value, str) or len(value) != 64:\n"
     "            raise ValueError(\"a run id binds three full sha256 hex digests\")"),
    ("py-sealed-header", "sealing: the first line", C, 'return f"{SEALED_SCHEMA} {manifest_id} {key_version}"',
     'return f"{SEALED_SCHEMA} {manifest_id} v{key_version}"'),
    ("py-r-key", "q_r keys: two decimals", C, 'return "0" if exact == 0 else f"{exact:.2f}"', "return str(exact)"),
    ("py-q-exact", "q_r: exact decimal", C,
     "return float(Decimal(repr(w_c_mm)) - (1 + Decimal(key)) * Decimal(repr(w_r_mm)))",
     "return w_c_mm - (1 + float(key)) * w_r_mm"),
    ("py-conductor-float", "hash: receipt geometry is exact", C, '"xLL": (2 * die["x_um"] - width) / 2000',
     '"xLL": die["x_um"] / 1000 - width / 2000'),
    # ── the intake and the offline checker ──
    ("attempt-space", "attempt: the first bytes", V, 'return note.startswith(b"{") or',
     'return note.strip().startswith(b"{") or'),
    ("attempt-sealed", "attempt: a sealed note", V, ' or note.startswith(SEALED_PREFIX)\n', "\n"),
    ("row-unattributable", "transport: unattributable", V, "if not reply.actor_user_id or not slot_ok:",
     "if not reply.actor_user_id:"),
    ("row-edited", "transport: edited before ingest", V,
     "if reply.message_revision != 1 or reply.edited_at is not None:", "if reply.message_revision != 1:"),
    ("limit-plaintext", "limit: 4,096 plaintext bytes", V, "MAX_PLAINTEXT_BYTES = 4096", "MAX_PLAINTEXT_BYTES = 4097"),
    ("limit-sealed", "limit: 8,192 sealed bytes", V, "MAX_SEALED_BYTES = 8192", "MAX_SEALED_BYTES = 8193"),
    ("limit-sealed-plaintext", "limit: 4,096 bytes inside a seal", V, "if len(plaintext) > MAX_PLAINTEXT_BYTES:",
     "if False:"),
    ("limit-depth", "limit: depth 4", V, "MAX_DEPTH = 4", "MAX_DEPTH = 5"),
    ("limit-utf8", "limit: strict UTF-8", V, 'note.decode("utf-8", errors="strict")',
     'note.decode("utf-8", errors="replace")'),
    ("limit-fence", "limit: only a json fence", V, 'FENCE = re.compile(r"```json', 'FENCE = re.compile(r"```(?:json)?'),
    ("limit-nonfinite", "limit: no NaN", V, '        flags.add("nonfinite_number")\n        return 0\n',
     "        return 0\n"),
    ("limit-duplicate", "limit: no duplicate keys", V, 'flags.add("duplicate_key")', "pass"),
    ("limit-violations", "limit: 64 violations", D, "MAX_VIOLATIONS = 64", "MAX_VIOLATIONS = 65"),
    ("limit-integer", "limit: integer literals only", K, "return isinstance(instance, int) and not isinstance",
     "return isinstance(instance, (int, float)) and not isinstance"),
    ("limit-closed", "limit: no unknown fields", K, 'found.append({"code": "unknown_field", "path": pointer(path)})',
     "pass"),
    ("limit-echo", "limit: never echo input", K, 'found.append({"code": "unknown_field", "path": pointer(path)})',
     'found.append({"code": "unknown_field", "path": pointer(path) + "/" + "_".join(sorted(error.instance))})'),
    ("private-plaintext", "sealing: private_requires_sealed", V,
     'if not local and (value.get("visibility") == "private" or kind_of(value) == "publish"):', "if False:"),
    ("private-local", "sealing: the offline checker reads plaintext", V,
     'if not local and (value.get("visibility") == "private" or kind_of(value) == "publish"):',
     'if (value.get("visibility") == "private" or kind_of(value) == "publish"):'),
    ("publish-plaintext", "publish: a plaintext command is refused", V,
     'if not local and (value.get("visibility") == "private" or kind_of(value) == "publish"):',
     'if not local and value.get("visibility") == "private":'),
    ("publish-sealable", "publish: a sealed command opens", V,
     'SEALABLE = frozenset({"proposal", "check-request", "publish"})', 'SEALABLE = frozenset({"proposal", "check-request"})'),
    ("sealed-key-version", "sealing: the manifest's key version", V, ' or sealing["key_version"] != key_version', ""),
    ("sealed-recipient", "sealing: a pinned recipient", V, 'if sealing["recipient"] is None or ', "if "),
    ("sealed-armour", "sealing: armour before opening", V, " or not armour.startswith(ARMOR_BEGIN)", ""),
    ("sealed-header-manifest", "sealing: the thread's manifest", V, "    if named != target_id:\n",
     "    if False:\n"),
    ("sealed-unknown", "sealing: a known manifest", V, "    if named not in manifests:\n", "    if False:\n"),
    ("sealed-faults", "sealing: only Unopenable is a code", V,
     "    except Unopenable:\n        return None, [violation(\"unsealable\")], False",
     "    except Exception:\n        return None, [violation(\"unsealable\")], False"),
    ("sealed-schema", "sealing: proposals and checks only", V, "if kind_of(value) not in SEALABLE:", "if False:"),
    ("schema-kind-string", "envelope: a schema value is a string", V,
     "return POSTED.get(schema) if isinstance(schema, str) else None", "return POSTED.get(schema)"),
    ("sealed-not-json", "sealing: one JSON object or unsealable", V,
     'if found and found[0]["code"] == "malformed_json":', "if False:"),
    ("sealed-not-utf8", "sealing: UTF-8 or unsealable", V,
     "    except UnicodeDecodeError:\n        return None, [violation(\"unsealable\")], True",
     "    except UnicodeDecodeError:\n        return None, [violation(\"not_utf8\")], True"),
    ("sealed-fence", "sealing: no fence inside a seal", V, "value, found = _json(text, fenced=False)",
     "value, found = _json(text, fenced=True)"),
    ("transport-key-check", "transport key: recomputed by the intake", V,
     "if reply is not None and reply.idempotency_key != hashes.transport_key_for(",
     "if False and reply.idempotency_key != hashes.transport_key_for("),
    ("manifest-unknown", "manifest: unknown", V, '    if value["manifest_id"] not in manifests:\n',
     "    if False:\n"),
    ("manifest-mismatch", "manifest: the thread's", V, '    if value["manifest_id"] != target_id:\n',
     "    if False:\n"),
    ("admission-signed", "manifest: only a signed manifest opens", V,
     'if state != "open" or manifest["status"] != "signed":', 'if state != "open":'),
    ("admission-default", "manifest: unlisted is not open", V, 'state = admission.get(manifest_id, "not_open_yet")',
     'state = admission.get(manifest_id, "open")'),
    ("admission-cpu", "admission: live CPU enforcement evidence", V,
     '    if manifest["checks"]["cpu_enforcement_evidence_sha256"] is None:\n', "    if False:\n"),
    ("admission-closed", "manifest: closed", V, '    if state == "closed":\n', "    if False:\n"),
    ("terms-accepted", "terms: an accepted version", V,
     'if kind in WITH_TERMS and value["terms"] not in manifest["terms"]["accepted_versions"]:', "if False:"),
    ("every-violation", "legality: every violation reported", V,
     "    found = _admission(manifest, target_id, admission)\n",
     "    found = _admission(manifest, target_id, admission)\n    if found:\n"
     "        return _rejected(found, kind=kind, item=value, content=content, sealed=sealed)\n"),
    ("geometry-hash", "geometry: recomputed hash", V, 'if server_hash != item["geometry_sha256"]:', "if False:"),
    ("geometry-count", "geometry: die count", V, 'found.append(violation("die_count", count=len(dies)))', "pass"),
    ("geometry-order", "geometry: die order", V,
     'misplaced = [index for index, die in enumerate(dies) if die["die"] != index]', "misplaced = []"),
    ("geometry-rotation", "geometry: rotation set", V, 'if die["rot_deg"] not in catalogue[index]["rot_deg"]:',
     "if False:"),
    ("geometry-frame-y", "geometry: frame in y", V,
     'outside = max(die["x_um"] - frame, die["y_um"] - frame, 0)', 'outside = max(die["x_um"] - frame, 0)'),
    ("geometry-frame-edge", "geometry: the frame edge is in", V,
     'outside = max(die["x_um"] - frame, die["y_um"] - frame, 0)',
     'outside = max(die["x_um"] - frame + 1, die["y_um"] - frame, 0)'),
    ("geometry-lattice", "geometry: exact lattice", V, "        if off:\n", "        if off > 250:\n"),
    ("geometry-lattice-nearest", "geometry: lattice distance", V, "    return min(rest, step - rest)",
     "    return rest"),
    ("seam-mapped", "seam: only when the dies map", V, "checked = mapped and layout_checker is not None",
     "checked = layout_checker is not None"),
    ("seam-contract", "seam: layout codes only", V, 'entry["code"] in LAYOUT_CODES and ', ""),
    ("seam-keepout", "seam: keepouts", V, 'LAYOUT_CODES = frozenset({"margin", "halo_overlap", "min_spacing", "keepout"})',
     'LAYOUT_CODES = frozenset({"margin", "halo_overlap", "min_spacing"})'),
    ("seam-legal", "seam: legal only when checked", V, 'outcome = "legal" if checked else "contract_valid"',
     'outcome = "legal"'),
    ("codes-order", "codes: canonical order", D, 'return (ORDER[item["code"]], item.get("path", ""),',
     'return (item["code"], item.get("path", ""),'),
    ("codes-fields", "violation.fields", D, 'and set(item) - {"code"} == set(FIELDS[item["code"]]))', ")"),
    # ── states, idempotency and order ──
    ("guard-reservation", "guard: reserved before launch", S, 'return "work needs a reservation before launch"',
     "pass"),
    ("guard-uuid", "guard: a reservation id", S, ' or not UUID.match(payload["reservation_id"])', ""),
    ("guard-settled", "guard: settled on every exit", S, 'return "an attempt is recorded only after it is settled"',
     "pass"),
    ("guard-reject", "guard: rejection codes", S,
     "(not codes or any(code not in REJECTION_CODES for code in codes))", "(not codes)"),
    ("guard-reject-empty", "guard: a rejection names codes", S,
     "(not codes or any(code not in REJECTION_CODES for code in codes))",
     "(any(code not in REJECTION_CODES for code in codes))"),
    ("guard-fail-one", "guard: one failure code", S,
     'if event == "fail" and (len(codes) != 1 or codes[0] not in FAILURE_CODES):',
     'if event == "fail" and (not codes or codes[0] not in FAILURE_CODES):'),
    ("guard-fail-codes", "guard: the five failure codes", S,
     'FAILURE_CODES = frozenset({"timeout", "stopped", "oracle_error", "grant_expired", "interrupted"})',
     'FAILURE_CODES = frozenset({"timeout", "stopped", "oracle_error", "grant_expired", "interrupted", '
     '"router_timeout"})'),
    ("guard-complete", "guard: qualifier codes only", S,
     'if event == "complete" and any(code not in QUALIFIER_CODES for code in codes):', "if False:"),
    ("guard-fresh", "guard: fresh process", S, 'return "reproduction needs a fresh process"', "pass"),
    ("guard-not-reproduced", "guard: reproduction code", S,
     'if event == "not_reproduced" and (len(codes) != 1 or codes[0] not in REPRODUCTION_CODES):', "if False:"),
    ("guard-tier", "guard: cross_build or cross_arch", S, 'CROSS_TIERS = frozenset({"cross_build", "cross_arch"})',
     'CROSS_TIERS = frozenset({"cross_build", "cross_arch", "cross_solver"})'),
    ("guard-cancel", "guard: cancellation codes", S, 'return "a cancellation carries policy codes only"', "pass"),
    ("guard-no-codes", "guard: events without codes", S, 'if event in ("accept", "hold",', 'if event in ("hold",'),
    ("guard-operator", "guard: operator only", S, 'return "operator only"', "pass"),
    ("guard-code-names", "guard: codes are names", S,
     "if not isinstance(codes, (list, tuple)) or not all(isinstance(code, str) for code in codes):",
     "if not isinstance(codes, (list, tuple)):"),
    ("guard-names", "guard: tiers and reasons are names", S, "return isinstance(value, str) and value in allowed",
     "return value in allowed"),
    ("guard-hide", "guard: a moderation reason", S, 'return "hiding needs a moderation reason"', "pass"),
    ("guard-restore", "guard: a restore reason", S, 'return "restoring needs a moderation reason"', "pass"),
    ("publish-sealed-guard", "publish: a sealed command", S, 'if event == "publish" and payload.get("sealed") is not True:',
     "if False:"),
    ("publish-refusal", "publish: a refusal changes nothing", S, 'if event == "publish" and codes:', "if False:"),
    ("publish-once", "publish: only a private entry", S, 'if entry.state is None or entry.visibility != "private":',
     "if entry.state is None:"),
    ("publish-result", "publish: the entry becomes public", S, 'return replace(entry, visibility="public")',
     "return entry"),
    ("table-cancel-running", "table: cancel only before a reservation", S,
     '"cancel": (("queued", "held"), "cancelled"),', '"cancel": (("queued", "held", "evaluating"), "cancelled"),'),
    ("table-fail-evaluated", "table: evaluated can fail", S, '"fail": (("evaluating", "evaluated"), "failed"),',
     '"fail": (("evaluating",), "failed"),'),
    ("table-retry", "table: no automatic retry", S,
     '    "expire": (("queued", "held"), "expired"),\n}',
     '    "expire": (("queued", "held"), "expired"),\n    "requeue": (("failed",), "queued"),\n}'),
    ("table-cross-early", "table: cross_checked follows reproduced", S,
     '"cross_checked": (("reproduced",), "cross_checked"),',
     '"cross_checked": (("reproduced", "evaluated"), "cross_checked"),'),
    ("flag-ingest", "flag: none before ingest", S, "if entry.state is None or (event == \"hide\") != (entry.hidden is None):",
     "if (event == \"hide\") != (entry.hidden is None):"),
    ("flag-twice", "flag: hide once, restore once", S,
     "if entry.state is None or (event == \"hide\") != (entry.hidden is None):", "if entry.state is None:"),
    ("summary", "four contract states", S, '"reproduced": "independently verified", "cross_checked"',
     '"reproduced": "evaluated", "cross_checked"'),
    ("charged", "quota charge", S, '"held": False, "evaluating": True,', '"held": False, "evaluating": False,'),
    ("ledger-rejected", "ledger: rejected_constraints", S,
     'return "rejected_constraints" if any(code in GROUPS["geometry"] for code in codes) else "rejected_schema"',
     'return "rejected_schema"'),
    ("idempotency-duplicate", "idempotency: same key and content", S,
     "if prior.logical_key == logical_key and prior.content_sha256 == content_sha256:",
     "if prior.logical_key == logical_key:"),
    ("idempotency-conflict", "idempotency: idempotency_conflict", S, 'codes.append("idempotency_conflict")', "pass"),
    ("idempotency-kind", "idempotency: keys per kind", S,
     "same_kind = [prior for prior in history if prior.kind == kind]", "same_kind = list(history)"),
    ("parent-known", "idempotency: unknown_parent", S, 'codes.append("unknown_parent")', "pass"),
    ("parent-kind", "idempotency: a parent is a proposal's", S,
     'proposals = [prior.geometry_sha256 for prior in history if prior.kind == "proposal"]',
     "proposals = [prior.geometry_sha256 for prior in history]"),
    ("publish-own", "publish: unknown_proposal", S, 'return () if proposal_sha256 in own else ("unknown_proposal",)',
     "return ()"),
    ("publish-kind", "publish: a proposal only", S,
     'own = {prior.content_sha256 for prior in history if prior.kind == "proposal"}',
     "own = {prior.content_sha256 for prior in history}"),
    ("order-history", "order: history in order", S, 'raise OrderError("history is not in submission order")', "pass"),
    ("order-later", "order: decided after every earlier row", S,
     'raise OrderError("a row is decided after every earlier one")', "pass"),
    ("order-offset", "order: numeric time with its offset", S,
     "calendar.timegm((year, month, day, hour, minute, second)) - offset",
     "calendar.timegm((year, month, day, hour, minute, second))"),
    ("order-text", "order: numeric, not text", S, 'return (created_at_ns(row["createdAt"]), row["id"], row["sessionId"])',
     'return (row["createdAt"], row["id"], row["sessionId"])'),
    ("order-room", "order: the room tiebreak", S,
     'return (created_at_ns(row["createdAt"]), row["id"], row["sessionId"])',
     'return (created_at_ns(row["createdAt"]), row["id"])'),
    ("order-dates", "order: impossible times refused", S,
     "    datetime(year, month, day, hour, minute, second)        # refuses impossible dates and times\n", ""),
    ("order-fraction", "order: exact fraction", S, '.ljust(9, "0")', '.rjust(9, "0")'),
    # ── record rules ──
    ("rule-die-index", "manifest.die_index", V,
     '        if die["die"] != index:\n            found.append(_bad("record_inconsistent", f"/dies/{index}", "manifest.die_index"))',
     '        if False:\n            found.append(_bad("record_inconsistent", f"/dies/{index}", "manifest.die_index"))'),
    ("rule-square", "manifest.square_rotation", V,
     'if (sorted(die["rot_deg"]) != [0]) if die["w_um"] == die["h_um"] else (sorted(die["rot_deg"]) != [0, 90]):',
     "if False:"),
    ("rule-real-chiplets", "manifest.real_chiplets", V,
     'if record["statistic"]["real_chiplets"] != [die["unit"] for die in dies]:', "if False:"),
    ("rule-netlist", "manifest.netlist", V, "any(len(row) != count or row[index] != 0 for index, row in enumerate(matrix))",
     "any(len(row) != count for index, row in enumerate(matrix))"),
    ("rule-budgets", "manifest.r_values", V, "if budgets != sorted(budgets) or not all(", "if not all("),
    ("rule-r-decimals", "manifest.r_values", V,
     ' or not all(_decimals_ok(value) for value in budgets + [policy["r"] or 0])', ""),
    ("rule-check-limits", "manifest.check_limits", V,
     'checks["solver_time_limit_s"] < checks["check_wall_s"]', 'checks["solver_time_limit_s"] <= checks["check_wall_s"]'),
    ("rule-quota-windows", "manifest.quota_windows", V, 'or limits["eval_room_day"] < limits["eval_room_hour"])', ")"),
    ("rule-window", "manifest.window", V,
     'if None not in window.values() and not window["opens_at"] < window["closes_at"]:', "if False:"),
    ("rule-scenarios-unique", "manifest.scenarios", V, 'if len(set(ids)) != len(ids) or "nominal" not in ids:',
     'if "nominal" not in ids:'),
    ("rule-scenarios-nominal", "manifest.scenarios", V, 'if len(set(ids)) != len(ids) or "nominal" not in ids:',
     "if len(set(ids)) != len(ids):"),
    ("rule-pins-recipient", "manifest.signed_pins", V, '            "/sealing/recipient": record["sealing"]["recipient"],\n',
     ""),
    ("rule-pins-policy", "manifest.signed_pins", V, 'if not policy["status"].startswith("frozen"):', "if False:"),
    ("rule-pins-template", "manifest.signed_pins", V,
     'if any(scenario["id"] == "position-<die>-<axis>-<sign>" for scenario in record["screen"]["scenarios"]):',
     "if False:"),
    ("rule-pins-admission", "manifest.signed_pins", V, 'if statistic["numerical_admission"] != "admitted":',
     "if False:"),
    ("rule-pins-terms", "manifest.signed_pins", V, 'if not record["terms"]["accepted_versions"]:', "if False:"),
    ("rule-pins-checks", "manifest.signed_pins", V,
     '"cleanup_headroom_s", "cpu_reserve_s",\n                 "cpu_enforcement_evidence_sha256"):',
     '"cleanup_headroom_s",\n                 "cpu_enforcement_evidence_sha256"):'),
    ("rule-pins-cpu-evidence", "manifest.signed_pins: live CPU enforcement evidence", V,
     '"cpu_reserve_s",\n                 "cpu_enforcement_evidence_sha256"):', '"cpu_reserve_s"):'),
    ("rule-terms-hash", "terms.version_hash", V, 'if not record["version"].endswith("@" + record["text_sha256"]):',
     "if False:"),
    ("rule-check-solver", "check.codes", V, 'return len(names) == 1 and unfinished == ["solver_time_limit_s"]',
     "return len(names) == 1"),
    ("rule-check-one-limit", "check.codes", V,
     'return len(names) == 1 and unfinished[0] in ("check_wall_s", "cpu_reserve_s")',
     'return unfinished[0] in ("check_wall_s", "cpu_reserve_s")'),
    ("rule-check-codes", "check.codes", V,
     "    if any(name not in CHECK_CODES for name in names):\n        return False\n", ""),
    ("rule-q-keys", "check.q_r_keys", V, "    if set(q_r) != q_r_keys(manifest):\n", "    if False:\n"),
    ("rule-q-values", "check.q_r_values", V,
     'if value != ("UNKNOWN" if w_c == "UNKNOWN" else hashes.q_r(w_c, w_r, key)):', "if False:"),
    ("rule-q-tolerance", "q_r keys: the tolerance r", V,
     '([policy["r"]] if policy["r"] is not None else [])', "[]"),
    ("rule-state-rejected", "state.codes", V,
     "        return bool(names) and all(name in REJECTION_CODES for name in names)", "        return True"),
    ("rule-state-failed", "state.codes", V, "return len(rest) == 1 and rest[0] in FAILURE_CODES",
     "return len(rest) >= 1"),
    ("rule-state-evaluated", "state.codes", V, "    if state in EVALUATED:\n        return not rest\n",
     "    if state in EVALUATED:\n        return True\n"),
    ("rule-state-cancelled", "state.codes", V, "        return all(name in POLICY_CODES for name in names)",
     "        return True"),
    ("rule-state-quiet", "state.codes", V, "    return not names                                # queued",
     "    return True                                # queued"),
    ("rule-fields-unread", "receipt.proposal_fields", V,
     "bad = [name for name in read + derived if record[name] is not None]", "bad = []"),
    ("rule-fields-read", "receipt.proposal_fields", V, "bad = [name for name in read if record[name] is None]",
     "bad = []"),
    ("rule-fields-rejected", "receipt.proposal_fields", V,
     '        if state != "rejected":\n            bad.append("proposal_sha256")\n', ""),
    ("rule-design-early", "receipt.design_hash", V, 'state in NO_DESIGN and record["design_hash"] is not None', "False"),
    ("rule-design-missing", "receipt.design_hash", V, '\n            or state in EVALUATED and record["design_hash"] is None)',
     ")"),
    ("rule-receipt-manifest", "record.manifest", V,
     '    if manifest is not None and record["manifest_id"] != hashes.manifest_id(manifest):\n'
     '        found.append(_bad("record_inconsistent", "/manifest_id", "record.manifest"))',
     "    if False:\n        found.append(_bad(\"record_inconsistent\", \"/manifest_id\", \"record.manifest\"))"),
    ("rule-ref-proposal", "ref.proposal", V, 'if (record["proposal_sha256"] != hashes.proposal_sha256(item)',
     "if (False"),
    ("rule-ref-geometry", "ref.geometry", V,
     'if record["geometry_sha256"] not in (None, hashes.geometry_sha256(item, manifest)):', "if False:"),
    ("rule-ref-values", "ref.values", V, 'if record["values"] not in (None, hashes.conductor_geometry(item, manifest)):',
     "if False:"),
    ("rule-ref-source", "ref.source", V,
     'if ctx["action_id"] is not None and record["source_ref"] != hashes.source_ref(ctx["action_id"]):', "if False:"),
    ("rule-ref-participant", "ref.participant", V,
     'if ctx["k_challenge"] is not None and ctx["account_id"] is not None and record["participant_ref"] != (',
     'if False and record["participant_ref"] != ('),
    ("rule-status-queue", "status.queue", V, 'if (receipt["queue"] is not None) != (receipt["state"] == "queued"):',
     "if False:"),
    ("rule-ref-run-id", "ref.run_id", V, 'if query and receipt["run_id"] != hashes.run_id(',
     'if False and receipt["run_id"] != hashes.run_id('),
    ("rule-privacy-handle", "privacy.handle", V, "if private_handles and exposes_handle(record, private_handles):",
     "if False:"),
    ("privacy-embedded", "privacy.handle: embedded, not only whole", V,
     "if any(handle in digits for handle in hexes)", "if any(handle == text for handle in hexes)"),
    ("privacy-case", "privacy.handle: any letter case", V, 'digits = NOT_HEX.sub("", text.lower())',
     'digits = NOT_HEX.sub("", text)'),
    ("privacy-separators", "privacy.handle: separators do not hide it", V, 'digits = NOT_HEX.sub("", text.lower())',
     "digits = text.lower()"),
    ("privacy-base64", "privacy.handle: base64 and base64url", V, " or any(form in text for form in encoded)", ""),
    ("privacy-keys", "privacy.handle: keys too", V, "            yield key\n", ""),
    ("rule-results-comparator", "results.comparator", V,
     'if (comparator["id"], comparator["T_R"], comparator["W_R_mm"]) != (',
     'if False and (comparator["id"], comparator["T_R"], comparator["W_R_mm"]) != ('),
    ("rule-delta-t", "results.delta_t", V, 'if row["delta_T"] != _exact_difference(row["T_M"], t_r):', "if False:"),
    ("rule-delta-exact", "results.delta_t: exact decimal", V,
     'else float(Decimal(repr(a)) - Decimal(repr(b)))', "else a - b"),
    ("rule-label-order", "results.label_set", V,
     'if positions != sorted(set(positions)) or set(ids) & {item["id"] for item in row["suppressed"]}:',
     'if set(ids) & {item["id"] for item in row["suppressed"]}:'),
    ("rule-label-suppressed", "results.label_set", V,
     'if positions != sorted(set(positions)) or set(ids) & {item["id"] for item in row["suppressed"]}:',
     "if positions != sorted(set(positions)):"),
    ("rule-label-r-carried", "results.label_r", V,
     'if relaxed != (item["r"] is not None) or relaxed and manifest is not None and item["r"] != policy_r:',
     'if relaxed and manifest is not None and item["r"] != policy_r:'),
    ("rule-label-r-value", "results.label_r", V,
     'if relaxed != (item["r"] is not None) or relaxed and manifest is not None and item["r"] != policy_r:',
     'if relaxed != (item["r"] is not None):'),
    ("rule-unknown-claim", "results.unknown_claim", V, '        if "UNKNOWN" in needs:\n', "        if False:\n"),
    ("rule-bounded", "results.bounded", V, 'and any(label["mode"] == "bounded" for label in row["labels"])',
     "and False"),
    ("rule-withdrawn-claim", "label.withdrawn_claim", V, 'if claimed and row["temperature_label"] == "withdrawn":',
     "if False:"),
    ("rule-label-temperature", "label.temperature", V,
     'return value == "UNKNOWN" and label is None or value != "UNKNOWN" and label == label_for(evaluator, lists)',
     "return True"),
    ("rule-results-state", "results.state", V,
     'if row["kind"] == "outside" and row["state"] not in EVALUATED and (row["T_M"] != "UNKNOWN" or row["labels"]):',
     "if False:"),
    ("rule-results-q", "results.q_r", V,
     '        found += _q_r_rules(row["q_r"], row["W_c_mm"], manifest, path + "/q_r", "results.q_r")\n',
     "        pass\n"),
    # ── labels: the SLAB-053 mirror ──
    ("label-case", "label: the withdrawn key ignores case", L, '.split(":")[:2]).lower()', '.split(":")[:2])'),
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
    # ── claim predicates (T13) ──
    ("pred-exact", "predicates: exact decimals", P, '"q0": exact(w_c) - exact(w_r) if wire else None,',
     '"q0": w_c - w_r if wire else None,'),
    ("pred-target", "predicates: declared temperature target", P, 'lambda x, p: x["t"] <= p["T_limit_C"]',
     'lambda x, p: x["t"] < p["T_limit_C"]'),
    ("pred-strict", "predicates: strict-wire tolerance", P,
     '(("q0", "d"), ("D_K",), lambda x, p: x["q0"] <= 0 and x["d"] <= p["D_K"])',
     '(("q0", "d"), ("D_K",), lambda x, p: x["q0"] < 0 and x["d"] <= p["D_K"])'),
    ("pred-relaxed", "predicates: r-relaxed tolerance", P, 'lambda x, p: x["qr"] <= 0 and x["d"] <= p["D_K"]',
     'lambda x, p: x["q0"] <= 0 and x["d"] <= p["D_K"]'),
    ("pred-thermal", "predicates: strict thermal improvement", P, 'x["d"] <= -p["B_T_K"]', 'x["d"] < -p["B_T_K"]'),
    ("pred-wire", "predicates: strict wire improvement", P,
     'lambda x, p: x["q0"] <= -p["B_W_mm"] and x["d"] <= 0)', 'lambda x, p: x["q0"] < -p["B_W_mm"] and x["d"] <= 0)'),
    ("pred-trade", "predicates: wire improvement with thermal degradation", P,
     'x["q0"] <= -p["B_W_mm"] and x["d"] <= p["D_K"]', 'x["q0"] <= -p["B_W_mm"] and x["d"] <= 0'),
    ("pred-dominance", "predicates: robust dominance needs a strict gain", P, '(x["q0"] < 0 or x["d"] < 0)', "True"),
    ("pred-mesh-wire", "predicates: the mesh case keeps the nominal wire", P,
     'runs["nominal" if s.get("grid") == MESH_GRID else s["id"]]', 'runs[s["id"]]'),
    ("pred-target-scope", "predicates: R-only cases do not evaluate c", P,
     'scope = [x for s, x in cases if label != TARGET or s["applies_to"] != "R"]', "scope = [x for s, x in cases]"),
    ("pred-incomplete", "predicates: a missing case is INCOMPLETE", P,
     'else INCOMPLETE if statuses != {"observed"} else None)', "else None)"),
    ("pred-inconclusive", "predicates: a failed case is INCONCLUSIVE", P, 'INCONCLUSIVE if "failed" in statuses',
     'INCOMPLETE if "failed" in statuses'),
    ("pred-admission", "predicates: no admission is UNKNOWN", P, "common = (UNKNOWN if not admission else ",
     "common = ("),
    ("pred-nominal", "predicates: no pass on an empty screen", P, '    if "nominal" not in runs:', "    if False:"),
    ("suppress-gate", "suppression: failed gate zero", P, '"failed gate zero": lambda failure, label: True,',
     '"failed gate zero": lambda failure, label: False,'),
    ("suppress-fixture", "suppression: a fixture naming no label", P,
     'failure.get("label") in (None, label["id"])', 'failure.get("label") == label["id"]'),
    ("suppress-unknown", "suppression: a diagnostic is no reason", P, "    if unknown:\n        raise ValueError",
     "    if False:\n        raise ValueError"),
    ("diagnostic-visible", "diagnostics: claims stay visible", P,
     'return labels, {"hypothesis": hypothesis, "observed": observed, "matched": matched}',
     'return [], {"hypothesis": hypothesis, "observed": observed, "matched": matched}'),
    ("diagnostic-empty", "diagnostics: an empty hypothesis matches nothing", P, "matched = bool(hypothesis) and all(",
     "matched = all("),
    # ── age v1 (T15) ──
    ("age-mac", "age: the header MAC", A, "        verifier.verify(mac)\n", "        pass\n"),
    ("age-final", "age: the final chunk flag", A, "bytes((1 if final else 0,))", "bytes((0,))"),
    ("age-armour", "age: canonical armour", A, "if not data or armor(data) !=", "if not data or False and armor(data) !="),
    ("age-key-version", "age: six-digit key versions", A, "([1-9][0-9]{0,5})", "([1-9][0-9]*)"),
    # ── schema-level rules ──
    ("schema-dies", "limit: 32 dies", SCH + "common.schema.json", '"minItems": 1,\n      "maxItems": 32,',
     '"minItems": 1,\n      "maxItems": 33,'),
    ("schema-coordinate", "limit: coordinate range", SCH + "common.schema.json",
     '"x_um": {"type": "integer", "minimum": 0, "maximum": 1000000},',
     '"x_um": {"type": "integer", "minimum": 0, "maximum": 2000000},'),
    ("schema-salt", "proposal: a 32-hex salt", SCH + "common.schema.json", '"pattern": "^[0-9a-f]{32}$"}',
     '"pattern": "^[0-9a-f]{32,64}$"}'),
    ("schema-key", "proposal: a 64-character key", SCH + "common.schema.json",
     '"type": "string", "pattern": "^[a-z0-9][a-z0-9_-]{0,63}$"},\n    "key_or_null"',
     '"type": "string", "pattern": "^[a-z0-9][a-z0-9_-]{0,127}$"},\n    "key_or_null"'),
    ("schema-visibility", "proposal: public or private", SCH + "common.schema.json", '"enum": ["public", "private"]},',
     '"enum": ["public", "private", "unlisted"]},'),
    ("schema-client", "proposal: a short client token", SCH + "proposal.schema.json",
     '"name": {"type": "string", "pattern": "^[A-Za-z0-9._-]{1,32}$"},',
     '"name": {"type": "string", "pattern": "^[A-Za-z0-9._-]{1,64}$"},'),
    ("schema-team", "team: the name pattern", SCH + "team.schema.json", "[A-Za-z0-9 ._-]{0,31}$", "[A-Za-z0-9 ._-]{0,32}$"),
    ("schema-check-labels", "check: four fixed labels", SCH + "check.schema.json",
     '"labels": {"const": ["routed wire only", "no thermal solve", "nominal", "not a score"]},',
     '"labels": {"const": ["routed wire only", "nominal", "not a score"]},'),
    ("schema-training", "terms: no training grant", SCH + "terms.schema.json", '"training": {"const": false},',
     '"training": {"type": "boolean"},'),
    ("schema-cpu-live", "checks: live CPU enforcement required", SCH + "manifest.schema.json",
     '"const": "live process-tree CPU, enforced while running"},', '"type": "string"},'),
    ("schema-sealed-publish", "sealing: publish commands are sealed", SCH + "manifest.schema.json",
     '"applies_to": {"const": ["private proposals", "private routed checks", "publish commands"]},',
     '"applies_to": {"const": ["private proposals", "private routed checks"]},'),
    ("schema-fallback", "sealing: no plaintext fallback", SCH + "manifest.schema.json",
     '"plaintext_fallback": {"const": false},', '"plaintext_fallback": {"type": "boolean"},'),
    ("schema-bounds", "bounds: never zero", SCH + "manifest.schema.json",
     '"u_T": {"$ref": "common.schema.json#/$defs/unknown"},',
     '"u_T": {"$ref": "common.schema.json#/$defs/number_or_unknown"},'),
    ("schema-threads", "manifest: threads outside the hash", SCH + "manifest.schema.json",
     '"threads": {"type": "null"}', '"threads": {"type": ["null", "array"]}'),
    ("schema-receipt-label", "receipt: no label names a participant", SCH + "receipt.schema.json",
     '"schema": {"const": "sentilab-open-receipt/1"},',
     '"schema": {"const": "sentilab-open-receipt/1"},\n    "label": {"type": "string", "pattern": "^[A-Za-z0-9 ]{1,32}$"},'),
    ("schema-private-count", "results: private entries counted", SCH + "results.schema.json",
     '"required": ["schema", "comparator", "rows", "private_entries"],', '"required": ["schema", "comparator", "rows"],'),
]


def run_suite(root: Path) -> list:
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    result = subprocess.run([sys.executable, "-c", RUNNER, json.dumps(sorted(FORM_TESTS)), json.dumps(SUITES)],
                            cwd=root, env=env, capture_output=True, text=True, check=False)
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


def lands(path: str, old: str) -> int:
    return (ROOT / path).read_bytes().decode("utf-8").count(old)


def main(argv) -> int:
    ids = [mutant[0] for mutant in MUTANTS]
    if len(set(ids)) != len(ids):
        print("duplicate mutant ids")
        return 1
    if "--land" in argv:
        bad = [(mutant_id, lands(path, old)) for mutant_id, _rule, path, old, _new in MUTANTS if lands(path, old) != 1]
        print(f"{len(MUTANTS)} mutants, {len(bad)} would not land: {bad}")
        return 1 if bad else 0
    baseline_root = fresh_copy()
    try:
        baseline = run_suite(baseline_root)
    finally:
        shutil.rmtree(baseline_root, ignore_errors=True)
    if baseline:
        print("baseline fails:", baseline)
        return 1
    results = {"caught": [], "survived": [], "not_landed": [], "broken": []}
    only = {name for arg in argv if arg.startswith("--only=") for name in arg[len("--only="):].split(",")}
    for mutant_id, rule, path, old, new in MUTANTS:
        if only and mutant_id not in only:
            continue
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
            if any(name.startswith("<runner crashed>") for name in failing):
                results["broken"].append(mutant_id)
                print(f"BROKEN    {mutant_id}: the suite did not run: {failing[0][:160]}", flush=True)
                continue
            outcome = "caught" if failing else "survived"
            results[outcome].append(mutant_id)
            print(f"{outcome.upper():9} {mutant_id:26} {rule:48} {', '.join(failing)[:120]}", flush=True)
        finally:
            shutil.rmtree(root, ignore_errors=True)
    print(f"\n{sum(len(names) for names in results.values())} mutants: {len(results['caught'])} caught, {len(results['survived'])} survived, "
          f"{len(results['not_landed'])} did not land, {len(results['broken'])} broken")
    return 0 if not (results["survived"] or results["not_landed"] or results["broken"]) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
