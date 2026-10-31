// Builds and checks the v0.6.2 paging vectors (C1 to C17).
//   node run-paging-vectors.mjs           regenerate every vector from the code and compare with vectors-paging.json
//   node run-paging-vectors.mjs --write   rewrite vectors-paging.json from the code, then run the same checks
// Exit 0 only if every check passes. The envelopes come from the v0.5 vectors (V1), read as data.
import { createHash, createPrivateKey, createPublicKey } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { canonical } from "../contract-0.2/resultcheck.mjs";
import { makeChain } from "../view-envelope-v0.5/view-envelope.mjs";
import { cursorHash, initialState, joinRows, liveLabel, logRowsFromFile, request, rowText, servePage, splitRows, step, track, verifyBytes, verifyReplayBytes, verifyRows } from "./paging.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const FILE = join(here, "vectors-paging.json");
const CONTRACT_SHA256 = "a5a04e9c7207ced732889dd4cc06915c15c20a445f7f03e13e4ac2f05edce040";
const same = (a, b) => canonical(a) === canonical(b);
const encoder = new TextEncoder();
// Lenient decoding, used only by the harness (to read seqs for the legacy server, and to show what decoding would do).
const lenient = (bytes) => new TextDecoder("utf-8", { fatal: false, ignoreBOM: true }).decode(bytes);
const BASE_MS = Date.UTC(2026, 9, 31, 12, 0, 0);
const T = (seconds) => new Date(BASE_MS + seconds * 1000).toISOString();

// Written separately from paging.mjs on purpose: SHA-256 over each raw row followed by one LF.
const rawHash = (rows) => createHash("sha256").update(Buffer.concat(rows.flatMap((row) => [Buffer.from(row), Buffer.from([0x0a])]))).digest("hex");
const sha256Bytes = (bytes) => createHash("sha256").update(bytes).digest("hex");

// ---- Test keys, derived at run time as in v0.5 (no key material is stored). ----
const PKCS8_ED25519_HEADER = Buffer.from("302e020100300506032b657004220420", "hex");
function testKey(name) {
  const seed = createHash("sha256").update(`sentilab-view-test-key:${name}`, "utf8").digest();
  const privateKey = createPrivateKey({ key: Buffer.concat([PKCS8_ED25519_HEADER, seed]), format: "der", type: "pkcs8" });
  return { privateKey, publicKey: createPublicKey(privateKey) };
}
const core = testKey("core");
const pinOf = (publicKey) => createHash("sha256").update(publicKey.export({ type: "spki", format: "der" }).subarray(12)).digest("hex");
const OPTIONS = { runId: "run-v1", pins: [{ key_id: "core", key_sha256: pinOf(core.publicKey) }], keys: { core: core.publicKey } };

// ---- Rows. Envelope rows are the V1 run from the v0.5 vectors; the rest are built here. ----
const v05 = JSON.parse(readFileSync(join(here, "../view-envelope-v0.5/vectors-view.json"), "utf8"));
const v1 = v05.chains.find((chain) => chain.name.startsWith("V1 "));
const two = (n) => String(n).padStart(2, "0");
function rowTable() {
  const lines = v1.envelopes.map((env) => JSON.stringify(env));
  const table = Object.fromEntries(lines.map((line, i) => [`v1-${two(i + 1)}`, { text: line }]));
  // A validly signed, different envelope at an old seq: the same V1 chain with that entry's ts changed.
  const fork = (seq, ts) => {
    const entries = v1.input.entries.map((entry) => (entry.event.seq === seq ? { ...entry, ts } : entry));
    return JSON.stringify(makeChain(v1.input.run, entries, v1.input.values, { key_id: "core", privateKey: core.privateKey }).find((env) => env.event.seq === seq));
  };
  table["v1-03-fork"] = { text: fork(3, T(3.5)) };
  table["v1-06-fork"] = { text: fork(6, T(6.5)) };
  const tampered = lines[9].replace('"ts":"2026-10-31T12:00:10.000Z"', '"ts":"2026-10-31T12:00:10.001Z"');
  if (tampered === lines[9]) throw new Error("tamper didn't apply");
  table["v1-10-tampered"] = { text: tampered };
  table["junk-text"] = { text: "this is not json" };
  table["junk-utf8"] = { base64: Buffer.from([...encoder.encode('{"note":"'), 0xff, 0xfe, ...encoder.encode('"}')]).toString("base64") };
  // The seq 1 envelope with a UTF-8 BOM in front: a default browser TextDecoder would drop the BOM, node's wouldn't.
  table["bom-v1-01"] = { base64: Buffer.concat([Buffer.from([0xef, 0xbb, 0xbf]), Buffer.from(lines[0])]).toString("base64") };
  table.filler = { text: "{}" };
  table["x-65535"] = { fill: "x", bytes: 65_535 };
  table["x-65536"] = { fill: "x", bytes: 65_536 };
  table["x-4194304"] = { fill: "x", bytes: 4_194_304 };
  // C11: a 44-envelope run-v1 chain (a lab proposes K11, then the core creates sources S2..S44), and a validly
  // signed, different seq 10 from the same chain with that entry's ts changed.
  const [labActor, coreActor] = [v1.input.entries[0].actor, v1.input.entries[1].actor];
  const c11Entries = (count) => Array.from({ length: count }, (_, i) => {
    const seq = i + 1;
    const event = seq === 1
      ? { event_id: "c11-e01", seq, type: "node.create", actor_role: "lab", body: { id: "K11", kind: "candidate" } }
      : { event_id: `c11-e${two(seq)}`, seq, type: "node.create", actor_role: "core", body: { id: `S${seq}`, kind: "source" } };
    return { event, ts: T(seq), actor: seq === 1 ? labActor : coreActor };
  });
  const c11 = c11Entries(44);
  const signer = { key_id: "core", privateKey: core.privateKey };
  makeChain(v1.input.run, c11, {}, signer).forEach((env, i) => { table[`c11-${two(i + 1)}`] = { text: JSON.stringify(env) }; });
  table["c11-10-fork"] = { text: JSON.stringify(makeChain(v1.input.run, c11.map((e) => (e.event.seq === 10 ? { ...e, ts: T(10.5) } : e)), {}, signer)[9]) };
  // C15: the same chain carried on to seq 46. Seq 45 keeps its content but its signature's last hex digit is changed
  // (a bad signature; hash and prev_hash still match). Seq 46 on its own stands for a row after a gap.
  const c15 = makeChain(v1.input.run, c11Entries(46), {}, signer);
  if (JSON.stringify(c15[43]) !== table["c11-44"].text) throw new Error("the C15 chain should extend the C11 chain");
  const badSig = structuredClone(c15[44]);
  badSig.sig.value = badSig.sig.value.slice(0, -1) + (badSig.sig.value.endsWith("0") ? "1" : "0");
  table["c11-45-badsig"] = { text: JSON.stringify(badSig) };
  table["c11-46"] = { text: JSON.stringify(c15[45]) };
  return table;
}
const ROWS = rowTable();
// C16: a 273-envelope run-v1 chain (a lab proposes K16, then the core creates sources U2..U273), built by rule.
const CHAINS = {
  c16: { rule: "run-v1, signed by core: seq 1 is a lab proposing K16 (event_id c16-e001); seq 2 to 273 are the core creating source U<seq> (event_id c16-e<seq, 3 digits>); ts is 12:00:00 plus seq seconds; actors as in V1", count: 273 },
};
const CHAIN_ROWS = (() => {
  const [labActor, coreActor] = [v1.input.entries[0].actor, v1.input.entries[1].actor];
  const entries = Array.from({ length: 273 }, (_, i) => {
    const seq = i + 1;
    const event = seq === 1
      ? { event_id: "c16-e001", seq, type: "node.create", actor_role: "lab", body: { id: "K16", kind: "candidate" } }
      : { event_id: `c16-e${String(seq).padStart(3, "0")}`, seq, type: "node.create", actor_role: "core", body: { id: `U${seq}`, kind: "source" } };
    return { event, ts: T(seq), actor: seq === 1 ? labActor : coreActor };
  });
  return { c16: makeChain(v1.input.run, entries, {}, { key_id: "core", privateKey: core.privateKey }).map((env) => encoder.encode(JSON.stringify(env))) };
})();
const bytesCache = new Map();
const bytesOf = (rowId) => {
  const chainRow = /^(\w+):(\d+)$/.exec(rowId);
  if (chainRow) return CHAIN_ROWS[chainRow[1]][Number(chainRow[2]) - 1];
  if (!bytesCache.has(rowId)) {
    const spec = ROWS[rowId];
    if (!spec) throw new Error(`unknown row ${rowId}`);
    bytesCache.set(rowId, spec.text !== undefined ? encoder.encode(spec.text) : spec.base64 !== undefined ? new Uint8Array(Buffer.from(spec.base64, "base64")) : new Uint8Array(spec.bytes).fill(spec.fill.charCodeAt(0)));
  }
  return bytesCache.get(rowId);
};
// A log or body is a list of row ids; ["id", n] stands for n copies.
// { chain, from, to } stands for that chain's rows, seq from..to.
const expand = (list) => list.flatMap((entry) => (Array.isArray(entry) ? Array(entry[1]).fill(entry[0])
  : typeof entry === "object" ? Array.from({ length: entry.to - entry.from + 1 }, (_, i) => `${entry.chain}:${entry.from + i}`) : [entry]));
