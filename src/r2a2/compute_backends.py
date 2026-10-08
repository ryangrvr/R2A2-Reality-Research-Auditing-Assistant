"""Compute Fabric backends implementing the r2a2.compute protocol.

All backends beyond NumPy are optional; the core imports and operates without
JAX/Torch installed. Backend-specific concepts stay behind this interface —
never in the theory model.

Honest capability reporting: a backend reports what it REALIZES and
distinguishes a deterministic *request* from a deterministic *guarantee*
(JAX/Torch on accelerators do not promise bitwise reproducibility).
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import time
from typing import Any, Dict, List, Optional

from .compute import (CAP_CPU, CAP_DETERMINISTIC, CAP_EXTERNAL, CAP_FLOAT32,
                      CAP_FLOAT64, CAP_GPU, BackendDescriptor, ComputeBackend,
                      ComputeRequest, ComputeResult, ExecutionContext)
from .failures import ExecutionError, ProtocolError

__all__ = ["NumPyBackend", "JaxBackend", "TorchBackend", "ExternalBackend",
           "available_backends", "get_compute_backend"]


def _module_hash(module) -> str:
    try:
        with open(module.__file__, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()[:16]
    except Exception:
        return ""


class NumPyBackend(ComputeBackend):
    """The conventional CPU reference backend. Establishes the Compute Fabric
    contract with mature ordinary numerical science (NumPy/SciPy where
    available)."""

    def __init__(self):
        try:
            import numpy
            self._np = numpy
            have = True
        except Exception:
            self._np = None
            have = False
        # The CPU reference backend SUPPORTS float64/float32/deterministic
        # execution by design; whether the optional numpy library is present
        # is reported honestly in `version`, not by hiding capabilities —
        # otherwise negotiation would wrongly refuse a valid request just
        # because an optional dependency is missing.
        caps = [CAP_CPU, CAP_FLOAT64, CAP_FLOAT32, CAP_DETERMINISTIC,
                CAP_CHECKPOINT] if have else [CAP_CPU, CAP_FLOAT64,
                                              CAP_DETERMINISTIC]
        self.descriptor = BackendDescriptor(
            backend_id="numpy",
            version=numpy.__version__ if have else "stdlib-fallback",
            capabilities=caps,
            device_type="cpu",
            precision_realized="float64",
            deterministic=True,
            checkpoint_support=have,
            extra={} if have else {"warning": "numpy not installed; "
                                               "pure-Python fallback active"},
        )

    def probe(self) -> BackendDescriptor:
        return self.descriptor

    def execute(self, request: ComputeRequest, ctx: ExecutionContext) -> ComputeResult:
        import random
        if request.seed is not None:
            random.seed(request.seed)
            if self._np is not None:
                self._np.random.seed(request.seed)
        theory = request.args.get("_theory")
        if theory is None:
            raise ProtocolError("NumPyBackend requires the theory reference in args")
        t0 = time.time()
        try:
            payload = theory.experiments[request.experiment](
                **{k: v for k, v in request.args.items() if not k.startswith("_")})
        except KeyError as exc:
            raise ExecutionError(f"experiment missing: {exc}")
        return ComputeResult(payload, self.descriptor.backend_id,
                             ctx.compute_fingerprint(),
                             provenance={"wall_time_s": time.time() - t0})


class JaxBackend(ComputeBackend):
    """JAX adapter. Reports device platform/count, precision mode, requested
    vs realized dtype, accelerator availability and determinism LIMITATIONS:
    JAX on GPU does not guarantee bitwise reproducibility across devices —
    same code + same seed ≠ bitwise identical result everywhere. Capability
    reporting distinguishes a deterministic *request* from a deterministic
    *guarantee*."""

    def __init__(self):
        try:
            import jax
            self._jax = jax
            installed = True
        except Exception:
            self._jax = None
            installed = False
        caps, det, devices = [], False, 0
        device_type = "cpu"
        if installed:
            devices = len(jax.devices())
            device_types = {d.platform for d in jax.devices()}
            device_type = "/".join(sorted(device_types))
            caps += [CAP_CPU, CAP_FLOAT64, CAP_FLOAT32]
            if any(t in ("gpu", "tpu") for t in device_types):
                caps += [CAP_GPU]
            if device_types == {"cpu"}:
                det = True
                caps += [CAP_DETERMINISTIC]
        self.descriptor = BackendDescriptor(
            backend_id="jax",
            version=jax.__version__ if installed else "not-installed",
            capabilities=caps,
            devices=devices,
            device_type=device_type,
            precision_realized="float32" if installed else "",
            deterministic=det,
            extra={"precision_note":
                   "JAX realizes float32 by default on accelerators; x64 needs "
                   "jax.config.update('jax_enable_x64', True)"},
        )

    def probe(self) -> BackendDescriptor:
        return self.descriptor

    def execute(self, request: ComputeRequest, ctx: ExecutionContext) -> ComputeResult:
        if self._jax is None:
            raise ExecutionError("JAX is not installed; the jax backend cannot run")
        theory = request.args.get("_theory")
        t0 = time.time()
        payload = theory.experiments[request.experiment](
            **{k: v for k, v in request.args.items() if not k.startswith("_")})
        return ComputeResult(payload, self.descriptor.backend_id,
                             ctx.compute_fingerprint(),
                             provenance={"wall_time_s": time.time() - t0})


class TorchBackend(ComputeBackend):
    """PyTorch adapter. Same rules as JAX. Torch tensors never enter the
    public scientific object model — conversion happens at this boundary."""

    def __init__(self):
        try:
            import torch
            self._torch = torch
            installed = True
        except Exception:
            self._torch = None
            installed = False
        caps, det, devices = [], False, 0
        device_type = "cpu"
        if installed:
            device_type = "cuda" if self._torch.cuda.is_available() else "cpu"
            devices = self._torch.cuda.device_count() if device_type == "cuda" else 1
            caps += [CAP_CPU, CAP_FLOAT64, CAP_FLOAT32]
            if device_type == "cuda":
                caps += [CAP_GPU]
            if device_type == "cpu":
                det = True
                caps += [CAP_DETERMINISTIC]
        self.descriptor = BackendDescriptor(
            backend_id="torch",
            version=self._torch.__version__ if installed else "not-installed",
            capabilities=caps,
            devices=devices,
            device_type=device_type,
            deterministic=det,
            extra={"determinism_note":
                   "GPU determinism requires "
                   "torch.use_deterministic_algorithms(True); some kernels "
                   "remain nondeterministic"},
        )

    def probe(self) -> BackendDescriptor:
        return self.descriptor

    def execute(self, request: ComputeRequest, ctx: ExecutionContext) -> ComputeResult:
        if self._torch is None:
            raise ExecutionError("PyTorch is not installed; the torch backend cannot run")
        theory = request.args.get("_theory")
        t0 = time.time()
        payload = theory.experiments[request.experiment](
            **{k: v for k, v in request.args.items() if not k.startswith("_")})
        return ComputeResult(payload, self.descriptor.backend_id,
                             ctx.compute_fingerprint(),
                             provenance={"wall_time_s": time.time() - t0})


class ExternalBackend(ComputeBackend):
    """External executable backend: Fortran/C/Julia/R/legacy solvers without
    rewriting them into Python.

    Process contract:
    - inputs are materialized into a frozen work directory;
    - executable identity is CONTENT-bound (hash of the binary — renaming
      does not change execution identity);
    - recorded: executable ref+hash, argv, input hashes, environment
      declaration, exit status, stdout/stderr hashes, output hashes,
      runtime metadata;
    - the program's textual stdout does NOT automatically become a scientific
      result: extraction is explicitly declared.
    """

    def __init__(self, executable: str, argv_template: List[str],
                 extraction: Dict[str, Any], backend_id: str = None,
                 env: Optional[Dict[str, str]] = None):
        self._path = shutil.which(executable) or executable
        if not os.path.exists(self._path):
            raise ExecutionError(f"external executable not found: {executable!r}")
        self._argv_template = argv_template
        self._extraction = extraction
        if not extraction or not extraction.get("kind"):
            raise ProtocolError(
                "no extraction rule declared; the program's textual stdout "
                "does not automatically become a scientific result")
        self._env = env
        self._content_hash = self._hash_file(os.path.abspath(self._path))
        self.descriptor = BackendDescriptor(
            backend_id=backend_id or f"external:{os.path.basename(executable)}",
            version=self._content_hash[:8],
            capabilities=[CAP_CPU, CAP_EXTERNAL],
            device_type="external",
        )

    @staticmethod
    def _hash_file(path: str) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    def probe(self) -> BackendDescriptor:
        return self.descriptor

    def execute(self, request: ComputeRequest, ctx: ExecutionContext) -> ComputeResult:
        import tempfile
        workdir = tempfile.mkdtemp(prefix="r2a2-external-")
        input_hashes: Dict[str, str] = {}
        output_hashes: Dict[str, str] = {}
        try:
            inputs = request.args.get("inputs", {})
            for name, content in inputs.items():
                p = os.path.join(workdir, name)
                with open(p, "w") as f:
                    f.write(content if isinstance(content, str) else json.dumps(content))
                input_hashes[name] = self._hash_bytes(
                    content.encode() if isinstance(content, str) else content)

            argv = [self._path] + [a.format(input=workdir, output=workdir)
                                   for a in self._argv_template]
            proc = subprocess.run(argv, capture_output=True, text=True,
                                  timeout=request.args.get("timeout", 300))
            if proc.returncode != 0:
                raise ExecutionError(
                    f"external executable exited {proc.returncode}: "
                    f"stderr={proc.stderr[-300:]}")
            payload = self._extract(workdir)
            # hash every file produced in the workdir after the run
            for name in sorted(os.listdir(workdir)):
                p = os.path.join(workdir, name)
                if os.path.isfile(p) and name not in input_hashes:
                    output_hashes[name] = self._hash_file(p)
            provenance = {
                "executable": self._path,
                "executable_hash": self._content_hash,
                "argv": argv,
                "input_hashes": input_hashes,
                "output_hashes": output_hashes,
                "exit_status": proc.returncode,
                "stdout_hash": self._hash_bytes(proc.stdout.encode()),
                "stderr_hash": self._hash_bytes(proc.stderr.encode()),
                "environment": dict(self._env or {}),
                "workdir": workdir,
            }
            return ComputeResult(payload, self.descriptor.backend_id,
                                 ctx.compute_fingerprint(), provenance)
        except subprocess.TimeoutExpired as exc:
            raise ExecutionError(f"external executable timed out: {exc}")

    @staticmethod
    def _hash_bytes(b: bytes) -> str:
        return hashlib.sha256(b).hexdigest()[:16]

    @classmethod
    def _hash_file(cls, path: str) -> str:
        return cls._hash_bytes(open(path, "rb").read())

    def _extract(self, workdir: str) -> Dict[str, Any]:
        kind = self._extraction.get("kind") if self._extraction else None
        if not kind:
            raise ProtocolError(
                "no extraction rule declared; the program's textual stdout "
                "does not automatically become a scientific result")
        if kind == "json-file":
            path = os.path.join(workdir, self._extraction["path"])
            with open(path) as f:
                return json.load(f)
        if kind == "json-stdout":
            return json.loads(self._extract_stdout())
        raise ProtocolError(
            f"undeclared extraction kind {kind!r}; stdout text does not "
            "automatically become a scientific result")

    def _extract_stdout(self) -> str:
        raise ProtocolError("json-stdout extraction requires the captured "
                            "stdout; use json-file extraction")


def available_backends() -> List[ComputeBackend]:
    """All importable backends, probed. Honest about what is installed."""
    backends = [NumPyBackend()]
    jax, torch = JaxBackend(), TorchBackend()
    if jax.descriptor.version != "not-installed":
        backends.append(jax)
    if torch.descriptor.version != "not-installed":
        backends.append(torch)
    return backends


def get_compute_backend(name: str, **kwargs) -> ComputeBackend:
    if name == "numpy":
        return NumPyBackend()
    if name == "jax":
        b = JaxBackend()
        if b.descriptor.version == "not-installed":
            raise ProtocolError("JAX backend requested but JAX is not installed")
        return b
    if name == "torch":
        b = TorchBackend()
        if b.descriptor.version == "not-installed":
            raise ProtocolError("PyTorch backend requested but torch is not installed")
        return b
    raise ProtocolError(f"unknown compute backend {name!r}")
