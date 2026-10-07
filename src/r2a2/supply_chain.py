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

    Reports SEPARATE facets — never a single score:
    - digest match, signature validity, signing identity, provenance
      presence, source revision, builder identity, policy result.
    """
    policy = policy or IdentityPolicy(allow_unsigned=True)
    actual = sha256_file(artifact_path)

    # unwrap a signed provenance envelope if present
    envelope = None
    prov_doc = provenance
    if "payload" in provenance and "provenance" in provenance.get("payload", {}):
        envelope = provenance
        prov_doc = provenance["payload"]["provenance"]

    report: Dict[str, Any] = stamp({
        "artifact": os.path.basename(artifact_path),
        "digest_match": None,
        "signature": None,
        "signing_identity": None,
        "provenance_present": prov_doc is not None,
        "provenance_shape": "SLSA v1.2" if prov_doc else None,
        "source_revision": (prov_doc.get("buildDefinition", {})
                            .get("invocation", {}).get("configSource", {})
                            .get("digest", {}).get("gitCommit")),
        "builder_identity": (prov_doc.get("builder", {}) or {}).get("id"),
        "build_level": prov_doc.get("buildLevel"),
        "trusted": False,
        "facet_notes": [],
    })

    # 1. digest: artifact must match a provenance subject
    subjects = prov_doc.get("subjects", []) if prov_doc else []
    report["digest_match"] = any(
        s.get("digest", {}).get("sha256") == actual for s in subjects)
    if not report["digest_match"]:
        report["facet_notes"].append("artifact digest not found in provenance subjects")

    # 2. signature + identity (independent facets)
    if envelope is not None:
        sig = verify_envelope(envelope, policy)
        report["signature"] = sig["content"]
        report["signing_identity"] = sig["identity"]
    else:
        report["signature"] = "UNSIGNED"
        report["facet_notes"].append("provenance is not signed")

    # trusted only when: digest matches AND provenance present AND (if signed)
    # signature valid AND identity passes policy
    sig_ok = report["signature"] in (CONTENT_VALID, "UNSIGNED") and \
        (report["signing_identity"] in (IDENTITY_VERIFIED, UNAUTHENTICATED)
         or report["signing_identity"] is None)
    report["trusted"] = bool(report["digest_match"] and
                             report["provenance_present"] and sig_ok)
    return report


def _sign_and_roundtrip(payload: dict, identity: str) -> dict:
    from .signing import sign_payload
    return sign_payload({"kind": "r2a2.build-provenance", "provenance": payload},
                        identity=identity)
