"""Failure taxonomy: three kinds of failure are never conflated."""
import pytest

from r2a2.failures import (FailureKind, classify, ExecutionError,
                            ProtocolError, TheoryFailure)


def test_kinds_distinct():
    assert FailureKind.EXECUTION != FailureKind.PROTOCOL != FailureKind.THEORY
    assert FailureKind.THEORY != FailureKind.EXECUTION


def test_classify():
    assert classify(ExecutionError("OOM")) is FailureKind.EXECUTION
    assert classify(ProtocolError("holdout opened before freeze")) is FailureKind.PROTOCOL
    assert classify(ZeroDivisionError("boom")) is FailureKind.EXECUTION
    assert classify(RuntimeError("manifest is frozen")) is FailureKind.PROTOCOL


def test_theory_failure_is_a_result_not_a_crash():
    tf = TheoryFailure("kill condition fired", prediction_id="P1")
    assert classify(tf) is FailureKind.THEORY
    assert tf.prediction_id == "P1"
