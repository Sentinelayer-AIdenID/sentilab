"""Writes web/test/door-legality-vectors.json: compact CPU-DRAM layouts with TapGeometry's own verdicts.

The agent door's preview check (web/src/door/layout.js) must agree with the legality the scorer intake applies,
TapGeometry.layout_violations in sundai_hotspot/tap_oracle.py, on the micro150-45mm fixture. This script asks
TapGeometry itself about a fixed, seeded set of layouts on the 500 um lattice (the legal snapped reference, every
single-die and paired move near it, CPU turns, and random layouts) and records each verdict: the rule, the die
indices and the amount in whole micrometres, plus the wire proxy. web/test/door-layout.test.mjs replays them.

    python web/test/make_door_vectors.py           # rewrite the vectors
    python web/test/make_door_vectors.py --check   # exit 1 when the file differs from what this tree generates
"""
import hashlib
import json
import random
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from sundai_hotspot.tap_oracle import TapGeometry  # noqa: E402

OUT = Path(__file__).resolve().parent / "door-legality-vectors.json"
FIXTURE = "micro150-45mm"
SNAPPED = [(36, 35, 0), (54, 35, 0), (54, 55, 0), (36, 55, 0), (17, 35, 0), (73, 35, 0), (73, 55, 0), (17, 55, 0)]
CPU = range(4)


def compact(items):
    return ",".join(f"{x}.{y}.{r}" for x, y, r in items)


def verdict(geometry, items):
    design = geometry.design_from_centers([(x * 0.5, y * 0.5) for x, y, _ in items], [r == 1 for _, _, r in items])
    found = [[v.rule, list(v.dies), round(v.amount_mm * 1000)] for v in geometry.layout_violations(design)]
    centers = geometry._centers(design)
    return {"l": compact(items), "violations": found, "wire_proxy_um": round(geometry.wirelength_mm(centers) * 1000)}


def layouts():
    seen, out = set(), []

    def add(items):
        key = compact(items)
        if key not in seen:
            seen.add(key)
            out.append(list(items))

    add(SNAPPED)
    for die in range(8):
        for dx, dy in [(d, 0) for d in range(-4, 5) if d] + [(0, d) for d in range(-4, 5) if d]:
            items = list(SNAPPED)
            x, y, r = items[die]
            items[die] = (min(max(x + dx, 0), 90), min(max(y + dy, 0), 90), r)
            add(items)
    for die in CPU:
        items = list(SNAPPED)
        x, y, _ = items[die]
        items[die] = (x, y, 1)
        add(items)
    for x in (0, 9, 10, 11, 79, 80, 81, 90):
        for y in (0, 9, 10, 11, 12, 78, 79, 80, 90):
            items = list(SNAPPED)
            items[0] = (x, y, 0)
            items[4] = (x, y, 0) if (x, y) == (0, 0) else items[4]
            add(items)
            items = list(SNAPPED)
            items[4] = (x, y, 0)
            add(items)
    rng = random.Random(20261101)
    while len(out) < 450:
        items = [(rng.randint(0, 90), rng.randint(0, 90), rng.randint(0, 1) if die in CPU else 0) for die in range(8)]
        add(items)
    for _ in range(250):
        items = [(min(max(x + rng.randint(-6, 6), 0), 90), min(max(y + rng.randint(-6, 6), 0), 90),
                  rng.randint(0, 1) if die in CPU else 0) for die, (x, y, _) in enumerate(SNAPPED)]
        add(items)
    return out


def generate():
    geometry = TapGeometry.load(FIXTURE)
    config = REPO / "sundai_tap" / "configs" / "sys_micro150_45mm.cfg"
    vectors = [verdict(geometry, items) for items in layouts()]
    document = {
        "schema": "sentilab-door-legality-vectors/1",
        "fixture": FIXTURE,
        "config_sha256": hashlib.sha256(config.read_bytes()).hexdigest(),
        "tap_oracle_sha256": hashlib.sha256((REPO / "sundai_hotspot" / "tap_oracle.py").read_bytes()).hexdigest(),
        "generator": "web/test/make_door_vectors.py",
        "legal": sum(1 for v in vectors if not v["violations"]),
        "vectors": vectors,
    }
    return (json.dumps(document, indent=None, separators=(",", ":")) + "\n").replace('{"l"', '\n{"l"').encode("utf-8")


if __name__ == "__main__":
    data = generate()
    if "--check" in sys.argv:
        sys.exit(0 if OUT.read_bytes() == data else 1)
    OUT.write_bytes(data)
    print("wrote", OUT.name, len(json.loads(data)["vectors"]), "vectors")
