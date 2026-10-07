"""Software supply-chain provenance and release verification.

DISTINCTION (required by the external review):

- SCIENTIFIC provenance  — what R2A2 tracks internally: claims, assumptions,
  frozen manifests, results, replications, attestations, transfers.
- SOFTWARE supply-chain provenance — where the code came from and how the
  release artifact was built. This module implements that layer using
  SLSA/in-toto-compatible structures (SLSA v1.2 provenance shape), NOT a
  private R2A2 format.

The two axes are independent and the tests prove it:
  scientifically valid artifacts from an untrusted build -> software FAIL
  perfectly signed official build running a falsified theory -> software PASS

Verification NEVER emits a single "secure" score; it reports separate facets:
digest, signature, identity, provenance presence, source revision, builder,
policy result.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .schema import SCHEMA_VERSION, stamp
from .signing import (CONTENT_VALID, IDENTITY_VERIFIED, IdentityPolicy,
                      SIGNER_OFFLINE, UNAUTHENTICATED, verify_envelope)

# SLSA v1.2 build levels we can claim/verify
SLSA_BUILD_L1 = "SLSA_BUILD_LEVEL_1"   # provenance present (scripted build)
SLSA_BUILD_L2 = "SLSA_BUILD_LEVEL_2"   # + hosted build service, signed provenance
SLSA_BUILD_L3 = "SLSA_BUILD_LEVEL_3"   # + hardened build platform


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def build_provenance(subject_files: Dict[str, str],
                     source_repo: str, source_revision: str,
                     builder_identity: str, build_invocation: str = "",
                     build_level: str = SLSA_BUILD_L1,
                     sign_backend: str = None) -> dict:
    """Create SLSA-v1.2-shaped build provenance for release artifacts.

    subject_files: {filename: sha256} of wheels/sdists produced by the build
    """
    payload = stamp({
        "slsaVersion": "1.2",
        "buildLevel": build_level,
        "builder": {"id": builder_identity},
        "buildDefinition": {
            "buildType": "https://r2a2-science.org/builds/python-package/v1",
            "invocation": {"configSource": {
                "uri": f"git+{source_repo}@{source_revision}",
                "digest": {"gitCommit": source_revision},
                "entryPoint": build_invocation or "python -m build"}},
            "parameters": {},
        },
        "runDetails": {
            "builder": {"id": builder_identity},
            "metadata": {},
        },
        "subjects": [{"name": name, "digest": {"sha256": digest}}
                     for name, digest in sorted(subject_files.items())],
    })
    if sign_backend:
        from .signing import sign_payload
        return sign_payload({"kind": "r2a2.build-provenance",
                             "provenance": payload},
                            signer_backend=sign_backend)
    return payload


def verify_release(artifact_path: str,
                   provenance: dict,
                   policy: IdentityPolicy = None) -> Dict[str, Any]:
    """Verify a release artifact against its provenance.

    v0.5.1: reports SEPARATE facets and NEVER conflates them into one score.
    Authenticated release trust requires: digest match AND provenance present
    AND signature valid AND signing identity authenticated AND policy match.
    Unsigned provenance may have digest_match=True and provenance_present=True
    but authenticated_release_trust is ALWAYS False — unsigned means the
    builder identity is self-asserted, not proven.
    """
    policy = policy or IdentityPolicy()
    actual = sha256_file(artifact_path)

    envelope = None
    prov_doc = provenance
    if "payload" in provenance and "provenance" in provenance.get("payload", {}):
        envelope = provenance
        prov_doc = provenance["payload"]["provenance"]

    claimed_builder = (prov_doc.get("builder", {}) or {}).get("id")
    report: Dict[str, Any] = stamp({
        "artifact": os.path.basename(artifact_path),
        "digest_match": None,
        "provenance_present": prov_doc is not None,
        "provenance_shape": "SLSA v1.2" if prov_doc else None,
        "signature_status": None,
        "authenticated_identity": None,
        "claimed_builder": claimed_builder,
        "authenticated_builder": False,
        "policy_match": False,
        "source_revision": (prov_doc.get("buildDefinition", {})
                            .get("invocation", {}).get("configSource", {})
                            .get("digest", {}).get("gitCommit")),
        # legacy facets (kept for compatibility, subordinate to the above)
        "signing_identity": None,
        "build_level": prov_doc.get("buildLevel"),
        "trusted": False,
        "facet_notes": [],
    })

    subjects = prov_doc.get("subjects", []) if prov_doc else []
    report["digest_match"] = any(
        s.get("digest", {}).get("sha256") == actual for s in subjects)
    if not report["digest_match"]:
        report["facet_notes"].append("artifact digest not found in provenance subjects")

    # AUTHENTICATION: signature must be valid AND identity verified.
    if envelope is not None:
        sig = verify_envelope(envelope, policy)
        report["signature_status"] = sig["content"]
        report["signing_identity"] = sig["identity"]
        report["authenticated_identity"] = (sig["authenticated"] is True)
        # the authenticated signer must match the CLAIMED builder under policy
        claim = envelope.get("identity")
        report["policy_match"] = sig["identity"] == IDENTITY_VERIFIED and (
            not policy.exact or claim in policy.exact or
            (policy.trust_issuer_identities and claim is not None))
    else:
        report["signature_status"] = "UNSIGNED"
        report["facet_notes"].append(
            "provenance is unsigned: builder identity is self-asserted, "
            "not authenticated")

    # authenticated builder = the SIGNER is verified AND equals the claim
    report["authenticated_builder"] = bool(
        report["authenticated_identity"] and report["policy_match"] and
        envelope is not None and envelope.get("identity") == claimed_builder)

    report["trusted"] = bool(
        report["digest_match"] and report["provenance_present"] and
        report["authenticated_builder"])
    return report


def _sign_and_roundtrip(payload: dict, identity: str) -> dict:
    from .signing import sign_payload
    return sign_payload({"kind": "r2a2.build-provenance", "provenance": payload},
                        identity=identity)
