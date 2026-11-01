// The declaration surface, hardened after the second security review of #89 and #90 (forge, on #90 at f99df0d):
//   1. a JSON body's name, reason or source that is not well-formed UTF-16 (a lone surrogate) is refused as a control
//      character; URLSearchParams used to turn it into U+FFFD and the door accepted that, though the API refuses Cs;
//   2. every Unicode 16.0 Default_Ignorable_Code_Point is refused in a name or reason (263 of them are marks that passed
//      both sides, so "admin" plus one read as "admin"), and so is a field with nothing left once the reserved-name
//      comparison's cleanup is done (only spaces);
//   3. the character policy reads Unicode 16.0 tables generated from the API's own unicodedata2 (src/door/unicode16.js),
//      not the engine's \p{...} (Unicode 17.0 here and in workerd): every code point U+0000..U+10FFFF gets the API's
//      verdict, which web/test/fixtures/door-a4/declaration-text-u16.json records (make_declare_unicode.py, from
//      intake._declaration_text_allowed itself; app/test_door_declaration_u16.py holds it to the API);
//   4. the notice text is pinned to its version by its SHA-256 (warden's P3).
// declare.js is imported as a namespace, so that against an older tree only the tests that need a new export fail.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import test from "node:test";

import { UA, installApi, setup } from "./door-harness.mjs";
import * as declare from "../src/door/declare.js";

const { DECLARATION_TEXT, NOTICE, displayTextProblem, readOptIn } = declare;
const FIXTURE = JSON.parse(readFileSync(new URL("./fixtures/door-a4/declaration-text-u16.json", import.meta.url), "utf8"));
const V = NOTICE.version;
const DECLARE = "/agents/declare";
const ARRIVAL = "/api/open/v1/door/arrival";
const cp = (...codes) => String.fromCodePoint(...codes);
const json = { headers: { "user-agent": UA.gptbot, accept: "application/json" } };
// Every limiter allows: these tests send thousands of declarations through one pass.
const OPEN = { DOOR_NONCE_LIMITER: { limit: async () => ({ success: true }) }, DOOR_IP_LIMITER: { limit: async () => ({ success: true }) },
  DOOR_READ_LIMITER: { limit: async () => ({ success: true }) } };
const sentDeclarations = (calls) => calls.filter((c) => c.path === ARRIVAL && c.body?.declaration).map((c) => c.body.declaration);
const read = (fields) => readOptIn(new URLSearchParams({ notice_version: V, ...fields }));
const refusedWith = (code) => ({ status: "not_recorded", code, detail: DECLARATION_TEXT[code] });
// Unicode 16.0 Default_Ignorable_Code_Point, as DerivedCoreProperties-16.0.0.txt lists it (forge's brief): 4,174.
const PINNED_DEFAULT_IGNORABLE = [[0x00ad, 0x00ad], [0x034f, 0x034f], [0x061c, 0x061c], [0x115f, 0x1160], [0x17b4, 0x17b5],
  [0x180b, 0x180f], [0x200b, 0x200f], [0x202a, 0x202e], [0x2060, 0x206f], [0x3164, 0x3164], [0xfe00, 0xfe0f], [0xfeff, 0xfeff],
  [0xffa0, 0xffa0], [0xfff0, 0xfff8], [0x1bca0, 0x1bca3], [0x1d173, 0x1d17a], [0xe0000, 0xe0fff]];
const codesOf = (ranges) => ranges.flatMap(([first, last]) => Array.from({ length: last - first + 1 }, (_, i) => first + i));
const pairs = (flat) => Array.from({ length: flat.length / 2 }, (_, i) => [flat[2 * i], flat[2 * i + 1]]);
// The 263 that passed both sides before: default-ignorable marks (Mn), which the category rule lets through.
const DI_MARKS = codesOf([[0x034f, 0x034f], [0x17b4, 0x17b5], [0x180b, 0x180d], [0x180f, 0x180f], [0xfe00, 0xfe0f], [0xe0100, 0xe01ef]]);
const RESERVED = ["human", "you", "senti", "participant", "unidentified participant", "system", "owner", "admin", "moderator"];

