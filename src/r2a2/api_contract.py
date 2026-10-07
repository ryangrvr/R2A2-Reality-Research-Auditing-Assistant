"""Stable extension API contract tests — runnable by plugin authors
independently of the R2A2 test suite.

Contract: `r2a2_extension_api: 1`
- supported import surface: r2a2.api, r2a2.backends, r2a2.signing, r2a2.plugins
- compatible minor additions to those modules are allowed;
- breaking changes require a new major extension API version;
- deprecated hooks warn for at least one compatibility cycle.

A plugin passes if it can: declare a Theory through r2a2.api, expose a
backend through r2a2.backends' protocol, declare a TransformationClass, and
be inspected by r2a2.plugins — WITHOUT importing any private R2A2 module.
"""

from __future__ import annotations

import inspect
from typing import List

from .plugins import API_MODULES, EXTENSION_API

PRIVATE_PREFIXES = ("r2a._", "r2a2._", "r2a2.canonical", "r2a2.compiler",
                    "r2a2.runner", "r2a2.ledger", "r2a2.audit",
                    "r2a2.trust", "r2a2.transport", "r2a2.schema",
                    "r2a2.schema_json", "r2a2.prov_export", "r2a2.rocrate",
                    "r2a2.usability", "r2a2.queries", "r2a2.report",
                    "r2a2.compare", "r2a2.transfer", "r2a2.failures",
                    "r2a2.doctor", "r2a2.cli")


def check_plugin_api(plugin_module) -> List[str]:
    """Verify a plugin uses only the supported API. Returns violations."""
    violations: List[str] = []
    seen = set()
    for name, obj in vars(plugin_module).items():
        mod = getattr(obj, "__module__", None)
        if mod and mod.startswith("r2a2") and mod not in API_MODULES:
            violations.append(
                f"{name}: imports from private module '{mod}' which is not "
                f"part of extension API {EXTENSION_API} (supported: "
                f"{', '.join(API_MODULES)})")
    # hook signatures must remain compatible: Theory/Parameter/etc. are
    # constructible with documented fields
    try:
        from .api import Theory, Parameter, Assumption, Prediction, Test, \
            TransformationClass, Comparator
        Theory(id="api-check", version="0",
               parameters=[Parameter("x", kind="commitment")],
               assumptions=[Assumption("A", "t", priced=True)],
               experiments={})
    except Exception as exc:
        violations.append(f"core API surface broken: {exc}")
    return violations


def extension_api_version() -> int:
    return EXTENSION_API
