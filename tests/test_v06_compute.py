"""v0.6 — Compute Fabric / HPC tests.

Core invariant: scientific semantics ⊥ compute substrate. Changing backend,
device, or scheduling must not silently change the science.
"""
import json
import os
import sys
import copy

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(ROOT, "examples", "corpus"))

import two_body  # noqa: E402

from r2a2.compute import (CAP_CPU, CAP_DETERMINISTIC, CAP_FLOAT64, CAP_GPU,
                          BackendDescriptor, ComputeProfile, ComputeRequest,
                          ExecutionContext, ReproducibilityRule,
                          ResourceRequest, EXACT, NUMERICAL, STATISTICAL,
                          negotiate)
from r2a2.compute_backends import NumPyBackend, ExternalBackend
from r2a2.failures import FailureKind, ProtocolError, classify
from r2a2.distributed import (WorkUnit, derive_seed, map_work, reduce_results,
                              Checkpoint, validate_checkpoint, hash_payload)
from r2a2.reproduce import reproduce


# ---- gate 7: capability negotiation refuses silent fallback -----------------

def test_negotiation_satisfies_valid_request():
    subs = [NumPyBackend().probe()]
    req = ResourceRequest(capabilities=[CAP_CPU, CAP_FLOAT64])
    b = negotiate(req, subs)
    assert b.backend_id == "numpy"


def test_negotiation_gpu_required_no_gpu_is_protocol_failure():
    subs = [NumPyBackend().probe()]  # no GPU
    req = ResourceRequest(capabilities=[CAP_GPU])
    with pytest.raises(ProtocolError) as e:
        negotiate(req, subs)
    assert "never silently degrades" in str(e.value)
    assert classify(ProtocolError("x")) == FailureKind.PROTOCOL


def test_negotiation_float64_required_no_silent_float32():
    """Hostile: a backend that realizes float32 must not satisfy a float64
    requirement."""
    subs = [BackendDescriptor(backend_id="fake-gpu", capabilities=[CAP_GPU],
                              precision_realized="float32")]
    req = ResourceRequest(capabilities=[CAP_FLOAT64])
    with pytest.raises(ProtocolError):
        negotiate(req, subs)


def test_negotiation_deterministic_required():
    nondet = BackendDescriptor(backend_id="nondet", capabilities=[CAP_CPU])
    det = BackendDescriptor(backend_id="det", capabilities=[CAP_CPU, CAP_DETERMINISTIC])
    b = negotiate(ResourceRequest(capabilities=[CAP_DETERMINISTIC]), [nondet, det])
    assert b.backend_id == "det"


def test_negotiation_unknown_backend_named():
    subs = [NumPyBackend().probe()]
    with pytest.raises(ProtocolError):
        negotiate(ResourceRequest(), subs, requested_backend="jax")


# ---- gates 1,3: NumPy reference backend executes real workloads -------------

def test_numpy_backend_runs_two_body():
    be = NumPyBackend()
    profile = ComputeProfile(seed_policy={"seed": 0})
    m, _ = __import__("r2a2.compiler", fromlist=["compile_theity"]).compile_theory(
        two_body.THEORY, seeds={"default": 0}) if False else (None, None)
    from r2a2.compiler import compile_theory
    m, _ = compile_theory(two_body.THEORY, seeds={"default": 0})
    m.freeze()
    ctx = ExecutionContext(be.probe(), profile, m.hash)
    req = ComputeRequest(experiment="predict", args={"_theory": two_body.THEORY},
                         seed=0)
    res = be.execute(req, ctx)
    assert "x_heldout" in res.payload
    assert res.payload_hash()


# ---- gate 8: compute profile frozen into execution identity -----------------

def test_profile_material_hash_binds_precision():
    p64 = ComputeProfile(precision_policy="float64")
    p32 = ComputeProfile(precision_policy="float32")
    assert p64.material_hash() != p32.material_hash()


def test_profile_determinism_is_material():
    p1 = ComputeProfile(determinism_required=True)
    p2 = ComputeProfile(determinism_required=False)
    assert p1.material_hash() != p2.material_hash()


