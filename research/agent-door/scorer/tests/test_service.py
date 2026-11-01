import copy
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import hashlib
import http.client
import json
import os
from pathlib import Path
import secrets
import sys
import threading
import time

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ledger import Ledger, Refused
from service import Scorer, server_for
from thermal import GRANT_ID, PINNED_SHA256, sha256
from open_proposals.contract import geometry_sha256, manifest_id, proposal_sha256, run_id
from sentilab_core.envelope import canonical
from test_thermal import SCORER, proposal_for


class Harness:
    def __init__(self, tmp_path, monkeypatch, mode='normal', wall_timeout=30, engine=None):
        self.path = tmp_path
        self.control = tmp_path / 'control'
        self.control.write_text(mode)
        self.engine = tmp_path / 'fake-engine'
        source = (Path(__file__).with_name('fake_engine.py')).read_text().replace('__CONTROL__', str(self.control))
        # The solver environment has no PATH; use the interpreter running the tests.
        self.engine.write_bytes(Path(engine).read_bytes()) if engine else self.engine.write_text(f'#!{sys.executable}\n{source}')
        self.engine.chmod(0o700)
        self.secret = secrets.token_urlsafe(24)  # memory only; never a test token on disk
        self.key = Ed25519PrivateKey.generate()  # memory only; only the public key/signature are serialized
        self.image = 'sha256:' + hashlib.sha256(b'test-image').hexdigest()
        self.admission = tmp_path / 'admission.json'
        self.ledger = tmp_path / 'ledger.jsonl'
        fixtures = json.loads((SCORER.parents[2] / 'contracts/open-proposal-v1/golden/manifests.json').read_text())
        self.manifest = copy.deepcopy(fixtures['manifests']['S'])
        physical = fixtures['manifests']['M']
        for name in ('problem', 'fixture', 'dies', 'netlist', 'legality'):
            self.manifest[name] = copy.deepcopy(physical[name])
        self.manifest['fixture']['package']['hotspot_config_sha256'] = hashlib.sha256(b'test-config').hexdigest()
        self.manifest['statistic']['real_chiplets'] = [f'Chiplet_{i}' for i in range(8)]
        self.manifest['statistic']['evaluator']['binary_sha256'] = sha256(self.engine)
        self.manifest['refs']['grant'] = GRANT_ID
        self.manifest['terms']['accepted_versions'] = ['sentilab-open-terms/1@' + 'a' * 64]
        current = datetime.now(timezone.utc)
        self.before, self.after = (current - timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M:%SZ'), (current + timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M:%SZ')
        self.manifest['window'] = {'opens_at': self.before, 'closes_at': self.after}
        self.write_admission()
        for k, v in {'SCORER_ENGINE': str(self.engine), 'SCORER_ENGINE_SHA256': sha256(self.engine),
                     'SCORER_TOKEN': self.secret, 'SCORER_IMAGE_DIGEST': self.image,
                     'SCORER_ADMISSION_PUBLIC_KEY': self.key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()}.items():
            monkeypatch.setenv(k, v)
        self.scorer = Scorer(ledger=self.ledger, admission=self.admission, work_root=tmp_path / 'work', wall_timeout=wall_timeout)
        self.server = server_for(self.scorer, ('127.0.0.1', 0))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def write_admission(self, **updates):
        payload = {'schema': 'sentilab-scorer-admission/1', 'manifest': self.manifest, 'grant_id': GRANT_ID,
                   'scope': 'propose:cpu-dram', 'admission': 'open', 'not_before': self.before, 'not_after': self.after,
                   'enforcement_sha256': self.manifest['checks']['cpu_enforcement_evidence_sha256'],
                   'binary_sha256': sha256(self.engine), 'image_digest': self.image, **updates}
        document = {'payload': payload, 'signature': self.key.sign(canonical(payload)).hex()}
        temporary = self.admission.with_suffix('.tmp')
        temporary.write_text(json.dumps(document))
        temporary.replace(self.admission)

    def request(self, key='example', token='one'):
        proposal = proposal_for(self.manifest)
        proposal['proposal_key'] = key
        ref = hashlib.sha256(token.encode()).hexdigest()
        return {'proposal': proposal, 'token_ref': ref,
                'run_id': run_id(manifest_id(self.manifest), ref, proposal_sha256(proposal))}

    def call(self, path, data=None, auth=True):
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=40)
        headers = {'Authorization': 'Bearer ' + self.secret} if auth is True else ({} if auth is False else {'Authorization': auth})
        connection.request('GET' if data is None else 'POST', path,
                           None if data is None else json.dumps(data).encode(), headers)
        response = connection.getresponse()
        result = response.status, json.loads(response.read())
        connection.close()
        return result

    def rows(self):
        return [json.loads(line) for line in self.ledger.read_text().splitlines()]

    def close(self):
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()
        self.scorer.close()


