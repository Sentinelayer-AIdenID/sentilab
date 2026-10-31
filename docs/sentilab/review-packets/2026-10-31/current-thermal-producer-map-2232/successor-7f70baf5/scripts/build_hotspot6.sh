#!/usr/bin/env bash
# SLAB-049: build the HotSpot 6.0 evaluator, TAP-2.5D's HotSpot (uvahotspot/HotSpot a7a3286e), on x86_64 or
# aarch64 (Debian/Ubuntu; the same packages on amd64 and arm64):
#   apt-get install build-essential libsuperlu-dev libblas-dev
# Two binaries come from the vendored source in sundai_hotspot6/:
#   hotspot               the evaluator: SuperLU direct solver plus the all-layer grid dump
#                         (-DSENTILAB_GRID_DUMP_ALL_LAYERS=1, writer only; the solver is unchanged)
#   hotspot-tap-faithful  the cross-check: upstream source, SUPERLU=0, as TAP-2.5D's util/hotspot was built
# -ffp-contract=off stops GCC contracting a*b+c into one fused multiply-add in the HotSpot sources it compiles here
# (GCC contracts by default where the target has FMA, as aarch64 does; the x86_64 baseline target has none). It
# does not reach the precompiled SuperLU, BLAS or libm, which may pick FMA or other kernels per CPU. So it narrows
# cross-architecture differences; it does not make results bit-identical across architectures, and none is claimed.
# Binary hashes depend on the toolchain and, through the Makefile's -g, on the build path. Every host pins its own
# through gate zero: an aarch64 build needs its own receipts. sundai_hotspot.provenance writes
# <binary>.provenance.json for each binary (compiler, flags, build path, SuperLU/BLAS packages, the libraries the
# loader resolves with their hashes, the binary hash); validate-reference refuses a binary without it.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root/sundai_hotspot6"
arch="$(uname -m)"
case "$arch" in
  x86_64|aarch64) ;;
  *) echo "unsupported architecture: $arch (x86_64 and aarch64 only)" >&2; exit 2 ;;
esac
SLU_HEADER="${SLU_HEADER:-/usr/include/superlu}"
if [ ! -f "$SLU_HEADER/slu_ddefs.h" ]; then
  echo "SuperLU headers are missing in $SLU_HEADER (apt-get install libsuperlu-dev)" >&2
  exit 2
fi
make cleano >/dev/null
rm -f hotspot hotspot-tap-faithful
make hotspot SUPERLU=0 EXTRAFLAGS="-ffp-contract=off"
mv hotspot hotspot-tap-faithful
make cleano >/dev/null
make hotspot SUPERLU=1 SUPERLULIB=-lsuperlu BLASLIB=-lblas SLU_HEADER="$SLU_HEADER" \
  EXTRAFLAGS="-DSENTILAB_GRID_DUMP_ALL_LAYERS=1 -ffp-contract=off"
make cleano >/dev/null
echo "architecture $arch"
gcc --version | head -n 1
sha256sum hotspot hotspot-tap-faithful
cd "$root"
python3 -m sundai_hotspot.provenance hotspot6 hotspot6_tap_faithful
