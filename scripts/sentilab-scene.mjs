#!/usr/bin/env node
// SentiLab scene CLI: build the Package view's scene from a replay, with the same verification and prefix rule as
// the page, but using the node REFERENCE verifier: VIEW ENVELOPE v0.5 (contracts/view-envelope-v0.5/view-envelope.mjs),
// after the v0.6.1 bytes-to-rows rule (contracts/view-envelope-v0.6.1/paging.mjs verifyReplayBytes), exactly the path the
// page takes through the browser ports of both.
// Output is JSON on stdout. This is the CLI half of SLAB-026's CLI+MCP; the MCP half comes later through the
// generated bridge, so the command table stays small and every result is one JSON object.
//
//   node scripts/sentilab-scene.mjs build  <replay.jsonl> [--run <id>] [--pins test] [--key <key_id>=<hex>] [--at <seq>] [--strict]
//   node scripts/sentilab-scene.mjs export <replay.jsonl> --out <scene.json> [same options]
//   node scripts/sentilab-scene.mjs help
//
// Trust: the production pins come from web/public/sentilab/view-pins.js, as in the page. A served public key may be
// given with --key; it is used only if its sha256 matches a pin. --pins test uses the vectors' "core" test key, which
// anyone can derive; the output says so. Exit codes: 0 ok; 1 usage or input error; with --strict, 2 for a broken
// prefix (chain) and 3 for refused values (a verified value with an unsupported unit or out of range: scene.errors).
// Lengths are exported in mm and temperatures in °C; a refused value is listed, never exported as a number.
import { createHash, createPrivateKey, createPublicKey } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { basename } from "node:path";
import { fileURLToPath } from "node:url";

// ── the verifier: the v0.5 reference, behind the v0.6 reference's bytes-to-rows (no verification of its own) ──────
import { checkLine, keySha256, VERSION } from "../contracts/view-envelope-v0.5/view-envelope.mjs";
import { verifyReplayBytes, splitRows, rowText } from "../contracts/view-envelope-v0.6.1/paging.mjs";
import { canonical } from "../contracts/contract-0.2/resultcheck.mjs";
import { VIEW_PINS } from "../web/public/sentilab/view-pins.js";
import { buildScene, sceneAt, runFrame, SCENE_VERSION } from "../web/public/sentilab/package/scene.mjs";

// The reference returns rows ({ seq, event_id, status, reasons, projected }), not envelopes. The prefix envelopes are
// read back from the rows that pass the input checks: for each projected row, the envelopes with its seq and event_id.
// Byte-identical duplicates count once and conflicts are never projected, so each projected row must map to exactly
// one envelope (by canonical bytes); anything else fails closed with an empty prefix.
const MAX_LINE_BYTES = 64 * 1024;
function checkedEnvelopes(rows) {
  const out = [];
  for (const row of rows) {
    const text = row.length <= MAX_LINE_BYTES ? rowText(row) : null;
    const checked = text === null ? null : checkLine(text);
    if (checked?.ok) out.push(checked.value);
  }
  return out;
}
function prefixFromRows(envelopes, verification) {
  const projected = verification.rows.filter((r) => r.projected);
  const prefix = [];
  for (const row of projected) {
    const found = envelopes.filter((e) => e.event.seq === row.seq && e.event.event_id === row.event_id);
    if (found.length === 0 || new Set(found.map((e) => canonical(e))).size !== 1) return null;
    prefix.push(found[0]);
  }
  return prefix;
}

