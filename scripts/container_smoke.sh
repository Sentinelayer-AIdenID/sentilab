#!/usr/bin/env bash
# Build-time proof that the image works: controller/property tests, the deterministic demo,
# thermal regressions, and all eight HotSpot+SuperLU cases on a scratch copy. Shipped evidence is untouched.
set -euo pipefail
cd /app/sundai_controller
python -m unittest -q test_controller.py 2>&1 | tee /tmp/unittest.out
python - <<'PY'
import re
ran = re.search(r"^Ran (\d+) tests?", open("/tmp/unittest.out", encoding="utf-8").read(), re.M)
assert ran and int(ran.group(1)) >= 16, "expected at least 16 controller tests"
print("controller tests ran:", ran.group(1))
PY
python demo.py | tee /tmp/demo.out
python - <<'PY'
import json
d = json.load(open("/tmp/demo.out", encoding="utf-8"))
assert round(d["baseline_c"], 7) == 93.3423169 and round(d["final_c"], 7) == 92.3143491, d
assert d["receipt_chain_valid"] is True, d
PY
# TFL-13: no commit without a bound simulator result, over 1,000 generated event orders; every injected bypass caught.
python -m unittest -q test_safety_property.py
python -m unittest -q test_experiment.py
python -m unittest -q test_tfl08_leaderboard.py
python tfl05_smoke.py --benchmark plate | tee /tmp/tfl05-plate.out
rm -rf /tmp/probe && mkdir -p /tmp/probe && cp -r /app/sundai_controller /app/sundai_hotspot /app/sundai_tap /tmp/probe/
cd /tmp/probe/sundai_hotspot
python -m unittest -q test_tap_oracle.py
python run_tap_probe.py --report /tmp/probe/sundai_hotspot/probe_results/report.json | tee /tmp/probe.out
python - <<'PY'
import json
import statistics
runs = [json.loads(line) for line in open("/tmp/probe.out", encoding="utf-8") if line.startswith("{")]
assert len(runs) == 8, len(runs)
right32 = next(r for r in runs if r["placement"] == "right_shift_2mm" and r["grid_rows"] == 32)
peak32 = right32["chip_layer_peak_C"]
elapsed32 = right32["evaluation_seconds"]
print("HotSpot probe cases ran:", len(runs))
print(f"right_shift_2mm 32x32 peak {peak32:.4f} C in {elapsed32:.3f} s")
assert 118.80 <= peak32 <= 118.90, peak32
# The TFL-03 latency targets (median < 0.1 s at 16x16, < 0.4 s at 32x32) apply to the DEPLOYED container; a build
# agent's speed is not that host, so they are reported here, not enforced. The hard bound below only proves SuperLU
# is in use: the stock solver takes about 5.6 s at 32x32.
for grid, target in ((16, 0.100), (32, 0.400)):
    samples = [run["evaluation_seconds"] for run in runs if run["grid_rows"] == grid]
    median = statistics.median(samples)
    flag = "within" if median < target else "ABOVE"
    print(f"{grid}x{grid} median oracle evaluation: {median:.3f} s ({flag} the deployed-host target {target:.3f} s)")
    assert median < 2.0, f"{grid}x{grid} median {median:.3f} s: SuperLU not in use?"
PY
cd /tmp/probe/sundai_controller
python tfl05_smoke.py --benchmark ascend910 | tee /tmp/tfl05-ascend910.out
cd /app/sundai_thermal
TFL_CANONICAL_CONTAINER=1 TFL_HOTSPOT_PROBE_REPORT=/tmp/probe/sundai_hotspot/probe_results/report.json python -m unittest -q test_tfl14_regression.py
rm -rf /tmp/probe
# TFL-09: the run service (start, one-run lock, persisted verifiable result, restart recovery, validation).
cd /app && python -m unittest -q app.test_runs
