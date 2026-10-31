// A small JSON Schema (draft 2020-12) validator for the keywords the progress packets use, and nothing more.
//
//   import { validateSchema } from "./json-schema-lite.mjs";
//   const errors = validateSchema(schema, value);   // [] when valid; a list of "path keyword: message" otherwise
//
// It fails closed: a schema keyword or format it does not implement throws UnsupportedSchemaError instead of being
// skipped, so a schema can never be under-checked without anyone noticing. No dependencies, because CI runs the deck
// test with plain node. Formats are asserted (date-time, uuid, uri), which is stricter than the annotation-only default.
// $ref resolves only local JSON pointers ("#/$defs/name").

export class UnsupportedSchemaError extends Error {}

const ANNOTATIONS = new Set(["$schema", "$id", "$comment", "$defs", "title", "description", "examples", "default", "deprecated",
  "readOnly", "writeOnly"]);
const ASSERTIONS = new Set(["$ref", "type", "const", "enum", "properties", "required", "additionalProperties", "minProperties",
  "maxProperties", "items", "prefixItems", "minItems", "maxItems", "uniqueItems", "contains", "minContains", "maxContains",
  "minLength", "maxLength", "pattern", "format", "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "allOf", "anyOf",
  "oneOf", "not", "if", "then", "else"]);

const isObject = (v) => v !== null && typeof v === "object" && !Array.isArray(v);
const typeOf = (v) => (v === null ? "null" : Array.isArray(v) ? "array" : Number.isInteger(v) ? "integer" : typeof v);
const TYPES = {
  null: (v) => v === null, boolean: (v) => typeof v === "boolean", object: isObject, array: Array.isArray,
  string: (v) => typeof v === "string", number: (v) => typeof v === "number" && Number.isFinite(v), integer: (v) => Number.isInteger(v),
};
function deepEqual(a, b) {
  if (a === b) return true;
  if (typeof a !== typeof b || a === null || b === null || typeof a !== "object") return false;
  if (Array.isArray(a) !== Array.isArray(b)) return false;
  if (Array.isArray(a)) return a.length === b.length && a.every((x, i) => deepEqual(x, b[i]));
  const ka = Object.keys(a), kb = Object.keys(b);
  return ka.length === kb.length && ka.every((k) => Object.hasOwn(b, k) && deepEqual(a[k], b[k]));
}
const short = (v) => { const s = JSON.stringify(v); return s.length > 60 ? `${s.slice(0, 57)}...` : s; };

// RFC 3339 date-time, with real calendar and offset ranges.
const DATE_TIME = /^(\d{4})-(\d{2})-(\d{2})[Tt](\d{2}):(\d{2}):(\d{2})(?:\.\d+)?(?:[Zz]|([+-])(\d{2}):(\d{2}))$/;
function isDateTime(s) {
  const m = DATE_TIME.exec(s);
  if (!m) return false;
  const [y, mo, d, h, mi, se] = m.slice(1, 7).map(Number);
  const leap = (y % 4 === 0 && y % 100 !== 0) || y % 400 === 0;
  const days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][mo - 1];
  if (!days || d < 1 || d > days || h > 23 || mi > 59 || se > 60) return false;
  return m[7] === undefined || (Number(m[8]) <= 23 && Number(m[9]) <= 59);
}
const FORMATS = {
  "date-time": isDateTime,
  uuid: (s) => /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(s),
  uri: (s) => /^[A-Za-z][A-Za-z0-9+.-]*:[^\s]*$/.test(s),
};

function resolveRef(root, ref) {
  if (typeof ref !== "string" || !ref.startsWith("#")) throw new UnsupportedSchemaError(`$ref ${short(ref)}: only local "#/..." pointers are supported`);
  let node = root;
  for (const raw of ref.slice(1).split("/").slice(1)) {
    const key = decodeURIComponent(raw).replace(/~1/g, "/").replace(/~0/g, "~");
    if (node === null || typeof node !== "object" || !Object.hasOwn(node, key)) throw new UnsupportedSchemaError(`$ref ${ref} does not resolve`);
    node = node[key];
  }
  return node;
}

