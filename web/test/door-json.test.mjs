// node --test web/test/door-json.test.mjs
// The door's strict JSON reader (web/src/door/strict-json.js) against the open-proposal contract's own reader:
// door-json-vectors.json records open_proposals/contract/validator.py _json(fenced=False), the reader #81's intake
// applies to every submit body (app/door/intake.py read_object), on 94 bodies; make_door_json_vectors.py regenerates
// them. Each body must get exactly the contract's codes, or read cleanly where the contract reads it cleanly.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { MAX_DEPTH, strictJson, tooDeep } from "../src/door/strict-json.js";

const vectors = JSON.parse(readFileSync(new URL("./door-json-vectors.json", import.meta.url), "utf8"));

test("the door's reader gives the contract reader's verdict on every recorded body", () => {
  assert.equal(vectors.schema, "sentilab-door-json-vectors/1");
  assert.equal(vectors.reader, "open_proposals/contract/validator.py _json(fenced=False)");
  const kinds = new Set(vectors.vectors.flatMap((v) => v.codes));
  assert.deepEqual([...kinds].sort(), ["duplicate_key", "malformed_json", "nonfinite_number", "too_deep"], "every envelope code is exercised");
  assert.ok(vectors.vectors.filter((v) => v.ok).length >= 20, "and enough clean bodies");
  for (const vector of vectors.vectors) {
    const result = strictJson(vector.text);
    if (vector.ok) assert.ok("value" in result && !result.codes, JSON.stringify(vector.text));
    else assert.deepEqual(result, { codes: vector.codes.map((code) => ({ code })) }, JSON.stringify(vector.text));
  }
});

test("clean bodies read to the values JSON gives, with every key an own property, and float literals boxed", () => {
  const read = strictJson('{"t":"x","layout":[{"die":0,"x_um":18000}],"n":-1.5E+3,"z":null,"b":true}').value;
  assert.deepEqual({ ...read, n: null }, { t: "x", layout: [{ die: 0, x_um: 18000 }], n: null, z: null, b: true });
  // 18000.0, 1.75e4 and 0e0 are floats in the contract, never integers: they come back boxed, so Number.isInteger
  // refuses them while their value is kept.
  assert.ok(read.n instanceof Number && read.n.valueOf() === -1500);
  for (const literal of ["18000.0", "1.75e4", "0e0", "1E2"]) {
    const value = strictJson(`{"a":${literal}}`).value.a;
    assert.ok(value instanceof Number && !Number.isInteger(value), literal);
  }
  assert.equal(strictJson('{"a":18000}').value.a, 18000);
  const proto = strictJson('{"__proto__":{"x":1},"a":"\\u00e9\\uD834\\uDD1E"}').value;
  assert.ok(Object.hasOwn(proto, "__proto__") && Object.getPrototypeOf(proto) === Object.prototype);
  assert.equal(proto.a, "é\u{1D11E}");
  assert.deepEqual(strictJson(" \t\r\n{}\n").value, {});
});

test("the depth bound is the contract's: 4 nested containers read, 5 do not, and strings do not count", () => {
  assert.equal(MAX_DEPTH, 4);
  assert.equal(tooDeep('{"a":[[[1]]]}'), false);
  assert.equal(tooDeep('{"a":[[[[1]]]]}'), true);
  assert.equal(tooDeep('{"a":"[[[[[[[[[["}'), false);
  assert.equal(tooDeep('{"a":"\\"[[[[[[[[["}'), false);
  assert.deepEqual(strictJson("{{{{{"), { codes: [{ code: "too_deep" }] }, "even malformed text is too deep first");
});
