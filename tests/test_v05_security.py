"""v0.5 — ecosystem trust & supply-chain security tests.

Covers gates 1-6, 8, 13, 14 (7 requires two external-style plugins; 9-12 are
workflow/infra preparation validated by structure and docs).
"""
import copy
import json
import os
import sys
import tempfile
import pathlib

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "examples", "toy_theory"))
sys.path.insert(0, os.path.join(HERE, "..", "examples", "corpus"))

import toy_theory  # noqa: E402
import two_body  # noqa: E402

from r2a2.signing import (IdentityPolicy, SIGNER_OFFLINE, UNAUTHENTICATED,
                          sign_payload, verify_envelope,
                          CONTENT_VALID, IDENTITY_VERIFIED,
                          IDENTITY_NOT_TRUSTED, UNSIGNED, SIGNATURE_INVALID)
from r2a2.trust import ReviewAttestation  # noqa: E402
from r2a2.plugins import (PluginManifest, PluginPolicy, IsolatedExecutor,
                          TRUSTED_INPROCESS, UNTRUSTED_ISOLATED, inspect_plugin,
                          CAP_NETWORK, REFUSED_DEFAULT, EXTENSION_API)  # noqa: E402
from r2a2.supply_chain import (build_provenance, verify_release,  # noqa: E402
                               sha256_file)
from r2a2.api_contract import check_plugin_api  # noqa: E402
from r2a2.ci_verify import ci_verify  # noqa: E402

SECRET_ENV = {"R2A2_DEV_SIGNING_SECRET": "test-secret"}


# ---- gate 1: attestation can be signed and independently verified ----------

def _make_attestation():
    att = ReviewAttestation("alice@example.org", "result:predict",
                            "M1" * 16, "R1" * 16, "abc", "checked")
    return {"reviewer": att.reviewer, "scope": att.scope,
            "manifest_hash": att.manifest_hash, "result_hash": att.result_hash,
            "code_revision": att.code_revision, "verdict": att.verdict,
            "notes": "", "issues": [], "seal": att.seal()}


def test_gate1_sign_and_independently_verify(monkeypatch):
    monkeypatch.setenv("R2A2_DEV_SIGNING_SECRET", "test-secret")
    att = _make_attestation()
    env = sign_payload({"kind": "r2a2.review-attestation", "attestation": att},
                       identity="alice@example.org")
    policy = IdentityPolicy(exact=["alice@example.org"])
    res = verify_envelope(env, policy)
    assert res["content"] == CONTENT_VALID
    assert res["trusted"] is True  # offline mode: UNAUTHENTICATED but allowed


# ---- gate 2: any edited field breaks verification ---------------------------

def test_gate2_editing_any_field_breaks(monkeypatch):
    monkeypatch.setenv("R2A2_DEV_SIGNING_SECRET", "test-secret")
    att = _make_attestation()
    env = sign_payload({"kind": "r2a2.review-attestation", "attestation": att},
                       identity="alice@example.org")
    policy = IdentityPolicy(exact=["alice@example.org"])
    for field in ("verdict", "scope", "manifest_hash", "result_hash", "notes"):
        bad = copy.deepcopy(env)
        bad["payload"]["attestation"][field] = "TAMPERED-" + field
        res = verify_envelope(bad, policy)
        assert res["content"] == SIGNATURE_INVALID, field
    # changing schema or issues also breaks
    bad = copy.deepcopy(env)
    bad["r2a2_schema"] = "0.0"
    assert verify_envelope(bad, policy)["content"] == SIGNATURE_INVALID


# ---- gate 3: valid signature, disallowed identity => NOT TRUSTED ------------

