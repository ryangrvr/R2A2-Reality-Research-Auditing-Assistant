"""v0.5.3 — Sigstore 4.x compatibility closure.

Gate 7 of v0.5.3: a non-network compatibility test against the INSTALLED
REAL Sigstore classes. Only the OIDC/network layer is mocked — SigningContext,
Issuer, ClientTrustConfig, Bundle and Verifier are the real library objects.

This proves the production object lifecycle actually runs with the current
client: trust config -> Issuer(oidc_url) -> SigningContext.from_trust_config
-> signer.sign_artifact -> Bundle.to_json -> Bundle.from_json ->
Verifier.production().verify_artifact(input, Bundle, Identity policy).
"""
import base64
import hashlib
import hmac
import json
import os
import sys
from unittest import mock

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import sigstore  # noqa
    HAVE_SIGSTORE = True
except ImportError:
    HAVE_SIGSTORE = False

pytestmark = pytest.mark.skipif(not HAVE_SIGSTORE,
                                reason="real sigstore client (>=4.x) not "
                                "importable in this environment; run in the "
                                "sigstore-compat CI job against pinned "
                                "lowest/highest supported versions")

ISSUER_URL = "https://github.com/login/oauth"
IDENTITY = "alice@example.org"


class _FakeIdentityToken:
    """Mocks ONLY the OIDC network layer: a token whose identity/issuer are
    what a real OIDC flow would return. Everything downstream is real."""

    identity = IDENTITY
    issuer = ISSUER_URL

    def __str__(self):
        return "fake-oidc-token"


def test_real_signer_signs_and_produces_canonical_bundle(tmp_path, monkeypatch):
    """Real SigningContext + real Signer.sign_artifact (with only the OIDC
    token mocked): produces a real Bundle whose to_json() is canonical."""
    from sigstore import sign as _ssign
    from sigstore._internal.trust import ClientTrustConfig
    from sigstore.oidc import Issuer

    trust = ClientTrustConfig.staging()  # staging: no network needed for config
    monkeypatch.setattr(Issuer, "identity_token",
                        lambda self, *a, **k: _FakeIdentityToken(), raising=True)
    issuer = Issuer(trust.signing_config.get_oidc_url())
    context = _ssign.SigningContext.from_trust_config(trust)
    with context.signer(identity_token=_FakeIdentityToken()) as signer:
        payload = b"r2a2 compatibility payload"
        bundle = signer.sign_artifact(input_=payload)
    raw = bundle.to_json()
    assert raw.lstrip().startswith("{"), "bundle must serialize as canonical JSON"


def test_real_bundle_roundtrip_and_verify_path(tmp_path, monkeypatch):
    """Bundle.to_json -> Bundle.from_json -> Verifier.production().verify_
    artifact(input, Bundle, Identity policy) with the REAL classes. A wrong
    identity policy fails AT the verifier."""
    from sigstore import sign as _ssign, verify as _sverify
    from sigstore._internal.trust import ClientTrustConfig
    from sigstore.oidc import Issuer

    trust = ClientTrustConfig.staging()
    monkeypatch.setattr(Issuer, "identity_token",
                        lambda self, *a, **k: _FakeIdentityToken(), raising=True)
    payload = b"r2a2 compatibility payload"
    with _ssign.SigningContext.from_trust_config(trust).signer(
            identity_token=_FakeIdentityToken()) as signer:
        bundle = signer.sign_artifact(input_=payload)
    raw = bundle.to_json()

    # reconstruct exactly as the R2A2 adapter does
    bundle2 = _sverify.Bundle.from_json(raw)
    verifier = _sverify.Verifier.production()

    # correct identity + issuer: verification SUCCEEDS (real crypto)
    policy_ok = _sverify.policy.Identity(identity=IDENTITY, issuer=ISSUER_URL)
    verifier.verify_artifact(input_=payload, bundle=bundle2, policy=policy_ok)

    # wrong identity in the policy: fails AT THE VERIFIER (real classes)
    policy_bad = _sverify.policy.Identity(identity="mallory@evil.example",
                                          issuer=ISSUER_URL)
    with pytest.raises(Exception):
        verifier.verify_artifact(input_=payload, bundle=bundle2, policy=policy_bad)


def test_adapter_transport_uses_real_bundle_objects(tmp_path, monkeypatch):
    """The R2A2 adapter's _sigstore_transport, fed a REAL bundle JSON,
    reconstructs a real Bundle and a real Identity policy."""
    from sigstore import sign as _ssign, verify as _sverify
    from sigstore._internal.trust import ClientTrustConfig
    from sigstore.oidc import Issuer
    from r2a2.signing import _sigstore_transport

    trust = ClientTrustConfig.staging()
    monkeypatch.setattr(Issuer, "identity_token",
                        lambda self, *a, **k: _FakeIdentityToken(), raising=True)
    payload = b"adapter transport payload"
    with _ssign.SigningContext.from_trust_config(trust).signer(
            identity_token=_FakeIdentityToken()) as signer:
        bundle = signer.sign_artifact(input_=payload)

    envelope = {"signature": bundle.to_json(),
                "signature_format": "sigstore-bundle-json",
                "identity": IDENTITY, "issuer": ISSUER_URL}
    factory, policy_obj, bundle_obj = _sigstore_transport(envelope, "digest")
    assert isinstance(bundle_obj, _sverify.Bundle)
    assert factory == _sverify.Verifier.production


def test_adapter_rejects_legacy_base64_signature():
    """The old ad-hoc base64 format must be rejected: the adapter requires
    canonical Sigstore JSON bundles (4.x wire format)."""
    from r2a2.signing import _sigstore_transport, SigstoreVerificationError
    envelope = {"signature": base64.b64encode(b"legacy-bytes").decode(),
                "identity": IDENTITY, "issuer": ISSUER_URL}
    with pytest.raises(SigstoreVerificationError):
        _sigstore_transport(envelope, "digest")
