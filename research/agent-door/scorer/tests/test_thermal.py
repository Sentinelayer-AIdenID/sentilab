import json
import os
from pathlib import Path
import sys

import pytest

SCORER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCORER))
from thermal import REFERENCE_ID, Thermal, stage
from open_proposals.contract import geometry_sha256, manifest_id
from sundai_hotspot import gate_zero, slab049


@pytest.fixture
def manifest():
    root = SCORER.parents[2]
    value = json.loads((root / 'contracts/open-proposal-v1/golden/manifests.json').read_text())['manifests']['M']
    value['terms']['accepted_versions'] = ['sentilab-open-terms/1@' + 'a' * 64]
    return value


def proposal_for(manifest):
    raw = Thermal().raw_spec
    result = {'schema': 'sentilab-open-proposal/1', 'manifest_id': manifest_id(manifest), 'terms': 'sentilab-open-terms/1@' + 'a' * 64,
              'proposal_key': 'example', 'parent': None, 'visibility': 'public', 'salt': '0' * 32,
              'units': 'um', 'anchor': 'die-centre',
              'dies': [{'die': i, 'x_um': round(raw['x'][i] * 2) * 500,
                        'y_um': round(raw['y'][i] * 2) * 500, 'rot_deg': 90 if raw['rotated'][i] else 0}
                       for i in range(8)]}
    result['geometry_sha256'] = geometry_sha256(result, manifest)
    return result


def test_raw_generation_is_frozen_and_snapped_is_distinct(tmp_path, manifest):
    thermal = Thermal()
    thermal.check_manifest(manifest)
    hashes = stage(thermal.raw_spec, tmp_path)
    assert hashes == gate_zero.frozen_inputs(gate_zero.reference(REFERENCE_ID))
    proposal = proposal_for(manifest)
    assert thermal.validate(json.dumps(proposal).encode(), manifest, manifest_id(manifest)).outcome == 'legal'
    assert thermal.wire(proposal) == 9.5
    centers = list(zip(thermal.raw_spec['x'], thermal.raw_spec['y']))
    assert thermal.geometry.wirelength_mm(centers) == pytest.approx(9.38487, abs=0.00001)


@pytest.mark.parametrize('change,code', [('overlap', 'halo_overlap'), ('edge', 'margin'),
                                       ('lattice', 'lattice'), ('rotation', 'rotation_not_allowed'),
                                       ('extra', 'unknown_field'), ('hash', 'geometry_hash_mismatch')])
def test_dispatch_validator_uses_real_geometry(manifest, change, code):
    thermal = Thermal()
    p = proposal_for(manifest)
    if change == 'overlap':
        p['dies'][1].update(x_um=p['dies'][0]['x_um'], y_um=p['dies'][0]['y_um'])
    elif change == 'edge':
        p['dies'][0]['x_um'] = 500
    elif change == 'lattice':
        p['dies'][0]['x_um'] += 1
    elif change == 'rotation':
        p['dies'][4]['rot_deg'] = 90
    elif change == 'extra':
        p['engine'] = 'forbidden'
    p['geometry_sha256'] = '0' * 64 if change == 'hash' else geometry_sha256(p, manifest)
    result = thermal.validate(json.dumps(p).encode(), manifest, manifest_id(manifest))
    assert result.outcome == 'rejected'
    assert code in [v['code'] for v in result.violations]


def test_public_case_matches_gate_zero_inputs(tmp_path):
    case_path = Path(os.environ.get('SCORER_REFERENCE_CASE', '/workspace/inputs/case.json'))
    if not case_path.is_file():
        pytest.skip('public af66bcfc case mirror not mounted')
    from thermal import sha256
    assert sha256(case_path) == 'b01b4a33c530db309889b8ad9feda96701ca5a7b9cb4b17562a6750a08b0805a'
    case = json.loads(case_path.read_text())
    thermal = Thermal()
    p = thermal.geometry.problem
    for i, die in enumerate(case['cases']['B']['chiplets']):
        assert die['catalog_width_height_mm'] == [p.widths_mm[i], p.heights_mm[i]]
        assert die['power_W'] == p.powers_w[i]
        assert die['microbump_halo_m'] == pytest.approx(p.bump_halos_mm[i] / 1000)
    stage(thermal.raw_spec, tmp_path)
    layers = slab049.read_lcf(tmp_path / 'samplelayers.lcf', tmp_path)
    for actual, public in zip(layers, case['stack']):
        assert actual['thickness'] == public['thickness_m']
        assert actual['resistivity'] == public['default_rho_mK_per_W']
        assert actual['power'] == public['has_power']
    config = slab049.read_hotspot_config(tmp_path / 'new_hotspot.config')
    for name, index in [('spreader', 6), ('sink', 7)]:
        public = case['stack'][index]
        assert float(config['t_' + name]) == public['thickness_m']
        assert float(config['k_' + name]) == public['default_k_W_per_mK']
        assert float(config['s_' + name]) == pytest.approx(public['extent_m']['x1'] - public['extent_m']['x0'])
