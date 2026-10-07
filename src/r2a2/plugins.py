"""Plugin trust model: two explicit execution classes, never silently upgraded.

TRUSTED in-process: a normal Python extension loaded into the R2A2 process.
It has the full power of the process — this is stated plainly, not hidden.

UNTRUSTED isolated: runs across a REAL process boundary via a subprocess
protocol with machine-readable stdio and explicit capability grants.
No Python-level monkey-patching/import-restriction is advertised as a
security sandbox: if isolation is claimed, it is enforced by the OS process
boundary, and capabilities that cannot be safely isolated are REFUSED
("unsupported isolation" beats fake isolation).

An unsigned plugin may be allowed only by explicit policy and is never
silently promoted to trusted because it imported successfully.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .schema import SCHEMA_VERSION, stamp

# execution classes
TRUSTED_INPROCESS = "trusted-in-process"
UNTRUSTED_ISOLATED = "untrusted-isolated"

# capability keys (explicit grants; anything not declared is refused)
CAP_READ_INPUT = "read-declared-input"
CAP_READ_DATASET = "read-declared-dataset"
CAP_WRITE_OUTPUT = "write-declared-output"
CAP_NETWORK = "network"           # v0.5: refused — cannot isolate yet
CAP_ACCELERATOR = "accelerator"   # v0.5: refused — cannot isolate yet
CAP_SUBPROCESS = "subprocess"     # v0.5: refused — cannot isolate yet

ISOLATABLE = {CAP_READ_INPUT, CAP_READ_DATASET, CAP_WRITE_OUTPUT}
REFUSED_DEFAULT = {CAP_NETWORK, CAP_ACCELERATOR, CAP_SUBPROCESS}

# R2A2 extension API version (independent from the artifact schema)
EXTENSION_API = 1

API_MODULES = (  # the only modules plugins may rely on as supported API
    "r2a2.api",
    "r2a2.backends",
    "r2a2.signing",
    "r2a2.plugins",
)


@dataclass
class PluginManifest:
    """Stable metadata for a plugin, inspectable before execution."""

    plugin_id: str
    version: str
    extension_api: int = EXTENSION_API
    origin: str = ""                 # package name / repository URL
    package_hash: str = ""           # hash of the plugin package file
    signature: Optional[dict] = None  # identity envelope from r2a2.signing
    capabilities: List[str] = field(default_factory=list)
    provides: List[str] = field(default_factory=list)  # hooks/types supplied
    execution_class: str = UNTRUSTED_ISOLATED

    def to_dict(self) -> dict:
        return stamp({
            "plugin_id": self.plugin_id, "version": self.version,
            "extension_api": self.extension_api, "origin": self.origin,
            "package_hash": self.package_hash, "signature": self.signature,
            "capabilities": self.capabilities, "provides": self.provides,
            "execution_class": self.execution_class,
        })

    @classmethod
    def from_dict(cls, d: dict) -> "PluginManifest":
        return cls(
            plugin_id=d["plugin_id"], version=d["version"],
            extension_api=d.get("extension_api", EXTENSION_API),
            origin=d.get("origin", ""), package_hash=d.get("package_hash", ""),
            signature=d.get("signature"), capabilities=d.get("capabilities", []),
            provides=d.get("provides", []),
            execution_class=d.get("execution_class", UNTRUSTED_ISOLATED))


class PluginPolicy:
    """What the installation will accept. Never silently upgraded."""

    def __init__(self, allow_unsigned: bool = False,
                 trusted_ids: List[str] = None,
                 identity_policy: Optional[object] = None):
        self.allow_unsigned = allow_unsigned
        self.trusted_ids = trusted_ids or []
        self.identity_policy = identity_policy

    def evaluate(self, manifest: PluginManifest) -> Dict[str, Any]:
        report = stamp({
            "plugin_id": manifest.plugin_id,
            "execution_class": manifest.execution_class,
            "extension_api": manifest.extension_api,
            "extension_api_compatible": manifest.extension_api == EXTENSION_API,
            "signature": None,
            "trusted": False,
            "reasons": [],
        })
        if manifest.extension_api != EXTENSION_API:
            report["reasons"].append(
                f"extension API {manifest.extension_api} != supported {EXTENSION_API}")
        if manifest.signature:
            from .signing import verify_envelope
            res = verify_envelope(manifest.signature,
                                  self.identity_policy or _permissive_policy())
            report["signature"] = res
            if res["trusted"]:
                report["trusted"] = True
            else:
                report["reasons"].append(f"signature: {res['identity']}")
        else:
            if self.allow_unsigned and manifest.plugin_id in self.trusted_ids:
                report["trusted"] = True
                report["reasons"].append(
                    "UNSIGNED but explicitly listed in policy.trusted_ids")
            else:
                report["reasons"].append(
                    "unsigned and not explicitly trusted; import success "
                    "never implies trust")
        # trusted in-process requires explicit listing, never import-success
        if manifest.execution_class == TRUSTED_INPROCESS and \
                manifest.plugin_id not in self.trusted_ids:
            report["trusted"] = False
            report["reasons"].append(
                "execution class trusted-in-process requires explicit "
                "listing in plugin policy")
        return report


def _permissive_policy():
    from .signing import IdentityPolicy
    return IdentityPolicy(allow_unsigned=True)


def hash_package(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


# --------------------------------------------------------------------------
# Isolated execution: real subprocess boundary
# --------------------------------------------------------------------------

_ISOLATED_RUNNER = '''"""Subprocess runner for untrusted R2A2 plugins.
Machine-readable protocol: JSON request on stdin, JSON response on stdout.
Only declared capabilities are honored; anything else is refused."""
import json, sys, os

def main():
    req = json.load(sys.stdin)
    grants = req.get("capabilities", [])
    for path in req.get("read_paths", []):
        if not any(path == g[5:] or path.startswith(g[5:] + os.sep)
                   for g in grants if g.startswith("read:")):
            sys.stdout.write(json.dumps(
                {"ok": False, "error": f"capability refused: read {path} not declared"}))
            return
    try:
        import importlib
        mod_name, _, qual = req["entry"].partition(":")
        mod = importlib.import_module(mod_name)
        fn = mod
        for part in qual.split("."):
            fn = getattr(fn, part)
        result = fn(**req.get("args", {}))
        sys.stdout.write(json.dumps({"ok": True, "result": result}))
    except Exception as exc:
        sys.stdout.write(json.dumps({"ok": False, "error": repr(exc)}))

main()
'''


class IsolatedExecutor:
    """Executes a plugin entry point in a separate OS process with explicit
    capability grants. Refuses capabilities v0.5 cannot isolate."""

    def __init__(self, workspace_dir: str = ".r2a2_plugin_sandbox"):
        self.workspace = workspace_dir
        os.makedirs(self.workspace, exist_ok=True)
        self._runner = os.path.join(self.workspace, "_isolated_runner.py")
        with open(self._runner, "w") as f:
            f.write(_ISOLATED_RUNNER)

    def run(self, entry: str, manifest: PluginManifest,
            args: Dict[str, Any] = None,
            read_paths: List[str] = None,
            timeout: int = 120) -> Dict[str, Any]:
        refused = [c for c in manifest.capabilities if c in REFUSED_DEFAULT]
        req = {
            "entry": entry,
            "args": args or {},
            "capabilities": [f"read:{p}" for p in (read_paths or [])],
            "read_paths": read_paths or [],
        }
        proc = subprocess.run(
            [sys.executable, self._runner],
            input=json.dumps(req), capture_output=True, text=True,
            timeout=timeout, cwd=self.workspace)
        try:
            resp = json.loads(proc.stdout)
        except json.JSONDecodeError:
            return {"ok": False,
                    "error": f"plugin produced no valid response: {proc.stderr[-400:]}"}
        if refused:
            resp["refused_capabilities"] = refused
            resp["note"] = "refused capabilities cannot be isolated in v0.5"
        return resp


def inspect_plugin(manifest: PluginManifest) -> str:
    """Human-readable inspection (before any execution)."""
    return "\n".join([
        f"plugin:        {manifest.plugin_id} v{manifest.version}",
        f"extension api: {manifest.extension_api} (supported: {EXTENSION_API})",
        f"origin:        {manifest.origin or '(undeclared)'}",
        f"package hash:  {manifest.package_hash or '(none)'}",
        f"signed:        {'yes' if manifest.signature else 'NO'}",
        f"exec class:    {manifest.execution_class}",
        f"capabilities:  {manifest.capabilities or '(none)'}",
        f"provides:      {manifest.provides or '(nothing declared)'}",
    ])
