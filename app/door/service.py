"""The door service: one object holding the policy, the store, the scorer and the workers, and the response bodies of
every endpoint. routes.py only moves bytes in and out.

Response vocabulary. A refusal of the submission itself always reads {"state": "rejected", "codes": [...]}, with the
contract's violations (codes, schema paths and keywords, die indices, whole micrometres, retry_after) and nothing a
visitor sent. Token refusals use the door token vocabulary of AGENT-DOOR section 1: {"error": "token_scope",
"allowed": <purpose>}, {"error": "token_expired"}, {"error": "token_invalid"}.
"""
from __future__ import annotations

import json
import math
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from open_proposals.contract import canonical as hashes
from open_proposals.contract.codes import GROUP, violation
from open_proposals.contract.labels import label_for

from . import intake
from . import terms as door_terms
from .dispatch import Dispatcher, ScorerState
from .policy import CASE, NONCE, Policy, parse_utc, principal_for, short_id, utc
from .presence import HERE, NOT_MEASURED, Presence
from .scorer import ACTIVE_GUARD_C, METRIC, METRIC_ID, HttpScorer
from .stats import Totals
from .store import Store, label

RUN_ID = re.compile(r"open-[0-9a-f]{8}-[0-9a-f]{32}\Z")
CURSOR_MAX = 2 ** 53 - 1
RESULT_LABEL = "simulated, not silicon; HotSpot 6.0, grid 64; " + METRIC_ID
EVALUATOR_IDENTITY = "hotspot6:751b357f6b5af395a4447d6e3bfeef3a75eb447091798365a3db4f0e00618cc6:grid:64x64"
PROXY = {"field": "wire_proxy_mm", "unit": "mm", "kind": "proxy, not routed wire",
         "definition": ("weighted-mean Manhattan centre distance over the netlist "
                        "(the 64-entry matrix, 5,120 unordered wire weights)")}
GUARD = {"field": "active_layer_peak_C", "rule": "strictly below", "limit_C": ACTIVE_GUARD_C}
# Fixed facts with their sources (AGENT-DOOR Amendments 1 and 2; root #57429, #57438, #57454). The raw reference is
# one measured pair: its metric and its proxy come from the same raw geometry. The snapped reference has no
# temperature, and none is invented.
REFERENCES = (
    {"id": "original-raw", "layout": "raw", "max_chiplet_centre_cell_mean_C": 115.935,
     "native_all_block_max_C": 115.93, "active_layer_peak_C": 119.07, "wire_proxy_mm": 9.38487,
     "note": "raw reconstruction of TAP-2.5D Fig. 5(a): reference only, not on the lattice; HotSpot 6.0 grid 64, "
             "gate zero PASS 2026-10-31T23:45Z"},
    {"id": "original-snapped-0p5", "layout": "snapped", "max_chiplet_centre_cell_mean_C": None,
     "native_all_block_max_C": None, "active_layer_peak_C": None, "wire_proxy_mm": 9.5,
     "note": "legal 0.5 mm snap of the raw layout; temperature not evaluated"},
)
PUBLISHED = (
    {"name": "original", "source": "TAP-2.5D (Ma et al., DATE 2021), Fig. 5(a)", "peak_C": 115.94,
     "statistic": "the paper's HotSpot block selector, not this board's metric", "routed_wire_mm": 67686},
    {"name": "TAP-2.5D", "source": "TAP-2.5D (Ma et al., DATE 2021), Fig. 5(c)", "peak_C": 94.89,
     "statistic": "the paper's HotSpot block selector, not this board's metric", "routed_wire_mm": 216064},
)
NOT_CLAIMED = ["beat", "margin", "routed wire", "source acceptance"]
# The words the open feeds give a state (results, board, status), one literal pair per lifecycle state: the Package view
# reads exactly these strings (web/public/sentilab/package/source3d.mjs SUMMARIES). The contract's four-state summary
# (states.py SUMMARY) stays the contract's; the door says what actually ran. A reproduced run is the same pinned build
# replayed in a fresh process: reproduction, not independent verification (the door never emits cross_checked, which
# the contract words as reproduced). A failed run has no score. Every other state keeps the contract's word.
FEED_SUMMARY = {"rejected": "rejected",
                "queued": "queued", "held": "queued", "evaluating": "queued",
                "evaluated": "evaluated", "replaying": "evaluated", "not_reproduced": "evaluated",
                "failed": "no score",
                "reproduced": "reproduced by a fresh-process replay",
                "cross_checked": "reproduced by a fresh-process replay",
                "cancelled": None, "expired": None}
