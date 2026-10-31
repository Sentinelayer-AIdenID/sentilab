"""Finite controller fakes only: never invoke SSH, Docker, a model or a solver."""
from contextlib import contextmanager
import hashlib
import importlib.util
import http.server
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest import mock

spec = importlib.util.spec_from_file_location('serve047', Path(__file__).with_name('serve047.py'))
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)
ORIGINAL_PORT_CLOSED = s.port_closed


class FakeDocker:
    def __init__(self, case):
        self.case, self.objects, self.calls = case, {}, []
        self.cid = 'a' * 64
        self.fail_create = self.fail_rm = False

    def command(self, argv, **kwargs):
        self.case.clock.now += 0.1
        self.calls.append(argv)
        self.case.assertEqual(argv[:3], ['/usr/bin/docker', '--host', 'unix:///var/run/docker.sock'])
        operation, rest = argv[3], argv[4:]
        if operation == 'create':
            if self.fail_create:
                raise s.Refusal('command_ambiguous')
            labels = dict(x.split('=', 1) for i, x in enumerate(rest) if i and rest[i-1] == '--label')
            self.objects[self.cid] = {'Id': self.cid, 'Image': s.IMAGE, 'Name': '/' + rest[rest.index('--name')+1],
                                      'Labels': labels, 'State': {'Running': False, 'ExitCode': 0}}
            return 0, self.cid.encode(), b''
        if operation == 'inspect':
            value = self.objects.get(rest[-1])
            return (0, s.encode(value), b'') if value else (1, b'', b'No such container')
        if operation == 'ps':
            return 0, '\n'.join(self.objects).encode(), b''
        if operation == 'logs':
            return 0, b'fixture stdout\n', b'fixture stderr\n'
        target = rest[-1]
        self.case.assertRegex(target, r'^[0-9a-f]{64}$')
        if operation in {'start', 'stop', 'kill'}:
            self.objects[target]['State']['Running'] = operation == 'start'
        elif operation == 'rm':
            if self.fail_rm:
                raise s.Refusal('command_ambiguous')
            del self.objects[target]
        else:
            raise AssertionError(operation)
        return 0, b'', b''


