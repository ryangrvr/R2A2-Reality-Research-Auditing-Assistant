"""v0.4.2 — PROV relation semantics closure (review of 49b9db6).

Five acceptance conditions:
1. two review inputs -> two `used` records, never one list-valued prov:entity
2. a prediction depending on n assumptions/parameters -> n derivation records,
   each with a single prov:usedEntity
3. multiple authors -> separate wasAssociatedWith records
4. reviewer identity via wasAssociatedWith(activity, agent); wasAttributedTo
   only entity->agent (review attestations become Entities)
5. a full export with results AND attestations passes the checker with every
   PROV identifier resolving to the exact declared entity/activity/agent
"""
import copy
import sys, os

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "examples", "toy_theory"))

import toy_theory  # noqa: E402

from r2a2.compiler import compile_theory  # noqa: E402
from r2a2.runner import run_manifest  # noqa: E402
from r2a2.transport import theory_to_dict  # noqa: E402
from r2a2.prov_export import export_prov, check_prov_conformance  # noqa: E402
from r2a2.trust import ReviewAttestation  # noqa: E402


@pytest.fixture
def full_prov():
    t = toy_theory.THEORY
    m, led = compile_theory(t, seeds={"default": 0}); m.freeze()
    res = run_manifest(t, m, led)
    rec = next(r for r in res.records if r["experiment"] == "predict")
    att = ReviewAttestation("reviewer1", "result:predict", m.hash,
                            rec["result_hash"], "abc", "checked")
    att2 = ReviewAttestation("reviewer2", "result:predict", m.hash,
                             rec["result_hash"], "abc", "checked")
    return export_prov(
        theory_to_dict(t), m.to_dict(), res.records,
        attestations=[att.to_dict(), att2.to_dict()],
        authors=["author1", "author2"],
        reviewers=["reviewer1", "reviewer2"],
        code_revision="abc"), t, m, res


def test_1_two_review_inputs_produce_two_used_records(full_prov):
    prov, t, m, res = full_prov
    used = prov["used"]
    # SINGLE-VALUED endpoints — no lists anywhere
    for rid, rec in used.items():
        assert isinstance(rec["prov:entity"], str), f"{rid}: list endpoint"
        assert isinstance(rec["prov:activity"], str), f"{rid}: list endpoint"
    # two reviewers -> two separate review-used records per artifact type
    review_uses = [k for k in used if "review" in k]
    assert len(review_uses) == 4  # 2 reviewers x (manifest + result)
    assert "r2a2:used:review-reviewer1-manifest" in used
    assert "r2a2:used:review-reviewer2-manifest" in used


def test_2_n_dependencies_give_n_derivation_records(full_prov):
    prov, t, m, res = full_prov
    derivs = prov["wasDerivedFrom"]
    pred = t.predictions[0]
    n_expected = len(pred.assumptions) + len(pred.parameters)
    pred_derivs = [k for k in derivs if k.startswith(f"r2a2:deriv:pred-{pred.id}-")]
    assert len(pred_derivs) == n_expected
    # each record has a single usedEntity (string, not list)
    for k in pred_derivs:
        assert isinstance(derivs[k]["prov:usedEntity"], str), k
    # and the endpoints resolve to the right entity types
    for k in pred_derivs:
        ue = derivs[k]["prov:usedEntity"]
        assert ue.startswith(("r2a2:assumption:", "r2a2:parameter:")), k


def test_3_multiple_authors_get_separate_associations(full_prov):
    prov, t, m, res = full_prov
    assoc = prov["wasAssociatedWith"]
    run_assocs = [v for v in assoc.values() if v["prov:activity"] == "r2a2:activity:run"]
    assert len(run_assocs) == 2  # one per author, not one list-valued record
    for rec in assoc.values():
        assert isinstance(rec["prov:agent"], str), "list endpoint in association"


def test_4_attribution_and_association_types(full_prov):
    prov, t, m, res = full_prov
    # wasAttributedTo: entity -> agent ONLY (no activity endpoints)
    for rid, rec in prov["wasAttributedTo"].items():
        assert isinstance(rec["prov:entity"], str)
        assert not rec["prov:entity"].startswith("r2a2:activity:"), \
            f"{rid}: an activity must not be attributed; use wasAssociatedWith"
    # reviewers are attributed through their ATTESTATION ENTITIES
    att_entities = [k for k in prov["entity"] if k.startswith("r2a2:attestation:")]
    assert len(att_entities) == 2
    for rid, rec in prov["wasAttributedTo"].items():
        if "attestation" in rid:
            assert rec["prov:entity"].startswith("r2a2:attestation:")
    # review activities connect to reviewers via wasAssociatedWith
    for rid, rec in prov["wasAssociatedWith"].items():
        if "review" in rid:
            assert rec["prov:activity"].startswith("r2a2:activity:review:")
            assert rec["prov:agent"].startswith("r2a2:agent:")


def test_5_full_export_all_identifiers_resolve(full_prov):
    prov, t, m, res = full_prov
    errs = check_prov_conformance(prov)
    assert errs == [], errs
    # specifically: review `used` references resolve to the RESULT ENTITY
    # keyed by experiment (the ID-mismatch bug from the review)
    used = prov["used"]
    result_entities = {k for k in prov["entity"] if k.startswith("r2a2:result:")}
    review_result_uses = [rec for k, rec in used.items()
                          if "review" in k and k.endswith("-result")]
    assert review_result_uses
    for rec in review_result_uses:
        assert rec["prov:entity"] in result_entities, \
            f"review used {rec['prov:entity']} must be a DECLARED result entity"