const runs = (ids) => {
  const out = [];
  for (const rowId of ids) {
    const last = out.at(-1);
    if (Array.isArray(last) && last[0] === rowId) last[1] += 1;
    else if (last === rowId) out[out.length - 1] = [rowId, 2];
    else out.push(rowId);
  }
  return out;
};
const V1_IDS = Array.from({ length: 11 }, (_, i) => `v1-${two(i + 1)}`);
const LOGS = {
  empty: [],
  v1: V1_IDS,
  "v1-first5": V1_IDS.slice(0, 5),
  "v1-first8": V1_IDS.slice(0, 8),
  "v1+fork": [...V1_IDS, "v1-03-fork"],
  c4: ["v1-01", "v1-02", "v1-03", "v1-03", "junk-text", "v1-04", "v1-05", "v1-06", "v1-07", "v1-08", "junk-utf8", "v1-09", "v1-10", "v1-11"],
  "c8-same": V1_IDS.map((rowId, i) => (i === 5 ? "v1-06-fork" : rowId)),
  "c8-longer": [...V1_IDS.map((rowId, i) => (i === 5 ? "v1-06-fork" : rowId)), "v1-03-fork", "junk-text"],
  "fillers-256": [["filler", 256]],
  "v1-first8+huge": [...V1_IDS.slice(0, 8), "x-4194304"],
  exact65: [["x-65535", 65]],
  c11: Array.from({ length: 44 }, (_, i) => `c11-${two(i + 1)}`),
  "c11+fork": [...Array.from({ length: 44 }, (_, i) => `c11-${two(i + 1)}`), "c11-10-fork"],
  "c11-first43": Array.from({ length: 43 }, (_, i) => `c11-${two(i + 1)}`),
  "v1+junk": [...V1_IDS, "junk-text"],
  "c16-backlog": [{ chain: "c16", from: 1, to: 272 }],
  "c16-plus1": [{ chain: "c16", from: 1, to: 273 }],
  "c15-badsig": [...Array.from({ length: 44 }, (_, i) => `c11-${two(i + 1)}`), "c11-45-badsig"],
  "c15-malformed": [...Array.from({ length: 44 }, (_, i) => `c11-${two(i + 1)}`), "junk-text"],
  "c15-gap": [...Array.from({ length: 44 }, (_, i) => `c11-${two(i + 1)}`), "c11-46"],
  c10: ["bom-v1-01", "v1-01", "v1-02", "v1-03", "v1-04", "v1-05", "v1-06", "junk-utf8", "v1-07", "v1-08", "v1-09", "v1-10", "v1-11"],
};

// ---- The harness server. A poll's `server` says how it answers:
//   { log }: the reference servePage() over that log;  headers: overrides (null removes);  tamper: { index, row }
//   replaces that log row in the body only;  { page: { log, rows } }: exactly those rows after the log, with
//   consistent headers and no limit;  { status, legacy }: that status for cursor requests, and for a request with
//   `after` a legacy 200 page of the log's rows with seq > after and no paging headers;  { network_error }: no response. ----
// Log files for C14: complete rows, each with its LF, then an optional tail that has no LF yet.
const FILES = {
  "c14v-tail": { rows: V1_IDS.slice(0, 5), tail: "v1-06" },
  "c14v-done": { rows: V1_IDS.slice(0, 6), tail: null },
};
const fileBytesOf = (spec) => Buffer.concat([joinRows(spec.rows.map(bytesOf)), spec.tail ? bytesOf(spec.tail) : new Uint8Array(0)]);
function legacyRows(logName, after) {
  return expand(LOGS[logName]).filter((rowId) => {
    try { return JSON.parse(lenient(bytesOf(rowId))).event.seq > after; } catch { return false; }
  });
}
function serve(server, req) {
  if (server.network_error) return { response: null, bodyIds: [] };
  if (server.status !== undefined && server.status !== 200) {
    if (server.legacy && req.after !== undefined) {
      const ids = legacyRows(server.legacy, req.after);
      return { response: { status: 200, headers: {}, bodyBytes: joinRows(ids.map(bytesOf)) }, bodyIds: ids };
    }
    return { response: { status: server.status, headers: {}, bodyBytes: new Uint8Array(0) }, bodyIds: [] };
  }
  if (server.page) {
    const before = expand(LOGS[server.page.log]);
    const rows = expand(server.page.rows);
    const next = req.cursor + rows.length;
    const headers = { "x-next-cursor": String(next), "x-has-more": "false", "x-cursor-hash": rawHash([...before, ...rows].slice(0, next).map(bytesOf)) };
    return { response: { status: 200, headers, bodyBytes: joinRows(rows.map(bytesOf)) }, bodyIds: rows };
  }
  if (server.file) {
    const spec = FILES[server.file];
    const response = servePage(logRowsFromFile(new Uint8Array(fileBytesOf(spec))), req);
    const ids = [...spec.rows, ...(spec.tail ? [spec.tail] : [])];
    return { response, bodyIds: response.status === 200 ? ids.slice(req.cursor, Number(response.headers["x-next-cursor"])) : [] };
  }
  const ids = expand(LOGS[server.log]);
  const response = servePage(ids.map(bytesOf), req);
  let bodyIds = response.status === 200 ? ids.slice(req.cursor, Number(response.headers["x-next-cursor"])) : [];
  for (const [name, value] of Object.entries(server.headers ?? {})) {
    if (value === null) delete response.headers[name];
    else response.headers[name] = value;
  }
  if (server.tamper) {
    const at = server.tamper.index - req.cursor;
    if (at >= 0 && at < bodyIds.length) {
      bodyIds = bodyIds.with(at, server.tamper.row);
      response.bodyBytes = joinRows(bodyIds.map(bytesOf));
    }
  }
  if (server.strip_final_lf && response.bodyBytes.length > 0) response.bodyBytes = response.bodyBytes.subarray(0, response.bodyBytes.length - 1);
  return { response, bodyIds };
}

// ---- The client loop: each poll fetches while x-has-more is true (at most 16 pages a poll). In a terminal state
// request() is null and the poll sends nothing. ----
const summary = (state) => ({ cursor: state.cursor, rows: state.rows.length, cursor_hash: state.cursor_hash, has_more: state.has_more, last_ok_ms: state.last_ok_ms, failure: state.failure, degraded: state.degraded, caught_up: state.caught_up, high_k: state.high_k, last_progress_ms: state.last_progress_ms });
function runScenario(spec) {
  let state = initialState("run-v1", { limit: spec.limit });
  const trace = [];
  const transitions = [];
  for (const poll of spec.polls) {
    const nowMs = BASE_MS + poll.t_s * 1000;
    const runStatus = poll.run_status ?? "running";
    const fetches = [];
    for (let n = 0; n < 16; n += 1) {
      const req = request(state);
      if (req === null) break;
      const { response, bodyIds } = serve(poll.server, req);
      const before = state;
      const result = step(state, response, nowMs);
      transitions.push({ before, after: result.state, req, outcome: result.outcome, newRows: result.newRows });
      state = result.state;
      // Re-verify after every page; a valid page also updates progress (catch-up pages only raise the high).
      const view = verifyRows(state, OPTIONS);
      if (result.outcome === "ok") state = track(state, view.K, nowMs);
      fetches.push({ request: req, response: response && { status: response.status, headers: response.headers, body_bytes: response.bodyBytes.length, body_rows: runs(bodyIds) }, outcome: result.outcome, new_rows: result.newRows.length, catching_up: state.catching_up, label: liveLabel(state, nowMs, view.K, view.frozen, runStatus) });
      if (result.outcome !== "ok" || !state.has_more) break;
    }
    const { verification, K } = verifyRows(state, OPTIONS);
    // Rows by status, and rejected rows counted by their reasons (joined with +).
    const row_counts = {};
    const rejected = {};
    for (const row of verification.rows) {
      row_counts[row.status] = (row_counts[row.status] ?? 0) + 1;
      if (["malformed", "oversize"].includes(row.status)) rejected[row.reasons.join("+")] = (rejected[row.reasons.join("+")] ?? 0) + 1;
    }
    trace.push({ t_s: poll.t_s, run_status: runStatus, fetches, after: summary(state), K, board: verification.label, label: liveLabel(state, nowMs, K, verification.frozen, runStatus), row_counts, rejected });
  }
  return { trace, transitions, state };
}

