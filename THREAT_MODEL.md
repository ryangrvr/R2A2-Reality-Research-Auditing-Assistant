# THREAT MODEL — R2A2 (v0.5)

**Founding principle, restated:** R2A2 verifies *discipline, not truth*.
Every protection below is about integrity of *process and identity*, never
about certifying scientific correctness.

## Assets

| Asset | Protected by |
|---|---|
| Theory declaration (assumptions, kill conditions) | content seal, manifest binding |
| Frozen execution manifest | canonical hash, immutability, execution enforcement |
| Results (result records) | content-addressed result_hash, bound to manifest |
| Replication records | content-addressed record_hash binding rule + verdict |
| Review attestations | content seal + optional identity signature |
| Plugin code boundary | capability-granted subprocess isolation (v0.5) |
| Release artifacts | SLSA-shaped provenance + identity signatures |
| Source revision identity | provenance binds artifacts to gitCommit |

## Actors

- **Theory author** — declares the theory; may be wrong (out of scope) or dishonest.
- **Reviewer** — attests to artifact hashes; may be dishonest but correctly signed (below).
- **Plugin author** — supplies theory/backend hooks; potentially malicious.
- **CI system** — executes verification; potentially compromised.
- **Release publisher** — builds/signs distributions; potentially compromised.
- **Attacker (external)** — forges, tampers, replays artifacts.

## Trust boundaries

1. R2A2 process ↔ plugin code (in-process plugins: FULL POWER, stated plainly).
2. R2A2 process ↔ isolated plugin subprocess (OS boundary; capability grants).
3. Author's workstation ↔ repository (signing occurs here).
4. Repository ↔ CI (OIDC identity for keyless signing).
5. CI ↔ release registry (Trusted Publishing; no long-lived tokens).
6. Scientific provenance ↔ software supply-chain provenance (independent axes).

## Attack classes — what R2A2 CAN detect

| Attack | Detection |
|---|---|
| Tampered manifest/result/attestation | content seal breaks; verify-attestation fails |
| Edited `agrees` verdict in a replication record | record_hash binds verdict; verifier recomputes |
| Same-name code swap after freeze | experiment_bindings source-hash check aborts as protocol failure |
| Swapped compute backend after freeze | frozen-backend check aborts |
| Unfrozen manifest executed | refused (protocol failure) |
| Valid signature, untrusted identity | reported IDENTITY NOT TRUSTED BY POLICY — never PASS |
| Tampered signed attestation | signature verification fails |
| Malicious isolated plugin reading undeclared files | capability check refuses; runner errors |
| Release artifact not matching provenance | digest_match false; trusted = false |
| Provenance claims wrong source revision | source_revision is a separate reported facet |

## Attack classes — MITIGATED but not eliminated

| Attack | Mitigation and residual risk |
|---|---|
| Malicious in-process plugin | Explicitly stated: in-process plugins have FULL Python-process power. Only mitigation is the plugin trust policy and review; there is NO in-process sandbox. Use isolated execution for untrusted code. |
| Malicious compute backend | Backend capability metadata is inspected; arbitrary backends still execute arbitrary code. Treat backends as trusted code. |
| Malicious package dependency | Outside R2A2's control; mitigated by lock files, SLSA provenance of the *release*, and standard supply-chain tooling — not by R2A2 itself. |
| Compromised developer workstation | Keys/identities on the workstation are game. Sigstore keyless limits long-lived key theft but the OIDC session is the boundary. |
| Compromised CI workflow | Trust publishing binds identity, not honesty. A compromised workflow with write access can sign as itself. Mitigation: environment protection, minimal scopes. |
| Replay of a stolen attestation file | Content seal binds to manifest/result/revision hashes — replay against different artifacts fails. Replay against the SAME artifacts is undetectable and out of scope. |

## Attack classes — CANNOT be solved by R2A2 (stated explicitly)

| Case | Why |
|---|---|
| Dishonest but correctly signed reviewer | A signature authenticates identity and action, not judgment. A malicious reviewer can sign a false verdict. Mitigation: multiple independent reviewers; policy on identity; nothing more. |
| Scientifically wrong but perfectly reproducible theory | R2A2 verifies discipline, not truth. Kill conditions, hostile controls, and comparators improve the odds of detection, but a wrong theory with clean provenance passes every audit. |
| Collusion among authors and reviewers | Identity binding proves who, not whether they colluded. |
| Fabricated empirical data fed as a trusted dataset | Dataset hashes are recorded; the provenance of the *data itself* (sensor, experiment) is out of scope. |

## Non-goals (v0.5)

- Not a certificate authority, package registry, or sandbox vendor.
- No custom cryptography: Sigstore for identity, SLSA/in-toto for build provenance.
- No promise that Python-level flags constitute isolation.
- No single "secure" score; facets are reported separately.
- No claim that signing validates scientific judgment.

## Summary sentence

R2A2 detects *undisclosed change* and *untrusted identity* in the scientific
pipeline, and leaves *truth* — as always — to science.
