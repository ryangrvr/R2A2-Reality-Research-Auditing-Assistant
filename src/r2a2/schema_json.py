"""Public JSON Schema for the R2A2 scientific vocabulary (2020-12).

The schema is the interoperability contract, NOT the Python implementation.
It is generated from the live vocabulary (enums, required fields) so the
dataclasses and the schema cannot silently drift.

Design rules:
- schema version is explicit (`r2a2_schema`);
- unknown required fields fail (additionalProperties controlled);
- invalid enum values fail;
- optional extension namespaces (`x_*` properties) are allowed without
  weakening core validation;
- every artifact type is a named $defs entry.

Validation: jsonschema is an optional dependency; a minimal built-in
validator covers the required/enum/additionalProperties semantics so
`r2a2 validate-artifact` works with zero dependencies.
"""

from __future__ import annotations

from typing import Any, Dict

from .api import (ASSUMPTION_KINDS, EVIDENCE_GRADES, PARAM_KINDS, TEST_KINDS)
from .schema import SCHEMA_VERSION
from .verdicts import VERDICTS

# R2A2-specific epistemic terms live in this namespace in exports (PROV, crates)
R2A2_NS = "https://r2a2-science.org/schema/"


def _str_enum(values) -> dict:
    return {"type": "string", "enum": sorted(values)}


def _obj(properties: dict, required: list, additional: bool = True) -> dict:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": additional,
    }


def _artifact(base: dict) -> dict:
    """Common artifact wrapper: schema-stamped, extensions allowed."""
    return {
        "type": "object",
        "properties": {
            "r2a2_schema": {"type": "string", "const": SCHEMA_VERSION},
            **base["properties"],
            # extension namespace: any x_-prefixed key is allowed
        },
        "required": ["r2a2_schema", *base.get("required", [])],
        "additionalProperties": False,
        "patternProperties": {"^x_": {}},
    }


