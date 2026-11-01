# Additive content correction, 2026-11-01

This note corrects the numerical-optimality wording in the retained DESIGN.md (lines 444 and 616 at PR66 head 609d339d)
without rewriting that design history. The open router requests zero relative MIP gap and reports HiGHS optimal
status under numerical tolerances and the declared time limit. Its retained reference records do not contain the
complete primal assignment, dual bound, achieved gap or feasibility/integrality residuals. Describe the reported
routed total with that scope; do not call it a proven optimum. Router acceptance remains separate.

The intended fresh-config branch uses a 90 mm spreader, 180 mm sink, 45 °C ambient model input and secondary path
off for the 45 mm frame. Existing generated configuration bypasses that branch, so each admitted run binds its
actual configuration. These intended values do not establish every historical run's settings.

The independent gate-zero derivation and exact source identities are summarized in web/public/agents/evidence.json.
It preserves separate native block-output, chiplet-centre-average and active-grid-peak fields. The numerical check
does not change the historical INCONCLUSIVE study or make the public challenge operational.
