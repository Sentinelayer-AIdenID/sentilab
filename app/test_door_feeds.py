"""Agent door read views and the scorer adapter (AGENT-DOOR.md section 4, Amendments 1 and 2): the results and events
cursors, the board on one frozen metric and one proxy scale, status bound to its principal, arrivals with no visitor
text, and HttpScorer's wire format, failure split and strict parse."""
import http.server
import json
import socket
import threading
import unittest

from app.door import testkit as tk
from app.door.legality import PinnedTapChecker
from app.door.policy import principal_for
from app.door.scorer import (EVALUATOR_BINARY_SHA256, METRIC, HttpScorer, ScorerError, parse_evaluation,
                             parse_replay)
from app.door.service import REFERENCES, front
from app.test_door_dispatch import moved


class FeedTests(tk.DoorCase, unittest.TestCase):
    http = True

    def get(self, path, headers=None):
        status, body, got = self.request("GET", path, headers=headers)
        self.assertEqual(got.get("cache-control"), "no-store")
        return status, body

    def queue(self, count, **edits):
        ids = []
        for index in range(count):
            status, reply = self.submit(self.body(moved(index), nonce_value=tk.nonce(10 + index), **edits))
            self.assertEqual(status, 202, reply)
            ids.append(reply["run_id"])
        return ids

    def test_results_cursor_returns_each_change_once_in_order(self):
        ids = self.queue(3)
        status, page = self.get("/api/open/v1/door/results?limit=2")
        self.assertEqual(status, 200)
        self.assertEqual([item["id"] for item in page["items"]], ids[:2])
        self.assertTrue(page["has_more"])
        status, rest = self.get(f"/api/open/v1/door/results?after={page['next_after']}")
        self.assertEqual([item["id"] for item in rest["items"]], ids[2:])
        self.assertFalse(rest["has_more"])
        cursor = rest["next_after"]
        self.assertEqual(self.get(f"/api/open/v1/door/results?after={cursor}")[1]["items"], [])
        self.drain()
        status, done = self.get(f"/api/open/v1/door/results?after={cursor}")
        self.assertEqual(sorted(item["id"] for item in done["items"]), sorted(ids))
        self.assertEqual({item["status"] for item in done["items"]}, {"reproduced"})
        seqs = [item["seq"] for item in done["items"]]
        self.assertEqual(seqs, sorted(seqs))
        self.assertTrue(all(seq > cursor for seq in seqs))
        for bad in ("-1", "1.5", "abc", "99999999999999999999", "%EF%BC%91"):
            self.assertEqual(self.get(f"/api/open/v1/door/results?after={bad}")[0], 400, bad)
        self.assertEqual(self.get("/api/open/v1/door/results?limit=21")[0], 400)

    def test_a_result_item_has_the_named_fields_and_no_generic_peak(self):
        run_id = self.queue(1)[0]
        status, page = self.get("/api/open/v1/door/results")
        item = page["items"][0]
        self.assertEqual((item["status"], item["result"], item["metric"]), ("queued", None, METRIC))
        self.assertEqual(item["position"], 1)
        self.assertEqual(item["label"], "declared_agent · " + item["short_id"])
        self.assertEqual(len(item["dies"]), 8)
        self.drain()
        item = self.get("/api/open/v1/door/results")[1]["items"][0]
        result = item["result"]
        self.assertEqual(item["id"], run_id)
        for name in ("max_chiplet_centre_cell_mean_C", "native_all_block_max_C", "active_layer_peak_C"):
            self.assertIsInstance(result[name], float)
        self.assertEqual(result["metric"], METRIC)
        self.assertEqual(result["metric_id"], "max_chiplet_centre_cell_mean_C")
        self.assertEqual(result["active_guard"]["limit_C"], 119.07)
        self.assertEqual(sorted(result["per_die_C"]), ["C0", "C1", "C2", "C3", "D0", "D1", "D2", "D3"])
        self.assertEqual(max(result["per_die_C"].values()), result["max_chiplet_centre_cell_mean_C"])
        self.assertIsNone(result["grid64"], "door-scorer returns no grid yet; the per-die values carry the map")
        self.assertEqual(result["label"], "simulated, not silicon; HotSpot 6.0, grid 64; "
                                          "max_chiplet_centre_cell_mean_C")
        self.assertEqual(result["temperature_label"], "unvalidated")
        for path in ("/api/open/v1/door/results", "/api/open/v1/door/board"):
            self.assertNotIn("peak_c", json.dumps(self.get(path)[1]))

    def test_a_grid_when_the_scorer_returns_one_is_served_rounded_for_display(self):
        self.scorer.with_grid = True
        self.queue(1)
        self.drain()
        result = self.get("/api/open/v1/door/results")[1]["items"][0]["result"]
        self.assertEqual((len(result["grid64"]), {len(row) for row in result["grid64"]}), (64, {64}))
        self.assertEqual(result["grid"]["orientation"],
                         "row 0 is the frame's top edge (max y); column 0 its left edge (min x)")

    def test_the_board_ranks_one_metric_keeps_the_references_apart_and_never_says_beat(self):
        self.queue(3)
        self.scorer.offset = -60.0
        self.drain()
        status, board = self.get("/api/open/v1/door/board")
        self.assertEqual(status, 200)
        self.assertEqual(board["metric"], METRIC)
        self.assertEqual(board["active_guard"], {"field": "active_layer_peak_C", "rule": "strictly below",
                                                 "limit_C": 119.07})
        self.assertEqual(board["beat"]["available"], False)
        raw, snapped = board["references"]
        self.assertEqual((raw["max_chiplet_centre_cell_mean_C"], raw["native_all_block_max_C"],
                          raw["active_layer_peak_C"], raw["wire_proxy_mm"]), (115.935, 115.93, 119.07, 9.38487))
        self.assertEqual((snapped["max_chiplet_centre_cell_mean_C"], snapped["wire_proxy_mm"]), (None, 9.5))
        self.assertEqual([point["peak_C"] for point in board["published"]], [115.94, 94.89])
        metrics = [entry["max_chiplet_centre_cell_mean_C"] for entry in board["top"]]
        self.assertEqual(metrics, sorted(metrics))
        self.assertEqual(board["counts"]["attempts"], 3)
        self.assertEqual(board["counts"]["reproduced"], 3)
        self.assertEqual(board["door"], {"open": True, "codes": []})
        self.assertNotIn("beat", json.dumps(board["top"]))
        self.assertGreaterEqual(board["counts"]["candidates"], 1)
        self.assertEqual(board["counts"]["candidates"], sum(entry["verdict"] == "candidate" for entry in board["top"]))

    def test_a_hot_layout_is_no_candidate_and_the_guard_is_strict(self):
        self.scorer.offset = 0.0                       # about 160 C: dominated by the raw reference
        self.queue(1)
        self.drain()
        entry = self.get("/api/open/v1/door/board")[1]["top"][0]
        self.assertIsNone(entry["verdict"])
        self.assertFalse(entry["active_guard_ok"])
        self.assertEqual(front([("a", 115.935, 9.38487), ("b", 115.935, 9.38487)]), {"a", "b"})
        self.assertEqual(front([("ref", 115.935, 9.38487), ("x", 116.0, 9.5)]), {"ref"})
        self.assertEqual(front([("ref", 115.935, 9.38487), ("x", 110.0, 9.5)]), {"ref", "x"})

    def test_an_active_peak_at_exactly_the_guard_is_not_ok(self):
        run_id = self.queue(1)[0]
        self.drain()
        import sqlite3
        with sqlite3.connect(self.store.path) as db:
            result = json.loads(db.execute("SELECT result FROM runs WHERE run_id = ?", (run_id,)).fetchone()[0])
            result["active_layer_peak_C"] = 119.07
            db.execute("UPDATE runs SET result = ?, active_c = ? WHERE run_id = ?",
                       (json.dumps(result), 119.07, run_id))
        status, item = self.get(f"/api/open/v1/door/status/{run_id}", {"x-door-nonce": tk.nonce(10)})
        self.assertFalse(item["result"]["active_guard"]["ok"])
        self.assertIsNone(item["verdict"])

    def test_status_is_bound_to_its_principal(self):
        run_id = self.queue(1)[0]
        status, item = self.get(f"/api/open/v1/door/status/{run_id}", {"x-door-nonce": tk.nonce(10)})
        self.assertEqual((status, item["id"], item["status"], item["position"]), (200, run_id, "queued", 1))
        self.assertEqual(item["token"]["cpu_s_reserved"], 10)
        self.assertEqual(item["token"]["cpu_s_remaining"], 20)
        self.assertEqual(self.get(f"/api/open/v1/door/status/{run_id}", {"x-door-nonce": tk.nonce(11)}),
                         (404, {"error": "run_not_found"}))
        self.assertEqual(self.get(f"/api/open/v1/door/status/{run_id}")[0], 400)
        self.assertEqual(self.get(f"/api/open/v1/door/status/{run_id}", {"x-door-nonce": "XYZ"})[0], 400)
        self.assertEqual(self.get("/api/open/v1/door/status/not-a-run", {"x-door-nonce": tk.nonce(10)})[0], 404)

    def test_events_carry_arrivals_attempts_and_state_changes_without_visitor_text(self):
        status, _reply, _ = self.request("POST", "/api/open/v1/door/arrival",
                                         json.dumps({"class": "declared_agent", "operator": "anthropic",
                                                     "purpose": "place-chiplets", "nonce": tk.NONCE}).encode())
        self.assertEqual(status, 204)
        status, reply, _ = self.request("POST", "/api/open/v1/door/arrival",
                                        json.dumps({"class": "declared_agent", "label": "Claude says hi"}).encode())
        self.assertEqual((status, reply["codes"]), (400, [{"code": "unknown_field", "path": ""}]))
        self.submit(self.body(tk.SNAPPED.replace("17.35.0", "17.35.1")))
        self.queue(1)
        status, page = self.get("/api/open/v1/door/events")
        kinds = [event["kind"] for event in page["events"]]
        self.assertEqual(kinds[:3], ["arrival", "attempt", "run"])
        arrival = page["events"][0]
        self.assertEqual({key: arrival[key] for key in ("class", "operator", "purpose", "short_id")},
                         {"class": "declared_agent", "operator": "anthropic", "purpose": "place-chiplets",
                          "short_id": principal_for(tk.NONCE)[13:17]})
        self.assertEqual(page["events"][1]["codes"], ["rotation_not_allowed"])
        self.assertNotIn("Claude says hi", json.dumps(page))
        status, later = self.get(f"/api/open/v1/door/events?after={page['events'][0]['seq']}&limit=1")
        self.assertEqual([event["seq"] for event in later["events"]], [page["events"][1]["seq"]])
        self.assertTrue(later["has_more"])


