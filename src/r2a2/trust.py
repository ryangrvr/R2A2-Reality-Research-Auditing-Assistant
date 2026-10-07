"""Independent implementation protocol and hash-bound review attestations.

The trust layer: can you believe that another person independently reproduced
and reviewed this exact result?

Replication. A test may declare two implementations with a frozen agreement
rule (|x_A - x_B| < tau, or structural equality of machine-readable output).
Not all "two implementations" are equal, so the independence *level* is part
of the evidence:

    L1  same algorithm, separate code        (catches coding errors)
    L2  separate algorithm, same equations   (catches method errors)
    L3  independent derivation + implementation (catches conception errors)

An L3 agreement is stronger evidence than an L1 agreement; the record keeps
which level was claimed so downstream audits can weigh it.

Review attestations. A reviewer attests to ARTIFACTS, not prose:

    attestation = H(manifest) + H(result) + code revision + scope + reviewer

If anything attested changes, the attestation no longer applies — verified by
hash comparison, not by reading a README.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from .canonical import canonical_hash
from .schema import SCHEMA_VERSION, stamp

INDEPENDENCE_LEVELS = ("L1-same-algorithm-separate-code",
                       "L2-separate-algorithm-same-equations",
                       "L3-independent-derivation-and-implementation")


@dataclass
class Implementation:
    """One implementation of a test. `derivation` documents how it came to be,
    which determines the independence level it can honestly claim."""

    name: str
    code_hash: str                                   # hash of the implementing code
    derivation_ref: str = ""                         # id of the derivation it implements
    derived_independently: bool = False              # True only for L3


@dataclass
class AgreementRule:
    """Frozen before results are opened."""

    kind: str = "tolerance"                          # "tolerance" | "structural"
    tolerance: Optional[float] = None                # |x_A - x_B| < tolerance
    observable: str = ""                             # which value to compare

    def check(self, a: Any, b: Any) -> tuple:
        """Returns (agrees: bool, detail: str)."""
        if self.kind == "structural":
            agrees = canonical_hash(a) == canonical_hash(b)
            return agrees, "structural equality of machine-readable output"
        if self.tolerance is None:
            raise ValueError("tolerance rule requires a tolerance value")
        try:
            delta = abs(float(a) - float(b))
        except (TypeError, ValueError):
            return False, f"non-numeric values: {a!r} vs {b!r}"
        return delta < self.tolerance, f"|{a} - {b}| = {delta} < {self.tolerance}"


@dataclass
class Replication:
    """The record of an A/B replication attempt."""

    test_id: str
    impl_a: Implementation
    impl_b: Implementation
    rule: AgreementRule
    value_a: Any = None
    value_b: Any = None
    manifest_hash: str = ""

    @property
    def independence_level(self) -> str:
        a, b = self.impl_a, self.impl_b
        if a.derived_independently and b.derived_independently and \
                a.derivation_ref != b.derivation_ref:
            return INDEPENDENCE_LEVELS[2]
        if a.derivation_ref == b.derivation_ref:
            return INDEPENDENCE_LEVELS[0]
        return INDEPENDENCE_LEVELS[1]

    def to_record(self) -> dict:
        """Complete, content-addressable record.

        Binds the frozen AgreementRule (so tolerance cannot be changed after
        seeing results), both implementations' derivation references and code
        hashes, the independence claims, and the values compared. The
        independence level is a **declared and evidenced grade**: R2A2 records
        the claim and its evidence; it cannot verify derivation independence
        from strings alone.
        """
        return stamp({
            "test_id": self.test_id,
            "rule": {"kind": self.rule.kind,
                     "tolerance": self.rule.tolerance,
                     "observable": self.rule.observable},
            "impl_a": {"name": self.impl_a.name,
                       "code_hash": self.impl_a.code_hash,
                       "derivation_ref": self.impl_a.derivation_ref,
                       "derived_independently": self.impl_a.derived_independently},
            "impl_b": {"name": self.impl_b.name,
                       "code_hash": self.impl_b.code_hash,
                       "derivation_ref": self.impl_b.derivation_ref,
                       "derived_independently": self.impl_b.derived_independently},
            "independence_level": self.independence_level,
            "independence_note": ("declared and evidenced grade, not verified "
                                  "by R2A2 from strings alone"),
            "value_a": self.value_a, "value_b": self.value_b,
            "manifest_hash": self.manifest_hash,
        })

    def evaluate(self) -> Dict[str, Any]:
        agrees, detail = self.rule.check(self.value_a, self.value_b)
        record = self.to_record()
        record.update({
            "agrees": agrees,
            "detail": detail,
            "record_hash": canonical_hash(record),
        })
        return record


# --------------------------------------------------------------------------
# Review attestations
# --------------------------------------------------------------------------

@dataclass
class ReviewAttestation:
    """A reviewer's attestation bound to the artifact hashes being reviewed."""

    reviewer: str
    scope: str                       # e.g. "theorem:T3 + result:R7"
    manifest_hash: str
    result_hash: str
    code_revision: str               # repository SHA or equivalent
    verdict: str                     # reviewer's verdict within the scope
    notes: str = ""
    issues: list = field(default_factory=list)   # open issues, if any

    def seal(self) -> str:
        """Content-address the attestation.

        Hashes EVERY semantically relevant field: reviewer, scope, artifact
        hashes, revision, verdict, notes, issues AND the schema version.
        Editing any of these — including the issue state that controls whether
        the attestation applies — invalidates the seal.
        """
        return canonical_hash(stamp({
            "reviewer": self.reviewer, "scope": self.scope,
            "manifest_hash": self.manifest_hash, "result_hash": self.result_hash,
            "code_revision": self.code_revision, "verdict": self.verdict,
            "notes": self.notes, "issues": sorted(map(str, self.issues)),
        }))

    def covers(self, manifest_hash: str, result_hash: str,
               code_revision: str) -> bool:
        """An attestation applies ONLY to the exact artifacts it reviewed."""
        return (self.manifest_hash == manifest_hash
                and self.result_hash == result_hash
                and self.code_revision == code_revision)

    def to_dict(self) -> dict:
        return stamp({
            "reviewer": self.reviewer, "scope": self.scope,
            "manifest_hash": self.manifest_hash, "result_hash": self.result_hash,
            "code_revision": self.code_revision, "verdict": self.verdict,
            "notes": self.notes, "issues": self.issues, "seal": self.seal(),
        })


def verify_attestation(attestation: ReviewAttestation, manifest_hash: str,
                       result_hash: str, code_revision: str,
                       sealed_as: str = None) -> Dict[str, Any]:
    """Check an attestation against the artifacts at hand.

    sealed_as: the seal recorded when the attestation was stored. If given,
    the current content must reproduce it — this is how post-hoc tampering
    with the verdict is detected.
    """
    covers = attestation.covers(manifest_hash, result_hash, code_revision)
    current_seal = attestation.seal()
    seal_ok = sealed_as is None or sealed_as == current_seal
    return stamp({
        "applies": covers and seal_ok and not attestation.issues,
        "covers_artifacts": covers,
        "seal_intact": seal_ok,
        "open_issues": len(attestation.issues),
    })
