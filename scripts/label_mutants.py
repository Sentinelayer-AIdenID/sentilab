"""Mutation check for the reproduction-tested build label: each mutant breaks the identity match (or lets the label
clear a result's qualifiers) in one of its three places, in a fresh temporary copy of the repo; the label tests must
fail. The working tree is never touched.

    python -m scripts.label_mutants              # every mutant; exit 1 if any survives, fails to land or breaks
    python -m scripts.label_mutants --land       # only check that every mutant's snippets occur exactly once
    python -m scripts.label_mutants --only=a,b   # just these (a spot check, not the result)
    python -m scripts.label_mutants --jobs=3     # copies tested at once

The three places and their tests, all run for every mutant:
  contract   open_proposals/contract labels.py, builds.py, labels.json: test_rules and test_golden (less the two tests
             that pin bytes, which fail on any change, so a kill must come from a test of the hazard)
  API        app/door evaluator.py, service.py, dispatch.py, policy.py: app.test_door_build_label, app.test_door_feeds
  pages      web/public/temperature-label.mjs: node --test web/test/temperature-label.test.mjs and
             web/test/door-build-label.test.mjs (the API's own results body through the page rule)
It reuses scripts/door_mutants.py's copy and landing rules: a mutant must land (each snippet occurs exactly once and
the file changes), or it is an error, never a survivor; a mutant that stops a suite from running is broken.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from scripts.door_mutants import fresh_copy, lands, pairs

FORM_TESTS = ("test_every_contract_file_is_pinned", "test_the_files_match_their_generator")
PY_SUITES = ("open_proposals.contract.test_rules", "open_proposals.contract.test_golden", "app.test_door_build_label",
             "app.test_door_feeds")
WEB_TESTS = ("web/test/temperature-label.test.mjs", "web/test/door-build-label.test.mjs")
RUNNER = """
import json, sys, unittest
form = set(json.loads(sys.argv[1]))
def flat(suite):
    for test in suite:
        yield from (flat(test) if isinstance(test, unittest.TestSuite) else [test])
loader = unittest.defaultTestLoader
tests = [t for name in json.loads(sys.argv[2]) for t in flat(loader.loadTestsFromName(name))
         if getattr(t, "_testMethodName", "") not in form]
errors = [t for t in tests if type(t).__name__ == "_FailedTest"]
if errors:
    print(json.dumps(["<runner crashed>: " + errors[0].id()]))
    raise SystemExit(0)
