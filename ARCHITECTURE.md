# R2A2 Architecture and Design Document

**Project:** R2A2 — Reality Research Auditing Assistant
**Package/repo name:** `r2a2-science`
**Status:** v0.1 design (pre-implementation baseline)
**Source material:** GRUT `proven/auditor.py`, `provenance/validate.py`,
`PROGRAM/RULES.md`, `PROGRAM/SCOREBOARD.md`, `PROGRAM/CHECKS.md` — used only to
extract general requirements. R2A2 core must contain none of GRUT.

---

## 0. Mission and founding principle

Build a standalone, open-source scientific software project that turns the
theory-testing methodology developed in GRUT into a **general-purpose hypothesis
auditing and execution framework**.

> **R2A2 verifies discipline, not truth.**

This sentence, inherited directly from the GRUT auditor's own docstring, is the
founding principle of the project. It is quoted in the package docstring, it is
printed on every audit report, and every verdict type exists to enforce it. A
wrong-but-well-provenanced theory passes; a correct theory with a hidden
relocation fails the discipline audit.

Long-term north star:

> R2A2 should do for executable scientific theories what pytest does for
> software: provide a neutral framework in which researchers can declare
> hypotheses, assumptions, parameters, invariances, comparators, controls,
> predictions, kill conditions and evidence, then execute and audit them
> reproducibly.

R2A2's differentiator is **executable epistemology**: a claim is a
machine-readable object with a dependency cone, assumptions, a possible
falsifier, an evidence grade, comparators, a test manifest and a transfer
history. The framework answers questions ordinary simulation packages do not:

- "What did this result actually assume?" (dependency cone)
- "Which assumption paid for this apparent prediction?" (cone attribution)
- "Was this quantity predicted or refit?" (transfer/commitment tracking)
- "Would removing this premise kill the result?" (counterfactual pruning)
- "Did the theory survive a truly independent sector?" (cross-sector locks)
- "Does this novel prediction merely restate an input?" (relocation/restatement check)

## 1. The four pillars

```
┌────────────┐  ┌────────────────┐  ┌──────────────────┐  ┌───────────────────────┐
│ Theory SDK │  │ Compute Fabric │  │ Epistemic Ledger │  │ Test Protocol Engine  │
└────────────┘  └────────────────┘  └──────────────────┘  └───────────────────────┘
```

### 1.1 Theory SDK (plugin system)

A small stable protocol (`r2a2.api`) by which an external package registers:

- theory/model identifier and version;
- state representation;
- parameters and their provenance;
- assumptions and commitments;
- observables;
- transformations / invariances / equivalence classes;
- datasets or synthetic data generators;
- experiments / interventions;
- predictions;
- comparators / null models;
- hostile controls;
- kill conditions;
- validity domain;
- optional symbolic derivations and numerical solvers.

Architecture follows the pytest plugin model: well-defined hook functions,
separately installable packages, no domain knowledge in core. A minimal theory
plugin must run with pure Python/NumPy; high-performance dependencies stay
optional. Discovery is by entry point (`r2a2.theories`) or by explicit
registration in the project manifest.

**Boundary rule (the adversarial test):** if implementing a theory requires a
conditional inside R2A2 core, the abstraction has failed. The GRUT adapter is
the standing test of this rule.

### 1.2 Compute fabric

Scientific semantics are separated from numerical execution via a backend
protocol (`r2a.backends.Backend`) exposing capability metadata:

- accelerator availability, precision, autodiff, vectorization;
- distributed execution (future);
- deterministic/reproducible mode;
- checkpoint/resume (future).

v0.1 ships a single reference backend: `LocalNumPyBackend` (pure Python +
optional NumPy). Planned: `JaxBackend`, `TorchBackend`, `SubprocessBackend`
(external executable adapters), then distributed runners.

Rule: the engine (and therefore audit semantics) must never depend on which
backend ran. Every execution record names its backend and version, and results
from different backends are comparable only through declared tolerance.

