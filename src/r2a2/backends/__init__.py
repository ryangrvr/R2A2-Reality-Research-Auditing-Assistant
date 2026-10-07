"""Compute fabric: the backend protocol.

Pillar 2. Scientific semantics are separated from numerical execution. The
theory API never names a tensor library. Backends declare capabilities; the
engine (and audit semantics) never depends on which backend ran.
"""

from __future__ import annotations

from typing import Any, Dict, Protocol, runtime_checkable


@runtime_checkable
class Backend(Protocol):
    """Compute backend protocol. Implement this to add JAX, torch, subprocess..."""

    name: str

    def capabilities(self) -> Dict[str, Any]:
        """accelerator, precision, autodiff, vectorization, deterministic..."""
        ...

    def run_experiment(self, theory: Any, experiment: str, **kwargs) -> Any:
        """Execute one named experiment of a theory."""
        ...


class LocalBackend:
    """The general deterministic local executor.

    Runs the theory's own experiment callables with plain Python; any NumPy
    the theory itself uses is its choice, not the backend's. This separates
    execution policy from the numerical library: capability adapters such as
    NumPyBackend/JAXBackend/TorchBackend sit in front of LocalBackend later.
    """

    name = "local"

    def __init__(self, seed: int | None = None):
        self.seed = seed

    def capabilities(self) -> Dict[str, Any]:
        return {
            "accelerator": False,
            "precision": "float64",
            "autodiff": False,
            "vectorization": "numpy-if-present",
            "distributed": False,
            "deterministic": self.seed is not None,
        }

    def run_experiment(self, theory, experiment: str, **kwargs):
        if experiment not in theory.experiments:
            raise KeyError(f"theory {theory.id!r} has no experiment {experiment!r}")
        if self.seed is not None:
            _seed_everything(self.seed)
        result = theory.experiments[experiment](**kwargs)
        if not isinstance(result, dict):
            raise TypeError(
                f"experiment {experiment!r} must return a machine-readable dict, "
                f"got {type(result).__name__}"
            )
        return result


def _seed_everything(seed: int) -> None:
    import random
    random.seed(seed)
    try:
        import numpy as np
        np.random.seed(seed)
    except Exception:
        pass  # numpy optional; a broken numpy must not break the local runner


def get_backend(name: str = "local", **kwargs) -> Backend:
    """Resolve a backend by name. Third-party backends may register here later."""
    if name in ("local", "local-numpy"):  # old name kept as an alias
        return LocalBackend(**kwargs)
    raise KeyError(f"unknown backend {name!r} (installed: local)")
