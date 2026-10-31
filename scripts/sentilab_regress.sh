#!/usr/bin/env bash
# SLAB-002 regression script: preserve each run separately from shipped evidence.
# Fixes applied per warden review of PR #6 (gpt-astra-carter #56118):
#   (1) PROVENANCE verifies against the immutable import commit 126507d4 (path -> blob -> sha256),
#       not the working tree; separately reports files that evolved since import.
#   (2) TFL-14 nonzero exit fails the script (was swallowed by unconditional || echo).
#   (3) demo.py output is captured and asserted: 93.3423169→92.3143491, receipt_chain_valid=true.
#   (4) Step logs, output artifacts and runtime hashes are retained per run,
#       including failures. Historical results.json observations are never rewritten.
# Exits nonzero on any failure. Requires: python3.12, build-essential, libsuperlu-dev, libblas-dev.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# SLAB-040: run entry points need a signer. Every rerun gets a fresh throwaway seed in its own environment,
# never a production seed and never a file; records it signs read as "integrity only, unanchored".
export FLIGHT_SIGNING_SEED_B64="$(python3 -c 'import base64,os;print(base64.b64encode(os.urandom(32)).decode())')"
FAILED=0
PASSED=0
# The repository import commit (PROVENANCE.json describes exactly its tree; see README).
IMPORT_BASE="126507d4dbd8cf327aa158c4dd893c436f7cdf8f"

red()   { printf '\033[31m%s\033[0m\n' "$*"; }
green() { printf '\033[32m%s\033[0m\n' "$*"; }

pass() { green "  PASS: $1"; PASSED=$((PASSED+1)); }
fail() { red   "  FAIL: $1"; FAILED=$((FAILED+1)); }

# Each invocation creates an exclusive run directory. Logs are written directly there;
# output artifacts are copied before returning from a step, including a failed step.
evidence() {
python3 - "$ROOT" "$RUN_DIR" "$@" <<'EVIDENCE_PY'
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00', 'Z')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, data):
    Path(path).write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')


def file_ref(run, path):
    return {'path': str(path.relative_to(run)), 'sha256': digest(path)}


def observe(command, cwd):
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True)
    return {'command': command, 'exit_code': result.returncode,
            'stdout': result.stdout.strip(), 'stderr': result.stderr.strip()}


def initialize(root, run):
    write_json(run / 'run.json', {
        'schema': 'sentilab-regression-run-v1', 'started_at': utc(),
        'head_sha': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip(),
        'git_tree_sha': subprocess.check_output(['git', 'rev-parse', 'HEAD^{tree}'], cwd=root, text=True).strip(),
        'script_sha256': digest(root / 'scripts/sentilab_regress.sh'),
        'status': 'running', 'steps': [],
    })


def record_step(run, name, cwd, command):
    step_dir = run / name
    step_dir.mkdir()  # Never overwrite an earlier step's evidence.
    started_at, start = utc(), time.monotonic()
    status = 125
    metadata = {'name': name, 'command': command, 'cwd': str(cwd), 'started_at': started_at}
    write_json(step_dir / 'step.json', metadata)
    try:
        with (step_dir / 'stdout.txt').open('wb') as stdout, (step_dir / 'stderr.txt').open('wb') as stderr:
            try:
                status = subprocess.run(command, cwd=cwd, stdout=stdout, stderr=stderr).returncode
            except OSError as error:
                stderr.write((str(error) + '\n').encode())
                status = 127
    finally:
        metadata.update(exit_code=status, ended_at=utc(), wall_time_s=time.monotonic() - start)
        artifacts = []
        # These are the files the entry points write. Smoke reports are stdout.
        paths = {'probe': ['probe_results/report.json'],
                 'demo': ['demo_results.json', 'demo_flight_record.json'],
                 'hotspot-build': ['hotspot', 'hotfloorplan']}.get(name, [])
        try:
            for relative in paths:
                source = cwd / relative
                if source.is_file():
                    target = step_dir / 'artifacts' / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, target)
                    artifacts.append(file_ref(run, target))
        finally:
            metadata['artifacts'] = artifacts
            for stream in ('stdout', 'stderr'):
                metadata[stream] = file_ref(run, step_dir / (stream + '.txt'))
            text = (step_dir / 'stderr.txt').read_text(errors='replace')
            count = re.search(r'^Ran (\d+) tests?\b', text, re.M)
            if count:
                metadata['test_count'] = int(count.group(1))
            write_json(step_dir / 'step.json', metadata)
    print(f'{name}: exit {status}, {metadata["wall_time_s"]:.3f}s; {step_dir}')
    return status if status >= 0 else 128 - status


