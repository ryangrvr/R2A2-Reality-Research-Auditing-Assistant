"""Deterministic local runner.

Executes a compiled manifest's tests and predictions through a backend and
attaches results to the ledger as evidence records — never rewriting the
preregistered graph.

v0.3.3: **binding the protocol != enforcing the binding.** Nothing executes
unless the live execution context matches the frozen manifest:

- the manifest must be frozen (an unfrozen manifest is a protocol failure);
- the live theory's declaration hash and experiment code bindings must match
  the frozen ones (a swapped or body-edited callable aborts before running);
- the backend must be the one frozen into the manifest.

Every abort is a ``ProtocolError`` (protocol-failure), never an execution.
"""

from __future__ import annotations

import time
from typing import Dict

from .api import Theory
from .backends import get_backend
from .compiler import (ExecutionManifest, canonical_hash, code_binding,
                       declaration_hash_of)
from .failures import ProtocolError
from .ledger import Ledger


class RunResult:
    def __init__(self, manifest_hash: str):
        self.manifest_hash = manifest_hash
        self.records: list = []          # one per executed experiment
        self.started = time.time()

    def add_record(self, node_id, experiment, backend, result, wall_time):
        """Records carry a canonical result_hash over the scientific payload;
        wall time is kept as metadata OUTSIDE the hashed content."""
        payload = {
            "node": node_id,
            "experiment": experiment,
            "backend": backend,
            "manifest_hash": self.manifest_hash,
            "result": result,
        }
        self.records.append({**payload,
                             "result_hash": canonical_hash(payload),
                             "wall_time": wall_time})


def _enforce_frozen_context(theory: Theory, manifest: ExecutionManifest,
                            backend_name: str | None) -> None:
    """Abort as a PROTOCOL failure if the live context diverges from the
    frozen manifest. Called before the first experiment executes."""
    if not manifest.frozen or not manifest.hash:
        raise ProtocolError(
            "manifest is not frozen; nothing may execute against an "
            "unfrozen manifest (freeze it first)")
    if backend_name is not None and backend_name != manifest.backend:
        raise ProtocolError(
            f"backend {backend_name!r} does not match the frozen backend "
            f"{manifest.backend!r}; changing backends requires a new manifest")
    if declaration_hash_of(theory) != manifest.theory_declaration_hash:
        raise ProtocolError(
            "live theory declaration hash does not match the frozen manifest; "
            "the theory changed after freezing (kill conditions, assumptions, "
            "parameters, bindings or other scientific content). "
            "Recompile and refreeze instead of executing divergent code.")
    for name, binding in manifest.experiment_bindings.items():
        fn = theory.experiments.get(name)
        if fn is None:
            raise ProtocolError(
                f"experiment {name!r} present in the frozen manifest but "
                "missing from the live theory")
        live = code_binding(fn)
        if live != binding:
            raise ProtocolError(
                f"experiment {name!r} code binding changed after freeze: "
                f"frozen {binding.get('ref')}/{str(binding.get('source_hash'))[:12]}"
                f" -> live {live.get('ref')}/{str(live.get('source_hash'))[:12]}. "
                "The frozen manifest no longer describes the executing code; "
                "refreeze or restore the original implementation.")


def run_manifest(theory: Theory, manifest: ExecutionManifest, ledger: Ledger,
                 backend_name: str | None = None) -> RunResult:
    """Run every experiment referenced by the theory's tests and predictions.

    Deterministic when the manifest pins a seed. Results attach to the graph
    as new ``result:*`` nodes with provenance back to the frozen manifest,
    each carrying a canonical result_hash (wall time excluded).
    """
    _enforce_frozen_context(theory, manifest, backend_name)

    backend = get_backend(manifest.backend,
                          **({"seed": manifest.seeds.get("default")}
                             if manifest.seeds else {}))
    if backend.name != manifest.backend:
        raise ProtocolError(
            f"resolved backend {backend.name!r} does not match the frozen "
            f"backend {manifest.backend!r}")
    res = RunResult(manifest.hash)

    experiments = sorted({t.experiment for t in theory.tests} |
                         {p.experiment for p in theory.predictions})
    for exp in experiments:
        t0 = time.time()
        result = backend.run_experiment(theory, exp)
        res.add_record(exp, exp, backend.name, result, time.time() - t0)
        node_id = f"result:{exp}"
        if node_id not in ledger.nodes:
            # attach to whichever predictions/tests use this experiment; do NOT
            # alter the preregistered nodes themselves
            users = [f"predict:{p.id}" for p in theory.predictions if p.experiment == exp]
            users += [f"test:{t.id}" for t in theory.tests if t.experiment == exp]
            ledger.add(node_id, "result", deps=users, backend=backend.name,
                       manifest_hash=res.manifest_hash)
    return res
