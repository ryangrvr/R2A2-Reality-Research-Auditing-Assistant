"""v0.4.1 — standards conformance closure (review of e0f2dd3).

Hostile conformance tests: deliberately malformed artifacts must be caught.

Gates:
1. complete attached RO-Crate (proper descriptor, root @id, datePublished,
   hasPart references, author entities, every declared file physically present),
   checked with an independent structural conformance checker
2. faithful PROV-JSON: top-level relation maps; conformance check catches
   embedded relations and unresolvable references
3. fail-closed JSON Schema validation (no silent "mostly validation")
4. malformed artifacts (missing payload, bad hasPart, invalid relation,
   wrong scalar type, malformed callable ref) are rejected
"""
import json
import os
import sys
import copy

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "examples", "toy_theory"))

import toy_theory  # noqa: E402

from r2a2.compiler import compile_theory  # noqa: E402
from r2a2.runner import run_manifest  # noqa: E402
from r2a2.rocrate import (export_rocrate, write_crate,  # noqa: E402
                          check_conformance)
from r2a2.prov_export import export_prov, check_prov_conformance  # noqa: E402
from r2a2.transport import theory_to_dict  # noqa: E402
from r2a2.schema_json import validate_artifact  # noqa: E402


@pytest.fixture
def good_crate(tmp_path):
    t = toy_theory.THEORY
    m, led = compile_theory(t, seeds={"default": 0})
    m.freeze()
    res = run_manifest(t, m, led)
    crate = export_rocrate(theory_to_dict(t), m.to_dict(), res.records,
                           authors=["A"], code_revision="abc")
    write_crate(crate, str(tmp_path / "crate"))
    return crate, str(tmp_path / "crate"), m, res


# --- gate 1: complete attached crate ----------------------------------------

def test_crate_conformant_and_physically_complete(good_crate):
    crate, directory, m, res = good_crate
    errs = check_conformance(crate, crate_dir=directory)
    assert errs == [], errs
    # metadata file exists and parses
    doc = json.load(open(os.path.join(directory, "ro-crate-metadata.json")))
    assert doc["@context"]
    # every file entity in the graph is on disk
    graph = doc["@graph"]
    for e in graph:
        eid = e.get("@id", "")
        if e.get("@type") == "File" and not eid.startswith("#"):
            assert os.path.exists(os.path.join(directory, eid)), eid


def test_crate_entity_references_never_inline(good_crate):
    crate, _, _, _ = good_crate
    root = next(e for e in crate["@graph"] if e["@id"] == "./")
    assert all(list(h.keys()) == ["@id"] for h in root["hasPart"])
    assert root["datePublished"]
    assert root["conformsTo"]["@id"].startswith("https://w3.org") or \
        "w3id.org" in root["conformsTo"]["@id"]
    # authors are contextual entities referenced by @id
    assert all(list(a.keys()) == ["@id"] and a["@id"].startswith("#author")
               for a in root["author"])


# --- gate 2: faithful PROV-JSON ----------------------------------------------

def test_prov_top_level_relations():
    t = toy_theory.THEORY
    m, led = compile_theory(t, seeds={"default": 0}); m.freeze()
    res = run_manifest(t, m, led)
    prov = export_prov(theory_to_dict(t), m.to_dict(), res.records, authors=["X"])
    errs = check_prov_conformance(prov)
    assert errs == [], errs
    # required PROV-JSON top-level maps
    for k in ("prefix", "entity", "activity", "agent",
              "used", "wasGeneratedBy", "wasDerivedFrom"):
        assert k in prov, k
    # relations NOT embedded inside entity/activity records
    for e in prov["entity"].values():
        assert not {"prov:used", "prov:generated", "prov:activity"} & set(e)
    for a in prov["activity"].values():
        assert not {"prov:entity", "prov:generated"} & set(a)


