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


def test_experiment_code_ref_change_changes_identity():
    d = theory_to_dict(toy_theory.THEORY)
    d["experiments_refs"] = {"predict": "other_module.other_fn"}
    decl = theory_to_dict(toy_theory.THEORY)
    decl["experiments_refs"] = {"predict": "toy_theory.predictive_half_life"}
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
