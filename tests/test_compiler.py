"""Tests for the compiler: manifest freezing and graph construction."""
import pytest

from r2a2.api import Theory, Parameter, Prediction
from r2a2.compiler import ExecutionManifest, compile_theory


def _theory():
    return Theory(
        id="t", version="1.0",
        parameters=[Parameter("a", kind="fitted-parameter", sector="s1", source="d")],
        sources={"d": "dataset"},
        predictions=[Prediction("P", "pred", experiment="e", observable="o",
                                kill_condition="x>0", parameters=["a"])],
        experiments={"e": lambda: {"o": 1}},
    )


def test_manifest_freeze_and_immutability():
    m, led = compile_theory(_theory())
    h1 = m.freeze()
    assert h1
    with pytest.raises(RuntimeError):
        m.backend = "other"
    # freezing twice gives the same hash
    assert m.freeze() == h1


def test_compile_builds_graph():
    m, led = compile_theory(_theory())
    m.freeze()
    assert "predict:P" in led.nodes
    assert "param:a" in led.ancestors("predict:P")
    assert led.nodes["param:a"].debt.get("fitted-parameter") == 1
    assert led.find_cycles() == []


def test_compile_rejects_bad_theory():
    bad = Theory(id="b", version="1", experiments={})
    bad.predictions.append(Prediction("P", "d", experiment="nope", observable="o",
                                      kill_condition="k"))
    with pytest.raises(ValueError):
        compile_theory(bad)


def test_fitted_parameter_requires_source():
    with pytest.raises(ValueError):
        Parameter("a", kind="fitted-parameter")