// The vectors' test-key rule: seed = sha256("sentilab-view-test-key:" + name); Ed25519 from that seed (a fixed
// 16-byte PKCS#8 header, then the seed). Nothing is stored; anyone can derive it, so it is never a production pin.
const PKCS8_ED25519_HEADER = Buffer.from([0x30, 0x2e, 0x02, 0x01, 0x00, 0x30, 0x05, 0x06, 0x03, 0x2b, 0x65, 0x70, 0x04, 0x22, 0x04, 0x20]);
const SPKI_ED25519_HEADER = Buffer.from([0x30, 0x2a, 0x30, 0x05, 0x06, 0x03, 0x2b, 0x65, 0x70, 0x03, 0x21, 0x00]);
function testPublicKey(name) {
  const seed = createHash("sha256").update(`sentilab-view-test-key:${name}`, "utf8").digest();
  return createPublicKey(createPrivateKey({ key: Buffer.concat([PKCS8_ED25519_HEADER, seed]), format: "der", type: "pkcs8" }));
}
const publicKeyFromHex = (hex) => createPublicKey({ key: Buffer.concat([SPKI_ED25519_HEADER, Buffer.from(hex, "hex")]), format: "der", type: "spki" });

export function trustFor({ pins = "production", served = [] } = {}) {
  if (pins === "test") {
    const pub = testPublicKey("core");
    return { mode: "test", note: "TEST KEYS: derived from a public seed rule; anyone can sign with them; never production", pins: [{ key_id: "core", key_sha256: keySha256(pub) }], keys: { core: pub } };
  }
  const keys = {};
  for (const { keyId, hex } of served) keys[keyId] = publicKeyFromHex(hex);
  return {
    mode: "production",
    note: VIEW_PINS.length === 0 ? "no production key is pinned yet, so no envelope can verify" : served.length ? "served key(s) checked against the page's pins" : "production pin set, but no key was served (--key)",
    pins: VIEW_PINS.map((p) => ({ key_id: p.key_id, key_sha256: p.key_sha256 })),
    keys,
  };
}

// Verify, take the projectable prefix, build the scene. Same prefix rule as the page (VIEW ENVELOPE rule 1).
// bytes: the replay file's raw bytes (Uint8Array). Over 64 MiB, nothing is split or decoded.
export function sceneFromReplay(bytes, { runId = null, trust, at = null } = {}) {
  const rows = splitRows(bytes);
  const envelopes = checkedEnvelopes(rows);
  let runFrom = "requested";
  if (!runId) {
    const first = [...envelopes].sort((a, b) => a.event.seq - b.event.seq)[0];
    runId = first ? first.run.run_id : "";
    runFrom = "file";
  }
  const read = verifyReplayBytes(bytes, { runId, pins: trust.pins, keys: trust.keys });
  if (!read.ok) throw new UsageError(`the replay file is over the 64 MiB cap (${read.reason}), so it was not read`);
  const v = read.verification;
  const recovered = prefixFromRows(envelopes, v);
  const prefix = recovered ?? [];
  const count = prefix.length;
  const projection = recovered ? v.projection : null;
  let scene;
  if (at !== null) {
    const upTo = prefix.filter((env) => env.event.seq <= at).length;
    scene = sceneAt(prefix, upTo, runFrame(prefix, projection));
  } else {
    scene = buildScene(prefix, projection);
  }
  const after = v.rows[count] ?? null;
  return {
    run: { id: runId, from: runFrom },
    trust: { mode: trust.mode, note: trust.note },
    verification: {
      contract: VERSION,
      envelopes: v.rows.length,
      verified: v.rows.filter((r) => r.status === "verified").length,
      chain_ok: v.chain_ok,
      prefix_end: v.prefix_end,
      frozen: v.frozen,
      label: v.label,
      first_break: after ? { seq: after.seq, status: after.status, reasons: after.reasons } : null,
      duplicates: v.duplicates ?? 0,
      projection_error: v.projection_error,
    },
    // Not chain validity: values in verified envelopes that the scene refused to place or colour.
    value_errors: scene.errors.length,
    scene,
  };
}

