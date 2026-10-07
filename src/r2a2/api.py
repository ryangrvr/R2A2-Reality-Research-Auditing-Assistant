"""Theory SDK: the plugin protocol and registry.

Pillar 1. Third-party theories register via the ``r2a2.theories`` entry point
group or ``register``; R2A2 core learns nothing about any specific theory.

A theory declares, declaratively or via hooks:

    id, version, state, parameters (with provenance kind), assumptions,
    commitments, observables, transformations/invariances, datasets,
    experiments, predictions, comparators, hostile controls, kill conditions,
    validity domain.

A minimal theory plugin must run with pure Python/NumPy: backends are
orthogonal (pillar 2) and high-performance dependencies are optional.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

# Provenance kinds for parameters. These are the ledger debt kinds of
# pillar 3, seen from the theory side. Nothing here is physics.
PARAM_KINDS = (
    "commitment",           # declared postulate, priced and explicit
    "imported-constant",    # external constant (must carry a source)
    "fitted-parameter",     # fit against data (sector-scoped)
    "external-prior",
    "numerical-approximation",
    "sector-input",         # parameter specific to one sector
)

ASSUMPTION_KINDS = ("assumption", "commitment", "identifying")
TEST_KINDS = ("identity", "hostile-control", "comparator", "holdout", "custom")

EVIDENCE_GRADES = (
    "theorem",              # proved
    "formal",               # formal / perturbative result, not fully rigorous
    "numerical",            # numerical evidence only
    "empirical",
    "conditional",
    "null",
    "unresolved-identification",
)


@dataclass
class Parameter:
    """A theory parameter with mandatory provenance."""

    name: str
    kind: str                        # one of PARAM_KINDS
    sector: str = "default"          # sector in which it was determined
    source: Optional[str] = None     # source id in the project's source register
    value: Any = None

    def __post_init__(self):
        if self.kind not in PARAM_KINDS:
            raise ValueError(f"unknown parameter kind {self.kind!r}; known: {PARAM_KINDS}")
        if self.kind in ("imported-constant", "fitted-parameter") and not self.source:
            raise ValueError(f"parameter {self.name!r} of kind {self.kind!r} requires a source")


@dataclass
class Assumption:
    """An assumption/commitment. Commitment is legal when explicit."""

    id: str
    text: str
    kind: str = "assumption"         # "assumption" | "commitment" | "identifying"
    priced: bool = False             # commitments must be priced
    source: Optional[str] = None

    def __post_init__(self):
        if self.kind not in ("assumption", "commitment", "identifying"):
            raise ValueError(f"unknown assumption kind {self.kind!r}")
        if self.kind == "commitment" and not self.priced:
            raise ValueError(f"commitment {self.id!r} must be priced (commitment != free)")


@dataclass
class Prediction:
    """A quantitative prediction, with the exact question it answers."""

    id: str
    description: str
    experiment: str                  # experiment key that produces the numbers
    observable: str
    kill_condition: str              # what observed result would kill this prediction
    assumptions: List[str] = field(default_factory=list)   # assumption ids
    parameters: List[str] = field(default_factory=list)    # parameter names used
    evidence_grade: str = "numerical"
    sector: str = "default"
    comparator: Optional[str] = None # comparator/null model id, if any

    def __post_init__(self):
        if self.evidence_grade not in EVIDENCE_GRADES:
            raise ValueError(f"unknown evidence grade {self.evidence_grade!r}")
        if not self.kill_condition:
            raise ValueError(f"prediction {self.id!r} has NO kill condition (not falsifiable)")


@dataclass
class Test:
    """A test: control, identity, comparator audit or hostile control."""

    id: str
    kind: str                        # "identity" | "hostile-control" | "comparator" | "holdout" | "custom"
    experiment: str
    description: str = ""
    exact: bool = False              # exact identity/conservation-law check
    comparator: Optional[str] = None
    preregistered: bool = True

    def __post_init__(self):
        if self.kind not in ("identity", "hostile-control", "comparator", "holdout", "custom"):
            raise ValueError(f"unknown test kind {self.kind!r}")


@dataclass
class TransformationClass:
    """An extension point for nuisance/interface freedom.

    R2A2 core does not know what T means (a group, a gauge, monotone maps,
    filters...). A plugin declares the class and supplies:

    - membership rule (``is_member``),
    - composition (``compose``),
    - canonicalisation if available (``canonicalize``),
    - invariants (``invariants``),
    - quotient-distance routines (``quotient_distance``),
    - numerical optimisers if needed (``optimise``).

    The scientific question the framework then answers is: does the candidate
    remain distinguishable after quotienting this declared freedom?
    """

    id: str
    description: str = ""
    is_member: Optional[Callable[..., Any]] = None       # T -> bool
    compose: Optional[Callable[..., Any]] = None         # T1, T2 -> T
    canonicalize: Optional[Callable[..., Any]] = None    # T -> canonical form
    invariants: Optional[Callable[..., Any]] = None      # T -> dict of invariants
    quotient_distance: Optional[Callable[..., Any]] = None  # T, x, y -> dist
    optimise: Optional[Callable[..., Any]] = None        # sup/inf over T


@dataclass
class Comparator:
    """A comparator or null model: what the prediction must beat or differ from."""

    id: str
    description: str
    model: Optional[Callable[..., Any]] = None   # returns comparator predictions
    source: Optional[str] = None


@dataclass
class Theory:
    """The full declaration of a theory. This is the plugin contract."""

    id: str
    version: str
    description: str = ""
    parameters: List[Parameter] = field(default_factory=list)
    assumptions: List[Assumption] = field(default_factory=list)
    predictions: List[Prediction] = field(default_factory=list)
    tests: List[Test] = field(default_factory=list)
    transformation_classes: List[TransformationClass] = field(default_factory=list)
    comparators: List[Comparator] = field(default_factory=list)
    transformations: List[Dict[str, Any]] = field(default_factory=list)  # invariances
    validity_domain: str = ""
    experiments: Dict[str, Callable[..., Any]] = field(default_factory=dict)
    sources: Dict[str, str] = field(default_factory=dict)  # source id -> description

    # -- validation --------------------------------------------------------
    def validate(self) -> List[str]:
        """Structural checks. Returns a list of blocking problems (empty = valid)."""
        blocking: List[str] = []
        seen_params = {p.name for p in self.parameters}
        seen_assum = {a.id for a in self.assumptions}
        for p in self.parameters:
            if p.sector == "default" and p.kind == "fitted-parameter":
                blocking.append(f"{self.id}: fitted parameter {p.name!r} has no sector")
        for pred in self.predictions:
            if pred.experiment not in self.experiments:
                blocking.append(f"{self.id}/{pred.id}: unknown experiment {pred.experiment!r}")
            for a in pred.assumptions:
                if a not in seen_assum:
                    blocking.append(f"{self.id}/{pred.id}: unknown assumption {a!r}")
            for name in pred.parameters:
                if name not in seen_params:
                    blocking.append(f"{self.id}/{pred.id}: unknown parameter {name!r}")
        for t in self.tests:
            if t.experiment not in self.experiments:
                blocking.append(f"{self.id}/{t.id}: unknown experiment {t.experiment!r}")
        return blocking


class TheoryRegistry:
    """Registry of installed theory plugins."""

    def __init__(self) -> None:
        self._theories: Dict[str, Theory] = {}

    def register(self, theory: Theory) -> None:
        if theory.id in self._theories:
            raise ValueError(f"theory {theory.id!r} already registered")
        self._theories[theory.id] = theory

    def get(self, theory_id: str) -> Theory:
        return self._theories[theory_id]

    def ids(self) -> List[str]:
        return sorted(self._theories)

    def load_entrypoints(self) -> int:
        """Discover plugins via the ``r2a2.theories`` entry-point group.

        Returns the number of newly loaded theories. Never a core failure if a
        plugin errors: plugin bugs must not break the framework, so failures
        are re-raised as ``PluginError`` with context.
        """
        try:
            from importlib.metadata import entry_points
        except ImportError:  # pragma: no cover - py<3.9 backport path
            return 0
        n = 0
        try:
            eps = entry_points(group="r2a2.theories")
        except TypeError:  # pragma: no cover - older importlib API
            eps = entry_points().get("r2a2.theories", [])
        for ep in eps:
            try:
                theory = ep.load()
                if isinstance(theory, Theory):
                    self.register(theory)
                    n += 1
            except Exception as exc:  # pragma: no cover - defensive
                raise PluginError(f"plugin {ep.name!r} failed to load: {exc}") from exc
        return n


class PluginError(RuntimeError):
    pass


#: process-wide registry
registry = TheoryRegistry()
