"""W3C PROV export: map R2A2 concepts into standard provenance.

Mapping (only where natural — R2A2-specific epistemic terms stay in the
r2a2: namespace/profile, never forced into misleading PROV semantics):

- entities:  theory declaration, execution manifest, datasets, results
- activities: compile, run (execution), replicate, review, transfer
- agents:    author, reviewer, replicator
- relations: result wasGeneratedBy execution; manifest wasDerivedFrom theory;
             review used manifest+result; prediction depended on assumptions
             and parameters (as r2a2: extensions).
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
    """Build a PROV-JSON document."""
    results = results or []
    replications = replications or []
    attestations = attestations or []
    transfers = transfers or []
    authors = authors or []
    reviewers = reviewers or []

    theory_id = f"r2a2:theory:{theory_dict.get('id')}"
    manifest_id = f"r2a2:manifest:{manifest.get('hash', '')[:16]}"

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
            "prov:wasDerivedFrom": {"prov:entity": theory_id},
        },
    }
    # predictions as R2A2-namespace entities with kill conditions
    for pred in theory_dict.get("predictions", []):
        entity[f"r2a2:prediction:{pred['id']}"] = {
            "prov:type": ["prov:Entity", f"{R2A2_NS}Prediction"],
            "r2a2:killCondition": pred.get("kill_condition"),
            "r2a2:evidenceGrade": pred.get("evidence_grade"),
            "prov:wasDerivedFrom": {
                "prov:entity": [f"r2a2:assumption:{a}" for a in pred.get("assumptions", [])]
                + [f"r2a2:parameter:{p}" for p in pred.get("parameters", [])]
            },
        }
    for a in theory_dict.get("assumptions", []):
        entity[f"r2a2:assumption:{a['id']}"] = {
            "prov:type": ["prov:Entity", f"{R2A2_NS}{a.get('kind', 'assumption').capitalize()}"],
            "r2a2:text": a.get("text"),
        }
    for p in theory_dict.get("parameters", []):
        entity[f"r2a2:parameter:{p['name']}"] = {
            "prov:type": ["prov:Entity", f"{R2A2_NS}Parameter"],
            "r2a2:provenanceKind": p.get("kind"),
            "r2a2:sector": p.get("sector"),
        }
    for rec in results:
        rid = f"r2a2:result:{rec.get('experiment')}"
        entity[rid] = {
            "prov:type": ["prov:Entity", f"{R2A2_NS}ResultRecord"],
            "r2a2:resultHash": rec.get("result_hash"),
        }

    activity: Dict[str, Any] = {
        "r2a2:activity:compile": {
            "prov:type": "prov:Activity",
            "r2a2:activityKind": "compile",
        },
        "r2a2:activity:run": {
            "prov:type": "prov:Activity",
            "prov:used": manifest_id,
            "r2a2:activityKind": "run",
            "r2a2:backend": manifest.get("backend"),
        },
    }
    for rec in results:
        activity[f"r2a2:activity:run"].setdefault("prov:generated", []).append(
            f"r2a2:result:{rec.get('experiment')}")
    for rep in replications:
        activity[f"r2a2:activity:replicate:{rep.get('test_id')}"] = {
            "prov:type": "prov:Activity",
            "r2a2:activityKind": "replicate",
            "r2a2:independenceLevel": rep.get("independence_level"),
        }
    for att in attestations:
        activity[f"r2a2:activity:review:{att.get('reviewer')}"] = {
            "prov:type": "prov:Activity",
            "r2a2:activityKind": "review",
            "prov:used": [att.get("manifest_hash"), att.get("result_hash")],
            "r2a2:verdict": att.get("verdict"),
        }
    for tr in transfers:
        activity[f"r2a2:activity:transfer"] = {
            "prov:type": "prov:Activity",
            "r2a2:activityKind": "transfer",
            "r2a2:outcome": tr.get("outcome"),
        }

    agent: Dict[str, Any] = {}
    for a in authors:
        agent[f"r2a2:agent:{a}"] = {"prov:type": "prov:Agent",
                                    "prov:type2": "prov:Person", "name": a}
    for r in reviewers:
        agent[f"r2a2:agent:{r}"] = {"prov:type": "prov:Agent",
                                    "prov:type2": "prov:Person", "name": r}

    return {
        "prefix": {
            "prov": PROV_NS,
            "r2a2": R2A2_NS,
        },
        "entity": entity,
        "activity": activity,
        "agent": agent,
        "r2a2_profile": {
            "description": "R2A2-specific epistemic terms (not part of core PROV): "
                           "identifying assumption, kill condition, hostile control, "
                           "evidence grade, parameter transfer, protocol failure, "
                           "theory failure. See r2a2-science.org/schema.",
            "schemaVersion": SCHEMA_VERSION,
            "codeRevision": code_revision,
        },
    }
