"""Software supply-chain provenance and release verification.

DISTINCTION (required by the external reviews):

- SCIENTIFIC provenance  — what R2A2 tracks internally: claims, assumptions,
  frozen manifests, results, replications, attestations, transfers.
- SOFTWARE supply-chain provenance — where the code came from and how the
  release artifact was built. SLSA v1.2-shaped, not a private format.

v0.5.2: release identity authorization is CONSUMED from the authoritative
verify_envelope() verdict — this module no longer re-implements IdentityPolicy
(partial reimplementations would diverge from the real policy semantics).
The authenticated identity must come from the Sigstore bundle verification
(certificate SAN + OID issuer bound by the client), not from self-asserted
provenance claims.
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Dict

from .schema import stamp
from .signing import (CONTENT_VALID, IDENTITY_VERIFIED, IdentityPolicy,
                      verify_envelope)

SLSA_BUILD_L1 = "SLSA_BUILD_LEVEL_1"
SLSA_BUILD_L2 = "SLSA_BUILD_LEVEL_2"
SLSA_BUILD_L3 = "SLSA_BUILD_LEVEL_3"


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def build_provenance(subject_files: Dict[str, str],
                     source_repo: str, source_revision: str,
                     builder_identity: str, build_invocation: str = "",
                     build_level: str = SLSA_BUILD_L1) -> dict:
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
        "runDetails": {"builder": {"id": builder_identity}, "metadata": {}},
        "subjects": [{"name": name, "digest": {"sha256": digest}}
                     for name, digest in sorted(subject_files.items())],
    })
    return payload


def verify_release(artifact_path: str,
                   provenance: dict,
                   policy: IdentityPolicy = None) -> Dict[str, Any]:
    """Verify a release artifact against its provenance.

    v0.5.2: identity authorization is taken from verify_envelope() — the
    authoritative verdict — never re-implemented here. Unsigned provenance
    is NEVER authenticated trust; the builder identity must be cryptographically
    bound (Sigstore bundle verification), not self-asserted.
    """
    policy = policy or IdentityPolicy()
    actual = sha256_file(artifact_path)

    envelope = None
    prov_doc = provenance
    if "payload" in provenance and "provenance" in provenance.get("payload", {}):
        envelope = provenance
        prov_doc = provenance["payload"]["provenance"]

    claimed_builder = (prov_doc.get("builder", {}) or {}).get("id")
    report = stamp({
        "artifact": os.path.basename(artifact_path),
        "digest_match": None,
        "provenance_present": prov_doc is not None,
        "provenance_shape": "SLSA v1.2" if prov_doc else None,
        "signature_status": None,
        "authenticated_identity": None,
        "signing_identity": None,
        "claimed_builder": claimed_builder,
        "authenticated_builder": False,
        # AUTHORIZATION: consumed verbatim from verify_envelope's verdict
        "policy_match": False,
        "source_revision": (prov_doc.get("buildDefinition", {})
                            .get("invocation", {}).get("configSource", {})
                            .get("digest", {}).get("gitCommit")),
        "build_level": prov_doc.get("buildLevel"),
        "trusted": False,
        "facet_notes": [],
    })

    subjects = prov_doc.get("subjects", []) if prov_doc else []
    report["digest_match"] = any(
        s.get("digest", {}).get("sha256") == actual for s in subjects)
    if not report["digest_match"]:
        report["facet_notes"].append("artifact digest not found in provenance subjects")

    if envelope is not None:
        sig = verify_envelope(envelope, policy)
        report["signature_status"] = sig["content"]
        report["signing_identity"] = sig["identity"]
        # authoritative authorization verdict from verify_envelope
        report["policy_match"] = sig["identity"] == IDENTITY_VERIFIED
        report["authenticated_identity"] = sig["authenticated"] is True
    else:
        report["signature_status"] = "UNSIGNED"
        report["facet_notes"].append(
            "provenance is unsigned: builder identity is self-asserted, "
            "not authenticated")

    # authenticated builder = signer verified under policy AND the signer's
    # identity equals the claimed builder (cryptographically bound via the
    # Sigstore bundle; a claim alone proves nothing)
    report["authenticated_builder"] = bool(
        report["authenticated_identity"] and report["policy_match"] and
        envelope is not None and envelope.get("identity") == claimed_builder)

    report["trusted"] = bool(
        report["digest_match"] and report["provenance_present"] and
        report["authenticated_builder"])
    return report