class FrozenNumbersTests(unittest.TestCase):
    def test_the_proxy_reproduces_both_references(self):
        policy = tk.policy()
        from app.door import intake

        self.assertEqual(policy.checker.wire_proxy_mm(intake.compact_dies(tk.SNAPPED)[0]), 9.5)
        raw = [(17.9249, 17.5496), (27.0751, 17.5496), (27.0751, 27.4497), (17.9249, 27.4497), (8.5751, 17.5496),
               (36.4249, 17.5496), (36.4249, 27.4497), (8.5751, 27.4497)]
        self.assertAlmostEqual(policy.checker.geometry.wirelength_mm(tuple(raw)), REFERENCES[0]["wire_proxy_mm"],
                               places=5)

    def test_the_selector_is_gate_zeros_grid_center_mapping(self):
        from sundai_hotspot.slab049 import block_extent, center_cells

        policy = tk.policy()
        from app.door import intake

        dies = intake.compact_dies(tk.SNAPPED)[0]
        grid = [[float(row * 64 + col) for col in range(64)] for row in range(64)]
        cells = policy.checker.centre_cells(dies)
        self.assertTrue(all(len(per_die) in (1, 2, 4) for per_die in cells))
        unit = {"name": "Chiplet_0", "leftx": (18000 - 4125) / 1e6, "bottomy": (17500 - 4500) / 1e6,
                "width": 8250 / 1e6, "height": 9000 / 1e6}
        self.assertEqual(cells[0], center_cells(block_extent(unit, 0.045, 0.045, 64, 64)))
        expected = max(sum(grid[c["row"]][c["col"]] * c["weight"] for c in per_die) for per_die in cells)
        self.assertEqual(policy.checker.selector(dies, grid), expected)
        rows = [cell["row"] for cell in cells[0]]
        self.assertTrue(all(36 <= row <= 40 for row in rows), "row 0 is the top edge: y 17.5 mm sits low")


