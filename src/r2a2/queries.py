"""First-class ledger queries: the scientific questions over the graph.

    why(node)     -- the full dependency cone as a tree
    impact(node)  -- what collapses if this assumption is removed
    inputs(node)  -- the leaves (sources/data/parameters) a claim rests on
    refits(sector)-- parameters refit outside their original sector
    circularity() -- cycles (circular support)

The signature warning this enables: when a dataset in a prediction's cone
overlaps its evaluation set, the prediction is not out-of-sample.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from .ledger import Ledger


def why(ledger: Ledger, node_id: str) -> str:
    """Render the dependency cone of a node as a tree (why does this hold?)."""
    if node_id not in ledger.nodes:
        raise KeyError(f"unknown node {node_id!r}")
    lines: List[str] = []

    def walk(nid: str, prefix: str, seen: frozenset) -> None:
        node = ledger.nodes[nid]
        attrs = {k: v for k, v in sorted(node.attrs.items())
                 if k in ("sector", "kind", "provenance_kind", "evidence_grade")}
        extra = f"  [{'; '.join(f'{k}={v}' for k, v in attrs.items())}]" if attrs else ""
        lines.append(f"{prefix}{nid}{extra}")
        if nid in seen:
            lines.append(f"{prefix}  (circular: already shown)")
            return
        deps = sorted(node.deps)
        for d in deps:
            last = d == deps[-1]
            walk(d, prefix + ("└── " if last else "├── "), seen | {nid})

    walk(node_id, "", frozenset())
    return "\n".join(lines)


def impact(ledger: Ledger, node_id: str) -> List[str]:
    """Which claims collapse if node_id is removed? (counterfactual pruning)"""
    if node_id not in ledger.nodes:
        raise KeyError(f"unknown node {node_id!r}")
    return sorted(ledger.descendants(node_id))


def inputs(ledger: Ledger, node_id: str) -> Dict[str, List[str]]:
    """The leaves a claim rests on, grouped by kind (what was actually assumed?)."""
    leaves = {}
    for aid in sorted(ledger.ancestors(node_id) | {node_id}):
        node = ledger.nodes[aid]
        if not node.deps or node.kind in ("source",):
            leaves.setdefault(node.kind, []).append(aid)
    return leaves


def refits(ledger: Ledger, sector: Optional[str] = None) -> List[str]:
    """Parameters refit outside their original sector (optionally filter)."""
    out = []
    for nid, node in sorted(ledger.nodes.items()):
        if node.kind == "parameter" and node.attrs.get("refit"):
            orig = node.attrs.get("sector")
            if sector is None or orig == sector or node.attrs.get("refit_sector") == sector:
                out.append(nid)
    return out


def circular_support(ledger: Ledger) -> List[List[str]]:
    return ledger.find_cycles()


def out_of_sample_warning(ledger: Ledger, prediction_id: str) -> List[str]:
    """Flag when a dataset in a prediction's cone is also its evaluation data."""
    warnings: List[str] = []
    if prediction_id not in ledger.nodes:
        raise KeyError(f"unknown node {prediction_id!r}")
    cone = ledger.ancestors(prediction_id) | {prediction_id}
    pred = ledger.nodes[prediction_id]
    eval_sets = set(pred.attrs.get("evaluation_datasets", []))
    for nid in cone:
        node = ledger.nodes[nid]
        overlap = eval_sets & set(node.attrs.get("provides_datasets", []))
        if overlap:
            warnings.append(
                f"WARNING: dataset {sorted(overlap)} appears in the dependency cone of "
                f"{prediction_id} (via {nid}). Prediction is not out-of-sample.")
    return warnings
