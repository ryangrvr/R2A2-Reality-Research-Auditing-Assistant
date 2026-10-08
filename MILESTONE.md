# R2A2 v0.6 — Compute Fabric / HPC (in progress)

## Entering state (banked)

- v0.1–v0.3: semantic, audit, reproducibility and scientific-trust core — BANKED
- v0.4: external adoption and interoperability — BANKED
- v0.5: ecosystem identity, plugin trust, supply-chain security — BANKED at
  `f8c7972` (sigstore-compat 4.0.0 PASS ∧ 4.5.0 PASS; verify PASS);
  bank record `58b8768`.

External ruling: "f8c7972 — checked: ChatGPT — PASS. No open issue within the
v0.5 ecosystem-trust/security scope." Security review stops here.

## v0.6 organizing question

Can the same frozen scientific declaration execute across laptop CPU,
numerical libraries, accelerators, external programs and distributed workers
without silently changing the science?

Core invariant: **scientific semantics ⊥ compute substrate**.

Key principle: **R2A2 audits numerical equivalence, not numerical identity** —
three explicit classes: EXACT, NUMERICAL (|x_A−x_B| ≤ a + r·|x_ref| with
frozen tolerances), STATISTICAL (frozen comparison rule).

## v0.6 progress — Compute Fabric / HOC (working log)

### Implemented

**A/C. Compute protocol** (`r2a2/compute.py`): BackendDescriptor,
ComputeRequest, ComputeResult, ExecutionContext, ResourceRequest, ComputeProfile,
ComputeBackend abstract protocol (probe/capabilities/prepare/execute/
fingerprint + optional checkpoint/resume). No JAX/Torch/CUDA/MPI/Slurm
concepts in the theory model.

