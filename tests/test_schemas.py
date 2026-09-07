"""Schema-validation tests for RAI's JSON Schemas and example artifacts."""

import json
from pathlib import Path

import pytest
import yaml

try:
    from jsonschema import Draft202012Validator as _JsonschemaValidator
except Exception:  # rpds-py native module missing/broken on this interpreter
    _JsonschemaValidator = None

from r2a2.schema.validate import Validator as _FallbackValidator, check_schema as _fallback_check

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = PROJECT_ROOT / "r2a2" / "schema"
EXAMPLE_CLAIMS = PROJECT_ROOT / "examples" / "minimal_project" / "claims"


def load_schema(name):
    with open(SCHEMA_DIR / name) as fh:
        return json.load(fh)


def make_validator(schema):
    if _JsonschemaValidator is not None:
        return _JsonschemaValidator(schema)
    return _FallbackValidator(schema)


def load_claims():
    claims = []
    for path in sorted(EXAMPLE_CLAIMS.glob("*.yaml")):
        with open(path) as fh:
            claims.append((path.name, yaml.safe_load(fh)))
    return claims


@pytest.fixture(scope="module")
def claim_validator():
    return make_validator(load_schema("claim.schema.json"))


@pytest.fixture(scope="module")
def run_validator():
    return make_validator(load_schema("run.schema.json"))


@pytest.fixture(scope="module")
def prereg_validator():
    return make_validator(load_schema("prereg.schema.json"))


def test_schemas_are_valid_json_schema():
    for name in ("claim.schema.json", "run.schema.json", "prereg.schema.json"):
        schema = load_schema(name)
        if _JsonschemaValidator is not None:
            _JsonschemaValidator.check_schema(schema)
        else:
            _fallback_check(schema)


def test_example_claims_exist():
    claims = load_claims()
    assert len(claims) >= 6


def test_all_example_claims_validate(claim_validator):
    for name, claim in load_claims():
        errors = list(claim_validator.iter_errors(claim))
        assert not errors, f"{name}: {[e.message for e in errors]}"


def test_example_covers_required_statuses():
    statuses = {claim["status"] for _, claim in load_claims()}
    for required in (
        "DECLARED_INPUT",
        "COMPUTED",
        "NEGATIVE_RESULT",
        "RETRACTED",
        "UNRESOLVED",
        "OUT_OF_SCOPE",
    ):
        assert required in statuses, f"example is missing status {required}"


def test_retracted_claim_has_supersession(claim_validator):
    for name, claim in load_claims():
        if claim["status"] == "RETRACTED":
            errors = list(claim_validator.iter_errors(claim))
            assert not errors
            assert "supersession" in claim, f"{name} lacks supersession block"


def test_derived_or_computed_claims_have_tests(claim_validator):
    """COMPUTED/DERIVED/MODEL_CONDITIONAL/REPRODUCED claims require tests."""
    conditional = ("COMPUTED", "DERIVED", "MODEL_CONDITIONAL", "REPRODUCED")
    for name, claim in load_claims():
        if claim["status"] in conditional:
            assert claim["evidence"].get("tests"), f"{name} lacks test evidence"


def test_every_claim_has_nonclaims_and_failure_conditions():
    for name, claim in load_claims():
        assert claim.get("nonclaims"), f"{name} lacks nonclaims"
        assert claim.get("failure_conditions"), f"{name} lacks failure_conditions"


def test_no_claim_asserts_truth():
    forbidden = ["is true", "proves the theory", "scientifically true", "truth of"]
    for name, claim in load_claims():
        text = json.dumps(claim).lower()
        for phrase in forbidden:
            assert phrase not in text, f"{name} contains forbidden phrase '{phrase}'"


def test_invalid_claim_rejected(claim_validator):
    bad = {
        "id": "claim.bad",
        "statement": "x",
        # missing status, scope, dependencies, evidence, nonclaims, failure_conditions
    }
    assert list(claim_validator.iter_errors(bad))


def test_sha256_pattern_enforced(claim_validator):
    claim = {
        "id": "claim.hashcheck",
        "statement": "s",
        "status": "COMPUTED",
        "scope": {"model": "m", "domain": "d"},
        "dependencies": {},
        "evidence": {
            "artifacts": [{"path": "r.json", "sha256": "nothex"}],
        },
        "nonclaims": ["n"],
        "failure_conditions": ["f"],
    }
    assert list(claim_validator.iter_errors(claim))


def test_run_schema(tmp_path, run_validator):
    run = {
        "id": "run.test-1",
        "command": "python run.py",
        "git": {"commit": "abc1234", "branch": "main", "worktree_dirty": False},
        "environment": {"python": "3.11", "platform": "darwin", "packages": {}},
        "seeds": {"python": 42},
        "inputs": [{"path": "in.json", "sha256": "a" * 64}],
        "outputs": [{"path": "out.json", "sha256": "b" * 64}],
        "started_at": "2026-01-01T00:00:00Z",
        "ended_at": "2026-01-01T00:01:00Z",
        "test_status": "PASS",
        "prereg_hash": "c" * 64,
        "claim_ids": ["claim.scaling.computed"],
    }
    assert not list(run_validator.iter_errors(run))


def test_invalid_evidence_rejected(evidence_validator):
    bad = {
        "id": "evidence.bad",
        # missing type, path, produced_at
    }
    assert list(evidence_validator.iter_errors(bad))


def test_invalid_run_rejected(run_validator):
    bad = {"id": "run.bad", "command": "python run.py"}
    assert list(run_validator.iter_errors(bad))


def test_invalid_prereg_rejected(prereg_validator):
    bad = {"id": "prereg.bad", "title": "t"}
    assert list(prereg_validator.iter_errors(bad))


def test_prereg_schema(prereg_validator):
    prereg = {
        "id": "prereg.scaling",
        "title": "Scaling preregistration",
        "registered_at": "2026-01-01T00:00:00Z",
        "sha256_at_registration": "d" * 64,
        "hypotheses": [{"statement": "s", "confirmatory": True}],
        "analysis_plan": {"commands": ["python run.py"], "parameters": {}},
        "exploratory": False,
    }
    assert not list(prereg_validator.iter_errors(prereg))