@pytest.fixture
def harness(tmp_path, monkeypatch):
    instances = []
    def create(mode='normal', wall_timeout=30):
        h = Harness(tmp_path, monkeypatch, mode, wall_timeout)
        instances.append(h)
        return h
    yield create
    for h in instances:
        h.close()


def test_fake_engine_executes_with_sandbox_environment(harness):
    h = harness()
    status, score = h.call('/v1/score', h.request())
    assert status == 200 and score['state'] == 'evaluated', score
    observed = json.loads((h.path / f"observed-{score['receipt']['engine_pid']}.json").read_text())
    assert observed['executable'] == sys.executable
    assert 'PATH' not in observed['environment']
    assert 'SCORER_TOKEN' not in observed['environment']
    assert observed['network_denied']


def test_http_score_replay_identity_and_isolation(harness, capsys):
    h = harness()
    request = h.request()
    for auth in (False, 'Bearer invalid'):
        assert h.call('/v1/health', auth=auth)[0] == 401
        assert h.call('/v1/score', request, auth=auth)[0] == 401
    assert h.call('/v1/health')[1]['budget_left_cpu_s'] == 3600
    assert h.rows() == []
    status, score = h.call('/v1/score', request)
    assert status == 200 and score['state'] == 'evaluated', score
    assert score['native_all_block_max_c'] == pytest.approx(115.93)
    assert score['max_chiplet_centre_mean_c'] == pytest.approx(114.93)
    assert score['active_grid_max_c'] == pytest.approx(119.07)
    assert score['hotspot_ok'] is False
    assert score['metric_id'] == 'max_chiplet_centre_cell_mean_C'
    assert score['references']['snapped']['max_chiplet_centre_mean_c'] is None
    assert score['wire_proxy_mm'] == 9.5
    assert set(score['per_die_c']) == {'C0', 'C1', 'C2', 'C3', 'D0', 'D1', 'D2', 'D3'}
    status, replay = h.call('/v1/replay', request)
    assert status == 200 and replay['state'] == 'reproduced', replay
    first, second = replay['receipts']
    for receipt in (first, second):
        assert receipt['binary_sha256'] == sha256(h.engine)
        assert receipt['image_digest'] == h.image and receipt['grant_id'] == GRANT_ID
        assert receipt['geometry_sha256'] == request['proposal']['geometry_sha256']
        assert len(receipt['input_sha256']) == 9
        assert len(receipt['output_sha256']) == 2
        assert receipt['cpu_s'] > 0 and receipt['wall_s'] > 0
        assert receipt['started_at'] < receipt['ended_at']
    assert first['engine_pid'] != second['engine_pid']
    assert first['worker_pid'] != second['worker_pid']
    assert first['workspace_id'] != second['workspace_id']
    assert first['output_map_sha256'] == second['output_map_sha256']
    assert [r['phase'] for r in h.rows()] == ['reserved', 'settled', 'reserved', 'settled']
    assert h.call('/v1/score', request)[1] == score
    assert h.call('/v1/replay', request)[1] == replay
    assert len(h.rows()) == 4
    for file in h.path.glob('observed-*.json'):
        observed = json.loads(file.read_text())
        assert observed['limits'] == [10, 10]
        assert observed['network_denied']
        assert 'SCORER_TOKEN' not in observed['environment']
    assert h.secret not in h.ledger.read_text()
    assert h.secret not in capsys.readouterr().out


