"""Epistemic ledger: the dependency graph.

Pillar 3. The canonical ledger is a **dependency graph, not a scalar sum**.
Scalar "logical debt" numbers are derived summaries and are always labelled
with the debt kinds they aggregate — the original GRU auditor's net was a
blind sum that could not detect double counting, and that failure mode is what
the graph exists to prevent.
"""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Dict, List, Optional, Set

# Debt kinds — never merged into one number without labels.
DEBT_KINDS = (
    "commitment",
    "imported-constant",
    "fitted-parameter",
    "external-prior",
    "numerical-approximation",
    "unproved-lemma",
    "waived-gate",
    "comparator-assumption",
    "identifying-assumption",
    "sector-input",
)


class Node:
    """One claim/assumption/test/source node in the dependency graph."""

    def __init__(self, node_id: str, kind: str, **attrs):
        self.id = node_id
        self.kind = kind  # "claim" | "assumption" | "parameter" | "source" | "test" | ...
        self.attrs = dict(attrs)
        self.deps: Set[str] = set()        # ids of nodes this depends on
        self.debt: Dict[str, int] = defaultdict(int)  # debt kind -> amount
        self.status: Optional[str] = attrs.get("status")

    def __repr__(self):  # pragma: no cover
        return f"Node({self.id!r}, {self.kind!r}, deps={sorted(self.deps)})"


class Ledger:
    """A directed dependency graph of claims, assumptions, parameters and sources."""

    def __init__(self) -> None:
        self.nodes: Dict[str, Node] = {}
        self._order: List[str] = []

    # -- construction ------------------------------------------------------
    def add(self, node_id: str, kind: str, deps=(), **attrs) -> Node:
        if node_id in self.nodes:
            raise ValueError(f"duplicate node {node_id!r}")
        node = Node(node_id, kind, **attrs)
        for d in deps:
            if d not in self.nodes:
                raise ValueError(f"node {node_id!r} depends on unknown node {d!r}")
            node.deps.add(d)
        self.nodes[node_id] = node
        self._order.append(node_id)
        return node

    def add_debt(self, node_id: str, kind: str, amount: int = 1) -> None:
        if kind not in DEBT_KINDS:
            raise ValueError(f"unknown debt kind {kind!r}; known: {DEBT_KINDS}")
        self.nodes[node_id].debt[kind] += amount

    # -- graph queries -----------------------------------------------------
    def ancestors(self, node_id: str) -> Set[str]:
        """The full dependency cone of a node (everything it rests on)."""
        seen: Set[str] = set()
        stack = [node_id]
        while stack:
            cur = stack.pop()
            for d in self.nodes[cur].deps:
                if d not in seen:
                    seen.add(d)
                    stack.append(d)
        return seen

    def descendants(self, node_id: str) -> Set[str]:
        """Everything that depends on a node (its support set)."""
        rev = self.reverse()
        return rev.ancestors(node_id)

    def reverse(self) -> "Ledger":
        rev = Ledger()
        for nid in self._order:
            n = self.nodes[nid]
            rev.add(n.id, n.kind, **n.attrs)
        for nid in self._order:
            for d in self.nodes[nid].deps:
                rev.nodes[d].deps.add(nid)
        return rev

    def find_cycles(self) -> List[List[str]]:
        """Return one representative cycle per strongly-connected component > 1."""
        index, low, on_stack, stack = {}, {}, set(), []
        cycles, counter = [], [0]

        def strongconnect(v):  # Tarjan, iterative
            work = [(v, iter(self.nodes[v].deps))]
            index[v] = low[v] = counter[0]; counter[0] += 1
            stack.append(v); on_stack.add(v)
            while work:
                node, it = work[-1]
                advanced = False
                for w in it:
                    if w not in index:
                        index[w] = low[w] = counter[0]; counter[0] += 1
                        stack.append(w); on_stack.add(w)
                        work.append((w, iter(self.nodes[w].deps)))
                        advanced = True
                        break
                    elif w in on_stack:
                        low[node] = min(low[node], index[w])
                if advanced:
                    continue
                work.pop()
                if work:
                    parent = work[-1][0]
                    low[parent] = min(low[parent], low[node])
                if low[node] == index[node]:
                    scc = []
                    while True:
                        w = stack.pop(); on_stack.discard(w); scc.append(w)
                        if w == node:
                            break
                    if len(scc) > 1 or (len(scc) == 1 and node in self.nodes[node].deps):
                        cycles.append(scc)

        for v in self._order:
            if v not in index:
                strongconnect(v)
        return cycles

    def topological_order(self) -> List[str]:
        """Kahn's order; raises if cyclic."""
        indeg = {nid: 0 for nid in self._order}
        for nid in self._order:
            for d in self.nodes[nid].deps:
                indeg[d] += 1
        q = deque(nid for nid in self._order if indeg[nid] == 0)
        out = []
        while q:
            n = q.popleft()
            out.append(n)
            for d in self.nodes[n].deps:
                indeg[d] -= 1
                if indeg[d] == 0:
                    q.append(d)
        if len(out) != len(self._order):
            raise ValueError("ledger contains a cycle")
        return out

    # -- summaries (derived, never canonical) ------------------------------
    def cone_debt(self, node_id: str, kinds=None) -> Dict[str, int]:
        """Labelled debt in the dependency cone of a node. Not a blind sum."""
        totals: Dict[str, int] = defaultdict(int)
        for aid in self.ancestors(node_id) | {node_id}:
            for kind, amt in self.nodes[aid].debt.items():
                if kinds is None or kind in kinds:
                    totals[kind] += amt
        return dict(totals)

    def total_debt(self, kinds=None) -> Dict[str, int]:
        totals: Dict[str, int] = defaultdict(int)
        for n in self.nodes.values():
            for kind, amt in n.debt.items():
                if kinds is None or kind in kinds:
                    totals[kind] += amt
        return dict(totals)

    # -- persistence -------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "nodes": [
                {
                    "id": n.id,
                    "kind": n.kind,
                    "attrs": n.attrs,
                    "deps": sorted(n.deps),
                    "debt": dict(n.debt),
                }
                for n in (self.nodes[i] for i in self._order)
            ]
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Ledger":
        led = cls()
        for nd in data["nodes"]:
            node = led.add(nd["id"], nd["kind"], **nd.get("attrs", {}))
            node.deps = set(nd.get("deps", []))
            for k, v in nd.get("debt", {}).items():
                node.debt[k] = v
        return led
