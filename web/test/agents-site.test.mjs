// node --test web/test/agents-site.test.mjs
// The agent pages: web/public/llms.txt, web/public/agents.json and everything under web/public/agents/. They are
// markdown and JSON only, readable with a plain GET, and:
//   1. every JSON file parses and has the shape its schema below gives it;
//   2. every link resolves to a file the Worker serves from web/public, and every link is root-relative, so a page
//      reads the same whether it is served at /, /sentilab/ or /agents/; a #fragment names a heading of its page;
//   3. no temperature appears: no absolute temperature except the declared 85 °C scenario target, kelvin values only as
//      provisional thresholds or invented worked-example numbers, and no withdrawn or published value;
//   4. every threshold is provisional and not frozen, and the pages quote each one as challenge.json has it;
//   5. no "validated", no "calibrated" or "calibration", and "measured" only as "not measured";
//   6. the status agrees everywhere: submissions not open, submit unavailable, the evaluator pending gate zero;
//   7. the reference copies keep their identities (content_sha256 recomputes from identity.canonical), their legality
//      follows the rules in math.md, and the manifest's dies are the references' dies;
//   8. once the SLAB-048 sources are in this tree, each copy names their exact bytes (make_agents_references.py).
import { test } from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, extname, join, relative, sep } from "node:path";
import { fileURLToPath } from "node:url";

import { AGENT_INDEX } from "../src/agent-view.js";

const here = dirname(fileURLToPath(import.meta.url));
const REPO = join(here, "..", "..");
const PUBLIC = join(here, "..", "public");
const AGENTS = join(PUBLIC, "agents");
const read = (rel) => readFileSync(join(PUBLIC, ...rel.split("/")), "utf8");
const json = (rel) => JSON.parse(read(rel));
function walk(dir) {
  return readdirSync(dir).flatMap((name) => {
    const full = join(dir, name);
    return statSync(full).isDirectory() ? walk(full) : [relative(PUBLIC, full).split(sep).join("/")];
  });
}
const AGENT_FILES = walk(AGENTS).sort();
const SITE = ["llms.txt", "agents.json", ...AGENT_FILES];
const TEXT = SITE.filter((rel) => [".md", ".txt"].includes(extname(rel)));
const JSONS = SITE.filter((rel) => extname(rel) === ".json");
const REFERENCES = ["ascend910-tap25d-fig6a", "micro150-tap25d-fig5a"];
const challenge = json("agents/challenge.json");

