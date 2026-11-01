"""Mutation check for the agent door: each mutant injects one real hazard into a fresh temporary copy of the repo; the
door's tests must fail. The working tree is never touched.

    python -m scripts.door_mutants              # every mutant; exit 1 if any survives, fails to land or breaks
    python -m scripts.door_mutants --land       # only check that every mutant's snippets occur exactly once
    python -m scripts.door_mutants --only=a,b   # just these (a spot check, not the result)
    python -m scripts.door_mutants --jobs=3     # copies tested at once

It lives in scripts/, outside the shipped trees, like the contract's own open_proposals/contract/mutants.py: it launches
the door's test suites in temporary copies, which is a development tool's process launch, not the service's.

A mutant must land (each of its snippets occurs exactly once and the file changes), or it is reported as an error,
never as a survivor; a mutant that stops the suites from importing is broken, never a kill. A mutant's snippet and
replacement are strings, or tuples of strings applied in order when one hazard needs more than one edit.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP = {".git", "deck", "sundai_thermal", "__pycache__", "node_modules"}
SUITES = ("app.test_door_intake", "app.test_door_dispatch", "app.test_door_feeds")
RUNNER = """
import json, sys, unittest
def flat(suite):
    for test in suite:
        yield from (flat(test) if isinstance(test, unittest.TestSuite) else [test])
loader = unittest.defaultTestLoader
tests = [t for name in json.loads(sys.argv[1]) for t in flat(loader.loadTestsFromName(name))]
errors = [t for t in tests if type(t).__name__ == "_FailedTest"]
if errors:
    print(json.dumps(["<runner crashed>: " + errors[0].id()]))
    raise SystemExit(0)
