# RAI — Reality Research Auditing Assistant

A local-first, evidence-aware **scientific claim and reproducibility auditor**.
Not a truth engine: RAI audits the structural soundness, provenance, and honest
labeling of a project's claim/evidence records. See [`RAI_GENERAL_CHARTER.md`](RAI_GENERAL_CHARTER.md).

## Status

Pre-implementation. The first deliverable is design artifacts only:

- `RAI_GENERAL_CHARTER.md` — mission, non-mission, claim graph, status vocabulary,
  preregistration rules, calibration policy, plugin boundary, human decision points.
- `rai/schema/` — JSON Schema for claim records, reproducibility runs, and
  preregistrations.
- `examples/minimal_project/` — a domain-neutral worked example.
- `tests/` — schema-validation tests only.

No CLI, database, LLM integration, plugins, or execution runner exists yet by design.

## Install (dev)

```bash
pip install -e ".[dev]"
pytest
```

## Example

```bash
pytest tests/ -v
```

The minimal example demonstrates `DECLARED_INPUT`, `COMPUTED`, `NEGATIVE_RESULT`,
`RETRACTED` (with supersession), `UNRESOLVED`, and `OUT_OF_SCOPE` — and contains no
statement that any claim is scientifically true.

## Non-goals

RAI does not certify truth, novelty, validity, or peer-review readiness, does not access
the network, and does not mutate anything without explicit human review.