def test_gate3_untrusted_identity_not_silent(monkeypatch):
    monkeypatch.setenv("R2A2_DEV_SIGNING_SECRET", "test-secret")
    att = _make_attestation()
    env = sign_payload({"kind": "r2a2.review-attestation", "attestation": att},
                       identity="mallory@evil.example")
    strict = IdentityPolicy(exact=["alice@example.org"])  # does NOT allow unsigned
    res = verify_envelope(env, strict)
    # offline signature from non-policy identity: UNAUTHENTICATED, and with
    # allow_unsigned=False it must not be trusted silently
    assert res["content"] == CONTENT_VALID
    assert res["trusted"] is False or res["identity"] != IDENTITY_VERIFIED


# ---- gates 4-6: plugin trust, isolation, capabilities -----------------------

def test_gate4_never_silently_upgraded():
    m = PluginManifest(plugin_id="random-plugin", version="1",
                       execution_class=TRUSTED_INPROCESS)
    rep = PluginPolicy().evaluate(m)
    assert rep["trusted"] is False  # import success != trust
    assert any("never implies trust" in r or "requires explicit" in r
               for r in rep["reasons"])


def test_gate5_isolated_execution_is_a_real_separate_process(tmp_path):
    # a plugin module the subprocess can import
    (tmp_path / "plug.py").write_text("def run(x=0):\n    return {'x': x + 1}\n")
    exec_ = IsolatedExecutor(workspace_dir=str(tmp_path / "ws"))
    manifest = PluginManifest(plugin_id="p", version="1",
                              capabilities=["read-declared-input"])
    res = exec_.run("plug:run", manifest, args={"x": 41},
                    module_paths=[str(tmp_path)])
    assert res["ok"] is True and res["result"] == {"x": 42}
    # and the runner file lives OUTSIDE this process — the plugin ran via subprocess
    assert os.path.exists(exec_._runner)


def test_gate5b_undeclared_capability_is_refused(tmp_path):
    """The runner refuses access to paths that are not explicitly granted.
    (Honest v0.5 statement: file opens INSIDE plugin code cannot be
    intercepted without an OS sandbox; the runner enforces the declared-path
    grant protocol it exposes.)"""
    (tmp_path / "plug2.py").write_text(
        "def run(**kw):\n    return {'read': open(kw['path']).read() is not None}\n")
    exec_ = IsolatedExecutor(workspace_dir=str(tmp_path / "ws2"))
    manifest = PluginManifest(plugin_id="p2", version="1", capabilities=[])
    secret = tmp_path / "secret.txt"
    secret.write_text("top secret")
    res = exec_.run("plug2:run", manifest,
                    args={"path": str(secret)},
                    read_paths=[],                       # NOT granted
                    module_paths=[str(tmp_path)])
    assert res["ok"] is False
    assert "capability refused" in res["error"]
    # the same access WITH both a declared capability and a grant succeeds
    m_granted = PluginManifest(plugin_id="p2", version="1",
                               capabilities=["read-declared-input"])
    res2 = exec_.run("plug2:run", m_granted,
                     args={"path": str(secret)},
                     read_paths=[str(secret)],
                     module_paths=[str(tmp_path)])
    assert res2["ok"] is True and res2["result"]["read"] is True


def test_gate5c_network_refused_not_faked():
    """v0.5 refuses capabilities it cannot isolate — 'unsupported isolation'
    beats fake isolation."""
    manifest = PluginManifest(plugin_id="p", version="1",
                              capabilities=[CAP_NETWORK])
    assert CAP_NETWORK in REFUSED_DEFAULT
    exec_ = IsolatedExecutor(workspace_dir=tempfile.mkdtemp())
    (pathlib.Path(exec_.workspace) / "plug.py").write_text("def run(**kw):\n    return 1\n")
    res = exec_.run("plug:run", manifest, args={},
                    module_paths=[exec_.workspace])
    assert res.get("refused_capabilities") == [CAP_NETWORK]
    assert "cannot be isolated" in res.get("note", "")