// ── command table ───────────────────────────────────────────────────────────────────────────────────────────
const OPTIONS = {
  "--run": { arg: "id", help: "run id the view requests (default: the run named by the lowest-seq envelope, reported as from=file)" },
  "--pins": { arg: "test", help: "use the derivable TEST key instead of the production pins (local checks only)" },
  "--key": { arg: "key_id=hex", help: "a served raw Ed25519 public key (64 hex); used only if its sha256 matches a pin", repeat: true },
  "--at": { arg: "seq", help: "the scene after seq N of the prefix (default: the whole prefix)" },
  "--strict": { help: "exit 2 if the prefix does not cover every envelope (a broken or frozen chain); exit 3 if the scene refused any value (scene.errors)" },
  "--out": { arg: "file", help: "export: where to write the scene JSON" },
};
export const COMMANDS = {
  build: { usage: "build <replay.jsonl> [--run <id>] [--pins test] [--key <key_id>=<hex>] [--at <seq>] [--strict]", help: "print { run, trust, verification, scene } as JSON" },
  export: { usage: "export <replay.jsonl> --out <scene.json> [--run <id>] [--pins test] [--key ...] [--at <seq>] [--strict]", help: "write the same JSON to a file; print a short summary" },
  help: { usage: "help", help: "print this command table as JSON" },
};

function parseArgs(argv) {
  const [command, ...rest] = argv;
  const opts = { positional: [], key: [] };
  for (let i = 0; i < rest.length; i += 1) {
    const a = rest[i];
    if (!a.startsWith("--")) { opts.positional.push(a); continue; }
    const spec = OPTIONS[a];
    if (!spec) throw new UsageError(`unknown option ${a}`);
    const name = a.slice(2);
    if (!spec.arg) { opts[name] = true; continue; }
    const value = rest[i + 1];
    if (value === undefined || value.startsWith("--")) throw new UsageError(`${a} needs ${spec.arg}`);
    i += 1;
    if (spec.repeat) opts[name].push(value); else opts[name] = value;
  }
  return { command, opts };
}
class UsageError extends Error {}

export function run(argv) {
  const { command, opts } = parseArgs(argv);
  if (!command || command === "help" || command === "--help") {
    return { code: 0, out: { tool: "sentilab-scene", scene_version: SCENE_VERSION, contract: VERSION, commands: COMMANDS, options: OPTIONS } };
  }
  if (!Object.hasOwn(COMMANDS, command)) throw new UsageError(`unknown command ${command}`);
  const file = opts.positional[0];
  if (!file) throw new UsageError(`${command} needs a replay file`);
  if (opts.pins !== undefined && opts.pins !== "test") throw new UsageError("--pins only accepts 'test'");
  if (command === "export" && !opts.out) throw new UsageError("export needs --out <file>");
  const served = opts.key.map((k) => {
    const m = /^([^=]{1,128})=([0-9a-f]{64})$/.exec(k);
    if (!m) throw new UsageError("--key must be <key_id>=<64 lowercase hex>");
    return { keyId: m[1], hex: m[2] };
  });
  const at = opts.at === undefined ? null : Number(opts.at);
  if (at !== null && !(Number.isSafeInteger(at) && at >= 0)) throw new UsageError("--at needs a seq (integer >= 0)");
  let bytes;
  try { bytes = new Uint8Array(readFileSync(file)); } catch (error) { throw new UsageError(`cannot read ${file}: ${error.code ?? error.message}`); }
  const trust = trustFor({ pins: opts.pins === "test" ? "test" : "production", served });
  const result = { command, input: basename(file), ...sceneFromReplay(bytes, { runId: opts.run ?? null, trust, at }) };
  const code = !opts.strict ? 0 : result.verification.frozen ? 2 : result.value_errors > 0 ? 3 : 0;
  if (command === "export") {
    const body = `${JSON.stringify(result, null, 2)}\n`;
    writeFileSync(opts.out, body);
    return { code, out: { command, out: opts.out, bytes: Buffer.byteLength(body), run: result.run, trust: result.trust.mode, verification: result.verification, value_errors: result.value_errors } };
  }
  return { code, out: result };
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  try {
    const { code, out } = run(process.argv.slice(2));
    process.stdout.write(`${JSON.stringify(out, null, 2)}\n`);
    process.exitCode = code;
  } catch (error) {
    const usage = error instanceof UsageError;
    process.stderr.write(`${JSON.stringify({ error: usage ? "usage" : "failed", message: String(error?.message ?? error), commands: usage ? COMMANDS : undefined })}\n`);
    process.exitCode = 1;
  }
}