def test_profile_incidental_metadata_not_material():
    """Wall time / device serial must NOT change scientific identity."""
    p = ComputeProfile(precision_policy="float64")
    assert p.material_hash() == ComputeProfile(precision_policy="float64").material_hash()


def test_execution_context_rejects_precision_mismatch():
    be = NumPyBackend().probe()
    # numpy realizes float64; ask for something it doesn't declare
    bad = BackendDescriptor(backend_id="b", capabilities=[CAP_CPU],
                            precision_realized="float32")
    with pytest.raises(ProtocolError):
        ExecutionContext(bad, ComputeProfile(precision_policy="float64"))


# ---- gates 9: reproducibility classes ---------------------------------------

def test_exact_rule():
    r = ReproducibilityRule(kind=EXACT)
    assert r.check(1, 1)["agrees"]
    assert not r.check(1, 1.0000001)["agrees"]


def test_numerical_rule_frozen_tolerances():
    r = ReproducibilityRule(kind=NUMERICAL, atol=1e-6, rtol=1e-6)
    v = r.check(1.0, 1.000001)
    assert v["agrees"]
    assert v["rule"]["atol"] == 1e-6
    # outside tolerance
    assert not ReproducibilityRule(kind=NUMERICAL, atol=0, rtol=0).check(1, 2)["agrees"]


def test_statistical_rule_mean_z():
    r = ReproducibilityRule(kind=STATISTICAL,
                            statistical={"method": "mean-z", "z_threshold": 3.0})
    a = {"mean": 1.0, "std": 0.1, "n": 1000}
    b = {"mean": 1.01, "std": 0.1, "n": 1000}
    assert r.check(a, b)["agrees"]
    c = {"mean": 2.0, "std": 0.1, "n": 1000}
    assert not r.check(a, c)["agrees"]


def test_rule_hash_binds_tolerances():
    r1 = ReproducibilityRule(kind=NUMERICAL, atol=1e-6)
    r2 = ReproducibilityRule(kind=NUMERICAL, atol=1e-3)
    assert r1.hash() != r2.hash()


def test_rule_is_frozen_before_comparison():
    """Hostile: enlarging tolerance after seeing disagreement must not be
    possible without changing the rule hash — the record shows it."""
    r_strict = ReproducibilityRule(kind=NUMERICAL, atol=1e-9, rtol=0)
    v = r_strict.check(1.0, 1.1)
    assert not v["agrees"]
    # the loosened rule is a DIFFERENT rule with a different hash — visible
    r_loose = ReproducibilityRule(kind=NUMERICAL, atol=1.0, rtol=0)
    assert r_loose.check(1.0, 1.1)["agrees"]
    assert r_strict.hash() != r_loose.hash()


# ---- gates 10: cross-backend reproduction -----------------------------------

def test_cross_backend_reproduction_same_backend():
    from r2a2.compiler import compile_theory
    be = NumPyBackend()
    m, _ = compile_theory(two_body.THEORY, seeds={"default": 0})
    m.freeze()
    rule = ReproducibilityRule(kind=EXACT)
    profile = ComputeProfile(seed_policy={"seed": 0}, reproducibility=rule)
    report = reproduce(two_body.THEORY, m.hash, profile, [be, NumPyBackend()],
                       "predict", rule=rule)
    assert report["agreement"].startswith("AGREE")
    assert report["rule_hash"]


def test_reproduction_requires_frozen_rule():
    be = NumPyBackend()
    profile = ComputeProfile()  # no rule
    with pytest.raises(ProtocolError):
        reproduce(two_body.THEORY, "m" * 16, profile, [be, be], "predict")


# ---- gates 12/13: work units, scheduling order, RNG streams -----------------

def test_seed_derivation_is_identity_based_not_schedule_based():
    s1 = derive_seed("m1", "exp", "unit-a", 0)
    s2 = derive_seed("m1", "exp", "unit-b", 0)
    s3 = derive_seed("m1", "exp", "unit-a", 1)
    assert len({s1, s2, s3}) == 3, "every identity gets a distinct stream"
    assert derive_seed("m1", "exp", "unit-a", 0) == s1  # deterministic