def finalize(root, run, status, passed, failed):
    data = json.loads((run / 'run.json').read_text())
    data.update(ended_at=utc(), exit_code=status, passed=passed, failed=failed,
                status='passed' if status == 0 else 'failed')
    data['toolchain'] = {
        'python': observe([sys.executable, '--version'], root),
        'gcc': observe(['gcc', '--version'], root),
        'superlu': observe(['dpkg-query', '-W', '-f=${Version}', 'libsuperlu-dev'], root),
        'blas': observe(['dpkg-query', '-W', '-f=${Version}', 'libblas-dev'], root),
    }
    binary = root / 'sundai_hotspot/hotspot'
    data['hotspot_binary_sha256'] = digest(binary) if binary.is_file() else None
    data['steps'] = []
    for path in sorted(run.glob('*/step.json')):
        step = json.loads(path.read_text())
        step['metadata'] = file_ref(run, path)
        data['steps'].append(step)
    write_json(run / 'run.json', data)


if __name__ == '__main__':
    root, run = map(Path, sys.argv[1:3])
    mode, *args = sys.argv[3:]
    if mode == 'init':
        initialize(root, run)
    elif mode == 'step':
        name, cwd, *command = args
        sys.exit(record_step(run, name, Path(cwd), command))
    elif mode == 'finish':
        finalize(root, run, *map(int, args))
EVIDENCE_PY
}

RUN_PARENT="$ROOT/docs/sentilab/evidence/SLAB-002/runs"
mkdir -p "$RUN_PARENT"
RUN_DIR="$(mktemp -d "$RUN_PARENT/$(date -u +%Y%m%dT%H%M%S.%NZ)-XXXXXX")"
evidence init
SCRATCH=""
finish() {
    local status=$?
    trap - EXIT
    # If evidence preservation fails, retain scratch for diagnosis and fail the run.
    if evidence finish "$status" "$PASSED" "$FAILED"; then
        [ -z "$SCRATCH" ] || rm -rf "$SCRATCH"
    else
        echo "Evidence finalization failed; scratch retained at $SCRATCH" >&2
        status=1
    fi
    echo "Run evidence: $RUN_DIR/run.json"
    exit "$status"
}
trap finish EXIT
step() { evidence step "$@"; }

echo "=== SLAB-002 regression ==="
echo "ROOT=$ROOT"
echo

# --- Toolchain ---
echo "--- Toolchain ---"
step toolchain "$ROOT" bash -ec 'gcc --version; python3 --version; dpkg-query -W libsuperlu-dev libblas-dev'
echo

# --- PROVENANCE ---
# Verify every manifest entry against its immutable git blob from the import
# commit 126507d4, not the working tree. Separately report which tracked files
# evolved since the import and assert the working tree is clean.
echo "--- PROVENANCE.json (vs immutable git blobs at $IMPORT_BASE) ---"
step provenance "$ROOT" python3 -c "
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
    at_import = subprocess.run(['git', 'rev-parse', '$IMPORT_BASE:' + entry['path']], cwd='$ROOT', capture_output=True, text=True)
    if at_import.returncode != 0 or at_import.stdout.strip() != blob:
        print(f'IMPORT TREE MISMATCH: {entry[\"path\"]} is not blob {blob} at $IMPORT_BASE')
        mismatches += 1
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
step import-delta "$ROOT" git diff --name-only "$IMPORT_BASE" HEAD

# --- Activate venv ---
if [ ! -d "$ROOT/.venv" ]; then
    step venv "$ROOT" python3.12 -m venv "$ROOT/.venv"
fi
. "$ROOT/.venv/bin/activate"
step dependencies "$ROOT" python -m pip install -q -r "$ROOT/requirements.txt" -r "$ROOT/requirements-service.txt"

# --- Build HotSpot ---
echo "--- HotSpot build ---"
step hotspot-build "$ROOT/sundai_hotspot" make -j4 SUPERLU=1 && pass "HotSpot build" || fail "HotSpot build"
HOTSPOT_SHA=$(sha256sum "$ROOT/sundai_hotspot/hotspot" | cut -d' ' -f1)
echo "  HotSpot sha256: $HOTSPOT_SHA"

# --- Controller tests ---
echo "--- Controller tests (55: 47 + 8) ---"
step controller "$ROOT/sundai_controller" python -m unittest -q test_controller.py test_experiment.py \
  && pass "Controller tests" || fail "Controller tests"

# --- Safety property ---
echo "--- Safety property (1,000-case TFL-13) ---"
step safety "$ROOT/sundai_controller" python -m unittest -q test_safety_property.py \
  && pass "Safety property" || fail "Safety property"

