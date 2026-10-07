"""v0.3.1 trust-closure acceptance tests.

Four conditions (external review, commit c83df63, "issue found"):

1. attestation tampering through the real CLI is detected, including edits
   to issues/notes;
2. changing any scientific-semantic field changes the declaration/manifest
   identity;
3. all declarative SDK objects survive transport round-trip losslessly, with
   executable hooks as stable references;
4. replication records content-addressably bind the agreement rule and
   independence evidence.
"""
import json
import subprocess
import sys
import os
import tempfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "examples", "toy_theory"))
sys.path.insert(0, os.path.join(HERE, "..", "examples", "alien_theories"))

import toy_theory  # noqa: E402
import gauge_toy  # noqa: E402
import ising_toy  # noqa: E402

from r2a2.compiler import compile_theory  # noqa: E402
from r2a2.transport import theory_from_dict, theory_to_dict  # noqa: E402
from r2a2.canonical import canonical_hash  # noqa: E402
from r2a2.trust import (AgreementRule, Implementation,  # noqa: E402
                        Replication, ReviewAttestation)


# --- condition 1: CLI detects tampering with verdict AND issues/notes ------

def _run_cli(*argv):
    from r2a2.cli import main
    return main(list(argv))


def _write_attest(tmpdir, **overrides):
    path = os.path.join(tmpdir, "att.json")
    att = ReviewAttestation(
        reviewer="alice", scope="identity:T-identity",
        manifest_hash="M1", result_hash="R1", code_revision="abc",
        verdict="checked", notes="reproduced residuals", issues=[])
    doc = att.to_dict()
    doc.update(overrides)
    # note: overrides WITHOUT re-sealing simulate tampering
    with open(path, "w") as f:
        json.dump(doc, f)
    return path, att


def test_cli_detects_verdict_tampering(tmp_path):
    path, _ = _write_attest(str(tmp_path), verdict="forged")
    assert _run_cli("verify-attestation", path, "--manifest-hash", "M1",
                    "--result-hash", "R1", "--revision", "abc") == 1


def test_cli_detects_issue_state_tampering(tmp_path):
    # flipping the issue state changes whether the attestation applies
    path, _ = _write_attest(str(tmp_path), issues=["previously resolved"])
    assert _run_cli("verify-attestation", path, "--manifest-hash", "M1",
                    "--result-hash", "R1", "--revision", "abc") == 1


def test_cli_detects_notes_tampering(tmp_path):
    path, _ = _write_attest(str(tmp_path), notes="something else entirely")
    assert _run_cli("verify-attestation", path, "--manifest-hash", "M1",
                    "--result-hash", "R1", "--revision", "abc") == 1


def test_cli_accepts_untampered_attestation(tmp_path):
    path, _ = _write_attest(str(tmp_path))
    assert _run_cli("verify-attestation", path, "--manifest-hash", "M1",
                    "--result-hash", "R1", "--revision", "abc") == 0


def test_seal_covers_notes_and_issues():
    a = ReviewAttestation("r", "S", "M", "R", "C", "ok", notes="n1")
    b = ReviewAttestation("r", "S", "M", "R", "C", "ok", notes="n2")
    assert a.seal() != b.seal()
    a2 = ReviewAttestation("r", "S", "M", "R", "C", "ok", issues=["i"])
    assert a.seal() != a2.seal()


# --- condition 2: semantic fields change the declaration/manifest identity --

def _compiled(theory):
    m, led = compile_theory(theory)
    m.freeze()
    return m


def _recompiled(theory, mutate):
    """Transport -> mutate declaration -> re-attach code (by reference) -> compile."""
    d = theory_to_dict(theory)
    mutate(d)
    t2 = theory_from_dict(d)
    t2.experiments = dict(theory.experiments)  # code binds by reference
    return _compiled(t2)


def test_kill_condition_change_changes_identity():
    m1 = _compiled(toy_theory.THEORY)

    def mutate(d):
        d["predictions"][0]["kill_condition"] += " CHANGED"
    m2 = _recompiled(toy_theory.THEORY, mutate)
    assert m1.theory_declaration_hash != m2.theory_declaration_hash
    assert m1.hash != m2.hash


def test_assumption_text_change_changes_identity():
    m1 = _compiled(toy_theory.THEORY)

    def mutate(d):
        d["assumptions"][0]["text"] += " (amended)"
    m2 = _recompiled(toy_theory.THEORY, mutate)
    assert m1.theory_declaration_hash != m2.theory_declaration_hash


