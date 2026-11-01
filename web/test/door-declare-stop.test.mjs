// The operator's stop for declarations (warden's condition for turning them on: one pass or one network prefix can be
// stopped from declaring; the hide works per event, so a repost would be public at once). DOOR_DECLARE_DENY_IDS lists
// pass short ids, DOOR_DECLARE_DENY_PREFIXES CIDR prefixes of the client address (CF-Connecting-IP, the address the
// door's limiters read). A listed opt-in, by form or JSON, is refused at the door before anything is sent, in the shape
// of any refusal there and in words that name no list; an entry that doesn't parse is ignored and logged by its
// position only, and the others still apply; with DOOR_DECLARATIONS off the route is 404, as before.
// Through the real Worker (door-harness.mjs), whose fetch mock records every call that could reach the intake. Every
// test checks at least one stop, so each fails without the stop.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import test from "node:test";

import { BROWSER, KEY, UA, installApi, mint, setup } from "./door-harness.mjs";
import { NOTICE } from "../src/door/declare.js";
import { declareKey } from "../src/door/token.js";

const DECLARE = "/agents/declare";
const ARRIVAL = "/api/open/v1/door/arrival";
const ORIGIN = "https://sentilab.aidenid.com";
const V = NOTICE.version;
// A stopped opt-in's answer: what any refusal at the door answers (status 200, sentilab-agent-declare/1), in words that
// name no list, no address and no operator.
const STOPPED = Object.freeze({ status: "not_recorded", code: "not_accepted", detail: "Your declaration was not recorded. Your purpose pass works as usual." });
const REVEALING = /den(y|ied)|block|\bban|list|prefix|network|address|operator|stop|cidr/i;

// A pass with a chosen nonce, its declare_key, and its short id as the intake derives it (the first 4 hex of
// sha256(nonce), app/door/policy.py short_id), computed here, not by the Worker.
async function pass(n) {
  const nonce = n.toString(16).padStart(16, "0");
  return { t: await mint("read", { nonce }), key: await declareKey(KEY, { site: "sentilab.aidenid.com", nonce, version: V }),
    shortId: createHash("sha256").update(nonce).digest("hex").slice(0, 4) };
}
const opt = (p, extra = {}) => ({ t: p.t, notice_version: V, declare_key: p.key, name: "a visitor", source: "other", ...extra });
const from = (ip) => (ip === null ? {} : { "cf-connecting-ip": ip });
const jsonPost = (fields, ip = null) => ({ method: "POST", headers: { "content-type": "application/json", "user-agent": UA.gptbot, ...from(ip) },
  body: JSON.stringify(fields) });
const formPost = (fields, ip = null) => ({ method: "POST", headers: { "content-type": "application/x-www-form-urlencoded", ...BROWSER,
  "sec-fetch-site": "same-origin", origin: ORIGIN, ...from(ip) }, body: new URLSearchParams(fields).toString() });
// The declaration a JSON answer reports (every answer here is a 200).
async function declaration(go, init) {
  const res = await go(DECLARE, init);
  assert.equal(res.status, 200, res.text.slice(0, 200));
  return JSON.parse(res.text).declaration;
}
const declared = (calls) => calls.filter((c) => c.path === ARRIVAL && c.body && "declaration" in c.body);
// A result page with its one sentence of outcome set aside.
const shape = (html) => html.replace(/(<h1>[^<]*<\/h1>\n<p>)[^<]*(<\/p>)/, "$1...$2");

// ── refused ─────────────────────────────────────────────────────────────────────────────────────────────────────────
test("refused: a listed short id, by JSON", async (t) => {
  const calls = installApi(t);
  const a = await pass(1);
  const { go, drain } = setup({ DOOR_DECLARE_DENY_IDS: a.shortId });
  const res = await go(DECLARE, jsonPost(opt(a)));
  assert.equal(res.status, 200);
  assert.deepEqual(JSON.parse(res.text), { schema: "sentilab-agent-declare/1", declaration: STOPPED });
  assert.ok(!res.text.includes("a visitor"), "the text is never echoed");
  await drain();
  assert.deepEqual(calls, [], "nothing was sent");
});

