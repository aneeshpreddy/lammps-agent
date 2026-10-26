"""Argument check for tool inputs against their JSON schema (plan Day 26, step 3).

Strict tool use (strict: true) already makes the API return schema-valid arguments; every tool checks
again anyway, because a direct Python call, a replayed trace or a future model without strict mode
can still hand it anything. Covers exactly the schema subset the tools use: type, enum, properties,
required, additionalProperties: false, items, anyOf. No dependency on the jsonschema package.
"""
from __future__ import annotations

from typing import List

_PY = {"object": dict, "array": list, "string": str, "boolean": bool, "null": type(None)}


def _is(t: str, v) -> bool:
    if t == "integer":
        return isinstance(v, int) and not isinstance(v, bool)
    if t == "number":
        return isinstance(v, (int, float)) and not isinstance(v, bool)
    return isinstance(v, _PY[t])


def check(schema: dict, value, path: str = "$") -> List[str]:
    """Returns the list of violations (empty = valid), each prefixed with its JSON path."""
    if "anyOf" in schema:
        if all(check(s, value, path) for s in schema["anyOf"]):
            forms = " or ".join(s.get("type", "?") if "enum" not in s else f"one of {s['enum']}" for s in schema["anyOf"])
            return [f"{path}: expected {forms}, got {value!r:.60}"]
        return []
    t = schema.get("type")
    if t and not _is(t, value):
        return [f"{path}: expected {t}, got {type(value).__name__}"]
    if "enum" in schema and value not in schema["enum"]:
        return [f"{path}: {value!r:.60} is not one of {schema['enum']}"]
    errs = []
    if t == "object":
        props = schema.get("properties", {})
        errs += [f"{path}: missing required field {k!r}" for k in schema.get("required", []) if k not in value]
        if schema.get("additionalProperties") is False:
            errs += [f"{path}: unknown field {k!r}" for k in value if k not in props]
        for k, v in value.items():
            if k in props:
                errs += check(props[k], v, f"{path}.{k}")
    elif t == "array" and "items" in schema:
        for i, v in enumerate(value):
            errs += check(schema["items"], v, f"{path}[{i}]")
    return errs