def build_schema() -> dict:
    """Build the complete public schema document."""
    parameter = _obj({
        "name": {"type": "string"},
        "kind": _str_enum(PARAM_KINDS),
        "sector": {"type": "string"},
        "source": {"type": ["string", "null"]},
        "value": {},
    }, ["name", "kind"])

    assumption = _obj({
        "id": {"type": "string"},
        "text": {"type": "string"},
        "kind": _str_enum(ASSUMPTION_KINDS),
        "priced": {"type": "boolean"},
        "source": {"type": ["string", "null"]},
    }, ["id"])

    prediction = _obj({
        "id": {"type": "string"},
        "description": {"type": "string"},
        "experiment": {"type": "string"},
        "observable": {"type": "string"},
        "kill_condition": {"type": "string", "minLength": 1},
        "assumptions": {"type": "array", "items": {"type": "string"}},
        "parameters": {"type": "array", "items": {"type": "string"}},
        "evidence_grade": _str_enum(EVIDENCE_GRADES),
        "sector": {"type": "string"},
        "comparator": {"type": ["string", "null"]},
    }, ["id", "experiment", "kill_condition"])

    test = _obj({
        "id": {"type": "string"},
        "kind": _str_enum(TEST_KINDS),
        "experiment": {"type": "string"},
        "description": {"type": "string"},
        "exact": {"type": "boolean"},
        "comparator": {"type": ["string", "null"]},
        "preregistered": {"type": "boolean"},
    }, ["id", "kind", "experiment"])

    theory = {
        "type": "object",
        "properties": {
            "r2a2_schema": {"type": "string", "const": SCHEMA_VERSION},
            "id": {"type": "string"},
            "version": {"type": "string"},
            "description": {"type": "string"},
            "validity_domain": {"type": "string"},
            "sources": {"type": "array", "items": {"type": "object",
                        "properties": {"id": {"type": "string"},
                                       "description": {"type": "string"}},
                        "required": ["id"], "additionalProperties": True}},
            "parameters": {"type": "array", "items": parameter},
            "assumptions": {"type": "array", "items": assumption},
            "predictions": {"type": "array", "items": prediction},
            "tests": {"type": "array", "items": test},
            # executable pieces travel as module:qualname references (never code)
            "experiments": {"type": "object",
                            "additionalProperties": {"type": "string",
                                                     "pattern": ":.*\\S"}},
            "transformation_classes": {"type": "array", "items": {
                "type": "object",
                "properties": {"id": {"type": "string"},
                               "description": {"type": "string"},
                               "is_member": {"type": "string"},
                               "compose": {"type": "string"},
                               "canonicalize": {"type": "string"},
                               "invariants": {"type": "string"},
                               "quotient_distance": {"type": "string"},
                               "optimise": {"type": "string"}},
                "required": ["id"], "additionalProperties": True}},
            "comparators": {"type": "array", "items": {
                "type": "object",
                "properties": {"id": {"type": "string"},
                               "description": {"type": "string"},
                               "model": {"type": "string"},
                               "source": {"type": ["string", "null"]}},
                "required": ["id"], "additionalProperties": True}},
            "transformations": {"type": "array", "items": {"type": "object"}},
        },
        "required": ["r2a2_schema", "id", "version"],
        "additionalProperties": False,
        "patternProperties": {"^x_": {}},
    }

    code_binding = _obj({
        "ref": {"type": "string"},
        "source_hash": {"type": "string"},  # content hash or "<unbound>"
    }, ["ref", "source_hash"])

    execution_manifest = _obj({
        "theory_id": {"type": "string"},
        "theory_version": {"type": "string"},
        "parameters": {"type": "object"},
        "parameter_sources": {"type": "object"},
        "tests": {"type": "array", "items": {"type": "string"}},
        "predictions": {"type": "array", "items": {"type": "string"}},
        "thresholds": {"type": "object"},
        "datasets": {"type": "object"},
        "seeds": {"type": "object"},
        "backend": {"type": "string"},
        "environment": {"type": "object"},
        "frozen": {"type": "boolean", "const": True},
        "hash": {"type": "string", "minLength": 64},
        "theory_declaration_hash": {"type": "string", "minLength": 64},
        "experiment_bindings": {"type": "object",
                                "additionalProperties": code_binding},
        "transformation_bindings": {"type": "object"},
    }, ["theory_id", "theory_version", "frozen", "hash",
        "theory_declaration_hash", "backend"])

    result_record = _obj({
        "node": {"type": "string"},
        "experiment": {"type": "string"},
        "backend": {"type": "string"},
        "manifest_hash": {"type": "string", "minLength": 64},
        "result": {},
        "result_hash": {"type": "string", "minLength": 64},
        "wall_time": {"type": "number"},  # metadata, OUTSIDE result_hash
    }, ["experiment", "manifest_hash", "result_hash"])

    replication_record = _obj({
        "test_id": {"type": "string"},
        "rule": {"type": "object",
                 "properties": {"kind": _str_enum(("tolerance", "structural")),
                                "tolerance": {"type": ["number", "null"]},
                                "observable": {"type": "string"}},
                 "required": ["kind"], "additionalProperties": True},
        "impl_a": {"type": "object"},
        "impl_b": {"type": "object"},
        "independence_level": _str_enum(
            ("L1-same-algorithm-separate-code",
             "L2-separate-algorithm-same-equations",
             "L3-independent-derivation-and-implementation")),
        "independence_note": {"type": "string"},
        "value_a": {},
        "value_b": {},
        "manifest_hash": {"type": "string"},
        "agrees": {"type": "boolean"},
        "detail": {"type": "string"},
        "record_hash": {"type": "string", "minLength": 64},
    }, ["test_id", "rule", "independence_level", "agrees", "record_hash"])

    review_attestation = _obj({
        "reviewer": {"type": "string"},
        "scope": {"type": "string"},
        "manifest_hash": {"type": "string"},
        "result_hash": {"type": "string"},
        "code_revision": {"type": "string"},
        "verdict": {"type": "string"},
        "notes": {"type": "string"},
        "issues": {"type": "array", "items": {"type": "string"}},
        "seal": {"type": "string", "minLength": 64},
    }, ["reviewer", "scope", "manifest_hash", "result_hash",
        "code_revision", "verdict", "seal"])

    transfer_record = _obj({
        "outcome": _str_enum(("PASS", "FAIL")),
        "lines": {"type": "array", "items": {"type": "object",
                  "properties": {"name": {"type": "string"},
                                 "status": {"type": "string"},
                                 "note": {"type": "string"}},
                  "required": ["name", "status"], "additionalProperties": True}},
        "reasons": {"type": "array", "items": {"type": "string"}},
    }, ["outcome"])

    verdict_meta = _obj({
        "verdict": _str_enum(VERDICTS),
        "test_outcome": _str_enum(("KILL", "BANK", "EXTEND")),
        "justification": {"type": "string"},
    }, [])

    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"{R2A2_NS}v{SCHEMA_VERSION}",
        "title": "R2A2 scientific vocabulary",
        "description": "Public interoperability contract for R2A2 artifacts. "
                       "R2A2 verifies discipline, not truth.",
        "$defs": {
            "parameter": parameter,
            "assumption": assumption,
            "prediction": prediction,
            "test": test,
            "theory": theory,
            "code_binding": code_binding,
            "execution_manifest": _artifact(execution_manifest),
            "result_record": _artifact(result_record),
            "replication_record": _artifact(replication_record),
            "review_attestation": _artifact(review_attestation),
            "transfer_record": _artifact(transfer_record),
            "verdict_meta": _artifact(verdict_meta),
        },
        # default: validate against theory unless $ref given
        "$ref": "#/$defs/theory",
    }


