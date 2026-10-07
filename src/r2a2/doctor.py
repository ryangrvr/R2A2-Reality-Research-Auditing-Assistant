"""Project scaffolding and the `doctor` diagnostic.

The ontology teaches itself through diagnostics: `doctor` explains missing or
malformed concepts in plain scientific language, never bare validation codes.

Three output categories:
- BLOCKING           — the project cannot compile/run/audit until fixed
- SCIENTIFIC WARNING — a methodological concern, not a software failure
- INFORMATIONAL      — context the author should know
"""

from __future__ import annotations

from typing import List, Tuple

from .api import Theory
from .compiler import code_binding
from .schema import SCHEMA_VERSION

BLOCKING, WARNING, INFO = "BLOCKING", "SCIENTIFIC WARNING", "INFORMATIONAL"


def run_doctor(theory: Theory) -> list:
    """Full diagnostic pass over a theory. Returns (category, message) pairs."""
    out: list = []

    # --- structural validation (schema level) ---
    for problem in theory.validate():
        out.append((BLOCKING, _humanize_validation(theory, problem)))

    # --- kill conditions ---
    for pred in theory.predictions:
        if not pred.kill_condition.strip():
            out.append((BLOCKING,
                f"Prediction {pred.id} states no kill condition. A prediction "
                "that cannot be wrong is not testable — describe the observed "
                "result that would falsify it."))
        if pred.evidence_grade == "theorem" and not pred.assumptions:
            out.append((WARNING,
                f"Prediction {pred.id} claims grade 'theorem' but lists no "
                "assumptions. Theorems follow from stated premises; list them "
                "or lower the grade."))
        if pred.comparator is None:
            out.append((INFO,
                f"Prediction {pred.id} declares no comparator. If it claims "
                "superiority over an existing model, add comparator: <id>; "
                "otherwise no novelty claim is implied."))

    # --- provenance ---
    for p in theory.parameters:
        if p.kind in ("fitted-parameter", "imported-constant") and not p.source:
            out.append((BLOCKING,
                f"Parameter {p.name} was fitted or imported but names no "
                "source. State where its value came from (dataset, literature "
                "constant, prior) so its provenance is auditable."))
        if p.kind == "fitted-parameter" and p.sector == "default":
            out.append((WARNING,
                f"Fitted parameter {p.name} has no sector. Which data fitted "
                "it — and is it the same data that will test the prediction?"))

    # --- controls ---
    if theory.predictions and not any(t.kind == "hostile-control" for t in theory.tests):
        out.append((WARNING,
            "No hostile control is defined. A hostile control is a test "
            "designed to fail if a confounder could explain the prediction; "
            "without one, a pass does not discriminate your theory from rivals."))
    if theory.tests and not any(t.kind == "identity" for t in theory.tests):
        out.append((INFO,
            "No exact identity or conservation-law check is defined. An "
            "exact check verifies the numerical pipeline itself, separately "
            "from the physics."))

    # --- code bindings ---
    for name, fn in theory.experiments.items():
        binding = code_binding(fn)
        if binding["source_hash"] == "<unbound>":
            out.append((WARNING,
                f"Experiment {name} could not be bound to source code "
                "(built-in or extension function). Define it as a named "
                "function in an importable module so its code can be hashed."))
    unnamed = [name for name, fn in theory.experiments.items()
               if getattr(fn, "__name__", "<lambda>") == "<lambda>"]
    for name in unnamed:
        out.append((BLOCKING,
            f"Experiment {name} is a lambda. Lambdas cannot be referenced or "
            "hash-bound — define it as a named function."))

    # --- transfer readiness ---
    fitted = [p for p in theory.parameters if p.kind == "fitted-parameter"]
    sectors = {p.sector for p in theory.parameters} | {pr.sector for pr in theory.predictions}
    if fitted and len(sectors) > 1:
        out.append((INFO,
            "Multiple sectors with fitted parameters detected. For a "
            "cross-sector prediction claim, run 'r2a2 transfer' to verify no "
            "parameter was refit in the target sector."))

    # --- schema compatibility ---
    out.append((INFO, f"Project validated against r2a2_schema {SCHEMA_VERSION}."))

    # sort: BLOCKING, WARNING, INFO
    order = {BLOCKING: 0, WARNING: 1, INFO: 2}
    return sorted(out, key=lambda x: order.get(x[0], 3))


def _humanize_validation(theory: Theory, problem: str) -> str:
    """Translate structural validation codes into plain scientific language."""
    if "unknown experiment" in problem:
        exp = problem.split("'")[1] if "'" in problem else "?"
        return (f"{problem}. The experiment '{exp}' is referenced but not "
                "defined. Add it to the theory's experiments so the "
                "prediction can actually be computed.")
    if "unknown assumption" in problem:
        a = problem.split("'")[1] if "'" in problem else "?"
        return (f"{problem}. The prediction relies on assumption '{a}' which "
                "is not declared. Declare it (with pricing if it is a "
                "commitment) or remove it from the prediction.")
    if "unknown parameter" in problem:
        p = problem.split("'")[1] if "'" in problem else "?"
        return (f"{problem}. The prediction uses parameter '{p}' which is not "
                "declared. Declare it with its provenance kind and source.")
    if "no sector" in problem:
        return (f"{problem}. A fitted parameter must name the sector whose "
                "data fitted it; otherwise fitted and tested data cannot be "
                "told apart.")
    return problem + " (structural validation failed)"
