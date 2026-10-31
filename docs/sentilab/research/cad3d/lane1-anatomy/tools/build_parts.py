"""Generate lane1-anatomy/parts.json from the verified fact table.

Usage: python -I build_parts.py <lane1-anatomy dir>
Every number below carries fact ids (evidence/<lane>/FACTS.jsonl) or a repo citation, or is marked
derived (with the inputs) or render_hint (illustrative, NOT sourced).
"""
import csv
import json
import os
import sys

OUT = sys.argv[1]
EV = os.path.join(OUT, "evidence")
REPO_SHA = "46791be360555d0e24b4ad5f906abafb71f07118"

FACT = {}
for lane in ("hbm", "packaging", "thermal", "products"):
    with open(os.path.join(EV, lane, "FACTS.jsonl"), encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                rec = json.loads(line)
                FACT[rec["fact_id"]] = rec


def S(*ids):
    out = []
    for i in ids:
        if i not in FACT:
            raise SystemExit(f"unknown fact {i}")
        out.append({"fact": i, "source": os.path.basename(FACT[i]["file"]).split(".")[0]})
    return out


def R(path, lines):
    return {"repo": f"H:/sentilab@origin/main {REPO_SHA[:7]}", "path": path, "lines": lines}


def T(mn=None, typ=None, mx=None, **kw):
    d = {"min": mn, "typical": typ, "max": mx}
    d.update(kw)
    return d


def C(*pairs):
    return [{"id": i, "type": t} for i, t in pairs]


TH, PW, SG, ME = "thermal", "power", "signal", "mechanical"

parts = []


def P(**kw):
    base = dict(id=None, name=None, parent=None, stack_order=None, count=1, material=None, thickness_um=None,
                lateral_mm=None, k_W_per_mK=None, function=None, connects_to=[], sources=[], confidence=None,
                variant="all", in_our_model=None, notes="")
    base.update(kw)
    parts.append(base)


# ------------------------------------------------------------------ board level
P(id="system_board", name="System board (PCB / OAM / SXM carrier)", parent=None, stack_order=0, count=1,
  material="Multilayer glass-epoxy PCB with copper power and ground planes",
  thickness_um=T(None, None, None, render_hint=2000, render_hint_basis="HotSpot secondary-path default t_pcb = 2 mm in our config (model default, not a product value)"),
  lateral_mm={"pattern": "board area around and under the package; carries VRMs and bypass capacitors"},
  k_W_per_mK={"value": None, "notes": "not sourced; Cu planes make in-plane k much higher than through-plane"},
  function="Mechanical carrier; delivers the core and HBM rails from the VRMs; routes off-package I/O; minor heat sink for the secondary path.",
  connects_to=C(("bga_balls", [PW, SG, TH, ME]), ("vrm_lateral", [PW]), ("vrm_vertical", [PW]), ("board_bypass_caps", [PW])),
  sources=S("pkg-044", "thm-012", "thm-035"), confidence="low",
  in_our_model={"modeled": False, "detail": "model_secondary = 0, so no PCB, solder or package-substrate secondary layers are built", "cite": [R("sundai_tap/util/hotspot.config", "48, 72-74")]},
  notes="Board-side lateral I2R loss is >= 50 W with lateral VRs (pkg-044). Purdue FEM model lumps the PCB side as 20 K/W (thm-035).")

P(id="vrm_lateral", name="Voltage regulators, lateral (multiphase buck around the package)", parent="system_board", stack_order=0,
  count=30, material="Power stages, inductors, controllers on the board",
  thickness_um=None, lateral_mm={"pattern": "ring of 30+ VR phases arranged around the processor footprint"},
  k_W_per_mK=None,
  function="Convert the board bus to the sub-1 V core rail (and 1.1-1.2 V HBM rail) at ~1000 A continuous with dI/dt >= 2000 A/us.",
  connects_to=C(("system_board", [PW, TH])), sources=S("pkg-044", "pkg-041", "pkg-042", "pkg-043"), confidence="medium",
  in_our_model={"modeled": False}, notes="count = 'thirty or more' phases (vendor article, Vicor). Core VDD as low as 0.7 V, +/-5%.")

P(id="vrm_vertical", name="Voltage regulator, vertical (module under the package, opposite board side)", parent="system_board", stack_order=-1,
  count=1, material="High-current-density VR module (~1 A/mm2 state of the art)", thickness_um=None,
  lateral_mm={"pattern": "inside the bypass-capacitor field beneath the package; ~3,500 mm2 package footprint quoted"},
  k_W_per_mK=None, variant="vertical_power_delivery",
  function="Shortens the PDN: moving one PoL module under the processor cut lumped PDN impedance from 60 to 11 uOhm in a vendor test.",
  connects_to=C(("system_board", [PW])), sources=S("pkg-045", "pkg-043"), confidence="medium", in_our_model={"modeled": False},
  notes="Optional variant; lateral and lateral-vertical schemes coexist.")

P(id="board_bypass_caps", name="Board bypass capacitors under the processor", parent="system_board", stack_order=-1,
  count=None, material="MLCC array", thickness_um=None, lateral_mm={"pattern": "fills the PCB area beneath the processor"},
  k_W_per_mK=None, function="Supply charge for fast load steps; >= 3 mF for a 1000 A TDC processor.",
  connects_to=C(("system_board", [PW])), sources=S("pkg-043"), confidence="medium", in_our_model={"modeled": False})

# ------------------------------------------------------------------ package
P(id="package", name="2.5D package assembly (CoWoS-class)", parent=None, stack_order=None, count=1,
  material="assembly", thickness_um=None,
  lateral_mm={"w": None, "h": None, "pattern": "substrate body 55-130 mm square depending on generation (see package_substrate)"},
  function="Container for everything from BGA balls to lid.", connects_to=C(("system_board", [PW, SG, TH, ME])),
  sources=S("pkg-001", "pkg-007", "pkg-033"), confidence="high", in_our_model={"modeled": True, "detail": "TAP passive-interposer system"},
  notes="Variants: lidded vs lidless; Si interposer (CoWoS-S) vs RDL interposer (CoWoS-R) vs RDL + local Si bridges (CoWoS-L / EMIB).")

P(id="bga_balls", name="BGA solder balls", parent="package", stack_order=1, count=None,
  material="Solder balls (SAC-family assumed; k from SAC305 data)",
  thickness_um=T(310, None, 600, render_hint=450, render_hint_basis="midpoint of cited stand-off range (derived)"),
  lateral_mm={"pattern": "full area array, pitch 0.8-1.0 mm; ball diameter 0.5-0.6 mm",
              "pitch_mm": [0.8, 1.0], "ball_diameter_mm": T(0.4, None, 0.7, nominals=[0.5, 0.6], notes="0.50 nominal (Microchip 15 mm FCBGA), 0.600 nominal (IDT 29 mm FCBGA)")},
  k_W_per_mK={"value": 58, "notes": "bulk SAC305; the ball layer as a whole is mostly air/underfill-free gap"},
  function="Second-level interconnect: power, ground and I/O between substrate and board; mechanical attach.",
  connects_to=C(("substrate_buildup_bottom", [PW, SG, TH, ME]), ("system_board", [PW, SG, TH, ME])),
  sources=S("pkg-022", "pkg-018", "pkg-049", "pkg-050", "pkg-027", "thm-025"), confidence="medium",
  in_our_model={"modeled": False, "detail": "secondary path disabled", "cite": [R("sundai_tap/util/hotspot.config", "48, 68-70")]},
  notes="Ball counts: 3,136 balls for a 55 mm body at 1.0 mm full array (pkg-027); a 90-110 mm body allows up to (90/1)^2 = 8,100 to (110/1)^2 = 12,100 sites at 1.0 mm (derived upper bound, not a product count). Diameter values from small FCBGA drawings (15 mm and 29 mm bodies).")

P(id="land_side_caps", name="Land-side capacitors (substrate bottom)", parent="package", stack_order=1, count=None,
  material="MLCC / silicon capacitors", thickness_um=None, lateral_mm={"pattern": "in the BGA field under the die shadow"},
  k_W_per_mK=None, function="Package-level decoupling close to the die.", connects_to=C(("substrate_buildup_bottom", [PW])),
  sources=[], confidence="low", in_our_model={"modeled": False},
  notes="Included for anatomy completeness; NO source captured in this evidence pack. Do not show numbers.")

P(id="package_substrate", name="Package substrate (FCBGA, ABF build-up on organic core)", parent="package", stack_order=None, count=1,
  material="Glass-reinforced resin (BT/epoxy) core + ABF build-up dielectric + Cu layers",
  thickness_um=T(None, None, None, notes="core 400-1600 um (thin core 150-250 um); total stack not sourced"),
  lateral_mm={"w": None, "h": None, "range_mm": [55, 130], "pattern": "square body; 90 x 90 mm (2026) to 130 x 130 mm (roadmap); 110 mm square already used for a 2.5x-reticle InFO_oS in 2021"},
  k_W_per_mK={"core": 0.8, "build_up_dielectric": 0.35, "solder_mask": 0.24, "notes": "dielectric values; Cu planes raise effective in-plane k (not sourced)"},
  function="Fans out from C4 pitch (~90-210 um) to BGA pitch (0.8-1.0 mm); distributes power/ground planes; mechanical base.",
  connects_to=C(("c4_bumps", [PW, SG, TH, ME]), ("bga_balls", [PW, SG, TH, ME]), ("stiffener_ring", [ME]), ("lid", [ME, TH])),
  sources=S("pkg-048", "pkg-032", "pkg-031", "pkg-033", "pkg-047", "pkg-017", "thm-015", "thm-014", "thm-013", "pkg-018"), confidence="medium",
  in_our_model={"modeled": True, "layer": "L0 'substrate'", "detail": "200 um, k = 0.30 W/mK, footprint = interposer (45 or 50 mm); bottom adiabatic", "cite": [R("sundai_tap/passive_interposer.py", "50-56, 144")]},
  notes="Build-up 9/x/9 to 10/x/10 in volume, 12/x/12 and 14/x/14 on roadmaps; Xilinx 2011 SSIT used 4-2-4 with 1.0 mm BGA pitch.")

P(id="substrate_buildup_bottom", name="Substrate build-up layers (bottom side)", parent="package_substrate", stack_order=2,
  count=10, material="ABF dielectric + patterned Cu, laser microvias",
  thickness_um=T(None, None, None, render_hint=300, render_hint_basis="illustrative, NOT sourced (layer thickness not captured)"),
  lateral_mm={"pattern": "full substrate body"}, k_W_per_mK={"dielectric": 0.35, "solder_mask": 0.24},
  function="BGA-side routing and power planes.", connects_to=C(("substrate_core", [PW, SG, TH, ME]), ("bga_balls", [PW, SG, TH, ME])),
  sources=S("pkg-031", "pkg-047", "thm-014", "thm-013"), confidence="medium", in_our_model={"modeled": False, "detail": "lumped into L0"},
  notes="count = build-up layers per side (10/x/10 class).")

P(id="substrate_core", name="Substrate core", parent="package_substrate", stack_order=3, count=1,
  material="Glass-fabric reinforced resin (BT/epoxy) copper-clad laminate with plated through holes",
  thickness_um=T(150, None, 1600, notes="conventional 400-1600 um; thin core 150-250 um", render_hint=800, render_hint_basis="within cited conventional range (illustrative)"),
  lateral_mm={"pattern": "full substrate body"}, k_W_per_mK={"value": 0.8, "notes": "organic core, room temperature"},
  function="Mechanical rigidity; through holes connect top and bottom build-ups.",
  connects_to=C(("substrate_buildup_bottom", [PW, SG, TH, ME]), ("substrate_buildup_top", [PW, SG, TH, ME])),
  sources=S("pkg-032", "pkg-048", "thm-015"), confidence="medium", in_our_model={"modeled": False, "detail": "lumped into L0"},
  notes="Glass-core substrates are on industry roadmaps (pkg-048 source).")

P(id="substrate_buildup_top", name="Substrate build-up layers (die side)", parent="package_substrate", stack_order=4,
  count=10, material="ABF dielectric + patterned Cu, fine line/space under the interposer",
  thickness_um=T(None, None, None, render_hint=300, render_hint_basis="illustrative, NOT sourced"),
  lateral_mm={"pattern": "full body; finest L/S (9/12 um now, 6/6 um roadmap) in the flip-chip area"},
  k_W_per_mK={"dielectric": 0.35}, function="Escape routing from C4 field; power/ground planes.",
  connects_to=C(("substrate_core", [PW, SG, TH, ME]), ("c4_bumps", [PW, SG, TH, ME]), ("die_side_caps", [PW])),
  sources=S("pkg-031", "pkg-034", "thm-014"), confidence="medium", in_our_model={"modeled": False, "detail": "lumped into L0"})

P(id="die_side_caps", name="Die-side capacitors (substrate top, around the interposer)", parent="package_substrate", stack_order=5,
  count=None, material="MLCC", thickness_um=None, lateral_mm={"pattern": "ring around the interposer footprint"}, k_W_per_mK=None,
  function="Package decoupling.", connects_to=C(("substrate_buildup_top", [PW])), sources=[], confidence="low",
  in_our_model={"modeled": False}, notes="NO source captured; anatomy placeholder only.")

P(id="stiffener_ring", name="Stiffener ring (lidless variant)", parent="package", stack_order=5, count=1,
  material="Metal frame (material not sourced here)", thickness_um=None,
  lateral_mm={"pattern": "ring around the die area on the substrate top; top surface may sit higher than the die"},
  k_W_per_mK=None, variant="lidless",
  function="Keeps large lidless packages flat and protects the die edge; lets the heat sink contact the die directly.",
  connects_to=C(("substrate_buildup_top", [ME])), sources=S("pkg-024", "pkg-039", "pkg-040"), confidence="medium",
  in_our_model={"modeled": False})

P(id="c4_bumps", name="C4 bumps (interposer-to-substrate)", parent="package", stack_order=5, count=None,
  material="Cu C4 / Cu pillar with SnAg cap, or Pb-free SnAg solder",
  thickness_um=T(40, 50, 100, notes="Cu pillar ~40 um; standard bump 60-100 um high; 50 um Cu pillar layer in a published FEM stack"),
  lateral_mm={"pattern": "full area array under the interposer", "pitch_um": [90, 210], "diameter_um": [80, 125]},
  k_W_per_mK={"cu": 389, "solder_sac305": 58, "derived_layer_estimate": "~14 W/mK (parallel model: bump area fraction ~0.24 for 100 um bumps at 180 um pitch, solder 58, underfill 0.6; derived, illustrative)"},
  function="First-level interconnect from interposer TSVs to substrate: all power, ground and off-package I/O.",
  connects_to=C(("interposer_silicon", [PW, SG, TH, ME]), ("substrate_buildup_top", [PW, SG, TH, ME]), ("c4_underfill", [ME, TH])),
  sources=S("pkg-013", "pkg-028", "pkg-029", "pkg-054", "pkg-053", "pkg-016", "pkg-021", "pkg-018", "pkg-034", "thm-029", "thm-013", "thm-025"), confidence="medium",
  in_our_model={"modeled": True, "layer": "L1 'C4 layer'", "detail": "70 um; 250 um 'copper' bumps on a 600 um cell, k_eff = 70.8 W/mK (17.4% Cu)", "cite": [R("sundai_tap/passive_interposer.py", "31-32, 37, 40, 59-65, 145")]},
  notes="Pitch examples: 130 um (InFO Cu bump; Amkor array minimum), 180 um (Xilinx 2011 test vehicle), 210 um (Virtex-7 SSIT); substrate bump pitch roadmap 130 -> 110 -> 90 um.")

P(id="c4_underfill", name="C4 underfill", parent="package", stack_order=5, count=1,
  material="Epoxy capillary underfill (silica filled)", thickness_um=T(40, None, 100, notes="equals C4 stand-off"),
  lateral_mm={"pattern": "fills the C4 field under the interposer, with fillet"}, k_W_per_mK={"value": 0.6},
  function="Buffers the interposer-substrate CTE mismatch; protects C4 joints.",
  connects_to=C(("c4_bumps", [ME, TH]), ("interposer_silicon", [ME, TH]), ("substrate_buildup_top", [ME, TH])),
  sources=S("pkg-005", "pkg-030", "thm-023", "thm-005"), confidence="medium",
  in_our_model={"modeled": True, "layer": "L1 (mixed into C4 effective material, underfill k = 1.6 W/mK)", "cite": [R("sundai_tap/passive_interposer.py", "22, 26, 40")]})

P(id="interposer_silicon", name="Silicon interposer (CoWoS-S class) with TSVs", parent="package", stack_order=6, count=1,
  material="Passive silicon (no transistors) with Cu TSVs",
  thickness_um=T(None, 100, None, notes="thinned to reveal TSVs"),
  lateral_mm={"w": 45, "h": 45, "max_area_mm2": 2700, "pattern": "up to 3.3x reticle (~2,700 mm2) for CoWoS-S; 3.5x (CoWoS-L) in production; 45 x 45 mm in TAP-2.5D; 42 x 42 mm in a published FEM model"},
  k_W_per_mK={"silicon_room_temp": [117.5, 150], "silicon_at_100C": 112, "effective_with_tsv_in_our_model": 112.0,
              "notes": "112 at 373 K from k = 150 (T/300)^-4/3 (derived); our model uses Si = 100 plus 4% Cu"},
  function="Dense die-to-die and die-to-HBM wiring (>10,000 connections, ~20x denser than organic); carries power through TSVs; stress buffer; hosts eDTC.",
  connects_to=C(("microbumps", [PW, SG, TH, ME]), ("c4_bumps", [PW, SG, TH, ME]), ("interposer_beol_rdl", [PW, SG, TH]), ("interposer_tsv", [PW, SG, TH]), ("interposer_edtc", [PW])),
  sources=S("pkg-001", "pkg-007", "pkg-021", "thm-029", "thm-006", "pkg-020", "pkg-015", "thm-016", "thm-017", "thm-019"), confidence="high",
  in_our_model={"modeled": True, "layer": "L2 'silicon interposer'", "detail": "110 um; k_eff 112 W/mK (10 um Cu TSV on 50 um cell = 4% Cu in Si at 100 W/mK)", "cite": [R("sundai_tap/passive_interposer.py", "33-34, 38, 41, 68-74, 146")]})

P(id="interposer_tsv", name="Interposer TSVs", parent="interposer_silicon", stack_order=6, count=None,
  material="Cu-filled through-silicon vias", thickness_um=T(None, 100, None, notes="TSV depth = interposer thickness"),
  lateral_mm={"pattern": "array under C4 sites", "diameter_um": ">10", "pitch_um": 210},
  k_W_per_mK={"cu": 389}, function="Vertical power, ground and I/O through the interposer; minor thermal vias.",
  connects_to=C(("c4_bumps", [PW, SG, TH]), ("interposer_beol_rdl", [PW, SG, TH])),
  sources=S("pkg-018", "pkg-021", "thm-013"), confidence="medium",
  in_our_model={"modeled": True, "layer": "L2 (homogenised)", "detail": "10 um diameter on 50 um cell", "cite": [R("sundai_tap/passive_interposer.py", "33-34")]},
  notes="Aspect ratio ~10:1 (100 um / ~10 um, derived). Xilinx 2011 SSIT values; current CoWoS TSV geometry not public in this pack ('New TSV' in CoWoS-S gen 4, pkg-012).")

P(id="interposer_edtc", name="Embedded deep-trench capacitors (eDTC / iCap)", parent="interposer_silicon", stack_order=6, count=None,
  material="High-k deep trench capacitors etched into the interposer silicon", thickness_um=None,
  lateral_mm={"pattern": "capacitor arrays under the dies; 40 x 40 um standard cell", "density_nF_per_mm2": 340},
  k_W_per_mK=None, function="On-interposer decoupling close to the die, lowering PDN impedance.",
  connects_to=C(("interposer_beol_rdl", [PW])), sources=S("pkg-002", "pkg-046", "pkg-006", "pkg-009", "pkg-012"), confidence="medium",
  in_our_model={"modeled": False}, notes="340 nF/mm2 from a blog report of TSMC's IEDM 2019 iCap paper (secondary). CoWoS-L can also embed stand-alone eDTCs under the SoC.")

P(id="interposer_beol_rdl", name="Interposer wiring (BEOL metal / RDL) on the top face", parent="interposer_silicon", stack_order=7, count=4,
  material="Cu interconnect in oxide/low-k (Si interposer) or polymer (RDL interposer)",
  thickness_um=T(None, 10, None, notes="10 um interposer BEOL in a published FEM model"),
  lateral_mm={"pattern": "full interposer; 4 metal layers at 2 um pitch (65 nm SSIT); thick Cu '5Mi' in 2021 CoWoS-S; RDL 2/2 um L/S (CoWoS-R)"},
  k_W_per_mK={"value": None, "notes": "dielectric k not sourced here"},
  function="Routes HBM buses and die-to-die links laterally (mm-scale); distributes power to micro-bumps.",
  connects_to=C(("microbumps", [PW, SG, TH]), ("interposer_tsv", [PW, SG]), ("interposer_edtc", [PW])),
  sources=S("pkg-018", "pkg-019", "pkg-014", "pkg-003", "thm-029"), confidence="medium",
  in_our_model={"modeled": False, "detail": "not a separate layer; L2 is 110 um of TSV-silicon"})

P(id="rdl_interposer", name="Organic RDL interposer (CoWoS-R variant)", parent="package", stack_order=6, count=1,
  material="Polymer dielectric + Cu RDL", thickness_um=None,
  lateral_mm={"pattern": "replaces the Si interposer; min 4 um pitch (2/2 um L/S)"}, k_W_per_mK={"value": None, "notes": "polymer; not sourced"},
  variant="cowos_r", function="Lower-cost, flexible interposer; buffers CTE mismatch.",
  connects_to=C(("microbumps", [PW, SG, TH, ME]), ("c4_bumps", [PW, SG, TH, ME])), sources=S("pkg-003", "pkg-004", "pkg-005"), confidence="high",
  in_our_model={"modeled": False})

P(id="lsi_bridge", name="Local silicon bridge (CoWoS-L LSI / Intel EMIB variant)", parent="package", stack_order=6, count=None,
  material="Small Si die with multi-layer sub-um Cu wiring, embedded in RDL interposer or substrate", thickness_um=None,
  lateral_mm={"pattern": "under die-to-die and die-to-HBM edges only; EMIB bump pitch 55 -> 45 um"}, k_W_per_mK={"silicon": [117.5, 150]},
  variant="cowos_l_or_emib", function="Fine-pitch die-to-die / die-to-HBM wiring without a full silicon interposer.",
  connects_to=C(("microbumps", [SG, PW])), sources=S("pkg-006", "pkg-008", "pkg-035", "pkg-036"), confidence="high", in_our_model={"modeled": False})

P(id="microbumps", name="Micro-bumps (die/HBM-to-interposer)", parent="package", stack_order=8, count=None,
  material="Cu pillar with solder (SnAg) cap",
  thickness_um=T(None, 35, None, notes="35 um reflowed height (HBM1 base-die micro-bumps); our model uses a 10 um layer"),
  lateral_mm={"pattern": "dense arrays under PHY edges and power/ground grid under die", "pitch_um": [36, 55], "diameter_um": 25,
              "examples": {"HBM base die": "55 um FCR pitch, 25 um CD", "Xilinx SSIT": "45 um", "UCIe advanced": "25-55 um", "EMIB": "55 -> 45 um"}},
  k_W_per_mK={"value": None, "our_model_effective": 124.6, "derived_parallel_range": "14-95 W/mK (bump area fraction 0.24 for 25 um round bumps on 45 um pitch; bump k 58 (solder) to 389 (Cu); underfill 0.6) - derived, illustrative"},
  function="First-level interconnect of every top die: power/ground, HBM bus, die-to-die links; part of the secondary heat path.",
  connects_to=C(("compute_die_active_layer", [PW, SG, TH, ME]), ("hbm_base_die", [PW, SG, TH, ME]), ("interposer_beol_rdl", [PW, SG, TH, ME]), ("microbump_underfill", [ME, TH])),
  sources=S("hbm-023", "hbm-026", "hbm-033", "hbm-032", "pkg-021", "pkg-018", "hbm-041", "pkg-035", "pkg-029"), confidence="medium",
  in_our_model={"modeled": True, "layer": "L3 'underfill with ubump'", "detail": "10 um; 25 um bumps on 45 um cell treated as a 25 x 25 um copper square: 30.9% Cu, k_eff 124.6 W/mK, applied under the whole die and its halo", "cite": [R("sundai_tap/passive_interposer.py", "35-36, 39, 42, 105-108, 114-115, 147")]},
  notes="Counts: ~4,000 bumps under an HBM2-era base die (3,990 TSV micro-bumps: 1,728 I/O, 1,030 ground); 10K-30K chip-to-chip connections in Virtex-7 SSIT. IEDM 2023 quotes a 96 um 'staggered' pitch for HBM's 1,024 I/Os (different pitch definition from 55 um FCR).")

P(id="microbump_underfill", name="Micro-bump underfill / molded underfill", parent="package", stack_order=8, count=1,
  material="Epoxy capillary underfill or molded underfill (MUF)", thickness_um=T(None, 35, None, notes="equals micro-bump stand-off; our model uses 10 um"),
  lateral_mm={"pattern": "under each top die"}, k_W_per_mK={"value": 0.6, "our_model": 1.6},
  function="Mechanical support of micro-bump joints; CTE buffer.",
  connects_to=C(("microbumps", [ME, TH]), ("compute_die_active_layer", [ME, TH]), ("interposer_beol_rdl", [ME, TH])),
  sources=S("thm-023", "thm-005", "pkg-038"), confidence="medium",
  in_our_model={"modeled": True, "layer": "L3 (mixed with bumps; whitespace between dies is underfill)", "cite": [R("sundai_tap/passive_interposer.py", "22, 147"), R("sundai_tap/util/fill_space.py", "19, 164")]})

# ------------------------------------------------------------------ top dies (stack_order 9)
P(id="compute_die", name="Compute die (logic chiplet, flip-chip)", parent="package", stack_order=9, count=1,
  material="Silicon (TSMC N7/N5/4N/4NP-class logic)",
  thickness_um=T(None, 720, 775, notes="710 um Si + 10 um BEOL in a published FEM stack; planarized to the HBM height (720 um HBM3E; 775 um if matched to HBM4 nominal, derived); our model uses 150 um"),
  lateral_mm={"w": 14.5, "h": 31.4, "area_mm2_examples": {"Ascend 910 Vitruvian": 456, "NVIDIA GH100": 814, "Blackwell": "two reticle-limited dies", "FEM model": "26 x 26 = 676"},
              "pattern": "w/h shown for the Ascend 910 reference (TAP Table II); reticle-limited dies are ~820-830 mm2"},
  k_W_per_mK={"silicon_room_temp": [117.5, 150], "silicon_85C": 118.5, "silicon_100C": 112, "notes": "temperature values from k = 150 (T/300)^-4/3 (derived); doped Si ~80% of pure"},
  function="Tensor/vector compute, SRAM, NoC, HBM controllers and PHYs, die-to-die PHYs. Main heat source.",
  connects_to=C(("compute_die_active_layer", [PW, SG, TH]), ("tim1", [TH]), ("mold_compound", [TH, ME]), ("hbm_stack", [SG, TH]), ("io_die", [SG])),
  sources=S("thm-029", "thm-032", "hbm-018", "hbm-009", "prd-003", "prd-009", "prd-014", "thm-007", "thm-016", "thm-017", "thm-018", "prd-012", "prd-022", "prd-023", "prd-005"),
  confidence="high",
  in_our_model={"modeled": True, "layer": "L4 'chip layer' (Chiplet_0)", "detail": "150 um silicon, k = 100, uniform power (Ascend910 fixture: 256 W)", "cite": [R("sundai_tap/passive_interposer.py", "116, 148, 189-190"), R("sundai_tap/configs/sys_ascend910_45mm.cfg", "18-21")]},
  notes="Power examples: H100 SXM5 700 W TDP; MI300X 750 W; MI325X 1000 W; Ascend 910 350 W (whole package). Average die flux for H100 <= 86 W/cm2 (700 W / 814 mm2; derived upper bound since TDP includes HBM). Flip-chip: active side faces the interposer.")

P(id="compute_die_active_layer", name="Active layer (FEOL transistors + BEOL interconnect), facing down", parent="compute_die", stack_order=9.1, count=1,
  material="Transistors + Cu/low-k interconnect stack", thickness_um=T(None, 10, None, notes="BEOL 10 um in a published FEM stack; FEOL is a sub-um layer"),
  lateral_mm={"pattern": "whole die; HBM PHY strips on edges facing HBM; D2D PHY on edges facing the partner die"},
  k_W_per_mK={"value": None, "notes": "low-k BEOL dielectric; not sourced"},
  function="Where heat is generated (junction). Sits at the BOTTOM of the flipped die, next to the micro-bumps, so top-side heat must cross the full die thickness.",
  connects_to=C(("microbumps", [PW, SG, TH]), ("compute_die_bulk_si", [TH]), ("hbm_phy", [SG]), ("d2d_phy", [SG])),
  sources=S("thm-043", "thm-029", "pkg-055", "pkg-026"), confidence="high",
  in_our_model={"modeled": True, "detail": "power is injected in L4 as a whole (no separate active layer)", "cite": [R("sundai_tap/passive_interposer.py", "148")]})

P(id="compute_die_bulk_si", name="Compute die bulk silicon (backside, facing up)", parent="compute_die", stack_order=9.2, count=1,
  material="Silicon", thickness_um=T(None, 710, None), lateral_mm={"pattern": "whole die"},
  k_W_per_mK={"silicon_room_temp": [117.5, 150], "silicon_100C": 112},
  function="Conducts and spreads heat from the active layer up to TIM1.",
  connects_to=C(("compute_die_active_layer", [TH]), ("tim1", [TH])), sources=S("thm-029", "pkg-051", "thm-017"), confidence="high",
  in_our_model={"modeled": True, "layer": "L4", "detail": "150 um"},
  notes="Measured area-specific resistance of a bulk Si die in TSMC's benchmark: 5 C*mm2/W (2 when thinned).")

P(id="hbm_phy", name="HBM PHY (on compute die edge)", parent="compute_die", stack_order=9.1, count=4,
  material="Mixed-signal I/O macros", thickness_um=None, lateral_mm={"pattern": "strip along each die edge that faces an HBM stack; one 1024-bit (HBM3/3E) or 2048-bit (HBM4) PHY per stack"},
  k_W_per_mK=None, function="Drives the HBM bus across the interposer (16 x 64-bit channels, up to 9.6 Gb/s/pin for HBM3E).",
  connects_to=C(("microbumps", [SG, PW]), ("hbm_base_die", [SG])), sources=S("hbm-025", "hbm-038", "hbm-039", "hbm-040", "hbm-005"), confidence="high",
  in_our_model={"modeled": False, "detail": "no intra-die power map"}, notes="count = number of HBM stacks served (4 for Ascend 910).")

P(id="d2d_phy", name="Die-to-die PHY (on facing edges)", parent="compute_die", stack_order=9.1, count=1,
  material="Parallel short-reach I/O", thickness_um=None, lateral_mm={"pattern": "edge facing the partner compute die or I/O die"},
  k_W_per_mK=None, function="Joins dies into one logical chip (e.g. NV-HBI 10 TB/s on Blackwell; UCIe-A x64 modules).",
  connects_to=C(("microbumps", [SG, PW])), sources=S("prd-015", "hbm-041", "hbm-042", "hbm-043"), confidence="high", in_our_model={"modeled": False})

P(id="io_die", name="I/O die (e.g. Ascend 910 'Nimbus V3')", parent="package", stack_order=9, count=1,
  material="Silicon", thickness_um=T(None, 720, None, notes="assumed planarized with the other top dies (derived)"),
  lateral_mm={"w": 10.5, "h": 16.0, "area_mm2": 168}, k_W_per_mK={"silicon_room_temp": [117.5, 150]}, variant="ascend910",
  function="PCIe / coherent links / host I/O; low power (14 W in TAP's model).",
  connects_to=C(("microbumps", [PW, SG, TH]), ("compute_die", [SG]), ("tim1", [TH])), sources=S("prd-003", "thm-007"), confidence="high",
  in_our_model={"modeled": True, "layer": "L4 (Chiplet_1)", "cite": [R("sundai_tap/configs/sys_ascend910_45mm.cfg", "19-21")]})

P(id="hbm_stack", name="HBM stack (molded known-good stacked die)", parent="package", stack_order=9, count=4,
  material="1 base logic die + 4-16 thinned DRAM core dies, TSVs, micro-bumps, gap fill, side mold",
  thickness_um=T(490, 720, 775, notes="490 um HBM1; 720 um HBM2-HBM3E (JEDEC height kept for 12-high); 775 um reported for HBM4 12/16-high"),
  lateral_mm={"w": 7.75, "h": 11.87, "examples": {"HBM2 (SK hynix)": "7.75 x 11.87", "HBM3E (Micron)": "11 x 11", "HBM3/3E/4 (press)": "~10.5 x 12.0", "Ascend 910 slide": "96 mm2"},
              "pattern": "w/h shown for the Ascend 910 / TAP reference"},
  k_W_per_mK={"silicon": [117.5, 150], "vertical_effective_derived": "~15 W/mK (720 um / ~49 K*mm2/W; 12 bond layers x 3.8 K*mm2/W + 501 um Si at 130 W/mK; BEOL ignored) - derived",
              "notes": "the stack is ~9x more resistive vertically than a 720 um logic die (derived)"},
  function="On-package DRAM: 1024-bit (HBM3/3E) or 2048-bit (HBM4) bus; 24-36 GB per stack for 12-high HBM3E, up to 64 GB.",
  connects_to=C(("microbumps", [PW, SG, TH, ME]), ("hbm_phy", [SG]), ("tim1", [TH]), ("mold_compound", [TH, ME]), ("compute_die", [TH])),
  sources=S("hbm-047", "hbm-003", "hbm-007", "hbm-018", "hbm-022", "hbm-035", "hbm-009", "hbm-037", "prd-003", "hbm-010", "hbm-014", "hbm-019", "hbm-004", "thm-031", "thm-030"),
  confidence="high",
  in_our_model={"modeled": True, "layer": "L4 (Chiplet_2..5)", "detail": "a single 150 um silicon block, 7.75 x 11.87 mm, uniform 20 W; no internal layers", "cite": [R("sundai_tap/configs/sys_ascend910_45mm.cfg", "19-21"), R("sundai_tap/passive_interposer.py", "116, 148")]},
  notes="Counts: Ascend 910 4; H100 SXM5 5 active of 6 sites; MI300X 8; Blackwell 8 (press). Power ~10-20 W per stack (imec ~40 W for four; TAP/Purdue models 20 W).")

P(id="hbm_base_die", name="HBM base (logic / buffer) die", parent="hbm_stack", stack_order=9.1, count=1,
  material="Silicon; DRAM-process up to HBM3E (SK hynix), foundry logic process for HBM4",
  thickness_um=T(None, 50, None, notes="50 um in a published FEM stack"), lateral_mm={"w": 12.0, "h": 7.75, "notes": "FEM-model footprint; product footprints differ"},
  k_W_per_mK={"silicon": [117.5, 150]},
  function="PHY, TSV landing, test/repair logic; drives the 1024/2048-bit bus to the host through the interposer. Hottest layer of the stack in a published model.",
  connects_to=C(("microbumps", [PW, SG, TH, ME]), ("hbm_bond_layer", [PW, SG, TH, ME]), ("hbm_tsv", [PW, SG])),
  sources=S("thm-030", "thm-029", "hbm-036", "hbm-025", "thm-034", "thm-033"), confidence="medium",
  in_our_model={"modeled": False, "detail": "HBM is one homogeneous block"}, notes="8 W assumed for the base die in the Purdue model (thm-033).")

P(id="hbm_bond_layer", name="HBM inter-die bond layer (micro-bumps + gap fill)", parent="hbm_stack", stack_order=9.2, count=12,
  material="~20 um micro-bumps + MR-MUF molded underfill (SK hynix) or TC-NCF film (Samsung); thermal dummy bumps",
  thickness_um=T(7, 15, None, notes="7 um chip gap with TC-NCF (Samsung); 15 um bump layer in a published FEM stack"),
  lateral_mm={"pattern": "full die area; signal/power bumps concentrated around the central TSV area, dummy thermal bumps elsewhere"},
  k_W_per_mK={"area_specific_R_K_mm2_per_W": 3.8, "effective_derived": "~3.9 W/mK if 15 um thick (derived)"},
  function="Electrical joints between stacked dies; dominant internal thermal resistance of the stack.",
  connects_to=C(("hbm_base_die", [PW, SG, TH, ME]), ("hbm_dram_core_die", [PW, SG, TH, ME])),
  sources=S("hbm-046", "hbm-013", "hbm-015", "hbm-017", "thm-029", "thm-031", "hbm-024", "hbm-016", "hbm-028", "hbm-031"), confidence="medium",
  in_our_model={"modeled": False}, notes="count = one per DRAM core die (12 for 12-high). Hybrid bonding (no gap fill) is the path for taller stacks (hbm-030).")

P(id="hbm_dram_core_die", name="HBM DRAM core dies", parent="hbm_stack", stack_order=9.3, count=11,
  material="Thinned DRAM silicon with TSVs", thickness_um=T(None, 35, None, notes="35 um in a published FEM stack; 12-high HBM3E dies were made 40% thinner than 8-high dies"),
  lateral_mm={"w": 11.5, "h": 7.5, "notes": "FEM-model footprint"}, k_W_per_mK={"silicon": [117.5, 150]},
  function="DRAM arrays; 24-32 Gb per die (HBM3E/HBM4); ~1 W each in a published model.",
  connects_to=C(("hbm_bond_layer", [PW, SG, TH, ME]), ("hbm_tsv", [PW, SG])), sources=S("thm-030", "hbm-010", "hbm-007", "thm-033"), confidence="medium",
  in_our_model={"modeled": False}, notes="count shown = 11 core dies below a thicker top die in a 12-high stack.")

P(id="hbm_top_die", name="HBM top DRAM die (thicker)", parent="hbm_stack", stack_order=9.4, count=1,
  material="DRAM silicon", thickness_um=T(None, 66, None, notes="66 um in a published FEM stack"),
  lateral_mm={"w": 11.5, "h": 7.5}, k_W_per_mK={"silicon": [117.5, 150]},
  function="Last DRAM die; extra thickness sets the stack height to the JEDEC limit.",
  connects_to=C(("hbm_bond_layer", [PW, SG, TH, ME]), ("tim1", [TH])), sources=S("thm-030"), confidence="medium", in_our_model={"modeled": False})

P(id="hbm_tsv", name="HBM TSVs", parent="hbm_stack", stack_order=9.2, count=60000,
  material="Cu TSVs through each core die", thickness_um=None,
  lateral_mm={"pattern": "concentrated in a central TSV area of each die; ~1.3% of die area (HBM1)"},
  k_W_per_mK={"cu": 389}, function="Vertical data, command and power paths through the stack.",
  connects_to=C(("hbm_base_die", [PW, SG]), ("hbm_dram_core_die", [PW, SG])), sources=S("hbm-034", "hbm-021", "hbm-033", "hbm-024"), confidence="medium",
  in_our_model={"modeled": False}, notes="count = >60,000 TSVs per 12-high stack (Samsung 2019); HBM3E has 2x the TSVs of HBM3 (Micron). Diameter not sourced in this pack.")

P(id="hbm_side_mold", name="HBM side mold", parent="hbm_stack", stack_order=9.2, count=1,
  material="Epoxy molding compound around the stack", thickness_um=T(None, 720, None, notes="full stack height"),
  lateral_mm={"pattern": "thin wall around the die stack"}, k_W_per_mK={"value": 0.96, "notes": "generic EMC value"},
  function="Protects and stiffens the stack (molded KGSD).", connects_to=C(("hbm_dram_core_die", [ME, TH])), sources=S("hbm-047", "thm-024"), confidence="medium",
  in_our_model={"modeled": False})

P(id="dummy_die", name="Dummy silicon die (Ascend 910)", parent="package", stack_order=9, count=2,
  material="Unpowered silicon", thickness_um=T(None, 720, None, notes="assumed planarized (derived)"),
  lateral_mm={"area_mm2": 110, "pattern": "beside the I/O die, in line with the HBM rows"}, k_W_per_mK={"silicon_room_temp": [117.5, 150]},
  variant="ascend910", function="Mechanical uniformity of the package (warpage, flat top for the cooler).",
  connects_to=C(("mold_compound", [ME, TH]), ("tim1", [TH]), ("interposer_silicon", [ME])), sources=S("prd-001", "prd-003", "prd-008"), confidence="high",
  in_our_model={"modeled": False, "detail": "omitted by TAP's Ascend910 fixture and by our reconstruction", "cite": [R("docs/sentilab/references/README.md", "172-174")]})

P(id="mold_compound", name="Molding compound between top dies", parent="package", stack_order=9, count=1,
  material="Epoxy molding compound (or molded underfill), ground flush with die tops",
  thickness_um=T(None, 720, None, notes="equal to the planarized die height (derived)"),
  lateral_mm={"pattern": "fills gaps between dies: 0.72 mm (compute to HBM row) and 2 mm (between HBMs) on Ascend 910; >= 0.1 mm die gap rule in our fixtures"},
  k_W_per_mK={"value": 0.96, "our_model": 1.6},
  function="Encapsulates and stiffens the chip-on-wafer assembly; a weak lateral thermal path between logic and HBM.",
  connects_to=C(("compute_die", [TH, ME]), ("hbm_stack", [TH, ME]), ("interposer_beol_rdl", [ME]), ("tim1", [TH])),
  sources=S("pkg-038", "thm-032", "thm-024", "prd-004"), confidence="medium",
  in_our_model={"modeled": True, "layer": "L4 whitespace", "detail": "gaps between dies filled with underfill (k 1.6); interposer edge strips get micro-bump material", "cite": [R("sundai_tap/util/fill_space.py", "19, 164"), R("sundai_tap/passive_interposer.py", "94-97, 122"), R("sundai_tap/configs/sys_ascend910_45mm.cfg", "35-36")]})

# ------------------------------------------------------------------ cooling stack
P(id="tim1", name="TIM1 (die to lid; die to cold plate in lidless designs = 'TIM1.5')", parent="package", stack_order=10, count=1,
  material="Polymer/PCM, indium solder, or liquid metal",
  thickness_um=T(20, None, 50, notes="PCM bondline min ~20 um, typical < 50 um; our model uses 20 um"),
  lateral_mm={"pattern": "over all top dies (compute, HBM, dummies)"},
  k_W_per_mK={"indium": 86, "pcm_ptm7950": 8.5, "conventional_high_performance": 20, "older_polymer_tim1_2011": 0.92, "our_model": 4,
              "area_specific_R_K_mm2_per_W": {"liquid_metal_TSMC": 4, "oxide_fusion_bond_TSMC": 1.5, "ptm7950": 4}},
  function="Fills microscopic gaps between die backsides and the lid/cold plate.",
  connects_to=C(("compute_die_bulk_si", [TH]), ("hbm_stack", [TH]), ("lid", [TH]), ("cold_plate", [TH])),
  sources=S("thm-020", "thm-021", "thm-022", "thm-028", "thm-013", "pkg-051", "pkg-012"), confidence="high",
  in_our_model={"modeled": True, "layer": "L5 'TIM'", "detail": "20 um, k = 4 W/mK, one block over the whole interposer (incl. gaps)", "cite": [R("sundai_tap/passive_interposer.py", "126-132, 149")]},
  notes="PTM7950: 0.04 C*cm2/W = 4 K*mm2/W, same as TSMC's measured liquid-metal TIM.")

P(id="lid", name="Lid / integrated heat spreader (lidded variant)", parent="package", stack_order=11, count=1,
  material="Copper (often Ni-plated; plating not sourced here)",
  thickness_um=T(None, None, None, render_hint=1000, render_hint_basis="HotSpot default spreader thickness 1 mm (model default, not a product value)"),
  lateral_mm={"pattern": "covers the die area and lands on the substrate (lid foot / seal not sourced)"},
  k_W_per_mK={"cu": 389, "our_model_spreader": 400}, variant="lidded",
  function="Spreads heat laterally, protects dies, flattens the package; the main lateral coupling path between logic and HBM in one study.",
  connects_to=C(("tim1", [TH]), ("tim2", [TH]), ("package_substrate", [ME, TH])),
  sources=S("pkg-025", "pkg-012", "thm-013", "thm-026", "thm-041"), confidence="medium",
  in_our_model={"modeled": True, "layer": "HotSpot spreader (appended)", "detail": "1 mm Cu, side = 2 x interposer (90 mm for 45 mm)", "cite": [R("sundai_tap/util/hotspot.config", "29-35"), R("sundai_tap/passive_interposer.py", "154, 160-161"), R("sundai_hotspot/temperature_grid.c", "529-541")]})

P(id="tim2", name="TIM2 (lid to cold plate / heat sink)", parent="package", stack_order=12, count=1,
  material="Thermal grease, PCM pad or putty", thickness_um=T(20, None, 50, notes="PCM-class bondline"),
  lateral_mm={"pattern": "lid top surface"}, k_W_per_mK={"pcm_ptm7950": 8.5, "notes": "grease values not captured"},
  variant="lidded", function="Interface between lid and cooler (absent in lidless designs, where TIM1.5 touches the die).",
  connects_to=C(("lid", [TH]), ("cold_plate", [TH])), sources=S("thm-021", "thm-022", "thm-040", "thm-041", "thm-009"), confidence="medium",
  in_our_model={"modeled": False, "detail": "HotSpot does not support TIM2", "cite": [R("sundai_tap/util/hotspot.config", "37-43")]})

P(id="cold_plate", name="Liquid cold plate", parent=None, stack_order=13, count=1,
  material="Copper (most used) with fins/pins or micro-channels",
  thickness_um=None, lateral_mm={"pattern": "covers the lid (or bare dies + stiffener)"},
  k_W_per_mK={"cu": 389},
  function="Moves heat into coolant; dominant single resistance at 1 kW class (case-to-fluid ~0.04 K/W in a vendor test).",
  connects_to=C(("tim2", [TH]), ("tim1", [TH]), ("coolant", [TH])), sources=S("thm-042", "thm-039", "thm-040", "prd-017", "pkg-051"), confidence="medium",
  variant="liquid_cooled",
  in_our_model={"modeled": "partly", "detail": "HotSpot heat sink layer + lumped r_convec stands in for any cooler", "cite": [R("sundai_tap/util/hotspot.config", "13-25"), R("sundai_tap/passive_interposer.py", "155-163")]})

P(id="heat_sink", name="Air heat sink (air-cooled alternative)", parent=None, stack_order=13, count=1,
  material="Copper/aluminium base + fins (or vapor chamber)",
  thickness_um=T(None, 6900, None, notes="HotSpot default sink base thickness (model value)"),
  lateral_mm={"w": 180, "h": 180, "notes": "our model: 2 x spreader = 4 x interposer (180 mm for 45 mm)"},
  k_W_per_mK={"our_model": 400}, variant="air_cooled",
  function="Forced-air cooling; TAP-2.5D models 'a realistic air-forced heatsink'.",
  connects_to=C(("tim2", [TH]), ("lid", [TH])), sources=S("thm-002", "thm-003"), confidence="low",
  in_our_model={"modeled": True, "layer": "HotSpot sink (appended)", "cite": [R("sundai_tap/util/hotspot.config", "15-25"), R("sundai_tap/passive_interposer.py", "155-163")]})

P(id="coolant", name="Coolant", parent=None, stack_order=14, count=1,
  material="DI water or water-glycol (single phase); dielectric or refrigerant in some systems", thickness_um=None, lateral_mm=None,
  k_W_per_mK=None, variant="liquid_cooled", function="Carries heat to the facility loop.",
  connects_to=C(("cold_plate", [TH])), sources=S("thm-044", "thm-039"), confidence="high",
  in_our_model={"modeled": False, "detail": "ambient 45 C boundary via r_convec", "cite": [R("sundai_tap/util/hotspot.config", "76-78")]})

# ------------------------------------------------------------------ interconnect classes
interconnects = [
    {"id": "microbump", "class": "die/HBM-to-interposer micro-bumps", "pitch_um": {"min": 25, "typical": 45, "max": 55, "typical_basis": "Xilinx SSIT / 2011 test vehicle example; HBM uses 55 um FCR"},
     "diameter_um": 25, "height_um": 35, "material": "Cu pillar + SnAg cap", "counts": "~4,000 under an HBM2-era base die; 10K-30K D2D (Virtex-7 SSIT)",
     "sources": S("pkg-021", "hbm-023", "hbm-033", "hbm-032", "hbm-041", "pkg-018", "pkg-035"),
     "notes": "Micro-bump joining is challenging below ~20 um pitch (hbm-029)."},
    {"id": "hbm_internal_bond", "class": "HBM die-to-die bonds", "pitch_um": None, "diameter_um": 20, "gap_um": {"tc_ncf": 7, "fem_model_layer": 15},
     "area_specific_R_K_mm2_per_W": 3.8, "methods": ["MR-MUF (SK hynix)", "TC-NCF (Samsung)", "hybrid bonding (future, >=16-high)"],
     "sources": S("hbm-046", "hbm-015", "thm-029", "thm-031", "hbm-013", "hbm-028", "hbm-030")},
    {"id": "hybrid_bond", "class": "3D hybrid bonding (Cu-Cu + dielectric)", "pitch_um": {"min": 0.9, "typical": 9, "max": 10, "typical_basis": "first-generation SoIC / Foveros Direct; 0.9 um is a roadmap point"},
     "examples": {"TSMC SoIC": "sub-10 um; roadmap 9 -> 6 -> 3 -> 0.9 um", "Intel Foveros Direct": "9 um", "UCIe-3D": "<= 10 um"},
     "sources": S("pkg-010", "pkg-011", "pkg-037", "hbm-043"), "notes": "MI300X stacks XCDs on IODs (prd-019/020); its bond pitch is not in this pack."},
    {"id": "c4", "class": "C4 bumps (interposer-to-substrate)", "pitch_um": {"min": 90, "typical": 180, "max": 210, "typical_basis": "Xilinx 2011 interposer test vehicle example; 90 um is a substrate roadmap value"},
     "diameter_um": {"min": 80, "max": 125}, "height_um": {"cu_pillar": 40, "standard_min": 60, "standard_max": 100},
     "material": "Cu C4 / Cu pillar + SnAg; Pb-free 98.2Sn/1.8Ag",
     "sources": S("pkg-053", "pkg-016", "pkg-021", "pkg-018", "pkg-034", "pkg-028", "pkg-029", "pkg-054", "pkg-013")},
    {"id": "interposer_tsv", "class": "interposer TSVs", "diameter_um": ">10", "pitch_um": 210, "depth_um": 100, "aspect_ratio": "~10:1 (derived)",
     "sources": S("pkg-018", "pkg-021"), "notes": "2011 Xilinx/TSMC SSIT values; our model uses 10 um on a 50 um cell."},
    {"id": "hbm_tsv", "class": "HBM TSVs", "count_per_12_high_stack": ">60,000", "relative": "HBM3E 2x HBM3", "area_fraction": "~1.3% (HBM1)",
     "sources": S("hbm-034", "hbm-021", "hbm-033"), "notes": "diameter/pitch not captured from a primary source."},
    {"id": "interposer_wiring", "class": "interposer BEOL / RDL line and space",
     "values": {"Si interposer (65 nm SSIT)": "4 metal layers, 2 um pitch", "CoWoS-S 2021": "thick metal (5Mi)", "CoWoS-R RDL": "2/2 um L/S, 4 um pitch", "CoWoS-L LSI": "sub-um Cu lines"},
     "sources": S("pkg-018", "pkg-019", "pkg-014", "pkg-003", "pkg-008")},
    {"id": "substrate_wiring", "class": "substrate build-up line/space and layers",
     "values": {"L/S": "9/12 um (volume) -> 6/6 um (roadmap)", "layers": "10/x/10 (2026) -> 14/x/14 (roadmap)", "Xilinx 2011": "4-2-4"},
     "sources": S("pkg-031", "pkg-034", "pkg-033", "pkg-047", "pkg-018")},
    {"id": "bga", "class": "BGA balls", "pitch_mm": {"min": 0.8, "typical": 1.0, "max": 1.0, "typical_basis": "Virtex-7 SSIT package and both FCBGA drawings use 1.0 mm"}, "ball_diameter_mm": {"min": 0.4, "typical": None, "max": 0.7, "nominals": [0.5, 0.6]},
     "standoff_mm": {"min": 0.31, "max": 0.6}, "sources": S("pkg-022", "pkg-018", "pkg-049", "pkg-050", "pkg-027")},
    {"id": "hbm_bus", "class": "HBM PHY-to-PHY bus across the interposer",
     "width_bits": {"HBM2/HBM3/HBM3E": 1024, "HBM4": 2048}, "channels": {"HBM3": "16 x 64-bit (32 pseudo)", "HBM4": "32 (2 pseudo each)"},
     "rate_Gbps_per_pin": {"HBM2": 2.0, "HBM3": 6.4, "HBM3E": [9.2, 9.6, 10.0], "HBM4": 8.0},
     "bandwidth_per_stack": {"HBM2": "256 GB/s", "HBM3": "819 GB/s", "HBM3E": "1.2-1.28 TB/s", "HBM4": "2 TB/s"},
     "energy_pJ_per_bit": {"HBM2E": 4.3, "HBM3E": "~20% lower", "HBM4": "~60% lower (expected)"},
     "voltages_V": {"HBM VDD (HBM3E era)": [1.1, 1.2], "HBM4 VDDQ": [0.7, 0.9], "HBM4 VDDC": [1.0, 1.05]},
     "route": "host HBM PHY -> micro-bumps -> interposer wiring -> micro-bumps -> HBM base-die PHY -> TSVs",
     "sources": S("hbm-048", "hbm-001", "hbm-002", "hbm-005", "hbm-006", "hbm-019", "hbm-011", "hbm-014", "hbm-025", "hbm-027", "hbm-039", "pkg-042", "hbm-008"),
     "notes": "Samsung quotes 1,280 GB/s for HBM3E 12H, i.e. 10 Gb/s x 1024 / 8 (derived)."},
    {"id": "die_to_die", "class": "compute-to-compute / compute-to-IO links",
     "examples": {"NVIDIA NV-HBI (Blackwell)": "10 TB/s", "AMD MI300X XCD-IOD": "2.1 TB/s", "AMD Infinity Fabric AP": "4.8 TB/s and 6 TB/s bisection",
                  "UCIe-A (2.5D)": "x64, 4-32 GT/s, <=2 mm, 165-1317 GB/s/mm, 0.25 pJ/b", "UCIe-S (2D)": "x16, 100-130 um bumps, <=25 mm, 28-224 GB/s/mm, 0.5 pJ/b",
                  "Xilinx SSIT": ">10,000 die-to-die connections"},
     "sources": S("prd-015", "prd-025", "hbm-041", "hbm-042", "hbm-043", "hbm-044", "pkg-020")},
    {"id": "power_delivery", "class": "VRM to die",
     "chain": ["vrm_lateral | vrm_vertical", "system_board planes", "bga_balls", "substrate_buildup_bottom", "substrate_core (PTH)", "substrate_buildup_top", "c4_bumps", "interposer_tsv", "interposer_beol_rdl (+ eDTC)", "microbumps", "compute_die_active_layer"],
     "values": {"core_VDD_V": ">= 0.7 (+/-5%)", "continuous_A": 1000, "dI_dt_A_per_us": ">= 2000", "board_bypass_mF": ">= 3", "PDN_uOhm": "60 lateral -> 11 lateral-vertical", "eDTC_nF_per_mm2": 340},
     "sources": S("pkg-041", "pkg-043", "pkg-045", "pkg-046", "thm-012", "pkg-026")},
]

flows = {
    "heat_primary_lidded": ["compute_die_active_layer", "compute_die_bulk_si", "tim1", "lid", "tim2", "cold_plate", "coolant"],
    "heat_primary_lidless": ["compute_die_active_layer", "compute_die_bulk_si", "tim1", "cold_plate", "coolant"],
    "heat_secondary": ["compute_die_active_layer", "microbumps", "interposer_beol_rdl", "interposer_silicon", "c4_bumps", "substrate_buildup_top", "substrate_core", "substrate_buildup_bottom", "bga_balls", "system_board"],
    "heat_hbm_vertical": ["hbm_base_die", "hbm_bond_layer", "hbm_dram_core_die", "hbm_top_die", "tim1"],
    "heat_lateral_coupling_logic_to_hbm": [["compute_die", "tim1", "lid", "tim1", "hbm_stack"], ["compute_die", "mold_compound", "hbm_stack"], ["compute_die_active_layer", "microbumps", "interposer_silicon", "microbumps", "hbm_base_die"]],
    "heat_share_note": "Some 95% of a chip's heat leaves through the top (thm-036); one study finds most inter-chiplet coupling goes through the heat spreader rather than the interposer (thm-026).",
    "power": ["vrm_lateral", "system_board", "bga_balls", "package_substrate", "c4_bumps", "interposer_tsv", "interposer_beol_rdl", "microbumps", "compute_die_active_layer"],
    "signal_hbm": ["hbm_phy", "microbumps", "interposer_beol_rdl", "microbumps", "hbm_base_die", "hbm_tsv", "hbm_dram_core_die"],
    "signal_d2d": ["d2d_phy", "microbumps", "interposer_beol_rdl | lsi_bridge", "microbumps", "d2d_phy"],
    "signal_off_package": ["compute_die_active_layer", "microbumps", "interposer_beol_rdl", "interposer_tsv", "c4_bumps", "package_substrate", "bga_balls", "system_board"],
}

reference_layouts = {
    "ascend910_reference": {
        "purpose": "Matches the die set our simulations use (TAP-2.5D Ascend 910 fixture) plus the real package's extra parts.",
        "interposer_mm": {"w": 45, "h": 45, "source": "TAP-2.5D Sec. IV (thm-006); our 45 mm fixture"},
        "dies": [
            {"part": "compute_die", "name": "Vitruvian", "w_mm": 14.5, "h_mm": 31.4, "power_W_in_model": 256},
            {"part": "io_die", "name": "Nimbus V3", "w_mm": 10.5, "h_mm": 16.0, "power_W_in_model": 14},
            {"part": "hbm_stack", "name": "HBM2 x4", "w_mm": 7.75, "h_mm": 11.87, "power_W_in_model": 20, "count": 4},
            {"part": "dummy_die", "name": "dummy x2", "area_mm2": 110, "power_W_in_model": None, "count": 2, "in_model": False},
        ],
        "real_gaps_mm": {"compute_to_hbm_row": 0.72, "between_hbms": 2.0},
        "total_silicon_mm2": 1228, "package_power_W": 350,
        "sources": S("thm-007", "prd-001", "prd-002", "prd-003", "prd-004", "prd-005", "thm-006"),
        "repo": [R("sundai_tap/configs/sys_ascend910_45mm.cfg", "14, 18-28"), R("docs/sentilab/references/README.md", "164-174")],
        "notes": "Die w/h follow TAP Table II (Huawei states areas only). The real interposer size is not in this pack.",
    },
    "generic_hbm3e_two_die": {
        "purpose": "Modern reticle-limited two-die accelerator with 8 HBM3E stacks (Blackwell-like class; NOT NVIDIA dimensions).",
        "dies": [
            {"part": "compute_die", "count": 2, "area_mm2": "~820-830 each (one reticle)", "note": "aspect ratio not public in this pack"},
            {"part": "hbm_stack", "count": 8, "w_mm": 11, "h_mm": 11, "height_um": 720},
        ],
        "interposer": "CoWoS-L class, >= 3.5x reticle", "substrate_mm": "90-110 square", "cooling": "liquid cold plate",
        "sources": S("prd-014", "prd-018", "hbm-018", "pkg-007", "pkg-001", "pkg-033", "pkg-017", "prd-017"),
    },
}

# ------------------------------------------------------------------ sources index
log = {}
with open(os.path.join(EV, "FETCHLOG.tsv"), encoding="utf-8") as fh:
    for row in csv.reader(fh, delimiter="\t"):
        if len(row) >= 7:
            stem = os.path.splitext(os.path.basename(row[1]))[0]
            log[stem] = {"evidence_file": "evidence/" + row[1], "url": row[6], "retrieved_utc": row[0], "sha256": row[5]}
src_index = {}
for rec in FACT.values():
    stem = os.path.basename(rec["file"]).split(".")[0]
    if stem not in src_index:
        e = dict(log.get(stem, {}))
        e.update(title=rec["title"], publisher=rec["publisher"], date=rec["date"], source_type=rec["source_type"])
        src_index[stem] = e

doc = {
    "schema": "sentilab.cad3d.lane1.parts/v1",
    "status": ("REPRESENTATIVE RECONSTRUCTION from public sources. Not any manufacturer's CAD, not silicon-validated. "
               "Contains no temperatures from the SentiLab repo (old HotSpot 7.0 detailed-3D kelvin values are withdrawn)."),
    "generated_by": "lane1-anatomy (research agent), 2026-10-31",
    "repo_snapshot": {"repo": "Sentinelayer-AIdenID/sentilab (local H:/sentilab)", "ref": "origin/main", "sha": REPO_SHA},
    "conventions": {
        "stack_order": "integer levels bottom-to-top: -1 under the board, 0 board, 1 BGA ... 9 top dies, 10 TIM1, 11 lid, 12 TIM2, 13 cooler, 14 coolant. Decimals order sub-layers inside an assembly. Parts sharing a level sit side by side or are alternatives (see variant).",
        "thickness_um": "{min, typical, max} only where a source gives them; null = not sourced. render_hint = an illustrative display value that is NOT a sourced claim (basis given).",
        "k_W_per_mK": "thermal conductivity near room temperature unless stated; 'derived' entries show their inputs.",
        "sources": "fact ids resolve to evidence/<lane>/FACTS.jsonl (verbatim quotes, verified) and source slugs to source_index.",
        "variant": "all | lidded | lidless | cowos_r | cowos_l_or_emib | ascend910 | liquid_cooled | air_cooled | vertical_power_delivery",
        "connection_types": [TH, PW, SG, ME],
    },
    "parts": parts,
    "interconnects": interconnects,
    "flows": flows,
    "reference_layouts": reference_layouts,
    "source_index": src_index,
}

# sanity: every connects_to id exists
ids = {p["id"] for p in parts}
for p in parts:
    for c in p["connects_to"]:
        if c["id"] not in ids:
            raise SystemExit(f"{p['id']} connects to unknown {c['id']}")
    if p["parent"] and p["parent"] not in ids:
        raise SystemExit(f"{p['id']} has unknown parent {p['parent']}")

with open(os.path.join(OUT, "parts.json"), "w", encoding="utf-8", newline="\n") as fh:
    json.dump(doc, fh, indent=2, ensure_ascii=False)
    fh.write("\n")
print("parts", len(parts), "interconnects", len(interconnects), "sources", len(src_index))
