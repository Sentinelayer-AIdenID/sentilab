"""Run inside the pinned gate-zero image. A skip is not numerical reproduction evidence."""
import os
from pathlib import Path

import pytest
from test_service import Harness
from service import same_evaluation
from thermal import PINNED_SHA256, REFERENCE_ID, sha256
from sundai_hotspot import gate_zero


def test_pinned_raw_reference_and_fresh_process_replay(tmp_path, monkeypatch):
    engine = Path(os.environ.get('SCORER_ENGINE', '/nonexistent'))
    if not engine.is_file() or sha256(engine) != PINNED_SHA256:
        pytest.skip('SCORER_ENGINE does not identify the pinned gate-zero binary')
    h = Harness(tmp_path, monkeypatch, engine=engine)
    try:
        raw_scores = []
        for operation in ('score', 'replay'):
            # Raw geometry is reference-only; it must never be admitted by the candidate HTTP route.
            binding = {'run_id': 'raw-reference', 'principal': 'reference-test', 'token_ref': 'reference-test',
                       'manifest_id': 'reference-test', 'request_key': 'raw-reference',
                       'payload_sha256': gate_zero.reference(REFERENCE_ID).raw_layout_sha256}
            reservation, _, _ = h.scorer.ledger.reserve(binding, operation, lambda: None)
            result, receipt = h.scorer.solve(h.scorer.thermal.raw_spec)
            receipt['raw_layout_sha256'] = binding['payload_sha256']
            response = {**result.get('score', {}), 'receipt': receipt,
                        'state': 'failed' if result.get('reason') else 'evaluated'}
            h.scorer.ledger.settle(reservation, receipt['cpu_s'], response)
            assert result.get('reason') is None, result
            assert receipt['input_sha256'] == gate_zero.frozen_inputs(gate_zero.reference(REFERENCE_ID))
            assert response['native_all_block_max_c'] == pytest.approx(115.93, abs=1e-9)
            assert response['max_chiplet_centre_mean_c'] == pytest.approx(115.935, abs=1e-9)
            assert response['active_grid_max_c'] == pytest.approx(119.07, abs=1e-9)
            assert response['hotspot_ok'] is False
            raw_scores.append(response)
        assert same_evaluation(raw_scores[1], raw_scores[0])
        assert raw_scores[0]['receipt']['engine_pid'] != raw_scores[1]['receipt']['engine_pid']
        assert raw_scores[0]['receipt']['workspace_id'] != raw_scores[1]['receipt']['workspace_id']
        # Legal snapped reference has its OWN measured score; never attach the raw values to it.
        request = h.request()
        status, snapped = h.call('/v1/score', request)
        assert status == 200 and snapped['state'] == 'evaluated'
        assert h.call('/v1/replay', request)[1]['state'] == 'reproduced'
    finally:
        h.close()
