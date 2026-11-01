// The off switch for declarations (warden, 13:29Z on #90: without one, any Worker deploy from main would turn them on).
// DOOR_DECLARATIONS must be exactly "on". Anything else (missing, "off", "On", ...) is off, the default that
// wrangler.jsonc ships in both environments until warden explicitly authorizes turning it on:
//   - POST /agents/declare (a person's confirm form, an agent's JSON) and any other method on it answer as they did
//     before Amendment 4's opt-in: the path is not the door's, so it gets what any path the door doesn't own gets (404);
//   - no page or JSON the door renders (the wall, the purpose pages, their next links, the ENGRAM view, the 405 text)
//     links to declaring or mentions it, and no link carries ?via=; nor do the agent files (/llms.txt, /agents/);
//   - nothing reaches the intake with a declaration.
// With "on", today's behavior is unchanged: the door's other tests run with it (door-harness.mjs), and the positive
// control below shows each of these probes finds the opt-in when it is there.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { BROWSER, KEY, UA, installApi, setup } from "./door-harness.mjs";
import { NOTICE, OPT_IN_LINE } from "../src/door/declare.js";
import { declareKey } from "../src/door/token.js";

const OFF = Object.freeze([["missing", undefined], ["off", "off"], ["On", "On"], ["ON", "ON"], ["true", "true"], ["1", "1"], ["' on'", " on"]]);
const ARRIVAL = "/api/open/v1/door/arrival";
const json = { headers: { "user-agent": UA.gptbot, accept: "application/json" } };
const md = { headers: { "user-agent": UA.gptbot, accept: "text/markdown" } };
const html = { headers: BROWSER };
// What declaring looks like on a page: the route, its fields, the opt-in line, the notice, the words.
const MARKERS = Object.freeze([/\/agents\/declare/, /notice_version/, /declare_key/, /\bdeclar(e|es|ing|ation|ations)\b/i, /tell us who you are/i,
  /[?&](amp;)?via=/, new RegExp(OPT_IN_LINE.slice(0, 40).replace(/[.*+?^${}()|[\]\\]/g, "\\$&")),
  new RegExp(NOTICE.text.slice(0, 40).replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))]);
const FORBIDDEN_KEYS = Object.freeze(["declare", "declaration", "notice_version", "declare_key"]);
const mentions = (text) => MARKERS.filter((marker) => marker.test(text)).map(String);
function keysDeep(value, found = new Set()) {
  if (Array.isArray(value)) value.forEach((item) => keysDeep(item, found));
  else if (value && typeof value === "object") for (const [key, item] of Object.entries(value)) { found.add(key); keysDeep(item, found); }
  return found;
}
// A link that carries everything a declaration would, as warden's crafted links did.
const CRAFTED = `&notice_version=${encodeURIComponent(NOTICE.version)}&name=off-canary&reason=off-canary&source=other&via=moltbook&declare_key=${"0".repeat(32)}`;
const declaredArrivals = (calls) => calls.filter((c) => c.path === ARRIVAL && c.body && "declaration" in c.body);

// Everything a visitor or agent can be shown or can send about declaring, through the real Worker. Returns what it saw.
async function probe(go) {
  const seen = { pages: [], json: [], declare: [] };
  const page = async (label, path, init) => {
    const res = await go(path, init);
    seen.pages.push({ label, status: res.status, text: res.text, referrer: res.headers.get("referrer-policy") });
    if ((res.headers.get("content-type") ?? "").startsWith("application/json")) seen.json.push({ label, value: JSON.parse(res.text) });
    return res;
  };
  for (const [kind, init] of [["html", html], ["md", md], ["json", json]]) {
    await page(`wall ${kind}`, "/agents/intent", init);
    await page(`wall ${kind} via`, "/agents/intent?via=moltbook", init);
    for (const purpose of ["read", "review", "place-chiplets"]) {
      await page(`token ${purpose} ${kind}`, `/agents/intent?purpose=${purpose}`, init);
      await page(`token ${purpose} ${kind} crafted`, `/agents/intent?purpose=${purpose}${CRAFTED}`, init);
    }
  }
  await page("wall in place of / for an agent", "/", { headers: { "user-agent": UA.gptbot } });
  await page("405 on a door write route", "/agents/submit", { method: "PUT", headers: { "content-type": "application/json" }, body: "{}" });
  for (const path of ["/llms.txt", "/agents/", "/agents/index.json"]) await page(`agent file ${path}`, path, { headers: { "user-agent": UA.gptbot } });
  const pass = JSON.parse((await go("/agents/intent?purpose=place-chiplets", json)).text);
  await page("ENGRAM view", `/agents/engram?t=${pass.t}&via=moltbook`, json);
  // The declare path, every way in, with this pass's own valid declare_key; and the same requests to a path the door
  // never had, for what "not the door's" answers.
  const key = await declareKey(KEY, { site: "sentilab.aidenid.com", nonce: pass.t.split(".")[4], version: NOTICE.version });
  const fields = { t: pass.t, notice_version: NOTICE.version, declare_key: key, name: "off-canary", source: "other" };
  const requests = [
    ["JSON POST", { method: "POST", headers: { "content-type": "application/json", "user-agent": UA.gptbot }, body: JSON.stringify(fields) }],
    ["form POST", { method: "POST", headers: { "content-type": "application/x-www-form-urlencoded", ...BROWSER, "sec-fetch-site": "same-origin",
      origin: "https://sentilab.aidenid.com" }, body: new URLSearchParams(fields).toString() }],
    ["GET", { headers: BROWSER }], ["agent GET", { headers: { "user-agent": UA.gptbot } }]];
  for (const [label, init] of requests) {
    const res = await go(`/agents/declare?${new URLSearchParams(fields)}`, init);
    const other = await go(`/agents/no-such-door-route?${new URLSearchParams(fields)}`, init);
    seen.declare.push({ label, status: res.status, text: res.text, type: res.headers.get("content-type"), otherStatus: other.status, otherText: other.text,
      otherType: other.headers.get("content-type") });
  }
  return seen;
}