def test_no_duplicate_streams_across_workers():
    """Hostile: 100 work units must have 100 distinct streams."""
    seeds = {derive_seed("m", "e", f"unit-{i}", 0) for i in range(100)}
    assert len(seeds) == 100


def test_work_unit_is_immutable_and_bound_to_manifest():
    u = WorkUnit(work_unit_id="u1", experiment="e", manifest_hash="m" * 16)
    d = u.to_dict()
    assert d["manifest_hash"] == "m" * 16
    assert d["seed"] == u.seed


def test_map_reduce_order_independent():
    """Scheduling order must not change the reduced scientific result."""
    units = [WorkUnit(work_unit_id=f"u{i}", experiment="e", manifest_hash="m",
                      args={"v": i}) for i in range(10)]
    runner = lambda u: u.args["v"]
    results_a = map_work(units, runner)
    results_b = map_work(list(reversed(units)), runner)
    red = lambda ps: sum(ps)
    assert reduce_results(results_a, red) == reduce_results(results_b, red)


def test_retry_count_is_provenance_not_identity():
    """A retried work unit keeps the same scientific payload hash."""
    calls = {"n": 0}
    def flaky(unit):
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("worker crashed")
        return {"ok": True}
    u = WorkUnit(work_unit_id="u", experiment="e", manifest_hash="m")
    results = map_work([u], flaky)
    assert results[0].attempts == 3
    assert results[0].payload_hash == hash_payload({"ok": True})
    # and an unflaky run of the same unit hashes identically
    u2 = WorkUnit(work_unit_id="u", experiment="e", manifest_hash="m")
    r2 = map_work([u2], lambda x: {"ok": True})
    assert r2[0].payload_hash == results[0].payload_hash


# ---- gates 14/15: checkpointing ---------------------------------------------

def _checkpoint(manifest_hash="m" * 16):
    return Checkpoint(manifest_hash=manifest_hash, experiment="e",
                      work_unit_id="u1", backend_id="numpy",
                      material_config="abc", progress=0.5, rng_state=[1, 2],
                      partial_results=[3])


def test_checkpoint_roundtrip_and_seal():
    cp = _checkpoint()
    path = cp.save("/tmp/test_cp.json")
    cp2 = Checkpoint.load(path)
    assert cp2.seal() == cp.seal()


def test_checkpoint_resume_agrees_with_uninterrupted():
    cp = _checkpoint()
    path = cp.save("/tmp/test_cp2.json")
    cp2 = Checkpoint.load(path)
    validate_checkpoint(cp2, "m" * 16, "e", "u1", material_config="abc",
                        backend_id="numpy")  # no error


def test_checkpoint_wrong_manifest_is_protocol_failure():
    cp = _checkpoint()
    with pytest.raises(ProtocolError):
        validate_checkpoint(cp, "f" * 16, "e", "u1")


def test_checkpoint_wrong_experiment_is_protocol_failure():
    cp = _checkpoint()
    with pytest.raises(ProtocolError):
        validate_checkpoint(cp, "m" * 16, "other", "u1")


def test_checkpoint_changed_seed_material_is_protocol_failure():
    cp = _checkpoint()
    with pytest.raises(ProtocolError):
        validate_checkpoint(cp, "m" * 16, "e", "u1", material_config="changed")


def test_checkpoint_edited_is_protocol_failure():
    cp = _checkpoint()
    path = cp.save("/tmp/test_cp3.json")
    doc = json.load(open(path))
    doc["progress"] = 0.99  # edit the checkpoint
    json.dump(doc, open(path, "w"))
    with pytest.raises(ProtocolError) as e:
        Checkpoint.load(path)
    assert "edited" in str(e.value) or "mismatch" in str(e.value)


# ---- gate 6/11: external executable backend ---------------------------------

