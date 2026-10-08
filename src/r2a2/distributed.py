"""Distributed execution: work units, RNG derivation, checkpoints, retries.

Design rules (v0.6):
- a large execution decomposes into immutable WorkUnits bound to a frozen
  manifest — each carries its own seed/substream derived deterministically
  from (manifest, experiment, work-unit, replicate) identity, NEVER from
  worker scheduling order;
- scientific output must not depend on scheduling order unless the theory
  explicitly declares order dependence;
- a retry of the exact same WorkUnit is not a new scientific trial: retry
  count is provenance, not scientific identity;
- checkpointing preserves scientific identity: mismatched manifest/seed/
  experiment/work-unit → protocol failure.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .compute import ComputeProfile, ExecutionContext
from .failures import ExecutionError, ProtocolError
from .schema import stamp


def derive_seed(manifest_hash: str, experiment: str, work_unit_id: str,
                replicate: int = 0) -> int:
    """Deterministic seed derivation from identity, not scheduling order.

    Worker 3 finishing first must not change the generated ensemble. The
    work-unit dimension and replicate dimension are ORTHOGONAL: the replicate
    stream is salted into the domain so that (unit W0, replicate 0) and
    (unit W0, replicate 0 of a different naming) can never collide with
    another unit's stream.
    """
    blob = f"{manifest_hash}|{experiment}|work-unit={work_unit_id}"
    unit_stream = hashlib.sha256(blob.encode()).digest()
    rep_blob = f"replicate={replicate}".encode()
    combined = hashlib.sha256(unit_stream + rep_blob).digest()
    return int.from_bytes(combined[:8], "big")


@dataclass
class WorkUnit:
    """An immutable unit of work bound to a frozen manifest."""

    work_unit_id: str
    experiment: str
    manifest_hash: str
    args: Dict[str, Any] = field(default_factory=dict)
    replicate: int = 0
    # derived deterministically — never assigned by a scheduler
    seed: int = 0
    backend_request: Optional[Dict[str, Any]] = None
    output_contract: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        self.seed = derive_seed(self.manifest_hash, self.experiment,
                                self.work_unit_id, self.replicate)

    def to_dict(self) -> dict:
        return stamp({
            "work_unit_id": self.work_unit_id, "experiment": self.experiment,
            "manifest_hash": self.manifest_hash, "args": self.args,
            "replicate": self.replicate, "seed": self.seed,
            "backend_request": self.backend_request,
            "output_contract": self.output_contract,
        })


@dataclass
class WorkResult:
    """The scientific result of one work unit, with separate provenance."""

    work_unit_id: str
    payload: Any
    payload_hash: str
    seed: int
    attempts: int = 1               # retry count: provenance, not identity
    provenance: Dict[str, Any] = field(default_factory=dict)


def hash_payload(payload: Any) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def map_work(units: List[WorkUnit], runner, parallel: int = 1) -> List[WorkResult]:
    """Map work units to results. Scheduling order must not change science.

    runner(unit) -> payload. Retry semantics: a retry of the same unit is
    recorded as attempts, never as a new trial.
    """
    results = []
    for unit in units:  # sequential executor; parallel executor wraps this
        attempts = 0
        while True:
            attempts += 1
            try:
                payload = runner(unit)
                break
            except Exception as exc:
                if attempts >= 3:
                    raise ExecutionError(
                        f"work unit {unit.work_unit_id} failed after "
                        f"{attempts} attempts: {exc}") from exc
                # retry the SAME unit — not a new scientific trial
        results.append(WorkResult(
            work_unit_id=unit.work_unit_id, payload=payload,
            payload_hash=hash_payload(payload), seed=unit.seed,
            attempts=attempts,
            provenance={"attempt_log": attempts}))
    return results


def reduce_results(results: List[WorkResult], reducer, deterministic_order: bool = True):
    """Reduce mapped results with FROZEN semantics.

    For floating-point reductions the caller may fix the reduction order —
    order can alter low-order bits, so deterministic reduction order is
    supported and documented. Changing the reducer after seeing results is
    scientifically material.
    """
    payloads = [r.payload for r in results]
    if deterministic_order:
        payloads = sorted(payloads, key=lambda p: json.dumps(p, sort_keys=True, default=str))
    return reducer(payloads)


# --- checkpointing -----------------------------------------------------------

CHECKPOINT_VERSION = 1


@dataclass
class Checkpoint:
    """A checkpoint that preserves scientific identity."""

    manifest_hash: str
    experiment: str
    work_unit_id: str
    backend_id: str
    material_config: str          # compute profile material hash
    progress: Any
    rng_state: Any
    partial_results: Any

    def seal(self) -> str:
        blob = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"),
                          default=str)
        return hashlib.sha256(blob.encode()).hexdigest()[:16]

    def to_dict(self) -> dict:
        return stamp({
            "checkpoint_version": CHECKPOINT_VERSION,
            "manifest_hash": self.manifest_hash,
            "experiment": self.experiment,
            "work_unit_id": self.work_unit_id,
            "backend_id": self.backend_id,
            "material_config": self.material_config,
            "progress": self.progress,
            "rng_state": self.rng_state,
            "partial_results": self.partial_results,
        })

    def save(self, path: str) -> str:
        doc = self.to_dict()
        doc["checkpoint_hash"] = self.seal()
        with open(path, "w") as f:
            json.dump(doc, f, indent=2)
        return path

    @classmethod
    def load(cls, path: str) -> "Checkpoint":
        with open(path) as f:
            doc = json.load(f)
        stored = doc.pop("checkpoint_hash", None)
        cp = cls(
            manifest_hash=doc["manifest_hash"], experiment=doc["experiment"],
            work_unit_id=doc["work_unit_id"], backend_id=doc["backend_id"],
            material_config=doc["material_config"], progress=doc["progress"],
            rng_state=doc["rng_state"], partial_results=doc["partial_results"])
        if stored != cp.seal():
            raise ProtocolError(
                "checkpoint content hash mismatch: the checkpoint was edited "
                "or corrupted")
        if doc.get("checkpoint_version") != CHECKPOINT_VERSION:
            raise ProtocolError(
                f"checkpoint version {doc.get('checkpoint_version')} != "
                f"supported {CHECKPOINT_VERSION}")
        return cp


def validate_checkpoint(cp: Checkpoint, manifest_hash: str, experiment: str,
                        work_unit_id: str, material_config: str = "",
                        backend_id: str = "") -> None:
    """On resume: any identity mismatch is a PROTOCOL failure."""
    mismatches = []
    if cp.manifest_hash != manifest_hash:
        mismatches.append(f"manifest {cp.manifest_hash[:12]} != {manifest_hash[:12]}")
    if experiment and cp.experiment != experiment:
        mismatches.append(f"experiment {cp.experiment!r} != {experiment!r}")
    if work_unit_id and cp.work_unit_id != work_unit_id:
        mismatches.append(f"work unit {cp.work_unit_id!r} != {work_unit_id!r}")
    if material_config and cp.material_config != material_config:
        mismatches.append("compute profile changed")
    if backend_id and cp.backend_id != backend_id:
        mismatches.append(f"backend {cp.backend_id!r} != {backend_id!r}")
    if mismatches:
        raise ProtocolError(
            "checkpoint mismatch: " + "; ".join(mismatches) +
            " — resuming would silently create a different scientific claim")
