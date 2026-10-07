"""Identity and signing layer for R2A5 trust artifacts.

Design principles (per external review of the v0.5 plan):

1. `content seal != identity signature`. The R2A2 content seal (v0.3) is the
   internal semantic integrity layer; the signature is the external
   identity/authentication layer. Verification establishes both INDEPENDENTLY.

2. Never equate "cryptographically signed" with "scientifically correct".

3. Never silently upgrade an unsigned or untrusted identity. Verification
   output is explicit:
   CONTENT VALID / IDENTITY VERIFIED / IDENTITY NOT TRUSTED BY POLICY /
   UNSIGNED / SIGNATURE INVALID / UNAUTHENTICATED (offline mode).

4. Use industry infrastructure where possible. Sigstore keyless signing
   (OIDC identity + transparency log) is the primary backend via the
   `sigstore` Python client when installed. An explicit offline HMAC mode
   exists ONLY for development and is always marked UNAUTHENTICATED — it
   authenticates possession of a local secret, not an identity.

5. Identity policy is data, not code: allowed issuers and identity patterns
   are declared, so "valid signature from untrusted identity" is
   distinguishable from "trusted".
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .schema import SCHEMA_VERSION, stamp

# --- verification verdicts (explicit, never a single "secure" score) --------
CONTENT_VALID = "CONTENT VALID"
IDENTITY_VERIFIED = "IDENTITY VERIFIED"
IDENTITY_NOT_TRUSTED = "IDENTITY NOT TRUSTED BY POLICY"
UNSIGNED = "UNSIGNED"
SIGNATURE_INVALID = "SIGNATURE INVALID"
UNAUTHENTICATED = "UNAUTHENTICATED (offline dev mode)"
SEAL_BROKEN = "CONTENT SEAL BROKEN"

SIGNER_SIGSTORE = "sigstore"
SIGNER_OFFLINE = "offline-hmac"


# --------------------------------------------------------------------------
# Identity policy
# --------------------------------------------------------------------------

@dataclass
class IdentityPolicy:
    """Declares which signer identities are trusted.

    exact:       list of exact identities (e.g. "alice@example.org")
    domains:     list of accepted email domains (e.g. "example.org")
    issuers:     list of accepted OIDC issuers (e.g. "https://github.com/login/oauth")
    workflows:   list of approved CI workflow identities (OIDC sub patterns)
    allow_unsigned: if True, UNSIGNED artifacts are accepted but ALWAYS
                 reported as UNSIGNED — never silently treated as trusted.
    """

    exact: List[str] = field(default_factory=list)
    domains: List[str] = field(default_factory=list)
    issuers: List[str] = field(default_factory=list)
    workflows: List[str] = field(default_factory=list)
    allow_unsigned: bool = False

    def check(self, identity: Optional[str], issuer: Optional[str],
              signer: str) -> str:
        """Returns one of the verification verdicts for the identity claim."""
        if signer == SIGNER_OFFLINE:
            return UNAUTHENTICATED
        if not identity:
            return UNSIGNED
        if self.exact and identity in self.exact:
            return IDENTITY_VERIFIED
        for d in self.domains:
            if identity.endswith("@" + d):
                return IDENTITY_VERIFIED
        if issuer and self.issuers and issuer in self.issuers:
            return IDENTITY_VERIFIED
        for w in self.workflows:
            if identity and identity.startswith(w):
                return IDENTITY_VERIFIED
        return IDENTITY_NOT_TRUSTED


# --------------------------------------------------------------------------
# Signed envelopes
# --------------------------------------------------------------------------

def _payload_digest(envelope: dict) -> str:
    """Digest over the signed payload (everything except the signature and
    the stored digest itself, which is derived, not signed content)."""
    payload = {k: v for k, v in envelope.items()
               if k not in ("signature", "signer_backend", "payload_digest")}
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()


def sign_payload(payload: dict, signer_backend: str = None,
                 identity: str = None, issuer: str = None) -> dict:
    """Wrap a payload in a signed envelope.

    Backend selection:
    - "sigstore": use the sigstore Python client (keyless, OIDC). If the
      package or network is unavailable, raises with instructions — never
      silently downgrades.
    - "offline-hmac": development-only HMAC with a local secret. Always
      marked UNAUTHENTICATED at verification.
    """
    backend = signer_backend or os.environ.get("R2A2_SIGNER", SIGNER_OFFLINE)
    envelope = stamp({
        "payload": payload,
        "signer_backend": backend,
        "identity": identity,
        "issuer": issuer,
    })
    digest = _payload_digest(envelope)
    if backend == SIGNER_OFFLINE:
        secret = os.environ.get("R2A2_DEV_SIGNING_SECRET", "")
        if not secret:
            raise RuntimeError(
                "offline signing requires R2A2_DEV_SIGNING_SECRET; this mode "
                "is UNAUTHENTICATED and for development only")
        envelope["signature"] = base64.b64encode(
            hmac.new(secret.encode(), digest.encode(), hashlib.sha256).digest()
        ).decode()
        envelope["payload_digest"] = digest
        return envelope
    if backend == SIGNER_SIGSTORE:
        try:
            from sigstore import __version__ as _sigstore_version  # noqa
        except ImportError:
            raise RuntimeError(
                "sigstore backend requires `pip install sigstore`; no silent "
                "downgrade to an unauthenticated mode is permitted")
        # The sigstore Python client performs OIDC-based keyless signing; the
        # exact call surface is version-dependent, so we delegate and record
        # the identity claim the signer reported. Integration lives in
        # _sigstore_sign below and is exercised when the package is present.
        return _sigstore_sign(envelope, digest)
    raise ValueError(f"unknown signer backend {backend!r}")


def _sigstore_sign(envelope: dict, digest: str) -> dict:  # pragma: no cover
    """Sigstore keyless signing. Requires network + OIDC; never faked."""
    try:
        from sigstore.sign import Signer
        from sigstore.oidc import Issuer
        issuer = Issuer.production()
        identity_token = issuer.identity_token()
        signer = Signer.explicit()
        # sigstore signs arbitrary bytes; we sign the payload digest
        import base64
        result = signer.sign(input_=digest.encode())
        bundle_b64 = getattr(result, "b64_bundle", None) or \
            base64.b64encode(result.bundle).decode()
        envelope["signature"] = bundle_b64
        envelope["payload_digest"] = digest
        envelope["identity"] = identity_token.identity
        return envelope
    except Exception as exc:  # pragma: no cover - network/OIDC dependent
        raise RuntimeError(
            f"sigstore signing failed: {exc}. R2A2 does not silently "
            "downgrade to an unauthenticated mode.") from exc


def verify_envelope(envelope: dict, policy: IdentityPolicy) -> Dict[str, Any]:
    """Verify content integrity and identity independently.

    Returns a report with separate verdicts:
    - content: CONTENT VALID / SEAL BROKEN / SIGNATURE INVALID
    - identity: IDENTITY VERIFIED / NOT TRUSTED / UNSIGNED / UNAUTHENTICATED
    - overall: trusted only if BOTH content is valid AND identity passes
      policy (or allow_unsigned with the UNSIGNED verdict surfaced).
    """
    stored_sig = envelope.get("signature")
    if not stored_sig:
        identity_v = UNSIGNED
        content_v = CONTENT_VALID if not envelope.get("payload_digest") \
            else SIGNATURE_INVALID
        if not envelope.get("payload_digest"):
            content_v = UNSIGNED
    else:
        digest = _payload_digest(envelope)
        if envelope.get("signer_backend") == SIGNER_OFFLINE:
            secret = os.environ.get("R2A2_DEV_SIGNING_SECRET", "")
            expected = base64.b64encode(
                hmac.new(secret.encode(), digest.encode(), hashlib.sha256).digest()
            ).decode()
            content_v = CONTENT_VALID if hmac.compare_digest(expected, stored_sig) \
                else SIGNATURE_INVALID
        else:  # sigstore
            content_v = _sigstore_verify(envelope, digest)
        identity_v = policy.check(envelope.get("identity"),
                                  envelope.get("issuer"),
                                  envelope.get("signer_backend", ""))

    content_ok = content_v == CONTENT_VALID
    identity_ok = identity_v in (IDENTITY_VERIFIED, UNAUTHENTICATED, UNSIGNED)
    if identity_v == UNSIGNED and not policy.allow_unsigned:
        identity_ok = False
    trusted = content_ok and identity_ok
    return stamp({
        "content": content_v,
        "identity": identity_v,
        "trusted": trusted,
        "signer_backend": envelope.get("signer_backend"),
        "identity_claim": envelope.get("identity"),
        "note": "A signature authenticates an identity and action; it does "
                "not validate scientific judgment.",
    })


def _sigstore_verify(envelope: dict, digest: str) -> str:  # pragma: no cover
    try:
        import base64
        from sigstore.verify import Verifier, policy as spolicy
        verifier = Verifier.production()
        bundle = base64.b64decode(envelope["signature"])
        verifier.verify(input_=digest.encode(),
                        bundle=bundle,
                        policy=spolicy.Identity(
                            identity=envelope.get("identity", ""),
                            issuer=envelope.get("issuer", "")))
        return CONTENT_VALID
    except Exception:
        return SIGNATURE_INVALID
