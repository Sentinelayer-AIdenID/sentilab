# Node runtime provenance for SLAB-043

The Dockerfile pins the resolved Python base image index and Debian Node package.
During each image build, `scripts/record_build_info.py` prints the actual Node
runtime/package versions and the pinned base reference, and writes the same JSON
to `/app/build-info.json`. It fails before writing if the base lacks a digest,
Node is shadowed by a non-Debian executable, or the installed package differs
from the requested pin. This is a build artifact, not a checked-in claim that
an image was built in this box.

Resolved on 2026-10-31:

| Input / observation | Value |
|---|---|
| Python image index | `python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159` |
| Linux amd64 manifest | `sha256:1148dbb014615300fa7e713b2f94f550c0d1c69780c0805f84f093ceee34dd0b` |
| Image metadata | `3.12.16-slim-trixie`, base `debian:trixie-slim` |
| Debian nodejs package | `20.19.2+dfsg-1+deb13u3` |
| Package SHA-256 (amd64) | `2f30b056911388a3abf27d015eda858bf5b76abfeb7f43b82c3cc35231f1c8bc` |
| Actual extracted package runtime | `v20.19.2` |

Sources: Docker Hub's `library/python:3.12-slim` OCI index and amd64 manifest
at `https://registry-1.docker.io/v2/library/python/manifests/3.12-slim`, and
`https://security.debian.org/debian-security/dists/trixie-security/main/binary-amd64/Packages.xz`.
The security index selected above contains a newer package than trixie main
(`20.19.2+dfsg-1+deb13u2`). The exact apt version is pinned; if Debian removes it,
builds fail and require a reviewed pin refresh. No fallback to an unpinned Node
package is permitted. Updating the base requires updating its digest; overrides
must retain a digest and matching package pin.

Independent of Docker, the amd64 Node package and its shared-library/JavaScript
dependencies were downloaded, SHA-256 checked against Debian package metadata,
and extracted into `/tmp/slab043-v4-debian-node/root`. After creating Debian's
usr-merge symlinks, these commands ran successfully:

```sh
sudo -n chroot /tmp/slab043-v4-debian-node/root /usr/bin/node --version
# v20.19.2
sudo -n chroot /tmp/slab043-v4-debian-node/root /usr/bin/node /app/render-probe.mjs
# exit 0; seven cards
```

The render probe is the unmodified JavaScript fragment extracted from the shipped
`chiplet.render` adapter, with its two existing browser modules and the committed
SLAB-016 JSONL supplied on stdin. This proves that the pinned Debian runtime can
render that fixture. It is not a Docker build or a full service smoke test.

The build-info regression runs the real script, Node and dpkg-query on the host
and checks successful recording plus refusal of an unpinned base/wrong package.
Its base identifier is explicitly a test fixture. The host reports Node
`v22.23.3`, package `22.23.3-1nodesource1`; those are not the image versions.
The test passes with the script and fails before it exists on pre-fix source.

Docker is unavailable locally. CI must verify the complete image build and retain
`/app/build-info.json` as the actual build receipt. The full smoke executes solves
and remains outside this lane's zero-solves execution constraint. Image packaging
requires elevated independent review (SWE Excellence Framework F.2/O.1).
Rollback: revert the runtime pin/provenance commit; the prior Node packaging fix
and shared browser model remain separately committed.
