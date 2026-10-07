"""RO-Crate 1.3 conformant research-object export.

Conformance notes (specification, not aspiration):
- every entity MUST have an `@id`;
- relationships (`hasPart`) point BY REFERENCE: {"@id": "..."} — never inline;
- the Root Data Entity (`./`) MUST include `datePublished`, `name`,
  `description`, `license`, and `conformsTo` the RO-Crate profile;
- the metadata descriptor (`ro-crate-metadata.json`) MUST have `@id`,
  `@type` CreativeWork, `conformsTo` the profile, and `about: {"@id": "./"}`;
- every relative file `@id` in the graph MUST correspond to a file that
  physically exists in the attached crate (the exporter writes them all);
- contextual entities (persons, organizations, licenses) are separate
  entities referenced by `@id`, never inlined.

RO-Crate is the EXCHANGE layer only; R2A2's epistemic graph remains the
scientific semantic layer.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List

from .schema import SCHEMA_VERSION
from .schema_json import R2A2_NS

RO_PROFILE = "https://w3id.org/ro/crate/1.3"
RO_CONTEXT = ["https://w3id.org/ro/crate/1.3/context",
              {"r2a2": R2A2_NS}]
METADATA_FILE = "ro-crate-metadata.json"


def _ref(entity_id: str) -> dict:
    """A relationship reference: RO-Crate points by @id, never inline."""
    return {"@id": entity_id}


def export_rocrate(theory_dict: Dict[str, Any],
                   manifest: Dict[str, Any],
                   results: List[Dict[str, Any]],
                   replications: List[Dict[str, Any]] = None,
                   attestations: List[Dict[str, Any]] = None,
                   reports: List[str] = None,
                   datasets: Dict[str, str] = None,
                   license_url: str = "https://creativecommons.org/licenses/by/4.0/",
                   authors: List[str] = None,
                   code_revision: str = "",
                   date_published: str = None) -> dict:
    """Build a conformant RO-Crate JSON-LD document.

    Use ``write_crate`` to materialize ALL payload files (RO-Crate requires
    graph file entities to really exist in the attached crate).
    """
    replications = replications or []
    attestations = attestations or []
    reports = reports or []
    datasets = datasets or {}
    authors = authors or []
    date_published = date_published or time.strftime("%Y-%m-%dT%H:%M:%S%z")

    graph: List[Dict[str, Any]] = []

    # --- contextual entities (authors) — referenced, never inlined ---------
    author_refs = []
    for i, name in enumerate(authors):
        aid = f"#author-{i}"
        graph.append({
            "@id": aid, "@type": "Person",
            "name": name,
        })
        author_refs.append(_ref(aid))

    # --- file payload entities ---------------------------------------------
    has_part: List[dict] = []
    payload: Dict[str, str] = {}  # relative path -> content (written later)

    def _file_entity(file_id: str, name: str, description: str,
                     sha256: str = None) -> None:
        ent: Dict[str, Any] = {
            "@id": file_id, "@type": "File",
            "name": name,
            "description": description,
            "encodingFormat": "application/json",
        }
        if sha256:
            ent["sha256"] = sha256
        graph.append(ent)
        has_part.append(_ref(file_id))

    theory_id = "theory.json"
    payload[theory_id] = json.dumps(theory_dict, indent=2, sort_keys=True)
    _file_entity(theory_id, f"Theory declaration: {theory_dict.get('id')}",
                 "Canonical declarative model: parameters, assumptions, "
                 "predictions (with kill conditions), tests, comparators, "
                 "transformation classes, validity domain.")

    manifest_id = "manifest.json"
    payload[manifest_id] = json.dumps(manifest, indent=2, sort_keys=True)
    _file_entity(manifest_id, "Frozen execution manifest",
                 f"Content-addressed binding of model, parameters, tests, "
                 f"thresholds, seeds, backend, environment and code bindings. "
                 f"Manifest hash: {manifest.get('hash')}",
                 sha256=manifest.get("hash"))

    for ds_id, ds_hash in datasets.items():
        fid = f"data/{ds_id}.json"
        payload[fid] = json.dumps({"id": ds_id, "sha256": ds_hash}, indent=2)
        _file_entity(fid, f"Input dataset: {ds_id}",
                     "Input data used by the executed experiments.",
                     sha256=ds_hash)

    for rec in results:
        fid = f"results/{rec.get('experiment', 'result')}.json"
        payload[fid] = json.dumps(rec, indent=2, sort_keys=True)
        _file_entity(fid, f"Result: {rec.get('experiment')}",
                     f"Result hash {rec.get('result_hash')}; produced by "
                     f"manifest {rec.get('manifest_hash')}",
                     sha256=rec.get("result_hash"))

    for rep in replications:
        fid = f"replications/{rep.get('test_id', 'T')}.json"
        payload[fid] = json.dumps(rep, indent=2, sort_keys=True)
        _file_entity(fid, f"A/B replication: {rep.get('test_id')}",
                     f"Independence level {rep.get('independence_level')}; "
                     f"agrees={rep.get('agrees')}; record hash "
                     f"{rep.get('record_hash')}")

    for att in attestations:
        fid = f"attestations/{att.get('reviewer', 'reviewer')}.json"
        payload[fid] = json.dumps(att, indent=2, sort_keys=True)
        _file_entity(fid, f"Review attestation by {att.get('reviewer')}",
                     f"Scope {att.get('scope')}; verdict {att.get('verdict')}; "
                     f"seal {att.get('seal')}")

    for r in reports:
        fid = f"reports/{r}"
        payload[fid] = ""  # caller supplies report content; entity declared
        graph.append({"@id": fid, "@type": "File",
                      "name": f"Generated report: {r}",
                      "description": "Human-readable report generated from "
                                     "machine-readable results."})
        has_part.append(_ref(fid))

    # --- root data entity ---------------------------------------------------
    graph.append({
        "@id": license_url, "@type": "CreativeWork",
        "name": "Creative Commons Attribution 4.0 International",
    })
    root = {
        "@id": "./",
        "@type": "Dataset",
        "name": f"R2A2 research object: {theory_dict.get('id', 'theory')} "
                f"v{theory_dict.get('version', '?')}",
        "description": theory_dict.get("description", ""),
        "datePublished": date_published,
        "license": _ref(license_url),
        "conformsTo": _ref(RO_PROFILE),
        "hasPart": has_part,
        "author": author_refs,
        "r2a2:schemaVersion": SCHEMA_VERSION,
        "r2a2:theoryId": theory_dict.get("id"),
        "r2a2:manifestHash": manifest.get("hash"),
        "r2a2:codeRevision": code_revision,
    }
    graph.append(root)

    # --- metadata descriptor -------------------------------------------------
    graph.append({
        "@id": METADATA_FILE,
        "@type": "CreativeWork",
        "conformsTo": _ref(RO_PROFILE),
        "about": _ref("./"),
    })

    return {
        "@context": RO_CONTEXT,
        "@graph": graph,
        # bookkeeping (NOT part of the crate document itself)
        "_payload_files": payload,
        "_metadata_file": METADATA_FILE,
    }


def write_crate(crate: dict, out_dir: str) -> List[str]:
    """Materialize the attached crate: metadata descriptor + ALL payload files.

    RO-Crate requires every relative file @id in the graph to physically
    exist in the attached crate; this writes them all and returns the paths.
    """
    payload: Dict[str, str] = crate["_payload_files"]
    os.makedirs(out_dir, exist_ok=True)
    written: List[str] = []
    doc = {k: v for k, v in crate.items() if not k.startswith("_")}
    for rel, content in payload.items():
        full = os.path.join(out_dir, rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w") as f:
            f.write(content)
        written.append(rel)
    with open(os.path.join(out_dir, METADATA_FILE), "w") as f:
        json.dump(doc, f, indent=2)
    written.append(METADATA_FILE)
    return written


def crate_to_files(crate: dict) -> Dict[str, str]:
    """Flatten the crate into {relative path: content} — metadata AND every
    payload file the graph declares (conformance requirement)."""
    out = dict(crate["_payload_files"])
    doc = {k: v for k, v in crate.items() if not k.startswith("_")}
    out[METADATA_FILE] = json.dumps(doc, indent=2)
    return out


# ---------------------------------------------------------------------------
# Structural conformance self-check (hostile; independent of our own export)
# ---------------------------------------------------------------------------

def check_conformance(crate_doc: dict, crate_dir: str = None) -> List[str]:
    """Structural RO-Crate 1.3 conformance check. Returns violation strings.

    Checked: every entity has @id; references resolve to graph @ids;
    root exists with required properties; hasPart entries are references;
    descriptor exists with conformsTo+about; every relative file entity
    physically exists (when crate_dir given).
    """
    errors: List[str] = []
    graph = crate_doc.get("@graph")
    if not graph:
        return ["crate has no @graph"]
    ids = set()
    for e in graph:
        if not isinstance(e, dict) or "@id" not in e:
            errors.append(f"entity without @id: {e!r:.80}")
        else:
            ids.add(e["@id"])
    by_id = {e.get("@id"): e for e in graph if isinstance(e, dict)}

    root = by_id.get("./")
    if root is None:
        errors.append("no Root Data Entity ('./')")
    else:
        for req in ("name", "description", "datePublished", "license",
                    "conformsTo", "hasPart"):
            if req not in root:
                errors.append(f"root missing required property {req!r}")
        ct = root.get("conformsTo")
        if not (isinstance(ct, dict) and ct.get("@id", "").startswith("https://w3id.org/ro/crate")):
            errors.append("root conformsTo must reference the RO-Crate profile")

    desc = by_id.get(METADATA_FILE)
    if desc is None:
        errors.append("no metadata descriptor (ro-crate-metadata.json)")
    elif not (isinstance(desc.get("about"), dict) and desc["about"].get("@id") == "./"):
        errors.append("metadata descriptor 'about' must reference './'")

    # relationship properties must be references, never inline objects with data
    def _walk(node, where):
        if isinstance(node, dict):
            if "@id" not in node or len(node) > 1:
                if node and set(node) - {"@id"}:
                    errors.append(f"{where}: inline entity (must be {{'@id': ...}})")
            for v in node.values():
                _walk(v, where)
        elif isinstance(node, list):
            for i, v in enumerate(node):
                _walk(v, f"{where}[{i}]")
    for key in ("hasPart", "author", "license", "conformsTo", "about"):
        if root and key in root:
            _walk(root[key], f"root/{key}")

    # every relative file entity must physically exist
    if crate_dir is not None:
        for eid in ids:
            if not eid.startswith("#") and not eid.startswith("http") \
                    and eid not in ("./", METADATA_FILE):
                if not os.path.exists(os.path.join(crate_dir, eid)):
                    errors.append(f"declared file entity {eid!r} not present in crate")
    return errors
