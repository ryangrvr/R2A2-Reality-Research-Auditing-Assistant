"""Trust layer tests: independent implementation protocol + attestations."""
import pytest

from r2a2.trust import (AgreementRule, Implementation, INDEPENDENCE_LEVELS,
                        Replication, ReviewAttestation, verify_attestation)
from r2a2.schema import SCHEMA_VERSION, SchemaError, check_compatible, migrate, stamp


def _impls(level3=False):
    a = Implementation("implA", code_hash="aaa", derivation_ref="d1",
                       derived_independently=level3)
    b = Implementation("implB", code_hash="bbb",
                       derivation_ref="d2" if level3 else "d1",
                       derived_independently=level3)
    return a, b


def test_tolerance_rule():
    rule = AgreementRule(kind="tolerance", tolerance=1e-6)
    assert rule.check(1.0, 1.0 + 1e-9)[0] is True
    assert rule.check(1.0, 1.1)[0] is False


def test_structural_rule():
    rule = AgreementRule(kind="structural")
    assert rule.check({"x": [1, 2]}, {"x": (1, 2)})[0] is True
    assert rule.check({"x": 1}, {"x": 2})[0] is False


def test_independence_levels():
    a, b = _impls(level3=False)
    rep = Replication("T1", a, b, AgreementRule(tolerance=1e-6),
                      value_a=1.0, value_b=1.0)
    assert rep.independence_level == INDEPENDENCE_LEVELS[0]  # same derivation
    a3, b3 = _impls(level3=True)
    rep3 = Replication("T1", a3, b3, AgreementRule(tolerance=1e-6),
                       value_a=1.0, value_b=1.0)
    assert rep3.independence_level == INDEPENDENCE_LEVELS[2]


def test_replication_record_is_stamped():
    a, b = _impls()
    rec = Replication("T1", a, b, AgreementRule(tolerance=1e-6),
                      value_a=1.0, value_b=1.0).evaluate()
    assert rec["r2a2_schema"] == SCHEMA_VERSION
    assert rec["agrees"] is True


def test_attestation_binds_to_exact_artifacts():
    att = ReviewAttestation(reviewer="alice", scope="theorem:T3",
                            manifest_hash="M1", result_hash="R1",
                            code_revision="abc123", verdict="checked")
    assert att.covers("M1", "R1", "abc123")
    assert not att.covers("M2", "R1", "abc123")   # manifest changed -> void
    assert not att.covers("M1", "R2", "abc123")
    assert not att.covers("M1", "R1", "def456")


def test_attestation_seal_detects_tampering():
    att = ReviewAttestation(reviewer="alice", scope="S", manifest_hash="M",
                            result_hash="R", code_revision="C", verdict="ok")
    doc = att.to_dict()
    assert verify_attestation(att, "M", "R", "C")["applies"] is True
    # a reader must compare the stored seal against the current content:
    stored_seal = doc["seal"]
    att.verdict = "forged"
    res = verify_attestation(att, "M", "R", "C", sealed_as=stored_seal)
    assert res["applies"] is False and res["seal_intact"] is False


def test_open_issues_block_attestation():
    att = ReviewAttestation(reviewer="bob", scope="S", manifest_hash="M",
                            result_hash="R", code_revision="C", verdict="issue",
                            issues=["the derivation assumes isotropy"])
    res = verify_attestation(att, "M", "R", "C")
    assert res["applies"] is False and res["open_issues"] == 1


def test_schema_stamp_and_check():
    doc = stamp({"anything": 1})
    assert check_compatible(doc) == SCHEMA_VERSION
    with pytest.raises(SchemaError):
        check_compatible({"no": "schema"})
    with pytest.raises(SchemaError):
        check_compatible({"r2a2_schema": "9.9"})


def test_migrate_identity_and_unknown():
    doc = stamp({"x": 1})
    assert migrate(doc) == doc
    with pytest.raises(SchemaError):
        migrate({"r2a2_schema": "0.1", "x": 2})