// ── a small schema checker: type, const, enum, pattern, required, properties, additionalProperties: false, items ─
const typeOf = (x) => (x === null ? "null" : Array.isArray(x) ? "array" : Number.isInteger(x) ? "integer" : typeof x);
function validate(value, schema, path = "$", errors = []) {
  if ("const" in schema && JSON.stringify(value) !== JSON.stringify(schema.const)) errors.push(`${path}: expected ${JSON.stringify(schema.const)}`);
  if (schema.enum && !schema.enum.includes(value)) errors.push(`${path}: ${JSON.stringify(value)} is not one of ${schema.enum.join(", ")}`);
  if (schema.type && ![].concat(schema.type).some((t) => typeOf(value) === t || (t === "number" && typeOf(value) === "integer"))) {
    errors.push(`${path}: expected ${schema.type}, got ${typeOf(value)}`);
    return errors;
  }
  if (schema.pattern && typeof value === "string" && !new RegExp(schema.pattern).test(value)) errors.push(`${path}: does not match ${schema.pattern}`);
  if (schema.minItems !== undefined && Array.isArray(value) && value.length < schema.minItems) errors.push(`${path}: fewer than ${schema.minItems} items`);
  if (schema.items && Array.isArray(value)) value.forEach((item, i) => validate(item, schema.items, `${path}[${i}]`, errors));
  if (typeOf(value) === "object") {
    for (const key of schema.required || []) if (!(key in value)) errors.push(`${path}: missing ${key}`);
    for (const [key, sub] of Object.entries(schema.properties || {})) if (key in value) validate(value[key], sub, `${path}.${key}`, errors);
    if (schema.additionalProperties === false) for (const key of Object.keys(value)) if (!(key in (schema.properties || {}))) errors.push(`${path}: unexpected ${key}`);
  }
  return errors;
}
const HEX64 = { type: "string", pattern: "^[0-9a-f]{64}$" };
const SITE_PATH = { type: "string", pattern: "^/" };
const STR = { type: "string" };
const PROVISIONAL = { required: ["unit", "status", "frozen"], properties: { unit: STR, status: { const: "provisional" }, frozen: { const: false } } };
const THRESHOLD = { type: "object", ...PROVISIONAL, required: [...PROVISIONAL.required, "value"], properties: { ...PROVISIONAL.properties, value: { type: "number" } } };
const THRESHOLD_LIST = { type: "object", ...PROVISIONAL, required: [...PROVISIONAL.required, "values"], properties: { ...PROVISIONAL.properties, values: { type: "array", minItems: 1, items: { type: "number" } } } };
const STATUS = {
  type: "object", additionalProperties: false,
  required: ["submissions", "learning", "offline_check", "status_and_results", "senti_room_skills", "evaluator", "thresholds", "temperatures_shown", "simulated_not_silicon"],
  properties: {
    submissions: { enum: ["not_open", "open"] }, learning: { enum: ["open"] }, offline_check: { enum: ["coming", "available"] },
    status_and_results: { enum: ["not_open", "open"] }, senti_room_skills: { enum: ["coming", "available"] }, evaluator: STR,
    thresholds: { enum: ["provisional", "frozen"] }, temperatures_shown: { type: "boolean" }, simulated_not_silicon: { const: true },
  },
};
const LINK = { type: "object", required: ["rel", "href", "type"], properties: { rel: STR, href: SITE_PATH, type: { enum: ["text/markdown", "application/json", "text/plain"] } } };
const DIE = {
  type: "object", additionalProperties: false, required: ["die", "unit", "name", "w_um", "h_um", "power_w", "halo_um", "rot_deg"],
  properties: { die: { type: "integer" }, unit: { type: "string", pattern: "^Chiplet_[0-9]+$" }, name: STR, w_um: { type: "integer" }, h_um: { type: "integer" },
    power_w: { type: "number" }, halo_um: THRESHOLD, rot_deg: { type: "array", minItems: 1, items: { enum: [0, 90] } } },
};
const PROBLEM = {
  type: "object",
  required: ["problem", "name", "description", "fixture", "dies", "netlist", "legality", "statistic", "wire", "references", "policy", "bounds", "screen", "sources"],
  properties: {
    problem: { enum: ["ascend910", "micro150"] }, name: STR,
    fixture: { type: "object", required: ["id", "config", "config_sha256", "frame_um", "link_type"], properties: { config_sha256: HEX64, frame_um: { type: "integer" } } },
    dies: { type: "array", minItems: 2, items: DIE },
    netlist: { type: "object", required: ["matrix", "counting"], properties: { matrix: { type: "array", items: { type: "array", items: { type: "integer" } } } } },
    legality: { type: "object", required: ["lattice_um", "margin_um", "min_die_gap_um", "keepouts", "rotation"],
      properties: { lattice_um: THRESHOLD, margin_um: THRESHOLD, min_die_gap_um: THRESHOLD, keepouts: { type: "array" } } },
    statistic: { type: "object", required: ["symbol", "definition", "real_chiplets", "grid", "evaluator", "numerical_admission"],
      properties: { symbol: { const: "T_M" }, grid: THRESHOLD, evaluator: { const: "pending gate zero" }, numerical_admission: { const: "UNKNOWN" } } },
    wire: { type: "object", required: ["symbol", "definition", "router_sha256", "proxy"], properties: { symbol: { const: "W" }, router_sha256: HEX64 } },
    references: { type: "object", required: ["comparator", "engineering_variants", "published_targets"], properties: {
      comparator: { type: "object", required: ["id", "file", "content_sha256", "design_hash", "T_R", "W_R_mm"],
        properties: { file: SITE_PATH, content_sha256: HEX64, design_hash: HEX64, T_R: { type: "string", pattern: "^UNKNOWN" }, W_R_mm: THRESHOLD, admissible_entry: { const: false } } },
      engineering_variants: { type: "array", minItems: 1, items: { type: "object", required: ["id", "file", "content_sha256", "design_hash"], properties: { file: SITE_PATH, content_sha256: HEX64, design_hash: HEX64, legal_on_fixture: { const: true } } } },
    } },
    policy: { type: "object", required: ["status", "frozen", "D_K", "r", "B_T_K", "B_W", "T_limit_C", "tradeoff_budgets_r"],
      properties: { frozen: { const: false }, D_K: THRESHOLD, r: THRESHOLD, B_T_K: THRESHOLD, B_W: THRESHOLD, T_limit_C: THRESHOLD, tradeoff_budgets_r: THRESHOLD_LIST } },
    bounds: { type: "object", properties: { u_T: { const: "UNKNOWN" }, u_q: { const: "UNKNOWN" }, u_abs: { const: "UNKNOWN" } } },
    screen: { type: "object", required: ["status", "frozen", "claim", "scenarios"], properties: { status: { const: "provisional" }, frozen: { const: false }, scenarios: { type: "array", minItems: 3 } } },
    sources: { type: "object", required: ["dies", "netlist"] },
  },
};
const SCHEMAS = {
  "agents.json": { type: "object", additionalProperties: false, required: ["schema", "name", "agents", "llms_txt", "status"],
    properties: { schema: { const: "sentilab-agents-pointer/1" }, name: STR, llms_txt: SITE_PATH, status: STATUS,
      agents: { type: "object", additionalProperties: false, required: ["md", "json", "alias"], properties: { md: SITE_PATH, json: SITE_PATH, alias: SITE_PATH } } } },
  "agents/index.json": { type: "object", required: ["schema", "name", "entry", "status", "opens_after", "sections"],
    properties: { schema: { const: "sentilab-agents-index/1" }, entry: { const: "/agents/index.md" }, status: STATUS, opens_after: { type: "array", minItems: 1, items: STR },
      sections: { type: "array", minItems: 1, items: { type: "object", required: ["id", "href"], properties: { id: STR, href: SITE_PATH, links: { type: "array", items: LINK } } } } } },
  "agents/challenge.json": { type: "object", required: ["schema", "status", "frozen", "label", "sources", "problems", "definitions"],
    properties: { schema: { const: "sentilab-agents-challenge/0" }, frozen: { const: false },
      status: { type: "object", required: ["manifest", "submissions", "thresholds", "evaluator", "temperatures"], properties: { submissions: { const: "not_open" }, evaluator: { const: "pending gate zero" } } },
      problems: { type: "array", minItems: 2, items: PROBLEM },
      definitions: { type: "object", required: ["layout", "comparisons", "bounded", "evidence_modes", "claims", "claim_states", "wire_tracks", "tradeoff", "pareto", "ties"],
        properties: { claims: { type: "array", minItems: 7, items: { type: "object", required: ["id", "label", "predicate"] } } } } } },
  "agents/skills/tools.json": { type: "object", required: ["schema", "status", "submissions", "registers_tools", "adapters", "tools", "definitions"],
    properties: { schema: { const: "sentilab-agents-tools/0" }, submissions: { const: "not_open" }, registers_tools: { const: false },
      tools: { type: "array", minItems: 4, items: { type: "object", required: ["name", "availability", "summary", "input"],
        properties: { name: { enum: ["sentilab_open_check", "sentilab_open_submit", "sentilab_open_status", "sentilab_open_results"] }, availability: { enum: ["available", "coming", "unavailable"] }, input: { type: "object" } } } } } },
};
const REFERENCE = {
  type: "object",
  required: ["schema", "layout_id", "reference_id", "kind", "label", "role", "labels", "fixture", "units", "dies", "centers_mm", "rotated", "footprints_mm", "legal_on_fixture", "identity", "design_hash", "routed_wirelength", "wire_proxy_mm", "copied_from", "omitted"],
  properties: {
    schema: { const: "sentilab-agents-reference/1" }, kind: { enum: ["raw", "engineering-variant"] },
    label: { enum: ["reconstructed from a published figure, continuous, reference-only", "engineering variant"] },
    rotated: { type: "array", items: { type: "boolean" } }, legal_on_fixture: { type: "boolean" }, design_hash: HEX64,
    identity: { type: "object", required: ["canonical", "content_sha256", "hashing"], properties: { content_sha256: HEX64 } },
    routed_wirelength: { type: "object", required: ["value_mm", "label", "router_sha256", "status", "frozen"], properties: { value_mm: { type: "number" }, router_sha256: HEX64, status: { const: "provisional" }, frozen: { const: false } } },
    copied_from: { type: "array", minItems: 1, items: { type: "object", required: ["path", "file_sha256"], properties: { file_sha256: HEX64 } } },
  },
};
for (const ref of REFERENCES) for (const name of [`${ref}.json`, `${ref}-snap0p5.json`]) SCHEMAS[`agents/references/${name}`] = REFERENCE;

