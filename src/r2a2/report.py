"""Report rendering: human tables generated FROM machine-readable results.

Never hand-transcribed (RULES rule 6: computed -> machine-readable output ->
generated tables).
"""

from __future__ import annotations

from .audit import AuditReport
from .ledger import Ledger


def render_audit(theory_id: str, report: AuditReport, ledger: Ledger) -> str:
    lines = []
    bar = "=" * 78
    lines.append(bar)
    lines.append(f"R2A2 AUDIT — {theory_id}")
    lines.append("R2A2 verifies discipline, not truth. PASS here is not a truth claim.")
    lines.append(bar)

    for node_id in ledger.nodes:
        n = ledger.nodes[node_id]
        if n.debt:
            debt = ", ".join(f"{k}={v:+d}" for k, v in sorted(n.debt.items()))
            lines.append(f"  {node_id:40} debt [{debt}] deps={sorted(n.deps)}")

    lines.append("-" * 78)
    lines.append("checks run: " + ", ".join(sorted(set(report.checks_run))))

    if report.warnings:
        lines.append("\nWARNINGS (non-blocking):")
        for w in report.warnings:
            lines.append("  ! " + w)

    if report.blocking:
        lines.append("\nBLOCKING VIOLATIONS:")
        for b in report.blocking:
            lines.append("  X " + b)
        lines.append(f"\nFAIL: {len(report.blocking)} blocking violation(s).")
        lines.append("Note: a FAIL is a discipline failure, not evidence the theory is wrong;")
        lines.append("a PASS is not evidence the theory is right.")
    else:
        lines.append("\nPASS: claims tiered, sourced, falsifiable, acyclic; dependency")
        lines.append("disclosure and refit discipline enforced (discipline, not truth).")

    totals = ledger.total_debt()
    if totals:
        lines.append("\nLABELLED DEBT SUMMARY (canonical object is the graph above; these")
        lines.append("numbers are derived and must never be quoted without their labels):")
        for k in sorted(totals):
            lines.append(f"  {k:24} {totals[k]:+d}")
    return "\n".join(lines)