test("refused: a listed short id, by form", async (t) => {
  const calls = installApi(t);
  const a = await pass(2);
  const { go, drain } = setup({ DOOR_DECLARE_DENY_IDS: a.shortId });
  const res = await go(DECLARE, formPost(opt(a)));
  assert.equal(res.status, 200);
  assert.match(res.headers.get("content-type"), /^text\/html/);
  assert.match(res.text, /<h1>Declaration not recorded<\/h1>/);
  assert.ok(res.text.includes(`<p>${STOPPED.detail}</p>`));
  await drain();
  assert.deepEqual(calls, [], "nothing was sent");
});

test("refused: an IPv4 address in a listed /24", async (t) => {
  const calls = installApi(t);
  const { go, drain } = setup({ DOOR_DECLARE_DENY_PREFIXES: "203.0.113.0/24" });
  for (const [n, ip] of [[3, "203.0.113.7"], [4, "203.0.113.0"], [5, "203.0.113.255"]]) {
    assert.deepEqual(await declaration(go, jsonPost(opt(await pass(n)), ip)), STOPPED, ip);
  }
  assert.match((await go(DECLARE, formPost(opt(await pass(6)), "203.0.113.7"))).text, /<h1>Declaration not recorded<\/h1>/, "by form too");
  await drain();
  assert.deepEqual(calls, [], "nothing was sent");
});

test("refused: an IPv6 address in a listed /32", async (t) => {
  const calls = installApi(t);
  const { go, drain } = setup({ DOOR_DECLARE_DENY_PREFIXES: "2001:db8::/32" });
  for (const [n, ip] of [[7, "2001:db8::1"], [8, "2001:db8::"], [9, "2001:db8:ffff:ffff:ffff:ffff:ffff:ffff"], [10, "2001:db8:5:0:0:0:0:7"]]) {
    assert.deepEqual(await declaration(go, jsonPost(opt(await pass(n)), ip)), STOPPED, ip);
  }
  assert.match((await go(DECLARE, formPost(opt(await pass(11)), "2001:db8:abcd::42"))).text, /<h1>Declaration not recorded<\/h1>/, "by form too");
  await drain();
  assert.deepEqual(calls, [], "nothing was sent");
});

// ── allowed ─────────────────────────────────────────────────────────────────────────────────────────────────────────
test("allowed: an address just outside a listed prefix", async (t) => {
  const calls = installApi(t);
  const { go, drain } = setup({ DOOR_DECLARE_DENY_PREFIXES: "203.0.113.0/24, 2001:db8::/32" });
  // Each prefix's first and last address are stopped; the next address out, on either side, is not.
  const edges = [["203.0.113.0", true], ["203.0.113.255", true], ["203.0.112.255", false], ["203.0.114.0", false],
    ["2001:db8::", true], ["2001:db8:ffff:ffff:ffff:ffff:ffff:ffff", true], ["2001:db7:ffff:ffff:ffff:ffff:ffff:ffff", false], ["2001:db9::", false]];
  let n = 20;
  for (const [ip, stopped] of edges) {
    const answer = await declaration(go, jsonPost(opt(await pass(n += 1)), ip));
    if (stopped) assert.deepEqual(answer, STOPPED, ip);
    else assert.equal(answer.status, "recorded", ip);
  }
  await drain();
  assert.equal(declared(calls).length, 4, "the four outside addresses' declarations were sent, and only those");
});

test("allowed: a pass whose short id isn't listed", async (t) => {
  const calls = installApi(t);
  const [a, b] = [await pass(30), await pass(31)];
  assert.notEqual(a.shortId, b.shortId);
  const { go, drain } = setup({ DOOR_DECLARE_DENY_IDS: a.shortId });
  assert.deepEqual(await declaration(go, jsonPost(opt(a))), STOPPED, "the listed pass");
  assert.equal((await declaration(go, jsonPost(opt(b)))).status, "recorded", "another pass");
  assert.match((await go(DECLARE, formPost(opt(b)))).text, /<h1>Declaration recorded<\/h1>/, "by form too");
  await drain();
  const sent = declared(calls);
  assert.equal(sent.length, 2);
  for (const call of sent) assert.equal(call.body.nonce, b.t.split(".")[4], "only the unlisted pass's declarations were sent");
});

