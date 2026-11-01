// The strict JSON reader for the body of POST /agents/submit: the open-proposal contract's envelope stage
// (open_proposals/contract/validator.py _json with fenced=False, the reader #81's intake applies through
// app/door/intake.py read_object), so the door never chooses among values the intake would refuse to read.
//   - Only space, tab, CR and LF are trimmed; the text must then start with "{" (a byte-order mark is malformed).
//   - too_deep: more than 4 nested objects or arrays, found by a lexical pre-scan before parsing, as the contract does.
//   - malformed_json: anything RFC 8259 refuses (trailing commas, comments, single quotes, leading zeros, raw control
//     characters in strings, a second value), and a root that is not an object.
//   - duplicate_key: a key twice in any one object, at any depth; parsing goes on, so a body can have more findings.
//   - nonfinite_number: NaN, Infinity or -Infinity, which Python's reader accepts as constants, or a float that
//     overflows. An integer literal is never flagged here, as in Python, where integers do not overflow.
//   - A number written with a fraction or an exponent is a float: it is returned boxed (a Number object), so no field
//     that must be an integer accepts 18000.0, 1.75e4 or 0e0. The contract's integers are JSON integer literals.
// Findings are returned in the contract's code order. The reader is bounded: the body is at most 4,096 bytes and the
// pre-scan caps recursion at 4 levels. A module of its own because worker.js may export nothing but its default handler.
export const MAX_DEPTH = 4;
const SPACE = " \t\r\n";
const NUMBER = /-?(?:0|[1-9][0-9]*)(\.[0-9]+)?([eE][-+]?[0-9]+)?/y;
const MALFORMED = Symbol("malformed_json");
const ESCAPES = Object.freeze({ '"': '"', "\\": "\\", "/": "/", b: "\b", f: "\f", n: "\n", r: "\r", t: "\t" });

function trim(text) {
  let start = 0;
  let end = text.length;
  while (start < end && SPACE.includes(text[start])) start += 1;
  while (end > start && SPACE.includes(text[end - 1])) end -= 1;
  return text.slice(start, end);
}

// The contract's pre-scan: brackets outside strings, counted lexically, so even malformed text can be too deep.
export function tooDeep(text) {
  let depth = 0;
  let inString = false;
  let escaped = false;
  for (const char of text) {
    if (inString) {
      if (escaped) escaped = false;
      else if (char === "\\") escaped = true;
      else if (char === '"') inString = false;
    } else if (char === '"') inString = true;
    else if (char === "{" || char === "[") {
      depth += 1;
      if (depth > MAX_DEPTH) return true;
    } else if (char === "}" || char === "]") depth -= 1;
  }
  return false;
}

// { value } for a clean object, or { codes } with the contract's envelope codes.
export function strictJson(raw) {
  const text = trim(String(raw));
  if (!text.startsWith("{")) return { codes: [{ code: "malformed_json" }] };
  if (tooDeep(text)) return { codes: [{ code: "too_deep" }] };
  const flags = new Set();
  let at = 0;
  const fail = () => { throw MALFORMED; };
  const space = () => { while (at < text.length && SPACE.includes(text[at])) at += 1; };
  const literal = (word, value) => {
    if (text.startsWith(word, at)) { at += word.length; return value; }
    return fail();
  };
  const constant = (word) => { at += word.length; flags.add("nonfinite_number"); return 0; };

  function string() {
    at += 1; // the opening quote
    let out = "";
    for (;;) {
      if (at >= text.length) fail();
      const char = text[at];
      if (char === '"') { at += 1; return out; }
      if (char < " ") fail(); // a raw control character
      if (char !== "\\") { out += char; at += 1; continue; }
      const next = text[at + 1];
      if (next === "u") {
        const hex = text.slice(at + 2, at + 6);
        if (!/^[0-9a-fA-F]{4}$/.test(hex)) fail();
        out += String.fromCharCode(parseInt(hex, 16));
        at += 6;
      } else if (next !== undefined && Object.hasOwn(ESCAPES, next)) {
        out += ESCAPES[next];
        at += 2;
      } else fail();
    }
  }

  function number() {
    NUMBER.lastIndex = at;
    const match = NUMBER.exec(text);
    if (!match) return fail();
    at = NUMBER.lastIndex;
    const value = Number(match[0]);
    if (match[1] === undefined && match[2] === undefined) return value;
    if (!Number.isFinite(value)) { flags.add("nonfinite_number"); return 0; }
    return new Number(value); // a float literal: never an integer, whatever its value
  }

  function object() {
    at += 1;
    const entries = [];
    const keys = new Set();
    space();
    if (text[at] === "}") { at += 1; return Object.fromEntries(entries); }
    for (;;) {
      space();
      if (text[at] !== '"') fail();
      const key = string();
      if (keys.has(key)) flags.add("duplicate_key");
      keys.add(key);
      space();
      if (text[at] !== ":") fail();
      at += 1;
      space();
      entries.push([key, value()]);
      space();
      if (text[at] === "}") { at += 1; return Object.fromEntries(entries); }
      if (text[at] !== ",") fail();
      at += 1;
    }
  }

  function array() {
    at += 1;
    const items = [];
    space();
    if (text[at] === "]") { at += 1; return items; }
    for (;;) {
      space();
      items.push(value());
      space();
      if (text[at] === "]") { at += 1; return items; }
      if (text[at] !== ",") fail();
      at += 1;
    }
  }

  function value() {
    const char = text[at];
    if (char === '"') return string();
    if (char === "{") return object();
    if (char === "[") return array();
    if (char === "n") return literal("null", null);
    if (char === "t") return literal("true", true);
    if (char === "f") return literal("false", false);
    if (char === "-" && text.startsWith("-Infinity", at)) return constant("-Infinity");
    if (char === "-" || (char >= "0" && char <= "9")) return number();
    if (text.startsWith("NaN", at)) return constant("NaN");
    if (text.startsWith("Infinity", at)) return constant("Infinity");
    return fail();
  }

  let parsed;
  try {
    parsed = value();
    space();
    if (at !== text.length) fail();
  } catch (error) {
    if (error === MALFORMED) return { codes: [{ code: "malformed_json" }] };
    throw error;
  }
  if (flags.size) return { codes: ["duplicate_key", "nonfinite_number"].filter((code) => flags.has(code)).map((code) => ({ code })) };
  return { value: parsed };
}