class Handler(http.server.BaseHTTPRequestHandler):
    """A stand-in for door-scorer's HTTP surface (sentilab PR #79, research/agent-door/scorer/service.py at 78bc0d18):
    the same paths, bearer check, request shape and answer shapes, with programmable answers."""

    def log_message(self, *_args):
        pass

    def do_GET(self):
        self.server.seen.append(("GET", self.path, self.headers.get("authorization")))
        self._send(*self.server.health)

    def do_POST(self):
        length = int(self.headers.get("content-length", "0"))
        body = json.loads(self.rfile.read(length))
        self.server.seen.append(("POST", self.path, self.headers.get("authorization"), body))
        if self.server.stall:
            self.server.stall.wait(5)
        if self.headers.get("authorization") != "Bearer " + TOKEN:
            self._send(401, {"error": "unauthorized"})
        elif set(body) != {"run_id", "token_ref", "proposal"}:
            self._send(422, {"state": "rejected", "codes": [{"code": "schema_invalid", "path": "",
                                                             "keyword": "required"}]})
        else:
            self._send(*self.server.answers[self.path.rsplit("/", 1)[1]])

    def _send(self, status, body):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


TOKEN = "scorer-bearer-for-loopback-test"
FAKE_BINARY = EVALUATOR_BINARY_SHA256