// A pass and the declare key its own view shows, and a JSON declare POST whose body is given as text (so a lone
// surrogate can travel as its JSON escape).
async function pass(go) {
  const view = JSON.parse((await go("/agents/intent?purpose=read", json)).text);
  return { t: view.t, key: view.declare.body.declare_key };
}
const declareText = (body) => ({ method: "POST", headers: { "content-type": "application/json", "user-agent": UA.gptbot }, body });
const bodyWith = (p, field, escaped) => `{"t":"${p.t}","notice_version":"${V}","declare_key":"${p.key}","${field}":"${escaped}"}`;
const escapeOf = (code) => `\\u${code.toString(16).padStart(4, "0")}`;

// ── 1. well-formed strings on the JSON path ──────────────────────────────────────────────────────────────────────
test("1. every lone surrogate (2,048) in a JSON name, reason or source is refused as a control character, and nothing is sent", async (t) => {
  const calls = installApi(t);
  const { go, drain } = setup(OPEN);
  const p = await pass(go);
  const accepted = [];
  for (let code = 0xd800; code <= 0xdfff; code += 1) {
    for (const field of ["name", "reason", "source"]) {
      const res = await go(DECLARE, declareText(bodyWith(p, field, escapeOf(code))));
      const outcome = res.status === 200 ? JSON.parse(res.text).declaration : { status: res.status };
      if (JSON.stringify(outcome) !== JSON.stringify(refusedWith("control_character"))) accepted.push({ field, code: code.toString(16), outcome });
    }
  }
  await drain();
  assert.deepEqual(accepted.slice(0, 5), [], `${accepted.length} of 6,144 not refused as control_character`);
  assert.deepEqual(sentDeclarations(calls), [], "no declaration reached the intake");
});

test("1. a lone surrogate inside other text, or one half of a pair, is refused too; a whole pair (an astral character) is recorded exactly", async (t) => {
  const calls = installApi(t);
  const { go, drain } = setup(OPEN);
  const p = await pass(go);
  for (const escaped of ["Bot\\ud83d", "\\udd25Bot", "\\ud83d\\ud83d", "\\udd25\\ud83d", "a\\udfffb"]) {
    for (const field of ["name", "reason"]) {
      const res = await go(DECLARE, declareText(bodyWith(p, field, escaped)));
      assert.deepEqual(JSON.parse(res.text).declaration, refusedWith("control_character"), `${field} ${escaped}`);
    }
  }
  assert.deepEqual(sentDeclarations(calls), []);
  // A valid astral character, as a JSON escape pair and as raw UTF-8, still passes and is passed on exactly as written.
  for (const [field, escaped, text] of [["name", "\\ud83d\\udd25", cp(0x1f525)], ["reason", "\\ud83e\\uddea chip", `${cp(0x1f9ea)} chip`],
    ["name", cp(0x1f525, 0x1f9ea), cp(0x1f525, 0x1f9ea)], ["name", "\\ud801\\udc37", cp(0x10437)]]) {
    const res = await go(DECLARE, declareText(bodyWith(p, field, escaped)));
    assert.deepEqual(JSON.parse(res.text).declaration, { status: "recorded", detail: DECLARATION_TEXT.recorded }, `${field} ${escaped}`);
  }
  await drain();
  assert.deepEqual(sentDeclarations(calls).map((d) => d.name ?? d.reason), [cp(0x1f525), `${cp(0x1f9ea)} chip`, cp(0x1f525, 0x1f9ea), cp(0x10437)]);
});

test("1. readOptIn refuses a field named ill-formed, in field order, and only once the visitor has opted in", () => {
  const params = new URLSearchParams({ notice_version: V, name: "fine", reason: "fine" });
  assert.deepEqual(readOptIn(params, ["reason"]), { status: "not_sent", code: "control_character" });
  assert.deepEqual(readOptIn(new URLSearchParams({ notice_version: V, name: "Admin", reason: "x" }), ["reason"]),
    { status: "not_sent", code: "reserved_name" }, "the name comes first");
  assert.deepEqual(readOptIn(new URLSearchParams({ name: "x" }), ["name"]), { status: "not_given", typed: true }, "no opt-in: nothing is read");
  assert.deepEqual(readOptIn(params), { status: "opted_in", declaration: { notice_version: V, name: "fine", reason: "fine" } });
});