// ---- Scenarios C1 to C6, C8 and C9. expect.polls lists, by second, the last fetch's outcome and the state after
// the poll; anything listed must match. ----
const live = (s) => `LIVE · progress ${s} s ago`;
const frozen = (k) => `chain broken after seq ${k}; board frozen at seq ${k}`;
const range = (from, to) => Array.from({ length: to - from + 1 }, (_, i) => from + i);
function scenarioSpecs() {
  // A poll may carry run_status: what GET /api/view/runs says then (running when absent).
  const polls = (list) => list.map(([t_s, server, run_status]) => (run_status ? { t_s, server, run_status } : { t_s, server }));
  const v1 = { log: "v1" };
  return [
    {
      name: "C1 late conflict: after the client has paged seq 1..11 (limit 4), a validly signed, different seq 3 is appended; the next poll freezes the board before seq 3",
      limit: 4,
      polls: polls([[0, v1], [1, v1], [2, { log: "v1+fork" }], [3, { log: "v1+fork" }]]),
      expect: {
        polls: {
          0: { outcome: "ok", fetches: 3, cursor: 11, rows: 11, K: 11, board: null, label: "STALE" },
          1: { outcome: "ok", fetches: 1, cursor: 11, rows: 11, K: 11, label: "STALE" },
          2: { outcome: "ok", cursor: 12, rows: 12, K: 2, board: frozen(2), label: "STALE · chain broken" },
          3: { outcome: "ok", cursor: 12, rows: 12, K: 2, board: frozen(2), label: "STALE · chain broken" },
        },
        legacy_would_miss: { log: "v1+fork", after: 11 },
      },
    },
    {
      name: "C2 truncated log: the log shrinks to 5 rows, so cursor 11 is beyond its end; 409, stream replaced, the prefix is kept, no reset, no more requests",
      limit: 256,
      polls: polls([[0, v1], [1, { log: "v1-first5" }], [2, v1]]),
      expect: {
        polls: {
          0: { outcome: "ok", cursor: 11, rows: 11, K: 11, label: "STALE" },
          1: { outcome: "stream_replaced", cursor: 11, rows: 11, K: 11, degraded: "stream_replaced", label: "STALE · stream replaced" },
          2: { outcome: "no_request", fetches: 0, cursor: 11, rows: 11, K: 11, degraded: "stream_replaced", label: "STALE · stream replaced" },
        },
      },
    },
    {
      name: "C3 bad x-next-cursor: missing, not an integer (eleven, 11.0), backwards (7), and not n plus the rows (12); each is a paging error and the prefix is kept",
      limit: 256,
      polls: polls([
        [0, { log: "v1-first8" }],
        [1, { log: "v1", headers: { "x-next-cursor": null } }],
        [2, { log: "v1", headers: { "x-next-cursor": "eleven" } }],
        [3, { log: "v1", headers: { "x-next-cursor": "11.0" } }],
        [4, { log: "v1", headers: { "x-next-cursor": "7" } }],
        [5, { log: "v1", headers: { "x-next-cursor": "12" } }],
        [6, v1],
      ]),
      expect: {
        polls: {
          0: { outcome: "ok", cursor: 8, rows: 8, K: 8, label: "STALE" },
          ...Object.fromEntries(range(1, 5).map((t) => [t, { outcome: "paging_error", cursor: 8, rows: 8, K: 8, label: "STALE · paging error" }])),
          6: { outcome: "ok", cursor: 11, rows: 11, K: 11, label: live(0) },
        },
      },
    },
    {
      name: "C4 rows, not envelopes: a byte-identical duplicate, a non-JSON row and a row with invalid UTF-8 each advance the cursor by one; the result equals verifying the same rows as one file",
      limit: 5,
      polls: polls([[0, { log: "c4" }]]),
      expect: {
        // Two refused rows follow the prefix, so the board is frozen: STALE · chain broken under v0.6.1 (v0.6 showed LIVE).
        polls: { 0: { outcome: "ok", fetches: 3, cursor: 14, rows: 14, K: 11, board: frozen(11), label: "STALE · chain broken" } },
        equals_one_file: true,
      },
    },
    {
      name: "C5 transport: a page of 257 lines, a page of 4 MiB + 1 byte, no response, and a 503; each poll fails (transport) and the prefix is unchanged",
      limit: 256,
      polls: polls([
        [0, { log: "v1-first8" }],
        [1, { page: { log: "v1-first8", rows: [["filler", 257]] } }],
        [2, { page: { log: "v1-first8", rows: [["x-65535", 63], "x-65536"] } }],
        [3, { network_error: true }],
        [4, { status: 503 }],
        [5, v1],
      ]),
      expect: {
        polls: {
          0: { outcome: "ok", cursor: 8, rows: 8, K: 8, label: "STALE" },
          ...Object.fromEntries(range(1, 4).map((t) => [t, { outcome: "transport", cursor: 8, rows: 8, K: 8, label: "STALE · transport" }])),
          5: { outcome: "ok", cursor: 11, rows: 11, K: 11, label: live(0) },
        },
      },
    },
    {
      name: "C5b caps are inclusive: exactly 256 lines, then exactly 4 MiB, are valid pages",
      limit: 256,
      polls: polls([[0, { page: { log: "empty", rows: [["filler", 256]] } }], [1, { page: { log: "fillers-256", rows: [["x-65535", 64]] } }]]),
      expect: { polls: { 0: { outcome: "ok", cursor: 256, rows: 256, K: 0 }, 1: { outcome: "ok", cursor: 320, rows: 320, K: 0 } } },
    },
    {
      name: "C6a no cursor support from the start (404; the server would answer after=<seq>): STALE · paging unsupported for 70 s, never LIVE, no seq paging",
      limit: 256,
      polls: polls(range(0, 70).map((t) => [t, { status: 404, legacy: "v1" }])),
      expect: {
        polls: {
          0: { outcome: "paging_unsupported", cursor: 0, rows: 0, K: 0, degraded: "paging_unsupported", label: "STALE · paging unsupported" },
          ...Object.fromEntries([1, 35, 70].map((t) => [t, { outcome: "no_request", fetches: 0, cursor: 0, rows: 0, K: 0, degraded: "paging_unsupported", label: "STALE · paging unsupported" }])),
        },
        never_live_from_s: 0,
      },
    },
    {
      name: "C6b cursor support lost (501) after seq 1..8 were paged: the prefix is kept, STALE · paging unsupported, never LIVE again",
      limit: 256,
      polls: polls([[0, { log: "v1-first8" }], ...range(1, 61).map((t) => [t, { status: 501, legacy: "v1" }])]),
      expect: {
        polls: {
          0: { outcome: "ok", cursor: 8, rows: 8, K: 8, label: "STALE" },
          1: { outcome: "paging_unsupported", cursor: 8, rows: 8, K: 8, degraded: "paging_unsupported", label: "STALE · paging unsupported" },
          ...Object.fromEntries([30, 61].map((t) => [t, { outcome: "no_request", fetches: 0, cursor: 8, rows: 8, K: 8, degraded: "paging_unsupported", label: "STALE · paging unsupported" }])),
        },
        never_live_from_s: 1,
      },
    },
    {
      name: "C6c a 400 on the cursor parameters is no cursor support too",
      limit: 256,
      polls: polls([[0, { status: 400, legacy: "v1" }], [1, { status: 400, legacy: "v1" }]]),
      expect: { polls: { 0: { outcome: "paging_unsupported", cursor: 0, K: 0, label: "STALE · paging unsupported" }, 1: { outcome: "no_request", fetches: 0, cursor: 0, K: 0, label: "STALE · paging unsupported" } }, never_live_from_s: 0 },
    },
    {
      name: "C8a replaced log of the same length (row 5 differs): the old cursor_hash gets 409, stream replaced, the prefix is kept, no reset",
      limit: 256,
      polls: polls([[0, v1], [1, { log: "c8-same" }], [2, { log: "c8-same" }]]),
      expect: {
        polls: {
          1: { outcome: "stream_replaced", cursor: 11, rows: 11, K: 11, degraded: "stream_replaced", label: "STALE · stream replaced" },
          2: { outcome: "no_request", fetches: 0, cursor: 11, rows: 11, K: 11, label: "STALE · stream replaced" },
        },
      },
    },
    {
      name: "C8b replaced log that is longer (row 5 differs, two rows added): the old cursor_hash gets 409, stream replaced, the prefix is kept",
      limit: 256,
      polls: polls([[0, v1], [1, { log: "c8-longer" }]]),
      expect: { polls: { 1: { outcome: "stream_replaced", cursor: 11, rows: 11, K: 11, degraded: "stream_replaced", label: "STALE · stream replaced" } } },
    },
    {
      name: "C9 hash mismatch: a page whose row 9 was altered in transit, then a page with no x-cursor-hash; each is a paging error and its rows are not kept",
      limit: 256,
      polls: polls([[0, { log: "v1-first8" }], [1, { log: "v1", tamper: { index: 9, row: "v1-10-tampered" } }], [2, { log: "v1", headers: { "x-cursor-hash": null } }], [3, v1]]),
      expect: {
        polls: {
          1: { outcome: "paging_error", cursor: 8, rows: 8, K: 8, label: "STALE · paging error" },
          2: { outcome: "paging_error", cursor: 8, rows: 8, K: 8, label: "STALE · paging error" },
          3: { outcome: "ok", cursor: 11, rows: 11, K: 11, label: live(0) },
        },
      },
    },
    {
      name: "C10 bytes to rows: one page holding a BOM-prefixed copy of seq 1 and a row of invalid UTF-8; both are malformed, the 11 other rows verify, and the cursor hash covers the raw bytes of all 13",
      limit: 256,
      polls: polls([[0, { log: "c10" }]]),
      expect: {
        polls: { 0: { outcome: "ok", fetches: 1, cursor: 13, rows: 13, K: 11, board: frozen(11), row_counts: { verified: 11, malformed: 2 }, rejected: { not_json: 1, invalid_utf8: 1 } } },
        raw_hash_covers_all: true,
      },
    },
    {
      name: "C11 K drops: after catch-up at 43, row 44 arrives (LIVE); 1 s later a validly signed, different seq 10 is appended and K falls to 9; the label is STALE · chain broken at once, not LIVE",
      limit: 256,
      polls: polls([[0, { log: "c11-first43" }], [1, { log: "c11" }], [2, { log: "c11+fork" }], [3, { log: "c11+fork" }], [62, { log: "c11+fork" }]]),
      expect: {
        polls: {
          0: { outcome: "ok", cursor: 43, rows: 43, K: 43, board: null, label: "STALE" },
          1: { outcome: "ok", cursor: 44, rows: 44, K: 44, board: null, label: live(0) },
          2: { outcome: "ok", cursor: 45, rows: 45, K: 9, board: frozen(9), label: "STALE · chain broken" },
          3: { outcome: "ok", cursor: 45, rows: 45, K: 9, label: "STALE · chain broken" },
          62: { outcome: "ok", cursor: 45, rows: 45, K: 9, label: "STALE · chain broken" },
        },
      },
    },
    {
      name: "C12a row too large: after seq 1..8, the next row is 4,194,304 bytes (4,194,305 with its LF); 413, STALE · row too large, the prefix is kept, and that cursor is never asked for again",
      limit: 256,
      polls: polls([[0, { log: "v1-first8" }], [1, { log: "v1-first8+huge" }], [2, { log: "v1-first8+huge" }], [10, { log: "v1-first8+huge" }]]),
      expect: {
        polls: {
          0: { outcome: "ok", cursor: 8, rows: 8, K: 8, label: "STALE" },
          1: { outcome: "row_too_large", fetches: 1, cursor: 8, rows: 8, K: 8, degraded: "row_too_large", label: "STALE · row too large" },
          2: { outcome: "no_request", fetches: 0, cursor: 8, rows: 8, K: 8, degraded: "row_too_large", label: "STALE · row too large" },
          10: { outcome: "no_request", fetches: 0, cursor: 8, rows: 8, K: 8, label: "STALE · row too large" },
        },
      },
    },
    {
      name: "C12b exactly 4 MiB: 65 rows of 65,535 bytes; the first page holds 64 whole rows (exactly 4,194,304 bytes with their LFs) and the 65th comes on the next page",
      limit: 256,
      polls: polls([[0, { log: "exact65" }]]),
      expect: { polls: { 0: { outcome: "ok", fetches: 2, cursor: 65, rows: 65, K: 0 } }, page_bytes: [4_194_304, 65_536] },
    },
    {
      name: "C13 malformed pages: with limit 1, a response holding 2 rows (headers otherwise consistent) is a paging error and neither row is kept; so is a one-row page whose body lacks its final LF",
      limit: 1,
      polls: polls([[0, { log: "v1-first8" }], [1, { page: { log: "v1-first8", rows: ["v1-09", "v1-10"] } }], [2, { log: "v1", strip_final_lf: true }], [3, v1]]),
      expect: {
        polls: {
          0: { outcome: "ok", fetches: 8, cursor: 8, rows: 8, K: 8, label: "STALE" },
          1: { outcome: "paging_error", fetches: 1, cursor: 8, rows: 8, K: 8, label: "STALE · paging error" },
          2: { outcome: "paging_error", fetches: 1, cursor: 8, rows: 8, K: 8, label: "STALE · paging error" },
          3: { outcome: "ok", fetches: 3, cursor: 11, rows: 11, K: 11, label: live(0) },
        },
      },
    },
    {
      name: "C14 unterminated tail: the log file ends with seq 6 still missing its LF, so the client gets 5 rows; once the LF lands, the next poll gets seq 6 and the earlier cursor hash still holds",
      limit: 256,
      polls: polls([[0, { file: "c14v-tail" }], [1, { file: "c14v-tail" }], [2, { file: "c14v-done" }]]),
      expect: {
        polls: {
          0: { outcome: "ok", cursor: 5, rows: 5, K: 5, label: "STALE" },
          1: { outcome: "ok", fetches: 1, cursor: 5, rows: 5, K: 5, label: "STALE" },
          2: { outcome: "ok", fetches: 1, cursor: 6, rows: 6, K: 6, label: live(0) },
        },
      },
    },
    ...[
      ["C15a", "c15-badsig", "a tampered row 45 (a bad signature)", "unverified"],
      ["C15b", "c15-malformed", "a malformed row 45 (not JSON)", "malformed"],
      ["C15c", "c15-gap", "row 45 is seq 46, after a gap", "unverified"],
    ].map(([id, log, what, status]) => ({
      name: `${id} frozen without a drop: after catch-up at 43, row 44 arrives (LIVE), then ${what} is appended; K stays 44, the board freezes after seq 44, and the label is STALE · chain broken at once, not LIVE`,
      limit: 256,
      polls: polls([[0, { log: "c11-first43" }], [1, { log: "c11" }], [2, { log }], [3, { log }], [31, { log }]]),
      expect: {
        polls: {
          0: { outcome: "ok", cursor: 43, rows: 43, K: 43, board: null, label: "STALE" },
          1: { outcome: "ok", cursor: 44, rows: 44, K: 44, board: null, label: live(0) },
          ...Object.fromEntries([2, 3, 31].map((t) => [t, { outcome: "ok", cursor: 45, rows: 45, K: 44, board: frozen(44), label: "STALE · chain broken", row_counts: { verified: 44, [status]: 1 } }])),
        },
      },
    })),
    {
      name: "C16 catching up is not progress: 272 rows load in 7 pages of 40; the label is STALE during catch-up and right after the last page, and LIVE on the first new row",
      limit: 40,
      polls: polls([[0, { log: "c16-backlog" }], [1, { log: "c16-backlog" }], [2, { log: "c16-plus1" }]]),
      expect: {
        polls: {
          0: { outcome: "ok", fetches: 7, cursor: 272, rows: 272, K: 272, board: null, label: "STALE" },
          1: { outcome: "ok", fetches: 1, cursor: 272, rows: 272, K: 272, label: "STALE" },
          2: { outcome: "ok", fetches: 1, cursor: 273, rows: 273, K: 273, label: live(0) },
        },
      },
    },
    {
      name: "C17a finished run: once the runs route says finished, the label is ENDED · run finished instead of LIVE or STALE, even right after growth, and a passing failure (transport, paging error) stays ENDED",
      limit: 256,
      polls: polls([[0, { log: "v1-first8" }], [1, v1], [2, v1, "finished"], [3, { network_error: true }, "finished"], [4, { log: "v1", headers: { "x-next-cursor": null } }, "finished"], [70, v1, "finished"]]),
      expect: {
        polls: {
          0: { outcome: "ok", cursor: 8, rows: 8, K: 8, label: "STALE" },
          1: { outcome: "ok", cursor: 11, rows: 11, K: 11, label: live(0) },
          2: { outcome: "ok", cursor: 11, K: 11, label: "ENDED · run finished" },
          3: { outcome: "transport", cursor: 11, K: 11, label: "ENDED · run finished" },
          4: { outcome: "paging_error", cursor: 11, K: 11, label: "ENDED · run finished" },
          70: { outcome: "ok", cursor: 11, K: 11, label: "ENDED · run finished" },
        },
      },
    },
    {
      name: "C17b finished run whose stream is replaced: the log shrinks to 5 rows, 409, and the label is STALE · stream replaced, not ENDED; no more requests",
      limit: 256,
      polls: polls([[0, v1, "finished"], [1, { log: "v1-first5" }, "finished"], [2, v1, "finished"]]),
      expect: {
        polls: {
          0: { outcome: "ok", cursor: 11, K: 11, label: "ENDED · run finished" },
          1: { outcome: "stream_replaced", cursor: 11, rows: 11, K: 11, degraded: "stream_replaced", label: "STALE · stream replaced" },
          2: { outcome: "no_request", fetches: 0, cursor: 11, K: 11, degraded: "stream_replaced", label: "STALE · stream replaced" },
        },
      },
    },
    {
      name: "C17c finished run with a refused row after the prefix: STALE · chain broken, not ENDED",
      limit: 256,
      polls: polls([[0, v1, "finished"], [1, { log: "v1+junk" }, "finished"], [2, { log: "v1+junk" }, "finished"]]),
      expect: {
        polls: {
          0: { outcome: "ok", cursor: 11, K: 11, board: null, label: "ENDED · run finished" },
          1: { outcome: "ok", cursor: 12, rows: 12, K: 11, board: frozen(11), label: "STALE · chain broken" },
          2: { outcome: "ok", cursor: 12, K: 11, label: "STALE · chain broken" },
        },
      },
    },
  ];
}

