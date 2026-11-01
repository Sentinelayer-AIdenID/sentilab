"""Internal authenticated HTTP scorer. Run directly; see README for operator configuration."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from open_proposals.contract import manifest_id, proposal_sha256, run_id as contract_run_id, validate_record
from open_proposals.contract.codes import violation
from sentilab_core.envelope import canonical
from sundai_hotspot.reference_validation import SOLVER_ENVIRONMENT
from ledger import Ledger, Refused
from sandbox import WALL_TIMEOUT_S
from thermal import GRANT_ID, PINNED_SHA256, Thermal, check_config, sha256, stage

HEX = re.compile(r'[0-9a-f]{64}\Z')
RUN = re.compile(r'open-[0-9a-f]{8}-[0-9a-f]{32}\Z')


def now():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


class Rejected(Exception):
    def __init__(self, violations):
        self.violations = list(violations)


class Admission:
    """Operator-signed runtime binding. Contains public data only, reread on every dispatch."""
    def __init__(self, path, public_key, thermal, binary_sha256, image_digest):
        self.path, self.thermal = Path(path), thermal
        self.key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key))
        self.binary_sha256, self.image_digest = binary_sha256, image_digest
        self.read()

    def read(self):
        try:
            document = json.loads(self.path.read_bytes())
            payload = document['payload']
            self.key.verify(bytes.fromhex(document['signature']), canonical(payload))
            if set(payload) != {'schema', 'manifest', 'grant_id', 'scope', 'admission', 'not_before', 'not_after',
                                'enforcement_sha256', 'binary_sha256', 'image_digest'}:
                raise ValueError('invalid admission fields')
            if (payload['schema'] != 'sentilab-scorer-admission/1' or payload['grant_id'] != GRANT_ID
                    or payload['scope'] != 'propose:cpu-dram' or payload['binary_sha256'] != self.binary_sha256
                    or payload['image_digest'] != self.image_digest
                    or not HEX.fullmatch(payload['enforcement_sha256'])):
                raise ValueError('invalid runtime binding')
            manifest = payload['manifest']
            if validate_record('manifest', manifest) or manifest['status'] != 'signed':
                raise ValueError('manifest is not signed/valid')
            if (manifest['statistic']['evaluator']['binary_sha256'] != self.binary_sha256
                    or manifest['checks']['cpu_enforcement_evidence_sha256'] != payload['enforcement_sha256']
                    or manifest['refs']['grant'] != GRANT_ID):
                raise ValueError('manifest runtime binding mismatch')
            self.thermal.check_manifest(manifest)
            return payload, manifest, manifest_id(manifest)
        except Exception:
            raise Rejected([violation('not_open_yet')]) from None

    def current(self):
        payload, manifest, identity = self.read()
        if payload['admission'] == 'closed':
            raise Rejected([violation('manifest_closed')])
        try:
            before = max(datetime.fromisoformat(value.replace('Z', '+00:00'))
                         for value in (payload['not_before'], manifest['window']['opens_at']))
            after = min(datetime.fromisoformat(value.replace('Z', '+00:00'))
                        for value in (payload['not_after'], manifest['window']['closes_at']))
            current = datetime.now(timezone.utc)
            if current >= after:
                raise Rejected([violation('manifest_closed')])
            if payload['admission'] != 'open' or current < before:
                raise Rejected([violation('not_open_yet')])
        except (ValueError, TypeError):
            raise Rejected([violation('not_open_yet')]) from None
        return manifest, identity


def same_evaluation(response, original):
    receipt = response['receipt']
    return (response.get('state') == 'evaluated'
            and receipt['input_sha256'] == original['receipt']['input_sha256']
            and receipt['output_sha256'] == original['receipt']['output_sha256']
            and all(response.get(k) == v for k, v in original.items()
                    if k not in ('receipt', 'state', 'run_id')))


class Scorer:
    def __init__(self, *, ledger, admission, work_root, wall_timeout=WALL_TIMEOUT_S):
        self.token = os.environ.get('SCORER_TOKEN', '')
        if not self.token or not self.token.isascii() or any(c.isspace() for c in self.token):
            raise ValueError('SCORER_TOKEN must be a nonempty ASCII bearer value')
        self.image_digest = os.environ.get('SCORER_IMAGE_DIGEST', '')
        if not re.fullmatch(r'sha256:[0-9a-f]{64}', self.image_digest):
            raise ValueError('SCORER_IMAGE_DIGEST must identify the deployed image')
        engine = Path(os.environ.get('SCORER_ENGINE', '/app/sundai_hotspot6/hotspot'))
        expected = os.environ.get('SCORER_ENGINE_SHA256', PINNED_SHA256)
        if not HEX.fullmatch(expected):
            raise ValueError('SCORER_ENGINE_SHA256 must be a SHA-256 digest')
        self.work_root = Path(work_root).resolve()
        self.work_root.mkdir(parents=True, exist_ok=True)
        self.engine_directory = tempfile.TemporaryDirectory(prefix='engine-', dir=self.work_root)
        self.engine = Path(self.engine_directory.name) / 'hotspot'
        try:
            # Verify the private bytes we will execute; later changes at SCORER_ENGINE cannot change a solve.
            self.engine.write_bytes(engine.read_bytes())
            self.binary_sha256 = sha256(self.engine)
            if not hmac.compare_digest(self.binary_sha256, expected):
                raise ValueError('SCORER_ENGINE SHA-256 mismatch; refusing startup')
            self.engine.chmod(0o500)
            self.thermal = Thermal()
            self.admission = Admission(admission, os.environ['SCORER_ADMISSION_PUBLIC_KEY'], self.thermal,
                                       self.binary_sha256, self.image_digest)
            self.ledger = Ledger(ledger)
            self.ledger.budget_left()  # reject corrupt accounting at startup
            self.wall_timeout = min(wall_timeout, WALL_TIMEOUT_S)
        except BaseException:
            self.engine_directory.cleanup()
            raise

    def close(self):
        self.engine_directory.cleanup()

    def health(self):
        return {'ok': True, 'binary_sha256': self.binary_sha256, 'grant_id': GRANT_ID,
                'image_digest': self.image_digest, 'budget_left_cpu_s': self.ledger.budget_left()}

    def validate(self, proposal, directory=None):
        manifest, identity = self.admission.current()
        if directory is not None:
            try:
                check_config(directory, manifest['fixture']['package']['hotspot_config_sha256'])
            except (OSError, ValueError):
                raise Rejected([violation('not_open_yet')]) from None
        result = self.thermal.validate(json.dumps(proposal, allow_nan=False, separators=(',', ':')).encode(), manifest, identity)
        if result.outcome != 'legal' or result.kind != 'proposal':
            raise Rejected(result.violations or [violation('schema_invalid', path='/schema', keyword='const')])
        return identity

    def solve(self, spec, *, directory=None):
        if directory is None:
            with tempfile.TemporaryDirectory(prefix='solve-', dir=self.work_root) as folder:
                return self.solve(spec, directory=Path(folder))
        start, clock_start = now(), time.monotonic()
        folder = str(directory)
        # Only geometry-derived generator inputs go to the worker; never a proposal, salt or credential.
        process = subprocess.Popen([sys.executable, str(Path(__file__).with_name('sandbox.py')),
                                    str(self.engine), folder, str(self.wall_timeout)],
                                   stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   env=SOLVER_ENVIRONMENT, start_new_session=True)
        try:
            process.stdin.write(json.dumps(dict(spec, hotspot_config_sha256=self.thermal.config_sha256)).encode())
            process.stdin.close()
        except BrokenPipeError:
            pass
        _, status, usage = os.wait4(process.pid, 0)
        process.returncode = os.waitstatus_to_exitcode(status)
        cpu_s = usage.ru_utime + usage.ru_stime  # worker + its reaped descendants, isolated per request
        result_path = directory / 'result.json'
        try:
            result = json.loads(result_path.read_bytes()) if process.returncode == 0 else {'reason': 'oracle_error'}
        except (OSError, ValueError):
            result = {'reason': 'oracle_error'}
        receipt = {'grant_id': GRANT_ID, 'image_digest': self.image_digest, 'binary_sha256': self.binary_sha256,
                   'input_sha256': result.get('input_sha256', {}), 'output_sha256': result.get('output_sha256', {}),
                   'output_map_sha256': result.get('output_sha256', {}).get('sample.grid.steady'),
                   'cpu_s': cpu_s, 'wall_s': time.monotonic() - clock_start, 'started_at': start, 'ended_at': now(),
                   'worker_pid': process.pid, 'engine_pid': result.get('engine_pid'),
                   'workspace_id': directory.name, 'cleanup_pids': result.get('cleanup_pids', [])}
        return result, receipt

    def request(self, operation, request):
        if (not isinstance(request, dict) or set(request) != {'run_id', 'proposal', 'token_ref'}
                or not isinstance(request.get('run_id'), str) or not RUN.fullmatch(request['run_id'])
                or not isinstance(request.get('token_ref'), str) or not HEX.fullmatch(request['token_ref'])
                or not isinstance(request.get('proposal'), dict)):
            raise Rejected([violation('schema_invalid', path='', keyword='required')])
        proposal, run_id, token_ref = request['proposal'], request['run_id'], request['token_ref']
        identity = self.validate(proposal)
        if run_id != contract_run_id(identity, token_ref, proposal_sha256(proposal)):
            raise Refused(409, 'idempotency_conflict')
        binding = {'run_id': run_id, 'token_ref': token_ref, 'principal': 'anon-token/1:' + token_ref,
                   'manifest_id': identity, 'request_key': proposal['proposal_key'],
                   # Domain separation: the contract's private proposal hash is itself a bearer handle.
                   'payload_sha256': digest({'schema': 'scorer-payload/1', 'proposal': proposal}),
                   'geometry_sha256': proposal['geometry_sha256'], 'grant_id': GRANT_ID,
                   'binary_sha256': self.binary_sha256, 'image_digest': self.image_digest}
        spec = self.thermal.spec(proposal)
        with tempfile.TemporaryDirectory(prefix='solve-', dir=self.work_root) as folder:
            directory = Path(folder)
            stage(spec, directory)
            reservation, cached, original = self.ledger.reserve(binding, operation, lambda: self.validate(proposal, directory))
            if cached is not None:
                return cached, 0.0
            receipt = {'grant_id': GRANT_ID, 'image_digest': self.image_digest, 'binary_sha256': self.binary_sha256,
                       'cpu_s': 0.0, 'input_sha256': {}, 'output_sha256': {}, 'output_map_sha256': None,
                       'started_at': now(), 'ended_at': now(), 'wall_s': 0.0}
            try:
                result, receipt = self.solve(spec, directory=directory)
            except Exception:
                # An uncertain launch cannot refund its reservation. No exception text reaches a log or response.
                result, receipt['cpu_s'] = {'reason': 'oracle_error'}, 10.0
            receipt.update(geometry_sha256=proposal['geometry_sha256'], reservation_id=reservation,
                           manifest_id=identity)
            response = {'run_id': run_id, 'receipt': receipt}
            if result.get('reason'):
                response.update(state='failed', codes=[violation(result['reason'])])
            else:
                response.update(result['score'], wire_proxy_mm=self.thermal.wire(proposal), state='evaluated')
            if operation == 'replay':
                equal = same_evaluation(response, original)
                response.update(state='reproduced' if equal else 'not_reproduced',
                                receipts=[original['receipt'], receipt],
                                codes=[] if equal else [violation('reproduction_failed' if result.get('reason')
                                                                else 'reproduction_mismatch')])
            self.ledger.settle(reservation, receipt['cpu_s'], response)
            return response, receipt['cpu_s']


def strict_json(data):
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                raise Rejected([violation('duplicate_key')])
            result[key] = value
        return result

    def constant(_value):
        raise Rejected([violation('nonfinite_number')])

    return json.loads(data, object_pairs_hook=pairs, parse_constant=constant)


def server_for(scorer, address):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def handle_request(self):
            response, status, run_id, token_ref = {'error': 'oracle_error'}, 500, None, None
            cpu_s = 0.0
            try:
                self.connection.settimeout(5)
                values = self.headers.get_all('Authorization', [])
                if len(values) != 1 or not hmac.compare_digest(values[0].encode(), ('Bearer ' + scorer.token).encode()):
                    status, response = 401, {'error': 'unauthorized'}
                elif self.command == 'GET' and self.path == '/v1/health':
                    status, response = 200, scorer.health()
                elif self.command == 'POST' and self.path in ('/v1/score', '/v1/replay'):
                    lengths = self.headers.get_all('Content-Length', [])
                    if self.headers.get('Transfer-Encoding') or len(lengths) != 1:
                        raise Rejected([violation('malformed_json')])
                    length = int(lengths[0])
                    if not 0 <= length <= 8192:
                        raise Rejected([violation('oversize', size_bytes=max(0, length))])
                    request = strict_json(self.rfile.read(length))
                    if isinstance(request, dict):
                        if isinstance(request.get('run_id'), str) and RUN.fullmatch(request['run_id']):
                            run_id = request['run_id']
                        if isinstance(request.get('token_ref'), str) and HEX.fullmatch(request['token_ref']):
                            token_ref = request['token_ref']
                    response, cpu_s = scorer.request(self.path.rsplit('/', 1)[1], request)
                    status = 200
                else:
                    status, response = 404, {'error': 'not_found'}
            except Rejected as exc:
                status, response = 422, {'run_id': run_id, 'state': 'rejected', 'codes': exc.violations}
            except Refused as exc:
                code = 'rate_limited' if exc.code == 'busy' else exc.code
                fields = {'retry_after': 1} if code in ('rate_limited', 'budget_exhausted') else {}
                status, response = exc.status, {'run_id': run_id, 'state': 'rejected', 'error': exc.code,
                                               'codes': [violation(code, **fields)]}
            except (ValueError, UnicodeError, RecursionError, TimeoutError):
                status, response = 400, {'state': 'rejected', 'codes': [violation('malformed_json')]}
            except Exception:
                status, response = 500, {'error': 'oracle_error'}
            finally:
                print(json.dumps({'run_id': run_id, 'token_ref': token_ref,
                                  'state': response.get('state', response.get('error', 'healthy')), 'cpu_s': cpu_s}),
                      flush=True)
            data = json.dumps(response, allow_nan=False, separators=(',', ':')).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Connection', 'close')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.close_connection = True
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass

        do_GET = handle_request
        do_POST = handle_request

    server = ThreadingHTTPServer(address, Handler)
    server.daemon_threads = False  # shutdown waits for reservation settlement before removing the engine copy
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ledger', type=Path, required=True)
    parser.add_argument('--admission', type=Path, required=True)
    parser.add_argument('--work-root', type=Path, required=True)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    try:
        scorer = Scorer(ledger=args.ledger, admission=args.admission, work_root=args.work_root)
    except (ValueError, OSError, KeyError, Rejected) as exc:
        detail = str(exc) if isinstance(exc, ValueError) else 'missing or invalid scorer configuration/admission'
        parser.exit(2, detail + '\n')
    try:
        with server_for(scorer, (args.host, args.port)) as server:
            server.serve_forever()
    finally:
        scorer.close()


if __name__ == '__main__':
    main()
