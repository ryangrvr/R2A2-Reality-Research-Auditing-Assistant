"""Canonical manifest hashing: the specification.

The manifest hash is scientific provenance, so it must be invariant to
non-semantic variation and sensitive to semantic variation.

INVARIANT (same hash):
- JSON key insertion order;
- whitespace/formatting;
- file location or path separators (paths are normalized to forward slashes
  and basenames are hashed relative to the project root when provided);
- tuple vs list (both normalize to lists);
- platform differences that don't affect the values.

SENSITIVE (different hash):
- a threshold value;
- a parameter source;
- an assumption text;
- an input dataset id/hash;
- code involved in the test (via source hashes supplied by the caller);
- the backend, when declared scientifically relevant.

Implementation: recursive canonicalization to JSON with sorted keys, compact
separators, then SHA-256. This module is the single place that defines the
rule, so the spec is testable.
"""

from __future__ import annotations

import hashlib
import json
import posixpath
from typing import Any


def _normalize(value: Any) -> Any:
    """Recursively canonicalize a JSON-like structure."""
    if isinstance(value, dict):
        return {str(k): _normalize(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
    if isinstance(value, (list, tuple)):
        return [_normalize(v) for v in value]
    if isinstance(value, bool) or value is None or isinstance(value, (int, float, str)):
        return value
    return str(value)  # fallback: deterministic stringification


def normalize_path(path: str) -> str:
    """Path-separator-independent, location-independent path key."""
    return posixpath.normpath(path.replace("\\", "/"))


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(_normalize(value), sort_keys=True,
                      separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def canonical_hash(value: Any) -> str:
    """SHA-256 of the canonical form. THE definition used everywhere."""
    return hashlib.sha256(canonical_bytes(value)).hexdigest()
