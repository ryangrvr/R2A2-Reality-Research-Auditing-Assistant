"""Local-only usability session recorder — measurement without surveillance.

Purpose: measure where the R2A2 ONTOLOGY fails to explain itself during
external-user testing. Records only explicit framework interactions:

- commands attempted;
- validation errors encountered;
- schema fields users repeatedly misunderstand;
- number of edits before a successful compile;
- elapsed workflow steps (not identity).

No personal data, no network calls, no automatic upload. Sessions live in
`./.r2a2_sessions/` and are exported only when the study participant chooses.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List

SESSION_DIR = ".r2a2_sessions"


class UsabilitySession:
    def __init__(self, session_id: str = None):
        self.id = session_id or time.strftime("%Y%m%d-%H%M%S")
        self.started = time.time()
        self.events: List[Dict[str, Any]] = []

    # -- explicit interaction recording ------------------------------------
    def command(self, cmd: str, ok: bool, error: str = "") -> None:
        self.events.append({"t": round(time.time() - self.started, 3),
                            "kind": "command", "cmd": cmd,
                            "ok": ok, "error": error})

    def validation_error(self, field: str, message: str) -> None:
        self.events.append({"t": round(time.time() - self.started, 3),
                            "kind": "validation_error", "field": field,
                            "message": message})

    def edit_cycle(self) -> None:
        self.events.append({"t": round(time.time() - self.started, 3),
                            "kind": "edit"})

    def doc_lookup(self, concept: str) -> None:
        self.events.append({"t": round(time.time() - self.started, 3),
                            "kind": "doc_lookup", "concept": concept})

    # -- derived workflow metrics (no identity) ----------------------------
    def report(self) -> Dict[str, Any]:
        cmds = [e for e in self.events if e["kind"] == "command"]
        edits = [e for e in self.events if e["kind"] == "edit"]
        val_errs = [e for e in self.events if e["kind"] == "validation_error"]
        lookups = [e for e in self.events if e["kind"] == "doc_lookup"]
        field_counts: Dict[str, int] = {}
        for e in val_errs:
            field_counts[e["field"]] = field_counts.get(e["field"], 0) + 1
        concept_counts: Dict[str, int] = {}
        for e in lookups:
            concept_counts[e["concept"]] = concept_counts.get(e["concept"], 0) + 1
        failed = [c for c in cmds if not c["ok"]]
        return {
            "session": self.id,
            "duration_s": round(time.time() - self.started, 1),
            "commands_attempted": len(cmds),
            "commands_failed": len(failed),
            "first_success_after_n_edits": (
                next((i + 1 for i, e in enumerate(edits)
                      if any(c["ok"] for c in cmds
                             if c["t"] >= e["t"])), None)),
            "edits_before_success": len(edits),
            "misunderstood_fields": field_counts,
            "doc_looked_up": concept_counts,
            "failed_commands": [{"cmd": c["cmd"], "error": c["error"][:200]}
                                for c in failed],
        }

    # -- persistence --------------------------------------------------------
    def save(self, base: str = ".") -> str:
        d = os.path.join(base, SESSION_DIR)
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, f"{self.id}.json")
        with open(path, "w") as f:
            json.dump({"session": self.report(), "events": self.events},
                      f, indent=2)
        return path


def export_usability_report(base: str = ".") -> str:
    """Aggregate all local session files into one report. Local only."""
    d = os.path.join(base, SESSION_DIR)
    if not os.path.isdir(d):
        raise FileNotFoundError("no sessions recorded")
    sessions = []
    for fn in sorted(os.listdir(d)):
        if fn.endswith(".json"):
            with open(os.path.join(d, fn)) as f:
                sessions.append(json.load(f)["session"])
    fields: Dict[str, int] = {}
    concepts: Dict[str, int] = {}
    for s in sessions:
        for k, v in s.get("misunderstood_fields", {}).items():
            fields[k] = fields.get(k, 0) + v
        for k, v in s.get("doc_looked_up", {}).items():
            concepts[k] = concepts.get(k, 0) + v
    return json.dumps({
        "n_sessions": len(sessions),
        "total_edits_before_success": sum(s.get("edits_before_success", 0)
                                          for s in sessions),
        "fields_failing_most": dict(sorted(fields.items(),
                                           key=lambda kv: -kv[1])),
        "concepts_looked_up_most": dict(sorted(concepts.items(),
                                               key=lambda kv: -kv[1])),
        "per_session": sessions,
    }, indent=2)
