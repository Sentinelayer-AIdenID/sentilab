"""Pure predicate fixtures for test T13 (DESIGN.md 4.10): synthetic numbers in K and mm. Every expectation is worked
out by hand from the section 4.8 algebra, never by running predicates.py. The policy is illustrative only.

A case is {"name", "policy", "bounds", "admission", "screen", "values", "expect"}, optionally with "failures" and
"expect_suppressed", and with "diagnostic" ({"hypothesis", "observed", "matched"}). In the comments d = T_c - T_R,
q0 = W_c - W_R and qr = W_c - 1.05 W_R. Unless a case says otherwise, every scenario repeats the nominal numbers.
"""
from __future__ import annotations

TARGET = "declared temperature target"
STRICT = "strict-wire thermal tolerance"
RELAXED = "r-relaxed-wire thermal tolerance"
THERMAL = "strict thermal improvement"
WIRE = "strict wire improvement"
TRADE = "wire improvement with allowed thermal degradation"
DOMINANCE = "robust dominance over R"
LABELS = (TARGET, STRICT, RELAXED, THERMAL, WIRE, TRADE, DOMINANCE)
PASS, BOUNDED = "passes the listed sensitivity cases", "bounded"
INCOMPLETE, INCONCLUSIVE, UNKNOWN = "INCOMPLETE", "INCONCLUSIVE", "UNKNOWN"

POLICY = {"D_K": 0.5, "r": 0.05, "B_T_K": 1.0, "B_W_mm": 328.35, "T_limit_C": 85}
NULL_POLICY = {"D_K": None, "r": None, "B_T_K": None, "B_W_mm": None, "T_limit_C": None}
NO_BOUNDS = {"u_T": "UNKNOWN", "u_q": "UNKNOWN", "u_abs": "UNKNOWN"}
BOUNDS = {"u_T": 0.25, "u_q": 100.0, "u_abs": 1.0}
SCREEN = [{"id": "nominal", "applies_to": "both", "grid": 64}, {"id": "mesh-32", "applies_to": "both", "grid": 32},
          {"id": "position-2-x-plus", "applies_to": "R"}]
W_R = 16417.5  # the Ascend 910 comparator wire: 1.05 W_R = 17238.375 exactly, and B_W_mm is 2% of it
COOL_SHORT = (73.0, 75.0, 15000.0, W_R)  # d = -2, q0 = -1417.5, qr = -2238.375: every predicate holds
RELAXED_ONLY = (75.25, 75.0, 17000.0, W_R)  # d = 0.25, q0 = 582.5 > 0, qr = -238.375: the relaxed tolerance only
SAVING = (73.0, 75.0, 16000.0, W_R)  # d = -2, q0 = -417.5, qr = -1238.375
# The diagnostic recorded beside a case that names none: unexpected, so every case shows its claims surviving one.
UNEXPECTED = {"hypothesis": {STRICT: True}, "observed": {STRICT: False}, "matched": False}
FIG_6C = {RELAXED: True, STRICT: False, THERMAL: False}  # the 4.10 hypothesis for Ascend TAP-2.5D, Fig. 6(c)


def run(t_c, t_r, w_c=None, w_r=None) -> dict:
    """One observed scenario. Without wires it compares T_M only, like the mesh case."""
    return {"status": "observed", "T_c": t_c, "T_R": t_r, **({} if w_c is None else {"W_c": w_c, "W_R": w_r})}


def runs(nominal, mesh=None, position=None) -> dict:
    """The three required cases; the mesh and position cases repeat the nominal unless given."""
    return {"nominal": run(*nominal), "mesh-32": run(*(mesh or nominal[:2])),
            "position-2-x-plus": run(*(position or nominal))}


def shown(*ids, mode=PASS, r=0.05) -> list:
    return [{"id": label, "r": r if label == RELAXED else None, "mode": mode} for label in ids]


