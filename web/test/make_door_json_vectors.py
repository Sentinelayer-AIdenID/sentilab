"""Writes web/test/door-json-vectors.json: request bodies with the open-proposal contract's own envelope verdicts.

The door's strict JSON reader (web/src/door/strict-json.js) must refuse exactly what the intake's reader refuses:
open_proposals/contract/validator.py _json with fenced=False, which #81's app/door/intake.py read_object applies to
every submit body. This script asks that reader about a fixed list of bodies (duplicates at every depth, depth limits,
non-finite numbers, every malformed form) and records its codes; web/test/door-json.test.mjs replays them.

    python web/test/make_door_json_vectors.py           # rewrite the vectors
    python web/test/make_door_json_vectors.py --check   # exit 1 when the file differs from what this tree generates
"""
import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from open_proposals.contract import validator  # noqa: E402

OUT = Path(__file__).resolve().parent / "door-json-vectors.json"
# A token-shaped value, assembled from its fields so no literal here looks like a credential.
SAMPLE_T = ".".join(["spt1", "place-chiplets", "cpu-dram", "1793500000", "0123456789abcdef", "0" * 32])
REF = "36.35.0,54.35.0,54.55.0,36.55.0,17.35.0,73.35.0,73.55.0,17.55.0"
DIE = '{"die":0,"x_um":18000,"y_um":17500,"rot_deg":0}'

BODIES = [
    # clean
    "{}", " \t\r\n{}\r\n", '{"a":1}', '{"a":true,"b":false,"c":null}', '{"a":[1,2,3],"b":{"c":"d"}}',
    '{"t":"' + SAMPLE_T + '","layout":"' + REF + '"}', '{"t":"' + SAMPLE_T + '","layout":[' + DIE + "]}",
    '{"t":"' + SAMPLE_T + '","layout":"' + REF + '","request_key":"door-0123"}',
    '{"a":[[[1]]]}', '{"a":{"b":{"c":1}}}', '{"a":"[[[[[[[[["}', '{"a":"\\"[[[[[[["}', '{"a":"\\\\"}',
    '{"a":"\\u00e9\\uD834\\uDD1E\\ud800"}', '{"a":"é\u007f"}', '{"a":-0}', '{"a":1e-400}', '{"a":-1.5E+3}',
    '{"a":' + "9" * 400 + "}", '{"a":0.5}', '{"":1}', '{"a":"\\/\\b\\f\\n\\r\\t"}',
    # duplicate keys at every depth
    '{"a":1,"a":2}', '{"t":"x","layout":"36.35.0","layout":"' + REF + '"}', '{"t":"bad","t":"' + SAMPLE_T + '","layout":"x"}',
    '{"":1,"":2}', '{"a":{"b":1,"b":2}}', '{"a":[{"b":1,"b":2}]}', '{"a":[[{"b":1,"b":2}]]}',
    '{"a":{"b":{"c":1,"c":2}}}', '{"a":1,"b":2,"a":3}', '{"a":{"b":1},"c":{"b":2}}',
    # depth
    '{"a":[[[[1]]]]}', '{"a":[[[[[[[[[[1]]]]]]]]]]}', '{"a":{"b":{"c":{"d":1}}}}', '{"a":[[[[', '{{{{{',
    # non-finite numbers
    '{"a":NaN}', '{"a":Infinity}', '{"a":-Infinity}', '{"a":1e400}', '{"a":-1e400}', '{"a":1.0e999}',
    '{"a":NaN,"a":1}', '{"a":[NaN]}', '{"a":{"b":Infinity}}',
    # malformed
    "", " ", "[]", "1", '"x"', "null", "﻿{}", " {}", "{", "{}x", "{} {}", '{"a":1}x', '{"a":1,}',
    '{,"a":1}', '{"a":1,,"b":2}', '{"a" 1}', '{a:1}', "{'a':1}", '{"a":01}', '{"a":.5}', '{"a":1.}', '{"a":-}',
    '{"a":+1}', '{"a":1e}', '{"a":0x1}', '{"a":\'b\'}', '{"a":"\\x"}', '{"a":"\\u12"}', '{"a":"\\u12G4"}',
    '{"a":"b\tc"}', '{"a":"b\nc"}', '{"a":"\u0000"}', '{"a":"b}', '{"a":tru}', '{"a":nul}', '{"a":True}',
    '{"a":NaNx}', '{"a":Infinityx}', '{"a":-Infinityx}', '{"a":[1,2,]}', '{"a":[,1]}', '{"a":[1 2]}',
    '{"a":1/**/}', '{"a":1}//', '{"a":1 // c\n}', '{"a"::1}', '{"a":1}}', '{"a":[1]]}',
]


def verdict(text):
    value, found = validator._json(text, fenced=False)
    return {"text": text, "codes": sorted({entry["code"] for entry in found}, key=lambda code: ORDER.index(code)),
            "ok": value is not None and not found}


ORDER = ["malformed_json", "duplicate_key", "nonfinite_number", "too_deep"]


def generate():
    source = (REPO / "open_proposals" / "contract" / "validator.py").read_bytes()
    document = {
        "schema": "sentilab-door-json-vectors/1",
        "reader": "open_proposals/contract/validator.py _json(fenced=False)",
        "validator_sha256": hashlib.sha256(source).hexdigest(),
        "generator": "web/test/make_door_json_vectors.py",
        "vectors": [verdict(text) for text in BODIES],
    }
    return (json.dumps(document, ensure_ascii=True, separators=(",", ":")) + "\n").replace('{"text"', '\n{"text"').encode("ascii")


if __name__ == "__main__":
    data = generate()
    if "--check" in sys.argv:
        sys.exit(0 if OUT.read_bytes() == data else 1)
    OUT.write_bytes(data)
    print("wrote", OUT.name, len(json.loads(data)["vectors"]), "vectors")
