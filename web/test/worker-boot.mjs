// node web/test/worker-boot.mjs   (CI: the browser-verifier job)
// Boots the real sentilab-web Worker in the Workers runtime and checks it serves. Node unit tests import worker.js as
// a plain module and can't see what the runtime refuses at startup (a named export of the main module that isn't a
// handler, for one); `wrangler deploy --dry-run` only bundles, so it can't either. This script:
//   1. bundles it: wrangler deploy --dry-run --outdir <tmp> (no credentials, nothing uploaded);
//   2. runs it: wrangler dev on 127.0.0.1, with the /api upstream switched off (API_ORIGIN=none), and checks
//      - /sentilab/, /sentilab/package/, /sentilab/lab.js and /, and the Package view's 3D assets (render3d.mjs, the
//        door fixture, the vendored three.js), answer 200 with the exact Content-Security-Policy and the bytes in web/public;
//      - the agent pages serve with the asset layer's own types (/llms.txt, /agents.json, /agents/*.md and *.json), and
//        /agents/ plus the agent versions of / and /sentilab/package/ (Accept: markdown or JSON) serve their files with
//        the Worker's types; a browser's Accept gets the human page, with Vary, private caching and the Link header;
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
import { UNRECOGNIZED_CLIENT_UA } from "./client-fixture.mjs";

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
  try { const r = await fetch(`${BASE}/sentilab/`, { headers: { "user-agent": UNRECOGNIZED_CLIENT_UA } }); if (r.status) { ready = true; break; } } catch {}
  await sleep(500);
}
check("the Workers runtime starts and answers", ready && !/\[ERROR\]/.test(strip(log)), ready ? "" : `exited=${exited}`);

if (ready) {
  const file = (rel) => new Uint8Array(readFileSync(join(WEB, "public", rel)));
  const same = (a, b) => a.length === b.length && a.every((x, i) => x === b[i]);
  for (const [path, rel] of [["/sentilab/", "sentilab/index.html"], ["/sentilab/package/", "sentilab/package/index.html"], ["/sentilab/lab.js", "sentilab/lab.js"], ["/", "index.html"],
    ["/sentilab/package/render3d.mjs", "sentilab/package/render3d.mjs"], ["/sentilab/package/door-fixture.json", "sentilab/package/door-fixture.json"],
    ["/vendor/three/0.187.0/three.module.js", "vendor/three/0.187.0/three.module.js"], ["/vendor/three/0.187.0/three.core.js", "vendor/three/0.187.0/three.core.js"]]) {
    const r = await fetch(BASE + path, { headers: { "user-agent": UNRECOGNIZED_CLIENT_UA } });
    const body = new Uint8Array(await r.arrayBuffer());
    check(`GET ${path}: 200, the exact CSP, the bytes in web/public/${rel}`, r.status === 200 && r.headers.get("content-security-policy") === CSP && same(body, file(rel)),
      `${r.status} · csp ${r.headers.get("content-security-policy") === CSP ? "exact" : JSON.stringify(r.headers.get("content-security-policy"))}`);
  }
  // The agent pages: the files as the asset layer types them, and the agent versions the Worker negotiates.
  for (const [path, rel, type] of [["/llms.txt", "llms.txt", /^text[/]plain/], ["/agents.json", "agents.json", /^application[/]json/],
    ["/agents/index.md", "agents/index.md", /^text[/]markdown/], ["/agents/challenge.json", "agents/challenge.json", /^application[/]json/]]) {
    const r = await fetch(BASE + path);
    const body = new Uint8Array(await r.arrayBuffer());
    check(`GET ${path}: 200, ${type.source}, the bytes in web/public/${rel}`, r.status === 200 && type.test(r.headers.get("content-type") || "") && same(body, file(rel)),
      `${r.status} · ${r.headers.get("content-type")}`);
  }
  for (const [path, accept, rel, type] of [["/agents/", undefined, "agents/index.md", "text/markdown; charset=utf-8"],
    ["/", "text/markdown", "agents/index.md", "text/markdown; charset=utf-8"], ["/", "application/json", "agents/index.json", "application/json; charset=utf-8"],
    ["/sentilab/package/", "text/markdown", "agents/physics.md", "text/markdown; charset=utf-8"]]) {
    const r = await fetch(BASE + path, { headers: { "user-agent": UNRECOGNIZED_CLIENT_UA, ...(accept ? { accept } : {}) } });
    const body = new Uint8Array(await r.arrayBuffer());
    check(`GET ${path}${accept ? ` (Accept: ${accept})` : ""}: the agent version web/public/${rel}, ${type}, the exact CSP`,
      r.status === 200 && r.headers.get("content-type") === type && r.headers.get("content-security-policy") === CSP && same(body, file(rel)),
      `${r.status} · ${r.headers.get("content-type")}`);
  }
  // A browser's Accept: the human page, byte for byte, varying on Accept, kept out of shared caches, naming its agent version.
  const human = await fetch(`${BASE}/`, { headers: { "user-agent": UNRECOGNIZED_CLIENT_UA, accept: "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8" } });
  const humanBody = new Uint8Array(await human.arrayBuffer());
  check("GET / with a browser's Accept: the human page, with Vary: Accept, private caching and the Link header",
    human.status === 200 && same(humanBody, file("index.html")) && human.headers.get("vary") === "Accept, User-Agent, Signature, Signature-Input, Signature-Agent, Cookie, Accept-Language, Sec-Fetch-Mode, Sec-Fetch-Dest, Sec-Fetch-Site, Sec-CH-UA, Sec-CH-UA-Mobile, Sec-CH-UA-Platform, Referer"
      && human.headers.get("cache-control") === "private, no-store" && human.headers.get("link") === '</agents/>; rel="alternate"; type="text/markdown"',
    `${human.status} · vary ${human.headers.get("vary")} · cache-control ${human.headers.get("cache-control")} · link ${human.headers.get("link")}`);
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