test("the agent pages are markdown and JSON only, and the walk reaches every one", () => {
  assert.deepEqual(AGENT_FILES.filter((rel) => ![".md", ".json"].includes(extname(rel))), []);
  for (const rel of ["agents/index.md", "agents/index.json", "agents/challenge.json", "agents/physics.md", "agents/math.md",
    "agents/skills/SKILL.md", "agents/skills/tools.json", "agents/skills/senti-room-skills.md"]) assert.ok(AGENT_FILES.includes(rel), rel);
  assert.equal(AGENT_FILES.filter((rel) => rel.startsWith("agents/references/")).length, 4);
});

test("1. every JSON file parses and has its schema's shape", () => {
  assert.deepEqual(JSONS.filter((rel) => !SCHEMAS[rel]), [], "every JSON file has a schema here");
  for (const rel of JSONS) assert.deepEqual(validate(json(rel), SCHEMAS[rel]), [], rel);
});
test("1. negative control: the schema checker catches a frozen threshold, a missing field and a wrong type", () => {
  const broken = structuredClone(challenge);
  broken.problems[0].policy.D_K.frozen = true;
  delete broken.problems[1].statistic.real_chiplets;
  broken.problems[0].dies[0].w_um = "14500";
  const errors = validate(broken, SCHEMAS["agents/challenge.json"]);
  assert.ok(errors.some((e) => e.includes("policy.D_K.frozen")), "frozen threshold");
  assert.ok(errors.some((e) => e.includes("missing real_chiplets")), "missing field");
  assert.ok(errors.some((e) => e.includes("dies[0].w_um")), "wrong type");
});

