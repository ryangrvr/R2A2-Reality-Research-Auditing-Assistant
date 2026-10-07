"""Example 3: GRUT adapter — the adversarial test of the abstraction.

This is a CLIENT. It imports a small subset of the existing GRUT ledger
machinery (provenance/auditor.py) as-is, without modifying R2A2 core, and
adapts a GRUT claim set into an R2A2 Theory. If this requires a GRUT-specific
conditional inside r2a2 core, the abstraction has failed.

The GRUT sources live one directory up from this repo (the R2A2 workspace).
"""
import os
import sys

from r2a2.api import Theory, Parameter, Prediction

# --- locate the GRUT repo and import its generalized auditor as a client ----
GRUT_ROOT = os.environ.get(
    "GRUT_ROOT",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."),
)
_AUDIT_DIR = os.path.join(GRUT_ROOT, "provenance")
if os.path.isdir(_AUDIT_DIR):
    sys.path.insert(0, _AUDIT_DIR)
    import auditor as grut_auditor  # noqa: E402  (GRUT module, untouched)
else:  # pragma: no cover
    grut_auditor = None


def load_grut_claims():
    """Load GRUT's own claims.json/sources.json and run the original auditor.

    Pure client behavior: no R2A2 core involvement, no GRUT modification.
    """
    if grut_auditor is None:
        raise RuntimeError("GRUT sources not found; set GRUT_ROOT")
    import json
    with open(os.path.join(_AUDIT_DIR, "claims.json")) as f:
        all_claims = json.load(f)["claims"]
    # scope exactly as GRUT's own gate does (validate.py): only nodes in the
    # default 'grut' scope; other scopes use their own vocabulary
    claims = [c for c in all_claims if c.get("ledger_scope", "grut") == "grut"]
    with open(os.path.join(_AUDIT_DIR, "sources.json")) as f:
        sources = json.load(f)
    source_ids = {k for k in sources if not k.startswith("_")}
    result = grut_auditor.audit(claims, source_ids, grut_auditor.DEFAULT_TIERS)
    return claims, source_ids, result


def grut_claims_to_theory(claims, max_claims=5) -> Theory:
    """Adapt GRUT claim nodes into an R2A2 Theory via the public SDK only."""
    claims = claims[:max_claims]
    predictions = []
    for c in claims:
        cid = c.get("id", "claim")
        predictions.append(Prediction(
            id=cid,
            description=c.get("statement", c.get("tier", "GRUT claim")),
            experiment="grut_ledger",
            observable="ledger_delta",
            kill_condition=c.get("overturning_computation") or "unspecified-by-claim",
            assumptions=[],
            parameters=[],
            evidence_grade="numerical",
        ))
    return Theory(
        id="grut-fragment",
        version="0.1.0",
        description="A GRUT claim-set fragment adapted through the public SDK.",
        predictions=predictions,
        tests=[],
        experiments={"grut_ledger": lambda **kw: {"ledger_delta": 0}},
    )


THEORY = Theory(
    id="grut-adapter-placeholder",
    version="0.1.0",
    description="Run load_grut_claims() for the real adapter; this Theory exists "
                "so the module is a valid plugin target.",
    experiments={"noop": lambda: {"ok": True}},
)
