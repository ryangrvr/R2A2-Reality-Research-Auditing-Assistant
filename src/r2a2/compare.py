"""Epistemic theory comparison: expose the dimensions, never one winner score.

Compare theories at the epistemic level: what does each assume, import, fit,
leave unresolved, and how did it fare in hostile controls and transfers? The
user inspects *why* one model is more economical or more predictive; R2A2
refuses to collapse that judgment into a single number.
"""

from __future__ import annotations

from typing import Dict

from .api import Theory
from .compiler import compile_theory


def epistemic_profile(theory: Theory) -> Dict[str, object]:
    """Compute the comparable epistemic dimensions of one theory."""
    manifest, ledger = compile_theory(theory)
    manifest.freeze()

    debt = ledger.total_debt()
    commitments = sum(1 for a in theory.assumptions if a.kind == "commitment")
    identifying = [a for a in theory.assumptions if a.kind == "identifying"]

    hostile = [t for t in theory.tests if t.kind == "hostile-control"]
    identities = [t for t in theory.tests if t.kind == "identity"]

    return {
        "theory": theory.id,
        "version": theory.version,
        "free_parameters": sum(
            1 for p in theory.parameters
            if p.kind in ("fitted-parameter", "external-prior")),
        "total_parameters": len(theory.parameters),
        "assumptions": len(theory.assumptions),
        "commitments": commitments,
        "identifying_assumptions": len(identifying),
        "unresolved_identifying": sum(
            1 for a in identifying if not a.text.strip()),
        "imported_constants": debt.get("imported-constant", 0),
        "fitted_parameters": debt.get("fitted-parameter", 0),
        "unproved_lemmas": debt.get("unproved-lemma", 0),
        "comparator_assumptions": debt.get("comparator-assumption", 0),
        "hostile_controls": len(hostile),
        "identity_checks": len(identities),
        "predictions": len(theory.predictions),
        "sectors": sorted({p.sector for p in theory.parameters} |
                          {pred.sector for pred in theory.predictions}),
        "validity_domain": theory.validity_domain or "-",
    }


def compare(theory_a: Theory, theory_b: Theory) -> str:
    """Render the side-by-side epistemic dimensions. No winner is declared."""
    pa, pb = epistemic_profile(theory_a), epistemic_profile(theory_b)
    dims = [k for k in pa if k not in ("theory", "version")]

    lines = ["THEORY COMPARISON (epistemic dimensions — no winner score; "
             "R2A2 exposes, you judge)", ""]
    width = max(len(d) for d in dims) + 2
    lines.append(f"{'dimension':<{width}} {str(pa['theory']):>20} {str(pb['theory']):>20}")
    lines.append("-" * (width + 42))
    for d in dims:
        va, vb = pa[d], pb[d]
        if isinstance(va, list):
            va = ", ".join(map(str, va)) or "-"
        if isinstance(vb, list):
            vb = ", ".join(map(str, vb)) or "-"
        marker = "  <-" if va != vb else ""
        lines.append(f"{d:<{width}} {str(va):>20} {str(vb):>20}{marker}")
    return "\n".join(lines)