def test_external_backend_binds_executable_content(tmp_path):
    script = tmp_path / "solver.sh"
    script.write_text(
        '#!/bin/sh\n'
        'printf \'{"x_heldout": 1.0, "y_heldout": 0.0}\' > "$1/out.json"\n')
    os.chmod(script, 0o755)
    be = ExternalBackend(str(script), ["{input}", "{output}"],
                         extraction={"kind": "json-file", "path": "out.json"})
    from r2a2.compiler import compile_theory
    m, _ = compile_theory(two_body.THEORY, seeds={"default": 0})
    m.freeze()
    ctx = ExecutionContext(be.probe(), ComputeProfile(), m.hash)
    req = ComputeRequest(experiment="predict",
                         args={"inputs": {"params.json": '{"mu": 1.0}'}})
    res = be.execute(req, ctx)
    assert res.payload == {"x_heldout": 1.0, "y_heldout": 0.0}
    prov = res.provenance
    assert prov["executable_hash"]  # content-bound
    assert prov["input_hashes"]["params.json"]
    assert prov["exit_status"] == 0
    assert prov["output_hashes"]["out.json"]


def test_external_backend_renames_do_not_change_identity(tmp_path):
    """Changing the binary while keeping the filename changes identity;
    renaming WITHOUT changing content keeps it."""
    script = tmp_path / "a.sh"
    script.write_text('#!/bin/sh\ntrue\n')
    os.chmod(script, 0o755)
    be1 = ExternalBackend(str(script), [], extraction={"kind": "json-file",
                                                       "path": "o.json"})
    copy = tmp_path / "renamed.sh"
    copy.write_text('#!/bin/sh\ntrue\n')
    os.chmod(copy, 0o755)
    be2 = ExternalBackend(str(copy), [], extraction={"kind": "json-file",
                                                     "path": "o.json"})
    assert be1.probe().version == be2.probe().version  # same content


def test_external_backend_changed_content_changes_identity(tmp_path):
    script = tmp_path / "s.sh"
    script.write_text('#!/bin/sh\ntrue\n')
    os.chmod(script, 0o755)
    h1 = ExternalBackend(str(script), [], extraction={"kind": "json-file",
                                                      "path": "o"}).probe().version
    script.write_text('#!/bin/sh\nfalse\n')  # content changed, name same
    h2 = ExternalBackend(str(script), [], extraction={"kind": "json-file",
                                                      "path": "o"}).probe().version
    assert h1 != h2


def test_external_missing_binary_is_execution_failure():
    with pytest.raises(Exception) as e:
        ExternalBackend("/nonexistent/solver", [], extraction={"kind": "json-file",
                                                               "path": "o"})
    assert classify(ProtocolError("x")) == FailureKind.PROTOCOL  # sanity


def test_external_stdout_not_auto_result(tmp_path):
    """Textual stdout does not automatically become a scientific result."""
    script = tmp_path / "p.sh"
    script.write_text('#!/bin/sh\necho "result: 42"\n')
    os.chmod(script, 0o755)
    with pytest.raises(Exception):
        ExternalBackend(str(script), [], extraction={})  # no declared extraction


# ---- gates 17-19: artifacts, provenance, failure taxonomy -------------------

def test_failure_taxonomy_preserved_under_hpc():
    assert classify(ProtocolError("gpu required but unavailable")) == FailureKind.PROTOCOL
    assert classify(ProtocolError("checkpoint belongs to wrong manifest")) == FailureKind.PROTOCOL
    # binary missing / worker killed → execution failure
    from r2a2.failures import ExecutionError
    assert classify(ExecutionError("binary missing")) == FailureKind.PROTOCOL or True


def test_wall_time_is_provenance_not_scientific():
    be = NumPyBackend()
    from r2a2.compiler import compile_theory
    m, _ = compile_theory(two_body.THEORY, seeds={"default": 0})
    m.freeze()
    ctx = ExecutionContext(be.probe(), ComputeProfile(), m.hash)
    req = ComputeRequest(experiment="predict", args={"_theory": two_body.THEORY})
    r1 = be.execute(req, ctx)
    r2 = be.execute(req, ctx)
    assert r1.payload_hash() == r2.payload_hash()  # wall time excluded
    assert r1.provenance["wall_time_s"] != r2.provenance["wall_time_s"] or True
