"""Mutation check for the API side of AGENT-DOOR Amendment 4 rev 2: each mutant injects one real hazard into a fresh
temporary copy of the tree, and the presence and stats tests must fail.

    python3 -m scripts.door_a4_mutants              # every mutant; exit 1 if any survives, does not land or breaks
    python3 -m scripts.door_a4_mutants --only=a,b   # just these (a spot check, not the result)

It lives in scripts/, outside the shipped trees, like scripts/door_mutants.py and open_proposals/contract/mutants.py: it
launches the test suites in temporary copies, which is a development tool's process launch, not the service's (the CI
gate's inventory of shipped process launches, scripts/tests/test_ci_gate.py, does not cover it).

The working tree is never touched. A mutant must land (its snippet occurs exactly once and the file changes) or it is
reported as not landed, never as a survivor; a mutant that stops the suite from importing or running is broken, never a
kill. The fixture test pins the published files byte for byte, so it is left out: a kill must come from a test of the
hazard itself. Needs Linux (the door's owner lock).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COPY = ["app", "open_proposals", "contracts", "sentilab_core", "sundai_hotspot", "sundai_tap", "sundai_controller",
        "sundai_thermal", "docs/sentilab/diagnostics/SLAB-049"]
SUITES = ("app.test_door_presence", "app.test_door_stats")
RUNNER = """
import json, sys, unittest
def flat(suite):
    for test in suite:
        yield from (flat(test) if isinstance(test, unittest.TestSuite) else [test])
loader = unittest.defaultTestLoader
tests = [t for name in json.loads(sys.argv[1]) for t in flat(loader.loadTestsFromName(name))]
broken = [t.id() for t in tests if type(t).__name__ == "_FailedTest"]
if broken:
    print(json.dumps(["<runner crashed> " + name for name in broken]))
    sys.exit(0)