BEAT = {"available": False,
        "requires": "reproduced by replay, plus the fixed routed-wire predicates and their evidence; "
                    "this API never emits a beat verdict"}


def iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def http_status(codes: list) -> int:
    first = codes[0]["code"]
    if first == "oversize":
        return 413
    if GROUP[first] in ("transport", "envelope"):
        return 400
    if first in ("not_open_yet", "manifest_closed"):
        return 503
    if first == "idempotency_conflict":
        return 409
    if GROUP[first] == "policy":
        return 429
    return 422


def front(points: list) -> set:
    """Ids of the points no other point dominates (lower or equal on both axes, lower on one). points:
    (id, metric, proxy); smaller is better on both. Exact values: display rounding never enters a comparison."""
    best, on_front = math.inf, set()
    ordered = sorted(points, key=lambda point: (point[1], point[2]))
    index = 0
    while index < len(ordered):
        metric = ordered[index][1]
        group = [point for point in ordered[index:] if point[1] == metric]
        lowest = group[0][2]
        if lowest < best:
            on_front.update(point[0] for point in group if point[2] == lowest)
        best = min(best, lowest)
        index += len(group)
    return on_front


class Door:
    presence = None          # measured presence (presence.py); None publishes #89's not_measured state

    def __init__(self, policy: Policy, store: Store, scorer=None, terms: door_terms.Terms | None = None,
                 presence: Presence | None = None):
        self.policy, self.store, self.scorer, self.presence = policy, store, scorer, presence
        # The signed manifest's terms text, bound to its pin when the door is built (terms.py); None: unavailable.
        self.terms = terms
        self.scorer_state = ScorerState()
        self.dispatcher = Dispatcher(self)
        self.totals = Totals()

    @classmethod
    def from_env(cls, env=None) -> "Door":
        env = os.environ if env is None else env
        configured = env.get("DOOR_DATA_DIR", "")
        data = Path(configured) if configured else (Path("/data/door") if Path("/data").is_dir() else
                                                     Path("/tmp/door"))
        policy, scorer = Policy.from_env(env), None
        if env.get("DOOR_SCORER_URL") and env.get("DOOR_SCORER_TOKEN") and policy.usable:
            try:
                # Health and every receipt must name the manifest's pinned binary, this grant and the signed image.
                scorer = HttpScorer(env["DOOR_SCORER_URL"], env["DOOR_SCORER_TOKEN"], grant_id=policy.grant.grant,
                                    image_digest=policy.grant.scorer_image_digest,
                                    binary_sha256=policy.manifest["statistic"]["evaluator"]["binary_sha256"])
            except ValueError:
                scorer = None
        # Presence is measured only where the pages send heartbeats, and the deployer says so (AGENT-DOOR A4 rev 2).
        presence = Presence() if env.get("DOOR_PRESENCE", "") == "on" else None
        return cls(policy, Store(data / "door.sqlite3"), scorer, door_terms.from_env(policy.manifest, env), presence)

    def start(self, workers: bool = True) -> None:
        if self.presence is not None:
            self.presence.start()
        self.dispatcher.start(workers)

    def stop(self) -> None:
        self.dispatcher.stop()
        if self.presence is not None:
            self.presence.stop()

    # ── submit ──────────────────────────────────────────────────────────────────────────────────────────────────

    def _rejected(self, codes: list, *, limits=None, now=None) -> tuple:
        body = {"schema": "sentilab-door-submit/1", "state": "rejected", "codes": codes}
        headers = {}
        if limits:
            body["limits"] = limits
        waits = [parse_utc(item["retry_after"]) for item in codes if "retry_after" in item]
        if waits and now is not None:
            headers["retry-after"] = str(max(1, math.ceil(max(waits) - now)))
        return http_status(codes), body, headers

    def submit(self, raw: bytes, size: int | None = None) -> tuple:
        """(HTTP status, body, headers) for one forwarded submission. size is the declared length when the body was
        not read in full."""
        now = self.policy.clock()
        value, found = intake.read_submit(raw, size)
        if found:
            return self._rejected(found)
        claims = value["token_claims"]
        refusal = intake.token_refusal(claims, now)
        if refusal is not None:
            return 403, refusal, {}
        principal = principal_for(claims["nonce"])
        # The declared operator is accepted (lane 1's shape) and never kept, not even in the store (warden's P3-6).
        short, klass, operator = short_id(principal), value.get("class", "unknown"), "unknown"
        limited = self.store.note_request(principal=principal, now=now, flood=self.policy.flood)
        if limited:
            return self._rejected(limited, limits=["request_rate"], now=now)

        def refuse(codes):
            self.store.note_rejected(principal=principal, short=short, klass=klass, codes=codes, now=now)
            return self._rejected(codes, now=now)

        closed, _final = self.policy.admission(now)
        if closed:
            return refuse(closed)
        dies, found = intake.layout_dies(value["layout"])
        if found:
            return refuse(found)
        proposal = intake.build_proposal(self.policy, principal=principal, terms=value["terms"], dies=dies,
                                         request_key=value.get("request_key"))
        legal, found = intake.legality(self.policy, proposal.item)
        if not legal:
            return refuse(found)
        decision = self.store.admit(policy=self.policy, proposal=proposal, klass=klass, operator=operator,
                                    wire_proxy_mm=self.policy.checker.wire_proxy_mm(proposal.item["dies"]),
                                    token_exp=claims["exp"], now=now)
        if decision["decision"] in ("rejected", "refused"):
            return self._rejected(decision["codes"], limits=decision.get("limits"), now=now)
        row, position = self.store.run(decision["run_id"])
        body = {"schema": "sentilab-door-submit/1", "state": row["state"], "run_id": row["run_id"],
                "position": position, "duplicate": decision["decision"] == "duplicate",
                "label": label(row["class"], row["short_id"]), "short_id": row["short_id"],
                "geometry_sha256": row["geometry_sha256"], "wire_proxy_mm": row["wire_proxy_mm"], "metric": METRIC}
        if decision["decision"] == "duplicate":
            return 200, body, {}
        self.dispatcher.wake()
        return 202, body, {}

    def arrival(self, raw: bytes, size: int | None = None) -> tuple:
        value, found = intake.read_arrival(raw, size)
        if found:
            return 400, {"schema": "sentilab-door-arrival/1", "state": "rejected", "codes": found}, {}
        short = short_id(principal_for(value["nonce"])) if "nonce" in value else None
        # operator is accepted (lane 1's shape) and never kept: it leaves every open feed (AGENT-DOOR Amendment 3).
        body = {"class": value["class"], "purpose": value.get("purpose"), "short_id": short,
                "label": label(value["class"], short) if short else value["class"]}
        if "declaration" in value:
            body["declaration"] = value["declaration"]
            if "nonce" in value and len(self.policy.k_challenge) >= 32:
                body["visitor_handle"] = self.policy.keyed("public-visitor/1", value["nonce"])
        now = self.policy.clock()
        if not self.store.note_arrival(body, now=now, per_min=self.policy.flood.arrivals_per_min):
            codes = [violation("rate_limited", retry_after=utc(now + 60))]
            body = {"schema": "sentilab-door-arrival/1", "state": "rejected", "codes": codes}
            return 429, body, {"retry-after": "60"}
        return 204, None, {}

    # ── launch revalidation (called inside the claim's transaction) ─────────────────────────────────────────────

    def launch_check(self, run):
        found, final = self.policy.admission(self.policy.clock())
        if found:
            return ("expire", "window_closed") if final else "wait"
        if run["manifest_id"] != self.policy.manifest_id or run["case_id"] != CASE:
            return ("expire", "manifest_changed")
        try:
            item = json.loads(run["proposal"])
            if hashes.content_sha256(item) != run["proposal_sha256"]:
                return ("cancel", "revalidation_failed")
            legal, _found = intake.legality(self.policy, item)
        except Exception:  # noqa: BLE001 - an unreadable stored run is cancelled, never left to block the queue
            return ("cancel", "revalidation_failed")
        return None if legal else ("cancel", "revalidation_failed")

    # ── reads ───────────────────────────────────────────────────────────────────────────────────────────────────

    def _front_ids(self) -> set:
        scored, _counters, _states, _grant = self.store.board_rows()
        eligible = [(row["run_id"], row["metric_c"], row["wire_proxy_mm"]) for row in scored
                    if self._eligible(row)]
        reference = REFERENCES[0]
        points = eligible + [(reference["id"], reference["max_chiplet_centre_cell_mean_C"],
                              reference["wire_proxy_mm"])]
        return front(points)

    @staticmethod
    def _eligible(row) -> bool:
        """A candidate needs replay (reproduced), a score bound to the selector, and the active guard strictly met."""
        return (row["state"] == "reproduced" and row["binding_ok"] == 1 and row["active_c"] is not None
                and row["active_c"] < ACTIVE_GUARD_C)

    def item(self, row, position, front_ids: set) -> dict:
        proposal = json.loads(row["proposal"])
        codes = [entry["code"] for entry in json.loads(row["codes"])]
        item = {"id": row["run_id"], "label": label(row["class"], row["short_id"]), "class": row["class"],
                "short_id": row["short_id"], "arrival": row["arrival"],
                "seq": row["version"], "status": row["state"], "summary": FEED_SUMMARY[row["state"]], "codes": codes,
                "reason": row["reason"], "position": position, "dies": proposal["dies"],
                "geometry_sha256": row["geometry_sha256"], "wire_proxy_mm": row["wire_proxy_mm"],
                "metric": METRIC, "result": None, "verdict": None}
        if row["result"]:
            result = json.loads(row["result"])
            guard_ok = result["active_layer_peak_C"] < ACTIVE_GUARD_C
            item["result"] = {
                "metric": METRIC, "metric_id": METRIC_ID,
                METRIC_ID: result[METRIC_ID],
                "native_all_block_max_C": result["native_all_block_max_C"],
                "active_layer_peak_C": result["active_layer_peak_C"],
                "active_guard": {**GUARD, "ok": guard_ok},
                "per_die_C": result["per_die_C"],
                "grid64": None if result["grid64"] is None else [[round(value, 3) for value in grid_row]
                                                                  for grid_row in result["grid64"]],
                "grid": {"rows": 64, "cols": 64, "unit": "C", "layer": "active",
                         "orientation": "row 0 is the frame's top edge (max y); column 0 its left edge (min x)"},
                "replay": result["replay"], "reproduced": row["state"] == "reproduced",
                "binding_ok": result["binding"]["ok"],
                "evaluator": result["evaluator"], "temperature_label": label_for(EVALUATOR_IDENTITY),
                "label": RESULT_LABEL,
                "verification": self.verification(row, result, guard_ok, row["run_id"] in front_ids)}
            if row["run_id"] in front_ids:
                item["verdict"] = "candidate"
        return item

    @staticmethod
    def verification(row, result: dict, guard_ok: bool, candidate: bool) -> dict:
        """What this result has been checked for, and what it is not. The 3D view's caption binds to this block.
        `candidate` means: reproduced by a distinct, receipt-bound replay; bound to the selector; the active guard
        strictly met; on the front against the raw reference. It claims none of NOT_CLAIMED."""
        replay = result["replay"]
        basis = ["per_die"] + (["grid"] if "grid_ok" in result["binding"] else []) + (
            ["wire"] if "wire_ok" in result["binding"] else [])
        return {"replay": "reproduced" if row["state"] == "reproduced" else "not_reproduced",
                "replay_code": replay.get("code"), "distinct_execution": replay["fresh_process"],
                "receipts_bound": replay.get("receipts_bound", False), "binding_ok": result["binding"]["ok"],
                "binding_basis": basis, "active_guard_ok": guard_ok,
                "cpu": "measured" if result.get("cpu_known", False) else "unknown_charged_conservatively",
                "candidate": candidate, "not_claimed": list(NOT_CLAIMED)}

    def status(self, run_id: str, nonce) -> tuple:
        if not isinstance(nonce, str) or not NONCE.match(nonce):
            return 400, {"error": "token_required"}, {}
        if not isinstance(run_id, str) or not RUN_ID.match(run_id):
            return 404, {"error": "run_not_found"}, {}
        row, position = self.store.run(run_id)
        principal = principal_for(nonce)
        if row is None or row["principal"] != principal:
            return 404, {"error": "run_not_found"}, {}
        body = {"schema": "sentilab-door-status/1", **self.item(row, position, self._front_ids())}
        if self.policy.grant is not None:
            body["token"] = self.store.token_usage(principal=principal, grant=self.policy.grant,
                                                   manifest_id=row["manifest_id"], now=self.policy.clock())
        body["scorer"] = self.scorer_state.snapshot()
        return 200, body, {}

    @staticmethod
    def cursor(value, default: int, low: int, high: int):
        if value is None:
            return default
        if not isinstance(value, str) or not value.isascii() or not value.isdecimal() or len(value) > 16:
            return None
        number = int(value)
        return number if low <= number <= high else None

    def results(self, after, limit) -> tuple:
        after, limit = self.cursor(after, 0, 0, CURSOR_MAX), self.cursor(limit, 10, 1, 20)
        if after is None or limit is None:
            return 400, {"error": "invalid paging range"}, {}
        rows = self.store.changed_runs(after, limit + 1)
        front_ids = self._front_ids()
        page = rows[:limit]
        items = []
        for row in page:
            position = self.store.run(row["run_id"])[1] if row["state"] in ("queued", "held") else None
            items.append(self.item(row, position, front_ids))
        next_after = page[-1]["version"] if page else after
        return 200, {"schema": "sentilab-door-results/1", "items": items, "next_after": next_after,
                     "has_more": len(rows) > limit, "metric": METRIC, "label": RESULT_LABEL,
                     "scorer": self.scorer_state.snapshot()}, {}

    def events(self, after, limit) -> tuple:
        after, limit = self.cursor(after, 0, 0, CURSOR_MAX), self.cursor(limit, 100, 1, 200)
        if after is None or limit is None:
            return 400, {"error": "invalid paging range"}, {}
        rows = self.store.events(after, limit + 1)
        page = rows[:limit]
        # Handles stay in the historical store for aggregation, never in an open feed.
        events = [{"seq": row["seq"], "at": iso(row["at"]), "kind": row["kind"],
                   **{key: value for key, value in json.loads(row["body"]).items() if key != "visitor_handle"}}
                  for row in page]
        return 200, {"schema": "sentilab-door-events/1", "events": events,
                     "next_after": page[-1]["seq"] if page else after, "has_more": len(rows) > limit,
                     "scorer": self.scorer_state.snapshot()}, {}

    def visitors(self, after, limit) -> tuple:
        """Public arrival history. Declared text never changes token scope or classifier output."""
        after, limit = self.cursor(after, 0, 0, CURSOR_MAX), self.cursor(limit, 100, 1, 500)
        if after is None or limit is None:
            return 400, {"error": "invalid paging range"}, {}
        rows, counts = self.store.visitors(after, limit + 1)
        page, items = rows[:limit], []
        for row in page:
            body = json.loads(row["body"])
            item = {"seq": row["seq"], "at": iso(row["at"])}
            # Explicit projection: legacy/private fields can never leak through this new view.
            item.update({key: body.get(key) for key in ("class", "purpose", "short_id", "label")})
            declaration = body.get("declaration")
            item["declaration"] = ({key: declaration[key] for key in ("notice_version", "name", "reason", "source")
                                    if key in declaration}
                                   if isinstance(declaration, dict) else None)
            items.append(item)
        return 200, {"schema": "sentilab-door-visitors/1", "items": items,
                     "next_after": page[-1]["seq"] if page else after, "has_more": len(rows) > limit,
                     "counts": counts, "current_presence": self.current_presence(),
                     "coverage": "Recorded Door arrivals, not all HTTP requests or verified people. "
                                 "Counts use internal handles of observed purpose passes, not unique humans or agents.",
                     "declaration_trust": "self_declared_display_data",
                     "notice": {"version": intake.VISITOR_NOTICE, "text": intake.VISITOR_DISCLOSURE}}, {}

    def current_presence(self) -> dict:
        """#89's current_presence: measured (presence.py) where heartbeats are on, else not_measured."""
        return self.presence.snapshot() if self.presence is not None else dict(NOT_MEASURED)

    def here(self, raw: bytes, size: int | None = None) -> tuple:
        """One page heartbeat {page, tab, class}, forwarded by the Worker (AGENT-DOOR A4 rev 2, 4.3)."""
        if self.presence is None:
            return 503, {"error": "presence_not_measured"}, {}
        value, found = intake.read_object(raw, HERE, size)
        if found:
            return 400, {"error": "bad_heartbeat", "codes": found}, {}
        if self.presence.beat(value["page"], value["tab"], value["class"]) == "limited":
            return 429, {"error": "rate_limited"}, {"retry-after": "60"}
        return 204, None, {}

    def stats(self) -> tuple:
        """Run totals, sentilab-door-stats/1 (stats.py)."""
        return 200, self.totals.read(self.store, self.policy.clock()), {}

    def board(self, nonce=None) -> tuple:
        """The public board. With the verified token's nonce (x-door-nonce), it also carries that token's CPU."""
        now = self.policy.clock()
        scored, counters, states, grant_rows = self.store.board_rows(
            self.policy.grant.grant if self.policy.grant else None)
        front_ids = self._front_ids()
        ranked = sorted(scored, key=lambda row: (row["metric_c"], row["geometry_sha256"]))[:10]
        full = {row["run_id"]: row for row in self.store.runs_by_id([row["run_id"] for row in ranked])}
        top = []
        for row in (full[row["run_id"]] for row in ranked):
            item = self.item(row, None, front_ids)
            result = item.pop("result")
            item.pop("dies")
            item.update({METRIC_ID: result[METRIC_ID], "native_all_block_max_C": result["native_all_block_max_C"],
                         "active_layer_peak_C": result["active_layer_peak_C"],
                         "active_guard_ok": result["active_guard"]["ok"], "reproduced": result["reproduced"],
                         "binding_ok": result["binding_ok"]})
            top.append(item)
        closed, _final = self.policy.admission(now)
        grant = self.policy.grant
        reserved = sum(grant_rows.get(state, 0) for state in ("held", "active"))
        charged = grant_rows.get("settled", 0)
        body = {"schema": "sentilab-door-board/1", "label": "simulated, not silicon", "metric": METRIC,
                "proxy": PROXY, "active_guard": GUARD, "beat": BEAT, "references": list(REFERENCES),
                "published": list(PUBLISHED),
                "counts": {"attempts": counters.get("attempts", 0), "legal": counters.get("legal", 0),
                           "rejected": counters.get("rejected", 0), "refused": counters.get("refused", 0),
                           "accepted": counters.get("accepted", 0),
                           **{state: states.get(state, 0) for state in (
                               "queued", "evaluating", "reproduced", "not_reproduced", "failed", "expired",
                               "cancelled")},
                           "candidates": sum(1 for row in scored if row["run_id"] in front_ids)},
                "queue": {"length": states.get("queued", 0) + states.get("held", 0),
                          "max": self.policy.manifest["limits"]["queue_max"] if self.policy.manifest else None,
                          "active": states.get("evaluating", 0),
                          "parallel": grant.parallel if grant else None},
                "grant": None if grant is None else {
                    "grant": grant.grant, "cpu_s_cap": grant.cpu_cap_s, "cpu_s_reserved": round(reserved, 6),
                    "cpu_s_charged": round(charged, 6),
                    "cpu_s_remaining": round(max(0.0, grant.cpu_cap_s - reserved - charged), 6)},
                "door": {"open": not closed, "codes": [item["code"] for item in closed]},
                "terms": {"accepted_versions": list(self.policy.manifest["terms"]["accepted_versions"])
                          if self.policy.manifest else []},
                "accounting_stops": [{key: stop[key] for key in ("scope", "short_id", "grant", "reason")}
                                     for stop in self.store.stops()],
                "scorer": self.scorer_state.snapshot(), "top": top}
        if nonce is not None:
            if not isinstance(nonce, str) or not NONCE.match(nonce):
                return 400, {"error": "token_required"}, {}
            if grant is not None and self.policy.manifest_id is not None:
                body["token"] = self.store.token_usage(principal=principal_for(nonce), grant=grant,
                                                       manifest_id=self.policy.manifest_id, now=now)
        return 200, body, {}