for (const [label, value] of OFF) {
  test(`DOOR_DECLARATIONS ${label}: no declare route, no page or JSON mentions declaring, nothing is forwarded`, async (t) => {
    const calls = installApi(t);
    const { go, drain } = setup({ DOOR_DECLARATIONS: value });
    const seen = await probe(go);
    await drain();
    await t.test("the declare path is not the door's: 404, exactly as a path the door never had", () => {
      for (const d of seen.declare) {
        assert.equal(d.status, 404, `${d.label} /agents/declare`);
        assert.deepEqual([d.status, d.text, d.type], [d.otherStatus, d.otherText, d.otherType], `${d.label}: answered as a path the door never had`);
      }
    });
    await t.test("no page or JSON links to declaring or mentions it", () => {
      // Every page rendered (an open door, its real content), so finding no mention is not for want of a page.
      for (const p of seen.pages) assert.equal(p.status, p.label.startsWith("405") ? 405 : 200, p.label);
      for (const p of seen.pages) assert.deepEqual(mentions(p.text), [], `${p.label} (${p.status})`);
      for (const j of seen.json) assert.deepEqual([...keysDeep(j.value)].filter((key) => FORBIDDEN_KEYS.includes(key)), [], j.label);
      for (const p of seen.pages.filter((p) => p.label.startsWith("token") && p.label.includes("html"))) {
        assert.equal(p.referrer, "no-referrer", `${p.label}: no form on the page, so no-referrer as before`);
      }
      assert.match(seen.pages.find((p) => p.label === "405 on a door write route").text, /The agent door's only write route is POST \/agents\/submit\./);
    });
    await t.test("nothing reaches the intake with a declaration", () => {
      assert.deepEqual(declaredArrivals(calls).map((c) => c.body.declaration), [], "no arrival carried a declaration");
      assert.ok(calls.some((c) => c.path === ARRIVAL), "the visits' plain arrivals were still sent (the check can see arrivals)");
    });
  });
}

test("DOOR_DECLARATIONS on (positive control): the same probes find the opt-in, and a declaration is forwarded", async (t) => {
  const calls = installApi(t);
  const { go, drain } = setup({ DOOR_DECLARATIONS: "on" });
  const seen = await probe(go);
  const json = Object.fromEntries(seen.declare.map((d) => [d.label, d]));
  assert.equal(json["JSON POST"].status, 200);
  assert.equal(JSON.parse(json["JSON POST"].text).declaration.status, "recorded");
  assert.equal(json["form POST"].status, 200);
  assert.equal(json.GET.status, 405, "the declare route takes no GET");
  for (const label of ["wall html", "wall md", "wall json", "token read html", "token place-chiplets md", "token review json"]) {
    assert.notDeepEqual(mentions(seen.pages.find((p) => p.label === label).text), [], label);
  }
  assert.ok(keysDeep(seen.json.find((j) => j.label === "ENGRAM view").value).has("declare"));
  assert.equal(seen.pages.find((p) => p.label === "token read html").referrer, "strict-origin");
  assert.match(seen.pages.find((p) => p.label === "405 on a door write route").text, /POST \/agents\/declare/);
  await drain();
  assert.deepEqual(declaredArrivals(calls).map((c) => c.body.declaration.name), ["off-canary", "off-canary"]);
});

test("wrangler.jsonc ships declarations off, in production and in staging, until warden explicitly authorizes them", () => {
  const text = readFileSync(new URL("../wrangler.jsonc", import.meta.url), "utf8");
  const config = JSON.parse(text.replace(/^\s*\/\/.*$/gm, ""));
  assert.equal(config.vars.DOOR_DECLARATIONS, "off");
  assert.equal(config.env.staging.vars.DOOR_DECLARATIONS, "off");
  // The rule is warden's explicit authorization, after the two conditions: no merge or deploy of another PR turns it
  // on.
  assert.match(text, /until warden explicitly authorizes turning it on/);
  assert.match(text, /hide is confirmed on both public feeds on every serving revision/);
  assert.match(text, /one pass or one network prefix can be stopped/);
  assert.doesNotMatch(text, /#97|paired deploy/);
});
