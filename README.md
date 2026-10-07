# R2A2 — Reality Research Auditing Assistant

**Package name:** `r2a2-science` (collision-resistant; the project title is
*R2A2 — Reality Research Auditing Assistant*).

R2A2 is a general-purpose **hypothesis auditing and execution framework**. It
turns a declarative theory manifest into a compiled, immutable test graph,
executes it on a pluggable compute backend, and audits the **dependency and
provenance structure** of every claim.

> **R2A2 verifies discipline, not truth.** Passing an audit means the test
> protocol was executed correctly and the claim graph is well-provenanced —
> it never means the theory is true.

## Four pillars

1. **Theory SDK** — a hook/plugin protocol (`r2a2.api`) for registering
   theories, parameters, assumptions, observables, predictions, comparators,
   hostile controls and kill conditions. Third-party theories install without
   changing R2A2 core.
2. **Compute fabric** — a backend protocol (`r2a2.backends`) with a pure
   NumPy/local-Python implementation. JAX, PyTorch or external solvers plug
   in; none of them leak into the theory API.
3. **Epistemic ledger** — the canonical object is a **dependency graph**, not
   a scalar sum. Scalar debt scores are derived summaries and can be misleading
   (the original GRUT auditor's net was a blind sum that could not detect
   double counting).
4. **Test protocol engine** — preregistered manifests, blind/candidate-blind
   holdouts, hostile controls, comparator audits, kill/bank/extend verdicts,
   and frozen execution manifests whose hash binds model, seeds, backend and
   data before results are opened.

## Quick start

```bash
pip install -e .
r2a2 init mytheory
r2a2 validate mytheory/theory.yaml
r2a2 compile mytheory/theory.yaml
r2a2 run mytheory
r2a2 audit mytheory
r2a2 report mytheory
```

## Non-goals (v0.1)

- No claim to certify truth.
- No physics ontology in core (GRUT, Hilbert spaces, cosmology all live in plugins).
- No single PASS/FAIL vocabulary or single epistemic score.
- No GPU/HPC work before the semantic core is stable.