result = unittest.TextTestRunner(stream=open(__import__("os").devnull, "w"), verbosity=0).run(unittest.TestSuite(tests))
print(json.dumps(sorted({t.id().rsplit(".", 1)[-1] for t, _ in result.failures + result.errors})))
"""
LB, BU, LJ = "open_proposals/contract/labels.py", "open_proposals/contract/builds.py", "contracts/open-proposal-v1/labels.json"
EV, SV, PO = "app/door/evaluator.py", "app/door/service.py", "app/door/policy.py"
TL = "web/public/temperature-label.mjs"
ALIAS = "hotspot6:751b357f6b5af395a4447d6e3bfeef3a75eb447091798365a3db4f0e00618cc6:grid:64x64"
PY_MATCH = '    if identity in lists["reproduction_tested"]:\n        return "reproduction_tested"\n'
JS_MATCH = "    if (reproducedIds.has(identity)) return LABELS.reproduction_tested;"
JS_ALL = "    if (labels.length > 0 && labels.every((label) => label === LABELS.reproduction_tested)) return LABELS.reproduction_tested;"

# (id, hazard, file, snippet, replacement)
MUTANTS = [
    # ── the contract: labels.py, builds.py, labels.json ──
    ("py-prefix", "contract: the build matched by a prefix (engine and commit)", LB,
     'if identity in lists["reproduction_tested"]:',
     'if any(identity.startswith(item[:52]) for item in lists["reproduction_tested"]):'),
    ("py-casefold", "contract: the build matched without case or padding", LB,
     'if identity in lists["reproduction_tested"]:',
     'if identity.strip().lower() in {item.lower() for item in lists["reproduction_tested"]}:'),
    ("py-derived-any", "contract: a derived value is reproduction-tested if any input is", LB,
     'if labels and all(label == "reproduction_tested" for label in labels):', 'if "reproduction_tested" in labels:'),
    ("py-derived-empty", "contract: a value derived from nothing is reproduction-tested", LB,
     'if labels and all(label == "reproduction_tested" for label in labels):',
     'if all(label == "reproduction_tested" for label in labels):'),
    ("py-before-withdrawn", "contract: the list is read before the withdrawn engine:commit", LB,
     (PY_MATCH, '    if evaluator_key(identity) in'),
     ("", PY_MATCH + '    if evaluator_key(identity) in')),
    ("py-list-alias", "contract: the broad alias is on the list", LJ,
     '"reproduction_tested": ["', f'"reproduction_tested": ["{ALIAS}", "'),
    ("py-seal-drops-image", "contract: the seal does not cover the image", BU,
     ":build_sha256:{digest(identity)}", ":build_sha256:{digest({k: v for k, v in identity.items() if k != 'image'})}"),
    ("py-seal-drops-mapping", "contract: the seal does not cover the centre mapping", BU,
     ":build_sha256:{digest(identity)}",
     ":build_sha256:{digest({k: v for k, v in identity.items() if k != 'centre_mapping'})}"),
    ("py-token-loose", "contract: an unreadable field is written into the string as it is", BU,
     '    return text if isinstance(text, str) and TOKEN.fullmatch(text) else "unknown"',
     '    return str(text)'),
    ("py-config-not-shared", "contract: the build's config is one reference's whole input set", BU,
     "for name, value in sorted(first.items()) if second.get(name) == value}",
     "for name, value in sorted(first.items())}"),
    ("py-evidence-unchecked", "contract: builds.json is not checked against the evidence record", BU,
     "            found += _against_evidence(build, evidence)\n", "            pass\n"),
    ("py-delta-unchecked", "contract: a reference outside the tolerance passes", BU,
     'if abs(delta) > tolerance or round(delta, 2) != reference["delta_K"]:', "if False:"),
    ("py-digest-unchecked", "contract: the registry takes a malformed image digest", BU,
     "    return value is None or (isinstance(value, str) and IMAGE_DIGEST.fullmatch(value) is not None)\n",
     "    return True\n"),
    ("py-digest-optional", "contract: a build without an image digest reads as recording null", BU,
     '    if "image_digest" not in build:\n        return False\n    value = build["image_digest"]\n',
     '    value = build.get("image_digest")\n'),
    ("py-id-twice", "contract: one id registered twice, with two digests", BU,
     '    if len(set(ids)) != len(ids):\n        raise ValueError("a build is registered once")\n', ""),
    # ── the API: app/door ──
    ("api-image-assumed", "API: the image is the build's, whatever digest the run carries", EV,
     '"image": build["identity"]["image"] if image_attested(build, receipt, grant) else None,',
     '"image": build["identity"]["image"],'),
    ("api-tag-attests", "API: the binding's image tag attests the image (warden's P1 on #85)", EV,
     '"image": build["identity"]["image"] if image_attested(build, receipt, grant) else None,',
     '"image": getattr(grant, "scorer_image_tag", None),'),
    ("api-tag-or-digest", "API: a tag naming the build stands in for the digest", EV,
     "if image_attested(build, receipt, grant) else None,",
     'if image_attested(build, receipt, grant) or getattr(grant, "scorer_image_tag", None) == '
     'build["identity"]["image"] else None,'),
    ("api-null-equals-null", "API: a null recorded digest matches a run that carries none either", EV,
     "    if not isinstance(recorded, str) or not IMAGE.match(recorded):",
     "    if recorded is not None and (not isinstance(recorded, str) or not IMAGE.match(recorded)):"),
    ("api-digest-malformed", "API: a malformed recorded digest matches the same malformed run digest", EV,
     "    if not isinstance(recorded, str) or not IMAGE.match(recorded):", "    if not isinstance(recorded, str):"),
    ("api-receipt-unchecked", "API: the receipt's image digest is not compared", EV,
     'return receipt.get("image_digest") == recorded and getattr(grant, "scorer_image_digest", None) == recorded',
     'return getattr(grant, "scorer_image_digest", None) == recorded'),
    ("api-grant-unchecked", "API: the grant's image digest is not compared", EV,
     'return receipt.get("image_digest") == recorded and getattr(grant, "scorer_image_digest", None) == recorded',
     'return receipt.get("image_digest") == recorded'),
    ("api-agreement-only", "API: receipt and grant agree, but not with the recorded digest", EV,
     'return receipt.get("image_digest") == recorded and getattr(grant, "scorer_image_digest", None) == recorded',
     'return receipt.get("image_digest") == getattr(grant, "scorer_image_digest", None) is not None'),
    ("api-grant-takes-a-tag", "API: a signed grant may carry fields beyond its own (an image tag again)", PO,
     "if not isinstance(value, dict) or set(value) != set(cls.FIELDS):",
     "if not isinstance(value, dict) or not set(cls.FIELDS) <= set(value):"),
    ("api-config-assumed", "API: the config is the build's, whatever the receipt staged", EV,
     '"config_sha256": {name: inputs.get(name) for name in build["identity"]["config_sha256"]},',
     '"config_sha256": build["identity"]["config_sha256"],'),
    ("api-config-one-file", "API: only the HotSpot config is compared, not the package layers", EV,
     '"config_sha256": {name: inputs.get(name) for name in build["identity"]["config_sha256"]},',
     '"config_sha256": {name: inputs.get(name) if name == "new_hotspot.config" else value '
     'for name, value in build["identity"]["config_sha256"].items()},'),
    ("api-binary-assumed", "API: the binary is the build's, whatever the receipt names", EV,
     '"binary_sha256": receipt.get("binary_sha256"),', '"binary_sha256": build["identity"]["binary_sha256"],'),
    ("api-commit-assumed", "API: the engine commit is the build's, whatever the manifest pins", EV,
     '"engine_commit": evaluator.get("upstream"),', '"engine_commit": build["identity"]["engine_commit"],'),
    ("api-engine-assumed", "API: the engine is the build's, whatever the manifest names", EV,
     '"engine": ENGINES.get(evaluator.get("kind")),', '"engine": build["identity"]["engine"],'),
    ("api-grid-assumed", "API: the grid is the build's, whatever the manifest pins", EV,
     '"grid": statistic.get("grid"),', '"grid": build["identity"]["grid"],'),
    ("api-mapping-assumed", "API: the centre mapping is the build's, whatever the manifest pins", EV,
     '"centre_mapping": statistic.get("centre_mapping")}', '"centre_mapping": build["identity"]["centre_mapping"]}'),
    ("api-always-build", "API: every result names the build", EV,
     "    return builds.build_id(attested(known[0], receipt, manifest, grant))", '    return known[0]["id"]'),
    ("api-mismatch-alias", "API: a mismatched run names the constant alias, not what it attests", EV,
     "    return builds.build_id(attested(known[0], receipt, manifest, grant))", "    return ALIAS"),
    ("api-seal-ignored", "API: a run matching the readable fields counts, whatever the seal says", EV,
     '        if builds.build_id(attested(build, receipt, manifest, grant)) == build["id"]:',
     '        if builds.build_id(attested(build, receipt, manifest, grant)).rsplit(":", 1)[0] == '
     'build["id"].rsplit(":", 1)[0]:'),
    ("api-label-alias", "API: the label is read from the alias, not the run's identity", SV,
     '"temperature_label": label_for(evaluator),', '"temperature_label": label_for(EVALUATOR_IDENTITY),'),
    ("api-label-claimed", "API: every scored result is labelled reproduction-tested", SV,
     '"temperature_label": label_for(evaluator),', '"temperature_label": "reproduction_tested",'),
    ("api-clears-replay", "hard rule: the build label clears a not-reproduced replay", SV,
     '"replay": "reproduced" if row["state"] == "reproduced" else "not_reproduced",',
     '"replay": "reproduced" if row["state"] == "reproduced" or label_for(result["evaluator"]) == "reproduction_tested" '
     'else "not_reproduced",'),
    ("api-clears-binding", "hard rule: the build label clears a binding mismatch", SV,
     '"reproduced": row["state"] == "reproduced",\n                "binding_ok": result["binding"]["ok"],',
     '"reproduced": row["state"] == "reproduced",\n'
     '                "binding_ok": result["binding"]["ok"] or label_for(result["evaluator"]) == "reproduction_tested",'),
    ("api-grants-candidate", "hard rule: the build label makes a candidate", SV,
     '            if row["run_id"] in front_ids:\n                item["verdict"] = "candidate"',
     '            if row["run_id"] in front_ids or label_for(result["evaluator"]) == "reproduction_tested":\n'
     '                item["verdict"] = "candidate"'),
    ("api-fills-grid-basis", "hard rule: the build label claims a grid check that did not run", SV,
     'basis = ["per_die"] + (["grid"] if "grid_ok" in result["binding"] else [])',
     'basis = ["per_die"] + (["grid"] if "grid_ok" in result["binding"] or label_for(result["evaluator"]) == "reproduction_tested" '
     'else [])'),
    # ── the pages: web/public/temperature-label.mjs ──
    ("js-prefix", "pages: the build matched by a prefix (engine and commit)", TL, JS_MATCH,
     "    if ([...reproducedIds].some((id) => identity.startsWith(id.slice(0, 52)))) return LABELS.reproduction_tested;"),
    ("js-casefold", "pages: the build matched without case or padding", TL, JS_MATCH,
     "    if ([...reproducedIds].some((id) => id.toLowerCase() === identity.trim().toLowerCase())) "
     "return LABELS.reproduction_tested;"),
    ("js-derived-any", "pages: a derived value is reproduction-tested if any input is", TL, JS_ALL,
     "    if (labels.includes(LABELS.reproduction_tested)) return LABELS.reproduction_tested;"),
    ("js-before-withdrawn", "pages: the list is read before the withdrawn engine:commit", TL,
     (JS_MATCH + " " * 23 + "// exactly the build\n", "    if (withdrawnKeys.has(evaluatorKey(identity)))"),
     ("", JS_MATCH + "\n    if (withdrawnKeys.has(evaluatorKey(identity)))")),
    ("js-list-alias", "pages: the broad alias is on the list", TL,
     "export const REPRODUCTION_TESTED = Object.freeze([\n",
     f'export const REPRODUCTION_TESTED = Object.freeze([\n  "{ALIAS}",\n'),
    ("js-notice-shown", "pages: the exact build still shows the amber notice", TL,
     'state: "reproduction_tested", notice: false,', 'state: "reproduction_tested", notice: true,'),
    ("js-footnote", "pages: the footnote is not the decided wording", TL,
     "within the declared 1°C tolerance.", "within tolerance."),
    ("js-swallows-tag", "hard rule: the build's tag hides the other source's qualifier", TL,
     "  if (tempsLabel && tempsLabel !== jLabel) tags.push",
     "  if (tempsLabel && tempsLabel !== jLabel && jLabel !== LABELS.reproduction_tested) tags.push"),
    ("js-absorbs-unassociated", "hard rule: an unassociated input takes the build's label", TL,
     "    const labels = list.map(labelFor);",
     "    const labels = list.map(labelFor).map((label, _i, all) => (label === LABELS.unvalidated && "
     "all.includes(LABELS.reproduction_tested) ? LABELS.reproduction_tested : label));"),
]


def run_suites(root: Path) -> list:
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    result = subprocess.run([sys.executable, "-c", RUNNER, json.dumps(FORM_TESTS), json.dumps(PY_SUITES)], cwd=root,
                            env=env, capture_output=True, text=True, check=False, timeout=900)
    lines = result.stdout.strip().splitlines()
    failing = json.loads(lines[-1]) if lines else ["<runner crashed>: " + result.stderr[-300:]]
    web = subprocess.run(["node", "--test", *WEB_TESTS], cwd=root, capture_output=True, text=True, check=False,
                         timeout=900)
    if not re.search(r"^# tests [1-9]", web.stdout, re.MULTILINE):
        return failing + ["<runner crashed>: node " + web.stderr[-300:]]
    failing += ["web: " + name for name in re.findall(r"^not ok \d+ - (.+)$", web.stdout, re.MULTILINE)]
    return failing


def one(mutant) -> tuple:
    mutant_id, rule, path, old, new = mutant
    root = fresh_copy()
    try:
        target = root / path
        text = original = target.read_bytes().decode("utf-8")
        for snippet, replacement in pairs(old, new):
            if text.count(snippet) != 1:
                return mutant_id, rule, "not_landed", [f"snippet occurs {text.count(snippet)} times"]
            text = text.replace(snippet, replacement, 1)
        target.write_bytes(text.encode("utf-8"))
        if target.read_bytes().decode("utf-8") == original:
            return mutant_id, rule, "not_landed", ["file unchanged"]
        failing = run_suites(root)
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
        baseline = run_suites(baseline_root)
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
            print(f"{outcome.upper():10} {mutant_id:24} {rule:66} {', '.join(failing)[:110]}", flush=True)
    print(f"\n{sum(len(names) for names in results.values())} mutants: {len(results['caught'])} caught, "
          f"{len(results['survived'])} survived, {len(results['not_landed'])} did not land, "
          f"{len(results['broken'])} broken")
    return 0 if not (results["survived"] or results["not_landed"] or results["broken"]) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