@pytest.mark.parametrize('mode,state,code', [('error', 'failed', 'oracle_error'), ('truncated', 'failed', 'oracle_error'),
                                           ('timeout', 'failed', 'timeout'), ('escape', 'failed', 'timeout')])
def test_failed_solves_are_charged_and_descendants_reaped(harness, mode, state, code):
    h = harness(mode, wall_timeout=0.6)
    status, score = h.call('/v1/score', h.request())
    assert status == 200 and score['state'] == state, score
    assert score['codes'] == [{'code': code}]
    assert h.rows()[0]['cpu_s'] == 10
    assert h.rows()[1]['cpu_s'] == score['receipt']['cpu_s'] > 0
    if mode == 'escape':
        child = int((h.path / 'escaped.pid').read_text())
        assert child in score['receipt']['cleanup_pids']
        assert not Path(f'/proc/{child}').exists()
    assert not Path('/proc/' + str(score['receipt']['engine_pid'])).exists()


def test_replay_mismatch_and_lower_active_guard(harness):
    h = harness()
    request = h.request()
    assert h.call('/v1/score', request)[1]['state'] == 'evaluated'
    h.control.write_text('mismatch')
    replay = h.call('/v1/replay', request)[1]
    assert replay['state'] == 'not_reproduced'
    assert replay['codes'] == [{'code': 'reproduction_mismatch'}]
    assert len(replay['receipts']) == 2
    h.control.write_text('lower')
    assert h.call('/v1/score', h.request('second'))[1]['hotspot_ok'] is True


@pytest.mark.parametrize('change,code', [('overlap', 'halo_overlap'), ('edge', 'margin'), ('lattice', 'lattice'),
                                       ('extra', 'unknown_field'), ('terms', 'terms_not_accepted')])
def test_http_illegal_input_never_dispatches(harness, change, code):
    h = harness()
    request = h.request()
    p = request['proposal']
    if change == 'overlap':
        p['dies'][1].update(x_um=p['dies'][0]['x_um'], y_um=p['dies'][0]['y_um'])
    elif change == 'edge':
        p['dies'][0]['x_um'] = 500
    elif change == 'lattice':
        p['dies'][0]['x_um'] += 1
    elif change == 'extra':
        p['extra'] = 'untrusted'
    elif change == 'terms':
        p['terms'] = 'sentilab-open-terms/2@' + 'b' * 64
    p['geometry_sha256'] = geometry_sha256(p, h.manifest)
    status, result = h.call('/v1/score', request)
    assert status == 422 and code in [v['code'] for v in result['codes']]
    assert h.rows() == []
    assert list(h.path.glob('observed-*.json')) == []


def test_closed_or_invalid_admission_refuses_even_after_success(harness):
    h = harness()
    assert h.call('/v1/score', h.request())[1]['state'] == 'evaluated'
    h.write_admission(admission='closed')
    status, result = h.call('/v1/score', h.request('second'))
    assert status == 422 and result['codes'] == [{'code': 'manifest_closed'}]
    h.write_admission()
    document = json.loads(h.admission.read_text())
    document['payload']['not_after'] = '2099-01-01T00:00:00Z'
    h.admission.write_text(json.dumps(document))
    assert h.call('/v1/score', h.request('third'))[1]['codes'] == [{'code': 'not_open_yet'}]
    assert len(h.rows()) == 2


def test_startup_pin_default_and_missing_image(harness, monkeypatch):
    h = harness()
    monkeypatch.delenv('SCORER_ENGINE_SHA256')
    with pytest.raises(ValueError, match='SHA-256 mismatch'):
        Scorer(ledger=h.ledger, admission=h.admission, work_root=h.path / 'bad')
    monkeypatch.setenv('SCORER_ENGINE_SHA256', sha256(h.engine))
    monkeypatch.delenv('SCORER_IMAGE_DIGEST')
    with pytest.raises(ValueError, match='SCORER_IMAGE_DIGEST'):
        Scorer(ledger=h.ledger, admission=h.admission, work_root=h.path / 'bad')