def receipt(cpu_s: float) -> dict:
    return {"grant_id": "slab-demo-20261101", "image_digest": "sha256:" + "0" * 64, "binary_sha256": FAKE_BINARY,
            "input_sha256": {}, "output_sha256": {}, "output_map_sha256": None, "cpu_s": cpu_s, "wall_s": 4.0}


def evaluation(dies) -> dict:
    """An `evaluated` answer as door-scorer builds it: thermal.METRIC, read_score's fields, wire and receipt."""
    checker = tk.policy().checker
    means = checker.centre_means(dies, tk.grid_for(dies, -60.0))
    per_die = dict(zip(("C0", "C1", "C2", "C3", "D0", "D1", "D2", "D3"), means))
    centre, active, native = max(means), max(means) + 3.0, max(means) - 0.01
    return {"run_id": "open-00000000-" + "0" * 32, "receipt": receipt(1.25), "state": "evaluated",
            "metric_id": "max_chiplet_centre_cell_mean_C",
            "metric_definition": "Maximum over Chiplet_0..7 of the mean of its 1, 2 or 4 central HotSpot 6 grid-64 "
                                 "cells.", "temperature_unit": "degC",
            "metric_precision": {"grid_resolution_K": 0.01, "averaging_adds_precision": False},
            "references": {"raw": {"layout_id": "micro150-tap25d-fig5a-raw", "layout_sha256": "1" * 64,
                                   "metric_id": "max_chiplet_centre_cell_mean_C", "max_chiplet_centre_mean_c": 115.935,
                                   "native_all_block_max_c": 115.93, "active_grid_max_c": 119.07,
                                   "wire_proxy_mm": 9.38487},
                           "snapped": {"metric_id": "max_chiplet_centre_cell_mean_C", "max_chiplet_centre_mean_c": None,
                                       "wire_proxy_mm": 9.5}},
            "label": "simulated, not silicon", "native_all_block_max_c": native, "max_chiplet_centre_mean_c": centre,
            "active_grid_max_c": active, "native_all_block_max_C": native, "active_layer_peak_C": active,
            "peak_c": centre, "per_die_c": per_die, "hotspot_ok": active < 119.07,
            "wire_proxy_mm": checker.geometry.wirelength_mm(checker._centres(dies))}


def replay(original: dict, state="reproduced", code=None) -> dict:
    answer = {**original, "receipt": receipt(1.5), "state": state, "receipts": [original["receipt"], receipt(1.5)],
              "codes": [] if code is None else [{"code": code}]}
    return answer