def hidden(*ids, by) -> list:
    return [{"id": label, "r": 0.05 if label == RELAXED else None, "by": by} for label in ids]


def case(name, values, expect, **inputs) -> dict:
    return {"name": name, "policy": POLICY, "bounds": NO_BOUNDS, "admission": True, "screen": SCREEN,
            "values": values, "expect": expect} | inputs


# Bounded where the bounds allow. Upper values: T_c 74, d -1.75, q0 -317.5, qr -1138.375. The q0 upper is above -B_W,
# so the two B_W labels fall to the screen, where the estimated q0 = -417.5 holds.
MIXED = shown(TARGET, STRICT, RELAXED, THERMAL, mode=BOUNDED) + shown(WIRE, TRADE) + shown(DOMINANCE, mode=BOUNDED)
VS_R_UNKNOWN = shown(STRICT, RELAXED, THERMAL, WIRE, TRADE, DOMINANCE, mode=UNKNOWN)  # the six comparisons with R
FAILED_MESH = {"nominal": run(*COOL_SHORT), "mesh-32": {"status": "failed"}}  # and the position case absent


def cases() -> list:
    return [
        # Each label, positive and negative.
        case("cooler and shorter: every label holds", runs(COOL_SHORT), shown(*LABELS)),
        # d = 0, q0 = 0, qr = -820.875: both tolerances hold; no gain, so no improvement and no dominance.
        case("R against itself with identical measurements: the only place R cancels",
             runs((75.0, 75.0, W_R, W_R)), shown(TARGET, STRICT, RELAXED)),
        case("within 1.05 W_R and 0.25 K warmer: the relaxed tolerance only", runs(RELAXED_ONLY),
             shown(TARGET, RELAXED)),
        # d = -1 = -B_T, but q0 = 1582.5 and qr = 761.625: every wire condition fails.
        case("beyond 1.05 W_R though cooler by exactly B_T", runs((74.0, 75.0, 18000.0, W_R)), shown(TARGET)),
        # T_c = 86 > 85; d = 0.5 = D holds; d > 0 fails the thermal gain, the strict wire gain and dominance.
        case("over the temperature target and warmer by exactly D", runs((86.0, 85.5, 15000.0, W_R)),
             shown(STRICT, RELAXED, TRADE)),
        # d = 1 > D: no tolerance and no allowed degradation, despite q0 = -1417.5.
        case("warmer than D despite a wire saving", runs((76.0, 75.0, 15000.0, W_R)), shown(TARGET)),
        # d = -1, q0 = -317.5 > -328.35, qr = -1138.375.
        case("a wire saving short of B_W", runs((74.0, 75.0, 16100.0, W_R)),
             shown(TARGET, STRICT, RELAXED, THERMAL, DOMINANCE)),

        # Exact boundaries: equality holds.
        # q0 = 0 and qr = -820.875; dominance holds by d < 0 alone.
        case("boundary: T_c = T_limit, d = -B_T and q0 = 0", runs((85.0, 86.0, W_R, W_R)),
             shown(TARGET, STRICT, RELAXED, THERMAL, DOMINANCE)),
        # q0 = 820.875 > 0.
        case("boundary: qr = 0 and d = D", runs((75.5, 75.0, 17238.375, W_R)), shown(TARGET, RELAXED)),
        # 671.65 - 1000.0 = -328.35; qr = -378.35. d = 0 at nominal and in the position case; d = -0.5 at grid 32.
        case("boundary: q0 = -B_W and d = 0", runs((75.0, 75.0, 671.65, 1000.0), mesh=(74.5, 75.0)),
             shown(TARGET, STRICT, RELAXED, WIRE, TRADE, DOMINANCE)),
        # The same tie through exact decimals: 1024.15 - 1352.5 is -328.35 in decimal but -328.3499999999999 in binary64,
        # which would miss the boundary. qr = -395.975.
        case("boundary: an exact decimal tie at q0 = -B_W holds", runs((75.0, 75.0, 1024.15, 1352.5),
                                                                        mesh=(74.5, 75.0)),
             shown(TARGET, STRICT, RELAXED, WIRE, TRADE, DOMINANCE)),

        # The screen.
        # COOL_SHORT at nominal; d = 0.25 at grid 32 fails every thermal gain but stays within D.
        case("grid 32 undoes the thermal gain", runs(COOL_SHORT, mesh=(75.25, 75.0)),
             shown(TARGET, STRICT, RELAXED, TRADE)),
        # d = -2 everywhere, but T_c = 85.5 > 85 at grid 32.
        case("grid 32 puts c over the temperature target", runs((84.0, 86.0, 15000.0, W_R), mesh=(85.5, 87.5)),
             shown(STRICT, RELAXED, THERMAL, WIRE, TRADE, DOMINANCE)),
        # d = 0 everywhere, q0 = -417.5, qr = -1238.375. Grid 32 keeps the nominal wire, so its strict gain is q0 < 0.
        case("the mesh case keeps the nominal wire: dominance by the wire alone", runs((75.0, 75.0, 16000.0, W_R)),
             shown(TARGET, STRICT, RELAXED, WIRE, TRADE, DOMINANCE)),
        # Nominal d = -1 and q0 = 0. At grid 32 d = 0 with the same wire: no strict gain, and d > -B_T.
        case("a tie in both values at grid 32 is not dominance", runs((74.0, 75.0, W_R, W_R), mesh=(75.0, 75.0)),
             shown(TARGET, STRICT, RELAXED)),
        # SAVING alone would give every label. The perturbed R routes 15800 mm: q0 = 200 and qr = -590 there.
        case("a perturbed R that routes shorter changes the wire outcome",
             runs(SAVING, position=(73.0, 75.0, 16000.0, 15800.0)), shown(TARGET, RELAXED)),
        # Identity cancels at nominal and grid 32 only; the position case has d = 75.0 - 74.4 = 0.6 > D.
        case("R against itself: a position case moves T_M by more than D",
             runs((75.0, 75.0, W_R, W_R), position=(75.0, 74.4, W_R, W_R)), shown(TARGET)),

        # Bounded.
        case("bounded where the bounds allow, the screen elsewhere", runs(SAVING), MIXED, bounds=BOUNDS),
        # Upper values: T_c 84.5 + 0.5 = 85 = T_limit, d 0.25 + 0.25 = 0.5 = D, q0 -100 + 100 = 0, qr -820.875.
        # The estimated d = 0.25 and q0 = -100 fail every other predicate.
        case("bounded at its boundaries", runs((84.5, 84.25, 16317.5, W_R)),
             shown(TARGET, STRICT, RELAXED, mode=BOUNDED), bounds={"u_T": 0.25, "u_q": 100.0, "u_abs": 0.5}),
        case("an unknown u_T: only the target can be bounded", runs(SAVING),
             shown(TARGET, mode=BOUNDED) + shown(STRICT, RELAXED, THERMAL, WIRE, TRADE, DOMINANCE),
             bounds=BOUNDS | {"u_T": "UNKNOWN"}),

        # INCOMPLETE and INCONCLUSIVE, the same for every label.
        case("a required position case absent: INCOMPLETE, even with bounds",
             {"nominal": run(*COOL_SHORT), "mesh-32": run(73.0, 75.0)}, shown(*LABELS, mode=INCOMPLETE),
             bounds=BOUNDS),
        case("a required case reported missing: INCOMPLETE", runs(COOL_SHORT) | {"mesh-32": {"status": "missing"}},
             shown(*LABELS, mode=INCOMPLETE)),
        case("a failed case: INCONCLUSIVE, over a missing one", FAILED_MESH, shown(*LABELS, mode=INCONCLUSIVE)),

        # UNKNOWN.
        case("no numerical admission: UNKNOWN", runs(COOL_SHORT), shown(*LABELS, mode=UNKNOWN), admission=False),
        case("no numerical admission outranks a failed case", FAILED_MESH, shown(*LABELS, mode=UNKNOWN),
             admission=False),
        case("W UNKNOWN: no proven routing optimum", runs((73.0, 75.0, "UNKNOWN", W_R)), shown(TARGET) + VS_R_UNKNOWN),
        case("T_R UNKNOWN: R not yet run under the admitted evaluator", runs((73.0, "UNKNOWN", 15000.0, W_R)),
             shown(TARGET) + VS_R_UNKNOWN),
        case("T_c UNKNOWN at grid 32: the target reads it too", runs(COOL_SHORT, mesh=("UNKNOWN", 75.0)),
             shown(*LABELS, mode=UNKNOWN)),
        case("T_c UNKNOWN in an R-only case: the target does not read it",
             runs(COOL_SHORT, position=("UNKNOWN", 75.0, 15000.0, W_R)), shown(TARGET) + VS_R_UNKNOWN),
        case("a None policy value: D_K", runs(COOL_SHORT),
             shown(TARGET) + shown(STRICT, RELAXED, mode=UNKNOWN) + shown(THERMAL, WIRE) + shown(TRADE, mode=UNKNOWN)
             + shown(DOMINANCE), policy=POLICY | {"D_K": None}),
        case("the draft manifest's null policy: dominance alone reads no policy field", runs(COOL_SHORT),
             shown(TARGET, STRICT, RELAXED, THERMAL, WIRE, TRADE, mode=UNKNOWN, r=None) + shown(DOMINANCE),
             policy=NULL_POLICY),

        # Suppression.
        case("failed gate zero suppresses every label", runs(COOL_SHORT), shown(*LABELS),
             failures=[{"by": "failed gate zero", "label": None}],
             expect_suppressed=hidden(*LABELS, by="failed gate zero")),
        case("failed binding suppresses every label", runs(RELAXED_ONLY), shown(TARGET, RELAXED),
             failures=[{"by": "failed binding", "label": None}],
             expect_suppressed=hidden(TARGET, RELAXED, by="failed binding")),
        case("a failed predicate fixture suppresses only its label", runs(COOL_SHORT), shown(*LABELS),
             failures=[{"by": "failed predicate fixture", "label": THERMAL}],
             expect_suppressed=hidden(THERMAL, by="failed predicate fixture")),
        case("a failed required scenario suppresses the screen's labels, not the bounded ones", runs(SAVING), MIXED,
             bounds=BOUNDS, failures=[{"by": "failed required scenario", "label": None}],
             expect_suppressed=hidden(WIRE, TRADE, by="failed required scenario")),
        case("two reasons: the first in the manifest's order is recorded", runs(RELAXED_ONLY), shown(TARGET, RELAXED),
             failures=[{"by": "failed required scenario", "label": None}, {"by": "failed binding", "label": None}],
             expect_suppressed=hidden(TARGET, RELAXED, by="failed binding")),
        case("a failed predicate fixture that names no label suppresses every label", runs(RELAXED_ONLY),
             shown(TARGET, RELAXED), failures=[{"by": "failed predicate fixture", "label": None}],
             expect_suppressed=hidden(TARGET, RELAXED, by="failed predicate fixture")),

        # Scientific diagnostics: recorded beside the claims, never instead of them.
        case("an unexpected diagnostic leaves the claims visible", runs(RELAXED_ONLY), shown(TARGET, RELAXED),
             diagnostic={"hypothesis": FIG_6C, "observed": {RELAXED: False, STRICT: False, THERMAL: False},
                         "matched": False}),
        case("an expected diagnostic, judged on its hypothesised predicates only", runs(COOL_SHORT), shown(*LABELS),
             diagnostic={"hypothesis": FIG_6C,
                         "observed": {TARGET: True, STRICT: False, RELAXED: True, THERMAL: False, WIRE: False,
                                      TRADE: False, DOMINANCE: False},
                         "matched": True}),
    ]
