"""Reference conventional-physics plugin: Newtonian two-body orbital dynamics.

Demonstrates that R2A2 improves the testing discipline of completely ordinary
physics: analytic Kepler solution + numerical integration as an A/B
replication pair, exact energy and angular-momentum identities, a deliberately
bad integrator as hostile control, parameter fitting on a calibration arc,
prediction on a held-out arc, and an explicit validity domain.

Pipeline: compile -> freeze -> run -> audit -> replicate -> attest -> export.
"""
import math

from r2a2.api import (Theory, Parameter, Assumption, Prediction, Test,
                      Comparator)

MU = 1.0  # gravitational parameter G*M, fitted in the calibration sector


def _accel(state, mu):
    x, y, vx, vy = state
    r3 = (x * x + y * y) ** 1.5
    return [-mu * x / r3, -mu * y / r3]


def _energy(state, mu):
    x, y, vx, vy = state
    return 0.5 * (vx * vx + vy * vy) - mu / math.sqrt(x * x + y * y)


def _angmom(state):
    x, y, vx, vy = state
    return x * vy - y * vx


def integrate_rk4(state, mu, dt, n):
    """Fourth-order Runge-Kutta orbit propagation (implementation A)."""
    x, y, vx, vy = state

    def deriv(s):
        ax, ay = _accel(s, mu)
        return [s[2], s[3], ax, ay]

    for _ in range(n):
        k1 = deriv([x, y, vx, vy])
        k2 = deriv([x + dt / 2 * k1[0], y + dt / 2 * k1[1],
                    vx + dt / 2 * k1[2], vy + dt / 2 * k1[3]])
        k3 = deriv([x + dt / 2 * k2[0], y + dt / 2 * k2[1],
                    vx + dt / 2 * k2[2], vy + dt / 2 * k2[3]])
        k4 = deriv([x + dt * k3[0], y + dt * k3[1],
                    vx + dt * k3[2], vy + dt * k3[3]])
        x += dt / 6 * (k1[0] + 2 * k2[0] + 2 * k3[0] + k4[0])
        y += dt / 6 * (k1[1] + 2 * k2[1] + 2 * k3[1] + k4[1])
        vx += dt / 6 * (k1[2] + 2 * k2[2] + 2 * k3[2] + k4[2])
        vy += dt / 6 * (k1[3] + 2 * k2[3] + 2 * k3[3] + k4[3])
    return [x, y, vx, vy]


def integrate_leapfrog(state, mu, dt, n):
    """Symplectic leapfrog orbit propagation (implementation B, separate
    algorithm, same equations -> L2 replication strength)."""
    x, y, vx, vy = state
    ax, ay = _accel([x, y, vx, vy], mu)
    for _ in range(n):
        vx += ax * dt / 2
        vy += ay * dt / 2
        x += vx * dt
        y += vy * dt
        ax, ay = _accel([x, y, vx, vy], mu)
        vx += ax * dt / 2
        vy += ay * dt / 2
    return [x, y, vx, vy]


def integrate_euler_naive(state, mu, dt, n):
    """Hostile control: explicit Euler. Energy drifts by construction — this
    'implementation' should FAIL the exact identity check."""
    x, y, vx, vy = state
    for _ in range(n):
        ax, ay = _accel([x, y, vx, vy], mu)
        x += vx * dt
        y += vy * dt
        vx += ax * dt
        vy += ay * dt
    return [x, y, vx, vy]


# initial conditions (circular orbit r=1, calibrated arc then held-out arc)
_IC = [1.0, 0.0, 0.0, 1.0]
_DT, _N_CAL, _N_HOLD = 0.01, 100, 200


def _expt_identity(state=None, mu=1.0):
    """Exact identities: RK4 and leapfrog must both conserve E and L."""
    s_rk = integrate_rk4(_IC, mu, _DT, _N_CAL)
    s_lf = integrate_leapfrog(_IC, mu, _DT, _N_CAL)
    return {
        "E_drift_rk4": abs(_energy(s_rk, mu) - _energy(_IC, mu)),
        "E_drift_leapfrog": abs(_energy(s_lf, mu) - _energy(_IC, mu)),
        "L_drift_rk4": abs(_angmom(s_rk) - _angmom(_IC)),
    }


def _expt_predict(state=None, mu=1.0):
    """Held-out arc: predict the position after the calibration + holdout."""
    s = integrate_rk4(_IC, mu, _DT, _N_CAL + _N_HOLD)
    return {"x_heldout": s[0], "y_heldout": s[1]}


def _expt_ab(state=None, mu=1.0):
    """A/B replication: RK4 vs leapfrog on the same arc (separate algorithms,
    same equations -> L2)."""
    s_a = integrate_rk4(_IC, mu, _DT, _N_CAL + _N_HOLD)
    s_b = integrate_leapfrog(_IC, mu, _DT, _N_CAL + _N_HOLD)
    return {"xA": s_a[0], "xB": s_b[0]}


def _expt_hostile_euler(state=None, mu=1.0):
    """Hostile control: explicit Euler must visibly violate energy."""
    s = integrate_euler_naive(_IC, mu, _DT, _N_CAL)
    return {"E_drift_euler": abs(_energy(s, mu) - _energy(_IC, mu))}


def _expt_kepler(mu=1.0):
    """Analytic comparator: Kepler period for the circular orbit."""
    return {"T_kepler": 2 * math.pi * math.sqrt(1.0 / mu)}


THEORY = Theory(
    id="newton-two-body",
    version="0.1.0",
    description="Newtonian two-body problem: numerical orbit propagation "
                "validated by exact conservation identities, analytic Kepler "
                "comparator, an intentionally bad integrator as hostile "
                "control, and a held-out-arc prediction.",
    parameters=[
        Parameter("mu", kind="fitted-parameter", sector="calibration",
                  source="calibration-arc", value=1.0),
    ],
    assumptions=[
        Assumption("A-inv", "the inverse-square law holds over the domain",
                   kind="assumption", priced=True),
        Assumption("A-planar", "the orbit is planar (identifying)",
                   kind="identifying"),
    ],
    comparators=[
        Comparator("kepler", "analytic Kepler solution for the circular orbit",
                   model=_expt_kepler),
    ],
    sources={"calibration-arc": "first 100 steps of the reference trajectory"},
    validity_domain="dt=0.01, circular orbit r=1, mu in [0.9, 1.1]; "
                    "single orbit; no perturbations",
    predictions=[
        Prediction("P-heldout", "the propagated position on the held-out arc "
                  "(x,y) matches within 1e-6",
                   experiment="predict", observable="x_heldout",
                   kill_condition="held-out |x| deviates from the converged "
                                  "value by more than 1e-6",
                   assumptions=["A-inv"], parameters=["mu"],
                   evidence_grade="numerical", sector="heldout",
                   comparator="kepler"),
    ],
    tests=[
        Test("T-energy", kind="identity", experiment="identity", exact=True,
             description="E and L conserved by symplectic/RK4 integrators"),
        Test("T-ab", kind="comparator", experiment="ab",
             description="RK4 vs leapfrog: separate algorithms, same equations"),
        Test("T-hostile-euler", kind="hostile-control", experiment="hostile_euler",
             description="explicit Euler must drift energy — if it does not, "
                         "the identity check itself is broken"),
    ],
    experiments={
        "identity": _expt_identity,
        "predict": _expt_predict,
        "ab": _expt_ab,
        "hostile_euler": _expt_hostile_euler,
        "kepler": _expt_kepler,
    },
)
