"""Verdict and evidence-grade vocabulary.

Never a single PASS/FAIL. A successful run means the test protocol executed
correctly, not that the theory is true.
"""

from __future__ import annotations

# per-test outcomes (GRUT short-ladder outcomes)
TEST_OUTCOMES = ("KILL", "BANK", "EXTEND")

# claim verdicts
VERDICTS = (
    "structural-validation",
    "computational-reproduction",
    "numerical-evidence",
    "formal-result",
    "proved-theorem",
    "empirical-confirmation",
    "conditional-result",
    "null-result",
    "killed-hypothesis",
    "unresolved-identification",
)

# statuses that are *claims about the answer being in the input* (RULES 1)
RELOCATED = "RELOCATED"
RESTATED = "RESTATED"

# external review status (generalized CHECKS.md)
REVIEW_STATUSES = ("pending", "checked", "issue-found")


def is_falsifiable(kill_condition: str) -> bool:
    return bool(kill_condition and kill_condition.strip())
