"""Audit rules: generalized from the GRU provenance auditor.

The original auditor (tiered / sourced / falsifiable / not laundered) checked a
flat list of claims. Here the same discipline is applied to the dependency
graph, so it can additionally catch what the blind sum could not: circular
dependencies, double-counted inputs, silent re-fits across sectors, and
validity claims exceeding their evidence domain.

It verifies **discipline, not truth**: a wrong-but-well-provenanced theory
passes, and nothing here certifies physical correctness.
"""

from __future__ import annotations

from typing import List

from .api import EVIDENCE_GRADES, Theory
from .ledger import Ledger

# A "derived" claim that introduces new inputs is laundering, unless the extra
# input is declared as an explicit stance (generalized GRU laundering_ok rule).
LAUNDERABLE = ("derived", "shown")


class AuditReport:
    def __init__(self) -> None:
        self.blocking: List[str] = []
        self.warnings: List[str] = []
        self.checks_run: List[str] = []

    @property
    def ok(self) -> bool:
        return not self.blocking

    def block(self, msg: str) -> None:
        self.blocking.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)


def audit_theory(theory: Theory, ledger: Ledger) -> AuditReport:
    """Audit a compiled theory against its ledger. Pure: no I/O."""
    report = AuditReport()

    # --- the four original disciplines (tiered, sourced, falsifiable, not
    # laundered), graph-flavored -----------------------------------------
    for pred in theory.predictions:
        pid = f"{theory.id}/{pred.id}"
        report.checks_run.append("tiered")
        if pred.evidence_grade not in EVIDENCE_GRADES:
            report.block(f"{pid}: invalid evidence grade {pred.evidence_grade!r}")
        report.checks_run.append("sourced")
        if pred.evidence_grade in ("theorem", "formal") and not pred.assumptions:
            report.warn(f"{pid}: claims grade {pred.evidence_grade!r} with no declared assumptions")
        report.checks_run.append("falsifiable")
        if not pred.kill_condition:
            report.block(f"{pid}: NO kill condition (nothing could kill it)")
        for a in pred.assumptions:
            if a not in {x.id for x in theory.assumptions}:
                report.block(f"{pid}: unknown assumption {a!r}")

    # --- graph-level disciplines (new, impossible in the flat auditor) ----
    report.checks_run.append("acyclic")
    for cycle in ledger.find_cycles():
        report.block("circular dependency: " + " -> ".join(cycle + [cycle[0]]))

    report.checks_run.append("unsupported")
    for node in ledger.nodes.values():
        if node.kind == "claim" and not node.deps:
            report.block(f"{node.id}: unsupported claim (no dependencies)")

    report.checks_run.append("double-count")
    # a source node feeding two different claims of the same theory as if they
    # were independent evidence
    feed_counts: dict = {}
    for node in ledger.nodes.values():
        for d in node.deps:
            if ledger.nodes[d].kind == "source":
                feed_counts.setdefault(d, set()).add(node.id)
    for src, users in feed_counts.items():
        if len(users) > 1:
            report.warn(
                f"source {src!r} feeds {len(users)} claims {sorted(users)}; "
                "if treated as independent evidence this is a double count"
            )

    report.checks_run.append("dependency-disclosure")
    for node in ledger.nodes.values():
        stance = node.attrs.get("stance_justification", "")
        extra = node.attrs.get("new_inputs", 0)
        if node.attrs.get("claim_kind") in LAUNDERABLE and extra and not stance:
            report.block(
                f"{node.id}: PROVENANCE VIOLATION - a {node.attrs.get('claim_kind')!r} result "
                f"introduces {extra} undeclared new input(s); declare them (or record a "
                "stance_justification for the assumption introduction)"
            )

    report.checks_run.append("silent-refit")
    for node in ledger.nodes.values():
        if node.attrs.get("refit") and not node.attrs.get("refit_declared"):
            report.block(
                f"{node.id}: UNDECLARED REFIT - parameter was re-fitted outside its original "
                "sector without a declared transfer record"
            )

    report.checks_run.append("validity-domain")
    for node in ledger.nodes.values():
        claimed = node.attrs.get("validity_domain")
        supported = node.attrs.get("supported_domain")
        if claimed and supported and claimed != supported:
            report.warn(
                f"{node.id}: stated validity domain {claimed!r} exceeds supported {supported!r}"
            )

    report.checks_run.append("no-missing-controls")
    has_hostile = any(t.kind == "hostile-control" for t in theory.tests)
    has_identity = any(t.kind == "identity" for t in theory.tests)
    if theory.predictions and not has_hostile:
        report.warn("no hostile control defined for the theory's predictions")
    if any(t.experiment for t in theory.tests) and not has_identity:
        report.warn("no exact identity / conservation-law control defined")

    return report
