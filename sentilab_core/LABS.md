# Fixture-only lab seam (SLAB-013/014)

`labs.Lab` defines async `propose`, `review` and `repair` methods. Each receives
an immutable `Request` containing bounded JSON context and core-selected envelope
bindings. It receives no oracle, ledger, gate or signer. The three version-1
schemas in `schemas/` reject unknown fields, roles, versions and event-shaped
output. The runtime also checks canonical UTF-8 size (16 KiB), finite numbers,
nesting and string caps before schema validation. Geometry places the frozen
chiplet catalog; it cannot resize chiplets, change the substrate or set outcomes.

`ReplayLab` reads local canned templates. `fixtures/labs/` contains OpenAI,
Claude, Grok and Kimi family examples plus negative wire examples. The only
template substitutions are `$target_hash`, `$review_hash` and `$judge_role`.
Ordinal-based selection is repeatable after restart. These family labels are
configuration, not claims of available endpoints, model calibration or access.

`dispatch.Registration` assigns lab identity, model family and a judge role
(`constraint_auditor`, `numerical_skeptic`, `reproducibility_auditor`). A judge
cannot review its own family, even under another lab ID. Reviews bind the target
candidate's **signed envelope hash**. Author repairs bind that same target and
the **signed review envelope hash**. A concern, no-concern or abstention is an
advisory opinion; none grants admission authority.

`Dispatcher.round()` gives every participating lab one opportunity and rotates
the starting lab each round. At most four calls run globally and at most two per
lab. Calls have per-lab call, token-unit and wall-time ceilings. For fixture
accounting, one canonical input byte is one conservative token unit, plus a
reservation for the entire output byte cap. Each call charges its full timeout
as a wall-time reservation. Reservations are never refunded on success, error,
timeout or cancellation; these are conservative ceilings, not measured model
usage or cost. Invalid responses, exhausted budgets and invalid assignments
produce refusal records without retries. Async adapters must cooperate with
cancellation; this is not isolation for hostile Python code. Live workers need
process isolation, real usage accounting and SLAB-039 approval in a later change.

The conductor hook requires both `enable_replay_labs=True` and a `Dispatcher`
of exact `ReplayLab` instances, plus an injected CPU fixture oracle. It refuses
the default native oracle and ReplayLab subclasses. No service or CLI flag
enables live model calls. The default AI-off baseline path is unchanged.

After the initial baseline, each tick gives the next registered lab one proposal
slot. A valid proposal enters the existing candidate/evaluate/reproduce/gate
path. A refused proposal falls back to the existing baseline operator for that
slot, letting later labs continue. One rotating cross-family reviewer and an
author repair run for each lab candidate. Reviews and repairs are signed
`node.create` source records only; repairs are not applied automatically. The
existing `AcceptanceGate` alone writes board outcomes. All output remains
labeled AI off, diagnostic integration and provisional margin.

Reservations are signed before adapter invocation. Opening an existing run
reconstructs spend from those records, including interrupted calls. Lab budgets,
identities, judge assignments and fixture hashes are frozen in the run config.
The finite-run solve budget continues to bound deterministic evaluations.

Run the complete fixture proof with:

```sh
python -m unittest -q sentilab_core.test_labs sentilab_core.test_lab_conductor
```

The integration test constructs the dispatcher from all four canned files and
injects the existing synthetic plate solver. It checks ten deterministic solves
(baseline plus four proposals, each evaluated and reproduced), four reviews,
four repairs, equal call allowances and gate-only outcomes with network access
disabled in the test. Other tests cover malformed messages, family independence,
all budget dimensions, cancellation and reconstruction from signed reservations.
