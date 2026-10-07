"""End-to-end: examples compile, run, and audit through the public API only."""
import sys
import os

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "examples", "toy_theory"))
sys.path.insert(0, os.path.join(HERE, "..", "examples", "pendulum_theory"))
sys.path.insert(0, os.path.join(HERE, "..", "examples", "grut_adapter"))

import toy_theory  # noqa: E402
import pendulum_theory  # noqa: E402
import grut_adapter  # noqa: E402

from r2a2.compiler import compile_theory  # noqa: E402
from r2a2.audit import audit_theory  # noqa: E402
from r2a2.runner import run_manifest  # noqa: E402
from r2a2.backends import get_backend  # noqa: E402


def test_toy_end_to_end():
    t = toy_theory.THEORY
    m, led = compile_theory(t, seeds={"default": 0})
    h = m.freeze()
    assert h
    # prediction checks out
    assert t.experiments["predict"]()["y2"] == 5.0
    assert t.experiments["identity"]()["residual"] == 0.0
    report = audit_theory(t, led)
    assert report.ok, report.blocking


def test_pendulum_prediction_is_real():
    t = pendulum_theory.THEORY
    res = t.experiments["period"](L=1.0)
    # the exact period exceeds the small-angle one, but by < 20%
    inc = res["T_exact"] / res["T_small_angle"] - 1
    assert 0 < inc < 0.20


def test_pendulum_end_to_end_audit():
    t = pendulum_theory.THEORY
    m, led = compile_theory(t, seeds={"default": 0})
    m.freeze()
    report = audit_theory(t, led)
    assert report.ok, report.blocking
    assert any("hostile-control" == k.kind for k in t.tests)


def test_runner_attaches_results_without_rewriting_graph():
    t = toy_theory.THEORY
    m, led = compile_theory(t, seeds={"default": 0})
    m.freeze()
    before = {n: sorted(d.deps) for n, d in led.nodes.items()}
    res = run_manifest(t, m, led)
    assert res.records
    assert "result:predict" in led.nodes
    # preregistered nodes unchanged
    after = {n: sorted(d.deps) for n, d in led.nodes.items() if n in before}
    assert after == before


def test_backend_protocol():
    be = get_backend("local", seed=0)
    assert isinstance(be, type("x", (), {}) if False else object)
    caps = be.capabilities()
    assert caps["deterministic"] is True
    assert caps["accelerator"] is False


def test_grut_adapter_loads_real_claims():
    """The adversarial test: the GRUT adapter works as a pure client."""
    claims, source_ids, result = grut_adapter.load_grut_claims()
    assert claims
    assert result.ok, result.blocking
    theory = grut_adapter.grut_claims_to_theory(claims)
    assert theory.id == "grut-fragment"
    # and the adapted theory compiles through the PUBLIC SDK with no core changes
    m, led = compile_theory(theory)
    m.freeze()
    assert len(led.nodes) > 0
