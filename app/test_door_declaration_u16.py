"""The declaration surface, hardened after the second security review of #89 and #90 (forge, on #90 at f99df0d); no
scorer or live server is started.

2  every Unicode 16.0 Default_Ignorable_Code_Point is refused in a name or reason (263 of them are marks that passed
   the category rule, so "admin" plus one read as "admin"), and so is a field with nothing left once the reserved-name
   comparison's cleanup is done (only spaces)
3  the Worker's Unicode 16.0 tables (web/src/door/unicode16.js) and the API's verdict for every code point
   (web/test/fixtures/door-a4/declaration-text-u16.json) are exactly what web/test/make_declare_unicode.py generates
   from this API, and the fixture is the API's own answer, code point by code point
4  the notice text is pinned to its version by its SHA-256 (warden's P3); web/test/door-declaration-u16.test.mjs holds
   the Worker's copy to the same table
"""
import hashlib
import json
import tempfile
import types
import unittest
from pathlib import Path
from types import SimpleNamespace

from app.door import intake
from app.door.service import Door
from app.door.store import Store

REPO = Path(__file__).resolve().parents[1]
GENERATOR = REPO / "web" / "test" / "make_declare_unicode.py"
FIXTURE = REPO / "web" / "test" / "fixtures" / "door-a4" / "declaration-text-u16.json"
# Unicode 16.0 Default_Ignorable_Code_Point, as DerivedCoreProperties-16.0.0.txt lists it (forge's brief): 4,174.
PINNED_DEFAULT_IGNORABLE = ((0x00AD, 0x00AD), (0x034F, 0x034F), (0x061C, 0x061C), (0x115F, 0x1160), (0x17B4, 0x17B5),
                            (0x180B, 0x180F), (0x200B, 0x200F), (0x202A, 0x202E), (0x2060, 0x206F), (0x3164, 0x3164),
                            (0xFE00, 0xFE0F), (0xFEFF, 0xFEFF), (0xFFA0, 0xFFA0), (0xFFF0, 0xFFF8), (0x1BCA0, 0x1BCA3),
                            (0x1D173, 0x1D17A), (0xE0000, 0xE0FFF))
# The 263 that passed before: default-ignorable marks (Mn), which the category rule lets through.
DI_MARKS = tuple(chr(cp) for first, last in ((0x034F, 0x034F), (0x17B4, 0x17B5), (0x180B, 0x180D), (0x180F, 0x180F),
                                             (0xFE00, 0xFE0F), (0xE0100, 0xE01EF)) for cp in range(first, last + 1))
RESERVED = ("human", "you", "senti", "participant", "unidentified participant", "system", "owner", "admin", "moderator")
# Each notice version names exactly one text: its SHA-256 over the UTF-8 bytes. Changing the text means a new version
# and a new line here (and in web/test/door-declaration-u16.test.mjs, which pins the Worker's copy).
PINNED_NOTICES = {"sentilab-public-visitor/1": "89a0a0672697cebba94fe2918f7fa2a09cbf1181617ff8cf8acaa759b899047b",
                  "sentilab-public-visitor/2": "7c627fb07e928f5f474268a512459d1e70fda1cfcb06f6524c2eb47656241cf1"}


def codes_of(ranges):
    return [cp for first, last in ranges for cp in range(first, last + 1)]


def load_generator():
    """web/test/make_declare_unicode.py as a module, without writing its bytecode beside it: web/test is scanned for
    control bytes (web/test/control-bytes.test.mjs), and a .pyc is full of them."""
    module = types.ModuleType("make_declare_unicode")
    module.__file__ = str(GENERATOR)
    exec(compile(GENERATOR.read_bytes(), str(GENERATOR), "exec"), module.__dict__)
    return module


