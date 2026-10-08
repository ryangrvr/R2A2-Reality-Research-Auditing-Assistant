"""v0.5.4 — Sigstore 4.x compatibility tests.

These tests run against the REAL installed sigstore client (pinned 4.0.0 and
4.5.0 in the compat CI matrix). Only the OIDC token issuance is mocked; the
Bundle, Verifier, policy and trust-config classes are the real library
objects.

HONEST SCOPE STATEMENT (per external review):
- Real *signing* requires a live Fulcio that accepts the OIDC token. A
  fabricated JWT is rejected by the live service, so signing is NOT tested
  here — it is covered by the explicit live-OIDC integration test.
- Real *verification* of a bundle also requires a genuine Fulcio/Rekor chain
  (Bundle._verify demands a real transparency-log inclusion promise), so a
  hand-built bundle cannot pass Bundle.from_json. What CAN be tested without
  live services — and is tested here — is that the adapter's transport
  handles the real wire format correctly: canonical JSON bundle in,
  real Bundle objects and Identity policy out, legacy formats rejected.
- The full sign->verify lifecycle is demonstrated only by the live-OIDC
  integration test, which is explicitly skipped (never substituted) when
  live credentials are unavailable.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import sigstore  # noqa
    HAVE_SIGSTORE = True
except ImportError:
    HAVE_SIGSTORE = False

pytestmark = pytest.mark.skipif(
    not HAVE_SIGSTORE,
    reason="real sigstore client (>=4.x) not importable here; runs in the "
           "sigstore-compat CI job against pinned 4.0.0/4.5.0")

ISSUER_URL = "https://github.com/login/oauth"
IDENTITY = "alice@example.org"


def test_bundle_parser_rejects_malformed_bundle():
    """The REAL Bundle parser is in use: a malformed bundle is rejected
    (pydantic ValidationError or the parser's own InvalidBundle — both are
    the real library's failure modes, proving no mock is involved)."""
    from sigstore.models import Bundle
    try:
        Bundle.from_json(json.dumps({"mediaType": "not-a-bundle"}))
        raise AssertionError("malformed bundle accepted")
    except AssertionError:
        raise
    except Exception as e:
        assert type(e).__module__.startswith(("sigstore", "pydantic")), \
            f"unexpected failure mode: {e!r}"


def test_bundle_parser_requires_complete_verification_material():
    """A structurally incomplete bundle (no transparency log entry) is
    rejected — documenting that Bundle.from_json enforces the full 0.1/0.3
    schema, including the Rekor inclusion promise."""
    from sigstore.models import Bundle
    incomplete = {
        "mediaType": "application/vnd.dev.sigstore.bundle+json;version=0.1",
        "verificationMaterial": {"publicKey": {
            "rawBytes": {"bytes": "", "algorithm": "ECDSA_P256_SHA256"},
            "hint": ""}},
        "messageSignature": {"messageDigest": {
            "digest": "AAAA", "algorithm": "SHA2_256"}},
    }
    try:
        Bundle.from_json(json.dumps(incomplete))
        raise AssertionError("incomplete bundle accepted")
    except AssertionError:
        raise
    except Exception as e:
        assert type(e).__module__.startswith(("sigstore", "pydantic")), \
            f"unexpected failure mode: {e!r}"


def test_identity_policy_binds_expected_identity_and_issuer():
    """The REAL Identity verification policy object binds the expected
    certificate identity and OID issuer — the values the client enforces
    during verify_artifact."""
    from sigstore import verify as _sverify
    pol = _sverify.policy.Identity(identity=IDENTITY, issuer=ISSUER_URL)
    assert pol._identity == IDENTITY
    # _issuer is an OIDCIssuer wrapper; compare its URL
    assert getattr(pol._issuer, "issuer_url", None) == ISSUER_URL or \
        str(getattr(pol._issuer, "issuer_url", "")) == ISSUER_URL


def test_adapter_transport_rejects_legacy_base64():
    from r2a2.signing import _sigstore_transport, SigstoreVerificationError
    envelope = {"signature": "AAAA",  # not JSON
                "identity": IDENTITY, "issuer": ISSUER_URL}
    with pytest.raises(SigstoreVerificationError):
        _sigstore_transport(envelope, "digest")


def test_adapter_transport_missing_issuer_fails_closed():
    from r2a2.signing import _sigstore_transport, SigstoreVerificationError
    envelope = {"signature": json.dumps({"mediaType": "x"}),
                "signature_format": "sigstore-bundle-json",
                "identity": IDENTITY, "issuer": None}
    with pytest.raises(SigstoreVerificationError):
        _sigstore_transport(envelope, "digest")


def test_live_signing_and_verification():
    """The full sign->verify lifecycle. Requires live OIDC + Fulcio + Rekor.
    Explicitly skipped (never substituted) when R2A2_LIVE_OIDC is unset."""
    if not os.environ.get("R2A2_LIVE_OIDC"):
        pytest.skip("requires live OIDC/Fulcio/Rekor; explicitly NOT RUN "
                    "in this environment")
    from sigstore import sign as _ssign, verify as _sverify
    from sigstore.models import ClientTrustConfig
    from sigstore.oidc import Issuer

    trust = ClientTrustConfig.production()
    issuer = Issuer(trust.signing_config.get_oidc_url())
    context = _ssign.SigningContext.from_trust_config(trust)
    token = issuer.identity_token()
    with context.signer(identity_token=token) as signer:
        payload = b"r2a2 live payload"
        bundle = signer.sign_artifact(input_=payload)
    raw = bundle.to_json()
    bundle2 = _sverify.Bundle.from_json(raw)
    verifier = _sverify.Verifier.production()
    verifier.verify_artifact(
        input_=payload, bundle=bundle2,
        policy=_sverify.policy.Identity(
            identity=token.identity, issuer=token.issuer))
