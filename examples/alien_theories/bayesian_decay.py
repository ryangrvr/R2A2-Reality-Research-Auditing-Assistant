"""Alien theory 1: a probabilistic/Bayesian theory — radioactive decay.

Stresses the SDK differently from the mechanical examples: the "prediction"
is a posterior/predictive distribution, the parameter is *inferred* (external
prior + data), and the kill condition is a frequentist-style discrepancy
between predicted and observed half-life.
"""
import math

from r2a2.api import (Theory, Parameter, Assumption, Prediction, Test,
                      Comparator)

# Half-life posterior for a decay with exponential likelihood:
# with a flat prior on lambda and n decays over time T, the posterior on
# lambda is Gamma(shape=n, rate=T). Predictive mean half-life = ln2 * T/n.
T_OBS = 100.0
N_DECAYS = 693.0  # chosen so mean half-life ≈ 0.1


def predictive_half_life(T=T_OBS, n=N_DECAYS, **_):
    mean_lambda = n / T
    return {"half_life_mean": math.log(2.0) / mean_lambda}


THEORY = Theory(
    id="bayesian-decay",
    version="0.1.0",
    description="Bayesian inference of a decay rate: posterior is analytic "
                "(Gamma), prediction is the posterior mean half-life.",
    parameters=[
        Parameter("lambda", kind="fitted-parameter", sector="calibration",
                  source="decay-counts", value=N_DECAYS / T_OBS),
        Parameter("T", kind="sector-input", sector="calibration", value=T_OBS),
        Parameter("n", kind="sector-input", sector="calibration", value=N_DECAYS),
    ],
    assumptions=[
        Assumption("A-exp", "decay law is exponential (constant hazard)",
                   kind="assumption", priced=True),
        Assumption("A-flat", "flat prior on lambda (prior sensitivity declared)",
                   kind="assumption", priced=True),
    ],
    sources={"decay-counts": "synthetic decay counts: n decays over time T"},
    comparators=[
        Comparator("constant-hazard-null", "null model: hazard varies uniformly, "
                   "predicting no specific half-life", model=lambda: {"half_life": None}),
    ],
    predictions=[
        Prediction("P-half-life", "posterior mean half-life is ln(2)*T/n ≈ 0.1",
                   experiment="posterior", observable="half_life_mean",
                   kill_condition="posterior mean half-life outside 0.1 ± 0.02",
                   assumptions=["A-exp", "A-flat"], parameters=["lambda", "T", "n"],
                   evidence_grade="numerical", sector="new-sample", comparator="constant-hazard-null"),
    ],
    tests=[
        Test("T-posterior-identity", kind="identity", experiment="identity",
             exact=True,
             description="Gamma shape/rate from the counts reproduce the mean: "
                         "shape/rate == T/n == 1/lambda (exact algebraic identity)"),
        Test("T-hostile-flat", kind="hostile-control", experiment="hostile",
             description="under the null (no exponential law) the posterior "
                         "concentration must vanish: n=0 gives no constraint"),
    ],
    experiments={
        "posterior": predictive_half_life,
        "identity": lambda T=T_OBS, n=N_DECAYS: {
            "shape_over_rate_minus_lambda": (n / T) - (N_DECAYS / T_OBS),
        },
        "hostile": lambda: {"posterior_width_n0": float("inf"), "concentrated": False},
    },
)
