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
