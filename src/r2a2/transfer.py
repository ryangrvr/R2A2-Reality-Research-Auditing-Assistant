"""Cross-sector parameter transfer: R2A2's signature feature.

The discipline, generalised from GRUT methodology:

1. parameters determined/calibrated in sector A;
2. frozen (commitment recorded);
3. sector-B prediction executed WITHOUT refitting;
4. any new B-specific parameter explicitly surfaced and priced.

A transfer record is the auditable artifact. A purported cross-sector
prediction is flagged when a parameter has been silently retuned, or when a
target-sector parameter entered the calibration set.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class FrozenParameter:
    """A parameter frozen at the end of a calibration sector."""

    name: str
    sector: str
    value: object
    source: str = ""
    manifest_hash: str = ""      # hash of the calibration manifest that fixed it


@dataclass
class SectorDemand:
    """What a target sector says it needs, and where it claims each came from."""

    sector: str
    required: List[str] = field(default_factory=list)          # parameter names
    introduced: List[str] = field(default_factory=list)        # declared NEW here
    calibration_data_overlap: List[str] = field(default_factory=list)  # dataset ids


@dataclass
class TransferVerdict:
    outcome: str                                   # "PASS" | "FAIL"
    lines: List[dict] = field(default_factory=list) # per-parameter audit lines
    reasons: List[str] = field(default_factory=list)

    def render(self, from_sector: str, to_sector: str) -> str:
        out = ["TRANSFER AUDIT", f"  sector: {from_sector} -> {to_sector}"]
        for ln in self.lines:
            out.append(f"  {ln['name']:10} {ln['status']:26} {ln['note']}")
        out.append(f"Cross-sector status: {self.outcome}")
        for r in self.reasons:
            out.append(f"Reason: {r}")
        if self.outcome == "PASS" and not self.reasons:
            out.append("No transferred parameter was refit.")
            out.append("No target-sector data entered calibration.")
        return "\n".join(out)


def audit_transfer(frozen: Dict[str, FrozenParameter],
                   demand: SectorDemand,
                   refit: Dict[str, str] | None = None) -> TransferVerdict:
    """Check that a target sector's predictions are genuinely transferred.

    frozen:    parameters frozen in the calibration sector(s)
    demand:    the target sector's declared requirements
    refit:     parameter name -> sector where it was (re)fit; absent = not refit
    """
    refit = refit or {}
    v = TransferVerdict(outcome="PASS")

    for name in demand.required:
        inherited = name in frozen
        was_refit = name in refit
        declared_new = name in demand.introduced
        if inherited and not was_refit:
            v.lines.append({"name": name, "status": "FROZEN",
                            "note": f"inherited from sector:{frozen[name].sector}"})
        elif inherited and was_refit:
            # a refit is legal only if DECLARED as a new sector input, priced
            if declared_new:
                v.lines.append({"name": name, "status": "REFIT (declared)",
                                "note": f"re-fitted in {demand.sector}; priced sector input"})
            else:
                v.outcome = "FAIL"
                v.reasons.append(
                    f"{name} was silently refit in sector {demand.sector!r}; "
                    "the cross-sector claim does not hold")
                v.lines.append({"name": name, "status": "SILENT REFIT",
                                "note": f"re-fitted in {demand.sector} without declaration"})
        elif declared_new:
            v.outcome = "FAIL"
            v.reasons.append(
                f"{name} is NEW IN SECTOR {demand.sector!r} -> the cross-sector "
                "claim requires one unpriced sector-specific parameter")
            v.lines.append({"name": name, "status": "NEW INPUT",
                            "note": f"introduced in {demand.sector}"})
        else:
            v.outcome = "FAIL"
            v.reasons.append(f"{name} has no provenance: not frozen, not declared new")
            v.lines.append({"name": name, "status": "UNRESOLVED",
                            "note": "missing provenance"})

    # calibration/target data overlap destroys out-of-sample status
    if demand.calibration_data_overlap:
        for d in demand.calibration_data_overlap:
            v.outcome = "FAIL"
            v.reasons.append(
                f"dataset {d!r} overlaps the calibration set; the sector-{demand.sector} "
                "prediction is not out-of-sample")
    return v