// ── robustness ──────────────────────────────────────────────────────────────────────────────────────────────────────
test("robustness: empty lists stop nothing", async (t) => {
  const warn = t.mock.method(console, "warn", () => undefined);
  const calls = installApi(t);
  const p = await pass(40);
  let n = 40;
  for (const [ids, prefixes] of [["", ""], [undefined, undefined], [" , \n\t,", ",,  "], [null, null]]) {
    const { go, drain } = setup({ DOOR_DECLARE_DENY_IDS: ids, DOOR_DECLARE_DENY_PREFIXES: prefixes });
    for (const ip of ["203.0.113.7", "2001:db8::1", null]) {
      assert.equal((await declaration(go, jsonPost(opt(await pass(n += 1)), ip))).status, "recorded", `${JSON.stringify([ids, prefixes])} ${ip}`);
    }
    await drain();
  }
  assert.equal(declared(calls).length, 12);
  assert.equal(warn.mock.callCount(), 0, "nothing to log");
  // The control: the same kind of request, once its pass is listed, is stopped.
  const { go } = setup({ DOOR_DECLARE_DENY_IDS: p.shortId, DOOR_DECLARE_DENY_PREFIXES: "" });
  assert.deepEqual(await declaration(go, jsonPost(opt(p), "203.0.113.7")), STOPPED);
});

test("robustness: a malformed entry next to a valid one: the valid one still applies; the bad one is logged by position only", async (t) => {
  const warn = t.mock.method(console, "warn", () => undefined);
  const calls = installApi(t);
  const [a, b, c] = [await pass(60), await pass(61), await pass(62)];
  // Entries the door doesn't read: a length out of range, two slashes, a bad octet, a leading zero, a triple colon, two
  // double colons, nine groups, a zone, an embedded IPv4 form, a word. And ids that aren't 4 hex.
  const badPrefixes = ["203.0.113.0/33", "198.51.100.0/24/8", "2001:db8::/129", "300.1.2.0/24", "010.0.0.0/8", "2001:db8:::/48", "2001:db8::1::/64",
    "2001:db8:1:2::3:4:5:6/64", "fe80::1%eth0/64", "::ffff:192.0.2.0/120", "not-a-prefix"];
  const badIds = ["ab1", "abcde", "zz12", "pass-12ab"];
  const { go, drain } = setup({ DOOR_DECLARE_DENY_PREFIXES: `${badPrefixes[0]}, 203.0.113.0/24, ${badPrefixes.slice(1).join(" ")}`,
    DOOR_DECLARE_DENY_IDS: `${badIds.join(",")} ${a.shortId}` });
  assert.deepEqual(await declaration(go, jsonPost(opt(b), "203.0.113.7")), STOPPED, "the valid prefix applies");
  assert.deepEqual(await declaration(go, jsonPost(opt(a), "192.0.2.1")), STOPPED, "the valid id applies");
  assert.equal((await declaration(go, jsonPost(opt(c), "192.0.2.1"))).status, "recorded", "the bad entries stop nothing");
  await drain();
  assert.equal(declared(calls).length, 1);
  const lines = warn.mock.calls.map((call) => call.arguments.map(String).join(" "));
  const numbers = (line) => (line.match(/\d+/g) ?? []).map(Number);
  assert.ok(lines.some((line) => line.includes("DOOR_DECLARE_DENY_PREFIXES") && numbers(line).join() === "1,3,4,5,6,7,8,9,10,11,12"), lines.join("\n"));
  assert.ok(lines.some((line) => line.includes("DOOR_DECLARE_DENY_IDS") && numbers(line).join() === "1,2,3,4"), lines.join("\n"));
  for (const line of lines) {
    for (const text of [...badPrefixes, ...badIds, "203.0.113.0/24", a.shortId, "203.0.113.7", "192.0.2.1", "a visitor"]) {
      assert.ok(!line.includes(text), `the log never holds an entry or an address: ${text}`);
    }
  }
});

