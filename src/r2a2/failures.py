"""Failure taxonomy: three kinds of failure are never conflated.

A researcher seeing FAIL must know whether nature rejected the theory, the
protocol was broken, or the code merely threw an exception.
"""

from __future__ import annotations

from enum import Enum


class FailureKind(str, Enum):
    EXECUTION = "execution-failure"   # solver did not converge, malformed file,
                                      # out of memory, exception in experiment
    PROTOCOL = "protocol-failure"     # holdout opened before freeze, missing
                                      # source, unresolved parameter provenance,
                                      # manifest modified after freeze
    THEORY = "theory-failure"         # a preregistered prediction disagreed
                                      # with the result, or a hostile control fired


class R2A2Error(Exception):
    """Base class: carries which kind of failure this is."""

    kind: FailureKind = FailureKind.EXECUTION


class ExecutionError(R2A2Error):
    kind = FailureKind.EXECUTION


class ProtocolError(R2A2Error):
    kind = FailureKind.PROTOCOL


class TheoryFailure(Exception):
    """Not an error in the software: a scientific result.

    Raised/recorded when a preregistered kill condition fires or a hostile
    control rejects the theory. This is the system working as intended.
    """

    def __init__(self, message: str, prediction_id: str = ""):
        super().__init__(message)
        self.prediction_id = prediction_id
        self.kind = FailureKind.THEORY


def classify(exc: BaseException) -> FailureKind:
    if isinstance(exc, R2A2Error):
        return exc.kind
    if isinstance(exc, TheoryFailure):
        return FailureKind.THEORY
    if isinstance(exc, (KeyError, TypeError, ValueError, AttributeError, RuntimeError)):
        return FailureKind.PROTOCOL if "manifest" in str(exc).lower() else FailureKind.EXECUTION
    return FailureKind.EXECUTION