class DeclarationTextU16Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / 'declarations.sqlite3')
        self.door = Door.__new__(Door)
        self.door.store = self.store
        self.door.policy = SimpleNamespace(clock=lambda: 1000.0,
                                          flood=SimpleNamespace(arrivals_per_min=10**9), k_challenge=b'')

    def tearDown(self):
        self.tmp.cleanup()

    def arrival(self, **fields):
        declaration = {'notice_version': intake.VISITOR_NOTICE, **fields}
        return self.door.arrival(json.dumps({'class': 'unknown', 'declaration': declaration}).encode())

    def assert_nothing_stored(self, canary: bytes):
        self.assertEqual(self.door.visitors(None, None)[1]['counts']['recorded_arrivals'], 0)
        self.assertNotIn(canary, Path(self.store.path).read_bytes())

    # 2 ──────────────────────────────────────────────────────────────────────────────────────────────────────────
    def test_2_default_ignorables_are_unicode16s_4174_code_points(self):
        self.assertEqual(tuple(intake._DEFAULT_IGNORABLE), PINNED_DEFAULT_IGNORABLE)
        self.assertEqual(len(codes_of(PINNED_DEFAULT_IGNORABLE)), 4174)
        self.assertEqual(len(intake._DEFAULT_IGNORABLE_CHARS), 4174)
        self.assertEqual(len(DI_MARKS), 263)

    def test_2_each_default_ignorable_is_refused_in_both_fields_before_storage(self):
        passed = []
        for cp in codes_of(PINNED_DEFAULT_IGNORABLE):
            for field in ('name', 'reason'):
                status, body, _ = self.arrival(**{field: 'di-canary' + chr(cp)})
                if (status, body.get('codes') if body else None) != (400, [
                        {'code': 'schema_invalid', 'path': '/declaration/' + field, 'keyword': 'pattern'}]):
                    passed.append((field, hex(cp), status))
        self.assertEqual(passed[:5], [], f"{len(passed)} of 8,348 not refused")
        self.assert_nothing_stored(b'di-canary')

    def test_2_a_reserved_name_padded_with_a_default_ignorable_mark_is_refused(self):
        passed = []
        for name in RESERVED:
            middle = len(name) // 2
            for mark in DI_MARKS:
                for padded in (name + mark, name[:middle] + mark + name[middle:]):
                    status, body, _ = self.arrival(name=padded, reason='padded-canary')
                    if status != 400 or body['codes'][0]['keyword'] != 'pattern':
                        passed.append((name, hex(ord(mark)), status))
        self.assertEqual(passed[:5], [], f"{len(passed)} of {len(RESERVED) * len(DI_MARKS) * 2} not refused")
        self.assert_nothing_stored(b'padded-canary')
        # An emoji with its presentation selector (U+FE0F) is refused for the same reason; the bare emoji is fine.
        self.assertEqual(self.arrival(name='\u2764\ufe0f')[0], 400)
        self.assertEqual(self.arrival(name='\u2764', reason='\U0001f525 chip')[0], 204)

    def test_2_a_field_with_nothing_visible_is_refused_before_storage(self):
        blanks = (' ', '   ', '\xa0', '\u3000\u3000\u3000', '\u2003 \u205f', '\u1680', '\u202f\u2007')
        for field in ('name', 'reason'):
            for text in blanks:
                with self.subTest(field=field, text=[hex(ord(c)) for c in text]):
                    status, body, _ = self.arrival(**{field: text}, source='senti')
                    self.assertEqual(status, 400)
                    self.assertEqual(body['codes'], [{'code': 'schema_invalid', 'path': '/declaration/' + field,
                                                     'keyword': 'pattern'}])
        self.assertEqual(self.door.visitors(None, None)[1]['counts']['recorded_arrivals'], 0)
        # Text with spaces around it is kept exactly as written, and an empty field is no text at all (root's contract).
        for fields in ({'name': '  Zo\xeb  ', 'reason': ' ok '}, {'name': ''}, {'reason': ''}):
            self.assertEqual(self.arrival(**fields)[0], 204, fields)
        items = self.door.visitors(None, None)[1]['items']
        self.assertEqual([item['declaration'] for item in items][0],
                         {'notice_version': intake.VISITOR_NOTICE, 'name': '  Zo\xeb  ', 'reason': ' ok '})

    # 3 ──────────────────────────────────────────────────────────────────────────────────────────────────────────
    def test_3_the_workers_tables_and_the_verdict_fixture_are_the_generators_output(self):
        for path, data in load_generator().generate().items():
            with self.subTest(path.relative_to(REPO).as_posix()):
                self.assertTrue(path.exists(), "regenerate with python web/test/make_declare_unicode.py")
                self.assertEqual(path.read_bytes(), data, "regenerate with python web/test/make_declare_unicode.py")

    def test_3_the_fixture_is_the_apis_own_answer_for_every_code_point(self):
        """Independently of the generator: expand the fixture's ranges and ask _declaration_text_allowed itself."""
        fixture = json.loads(FIXTURE.read_bytes())
        self.assertEqual((fixture['unicode'], fixture['max_mark_run']), ('16.0.0', intake._MAX_COMBINING_RUN))
        refused, marks = bytearray(0x110000), bytearray(0x110000)
        for table, ranges in ((refused, fixture['refused']['ranges']), (marks, fixture['marks']['ranges'])):
            for first, last in ranges:
                table[first:last + 1] = b'\x01' * (last - first + 1)
        allowed, run = intake._declaration_text_allowed, intake._MAX_COMBINING_RUN
        wrong = []
        for cp in range(0x110000):
            api_refused = not allowed(chr(cp))
            api_mark = not api_refused and allowed(chr(cp) * run) and not allowed(chr(cp) * (run + 1))
            if (api_refused, api_mark) != (bool(refused[cp]), bool(marks[cp])):
                wrong.append(hex(cp))
        self.assertEqual(wrong[:10], [], f"{len(wrong)} code points differ")
        self.assertEqual((sum(refused), sum(marks)), (959554, 2238))
        self.assertEqual([tuple(pair) for pair in fixture['default_ignorable']['ranges']], list(PINNED_DEFAULT_IGNORABLE))
        # U+20C1 is unassigned in Unicode 16.0 (assigned in 17.0): refused here and in the fixture.
        self.assertTrue(refused[0x20C1])
        self.assertEqual(self.arrival(name='\u20c1')[0], 400)

    # 4 ──────────────────────────────────────────────────────────────────────────────────────────────────────────
    def test_4_the_notice_text_is_the_one_its_version_names(self):
        self.assertIn(intake.VISITOR_NOTICE, PINNED_NOTICES, "a new notice version needs its own line in PINNED_NOTICES")
        data = intake.VISITOR_DISCLOSURE.encode("utf-8")
        self.assertEqual(hashlib.sha256(data).hexdigest(), PINNED_NOTICES[intake.VISITOR_NOTICE],
                         "the notice text changed without a new version")
        if intake.VISITOR_NOTICE == "sentilab-public-visitor/1":
            self.assertEqual(len(data), 506)
        # The visitors page publishes exactly this pair.
        self.assertEqual(self.door.visitors(None, None)[1]['notice'],
                         {'version': intake.VISITOR_NOTICE, 'text': intake.VISITOR_DISCLOSURE})


if __name__ == '__main__':
    unittest.main()
