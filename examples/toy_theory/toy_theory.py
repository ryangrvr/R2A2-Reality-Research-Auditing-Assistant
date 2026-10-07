"""Example 1: tiny analytic toy theory (pure Python, unit-test grade).

Demonstrates the minimal plugin: one commitment parameter, one assumption,
one prediction with a kill condition, one exact identity test.
"""
from r2a2.api import Theory, Parameter, Assumption, Prediction, Test

def _expt_predict(a=2.0, b=1.0):
    return {"y2": a * 2 + b}


def _expt_identity(a=2.0, b=1.0):
    return {"residual": (a * 1 + b) - 3.0}


def _expt_hostile(a=2.0, b=1.0):
    return {"quadratic_coeff": 0.0}


THEORY = Theory(
    id="toy-linear",
    version="0.1.0",
    description="y = a*x + b, predicting y(2) = 5 from y(0)=1, y(1)=3.",
    parameters=[
        Parameter("a", kind="fitted-parameter", sector="calibration",
                  source="toy-dataset", value=2.0),
        Parameter("b", kind="fitted-parameter", sector="calibration",
                  source="toy-dataset", value=1.0),
    ],
    assumptions=[Assumption("A1", "the relation is linear on the calibration range",
                            kind="assumption", priced=True)],
    sources={"toy-dataset": "synthetic calibration points (0,1), (1,3)"},
    predictions=[
        Prediction("P-y2", "y(2) = 5", experiment="predict", observable="y2",
                   kill_condition="observed y(2) outside 5 +/- 1e-9",
                   assumptions=["A1"], parameters=["a", "b"],
                   evidence_grade="numerical", sector="extrapolation"),
    ],
    tests=[
        Test("T-identity", kind="identity", experiment="identity",
             description="y(1) reproduces the calibration point exactly", exact=True),
        Test("T-hostile", kind="hostile-control", experiment="hostile",
             description="quadratic term must be indistinguishable from zero "
                         "on the calibration range"),
    ],
    experiments={
        "predict": _expt_predict,
        "identity": _expt_identity,
        "hostile": _expt_hostile,
    },
)