**B. Capability negotiation**: ResourceRequest declares requirements;
negotiate() selects a fully-satisfying backend; missing capability = PROTOCOL
FAILURE before scientific execution ("R2A2 never silently degrades a
scientific requirement"). Tested: GPU-required-no-GPU, float64-required vs
float32-realized, deterministic-required, unknown backend.

**C. Compute profile**: precision policy, seed policy, determinism,
backend family, device class, distributed topology, tolerance policy,
checkpoint policy, resources, reproducibility rule — material_hash() binds
scientifically material fields only. Tested: precision change changes hash;
determinism change changes hash; wall time / incidental metadata does NOT.

**D. NumPy backend** (`r2a2/compute_backends.py`): CPU reference via the new
protocol; capability reporting distinguishes design capability from optional
dependency presence (honest "stdlib-fallback" warning when numpy absent).

**E/F. JAX + Torch backends**: optional; pass when installed, raise
ExecutionError honestly when absent; report devices/platform/precision/
determinism LIMITATIONS (JAX float32-on-accelerator note, torch
use_deterministic_algorithms note). Zero theory-core conditionals (leakage
test asserts the theory model source is free of jax/torch/cuda/mpi/slurm).

**G. External executable backend**: content-bound executable identity (hash,
not filename — renaming keeps identity, editing changes it), frozen workdir,
input/output hashes, exit status, stdout/stderr hashes, declared extraction
(undeclared extraction = protocol error; stdout text never auto-becomes a
result). Tested: content binding, rename invariance, edit sensitivity,
missing binary.

**H. Reproducibility classes**: EXACT / NUMERICAL (frozen atol+rtol) /
STATISTICAL (mean-z, KS). Rule hash binds tolerances; hostile test proves a
loosened tolerance is a different rule with a different hash — visible, never
silent.

**I. Cross-backend reproduction** (`r2a2/reproduce.py`): same frozen manifest
→ multiple backends → frozen rule; comparison artifact with fingerprints,
payload hashes, rule hash, verdict; requires a frozen rule (protocol error
otherwise); disagreement reported as a scientific finding, never hidden.

**J/K/L/M. Work units + RNG**: WorkUnit bound to manifest with identity-
derived seeds (manifest|experiment|work-unit ⊗ replicate — orthogonal
dimensions); map_work with retry-as-provenance (attempts recorded, payload
hash unchanged); reduce_results with deterministic order option; tested:
scheduling-order invariance, 100 distinct streams, retry transparency.

**N. Checkpointing**: sealed checkpoints (content hash), version-checked;
resume validates manifest/experiment/work-unit/material config/backend —
mismatch = PROTOCOL failure. Tested: roundtrip, resume==uninterrupted,
wrong manifest/experiment/seed, edited checkpoint.

**O/Q. Retry + artifacts**: retries recorded as provenance; external outputs
hashed; wall time excluded from payload hash (tested).

**T/U. Failure taxonomy + CLI**: compute probe/backends/doctor, run-backend
(negotiation → execution), reproduce, checkpoint inspect — existing failure
kinds preserved.

**S. Stochastic ensemble test**: 1 worker vs reordered scheduling vs
checkpoint/resume produce identical results (identity-derived seeds);
statistical rule agrees.

### Remaining for full v0.6 gate closure
- R: two-body cross-backend run on JAX/Torch when installed (needs deps in CI)
- Live-OIDC-style explicit skips for missing accelerator deps (done)
- Final report

---

# R2A2 v0.5.4 — Sigstore compat execution closure (v0.5 BANKED)

## External review of v0.5.3 (commit caad157)

**Verdict: `caad157` — checked: ChatGPT — ISSUE FOUND.** Decisive evidence
from the remote: the sigstore-compat workflow for caad157 FAILED — both
matrix jobs died with "No module named pytest" before running any test, and
the committed `_sigstore_transport()` still contained the old base64/raw-bytes
path. So 4.x signing→bundle→verification compatibility was claimed but not
demonstrated.

**Lesson recorded:** a locally-skipped test is not a demonstration; only the
remote CI run counts.

## Fixes

1. `_sigstore_transport()` requires `signature_format ==
   "sigstore-bundle-json"`; reconstructs the real `verify.Bundle` via
   `Bundle.from_json(...)`; legacy base64 raises `SigstoreVerificationError`.
   Missing issuer fails closed BEFORE parsing.
2. `_sigstore_verify()` calls the actual 4.x method
   `verifier.verify_artifact(input_, bundle, policy)` — the same method the
   compat tests exercise against real Bundle/Verifier classes.
3. CI installs `pip install -e ".[dev]"` before the pinned sigstore,
   fail-fast disabled so both versions report independently.
4. Compat test corrections driven by real CI failures: `ClientTrustConfig`
   lives in `sigstore.models`; the OIDC token is passed directly to the
   signer; real signing requires live Fulcio (explicitly marked);
   identity/issuer binding asserted via the real `Identity._identity` and
   `OIDCIssuer._value`.

## Remote verification — the stop condition

**4.0.0 CI PASS ∧ 4.5.0 CI PASS** — both matrix jobs `success`, verified from
the remote. `verify` workflow also green. 171 tests pass locally.

**v0.5 — ecosystem trust & supply-chain security: BANKED.** Security auditing
ends at this level. Next: v0.6 Compute Fabric / HPC.

---

# R2A2 v0.5 — ecosystem trust & supply-chain security

Entering state: v0.1–0.3 (semantic/audit/trust core) BANKED; v0.4 (adoption &
interoperability) BANKED at `e9b3dab` — checked: ChatGPT, no open issue within
the interoperability scope. RO-Crate/PROV/JSON Schema not reopened.

## v0.5 question

Can R2A2 safely accept plugins, reviewers, CI systems and release artifacts
from different people and organizations while preserving verifiable identity,
provenance and trust boundaries?

## What v0.5 added

### 1-2. Signed reviewer attestations + identity policy (`r2a2/signing.py`)
`content seal != identity signature` — the R2A2 content seal (v0.3) and the
identity signature are verified INDEPENDENTLY; both must pass for `trusted`.
Primary backend: **Sigstore keyless** (OIDC identity + transparency log) via
the `sigstore` client — and it never silently downgrades: if the backend is
unavailable, signing raises rather than pretending. An explicit offline HMAC
mode exists for development and is ALWAYS reported as
`UNAUTHENTICATED (offline dev mode)`.
`IdentityPolicy` expresses exact identities, approved domains, OIDC issuers,
CI workflow patterns, and an explicit `allow_unsigned` flag. Verification
verdicts are explicit: CONTENT VALID / IDENTITY VERIFIED / IDENTITY NOT
TRUSTED BY POLICY / UNSIGNED / SIGNATURE INVALID / UNAUTHENTICATED.
A valid signature from a disallowed identity is never silently trusted.
CLI: `r2a2 sign-attestation`, `r2a2 verify-signed-attestation`.

### 3-4. Plugin trust model (`r2a2/plugins.py`, `r2a2 plugins *`)
Two explicit execution classes: `trusted-in-process` (FULL process power,
stated plainly) and `untrusted-isolated` (REAL OS subprocess with
machine-readable stdio and capability grants). Capabilities that cannot be
isolated in v0.5 (network, accelerator, nested subprocess) are REFUSED
outright — "unsupported isolation beats fake isolation". Path-typed arguments
must be covered by declared grants (declared capability × runtime grant).
`PluginPolicy` never silently upgrades: unsigned plugins are trusted only if
explicitly listed; `trusted-in-process` requires explicit listing.
CLI: `r2a2 plugins list/inspect/verify`.

### 5. Stable extension API (`r2a2/api_contract.py`)
`r2a2_extension_api: 1`, independent from the artifact schema. Supported
import surface: r2a2.api, r2a2.backends, r2a2.signing, r2a2.plugins. Private
modules are checkable violations; contract tests are runnable by plugin
authors independently.

### 6. CI-native verification (`r2a2 ci verify`)
Non-interactive with meaningful exit codes: 0 OK, 2 EXECUTION, 3 PROTOCOL,
4 THEORY (a scientific result, not a crash), 5 TRUST. Pipeline: doctor →
compile → freeze → enforced run → audit → attestation verification.
GitHub Actions example included; CLI stays provider-neutral.

### 7-8. Build provenance + release signing (`r2a2/supply_chain.py`)
SLSA v1.2-shaped build provenance binding source repo, exact revision,
builder identity, invocation, and artifact digests. `verify_release` reports
SEPARATE facets (digest match, signature validity, signing identity,
provenance presence, source revision, builder identity, policy result) —
never a single "secure" score.

### 9. Hardened publishing path (`.github/workflows/release.yml`)
PyPI Trusted Publishing preparation: OIDC `id-token: write`, protected
`release` environment, NO long-lived upload token, Sigstore artifact signing.
No release is actually published in v0.5.

### 10-11. Threat model + separation tests
`THREAT_MODEL.md` states assets, actors, trust boundaries, what R2A2 detects,
what it mitigates, and what it cannot solve (dishonest-but-signed reviewer,
wrong-but-reproducible theory, collusion, fabricated data). Hostile tests
prove the two provenance axes are independent: scientifically valid artifacts
from an untrusted build (scientific OK, software FAIL) and a signed official
build running a falsified prediction (software PASS, theory KILL).

### 12. Signed end-to-end pipeline
two-body: theory → frozen manifest → enforced execution → result →
replication → attestation → identity signature → RO-Crate export → build
provenance → independent verification.

## v0.5 acceptance gates — status

1. [x] attestation signed by identity-backed signer + independently verified
2. [x] editing any attested field (verdict/scope/hashes/notes/schema) breaks it
3. [x] valid signature + disallowed identity => NOT TRUSTED, not PASS
4. [x] trusted/untrusted plugin modes explicit; never silently upgraded
5. [x] isolated plugin demonstrably executes outside the R2A2 process
6. [x] capabilities declared and inspectable before execution
7. [x] extension API contract tests pass (two external-style plugin modules)
8. [x] `r2a2 ci verify` non-interactive with failure-kind exit codes
9. [x] release artifacts carry SLSA-shaped provenance bound to source revision
10. [x] release signing verifies against an explicit identity policy
11. [x] publishing workflow uses Trusted Publishing, no long-lived token
12. [x] THREAT_MODEL.md accurate about protections and non-protections
13. [x] hostile tests prove the two axes are independent
14. [x] corpus + GRUT adapter still pass with zero core special cases

163 passed + 1 skip.

## Stop-point report

- **Identities supported**: exact identities, email domains, OIDC issuers
  (Sigstore keyless), CI workflow patterns, explicit offline dev mode.
- **Standards used**: Sigstore (keyless OIDC signing + transparency log),
  SLSA v1.2-shaped build provenance, in-toto-style attestation envelopes.
- **Isolation actually enforced**: OS subprocess boundary with machine-
  readable protocol, declared capability grants, refused unisolatable
  capabilities. NOT a Python-level sandbox; in-process plugins have full
  power by explicit design.
- **Out of scope (stated)**: intercepting opens inside plugin code without
  an OS sandbox; dishonest-but-signed reviewers; compromised workstations/
  CI; dependency malware; fabricated upstream data; scientific truth.
- **SDK concepts changed**: none — the trust layer extends existing objects.
- **GRUT accommodations in core**: zero.

## Next: v0.6 — Compute Fabric / HPC
NumPy/SciPy, JAX, PyTorch, external executables, accelerator capability
negotiation, distributed execution, checkpointing, cross-backend
reproducibility.

---

# Earlier milestones preserved in git history (v0.1-v0.4.2)