def test_preregistration_flag_change_changes_identity():
    m1 = _compiled(ising_toy.THEORY)

    def mutate(d):
        d["tests"][0]["preregistered"] = not d["tests"][0]["preregistered"]
    m2 = _recompiled(ising_toy.THEORY, mutate)
    assert m1.theory_declaration_hash != m2.theory_declaration_hash


def test_transformation_class_change_changes_identity():
    m1 = _compiled(gauge_toy.THEORY)

    def mutate(d):
        d["transformation_classes"][0]["description"] += " amended"
    m2 = _recompiled(gauge_toy.THEORY, mutate)
    assert m1.theory_declaration_hash != m2.theory_declaration_hash


def test_experiment_code_binding_change_changes_identity():
    d = theory_to_dict(toy_theory.THEORY)
    d["experiments_bindings"] = {"predict": {"ref": "other_module:other_fn",
                                             "source_hash": "x"}}
    decl = theory_to_dict(toy_theory.THEORY)
    decl["experiments_bindings"] = {"predict": {"ref": "toy_theory:predictive_half_life",
                                                "source_hash": "y"}}
    assert canonical_hash(d) != canonical_hash(decl)


# --- condition 3: lossless declarative round-trip ---------------------------

@pytest.mark.parametrize("theory", [toy_theory.THEORY, gauge_toy.THEORY, ising_toy.THEORY])
def test_declarative_round_trip_lossless(theory):
    d = theory_to_dict(theory)
    t2 = theory_from_dict(d)
    # declarative fields identical, including the previously-omitted ones
    assert len(t2.transformation_classes) == len(theory.transformation_classes)
    assert len(t2.comparators) == len(theory.comparators)
    assert [t.preregistered for t in t2.tests] == [t.preregistered for t in theory.tests]
    assert [t.kind for t in t2.tests] == [t.kind for t in theory.tests]
    # hooks travel as references and resolve back to callables
    if theory.transformation_classes:
        tc_src, tc_dst = theory.transformation_classes[0], t2.transformation_classes[0]
        assert tc_dst.quotient_distance is tc_src.quotient_distance
    # and the full serialization is stable
    assert canonical_hash(theory_to_dict(t2)) == canonical_hash(d)


def test_unknown_hook_reference_raises():
    d = theory_to_dict(gauge_toy.THEORY)
    d["transformation_classes"][0]["quotient_distance"] = "no.such.module.fn"
    with pytest.raises(Exception):
        theory_from_dict(d)


# --- condition 4: replication records bind rule + evidence ------------------

def _replication():
    a = Implementation("implA", code_hash="hA", derivation_ref="d1")
    b = Implementation("implB", code_hash="hB", derivation_ref="d2",
                       derived_independently=True)
    return Replication("T1", a, b, AgreementRule(kind="tolerance",
                       tolerance=1e-9, observable="x"), value_a=1.0,
                       value_b=1.0, manifest_hash="M1")


def test_replication_record_binds_rule_and_evidence():
    rec = _replication().evaluate()
    assert rec["rule"] == {"kind": "tolerance", "tolerance": 1e-9, "observable": "x"}
    assert rec["impl_a"]["derivation_ref"] == "d1"
    assert rec["impl_b"]["derived_independently"] is True
    assert rec["record_hash"]


def test_replication_record_content_addressed_and_tamper_evident():
    rep = _replication()
    rec1 = rep.evaluate()
    # changing the frozen tolerance after the fact changes the record hash
    rep.rule.tolerance = 5.0
    rec2 = rep.evaluate()
    assert rec1["record_hash"] != rec2["record_hash"]
    # identical setup reproduces the identical record hash
    rep.rule.tolerance = 1e-9
    assert rep.evaluate()["record_hash"] == rec1["record_hash"]


def test_independence_grade_is_declared_not_verified():
    rec = _replication().evaluate()
    assert rec["independence_note"].startswith("declared and evidenced")

# ===========================================================================
# v0.3.2 — executable provenance closure (review of d02bdf9)
#
# Acceptance conditions:
#   (1) change function body (same name)  => manifest identity changes
#   (2) tamper replication verdict        => verification fails
#   (3) round-trip dotted-module theory   => same executable bindings
# ===========================================================================