// ── 2. links ──────────────────────────────────────────────────────────────────────────────────────────────────────
function markdownLinks(text) {
  const out = [];
  for (let at = text.indexOf("]("); at !== -1; at = text.indexOf("](", at + 2)) {
    const end = text.indexOf(")", at + 2);
    if (end !== -1) out.push(text.slice(at + 2, end));
  }
  return out;
}
function jsonLinks(value, out = []) {
  if (typeof value === "string" && value.startsWith("/")) out.push(value);
  else if (Array.isArray(value)) value.forEach((v) => jsonLinks(v, out));
  else if (value && typeof value === "object") Object.values(value).forEach((v) => jsonLinks(v, out));
  return out;
}
const slug = (heading) => heading.toLowerCase().replace(/[^a-z0-9 _-]/g, "").trim().replace(/ /g, "-");
const anchors = (text) => new Set(text.split("\n").filter((line) => line.startsWith("#")).map((line) => slug(line.replace(/^#+[ ]+/, ""))));
// The file a root-relative path is served from: the Worker's /agents index, a folder's index.html, or the file itself.
function servedFile(path) {
  const clean = path.split("#")[0].split("?")[0];
  const target = Object.hasOwn(AGENT_INDEX, clean) ? AGENT_INDEX[clean] : clean.endsWith("/") ? `${clean}index.html` : clean;
  return target.slice(1);
}
function linkProblems(from, href) {
  if (/^https?:[/][/]/.test(href)) return [];
  if (href.startsWith("#")) return anchors(read(from)).has(href.slice(1)) ? [] : [`${from}: no heading for ${href}`];
  if (!href.startsWith("/")) return [`${from}: ${href} is not root-relative`];
  const rel = servedFile(href);
  if (!existsSync(join(PUBLIC, ...rel.split("/")))) return [`${from}: ${href} resolves to nothing (${rel})`];
  const fragment = href.split("#")[1];
  if (fragment !== undefined && extname(rel) === ".md" && !anchors(read(rel)).has(fragment)) return [`${from}: ${href} names no heading of ${rel}`];
  return [];
}
test("2. every link in the agent pages resolves to a file the Worker serves, and is root-relative", () => {
  const found = [];
  let count = 0;
  for (const rel of TEXT) for (const href of markdownLinks(read(rel))) { count += 1; found.push(...linkProblems(rel, href)); }
  for (const rel of JSONS) for (const href of jsonLinks(json(rel))) { count += 1; found.push(...linkProblems(rel, href)); }
  assert.ok(count > 60, `the walk finds the links (${count})`);
  assert.deepEqual(found, []);
});
test("2. index.md and index.json link the same files", () => {
  const files = (hrefs) => new Set(hrefs.filter((h) => h.startsWith("/")).map(servedFile));
  const md = files(markdownLinks(read("agents/index.md")));
  const js = files(jsonLinks(json("agents/index.json")));
  js.delete("agents/index.md");   // index.json's entry and section links point into index.md itself
  assert.deepEqual([...js].filter((f) => !md.has(f)), [], "every file index.json links, index.md links too");
  assert.deepEqual([...md].filter((f) => !js.has(f)), [], "and the other way round");
});
test("2. negative control: a missing file, a relative link and a missing heading are caught", () => {
  assert.equal(linkProblems("agents/index.md", "/agents/nope.md").length, 1);
  assert.equal(linkProblems("agents/index.md", "challenge.json").length, 1);
  assert.equal(linkProblems("agents/index.md", "/agents/physics.md#no-such-heading").length, 1);
  assert.deepEqual(linkProblems("agents/index.md", "/agents/physics.md#the-evaluator"), []);
  assert.deepEqual(linkProblems("llms.txt", "/agents/"), []);
});

// ── 3. temperatures ──────────────────────────────────────────────────────────────────────────────────────────────
const NUMBER = "(?<![A-Za-z0-9_.])[-+−]?[0-9][0-9,]*([.][0-9]+)?";
const ABSOLUTE = [new RegExp(`${NUMBER}[ ]?(°|º|deg[ ]?|degrees[ ]?)[ ]?[CF](?![A-Za-z])`, "g"), new RegExp(`${NUMBER}[ ]?[CF](?![A-Za-z0-9_])`, "g"),
  new RegExp(`${NUMBER}[ ]?(celsius|fahrenheit)`, "gi")];
const KELVIN = new RegExp(`${NUMBER}[ ]?K(?![A-Za-z0-9_])`, "g");
// Withdrawn, published and model temperatures that must never appear, in any unit or none: the paper's reported values,
// the ambient in kelvin and the kelvin offset, and an old-engine figure.
const DENIED = [75.48, 115.94, 75.13, 75.47, 113.54, 94.89, 93.89, 318.15, 273.15, 69.6];
const BLOB = /^[A-Za-z0-9+/=_-]{32,}$/;
const numbersIn = (text) => [...text.matchAll(/(?<![0-9.])[0-9]+([.][0-9]+)?(?![0-9])/g)].map((m) => Number(m[0]));
const matches = (re, text) => [...text.matchAll(re)].map((m) => m[0]);
// Every temperature finding in one text file: [] when it is clean.
function textTemperatures(rel, text) {
  const found = [];
  text.split("\n").forEach((line, i) => {
    for (const hit of ABSOLUTE.flatMap((re) => matches(re, line))) {
      if (!(/^85 ?°C$/.test(hit.trim()) && /scenario target/i.test(line))) found.push(`${rel}:${i + 1}: absolute temperature ${hit.trim()}`);
    }
    for (const hit of matches(KELVIN, line)) if (!/provisional|invented/i.test(line)) found.push(`${rel}:${i + 1}: ${hit.trim()} outside a provisional threshold or an invented example`);
    for (const n of numbersIn(line)) if (DENIED.includes(n)) found.push(`${rel}:${i + 1}: denied value ${n}`);
  });
  return found;
}
// A JSON key names a temperature when it carries a temperature unit suffix or word.
const TEMPERATURE_KEY = /(^|_)(c|k)$|temp|celsius|kelvin|ambient|peak/i;
const ALLOWED_TEMPERATURE_PATHS = /^[$][.]problems[[][0-9]+][.]policy[.](D_K|B_T_K|T_limit_C)[.]value$/;
function jsonTemperatures(rel, value, path = "$", parentKey = "", found = []) {
  if (typeof value === "string") {
    if (!BLOB.test(value)) {
      for (const hit of [...ABSOLUTE, KELVIN].flatMap((re) => matches(re, value))) found.push(`${rel} ${path}: ${hit.trim()} in a string`);
      for (const n of numbersIn(value)) if (DENIED.includes(n)) found.push(`${rel} ${path}: denied value ${n}`);
    }
  } else if (typeof value === "number") {
    const key = path.slice(path.lastIndexOf(".") + 1).replace(/[[][0-9]+]$/, "");
    const named = ["value", "values"].includes(key) ? parentKey : key;
    if (TEMPERATURE_KEY.test(named) && !ALLOWED_TEMPERATURE_PATHS.test(path)) found.push(`${rel} ${path}: a number under a temperature key`);
    if (DENIED.includes(value)) found.push(`${rel} ${path}: denied value ${value}`);
  } else if (Array.isArray(value)) {
    value.forEach((v, i) => jsonTemperatures(rel, v, `${path}[${i}]`, parentKey, found));
  } else if (value && typeof value === "object") {
    if (["K", "degC", "°C", "C", "kelvin"].includes(value.unit) && !ALLOWED_TEMPERATURE_PATHS.test(`${path}.value`)) found.push(`${rel} ${path}: a temperature unit outside the allowed thresholds`);
    for (const [k, v] of Object.entries(value)) {
      if (TEMPERATURE_KEY.test(k) && typeof v === "number" && !ALLOWED_TEMPERATURE_PATHS.test(`${path}.${k}`)) found.push(`${rel} ${path}.${k}: a number under a temperature key`);
      else jsonTemperatures(rel, v, `${path}.${k}`, k, found);
    }
  }
  return found;
}
test("3. no temperature appears in any agent page, except the provisional thresholds and invented example numbers", () => {
  const found = [...TEXT.flatMap((rel) => textTemperatures(rel, read(rel))), ...JSONS.flatMap((rel) => jsonTemperatures(rel, json(rel)))];
  assert.deepEqual(found, []);
  for (const problem of challenge.problems) assert.equal(problem.policy.T_limit_C.value, 85, "the one absolute temperature is the declared scenario target");
});
test("3. negative control: temperatures in every form are caught", () => {
  for (const line of ["Ascend 910 runs at 75.48 °C.", "peak 115.94 C", "a 45 degC ambient", "it rose 0.32 K", "T = 318.15", "47.1 Celsius", "85 °C as a limit"]) {
    assert.ok(textTemperatures("x.md", line).length > 0, line);
  }
  for (const line of ["85 °C, provisional: the declared temperature target, a chosen scenario target", "D = 0.5 K (provisional)", "+0.32 K (invented)", "C4 bumps", "Chiplet_0", "TAP-2.5D", "f18831e"]) {
    assert.deepEqual(textTemperatures("x.md", line), [], line);
  }
  assert.ok(jsonTemperatures("x.json", { paper: { peak_temperature_c: 75.48 } }).length > 0);
  assert.ok(jsonTemperatures("x.json", { ambient_c: 45 }).length > 0);
  assert.ok(jsonTemperatures("x.json", { round_trip: { tolerance_k: 1.0 } }).length > 0);
  assert.ok(jsonTemperatures("x.json", { result: { value: 80.2, unit: "degC" } }).length > 0);
  assert.ok(jsonTemperatures("x.json", { note: "sink rise 18.4 K" }).length > 0);
  assert.deepEqual(jsonTemperatures("x.json", { problems: [{ policy: { T_limit_C: { value: 85, unit: "degC" }, D_K: { value: 0.5, unit: "K" } } }] }), []);
});

// ── 4. thresholds ────────────────────────────────────────────────────────────────────────────────────────────────
function provisionalProblems(value, path = "$", found = []) {
  if (Array.isArray(value)) value.forEach((v, i) => provisionalProblems(v, `${path}[${i}]`, found));
  else if (value && typeof value === "object") {
    if (("value" in value || "values" in value) && "unit" in value && (value.status !== "provisional" || value.frozen !== false)) found.push(`${path}: not provisional`);
    for (const [k, v] of Object.entries(value)) provisionalProblems(v, `${path}.${k}`, found);
  }
  return found;
}
const THRESHOLD_PATHS = ["legality.lattice_um", "legality.margin_um", "legality.min_die_gap_um", "dies[].halo_um", "statistic.grid",
  "references.comparator.W_R_mm", "policy.D_K", "policy.r", "policy.B_T_K", "policy.B_W", "policy.T_limit_C", "policy.tradeoff_budgets_r"];
// The threshold objects at a path like "dies[].halo_um", in one problem.
const at = (problem, path) => path.split(".").reduce((nodes, part) => nodes.flatMap((n) => (part.endsWith("[]") ? n[part.slice(0, -2)] : [n[part]])), [problem]);
const valuesAt = (path) => [...new Set(challenge.problems.flatMap((p) => at(p, path)).flatMap((t) => ("values" in t ? t.values : [t.value])))].sort((a, b) => a - b);
test("4. every threshold is provisional and not frozen, wherever it is", () => {
  for (const problem of challenge.problems) {
    for (const path of THRESHOLD_PATHS) {
      for (const t of at(problem, path)) {
        assert.equal(t.status, "provisional", `${problem.problem} ${path}`);
        assert.equal(t.frozen, false, `${problem.problem} ${path}`);
      }
    }
    for (const block of [problem.legality, problem.policy]) {
      assert.deepEqual(Object.entries(block).filter(([, v]) => typeof v === "number"), [], "no bare number in legality or policy");
    }
  }
  for (const rel of JSONS) assert.deepEqual(provisionalProblems(json(rel)), [], rel);
});
test("4. math.md quotes every threshold as challenge.json has it, and both problems share the policy values it quotes", () => {
  const rows = read("agents/math.md").split("\n").filter((line) => line.startsWith("|")).map((line) => line.split("|").map((c) => c.trim()))
    .filter((cells) => cells[2] && cells[2].startsWith("`") && cells[2].endsWith("`"));
  const quoted = new Map(rows.map((cells) => [cells[2].slice(1, -1), cells[3]]));
  assert.deepEqual([...quoted.keys()].sort(), [...THRESHOLD_PATHS].filter((p) => !["statistic.grid", "references.comparator.W_R_mm"].includes(p)).sort());
  for (const [path, cell] of quoted) {
    assert.match(cell, /provisional/, `${path}: says provisional`);
    const cellNumbers = [...new Set(numbersIn(cell.replaceAll("Ascend 910", "Ascend")))].sort((a, b) => a - b);
    assert.deepEqual(cellNumbers, valuesAt(path), `${path}: ${cell}`);
  }
  for (const p of challenge.problems.slice(1)) assert.deepEqual(p.policy, challenge.problems[0].policy, "one set of policy values");
});

// ── 5. wording ───────────────────────────────────────────────────────────────────────────────────────────────────
function wordingProblems(rel, text) {
  const found = [];
  for (const m of text.matchAll(/(?<![A-Za-z])(validated|calibrat[a-z]*)(?![A-Za-z])/gi)) found.push(`${rel}: "${m[0]}"`);
  for (const m of text.matchAll(/(?<![A-Za-z])measured(?![A-Za-z])/gi)) {
    if (!/(not|never|nor)[ ]+$/i.test(text.slice(Math.max(0, m.index - 8), m.index))) found.push(`${rel}: "measured" not negated`);
  }
  return found;
}
test("5. no 'validated', no 'calibrated' or 'calibration', and 'measured' only as 'not measured'", () => {
  assert.deepEqual(SITE.flatMap((rel) => wordingProblems(rel, read(rel))), []);
  assert.ok(wordingProblems("x.md", "a validated result").length && wordingProblems("x.md", "calibration against silicon").length
    && wordingProblems("x.md", "the measured peak").length);
  assert.deepEqual(wordingProblems("x.md", "Not CAD, not silicon, not measured. unvalidated"), []);
});

// ── 6. status ────────────────────────────────────────────────────────────────────────────────────────────────────
test("6. the status agrees everywhere: submissions not open, submit unavailable, the evaluator pending gate zero", () => {
  const index = json("agents/index.json");
  assert.deepEqual(json("agents.json").status, index.status, "agents.json matches agents/index.json");
  assert.equal(index.status.submissions, "not_open");
  assert.equal(index.status.temperatures_shown, false);
  assert.equal(index.status.thresholds, "provisional");
  assert.equal(index.status.evaluator, "pending gate zero");
  assert.equal(challenge.status.submissions, "not_open");
  const tools = json("agents/skills/tools.json");
  assert.equal(tools.submissions, "not_open");
  assert.equal(tools.tools.find((t) => t.name === "sentilab_open_submit").availability, "unavailable");
  assert.deepEqual(tools.tools.filter((t) => t.availability === "available"), [], "nothing is claimed available yet");
  for (const rel of ["llms.txt", "agents/index.md", "agents/physics.md", "agents/math.md", "agents/skills/SKILL.md"]) {
    assert.match(read(rel), /submissions not open yet/i, rel);
  }
  const skill = read("agents/skills/SKILL.md");
  assert.match(skill.slice(skill.indexOf("## 5. Submit")), /^## 5[.] Submit [(]not open yet[)]/);
  assert.match(read("agents/skills/senti-room-skills.md"), /coming, not available yet/);
  assert.match(read("agents/index.md"), /## Identify yourself\n\nAgents visiting this site may be asked to state their purpose and will receive a receipt[.]\n/);
  for (const p of challenge.problems) {
    assert.equal(p.statistic.evaluator, "pending gate zero");
    assert.match(p.references.comparator.T_R, /^UNKNOWN/);
  }
});

// ── 7. references ────────────────────────────────────────────────────────────────────────────────────────────────
// Python's json.dumps(value, sort_keys=True, separators=(",", ":")), which identity.hashing names, for canonical objects
// whose numbers are all floats (45.0, never 45) and whose strings are printable ASCII.
function pythonJson(v) {
  if (typeof v === "boolean" || v === null) return JSON.stringify(v);
  if (typeof v === "number") return Number.isInteger(v) ? `${v}.0` : String(v);
  if (typeof v === "string") { assert.match(v, /^[ -~]*$/); return JSON.stringify(v); }
  if (Array.isArray(v)) return `[${v.map(pythonJson).join(",")}]`;
  return `{${Object.keys(v).sort().map((k) => `${JSON.stringify(k)}:${pythonJson(v[k])}`).join(",")}}`;
}
const sha256 = (data) => createHash("sha256").update(data).digest("hex");
const copy = (name) => json(`agents/references/${name}.json`);
// Every rule of math.md section 2 over one problem, in micrometres. Centres may be fractional (the raw references); tol
// is the tolerance the reference checker uses, 1e-9 mm.
function violations(problem, layout, { tol = 1e-6 } = {}) {
  const F = problem.fixture.frame_um, L = problem.legality.lattice_um.value, m = problem.legality.margin_um.value, s = problem.legality.min_die_gap_um.value;
  const found = [];
  if (layout.length !== problem.dies.length) return [{ rule: "die_count" }];
  const boxes = layout.map((p, i) => {
    const d = problem.dies[i];
    if (p.die !== i) found.push({ rule: "die_order", dies: [i] });
    if (!d.rot_deg.includes(p.rot_deg)) found.push({ rule: "rotation_not_allowed", dies: [i] });
    const [W, H] = p.rot_deg === 90 ? [d.h_um, d.w_um] : [d.w_um, d.h_um];
    return { i, x: p.x_um, y: p.y_um, W, H, g: d.halo_um.value };
  });
  for (const b of boxes) {
    if (b.x < 0 || b.y < 0 || b.x > F || b.y > F) found.push({ rule: "out_of_frame", dies: [b.i] });
    if ([b.x, b.y].some((c) => Math.abs(c / L - Math.round(c / L)) * L > tol)) found.push({ rule: "lattice", dies: [b.i] });
    if (b.x - b.W / 2 - b.g < m - tol || b.y - b.H / 2 - b.g < m - tol || b.x + b.W / 2 + b.g > F - m + tol || b.y + b.H / 2 + b.g > F - m + tol) found.push({ rule: "margin", dies: [b.i] });
  }
  for (const a of boxes) for (const b of boxes.filter((o) => o.i > a.i)) {
    const apart = a.x + a.W / 2 + a.g <= b.x - b.W / 2 - b.g + tol || b.x + b.W / 2 + b.g <= a.x - a.W / 2 - a.g + tol
      || a.y + a.H / 2 + a.g <= b.y - b.H / 2 - b.g + tol || b.y + b.H / 2 + b.g <= a.y - a.H / 2 - a.g + tol;
    if (!apart) found.push({ rule: "halo_overlap", dies: [a.i, b.i] });
    const gap = Math.max(b.x - b.W / 2 - (a.x + a.W / 2), a.x - a.W / 2 - (b.x + b.W / 2), b.y - b.H / 2 - (a.y + a.H / 2), a.y - a.H / 2 - (b.y + b.H / 2));
    if (gap < s - tol) found.push({ rule: "min_spacing", dies: [a.i, b.i] });
  }
  return found;
}
const layoutOf = (ref) => ref.centers_mm.map(([x, y], i) => ({ die: i, x_um: x * 1000, y_um: y * 1000, rot_deg: ref.rotated[i] ? 90 : 0 }));
const problemOf = (ref) => challenge.problems.find((p) => p.fixture.id === ref.fixture.fixture_id);

test("7. every reference copy keeps its identity: content_sha256 recomputes from identity.canonical", () => {
  for (const ref of REFERENCES) for (const name of [ref, `${ref}-snap0p5`]) {
    const r = copy(name);
    assert.equal(sha256(pythonJson(r.identity.canonical)), r.identity.content_sha256, name);
    assert.deepEqual(r.identity.canonical.centers_mm, r.centers_mm, `${name}: the canonical centres are the layout's`);
    assert.deepEqual(r.identity.canonical.rotated, r.rotated);
    assert.deepEqual(r.identity.canonical.footprints_mm, r.footprints_mm);
  }
});
test("7. the rules in math.md give each reference its recorded legality: raw fails the lattice only, variants pass", () => {
  for (const ref of REFERENCES) {
    const raw = copy(ref);
    const problem = problemOf(raw);
    const found = violations(problem, layoutOf(raw));
    assert.deepEqual([...new Set(found.map((v) => v.rule))], ["lattice"], `${ref}: the lattice rule only`);
    assert.deepEqual(found.map((v) => v.dies[0]), raw.violations_on_fixture.map((v) => v.dies[0]), `${ref}: the dies it records`);
    assert.equal(raw.legal_on_fixture, false);
    assert.equal(raw.continuous_rules_legal, true);
    const variant = copy(`${ref}-snap0p5`);
    assert.deepEqual(violations(problem, layoutOf(variant)), [], `${ref}-snap0p5 passes every rule`);
    assert.equal(variant.legal_on_fixture, true);
    assert.ok(layoutOf(variant).every((p) => Number.isInteger(p.x_um) && Number.isInteger(p.y_um)), "whole micrometres");
  }
});
test("7. negative control: the legality rules catch each kind of violation", () => {
  const problem = challenge.problems[0];
  const good = layoutOf(copy("ascend910-tap25d-fig6a-snap0p5"));
  const moved = (i, dx, dy, rot) => good.map((p) => (p.die === i ? { ...p, x_um: p.x_um + dx, y_um: p.y_um + dy, rot_deg: rot ?? p.rot_deg } : p));
  const rules = (layout) => [...new Set(violations(problem, layout).map((v) => v.rule))].sort();
  assert.deepEqual(rules(moved(2, 250, 0)), ["lattice"]);
  assert.deepEqual(rules(moved(2, -1500, 0)), ["margin"]);
  assert.deepEqual(rules(moved(3, -7000, 0)), ["halo_overlap", "min_spacing"]);
  assert.deepEqual(rules(moved(5, 0, -11500)), ["halo_overlap", "min_spacing"]);
  assert.deepEqual(rules(moved(1, 0, 0, 90)), ["halo_overlap", "margin", "min_spacing"], "a turned die swaps width and height: the I/O die then crosses the edge and the compute die");
  assert.deepEqual(rules(good.slice(1)), ["die_count"]);
  const square = challenge.problems[1];
  assert.deepEqual([...new Set(violations(square, layoutOf(copy("micro150-tap25d-fig5a-snap0p5")).map((p) => (p.die === 4 ? { ...p, rot_deg: 90 } : p))).map((v) => v.rule))], ["rotation_not_allowed"]);
});
test("7. the manifest's dies, identities and comparator wire are the reference copies'", () => {
  for (const ref of REFERENCES) {
    const raw = copy(ref);
    const variant = copy(`${ref}-snap0p5`);
    const problem = problemOf(raw);
    assert.deepEqual(variant.dies, raw.dies);
    assert.deepEqual(problem.dies.map((d) => [d.die, d.w_um, d.h_um, d.power_w, d.halo_um.value]),
      raw.dies.map((d) => [d.die, Math.round(d.catalog_mm[0] * 1000), Math.round(d.catalog_mm[1] * 1000), d.power_w, Math.round(d.halo_mm * 1000)]), `${ref}: dies`);
    assert.deepEqual(problem.dies.map((d) => d.rot_deg), problem.dies.map((d) => (d.w_um === d.h_um ? [0] : [0, 90])), "square dies cannot turn");
    assert.deepEqual(problem.statistic.real_chiplets, problem.dies.map((d) => d.unit));
    assert.deepEqual(problem.dies.map((d) => d.unit), problem.dies.map((d, i) => `Chiplet_${i}`));
    assert.equal(problem.fixture.frame_um, Math.round(raw.fixture.frame_mm * 1000));
    assert.equal(problem.fixture.config_sha256, raw.fixture.config_sha256);
    const R = problem.netlist.matrix;
    assert.ok(R.length === problem.dies.length && R.every((row, i) => row.length === R.length && row[i] === 0 && row.every((v, j) => v === R[j][i])), "a square, symmetric netlist");
    const comparator = problem.references.comparator;
    assert.equal(comparator.file, `/agents/references/${ref}.json`);
    assert.equal(comparator.content_sha256, raw.identity.content_sha256);
    assert.equal(comparator.design_hash, raw.design_hash);
    assert.equal(comparator.W_R_mm.value, raw.routed_wirelength.value_mm);
    assert.equal(problem.wire.router_sha256, raw.routed_wirelength.router_sha256);
    const [engineering] = problem.references.engineering_variants;
    assert.equal(engineering.file, `/agents/references/${ref}-snap0p5.json`);
    assert.equal(engineering.content_sha256, variant.identity.content_sha256);
    assert.equal(engineering.design_hash, variant.design_hash);
  }
});
test("7. the proposal example in SKILL.md is legal, and is the Ascend 910 engineering variant it says it is", () => {
  const skill = read("agents/skills/SKILL.md");
  const start = skill.indexOf("```json\n") + "```json\n".length;
  const example = JSON.parse(skill.slice(start, skill.indexOf("```", start)));
  const tools = json("agents/skills/tools.json");
  assert.deepEqual(Object.keys(example).sort(), [...tools.definitions.proposal.required, "client"].sort(), "the draft schema's fields");
  assert.deepEqual(violations(challenge.problems[0], example.dies), []);
  assert.deepEqual(example.dies, layoutOf(copy("ascend910-tap25d-fig6a-snap0p5")));
});

// ── 8. provenance ────────────────────────────────────────────────────────────────────────────────────────────────
test("8. when the SLAB-048 sources are in this tree, each reference copy names their exact bytes", (t) => {
  let present = 0;
  for (const ref of REFERENCES) for (const name of [ref, `${ref}-snap0p5`]) {
    for (const source of copy(name).copied_from) {
      assert.match(source.path, /^docs[/]sentilab[/]references[/][a-z0-9-]+[.]json$/);
      const path = join(REPO, ...source.path.split("/"));
      if (!existsSync(path)) continue;
      present += 1;
      assert.equal(sha256(readFileSync(path)), source.file_sha256, `${name}: ${source.path} changed; rerun python web/test/make_agents_references.py --write`);
    }
  }
  if (present === 0) t.diagnostic("the SLAB-048 reference files are not in this tree yet; nothing to compare");
});