test("robustness: with declarations off the route is 404 as before, even for a listed id and a listed prefix", async (t) => {
  const warn = t.mock.method(console, "warn", () => undefined);
  const calls = installApi(t);
  const a = await pass(70);
  const stop = { DOOR_DECLARE_DENY_IDS: `${a.shortId} not-an-id`, DOOR_DECLARE_DENY_PREFIXES: "203.0.113.0/24, not-a-prefix" };
  for (const value of [undefined, "off", "On"]) {
    const { go, drain } = setup({ ...stop, DOOR_DECLARATIONS: value });
    for (const init of [jsonPost(opt(a), "203.0.113.7"), formPost(opt(a), "203.0.113.7")]) {
      const [res, other] = [await go(DECLARE, init), await go("/agents/no-such-door-route", init)];
      assert.equal(res.status, 404, String(value));
      assert.deepEqual([res.status, res.text, res.headers.get("content-type")], [other.status, other.text, other.headers.get("content-type")],
        "answered as a path the door never had");
    }
    await drain();
  }
  assert.deepEqual(declared(calls), [], "nothing reached the intake with a declaration");
  assert.equal(warn.mock.callCount(), 0, "with declarations off the lists aren't read");
  // The control: on, the same request is stopped.
  const { go } = setup({ ...stop, DOOR_DECLARATIONS: "on" });
  assert.deepEqual(await declaration(go, jsonPost(opt(a), "203.0.113.7")), STOPPED);
});

// ── never sent ──────────────────────────────────────────────────────────────────────────────────────────────────────
test("never sent: a stopped declaration reaches nothing; an allowed one sends exactly its arrival", async (t) => {
  const calls = installApi(t);
  const [a, b] = [await pass(80), await pass(81)];
  const { go, drain } = setup({ DOOR_DECLARE_DENY_IDS: a.shortId, DOOR_DECLARE_DENY_PREFIXES: "203.0.113.0/24" });
  for (const [label, init] of [["listed pass, JSON", jsonPost(opt(a))], ["listed pass, form", formPost(opt(a))],
    ["listed prefix, JSON", jsonPost(opt(b), "203.0.113.9")], ["listed prefix, form", formPost(opt(b), "203.0.113.9")]]) {
    const before = calls.length;
    assert.equal((await go(DECLARE, init)).status, 200, label);
    await drain();
    assert.deepEqual(calls.slice(before), [], `${label}: the fetch mock recorded no call`);
  }
  // The control: the same pass from outside the prefix sends one call, its arrival, with its declaration.
  const before = calls.length;
  assert.equal((await declaration(go, jsonPost(opt(b), "192.0.2.1"))).status, "recorded");
  await drain();
  const sent = calls.slice(before);
  assert.deepEqual(sent.map((c) => [c.method, c.path]), [["POST", ARRIVAL]]);
  assert.deepEqual(sent[0].body.declaration, { notice_version: V, name: "a visitor", source: "other" });
});

// ── fail closed ─────────────────────────────────────────────────────────────────────────────────────────────────────
test("an address the door can't read is refused while a prefix is listed, and stops nothing while none is", async (t) => {
  const calls = installApi(t);
  const listed = setup({ DOOR_DECLARE_DENY_PREFIXES: "198.51.100.0/24" });
  let n = 90;
  for (const ip of [null, "", "unknown", "::ffff:203.0.113.7", "203.0.113.07", "203.0.113.7, 192.0.2.1", "2001:db8::1%eth0"]) {
    assert.deepEqual(await declaration(listed.go, jsonPost(opt(await pass(n += 1)), ip)), STOPPED, JSON.stringify(ip));
  }
  await listed.drain();
  assert.deepEqual(declared(calls), []);
  // With only an id listed, the address isn't consulted.
  const idsOnly = setup({ DOOR_DECLARE_DENY_IDS: (await pass(100)).shortId });
  assert.equal((await declaration(idsOnly.go, jsonPost(opt(await pass(101)), null))).status, "recorded");
});

