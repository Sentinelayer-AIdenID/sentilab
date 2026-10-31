"""Vector figure extraction from the TAP-2.5D PDF (sha256 b209f51a...), mapped to TAP's floorplan grid.

What it does, and nothing more:
1. Reads the stroked single-line segments in two bands of page index 5 (Fig. 5 and Fig. 6) of the
   PDF given on the command line, and records that file's sha256.
2. Groups consecutive segments into closed axis-aligned rectangles.
3. Splits each figure into panels at four frame strips, and reads each panel's frame and scale from
   them (TAP's 1 mm granularity sets the strip width).
4. Takes the die-sized rectangles of each panel in drawing order as TAP dies 0..n-1. It checks
   each outline against that die's catalog size from the repo's TAP config, in either orientation.
5. Maps the outlines to millimetres in the panel's frame. A panel whose strips and line order
   show it was drawn rotated 90 degrees clockwise is rotated back.

Assumptions, not established by the paper: the drawing order and the frame strips are those of TAP's
util/grid_thermal_map.pl over its generated chip-layer floorplan. The checks above are consistent with
that, but they do not prove it. The output is an approximate reconstruction from a published figure:
not CAD, not silicon, and not a figure-to-silicon error bound.

Usage (PyMuPDF required; the paper PDF is not committed to this repository):
    python -I decode_tap25d_figures.py <tap25d.pdf> <repo-root> <output.json>

The committed output is docs/sentilab/references/tap25d-figure-decode.json (PDF sha256 inside).
"""
from __future__ import annotations

import configparser
import hashlib
import json
import sys
from pathlib import Path

import fitz  # PyMuPDF

PAPER = {
    "citation": ("Y. Ma, L. Delshadtehrani, C. Demirkiran, J. L. Abellan, A. Joshi, "
                 "\"TAP-2.5D: A Thermally-Aware Chiplet Placement Methodology for 2.5D Systems\", "
                 "DATE 2021, pp. 1246-1251, doi:10.23919/DATE51398.2021.9474011"),
    "url": "http://people.bu.edu/joshi/files/Ma_TAP-2.5D-DATE2021.pdf",
}
PAGE_INDEX = 5  # zero-based; the sixth page carries Fig. 5 and Fig. 6
FIGURES = {
    "fig5": {"system": "micro150", "band_pt": (30.0, 130.0), "panels": ("a", "b", "c", "d"),
             "caption": "Fig. 5: Thermal maps of the CPU-DRAM System: (a) the original placement [14], "
                        "(b) a placement solution using Compact-2.5D approach, (c) TAP-2.5D solutions using "
                        "repeaterless non-pipelined link, and (d) using gas-station links."},
    "fig6": {"system": "ascend910", "band_pt": (165.0, 236.0), "panels": ("a", "b", "c"),
             "caption": "Fig. 6: Thermal maps of the Huawei Ascend 910 System [15]: (a) the original layout, "
                        "(b) a placement solution using Compact-2.5D approach, and (c) TAP-2.5D solution."},
}
GRANULARITY_MM = 1.0  # paper Sec. III-C1: "We assume 1mm granularity for the grid"
SIZE_TOLERANCE_MM = 0.02
AXIS_TOLERANCE_PT = 1e-3
NATIVE_ORDER = ("top", "left", "right", "bottom")
ROTATED_CW_ORDER = ("right", "top", "bottom", "left")


def catalog(repo_root: Path, system: str):
    parser = configparser.ConfigParser(interpolation=None)
    parser.read_string((repo_root / "sundai_tap" / "configs" / f"sys_{system}.cfg").read_text(encoding="utf-8"))

    def values(key):
        return [float(v) for v in parser.get("chiplets", key).replace("\n", "").split(",") if v.strip()]
    return list(zip(values("widths"), values("heights")))


def segments(page, band):
    """Single thin line segments inside the figure band, in drawing order."""
    out = []
    for drawing in page.get_drawings():
        if drawing["type"] != "s" or drawing["rect"].y0 < band[0] or drawing["rect"].y1 > band[1]:
            continue
        items = drawing["items"]
        # Hand-drawn annotation boxes ('re' items, ~0.22 pt pen) and the colour-bar outline
        # (one drawing holding four lines) are not floorplan units.
        if len(items) != 1 or items[0][0] != "l":
            continue
        p, q = items[0][1], items[0][2]
        out.append((min(p.x, q.x), min(p.y, q.y), max(p.x, q.x), max(p.y, q.y)))
    return out


def _close(a, b):
    return abs(a - b) < AXIS_TOLERANCE_PT


