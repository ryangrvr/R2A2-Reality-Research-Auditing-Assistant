"""Research-object export: RO-Crate-compatible package.

RO-Crate is the EXCHANGE layer only — R2A2's epistemic graph remains the
scientific semantic layer. The crate contains (or references): the theory
declaration, frozen execution manifest, source revision, input data, result
records, replication records, review attestations, generated reports,
license/authorship metadata and the R2A2 schema version.

An independent consumer must be able to identify from the crate alone:
what was proposed, what was assumed, what code/data were executed, which
result came from which manifest, and which review/replication records apply.
"""

from __future__ import annotations

from typing import Any, Dict, List

from .schema import SCHEMA_VERSION, stamp
from .schema_json import R2A2_NS

# RO-Crate context and classes (subset; spec 1.3)
RO_CONTEXT = "https://w3id.org/ro/crate/1.3/context"
RO_METADATA = "ro-crate-metadata.json"
RO_PROFILE = "https://w3id.org/ro/crate/1.3"


def _dataset_entity(name: str, about: str) -> dict:
    return {"@type": "Dataset", "name": name, "description": about}


def export_rocrate(theory_dict: Dict[str, Any],
                   manifest: Dict[str, Any],
                   results: List[Dict[str, Any]],
                   replications: List[Dict[str, Any]] = None,
                   attestations: List[Dict[str, Any]] = None,
                   reports: List[str] = None,
                   datasets: Dict[str, str] = None,
                   license: str = "https://creativecommons.org/licenses/by/4.0/",
                   authors: List[str] = None,
                   code_revision: str = "") -> dict:
    """Build an RO-Crate JSON-LD document from R2A2 artifacts.

    All inputs are plain dicts (machine-readable, hash-bound artifacts).
    """
    replications = replications or []
    attestations = attestations or []
    reports = reports or []
    datasets = datasets or {}
    authors = authors or []

    hasPart: List[Dict[str, Any]] = []

    # root
    root: Dict[str, Any] = {
        "@type": "Dataset",
        "name": f"R2A2 research object: {theory_dict.get('id', 'theory')} "
                f"v{theory_dict.get('version', '?')}",
        "description": theory_dict.get("description", ""),
        "license": license,
        "r2a2:schemaVersion": SCHEMA_VERSION,
        "r2a2:theoryId": theory_dict.get("id"),
        "r2a2:manifestHash": manifest.get("hash"),
        "r2a2:codeRevision": code_revision,
    }
    for a in authors:
        root.setdefault("author", []).append({"@type": "Person", "name": a})

    # theory declaration (the proposal + assumptions)
    theory_entity = {
        "@type": "File",
        "id": "theory.json",
        "name": f"Theory declaration: {theory_dict.get('id')}",
        "description": "Canonical declarative model: parameters, assumptions, "
                       "predictions (with kill conditions), tests, comparators, "
                       "transformation classes, validity domain.",
        "encodingFormat": "application/json",
    }
    hasPart.append(theory_entity)

    # frozen execution manifest
    manifest_entity = {
        "@type": "File",
        "id": "manifest.json",
        "name": "Frozen execution manifest",
        "description": "Content-addressed binding of model, parameters, tests, "
                       "thresholds, seeds, backend, environment and code "
                       f"bindings. Hash: {manifest.get('hash')}",
        "sha256": manifest.get("hash"),
        "encodingFormat": "application/json",
    }
    hasPart.append(manifest_entity)

    # input datasets
    for ds_id, ds_hash in datasets.items():
        hasPart.append({
            "@type": "File",
            "id": f"data/{ds_id}.json",
            "name": f"Input dataset: {ds_id}",
            "sha256": ds_hash,
            "description": "Input data used by the executed experiments.",
        })

    # result records
    for rec in results:
        hasPart.append({
            "@type": "File",
            "id": f"results/{rec.get('experiment', 'result')}.json",
            "name": f"Result: {rec.get('experiment')}",
            "description": f"Result hash {rec.get('result_hash')}; produced by "
                           f"manifest {rec.get('manifest_hash')}",
            "sha256": rec.get("result_hash"),
            "encodingFormat": "application/json",
        })

    # replications
    for rep in replications:
        hasPart.append({
            "@type": "File",
            "id": f"replications/{rep.get('test_id')}.json",
            "name": f"A/B replication: {rep.get('test_id')}",
            "description": f"Independence level {rep.get('independence_level')}; "
                           f"agrees={rep.get('agrees')}; "
                           f"record hash {rep.get('record_hash')}",
        })

    # attestations
    for att in attestations:
        hasPart.append({
            "@type": "File",
            "id": f"attestations/{att.get('reviewer')}.json",
            "name": f"Review attestation by {att.get('reviewer')}",
            "description": f"Scope {att.get('scope')}; verdict "
                           f"{att.get('verdict')}; seal {att.get('seal')}",
        })

    # reports (human-readable, generated from machine-readable results)
    for r in reports:
        hasPart.append({"@type": "File", "id": f"reports/{r}",
                        "name": f"Generated report: {r}"})

    root["hasPart"] = hasPart

    return {
        "@context": [RO_CONTEXT, {**{"r2a2": R2A2_NS}}],
        "@graph": [
            {**root, "@id": "./"},
            {"@type": "CreativeWork", "@id": RO_METADATA,
             "about": {"@id": "./"},
             "conformsTo": {"@id": RO_PROFILE}},
            {**theory_entity, "@id": theory_entity["id"],
             "@content": theory_dict},
            {**manifest_entity, "@id": manifest_entity["id"],
             "@content": manifest},
            *[{"@id": e["id"], **e} for e in hasPart[2:]],
        ],
    }


def crate_to_files(crate: dict) -> Dict[str, str]:
    """Flatten a crate into {path: json-serialized-content} for writing."""
    out = {
        RO_METADATA: __import__("json").dumps(crate, indent=2),
    }
    for node in crate.get("@graph", []):
        content = node.get("@content")
        if content is not None and node.get("@id", "").endswith(".json"):
            out[node["@id"]] = __import__("json").dumps(content, indent=2)
        node.pop("@content", None)
    # rewrite metadata without inline content
    out[RO_METADATA] = __import__("json").dumps(crate, indent=2)
    return out
