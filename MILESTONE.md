# R2A2 v0.4 — external adoption & interoperability

v0.4 question: **can an outside researcher encode, test, export, exchange and
inspect a scientific theory without help from the framework's authors?**

## External check ruling recorded
`336ce58` — checked: ChatGPT — NO OPEN ISSUE within the v0.3 trust scope.
**v0.3 trust/reproducibility boundary BANKED.** Stopping rule honored.

## What v0.4 added

### A. Public JSON Schema (2020-12) — the interoperability contract
`r2a2 schema --json` emits the schema; `r2a2 validate-artifact <file>`
validates. Generated from the live vocabulary (enums/required fields) so the
Python objects and the contract cannot silently drift. Unknown required
fields fail; invalid enums fail; unknown schema versions fail; `x_*`
extension namespaces allowed without weakening core validation. Dependency-
free validator included (jsonschema used when present).

### B. RO-Crate export (`r2a2 export-rocrate`)
Standard research-object packaging: theory declaration, frozen manifest
(sha256), input datasets, result records (result_hash), replications,
attestations, reports, license/authorship, schema version. RO-Crate is the
exchange layer; the epistemic graph remains R2A2's semantic layer.

### C. W3C PROV export (`r2a2 export-prov`)
Natural mappings: theory/manifests/results/data → entities; compile/run/
replicate/review/transfer → activities; authors/reviewers → agents. R2A2-only
epistemic terms (kill condition, evidence grade, identifying assumption,
transfer, protocol/theory failure) stay in the `r2a2:` namespace profile —
never forced into misleading prov: semantics.

### D/G. `r2a2 init-project` + `r2a2 doctor`
Scaffold: theory.py, data/, tests/, r2a2.toml, README, example kill
condition/comparator/identity. `doctor` runs 10+ checks (schema, provenance,
code binding, unbound executables, controls, comparator linkage, transfer
readiness, schema compatibility) and reports BLOCKING / SCIENTIFIC WARNING /
INFORMATIONAL in plain scientific language ("Prediction P claims superiority
over an existing model but declares no comparator…"). The ontology teaches
itself through diagnostics.

### E. Usability session recorder (local-only)
`.r2a2_sessions/`: commands attempted, validation errors, misunderstood
fields, edits before success, doc lookups. No personal data, no upload.
`export_usability_report()` aggregates where the ontology fails to explain
itself.

### F. External-user challenge corpus (5 heterogeneous theories)
`examples/corpus/`: Newtonian two-body, SR dispersion (Lorentz
transformation class), Bayesian epi toy (leakage test), modified-gravity toy
(transfer exposes the refit), logistic map (seeded ensemble + replication).
All compile→run→audit through the unchanged public API. **No core conditionals
for any domain.**

### I. Reference physics: Newtonian two-body
Analytic Kepler comparator; RK4 + symplectic leapfrog as separate-algorithm
implementations; exact E/L conservation identities; intentionally-bad Euler
integrator as hostile control; calibration arc → held-out prediction;
explicit validity domain. Demonstrates R2A2 improving ordinary physics
discipline.

### H. Artifact inspection without Python
`r2a2 inspect artifact.json` and `r2a2 verify <artifact>` — expose/validate
manifest/result/replication/attestation hashes and semantics without
executing anything.

### J. GRUT remains the adversarial client — unchanged, still passing.

## v0.4 acceptance gates — ALL PASS (132 tests)
1. [x] public schema validates all 9 built-in projects (incl. round-trip to identical manifest hashes)
2. [x] RO-Crate export identifies proposal/assumptions/execution/result-manifest linkage/attestations
3. [x] PROV export with correct prov: + r2a2: namespace separation
4. [x] fresh project scaffolded and compiled without touching R2A2 source
5. [x] doctor explains ontology mistakes in domain-neutral language
6. [x] five heterogeneous external-style projects compile without core changes
7. [x] two-body completes compile→freeze→run→audit→replicate→attest→export→verify
8. [x] GRUT adapter passes unchanged
9. [x] documentation contains no GRUT requirement (docs below)
10. [x] no single theory-quality score introduced (compare exposes dimensions only)

## Stop-point report
- Friction discovered while building the corpus: lambdas cannot be referenced
  (by design) — three corpus examples initially used lambdas and had to be
  named. Doctor now catches this with a plain-language message.
- Public concepts that changed: none — the v0.3 object model absorbed five
  new domains unchanged.
- Theories requiring a core special case: **zero**.
- External standards R2A2 exchanges with: RO-Crate 1.3, W3C PROV-JSON,
  JSON Schema 2020-12.
- Remaining R2A2-specific: the epistemic layer — kill conditions, evidence
  grades, hostile controls, identifying assumptions, transfer audits,
  replication grades, attestation sealing.

## Next: v0.5 ecosystem hardening
Signed reviewer identities; plugin security/trust; package signing; stable
extension API; CI integrations; long-term artifact compatibility. HPC is v0.6.
