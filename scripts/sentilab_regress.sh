#!/usr/bin/env bash
# SLAB-002 regression script: rerun every claim without touching shipped evidence.
# Fixes applied per warden review of PR #6 (gpt-astra-carter #56118):
#   (1) PROVENANCE verifies against immutable git blobs from import base 0cd32a4,
#       not the working tree; separately reports files that evolved since import.
#   (2) TFL-14 nonzero exit fails the script (was swallowed by unconditional || echo).
#   (3) demo.py output is captured and asserted: 93.3423169→92.3143491, receipt_chain_valid=true.
#   (4) Fresh results written to a separate observation block with runtime hashes
#       before scratch cleanup; original 05:10Z observations preserved.
# Exits nonzero on any failure. Requires: python3.12, build-essential, libsuperlu-dev, libblas-dev.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# SLAB-040: run entry points need a signer. Every rerun gets a fresh throwaway seed in its own environment,
# never a production seed and never a file; records it signs read as "integrity only, unanchored".
export FLIGHT_SIGNING_SEED_B64="$(python3 -c 'import base64,os;print(base64.b64encode(os.urandom(32)).decode())')"
FAILED=0
PASSED=0
IMPORT_BASE="0cd32a4"

red()   { printf '\033[31m%s\033[0m\n' "$*"; }
green() { printf '\033[32m%s\033[0m\n' "$*"; }

pass() { green "  PASS: $1"; PASSED=$((PASSED+1)); }
fail() { red   "  FAIL: $1"; FAILED=$((FAILED+1)); }

echo "=== SLAB-002 regression ==="
echo "ROOT=$ROOT"
echo

# --- Toolchain ---
echo "--- Toolchain ---"
gcc --version | head -1
python3 --version
dpkg -l libsuperlu-dev libblas-dev 2>/dev/null | grep '^ii' || true
echo

# --- PROVENANCE ---
# Verify every manifest entry against its immutable git blob from the import
# base (0cd32a4), not the working tree. Separately report which tracked files
# evolved since the import and assert the working tree is clean.
echo "--- PROVENANCE.json (vs immutable git blobs at $IMPORT_BASE) ---"
python3 -c "
import json, hashlib, subprocess, sys
with open('$ROOT/PROVENANCE.json') as f:
    p = json.load(f)
mismatches = 0
missing_blobs = 0
for entry in p['files']:
    blob = entry['git_blob']
    r = subprocess.run(['git', 'cat-file', '-e', blob], cwd='$ROOT', capture_output=True)
    if r.returncode != 0:
        print(f'BLOB MISSING: {entry[\"path\"]} blob={blob}')
        missing_blobs += 1
        continue
    r = subprocess.run(['git', 'cat-file', 'blob', blob], cwd='$ROOT', capture_output=True, text=False)
    actual = hashlib.sha256(r.stdout).hexdigest()
    if actual != entry['sha256']:
        print(f'SHA256 MISMATCH: {entry[\"path\"]} (expected {entry[\"sha256\"][:16]}... got {actual[:16]}...)')
        mismatches += 1
if missing_blobs > 0:
    raise SystemExit(f'PROVENANCE: {missing_blobs} blobs missing from repo')
if mismatches > 0:
    raise SystemExit(f'PROVENANCE SHA256 MISMATCHES: {mismatches}')
print(f'IMMUTABLE IMPORT VERIFIED: {len(p[\"files\"])} files checked against git blobs at $IMPORT_BASE, 0 mismatches')
" && pass "PROVENANCE vs blobs" || fail "PROVENANCE vs blobs"

# --- Delta from import ---
echo "--- Delta from import base $IMPORT_BASE ---"
CHANGED_FILES=$(git -C "$ROOT" diff --name-only "$IMPORT_BASE" HEAD | sort)
if [ -n "$CHANGED_FILES" ]; then
    CHANGED_COUNT=$(echo "$CHANGED_FILES" | wc -l)
    echo "  $CHANGED_COUNT files evolved since $IMPORT_BASE (legitimate post-import changes):"
    echo "$CHANGED_FILES" | while IFS= read -r f; do echo "    $f"; done
fi

# --- Activate venv ---
if [ ! -d "$ROOT/.venv" ]; then
    python3.12 -m venv "$ROOT/.venv"
fi
. "$ROOT/.venv/bin/activate"
pip install -q -r "$ROOT/requirements.txt" -r "$ROOT/requirements-service.txt"

# --- Build HotSpot ---
echo "--- HotSpot build ---"
make -C "$ROOT/sundai_hotspot" -j4 SUPERLU=1 >/dev/null 2>&1 && pass "HotSpot build" || fail "HotSpot build"
HOTSPOT_SHA=$(sha256sum "$ROOT/sundai_hotspot/hotspot" | cut -d' ' -f1)
echo "  HotSpot sha256: $HOTSPOT_SHA"

# --- Controller tests ---
echo "--- Controller tests (55: 47 + 8) ---"
(cd "$ROOT/sundai_controller" && python -m unittest -q test_controller.py test_experiment.py) \
  && pass "Controller tests" || fail "Controller tests"