def unit_rectangles(segs):
    """Group the stream into closed four-line rectangles; resynchronise on any stray line."""
    units, i = [], 0
    while i + 4 <= len(segs):
        group = segs[i:i + 4]
        x0, y0 = min(s[0] for s in group), min(s[1] for s in group)
        x1, y1 = max(s[2] for s in group), max(s[3] for s in group)
        sides = []
        for sx0, sy0, sx1, sy1 in group:
            horizontal = _close(sy0, sy1) and _close(sx0, x0) and _close(sx1, x1)
            vertical = _close(sx0, sx1) and _close(sy0, y0) and _close(sy1, y1)
            # PDF y grows downward: the smaller y is the top of the drawing.
            if horizontal and _close(sy0, y0):
                sides.append("top")
            elif horizontal and _close(sy0, y1):
                sides.append("bottom")
            elif vertical and _close(sx0, x0):
                sides.append("left")
            elif vertical and _close(sx0, x1):
                sides.append("right")
            else:
                sides.append(None)
        if sorted(s for s in sides if s) == ["bottom", "left", "right", "top"] and x1 > x0 and y1 > y0:
            units.append({"rect_pt": (x0, y0, x1, y1), "order": tuple(sides)})
            i += 4
        else:
            i += 1
    return units


def _wide(unit):
    x0, y0, x1, y1 = unit["rect_pt"]
    return (x1 - x0) > 20 * (y1 - y0)


def _tall(unit):
    x0, y0, x1, y1 = unit["rect_pt"]
    return (y1 - y0) > 20 * (x1 - x0)


def split_panels(units):
    """A panel starts at Edge_0..Edge_3: wide, wide, tall, tall (native) or tall, tall, wide, wide (rotated)."""
    panels, current, index = [], None, 0
    while index < len(units):
        edges = units[index:index + 4]
        if len(edges) == 4:
            native = _wide(edges[0]) and _wide(edges[1]) and _tall(edges[2]) and _tall(edges[3])
            rotated = _tall(edges[0]) and _tall(edges[1]) and _wide(edges[2]) and _wide(edges[3])
            if native or rotated:
                current = {"edges": edges, "rotated_cw": rotated, "units": []}
                panels.append(current)
                index += 4
                continue
        if current is not None:
            current["units"].append(units[index])
        index += 1
    return panels


