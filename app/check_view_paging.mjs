// Real-route composition with the unchanged reference reducer and vector data (v0.6.1 or v0.6.2).
// Run through `python -m app.check_view_paging [contract-dir]` (starts a local HTTP server).
// v0.6.2 (the reference exports track()): progress lives in the paging state, catching up is not progress, and the
// label takes the run's status. Each poll's run status is written to the run's meta file and read back through the
// real GET /api/view/runs, so a finished run's "ENDED · run finished" is checked end to end.
import assert from "node:assert/strict";
import { createHash, createPrivateKey, createPublicKey } from "node:crypto";
import { appendFileSync, existsSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

const [reference, origin, root] = process.argv.slice(2);
const paging = await import(pathToFileURL(join(reference, "paging.mjs")));
const { initialState, request, step, joinRows, verifyRows, liveLabel } = paging;
const v062 = typeof paging.track === "function";
const { progressTracker, makeChain } = await import(pathToFileURL(join(reference, "../view-envelope-v0.5/view-envelope.mjs")));
const vectors = JSON.parse(readFileSync(join(reference, "vectors-paging.json")));
const sha = (bytes) => createHash("sha256").update(bytes).digest("hex");
assert.equal(sha(readFileSync(join(reference, "VIEW-ENVELOPE.md"))), vectors.contract_sha256);

// The reference fixture key, derived by its public rule (a test key, never a production one). The private half is
// used only to rebuild the vectors' rule-built chains (v0.6.2's C16), exactly as the reference runner does.
const fixturePrivateKey = createPrivateKey({
  key: Buffer.concat([Buffer.from("302e020100300506032b657004220420", "hex"),
    createHash("sha256").update("sentilab-view-test-key:core").digest()]),
  format: "der", type: "pkcs8",
});
// Chains the vectors give by rule (v0.6.2: c16, 273 envelopes), rebuilt as run-paging-vectors.mjs builds them and
// checked against the recorded rows_sha256.
const chainRows = {};
for (const [name, spec] of Object.entries(vectors.chains ?? {})) {
  assert.equal(name, "c16", `unknown rule-built chain ${name}`);
  const v05 = JSON.parse(readFileSync(join(reference, "../view-envelope-v0.5/vectors-view.json")));
  const v1 = v05.chains.find((chain) => chain.name.startsWith("V1 "));
  const [labActor, coreActor] = [v1.input.entries[0].actor, v1.input.entries[1].actor];
  const at = (seconds) => new Date(Date.UTC(2026, 9, 31, 12, 0, 0) + seconds * 1000).toISOString();
  const entries = Array.from({ length: spec.count }, (_, i) => {
    const seq = i + 1;
    const event = seq === 1
      ? { event_id: "c16-e001", seq, type: "node.create", actor_role: "lab", body: { id: "K16", kind: "candidate" } }
      : { event_id: `c16-e${String(seq).padStart(3, "0")}`, seq, type: "node.create", actor_role: "core", body: { id: `U${seq}`, kind: "source" } };
    return { event, ts: at(seq), actor: seq === 1 ? labActor : coreActor };
  });
  chainRows[name] = makeChain(v1.input.run, entries, {}, { key_id: "core", privateKey: fixturePrivateKey }).map((env) => Buffer.from(JSON.stringify(env)));
  assert.equal(sha(Buffer.concat(chainRows[name].flatMap((row) => [row, Buffer.from("\n")]))), spec.rows_sha256, `${name} rebuilt by its rule`);
}
const bytesOf = (id) => {
  const chainRow = /^(\w+):(\d+)$/.exec(id);
  if (chainRow && chainRows[chainRow[1]]) return chainRows[chainRow[1]][Number(chainRow[2]) - 1];
  const row = vectors.rows[id];
  return row.text !== undefined ? Buffer.from(row.text) : row.base64 !== undefined
    ? Buffer.from(row.base64, "base64") : Buffer.alloc(row.bytes, row.fill);
};
// A log entry is a row id, [id, n] for n copies, or { chain, from, to } for that chain's rows seq from..to.
const expand = (ids) => ids.flatMap((id) => (Array.isArray(id) ? Array(id[1]).fill(id[0])
  : typeof id === "object" ? Array.from({ length: id.to - id.from + 1 }, (_, i) => `${id.chain}:${id.from + i}`) : [id])).map(bytesOf);
const log = (name) => expand(vectors.logs[name]);
const ledger = join(root, "run-v1.jsonl");
const write = (rows) => writeFileSync(ledger, joinRows(rows));
let requests = 0, hashedPages = 0, injectedPolls = 0;
async function http(req, physicalRows) {
  requests += 1;
  const response = await fetch(`${origin}/api/view/events?${new URLSearchParams({ run_id: "run-v1", ...req })}`);
  const page = { status: response.status, headers: Object.fromEntries(response.headers), bodyBytes: new Uint8Array(await response.arrayBuffer()) };
  if (page.status === 200) {
    assert.ok(page.bodyBytes.length <= 4 * 1024 * 1024, "HTTP never serves a page over 4 MiB");
    const next = Number(page.headers["x-next-cursor"]);
    assert.deepEqual(Buffer.from(page.bodyBytes), Buffer.from(joinRows(physicalRows.slice(req.cursor, next))), "HTTP serves physical bytes");
    assert.equal(page.headers["x-cursor-hash"], sha(joinRows(physicalRows.slice(0, next))), "HTTP prefix hash");
    hashedPages += 1;
  }
  if (page.status === 413) {
    assert.equal(page.bodyBytes.length, 0, "413 has no body");
    for (const name of ["x-next-cursor", "x-cursor-hash", "x-has-more", "x-next-after"]) {
      assert.equal(page.headers[name], undefined, "413 has no paging headers");
    }
  }
  return page;
}

const key = createPublicKey(fixturePrivateKey);
const options = { runId: "run-v1", pins: [{ key_id: "core", key_sha256: sha(key.export({ format: "der", type: "spki" }).subarray(12)) }], keys: { core: key } };

// C3/C5/C6/C9/C13 inject the vector's broken network/server behavior after a real
// HTTP fetch; the producer itself must not emit those malformed responses.
async function serve(server, req) {
  const physical = server.file ? log("v1").slice(0, server.file === "c14v-tail" ? 5 : 6)
    : server.page ? [...log(server.page.log), ...expand(server.page.rows)] : log(server.log ?? server.legacy ?? "empty");
  write(physical);
  if (server.file === "c14v-tail") appendFileSync(ledger, bytesOf("v1-06"));
  let page = await http(req, physical);
  if (server.network_error || server.status || server.page || server.headers || server.tamper || server.strip_final_lf) injectedPolls += 1;
  if (server.network_error) return null;
  if (server.status) return { ...page, status: server.status, headers: {}, bodyBytes: new Uint8Array() };
  if (server.page) {
    const rows = expand(server.page.rows), next = req.cursor + rows.length;
    page = { status: 200, bodyBytes: joinRows(rows), headers: {
      "x-next-cursor": String(next), "x-has-more": "false", "x-cursor-hash": sha(joinRows(physical.slice(0, next))),
    } };
  }
  for (const [name, value] of Object.entries(server.headers ?? {})) {
    if (value === null) delete page.headers[name]; else page.headers[name] = value;
  }
  if (server.tamper) {
    const rows = physical.slice(req.cursor, Number(page.headers["x-next-cursor"]));
    rows[server.tamper.index - req.cursor] = bytesOf(server.tamper.row);
    page.bodyBytes = joinRows(rows);
  }
  if (server.strip_final_lf && page.bodyBytes.length > 0) page.bodyBytes = page.bodyBytes.subarray(0, -1);
  return page;
}

// v0.6.2: the run's status as the real GET /api/view/runs reports it, after writing what the vector says it is then.
// "finished" stays finished; anything else counts as running, as the view reads it.
let statusPolls = 0, finishedPolls = 0, catchUpPages = 0;
async function routeRunStatus(want) {
  if (!existsSync(ledger)) writeFileSync(ledger, "");
  writeFileSync(join(root, "run-v1.meta.json"), JSON.stringify({ status: want }));
  const response = await fetch(`${origin}/api/view/runs`);
  assert.equal(response.status, 200, "runs route");
  const listed = (await response.json()).runs.find((run) => run.run_id === "run-v1");
  assert.ok(listed, "the runs route lists the run");
  assert.equal(listed.status, want, "the runs route reports the status the run has");
  statusPolls += 1;
  if (want === "finished") finishedPolls += 1;
  return listed.status === "finished" ? "finished" : "running";
}

for (const scenario of vectors.scenarios) {
  let state = initialState("run-v1", { limit: scenario.limit });
  const tracker = v062 ? null : progressTracker();
  for (const [index, poll] of scenario.polls.entries()) {
    const now = Date.UTC(2026, 9, 31, 12) + poll.t_s * 1000;
    const expected = scenario.trace[index];
    const runStatus = v062 ? await routeRunStatus(poll.run_status ?? "running") : undefined;
    let count = 0;
    for (; count < 16;) {
      const req = request(state);
      if (req === null) break;
      const result = step(state, await serve(poll.server, req), now);
      state = result.state;
      const fetch = expected.fetches[count++];
      assert.equal(result.outcome, fetch.outcome, scenario.name);
      assert.equal(result.newRows.length, fetch.new_rows, scenario.name);
      if (v062) {
        // Re-verify after every page; a valid page also updates progress (catch-up pages only raise the high).
        const page = verifyRows(state, options);
        if (result.outcome === "ok") state = paging.track(state, page.K, now);
        const label = liveLabel(state, now, page.K, page.frozen, runStatus);
        assert.equal(state.catching_up, fetch.catching_up, `${scenario.name}: catching_up`);
        assert.equal(label, fetch.label, `${scenario.name}: label after page ${count}`);
        // Catching up is not progress: a backlog load never shows LIVE.
        if (result.outcome === "ok" && state.catching_up) {
          assert.ok(!label.startsWith("LIVE"), `${scenario.name}: LIVE during catch-up`);
          catchUpPages += 1;
        }
      } else if (result.outcome === "ok") tracker.poll({ nowMs: now, ok: true, K: verifyRows(state, options).K, received: result.newRows.length });
      else tracker.poll({ nowMs: now, ok: false });
      if (result.outcome !== "ok" || !state.has_more) break;
    }
    assert.equal(count, expected.fetches.length, scenario.name);
    for (const [field, value] of Object.entries(expected.after)) {
      assert.deepEqual(field === "rows" ? state.rows.length : state[field], value, `${scenario.name}: ${field}`);
    }
    const { verification, K, frozen } = verifyRows(state, options);
    assert.equal(K, expected.K, scenario.name);
    assert.equal(verification.label, expected.board, scenario.name);
    assert.equal(v062 ? liveLabel(state, now, K, frozen, runStatus) : liveLabel(state, tracker, now, K, frozen), expected.label, scenario.name);
    const rowCounts = {}, rejected = {};
    for (const row of verification.rows) {
      rowCounts[row.status] = (rowCounts[row.status] ?? 0) + 1;
      if (["malformed", "oversize"].includes(row.status)) {
        const reason = row.reasons.join("+");
        rejected[reason] = (rejected[reason] ?? 0) + 1;
      }
    }
    assert.deepEqual(rowCounts, expected.row_counts, scenario.name);
    assert.deepEqual(rejected, expected.rejected, scenario.name);
  }
  console.log(`PASS HTTP ${scenario.name.split(" ")[0]}`);
}

const serverLogs = {
  log600: Array.from({ length: 600 }, (_, i) => i % 100 === 7
    ? Buffer.concat([Buffer.from(`{"row":${i},"raw":"`), Buffer.from([255, 254]), Buffer.from('"}')]) : Buffer.from(`{"row":${i}}`)),
  big: Array.from({ length: 100 }, () => Buffer.alloc(65535, "x")),
  huge1: [Buffer.alloc(4_194_304, "x")],
  exact65: Array.from({ length: 65 }, () => Buffer.alloc(65535, "x")),
  "c14-tail": Array.from({ length: 5 }, (_, i) => Buffer.from(`{"row":${i}}`)),
  "c14-done": Array.from({ length: 6 }, (_, i) => Buffer.from(`{"row":${i}}`)),
};
for (const item of vectors.server_cases) {
  const physical = serverLogs[item.file ?? item.log];
  write(physical);
  if (item.file === "c14-tail") appendFileSync(ledger, '{"row":5}');
  const page = await http(item.request, physical);
  assert.equal(page.status, item.expect.status, item.name);
  if (page.status === 200) {
    for (const [name, value] of Object.entries(item.expect.headers)) assert.equal(page.headers[name], value, item.name);
    assert.equal(sha(page.bodyBytes), item.expect.body_sha256, item.name);
  }
}
console.log(`PASS HTTP C7/C12/C14: ${vectors.server_cases.length} exact status cases`);

// The two producer regressions, composed with the actual step() implementation.
let state = initialState("run-v1");
const first = log("v1-first5"), following = bytesOf("v1-06");
writeFileSync(ledger, Buffer.concat([Buffer.from(joinRows(first)), following.subarray(0, 21)]));
let result = step(state, await http(request(state), first), 0);
assert.equal(result.outcome, "ok");
assert.equal(result.state.cursor, 5);
state = result.state;
appendFileSync(ledger, following.subarray(21));
result = step(state, await http(request(state), first), 1);
assert.equal(result.outcome, "ok");
assert.equal(result.state.cursor, 5);
appendFileSync(ledger, "\n");
result = step(state, await http(request(state), [...first, following]), 2);
assert.equal(result.outcome, "ok");
assert.equal(result.state.cursor, 6);
console.log("PASS HTTP incomplete tail through LF completion");

for (const size of [65537, 4 * 1024 * 1024 - 1, 4 * 1024 * 1024, 4 * 1024 * 1024 + 1]) {
  const physical = [bytesOf("v1-01"), Buffer.alloc(size, 255), bytesOf("v1-02")];
  write(physical);
  state = initialState("run-v1", { limit: 1 });
  for (let cursor = 0; cursor < physical.length; cursor += 1) {
    result = step(state, await http(request(state), physical), cursor);
    if (cursor === 1 && size >= 4 * 1024 * 1024) {
      assert.equal(result.outcome, "row_too_large");
      assert.equal(result.state.cursor, state.cursor);
      assert.equal(result.state.cursor_hash, state.cursor_hash);
      assert.deepEqual(result.state.rows, state.rows);
      assert.equal(request(result.state), null);
      break;
    }
    assert.equal(result.outcome, "ok");
    state = result.state;
  }
  if (size < 4 * 1024 * 1024) assert.equal(verifyRows(state, options).verification.rows.at(-1).status, "oversize");
}
console.log("PASS HTTP oversize rows below, at and above the page cap");
if (v062) {
  assert.ok(catchUpPages > 0 && finishedPolls > 0, "the v0.6.2 catch-up and finished-run cases ran");
  console.log(`PASS HTTP v0.6.2 rule 5: ${catchUpPages} catch-up pages never LIVE; ${statusPolls} run statuses read back from /api/view/runs (${finishedPolls} finished)`);
}
console.log(JSON.stringify({ scenarios: vectors.scenarios.length, serverCases: vectors.server_cases.length,
  validationDifferences: 0, requests, hashedPages, injectedPolls, extraRegressions: 2,
  ...(v062 ? { catchUpPages, statusPolls, finishedPolls } : {}) }));
