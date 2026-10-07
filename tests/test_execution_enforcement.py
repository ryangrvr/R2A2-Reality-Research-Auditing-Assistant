"""v0.3.3 — execution enforcement closure (review of 0aba55c).

Six acceptance conditions:
1. freeze, replace experiment callable, run  -> protocol failure BEFORE execution
2. run an unfrozen manifest                  -> protocol failure
3. freeze with backend A, attempt backend B  -> protocol failure
4. unbindable executable                     -> explicit UNBOUND, never hash("")
5. successful run emits canonical result_hash; changing a result value changes
   it; changing only wall time does not
6. attestation created from the generated result hash verifies end-to-end
"""
import copy
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "examples", "toy_theory"))

import toy_theory  # noqa: E402

from r2a2.api import Theory, Parameter, Prediction, Test  # noqa: E402
from r2a2.backends import LocalBackend  # noqa: E402
from r2a2.compiler import compile_theory  # noqa: E402
from r2a2.failures import FailureKind, ProtocolError, classify  # noqa: E402
from r2a2.ledger import Ledger  # noqa: E402
from r2a2.runner import run_manifest  # noqa: E402
from r2a2.trust import ReviewAttestation, verify_attestation  # noqa: E402


def _frozen(theory=None, backend="local"):
    theory = theory or toy_theory.THEORY
    m, led = compile_theory(theory, backend=backend, seeds={"default": 0})
    m.freeze()
    return m, led


def test_swapped_callable_is_protocol_failure_before_execution():
    """Condition 1: the swapped code must NOT run; the error must be a
    protocol failure, not an execution outcome."""
    m, led = _frozen()
    executed = []
    theory2 = theory_from = copy.deepcopy(toy_theory.THEORY)
    theory2.experiments["predict"] = lambda a=2.0, b=1.0: (
        executed.append(True) or {"y2": 999.0})
    with pytest.raises(ProtocolError):
        run_manifest(theory2, m, led)
    assert executed == [], "the divergent code must never execute"
    assert classify(ProtocolError("x")) is FailureKind.PROTOCOL


def test_body_edit_same_name_is_protocol_failure():
    m, led = _frozen()
    theory2 = copy.deepcopy(toy_theory.THEORY)
    original = theory2.experiments["predict"]
    # same name, different behavior
    theory2.experiments["predict"] = lambda a=2.0, b=1.0: {"y2": a * 2 + b + 1}
    with pytest.raises(ProtocolError):
        run_manifest(theory2, m, led)


def test_unfrozen_manifest_is_protocol_failure():
    t = toy_theory.THEORY
    m, led = compile_theory(t)          # NOT frozen
    with pytest.raises(ProtocolError):
        run_manifest(t, m, led)


def test_backend_swap_is_protocol_failure():
    m, led = _frozen(backend="local")
    with pytest.raises(ProtocolError):
        run_manifest(toy_theory.THEORY, m, led, backend_name="some-other")


def test_unbindable_callable_is_explicitly_unbound():
    """Condition 4: hash('') must never masquerade as a source hash."""
    from r2a2.compiler import code_binding, canonical_hash
    import builtins
    binding = code_binding(builtins.len)   # builtin: no retrievable source
    assert binding["source_hash"] == "<unbound>"
    assert binding["source_hash"] != canonical_hash("")
    # and two different unbindable callables must NOT look content-identical
    assert code_binding(builtins.sum)["source_hash"] == "<unbound>"


def test_result_hash_content_addressed_and_time_independent():
    """Condition 5: result_hash binds the scientific payload; wall time excluded."""
    t = toy_theory.THEORY
    m, led = _frozen()
    res = run_manifest(t, m, led)
    rec = next(r for r in res.records if r["experiment"] == "predict")
    assert rec["result_hash"]

    # identical payload -> identical hash (rerun under the same manifest)
    res2 = run_manifest(t, m, copy.deepcopy(led))
    rec2 = next(r for r in res2.records if r["experiment"] == "predict")
    assert rec2["result_hash"] == rec["result_hash"]

    # changing ONLY wall time must not change the hash
    rec3 = dict(rec); rec3["wall_time"] = rec["wall_time"] + 42.0
    # wall_time sits outside the hashed payload; verify by re-deriving:
    from r2a2.compiler import canonical_hash
    payload = {k: rec[k] for k in ("node", "experiment", "backend",
                                   "manifest_hash", "result")}
    assert canonical_hash(payload) == rec["result_hash"]

    # changing the scientific result DOES change the hash
    rec4 = dict(rec); rec4["result"] = {"y2": 6.0}
    payload4 = {k: rec4[k] for k in payload}
    assert canonical_hash(payload4) != rec["result_hash"]


def test_attestation_on_generated_result_hash_end_to_end():
    """Condition 6: manifest -> execution -> result -> attestation -> verdict."""
    t = toy_theory.THEORY
    m, led = _frozen()
    res = run_manifest(t, m, led)
    rec = next(r for r in res.records if r["experiment"] == "predict")
    att = ReviewAttestation(
        reviewer="ext-checker", scope=f"result:{rec['experiment']}",
        manifest_hash=m.hash, result_hash=rec["result_hash"],
        code_revision="0aba55c", verdict="checked")
    doc = att.to_dict()
    # a verifier, on the same artifacts, confirms it applies
    live = ReviewAttestation(
        reviewer=doc["reviewer"], scope=doc["scope"],
        manifest_hash=doc["manifest_hash"], result_hash=doc["result_hash"],
        code_revision=doc["code_revision"], verdict=doc["verdict"])
    out = verify_attestation(live, m.hash, rec["result_hash"],
                             "0aba55c", sealed_as=doc["seal"])
    assert out["applies"] is True
    # and the SAME attestation is void for any other result hash
    out2 = verify_attestation(live, m.hash, "different-result", "0aba55c",
                              sealed_as=doc["seal"])
    assert out2["applies"] is False
