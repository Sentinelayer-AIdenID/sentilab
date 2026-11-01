// node --test web/test/livelab-route.test.mjs
// The Live Lab route (web/src/worker.js), through the real Worker over the real files in web/public:
//   1. A person at / (GET or HEAD), and /?view=human from any client, gets a same-origin 302 to /sentilab/live/ with
//      the headers the human page at / had: the exact CSP, Vary on everything the edge classifies on, private, no-store,
//      the Link to the agent version, and with ?view=human the sl_view=human cookie.
//   2. /lab is the earlier replay page that / served before (web/public/index.html), byte for byte, with the exact
//      CSP. It has no agent version, so it is the same for every client: no Vary, no Link, the asset layer's caching.
//   3. Agents and machine requests at / (the wall, the agent version) and every other route answer byte for byte what
//      the Worker answered before this change: a copy of web/src whose human page is the asset itself again. Unsafe
//      methods at / and /lab answer what / answered before.
//   4. HEAD mirrors GET; /sentilab/live/ is a plain asset, so the redirect ends there (no loop).
//   5. Caches keep the representations at / apart: the redirect and the agent versions are private, no-store and
//      vary on the same request headers.
//   6. The wall's "the earlier demo" link is /lab, in HTML, markdown and JSON.
import { test } from "node:test";
import assert from "node:assert/strict";
import { cpSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import { CSP } from "../src/csp.js";
import { BASE, BROWSER, UA, agent, file, installApi, mint, same, setup } from "./door-harness.mjs";
import worker from "../src/worker.js";

const SRC = join(dirname(fileURLToPath(import.meta.url)), "..", "src");
const LIVE_LAB = "/sentilab/live/";
const LIVE_3D = `${BASE}/sentilab/package/?feed=door&src=live`;
const LIVE_LAB_URL = `${BASE}${LIVE_LAB}`;
const HUMAN_COOKIE = "sl_view=human; Max-Age=1800; Path=/; Secure; SameSite=Lax";
const LINK = '</agents/>; rel="alternate"; type="text/markdown"';
const VARY = "Accept, User-Agent, Signature, Signature-Input, Signature-Agent, Cookie, Accept-Language, Sec-Fetch-Mode, Sec-Fetch-Dest, Sec-Fetch-Site, Sec-CH-UA, Sec-CH-UA-Mobile, Sec-CH-UA-Platform, Referer";
const HTML = "text/html; charset=utf-8";
// The classifier's documented Safari trade-offs (edge.test.mjs): real browsers it leaves unclassified, so they get the
// human page by Accept.
const SAFARI = Object.freeze({ "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.6 Safari/605.1.15",
  accept: "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", "accept-language": "en-US,en;q=0.9", "accept-encoding": "gzip",
  connection: "keep-alive", "upgrade-insecure-requests": "1", "cache-control": "max-age=0" });
const IPHONE = Object.freeze({ "user-agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
  accept: "text/html", "accept-language": "en-US", "accept-encoding": "gzip", connection: "keep-alive", "upgrade-insecure-requests": "1", "cache-control": "max-age=0" });
const GOOGLEBOT = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)";
const plain = (accept) => ({ headers: { "user-agent": "unrecognized-client", ...(accept ? { accept } : {}) } });
const head = (init) => ({ ...init, method: "HEAD" });
const sorted = (entries) => [...entries].sort(([a, x], [b, y]) => (a === b ? (x < y ? -1 : x > y ? 1 : 0) : a < b ? -1 : 1));

// One request through a Worker, with a fresh environment (the door harness's: real files, the stand-in intake).
async function answer(handler, resetDoor, path, init = {}, extra = {}) {
  const s = setup(extra);
  resetDoor?.();
  const res = await handler.fetch(new Request(BASE + path, init), s.env, s.ctx);
  const bytes = new Uint8Array(await res.arrayBuffer());
  await s.drain();
  return { status: res.status, headers: sorted(res.headers), bytes, get: (name) => res.headers.get(name) };
}
const now = (path, init, extra) => answer(worker, null, path, init, extra);

