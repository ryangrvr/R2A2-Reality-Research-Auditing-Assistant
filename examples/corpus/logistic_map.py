"""Corpus theory 5: nonlinear dynamical system (logistic map) with stochastic
seed, ensemble output, nontrivial validity domain, replication requirement.

Stresses: seeded ensembles, statistics over runs, explicit replication rule,
and chaos-limited validity claims.
"""
import math
import random

from r2a2.api import Theory, Parameter, Assumption, Prediction, Test


def logistic(x, r):
    return r * x * (1 - x)


def ensemble_lyapunov(r=3.9, n_orbits=32, T=200, seed=0):
    """Ensemble estimate of the Lyapunov exponent via the standard formula."""
    rng = random.Random(seed)
    total = 0.0
    for _ in range(n_orbits):
        x = rng.random()
        s = 0.0
        for _ in range(T):
            dx = abs(r * (1 - 2 * x))
            s += math.log(max(dx, 1e-12))
            x = logistic(x, r)
        total += s / T
    return total / n_orbits


def period_doubling_onset(r_start=2.5, tol=1e-3):
    """Find the first period-doubling: x oscillates between 2 values."""
    lo, hi = r_start, 3.0
    def cycles(r):
        x, hist = 0.2, []
        for i in range(500):
            x = logistic(x, r)
            if i >= 400:
                hist.append(round(x, 6))
        return len(set(hist))
    while hi - lo > tol:
        mid = (lo + hi) / 2
        if cycles(mid) > 1:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def _expt_lyapunov(r=3.9):
    return {"lambda": ensemble_lyapunov(r), "positive": ensemble_lyapunov(r) > 0}


def _expt_seed_ab(seed=0):
    """A/B: two seeds must agree on the sign, differ in low-order digits —
    chaos is the point, but the exponent converges."""
    la = ensemble_lyapunov(seed=seed)
    lb = ensemble_lyapunov(seed=seed + 1)
    return {"lambda_A": la, "lambda_B": lb,
            "signs_agree": (la > 0) == (lb > 0)}


def _expt_identity(r=3.2):
    """Exact identity: a period-n fixed point satisfies logistic^n(x) = x."""
    # at r=3.2 the 2-cycle values are known exactly:
    x = (1 + r + math.sqrt((r - 3) * (r + 1))) / (2 * r)
    xn = logistic(logistic(x, r), r)
    return {"fixed_point_gap": xn - x}


def _expt_hostile_stable(r=2.5):
    """Hostile control: at r=2.5 the Lyapunov exponent must be NEGATIVE
    (stable fixed point). If the estimator says otherwise, it is broken."""
    return {"lambda_stable": ensemble_lyapunov(r), "expected_negative": True}


def _expt_onset():
    return {"onset": period_doubling_onset()}


THEORY = Theory(
    id="logistic-map",
    version="0.1.0",
    description="Logistic map: ensemble Lyapunov exponent positive for "
                "r=3.9 (chaos), negative for r=2.5 (stable), with the "
                "period-doubling onset located numerically.",
    parameters=[
        Parameter("r_chaos", kind="sector-input", sector="chaotic-regime", value=3.9),
        Parameter("r_stable", kind="sector-input", sector="stable-regime", value=2.5),
    ],
    assumptions=[
        Assumption("A-discrete", "discrete-time logistic dynamics",
                   kind="assumption", priced=True),
    ],
    validity_domain="r in [2.5, 4.0], T=200 transient-removed, ensemble n=32; "
                    "exponent is regime-averaged, not pointwise",
    predictions=[
        Prediction("P-chaos", "the ensemble Lyapunov exponent at r=3.9 is "
                   "positive (~0.49) and at r=2.5 is negative",
                   experiment="lyapunov", observable="lambda",
                   kill_condition="lambda(3.9) <= 0 or lambda(2.5) >= 0",
                   assumptions=["A-discrete"], parameters=["r_chaos", "r_stable"],
                   evidence_grade="numerical", sector="chaotic-regime"),
    ],
    tests=[
        Test("T-cycle", kind="identity", experiment="identity", exact=True,
             description="the analytic 2-cycle point is an exact fixed point "
                         "of logistic^2"),
        Test("T-seed-robust", kind="comparator", experiment="seed_ab",
             description="two different seeds must agree on the exponent SIGN "
                         "(chaos is seed-independent in sign)"),
        Test("T-hostile-stable", kind="hostile-control", experiment="hostile_stable",
             description="the estimator must give a negative exponent in the "
                         "stable regime; else the estimator is broken"),
    ],
    experiments={
        "lyapunov": _expt_lyapunov,
        "seed_ab": _expt_seed_ab,
        "identity": _expt_identity,
        "hostile_stable": _expt_hostile_stable,
        "onset": _expt_onset,
    },
)