test("a list that isn't text refuses every opt-in, logged; anything unexpected reading the lists fails closed, never the Worker", async (t) => {
  const warn = t.mock.method(console, "warn", () => undefined);
  const calls = installApi(t);
  let n = 110;
  for (const [name, value] of [["DOOR_DECLARE_DENY_IDS", ["82ab"]], ["DOOR_DECLARE_DENY_IDS", { id: "82ab" }], ["DOOR_DECLARE_DENY_IDS", 1234],
    ["DOOR_DECLARE_DENY_PREFIXES", ["203.0.113.0/24"]], ["DOOR_DECLARE_DENY_PREFIXES", true]]) {
    const { go } = setup({ [name]: value });
    assert.deepEqual(await declaration(go, jsonPost(opt(await pass(n += 1)), "192.0.2.1")), STOPPED, `${name} ${JSON.stringify(value)}`);
  }
  const { go, env, drain } = setup();
  Object.defineProperty(env, "DOOR_DECLARE_DENY_PREFIXES", { get() { throw new Error("an unreadable binding"); }, enumerable: true });
  assert.deepEqual(await declaration(go, jsonPost(opt(await pass(120)), "192.0.2.1")), STOPPED, "a throwing read is refused, not a crash");
  assert.equal((await go("/agents/board", { headers: { "user-agent": UA.gptbot } })).status, 200, "the Worker still serves");
  await drain();
  assert.deepEqual(declared(calls), []);
  const lines = warn.mock.calls.map((call) => call.arguments.map(String).join(" "));
  assert.ok(lines.filter((line) => line.includes("DOOR_DECLARE_DENY_IDS")).length >= 3, lines.join("\n"));
  assert.ok(lines.filter((line) => line.includes("DOOR_DECLARE_DENY_PREFIXES")).length >= 2, lines.join("\n"));
  assert.ok(lines.length >= 6, "the throwing read is logged too");
  for (const line of lines) for (const text of ["82ab", "1234", "203.0.113.0/24", "192.0.2.1", "an unreadable binding"]) assert.ok(!line.includes(text), text);
});

// ── what the stop shows ─────────────────────────────────────────────────────────────────────────────────────────────
test("the stop shows only where a declaration would be sent: a stopped pass gets every other answer as any pass does", async (t) => {
  const calls = installApi(t);
  const [a, b, a2] = [await pass(130), await pass(131), await pass(132)];
  const { go, drain } = setup({ DOOR_DECLARE_DENY_IDS: `${a.shortId},${a2.shortId}` });
  const answer = async (fields) => { const res = await go(DECLARE, jsonPost(fields)); return [res.status, JSON.parse(res.text)]; };
  for (const [label, fields] of [["typed, not opted in", (p) => ({ t: p.t, name: "typed" })], ["nothing typed", (p) => ({ t: p.t })],
    ["reserved name", (p) => opt(p, { name: "Admin" })], ["too long", (p) => opt(p, { name: "x".repeat(65) })],
    ["unknown source", (p) => opt(p, { source: "evil" })], ["another pass's key", (p) => opt(p, { declare_key: "0".repeat(32) })]]) {
    assert.deepEqual(await answer(fields(a)), await answer(fields(b)), label);
  }
  // Only a declaration that would be sent differs, and its answer has the shape of the door's other refusals.
  const [stopped, recorded, reserved] = [await answer(opt(a)), await answer(opt(b)), await answer(opt(a, { name: "Admin" }))];
  assert.deepEqual(stopped, [200, { schema: "sentilab-agent-declare/1", declaration: STOPPED }]);
  assert.equal(recorded[1].declaration.status, "recorded");
  assert.deepEqual(Object.keys(stopped[1].declaration), Object.keys(reserved[1].declaration));
  assert.doesNotMatch(JSON.stringify(stopped), REVEALING);
  // The form's page is the door's refusal page: the same page as a reserved name's, but for its one sentence.
  const [page, refusal] = [await go(DECLARE, formPost(opt(a2))), await go(DECLARE, formPost(opt(a2, { name: "Admin" })))];
  assert.equal(page.status, refusal.status);
  assert.equal(page.headers.get("content-type"), refusal.headers.get("content-type"));
  assert.equal(shape(page.text), shape(refusal.text));
  assert.ok(page.text.includes(`<p>${STOPPED.detail}</p>`));
  assert.doesNotMatch(STOPPED.detail, REVEALING);
  await drain();
  assert.equal(declared(calls).length, 1, "only the unlisted pass's declaration was sent");
});