def test_concurrency_four_global_and_three_per_token(harness):
    h = harness('sleep-normal')
    with ThreadPoolExecutor(max_workers=4) as pool:
        pending = [pool.submit(h.call, '/v1/score', h.request(str(i), str(i))) for i in range(4)]
        deadline = time.monotonic() + 5
        while len(h.rows()) < 4 and time.monotonic() < deadline:
            time.sleep(0.01)
        assert len(h.rows()) == 4
        status, result = h.call('/v1/score', h.request('fifth', 'fifth'))
        assert status == 429 and result['error'] == 'busy'
        assert all(f.result()[1]['state'] == 'evaluated' for f in pending)
    with ThreadPoolExecutor(max_workers=3) as pool:
        pending = [pool.submit(h.call, '/v1/score', h.request('same' + str(i), 'same')) for i in range(3)]
        deadline = time.monotonic() + 5
        while len(h.rows()) < 11 and time.monotonic() < deadline:
            time.sleep(0.01)
        status, result = h.call('/v1/score', h.request('fourth', 'same'))
        assert status == 403 and result['error'] == 'budget_exhausted'
        assert all(f.result()[1]['state'] == 'evaluated' for f in pending)


def test_atomic_budget_caps_crash_reservation_and_cross_instance_lock(tmp_path):
    path = tmp_path / 'ledger'
    def binding(i, token='same'):
        return {'run_id': str(i), 'principal': token, 'token_ref': token, 'manifest_id': 'manifest',
                'request_key': str(i), 'payload_sha256': str(i)}
    # No settlements: a replacement Ledger still charges every reserved CPU-second.
    for i in range(3):
        Ledger(path).reserve(binding(i), 'score', lambda: None)
    assert Ledger(path).budget_left() == 3570
    with pytest.raises(Refused) as caught:
        Ledger(path).reserve(binding(4), 'score', lambda: None)
    assert caught.value.status == 403
    # Consume the global cap via production reservation/settlement, without fake solves or editing the ledger.
    path = tmp_path / 'global'
    for i in range(360):
        ledger = Ledger(path)
        reservation, _, _ = ledger.reserve(binding(i, str(i)), 'score', lambda: None)
        ledger.settle(reservation, 10, {'state': 'failed'})
    with pytest.raises(Refused) as caught:
        Ledger(path).reserve(binding(361, 'new'), 'score', lambda: None)
    assert caught.value.status == 403 and Ledger(path).budget_left() == 0


def test_principal_and_payload_are_bound_to_request_key(harness):
    h = harness()
    request = h.request()
    assert h.call('/v1/score', request)[1]['state'] == 'evaluated'
    changed = h.request()
    changed['proposal']['salt'] = '1' * 32
    changed['run_id'] = run_id(manifest_id(h.manifest), changed['token_ref'], proposal_sha256(changed['proposal']))
    assert h.call('/v1/score', changed)[0] == 409
    intruder = h.request(token='another')
    intruder['run_id'] = request['run_id']
    assert h.call('/v1/replay', intruder)[0] == 409
    assert len(h.rows()) == 2


def test_dispatch_rechecks_admission_under_reservation_lock(harness):
    h = harness()
    with ThreadPoolExecutor(max_workers=1) as pool:
        with h.scorer.ledger.locked():
            pending = pool.submit(h.call, '/v1/score', h.request())
            # Observe the real HTTP thread blocked on flock, after its intake validation.
            deadline = time.monotonic() + 5
            blocked = False
            while time.monotonic() < deadline and not blocked:
                for frame in sys._current_frames().values():
                    while frame:
                        if (frame.f_code.co_name == 'locked' and frame.f_code.co_filename.endswith('/ledger.py')
                                and frame.f_locals.get('records') is None):
                            blocked = True
                        frame = frame.f_back
                time.sleep(0.01)
            assert blocked
            h.write_admission(admission='closed')
        status, result = pending.result()
    assert status == 422 and result['codes'] == [{'code': 'manifest_closed'}]
    assert h.rows() == []