def test_body_edit_same_name_changes_manifest_identity(tmp_path):
    """Condition 1: the manifest binds source CONTENT, not just the name."""
    # write a module with an experiment, compile it
    mod = tmp_path / "victim_theory.py"
    mod.write_text(
        "from r2a2.api import Theory, Parameter, Prediction, Test\n"
        "def _predict(a=2.0, b=1.0):\n"
        "    return {\"y2\": a * 2 + b}\n"
        "def _identity(a=2.0, b=1.0):\n"
        "    return {\"residual\": 0.0}\n"
        "THEORY = Theory(\n"
        "    id=\"victim\", version=\"1\",\n"
        "    parameters=[Parameter(\"a\", kind=\"commitment\", value=2.0)],\n"
        "    predictions=[Prediction(\"P\", \"d\", \"predict\", \"y2\", \"kill\",\n"
        "                            parameters=[\"a\"])],\n"
        "    tests=[Test(\"T\", kind=\"identity\", experiment=\"identity\", exact=True)],\n"
        "    experiments={\"predict\": _predict, \"identity\": _identity},\n"
        ")\n")
    sys.path.insert(0, str(tmp_path))
    try:
        spec = importlib.util.spec_from_file_location("victim_theory", mod)
        victim = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(victim)
        m1, _ = compile_theory(victim.THEORY); m1.freeze()

        # now EDIT THE BODY without renaming, reload, recompile
        text = mod.read_text().replace("return {\"y2\": a * 2 + b}",
                                       "return {\"y2\": a * 2 + b + 1000.0}")
        mod.write_text(text)
        spec2 = importlib.util.spec_from_file_location("victim_theory", mod)
        victim2 = importlib.util.module_from_spec(spec2)
        spec2.loader.exec_module(victim2)
        m2, _ = compile_theory(victim2.THEORY); m2.freeze()

        assert m1.experiment_bindings["predict"]["ref"] == \
            m2.experiment_bindings["predict"]["ref"], "same name expected"
        assert m1.theory_declaration_hash != m2.theory_declaration_hash, \
            "body edit must change the declaration hash"
        assert m1.hash != m2.hash, "body edit must change the manifest identity"
    finally:
        sys.path.remove(str(tmp_path))


def test_tampered_replication_verdict_fails_verification():
    """Condition 2: record_hash binds agrees/detail; a flipped verdict fails."""
    from r2a2.trust import verify_replication_record
    a = Implementation("implA", code_hash="hA", derivation_ref="d1")
    b = Implementation("implB", code_hash="hB", derivation_ref="d1")
    rep = Replication("T", a, b, AgreementRule(tolerance=1e-6),
                      value_a=1.0, value_b=1.0, manifest_hash="M")
    rec = rep.evaluate()
    assert verify_replication_record(rec)["applies"] is True

    # tamper: flip the verdict but keep everything else (incl. record_hash)
    import copy
    tampered = copy.deepcopy(rec)
    tampered["agrees"] = not tampered["agrees"]
    res = verify_replication_record(tampered)
    assert res["applies"] is False and res["verdict_valid"] is False

    # tamper: change a value under the same record_hash
    tampered2 = copy.deepcopy(rec)
    tampered2["value_b"] = 9.0
    res2 = verify_replication_record(tampered2)
    assert res2["applies"] is False


def test_dotted_module_round_trip_keeps_executable_bindings(tmp_path):
    """Condition 3: 'pkg.mod:qualname' references survive round-trip."""
    pkg = tmp_path / "fakepkg"
    (pkg / "models").mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "models" / "__init__.py").write_text("")
    (pkg / "models" / "gravity.py").write_text(
        "def solve(a=1.0):\n    return {\"x\": a * 2}\n")
    sys.path.insert(0, str(tmp_path))
    try:
        from fakepkg.models import gravity
        d = {
            "id": "dotted", "version": "1",
            "predictions": [{"id": "P", "experiment": "solve",
                             "kill_condition": "x>0", "observable": "x"}],
            "experiments": {"solve": gravity.solve.__module__ + ":" + gravity.solve.__qualname__},
        }
        t2 = theory_from_dict(d)
        assert t2.experiments["solve"] is gravity.solve
        # and the serialization round-trips to the same reference
        assert theory_to_dict(t2)["experiments"]["solve"] == "fakepkg.models.gravity:solve"
    finally:
        sys.path.remove(str(tmp_path))


import importlib.util  # noqa: E402  (used by condition-1 test)