### 1.3 Epistemic ledger

Generalizes GRUT's `auditor.py`. **The canonical ledger is a dependency graph,
not a scalar sum.** The original auditor's net ledger was explicitly a blind
sum that could not detect double counting; that limitation is unacceptable in
the general product, so the graph is the primitive and any scalar "logical
debt" is a derived, labelled summary.

Every claim node carries:

- inputs, assumptions, imported data/constants;
- fitted quantities vs. derived quantities (distinct types);
- sources, code/artifact hashes, tests, hostile controls;
- comparator models, identifying assumptions;
- validity domain, evidence grade;
- falsification/overturning condition;
- current status.

The ledger distinguishes at least these debt kinds (each a graph edge/attribute
family, never merged into one number without labels):

`commitment`, `imported-constant`, `fitted-parameter`, `external-prior`,
`numerical-approximation`, `unproved-lemma`, `waived-gate`,
`comparator-assumption`, `identifying-assumption`, `sector-input`.

The ledger detects/flags:

- unsupported claims;
- circular dependencies;
- double-counted assumptions (one input feeding two claims as if independent);
- derived claims that introduce new inputs (anti-laundering, generalized from
  the GRUT `laundering_ok` rule);
- parameters silently refit across sectors (see §3);
- claims whose stated validity exceeds their evidence domain;
- missing kill conditions;
- missing provenance;
- evidence-grade inflation (claiming theorem grade for a numerical result).

The GRUT principle **commitment is legal when explicit; hidden relocation is
not** is enforced here: a postulate may be carried if it is priced and declared;
a result whose answer is encoded in its inputs must be labelled RELOCATED.

### 1.4 Test protocol engine

The central differentiator. Native concepts:

- preregistration / frozen test plans;
- blind and candidate-blind holdouts;
- hostile controls;
- exact identities / conservation-law checks;
- comparator audits;
- nuisance/interface classes;
- identifying assumptions;
- kill / bank / extend outcomes;
- theorem vs. formal vs. numerical vs. evidence grades;
- independent reimplementation;
- external review/check status;
- cross-sector parameter transfer.

A theory test compiles into an **immutable execution manifest** before results
are opened. The manifest hashes: model version, source revision, assumptions,
parameter sources, datasets, test definitions, thresholds, random seeds,
numerical backend, environment information. Results attach to the graph; they
never rewrite the preregistered structure. A failed stage terminates and is
recorded — it does not automatically spawn a "missing ingredient" campaign
(RULES rule 4, short ladders).

## 2. Theory compiler and CLI

Workflow:

```
r2a2 init                 # scaffold a project
r2a2 validate theory.yaml # structural validation of the manifest
r2a2 compile theory.yaml  # manifest -> directed test/dependency graph
r2a2 run <experiment>     # execute via configured backend
r2a2 audit                # ledger/discipline audit of the whole graph
r2a2 compare A B          # comparator audit between two theories
r2a2 transfer A B         # cross-sector parameter transfer, with pricing
r2a2 report               # human report generated from machine-readable output
```

The compiler converts a declarative theory/project manifest into a directed
test/dependency graph (DAG, cycles rejected). A compiled node may represent a
commitment, derivation, simulation, test, control, comparator, prediction or
external evidence item. Execution results attach to nodes as new evidence
records; they do not alter graph structure.

## 3. Cross-sector transfer

A first-class operation, and a signature capability:

1. parameter θ determined/calibrated in sector A;
2. θ frozen (commitment recorded, hash-bound);
3. sector B prediction executed **without refitting**;
4. any new B-specific parameter explicitly surfaced and priced.

The engine flags a purported cross-sector prediction when parameters have been
silently retuned — this is the "parameter transfer" discipline from GRUT,
generalized. `r2a2 transfer` produces a transfer record: which parameters
moved, which were refrozen, which were re-fit, and the debt incurred by each.

## 4. Evidence and verdicts