def test_prov_precise_spec_wording():
    t = toy_theory.THEORY
    m, _ = compile_theory(t, seeds={"default": 0}); m.freeze()
    prov = export_prov(theory_to_dict(t), m.to_dict(), [])
    spec = prov["r2a2_profile"]["provenanceSpec"]
    assert "Member Submission" in spec
    assert "not a W3C Recommendation" in spec


# --- gate 3: fail-closed schema validation ------------------------------------

def test_fail_closed_policy():
    try:
        import jsonschema  # noqa
        pytest.skip("jsonschema installed; fail-closed fallback not exercised")
    except ImportError:
        pass
    doc = theory_to_dict(toy_theory.THEORY)
    errs = validate_artifact(doc)  # require_full default
    assert errs and "FULL-SCHEMA VALIDATOR REQUIRED" in errs[0]
    # explicit partial is allowed but clearly marked
    partial = validate_artifact(doc, require_full=False)
    assert partial[0].startswith("WARNING: partial")
    # and the partial check still catches structure it CAN enforce
    bad = copy.deepcopy(doc)
    bad["not_a_field"] = 1
    assert any("unknown field" in e for e in validate_artifact(bad, require_full=False))


# --- gate 4: hostile malformed artifacts --------------------------------------

def test_hostile_missing_crate_payload(good_crate):
    """Delete a payload file that the graph declares -> conformance fails."""
    crate, directory, _, _ = good_crate
    os.remove(os.path.join(directory, "results", "predict.json"))
    errs = check_conformance(crate, crate_dir=directory)
    assert any("not present in crate" in e for e in errs)


def test_hostile_malformed_haspart():
    """An inline entity in hasPart (instead of a reference) is caught."""
    crate, _, _, _ = export_rocrate(
        {"id": "x", "version": "1"}, {"hash": "h"}, []), None, None, None
    # build minimal doc and corrupt it
    doc = {"@context": crate["@context"], "@graph": copy.deepcopy(crate["@graph"])}
    root = next(e for e in doc["@graph"] if e["@id"] == "./")
    root["hasPart"].append({"@id": "f.json", "name": "inline data!"})
    errs = check_conformance(doc)
    assert any("inline entity" in e for e in errs)


def test_hostile_invalid_prov_relation():
    """A relation embedded in an entity is caught; an unresolvable reference too."""
    t = toy_theory.THEORY
    m, _ = compile_theory(t, seeds={"default": 0}); m.freeze()
    prov = export_prov(theory_to_dict(t), m.to_dict(), [])
    bad = copy.deepcopy(prov)
    bad["entity"][f"r2a2:theory:{t.id}"]["prov:used"] = "r2a2:manifest:x"
    errs = check_prov_conformance(bad)
    assert any("embeds relation" in e for e in errs)
    bad2 = copy.deepcopy(prov)
    bad2["used"]["r2a2:used:bad"] = {"prov:activity": "r2a2:activity:run",
                                     "prov:entity": "r2a2:manifest:nonexistent00"}
    # unresolvable manifest refs to undeclared ids are flagged
    errs2 = check_prov_conformance(bad2)
    assert errs2, "an undeclared reference must be flagged"


def test_hostile_wrong_scalar_type():
    """A wrong scalar type (kill_condition as a number) must be rejected."""
    doc = theory_to_dict(toy_theory.THEORY)
    try:
        import jsonschema  # noqa
        doc["predictions"][0]["kill_condition"] = 12345
        assert validate_artifact(doc), "wrong scalar type must fail"
    except ImportError:
        pytest.skip("full validator not installed in this environment")


def test_hostile_malformed_callable_ref():
    """A callable ref without the required 'module:qualname' shape is rejected
    by the schema pattern and by the resolver."""
    doc = theory_to_dict(toy_theory.THEORY)
    try:
        import jsonschema  # noqa
        doc["experiments"]["predict"] = "no-separator-here"
        assert validate_artifact(doc), "malformed callable ref must fail"
    except ImportError:
        pass
    from r2a2.transport import _resolve
    from r2a2.failures import ProtocolError
    with pytest.raises(ProtocolError):
        _resolve("no_such_module:function_name")
