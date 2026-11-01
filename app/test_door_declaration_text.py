"""Focused declaration character-policy controls; no scorer or live server is started."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from app.door import intake
from app.door.service import Door
from app.door.store import Store


class DeclarationTextTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / 'declarations.sqlite3')
        self.door = Door.__new__(Door)
        self.door.store = self.store
        self.door.policy = SimpleNamespace(clock=lambda: 1000.0,
                                          flood=SimpleNamespace(arrivals_per_min=600), k_challenge=b'')

    def tearDown(self):
        self.tmp.cleanup()

    def arrival(self, **fields):
        declaration = {'notice_version': intake.VISITOR_NOTICE, **fields}
        raw = json.dumps({'class': 'unknown', 'declaration': declaration}).encode()
        return self.door.arrival(raw)

    def test_all_refused_categories_are_rejected_before_storage(self):
        # Cc, Cf, Co, Cs, Cn, Zl and Zp. JSON escapes exercise lone surrogates safely.
        refused = ('\u0085', '\U000e0069', '\ue000', '\ud800', '\u0378', '\u2028', '\u2029')
        for field in ('name', 'reason'):
            for char in refused:
                with self.subTest(field=field, codepoint=hex(ord(char))):
                    status, body, _ = self.arrival(**{field: 'character-canary' + char})
                    self.assertEqual(status, 400)
                    self.assertEqual(body['codes'], [{'code': 'schema_invalid',
                                                     'path': '/declaration/' + field, 'keyword': 'pattern'}])
                    self.assertNotIn('character-canary', json.dumps(body))
        self.assertEqual(self.door.visitors(None, None)[1]['counts']['recorded_arrivals'], 0)
        self.assertNotIn(b'character-canary', Path(self.store.path).read_bytes())

    def test_format_controls_and_private_plane_characters_are_refused(self):
        for char in ('\u200b', '\u200c', '\u200d', '\u200e', '\u200f', '\u061c', '\ufeff',
                     '\U000e0001', '\U000e007f', '\U000f0000', '\U00100000', '\udfff'):
            for field in ('name', 'reason'):
                with self.subTest(field=field, codepoint=hex(ord(char))):
                    self.assertEqual(self.arrival(**{field: 'prefix' + char + 'suffix'})[0], 400)
        self.assertEqual(self.door.visitors(None, None)[1]['counts']['recorded_arrivals'], 0)

    def test_invisible_fillers_are_refused_before_storage_in_both_fields(self):
        for char in ('\u3164', '\u115f', '\u1160', '\uffa0', '\u2800'):
            for field in ('name', 'reason'):
                for text in ('admin' + char, char + 'admin', 'ad' + char + 'min', char):
                    with self.subTest(field=field, codepoint=hex(ord(char)), text=text):
                        status, body, _ = self.arrival(**{field: text}, source='senti')
                        self.assertEqual(status, 400)
                        self.assertEqual(body['codes'], [{'code': 'schema_invalid',
                                                         'path': '/declaration/' + field, 'keyword': 'pattern'}])
        self.assertEqual(self.store.events(0, 100), [])
        self.assertEqual(self.door.visitors(None, None)[1]['counts']['recorded_arrivals'], 0)

    def test_eight_consecutive_marks_are_allowed_and_nine_are_refused(self):
        for mark in ('\u0301', '\u093e', '\u20dd'):  # Mn, Mc, Me
            for field in ('name', 'reason'):
                with self.subTest(field=field, mark=hex(ord(mark))):
                    self.assertEqual(self.arrival(**{field: 'base' + mark * 8})[0], 204)
                    self.assertEqual(self.arrival(**{field: 'base' + mark * 9})[0], 400)
                    self.assertEqual(self.arrival(**{field: mark * 64})[0], 400)
        mixed = '\u0301\u093e\u20dd' * 3
        self.assertEqual(self.arrival(name='base' + mixed)[0], 400)

    def test_mark_run_resets_at_a_nonmark_and_has_no_global_total_cap(self):
        name = ('a' + '\u0301' * 8) * 4
        reason = ('क' + '\u093e\u20dd\u0301') * 30
        self.assertEqual(self.arrival(name=name, reason=reason)[0], 204)
        declaration = self.door.visitors(None, None)[1]['items'][0]['declaration']
        self.assertEqual((declaration['name'], declaration['reason']), (name, reason))

    def test_normal_multilingual_and_unicode16_assigned_text_stays_original(self):
        outlined_helper = ''.join(chr(0x1ccd6 + ord(char) - ord('A')) for char in 'HELPER')
        names = ('  Zoë 李\u00a0', 'नमस्ते', 'مرحبا', 'ภาษาไทย', '🌡️', '한글', '한', '⠁⠃',
                 '\U000105c0', '\U00016d40', '\U0001fae9', outlined_helper)
        for name in names:
            self.assertEqual(self.arrival(name=name, reason='e\u0301 résumé')[0], 204)
        page = self.door.visitors(None, None)[1]
        self.assertEqual([row['declaration']['name'] for row in page['items']], list(names))
        self.assertTrue(all(row['declaration']['reason'] == 'e\u0301 résumé' for row in page['items']))

    def test_reserved_unicode16_names_remain_refused(self):
        for name in ('HUMAN', 'YOU', 'SENTI', 'PARTICIPANT', 'UNIDENTIFIED PARTICIPANT',
                     'SYSTEM', 'OWNER', 'ADMIN', 'MODERATOR'):
            outlined = ''.join(chr(0x1ccd6 + ord(char) - ord('A')) if char != ' ' else char for char in name)
            status, body, _ = self.arrival(name=outlined)
            self.assertEqual(status, 400)
            self.assertEqual(body['codes'], [{'code': 'schema_invalid', 'path': '/declaration/name', 'keyword': 'not'}])

    def test_existing_field_caps_and_schema_precedence_are_unchanged(self):
        self.assertEqual(self.arrival(name='x' * 64, reason='x' * 160)[0], 204)
        for field, value, keyword in (('name', 'x' * 65, 'maxLength'),
                                      ('reason', 'x' * 161, 'maxLength'), ('name', 123, 'type')):
            status, body, _ = self.arrival(**{field: value})
            self.assertEqual(status, 400)
            self.assertEqual(body['codes'], [{'code': 'schema_invalid', 'path': '/declaration/' + field,
                                             'keyword': keyword}])
        self.assertEqual(self.arrival(source='senti')[0], 204)


if __name__ == '__main__':
    unittest.main()