// ---- Bytes to rows: split on LF only, then strict UTF-8 per row with any BOM kept. null means not valid UTF-8. ----
// ---- Rule 5, one condition at a time, through liveLabel(). Each case sets the mode inputs directly and reads the
// label at 100 s: the last valid page and the last growth after catch-up were ok_age_s and progress_age_s seconds
// earlier (null: never). In the reference client a drop of K always leaves the old rows after the prefix, so it also
// sets frozen; the K-below-high case is still checked on its own because rule 5 lists it. ----
function labelSpecs() {
  const c = (name, run_status, failure, high_k, K, frozen, ok_age_s, progress_age_s, expect) => ({ name, run_status, failure, high_k, K, frozen, ok_age_s, progress_age_s, expect });
  return [
    c("running, K at its high, nothing after the prefix, growth 1 s ago: LIVE", "running", null, 44, 44, false, 1, 1, "LIVE · progress 1 s ago"),
    c("running, no growth since catch-up: STALE", "running", null, 272, 272, false, 1, null, "STALE"),
    c("running, last growth 61 s ago: STALE", "running", null, 44, 44, false, 1, 61, "STALE"),
    c("running, a refused row after the prefix, K at its high: STALE · chain broken", "running", null, 44, 44, true, 1, 1, "STALE · chain broken"),
    c("running, K below its high on its own: STALE · chain broken", "running", null, 44, 9, false, 1, 1, "STALE · chain broken"),
    c("running, a failed latest poll shows its own reason first, even on a frozen board", "running", "transport", 44, 44, true, 1, 1, "STALE · transport"),
    c("finished, not frozen: ENDED, even with growth 1 s ago", "finished", null, 44, 44, false, 1, 1, "ENDED · run finished"),
    c("finished, a refused row after the prefix: STALE · chain broken", "finished", null, 44, 44, true, 1, 1, "STALE · chain broken"),
    c("finished, K below its high: STALE · chain broken", "finished", null, 44, 9, false, 1, 1, "STALE · chain broken"),
    c("finished, a passing failure (transport): still ENDED", "finished", "transport", 44, 44, false, 10, 30, "ENDED · run finished"),
    c("finished, a passing failure (paging error): still ENDED", "finished", "paging_error", 44, 44, false, 10, 30, "ENDED · run finished"),
    c("finished, stream replaced: the terminal state wins over ENDED", "finished", "stream_replaced", 44, 44, false, 10, 30, "STALE · stream replaced"),
    c("finished, row too large: the terminal state wins over ENDED", "finished", "row_too_large", 44, 44, false, 10, 30, "STALE · row too large"),
    c("finished, paging unsupported: the terminal state wins over ENDED", "finished", "paging_unsupported", 44, 44, false, 10, 30, "STALE · paging unsupported"),
    c("finished, stream replaced on a frozen board: the terminal state shows first", "finished", "stream_replaced", 44, 44, true, 10, 30, "STALE · stream replaced"),
  ];
}