// The Worker as it answered before this change: a copy of web/src in which humanAsset gets the human page from the
// asset layer again (the one line main had at b66fb56), so a difference can only come from the human page itself.
const SEAM = "const res = await humanVersion(request, env);";
const BEFORE = "const res = await env.ASSETS.fetch(request);";
let built;
function beforeWorker() {
  built ??= (async () => {
    const source = readFileSync(join(SRC, "worker.js"), "utf8");
    assert.equal(source.split(SEAM).length - 1, 1, "worker.js takes the human page from humanVersion at exactly one place");
    const dir = mkdtempSync(join(tmpdir(), "livelab-before-"));
    try {
      cpSync(SRC, dir, { recursive: true });
      writeFileSync(join(dir, "worker.js"), source.replace(SEAM, BEFORE));
      const handler = (await import(pathToFileURL(join(dir, "worker.js")).href)).default;
      const { resetDoorState } = await import(pathToFileURL(join(dir, "door", "door.js")).href);
      return { handler, resetDoorState };
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  })();
  return built;
}
async function was(path, init, extra) {
  const { handler, resetDoorState } = await beforeWorker();
  return answer(handler, resetDoorState, path, init, extra);
}

// What a person's request at / gets now: the redirect, and every header the human page had except its body's type.
function redirectFrom(earlier) {
  return sorted([...earlier.headers.filter(([name]) => name !== "content-type"), ["location", LIVE_LAB]]);
}
function assertRedirect(r, why, { cookie = false } = {}) {
  assert.equal(r.status, 302, why);
  assert.equal(r.get("location"), LIVE_LAB, why);
  assert.equal(r.bytes.length, 0, `${why}: no body`);
  assert.deepEqual(r.headers, sorted([["cache-control", "private, no-store"], ["content-security-policy", CSP], ["link", LINK],
    ["location", LIVE_LAB], ["vary", VARY], ...(cookie ? [["set-cookie", HUMAN_COOKIE]] : [])]), `${why}: headers`);
}

const PEOPLE = [
  ["/", { headers: BROWSER }, "a desktop browser"],
  ["/", { headers: SAFARI }, "Safari, unclassified, by its Accept"],
  ["/", { headers: IPHONE }, "iPhone Safari, unclassified, by its Accept"],
  ["/?view=human", { headers: BROWSER }, "a browser with ?view=human"],
  ["/?view=human", agent(UA.gptbot), "the human override by query, from an agent"],
  ["/", agent(UA.gptbot, { cookie: "x=1; sl_view=human" }), "the human override by cookie, from an agent"],
];

test("1. a person at / and /?view=human gets a same-origin 302 to /sentilab/live/, with the human page's headers and the cookie", async (t) => {
  installApi(t);
  for (const [path, init, why] of PEOPLE) {
    const r = await now(path, init);
    assertRedirect(r, why, { cookie: path.includes("view=human") });
    assert.equal(new URL(r.get("location"), BASE + path).origin, BASE, `${why}: same origin`);
  }
});

test("4. HEAD mirrors GET: the same 302 at / and /?view=human, the same 200 at /lab, no body", async (t) => {
  installApi(t);
  for (const [path, init, status] of [["/", { headers: BROWSER }, 302], ["/", { headers: IPHONE }, 302], ["/?view=human", { headers: BROWSER }, 302],
    ["/?view=human", agent(UA.gptbot), 302], ["/lab", { headers: BROWSER }, 200], ["/lab", agent(UA.gptbot), 200], ["/", agent(UA.gptbot), 200]]) {
    const [get, got] = [await now(path, init), await now(path, head(init))];
    assert.equal(get.status, status, `GET ${path}`);
    assert.equal(got.status, get.status, `HEAD ${path}: status`);
    assert.deepEqual(got.headers, get.headers, `HEAD ${path}: headers`);
    assert.equal(got.bytes.length, 0, `HEAD ${path}: no body`);
  }
});

test("2. /lab is the earlier replay page, byte for byte, with the exact CSP, the same for every client", async (t) => {
  installApi(t);
  const page = file("index.html");
  for (const init of [{ headers: BROWSER }, { headers: SAFARI }, agent(UA.gptbot), agent(UA.claudebot), agent(UA.curl), { headers: {} },
    agent(GOOGLEBOT), plain("text/markdown"), plain("application/json"), agent(UA.gptbot, { cookie: "sl_view=human" })]) {
    const r = await now("/lab", init);
    const who = init.headers["user-agent"] ?? "no user agent";
    assert.equal(r.status, 200, who);
    assert.ok(same(r.bytes, page), `${who}: web/public/index.html byte for byte`);
    assert.deepEqual(r.headers, [["content-security-policy", CSP], ["content-type", HTML]], `${who}: the asset layer's headers and the CSP, nothing negotiated`);
  }
});

test("2. /lab answers what a person got at / before, less the headers of a page with an agent version (Vary, private, Link)", async (t) => {
  installApi(t);
  for (const init of [{ headers: BROWSER }, { headers: SAFARI }]) {
    const [earlier, lab] = [await was("/", init), await now("/lab", init)];
    assert.ok(same(earlier.bytes, file("index.html")), "the earlier page at / (the copy without the change)");
    assert.equal(lab.status, earlier.status);
    assert.ok(same(lab.bytes, earlier.bytes), "the same bytes");
    assert.deepEqual(lab.headers, earlier.headers.filter(([name]) => !["vary", "cache-control", "link"].includes(name)), "the same headers but the negotiated ones");
  }
});

test("4. no loop: / redirects once, to /sentilab/live/, a plain asset for every client; /sentilab/live is left to the asset layer", async (t) => {
  installApi(t);
  const page = file("sentilab/live/index.html");
  for (const [path, init, why] of PEOPLE) {
    const first = await now(path, init);
    assert.equal(first.status, 302, why);
    const target = new URL(first.get("location"), BASE + path);
    assert.equal(target.pathname + target.search, LIVE_LAB, why);
    const live = await now(target.pathname, init);
    assert.equal(live.status, 200, `${why}: the Live Lab answers`);
    assert.equal(live.get("location"), null, `${why}: and does not redirect`);
    assert.ok(same(live.bytes, page), `${why}: web/public/sentilab/live/index.html`);
    assert.equal(live.get("content-security-policy"), CSP);
  }
  for (const init of [agent(UA.gptbot), plain("text/markdown"), { headers: BROWSER, method: "HEAD" }]) {
    const live = await now(LIVE_LAB, init);
    assert.deepEqual([live.status, live.get("location")], [200, null], init.headers["user-agent"]);
  }
  // Without the slash, the Worker hands the path to the asset layer exactly as it hands it /sentilab/package (the
  // deployed asset layer answers both with a 307 to the slash; web/test/worker-boot.mjs checks that in the runtime).
  const [bare, pkg] = [await now("/sentilab/live", { headers: BROWSER }), await now("/sentilab/package", { headers: BROWSER })];
  assert.deepEqual([bare.status, bare.headers], [pkg.status, pkg.headers]);
});

// Every client and path below is answered by both Workers; GET decides whether the earlier one served the replay page.
const CLIENTS = [
  ["browser", { headers: BROWSER }], ["safari", { headers: SAFARI }], ["iphone", { headers: IPHONE }], ["gptbot", agent(UA.gptbot)],
  ["claudebot", agent(UA.claudebot)], ["chatgpt-user", agent(UA.chatgptUser)], ["curl", agent(UA.curl)], ["requests", agent(UA.requests)],
  ["no user agent", { headers: {} }], ["googlebot", agent(GOOGLEBOT)], ["gptbot markdown", agent(UA.gptbot, { accept: "text/markdown" })],
  ["curl json", agent(UA.curl, { accept: "application/json" })], ["plain markdown", plain("text/markdown")], ["plain json", plain("application/json")],
  ["plain html", plain("text/html")], ["plain, no accept", plain()], ["plain markdown preferred", plain("text/html;q=0.5, text/markdown;q=0.9")],
  ["gptbot with the cookie", agent(UA.gptbot, { cookie: "sl_view=human" })],
];

test("3. agents and machine requests at /, and every other route, are byte for byte what the Worker answered before", async (t) => {
  installApi(t);
  const token = await mint("read");
  const page = file("index.html");
  const changed = [];
  for (const path of ["/", "/?view=human", `/?t=${token}`, "/sentilab/", "/sentilab/package/", LIVE_LAB, "/sentilab/live", "/agents", "/agents/",
    "/agents/index.md", "/agents/intent", "/agents/board", "/index.html", "/styles.css", "/nope", "/api/view/runs"]) {
    for (const [who, init] of CLIENTS) {
      const earlierGet = await was(path, init);
      const servedThePage = earlierGet.status === 200 && same(earlierGet.bytes, page);
      for (const method of ["GET", "HEAD"]) {
        const [earlier, current] = method === "GET" ? [earlierGet, await now(path, init)] : [await was(path, head(init)), await now(path, head(init))];
        const why = `${method} ${path.slice(0, 40)} (${who})`;
        if (servedThePage && path.split("?")[0] === "/") {
          changed.push(why);
          assert.equal(current.status, 302, why);
          assert.deepEqual(current.headers, redirectFrom(earlier), `${why}: the human page's headers, less its type, plus the location`);
          assert.equal(current.bytes.length, 0, why);
        } else {
          assert.equal(current.status, earlier.status, `${why}: status`);
          assert.deepEqual(current.headers, earlier.headers, `${why}: headers`);
          assert.ok(same(current.bytes, earlier.bytes), `${why}: body`);
        }
      }
    }
  }
  // The changed answers are exactly the people's: browsers and unclassified clients asking for HTML, and the override.
  const root = (path) => changed.filter((c) => c.split(" ")[1] === path).map((c) => c.slice(c.indexOf("(") + 1, -1));
  const people = ["browser", "safari", "iphone", "plain html", "plain, no accept", "gptbot with the cookie"];
  assert.deepEqual([...new Set(root("/"))], people);
  assert.deepEqual([...new Set(root("/?view=human"))], CLIENTS.map(([who]) => who), "?view=human is the human page for every client");
  assert.deepEqual([...new Set(root(`/?t=${token}`.slice(0, 40)))], people, "a token-bearing / is the same split");
  // The door closed (no usable DOOR_TOKEN_KEY): agents keep their agent version, unchanged.
  for (const init of [agent(UA.gptbot), agent(UA.curl, { accept: "application/json" })]) {
    const [earlier, current] = [await was("/", init, { DOOR_TOKEN_KEY: undefined }), await now("/", init, { DOOR_TOKEN_KEY: undefined })];
    assert.deepEqual([current.status, current.headers], [earlier.status, earlier.headers]);
    assert.ok(same(current.bytes, earlier.bytes));
  }
});

test("3. unsafe methods at / and /lab answer exactly what / answered before", async (t) => {
  installApi(t);
  for (const method of ["POST", "PUT", "DELETE", "OPTIONS", "PATCH"]) {
    for (const init of [{ headers: BROWSER }, agent(UA.gptbot), plain("text/markdown")]) {
      for (const [path, before] of [["/", "/"], ["/lab", "/"], ["/?view=human", "/?view=human"], ["/lab?view=human", "/?view=human"]]) {
        const [earlier, current] = [await was(before, { ...init, method }), await now(path, { ...init, method })];
        const why = `${method} ${path} (${init.headers["user-agent"]})`;
        assert.equal(current.status, earlier.status, why);
        assert.deepEqual(current.headers, earlier.headers, why);
        assert.ok(same(current.bytes, earlier.bytes), why);
        assert.equal(current.get("location"), null, `${why}: never redirected`);
      }
    }
  }
});

test("3. agents at / still get the wall or the agent version: the known files, never the redirect", async (t) => {
  installApi(t);
  const token = await mint("read");
  for (const [path, init, rel, type, extra] of [
    ["/", plain("text/markdown"), "agents/index.md", "text/markdown; charset=utf-8"],
    ["/", plain("application/json"), "agents/index.json", "application/json; charset=utf-8"],
    ["/", agent(GOOGLEBOT), "agents/index.md", "text/markdown; charset=utf-8"],
    [`/?t=${token}`, agent(UA.gptbot), "agents/index.md", "text/markdown; charset=utf-8"],
    ["/", agent(UA.gptbot), "agents/index.md", "text/markdown; charset=utf-8", { DOOR_TOKEN_KEY: undefined }],
  ]) {
    const r = await now(path, init, extra);
    assert.equal(r.status, 200, `${path} ${rel}`);
    assert.ok(same(r.bytes, file(rel)), rel);
    assert.equal(r.get("content-type"), type);
    assert.equal(r.get("content-security-policy"), CSP);
    assert.equal(r.get("location"), null);
  }
  for (const ua of [UA.gptbot, UA.claudebot, UA.chatgptUser, UA.curl, UA.requests]) {
    const r = await now("/", agent(ua));
    assert.deepEqual([r.status, r.get("content-type"), r.get("location")], [200, HTML, null], ua);
    assert.match(new TextDecoder().decode(r.bytes), /<h1>Before you continue: what are you here to do\?<\/h1>/, ua);
  }
});

test("5. caches keep the representations at / apart: the redirect and the agent versions are all private, no-store, varying alike", async (t) => {
  installApi(t);
  const names = (r) => new Set(r.get("vary").split(/,\s*/).map((name) => name.toLowerCase()));
  const human = await now("/", { headers: BROWSER });
  assert.equal(human.status, 302);
  for (const init of [agent(UA.gptbot), agent(UA.gptbot, { accept: "text/markdown" }), agent(UA.curl, { accept: "application/json" }),
    plain("text/markdown"), plain("application/json"), agent(GOOGLEBOT)]) {
    const r = await now("/", init);
    assert.equal(r.status, 200, init.headers["user-agent"]);
    for (const res of [human, r]) assert.equal(res.get("cache-control"), "private, no-store");
    assert.deepEqual(names(r), names(human), `${init.headers["user-agent"]}: the same Vary`);
  }
});

test("6. the wall: the earlier demo is /lab in HTML, markdown and JSON, and /lab shows that page to the agent that follows it", async (t) => {
  installApi(t);
  const html = new TextDecoder().decode((await now("/", agent(UA.gptbot))).bytes);
  assert.ok(html.includes(`A person? <a href="${LIVE_LAB_URL.replace("&", "&#38;")}">Watch it live</a>, or see <a href="${BASE}/lab">the earlier demo</a>.`), "html");
  const md = new TextDecoder().decode((await now("/", agent(UA.gptbot, { accept: "text/markdown" }))).bytes);
  assert.ok(md.includes(`A person? [Watch it live](${LIVE_LAB_URL}), or see [the earlier demo](${BASE}/lab).`), "markdown");
  const json = JSON.parse(new TextDecoder().decode((await now("/", agent(UA.curl, { accept: "application/json" }))).bytes));
  assert.equal(json.human_page, `${BASE}/lab`);
  assert.equal(json.live_view, LIVE_LAB_URL);
  for (const text of [html, md, JSON.stringify(json)]) assert.ok(!text.includes("view=human"), "the wall no longer sends people to /?view=human");
  const followed = await now("/lab", agent(UA.gptbot));
  assert.equal(followed.status, 200);
  assert.ok(same(followed.bytes, file("index.html")), "the agent that follows the link gets the earlier page, not the wall");
});

// Old run links (forge's decision, 16:2xZ): /?run=<id> in posts and earlier decks keeps opening the run it names. A
// person's request goes to the earlier replay at /lab with the full query, under the same 302, cache and Vary rules as
// the redirect to the Live Lab; a URL that carries a door token never forwards its query; machine requests are unchanged.
test("7. an old run link /?run=<id> keeps opening its run: a person goes to /lab with the full query; machines unchanged", async (t) => {
  installApi(t);
  const runRedirect = (r, location, why, { cookie = false } = {}) => {
    assert.equal(r.status, 302, why);
    assert.equal(r.get("location"), location, why);
    assert.equal(r.bytes.length, 0, `${why}: no body`);
    assert.deepEqual(r.headers, sorted([["cache-control", "private, no-store"], ["content-security-policy", CSP], ["link", LINK],
      ["location", location], ["vary", VARY], ...(cookie ? [["set-cookie", HUMAN_COOKIE]] : [])]), `${why}: headers`);
  };
  for (const [path, init, location, why, cookie] of [
    ["/?run=4f2a9c", { headers: BROWSER }, "/lab?run=4f2a9c", "a desktop browser"],
    ["/?run=4f2a9c", { headers: IPHONE }, "/lab?run=4f2a9c", "iPhone Safari"],
    ["/?run=4f2a9c&speed=4", { headers: BROWSER }, "/lab?run=4f2a9c&speed=4", "the full query"],
    ["/?view=human&run=4f2a9c", { headers: BROWSER }, "/lab?view=human&run=4f2a9c", "with the human override", true],
    ["/?run=4f2a9c&view=human", agent(UA.gptbot), "/lab?run=4f2a9c&view=human", "an agent with the human override", true],
  ]) {
    const get = await now(path, init), got = await now(path, head(init));
    runRedirect(get, location, `GET ${path}: ${why}`, { cookie });
    assert.deepEqual([got.status, got.headers, got.bytes.length], [get.status, get.headers, 0], `HEAD ${path} mirrors GET`);
  }
  // The run page it lands on is the earlier replay, which reads ?run= itself.
  const lab = await now("/lab?run=4f2a9c", { headers: BROWSER });
  assert.equal(lab.status, 200);
  assert.ok(same(lab.bytes, file("index.html")), "/lab?run= is web/public/index.html byte for byte");
  // A URL carrying a door token never forwards its query: the person goes to the Live Lab, as before.
  const tok = await now("/?run=4f2a9c&t=abc", { headers: BROWSER });
  assert.equal(tok.status, 302);
  assert.equal(tok.get("location"), LIVE_LAB, "no query forwarded with a token");
  // Machine requests at /?run= are byte for byte what they were.
  for (const init of [agent(UA.gptbot), agent(UA.claudebot), agent(UA.curl), plain("text/markdown"), plain("application/json")]) {
    const [after, before] = [await now("/?run=4f2a9c", init), await was("/?run=4f2a9c", init)];
    const who = init.headers["user-agent"] ?? init.headers.accept;
    assert.deepEqual([after.status, after.headers], [before.status, before.headers], `${who}: status and headers unchanged`);
    assert.ok(same(after.bytes, before.bytes), `${who}: body unchanged`);
  }
});
