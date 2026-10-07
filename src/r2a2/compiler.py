"""Compiler: a theory declaration -> immutable execution manifest + dependency ledger.

Pillar 4 entry point. ``compile`` produces two artifacts:

1. an ``ExecutionManifest`` binding model version, parameter sources, test
   definitions, thresholds, seeds, backend and environment, with a content hash;
2. a ``Ledger`` dependency graph whose nodes are commitments, parameters,
   sources, predictions and tests.

Results attach to these artifacts; they never rewrite the preregistered
structure.
"""

from __future__ import annotations

import hashlib
import json
import platform
import sys
from dataclasses import dataclass, field
from typing import Any, Dict

from .api import Theory
from .canonical import canonical_hash as canonical_hash_impl
from .schema import SCHEMA_VERSION
from .ledger import Ledger

KIND_DEBT = {
    "commitment": "commitment",
    "assumption": "unproved-lemma",
    "identifying": "identifying-assumption",
}


def canonical_hash(obj: Any) -> str:
    """Stable content hash of a JSON-serializable object.

    Delegates to r2a2.canonical: the single definition of the canonicalization
    rules (key-order and whitespace invariant, tuple/list equivalent).
    """
    return canonical_hash_impl(obj)


@dataclass
class ExecutionManifest:
    """Immutable binding of everything that determines a run, hashed before
    results exist."""

    theory_id: str
    theory_version: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    parameter_sources: Dict[str, str] = field(default_factory=dict)
    tests: list = field(default_factory=list)
    predictions: list = field(default_factory=list)
    thresholds: Dict[str, Any] = field(default_factory=dict)
    datasets: Dict[str, str] = field(default_factory=dict)  # dataset id -> hash
    r2a2_schema: str = ""
    # binds the FULL scientific declaration (assumption texts, kill conditions,
    # comparator definitions, transformation classes, test definitions,
    # preregistration flags) — not just the ID lists
    theory_declaration_hash: str = ""
    # code-binding references: experiment name -> (module, qualname) so the
    # implementing code is pinned to the manifest
    experiment_refs: Dict[str, str] = field(default_factory=dict)
    transformation_refs: Dict[str, str] = field(default_factory=dict)
    seeds: Dict[str, int] = field(default_factory=dict)
    backend: str = "local"
    environment: Dict[str, str] = field(default_factory=dict)
    frozen: bool = False
    hash: str = ""

    def freeze(self) -> str:
        """Compute and lock the manifest hash. After this, no mutation."""
        payload = {k: v for k, v in self.__dict__.items() if k not in ("frozen", "hash")}
        self.hash = canonical_hash(payload)
        self.frozen = True
        return self.hash

    def _guard(self) -> None:
        if self.frozen:
            raise RuntimeError(
                "execution manifest is frozen; results attach to it, they never rewrite it"
            )

    def __setattr__(self, name, value):
        if getattr(self, "frozen", False) and name not in ("frozen", "hash"):
            raise RuntimeError(f"manifest is frozen; cannot modify {name!r}")
        object.__setattr__(self, name, value)

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def _code_ref(fn) -> str:
    """Stable reference to a callable: module.qualname (code is pinned by
    reference + hash at execution time, not embedded in the manifest)."""
    if fn is None:
        return ""
    mod = getattr(fn, "__module__", None)
    qual = getattr(fn, "__qualname__", getattr(fn, "__name__", repr(fn)))
    return f"{mod}.{qual}" if mod else str(qual)


def compile_theory(theory: Theory, backend: str = "local",
                   seeds: Dict[str, int] = None,
                   datasets: Dict[str, str] = None) -> tuple:
    """Compile a Theory into (ExecutionManifest, Ledger)."""
    problems = theory.validate()
    if problems:
        raise ValueError("theory does not compile: " + "; ".join(problems))

    ledger = Ledger()

    # sources first (everything may depend on them)
    for sid, desc in theory.sources.items():
        ledger.add(f"source:{sid}", "source", description=desc)

    # parameters with provenance
    for p in theory.parameters:
        deps = []
        if p.source:
            deps.append(f"source:{p.source}")
        ledger.add(
            f"param:{p.name}", "parameter", deps=deps,
            provenance_kind=p.kind, sector=p.sector,
            validity_domain=theory.validity_domain,
            supported_domain=theory.validity_domain,
        )
        ledger.add_debt(f"param:{p.name}", p.kind)

    # assumptions / commitments
    for a in theory.assumptions:
        deps = [f"source:{a.source}"] if a.source else []
        ledger.add(f"assume:{a.id}", "assumption", deps=deps,
                   text=a.text, assumption_kind=a.kind, priced=a.priced)
        if a.kind in KIND_DEBT:
            ledger.add_debt(f"assume:{a.id}", KIND_DEBT[a.kind])

    # predictions: claims depending on their assumptions and parameters
    for pred in theory.predictions:
        deps = [f"assume:{a}" for a in pred.assumptions]
        deps += [f"param:{name}" for name in pred.parameters]
        if pred.comparator:
            ledger.add(f"comparator:{pred.comparator}", "comparator",
                       comparator_assumption=True)
            ledger.add_debt(f"comparator:{pred.comparator}", "comparator-assumption")
            deps.append(f"comparator:{pred.comparator}")
        ledger.add(f"predict:{pred.id}", "claim", deps=deps,
                   description=pred.description, observable=pred.observable,
                   kill_condition=pred.kill_condition, claim_kind="derived",
                   evidence_grade=pred.evidence_grade, sector=pred.sector,
                   validity_domain=theory.validity_domain,
                   supported_domain=theory.validity_domain)

    # tests
    for t in theory.tests:
        ledger.add(f"test:{t.id}", "test", experiment=t.experiment,
                   test_kind=t.kind, exact=t.exact, preregistered=t.preregistered)

    # --- full scientific declaration hash -------------------------------
    # Uses the canonical transport serialization of the declarative model,
    # plus code references for the executable hooks. Changing ANY scientific
    # semantic field (kill condition, assumption text, transformation class,
    # preregistration flag, comparator...) changes this hash.
    from .transport import theory_to_dict
    decl = theory_to_dict(theory)
    decl["experiments_refs"] = {
        name: _code_ref(fn) for name, fn in sorted(theory.experiments.items())
    }
    decl["transformation_class_refs"] = {
        tc.id: _code_ref(tc) for tc in theory.transformation_classes
    }
    decl["comparator_refs"] = {
        c.id: _code_ref(c.model) if c.model else "" for c in theory.comparators
    }
    declaration_hash = canonical_hash(decl)

    experiment_refs = {name: _code_ref(fn) for name, fn in theory.experiments.items()}
    transformation_refs = {tc.id: _code_ref(tc) for tc in theory.transformation_classes}

    env = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
    }
    manifest = ExecutionManifest(
        theory_id=theory.id,
        theory_version=theory.version,
        parameters={p.name: p.value for p in theory.parameters},
        parameter_sources={p.name: p.source or "" for p in theory.parameters},
        datasets={k: v for k, v in (datasets or {}).items()},
        tests=[t.id for t in theory.tests],
        predictions=[p.id for p in theory.predictions],
        seeds=dict(seeds or {}),
        backend=backend,
        environment=env,
        r2a2_schema=SCHEMA_VERSION,
        theory_declaration_hash=declaration_hash,
        experiment_refs=experiment_refs,
        transformation_refs=transformation_refs,
    )
    return manifest, ledger
