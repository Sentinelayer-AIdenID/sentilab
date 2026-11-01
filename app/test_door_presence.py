"""Measured presence (AGENT-DOOR Amendment 4 rev 2, section 4.3): active tabs, not people, kept exactly as stated.

- The state holds tab -> {page, class, last_seen} for 120 s, and today's set of HMAC(daily key, tab). Nothing else:
  the exact key sets are asserted, and no IP, user agent, cookie or Referer reaches the state or the disk.
- A tab is active while its last heartbeat is less than 120 s old; a returning tab is counted once per UTC day; the
  day's set and key are dropped together at day end, by the sweeper even when nothing calls.
- Presence is published as #89's current_presence, and stays not_measured on a door without it.
- A heartbeat never touches the door's store: admission, runs, counters and events are unchanged.
"""
import hashlib
import hmac
import json
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path

from app.door import testkit as tk
from app.door.presence import CLASSES, NOT_MEASURED, PAGES, WINDOW_S, Presence

TAB_A, TAB_B, TAB_C = "a" * 32, "0123456789abcdef" * 2, "f" * 31 + "0"
NOON = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc).timestamp()
MIDNIGHT = datetime(2026, 11, 2, 0, 0, tzinfo=timezone.utc).timestamp()
CANARIES = ("203.0.113.77", "198.51.100.9", "canary-agent/9.9", "sl_view=canary", "https://referer.example/canary")
STATE = {"_clock", "_new_key", "_max_active", "_max_day", "_per_minute", "_lock", "_active", "_day", "_key", "_seen",
         "_minute", "_stop", "_sweeper"}


class Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


def keys():
    """Distinct, recognisable daily keys, so a test can tell yesterday's key from today's."""
    count = [0]

    def make():
        count[0] += 1
        return hashlib.sha256(f"presence test daily key {count[0]}".encode()).digest()
    return make


class PresenceStateTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock(NOON)
        self.presence = Presence(clock=self.clock, new_key=keys())

    def test_a_returning_tab_is_not_counted_twice_within_the_day(self):
        self.assertEqual(self.presence.beat("live", TAB_A, "likely_human"), "counted")
        self.clock.now += 60
        self.assertEqual(self.presence.beat("live", TAB_A, "likely_human"), "refreshed")
        self.clock.now += WINDOW_S + 5          # the tab went quiet: no longer active
        snap = self.presence.snapshot()
        self.assertEqual((snap["active_tabs"]["total"], snap["tabs_seen_today"]), (0, 1))
        self.clock.now += 1                     # the same tab comes back, the same day
        self.assertEqual(self.presence.beat("board", TAB_A, "likely_human"), "counted")
        snap = self.presence.snapshot()
        self.assertEqual((snap["active_tabs"]["total"], snap["tabs_seen_today"]), (1, 1))
        self.assertEqual(snap["active_tabs"]["by_page"]["board"], 1)
        self.presence.beat("live", TAB_B, "bot")
        self.assertEqual(self.presence.snapshot()["tabs_seen_today"], 2)

    def test_the_window_is_120_seconds_exactly(self):
        self.presence.beat("wall", TAB_A, "agent")
        self.clock.now += WINDOW_S - 0.5
        self.assertEqual(self.presence.snapshot()["active_tabs"]["total"], 1)
        self.clock.now += 0.5
        self.assertEqual(self.presence.snapshot()["active_tabs"]["total"], 0)
        self.assertEqual(self.presence._active, {})

    def test_a_refresh_keeps_a_tab_active_from_its_latest_heartbeat(self):
        self.presence.beat("wall", TAB_A, "agent")
        self.presence.beat("wall", TAB_B, "agent")
        self.clock.now += 100
        self.presence.beat("wall", TAB_A, "agent")
        self.clock.now += 30                    # TAB_B is 130 s old, TAB_A 30 s
        self.assertEqual(self.presence.snapshot()["active_tabs"]["total"], 1)
        self.assertEqual(set(self.presence._active), {TAB_A})

    def test_the_day_ends_with_its_set_and_key(self):
        self.presence.beat("live", TAB_A, "likely_human")
        yesterday = self.presence._key
        self.clock.now = MIDNIGHT - 0.001
        self.assertEqual(self.presence.snapshot()["tabs_seen_today"], 1)
        self.clock.now = MIDNIGHT
        self.assertEqual(self.presence.snapshot()["tabs_seen_today"], 0)
        self.assertNotEqual(self.presence._key, yesterday)
        self.assertEqual(self.presence._seen, set())
        self.assertEqual(self.presence._day, "2026-11-02")
        self.presence.beat("live", TAB_A, "likely_human")      # a new day counts the tab again, once
        self.presence.beat("live", TAB_A, "likely_human")
        self.assertEqual(self.presence.snapshot()["tabs_seen_today"], 1)

    def test_the_sweeper_erases_expired_tabs_and_ends_the_day_with_no_request(self):
        self.presence.beat("live", TAB_A, "likely_human")
        self.presence.start()
        try:
            self.clock.now = MIDNIGHT + WINDOW_S
            deadline = time.monotonic() + 5
            while (self.presence._active or self.presence._seen) and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertEqual(self.presence._active, {})
            self.assertEqual(self.presence._seen, set())
            self.assertEqual(self.presence._day, "2026-11-02")
        finally:
            self.presence.stop()
        self.assertIsNone(self.presence._sweeper)

    def test_the_sweeper_erases_a_tab_wherever_it_sits(self):
        # A step back of the clock puts a newer heartbeat behind an older one; the sweep still finds every expired tab.
        self.presence.beat("live", TAB_A, "likely_human")
        self.clock.now -= 10
        self.presence.beat("live", TAB_B, "likely_human")
        self.clock.now += 10 + WINDOW_S - 5     # TAB_A is 115 s old, TAB_B 125 s
        self.presence.sweep()
        self.assertEqual(set(self.presence._active), {TAB_A})

    def test_the_stored_state_has_exactly_the_named_keys(self):
        self.presence.beat("live", TAB_A, "likely_human")
        self.presence.beat("package3d", TAB_B, "bot")
        self.assertEqual(set(vars(self.presence)), STATE)
        self.assertEqual(set(self.presence._active), {TAB_A, TAB_B})
        for entry in self.presence._active.values():
            self.assertEqual(set(entry), {"page", "class", "last_seen"})
            self.assertIn(entry["page"], PAGES)
            self.assertIn(entry["class"], CLASSES)
            self.assertIsInstance(entry["last_seen"], float)
        self.assertEqual(len(self.presence._seen), 2)
        for mark in self.presence._seen:
            self.assertIsInstance(mark, bytes)
            self.assertEqual(len(mark), 16)
        # The day's marks are the keyed HMAC of the tab: the raw tab is not in the set, and without the key (dropped at
        # day end) a mark can't be tied back to a tab.
        expected = {hmac.new(self.presence._key, tab.encode(), hashlib.sha256).digest()[:16] for tab in (TAB_A, TAB_B)}
        self.assertEqual(self.presence._seen, expected)
        self.assertEqual(self.presence._day, "2026-11-01")
        self.assertIsInstance(self.presence._key, bytes)
        self.assertEqual(len(self.presence._key), 32)
        start, count = self.presence._minute
        self.assertEqual((start, count), (NOON, 2))

    def test_every_page_and_class_is_listed_with_zeros(self):
        self.assertEqual(self.presence.snapshot(), {
            "status": "measured", "window_s": 120,
            "active_tabs": {"total": 0, "by_page": dict.fromkeys(PAGES, 0), "by_class": dict.fromkeys(CLASSES, 0)},
            "tabs_seen_today": 0})
        self.presence.beat("results", TAB_A, "unknown")
        self.presence.beat("results", TAB_B, "agent")
        self.presence.beat("wall", TAB_C, "agent")
        snap = self.presence.snapshot()
        self.assertEqual(snap["active_tabs"], {"total": 3,
                                               "by_page": {"wall": 1, "package3d": 0, "live": 0, "board": 0, "results": 2},
                                               "by_class": {"likely_human": 0, "agent": 2, "bot": 0, "unknown": 1}})
        self.assertEqual(list(snap["active_tabs"]["by_page"]), list(PAGES))
        self.assertEqual(list(snap["active_tabs"]["by_class"]), list(CLASSES))

    def test_a_tab_that_moves_page_or_class_is_one_tab(self):
        self.presence.beat("live", TAB_A, "unknown")
        self.presence.beat("board", TAB_A, "likely_human")
        snap = self.presence.snapshot()
        self.assertEqual(snap["active_tabs"]["total"], 1)
        self.assertEqual((snap["active_tabs"]["by_page"]["board"], snap["active_tabs"]["by_page"]["live"]), (1, 0))
        self.assertEqual(snap["active_tabs"]["by_class"]["likely_human"], 1)
        self.assertEqual(snap["tabs_seen_today"], 1)

    def test_only_a_heartbeat_of_the_exact_shape_is_kept(self):
        for page, tab, klass in (("lab", TAB_A, "agent"), ("live", TAB_A.upper(), "agent"), ("live", TAB_A[:31], "agent"),
                                 ("live", TAB_A + "0", "agent"), ("live", TAB_A, "human"), ("live", 7, "agent"),
                                 ("live", TAB_A + "\n", "agent"), ("live", "g" * 32, "agent")):
            with self.assertRaises(ValueError):
                self.presence.beat(page, tab, klass)
        self.assertEqual(self.presence._active, {})
        self.assertEqual(self.presence._seen, set())

    def test_the_overall_limit_counts_heartbeats_per_minute(self):
        presence = Presence(clock=self.clock, new_key=keys(), per_minute=3)
        for tab in (TAB_A, TAB_B, TAB_C):
            self.assertIn(presence.beat("live", tab, "agent"), ("counted", "refreshed"))
        self.assertEqual(presence.beat("live", "1" * 32, "agent"), "limited")
        self.assertEqual(presence.beat("live", TAB_A, "agent"), "limited")
        self.assertNotIn("1" * 32, presence._active)
        self.clock.now += 59.5
        self.assertEqual(presence.beat("live", "1" * 32, "agent"), "limited")
        self.clock.now += 0.5
        self.assertEqual(presence.beat("live", "1" * 32, "agent"), "counted")
        self.assertEqual(presence.snapshot()["tabs_seen_today"], 4)

    def test_capacity_bounds_active_tabs_and_the_day_set(self):
        presence = Presence(clock=self.clock, new_key=keys(), max_active=2, max_day=3)
        self.assertEqual(presence.beat("live", TAB_A, "agent"), "counted")
        self.assertEqual(presence.beat("live", TAB_B, "agent"), "counted")
        self.assertEqual(presence.beat("live", TAB_C, "agent"), "limited")      # full: a new tab is not kept
        self.assertEqual(presence.beat("live", TAB_A, "agent"), "refreshed")    # a known tab still refreshes
        self.clock.now += WINDOW_S
        self.assertEqual(presence.beat("live", TAB_C, "agent"), "counted")
        self.assertEqual(presence.beat("live", "1" * 32, "agent"), "counted")
        self.assertEqual(presence.snapshot()["tabs_seen_today"], 3)             # the day set stops at max_day
        self.assertEqual(presence.beat("live", "2" * 32, "agent"), "limited")
        self.assertEqual(len(presence._seen), 3)