test("list syntax: ids in either case; commas, spaces or new lines between entries; a bare address is that address; host bits are ignored", async (t) => {
  const calls = installApi(t);
  const [a, b] = [await pass(110), await pass(140)];
  assert.match(a.shortId, /[a-f]/, "an id with letters, to list in upper case");
  const { go, drain } = setup({ DOOR_DECLARE_DENY_IDS: `\n ${a.shortId.toUpperCase()},\t${b.shortId} `,
    DOOR_DECLARE_DENY_PREFIXES: " 203.0.113.77/24\n198.51.100.5\t2001:DB8::/32,,192.0.2.0/25 198.51.100.9/32, 2001:db9::7/128 " });
  assert.deepEqual(await declaration(go, jsonPost(opt(a), "192.0.2.200")), STOPPED, "an id listed in upper case");
  assert.deepEqual(await declaration(go, jsonPost(opt(b), "192.0.2.200")), STOPPED, "an id after a tab");
  let n = 150;
  // 32.1.13.184 has the bytes of 2001:db8::/32's first 32 bits, and cb00:7100:: starts with 203.0.113's: an address
  // never matches a prefix of the other family.
  for (const [ip, stopped] of [["203.0.113.1", true], ["198.51.100.5", true], ["198.51.100.6", false], ["2001:db8::abcd", true], ["192.0.2.127", true],
    ["192.0.2.128", false], ["203.0.112.1", false], ["198.51.100.9", true], ["198.51.100.10", false], ["2001:db9::7", true], ["2001:db9::8", false],
    ["32.1.13.184", false], ["cb00:7100::1", false]]) {
    const result = await declaration(go, jsonPost(opt(await pass(n += 1)), ip));
    if (stopped) assert.deepEqual(result, STOPPED, ip);
    else assert.equal(result.status, "recorded", ip);
  }
  await drain();
  assert.equal(declared(calls).length, 7);
});

// ── the shipped config ──────────────────────────────────────────────────────────────────────────────────────────────
test("wrangler.jsonc declares both lists, as text, in production and in staging, and every entry in them parses", async (t) => {
  const text = readFileSync(new URL("../wrangler.jsonc", import.meta.url), "utf8");
  const config = JSON.parse(text.replace(/^\s*\/\/.*$/gm, ""));
  const warn = t.mock.method(console, "warn", () => undefined);
  for (const [where, vars] of [["production", config.vars], ["staging", config.env.staging.vars]]) {
    for (const name of ["DOOR_DECLARE_DENY_IDS", "DOOR_DECLARE_DENY_PREFIXES"]) assert.equal(typeof vars[name], "string", `${where} ${name}`);
    // A stop committed here is read as the Worker reads it: an entry it would ignore fails this test instead.
    const { declareStopped } = await import("../src/door/declare-stop.js");
    declareStopped(vars, { shortId: "0000", address: "192.0.2.1" });
  }
  assert.equal(warn.mock.callCount(), 0, "no entry is ignored");
  assert.equal(text.match(/operator stop for one pass or prefix/g)?.length, 2, "the operator's note, in both environments");
});
