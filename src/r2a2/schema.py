"""Schema identity and versioning.

Manifests, attestations and published results must stay interpretable after
the code that wrote them is gone. Every artifact therefore carries
``r2a2_schema`` — the version of the *vocabulary* it was written in — with
explicit migration rules. Artifact semantics outlive code versions.
"""

from __future__ import annotations

# Version of R2A2's public scientific vocabulary. Bump on any change to the
# meaning (not just the implementation) of core objects: Claim, Assumption,
# Parameter, Prediction, Test, Comparator, TransformationClass, Evidence,
# Verdict, Domain, Source, ReviewAttestation, Replication.
SCHEMA_VERSION = "0.3"

# Known versions and their forward migrations. A migration takes an artifact
# dict in the old schema and returns the same artifact in the next schema.
# No data is dropped: unrepresentable fields are preserved under "_legacy".
_MIGRATIONS: dict = {
    # "0.2": (lambda doc: {**doc, ...}),  # example shape; 0.2 docs are
    # structurally compatible with 0.3 (only additive fields exist), so the
    # identity migration is implicit — see migrate().
}


class SchemaError(ValueError):
    pass


def check_compatible(doc: dict) -> str:
    """Validate the r2a2_schema field of an artifact. Returns its version."""
    version = doc.get("r2a2_schema")
    if version is None:
        raise SchemaError("artifact missing 'r2a2_schema' field")
    if version != SCHEMA_VERSION and version not in _MIGRATIONS:
        raise SchemaError(
            f"artifact declares schema {version!r}; this build knows "
            f"{SCHEMA_VERSION!r} and migrations {sorted(_MIGRATIONS)}")
    return version


def migrate(doc: dict, to: str = None) -> dict:
    """Bring an artifact forward to a known schema version."""
    to = to or SCHEMA_VERSION
    doc = dict(doc)
    version = doc.get("r2a2_schema")
    if version is None:
        raise SchemaError("cannot migrate an artifact with no r2a2_schema field")
    if version == to:
        return doc
    if version not in _MIGRATIONS:
        raise SchemaError(f"no migration path from {version!r} to {to!r}")
    migrated = _MIGRATIONS[version](doc)
    migrated["r2a2_schema"] = to
    return migrated


def stamp(doc: dict) -> dict:
    """Return a copy of doc stamped with the current schema version."""
    out = dict(doc)
    out["r2a2_schema"] = SCHEMA_VERSION
    return out