# --- Safety property ---
echo "--- Safety property (1,000-case TFL-13) ---"
(cd "$ROOT/sundai_controller" && python -m unittest -q test_safety_property.py) \
  && pass "Safety property" || fail "Safety property"

# --- TFL-08 fingerprints ---
echo "--- TFL-08 fingerprints ---"
(cd "$ROOT/sundai_controller" && python -m unittest -q test_tfl08_leaderboard.py) \
  && pass "TFL-08 fingerprints" || fail "TFL-08 fingerprints"

# --- Tap oracle ---
echo "--- Tap oracle ---"
(cd "$ROOT/sundai_hotspot" && python -m unittest -q test_tap_oracle.py) \
  && pass "Tap oracle" || fail "Tap oracle"

# --- Scratch work (probe, demo, TFL-05 smoke) ---
# Run filesystem-mutating commands against a scratch copy, exactly as container_smoke.sh does,
# so shipped evidence is never touched.
SCRATCH="$(mktemp -d)"
trap 'rm -rf "$SCRATCH"' EXIT
cp -r "$ROOT/sundai_controller" "$ROOT/sundai_hotspot" "$ROOT/sundai_tap" "$ROOT/sundai_thermal" "$SCRATCH/"

# Record hashes for the observation block
SCRIPT_SHA=$(sha256sum "$0" | cut -d' ' -f1)
HEAD_SHA=$(git -C "$ROOT" rev-parse HEAD)

# HotSpot probe in scratch
echo "--- HotSpot probe (8 Ascend910 cases) ---"
(cd "$SCRATCH/sundai_hotspot" && python run_tap_probe.py --report "$SCRATCH/sundai_hotspot/probe_results/report.json" > /dev/null) \
  && pass "HotSpot probe" || fail "HotSpot probe"

# TFL-14 full regression: both tests must pass on main (README artifact check
# was fixed at 29b0c3b). Any nonzero exit fails the script.
echo "--- TFL-14 regression ---"
(cd "$ROOT/sundai_thermal" && OPENBLAS_CORETYPE=Haswell TFL_CANONICAL_CONTAINER=1 TFL_HOTSPOT_PROBE_REPORT="$SCRATCH/sundai_hotspot/probe_results/report.json" python -m unittest -q \
    test_tfl14_regression) \
  && pass "TFL-14 full regression" || fail "TFL-14 full regression"

# Demo in scratch — capture output and assert the known values
echo "--- Deterministic demo ---"
(cd "$SCRATCH/sundai_controller" && python demo.py > "$SCRATCH/demo.out" 2>&1) \
  && pass "Demo" || fail "Demo"
python3 -c "
import json
d = json.load(open('$SCRATCH/demo.out', encoding='utf-8'))
assert round(d['baseline_c'], 7) == 93.3423169, f\"baseline {d['baseline_c']}\"
assert round(d['final_c'], 7) == 92.3143491, f\"final {d['final_c']}\"
assert d['receipt_chain_valid'] is True, d
print(f\"demo OK: {d['baseline_c']} → {d['final_c']} C, receipt_chain_valid={d['receipt_chain_valid']}\")
" && pass "Demo assertions" || fail "Demo assertions"

# TFL-05 smoke in scratch
echo "--- TFL-05 smoke ---"
(cd "$SCRATCH/sundai_controller" && python tfl05_smoke.py --benchmark plate > /dev/null) \
  && pass "TFL-05 plate" || fail "TFL-05 plate"
(cd "$SCRATCH/sundai_controller" && python tfl05_smoke.py --benchmark ascend910 > /dev/null) \
  && pass "TFL-05 ascend910" || fail "TFL-05 ascend910"

# --- TFL-09 run service ---
echo "--- TFL-09 run service ---"
(cd "$ROOT" && python -m unittest -q app.test_runs) \
  && pass "TFL-09 run service" || fail "TFL-09 run service"

# --- No tracked-file changes ---
echo "--- Clean checkout check ---"
# Write fresh observation block with runtime hashes before scratch cleanup
OBS_TIME=$(date -u +%Y-%m-%dT%H:%M:%SZ)
RUNTIME_VERSIONS="gcc=$(gcc --version 2>/dev/null | head -1) python=$(python3 --version 2>&1) superlu=$(dpkg -l libsuperlu-dev 2>/dev/null | grep '^ii' | awk '{print $3}') blas=$(dpkg -l libblas-dev 2>/dev/null | grep '^ii' | awk '{print $3}')"
echo "--- Fresh observation block ---"
echo "  observed_at: $OBS_TIME"
echo "  head_sha: $HEAD_SHA"
echo "  script_sha256: $SCRIPT_SHA"
echo "  host: $(uname -a)"
echo "  runtime: $RUNTIME_VERSIONS"
DIRTY=$(git -C "$ROOT" status --porcelain)
if [ -n "$DIRTY" ]; then
    red "TRACKED FILES MODIFIED:"
    echo "$DIRTY"
    fail "Clean checkout"
else
    pass "Clean checkout"
fi

# --- Summary ---
echo
echo "=== Results: $PASSED passed, $FAILED failed ==="
if [ "$FAILED" -gt 0 ]; then
    red "REGRESSION FAILED"
    exit 1
fi
green "ALL CHECKS PASSED"
