# R2A2 v0.3 milestone: reproducibility and trust

v0.3 question: **can I trust that another person independently reproduced and
reviewed this exact scientific result?**

## What v0.3 added

### 1. Independent implementation protocol (`r2a2.trust`, `r2a2 replicate`)

A/B replication is a first-class object with a frozen agreement rule
(`|x_A - x_B| < tau` or structural equality of machine-readable output) and
an explicit **independence level**, because "two implementations agree" is
evidence only at a stated strength:

- `L1-same-algorithm-separate-code` — catches coding errors
- `L2-separate-algorithm-same-equations` — catches method errors
- `L3-independent-derivation-and-implementation` — catches conception errors

### 2. Hash-bound review attestations (`r2a2 attest`, `r2a2 verify-attestation`)

An attestation binds reviewer + scope + manifest hash + result hash + code
revision, is content-sealed, and **applies only to the exact artifacts** it
covered. Change anything and verification returns `applies: false`. Post-hoc
tampering with the verdict is detected against the stored seal. This replaces
"reviewed by X" in markdown (the generalized CHECKS.md gate).

### 3. Epistemic compare (`r2a2 compare`)

Side-by-side dimensions — free parameters, commitments, identifying
assumptions, imported constants, unproved lemmas, hostile controls, identity
checks, sectors, validity domain. **No winner score**; R2A2 exposes, the
researcher judges.

### 4. YAML/JSON as transport, never truth (`r2a2/transport.py`)

Pipeline: YAML input → validated canonical internal model → canonical hash.
We never hash the YAML text (anchors/aliases/implicit typing/parser
differences). Declarative round-trip is hash-stable; experiments are code and
transport by reference. PyYAML optional; JSON always available.

### 5. Schema versioning (`r2a2/schema.py`, `r2a2 schema`)

Every manifest, replication record and attestation carries
`r2a2_schema: 0.3`, with explicit migration rules, so artifact semantics stay
interpretable across future code versions.

## State

81 tests pass. Chain now routine: assumption → test → execution → result →
independent replication → external attestation → verdict.

## Next (v0.4 per the ladder)

**External-user validation**: hand the SDK to a scientist who has never seen
GRUT; measure where the ontology is not self-explanatory. Then v0.5 ecosystem
hardening, v0.6 HPC backends.

---

# v0.2 milestone: adversarial generalization (recap)

v0.2 goal: **attack the abstraction**. No GPUs, no dashboard — try to break
what exists with unrelated theories and new first-class machinery.

## What v0.2 added

### 1. Three alien theories through the unchanged SDK

- `examples/alien_theories/bayesian_decay.py` — probabilistic/Bayesian theory:
  inferred parameter with prior, posterior prediction, null comparator.
- `examples/alien_theories/ising_toy.py` — statistical-mechanics/lattice theory:
  exact-enumeration ensemble, fixed-by-symmetry + fitted parameters,
  phase-domain claim, exact partition-function identity, mean-field hostile control.
- `examples/alien_theories/gauge_toy.py` — gauge-equivalence theory:
  `TransformationClass` is a native API object; gauge-dependent observables
  are distinguished from invariants by the quotient machinery itself.

If any of these had required an `if theory == ...` in core, the abstraction
would have failed. It did not.

### 2. `TransformationClass` and `Comparator` as SDK objects

`r2a2.api.TransformationClass` carries membership, composition,
canonicalization, invariants, quotient distance and optimisation hooks.
R2A2 core knows only the question: *does the candidate remain distinguishable
after quotienting the declared nuisance/interface freedom?*

### 3. `transfer` — the signature feature

`r2a2 transfer <calibration> <target>` audits the full provenance chain and
prints per-parameter verdicts:

```
TRANSFER AUDIT
  sector: A -> B
  theta_1    FROZEN            inherited from sector:A
  theta_2    FROZEN            inherited from sector:A
  phi_1      NEW INPUT         introduced in B
Cross-sector status: FAIL
Reason: phi_1 is NEW IN SECTOR 'B' -> the cross-sector claim requires one unpriced sector-specific parameter
```

Silent refits FAIL; declared refits pass but are priced; calibration/target
data overlap fails out-of-sample status.

### 4. Canonical manifest hashing, specified and fuzz-tested

`r2a2.canonical` is the single definition: key-order/whitespace invariant,
tuple≡list, path-normalized; sensitive to thresholds, assumption text,
dataset ids, parameter sources, backend. Property + randomized key-shuffle
fuzz tests in `tests/test_canonical.py`.

### 5. Three failure kinds, never conflated

`r2a2.failures`: `execution-failure` (the code threw), `protocol-failure`
(the preregistration/provenance process broke), `theory-failure` (nature
rejected a preregistered prediction — a *result*, not a crash).

### 6. Ledger queries as CLI

`r2a2 why <theory> <node>` (dependency cone as a tree),
`r2a2 impact <theory> <node>` (what collapses if removed),
`r2a2 inputs <theory> <node>` (labelled leaves + out-of-sample overlap warning).

### 7. Naming / vocabulary

`LocalNumPyBackend` → `LocalBackend` (execution policy separated from
numerical library; `"local-numpy"` remains an alias). Public messages use
neutral language: *provenance violation*, *undeclared refit*,
*dependency disclosure* — same rigor, professional vocabulary.

## v0.1 checks (still green)

Toy theory and GRUT adapter compile/run/audit through the public SDK with zero
theory-specific code in core; 67 tests pass.

## Next (v0.3 per the maturity ladder)

Independent implementations A/B with declared agreement requirements;
review attestations bound to artifact hashes; `r2a2 compare`; YAML project
manifests; `refits`/`unresolved` query surfaces.
