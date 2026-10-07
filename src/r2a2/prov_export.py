"""W3C PROV export — conformant PROV-JSON serialization.

PROVENANCE SPECIFICATION STATUS (precise wording, per the external review):
PROV-JSON is a **W3C Member Submission** (W3C Team Submission, 2013), NOT a
W3C Recommendation. R2A2 claims conformance to that submission's serialization
and says exactly that — no stronger claim.

Serialization rules (PROV-JSON Member Submission):
- top-level maps: ``prefix``, ``entity``, ``activity``, ``agent``,
  and the RELATION maps: ``used``, ``wasGeneratedBy``, ``wasDerivedFrom``,
  ``wasAttributedTo``, ``wasAssociatedWith``, ``wasInformedBy``;
- relations are expressed as separate top-level entries whose keys are
  relation-instance ids and whose values reference the involved identifiers
  — relations are NEVER embedded inside entity/activity records;
- R2A2-specific epistemic terms stay in the ``r2a2:`` namespace as
  attributes; they are never forced into prov: semantics.

Mapping (only where natural):
- entities:  theory declaration, execution manifest, datasets, results
- activities: compile, run, replicate, review, transfer
- agents:    author, reviewer, replicator
"""

from __future__ import annotations

from typing import Any, Dict, List

from .schema import SCHEMA_VERSION
from .schema_json import R2A2_NS

PROV_NS = "http://www.w3.org/ns/prov#"


def export_prov(theory_dict: Dict[str, Any],
                manifest: Dict[str, Any],
                results: List[Dict[str, Any]] = None,
                replications: List[Dict[str, Any]] = None,
                attestations: List[Dict[str, Any]] = None,
                transfers: List[Dict[str, Any]] = None,
                authors: List[str] = None,
                reviewers: List[str] = None,
                code_revision: str = "") -> dict:
    """Build a PROV-JSON (W3C Member Submission) document."""
    results = results or []
    replications = replications or []
    attestations = attestations or []
    transfers = transfers or []
    authors = authors or []
    reviewers = reviewers or []

    theory_id = f"r2a2:theory:{theory_dict.get('id')}"
    manifest_id = f"r2a2:manifest:{manifest.get('hash', '')[:16]}"
    run_id = "r2a2:activity:run"
    compile_id = "r2a2:activity:compile"

    entity: Dict[str, Any] = {
        theory_id: {
            "prov:type": ["prov:Entity", f"{R2A2_NS}TheoryDeclaration"],
            "r2a2:theoryVersion": theory_dict.get("version"),
            "r2a2:validityDomain": theory_dict.get("validity_domain", ""),
        },
        manifest_id: {
            "prov:type": ["prov:Entity", f"{R2A2_NS}ExecutionManifest"],
            "r2a2:manifestHash": manifest.get("hash"),
            "r2a2:frozen": True,
        },
    }
    for pred in theory_dict.get("predictions", []):
        entity[f"r2a2:prediction:{pred['id']}"] = {
            "prov:type": ["prov:Entity", f"{R2A2_NS}Prediction"],
            "r2a2:killCondition": pred.get("kill_condition"),
            "r2a2:evidenceGrade": pred.get("evidence_grade"),
        }
    for a in theory_dict.get("assumptions", []):
        entity[f"r2a2:assumption:{a['id']}"] = {
            "prov:type": ["prov:Entity",
                          f"{R2A2_NS}{a.get('kind', 'assumption').capitalize()}"],
            "r2a2:text": a.get("text"),
        }
    for p in theory_dict.get("parameters", []):
        entity[f"r2a2:parameter:{p['name']}"] = {
            "prov:type": ["prov:Entity", f"{R2A2_NS}Parameter"],
            "r2a2:provenanceKind": p.get("kind"),
            "r2a2:sector": p.get("sector"),
        }
    for rec in results:
        entity[f"r2a2:result:{rec.get('experiment')}"] = {
            "prov:type": ["prov:Entity", f"{R2A2_NS}ResultRecord"],
            "r2a2:resultHash": rec.get("result_hash"),
        }

    activity: Dict[str, Any] = {
        compile_id: {"prov:type": "prov:Activity", "r2a2:activityKind": "compile"},
        run_id: {"prov:type": "prov:Activity", "r2a2:activityKind": "run",
                 "r2a2:backend": manifest.get("backend")},
    }
    for rep in replications:
        activity[f"r2a2:activity:replicate:{rep.get('test_id')}"] = {
            "prov:type": "prov:Activity", "r2a2:activityKind": "replicate",
            "r2a2:independenceLevel": rep.get("independence_level"),
        }
    for att in attestations:
        activity[f"r2a2:activity:review:{att.get('reviewer')}"] = {
            "prov:type": "prov:Activity", "r2a2:activityKind": "review",
            "r2a2:verdict": att.get("verdict"),
        }
    for tr in transfers:
        activity["r2a2:activity:transfer"] = {
            "prov:type": "prov:Activity", "r2a2:activityKind": "transfer",
            "r2a2:outcome": tr.get("outcome"),
        }

    agent: Dict[str, Any] = {}
    for name in list(authors) + list(reviewers):
        role = "author" if name in authors else "reviewer"
        agent[f"r2a2:agent:{name}"] = {
            "prov:type": ["prov:Agent", "prov:Person"],
            "r2a2:role": role,
        }

    # ------------------------------------------------------------------
    # RELATION maps — the PROV-JSON required shape. Relations live here,
    # keyed by relation-instance id, NEVER inside entity/activity records.
    # ------------------------------------------------------------------
    used: Dict[str, Any] = {
        "r2a2:used:run-manifest": {
            "prov:activity": run_id, "prov:entity": manifest_id,
        },
        "r2a2:used:compile-theory": {
            "prov:activity": compile_id, "prov:entity": theory_id,
        },
    }
    for rec in results:
        used[f"r2a2:used:run-{rec.get('experiment')}"] = {
            "prov:activity": run_id,
            "prov:entity": f"r2a2:manifest:{rec.get('manifest_hash', '')[:16]}",
        }
    for att in attestations:
        used[f"r2a2:used:review-{att.get('reviewer')}"] = {
            "prov:activity": f"r2a2:activity:review:{att.get('reviewer')}",
            "prov:entity": [f"r2a2:manifest:{str(att.get('manifest_hash'))[:16]}",
                            f"r2a2:result:{str(att.get('result_hash'))[:16]}"],
        }

    was_generated_by: Dict[str, Any] = {}
    for rec in results:
        was_generated_by[f"r2a2:gen:{rec.get('experiment')}"] = {
            "prov:entity": f"r2a2:result:{rec.get('experiment')}",
            "prov:activity": run_id,
        }

    was_derived_from: Dict[str, Any] = {
        "r2a2:deriv:manifest-from-theory": {
            "prov:generatedEntity": manifest_id,
            "prov:usedEntity": theory_id,
        },
    }
    for pred in theory_dict.get("predictions", []):
        was_derived_from[f"r2a2:deriv:pred-{pred['id']}"] = {
            "prov:generatedEntity": f"r2a2:prediction:{pred['id']}",
            "prov:usedEntity": [f"r2a2:assumption:{a}"
                                for a in pred.get("assumptions", [])]
            + [f"r2a2:parameter:{p}" for p in pred.get("parameters", [])],
        }

    was_attributed_to: Dict[str, Any] = {}
    for name in authors:
        was_attributed_to[f"r2a2:attr:theory-{name}"] = {
            "prov:entity": theory_id, "prov:agent": f"r2a2:agent:{name}",
        }
    for att in attestations:
        was_attributed_to[f"r2a2:attr:review-{att.get('reviewer')}"] = {
            "prov:entity": f"r2a2:activity:review:{att.get('reviewer')}",
            "prov:agent": f"r2a2:agent:{att.get('reviewer')}",
        }

    was_associated_with: Dict[str, Any] = {
        "r2a2:assoc:run": {"prov:activity": run_id,
                           "prov:agent": [f"r2a2:agent:{a}" for a in authors]
                           or None},
    }

    doc: Dict[str, Any] = {
        "prefix": {"prov": PROV_NS, "r2a2": R2A2_NS},
        "entity": entity,
        "activity": activity,
        "agent": agent,
        "used": used,
        "wasGeneratedBy": was_generated_by,
        "wasDerivedFrom": was_derived_from,
        "wasAttributedTo": was_attributed_to,
        "wasAssociatedWith": {k: v for k, v in was_associated_with.items()
                              if v.get("prov:agent")},
        "r2a2_profile": {
            "note": "R2A2-specific epistemic terms (identifying assumption, "
                    "kill condition, hostile control, evidence grade, "
                    "parameter transfer, protocol failure, theory failure) "
                    "are serialized in the r2a2: namespace, not as prov: "
                    "semantics.",
            "provenanceSpec": "PROV-JSON (W3C Member Submission, 2013) — "
                              "not a W3C Recommendation.",
            "schemaVersion": SCHEMA_VERSION,
            "codeRevision": code_revision,
        },
    }
    return doc


