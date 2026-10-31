// Real-route composition with the unchanged PR26 reducer and vector data.
// Run through `python -m app.check_view_paging [contract-dir]` (starts a local HTTP server).
import assert from "node:assert/strict";
import { createHash, createPrivateKey, createPublicKey } from "node:crypto";
import { appendFileSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

const [reference, origin, root] = process.argv.slice(2);
const { initialState, request, step, joinRows, verifyRows, liveLabel } = await import(pathToFileURL(join(reference, "paging.mjs")));
const { progressTracker } = await import(pathToFileURL(join(reference, "../view-envelope-v0.5/view-envelope.mjs")));
const vectors = JSON.parse(readFileSync(join(reference, "vectors-paging.json")));
const sha = (bytes) => createHash("sha256").update(bytes).digest("hex");
assert.equal(sha(readFileSync(join(reference, "VIEW-ENVELOPE.md"))), vectors.contract_sha256);
const bytesOf = (id) => {
  const row = vectors.rows[id];
  return row.text !== undefined ? Buffer.from(row.text) : row.base64 !== undefined
    ? Buffer.from(row.base64, "base64") : Buffer.alloc(row.bytes, row.fill);
};
const expand = (ids) => ids.flatMap((id) => Array.isArray(id) ? Array(id[1]).fill(id[0]) : [id]).map(bytesOf);
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

// Only the public half of the reference fixture key survives this expression.
const key = createPublicKey(createPrivateKey({
  key: Buffer.concat([Buffer.from("302e020100300506032b657004220420", "hex"),
    createHash("sha256").update("sentilab-view-test-key:core").digest()]),
  format: "der", type: "pkcs8",
}));
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

for (const scenario of vectors.scenarios) {
  let state = initialState("run-v1", { limit: scenario.limit });
  const tracker = progressTracker();
  for (const [index, poll] of scenario.polls.entries()) {
    const now = Date.UTC(2026, 9, 31, 12) + poll.t_s * 1000;
    const expected = scenario.trace[index];
    let count = 0;
    for (; count < 16;) {
      const req = request(state);
      if (req === null) break;
      const result = step(state, await serve(poll.server, req), now);
      state = result.state;
      const fetch = expected.fetches[count++];
      assert.equal(result.outcome, fetch.outcome, scenario.name);
      assert.equal(result.newRows.length, fetch.new_rows, scenario.name);
      if (result.outcome === "ok") tracker.poll({ nowMs: now, ok: true, K: verifyRows(state, options).K, received: result.newRows.length });
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
    assert.equal(liveLabel(state, tracker, now, K, frozen), expected.label, scenario.name);
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
console.log(JSON.stringify({ scenarios: vectors.scenarios.length, serverCases: vectors.server_cases.length,
  validationDifferences: 0, requests, hashedPages, injectedPolls, extraRegressions: 2 }));
