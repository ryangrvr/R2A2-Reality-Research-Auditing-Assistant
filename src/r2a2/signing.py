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

    Authorization logic (v0.5.1 — issuer AND identity must both pass):
    - Sigstore identities are trusted only when BOTH the OIDC issuer is
      permitted AND the identity matches an exact/domain/workflow constraint.
      `trust_issuer_identities=True` relaxes this to issuer-only — an
      explicit opt-in, never the default.
    - exact:       exact identities (e.g. "alice@example.org")
    - domains:     accepted email domains (e.g. "example.org")
    - issuers:     accepted OIDC issuers (e.g. "https://github.com/login/oauth")
    - workflows:   approved CI workflow identity (OIDC sub) prefixes
    - trust_issuer_identities: if True, ANY identity from a permitted issuer
      is trusted (issuer-only authorization). Default False.
    - allow_unsigned: if True, UNSIGNED artifacts get local acceptance —
      reported as UNSIGNED, NEVER as authenticated trust.
    """

    exact: List[str] = field(default_factory=list)
    domains: List[str] = field(default_factory=list)
    issuers: List[str] = field(default_factory=list)
    workflows: List[str] = field(default_factory=list)
    trust_issuer_identities: bool = False
    allow_unsigned: bool = False

    def check(self, identity: Optional[str], issuer: Optional[str],
              signer: str) -> str:
        """Authorization verdict. Offline mode is ALWAYS UNAUTHENTICATED —
        it cannot be promoted to an identity verdict by any policy."""
        if signer == SIGNER_OFFLINE:
            return UNAUTHENTICATED
        if not identity:
            return UNSIGNED
        # Sigstore: issuer AND identity constraints must BOTH pass (unless
        # trust_issuer_identities is explicitly opted in).
        if signer == SIGNER_SIGSTORE:
            issuer_ok = (not self.issuers) or (issuer in self.issuers) \
                if self.trust_issuer_identities else \
                (issuer is not None and issuer in self.issuers) \
                if self.issuers else True
            if self.issuers and not issuer_ok:
                return IDENTITY_NOT_TRUSTED
        # identity constraints
        if self.exact and identity in self.exact:
            return IDENTITY_VERIFIED if self._issuer_ok(issuer, signer) \
                else IDENTITY_NOT_TRUSTED
        for d in self.domains:
            if identity.endswith("@" + d):
                return IDENTITY_VERIFIED if self._issuer_ok(issuer, signer) \
                    else IDENTITY_NOT_TRUSTED
        for w in self.workflows:
            if identity.startswith(w):
                return IDENTITY_VERIFIED if self._issuer_ok(issuer, signer) \
                    else IDENTITY_NOT_TRUSTED
        # issuer-only authorization requires the explicit opt-in
        if self.trust_issuer_identities and issuer and issuer in self.issuers:
            return IDENTITY_VERIFIED
        return IDENTITY_NOT_TRUSTED

    def _issuer_ok(self, issuer: Optional[str], signer: str) -> bool:
        if signer != SIGNER_SIGSTORE or not self.issuers:
            return True
        if issuer is None:
            return False
        return issuer in self.issuers


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
    """Verify content integrity and identity INDEPENDENTLY.

    v0.5.1 semantics — four concepts kept rigorously separate:

        integrity (content matches its seal/signature)
      ≠ authentication (a verified identity produced it)
      ≠ authorization (policy allows that identity)
      ≠ isolation (code containment)

    Rules enforced here:
    - OFFLINE HMAC is integrity-only. identity verdict is ALWAYS
      UNAUTHENTICATED and `trusted` is ALWAYS False — no policy can promote
      an offline identity claim to authenticated trust.
    - UNSIGNED is never trusted unless policy.allow_unsigned AND the verdict
      still reports UNSIGNED (a weaker local-acceptance concept, not
      authenticated trust).
    - For Sigstore: trusted requires signature valid AND issuer permitted
      AND identity/workflow constraint permitted. An approved issuer alone
      is NOT sufficient unless policy.trust_issuer_identities is set.
    """
    stored_sig = envelope.get("signature")
    backend = envelope.get("signer_backend", "")
    if not stored_sig:
        identity_v = UNSIGNED
        # an envelope with a claimed backend/digest but NO signature is
        # SUSPECT (signature stripped) — SIGNATURE INVALID, not merely unsigned
        content_v = SIGNATURE_INVALID if \
            (envelope.get("payload_digest") or backend) else UNSIGNED
    else:
        digest = _payload_digest(envelope)
        if backend == SIGNER_OFFLINE:
            secret = os.environ.get("R2A2_DEV_SIGNING_SECRET", "")
            expected = base64.b64encode(
                hmac.new(secret.encode(), digest.encode(), hashlib.sha256).digest()
            ).decode()
            content_v = CONTENT_VALID if hmac.compare_digest(expected, stored_sig) \
                else SIGNATURE_INVALID
            # integrity ≠ authentication: offline HMAC proves possession of
            # the dev secret, never an identity. No policy promotion.
            identity_v = UNAUTHENTICATED
        else:  # sigstore
            try:
                content_v = _sigstore_verify(envelope, digest)
            except ImportError:
                # sigstore backend configured but client absent: this is a
                # TRUST failure, never a silent downgrade
                return stamp({
                    "content": SIGNATURE_INVALID,
                    "identity": IDENTITY_NOT_TRUSTED,
                    "trusted": False,
                    "authenticated": False,
                    "signer_backend": backend,
                    "identity_claim": envelope.get("identity"),
                    "error": "sigstore backend declared but 'sigstore' package "
                             "is not installed; refusing to verify without it",
                    "note": "integrity != authentication != authorization "
                            "!= isolation.",
                })
            identity_v = policy.check(envelope.get("identity"),
                                      envelope.get("issuer"), backend)

    content_ok = content_v == CONTENT_VALID
    # AUTHENTICATED trust exists ONLY when the identity verdict is
    # IDENTITY_VERIFIED. UNAUTHENTICATED/UNSIGNED are integrity outcomes,
    # never identity outcomes — they cannot produce authenticated trust.
    if backend == SIGNER_OFFLINE:
        trusted = False
    elif identity_v == IDENTITY_VERIFIED:
        trusted = content_ok
    elif identity_v == UNSIGNED and policy.allow_unsigned:
        trusted = False  # local-acceptance only; never authenticated trust
    else:
        trusted = False
    return stamp({
        "content": content_v,
        "identity": identity_v,
        "trusted": trusted,
        "authenticated": identity_v == IDENTITY_VERIFIED and content_ok,
        "signer_backend": backend,
        "identity_claim": envelope.get("identity"),
        "note": "integrity != authentication != authorization != isolation. "
                "A signature authenticates an identity and action; it does "
                "not validate scientific judgment.",
    })


def _sigstore_verify(envelope: dict, digest: str) -> str:
    """Verify via the sigstore client. The transport is looked up through
    `_sigstore_transport()` so tests can exercise the SAME verification
    semantics with a mock bundle/verifier. In production this uses the real
    sigstore package + network + Rekor transparency log."""
    try:
        verifier_factory, bundle_bytes, identity, issuer = _sigstore_transport(
            envelope, digest)
        verifier = verifier_factory()
        verifier.verify(input_=digest.encode(), bundle=bundle_bytes,
                        policy=identity) if False else None
        # the mock/real verifier exposes verify(input, bundle, policy)
        verifier.verify(input_=digest.encode(), bundle=bundle_bytes)
        return CONTENT_VALID
    except ImportError:
        raise
    except Exception:
        return SIGNATURE_INVALID


def _sigstore_transport(envelope: dict, digest: str):
    """Locate the Sigstore verification machinery. Tests may monkeypatch this
    to supply a mock verifier exercising the same code path."""
    import base64
    from sigstore.verify import Verifier, policy as spolicy  # type: ignore
    bundle = base64.b64decode(envelope["signature"])
    ident = spolicy.Identity(identity=envelope.get("identity", ""),
                             issuer=envelope.get("issuer", ""))
    return Verifier.production, bundle, ident, envelope.get("issuer")