class HttpScorerTests(unittest.TestCase):
    def setUp(self):
        from app.door import intake

        self.dies = intake.compact_dies(tk.SNAPPED)[0]
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.seen, self.server.stall = [], None
        good = evaluation(self.dies)
        self.server.health = (200, {"ok": True, "binary_sha256": FAKE_BINARY, "grant_id": "slab-demo-20261101",
                                    "image_digest": "sha256:" + "0" * 64, "budget_left_cpu_s": 3600})
        self.server.answers = {"score": (200, good), "replay": (200, replay(good))}
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/scorer"

    def tearDown(self):
        if self.server.stall:
            self.server.stall.set()
        self.server.shutdown()
        self.server.server_close()

    def scorer(self, **kwargs):
        return HttpScorer(self.url, TOKEN, **kwargs)

    def request(self):
        return {"run_id": "open-00000000-" + "0" * 32, "token_ref": "2" * 64,
                "proposal": {"schema": "sentilab-open-proposal/1", "dies": self.dies}}

    def test_a_score_and_its_replay_become_one_score_with_the_named_statistics(self):
        score = self.scorer().score(self.request())
        good = self.server.answers["score"][1]
        self.assertEqual((score.metric_id, score.max_chiplet_centre_cell_mean_C, score.active_layer_peak_C,
                          score.native_all_block_max_C),
                         ("max_chiplet_centre_cell_mean_C", good["max_chiplet_centre_mean_c"],
                          good["active_layer_peak_C"], good["native_all_block_max_C"]))
        self.assertEqual((score.replay_fresh_process, score.replay_match, score.replay_code), (True, True, None))
        self.assertEqual(score.cpu_s, 2.75, "the score's and the replay's measured CPU")
        self.assertEqual(score.per_die_C, good["per_die_c"])
        self.assertIsNone(score.grid64)
        posts = [entry for entry in self.server.seen if entry[0] == "POST"]
        self.assertEqual([entry[1] for entry in posts], ["/scorer/v1/score", "/scorer/v1/replay"])
        self.assertEqual({entry[2] for entry in posts}, {"Bearer " + TOKEN})
        self.assertEqual(posts[0][3], self.request())
        self.assertEqual(posts[1][3], self.request(), "the replay repeats the exact body")

    def test_health_requires_the_pinned_binary_and_the_grant(self):
        self.assertTrue(self.scorer(grant_id="slab-demo-20261101").health())
        self.assertEqual(self.server.seen[-1][:3], ("GET", "/scorer/v1/health", "Bearer " + TOKEN))
        self.assertFalse(self.scorer(grant_id="another-grant").health())
        self.assertFalse(self.scorer(binary_sha256="0" * 64).health())
        self.server.health = (401, {"error": "unauthorized"})
        self.assertFalse(self.scorer().health())

    def test_replay_outcomes(self):
        good = self.server.answers["score"][1]
        self.server.answers["replay"] = (200, replay(good, "not_reproduced", "reproduction_mismatch"))
        score = self.scorer().score(self.request())
        self.assertEqual((score.replay_match, score.replay_code), (False, "reproduction_mismatch"))
        self.server.answers["replay"] = (500, {"error": "oracle_error"})
        score = self.scorer().score(self.request())
        self.assertEqual((score.replay_fresh_process, score.replay_code, score.cpu_s),
                         (False, "reproduction_failed", 11.25), "an ambiguous replay is charged its reservation")
        self.server.answers["replay"] = (429, {"state": "rejected", "error": "busy", "codes": [{"code": "rate_limited",
                                                                                             "retry_after": 1}]})
        score = self.scorer().score(self.request())
        self.assertEqual((score.replay_code, score.cpu_s), ("reproduction_failed", 1.25), "a refused replay costs 0")

    def test_failures_split_never_began_from_ambiguous(self):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            closed_port = probe.getsockname()[1]
        with self.assertRaises(ScorerError) as caught:
            HttpScorer(f"http://127.0.0.1:{closed_port}", TOKEN).score(self.request())
        self.assertEqual((caught.exception.reason, caught.exception.began), ("scorer_down", False))
        self.assertFalse(HttpScorer(f"http://127.0.0.1:{closed_port}", TOKEN).health())
        for status, code in ((401, None), (403, "budget_exhausted"), (409, "idempotency_conflict"),
                             (422, "not_open_yet"), (429, "rate_limited")):
            self.server.answers["score"] = (status, {"state": "rejected", "codes": [{"code": code}] if code else []})
            with self.assertRaises(ScorerError) as caught:
                self.scorer().score(self.request())
            self.assertEqual((caught.exception.reason, caught.exception.began), ("scorer_refused", False), status)
        for code, reason in (("timeout", "scorer_timeout"), ("oracle_error", "scorer_error"),
                             ("interrupted", "interrupted")):
            self.server.answers["score"] = (200, {"run_id": "x", "state": "failed", "codes": [{"code": code}],
                                                  "receipt": receipt(10.0)})
            with self.assertRaises(ScorerError) as caught:
                self.scorer().score(self.request())
            self.assertEqual((caught.exception.reason, caught.exception.began, caught.exception.cpu_s),
                             (reason, True, 10.0), code)
        self.server.stall = threading.Event()
        with self.assertRaises(ScorerError) as caught:
            self.scorer(timeout_s=0.3).score(self.request())
        self.assertEqual((caught.exception.reason, caught.exception.began), ("scorer_timeout", True))
        self.server.stall.set()
        self.server.stall = None
        for answer in ((500, {"error": "oracle_error"}), (200, b"{not json"), (200, b'{"state": NaN}')):
            self.server.answers["score"] = answer
            with self.assertRaises(ScorerError) as caught:
                self.scorer().score(self.request())
            self.assertEqual((caught.exception.reason, caught.exception.began), ("scorer_error", True), answer)

    def test_the_evaluation_parse_is_strict(self):
        good = self.server.answers["score"][1]
        self.assertEqual(parse_evaluation(good)["metric"], good["max_chiplet_centre_mean_c"])
        dies = dict(good["per_die_c"])
        dies.pop("D3")
        broken = ({"metric_id": "peak_c"}, {"metric_precision": {"grid_resolution_K": 0.001}},
                  {"references": {"raw": {"max_chiplet_centre_mean_c": 115.93}}},
                  {"receipt": {**receipt(1.0), "binary_sha256": "0" * 64}}, {"receipt": {**receipt(1.0), "cpu_s": -1}},
                  {"receipt": {**receipt(1.0), "pad": "y" * 20000}}, {"per_die_c": dies},
                  {"peak_c": good["peak_c"] + 1}, {"active_grid_max_c": good["active_layer_peak_C"] + 1},
                  {"native_all_block_max_c": float("inf")}, {"hotspot_ok": not good["hotspot_ok"]},
                  {"grid64": [[50.0] * 64] * 63}, {"wire_proxy_mm": -1}, {"state": "failed"})
        for edit in broken:
            with self.assertRaises(ValueError, msg=str(list(edit))[:60]):
                parse_evaluation({**good, **edit})
        with self.assertRaises(ValueError):
            parse_replay({**replay(good), "codes": [{"code": "reproduction_mismatch"}]})
        with self.assertRaises(ValueError):
            parse_replay({**replay(good, "not_reproduced"), "codes": []})
        self.assertEqual(parse_replay(replay(good))[:2], (True, None))

    def test_only_https_or_loopback_and_a_token(self):
        for url, token in (("http://scorer.example", "t"), ("ftp://127.0.0.1", "t"), ("https://x.example", ""),
                           ("https://x.example", "two words")):
            with self.assertRaises(ValueError):
                HttpScorer(url, token)
        HttpScorer("https://scorer.example", "t")


class CheckerPinTests(unittest.TestCase):
    def test_the_pinned_checker_reports_whole_micrometres_rounded_up(self):
        from app.door.legality import amount_um

        self.assertEqual((amount_um(0.0103), amount_um(0.00999999999), amount_um(1e-12)), (11, 10, 1))
        with self.assertRaises(ValueError):
            PinnedTapChecker(tk.door_manifest(**{"fixture.id": "ascend910-45mm"}))


if __name__ == "__main__":
    unittest.main()