function bytesToRowsSpecs() {
  const b64 = (bytes) => Buffer.from(bytes).toString("base64");
  const text = (s) => [...encoder.encode(s)];
  return [
    { name: "a trailing LF ends the last row and doesn't start a new one", body_base64: b64(text("a\nb\n")), rows: ["a", "b"] },
    { name: "no trailing LF: the last row is still a row", body_base64: b64(text("a\nb")), rows: ["a", "b"] },
    { name: "a blank line in the middle is a row", body_base64: b64(text("a\n\nb\n")), rows: ["a", "", "b"] },
    { name: "an empty body has no rows", body_base64: "", rows: [] },
    { name: "a lone LF is one blank row", body_base64: b64(text("\n")), rows: [""] },
    { name: "only LF splits: a CR stays in the row", body_base64: b64(text("{}\r\n")), rows: ["{}\r"] },
    { name: "a leading BOM is kept", body_base64: b64([0xef, 0xbb, 0xbf, ...text("{}\n")]), rows: ["﻿{}"] },
    { name: "invalid UTF-8 (FF) is no text, and the next row still decodes", body_base64: b64([0x7b, 0xff, 0x7d, 0x0a, ...text("{}\n")]), rows: [null, "{}"] },
    { name: "an overlong encoding (C0 AF) is not valid UTF-8", body_base64: b64([0xc0, 0xaf, 0x0a]), rows: [null] },
    { name: "an encoded surrogate (ED A0 80) is not valid UTF-8", body_base64: b64([0xed, 0xa0, 0x80, 0x0a]), rows: [null] },
  ];
}