# --- TFL-08 fingerprints ---
echo "--- TFL-08 fingerprints ---"
step fingerprints "$ROOT/sundai_controller" python -m unittest -q test_tfl08_leaderboard.py \
  && pass "TFL-08 fingerprints" || fail "TFL-08 fingerprints"

# --- Tap oracle ---
echo "--- Tap oracle ---"
step tap-oracle "$ROOT/sundai_hotspot" python -m unittest -q test_tap_oracle.py \
  && pass "Tap oracle" || fail "Tap oracle"

# --- Scratch work (probe, demo, TFL-05 smoke) ---
# Run filesystem-mutating commands against a scratch copy, exactly as container_smoke.sh does,
# so shipped evidence is never touched.
SCRATCH="$(mktemp -d)"
step scratch-copy "$ROOT" cp -r "$ROOT/sundai_controller" "$ROOT/sundai_hotspot" "$ROOT/sundai_tap" "$ROOT/sundai_thermal" "$SCRATCH/"

# Remove copied historical outputs so a failed entry point cannot present stale
# input evidence as a newly generated artifact.
step scratch-outputs "$ROOT" rm -f "$SCRATCH/sundai_hotspot/probe_results/report.json" \
    "$SCRATCH/sundai_controller/demo_results.json" "$SCRATCH/sundai_controller/demo_flight_record.json"

# HotSpot probe in scratch
echo "--- HotSpot probe (8 Ascend910 cases) ---"
step probe "$SCRATCH/sundai_hotspot" python run_tap_probe.py --report "$SCRATCH/sundai_hotspot/probe_results/report.json" \
  && pass "HotSpot probe" || fail "HotSpot probe"

# TFL-14 full regression: both tests must pass on main (README artifact check
# was fixed at 29b0c3b). Any nonzero exit fails the script.
echo "--- TFL-14 regression ---"
step thermal "$ROOT/sundai_thermal" env OPENBLAS_CORETYPE=Haswell TFL_CANONICAL_CONTAINER=1 TFL_HOTSPOT_PROBE_REPORT="$SCRATCH/sundai_hotspot/probe_results/report.json" python -m unittest -q test_tfl14_regression \
  && pass "TFL-14 full regression" || fail "TFL-14 full regression"

# Demo in scratch — capture output and assert the known values
echo "--- Deterministic demo ---"
step demo "$SCRATCH/sundai_controller" python demo.py \
  && pass "Demo" || fail "Demo"
step demo-assertions "$ROOT" python3 -c "
import json
d = json.load(open('$RUN_DIR/demo/stdout.txt', encoding='utf-8'))
assert round(d['baseline_c'], 7) == 93.3423169, f\"baseline {d['baseline_c']}\"
assert round(d['final_c'], 7) == 92.3143491, f\"final {d['final_c']}\"
assert d['receipt_chain_valid'] is True, d
print(f\"demo OK: {d['baseline_c']} → {d['final_c']} C, receipt_chain_valid={d['receipt_chain_valid']}\")
" && pass "Demo assertions" || fail "Demo assertions"

# TFL-05 smoke in scratch
echo "--- TFL-05 smoke ---"
step smoke-plate "$SCRATCH/sundai_controller" python tfl05_smoke.py --benchmark plate \
  && pass "TFL-05 plate" || fail "TFL-05 plate"
step smoke-ascend910 "$SCRATCH/sundai_controller" python tfl05_smoke.py --benchmark ascend910 \
  && pass "TFL-05 ascend910" || fail "TFL-05 ascend910"

# --- TFL-09 run service ---
echo "--- TFL-09 run service ---"
step service "$ROOT" python -m unittest -q app.test_runs \
  && pass "TFL-09 run service" || fail "TFL-09 run service"

# --- No tracked-file changes ---
echo "--- Clean checkout check ---"
# Only this newly-created evidence directory is exempt. Existing evidence and
# product files still participate in the clean checkout assertion.
step clean-checkout "$ROOT" bash -c '
    dirty=$(git status --porcelain -- . ":(exclude)$1")
    [ -z "$dirty" ] || { printf "%s\n" "$dirty"; exit 1; }
' bash "${RUN_DIR#"$ROOT/"}" && pass "Clean checkout" || fail "Clean checkout"

# --- Summary ---
echo
echo "=== Results: $PASSED passed, $FAILED failed ==="
if [ "$FAILED" -gt 0 ]; then
    red "REGRESSION FAILED"
    exit 1
fi
green "ALL CHECKS PASSED"
