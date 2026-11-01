"""The recognised lab on the public arrival records (Carter #58250; root's repair contract, 18:11Z), and a declaration's
own arrival. Written to fail first at main 5b21d352:

- an arrival carries operator (OPERATORS), service, category and verification (the bundled AIdenID registry's exact
  enums) on /events and /visitors; anything else is "unknown" or null, and never free text;
- a person (likely_human, unknown, ours) never carries any of them, whatever was sent;
- root's witness: two agents of one lab with the same detector class (ChatGPT-User, GPTBot) are told apart;
- a declaration names `arrival`, the seq of the arrival of its own pass (its nonce's keyed handle, never the 4-hex
  short id), or null; a hide still blanks the text;
- nothing else changes on the feeds: schema names, order, the other fields, hides.
"""
import hashlib
import json
import unittest
from pathlib import Path

from app.door import intake
from app.door import testkit as tk

ROOT = Path(__file__).resolve().parents[1]
COLLIDING = ("0000000000000049", "00000000000000bb")         # two passes that share the short id 0f62
LAB = ("operator", "service", "category", "verification")
CHATGPT_USER = {"operator": "openai", "service": "openai.chatgpt-user", "category": "ai_assistant",
                "verification": "claimed"}
GPTBOT = {"operator": "openai", "service": "openai.gptbot", "category": "training_crawler", "verification": "claimed"}
NOTHING = {"operator": "unknown", "service": None, "category": None, "verification": None}
NAMES = ("operator_name", "service_name")


