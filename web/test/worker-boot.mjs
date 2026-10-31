// node web/test/worker-boot.mjs   (CI: the browser-verifier job)
// Boots the real sentilab-web Worker in the Workers runtime and checks it serves. Node unit tests import worker.js as
// a plain module and can't see what the runtime refuses at startup (a named export of the main module that isn't a
// handler, for one); `wrangler deploy --dry-run` only bundles, so it can't either. This script:
//   1. bundles it: wrangler deploy --dry-run --outdir <tmp> (no credentials, nothing uploaded);
//   2. runs it: wrangler dev on 127.0.0.1, with the /api upstream switched off (API_ORIGIN=none), and checks
//      - /sentilab/, /sentilab/package/, /sentilab/lab.js and / answer 200 with the exact Content-Security-Policy and
//        the bytes in web/public;
//      - /api/view/runs reaches the proxy (503 "API origin not configured": the upstream is off) with no CSP added;
//      - a write to /api is refused (405 read_only) with no CSP added;
//      - the runtime logged no error.
// Exit 0 when every check passes; 1 (with the runtime's log) otherwise. WRANGLER_VERSION pins the CLI (default below).
import { spawn, spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { CSP } from "../src/csp.js";

const WEB = join(dirname(fileURLToPath(import.meta.url)), "..");
const VERSION = process.env.WRANGLER_VERSION || "4.156.0";
const PORT = Number(process.env.WORKER_BOOT_PORT || 8811);
const BASE = `http://127.0.0.1:${PORT}`;
const env = { ...process.env, WRANGLER_SEND_METRICS: "false", CI: "true", NO_COLOR: "1" };
const npx = process.platform === "win32" ? "npx.cmd" : "npx";
const strip = (s) => s.replace(/\x1b\[[0-9;]*m/g, "");
const failures = [];
const check = (name, ok, detail = "") => { console.log(`${ok ? "PASS" : "FAIL"} ${name}${detail ? ` · ${detail}` : ""}`); if (!ok) failures.push(name); };

// 1. The bundle.
const out = mkdtempSync(join(tmpdir(), "worker-dry-"));
const dry = spawnSync(npx, ["--yes", `wrangler@${VERSION}`, "deploy", "--dry-run", "--outdir", out], { cwd: WEB, env, encoding: "utf8", shell: process.platform === "win32" });
check(`wrangler ${VERSION} deploy --dry-run bundles the Worker`, dry.status === 0, dry.status === 0 ? "" : strip(`${dry.stdout}\n${dry.stderr}`).slice(-1500));
rmSync(out, { recursive: true, force: true });

// 2. The runtime.
let log = "";
const dev = spawn(npx, ["--yes", `wrangler@${VERSION}`, "dev", "--ip", "127.0.0.1", "--port", String(PORT), "--var", "API_ORIGIN:none"],
  { cwd: WEB, env, shell: process.platform === "win32", detached: process.platform !== "win32" });
dev.stdout.on("data", (d) => { log += d; });
dev.stderr.on("data", (d) => { log += d; });
let exited = null;
dev.on("exit", (code) => { exited = code ?? -1; });
const stop = () => {
  if (exited !== null) return;
  if (process.platform === "win32") spawnSync("taskkill", ["/pid", String(dev.pid), "/T", "/F"]);
  else try { process.kill(-dev.pid, "SIGTERM"); } catch {}
};

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let ready = false;
for (let i = 0; i < 120 && exited === null && !/\[ERROR\]/.test(log); i += 1) {
  try { const r = await fetch(`${BASE}/sentilab/`); if (r.status) { ready = true; break; } } catch {}
  await sleep(500);
}
check("the Workers runtime starts and answers", ready && !/\[ERROR\]/.test(strip(log)), ready ? "" : `exited=${exited}`);

if (ready) {
  const file = (rel) => new Uint8Array(readFileSync(join(WEB, "public", rel)));
  const same = (a, b) => a.length === b.length && a.every((x, i) => x === b[i]);
  for (const [path, rel] of [["/sentilab/", "sentilab/index.html"], ["/sentilab/package/", "sentilab/package/index.html"], ["/sentilab/lab.js", "sentilab/lab.js"], ["/", "index.html"]]) {
    const r = await fetch(BASE + path);
    const body = new Uint8Array(await r.arrayBuffer());
    check(`GET ${path}: 200, the exact CSP, the bytes in web/public/${rel}`, r.status === 200 && r.headers.get("content-security-policy") === CSP && same(body, file(rel)),
      `${r.status} · csp ${r.headers.get("content-security-policy") === CSP ? "exact" : JSON.stringify(r.headers.get("content-security-policy"))}`);
  }
  const api = await fetch(`${BASE}/api/view/runs`);
  const apiText = await api.text();
  check("GET /api/view/runs reaches the proxy (upstream off: 503) with no CSP added", api.status === 503 && apiText === "API origin not configured" && api.headers.get("content-security-policy") === null, `${api.status} ${apiText}`);
  const write = await fetch(`${BASE}/api/runs`, { method: "POST", body: "{}" });
  const writeJson = await write.json().catch(() => null);
  check("POST /api/runs is refused read-only (405) with no CSP added", write.status === 405 && writeJson?.error === "read_only" && write.headers.get("content-security-policy") === null, String(write.status));
  check("the runtime logged no error", !/\[ERROR\]/.test(strip(log)));
}
stop();
await sleep(500);
if (failures.length) {
  console.log(`\n--- wrangler dev log (last 3000 chars) ---\n${strip(log).slice(-3000)}`);
  console.log(`\nworker boot: ${failures.length} check(s) failed`);
  process.exit(1);
}
console.log("\nworker boot: all checks passed");
process.exit(0);
