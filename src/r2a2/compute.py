"""Compute Fabric: the domain-neutral compute protocol.

Core invariant: scientific semantics ⊥ compute substrate.

Changing CPU→GPU, NumPy→JAX, single→distributed, fresh→resumed must not
silently create a new scientific claim. If a computational change is
scientifically material, R2A2 must expose it — via capability negotiation
(no silent fallback), the compute profile in the frozen manifest, and
explicit reproducibility classes.

The three concepts this module keeps rigorously separate:
- scientifically material compute configuration (e.g. float64 vs float32,
  determinism, tolerance) — part of the frozen manifest;
- incidental execution metadata (GPU serial number, wall time) — provenance
  only, never part of a scientific hash;
- reproducibility class (EXACT / NUMERICAL / STATISTICAL) — how two results
  count as the same scientific result.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .failures import ProtocolError
from .schema import SCHEMA_VERSION, stamp

# --- reproducibility classes -------------------------------------------------

EXACT = "EXACT"                # canonical results must match exactly
NUMERICAL = "NUMERICAL"        # |a - b| <= atol + rtol * |ref| (frozen tol)
STATISTICAL = "STATISTICAL"    # frozen statistical comparison rule


class ReproducibilityRule:
    """A frozen rule for when two results count as the same scientific result.

    Constructed BEFORE any comparison; the tolerances are provenance-bound.
    A tolerance chosen after observing disagreement is a protocol violation.
    """

    def __init__(self, kind: str = NUMERICAL,
                 atol: float = 1e-9, rtol: float = 1e-6,
                 statistical: Optional[Dict[str, Any]] = None):
        if kind not in (EXACT, NUMERICAL, STATISTICAL):
            raise ValueError(f"unknown reproducibility class {kind!r}")
        self.kind = kind
        self.atol = float(atol)
        self.rtol = float(rtol)
        self.statistical = statistical or {}

    def check(self, a: Any, b: Any) -> Dict[str, Any]:
        """Compare two results under the frozen rule. Returns a verdict dict."""
        if self.kind == EXACT:
            agrees = a == b
            detail = "exact equality" if agrees else "values differ"
        elif self.kind == NUMERICAL:
            try:
                diff = abs(float(a) - float(b))
                tol = self.atol + self.rtol * abs(float(b))
                agrees = diff <= tol
                detail = f"|Δ|={diff:.3e} vs tol={tol:.3e} (atol={self.atol}, rtol={self.rtol})"
            except (TypeError, ValueError):
                agrees = False
                detail = "non-numeric results under NUMERICAL rule"
        elif self.kind == STATISTICAL:
            agrees, detail = self._statistical_check(a, b)
        return {"agrees": agrees, "detail": detail, "rule": self.to_dict()}

    def _statistical_check(self, a, b):
        stat = self.statistical
        method = stat.get("method", "mean-z")
        try:
            if method == "mean-z":
                import math
                ma, mb = float(a["mean"]), float(b["mean"])
                sa, sb = float(a.get("std", 0)), float(b.get("std", 0))
                na, nb = int(a.get("n", 1)), int(b.get("n", 1))
                z_threshold = float(stat.get("z_threshold", 3.0))
                se = math.sqrt(max(sa * sa / na + sb * sb / nb, 1e-300))
                z = abs(ma - mb) / se if se > 0 else 0.0
                return z <= z_threshold, f"z={z:.3f} <= {z_threshold} (mean-z test)"
            if method == "ks":
                from .stats import ks_test  # optional helper
                d, p = ks_test(a["samples"], b["samples"])
                alpha = float(stat.get("alpha", 0.05))
                return p >= alpha, f"KS d={d:.4f}, p={p:.4f} >= {alpha}"
        except (KeyError, TypeError) as exc:
            return False, f"statistical rule misapplied: {exc}"
        return False, f"unknown statistical method {method!r}"

    def to_dict(self) -> dict:
        d = {"kind": self.kind}
        if self.kind == NUMERICAL:
            d.update({"atol": self.atol, "rtol": self.rtol})
        if self.kind == STATISTICAL:
            d["statistical"] = self.statistical
        return d

    def hash(self) -> str:
        """Frozen rule hash — provenance-bound before any comparison."""
        blob = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode()).hexdigest()[:16]


# --- capability negotiation --------------------------------------------------

# capabilities a workload may REQUIRE (never silently degraded)
CAP_CPU = "cpu"
CAP_GPU = "gpu"
CAP_FLOAT64 = "float64"
CAP_FLOAT32 = "float32"
CAP_DETERMINISTIC = "deterministic"
CAP_DISTRIBUTED = "distributed"
CAP_CHECKPOINT = "checkpoint"
CAP_EXTERNAL = "external-executable"


@dataclass
class ResourceRequest:
    """What the workload requires. Requirements are never silently degraded."""

    capabilities: List[str] = field(default_factory=lambda: [CAP_CPU])
    min_devices: int = 1
    min_memory_gb: float = 0.0
    allow_fallback: bool = False   # only explicit fallback is permitted

    def to_dict(self) -> dict:
        return {"capabilities": sorted(self.capabilities),
                "min_devices": self.min_devices,
                "min_memory_gb": self.min_memory_gb,
                "allow_fallback": self.allow_fallback}


@dataclass
class BackendDescriptor:
    """What a backend provides. Probed, never assumed."""

    backend_id: str
    version: str = ""
    capabilities: List[str] = field(default_factory=list)
    devices: int = 1
    device_type: str = "cpu"
    precision_realized: str = "float64"
    deterministic: bool = False
    distributed: bool = False
    checkpoint_support: bool = False
    extra: Dict[str, Any] = field(default_factory=dict)

    def satisfies(self, request: ResourceRequest) -> tuple:
        """(ok, missing) — requirements must be fully met, no silent degrade."""
        missing = [c for c in request.capabilities if c not in self.capabilities]
        ok = (not missing
              and self.devices >= request.min_devices)
        return ok, missing


def negotiate(request: ResourceRequest, available: List[BackendDescriptor],
              requested_backend: Optional[str] = None) -> BackendDescriptor:
    """Select a backend that fully satisfies the request.

    Protocol failure BEFORE scientific execution if no backend qualifies.
    A performance preference may fall back only when the request explicitly
    allows it — and fallback never drops a required capability.
    """
    if requested_backend:
        candidates = [b for b in available if b.backend_id == requested_backend]
        if not candidates:
            raise ProtocolError(
                f"requested backend {requested_backend!r} not available; "
                f"installed: {[b.backend_id for b in available]}")
    else:
        candidates = available
    for b in candidates:
        ok, missing = b.satisfies(request)
        if ok:
            return b
    raise ProtocolError(
        f"no backend satisfies required capabilities {sorted(request.capabilities)}; "
        f"missing across candidates: {missing}. "
        "R2A2 never silently degrades a scientific requirement.")


# --- compute profile (frozen into the manifest where material) ---------------

@dataclass
class ComputeProfile:
    """Scientifically material compute configuration.

    Fields here become part of the execution identity when set. Incidental
    metadata (device serials, wall time) belongs in the fingerprint's
    provenance section, NOT here.
    """

    precision_policy: Optional[str] = None      # e.g. "float64"
    seed_policy: Optional[Dict[str, Any]] = None  # {"seed": 42, "rng": "philox"}
    determinism_required: bool = False
    backend_family: Optional[str] = None        # scientifically fixed family
    device_class: Optional[str] = None          # e.g. "gpu" when material
    distributed_topology: Optional[Dict[str, Any]] = None
    tolerance_policy: Optional[Dict[str, Any]] = None
    checkpoint_policy: Optional[str] = None     # "none" | "allowed" | "required"
    resources: Optional[ResourceRequest] = None
    reproducibility: Optional[ReproducibilityRule] = None

    def material_hash(self) -> str:
        """Hash over only the scientifically material fields."""
        d = {k: v for k, v in {
            "precision": self.precision_policy,
            "seed": self.seed_policy,
            "determinism": self.determinism_required or None,
            "backend_family": self.backend_family,
            "device_class": self.device_class,
            "distributed": self.distributed_topology,
            "tolerance": self.tolerance_policy,
            "checkpoint": self.checkpoint_policy,
            "resources": self.resources.to_dict() if self.resources else None,
            "reproducibility": self.reproducibility.to_dict() if self.reproducibility else None,
        }.items() if v is not None}
        blob = json.dumps(d, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode()).hexdigest()[:16] if d else ""


# --- fingerprints ------------------------------------------------------------

def _nonvolatile_fingerprint() -> Dict[str, Any]:
    return {
        "python": sys.version.split()[0],
        "platform": platform.system(),
        "machine": platform.machine(),
    }


class ExecutionContext:
    """Binds a request + backend + profile into an executable context, with a
    fingerprint separating scientific identity from provenance."""

    def __init__(self, backend: BackendDescriptor, profile: ComputeProfile,
                 manifest_hash: str = ""):
        self.backend = backend
        self.profile = profile
        self.manifest_hash = manifest_hash
        # fail fast: the negotiated backend must still satisfy the profile
        if profile.precision_policy and profile.precision_policy not in \
                backend.capabilities and backend.precision_realized != profile.precision_policy:
            raise ProtocolError(
                f"profile requires precision {profile.precision_policy!r} but "
                f"backend {backend.backend_id!r} realizes "
                f"{backend.precision_realized!r}")

    def compute_fingerprint(self) -> Dict[str, Any]:
        """Scientific fingerprint (material) + provenance (non-volatile)."""
        return stamp({
            "material": self.profile.material_hash(),
            "backend": {
                "id": self.backend.backend_id,
                "version": self.backend.version,
                "device_type": self.backend.device_type,
                "devices": self.backend.devices,
                "precision_realized": self.backend.precision_realized,
                "deterministic": self.backend.deterministic,
            },
            "reproducibility_rule_hash": (
                self.profile.reproducibility.hash()
                if self.profile.reproducibility else None),
            "environment": _nonvolatile_fingerprint(),
            "manifest_hash": self.manifest_hash,
        })


class ComputeRequest:
    """A unit of computation sent to a backend."""

    def __init__(self, experiment: str, work_unit_id: str = "",
                 args: Optional[Dict[str, Any]] = None,
                 seed: Optional[int] = None):
        self.experiment = experiment
        self.work_unit_id = work_unit_id
        self.args = args or {}
        self.seed = seed


class ComputeResult:
    """A backend's response: scientific payload + provenance metadata."""

    def __init__(self, payload: Any, backend_id: str, fingerprint: dict,
                 provenance: Optional[Dict[str, Any]] = None):
        self.payload = payload
        self.backend_id = backend_id
        self.fingerprint = fingerprint
        self.provenance = provenance or {}   # wall time etc. — NOT in payload hash

    def payload_hash(self) -> str:
        blob = json.dumps(self.payload, sort_keys=True, separators=(",", ":"),
                          default=str)
        return hashlib.sha256(blob.encode()).hexdigest()[:16]


# --- the protocol every backend implements -----------------------------------

class ComputeBackend:
    """Domain-neutral backend protocol. Implement probe/capabilities/prepare/
    execute/fingerprint. Optional: checkpoint/resume/cancel.

    JAX-, Torch-, CUDA-, MPI- or Slurm-specific concepts must NOT appear here
    or in the theory model; they belong behind this interface.
    """

    descriptor: BackendDescriptor

    def probe(self) -> BackendDescriptor:
        raise NotImplementedError

    def capabilities(self) -> List[str]:
        return self.descriptor.capabilities

    def prepare(self, request: ComputeRequest, ctx: ExecutionContext):
        return request

    def execute(self, request: ComputeRequest, ctx: ExecutionContext) -> ComputeResult:
        raise NotImplementedError

    def fingerprint(self) -> Dict[str, Any]:
        return self.descriptor.__dict__

    # optional
    def checkpoint(self, ctx: ExecutionContext, state: Any) -> bytes:
        raise NotImplementedError("checkpoint not supported by this backend")

    def resume(self, ctx: ExecutionContext, state: bytes):
        raise NotImplementedError("checkpoint not supported by this backend")