// ── 2. default-ignorable code points, and blank fields ───────────────────────────────────────────────────────────
test("2. the Worker's DEFAULT_IGNORABLE is Unicode 16.0's 4,174 code points, the same ranges as the API's", () => {
  assert.ok(Array.isArray(declare.DEFAULT_IGNORABLE), "declare.js exports DEFAULT_IGNORABLE");
  assert.deepEqual(pairs(declare.DEFAULT_IGNORABLE), PINNED_DEFAULT_IGNORABLE);
  assert.deepEqual(FIXTURE.default_ignorable.ranges, PINNED_DEFAULT_IGNORABLE, "the API's own copy (intake._DEFAULT_IGNORABLE)");
  assert.equal(codesOf(PINNED_DEFAULT_IGNORABLE).length, 4174);
  assert.equal(FIXTURE.default_ignorable.count, 4174);
  assert.equal(DI_MARKS.length, 263);
});

test("2. each of the 4,174 default-ignorable code points is refused in a name and in a reason, wherever it stands", () => {
  const passed = [];
  for (const code of codesOf(PINNED_DEFAULT_IGNORABLE)) {
    for (const field of ["name", "reason"]) {
      for (const text of [cp(code), `ok${cp(code)}`, `${cp(code)}ok`, `o${cp(code)}k`]) {
        const outcome = read({ [field]: text });
        if (outcome.code !== "control_character") passed.push({ field, code: code.toString(16), outcome: outcome.status });
      }
    }
  }
  assert.deepEqual(passed.slice(0, 5), [], `${passed.length} not refused`);
});

test("2. a reserved name padded with a default-ignorable mark is refused at the door, and nothing is sent", async (t) => {
  const calls = installApi(t);
  const { go, drain } = setup(OPEN);
  const p = await pass(go);
  const passed = [];
  for (const name of RESERVED) {
    const middle = name.length >> 1;
    for (const code of DI_MARKS) {
      // Through the route with the mark appended; inside the name through readOptIn (the route's own reader).
      const res = await go(DECLARE, declareText(JSON.stringify({ t: p.t, notice_version: V, declare_key: p.key, name: `${name}${cp(code)}` })));
      const outcomes = [JSON.parse(res.text).declaration.code, read({ name: `${name.slice(0, middle)}${cp(code)}${name.slice(middle)}` }).code];
      if (outcomes.some((outcome) => outcome !== "control_character")) passed.push({ name, code: code.toString(16), outcomes });
    }
  }
  await drain();
  assert.deepEqual(passed.slice(0, 5), [], `${passed.length} of ${RESERVED.length * DI_MARKS.length} not refused`);
  assert.deepEqual(sentDeclarations(calls), []);
  // An emoji with its presentation selector (U+FE0F) is refused for the same reason; the bare emoji is fine.
  assert.equal(displayTextProblem(cp(0x2764, 0xfe0f), 64), "control_character");
  assert.equal(displayTextProblem(cp(0x2764), 64), null);
});

test("2. a name or reason with nothing visible (only spaces) is refused as blank; padded text and an empty field are not", async (t) => {
  const blanks = [" ", "   ", cp(0xa0), cp(0x3000, 0x3000, 0x3000), cp(0x2003, 0x20, 0x205f), cp(0x1680), cp(0x202f, 0x2007)];
  for (const text of blanks) {
    for (const field of ["name", "reason"]) assert.deepEqual(read({ [field]: text }), { status: "not_sent", code: "blank" }, `${field} ${JSON.stringify(text)}`);
  }
  assert.equal(typeof DECLARATION_TEXT.blank, "string");
  assert.deepEqual(read({ name: `  Zo${cp(0xeb)}  `, reason: " ok " }), { status: "opted_in", declaration: { notice_version: V, name: `  Zo${cp(0xeb)}  `, reason: " ok " } });
  assert.deepEqual(read({ name: "", reason: "" }), { status: "opted_in", declaration: { notice_version: V } }, "an empty field is left out, as before");
  // Through the route: refused before anything is sent.
  const calls = installApi(t);
  const { go, drain } = setup(OPEN);
  const p = await pass(go);
  for (const text of blanks) {
    const res = await go(DECLARE, declareText(JSON.stringify({ t: p.t, notice_version: V, declare_key: p.key, name: text })));
    assert.deepEqual(JSON.parse(res.text).declaration, refusedWith("blank"), JSON.stringify(text));
  }
  await drain();
  assert.deepEqual(sentDeclarations(calls), []);
});

