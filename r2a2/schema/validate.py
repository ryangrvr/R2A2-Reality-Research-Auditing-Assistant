"""Minimal pure-Python validator for the subset of JSON Schema used by RAI.

RAI is local-first and deliberately low-dependency. The official `jsonschema`
package is used when available, but this module lets schema validation work
on machines where its compiled dependency (rpds-py) cannot be built.

Supported keywords: type, required, properties, items, enum, const,
pattern, minItems, minimum, additionalProperties (bool).
"""

import re

TYPE_MAP = {
    "object": dict,
    "array": list,
    "string": str,
    "number": (int, float),
    "integer": int,
    "boolean": bool,
    "null": type(None),
}


def _check(inst, schema, path, errors):
    if not isinstance(schema, dict):
        return
    types = schema.get("type")
    if types:
        types = [types] if isinstance(types, str) else types
        python_types = [TYPE_MAP[t] for t in types]
        # bool is a subclass of int; exclude that accidental match
        ok = any(
            isinstance(inst, pt) and not (pt is int and isinstance(inst, bool))
            for pt in python_types
        )
        if not ok:
            errors.append(f"{path}: expected type {types}, got {type(inst).__name__}")
            return
    if "const" in schema and inst != schema["const"]:
        errors.append(f"{path}: expected const {schema['const']!r}, got {inst!r}")
    if "enum" in schema and inst not in schema["enum"]:
        errors.append(f"{path}: {inst!r} is not one of {schema['enum']}")
    if "pattern" in schema and isinstance(inst, str):
        if not re.search(schema["pattern"], inst):
            errors.append(f"{path}: {inst!r} does not match pattern {schema['pattern']!r}")
    if isinstance(inst, dict):
        for req in schema.get("required", []):
            if req not in inst:
                errors.append(f"{path}: missing required property {req!r}")
        props = schema.get("properties", {})
        for key, value in inst.items():
            if key in props:
                _check(value, props[key], f"{path}.{key}", errors)
        if schema.get("additionalProperties") is False and props:
            extra = set(inst) - set(props)
            for key in sorted(extra):
                errors.append(f"{path}: additional property {key!r} not allowed")
    elif isinstance(inst, list):
        if "minItems" in schema and len(inst) < schema["minItems"]:
            errors.append(f"{path}: expected at least {schema['minItems']} items")
        item_schema = schema.get("items")
        if item_schema:
            for i, item in enumerate(inst):
                _check(item, item_schema, f"{path}[{i}]", errors)
    if "minimum" in schema and isinstance(inst, (int, float)):
        if inst < schema["minimum"]:
            errors.append(f"{path}: {inst} is less than minimum {schema['minimum']}")


class ValidationError:
    def __init__(self, message):
        self.message = message

    def __repr__(self):
        return f"ValidationError({self.message!r})"


class Validator:
    """Duck-typed stand-in for jsonschema.Draft202012Validator."""

    def __init__(self, schema):
        self.schema = schema

    def iter_errors(self, instance):
        errors = []
        _check(instance, self.schema, "$", errors)
        return [ValidationError(e) for e in errors]


def check_schema(schema):
    """Basic sanity check: a schema must be a dict (or raise for garbage)."""
    if not isinstance(schema, dict):
        raise ValueError("schema must be a JSON object")
    return True
