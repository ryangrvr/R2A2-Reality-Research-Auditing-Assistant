"""Corpus theory 3: Bayesian epidemiological toy (SIR-lite) with
calibration/evaluation leakage test.

Stresses: external prior, inferred parameters, posterior-predictive claim,
and an explicit out-of-sample test in a second sector.
"""
import math

from r2a2.api import Theory, Parameter, Assumption, Prediction, Test


def r0_from_growth(growth_rate, gamma):
    """For SIR with recovery gamma, R0 = 1 + growth/gamma."""
    return 1.0 + growth_rate / gamma


def predicted_growth(R0, gamma):
    """Inverse relation (the posterior-predictive claim)."""
    return gamma * (R0 - 1.0)


def _expt_calibration(R0=2.0, gamma=0.5):
    """Calibration sector: infer growth from (R0, gamma)."""
    return {"growth": predicted_growth(R0, gamma)}


def _expt_eval(R0=2.0, gamma=0.5):
    """Evaluation sector: NEW wave, R0 refrozen from calibration."""
    return {"growth_eval": predicted_growth(R0, gamma)}


def _expt_identity(R0=2.0, gamma=0.5):
    """Exact algebraic identity: the two formulas are mutual inverses."""
    return {"roundtrip_gap": r0_from_growth(predicted_growth(R0, gamma), gamma) - R0}


def _expt_leakage_check():
    """Hostile control: sector-B evaluation uses wave-2 data; if the
    calibration had seen wave-2 data, the prediction is not out-of-sample.
    This check must report NO overlap for the discipline to hold."""
    return {"wave2_in_calibration": False}


THEORY = Theory(
    id="epi-toy",
    version="0.1.0",
    description="SIR-lite: R0 = 1 + growth/gamma. Calibration fits (R0, gamma) "
                "on wave 1; the evaluation sector predicts wave 2 growth with "
                "the same frozen values.",
    parameters=[
        Parameter("R0", kind="fitted-parameter", sector="calibration",
                  source="wave1", value=2.0),
        Parameter("gamma", kind="external-prior", source="literature-gamma",
                  value=0.5),
    ],
    assumptions=[
        Assumption("A-SIR", "SIR dynamics with constant recovery rate",
                   kind="assumption", priced=True),
        Assumption("A-homog", "homogeneous mixing (identifying)",
                   kind="identifying"),
    ],
    sources={"wave1": "early epidemic growth rates, wave 1",
             "literature-gamma": "published recovery-rate estimate"},
    validity_domain="single wave, early exponential phase",
    predictions=[
        Prediction("P-wave2", "wave-2 growth matches gamma*(R0-1) with the "
                   "calibration-frozen R0",
                   experiment="eval", observable="growth_eval",
                   kill_condition="wave-2 growth outside gamma*(R0-1) +/- 0.05",
                   assumptions=["A-SIR"], parameters=["R0", "gamma"],
                   evidence_grade="numerical", sector="evaluation"),
    ],
    tests=[
        Test("T-inverse", kind="identity", experiment="identity", exact=True,
             description="growth<->R0 formulas are mutual inverses (algebraic)"),
        Test("T-leakage", kind="holdout", experiment="leakage",
             description="wave-2 data must not have entered calibration"),
    ],
    experiments={
        "calibration": _expt_calibration,
        "eval": _expt_eval,
        "identity": _expt_identity,
        "leakage": _expt_leakage_check,
    },
)