// ---- C7 server conformance. Expected values are computed with rawHash(), not with paging.mjs. ----
const LOG600_RULE = "row i (0 to 599) is the ASCII text {\"row\":i}, except when i % 100 is 7: then it is {\"row\":i,\"raw\":\" followed by the bytes FF FE and then \"}";
const LOG_BIG_RULE = "100 rows, each 65,535 bytes of 'x'";
function log600() {
  return Array.from({ length: 600 }, (_, i) => (i % 100 === 7
    ? new Uint8Array([...encoder.encode(`{"row":${i},"raw":"`), 0xff, 0xfe, ...encoder.encode('"}')])
    : encoder.encode(`{"row":${i}}`)));
}
const logBig = () => Array.from({ length: 100 }, () => new Uint8Array(65_535).fill(0x78));
const C7_LOGS = { log600: log600(), big: logBig(), huge1: [new Uint8Array(4_194_304).fill(0x78)], exact65: Array.from({ length: 65 }, () => new Uint8Array(65_535).fill(0x78)) };
const LOG_RULES = { log600: LOG600_RULE, big: LOG_BIG_RULE, huge1: "one row of 4,194,304 bytes of 'x'", exact65: "65 rows, each 65,535 bytes of 'x'" };
// C14 log files: the ASCII rows {"row":0} to {"row":5}. "c14-tail" ends with {"row":5} and no LF; "c14-done" adds the LF.
const c14Rows = Array.from({ length: 6 }, (_, i) => encoder.encode(`{"row":${i}}`));
const withLF = (rows) => rows.flatMap((row) => [Buffer.from(row), Buffer.from([0x0a])]);
const C14_FILES = {
  "c14-tail": { complete: c14Rows.slice(0, 5), bytes: new Uint8Array(Buffer.concat([...withLF(c14Rows.slice(0, 5)), Buffer.from(c14Rows[5])])) },
  "c14-done": { complete: c14Rows, bytes: new Uint8Array(Buffer.concat(withLF(c14Rows))) },
};
const FILE_RULES = { "c14-tail": "the rows {\"row\":0} to {\"row\":4}, each followed by LF, then {\"row\":5} with no LF", "c14-done": "the rows {\"row\":0} to {\"row\":5}, each followed by LF" };
const rowsOf = (key) => C7_LOGS[key] ?? C14_FILES[key].complete;
function serverSpecs() {
  const L = C7_LOGS.log600;
  const h = (n) => rawHash(L.slice(0, n));
  const other = L.map((row, i) => (i === 3 ? encoder.encode('{"row":3,"replaced":true}') : row));
  const ok = (log, from, to, more) => ({ status: 200, rows: [from, to], headers: { "x-next-cursor": String(to), "x-has-more": String(more), "x-cursor-hash": rawHash(rowsOf(log).slice(0, to)) }, body_sha256: sha256Bytes(Buffer.concat(rowsOf(log).slice(from, to).flatMap((row) => [Buffer.from(row), Buffer.from([0x0a])]))) });
  const status = (code) => ({ status: code, rows: [0, 0], headers: {}, body_sha256: sha256Bytes(Buffer.alloc(0)) });
  return [
    { name: "cursor 0, limit 256: rows 0 to 255", log: "log600", request: { cursor: 0, limit: 256 }, expect: ok("log600", 0, 256, true) },
    { name: "cursor 256 with the hash of rows 0..255: rows 256 to 511", log: "log600", request: { cursor: 256, limit: 256, cursor_hash: h(256) }, expect: ok("log600", 256, 512, true) },
    { name: "cursor 512: the last 88 rows, no more", log: "log600", request: { cursor: 512, limit: 256, cursor_hash: h(512) }, expect: ok("log600", 512, 600, false) },
    { name: "cursor 600 (the end): 0 rows, no more", log: "log600", request: { cursor: 600, limit: 256, cursor_hash: h(600) }, expect: ok("log600", 600, 600, false) },
    { name: "cursor 601 (beyond the end): 409", log: "log600", request: { cursor: 601, limit: 256, cursor_hash: h(600) }, expect: status(409) },
    { name: "a stale cursor_hash (from a log whose row 3 differs): 409", log: "log600", request: { cursor: 256, limit: 256, cursor_hash: rawHash(other.slice(0, 256)) }, expect: status(409) },
    { name: "a cursor above 0 without cursor_hash: 409", log: "log600", request: { cursor: 256, limit: 256 }, expect: status(409) },
    { name: "cursor 0, limit 1", log: "log600", request: { cursor: 0, limit: 1 }, expect: ok("log600", 0, 1, true) },
    { name: "limit 0: 400", log: "log600", request: { cursor: 0, limit: 0 }, expect: status(400) },
    { name: "limit 257: 400", log: "log600", request: { cursor: 0, limit: 257 }, expect: status(400) },
    { name: "cursor -1: 400", log: "log600", request: { cursor: -1, limit: 256 }, expect: status(400) },
    { name: "rows of 65,535 bytes: a page stops at 64 rows, exactly 4 MiB", log: "big", request: { cursor: 0, limit: 256 }, expect: ok("big", 0, 64, true) },
    { vector: "C12", name: "a first row of 4,194,304 bytes (4,194,305 with its LF): 413, no body, no cursor headers", log: "huge1", request: { cursor: 0, limit: 256 }, expect: status(413) },
    { vector: "C12", name: "65 rows of 65,535 bytes: whole rows up to exactly 4 MiB (64 rows), the 65th left for the next page", log: "exact65", request: { cursor: 0, limit: 256 }, expect: ok("exact65", 0, 64, true) },
    { vector: "C12", name: "the next page holds the deferred 65th row", log: "exact65", request: { cursor: 64, limit: 256, cursor_hash: rawHash(rowsOf("exact65").slice(0, 64)) }, expect: ok("exact65", 64, 65, false) },
    { vector: "C14", name: "a file whose last row has no LF: only the 5 complete rows are served and hashed", file: "c14-tail", request: { cursor: 0, limit: 256 }, expect: ok("c14-tail", 0, 5, false) },
    { vector: "C14", name: "cursor 5 on that file: 0 rows; the tail is not served", file: "c14-tail", request: { cursor: 5, limit: 256, cursor_hash: rawHash(rowsOf("c14-tail")) }, expect: ok("c14-tail", 5, 5, false) },
    { vector: "C14", name: "cursor 6 on that file is beyond the end: 409 (the tail is not counted)", file: "c14-tail", request: { cursor: 6, limit: 256, cursor_hash: rawHash(rowsOf("c14-done")) }, expect: status(409) },
    { vector: "C14", name: "once the LF lands, cursor 5 with the earlier hash gets the sixth row", file: "c14-done", request: { cursor: 5, limit: 256, cursor_hash: rawHash(rowsOf("c14-tail")) }, expect: ok("c14-done", 5, 6, false) },
    { vector: "C14", name: "after the LF, all 6 rows from cursor 0", file: "c14-done", request: { cursor: 0, limit: 256 }, expect: ok("c14-done", 0, 6, false) },
  ];
}

// ---- cursorHash() over raw bytes. Expected values are computed with rawHash(). ----
function cursorHashSpecs() {
  const reencoded = (rowId) => encoder.encode(lenient(bytesOf(rowId)));
  return [
    { name: "no rows: the SHA-256 of nothing", rows: [], expect: rawHash([]) },
    { name: "one row {}: the SHA-256 of {} and LF", rows: ["filler"], expect: rawHash([bytesOf("filler")]) },
    { name: "the 11 V1 rows", rows: V1_IDS, expect: rawHash(V1_IDS.map(bytesOf)) },
    { name: "a row with invalid UTF-8 is hashed as received; decoding first would give a different hash", rows: ["junk-utf8"], expect: rawHash([bytesOf("junk-utf8")]), decoded_would_give: rawHash([reencoded("junk-utf8")]) },
  ];
}

function generate() {
  return {
    description: "Paging vectors for the SentiLab view, DRAFT v0.6.2 (view-envelope-0.6.2.md, rules 4 and 5). Generated by `node run-paging-vectors.mjs --write` and checked by `node run-paging-vectors.mjs`. Envelopes keep v0.5's format; the V1 rows come from ../view-envelope-v0.5/vectors-view.json. Scenarios give the polls, what the server does at each, hand-written expectations and the full trace.",
    contract_sha256: CONTRACT_SHA256,
    rules: {
      cursor_hash: "lowercase hex SHA-256 over the raw bytes of rows 0..n-1, each followed by one LF; computed on bytes as received, never on decoded text",
      request: "{ cursor, limit } plus cursor_hash for every cursor above 0; never a seq parameter",
      ok: "status 200, body within 256 lines and 4 MiB, x-next-cursor a decimal integer equal to cursor + rows returned, and x-cursor-hash equal to the client's own hash of all rows it would then hold",
      failures: "transport: no response, a status other than 200, 400, 404, 409, 413 or 501, or a body over the caps; paging_error: a bad x-next-cursor, more rows than the requested limit, a non-empty body that doesn't end with LF, or a bad x-cursor-hash; stream_replaced: 409; row_too_large: 413; paging_unsupported: 400, 404 or 501. A failed poll keeps no rows and never resets the cursor; stream_replaced, row_too_large and paging_unsupported are terminal: no more requests until a manual reload",
      label: "a finished run (run_status from GET /api/view/runs) shows \"ENDED · run finished\", but integrity problems win: a terminal state (stream replaced, row too large, paging unsupported) keeps its \"STALE · <reason>\" label, then a frozen board shows \"STALE · chain broken\"; a passing failure (transport, paging error) stays ENDED; a missing or unknown status counts as running; for a running run, a failed latest poll shows \"STALE · <reason>\" (transport, paging error, stream replaced, row too large, paging unsupported); otherwise a frozen board (K below the highest value it has reached, or anything after the projectable prefix) shows \"STALE · chain broken\" at once; otherwise v0.5's mode rule: LIVE needs a valid page within 5 s and growth within 60 s",
      progress: "catching up is not progress: every valid page up to and including the first one with no more to fetch (x-has-more false) is history, whose rows raise the high-water mark but never count as growth; after catch-up, K rising above its highest value is growth",
      run_status: "each poll's run_status is what GET /api/view/runs says then; running when absent",
      bytes_to_rows: "split raw bytes on LF (0x0A) only; a trailing LF doesn't start a row; decode each row on its own as strict UTF-8 keeping any BOM (TextDecoder(\"utf-8\", { fatal: true, ignoreBOM: true })); a row that isn't valid UTF-8 is malformed (invalid_utf8), a row starting with a BOM is malformed (not_json, since JSON.parse rejects it), and the page continues; the same for replay files, except that a replay file's last line may lack its LF and still counts as a row; the hash never sees decoded text",
      server: "400 for a cursor or limit outside the allowed range; 409 for a cursor beyond the end, or above 0 without a cursor_hash or with one that doesn't match; 413, with no body and no cursor headers, when the row at the cursor plus its LF is over 4 MiB; otherwise as many whole rows, each with its LF, as fit within 4 MiB, up to limit, with x-next-cursor, x-has-more and x-cursor-hash; never a 200 over 4 MiB",
      complete_rows: "the log is its complete, LF-terminated rows (logRowsFromFile); a tail with no LF yet is neither served, counted nor hashed until its LF is written",
      rows: "text rows are UTF-8; base64 rows are raw bytes; fill rows are `bytes` copies of `fill`. In logs and bodies, [\"id\", n] means n copies",
      server_behaviors: "log: servePage() over that log; headers: overrides, null removes; tamper: replace that log row in the body only; page: exactly those rows after the log, consistent headers, no limit; status + legacy: that status for cursor requests, and a legacy 200 page (rows with seq > after, no paging headers) if a request carries after; strip_final_lf: drop the body's final LF; network_error: no response",
    },
    view: { run_id: "run-v1", pins: [{ key_id: "core", test_key: "core" }], served_keys: { core: "core" } },
    rows: ROWS,
    chains: Object.fromEntries(Object.entries(CHAINS).map(([name, spec]) => [name, { ...spec, rows_sha256: rawHash(CHAIN_ROWS[name]) }])),
    logs: LOGS,
    label_cases: labelSpecs(),
    bytes_to_rows: bytesToRowsSpecs(),
    cursor_hash_cases: cursorHashSpecs(),
    server_logs: LOG_RULES,
    server_files: FILE_RULES,
    server_cases: serverSpecs(),
    scenarios: scenarioSpecs().map((spec) => ({ ...spec, trace: runScenario(spec).trace })),
  };
}

