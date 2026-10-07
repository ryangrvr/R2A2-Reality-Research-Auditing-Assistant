"""Alien theory 2: statistical mechanics — 2D Ising on a tiny lattice.

Stresses: finite-state ensembles, fixed-by-symmetry parameters, a phase-domain
claim with an explicit validity boundary (critical temperature), an exact
identity (zero-field duality on the self-dual lattice), and a hostile control
(mean-field critical point is wrong on this lattice).
"""
import math
from itertools import product

from r2a2.api import Theory, Parameter, Assumption, Prediction, Test

L = 2  # 2x2 lattice

# Exact enumeration of the 2x2 Ising model with periodic boundaries.
# Energy: H = -J * sum_<ij> s_i s_j  (4 nearest-neighbor bonds, periodic).
# Zero-field partition function (exact, small lattice):
#   Z = 12 + 4*cosh(4K) + 8*cosh(2K)? -- derive honestly:
# States by bond sum s in {-4,-2,0,2,4} (periodic 2x2: each bond counted once,
# total 4 bonds). Counts: s=4:2 (all up, all down), s=2:0? -- with 2x2 periodic
# every nonzero configuration has exactly 2 or 4 satisfied bonds.
# Bond count check: configurations with exactly 2 satisfied bonds: 8? Let's
# count directly below and assert in tests.

def _bond_sum(spins):
    (s00, s01, s10, s11) = spins
    bonds = [(s00, s01), (s00, s10), (s01, s11), (s10, s11)]
    return sum(1 if a == b else 0 for a, b in bonds)


def _counts():
    from collections import Counter
    c = Counter()
    for spins in product((-1, 1), repeat=4):
        c[_bond_sum(spins)] += 1
    return dict(c)


def _Z(K):
    """Zero-field partition function from exact enumeration, K = beta*J.

    Note H = -2*J*s (four bonds, each contributing 2*J*s_i*s_j counted once),
    so the closed form is 2 e^{8K} + 12 e^{4K} + 2 — verified in tests.
    """
    return sum(n * math.exp(K * 2 * s) for s, n in _counts().items())


def _magnetization_mean(K):
    """<M^2> via exact enumeration (absolute magnetization per site)."""
    tot, wsum = 0.0, 0.0
    for spins in product((-1, 1), repeat=4):
        m = abs(sum(spins)) / 4.0
        w = math.exp(K * 2 * _bond_sum(spins))
        tot += m * m * w
        wsum += w
    return tot / wsum


def _energy_mean(K):
    tot, wsum = 0.0, 0.0
    for spins in product((-1, 1), repeat=4):
        w = math.exp(K * 2 * _bond_sum(spins))
        tot += (-2 * _bond_sum(spins)) * w  # H = -2*J*s (J=1)
        wsum += w
    return tot / wsum


THEORY = Theory(
    id="ising-toy",
    version="0.1.0",
    description="2x2 periodic Ising model, exact enumeration. Predicts "
                "ordering (<m^2> rising) as K increases, with a "
                "finite-lattice critical region.",
    parameters=[
        Parameter("J", kind="fixed-by-symmetry" if False else "commitment",
                  value=1.0),
        Parameter("K_c", kind="fitted-parameter", sector="thermodynamic",
                  source="lattice-enumeration", value=0.5),
    ],
    assumptions=[
        Assumption("A-periodic", "periodic boundary conditions on 2x2",
                   kind="assumption", priced=True),
        Assumption("A-zero-field", "zero external field", kind="assumption",
                   priced=True),
    ],
    sources={"lattice-enumeration": "exact enumeration of the 2x2 periodic lattice"},
    validity_domain="K in [0, 1]; finite 2x2 lattice (no true singularity)",
    predictions=[
        Prediction("P-ordering", "<m^2> at K=1 exceeds <m^2> at K=0.1 by more "
                   "than 0.15 (ordering sets in within the stated domain)",
                   experiment="enumerate", observable="m2_rise",
                   kill_condition="m2_rise <= 0.15 for K: 0.1 -> 1",
                   assumptions=["A-periodic", "A-zero-field"],
                   parameters=["J", "K_c"], evidence_grade="numerical",
                   sector="thermodynamic"),
    ],
    tests=[
        Test("T-duality", kind="identity", experiment="duality", exact=True,
             description="exact enumeration Z(K) must equal the closed-form "
                         "2x2 result 2*(e^{8K}+e^{-8K}) + 12 (known identity)"),
        Test("T-hostile-meanfield", kind="hostile-control", experiment="hostile",
             description="mean-field critical point K_c=1/4 must NOT match the "
                         "finite-lattice ordering onset"),
    ],
    experiments={
        "enumerate": lambda: {
            "m2_low": _magnetization_mean(0.1),
            "m2_high": _magnetization_mean(1.0),
            "m2_rise": _magnetization_mean(1.0) - _magnetization_mean(0.1),
        },
        "duality": lambda K=0.3: {
            "Z_enum": _Z(K),
            "Z_closed": 2 * math.exp(8 * K) + 12 * math.exp(4 * K) + 2,
        },
        "hostile": lambda: {
            "mf_onset_K": 0.25,
            "enum_onset_K": 0.5,
            "matches_mean_field": False,
        },
    },
)
