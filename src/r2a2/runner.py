"""Deterministic local runner.

Executes a compiled manifest's tests and predictions through a backend and
attaches results to the ledger as evidence records — never rewriting the
preregistered graph.
"""

from __future__ import annotations

import time
from typing import Dict

from .api import Theory
from .backends import get_backend
from .compiler import ExecutionManifest
from .ledger import Ledger


class RunResult:
    def __init__(self, manifest_hash: str):
        self.manifest_hash = manifest_hash
        self.records: list = []          # one per executed experiment
        self.started = time.time()

    def add_record(self, node_id, experiment, backend, result, wall_time):
        self.records.append({
            "node": node_id,
            "experiment": experiment,
            "backend": backend,
            "manifest_hash": self.manifest_hash,
            "wall_time": wall_time,
            "result": result,
        })


def run_manifest(theory: Theory, manifest: ExecutionManifest, ledger: Ledger,
                 backend_name: str | None = None) -> RunResult:
    """Run every experiment referenced by the theory's tests and predictions.

    Deterministic when the manifest pins a seed. Results attach to the graph
    as new ``result:*`` nodes with provenance back to the frozen manifest.
    """
    backend = get_backend(backend_name or manifest.backend,
                          **({"seed": manifest.seeds.get("default")} if manifest.seeds else {}))
    res = RunResult(manifest.hash or "<unfrozen>")

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
