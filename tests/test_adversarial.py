"""Adversarial generalization: alien theories through the unchanged SDK.

If any of these requires an `if theory == ...` inside core, the abstraction
has failed. These tests import nothing but the public API + engine.
"""
import sys, os
import math

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
for name in ("alien_theories",):
    sys.path.insert(0, os.path.join(HERE, "..", "examples", name))

import bayesian_decay  # noqa: E402
import ising_toy  # noqa: E402
import gauge_toy  # noqa: E402

from r2a2.compiler import compile_theory  # noqa: E402
from r2a2.audit import audit_theory  # noqa: E402
from r2a2.runner import run_manifest  # noqa: E402
from r2a2.queries import why, impact, inputs, out_of_sample_warning  # noqa: E402


ALIENS = [bayesian_decay.THEORY, ising_toy.THEORY, gauge_toy.THEORY]


@pytest.mark.parametrize("theory", ALIENS, ids=lambda t: t.id)
def test_alien_theory_compiles_runs_audits(theory):
    m, led = compile_theory(theory, seeds={"default": 0})
    h = m.freeze()
    assert h
    report = audit_theory(theory, led)
    assert report.ok, report.blocking
    res = run_manifest(theory, m, led)
    assert res.records


def test_bayesian_posterior_prediction():
    assert abs(bayesian_decay.predictive_half_life()["half_life_mean"] - 0.1) < 0.02


def test_ising_exact_identity():
    res = ising_toy.theory_experiments["duality"]() if hasattr(ising_toy, "theory_experiments") \
        else ising_toy.THEORY.experiments["duality"]()
    assert res["Z_enum"] == pytest.approx(res["Z_closed"], rel=1e-12)
    r = ising_toy.THEORY.experiments["enumerate"]()
    assert r["m2_rise"] > 0.15


def test_ising_hostile_control_fires():
    r = ising_toy.THEORY.experiments["hostile"]()
    assert r["matches_mean_field"] is False


def test_gauge_transformation_class_is_native():
    t = gauge_toy.THEORY
    # the gauge class is an API object, not an assumption with special casing
    assert t.transformation_classes[0].id == "Z2-gauge"
    qc = t.transformation_classes[0].quotient_distance
    # a sign flip is within distance 0 of itself in the quotient
    assert qc(1, 2.5, -1, 2.5) == 0.0
    # invariant observable unchanged under gauge
    assert t.experiments["identity"]()["gauge_shift"] == 0.0
    # the gauge-DEPENDENT observable is genuinely distinguishable in the orbit
    dep = t.experiments["measure_dep"]()
    assert dep["orbit_variation"] == 5.0  # not gauge-invariant


def test_every_alien_runs_under_same_backend():
    from r2a2.backends import LocalBackend
    for theory in ALIENS:
        be = LocalBackend(seed=0)
        out = be.run_experiment(theory, list(theory.experiments)[0])
        assert isinstance(out, dict)


def test_why_query_on_alien():
    theory = bayesian_decay.THEORY
    m, led = compile_theory(theory)
    m.freeze()
    tree = why(led, "predict:P-half-life")
    assert "param:lambda" in tree
    assert "assume:A-exp" in tree


def test_impact_query():
    theory = bayesian_decay.THEORY
    m, led = compile_theory(theory)
    m.freeze()
    collapsing = impact(led, "assume:A-exp")
    assert "predict:P-half-life" in collapsing


def test_out_of_sample_warning():
    theory = bayesian_decay.THEORY
    m, led = compile_theory(theory)
    m.freeze()
    # simulate the classic error: the prediction's evaluation data is also in
    # its calibration cone
    led.nodes["source:decay-counts"].attrs["provides_datasets"] = ["D7"]
    led.nodes["predict:P-half-life"].attrs["evaluation_datasets"] = ["D7"]
    warns = out_of_sample_warning(led, "predict:P-half-life")
    assert warns and "not out-of-sample" in warns[0]
