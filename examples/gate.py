#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The gate used in README's 30-second example.

A small validator that understands the subset of JSON Schema that
schema.json uses, so the example needs nothing installed.

    python gate.py <target-dir>      # exit 0 = accept, exit 1 = reject

Replace it with your own gate: a linter, a CI step, a policy check, an LLM
guardrail — anything that exits non-zero to mean "reject".
"""
import json
import sys
from pathlib import Path

TYPES = {"string": str, "integer": int, "number": (int, float),
         "boolean": bool, "array": list, "object": dict}


def check(schema, value, path="$"):
    """Return an error string, or None if the value satisfies the schema."""
    if not isinstance(schema, dict):
        return "%s: the schema for this value is not an object" % path

    t = schema.get("type")
    if t is not None:
        py = TYPES.get(t)
        if py is None:
            return "%s: schema declares an unknown type %r" % (path, t)
        if isinstance(value, bool) and t != "boolean":
            return "%s: expected %s, got boolean" % (path, t)
        if not isinstance(value, py):
            return "%s: expected %s, got %s" % (path, t, type(value).__name__)

    if "enum" in schema and value not in schema["enum"]:
        return "%s: %r is not one of %s" % (path, value, schema["enum"])
    if "minLength" in schema and isinstance(value, str) and len(value) < schema["minLength"]:
        return "%s: shorter than minLength %d" % (path, schema["minLength"])
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            return "%s: %r is below minimum %s" % (path, value, schema["minimum"])
        if "maximum" in schema and value > schema["maximum"]:
            return "%s: %r is above maximum %s" % (path, value, schema["maximum"])
    if "minItems" in schema and isinstance(value, list) and len(value) < schema["minItems"]:
        return "%s: fewer than minItems %d" % (path, schema["minItems"])

    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                return "%s: missing required property %r" % (path, key)
        for key, sub in schema.get("properties", {}).items():
            if key in value:
                err = check(sub, value[key], "%s.%s" % (path, key))
                if err:
                    return err

    if "items" in schema and isinstance(value, list):
        for i, item in enumerate(value):
            err = check(schema["items"], item, "%s[%d]" % (path, i))
            if err:
                return err

    return None


def main() -> int:
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    try:
        schema = json.loads((target / "schema.json").read_text(encoding="utf-8"))
        data = json.loads((target / "data.json").read_text(encoding="utf-8"))
    except Exception as exc:  # an unreadable config counts as a rejection
        print("REJECT: cannot read the config: %s: %s" % (type(exc).__name__, exc))
        return 1

    err = check(schema, data)
    if err:
        print("REJECT: %s" % err)
        return 1

    print("PASS: data.json satisfies schema.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
