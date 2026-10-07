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


def _result_entity_for(att: dict, results: list) -> str:
    """Resolve an attestation's result reference to the declared result Entity ID.

    Result entities are keyed by EXPERIMENT (matching the runner's output), so
    an attestation's result_hash is matched against the declared results. If
    no match exists, the attestation still references a real declared entity
    by falling back to the manifest it reviewed.
    """
    target_hash = str(att.get("result_hash", ""))
    for rec in results:
        if rec.get("result_hash") == target_hash:
            return f"r2a2:result:{rec.get('experiment')}"
    # attestation references a result not in this export: reference the
    # reviewed manifest instead so the identifier still resolves
    return f"r2a2:manifest:{str(att.get('manifest_hash'))[:16]}"


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
    #
    # SEMANTIC RULES (v0.4.2):
    # - every relation record has SINGLE-VALUED endpoints; multiple
    #   relationships = multiple relation records, never arrays;
    # - wasAttributedTo is ENTITY -> AGENT only (activities use
    #   wasAssociatedWith); a review's attestation is modelled as an entity
    #   so it can be attributed to the reviewer;
    # - result entities are keyed by experiment (matching what the runner
    #   produces), so review references resolve exactly.
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
    for i, att in enumerate(attestations):
        reviewer = att.get('reviewer', 'reviewer')
        # each reviewed artifact gets its OWN single-endpoint used record
        used[f"r2a2:used:review-{reviewer}-manifest"] = {
            "prov:activity": f"r2a2:activity:review:{reviewer}",
            "prov:entity": f"r2a2:manifest:{str(att.get('manifest_hash'))[:16]}",
        }
        used[f"r2a2:used:review-{reviewer}-result"] = {
            "prov:activity": f"r2a2:activity:review:{reviewer}",
            # result entities are keyed by experiment; find the matching one
            "prov:entity": _result_entity_for(att, results),
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
        # one derivation record per dependency — never a list endpoint
        for dep in list(pred.get("assumptions", [])):
            was_derived_from[f"r2a2:deriv:pred-{pred['id']}-assumption-{dep}"] = {
                "prov:generatedEntity": f"r2a2:prediction:{pred['id']}",
                "prov:usedEntity": f"r2a2:assumption:{dep}",
            }
        for dep in list(pred.get("parameters", [])):
            was_derived_from[f"r2a2:deriv:pred-{pred['id']}-parameter-{dep}"] = {
                "prov:generatedEntity": f"r2a2:prediction:{pred['id']}",
                "prov:usedEntity": f"r2a2:parameter:{dep}",
            }

    # wasAttributedTo is ENTITY -> AGENT. Review attestations are modelled as
    # entities so reviewers can be attributed; activities use
    # wasAssociatedWith instead.
    for i, att in enumerate(attestations):
        reviewer = att.get('reviewer', 'reviewer')
        entity[f"r2a2:attestation:{reviewer}-{i}"] = {
            "prov:type": ["prov:Entity", f"{R2A2_NS}ReviewAttestation"],
            "r2a2:scope": att.get("scope"),
            "r2a2:verdict": att.get("verdict"),
            "r2a2:seal": att.get("seal"),
        }

    was_attributed_to: Dict[str, Any] = {}
    for name in authors:
        was_attributed_to[f"r2a2:attr:theory-{name}"] = {
            "prov:entity": theory_id, "prov:agent": f"r2a2:agent:{name}",
        }
    for i, att in enumerate(attestations):
        reviewer = att.get('reviewer', 'reviewer')
        was_attributed_to[f"r2a2:attr:attestation-{reviewer}-{i}"] = {
            # entity -> agent: the ATTESTATION ENTITY is attributed
            "prov:entity": f"r2a2:attestation:{reviewer}-{i}",
            "prov:agent": f"r2a2:agent:{reviewer}",
        }

    # wasAssociatedWith: ACTIVITY -> AGENT, one record per pair
    was_associated_with: Dict[str, Any] = {}
    for name in authors:
        was_associated_with[f"r2a2:assoc:run-{name}"] = {
            "prov:activity": run_id, "prov:agent": f"r2a2:agent:{name}",
        }
    for att in attestations:
        reviewer = att.get('reviewer', 'reviewer')
        was_associated_with[f"r2a2:assoc:review-{reviewer}"] = {
            "prov:activity": f"r2a2:activity:review:{reviewer}",
            "prov:agent": f"r2a2:agent:{reviewer}",
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

    Enforces (v0.4.2): prefix map exists; relations live in TOP-LEVEL relation
    maps; entity/activity records do NOT embed relation keys; every relation
    has SINGLE-VALUED endpoints of the CORRECT TYPE (entity/activity/agent)
    that resolve to declared ids.
    """
    errors: List[str] = []
    if "prefix" not in doc:
        errors.append("PROV-JSON requires a prefix map")
    entity = doc.get("entity", {})
    activity = doc.get("activity", {})
    agents = doc.get("agent", {})
    known = set(entity) | set(activity) | set(agents)

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

    # ---- single-valued endpoints + endpoint TYPE + resolution -------------
    # (relmap, endpoint key, required endpoint kind)
    SPEC = {
        "used": {"prov:activity": "activity", "prov:entity": "entity"},
        "wasGeneratedBy": {"prov:entity": "entity", "prov:activity": "activity"},
        "wasDerivedFrom": {"prov:generatedEntity": "entity",
                           "prov:usedEntity": "entity"},
        "wasAttributedTo": {"prov:entity": "entity", "prov:agent": "agent"},
        "wasAssociatedWith": {"prov:activity": "activity", "prov:agent": "agent"},
    }
    kind_of = {}
    for eid in entity:
        kind_of[eid] = "entity"
    for aid in activity:
        kind_of[aid] = "activity"
    for gid in agents:
        kind_of[gid] = "agent"

    for relmap, endpoints in SPEC.items():
        records = doc.get(relmap)
        if records is None and relmap in ("wasAttributedTo", "wasAssociatedWith"):
            continue  # optional maps
        if not isinstance(records, dict):
            errors.append(f"{relmap}: must be a top-level relation map")
            continue
        for rid, rec in records.items():
            if not isinstance(rec, dict):
                errors.append(f"{relmap}/{rid}: relation value must be an object")
                continue
            for endpoint, expected_kind in endpoints.items():
                if endpoint not in rec:
                    errors.append(f"{relmap}/{rid}: missing endpoint {endpoint}")
                    continue
                value = rec[endpoint]
                # CARDINALITY: endpoints must be single-valued strings
                if isinstance(value, list):
                    errors.append(
                        f"{relmap}/{rid}: {endpoint} is a LIST; PROV requires "
                        "separate relation records, one per assertion")
                    continue
                if not isinstance(value, str):
                    errors.append(
                        f"{relmap}/{rid}: {endpoint} must be an identifier "
                        f"string, got {type(value).__name__}")
                    continue
                # ENDPOINT TYPE: the referenced id must be of the right kind
                if value in kind_of and kind_of[value] != expected_kind:
                    errors.append(
                        f"{relmap}/{rid}: {endpoint} references {value!r} which "
                        f"is a {kind_of[value]}, but {relmap} requires a "
                        f"{expected_kind}")
                # RESOLUTION
                if value.startswith("r2a2:") and value not in known:
                    errors.append(
                        f"{relmap}/{rid}: reference {value!r} does not resolve "
                        "to a declared id")
            # unknown endpoint keys are suspicious
            for k in rec:
                if k not in endpoints and k.startswith("prov:"):
                    errors.append(
                        f"{relmap}/{rid}: unexpected PROV endpoint {k!r} for "
                        f"{relmap}")

    return errors