def validate_artifact(doc: dict, kind: str = "auto",
                      require_full: bool = True) -> list:
    """Validate a document against the public schema.

    Returns a list of error strings (empty = valid).

    FAIL-CLOSED POLICY (standards conformance, v0.4.1): the dependency-free
    fallback validator does NOT enforce every JSON Schema keyword, so it can
    only give weaker guarantees. When ``require_full`` is set (default) and
    the ``jsonschema`` package is not installed, this function REFUSES to
    claim full conformance and returns an explicit error instead of silently
    'mostly validating'. Callers who knowingly accept the weaker check pass
    ``require_full=False``; the returned list still begins with a warning
    marking the validation as partial.
    """
    schema = build_schema()
    if kind != "auto" and kind in schema["$defs"]:
        sub = schema["$defs"][kind]
    elif kind == "auto":
        sub = schema["$defs"][schema["$ref"].split("/")[-1]]
    else:
        sub = schema
    try:
        import jsonschema  # type: ignore
        from jsonschema import Draft202012Validator
        validator = Draft202012Validator(sub)
        return [f"{'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}"
                for e in validator.iter_errors(doc)]
    except ImportError:
        if require_full:
            return [
                "FULL-SCHEMA VALIDATOR REQUIRED: the optional 'jsonschema' "
                "package is not installed, and the built-in fallback cannot "
                "enforce every keyword (e.g. pattern, type unions). Install "
                "it: pip install jsonschema — or call with require_full=False "
                "to accept explicitly partial validation."]
        errors = _minimal_validate(sub, doc)
        return ["WARNING: partial validation (jsonschema not installed; "
                "fallback enforces required/enum/const/additionalProperties "
                "only)"] + errors


def _minimal_validate(schema: dict, doc, path: str = "", errors: list = None) -> list:
    """Dependency-free validator covering the subset we rely on: type=object,
    required, properties (recursive), additionalProperties, enum, const,
    minLength, patternProperties (extension namespace)."""
    errors = [] if errors is None else errors
    # resolve local $refs ($defs references)
    if schema.get("$ref", "").startswith("#/$defs/"):
        root = build_schema()
        return _minimal_validate(root["$defs"][schema["$ref"].split("/")[-1]],
                                 doc, path, errors)
    if "properties" in schema or schema.get("type") == "object":
        if not isinstance(doc, dict):
            errors.append(f"{path or '<root>'}: expected object, got {type(doc).__name__}")
            return errors
        for req in schema.get("required", []):
            if req not in doc:
                errors.append(f"{path or '<root>'}/{req}: required field missing")
        props = schema.get("properties", {})
        addl = schema.get("additionalProperties", True)
        patterns = schema.get("patternProperties", {})
        import re
        for k, v in doc.items():
            if k in props:
                _minimal_validate(props[k], v, f"{path}/{k}", errors)
            elif any(re.match(p, k) for p in patterns):
                continue  # extension namespace
            elif addl is False:
                errors.append(f"{path}/{k}: unknown field (not in schema)")
    if schema.get("type") == "array" or "items" in schema:
        if not isinstance(doc, list):
            errors.append(f"{path or '<root>'}: expected array, got {type(doc).__name__}")
            return errors
        for i, v in enumerate(doc):
            _minimal_validate(schema["items"], v, f"{path}[{i}]", errors)
    if "enum" in schema and isinstance(doc, str) and doc not in schema["enum"]:
        errors.append(f"{path}: value {doc!r} not in {schema['enum']}")
    if "const" in schema and doc != schema["const"]:
        errors.append(f"{path}: must be {schema['const']!r}, got {doc!r}")
    if "minLength" in schema and isinstance(doc, str) and len(doc) < schema["minLength"]:
        errors.append(f"{path}: shorter than {schema['minLength']} characters")
    return errors


def schema_version_check(doc: dict) -> list:
    """Explicit schema-version gate: unknown versions fail loudly."""
    v = doc.get("r2a2_schema")
    if v is None:
        return ["artifact missing 'r2a2_schema'"]
    if v != SCHEMA_VERSION:
        return [f"artifact schema {v!r} != this build's {SCHEMA_VERSION!r}; "
                "migrate first (r2a2.schema.migrate)"]
    return []
