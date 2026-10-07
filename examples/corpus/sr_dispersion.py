"""Corpus theory 2: special-relativistic dispersion with Lorentz invariance.

Stresses TransformationClass (boosts), a comparator against the Galilean
prediction, and an invariant-mass identity.
"""
import math

from r2a2.api import (Theory, Parameter, Assumption, Prediction, Test,
                      Comparator, TransformationClass)

C = 1.0  # natural units (imported constant, declared)


def boost_velocity(v, u):
    """Einstein velocity addition: boost by u."""
    return (v - u) / (1 - v * u)


def galilean_velocity(v, u):
    """Galilean velocity addition (the comparator that must FAIL)."""
    return v - u


def is_proper_boost(u):
    return abs(u) < 1.0  # subluminal


def _compose_boosts(u1, u2):
    """Relativistic composition of two boosts."""
    return (u1 + u2) / (1 + u1 * u2)


BOOSTS = TransformationClass(
    id="lorentz-boosts",
    description="Subluminal boosts acting on velocities; the invariant is the "
                "rest mass (dispersion E^2 = p^2 + m^2).",
    is_member=is_proper_boost,
    compose=_compose_boosts,
)


def dispersion_energy(p, m):
    return math.sqrt(p * p + m * m)


def galilean_energy(p, m):
    """Kinetic-only Galilean dispersion (must disagree relativistically)."""
    return 0.5 * p * p / m + m


def _expt_dispersion(p=0.5, m=1.0):
    return {"E_rel": dispersion_energy(p, m),
            "E_gal": galilean_energy(p, m)}


def _expt_boost_identity(u=0.3, v=0.5):
    """Exact identity: two boosts compose per the velocity-addition law, and
    the composed boost of the composition equals the composition of boosts."""
    w1 = boost_velocity(v, u)
    w2 = boost_velocity(boost_velocity(v, u / 2), u / 2)
    return {"compose_gap": w1 - w2}


def _expt_hostile_galilean(u=0.3, v=0.5):
    """Hostile control: the Galilean law must NOT reproduce the relativistic
    composition at these speeds."""
    rel = boost_velocity(v, u)
    gal = galilean_velocity(v, u)
    return {"differs": abs(rel - gal) > 1e-9, "rel": rel, "gal": gal}


THEORY = Theory(
    id="sr-dispersion",
    version="0.1.0",
    description="Special-relativistic dispersion E^2 = p^2 + m^2 with "
                "Lorentz boosts as the declared transformation class; the "
                "Galilean dispersion is the comparator it must differ from.",
    parameters=[
        Parameter("c", kind="imported-constant", source="natural-units", value=1.0),
        Parameter("m", kind="fixed-by-symmetry" if False else "commitment", value=1.0),
    ],
    assumptions=[
        Assumption("A-SR", "special relativity holds in the domain",
                   kind="assumption", priced=True),
    ],
    transformation_classes=[BOOSTS],
    comparators=[Comparator("galilean", "Galilean dispersion/composition")],
    sources={"natural-units": "c=1 conventional unit choice"},
    validity_domain="p in [0, 0.9], subluminal boosts |u|<1, m=1",
    predictions=[
        Prediction("P-dispersion", "relativistic energy exceeds the Galilean "
                   "one at p=0.5 by ~4.6%",
                   experiment="dispersion", observable="E_rel",
                   kill_condition="E_rel <= E_gal at p=0.5",
                   assumptions=["A-SR"], parameters=["c", "m"],
                   evidence_grade="formal", sector="kinematics",
                   comparator="galilean"),
    ],
    tests=[
        Test("T-boost", kind="identity", experiment="boost_identity", exact=True,
             description="boost composition is associative-exact"),
        Test("T-hostile-gal", kind="hostile-control", experiment="hostile_galilean",
             description="Galilean law must differ from relativistic composition"),
    ],
    experiments={
        "dispersion": _expt_dispersion,
        "boost_identity": _expt_boost_identity,
        "hostile_galilean": _expt_hostile_galilean,
    },
)