Never a single PASS/FAIL. At minimum:

`structural-validation`, `computational-reproduction`, `numerical-evidence`,
`formal-result`, `proved-theorem`, `empirical-confirmation`,
`conditional-result`, `null-result`, `killed-hypothesis`,
`unresolved-identification`.

Plus per-test outcomes: KILL / BANK / EXTEND. A successful run means the test
protocol executed correctly, not that the theory is true.

## 5. Provenance

Every result is reproducible from: repository SHA, manifest hash, environment
lock, backend/version, input hashes, machine-readable output. Human-facing
tables and reports are generated from machine-readable results, never hand
transcribed. The GRUT external-check concept generalizes into **review
attestations** bound (by hash) to the artifact being reviewed: a reviewer signs
a claim-hash, not a prose document.

## 6. Architecture boundary

R2A2 core knows nothing about GRUT, Hilbert spaces, relativity, cosmology,
particle physics, or any specific physical theory. Core knows only: models,
claims, dependencies, transformations, parameters, experiments, tests, evidence,
provenance, execution.

## 7. Reference plugins

Three deliberately different examples ship in `examples/`:

1. **toy** (`examples/toy_theory`) — tiny analytic model, pure Python, unit-test
   grade; shows the minimal plugin.
2. **pendulum** (`examples/pendulum_theory`) — a conventional physics example
   with known correct behaviour, exact conservation-law control, a comparator
   (small-angle approximation) and hostile controls.
3. **GRUT adapter** (`examples/grut_adapter`) — imports a small subset of the
   existing ledger/test machinery as a *client*, without modifying R2A2 core.
   This is the adversarial test of the abstraction.

## 8. Package layout

```
r2a2-science/
  pyproject.toml
  README.md
  ARCHITECTURE.md
  src/r2a2/
    __init__.py          # package docstring carries the founding principle
    api.py               # Theory SDK: plugin protocol + registry
    ledger.py            # epistemic ledger: dependency graph, debt kinds
    audit.py             # audit rules (generalized auditor)
    manifest.py          # execution manifests, hashing, freezing
    compiler.py          # manifest -> test/dependency graph
    backends/
      __init__.py        # Backend protocol
      local.py           # LocalNumPyBackend
    runner.py            # deterministic local runner
    verdicts.py          # verdict / evidence-grade vocabulary
    cli.py               # r2a2 command line
    report.py            # machine -> human report rendering
  examples/
    toy_theory/
    pendulum_theory/
    grut_adapter/        # client only; requires GRUT sources at a path
  tests/
```

## 9. Development sequence (v0.1)

1. schemas → 2. plugin protocol → 3. dependency DAG → 4. manifest/compiler →
5. audit rules → 6. deterministic local runner → 7. CLI → 8. tests.

Then reproduce the existing generalized GRUT `auditor.py` behaviour on top of
R2A2. Only after the semantic core is stable: JAX backend, PyTorch backend,
parallel execution, GPU/distributed execution. Governance/audit semantics must
never depend on the numerical backend.

**Definition of done (v0.1):** an unrelated toy theory and a GR theory
fragment can both be expressed through the same public SDK, compiled into test
graphs, executed through the local backend, audited for logical/provenance
debt, and reported without any theory-specific code in R2A2 core. Then stop and
report before any HPC work.

## 10. Non-goals

- redesigning GRUT or moving GRUT 2 development into this repository;
- claiming to certify truth;
- building an autonomous AI physicist;
- adding arbitrary LLM judgment to scientific verdicts;
- hard-coding a physics ontology;
- optimizing for GPU performance before the API is stable;
- collapsing epistemic status into one score.

## 11. Naming

Project title: **R2A2 — Reality Research Auditing Assistant**. The string
"R2A2" collides with unrelated projects (e.g. "Responsible Reasoning AI
Agents", an FPGA accelerator), so the Python package and repository use
`r2a2-science` and import as `r2a2`.
