"""Measured presence: active tabs on the lab's pages (AGENT-DOOR Amendment 4 rev 2, section 4.3).

A visible lab page sends POST /api/open/v1/door/here {page, tab} every 60 s (web/public/sentilab/here.mjs). The Worker
checks the body and its per-IP limit (in its own memory, for at most 60 s), adds the detector-qualified class and
forwards {page, tab, class} with fresh headers: this service never receives a visitor's IP, user agent, cookie or
Referer, so it cannot keep one.

What is kept, all of it in this process's memory, never on disk:
- tab -> {page, class, last_seen} while the tab's last heartbeat is less than WINDOW_S (120 s) old. Every read and
  every heartbeat erases expired tabs first, and a sweeper thread erases them within SWEEP_S of expiry when nothing
  calls.
- for "tabs seen today": the set of HMAC-SHA256(daily key, tab), first 16 bytes, so that a tab that comes back is not
  counted twice. The daily key is random. The set and its key are dropped together when the UTC day ends.
- the number of heartbeats in the current minute, for the overall limit (no IP: this service has none).

Memory is bounded (max_active tabs, max_day marks a day). A heartbeat over a bound or a limit is refused and counted
nowhere: once today's set is full, a tab not already in it is refused until the day ends, so every counted tab is in the
set and tabs_seen_today is exact for the heartbeats accepted (root's P2 on #90 at 6438264c).

These are tabs, not people: one browser can open many tabs, and a bot can POST here. A restart starts every count
again. Turned on by DOOR_PRESENCE=on (service.Door.from_env); without it the door publishes #89's not_measured state.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import threading
import time
from collections import OrderedDict
from datetime import datetime, timezone

from open_proposals.contract.schemas import REGISTRY, StrictValidator

PAGES = ("wall", "package3d", "live", "board", "results")
CLASSES = ("likely_human", "agent", "bot", "unknown")
WINDOW_S = 120
SWEEP_S = 1.0
MINUTE_S = 60
TAB = re.compile(r"[0-9a-f]{32}\Z")
NOT_MEASURED = {"status": "not_measured", "count": None}
HERE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["page", "tab", "class"],
    "properties": {
        "page": {"enum": list(PAGES)},
        "tab": {"type": "string", "pattern": "^[0-9a-f]{32}$"},
        "class": {"enum": list(CLASSES)},
    },
}
HERE = StrictValidator(HERE_SCHEMA, registry=REGISTRY)


def utc_day(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d")


class Presence:
    """Active tabs (the last WINDOW_S seconds) and today's distinct tabs. Thread-safe; every method reads the clock it
    is given."""

    def __init__(self, *, clock=time.time, max_active: int = 20_000, max_day: int = 200_000, per_minute: int = 6_000,
                 new_key=lambda: secrets.token_bytes(32)):
        self._clock, self._new_key = clock, new_key
        self._max_active, self._max_day, self._per_minute = max_active, max_day, per_minute
        self._lock = threading.Lock()
        self._active: OrderedDict = OrderedDict()    # tab -> {"page", "class", "last_seen"}, least recently seen first
        self._day = None                             # the UTC day that _key and _seen belong to
        self._key = None                             # that day's random HMAC key
        self._seen: set = set()                      # that day's HMAC(key, tab)[:16]
        self._minute = (0.0, 0)                      # (start of the current minute, heartbeats in it)
        self._stop = threading.Event()
        self._sweeper = None

    def _mark(self, tab: str) -> bytes:
        return hmac.new(self._key, tab.encode("ascii"), hashlib.sha256).digest()[:16]

    def _expire(self, now: float) -> None:
        """Erase tabs last seen WINDOW_S or more ago (oldest first), and end yesterday's set and key."""
        while self._active:
            tab, entry = next(iter(self._active.items()))
            if now - entry["last_seen"] < WINDOW_S:
                break
            del self._active[tab]
        day = utc_day(now)
        if day != self._day:
            self._day, self._key, self._seen = day, self._new_key(), set()

    def beat(self, page: str, tab: str, klass: str) -> str:
        """One heartbeat: "counted" (a tab not active until now), "refreshed", or "limited" (nothing is kept)."""
        if page not in PAGES or klass not in CLASSES or not isinstance(tab, str) or not TAB.match(tab):
            raise ValueError("not a heartbeat")
        with self._lock:
            now = self._clock()
            self._expire(now)
            start, count = self._minute
            if now - start >= MINUTE_S or now < start:
                start, count = now, 0
            if count >= self._per_minute:
                return "limited"
            known = tab in self._active
            mark = self._mark(tab)
            # A tab today's set can't hold is not counted anywhere, so every counted tab is in the set and
            # tabs_seen_today stays exact, never a silent undercount (root's #90 P2).
            if mark not in self._seen and len(self._seen) >= self._max_day:
                return "limited"
            if not known and len(self._active) >= self._max_active:
                return "limited"
            self._minute = (start, count + 1)
            self._active.pop(tab, None)
            self._active[tab] = {"page": page, "class": klass, "last_seen": float(now)}
            self._seen.add(mark)
            return "refreshed" if known else "counted"

    def snapshot(self) -> dict:
        """#89's current_presence, measured: every page and class listed, zeros included."""
        with self._lock:
            self._expire(self._clock())
            by_page, by_class = dict.fromkeys(PAGES, 0), dict.fromkeys(CLASSES, 0)
            for entry in self._active.values():
                by_page[entry["page"]] += 1
                by_class[entry["class"]] += 1
            return {"status": "measured", "window_s": WINDOW_S,
                    "active_tabs": {"total": len(self._active), "by_page": by_page, "by_class": by_class},
                    "tabs_seen_today": len(self._seen)}

    def sweep(self) -> None:
        """Erase every expired tab wherever it sits (a clock step back can order them out of time), and end the day."""
        with self._lock:
            now = self._clock()
            for tab in [tab for tab, entry in self._active.items() if now - entry["last_seen"] >= WINDOW_S]:
                del self._active[tab]
            self._expire(now)

    def _sweep_loop(self) -> None:
        while not self._stop.wait(SWEEP_S):
            self.sweep()

    def start(self) -> None:
        if self._sweeper is None:
            self._stop.clear()
            self._sweeper = threading.Thread(target=self._sweep_loop, name="door-presence-sweeper", daemon=True)
            self._sweeper.start()

    def stop(self) -> None:
        self._stop.set()
        if self._sweeper is not None:
            self._sweeper.join(5)
            self._sweeper = None
