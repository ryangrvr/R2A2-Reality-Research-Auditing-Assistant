"""Tests for the audit rules: the generalized GRU disciplines."""
import pytest

from r2a2.audit import audit_theory
from r2a2.api import Theory, Parameter, Prediction, Test, Assumption
from r2a2.compiler import compile_theory


def _audit(theory):
    m, led = compile_theory(theory)
    m.freeze()
    return audit_theory(theory, led), led


def test_missing_kill_condition_blocks_at_declaration():
    """A prediction with no kill condition cannot even be declared."""
    with pytest.raises(ValueError):
        Prediction("P", "d", "e", "o", kill_condition="")


def test_good_theory_passes():
    t = Theory(
        id="t", version="1",
        parameters=[Parameter("a", kind="commitment", value=1)],
        assumptions=[Assumption("A1", "x", priced=True)],
        predictions=[Prediction("P", "d", "e", "o", kill_condition="k",
                                assumptions=["A1"], parameters=["a"])],
        tests=[Test("T1", kind="identity", experiment="e", exact=True),
               Test("T2", kind="hostile-control", experiment="e")],
        experiments={"e": lambda: {"x": 1}},
    )
    report, _ = _audit(t)
    assert report.ok, report.blocking


def test_silent_refit_flagged():
    t = Theory(
        id="t", version="1",
        predictions=[Prediction("P", "d", "e", "o", kill_condition="k")],
        tests=[Test("T1", kind="identity", experiment="e", exact=True)],
        experiments={"e": lambda: {}})
    m, led = compile_theory(t)
    m.freeze()
    # a parameter silently refit outside its sector
    led.add("param:theta", "parameter", refit=True, refit_declared=False)
    report = audit_theory(t, led)
    assert any("UNDECLARED REFIT" in b for b in report.blocking)
    # declared refits only warn? No — declared refits are legal (explicit
    # commitment); only silent ones block.
    led2 = led
    led2.nodes["param:theta"].attrs["refit_declared"] = True
    report2 = audit_theory(t, led2)
    assert not any("UNDECLARED REFIT" in b for b in report2.blocking)


def test_laundering_blocked():
    t = Theory(
        id="t", version="1",
        predictions=[Prediction("P", "d", "e", "o", kill_condition="k")],
        tests=[Test("T1", kind="identity", experiment="e", exact=True)],
        experiments={"e": lambda: {}})
    m, led = compile_theory(t)
    m.freeze()
    led.nodes["predict:P"].attrs.update({"kind": "derived", "new_inputs": 2})
    report = audit_theory(t, led)
    assert any("PROVENANCE VIOLATION" in b for b in report.blocking)
    led.nodes["predict:P"].attrs["stance_justification"] = "declared recovery"
    report2 = audit_theory(t, led)
    assert not any("PROVENANCE VIOLATION" in b for b in report2.blocking)