def test_replay_failure_is_charged_and_retains_both_receipts(harness):
    h = harness()
    request = h.request()
    score = h.call('/v1/score', request)[1]
    h.control.write_text('error')
    replay = h.call('/v1/replay', request)[1]
    assert replay['state'] == 'not_reproduced'
    assert replay['codes'] == [{'code': 'reproduction_failed'}]
    assert replay['receipts'][0] == score['receipt']
    assert h.rows()[-1]['cpu_s'] > 0


def test_engine_replacement_cannot_change_startup_identity(harness):
    h = harness()
    measured = sha256(h.engine)
    h.engine.write_text('#!/bin/sh\nexit 9\n')
    response = h.call('/v1/score', h.request())[1]
    assert response['state'] == 'evaluated'
    assert response['receipt']['binary_sha256'] == measured


def test_http_duplicate_keys_and_extra_envelope_are_refused(harness, capsys):
    h = harness()
    request = h.request()
    request['free_text'] = 'must-never-appear-in-logs'
    assert h.call('/v1/score', request)[0] == 422
    connection = http.client.HTTPConnection(*h.server.server_address)
    connection.request('POST', '/v1/score', b'{"run_id":1,"run_id":2}',
                       {'Authorization': 'Bearer ' + h.secret})
    response = connection.getresponse()
    assert response.status == 422
    assert json.loads(response.read())['codes'] == [{'code': 'duplicate_key'}]
    connection.close()
    assert h.rows() == []
    assert 'must-never-appear-in-logs' not in capsys.readouterr().out


def test_http_integral_float_stays_invalid_before_canonical_hashing(harness):
    h = harness()
    request = h.request()
    request['proposal']['dies'][0]['x_um'] = float(request['proposal']['dies'][0]['x_um'])
    status, result = h.call('/v1/score', request)
    assert status == 422
    assert {'code': 'schema_invalid', 'path': '/dies/0/x_um', 'keyword': 'type'} in result['codes']
    assert h.rows() == []


def test_restart_retains_idempotency_and_replay(harness):
    h = harness()
    request = h.request()
    score = h.call('/v1/score', request)[1]
    h.close()
    h.scorer = Scorer(ledger=h.ledger, admission=h.admission, work_root=h.path / 'work')
    h.server = server_for(h.scorer, ('127.0.0.1', 0))
    h.thread = threading.Thread(target=h.server.serve_forever, daemon=True)
    h.thread.start()
    assert h.call('/v1/score', request)[1] == score
    assert len(h.rows()) == 2
    assert h.call('/v1/replay', request)[1]['state'] == 'reproduced'


def reserve_in_process(path, number, barrier, output):
    barrier.wait()
    try:
        reservation, _, _ = Ledger(path).reserve(
            {'run_id': str(number), 'principal': 'same', 'token_ref': 'same', 'manifest_id': 'same',
             'request_key': str(number), 'payload_sha256': str(number)}, 'score', lambda: None)
        output.put(('reserved', reservation))
    except Refused as exc:
        output.put(('refused', exc.status))


def test_reservation_is_atomic_across_processes(tmp_path):
    import multiprocessing
    context = multiprocessing.get_context('fork')
    barrier, output = context.Barrier(8), context.Queue()
    path = tmp_path / 'ledger'
    processes = [context.Process(target=reserve_in_process, args=(path, i, barrier, output)) for i in range(8)]
    for process in processes:
        process.start()
    for process in processes:
        process.join(10)
        assert process.exitcode == 0
    results = [output.get(timeout=1) for _ in processes]
    assert sum(r[0] == 'reserved' for r in results) == 3
    assert sum(r == ('refused', 403) for r in results) == 5
    assert Ledger(path).budget_left() == 3570
    output.close()
