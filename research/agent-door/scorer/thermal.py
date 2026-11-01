"""CPU-DRAM adapter; numerical generation and selectors belong to gate zero."""
from __future__ import annotations

import hashlib
import math
from pathlib import Path

from open_proposals.contract import validate_local
from open_proposals.contract.codes import violation
from sundai_hotspot import gate_zero, slab049
from sundai_hotspot.tap_oracle import TapGeometry

PINNED_SHA256 = '751b357f6b5af395a4447d6e3bfeef3a75eb447091798365a3db4f0e00618cc6'
GRANT_ID = 'slab-demo-20261101'
REFERENCE_ID = 'micro150-tap25d-fig5a-raw'
METRIC_ID = 'max_chiplet_centre_cell_mean_C'
METRIC = {
    'metric_id': METRIC_ID,
    'metric_definition': 'Maximum over Chiplet_0..7 of the mean of its 1, 2 or 4 central HotSpot 6 grid-64 cells.',
    'temperature_unit': 'degC',
    'metric_precision': {'grid_resolution_K': 0.01, 'averaging_adds_precision': False},
    'references': {
        'raw': {'layout_id': REFERENCE_ID,
                'layout_sha256': gate_zero.reference(REFERENCE_ID).raw_layout_sha256,
                'metric_id': METRIC_ID, 'max_chiplet_centre_mean_c': 115.935,
                'native_all_block_max_c': 115.93, 'active_grid_max_c': 119.07,
                'wire_proxy_mm': 9.38487},
        'snapped': {'metric_id': METRIC_ID, 'max_chiplet_centre_mean_c': None, 'wire_proxy_mm': 9.5},
    },
    'label': 'simulated, not silicon',
}


def sha256(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


class Thermal:
    def __init__(self):
        self.geometry = TapGeometry.load('micro150-45mm')
        self.raw_spec = slab049.reference_spec(REFERENCE_ID)
        reference = gate_zero.reference(REFERENCE_ID)
        self.config_sha256 = gate_zero.frozen_inputs(reference)['new_hotspot.config']
        # Package config is independent of die placement. Use the gate-zero
        # bytes for admission; generation belongs to the reserved worker tree.
        self.config_bytes = (gate_zero.REPO_ROOT / reference.inputs / 'new_hotspot.config').read_bytes()

    def check_manifest(self, manifest):
        """A signed manifest cannot change the problem or relax the pinned geometry."""
        p, rules = self.geometry.problem, self.geometry.legality
        if (manifest['problem'] != 'micro150' or manifest['fixture']['id'] != p.fixture_id
                or manifest['fixture']['config_sha256'] != p.config_sha256
                or manifest['fixture']['frame_um'] != 45000 or len(manifest['dies']) != 8):
            raise ValueError('manifest does not bind micro150-45mm')
        if manifest['fixture']['package']['hotspot_config_sha256'] != self.config_sha256:
            raise ValueError('manifest package config differs from gate zero')
        if (manifest['netlist']['matrix'] != [list(row) for row in p.connections]
                or manifest['fixture']['ambient_c'] != p.ambient_c
                or manifest['fixture']['link_type'] != p.link_type
                or manifest['statistic']['grid'] != 64
                or manifest['statistic']['record_field'] != 'chiplet_centre_mapping.max_C'):
            raise ValueError('manifest physics or selector differs from gate zero')
        for i, die in enumerate(manifest['dies']):
            expected = (i, round(p.widths_mm[i] * 1000), round(p.heights_mm[i] * 1000),
                        p.powers_w[i], round(p.bump_halos_mm[i] * 1000), [0, 90] if i < 4 else [0])
            if tuple(die[k] for k in ('die', 'w_um', 'h_um', 'power_w', 'halo_um', 'rot_deg')) != expected:
                raise ValueError('manifest die catalogue differs from micro150')
        law = manifest['legality']
        if (law['units'], law['anchor'], law['lattice_um'], law['margin_um'], law['min_die_gap_um'],
                law['keepouts']) != ('um', 'die-centre', rules.center_lattice_mm * 1000,
                                    rules.margin_mm * 1000, rules.min_die_gap_mm * 1000, []):
            raise ValueError('manifest legality differs from micro150')

    def design(self, proposal):
        return self.geometry.design_from_centers(
            [(d['x_um'] / 1000, d['y_um'] / 1000) for d in proposal['dies']],
            [d['rot_deg'] == 90 for d in proposal['dies']])

    def layout_checker(self, proposal, manifest):
        return [violation(v.rule, dies=list(v.dies), amount_um=math.ceil(v.amount_mm * 1000 - 1e-9))
                for v in self.geometry.layout_violations(self.design(proposal), lattice=False)]

    def validate(self, note, manifest, manifest_id):
        return validate_local(note, manifests={manifest_id: manifest}, manifest_id=manifest_id,
                              layout_checker=self.layout_checker)

    def spec(self, proposal):
        # The same TAP inputs and generator as validate-reference; only the candidate centres/rotations change.
        spec = dict(self.raw_spec)
        centers = self.geometry.centers_for(self.design(proposal))
        spec.update(x=[p[0] for p in centers], y=[p[1] for p in centers],
                    rotated=[d['rot_deg'] == 90 for d in proposal['dies']])
        return spec

    def wire(self, proposal):
        return self.geometry.wirelength_mm(self.geometry.centers_for(self.design(proposal)))


def stage(spec, directory):
    files = slab049.generate_reference(spec, directory)
    for name, data in files.items():
        (directory / name).write_bytes(data)
    return {name: sha256(directory / name) for name in files}


def check_config(directory, expected):
    if sha256(directory / 'new_hotspot.config') != expected:
        raise ValueError('staged HotSpot config differs from signed package')


def read_score(directory):
    record = slab049.summarize_evaluation(directory, grid_size=64, grid_format='all_layers')
    chiplets = record['chiplet_centre_mapping']['chiplets']
    if {c['name'] for c in chiplets} != {f'Chiplet_{i}' for i in range(8)}:
        raise ValueError('incomplete CPU-DRAM output')
    per_die = {('C' + str(i) if i < 4 else 'D' + str(i - 4)):
               next(c['centre_C'] for c in chiplets if c['name'] == f'Chiplet_{i}') for i in range(8)}
    native = record['historical_tap_stdout_selector']['on_steady_file_C']
    centre = record['chiplet_centre_mapping']['max_C']
    active = record['active_layer_grid_peak']['peak_C']
    return {**METRIC, 'native_all_block_max_c': native, 'max_chiplet_centre_mean_c': centre,
            'active_grid_max_c': active, 'native_all_block_max_C': native, 'active_layer_peak_C': active,
            'peak_c': centre, 'per_die_c': per_die, 'hotspot_ok': active < 119.07}