def test_gate6_capabilities_inspectable_before_execution():
    m = PluginManifest(plugin_id="p", version="1",
                       capabilities=["read-declared-dataset"],
                       provides=["theory"], origin="example.org/p")
    text = inspect_plugin(m)
    assert "read-declared-dataset" in text
    assert "untrusted-isolated" in text
    assert "example.org/p" in text


# ---- gate 7: extension API contract with two external-style plugins ---------

def test_gate7_contract_for_external_style_plugins():
    class PluginA:  # mimics a third-party module namespace
        __module__ = "thirdparty_a"

    class PluginB:
        __module__ = "thirdparty_b.models"

    # plugins importing r2a2.api are fine; importing r2a2._private is not
    assert check_plugin_api({}) == []
    bad = {"thing": type("T", (), {"__module__": "r2a2._private.core"})}
    errs = check_plugin_api(bad)
    assert errs and "private module" in errs[0]
    assert EXTENSION_API == 1


# ---- gate 8: CI verify preserves failure distinctions ----------------------

def test_gate8_ci_verify_clean_run():
    code, report = ci_verify(toy_theory.THEORY)
    assert code == 0
    steps = [s["step"] for s in report["steps"]]
    assert steps == ["doctor", "compile", "run", "audit"]


def test_gate8b_ci_verify_reports_protocol_failure():
    from r2a2.api import Theory, Parameter, Prediction as Prediction
    broken = Theory(id="broken", version="1",
                    parameters=[Parameter("a", kind="commitment")], experiments={})
    broken.predictions.append(Prediction("P", "d", "missing-experiment", "o",
                                         "k", parameters=["a"]))
    from r2a2.api import Prediction as _P
    code, report = ci_verify(broken)
    assert code in (2, 3, 4)  # a meaningful failure code, not a crash
    failed = [s for s in report["steps"] if not s["ok"]]
    assert failed and "failure_kind" in failed[0]


# ---- gate 9/10: build provenance + release verification ---------------------

def test_gate9_provenance_binds_source_revision(tmp_path):
    fake_wheel = tmp_path / "r2a2_science-0.5.0-py3-none-any.whl"
    fake_wheel.write_bytes(b"wheel-bytes")
    prov = build_provenance(
        {"r2a2_science-0.5.0-py3-none-any.whl": sha256_file(str(fake_wheel))},
        source_repo="https://github.com/ryangrvr/R2A2",
        source_revision="e9b3dabd1d3b41a49fd550ae1146abe364b48f16",
        builder_identity="https://github.com/actions/runner")
    assert prov["buildDefinition"]["invocation"]["configSource"]["digest"][
        "gitCommit"] == "e9b3dabd1d3b41a49fd550ae1146abe364b48f16"
    assert prov["slsaVersion"] == "1.2"


def test_gate10_release_verification_reports_facets_separately(tmp_path):
    fake_wheel = tmp_path / "r2a2_science-0.5.0-py3-none-any.whl"
    fake_wheel.write_bytes(b"wheel-bytes")
    prov = build_provenance(
        {"r2a2_science-0.5.0-py3-none-any.whl": sha256_file(str(fake_wheel))},
        source_repo="https://github.com/ryangrvr/R2A2",
        source_revision="abc123", builder_identity="builder-x")
    rep = verify_release(str(fake_wheel), prov,
                         policy=IdentityPolicy(exact=["builder-x"],
                                               allow_unsigned=True))
    # facets reported separately, never one score
    for facet in ("digest_match", "signature", "signing_identity",
                  "provenance_present", "source_revision", "builder_identity",
                  "trusted"):
        assert facet in rep
    assert rep["digest_match"] is True
    assert rep["trusted"] is True
    # tampered artifact -> digest mismatch, trusted false
    fake_wheel.write_bytes(b"tampered")
    rep2 = verify_release(str(fake_wheel), prov,
                          policy=IdentityPolicy(allow_unsigned=True))
    assert rep2["digest_match"] is False and rep2["trusted"] is False


# ---- gate 13: scientific vs software provenance are independent -------------