// Indented JSON, with each fetch and each trace step's state on one line.
function format(vectors) {
  const inline = [];
  const mark = (value) => `@@inline-${inline.push(JSON.stringify(value)) - 1}@@`;
  const marked = {
    ...vectors,
    scenarios: vectors.scenarios.map((spec) => ({
      ...spec,
      polls: spec.polls.map(mark),
      trace: spec.trace.map((stepRecord) => ({ ...stepRecord, fetches: stepRecord.fetches.map(mark), after: mark(stepRecord.after) })),
    })),
    server_cases: vectors.server_cases.map((spec) => ({ ...spec, request: mark(spec.request), expect: mark(spec.expect) })),
  };
  return `${JSON.stringify(marked, null, 2).replace(/"@@inline-(\d+)@@"/g, (_, i) => inline[Number(i)])}\n`;
}

// ---- Checks. ----
const results = [];
function check(name, fn) {
  let errors;
  try { errors = fn(); } catch (error) { errors = [`threw ${error.name}: ${error.message}`]; }
  results.push({ name, errors });
  console.log(errors.length === 0 ? `PASS  ${name}` : `FAIL  ${name}: ${errors.slice(0, 4).join("; ")}${errors.length > 4 ? ` (+${errors.length - 4} more)` : ""}`);
}

if (process.argv.includes("--write")) {
  writeFileSync(FILE, format(generate()));
  console.log(`wrote ${FILE}`);
}
const file = JSON.parse(readFileSync(FILE, "utf8"));
const fresh = generate();

check("file: same rules, view, rows and logs as the generator", () =>
  ["description", "contract_sha256", "rules", "view", "rows", "chains", "logs", "server_logs"].filter((k) => !same(file[k], fresh[k])).map((k) => `${k} differs`));
check("file: same vectors as the generator in every section", () =>
  ["label_cases", "bytes_to_rows", "cursor_hash_cases", "server_cases", "scenarios"].filter((k) => !same(file[k].map((v) => v.name), fresh[k].map((v) => v.name))).map((k) => `${k} list differs`));
check("purity: paging.mjs reads no clock, randomness, network, timers, files or process state", () => {
  const text = readFileSync(join(here, "paging.mjs"), "utf8");
  return ["Date", "Math.random", "fetch(", "setTimeout", "setInterval", "process.", "node:fs", "performance", "Buffer"].filter((token) => text.includes(token)).map((token) => `uses ${token}`);
});

for (const [index, spec] of file.label_cases.entries()) {
  check(`label: ${spec.name}`, () => {
    const errors = same(spec, fresh.label_cases[index]) ? [] : ["differs from the generator"];
    const nowMs = BASE_MS + 100_000;
    const ago = (s) => (s === null ? null : nowMs - s * 1000);
    // A terminal failure is also the state's degraded reason, as step() sets it.
    const degraded = ["stream_replaced", "row_too_large", "paging_unsupported"].includes(spec.failure) ? spec.failure : null;
    const state = { ...initialState("run-v1"), failure: spec.failure, degraded, caught_up: true, high_k: spec.high_k, last_ok_ms: ago(spec.ok_age_s), last_progress_ms: ago(spec.progress_age_s) };
    const got = liveLabel(state, nowMs, spec.K, spec.frozen, spec.run_status);
    return got === spec.expect ? errors : [...errors, `got "${got}"`];
  });
}
for (const [index, spec] of file.bytes_to_rows.entries()) {
  check(`bytes to rows: ${spec.name}`, () => {
    const errors = same(spec, fresh.bytes_to_rows[index]) ? [] : ["differs from the generator"];
    const got = splitRows(new Uint8Array(Buffer.from(spec.body_base64, "base64"))).map(rowText);
    return same(got, spec.rows) ? errors : [...errors, `rows ${JSON.stringify(got)}, expected ${JSON.stringify(spec.rows)}`];
  });
}
check("bytes to rows: a BOM row is malformed (not_json) and an invalid-UTF-8 row is malformed (invalid_utf8), wherever they sit, and the rows around them verify", () => {
  const v1Rows = V1_IDS.map(bytesOf);
  const errors = [];
  for (const at of [0, 5, 11]) {
    const rows = [...v1Rows.slice(0, at), bytesOf("bom-v1-01"), bytesOf("junk-utf8"), ...v1Rows.slice(at)];
    const result = verifyBytes(rows, OPTIONS);
    const rejected = result.rows.filter((row) => row.status === "malformed").map((row) => row.reasons);
    if (!same(rejected, [["not_json"], ["invalid_utf8"]]) || result.prefix_end !== 11) errors.push(`at ${at}: ${canonical(rejected)}, K ${result.prefix_end}`);
  }
  return errors;
});
check("bytes to rows: an invalid-UTF-8 row over 64 KiB is oversize (raw size first), not invalid_utf8", () => {
  const big = new Uint8Array(65_537).fill(0xff);
  const row = verifyBytes([big], OPTIONS).rows[0];
  return row.status === "oversize" && same(row.reasons, ["line_too_large"]) ? [] : [`got ${row.status} ${canonical(row.reasons)}`];
});
check("replay bytes: a file over 64 MiB is refused before any row is read; a small one verifies like the paged rows", () => {
  const big = verifyReplayBytes(new Uint8Array(64 * 1024 * 1024 + 1), OPTIONS);
  const errors = !big.ok && big.reason === "file_too_large" ? [] : ["big file accepted"];
  const small = verifyReplayBytes(joinRows(V1_IDS.map(bytesOf)), OPTIONS);
  return small.ok && small.verification.prefix_end === 11 ? errors : [...errors, "small file didn't verify to K = 11"];
});
check("replay bytes: a replay file's last line may lack its LF and still counts as a row", () => {
  const full = joinRows(V1_IDS.map(bytesOf));
  const result = verifyReplayBytes(full.subarray(0, full.length - 1), OPTIONS);
  return result.ok && result.verification.rows.length === 11 && result.verification.prefix_end === 11 ? [] : [`got ${result.ok ? result.verification.rows.length + " rows, K " + result.verification.prefix_end : result.reason}`];
});
for (const [index, spec] of file.cursor_hash_cases.entries()) {
  check(`cursor hash: ${spec.name}`, () => {
    const errors = same(spec, fresh.cursor_hash_cases[index]) ? [] : ["differs from the generator"];
    const rows = spec.rows.map(bytesOf);
    if (cursorHash(rows) !== spec.expect || rawHash(rows) !== spec.expect) errors.push(`cursorHash ${cursorHash(rows)}, expected ${spec.expect}`);
    if (spec.decoded_would_give !== undefined && spec.decoded_would_give === spec.expect) errors.push("decoding should change this hash");
    return errors;
  });
}

for (const [index, spec] of file.server_cases.entries()) {
  check(`${spec.vector ?? "C7"} server: ${spec.name}`, () => {
    const errors = same(spec, fresh.server_cases[index]) ? [] : ["differs from the generator"];
    const reply = servePage(spec.file ? logRowsFromFile(C14_FILES[spec.file].bytes) : C7_LOGS[spec.log], spec.request);
    const want = spec.expect;
    if (reply.status !== want.status) errors.push(`status ${reply.status}, expected ${want.status}`);
    if (!same(reply.headers, want.headers)) errors.push(`headers ${canonical(reply.headers)}, expected ${canonical(want.headers)}`);
    if (sha256Bytes(reply.bodyBytes) !== want.body_sha256) errors.push("body differs");
    const [from, to] = want.rows;
    const expectedBody = joinRows(rowsOf(spec.file ?? spec.log).slice(from, to));
    if (sha256Bytes(expectedBody) !== want.body_sha256) errors.push("the recorded body is not rows from..to");
    return errors;
  });
}

