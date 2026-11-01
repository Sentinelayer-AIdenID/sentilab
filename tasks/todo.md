# CI allocation transition draft

- [x] Pin current main5cedde1181141df82c57a8d7e3e24ae20220d67a and isolate this checkout.
- [x] Retain the sealed old56314 ledger review; no grant or remote write is authorized in this draft lane.
- [x] Add explicit policy objects: legacy remains the default; a new policy requires owner selection and an immutable grant digest.
- [x] Add a source-pinned read-only transition loader, exact owner-reserved slot1 path, and metadata/source validation.
- [x] Wire admission, pre-workload validation, meter and terminal witness without skipping required jobs or reopening old bootstrap.
- [x] Verify legacy controls plus new offline refusal, identity, source, concurrency and settlement controls. No native build or numerical test execution.
- [ ] Preserve local patch/head and test output for Warden's independent review; leave activation entirely to the owner.

The owner selection is configuration, not a secret. There is no installed grant, owner tag, active namespace, reservation, PR, push or CI run in this draft. Tests use synthetic owner records and fake GitHub reads/writes. The runtime loader may execute downloaded Python only after a separately supplied owner selection pins its SHA256 and the immutable grant pins every controller file. The new operator reserves exactly slot1 from authenticated first-attempt metadata before workload; ordinary admission stays closed until an owner-pinned activation commit is on main. Historical policy and settlement paths remain readable.

Author evidence: the82 existing offline tests passed together with the first12 new transition tests; the expanded14 transition tests then passed. The final frozen-source run and handoff are retained outside the implementation checkout in TASK/ci-transition-draft-20261101. Independent review and actual Actions admission remain pending. No runtime acceptance is claimed from these offline tests.