function run(s, v, at, root) {
  if (s === true) return [];
  if (s === false) return [`${at || "/"} false: no value is allowed here`];
  if (!isObject(s)) throw new UnsupportedSchemaError(`schema at ${at || "/"} is not an object or boolean`);
  for (const k of Object.keys(s)) if (!ANNOTATIONS.has(k) && !ASSERTIONS.has(k)) throw new UnsupportedSchemaError(`unsupported keyword "${k}" at ${at || "/"}`);
  const errs = [];
  const fail = (kw, msg) => errs.push(`${at || "/"} ${kw}: ${msg}`);
  const sub = (schema, value, path) => run(schema, value, path, root);
  const ok = (schema, value, path) => sub(schema, value, path).length === 0;

  if ("$ref" in s) errs.push(...sub(resolveRef(root, s.$ref), v, at));
  if ("type" in s) { const ts = [].concat(s.type); if (!ts.some((t) => { if (!TYPES[t]) throw new UnsupportedSchemaError(`unknown type ${t}`); return TYPES[t](v); })) fail("type", `expected ${ts.join("|")}, got ${typeOf(v)}`); }
  if ("const" in s && !deepEqual(v, s.const)) fail("const", `expected ${short(s.const)}, got ${short(v)}`);
  if ("enum" in s && !s.enum.some((e) => deepEqual(v, e))) fail("enum", `${short(v)} is not one of ${s.enum.length} allowed values`);

  if (typeof v === "string") {
    const len = [...v].length;
    if ("minLength" in s && len < s.minLength) fail("minLength", `${len} < ${s.minLength}`);
    if ("maxLength" in s && len > s.maxLength) fail("maxLength", `${len} > ${s.maxLength}`);
    if ("pattern" in s && !new RegExp(s.pattern, "u").test(v)) fail("pattern", `${short(v)} does not match ${s.pattern}`);
    if ("format" in s) {
      const check = FORMATS[s.format];
      if (!check) throw new UnsupportedSchemaError(`unsupported format "${s.format}" at ${at || "/"}`);
      if (!check(v)) fail("format", `${short(v)} is not a ${s.format}`);
    }
  }
  if (typeof v === "number") {
    if ("minimum" in s && v < s.minimum) fail("minimum", `${v} < ${s.minimum}`);
    if ("maximum" in s && v > s.maximum) fail("maximum", `${v} > ${s.maximum}`);
    if ("exclusiveMinimum" in s && v <= s.exclusiveMinimum) fail("exclusiveMinimum", `${v} <= ${s.exclusiveMinimum}`);
    if ("exclusiveMaximum" in s && v >= s.exclusiveMaximum) fail("exclusiveMaximum", `${v} >= ${s.exclusiveMaximum}`);
  }
  if (isObject(v)) {
    const keys = Object.keys(v);
    for (const k of s.required ?? []) if (!Object.hasOwn(v, k)) fail("required", `missing "${k}"`);
    if ("minProperties" in s && keys.length < s.minProperties) fail("minProperties", `${keys.length} < ${s.minProperties}`);
    if ("maxProperties" in s && keys.length > s.maxProperties) fail("maxProperties", `${keys.length} > ${s.maxProperties}`);
    const props = s.properties ?? {};
    for (const k of keys) {
      if (Object.hasOwn(props, k)) errs.push(...sub(props[k], v[k], `${at}/${k}`));
      else if ("additionalProperties" in s) {
        const extra = sub(s.additionalProperties, v[k], `${at}/${k}`);
        if (extra.length) fail("additionalProperties", `"${k}" is not allowed (${extra[0]})`);
      }
    }
  }
  if (Array.isArray(v)) {
    const prefix = s.prefixItems ?? [];
    prefix.forEach((p, i) => { if (i < v.length) errs.push(...sub(p, v[i], `${at}/${i}`)); });
    if ("items" in s) for (let i = prefix.length; i < v.length; i++) errs.push(...sub(s.items, v[i], `${at}/${i}`));
    if ("minItems" in s && v.length < s.minItems) fail("minItems", `${v.length} < ${s.minItems}`);
    if ("maxItems" in s && v.length > s.maxItems) fail("maxItems", `${v.length} > ${s.maxItems}`);
    if (s.uniqueItems === true) for (let i = 0; i < v.length; i++) for (let j = i + 1; j < v.length; j++) if (deepEqual(v[i], v[j])) fail("uniqueItems", `items ${i} and ${j} are equal`);
    if ("contains" in s) {
      const n = v.filter((x, i) => ok(s.contains, x, `${at}/${i}`)).length;
      const min = s.minContains ?? 1;
      if (n < min) fail("contains", `${n} matching item(s), at least ${min} required`);
      if ("maxContains" in s && n > s.maxContains) fail("maxContains", `${n} matching items, at most ${s.maxContains} allowed`);
    }
  }
  for (const [i, part] of (s.allOf ?? []).entries()) errs.push(...sub(part, v, at).map((e) => `${e} (allOf ${i})`));
  if ("anyOf" in s && !s.anyOf.some((part) => ok(part, v, at))) fail("anyOf", "matches none of the alternatives");
  if ("oneOf" in s) {
    const n = s.oneOf.filter((part) => ok(part, v, at)).length;
    if (n !== 1) fail("oneOf", `matches ${n} of ${s.oneOf.length} alternatives, exactly one required`);
  }
  if ("not" in s && ok(s.not, v, at)) fail("not", "matches a forbidden schema");
  if ("if" in s) {
    const branch = ok(s.if, v, at) ? s.then : s.else;
    if (branch !== undefined) errs.push(...sub(branch, v, at));
  }
  return errs;
}

export function validateSchema(schema, value) {
  return run(schema, value, "", schema);
}