check("C14 file to rows: only complete, LF-terminated rows count; a tail without its LF is not a row", () => {
  const errors = [];
  const hex = (rows) => rows.map((row) => Buffer.from(row).toString("hex"));
  const cases = [
    ["the file with a tail", C14_FILES["c14-tail"].bytes, C14_FILES["c14-tail"].complete],
    ["the file once its LF lands", C14_FILES["c14-done"].bytes, C14_FILES["c14-done"].complete],
    ["an empty file", new Uint8Array(0), []],
    ["a file with no LF at all", encoder.encode('{"row":0}'), []],
    ["a blank complete row", encoder.encode("a\n\n"), [encoder.encode("a"), new Uint8Array(0)]],
  ];
  for (const [name, bytes, want] of cases) if (!same(hex(logRowsFromFile(bytes)), hex(want))) errors.push(name);
  return errors;
});

const independentRequestHash = (state) => rawHash(state.rows);
for (const [index, spec] of file.scenarios.entries()) {
  const label = spec.name.split(" ")[0];
  const run = runScenario(spec);
  const byTime = new Map(run.trace.map((s) => [s.t_s, s]));
  check(`${label}: polls and expectations match the generator`, () =>
    ["name", "limit", "polls", "expect"].filter((k) => !same(spec[k], fresh.scenarios[index]?.[k])).map((k) => `${k} differs`));
  check(`${label}: the trace regenerates identically`, () => {
    if (same(run.trace, spec.trace)) return [];
    const at = run.trace.findIndex((s, i) => !same(s, spec.trace[i]));
    return [`first difference at t = ${run.trace[at]?.t_s} s: ${canonical(run.trace[at]).slice(0, 300)}`];
  });
  check(`${label}: the hand-written expectations hold`, () => Object.entries(spec.expect.polls).flatMap(([t, want]) => {
    const got = byTime.get(Number(t));
    if (!got) return [`no poll at ${t} s`];
    const actual = { outcome: got.fetches.at(-1)?.outcome ?? "no_request", fetches: got.fetches.length, cursor: got.after.cursor, rows: got.after.rows, K: got.K, board: got.board, label: got.label, degraded: got.after.degraded, row_counts: got.row_counts, rejected: got.rejected };
    return Object.entries(want).filter(([key, value]) => !same(actual[key] ?? null, value)).map(([key, value]) => `at ${t} s ${key}: expected ${JSON.stringify(value)}, got ${JSON.stringify(actual[key])}`);
  }));
  check(`${label}: no reset, no rows kept from a failed poll, cursor = rows held, cursor_hash sent for every cursor above 0, never a seq parameter`, () => run.transitions.flatMap(({ before, after, req, outcome }, i) => {
    const errors = [];
    if (after.cursor < before.cursor || after.rows.length < before.rows.length) errors.push(`fetch ${i}: went back from ${before.cursor} to ${after.cursor}`);
    if (outcome !== "ok" && (after.rows !== before.rows || after.cursor !== before.cursor || after.cursor_hash !== before.cursor_hash)) errors.push(`fetch ${i}: a failed poll changed the rows or cursor`);
    if (after.cursor !== after.rows.length) errors.push(`fetch ${i}: cursor ${after.cursor} but ${after.rows.length} rows`);
    if (!same(Object.keys(req).sort(), before.cursor > 0 ? ["cursor", "cursor_hash", "limit"] : ["cursor", "limit"])) errors.push(`fetch ${i}: request ${canonical(req)}`);
    if (before.cursor > 0 && req.cursor_hash !== independentRequestHash(before)) errors.push(`fetch ${i}: cursor_hash isn't the hash of the rows held`);
    return errors;
  }));
  check(`${label}: LIVE only right after a valid page`, () => run.trace.flatMap((s) => (s.label.startsWith("LIVE") && s.fetches.at(-1)?.outcome !== "ok" ? [`at ${s.t_s} s: ${s.label} after ${s.fetches.at(-1)?.outcome ?? "no request"}`] : [])));
  check(`${label}: LIVE never shows during catch-up (after any page that was still history)`, () => run.trace.flatMap((s) => s.fetches.filter((f) => f.outcome === "ok" && f.catching_up && f.label.startsWith("LIVE")).map((f) => `at ${s.t_s} s: ${f.label} after a catch-up page`)));
  check(`${label}: LIVE never shows while the board is frozen`, () => run.trace.flatMap((s) => (s.label.startsWith("LIVE") && s.board !== null ? [`at ${s.t_s} s: ${s.label} next to "${s.board}"`] : [])));
  check(`${label}: after a terminal outcome (stream replaced, row too large, paging unsupported) no request is ever sent again`, () => {
    const at = run.trace.findIndex((s) => s.fetches.some((f) => ["stream_replaced", "row_too_large", "paging_unsupported"].includes(f.outcome)));
    return at < 0 ? [] : run.trace.slice(at + 1).filter((s) => s.fetches.length > 0).map((s) => `request at ${s.t_s} s`);
  });
  if (spec.expect.page_bytes) {
    check(`${label}: the pages are exactly ${spec.expect.page_bytes.map((b) => b.toLocaleString("en-US")).join(" and ")} bytes`, () => {
      const sizes = run.trace[0].fetches.map((f) => f.response.body_bytes);
      return same(sizes, spec.expect.page_bytes) ? [] : [`page sizes ${sizes.join(", ")}`];
    });
  }
  check(`${label}: verifying the rows held equals verifying the same bytes as one replay file`, () => {
    const fileRead = verifyReplayBytes(joinRows(run.state.rows), OPTIONS);
    return fileRead.ok && same(verifyRows(run.state, OPTIONS).verification, fileRead.verification) ? [] : ["they differ"];
  });
  if (spec.expect.raw_hash_covers_all) {
    check(`${label}: the cursor hash is over the raw bytes of every row held, BOM and invalid UTF-8 included`, () => {
      const errors = run.state.cursor_hash === rawHash(run.state.rows) ? [] : ["cursor_hash isn't the raw-byte hash"];
      if (run.state.cursor_hash === rawHash(run.state.rows.map((row) => encoder.encode(lenient(row))))) errors.push("decoded text would give the same hash, so the vector can't tell them apart");
      if (!run.state.rows.some((row) => row[0] === 0xef && row[1] === 0xbb && row[2] === 0xbf) || !run.state.rows.some((row) => rowText(row) === null)) errors.push("the BOM row or the invalid row is missing");
      return errors;
    });
  }
  if (spec.expect.never_live_from_s !== undefined) {
    check(`${label}: never LIVE from ${spec.expect.never_live_from_s} s, every label says why, and no request pages by seq`, () => run.trace.filter((s) => s.t_s >= spec.expect.never_live_from_s).flatMap((s) => [
      ...(s.label.startsWith("LIVE") ? [`LIVE at ${s.t_s} s`] : []),
      ...(s.label === "STALE · paging unsupported" ? [] : [`at ${s.t_s} s: ${s.label}`]),
      ...s.fetches.filter((f) => "after" in f.request).map(() => `seq paging at ${s.t_s} s`),
    ]));
  }
  if (spec.expect.legacy_would_miss) {
    const { log, after } = spec.expect.legacy_would_miss;
    check(`${label}: seq paging (after=${after}) never delivers the conflicting row; the cursor delivered it`, () => {
      const errors = legacyRows(log, after).length === 0 ? [] : ["seq paging delivered rows"];
      const delivered = run.trace.find((s) => s.t_s === 2).fetches.some((f) => f.new_rows === 1 && same(f.response.body_rows, ["v1-03-fork"]));
      return delivered ? errors : [...errors, "the cursor page at 2 s didn't deliver the conflicting row"];
    });
  }
}

const failed = results.filter((r) => r.errors.length > 0).length;
console.log(failed === 0 ? `PASS: ${results.length} of ${results.length} checks` : `FAIL: ${failed} of ${results.length} checks failed`);
const fileSha = (name) => createHash("sha256").update(readFileSync(join(here, name))).digest("hex");
for (const name of ["paging.mjs", "run-paging-vectors.mjs", "vectors-paging.json"]) console.log(`${fileSha(name)}  ${name}`);
process.exit(failed === 0 ? 0 : 1);
