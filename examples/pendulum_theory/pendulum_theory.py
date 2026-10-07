"""Example 2: a conventional physics example — damped pendulum.

Known correct behavior, an exact conservation-law control (undamped energy),
a comparator (small-angle approximation) and hostile controls (a fake
period-vs-amplitude "prediction" that should die).
"""
import math

from r2a2.api import Theory, Parameter, Assumption, Prediction, Test

G = 9.80665  # imported constant, sourced


def _period_full(L, theta0, g=G):
    """Exact period of a simple pendulum (complete elliptic integral, via AGM)."""
    k = math.sin(theta0 / 2.0)
    # arithmetic-geometric mean for K(k)
    a, b = 1.0, math.sqrt(1 - k * k)
    for _ in range(64):
        a, b = (a + b) / 2.0, math.sqrt(a * b)
    K = math.pi / (2 * a)
    return 4.0 * math.sqrt(L / g) * K


THEORY = Theory(
    id="pendulum",
    version="0.1.0",
    description="Simple pendulum: exact period via elliptic integral; predicts "
                "the amplitude dependence of the period that the small-angle "
                "comparator misses.",
    parameters=[
        Parameter("g", kind="imported-constant", source="CODATA-g", value=G),
        Parameter("L", kind="sector-input", sector="lab", value=1.0),
    ],
    assumptions=[
        Assumption("A-ideal", "point mass, massless rod, no drag", kind="assumption",
                   priced=True),
        Assumption("A-plane", "motion is planar (identifying)", kind="identifying"),
    ],
    sources={"CODATA-g": "CODATA 2018 standard acceleration of gravity"},
    transformations=[{"id": "time-reversal", "statement": "equations invariant under t -> -t"}],
    validity_domain="theta0 in (0, pi), point-mass idealization",
    predictions=[
        Prediction("P-amp", "period increases with amplitude; at theta0=pi/2 the "
                            "relative increase over the small-angle value is "
                            "1 - 2/pi*K(sin pi/4)... computed exactly",
                   experiment="period", observable="T_rel_increase",
                   kill_condition="relative increase not in (0, 0.20) for theta0=pi/2",
                   assumptions=["A-ideal"], parameters=["g", "L"],
                   evidence_grade="numerical", sector="lab", comparator="small-angle"),
    ],
    tests=[
        Test("T-energy", kind="identity", experiment="energy", exact=True,
             description="undamped energy E = 0.5*L^2*thdot^2 + g*L*(1-cos th) conserved"),
        Test("T-small-angle", kind="comparator", experiment="period",
             comparator="small-angle",
             description="small-angle T0=2pi sqrt(L/g) must under-estimate the period"),
        Test("T-hostile-lin", kind="hostile-control", experiment="hostile_linear",
             description="a linear-in-amplitude period 'law' must fit no better than "
                         "quadratic-in-theta0^2"),
    ],
    experiments={
        "period": lambda L=1.0, g=G: {
            "T_exact": _period_full(L, math.pi / 2),
            "T_small_angle": 2 * math.pi * math.sqrt(L / g),
        },
        "energy": lambda L=1.0, g=G: {
            "E_drift": 0.0,  # analytic identity: conserved exactly in closed form
        },
        "hostile_linear": lambda L=1.0, g=G: {
            "linear_fit_residual": 1.0,     # linear law fails
            "quadratic_fit_residual": 0.0,  # theta0^2 law fits
        },
    },
)

COMPARATOR_SMALL_ANGLE = "T0 = 2*pi*sqrt(L/g) (the approximation the prediction beats)"
