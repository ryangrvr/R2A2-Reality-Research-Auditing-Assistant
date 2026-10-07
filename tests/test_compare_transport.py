"""Epistemic compare + YAML/JSON transport tests."""
import sys, os
import json

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "examples", "toy_theory"))
sys.path.insert(0, os.path.join(HERE, "..", "examples", "alien_theories"))

import toy_theory  # noqa: E402
import ising_toy  # noqa: E402

from r2a2.compare import compare, epistemic_profile  # noqa: E402
from r2a2.transport import theory_from_dict, theory_to_dict  # noqa: E402
from r2a2.canonical import canonical_hash  # noqa: E402
from r2a2.compiler import compile_theory  # noqa: E402,F401


def test_profile_dimensions():
    p = epistemic_profile(ising_toy.THEORY)
    assert p["hostile_controls"] >= 1
    assert p["identity_checks"] >= 1
    assert p["predictions"] >= 1
    assert "fitted_parameters" in p and "commitments" in p


def test_compare_exposes_no_winner():
    out = compare(toy_theory.THEORY, ising_toy.THEORY)
    assert "no winner score" in out
    # dimensions appear side by side
    assert "hostile_controls" in out and "commitments" in out


def test_yaml_transport_round_trip():
    t = toy_theory.THEORY
    d = theory_to_dict(t)
    t2 = theory_from_dict(d)
    assert canonical_hash(theory_to_dict(t2)) == canonical_hash(d)
    assert t2.id == t.id and len(t2.predictions) == len(t.predictions)
    # the declarative half round-trips; experiments are code and resolve by
    # reference (module:experiment name) when transported — here we re-attach
    # them explicitly to verify the full theory compiles to the SAME manifest
    # hash as the original
    from r2a2.api import Theory
    t2.experiments = dict(t.experiments)
    m1, l1 = compile_theory(t); m1.freeze()
    m2, l2 = compile_theory(t2); m2.freeze()
    assert m1.hash == m2.hash


def test_transport_rejects_incomplete():
    with pytest.raises(Exception):
        theory_from_dict({"id": "x"})  # no version


def test_json_transport_file():
    d = theory_to_dict(ising_toy.THEORY)
    t = theory_from_dict(json.loads(json.dumps(d)))
    assert t.id == "ising-toy"
