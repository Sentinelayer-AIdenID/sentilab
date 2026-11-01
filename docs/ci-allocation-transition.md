# CI allocation transition — local draft, inactive

This source supplies a path for testing a replacement allocation controller when
the old allocation is exhausted. It does not issue a grant. No owner selection,
namespace, tag, reservation or activation is installed by this change. The
existing `56314` constants, bootstrap exception, immutable records and terminal
validation remain available. No existing reservation is refunded or reused.

## Trust and accounting

The owner supplies the repository variable `CI_ALLOCATION_SELECTION`, using the
exact schema in `scripts/ci_policy.py`. Its allocation ID must differ from
`56314`; it pins a bootstrap commit SHA, canonical grant SHA256, approved source
commit SHA, loader SHA256 and a nullable activation commit SHA. This variable is
configuration, not a credential. Missing selection follows the existing legacy
path; malformed selection refuses instead of falling back to another grant.

The lightweight `ci-allocation-<id>/bootstrap` tag points to an immutable commit
whose message is the exact `ci-allocation-grant-v2` JSON object. Its canonical
digest is SHA256 of UTF-8 `json.dumps(value, sort_keys=True,
separators=(',', ':'), allow_nan=False)`, with no trailing newline. Duplicate
JSON keys and nonfinite values are refused. The schema requires:

- Actual prospective authorization ID and approver, repository and workflow.
- Explicit integer `not_before`, `expires_at`, run cap at most150, exactly100
  launches and900 container CPU-seconds per run. There is no default renewal
  date, grant ID, approval or dollar estimate.
- A zero debit in the new namespace, while preserving predecessor56314, its
  exact bootstrap SHA, all200 accounted runs and the owner's closure hash.
- Exact transition head/base SHAs and slot1. The transition consumes one of the
  new run cap; it is not an extra bootstrap allowance.
- SHA256 hashes for all12 controller/workflow files enumerated by `SOURCE_FILES`.
  The bootstrap grant is outside this source manifest, avoiding a self-hash loop.
- A real repository ruleset ID. Admission checks active tag protection for the
  exact new namespace, no excludes or bypass actors, and update/deletion/
  non-fast-forward prohibitions. A broad or inactive ruleset is refused.

The grant digest authenticates owner input; it does not establish that an
approver string itself is an independently verified human identity. The owner
must issue the grant and independently stage its repository selection. CI jobs
receive only read credentials; only the trusted default-branch writer and the
separate operator process can create reservation refs.

## Prospective operator sequence, requiring independent review first

1. Review and publish the exact transition source on a branch, without changing
   the old allocation. Pin the then-current main base. Create the new protected
   namespace and actual prospective owner grant; retain the old closure evidence.
2. Set the selection before creating the transition PR/run. Use the reviewed
   source and loader hashes, and `activation_sha: null`. A variable added after
   run creation may not be visible to that run. This design requires a fresh
   first attempt; it never treats a retry of an old workflow as new source.
3. When the exact CI run exists, invoke from the independently reviewed local
   source using an owner credential supplied through the existing secure
   environment, not chat:

   `python3 -m scripts.ci_transition reserve-transition <receipt-path> --run-id <actual-run-id>`

   The command refuses a GitHub Actions context. It authenticates the live run,
   open PR, current-main merge, exact head/base/build, attempt1 and source tree;
   verifies old200 closure and new namespace protection; then atomically claims
   only slot1. An existing slot, race or lost response never spills into slot2.
   Retain the operator receipt and immutable ref even if the workflow refuses.
4. The PR's admission step verifies the downloaded loader against the independent
   owner hash before execution. The loader verifies all12 pinned source blobs
   before writing/importing them, then reads the exact reservation. Container
   validation fetches owner source independently and re-reads the reservation.
   Only after validation does the normal checkout and metered build/smoke suite
   run. The meter imports verified controller files with isolated Python, and
   preserves the selected policy through `sudo`. Required `container`,
   `contracts`, and `secret-scan` checks still have to succeed normally.
5. Before the new default-branch settlement workflow is installed, retain a
   terminal witness with the reviewed controller's read-only `terminal` mode.
   Supply the authenticated completed workflow event in `GITHUB_EVENT_PATH`,
   `GITHUB_REPOSITORY`, read-only `GH_TOKEN`, the independently staged selection,
   and an output directory containing any downloaded `download/settlement.json`:

   `python3 -m scripts.ci_transition terminal <terminal-directory>`

   Missing, invalid or foreign measurements remain unknown and charged; no
   downloaded artifact code is executed. Retain the original default-branch
   witness as well. This command is not an upload or a refund.
6. After the exact transition checks pass, merge normally. Then the owner may
   set `activation_sha` to the actual approved merge commit. Ordinary admission
   verifies approved-source ancestry, that activation is on current main, the
   pinned controller bytes, the retained slot1, and the transition run's actual
   successful `container`, `contracts` and `secret-scan` jobs. Subsequent runs
   use slots2 onward. A main push created before activation can still refuse;
   activation does not reopen it or authorize an attempt2.

## Refusal and platform boundaries

The operator must reserve within the admission reader's180-second window after
its controller verification; the job's five-minute timeout also applies. The
window is not a reservation retry allowance. If a reserved transition fails,
expires or is cancelled, its slot remains charged. This draft deliberately does
not invent another bridge slot or a retry grant. An owner must review any next
allocation/source plan prospectively.

No admin bypass is needed in the design: the transition's PR workflow can load
reviewed source and read an owner-created slot while the old default writer
remains exhausted. However, the draft has only offline evidence. Live Actions
permissions, variable visibility, read access to rulesets/commit blobs, slot
creation protections, actual job timing and containment still require an
independently admitted trial. A host or organization policy that prevents these
reads/creation is a real operational impasse, not permission to skip checks.

The selected controller and workflow bytes stay pinned for the allocation.
Changes to those12 files require renewed owner review/input; ordinary application
code may change while the pinned controller verifies each run's exact build.
Keep the owner selection/grant and old bootstrap provenance available for late
settlement. Both namespaces are read after expiry. Cross-policy duplicates are
reported as ambiguous, with both reservations charged; an unavailable namespace
cannot turn the other run's usage into a measured zero.

The150×900 envelope is37.5 container CPU-hours of reservation. It is not total
runner CPU,70-job-minute workflow-chain capacity, GPU time, a price quotation or
current spend. Native solves and experiment allowances are separate from this
local implementation proof.

## Offline evidence

`scripts/tests/test_ci_transition.py` uses explicitly synthetic grants, local
source blobs, fake GitHub reads/writes, fake clocks and temporary journals. It
checks old exhaustion, exact identity/source/protection refusal, loader hashes,
slot1 conflicts/lost replies, the cap including the bridge, activation and
ordinary slot2 admission, and dual-policy terminal accounting. Existing
allocation, workflow, handoff, meter and bootstrap tests remain required.

The offline test selection excludes `test_ci_gate.py`, which compiles a native
test executable. No solver, Docker build, model job, CI job or GitHub mutation
is part of this local proof.