// ── 3. Unicode 16.0, not the engine's tables ─────────────────────────────────────────────────────────────────────
test("3. U+20C1 (unassigned in Unicode 16.0, assigned in 17.0) is refused by the Worker, as by the API", async (t) => {
  assert.equal(displayTextProblem(cp(0x20c1), 64), "control_character");
  assert.deepEqual(read({ name: `x${cp(0x20c1)}` }), { status: "not_sent", code: "control_character" });
  const calls = installApi(t);
  const { go, drain } = setup(OPEN);
  const p = await pass(go);
  const res = await go(DECLARE, declareText(JSON.stringify({ t: p.t, notice_version: V, declare_key: p.key, name: cp(0x20c1) })));
  assert.deepEqual(JSON.parse(res.text).declaration, refusedWith("control_character"));
  await drain();
  assert.deepEqual(sentDeclarations(calls), []);
});

test("3. every code point U+0000..U+10FFFF: the Worker's verdict is the API's (refused alone; a mark in a run)", () => {
  assert.equal(FIXTURE.unicode, "16.0.0");
  assert.equal(FIXTURE.max_mark_run, declare.MAX_MARK_RUN);
  const expand = (ranges) => { const bits = new Uint8Array(0x110000); for (const [first, last] of ranges) bits.fill(1, first, last + 1); return bits; };
  const refused = expand(FIXTURE.refused.ranges);
  const marks = expand(FIXTURE.marks.ranges);
  const wrong = [];
  let disagreements = 0;
  for (let code = 0; code < 0x110000; code += 1) {
    const char = String.fromCodePoint(code);
    const workerRefused = displayTextProblem(char, 64) !== null;
    const workerMark = !workerRefused && displayTextProblem(char.repeat(8), 64) === null && displayTextProblem(char.repeat(9), 64) === "combining_marks";
    if (workerRefused !== (refused[code] === 1) || workerMark !== (marks[code] === 1)) {
      disagreements += 1;
      if (wrong.length < 10) wrong.push({ code: code.toString(16), api: { refused: refused[code], mark: marks[code] }, worker: { refused: workerRefused, mark: workerMark } });
    }
  }
  assert.deepEqual({ disagreements, first: wrong }, { disagreements: 0, first: [] });
  // The counts the API's own sweep gives (unicodedata2 16.0.0): the check can fail.
  assert.equal(refused.reduce((n, bit) => n + bit, 0), 959554);
  assert.equal(marks.reduce((n, bit) => n + bit, 0), 2238);
});

test("3. declare.js reads no engine Unicode property tables: its categories and marks come from unicode16.js (Unicode 16.0.0)", async () => {
  const source = readFileSync(new URL("../src/door/declare.js", import.meta.url), "utf8");
  const code = source.split("\n").filter((line) => !line.trimStart().startsWith("//")).join("\n");
  assert.ok(!/\\p\{/i.test(code), "no \\p{...} property escape");
  assert.match(code, /from "\.\/unicode16\.js"/);
  const tables = await import("../src/door/unicode16.js");
  assert.equal(tables.UNICODE_VERSION, "16.0.0");
  for (const name of ["REFUSED", "MARKS", "FORMAT"]) {
    const table = tables[name];
    assert.ok(Object.isFrozen(table) && table.length % 2 === 0, name);
    for (let i = 0; i < table.length; i += 2) {
      assert.ok(table[i] <= table[i + 1] && (i === 0 || table[i] > table[i - 1] + 1), `${name}: sorted, disjoint, merged ranges at ${i}`);
    }
  }
});

// ── 4. the notice text, pinned to its version ────────────────────────────────────────────────────────────────────
// Each notice version names exactly one text. Changing the text means a new version and a new line here; the API's
// copy is pinned by the same table (app/test_door_declaration_u16.py).
const PINNED_NOTICES = Object.freeze({ "sentilab-public-visitor/1": "89a0a0672697cebba94fe2918f7fa2a09cbf1181617ff8cf8acaa759b899047b" });

test("4. the bundled notice's text is the one its version names (SHA-256 of its UTF-8 bytes)", () => {
  assert.ok(Object.hasOwn(PINNED_NOTICES, NOTICE.version), `${NOTICE.version} has no pinned text: a new version needs its own line`);
  const bytes = Buffer.from(NOTICE.text, "utf8");
  assert.equal(createHash("sha256").update(bytes).digest("hex"), PINNED_NOTICES[NOTICE.version], "the text changed without a new version");
  if (NOTICE.version === "sentilab-public-visitor/1") assert.equal(bytes.length, 506);
});