class Lifecycle(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = b'reviewed fixture source'
        self.clock = SimpleNamespace(now=s.START_BY - 1200)
        self.locks = {}
        @contextmanager
        def fake_lock(name, wait=3):
            guard = self.locks.setdefault(name, threading.RLock())
            with guard:
                yield
        clock = SimpleNamespace(time=lambda: self.clock.now, monotonic=lambda: self.clock.now,
                                sleep=lambda n: setattr(self.clock, 'now', self.clock.now+n))
        self.fake = FakeDocker(self)
        self.patches = [mock.patch.object(s, 'ROOT', self.root), mock.patch.object(s, 'lock', fake_lock),
                        mock.patch.object(s, 'time', clock), mock.patch.object(s, 'sync_directory'),
                        mock.patch.object(s, 'command', self.fake.command),
                        mock.patch.object(s, 'port_closed', lambda: not any(x['State']['Running'] for x in self.fake.objects.values())),
                        mock.patch.object(s.subprocess, 'Popen', side_effect=AssertionError('unexpected process'))]
        for p in self.patches:
            p.start(); self.addCleanup(p.stop)
        self.approval = {'schema': 'sentilab-slab047-review/1', 'grant_source': s.POLICY['grant_source'],
                         'controller_sha256': s.digest(self.source), 'policy_sha256': s.POLICY_SHA,
                         'decision': '+1', 'reviewer': 'independent-fixture-reviewer', 'review_record': 'fixture-approval'}
        self.save_approval()

    def save_approval(self):
        (self.root / 'APPROVED.json').write_bytes(s.encode(self.approval))

    def reserve(self):
        with mock.patch.object(s.subprocess, 'Popen', return_value=SimpleNamespace()) as spawn:
            result = s.start(self.source)
        self.assertEqual(result['phase'], 'start_reserved')
        args, kwargs = spawn.call_args
        self.assertTrue(kwargs['start_new_session'])
        self.assertTrue(kwargs['close_fds'])
        self.assertEqual(kwargs['stdin'], subprocess.DEVNULL)
        self.assertIn(repr(self.source), args[0][5])
        return s.reservation()

    def rows(self):
        return [{'row_id': str(i), 'system': 'system', 'instruction': 'fixture', 'output': '{"ok":true}'} for i in range(20)]

    def run_worker(self, r, request=None):
        def fake_request(path, body, allowance):
            self.assertGreater(allowance, 0)
            self.clock.now += 0.5
            return 200, s.encode({'choices': [{'message': {'content': '{"ok":true}'}}]})
        with mock.patch.object(s, 'verify_inputs', return_value=self.rows()), mock.patch.object(s, 'request', side_effect=request or fake_request):
            s.worker(r['token'], self.source)

    def test_no_review_no_reservation_or_process(self):
        (self.root / 'APPROVED.json').unlink()
        with self.assertRaises(FileNotFoundError): s.start(self.source)
        self.assertFalse((self.root / 'reservation.json').exists())

    def test_wrong_grant_source_policy_and_author_refused(self):
        for key, value in [('grant_source', 'other'), ('controller_sha256', '0'*64), ('policy_sha256', '0'*64),
                           ('reviewer', 'requirements_audit'), ('decision', 'pending'), ('review_record', '')]:
            previous = self.approval[key]; self.approval[key] = value; self.save_approval()
            with self.assertRaisesRegex(s.Refusal, 'exact_independent_review_required'): s.start(self.source)
            self.approval[key] = previous
            self.assertFalse((self.root / 'reservation.json').exists())

    def test_expired_and_stop_admission_refuse_before_reservation(self):
        self.clock.now = s.START_BY
        with self.assertRaisesRegex(s.Refusal, 'start_deadline_expired'): s.start(self.source)
        self.clock.now -= 1
        (self.root / 'STOP').touch()
        with self.assertRaisesRegex(s.Refusal, 'stop_requested'): s.start(self.source)
        self.assertFalse((self.root / 'reservation.json').exists())

    def test_lock_wait_revalidates_expiry(self):
        @contextmanager
        def expiry_lock(*args, **kwargs):
            self.clock.now = s.START_BY
            yield
        with mock.patch.object(s, 'lock', expiry_lock), self.assertRaisesRegex(s.Refusal, 'admission_expired_or_stopped'):
            s.start(self.source)
        self.assertFalse((self.root / 'reservation.json').exists())

    def test_frozen_admission_bytes_survive_later_policy_file_edits(self):
        r = self.reserve()
        original = r['approval_sha256']
        (self.root / 'APPROVED.json').write_text('{}')
        self.run_worker(r)
        self.assertEqual(s.reservation()['approval_sha256'], original)
        self.assertEqual(s.reservation()['approval_bytes'], s.encode(self.approval).decode())

    def test_approval_revoked_during_lock_wait_refuses(self):
        @contextmanager
        def revoked_lock(name, **kwargs):
            self.approval['decision'] = 'revoked'; self.save_approval()
            yield
        with mock.patch.object(s, 'lock', revoked_lock), self.assertRaisesRegex(s.Refusal, 'exact_independent_review_required'):
            s.start(self.source)
        self.assertFalse((self.root/'reservation.json').exists())

    def test_missing_state_after_durable_reservation_never_implies_zero_charge(self):
        self.reserve(); (self.root/'state.json').unlink()
        self.assertEqual(s.state()['charged_seconds'], 900)
        self.assertFalse(s.state()['cleanup_verified'])

    def test_spawn_failure_consumes_only_attempt_and_conservative_charge(self):
        with self.assertRaisesRegex(s.Refusal, 'worker_spawn_unresolved'): s.start(self.source)
        self.assertEqual(s.state()['charged_seconds'], 900)
        with self.assertRaisesRegex(s.Refusal, 'attempt_already_consumed'): s.start(self.source)

    def test_two_racing_starts_have_one_durable_reservation(self):
        outcomes = []
        def run():
            try: outcomes.append(s.start(self.source)['phase'])
            except s.Refusal as exc: outcomes.append(str(exc))
        with mock.patch.object(s.subprocess, 'Popen', return_value=SimpleNamespace()) as spawn:
            threads = [threading.Thread(target=run) for _ in range(2)]
            for t in threads: t.start()
            for t in threads: t.join(2)
        self.assertCountEqual(outcomes, ['start_reserved', 'attempt_already_consumed'])
        self.assertEqual(spawn.call_count, 1)

    def test_success_has_twenty_exact_body_receipts_and_verified_new_teardown(self):
        r = self.reserve(); self.run_worker(r)
        current = s.state()
        self.assertEqual(current['phase'], 'completed')
        self.assertEqual(current['inference_requests_reserved'], 20)
        self.assertTrue(current['cleanup_verified'])
        self.assertTrue(current['container_removed'])
        self.assertLess(current['charged_seconds'], 900)
        self.assertFalse(current['final_deliverable_accepted'])
        self.assertEqual(len(list(self.root.glob('request-*.json'))), 20)
        for i in range(20):
            receipt = json.loads((self.root / f'inference-{i:02d}.json').read_text())
            self.assertEqual(receipt['response_sha256'], s.digest((self.root / f'response-{i:02d}.json').read_bytes()))
            self.assertEqual(receipt['request_sha256'], s.digest((self.root / f'request-{i:02d}.json').read_bytes()))

    def test_stop_before_worker_creates_no_container(self):
        r = self.reserve(); (self.root / 'STOP').touch(); self.run_worker(r)
        self.assertEqual(s.state()['phase'], 'failed_closed')
        self.assertNotIn('create', [x[3] for x in self.fake.calls])

    def test_stop_between_requests_does_not_retry_or_exceed_twenty(self):
        r = self.reserve(); calls = []
        def request(path, body, allowance):
            if body:
                calls.append(body)
                if len(calls) == 3: (self.root / 'STOP').touch()
            return 200, s.encode({'choices': [{'message': {'content': '{"ok":true}'}}]})
        self.run_worker(r, request)
        self.assertEqual(len(calls), 3)
        self.assertEqual(s.state()['inference_requests_reserved'], 3)
        self.assertTrue(s.state()['cleanup_verified'])

    def test_ambiguous_create_without_id_never_claims_cleanup(self):
        r = self.reserve(); self.fake.fail_create = True; self.run_worker(r)
        self.assertEqual(s.state()['phase'], 'cleanup_unresolved')
        self.assertGreaterEqual(s.state()['charged_seconds'], 900)
        self.assertFalse(s.state()['cleanup_verified'])

    def test_worker_cannot_restart_an_already_consumed_attempt(self):
        r = self.reserve(); self.run_worker(r)
        previous = len(self.fake.calls)
        with self.assertRaisesRegex(s.Refusal, 'worker_already_started'): self.run_worker(r)
        self.assertEqual(len(self.fake.calls), previous)

    def test_supplied_token_usage_and_warmup_are_scoped_measurements(self):
        r = self.reserve()
        def response(path, body, allowance):
            self.clock.now += 2
            return 200, s.encode({'choices': [{'message': {'content':'{"ok":true}'}}],
                                  'usage': {'prompt_tokens':10, 'completion_tokens':8, 'total_tokens':18}})
        self.run_worker(r, response)
        receipt = json.loads((self.root/'inference-00.json').read_text())
        self.assertEqual(receipt['reported_usage']['completion_tokens'], 8)
        self.assertEqual(receipt['client_observed_completion_tokens_per_second'], 4)
        self.assertGreater(s.state()['launch_to_ready_seconds'], 0)

    def test_ambiguous_removal_never_claims_completion(self):
        r = self.reserve(); self.fake.fail_rm = True; self.run_worker(r)
        self.assertEqual(s.state()['phase'], 'cleanup_unresolved')
        self.assertGreaterEqual(s.state()['charged_seconds'], 900)
        self.assertFalse(self.fake.objects[self.fake.cid]['State']['Running'])

    def test_wrong_token_image_or_full_id_refuses_destructive_calls(self):
        r = self.reserve()
        cid = s.docker(*s.container_argv(r)).decode()
        s.update(container_id=cid)
        for field, value in [('Image', 'other'), ('Id', 'b'*64), ('Name', '/other')]:
            before = self.fake.objects[cid][field]; self.fake.objects[cid][field] = value
            with self.assertRaisesRegex(s.Refusal, 'container_identity_mismatch'): s.cleanup(r)
            self.fake.objects[cid][field] = before
        self.fake.objects[cid]['Labels']['sentilab.attempt'] = 'other'
        with self.assertRaisesRegex(s.Refusal, 'container_identity_mismatch'): s.cleanup(r)
        self.assertFalse({'kill', 'stop', 'rm'} & {x[3] for x in self.fake.calls})

    def test_ambiguous_http_consumes_slot_and_never_retries(self):
        r = self.reserve(); count = []
        def request(path, body, allowance):
            if body:
                count.append(body); raise subprocess.TimeoutExpired('fixture', 15)
            return 200, b'{}'
        self.run_worker(r, request)
        self.assertEqual(len(count), 1)
        self.assertEqual(s.state()['inference_requests_reserved'], 1)
        self.assertEqual(s.state()['phase'], 'failed_closed')
        self.assertTrue((self.root / 'request-00.json').exists())

    def reservation_barrier(self, expire):
        r = self.reserve()
        original_update = s.update
        posts = []
        def update(**fields):
            original_update(**fields)
            if fields.get('inference_requests_reserved') == 1:
                if expire:
                    self.clock.now = r['deadline_monotonic'] - s.CLEANUP_RESERVE
                else:
                    (self.root / 'STOP').touch()
        def request(path, body, allowance):
            if body: posts.append(body)
            return 200, b'{}'
        with mock.patch.object(s, 'update', side_effect=update):
            self.run_worker(r, request)
        self.assertEqual(posts, [])
        self.assertEqual(s.state()['inference_requests_reserved'], 1)
        self.assertTrue((self.root / 'request-00.json').exists())
        self.assertFalse((self.root / 'response-00.json').exists())
        self.assertEqual(s.state()['phase'], 'failed_closed')
        self.assertTrue(s.state()['cleanup_verified'])

    def test_stop_during_slot_reservation_prevents_post(self):
        self.reservation_barrier(False)

    def test_deadline_during_slot_reservation_prevents_post(self):
        self.reservation_barrier(True)

    def test_malformed_200_retains_status_hashes_and_failure_receipt(self):
        r = self.reserve(); posts = []
        def request(path, body, allowance):
            if body:
                posts.append(body)
                return 200, b'{malformed'
            return 200, b'{}'
        self.run_worker(r, request)
        self.assertEqual(len(posts), 1)
        self.assertEqual(s.state()['inference_requests_reserved'], 1)
        self.assertEqual(s.state()['error'], 'inference_invalid_json')
        self.assertEqual(s.state()['phase'], 'failed_closed')
        receipt = json.loads((self.root / 'inference-00.json').read_bytes())
        self.assertEqual(receipt['http_status'], 200)
        self.assertEqual(receipt['request_sha256'], s.digest(posts[0]))
        self.assertEqual(receipt['response_sha256'], s.digest(b'{malformed'))
        self.assertEqual(receipt['response_parse_error'], 'JSONDecodeError')
        self.assertFalse(receipt['exact_json_match'])
        self.assertEqual((self.root / 'response-00.json').read_bytes(), b'{malformed')
        self.assertTrue(s.state()['cleanup_verified'])

    def test_valid_outer_json_with_missing_or_deep_content_retains_receipts(self):
        r = self.reserve()
        responses = [b'{"choices":[]}', s.encode({'choices': [{'message': {'content': '[' * 2000 + '0' + ']' * 2000}}]})]
        for index, raw in enumerate(responses):
            with mock.patch.object(s, 'request', return_value=(200, raw)):
                s.inference(r, self.rows()[index], index)
            receipt = json.loads((self.root / f'inference-{index:02d}.json').read_bytes())
            self.assertEqual(receipt['http_status'], 200)
            self.assertFalse(receipt['exact_json_match'])
            self.assertEqual(receipt['response_sha256'], s.digest(raw))
            self.assertEqual(s.state()['inference_requests_reserved'], index + 1)

    def test_readiness_and_cleanup_are_inside_original_time_budget(self):
        r = self.reserve()
        def unavailable(path, body, allowance):
            self.clock.now += 100
            return 503, b''
        self.run_worker(r, unavailable)
        self.assertEqual(s.state()['phase'], 'failed_closed')
        self.assertLess(s.state()['charged_seconds'], 900)
        self.assertEqual(s.state()['inference_requests_reserved'], 0)

    def test_container_policy_has_fixed_readonly_mounts_and_old_root_not_writable(self):
        r = self.reserve(); args = s.container_argv(r)
        self.assertIn('--pull=never', args); self.assertIn('--read-only', args)
        self.assertIn('127.0.0.1:18047:8000', args)
        mounts = [args[i+1] for i,x in enumerate(args) if x == '--mount']
        self.assertEqual(len(mounts), 3)
        self.assertTrue(all(x.endswith(',readonly') for x in mounts))
        self.assertNotIn('--privileged', args)
        self.assertIn(str(r['deadline_unix']-35), args[-1])

    def test_expired_inner_timeout_cannot_launch_vllm(self):
        r = self.reserve(); wrapper = s.container_argv(r)[-1]
        with mock.patch('time.time', return_value=r['deadline_unix']), mock.patch('time.monotonic', return_value=r['deadline_monotonic']), mock.patch('os._exit', side_effect=SystemExit(3)), mock.patch('os.execvp') as execute:
            with self.assertRaises(SystemExit): exec(wrapper)
        execute.assert_not_called()

    def test_http_has_no_process_when_allowance_is_expired_or_nonfinite(self):
        for allowance in [0, -1, float('nan'), float('inf'), True]:
            with self.assertRaisesRegex(s.Refusal, 'http_deadline_expired'):
                s.request('/health', b'', allowance)


class HttpTransport(unittest.TestCase):
    def test_slow_local_response_exceeds_old_two_second_timeout(self):
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                self.rfile.read(int(self.headers['Content-Length']))
                time.sleep(2.6)
                self.send_response(200); self.end_headers()
                self.wfile.write(b'{"ok":true}')
            def log_message(self, *args): pass
        with http.server.HTTPServer(('127.0.0.1', 18047), Handler) as server:
            thread = threading.Thread(target=server.handle_request, daemon=True)
            thread.start()
            started = time.monotonic()
            try:
                self.assertEqual(s.request('/v1/chat/completions', b'{}', 5), (200, b'{"ok":true}'))
                self.assertGreaterEqual(time.monotonic() - started, 2.6)
            finally:
                thread.join(timeout=6)
            self.assertFalse(thread.is_alive())

    def test_socket_and_outer_timeouts_share_bounded_allowance(self):
        for supplied, expected in [(900, 60), (32.8, 32.8), (3, 3)]:
            with mock.patch.object(s.subprocess, 'Popen') as spawn:
                process = spawn.return_value
                process.communicate.return_value = (b'200\n{}', None)
                process.returncode = 0
                s.request('/v1/chat/completions', b'{}', supplied)
                self.assertEqual(float(spawn.call_args.args[0][-1]), expected)
                self.assertEqual(process.communicate.call_args.kwargs['timeout'], expected)


class InputPins(unittest.TestCase):
    def test_only_connection_refused_proves_port_closed(self):
        for code, closed in [(0,False), (s.errno.ECONNREFUSED,True), (s.errno.ETIMEDOUT,False), (s.errno.EACCES,False)]:
            with mock.patch.object(s.socket, 'socket') as socket:
                socket.return_value.__enter__.return_value.connect_ex.return_value = code
                self.assertEqual(ORIGINAL_PORT_CLOSED(), closed)

    def test_pins_match_committed_model_and_fixture_sources(self):
        root = Path(__file__).resolve().parents[2] / 'docs/sentilab/evidence/SLAB-018'
        model = json.loads((root/'MODEL-ADMISSION-MANIFEST.json').read_text())
        pins = {name:(size, digest) for name,size,digest in s.INPUTS}
        for entry in model['files']:
            self.assertEqual(pins['model/'+entry['path']], (entry['bytes'], entry['expectedSha256']))
        raw = (root/'fixtures/eval.jsonl').read_bytes()
        self.assertEqual(pins['fixtures/eval.jsonl'], (len(raw), hashlib.sha256(raw).hexdigest()))
        self.assertEqual(len(raw.splitlines()), 20)


if __name__ == '__main__': unittest.main()