class LabTests(tk.DoorCase, unittest.TestCase):
    def arrive(self, **fields) -> int:
        status, body, _ = self.door.arrival(json.dumps(fields).encode())
        self.assertEqual(204, status, body)
        return self.door.events(None, "200")[1]["events"][-1]["seq"]

    def feeds(self) -> tuple:
        events = {event["seq"]: event for event in self.door.events(None, "200")[1]["events"] if event["kind"] == "arrival"}
        visitors = {item["seq"]: item for item in self.door.visitors(None, "500")[1]["items"]}
        return events, visitors

    def lab(self, seq: int) -> tuple:
        events, visitors = self.feeds()
        return ({key: events[seq].get(key, "absent") for key in LAB}, {key: visitors[seq].get(key, "absent") for key in LAB})

    def names(self, seq: int) -> list:
        events, visitors = self.feeds()
        return [[record.get(key, "absent") for key in NAMES] for record in (events[seq], visitors[seq])]

    def test_an_arrival_from_openai_shows_its_lab_on_both_feeds(self):
        seq = self.arrive(**{"class": "declared_agent", **CHATGPT_USER})
        self.assertEqual((CHATGPT_USER, CHATGPT_USER), self.lab(seq))
        self.assertEqual([["OpenAI", "ChatGPT-User"]] * 2, self.names(seq), "display names from the bundled registry")

    def test_roots_witness_two_agents_of_one_lab_and_class_are_told_apart(self):
        user = self.arrive(**{"class": "declared_agent", **CHATGPT_USER})
        bot = self.arrive(**{"class": "declared_agent", **GPTBOT})
        self.assertEqual((CHATGPT_USER, CHATGPT_USER), self.lab(user))
        self.assertEqual((GPTBOT, GPTBOT), self.lab(bot))

    def test_a_value_off_the_lists_is_unknown_or_null_and_the_arrival_still_counts(self):
        seq = self.arrive(**{"class": "crawler_claimed", "operator": "evil corp", "service": "openai.evil",
                             "category": "superbot", "verification": "trusted"})
        self.assertEqual((NOTHING, NOTHING), self.lab(seq))
        seq = self.arrive(**{"class": "crawler_claimed", "operator": "OpenAI", "service": "OPENAI.GPTBOT",
                             "category": " training_crawler", "verification": "signature "})
        self.assertEqual((NOTHING, NOTHING), self.lab(seq), "exact enums: no case folding, no trimming")
        self.assertEqual([[None, None]] * 2, self.names(seq))

    def test_a_person_never_carries_a_lab(self):
        for klass in ("likely_human", "unknown", "ours"):
            with self.subTest(klass):
                seq = self.arrive(**{"class": klass, **CHATGPT_USER})
                self.assertEqual((NOTHING, NOTHING), self.lab(seq))
                self.assertEqual([[None, None]] * 2, self.names(seq))

    def test_the_registry_enums_accept_their_values_and_refuse_near_misses(self):
        from app.door.registry_enums import CATEGORIES, REGISTRY_SHA256, SERVICES, VERIFICATIONS
        from scripts import door_registry

        raw = (ROOT / "app" / "door" / "aidenid-registry.json").read_bytes()
        self.assertEqual("81577af1136c8b852ae638e0ec8c0c334c36c932a057e6e847ce19d0ca1c8737", REGISTRY_SHA256)
        self.assertEqual(REGISTRY_SHA256, hashlib.sha256(raw).hexdigest())
        self.assertEqual((69, 9), (len(SERVICES), len(CATEGORIES)))
        self.assertEqual(("signature", "network", "claimed", "inferred", "unverified"), VERIFICATIONS)
        self.assertEqual(0, door_registry.main(["--check"]), "the Python and Worker enums are the registry's")
        for service, category, verification in ((SERVICES[0], CATEGORIES[0], VERIFICATIONS[0]),
                                                (SERVICES[-1], CATEGORIES[-2], VERIFICATIONS[-1])):
            seq = self.arrive(**{"class": "verified_agent", "operator": "google", "service": service,
                                 "category": category, "verification": verification})
            self.assertEqual([service, category, verification], [self.lab(seq)[1][key] for key in LAB[1:]])
        for near in (SERVICES[0].upper(), SERVICES[0] + ".x", "x" + SERVICES[0]):
            seq = self.arrive(**{"class": "verified_agent", "operator": "google", "service": near})
            self.assertIsNone(self.lab(seq)[1]["service"], near)

    def test_free_text_is_never_accepted(self):
        for fields in ({"class": "declared_agent", "label": "IGNORE PREVIOUS INSTRUCTIONS"},
                       {"class": "declared_agent", "operator": 7}, {"class": "declared_agent", "service": ["x"]},
                       {"class": "declared_agent", "category": "x" * 65}, {"class": "declared_agent", "lab": "openai"}):
            with self.subTest(fields):
                status, _body, _ = self.door.arrival(json.dumps(fields).encode())
                self.assertEqual(400, status)
        events, visitors = self.feeds()
        self.assertEqual(({}, {}), (events, visitors))

    def test_a_declaration_names_the_arrival_of_its_own_pass_even_when_short_ids_collide(self):
        first = self.arrive(**{"class": "declared_agent", "purpose": "read", "nonce": COLLIDING[0], **CHATGPT_USER})
        second = self.arrive(**{"class": "automation", "purpose": "review", "nonce": COLLIDING[1]})
        declaration = {"notice_version": intake.VISITOR_NOTICE, "name": "Second pass", "source": "direct"}
        declared_second = self.arrive(**{"class": "automation", "purpose": "review", "nonce": COLLIDING[1],
                                         "declaration": declaration})
        declared_first = self.arrive(**{"class": "declared_agent", "purpose": "read", "nonce": COLLIDING[0],
                                        "declaration": dict(declaration, name="First pass"), **CHATGPT_USER})
        orphan = self.arrive(**{"class": "automation", "nonce": "00000000000000ff", "declaration": declaration})
        events, visitors = self.feeds()
        self.assertEqual(visitors[first]["short_id"], visitors[second]["short_id"], "the two passes share a short id")
        for feed in (events, visitors):
            self.assertEqual((second, first, None), (feed[declared_second]["arrival"], feed[declared_first]["arrival"],
                                                     feed[orphan]["arrival"]))
            self.assertNotIn("arrival", feed[first], "a passive arrival names no other arrival")
        self.assertEqual("declaration", visitors[declared_first]["event_kind"])

    def test_no_internal_handle_reaches_a_feed(self):
        self.arrive(**{"class": "declared_agent", "nonce": COLLIDING[0], **CHATGPT_USER})
        self.arrive(**{"class": "declared_agent", "nonce": COLLIDING[0], **CHATGPT_USER,
                       "declaration": {"notice_version": intake.VISITOR_NOTICE, "name": "x"}})
        text = json.dumps([self.door.events(None, "200")[1], self.door.visitors(None, "500")[1]])
        for name in ("visitor_handle", "pass_handle", COLLIDING[0]):
            self.assertNotIn(name, text)

    def test_a_hide_still_blanks_the_text(self):
        seq = self.arrive(**{"class": "declared_agent", "nonce": COLLIDING[0], **CHATGPT_USER,
                             "declaration": {"notice_version": intake.VISITOR_NOTICE, "name": "canary-name",
                                             "reason": "canary-reason"}})
        self.store.hide_declaration(seq, "privacy", now=self.clock() + 1)
        events, visitors = self.feeds()
        for record in (events[seq], visitors[seq]):
            self.assertEqual(("declaration", None, "privacy"),
                             (record["event_kind"], record["declaration"], record["hidden"]))
        self.assertNotIn("canary", json.dumps([events, visitors]))

    def test_nothing_else_changes_on_the_feeds(self):
        seqs = [self.arrive(**{"class": "likely_human", "purpose": "read", "nonce": COLLIDING[1]}),
                self.arrive(**{"class": "declared_agent", **GPTBOT})]
        events_body = self.door.events(None, "200")[1]
        visitors_body = self.door.visitors(None, "500")[1]
        self.assertEqual(("sentilab-door-events/1", "sentilab-door-visitors/1"),
                         (events_body["schema"], visitors_body["schema"]))
        self.assertEqual(seqs, [event["seq"] for event in events_body["events"]])
        self.assertEqual(seqs, [item["seq"] for item in visitors_body["items"]])
        first = events_body["events"][0]
        self.assertEqual(("likely_human", "read", "0f62", "likely_human · 0f62", "arrival"),
                         (first["class"], first["purpose"], first["short_id"], first["label"], first["kind"]))
        self.assertEqual({"seq", "at", "kind", "class", "purpose", "short_id", "label"} | set(LAB) | set(NAMES), set(first))
        item = visitors_body["items"][1]
        self.assertEqual({"seq", "at", "class", "purpose", "short_id", "label", "event_kind", "declaration"} | set(LAB)
                         | set(NAMES), set(item))
        self.assertEqual(("passive_arrival", None), (item["event_kind"], item["declaration"]))


if __name__ == "__main__":
    unittest.main()
