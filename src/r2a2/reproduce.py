"""Cross-backend reproduction: same frozen manifest → different compute
substrates → declared equivalence rule.

Produces a comparison artifact: manifest hash, backend fingerprints, result
hashes, comparison class, frozen tolerances, agreement verdict, differences.
No backend is automatically the truth/reference unless declared.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .compute import (ComputeProfile, ExecutionContext, ComputeRequest,
                      ReproducibilityRule)
from .failures import ProtocolError
from .schema import stamp


def reproduce(theory, manifest_hash: str, profile: ComputeProfile,
              backends: List,  # List[ComputeBackend]
              experiment: str,
              rule: Optional[ReproducibilityRule] = None,
              reference: Optional[str] = None) -> Dict[str, Any]:
    """Run one frozen experiment on multiple backends and compare.

    rule must be declared BEFORE comparison (frozen tolerances). If the
    profile carries a reproducibility rule, it is used; passing a different
    rule here after seeing disagreement is a protocol violation — the rule
    hash is recorded either way.
    """
    if rule is None:
        rule = profile.reproducibility
    if rule is None:
        raise ProtocolError(
            "no reproducibility rule declared; comparing results without a "
            "frozen rule would let tolerances be chosen after disagreement")

    runs = []
    for backend in backends:
        desc = backend.probe()
        ctx = ExecutionContext(desc, profile, manifest_hash)
        # seed_policy configures the BACKEND's RNG (the request carries it as
        # `seed`); it is never splatted into the theory's experiment args
        seed = (profile.seed_policy or {}).get("seed")
        req = ComputeRequest(experiment=experiment, args={"_theory": theory},
                             seed=seed)
        result = backend.execute(req, ctx)
        runs.append({
            "backend_id": desc.backend_id,
            "fingerprint": result.fingerprint,
            "payload": result.payload,
            "payload_hash": result.payload_hash(),
        })

    # pairwise comparison against the declared reference (or first backend);
    # no backend is automatically truth unless declared
    ref = reference or runs[0]["backend_id"]
    ref_run = next((r for r in runs if r["backend_id"] == ref), None)
    if ref_run is None:
        raise ProtocolError(f"declared reference backend {ref!r} did not run")

    comparisons = []
    all_agree = True
    for run in runs:
        if run["backend_id"] == ref:
            continue
        verdict = rule.check(run["payload"], ref_run["payload"])
        comparisons.append({
            "backend": run["backend_id"],
            "reference": ref,
            "agrees": verdict["agrees"],
            "detail": verdict["detail"],
            "payload_hash": run["payload_hash"],
        })
        all_agree = all_agree and verdict["agrees"]

    return stamp({
        "manifest_hash": manifest_hash,
        "experiment": experiment,
        "reproducibility_rule": rule.to_dict(),
        "rule_hash": rule.hash(),
        "reference_backend": ref,
        "runs": runs,
        "comparisons": comparisons,
        "agreement": "AGREE" if all_agree else
                     "DISAGREE (scientific/reproducibility finding — not "
                     "automatically a software crash)",
        "note": "cross-backend disagreement beyond the frozen rule is a "
                "scientific finding, recorded as such; it is never silently "
                "hidden by loosening tolerances",
    })