def check_prov_conformance(doc: dict) -> List[str]:
    """Structural PROV-JSON conformance check. Returns violations.

    Enforces: prefix map exists; relations live in TOP-LEVEL relation maps;
    entity/activity records do NOT embed relation keys; every relation
    references declared ids.
    """
    errors: List[str] = []
    if "prefix" not in doc:
        errors.append("PROV-JSON requires a prefix map")
    entity = doc.get("entity", {})
    activity = doc.get("activity", {})
    known = set(entity) | set(activity) | set(doc.get("agent", {}))

    # relations must NOT be embedded inside entity/activity records
    relation_keys = {"prov:used", "prov:generated", "prov:activity",
                     "prov:entity", "prov:agent", "prov:generatedEntity",
                     "prov:usedEntity"}
    for kind, records in (("entity", entity), ("activity", activity)):
        for rid, rec in records.items():
            embedded = relation_keys & set(rec)
            if embedded:
                errors.append(
                    f"{kind} {rid!r} embeds relation key(s) {sorted(embedded)}; "
                    "PROV-JSON requires relations in top-level relation maps")

    # required relation maps must exist as top-level maps
    for relmap in ("used", "wasGeneratedBy", "wasDerivedFrom"):
        if relmap not in doc:
            errors.append(f"missing top-level relation map {relmap!r}")

    # relation references must resolve
    for relmap in ("used", "wasGeneratedBy", "wasDerivedFrom",
                   "wasAttributedTo", "wasAssociatedWith"):
        for rid, rec in doc.get(relmap, {}).items():
            if not isinstance(rec, dict):
                errors.append(f"{relmap}/{rid}: relation value must be an object")
                continue
            for k, v in rec.items():
                refs = v if isinstance(v, list) else [v]
                for r in refs:
                    if isinstance(r, str) and r.startswith("r2a2:"):
                        # r2a2: references must resolve within this document
                        if r not in known:
                            errors.append(
                                f"{relmap}/{rid}: reference {r!r} does not "
                                "resolve to a declared id")
    return errors
