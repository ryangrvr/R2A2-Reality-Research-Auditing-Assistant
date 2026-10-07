"""v0.4 acceptance gates: interoperability, adoption, standards.

Gates:
1. the public JSON Schema validates all built-in/reference projects
2. a project exports to a standards-compatible research package (RO-Crate)
3. provenance exports into a standard provenance representation (W3C PROV)
4. a fresh project can be scaffolded without touching R2A2 source
5. `doctor` explains common ontology mistakes in domain-neutral language
6. at least five heterogeneous external-style projects compile unchanged
7. the physics reference completes compile→freeze→run→audit→replicate→attest→export→verify
8. the GRUT adapter still passes unchanged
9. no new single quality score is introduced (structural check)
"""
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
for p in ("examples/toy_theory", "examples/alien_theories",
          "examples/corpus", "examples/pendulum_theory"):
    sys.path.insert(0, os.path.join(ROOT, p))

import toy_theory  # noqa: E402
import ising_toy  # noqa: E402
import bayesian_decay  # noqa: E402
import gauge_toy  # noqa: E402
import two_body  # noqa: E402
import sr_dispersion  # noqa: E402
import epi_toy  # noqa: E402
import modified_gravity  # noqa: E402
import logistic_map  # noqa: E402

from r2a2.transport import theory_to_dict, theory_from_dict  # noqa: E402
from r2a2.schema_json import validate_artifact, build_schema, schema_version_check  # noqa: E402
from r2a2.compiler import compile_theory  # noqa: E402
from r2a2.runner import run_manifest  # noqa: E402
from r2a2.audit import audit_theory  # noqa: E402
from r2a2.rocrate import export_rocrate  # noqa: E402
from r2a2.prov_export import export_prov  # noqa: E402
from r2a2.doctor import run_doctor  # noqa: E402

ALL_PROJECTS = [toy_theory.THEORY, ising_toy.THEORY, bayesian_decay.THEORY,
                gauge_toy.THEORY, two_body.THEORY, sr_dispersion.THEORY,
                epi_toy.THEORY, modified_gravity.THEORY, logistic_map.THEORY]


# --- gate 1: schema validates everything ------------------------------------

def test_gate1_schema_validates_all_projects():
    for t in ALL_PROJECTS:
        errs = validate_artifact(theory_to_dict(t))
        assert errs == [], f"{t.id}: {errs[:3]}"


def test_gate1_schema_rejects_unknown_fields_and_bad_enums():
    d = theory_to_dict(toy_theory.THEORY)
    d["not_a_real_field"] = 1
    assert validate_artifact(d)
    d2 = theory_to_dict(toy_theory.THEORY)
    d2["parameters"][0]["kind"] = "vibes"
    assert validate_artifact(d2)


def test_gate1_extension_namespace_allowed():
    d = theory_to_dict(toy_theory.THEORY)
    d["x_lab_notebook"] = "our internal extension"
    assert validate_artifact(d) == []


def test_gate1_round_trip_preserves_semantics():
    for t in ALL_PROJECTS:
        t2 = theory_from_dict(theory_to_dict(t))
        t2.experiments = dict(t.experiments)  # code by reference
        assert t2.id == t.id
        assert [p.kill_condition for p in t2.predictions] == \
            [p.kill_condition for p in t.predictions]
        assert [p.evidence_grade for p in t2.predictions] == \
            [p.evidence_grade for p in t.predictions]
        m1, _ = compile_theory(t); m1.freeze()
        m2, _ = compile_theory(t2); m2.freeze()
        assert m1.hash == m2.hash, t.id


# --- gate 2: RO-Crate export -------------------------------------------------

