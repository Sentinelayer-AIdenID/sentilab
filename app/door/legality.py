"""The pinned legality adapter (the contract's OP-F7 layout seam) and the two numbers the door derives itself.

PinnedTapChecker loads TapGeometry for the manifest's fixture and refuses to exist unless every manifest value the
geometry depends on matches the fixture file it loaded: the config sha256, the frame, each die's footprint, power and
halo, the lattice, margin and minimum gap, the rotations each die may take, the netlist, and no keepouts (TapGeometry
checks none, so a manifest that declares one cannot be pinned here). As a layout_checker it returns the contract's
margin, halo_overlap and min_spacing violations, with whole-micrometre amounts rounded up so a miss never reads 0.
The lattice stays the contract validator's exact-integer check.

The wire proxy is TapGeometry's weighted-mean Manhattan centre distance over the netlist (5,120 unordered wire
weights for CPU-DRAM), in mm. The board metric max_chiplet_centre_cell_mean_C is recomputed from a scorer's grid with
gate zero's own selector code (sundai_hotspot.slab049 block_extent and center_cells), so one selector serves the
score, the replay, the board and the results.
"""
from __future__ import annotations

import math

from open_proposals.contract import canonical as hashes
from open_proposals.contract.codes import violation

GRID = 64
LAYOUT_RULES = ("margin", "halo_overlap", "min_spacing")


def _whole_um(mm: float):
    """The integer micrometres a millimetre value names exactly, or None."""
    value = mm * 1000
    nearest = round(value)
    return int(nearest) if abs(value - nearest) < 1e-6 else None


def amount_um(mm: float) -> int:
    """A violation amount in whole micrometres, rounded up (float noise first removed), never below 1."""
    return min(1_000_000, max(1, math.ceil(round(mm * 1000, 6))))


class PinnedTapChecker:
    def __init__(self, manifest: dict):
        from sundai_hotspot.tap_oracle import TAP_CONFIGS, TapGeometry

        fixture = manifest["fixture"]["id"]
        if fixture not in TAP_CONFIGS:
            raise ValueError("the manifest's fixture has no TapGeometry")
        geometry = TapGeometry.load(fixture)
        problem, legality = geometry.problem, geometry.legality
        rules = manifest["legality"]
        dies = manifest["dies"]
        pinned = [
            problem.config_sha256 == manifest["fixture"]["config_sha256"],
            _whole_um(problem.interposer_size_mm) == manifest["fixture"]["frame_um"],
            len(dies) == len(problem.widths_mm),
            _whole_um(legality.center_lattice_mm or 0) == rules["lattice_um"],
            _whole_um(legality.margin_mm) == rules["margin_um"],
            _whole_um(legality.min_die_gap_mm) == rules["min_die_gap_um"],
            legality.rotation == "per_die_90" and rules["rotation"] == "per_die_90",
            rules["keepouts"] == [],
            [[float(value) for value in row] for row in manifest["netlist"]["matrix"]]
            == [list(row) for row in problem.connections],
        ]
        if all(pinned):
            for index, die in enumerate(dies):
                catalogue = legality.orientation_catalog_mm[index]
                pinned += [
                    die["die"] == index,
                    _whole_um(problem.widths_mm[index]) == die["w_um"],
                    _whole_um(problem.heights_mm[index]) == die["h_um"],
                    float(die["power_w"]) == problem.powers_w[index],
                    _whole_um(problem.bump_halos_mm[index]) == die["halo_um"],
                    sorted(die["rot_deg"]) == ([0] if len(catalogue) == 1 else [0, 90]),
                ]
        if not all(pinned):
            raise ValueError("the manifest does not match the pinned TapGeometry fixture")
        self.geometry = geometry
        self.manifest = manifest
        self.manifest_id = hashes.manifest_id(manifest)
        self.frame_um = manifest["fixture"]["frame_um"]
        self.footprints = [(die["w_um"], die["h_um"]) for die in dies]

    def _bound(self, manifest: dict) -> None:
        if manifest is not self.manifest and hashes.manifest_id(manifest) != self.manifest_id:
            raise ValueError("the checker is pinned to another manifest")

    def _centres(self, dies) -> tuple:
        return tuple((die["x_um"] / 1000, die["y_um"] / 1000) for die in dies)

    def __call__(self, item: dict, manifest: dict) -> list:
        """The contract's layout seam: every margin, halo_overlap and min_spacing violation."""
        self._bound(manifest)
        dies = item["dies"]
        design = self.geometry.design_from_centers(self._centres(dies), [die["rot_deg"] == 90 for die in dies])
        found = []
        for miss in self.geometry.layout_violations(design, lattice=False):
            if miss.rule not in LAYOUT_RULES:
                raise ValueError("TapGeometry reported a rule outside the layout seam")
            found.append(violation(miss.rule, dies=sorted(set(miss.dies)), amount_um=amount_um(miss.amount_mm)))
        return found

    def wire_proxy_mm(self, dies) -> float:
        """Weighted-mean Manhattan centre distance over the netlist, in mm (a proxy, never routed wire)."""
        return round(self.geometry.wirelength_mm(self._centres(dies)), 6)

    def centre_cells(self, dies) -> list:
        """Per real chiplet, gate zero's GRID_CENTER cells on the grid-64 map (row 0 at the top): 1, 2 or 4 cells."""
        from sundai_hotspot.slab049 import block_extent, center_cells

        side = self.frame_um / 1e6
        cells = []
        for die in dies:
            width, height = self.footprints[die["die"]]
            if die["rot_deg"] == 90:
                width, height = height, width
            unit = {"name": f"Chiplet_{die['die']}", "leftx": (die["x_um"] - width / 2) / 1e6,
                    "bottomy": (die["y_um"] - height / 2) / 1e6, "width": width / 1e6, "height": height / 1e6}
            cells.append(center_cells(block_extent(unit, side, side, GRID, GRID)))
        return cells

    def centre_means(self, dies, grid) -> list:
        """Each real chiplet's centre-cell mean on the grid, in die order."""
        return [sum(grid[cell["row"]][cell["col"]] * cell["weight"] for cell in cells)
                for cells in self.centre_cells(dies)]

    def selector(self, dies, grid) -> float:
        """max_chiplet_centre_cell_mean_C: per real chiplet the mean of its central cells, then the maximum."""
        return max(self.centre_means(dies, grid))