result = unittest.TextTestRunner(stream=open(__import__("os").devnull, "w"), verbosity=0).run(unittest.TestSuite(tests))
print(json.dumps(sorted({t.id().rsplit(".", 1)[-1] for t, _ in result.failures + result.errors})))
"""
D = "app/door/"
IN, L, P, S, SV, DP = (D + "intake.py", D + "legality.py", D + "policy.py", D + "store.py", D + "service.py",
                       D + "dispatch.py")
SC = D + "scorer.py"

# (id, hazard, file, snippet, replacement)
MUTANTS = [
    # ── the legality gate ──
    ("gate-no-checker", "legality: validate_local runs without the pinned adapter", IN,
     "manifest_id=policy.manifest_id,\n                             layout_checker=policy.checker)",
     "manifest_id=policy.manifest_id,\n                             layout_checker=None)"),
    ("gate-accepts-unchecked", "legality: contract_valid (no layout check) passes", IN,
     'if outcome.outcome == "legal":', 'if outcome.outcome in ("legal", "contract_valid"):'),
    ("adapter-silent", "legality: the adapter drops what TapGeometry finds", L,
     "            found.append(violation(miss.rule, dies=sorted(set(miss.dies)), "
     "amount_um=amount_um(miss.amount_mm)))",
     "            pass"),
    ("adapter-amount-floor", "legality: amounts rounded down to zero", L,
     "return min(1_000_000, max(1, math.ceil(round(mm * 1000, 6))))", "return min(1_000_000, max(1, int(mm * 1000)))"),
    ("pin-config-ignored", "legality: the fixture's config hash is not pinned", L,
     'problem.config_sha256 == manifest["fixture"]["config_sha256"],', "True,"),
    ("pin-gap-ignored", "legality: the minimum die gap is not pinned", L,
     '_whole_um(legality.min_die_gap_mm) == rules["min_die_gap_um"],', "True,"),
    ("compact-rotation-dropped", "mapping: r is ignored", IN, '"rot_deg": 90 * r}', '"rot_deg": 0}'),
    ("compact-trailing", "mapping: trailing characters accepted", IN,
     r'COMPACT_ITEM = re.compile(r"(0|[1-9][0-9]{0,2})\.(0|[1-9][0-9]{0,2})\.([0-9])\Z")',
     r'COMPACT_ITEM = re.compile(r"(0|[1-9][0-9]{0,2})\.(0|[1-9][0-9]{0,2})\.([0-9])")'),
    ("compact-step", "mapping: the 500 um step", IN, '"x_um": x * 500,', '"x_um": x * 1000,'),
    ("launch-unchecked", "dispatch: no revalidation at launch", SV,
     "    def launch_check(self, run):\n", "    def launch_check(self, run):\n        return None\n"),
    # ── quotas and CPU ──
    ("quota-off-by-one", "quota: a window's cap admits one more", S, "            if count >= cap:",
     "            if count > cap:"),
    ("queue-unbounded", "quota: the queue cap is ignored", S, 'if queued >= limits["queue_max"]:', "if False:"),
    ("cpu-held-ignored", "cpu: held envelopes are not counted", S,
     "THEN amount_cpu_s \"\n               \"WHEN state = 'settled'",
     "THEN 0 \"\n               \"WHEN state = 'settled'"),
    ("cpu-token-ignored", "cpu: the token's budget is ignored", S,
     "if self._cpu_used(db, grant.grant, principal) + envelope > grant.token_cpu_s + EPSILON:", "if False:"),
    ("cpu-grant-ignored", "cpu: the grant's cap is ignored", S,
     "if self._cpu_used(db, grant.grant) + envelope > grant.cpu_cap_s + EPSILON:", "if False:"),
    ("cpu-decided-before-lock", "cpu: quotas read before the write lock, then written (check-then-act)", S,
     ("        with self.tx() as db:\n            bound = db.execute(",
      "            found = self._quota(db, policy=policy, principal=proposal.principal, token_exp=token_exp, now=now)"),
     ("        snapshot = self._connect()\n        stale = self._quota(snapshot, policy=policy, "
      "principal=proposal.principal, token_exp=token_exp, now=now)\n        snapshot.close()\n"
      "        with self.tx() as db:\n            bound = db.execute(",
      "            found = stale")),
    ("cpu-not-atomic", "cpu: decision and write outside one write-locked transaction", S,
     '        with self._lock:\n            db = self._connect()\n            try:\n'
     '                db.execute("BEGIN IMMEDIATE")',
     '        if True:\n            db = self._connect()\n            try:\n                db.execute("BEGIN")'),
    ("failure-free", "cpu: an ambiguous failure is not charged", DP,
     'charged, usage = max(envelope, reported or 0.0), "unknown_charged_envelope"',
     'charged, usage = 0.0, "unknown_charged_envelope"'),
    ("overrun-capped", "cpu: an overrun is charged only the envelope", DP,
     '"charged_cpu_s": score.cpu_s, "usage"', '"charged_cpu_s": min(score.cpu_s, envelope), "usage"'),
    ("interrupted-free", "cpu: an interrupted attempt is not charged", S,
     "UPDATE reservations SET state = 'settled', charged_cpu_s = amount_cpu_s, ",
     "UPDATE reservations SET state = 'settled', charged_cpu_s = 0, "),
    ("parallel-ignored", "dispatch: more attempts than the grant's parallel", S, "            if active >= parallel:",
     "            if False:"),
    ("rate-nonce-ignored", "flood: the per-nonce request limit is ignored", S,
     "if mine[0] >= flood.nonce_per_min:", "if False:"),
    # ── scope, admission and the principal ──
    ("scope-purpose", "scope: the purpose is not checked", IN,
     'if claims["purpose"] != PURPOSE or claims["case"] != CASE:', 'if claims["case"] != CASE:'),
    ("scope-case", "scope: the case is not checked", IN,
     'if claims["purpose"] != PURPOSE or claims["case"] != CASE:', 'if claims["purpose"] != PURPOSE:'),
    ("scope-expiry-edge", "scope: a token is accepted at its expiry", IN, 'if not now < claims["exp"]:',
     'if not now <= claims["exp"]:'),
    ("scope-ttl", "scope: a token outliving its lifetime is accepted", IN,
     'if claims["exp"] > now + TOKEN_TTL_S + TOKEN_SKEW_S:', "if False:"),
    ("admission-switch", "admission: the operator switch is ignored", P,
     'switch = self.admission_switch if self.admission_switch in ("open", "closed") else "not_open_yet"',
     'switch = "open"'),
    ("admission-window", "admission: the window's end is ignored", P, "        if now >= closes:",
     "        if False:"),
    ("binding-unsigned", "admission: the binding's signature is not verified", P,
     "        body = gate0_anchor.verify(public_key_hex, signed)",
     "        body = {k: v for k, v in signed.items() if k != 'signature'} if isinstance(signed, dict) else {}"),
    ("binding-other-manifest", "admission: a binding for another manifest opens this one", P,
     '            if body["manifest_id"] != self.manifest_id:', "            if False:"),
    ("status-unbound", "principal: status readable by another token", SV,
     'if row is None or row["principal"] != principal:', "if row is None:"),
    ("key-reuse-changed", "idempotency: a changed body under a used key returns the old run", S,
     'if bound["proposal_sha256"] == proposal.proposal_sha256:', "if True:"),
    # ── the frozen metric ──
    ("guard-not-strict", "metric: the active guard admits 119.07", SV, "and row[\"active_c\"] < ACTIVE_GUARD_C)",
     "and row[\"active_c\"] <= ACTIVE_GUARD_C)"),
    ("binding-unchecked", "metric: a score that disagrees with its parts stands unqualified", DP,
     '    checks["ok"] = all(value for name, value in checks.items() if name.endswith("_ok"))',
     '    checks["ok"] = True'),
    ("binding-grid-ignored", "metric: a returned grid is not checked against the per-die values", DP,
     "                               and all(abs(mean - score.per_die_C[name]) <= BINDING_TOLERANCE_K",
     "                               and all(True or abs(mean - score.per_die_C[name]) <= BINDING_TOLERANCE_K"),
    # ── the scorer seam (door-scorer, PR #79) ──
    ("token-ref-unkeyed", "scorer: token_ref is the bare nonce hash, not the keyed participant_ref", DP,
     '"token_ref": door.policy.participant_ref(claimed["principal"]),', '"token_ref": claimed["principal"][-64:],'),
    ("refusal-charged", "scorer: a refusal before any solve is charged the envelope", SC,
     'raise ScorerError("scorer_refused", began=False)', 'raise ScorerError("scorer_refused", began=True)'),
    ("replay-error-reproduced", "scorer: a replay that could not complete counts as reproduced", SC,
     'reproduced, code, replay_receipt = False, "reproduction_failed", None',
     'reproduced, code, replay_receipt = True, None, {}'),
    ("health-binary-ignored", "scorer: health accepts another binary", SC,
     'and payload.get("binary_sha256") == self._binary', ""),
    ("replay-unchecked", "metric: a failed replay counts as reproduced", DP,
     "reproduced = score.replay_fresh_process and score.replay_match", "reproduced = True"),
]


def pairs(old, new) -> list:
    return list(zip(old, new)) if isinstance(old, tuple) else [(old, new)]


def lands(path: str, old, new) -> bool:
    text = (ROOT / path).read_bytes().decode("utf-8")
    return all(text.count(snippet) == 1 for snippet, _ in pairs(old, new))


def fresh_copy() -> Path:
    root = Path(tempfile.mkdtemp(prefix="door-mutant-"))
    for item in ROOT.iterdir():
        if item.name in SKIP:
            continue
        target = root / item.name
        if item.is_dir():
            shutil.copytree(item, target, ignore=shutil.ignore_patterns(*SKIP))
        else:
            shutil.copy2(item, target)
    return root


def run_suite(root: Path) -> list:
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    result = subprocess.run([sys.executable, "-c", RUNNER, json.dumps(SUITES)], cwd=root, env=env,
                            capture_output=True, text=True, check=False, timeout=900)
    lines = result.stdout.strip().splitlines()
    if not lines:
        return ["<runner crashed>: " + result.stderr[-300:]]
    return json.loads(lines[-1])


def one(mutant) -> tuple:
    mutant_id, rule, path, old, new = mutant
    root = fresh_copy()
    try:
        target = root / path
        text = original = target.read_bytes().decode("utf-8")
        for snippet, replacement in pairs(old, new):
            if text.count(snippet) != 1:
                return mutant_id, rule, "not_landed", [f"snippet occurs {text.count(snippet)} times"]
            text = text.replace(snippet, replacement)
        target.write_bytes(text.encode("utf-8"))
        if target.read_bytes().decode("utf-8") == original:
            return mutant_id, rule, "not_landed", ["file unchanged"]
        failing = run_suite(root)
        if any(name.startswith("<runner crashed>") for name in failing):
            return mutant_id, rule, "broken", failing
        return mutant_id, rule, "caught" if failing else "survived", failing
    finally:
        shutil.rmtree(root, ignore_errors=True)


def main(argv) -> int:
    ids = [mutant[0] for mutant in MUTANTS]
    if len(set(ids)) != len(ids):
        print("duplicate mutant ids")
        return 1
    if "--land" in argv:
        bad = [mutant_id for mutant_id, _rule, path, old, new in MUTANTS if not lands(path, old, new)]
        print(f"{len(MUTANTS)} mutants, {len(bad)} would not land: {bad}")
        return 1 if bad else 0
    jobs = next((int(arg[len("--jobs="):]) for arg in argv if arg.startswith("--jobs=")), 1)
    only = {name for arg in argv if arg.startswith("--only=") for name in arg[len("--only="):].split(",")}
    baseline_root = fresh_copy()
    try:
        baseline = run_suite(baseline_root)
    finally:
        shutil.rmtree(baseline_root, ignore_errors=True)
    if baseline:
        print("baseline fails:", baseline)
        return 1
    chosen = [mutant for mutant in MUTANTS if not only or mutant[0] in only]
    results = {"caught": [], "survived": [], "not_landed": [], "broken": []}
    with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        for mutant_id, rule, outcome, failing in pool.map(one, chosen):
            results[outcome].append(mutant_id)
            print(f"{outcome.upper():10} {mutant_id:24} {rule:62} {', '.join(failing)[:110]}", flush=True)
    print(f"\n{sum(len(names) for names in results.values())} mutants: {len(results['caught'])} caught, "
          f"{len(results['survived'])} survived, {len(results['not_landed'])} did not land, "
          f"{len(results['broken'])} broken")
    return 0 if not (results["survived"] or results["not_landed"] or results["broken"]) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