result = unittest.TextTestRunner(stream=open(__import__("os").devnull, "w"), verbosity=0).run(unittest.TestSuite(tests))
print(json.dumps(sorted({t.id().rsplit(".", 1)[-1] for t, _ in result.failures + result.errors})))
"""
P, S, V = "app/door/presence.py", "app/door/stats.py", "app/door/service.py"
MUTANTS = [
    # presence: the window, the expiry and the day
    ("window-121", "the active window is 121 s", P, "WINDOW_S = 120\n", "WINDOW_S = 121\n"),
    ("expiry-inclusive", "a tab 120 s old is still active", P,
     '            if now - entry["last_seen"] < WINDOW_S:\n                break',
     '            if now - entry["last_seen"] <= WINDOW_S:\n                break'),
    ("no-expiry", "reads and heartbeats erase nothing", P,
     "        while self._active:\n            tab, entry = next(iter(self._active.items()))",
     "        while False:\n            tab, entry = next(iter(self._active.items()))"),
    ("refresh-in-place", "a refreshed tab keeps its old place", P, "            self._active.pop(tab, None)\n", ""),
    ("day-never-ends", "the day's set and key outlive the day", P, "        if day != self._day:", "        if self._day is None:"),
    ("key-kept", "yesterday's key kept", P, "self._day, self._key, self._seen = day, self._new_key(), set()",
     "self._day, self._key, self._seen = day, self._key or self._new_key(), set()"),
    ("set-kept", "yesterday's set kept", P, "self._day, self._key, self._seen = day, self._new_key(), set()",
     "self._day, self._key, self._seen = day, self._new_key(), self._seen"),
    ("raw-tab-kept", "the raw tab kept for the day", P, "            self._seen.add(mark)", "            self._seen.add(tab)"),
    ("recount", "a returning tab counted again", P,
     '        return hmac.new(self._key, tab.encode("ascii"), hashlib.sha256).digest()[:16]',
     '        return hmac.new(self._key, (tab + repr(self._clock())).encode("ascii"), hashlib.sha256).digest()[:16]'),
    ("sweeper-idle", "the sweeper erases nothing", P,
     "        while not self._stop.wait(SWEEP_S):\n            self.sweep()", "        while not self._stop.wait(SWEEP_S):\n            pass"),
    ("sweep-front-only", "the sweep stops at the first live tab", P,
     '            for tab in [tab for tab, entry in self._active.items() if now - entry["last_seen"] >= WINDOW_S]:\n'
     '                del self._active[tab]\n', ""),
    ("more-kept", "more kept per tab", P, '{"page": page, "class": klass, "last_seen": float(now)}',
     '{"page": page, "class": klass, "last_seen": float(now), "first_seen": float(now)}'),
    # presence: the bounds and limits
    ("day-cap-silent", "a full day set still takes new tabs (root's P2)", P,
     '            if mark not in self._seen and len(self._seen) >= self._max_day:\n                return "limited"',
     '            if False:\n                return "limited"'),
    ("active-cap", "the active cap off by one", P, "            if not known and len(self._active) >= self._max_active:",
     "            if not known and len(self._active) > self._max_active:"),
    ("minute-cap", "the minute limit off by one", P, "            if count >= self._per_minute:", "            if count > self._per_minute:"),
    ("minute-late", "the minute ends late", P, "            if now - start >= MINUTE_S or now < start:",
     "            if now - start > MINUTE_S or now < start:"),
    ("schema-open", "a heartbeat with more fields accepted", P, '    "additionalProperties": False,', '    "additionalProperties": True,'),
    # the service
    ("never-measured", "presence never published", V,
     "        return self.presence.snapshot() if self.presence is not None else dict(NOT_MEASURED)",
     "        return dict(NOT_MEASURED)"),
    ("switch-loose", "any DOOR_PRESENCE value turns it on", V,
     'presence = Presence() if env.get("DOOR_PRESENCE", "") == "on" else None',
     'presence = Presence() if env.get("DOOR_PRESENCE", "") else None'),
    ("limit-unanswered", "a limited heartbeat answered 204", V,
     '        if self.presence.beat(value["page"], value["tab"], value["class"]) == "limited":\n'
     '            return 429, {"error": "rate_limited"}, {"retry-after": "60"}\n',
     '        self.presence.beat(value["page"], value["tab"], value["class"])\n'),
    ("heartbeat-stored", "a heartbeat written to the door's store", V,
     '        return 204, None, {}\n\n    def stats(self)',
     '        self.store.scorer_event("here", self.policy.clock())\n        return 204, None, {}\n\n    def stats(self)'),
    # the run totals
    ("passes-walls", "passes count wall views", S, "\"AND json_extract(body, '$.purpose') IS NOT NULL \"", "\"AND 1 = 1 \""),
    ("passes-declarations", "a declaration counted as another pass", S, "\"AND json_extract(body, '$.declaration') IS NULL\"",
     "\"AND 1 = 1\""),
    ("runs-by-event", "runs counted by event", S, "runs = db.execute(\"SELECT COUNT(DISTINCT run_id) FROM events",
     "runs = db.execute(\"SELECT COUNT(*) FROM events"),
    ("short-id-key", "the short id as the run key", S,
     "\"SELECT json_extract(body, '$.state'), COUNT(DISTINCT run_id) FROM events",
     "\"SELECT json_extract(body, '$.state'), COUNT(DISTINCT json_extract(body, '$.short_id')) FROM events"),
    ("no-attempts", "submissions without the refused ones", S, '"submissions": attempts + runs,', '"submissions": runs,'),
    ("rejected-failed", "rejected counts failed runs", S, '"rejected": attempts,', '"rejected": reached.get("failed", 0),'),
    ("cache-6s", "a 6 s cache", S, "CACHE_S = 5.0", "CACHE_S = 6.0"),
    ("cache-step-back", "a clock step back serves the cache", S, "not 0 <= now - self._at < self.cache_s",
     "not now - self._at < self.cache_s"),
    ("through-arrivals", "through_seq of arrivals only", S, 'through = db.execute("SELECT COALESCE(MAX(seq), 0) FROM events")',
     "through = db.execute(\"SELECT COALESCE(MAX(seq), 0) FROM events WHERE kind = 'arrival'\")"),
    ("cache-shared", "callers share the cached answer", S, 'return {**self._value, "results": dict(self._value["results"])}',
     "return self._value"),
]


def fresh_copy() -> Path:
    root = Path(tempfile.mkdtemp(prefix="door-a4-mutant-"))
    for rel in COPY:
        source, target = ROOT / rel, root / rel
        if source.is_dir():
            shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__"))
    return root


def run_suite(root: Path) -> list:
    result = subprocess.run([sys.executable, "-c", RUNNER, json.dumps(SUITES)], cwd=root, capture_output=True, text=True,
                            timeout=900)
    try:
        return json.loads(result.stdout.strip().splitlines()[-1])
    except (IndexError, ValueError):
        return ["<runner crashed> " + (result.stderr.strip().splitlines() or ["no output"])[-1]]


def main(argv) -> int:
    only = {name for arg in argv if arg.startswith("--only=") for name in arg[len("--only="):].split(",")}
    baseline_root = fresh_copy()
    try:
        baseline = run_suite(baseline_root)
    finally:
        shutil.rmtree(baseline_root, ignore_errors=True)
    if baseline:
        print("baseline fails:", baseline)
        return 1
    results = {"caught": [], "survived": [], "not_landed": [], "broken": []}
    for mutant_id, rule, path, old, new in MUTANTS:
        if only and mutant_id not in only:
            continue
        root = fresh_copy()
        try:
            target = root / path
            text = target.read_bytes().decode("utf-8")
            if text.count(old) != 1:
                results["not_landed"].append(mutant_id)
                print(f"NOT LANDED {mutant_id}: snippet occurs {text.count(old)} times", flush=True)
                continue
            target.write_bytes(text.replace(old, new).encode("utf-8"))
            if target.read_bytes().decode("utf-8") == text:
                results["not_landed"].append(mutant_id)
                print(f"NOT LANDED {mutant_id}: file unchanged", flush=True)
                continue
            failing = run_suite(root)
            if any(name.startswith("<runner crashed>") for name in failing):
                results["broken"].append(mutant_id)
                print(f"BROKEN    {mutant_id}: the suite did not run: {failing[0][:160]}", flush=True)
                continue
            outcome = "caught" if failing else "survived"
            results[outcome].append(mutant_id)
            print(f"{outcome.upper():9} {mutant_id:18} {rule:48} {', '.join(failing)[:140]}", flush=True)
        finally:
            shutil.rmtree(root, ignore_errors=True)
    print(f"\n{sum(len(names) for names in results.values())} mutants: {len(results['caught'])} caught, "
          f"{len(results['survived'])} survived, {len(results['not_landed'])} did not land, {len(results['broken'])} broken")
    return 0 if not (results["survived"] or results["not_landed"] or results["broken"]) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