def decode_panel(panel, dies):
    edges = panel["edges"]
    rotated = panel["rotated_cw"]
    xs = [e["rect_pt"][0] for e in edges] + [e["rect_pt"][2] for e in edges]
    ys = [e["rect_pt"][1] for e in edges] + [e["rect_pt"][3] for e in edges]
    left, right, top, bottom = min(xs), max(xs), min(ys), max(ys)
    width_pt, height_pt = right - left, bottom - top
    # In floorplan terms Edge_0 is (S - g) long and Edge_2 is g/2 thick; both read off the figure.
    edge0, edge2 = edges[0]["rect_pt"], edges[2]["rect_pt"]
    edge0_length = (edge0[3] - edge0[1]) if rotated else (edge0[2] - edge0[0])
    edge2_thickness = (edge2[3] - edge2[1]) if rotated else (edge2[2] - edge2[0])
    span = height_pt if rotated else width_pt
    frame_from_strip = GRANULARITY_MM / (2 * edge2_thickness / span)
    frame_from_length = GRANULARITY_MM / (1 - edge0_length / span)
    frame_mm = round(frame_from_strip)
    sx, sy = width_pt / frame_mm, height_pt / frame_mm

    units = panel["units"]
    # Halo strips (<= 0.36 mm) are drawn in some panels and not others; dies are >= 7.75 mm.
    first = units[0]["rect_pt"] if units else (0, 0, 0, 0)
    strips = bool(units) and min((first[2] - first[0]) / sx, (first[3] - first[1]) / sy) < 1.0
    stride = 5 if strips else 1
    if len(units) < stride * len(dies):
        raise ValueError("panel ends before its last die")
    bodies = [units[stride * i + stride - 1] for i in range(len(dies))]
    order_signatures = sorted({u["order"] for u in bodies})
    expected_order = ROTATED_CW_ORDER if rotated else NATIVE_ORDER
    if order_signatures != [expected_order]:
        raise ValueError(f"line-order signature {order_signatures} disagrees with edge orientation")

    # An independent scale: each die outline against its catalog size, in whichever orientation fits.
    die_scales = []
    for (cw, ch), body in zip(dies, bodies):
        x0, y0, x1, y1 = body["rect_pt"]
        w_pt, h_pt = x1 - x0, y1 - y0
        options = ((w_pt / cw, h_pt / ch), (w_pt / ch, h_pt / cw))
        die_scales.extend(min(options, key=lambda pair: abs(pair[0] - pair[1])))
    scale_from_dies = sum(die_scales) / len(die_scales)

    def to_native(rect_pt):
        x0, y0, x1, y1 = rect_pt
        dx0, dx1 = (x0 - left) / sx, (x1 - left) / sx
        dy0, dy1 = (bottom - y1) / sy, (bottom - y0) / sy  # display, y up
        if rotated:
            return frame_mm - dy1, dx0, frame_mm - dy0, dx1
        return dx0, dy0, dx1, dy1

    chiplets = []
    for die, ((cw, ch), body) in enumerate(zip(dies, bodies)):
        nx0, ny0, nx1, ny1 = to_native(body["rect_pt"])
        w_mm, h_mm = nx1 - nx0, ny1 - ny0
        as_catalog = max(abs(w_mm - cw), abs(h_mm - ch))
        swapped = max(abs(w_mm - ch), abs(h_mm - cw))
        rotated_die = swapped < as_catalog
        residual = min(as_catalog, swapped)
        if residual > SIZE_TOLERANCE_MM:
            raise ValueError(f"die {die} outline {w_mm:.4f} x {h_mm:.4f} mm does not match catalog {cw} x {ch}")
        footprint = (ch, cw) if rotated_die else (cw, ch)
        halos = []
        if strips:
            for strip in units[stride * die:stride * die + 4]:
                sx0, sy0, sx1, sy1 = to_native(strip["rect_pt"])
                halos.append(round(min(sx1 - sx0, sy1 - sy0), 4))
        chiplets.append({
            "die": die,
            "rotated_vs_catalog": rotated_die,
            "footprint_mm": [footprint[0], footprint[1]],
            "decoded_size_mm": [round(w_mm, 4), round(h_mm, 4)],
            "size_residual_mm": round(residual, 4),
            "decoded_lower_left_mm": [round(nx0, 4), round(ny0, 4)],
            "decoded_center_mm": [round((nx0 + nx1) / 2, 4), round((ny0 + ny1) / 2, 4)],
            "decoded_halo_strips_mm": sorted(set(halos)),
            "body_pt": [round(v, 4) for v in body["rect_pt"]],
        })
    return {
        "displayed_rotated_90_cw": rotated,
        "frame_pt": {"left": round(left, 4), "right": round(right, 4), "top": round(top, 4),
                     "bottom": round(bottom, 4)},
        "frame_mm": frame_mm,
        "frame_checks_mm": {"from_edge_strip_thickness": round(frame_from_strip, 4),
                            "from_edge_strip_length": round(frame_from_length, 4),
                            "from_die_outlines": round(width_pt / scale_from_dies, 4)},
        "scale_pt_per_mm": {"x": round(sx, 6), "y": round(sy, 6), "from_die_outlines": round(scale_from_dies, 6)},
        "halo_strips_drawn": strips,
        "whitespace_units": len(units) - stride * len(dies),
        "chiplets": chiplets,
    }


def main(argv):
    pdf_path, repo_root, output_path = Path(argv[1]), Path(argv[2]), Path(argv[3])
    pdf_bytes = pdf_path.read_bytes()
    page = fitz.open(stream=pdf_bytes, filetype="pdf")[PAGE_INDEX]
    result = {"schema": "tap25d-figure-decode-v1",
              "paper": {**PAPER, "pdf_sha256": hashlib.sha256(pdf_bytes).hexdigest(), "page_index": PAGE_INDEX},
              "decoder_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "pymupdf_version": fitz.VersionBind, "figures": {}}
    for figure, spec in FIGURES.items():
        dies = catalog(repo_root, spec["system"])
        panels = split_panels(unit_rectangles(segments(page, spec["band_pt"])))
        if len(panels) != len(spec["panels"]):
            raise ValueError(f"{figure}: found {len(panels)} panels, expected {len(spec['panels'])}")
        panels.sort(key=lambda p: min(e["rect_pt"][0] for e in p["edges"]))
        result["figures"][figure] = {
            "system": spec["system"], "caption": spec["caption"],
            "panels": {name: decode_panel(panel, dies) for name, panel in zip(spec["panels"], panels)},
        }
    # Bytes with LF endings, so the file and its sha256 do not depend on the host platform.
    output_path.write_bytes((json.dumps(result, indent=1, sort_keys=True) + "\n").encode("utf-8"))


if __name__ == "__main__":
    main(sys.argv)