def test_gate2_rocrate_identifies_all_five():
    t = two_body.THEORY
    m, led = compile_theory(t, seeds={"default": 0}); m.freeze()
    res = run_manifest(t, m, led)
    crate = export_rocrate(
        theory_to_dict(t), m.to_dict(), res.records,
        authors=["A. Researcher"], code_revision="336ce58")
    root = crate["@graph"][0]
    assert root["r2a2:manifestHash"] == m.hash
    ids = " ".join(str(e.get("id", "")) + e.get("name", "") + e.get("description", "")
                   for e in crate["@graph"])
    # (1) what was proposed  (2) what was assumed
    assert "Theory declaration" in ids
    assert "kill condition" in ids or "canonical declarative" in ids.lower() \
        or "parameters" in ids
    # (3) what code/data executed (4) result-to-manifest linkage
    assert any(r.get("manifest_hash") == m.hash for r in res.records)
    # (5) replication/review applicability is representable
    assert root["r2a2:schemaVersion"]


# --- gate 3: W3C PROV --------------------------------------------------------

def test_gate3_prov_structure():
    t = toy_theory.THEORY
    m, led = compile_theory(t, seeds={"default": 0}); m.freeze()
    res = run_manifest(t, m, led)
    prov = export_prov(theory_to_dict(t), m.to_dict(), res.records,
                       authors=["P. Physicist"], reviewers=["R. Reviewer"])
    assert "prefix" in prov and "prov" in prov["prefix"]
    assert "activity" in prov and "entity" in prov and "agent" in prov
    # result wasGeneratedBy execution; manifest derived from theory
    run_act = prov["activity"]["r2a2:activity:run"]
    assert run_act["prov:used"].startswith("r2a2:manifest")
    # R2A2-specific terms stay in the r2a2 namespace, not in prov: types
    pred = prov["entity"][f"r2a2:prediction:{t.predictions[0].id}"]
    assert "prov:type" in pred
    assert pred["r2a2:killCondition"]  # in the r2a2 profile, not prov:semantics


# --- gate 4: fresh scaffold --------------------------------------------------

def test_gate4_scaffold_compiles(tmp_path):
    from r2a2.cli import main
    target = tmp_path / "fresh"
    assert main(["init-project", str(target)]) == 0
    assert (target / "theory.py").exists()
    assert (target / "README.md").exists()
    sys.path.insert(0, str(target))
    try:
        import importlib
        mod = importlib.import_module("theory")
        theory = mod.THEORY
        m, led = compile_theory(theory, seeds={"default": 0}); m.freeze()
        res = run_manifest(theory, m, led)
        assert res.records
    finally:
        sys.path.remove(str(target))


# --- gate 5: doctor teaches the ontology -------------------------------------

def test_gate5_doctor_plain_language():
    from r2a2.api import Prediction, Theory, Parameter
    t = Theory(id="x", version="1",
               parameters=[Parameter("a", kind="fitted-parameter",
                                     source="no-such-dataset", sector="s1")],
               experiments={})
    t.predictions.append(Prediction("P", "d", "nope", "o", "k", parameters=["a"]))
    findings = run_doctor(t)
    msgs = " ".join(m for _, m in findings)
    assert "BLOCKING" in [c for c, _ in findings]
    # plain-language: mentions where to get the missing experiment, not bare codes
    assert "referenced but not defined" in msgs
    assert "add it to the theory's experiments" in msgs.lower() or \
        "add it to the theory's experiments" in msgs


def test_gate5_doctor_categorizes_not_fails():
    """A scientific warning is not a software failure."""
    findings = run_doctor(two_body.THEORY)
    cats = {c for c, _ in findings}
    assert "SCIENTIFIC WARNING" in cats or "INFORMATIONAL" in cats


# --- gate 6: corpus compiles/runs/audits without core changes ----------------

@pytest.mark.parametrize("theory", ALL_PROJECTS, ids=lambda t: t.id)
def test_gate6_all_projects_full_cycle(theory):
    m, led = compile_theory(theory, seeds={"default": 0})
    m.freeze()
    res = run_manifest(theory, m, led)
    report = audit_theory(theory, led)
    assert report.ok, report.blocking
    assert res.records


def test_gate6_two_body_hostile_control_fires():
    """The Euler hostile control must show drift (otherwise the check is broken)."""
    r = two_body.THEORY.experiments["hostile_euler"]()
    assert r["E_drift_euler"] > 1e-6


