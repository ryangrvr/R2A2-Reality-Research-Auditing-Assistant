"""YAML as a transport format, never the internal truth.

Pipeline: YAML input -> validated canonical internal model -> canonical hash.
We never hash the YAML text: anchors, aliases, implicit typing and parser
differences make the file itself unreliable as identity. The typed Theory
objects (and their canonical serialization) are the truth; YAML is just how
humans hand them to us.

PyYAML is an optional dependency; without it, a JSON transport is accepted.
"""

from __future__ import annotations

from typing import Any, Dict

from .api import (Assumption, Comparator, Parameter, Prediction, Test,
                  Theory, TransformationClass)
from .failures import ProtocolError


def _load_yaml(text: str) -> Dict[str, Any]:
    try:
        import yaml  # type: ignore
    except ImportError:
        raise ProtocolError(
            "YAML transport requires PyYAML (pip install r2a2-science[yaml]); "
            "JSON transport is always available")
    try:
        return yaml.safe_load(text)
    except Exception as exc:
        raise ProtocolError(f"invalid YAML: {exc}") from exc


def _require(d: dict, key: str, ctx: str):
    if key not in d:
        raise ProtocolError(f"{ctx}: missing required field {key!r}")
    return d[key]


def _ref(fn) -> str:
    """Stable reference for a hook callable: 'module:qualname'.

    The colon separates module path from qualname, so dotted packages
    (my_package.models.gravity:solve) are unambiguous. Executable pieces
    travel as references + are hashed at compile time; the loader resolves
    them at import time. None serializes as ''.
    """
    if fn is None:
        return ""
    from .compiler import _module_qualname
    return _module_qualname(fn)


def theory_from_dict(d: Dict[str, Any]) -> Theory:
    """Build a Theory from a plain mapping (already-parsed YAML/JSON)."""
    ctx = d.get("id", "<theory>")
    theory = Theory(
        id=str(_require(d, "id", ctx)),
        version=str(_require(d, "version", ctx)),
        description=d.get("description", ""),
        validity_domain=d.get("validity_domain", ""),
        sources={s["id"]: s.get("description", "")
                 for s in d.get("sources", [])},
        experiments={},  # filled below from references or inline callables
    )
    for name, ex in d.get("experiments", {}).items():
        if callable(ex):
            theory.experiments[name] = ex
        else:
            theory.experiments[name] = _resolve(ex)
    for p in d.get("parameters", []):
        theory.parameters.append(Parameter(
            name=str(_require(p, "name", ctx)),
            kind=str(_require(p, "kind", ctx)),
            sector=p.get("sector", "default"),
            source=p.get("source"),
            value=p.get("value"),
        ))
    for a in d.get("assumptions", []):
        theory.assumptions.append(Assumption(
            id=str(_require(a, "id", ctx)),
            text=a.get("text", ""),
            kind=a.get("kind", "assumption"),
            priced=bool(a.get("priced", False)),
            source=a.get("source"),
        ))
    for pred in d.get("predictions", []):
        theory.predictions.append(Prediction(
            id=str(_require(pred, "id", ctx)),
            description=pred.get("description", ""),
            experiment=str(_require(pred, "experiment", ctx)),
            observable=pred.get("observable", ""),
            kill_condition=str(_require(pred, "kill_condition", ctx)),
            assumptions=list(pred.get("assumptions", [])),
            parameters=list(pred.get("parameters", [])),
            evidence_grade=pred.get("evidence_grade", "numerical"),
            sector=pred.get("sector", "default"),
            comparator=pred.get("comparator"),
        ))
    for t in d.get("tests", []):
        theory.tests.append(Test(
            id=str(_require(t, "id", ctx)),
            kind=str(_require(t, "kind", ctx)),
            experiment=str(_require(t, "experiment", ctx)),
            description=t.get("description", ""),
            exact=bool(t.get("exact", False)),
            comparator=t.get("comparator"),
            preregistered=bool(t.get("preregistered", True)),
        ))
    theory.transformations = [dict(tr) for tr in d.get("transformations", [])]
    for tc in d.get("transformation_classes", []):
        theory.transformation_classes.append(TransformationClass(
            id=str(_require(tc, "id", ctx)),
            description=tc.get("description", ""),
            **{k: _resolve(tc.get(k)) for k in
               ("is_member", "compose", "canonicalize", "invariants",
                "quotient_distance", "optimise")},
        ))
    for c in d.get("comparators", []):
        theory.comparators.append(Comparator(
            id=str(_require(c, "id", ctx)),
            description=c.get("description", ""),
            model=_resolve(c.get("model")),
            source=c.get("source"),
        ))
    return theory