class PresenceDoorTests(tk.DoorCase, unittest.TestCase):
    http = True

    def setUp(self):
        super().setUp()
        self.door.presence = Presence(clock=self.clock, new_key=keys())

    def here(self, value, headers=None):
        raw = value if isinstance(value, bytes) else json.dumps(value).encode()
        return self.request("POST", "/api/open/v1/door/here", raw, {"content-type": "application/json", **(headers or {})})

    def test_a_heartbeat_is_kept_without_ip_user_agent_cookie_or_referer(self):
        before = self.store.last_seq()
        status, body, headers = self.here({"page": "live", "tab": TAB_A, "class": "likely_human"}, {
            "cf-connecting-ip": CANARIES[0], "x-forwarded-for": f"{CANARIES[1]}, {CANARIES[0]}",
            "user-agent": CANARIES[2], "cookie": CANARIES[3], "referer": CANARIES[4]})
        self.assertEqual((status, body), (204, None))
        self.assertEqual(headers.get("cache-control"), "no-store")
        state = repr(vars(self.door.presence)) + repr(self.door.presence._active) + repr(self.door.presence._seen)
        for canary in CANARIES:
            self.assertNotIn(canary, state)
        # Nothing about presence is written to disk: not the tab, not any header.
        self.assertEqual(self.store.last_seq(), before)
        for path in Path(self.tmp.name).iterdir():
            data = path.read_bytes()
            for needle in (TAB_A, *CANARIES):
                self.assertNotIn(needle.encode(), data, path.name)
        self.assertEqual(self.door.presence.snapshot()["active_tabs"]["by_class"]["likely_human"], 1)

    def test_bad_heartbeats_are_refused_and_keep_nothing(self):
        good = {"page": "live", "tab": TAB_A, "class": "likely_human"}
        bad = [{**good, "page": "admin"}, {**good, "tab": TAB_A.upper()}, {**good, "class": "human"},
               {"page": "live", "tab": TAB_A}, {**good, "ip": CANARIES[0]}, {**good, "user_agent": CANARIES[2]},
               b"not json", b'{"page":"live","page":"wall","tab":"' + TAB_A.encode() + b'","class":"bot"}', b" " * 4097]
        for value in bad:
            status, body, _ = self.here(value)
            self.assertEqual(status, 400, value)
            self.assertEqual(body["error"], "bad_heartbeat")
            self.assertNotIn(CANARIES[0], json.dumps(body))
        self.assertEqual(self.door.presence._active, {})
        self.assertEqual(self.door.presence._seen, set())

    def test_over_the_overall_limit_is_429_and_keeps_nothing(self):
        self.door.presence = Presence(clock=self.clock, new_key=keys(), per_minute=1)
        self.assertEqual(self.here({"page": "live", "tab": TAB_A, "class": "bot"})[0], 204)
        status, body, headers = self.here({"page": "live", "tab": TAB_B, "class": "bot"})
        self.assertEqual((status, body, headers.get("retry-after")), (429, {"error": "rate_limited"}, "60"))
        self.assertEqual(set(self.door.presence._active), {TAB_A})

    def test_presence_is_published_as_current_presence(self):
        self.here({"page": "package3d", "tab": TAB_A, "class": "likely_human"})
        self.here({"page": "live", "tab": TAB_B, "class": "agent"})
        status, page, _ = self.request("GET", "/api/open/v1/door/visitors?limit=1")
        self.assertEqual(status, 200)
        self.assertEqual(page["current_presence"], {
            "status": "measured", "window_s": 120,
            "active_tabs": {"total": 2, "by_page": {"wall": 0, "package3d": 1, "live": 1, "board": 0, "results": 0},
                            "by_class": {"likely_human": 1, "agent": 1, "bot": 0, "unknown": 0}},
            "tabs_seen_today": 2})

    def test_a_heartbeat_never_touches_admission_runs_counters_or_events(self):
        status, reply = self.submit(self.body())
        self.assertEqual(status, 202, reply)
        before = (self.door.board()[1]["counts"], self.door.board()[1]["door"], self.store.last_seq(),
                  self.door.results(None, None)[1]["items"])
        for index in range(20):
            self.assertEqual(self.here({"page": "live", "tab": f"{index:032x}", "class": "bot"})[0], 204)
        after = (self.door.board()[1]["counts"], self.door.board()[1]["door"], self.store.last_seq(),
                 self.door.results(None, None)[1]["items"])
        self.assertEqual(before, after)


class NotMeasuredTests(tk.DoorCase, unittest.TestCase):
    http = True

    def test_a_door_without_presence_says_not_measured_and_refuses_heartbeats(self):
        self.assertIsNone(self.door.presence)
        status, body, _ = self.request("POST", "/api/open/v1/door/here",
                                       json.dumps({"page": "live", "tab": TAB_A, "class": "bot"}).encode(),
                                       {"content-type": "application/json"})
        self.assertEqual((status, body), (503, {"error": "presence_not_measured"}))
        page = self.request("GET", "/api/open/v1/door/visitors")[1]
        self.assertEqual(page["current_presence"], NOT_MEASURED)
        self.assertEqual(page["current_presence"], {"status": "not_measured", "count": None})

    def test_the_environment_switch_is_the_only_way_on(self):
        from app.door.service import Door

        for value, measured in (("on", True), ("", False), ("off", False), ("ON", False), ("1", False)):
            door = Door.from_env({"DOOR_PRESENCE": value, "DOOR_DATA_DIR": self.tmp.name})
            self.assertEqual(door.presence is not None, measured, value)


if __name__ == "__main__":
    unittest.main()
