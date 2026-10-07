"""Alien theory 3: a gauge-equivalence theory.

Stresses TransformationClass as a *natural* API citizen: two descriptions
related by a gauge transformation are the SAME physics, and a "prediction"
that merely restates a gauge choice must be caught as gauge-dependent
(equivalent to a restatement).
"""
import math

from r2a2.api import (Theory, Parameter, Assumption, Prediction, Test,
                      TransformationClass)


def gauge_spin_flip(theta):
    """The gauge group: Z2, theta -> -theta (or not). Represented as sign."""
    return theta


def transform(sign, theta):
    return sign * theta


def canonicalize(sign, theta):
    # canonical representative: choose sign > 0
    return (1, sign * theta)


def quotient_distance(sign1, theta1, sign2, theta2):
    """Distance modulo gauge: |theta1 - sign*theta2| minimized over gauge."""
    d_same = abs(theta1 - theta2)
    d_flip = abs(theta1 + theta2)
    return min(d_same, d_flip)


def _compose(s1, s2):
    return s1 * s2


def is_member(sign):
    return sign in (1, -1)


GAUGE = TransformationClass(
    id="Z2-gauge",
    description="Z2 gauge freedom: global sign flip of the order parameter is "
                "unphysical. Two states are gauge-equivalent iff they differ "
                "by a sign flip.",
    is_member=is_member,
    compose=_compose,
    canonicalize=canonicalize,
    quotient_distance=quotient_distance,
)


def observable_gauge_inv(sign, theta):
    """<|theta|>: gauge invariant."""
    return abs(sign * theta)


def observable_gauge_dep(sign, theta):
    """<theta> as declared: gauge-DEPENDENT — a gauge choice, not a prediction."""
    return sign * theta


THEORY = Theory(
    id="gauge-toy",
    version="0.1.0",
    description="Scalar theta with Z2 gauge freedom: only gauge-invariant "
                "observables count as predictions.",
    parameters=[Parameter("theta", kind="sector-input", sector="sample", value=2.5)],
    assumptions=[Assumption("A-Z2", "the only gauge freedom is the global sign",
                            kind="assumption", priced=True)],
    transformation_classes=[GAUGE],
    predictions=[
        Prediction("P-gauge-inv", "<|theta|> = 2.5, a gauge-invariant number",
                   experiment="measure_inv", observable="abs_theta",
                   kill_condition="|<|theta|>| outside 2.5 ± 1e-12",
                   parameters=["theta"], evidence_grade="numerical",
                   sector="sample"),
    ],
    tests=[
        Test("T-gauge-dep-flag", kind="hostile-control", experiment="measure_dep",
             description="<theta> with a chosen sign differs across the gauge "
                         "orbit: it must be flagged as gauge-dependent "
                         "(quotient distance to its flipped self is nonzero)"),
        Test("T-gauge-inv-identity", kind="identity", experiment="identity",
             exact=True,
             description="the invariant observable is unchanged under the "
                         "gauge map (exact identity: d(Inv, g*Inv) = 0)"),
    ],
    experiments={
        "measure_inv": lambda sign=1, theta=2.5: {"abs_theta": observable_gauge_inv(sign, theta)},
        "measure_dep": lambda sign=1, theta=2.5: {
            "theta_signed": observable_gauge_dep(sign, theta),
            # variation of the signed observable across the gauge orbit:
            # nonzero means the observable is NOT gauge-invariant
            "orbit_variation": observable_gauge_dep(1, theta) - observable_gauge_dep(-1, theta),
        },
        "identity": lambda sign=-1, theta=2.5: {
            "gauge_shift": observable_gauge_inv(-1, theta) - observable_gauge_inv(1, theta),
        },
    },
)