def _resolve(ref: str, expect_class=False):
    """Resolve a 'module.qualname' hook reference back to a callable.

    Empty string or missing → None. Qualname path is tried first; if the
    callable is a lambda or nested closure (no stable attribute path), the
    declaring module's namespace is searched for an identity match. This is
    how executable pieces travel: by stable reference, resolved at load time.
    """
    if not ref:
        return None
    import importlib
    # 'module:qualname' — colon separates module path from qualname, so
    # dotted package modules like pkg.models.gravity:solve parse correctly.
    # Legacy 'module.qualname' refs (top-level modules only) still accepted.
    module_name, _, qual = ref.partition(":")
    if not _:
        module_name, _, qual = ref.rpartition(".")
    try:
        mod = importlib.import_module(module_name)
    except ImportError as exc:
        raise ProtocolError(f"cannot resolve hook reference {ref!r}: {exc}") from exc
    # try the attribute path
    try:
        obj = mod
        for part in qual.split("."):
            obj = getattr(obj, part)
        return obj
    except AttributeError:
        pass
    # fallback: identity search in the module namespace (lambdas, closures).
    # Ambiguous references (several <lambda>s) must FAIL, never guess.
    matches = [v for v in vars(mod).values()
               if callable(v) and getattr(v, "__qualname__", None) == qual]
    if len(matches) == 1:
        return matches[0]
    raise ProtocolError(
        f"cannot resolve hook reference {ref!r} "
        + (f"({len(matches)} candidates with that qualname; name the function)"
           if matches else "(not found)")
        + " — the declaring module must be importable at load time")


def theory_from_yaml(text: str) -> Theory:
    """YAML text -> validated canonical internal model."""
    return theory_from_dict(_load_yaml(text))


def theory_to_dict(theory: Theory) -> Dict[str, Any]:
    """Canonical serialization of a Theory (round-trips through from_dict)."""
    from .schema import stamp
    return stamp({
        "id": theory.id,
        "version": theory.version,
        "description": theory.description,
        "validity_domain": theory.validity_domain,
        "sources": [{"id": k, "description": v}
                    for k, v in sorted(theory.sources.items())],
        "parameters": [{"name": p.name, "kind": p.kind, "sector": p.sector,
                        "source": p.source, "value": p.value}
                       for p in theory.parameters],
        "assumptions": [{"id": a.id, "text": a.text, "kind": a.kind,
                         "priced": a.priced, "source": a.source}
                        for a in theory.assumptions],
        "predictions": [{"id": p.id, "description": p.description,
                         "experiment": p.experiment, "observable": p.observable,
                         "kill_condition": p.kill_condition,
                         "assumptions": list(p.assumptions),
                         "parameters": list(p.parameters),
                         "evidence_grade": p.evidence_grade,
                         "sector": p.sector, "comparator": p.comparator}
                                         for p in theory.predictions],
                        "tests": [{"id": t.id, "kind": t.kind, "experiment": t.experiment,
                                   "description": t.description, "exact": t.exact,
                                   "comparator": t.comparator, "preregistered": t.preregistered}
                                  for t in theory.tests],
            # general transformations (invariance declarations)
            # experiments: executable code travels as module:qualname references
            "experiments": {name: _ref(fn) for name, fn in
                            sorted(theory.experiments.items())},
            "transformations": [dict(tr) for tr in theory.transformations],
            # transformation classes: hooks serialized as stable code references
            "transformation_classes": [
                {"id": tc.id, "description": tc.description,
                 "is_member": _ref(tc.is_member), "compose": _ref(tc.compose),
                 "canonicalize": _ref(tc.canonicalize), "invariants": _ref(tc.invariants),
                 "quotient_distance": _ref(tc.quotient_distance),
                 "optimise": _ref(tc.optimise)}
                for tc in theory.transformation_classes],
            # comparators: model as stable code reference
            "comparators": [
                {"id": c.id, "description": c.description,
                 "model": _ref(c.model), "source": c.source}
                for c in theory.comparators],
        })
