"""Corpus theory 4: modified-gravity toy — is the 'prediction' a refit?

Stresses: a baseline Newton comparator, one extra fitted parameter (gamma
anomaly), and a cross-sector transfer whose outcome DEPENDS on whether the
extra parameter was refit. This is the theory that must NOT survive a silent
refit — the transfer audit should catch it.
"""
import math

from r2a2.api import (Theory, Parameter, Assumption, Prediction, Test,
                      Comparator)


def newton_velocity(r, mu):
    return math.sqrt(mu / r)


def modified_velocity(r, mu, delta):
    """Toy modification: velocity boosted by delta at r=1."""
    return math.sqrt(mu / r) * (1.0 + delta)


def _expt_calibrate(mu=1.0, delta=0.1):
    """Calibration sector (solar system): fit mu and delta on data."""
    return {"mu_fit": mu, "delta_fit": delta}


def _expt_predict_galaxy(r=10.0, mu=1.0, delta=0.1):
    """Galaxy-sector prediction with FROZEN mu, delta (true transfer)."""
    return {"v_mod": modified_velocity(r, mu, delta),
            "v_newton": newton_velocity(r, mu)}


def _expt_identity(mu=1.0):
    """Exact identity: at delta=0 the modified law reduces to Newton."""
    return {"reduction_gap": modified_velocity(1.0, mu, 0.0) - newton_velocity(1.0, mu)}


def _expt_hostile_refit(delta=0.1):
    """Hostile control: if delta were REFIT per galaxy, the 'prediction'
    would be a fit, not a prediction. Report what a refit would give."""
    return {"refit_delta": delta, "refit_would_match": True}


THEORY = Theory(
    id="modified-gravity-toy",
    version="0.1.0",
    description="Toy modified gravity: velocity = Newton * (1+delta). Claims "
                "a galaxy-rotation prediction from solar-system calibration "
                "with delta frozen. The transfer audit is the point.",
    parameters=[
        Parameter("mu", kind="fitted-parameter", sector="solar", source="solar-data", value=1.0),
        Parameter("delta", kind="fitted-parameter", sector="solar", source="solar-data", value=0.1),
    ],
    assumptions=[
        Assumption("A-metric", "static weak-field metric ansatz", kind="assumption",
                   priced=True),
    ],
    comparators=[Comparator("newton", "Newtonian circular velocity")],
    sources={"solar-data": "planetary ephemerides (calibration arc)"},
    validity_domain="r in [0.8, 20], weak field, delta constant",
    predictions=[
        Prediction("P-galaxy", "galaxy circular velocity = Newton*(1+delta) "
                   "with solar-calibrated delta frozen",
                   experiment="predict_galaxy", observable="v_mod",
                   kill_condition="observed galaxy velocity outside Newton*(1+delta) "
                                  "+/- 1% with frozen delta",
                   assumptions=["A-metric"], parameters=["mu", "delta"],
                   evidence_grade="numerical", sector="galaxy",
                   comparator="newton"),
    ],
    tests=[
        Test("T-reduction", kind="identity", experiment="identity", exact=True,
             description="modified law reduces exactly to Newton at delta=0"),
        Test("T-refit-exposure", kind="hostile-control", experiment="hostile_refit",
             description="expose what a per-galaxy refit of delta would give; "
                         "the transfer audit must refuse it"),
    ],
    experiments={
        "calibrate": _expt_calibrate,
        "predict_galaxy": _expt_predict_galaxy,
        "identity": _expt_identity,
        "hostile_refit": _expt_hostile_refit,
    },
)