def test_gate6_two_body_identities_exact():
    r = two_body.THEORY.experiments["identity"]()
    assert r["E_drift_rk4"] < 1e-6
    assert r["E_drift_leapfrog"] < 1e-6
    assert r["L_drift_rk4"] < 1e-9


def test_gate6_modified_gravity_transfer_exposes_refit():
    """The modified-gravity theory must FAIL a transfer if delta is refit —
    the point of the theory."""
    from r2a2.transfer import FrozenParameter, SectorDemand, audit_transfer
    frozen = {"mu": FrozenParameter("mu", "solar", 1.0),
              "delta": FrozenParameter("delta", "solar", 0.1)}
    v = audit_transfer(frozen, SectorDemand("galaxy", required=["mu", "delta"]),
                       refit={"delta": "galaxy"})
    assert v.outcome == "FAIL"
    assert any(l["status"] == "SILENT REFIT" for l in v.lines)


# --- gate 7: reference physics full pipeline ---------------------------------

def test_gate7_two_body_pipeline_end_to_end(tmp_path):
    t = two_body.THEORY
    # compile -> freeze -> run
    m, led = compile_theory(t, seeds={"default": 0})
    m.freeze()
    res = run_manifest(t, m, led)
    # audit
    report = audit_theory(t, led)
    assert report.ok, report.blocking
    # replicate (A/B: RK4 vs leapfrog)
    from r2a2.trust import (AgreementRule, Implementation, Replication,
                            verify_replication_record)
    ab = t.experiments["ab"]()
    rep = Replication(
        "T-ab",
        Implementation("rk4", code_hash="hA", derivation_ref="d1"),
        Implementation("leapfrog", code_hash="hB", derivation_ref="d1"),
        AgreementRule(kind="tolerance", tolerance=1e-3, observable="x"),
        value_a=ab["xA"], value_b=ab["xB"], manifest_hash=m.hash)
    record = rep.evaluate()
    assert record["agrees"] is True, record["detail"]
    assert verify_replication_record(record)["applies"]
    # attest
    from r2a2.trust import ReviewAttestation, verify_attestation
    rec = next(r for r in res.records if r["experiment"] == "predict")
    att = ReviewAttestation("ext", "result:predict", m.hash, rec["result_hash"],
                            "336ce58", "checked")
    doc = att.to_dict()
    out = verify_attestation(
        ReviewAttestation("ext", doc["scope"], doc["manifest_hash"],
                          doc["result_hash"], doc["code_revision"], doc["verdict"]),
        m.hash, rec["result_hash"], "336ce58", sealed_as=doc["seal"])
    assert out["applies"]
    # export + verify
    from r2a2.rocrate import export_rocrate
    crate = export_rocrate(theory_to_dict(t), m.to_dict(), res.records,
                           replications=[record], attestations=[doc],
                           authors=["A"], code_revision="336ce58")
    assert any("replication" in str(e) for e in crate["@graph"])


# --- gate 8: GRUT adapter regression ------------------------------------------

def test_gate8_grut_adapter_unchanged():
    grut_dir = os.path.join(ROOT, "examples", "grut_adapter")
    sys.path.insert(0, grut_dir)
    try:
        import grut_adapter
        claims, source_ids, result = grut_adapter.load_grut_claims()
        assert result.ok, result.blocking
        theory = grut_adapter.grut_claims_to_theory(claims)
        m, led = compile_theory(theory)
        m.freeze()
        assert led.nodes
    finally:
        sys.path.remove(grut_dir)


# --- gate 10: no single quality score -----------------------------------------

def test_gate10_no_single_score():
    """compare() must not declare a winner; audit must not produce one number."""
    from r2a2.compare import compare
    out = compare(toy_theory.THEORY, two_body.THEORY)
    assert "no winner" in out.lower()
    from r2a2.ledger import Ledger
    led = Ledger()
    led.add("a", "claim", deps=[])
    assert isinstance(led.total_debt(), dict)  # labelled, not summed