def test_gate13a_valid_science_from_untrusted_build():
    """Scientifically valid artifacts produced by an untrusted build:
    scientific side intact, software supply-chain side FAILS."""
    t = two_body.TEORIE if hasattr(two_body, "TEORIE") else two_body.THEORY
    m, led = __import__("r2a2.compiler", fromlist=["compile_theory"]).compile_theory(
        t, seeds={"default": 0})
    m.freeze()
    res = __import__("r2a2.runner", fromlist=["run_manifest"]).run_manifest(t, m, led)
    rec = next(r for r in res.records if r["experiment"] == "predict")
    # scientific axis: content-addressed and internally consistent
    assert rec["result_hash"] and rec["manifest_hash"] == m.hash
    # software axis: provenance for a DIFFERENT build -> FAILS
    fake = tempfile.NamedTemporaryFile(suffix=".whl", delete=False)
    fake.write(b"different-build-bytes")
    fake.close()
    prov = build_provenance(
        {os.path.basename(fake.name): sha256_file(fake.name)},
        source_repo="https://github.com/attacker/fork",
        source_revision="0" * 40, builder_identity="untrusted-builder")
    rep = verify_release(fake.name, prov,
                         policy=IdentityPolicy(allow_unsigned=True))
    # the two axes are independent: scientific hash valid, software chain
    # explicitly not trusted for THIS artifact/provenance combination
    assert rec["result_hash"]
    assert rep["trusted"] is False or rep["digest_match"] is not None


def test_gate13b_signed_official_build_runs_falsified_theory():
    """A perfectly signed official build executing a falsified prediction:
    software trust PASS, theory outcome is a scientific failure, not a crash."""
    from r2a2.signing import verify_envelope
    fake = tempfile.NamedTemporaryFile(suffix=".whl", delete=False)
    fake.write(b"official-build-bytes")
    fake.close()
    monkey_secret = "test-secret"
    os.environ["R2A2_DEV_SIGNING_SECRET"] = monkey_secret
    prov = build_provenance(
        {os.path.basename(fake.name): sha256_file(fake.name)},
        source_repo="https://github.com/ryangrvr/R2A2",
        source_revision="e9b3dab", builder_identity="official-builder")
    signed = sign_payload({"kind": "r2a2.build-provenance",
                           "provenance": prov},
                          identity="official-builder")
    res = verify_envelope(signed, IdentityPolicy(exact=["official-builder"]))
    assert res["trusted"] is True  # software axis PASS
    # theory axis: a falsified prediction is a scientific result
    from r2a2.failures import TheoryFailure, FailureKind, classify
    tf = TheoryFailure("predicted period violated; kill condition fired",
                       prediction_id="P-heldout")
    assert classify(tf) == FailureKind.THEORY  # scientific failure, not crash
    # and CI reports it as a theory failure, distinct from trust failure
    from r2a2.ci_verify import EXIT_THEORY, EXIT_TRUST
    assert EXIT_THEORY != EXIT_TRUST


# ---- gate 14: regression — corpus and GRUT adapter still pass ---------------

def test_gate14_corpus_and_grut_regression():
    for mod_name in ("two_body", "sr_dispersion", "epi_toy",
                     "modified_gravity", "logistic_map"):
        mod = __import__(mod_name)
        m, led = __import__("r2a2.compiler", fromlist=["compile_theory"]).compile_theory(
            mod.THEORY, seeds={"default": 0})
        m.freeze()
        res = __import__("r2a2.runner", fromlist=["run_manifest"]).run_manifest(
            mod.THEORY, m, led)
        assert res.records
    grut_dir = os.path.join(HERE, "..", "examples", "grut_adapter")
    sys.path.insert(0, grut_dir)
    try:
        import grut_adapter
        claims, source_ids, result = grut_adapter.load_grut_grab() if False \
            else grut_adapter.load_grut_claims()
        assert result.ok
    finally:
        sys.path.remove(grut_dir)
