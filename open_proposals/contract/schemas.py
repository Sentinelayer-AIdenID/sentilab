"""The contract's JSON Schemas (draft 2020-12), validated offline, with errors mapped to reason codes.

Schemas resolve only against each other through a local registry; nothing is ever fetched. "integer" means a JSON
integer literal: Python's json parses 17000.0 and 1e4 as floats, which this checker refuses (JSON Schema's own
"integer" would accept them). Errors become unknown_field (the containing object's path) or schema_invalid (the path
and the failing keyword). Paths are built only from schema-declared property names and array indices, so no
submitted text is ever echoed.

"pattern" is ECMA-262, JSON Schema's regex dialect: without the multiline flag, $ matches only at the end of the input.
Python's $ also matches just before a final newline, so "t-1\n" would pass "^...$" here and fail in JavaScript; every
$ outside a character class is therefore read as \Z (ecma_pattern), and Python and JavaScript agree on each pattern
(vectors-canonical.json "patterns").
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from jsonschema import Draft202012Validator, ValidationError
from jsonschema.validators import extend
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

CONTRACT_DIR = Path(__file__).resolve().parents[2] / "contracts" / "open-proposal-v1"
SCHEMA_DIR = CONTRACT_DIR / "schemas"
NAMES = ("common", "manifest", "proposal", "check-request", "team", "publish", "terms", "geometry", "transport-key",
         "check", "receipt", "status", "results", "reason-codes")
# The objects a participant posts, by their "schema" value.
POSTED = {"sentilab-open-proposal/1": "proposal", "sentilab-open-check-request/1": "check-request",
          "sentilab-open-team/1": "team", "sentilab-open-publish/1": "publish"}


def _is_integer(_checker, instance):
    return isinstance(instance, int) and not isinstance(instance, bool)


def _is_number(_checker, instance):
    return isinstance(instance, (int, float)) and not isinstance(instance, bool)


def ecma_pattern(pattern: str) -> str:
    """The Python spelling of an ECMA-262 pattern: each $ outside a character class becomes \Z (the end of the input,
    as $ is in ECMA-262 without the multiline flag). Escapes and classes are copied as they are."""
    out, in_class, escaped = [], False, False
    for char in pattern:
        if escaped:
            escaped = False
        elif char == "\\":
            escaped = True
        elif in_class:
            in_class = char != "]"
        elif char == "[":
            in_class = True
        elif char == "$":
            out.append(r"\Z")
            continue
        out.append(char)
    return "".join(out)


_COMPILED = {}


def pattern_matches(pattern: str, text: str) -> bool:
    """JSON Schema's "pattern": an unanchored search, with ECMA-262's $."""
    compiled = _COMPILED.get(pattern)
    if compiled is None:
        compiled = _COMPILED[pattern] = re.compile(ecma_pattern(pattern))
    return compiled.search(text) is not None


def _pattern(validator, pattern, instance, _schema):
    if validator.is_type(instance, "string") and not pattern_matches(pattern, instance):
        yield ValidationError("does not match the pattern")          # never the instance: no echo


StrictValidator = extend(Draft202012Validator, validators={"pattern": _pattern},
                         type_checker=Draft202012Validator.TYPE_CHECKER.redefine_many(
                             {"integer": _is_integer, "number": _is_number}))


def load_schemas(schema_dir: Path = SCHEMA_DIR) -> dict:
    return {name: json.loads((schema_dir / f"{name}.schema.json").read_bytes()) for name in NAMES}


def build_registry(schemas: dict) -> Registry:
    return Registry().with_resources(
        (schema["$id"], Resource.from_contents(schema, default_specification=DRAFT202012))
        for schema in schemas.values())


SCHEMAS = load_schemas()
REGISTRY = build_registry(SCHEMAS)
VALIDATORS = {name: StrictValidator(schema, registry=REGISTRY) for name, schema in SCHEMAS.items()}
# One shared definition on its own, e.g. a violation handed back through the layout seam.
_DEF_VALIDATORS = {name: StrictValidator({"$ref": SCHEMAS["common"]["$id"] + "#/$defs/" + name}, registry=REGISTRY)
                   for name in ("violation",)}


def def_is_valid(name: str, instance) -> bool:
    return _DEF_VALIDATORS[name].is_valid(instance)


def pointer(path) -> str:
    return "".join("/" + str(part) for part in path)


def schema_violations(name: str, instance) -> list:
    """Every schema error as a violation, deduplicated, in a stable order."""
    found = []
    for error in VALIDATORS[name].iter_errors(instance):
        path = list(error.absolute_path)
        if error.validator == "additionalProperties":
            found.append({"code": "unknown_field", "path": pointer(path)})
        elif error.validator == "required":
            present = error.instance if isinstance(error.instance, dict) else {}
            for missing in error.validator_value:
                if missing not in present:
                    found.append({"code": "schema_invalid", "path": pointer(path + [missing]), "keyword": "required"})
        else:
            found.append({"code": "schema_invalid", "path": pointer(path), "keyword": str(error.validator)})
    unique = {json.dumps(item, sort_keys=True): item for item in found}
    return [unique[key] for key in sorted(unique)]
