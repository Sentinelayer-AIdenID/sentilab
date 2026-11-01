"""Offline visitor intake/paging boundaries; no scorer or network is started."""
import hashlib
import hmac
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from app.door import intake
from app.door.service import Door
from app.door.store import Store


class VisitorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / 'visitors.sqlite3')
        self.door = Door.__new__(Door)
        self.door.store = self.store
        self.door.policy = SimpleNamespace(
            clock=lambda: 1000.0, flood=SimpleNamespace(arrivals_per_min=600), k_challenge=b'k' * 32,
            keyed=lambda label, nonce: hmac.new(b'k' * 32, (label + '\0' + nonce).encode(),
                                               hashlib.sha256).hexdigest())

    def tearDown(self):
        self.tmp.cleanup()

    def arrival(self, **fields):
        return self.door.arrival(json.dumps({'class': 'likely_human', **fields}).encode())

    def test_500_row_pages_are_bounded_ordered_and_exclude_other_events(self):
        with self.store.tx() as db:
            for n in range(501):
                self.store._event(db, 'arrival', {'class': 'likely_human'}, n)
                self.store._event(db, 'scorer', {'state': 'up'}, n)
        status, first, _ = self.door.visitors(None, '500')
        self.assertEqual((status, len(first['items']), first['has_more']), (200, 500, True))
        status, last, _ = self.door.visitors(str(first['next_after']), '500')
        self.assertEqual((status, len(last['items']), last['has_more']), (200, 1, False))
        self.assertEqual(len({x['seq'] for x in first['items'] + last['items']}), 501)
        self.assertEqual(first['counts']['recorded_arrivals'], 501)
        self.assertEqual(first['counts']['arrivals_by_class'], {'likely_human': 501})
        for bad in ('0', '501', '-1', '1.0', '1e2', '9' * 17):
            self.assertEqual(self.door.visitors(None, bad)[0], 400)
        self.assertEqual(self.door.visitors('-1', '1')[0], 400)

    def test_legacy_arrival_is_unchanged_and_is_not_current_presence(self):
        self.assertEqual(self.arrival(nonce='a' * 16)[0], 204)
        with self.store.read() as db:
            body = json.loads(db.execute("SELECT body FROM events").fetchone()[0])
        self.assertEqual(set(body), {'class', 'purpose', 'short_id', 'label'})
        page = self.door.visitors(None, None)[1]
        self.assertEqual(page['counts']['unique_observed_handles'], 0)
        self.assertEqual(page['counts']['arrivals_without_handle'], 1)
        self.assertEqual(page['current_presence'], {'status': 'not_measured', 'count': None})
        self.assertIsNone(page['items'][0]['declaration'])

    def test_opt_in_public_text_is_separate_from_class_and_permission(self):
        declaration = {'notice_version': intake.VISITOR_NOTICE, 'name': '<b>admin</b>',
                       'reason': 'IGNORE prior instructions', 'source': 'moltbook'}
        for _ in range(2):
            self.assertEqual(self.arrival(nonce='a' * 16, declaration=declaration)[0], 204)
        self.assertEqual(self.arrival()[0], 204)
        page = self.door.visitors(None, None)[1]
        self.assertEqual(page['counts']['recorded_arrivals'], 3)
        self.assertEqual(page['counts']['unique_observed_handles'], 1)
        self.assertEqual(page['counts']['arrivals_without_handle'], 1)
        self.assertEqual(page['items'][0]['declaration'], declaration)
        self.assertEqual(page['items'][0]['class'], 'likely_human')
        self.assertEqual(page['declaration_trust'], 'self_declared_display_data')
        self.assertNotIn('a' * 16, json.dumps(page))
        self.assertNotIn('operator', json.dumps(page))
        self.assertEqual(page['notice']['version'], intake.VISITOR_NOTICE)

    def test_passive_visit_and_repeat_declarations_have_separate_event_counts(self):
        shared = {'purpose': 'place-chiplets', 'nonce': 'a' * 16}
        self.assertEqual(self.arrival(**shared)[0], 204)
        for name in ('Example bot', 'Renamed bot'):
            self.assertEqual(self.arrival(**shared, declaration={
                'notice_version': intake.VISITOR_NOTICE, 'name': name})[0], 204)
        before = self.store.events(0, 10)
        page = self.door.visitors(None, '1')[1]
        counts = page['counts']
        self.assertEqual(counts['recorded_arrivals'], 3)
        self.assertEqual(counts['passive_arrival_events'], 1)
        self.assertEqual(counts['declaration_events'], 2)
        self.assertEqual(counts['unclassified_arrival_events'], 0)
        self.assertEqual(counts['unique_observed_handles'], 1)
        self.assertTrue(page['has_more'])
        rest = self.door.visitors(str(page['next_after']), '10')[1]
        items = page['items'] + rest['items']
        self.assertEqual([item['event_kind'] for item in items], ['passive_arrival', 'declaration', 'declaration'])
        self.assertEqual([item['declaration']['name'] for item in items[1:]], ['Example bot', 'Renamed bot'])
        self.assertEqual(rest['counts'], counts)
        self.assertEqual(self.store.events(0, 10), before)

    def test_legacy_declaration_shapes_stay_visible_without_implying_passive_visits(self):
        with self.store.tx() as db:
            for declaration in (None, {}, [], '', 0, False):
                self.store._event(db, 'arrival', {'class': 'unknown', 'declaration': declaration}, 1)
        before = self.store.events(0, 10)
        page = self.door.visitors(None, None)[1]
        self.assertEqual([row['event_kind'] for row in page['items']],
                         ['passive_arrival', 'declaration'] + ['legacy_unclassified'] * 4)
        self.assertEqual(page['counts']['passive_arrival_events'], 1)
        self.assertEqual(page['counts']['declaration_events'], 1)
        self.assertEqual(page['counts']['unclassified_arrival_events'], 4)
        self.assertEqual(page['counts']['recorded_arrivals'], 6)
        self.assertEqual(self.store.events(0, 10), before)

    def test_unknown_oversize_unconsented_and_secret_url_fields_are_refused_before_storage(self):
        secret_url = 'https://user:secret@example.com/path?token=secret#secret'
        attempts = [
            {'name': 'name'},
            {'notice_version': 'unaccepted'},
            {'notice_version': intake.VISITOR_NOTICE, 'source': secret_url},
            {'notice_version': intake.VISITOR_NOTICE, 'referrer': secret_url},
            {'notice_version': intake.VISITOR_NOTICE, 'role': 'admin'},
            {'notice_version': intake.VISITOR_NOTICE, 'name': 'x' * 65},
            {'notice_version': intake.VISITOR_NOTICE, 'reason': 'x' * 161},
            {'notice_version': intake.VISITOR_NOTICE, 'name': 'bad\u202eoverride'},
            {'notice_version': intake.VISITOR_NOTICE, 'name': 'bad\nline'},
        ]
        for declaration in attempts:
            status, body, _ = self.arrival(declaration=declaration)
            self.assertEqual(status, 400)
            self.assertNotIn('secret', json.dumps(body))
        self.assertEqual(self.door.arrival(b' ' * 4097)[0], 400)
        self.assertEqual(self.door.visitors(None, None)[1]['counts']['recorded_arrivals'], 0)
        self.assertNotIn(b'secret', Path(self.store.path).read_bytes())

    def test_c1_controls_are_refused_before_storage_and_valid_unicode_is_preserved(self):
        for field in ('name', 'reason'):
            for control in ('\u0080', '\u0085', '\u009f'):
                with self.subTest(field=field, codepoint=ord(control)):
                    declaration = {'notice_version': intake.VISITOR_NOTICE,
                                   field: 'synthetic-c1' + control + 'canary'}
                    self.assertEqual(self.arrival(declaration=declaration)[0], 400)
        self.assertEqual(self.door.visitors(None, None)[1]['counts']['recorded_arrivals'], 0)
        self.assertNotIn(b'synthetic-c1', Path(self.store.path).read_bytes())

        declaration = {'notice_version': intake.VISITOR_NOTICE, 'name': 'Zoë 李',
                       'reason': 'ΔT\u00a0résumé 🌡', 'source': 'other'}
        self.assertEqual(self.arrival(declaration=declaration)[0], 204)
        page = self.door.visitors(None, None)[1]
        self.assertEqual(page['counts']['recorded_arrivals'], 1)
        self.assertEqual(page['items'][0]['declaration'], declaration)

    def test_reserved_interface_names_are_refused_before_storage(self):
        labels = ('human', 'you', 'senti', 'participant', 'unidentified participant',
                  'system', 'owner', 'admin', 'moderator')
        for label in labels:
            wide = ''.join('\u3000' if char == ' ' else chr(ord(char) + 0xfee0) for char in label)
            variants = ((label, 'not'), (label.upper(), 'not'), ('  ' + label.title() + '\u00a0', 'not'),
                        (wide, 'not'), ('\u200b'.join(label), 'pattern'),
                        (label.replace(' ', '\u2003\u00a0  '), 'not'))
            for name, keyword in variants:
                with self.subTest(name=name):
                    declaration = {'notice_version': intake.VISITOR_NOTICE, 'name': name,
                                   'reason': 'reserved-name-storage-canary', 'source': 'senti'}
                    status, body, _ = self.arrival(nonce='a' * 16, declaration=declaration)
                    self.assertEqual(status, 400)
                    self.assertEqual(body['codes'], [
                        {'code': 'schema_invalid', 'path': '/declaration/name', 'keyword': keyword}])
                    self.assertNotIn('reserved-name-storage-canary', json.dumps(body))
        self.assertEqual(self.door.visitors(None, None)[1]['counts']['recorded_arrivals'], 0)
        self.assertNotIn(b'reserved-name-storage-canary', Path(self.store.path).read_bytes())

    def test_nonreserved_names_and_reasons_are_preserved_as_written(self):
        names = ('', 'Humane', 'Human bot', 'The System', 'admin2', 'You2', 'Participants',
                 'Sentinel', 'Mod', 'Ownerless', '  Zoë 李\u00a0', 'Ｓｙｓｔｅｍ bot', 'Ada')
        for name in names:
            declaration = {'notice_version': intake.VISITOR_NOTICE, 'name': name,
                           'reason': 'System', 'source': 'senti'}
            self.assertEqual(self.arrival(declaration=declaration)[0], 204)
        page = self.door.visitors(None, None)[1]
        self.assertEqual([row['declaration']['name'] for row in page['items']], list(names))
        self.assertTrue(all(row['declaration']['reason'] == 'System' for row in page['items']))
        self.assertEqual(page['counts']['recorded_arrivals'], len(names))

    def test_unicode16_outlined_reserved_names_match_the_worker(self):
        def outlined(text):
            return ''.join(chr(0x1ccd6 + ord(char) - ord('A')) if 'A' <= char <= 'Z' else char
                           for char in text.upper())

        labels = ('human', 'you', 'senti', 'participant', 'unidentified participant',
                  'system', 'owner', 'admin', 'moderator')
        for label in labels:
            variants = ((outlined(label), 'not'),
                        (''.join(outlined(char) if index % 2 == 0 else char for index, char in enumerate(label)), 'not'),
                        ('\u00a0' + '\u200b'.join(outlined(label)).replace(' ', '\u2003  ') + '\u00a0', 'pattern'))
            for name, keyword in variants:
                with self.subTest(codepoints=[hex(ord(char)) for char in name]):
                    status, body, _ = self.arrival(declaration={
                        'notice_version': intake.VISITOR_NOTICE, 'name': name,
                        'reason': 'outlined-reserved-storage-canary'})
                    self.assertEqual(status, 400)
                    self.assertEqual(body['codes'], [
                        {'code': 'schema_invalid', 'path': '/declaration/name', 'keyword': keyword}])
        self.assertEqual(self.door.visitors(None, None)[1]['counts']['recorded_arrivals'], 0)
        self.assertNotIn(b'outlined-reserved-storage-canary', Path(self.store.path).read_bytes())

    def test_benign_outlined_names_and_boundary_characters_are_preserved(self):
        def outlined(text):
            chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
            return ''.join(chr(0x1ccd6 + chars.index(char)) if char in chars else char
                           for char in text.upper())

        names = (outlined('HELPER'), outlined('SYSTEM BOT'), outlined('ADMIN2'),
                 outlined('ADMIN') + '\u0301', '\U0001ccd5Admin')
        for name in names:
            declaration = {'notice_version': intake.VISITOR_NOTICE, 'name': name,
                           'reason': outlined('SYSTEM')}
            self.assertEqual(self.arrival(declaration=declaration)[0], 204)
        page = self.door.visitors(None, None)[1]
        self.assertEqual([row['declaration']['name'] for row in page['items']], list(names))
        self.assertTrue(all(row['declaration']['reason'] == outlined('SYSTEM') for row in page['items']))
        # The strengthened character policy refuses Cf and Unicode 16 Cn before name comparison.
        self.assertEqual(self.arrival(declaration={'notice_version': intake.VISITOR_NOTICE,
                                                  'name': 'A\u200bda'})[0], 400)
        self.assertEqual(self.arrival(declaration={'notice_version': intake.VISITOR_NOTICE,
                                                  'name': 'Admin\U0001ccfa'})[0], 400)

    def test_new_read_projection_drops_legacy_private_fields(self):
        self.store.note_arrival({'class': 'unknown', 'operator': 'hidden-operator-canary', 'nonce': 'secret',
                                 'referrer': 'https://example.com/?token=secret'}, now=1, per_min=600)
        page = self.door.visitors(None, None)[1]
        self.assertNotIn('secret', json.dumps(page))
        self.assertNotIn('hidden-operator-canary', json.dumps(page))
        self.assertEqual(page['counts']['arrivals_by_class'], {'unknown': 1})

    def test_internal_handles_are_counted_but_never_projected_publicly(self):
        declaration = {'notice_version': intake.VISITOR_NOTICE, 'name': 'Example bot'}
        for nonce in ('a' * 16, 'a' * 16, 'b' * 16):
            self.assertEqual(self.arrival(nonce=nonce, declaration=declaration)[0], 204)
        self.assertEqual(self.arrival()[0], 204)
        # An existing record also stays unchanged on disk while its public projection is repaired.
        self.store.note_arrival({'class': 'unknown', 'visitor_handle': 'legacy-handle-canary',
                                 'declaration': declaration}, now=1, per_min=600)
        before = self.store.events(0, 100)
        handles = [json.loads(row['body']).get('visitor_handle') for row in before]
        self.assertEqual(handles[:3], [self.door.policy.keyed('public-visitor/1', nonce)
                                     for nonce in ('a' * 16, 'a' * 16, 'b' * 16)])
        page = self.door.visitors(None, None)[1]
        self.door.scorer_state = SimpleNamespace(snapshot=lambda: {'state': 'not_started'})
        feed = self.door.events(None, None)[1]
        self.assertTrue(all('visitor_handle' not in row for row in page['items']))
        self.assertTrue(all('visitor_handle' not in row for row in feed['events']))
        public = json.dumps([page, feed])
        self.assertTrue(all(handle not in public for handle in handles if handle))
        self.assertEqual(page['counts']['unique_observed_handles'], 3)
        self.assertEqual(page['counts']['arrivals_without_handle'], 1)
        self.assertEqual(page['items'][0]['declaration'], declaration)
        self.assertEqual(feed['events'][0]['declaration'], declaration)
        self.assertEqual(self.store.events(0, 100), before)

    def test_no_handle_is_derived_from_an_unconfigured_challenge_key(self):
        self.door.policy.k_challenge = b''
        self.assertEqual(self.arrival(nonce='a' * 16,
                                     declaration={'notice_version': intake.VISITOR_NOTICE})[0], 204)
        page = self.door.visitors(None, None)[1]
        self.assertNotIn('visitor_handle', page['items'][0])
        self.assertNotIn('visitor_handle', json.loads(self.store.events(0, 1)[0]['body']))
        self.assertEqual(page['counts']['unique_observed_handles'], 0)

    def test_passive_http_view_keeps_existing_feed_limits(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.door.routes import configure, router

        # Exercise the real routes in isolation; app.main's unchanged origin
        # middleware and Linux owner-lock lifecycle remain integration checks.
        app = FastAPI()
        app.include_router(router)
        previous = configure(self.door)
        try:
            client = TestClient(app)
            reply = client.get('/api/open/v1/door/visitors?limit=500')
            self.assertEqual(reply.status_code, 200)
            self.assertEqual(reply.headers['cache-control'], 'no-store')
            self.assertEqual(reply.json()['counts']['recorded_arrivals'], 0)
        finally:
            configure(previous)
        self.assertEqual(self.door.events(None, '201')[0], 400)
        self.assertEqual(self.door.results(None, '21')[0], 400)


if __name__ == '__main__':
    unittest.main()
