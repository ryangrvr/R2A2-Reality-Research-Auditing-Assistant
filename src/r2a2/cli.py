"""The ``r2a2`` command line.

    r2a2 init <dir>
    r2a2 validate <theory.yaml>
    r2a2 compile <theory.yaml>
    r2a2 run <theory-module>
    r2a2 audit <theory-module>
    r2a2 report <theory-module>
    r2a2 theories
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import sys

from . import __version__
from .audit import audit_theory
from .compiler import compile_theory
from .ledger import Ledger
from .report import render_audit
from .runner import run_manifest


def _load_theory(spec: str):
    """Import ``module:attr`` or ``module`` and return a Theory."""
    mod_name, _, attr = spec.partition(":")
    mod = importlib.import_module(mod_name)
    obj = getattr(mod, attr) if attr else getattr(mod, "THEORY", None)
    if obj is None:
        # fall back to first Theory in module
        from .api import Theory
        candidates = [v for v in vars(mod).values() if isinstance(v, Theory)]
        if not candidates:
            raise SystemExit(f"{spec}: no Theory found in module {mod_name!r}")
        obj = candidates[0]
    return obj


def cmd_init(args) -> int:
    os.makedirs(args.dir, exist_ok=True)
    template = '''"""A minimal R2A2 theory plugin (pure Python)."""
from r2a2.api import Theory, Parameter, Assumption, Prediction, Test

THEORY = Theory(
    id="my-theory",
    version="0.0.1",
    description="Edit me.",
    parameters=[Parameter("theta", kind="commitment", value=1.0)],
    assumptions=[Assumption("A1", "state the assumption", kind="assumption", priced=True)],
    predictions=[Prediction(
        "P1", "what it predicts", experiment="main", observable="x",
        kill_condition="state what would kill this", assumptions=["A1"],
        parameters=["theta"], evidence_grade="numerical",
    )],
    tests=[Test("T1", kind="identity", experiment="identity", exact=True)],
    experiments={
        "main": lambda **kw: {"x": 0.0},
        "identity": lambda **kw: {"exact_control": 0.0},
    },
)
'''
    with open(os.path.join(args.dir, "my_theory.py"), "w") as f:
        f.write(template)
    print(f"scaffolded {args.dir}/my_theory.py — edit it, then: r2a2 audit my_theory")
    return 0


def cmd_compile(args) -> int:
    theory = _load_theory(args.theory)
    manifest, ledger = compile_theory(theory)
    h = manifest.freeze()
    if args.output:
        with open(args.output, "w") as f:
            json.dump({"manifest": manifest.to_dict(), "ledger": ledger.to_dict()}, f, indent=2)
    print(f"compiled {theory.id} v{theory.version}")
    print(f"manifest hash: {h}")
    print(f"graph nodes: {len(ledger.nodes)}")
    return 0


def cmd_audit(args) -> int:
    theory = _load_theory(args.theory)
    manifest, ledger = compile_theory(theory)
    manifest.freeze()
    report = audit_theory(theory, ledger)
    print(render_audit(theory.id, report, ledger))
    return 0 if report.ok else 1


def cmd_run(args) -> int:
    theory = _load_theory(args.theory)
    manifest, ledger = compile_theory(theory, seeds={"default": args.seed})
    manifest.freeze()
    res = run_manifest(theory, manifest, ledger)
    print(f"run of {theory.id} under manifest {res.manifest_hash[:12]}…")
    for rec in res.records:
        print(f"  [{rec['backend']}] {rec['experiment']}: "
              f"{json.dumps(rec['result'], default=str)[:100]}")
    print(f"{len(res.records)} experiment(s) executed; results attached to the graph.")
    return 0


def _load_theory_and_ledger(spec):
    theory = _load_theory(spec)
    manifest, ledger = compile_theory(theory)
    manifest.freeze()
    return theory, ledger


def cmd_transfer(args) -> int:
    """r2a2 transfer <calibration-theory> <target-theory>

    The target theory declares which parameters it requires and which it
    introduced itself (Parameter sector/kind). The engine verifies provenance.
    """
    cal, _ = _load_theory_and_ledger(args.calibration)
    target, _ = _load_theory_and_ledger(args.target)
    from .transfer import FrozenParameter, SectorDemand, audit_transfer
    frozen = {
        p.name: FrozenParameter(name=p.name, sector=p.sector, value=p.value,
                                source=p.source or "")
        for p in cal.parameters
    }
    required = [p.name for p in target.parameters]
    introduced = [p.name for p in target.parameters if p.sector != "default"
                  and p.kind in ("sector-input", "fitted-parameter")]
    demand = SectorDemand(sector=target.id, required=required, introduced=introduced)
    v = audit_transfer(frozen, demand)
    print(v.render(cal.id, target.id))
    return 0 if v.outcome == "PASS" else 1


def cmd_why(args) -> int:
    _, ledger = _load_theory_and_ledger(args.theory)
    from .queries import why
    print(why(ledger, args.node))
    return 0


def cmd_impact(args) -> int:
    _, ledger = _load_theory_and_ledger(args.theory)
    from .queries import impact
    deps = impact(ledger, args.node)
    print(f"claims that collapse if {args.node} is removed:")
    for d in deps:
        print(f"  {d}")
    return 0


def cmd_inputs(args) -> int:
    _, ledger = _load_theory_and_ledger(args.theory)
    from .queries import inputs, out_of_sample_warning
    leaves = inputs(ledger, args.node)
    print(f"inputs of {args.node}:")
    for kind, ids in sorted(leaves.items()):
        for i in ids:
            print(f"  [{kind}] {i}")
    for w in out_of_sample_warning(ledger, args.node):
        print(w)
    return 0


def cmd_compare(args) -> int:
    from .compare import compare
    print(compare(_load_theory(args.theory_a), _load_theory(args.theory_b)))
    return 0


def cmd_replicate(args) -> int:
    """Evaluate an A/B replication record from a JSON spec file."""
    from .trust import (AgreementRule, Implementation, Replication)
    with open(args.spec) as f:
        spec = json.load(f)
    rep = Replication(
        test_id=spec["test_id"],
        impl_a=Implementation(**spec["impl_a"]),
        impl_b=Implementation(**spec["impl_b"]),
        rule=AgreementRule(kind=spec["rule"].get("kind", "tolerance"),
                           tolerance=spec["rule"].get("tolerance"),
                           observable=spec["rule"].get("observable", "")),
        value_a=spec["value_a"], value_b=spec["value_b"],
        manifest_hash=spec.get("manifest_hash", ""),
    )
    rec = rep.evaluate()
    print(json.dumps(rec, indent=2))
    return 0 if rec["agrees"] else 1


def cmd_attest(args) -> int:
    """Record a review attestation bound to artifact hashes."""
    from .trust import ReviewAttestation
    att = ReviewAttestation(
        reviewer=args.reviewer, scope=args.scope,
        manifest_hash=args.manifest_hash, result_hash=args.result_hash,
        code_revision=args.revision, verdict=args.verdict,
        notes=args.notes or "")
    with open(args.output, "w") as f:
        json.dump(att.to_dict(), f, indent=2)
    print(f"attestation sealed: {att.seal()[:16]}…  written to {args.output}")
    return 0


def cmd_verify_attestation(args) -> int:
    from .trust import ReviewAttestation, verify_attestation
    with open(args.attestation) as f:
        doc = json.load(f)
    if "seal" not in doc:
        print("X attestation file has no seal; it cannot be verified")
        return 1
    att = ReviewAttestation(
        reviewer=doc["reviewer"], scope=doc["scope"],
        manifest_hash=doc["manifest_hash"], result_hash=doc["result_hash"],
        code_revision=doc["code_revision"], verdict=doc["verdict"],
        notes=doc.get("notes", ""), issues=doc.get("issues", []))
    # ALWAYS verify the current content against the STORED seal: any edit to
    # verdict, notes or issue state after sealing is detected here.
    res = verify_attestation(att, args.manifest_hash, args.result_hash,
                             args.revision, sealed_as=doc["seal"])
    print(json.dumps(res, indent=2))
    return 0 if res["applies"] else 1


def cmd_schema(args) -> int:
    from .schema import SCHEMA_VERSION
    print(f"r2a2_schema: {SCHEMA_VERSION}")
    return 0


def cmd_import_theory(args) -> int:
    """Load a theory from YAML/JSON transport and validate it."""
    from .transport import theory_from_dict, theory_from_yaml
    with open(args.file) as f:
        text = f.read()
    theory = (theory_from_yaml(text) if args.file.endswith(('.yaml', '.yml'))
              else theory_from_dict(json.loads(text)))
    problems = theory.validate()
    if problems:
        for p in problems:
            print(f"X {p}")
        return 1
    print(f"theory {theory.id} v{theory.version}: transport-validated")
    return 0


def cmd_theories(args) -> int:
    from .api import registry
    registry.load_entrypoints()
    for tid in registry.ids():
        t = registry.get(tid)
        print(f"{tid} v{t.version} — {t.description}")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="r2a2", description=__doc__)
    p.add_argument("--version", action="version", version=f"r2a2 {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init", help="scaffold a theory project")
    s.add_argument("dir")
    s.set_defaults(fn=cmd_init)

    s = sub.add_parser("compile", help="compile a theory into manifest + graph")
    s.add_argument("theory", help="module:attr or module path")
    s.add_argument("-o", "--output", help="write machine-readable JSON here")
    s.set_defaults(fn=cmd_compile)

    s = sub.add_parser("audit", help="audit a theory's ledger (discipline, not truth)")
    s.add_argument("theory")
    s.set_defaults(fn=cmd_audit)

    s = sub.add_parser("run", help="execute the theory's experiments via the local backend")
    s.add_argument("theory")
    s.add_argument("--seed", type=int, default=0)
    s.set_defaults(fn=cmd_run)

    s = sub.add_parser("theories", help="list registered theory plugins")
    s.set_defaults(fn=cmd_theories)

    s = sub.add_parser("transfer", help="cross-sector parameter transfer audit")
    s.add_argument("calibration", help="theory module that fixed the parameters")
    s.add_argument("target", help="theory/sector claiming the transferred prediction")
    s.set_defaults(fn=cmd_transfer)

    s = sub.add_parser("why", help="print the dependency cone of a node")
    s.add_argument("theory")
    s.add_argument("node")
    s.set_defaults(fn=cmd_why)

    s = sub.add_parser("impact", help="which claims collapse if a node is removed")
    s.add_argument("theory")
    s.add_argument("node")
    s.set_defaults(fn=cmd_impact)

    s = sub.add_parser("inputs", help="list the inputs a claim rests on")
    s.add_argument("theory")
    s.add_argument("node")
    s.set_defaults(fn=cmd_inputs)

    s = sub.add_parser("compare", help="side-by-side epistemic dimensions (no winner score)")
    s.add_argument("theory_a")
    s.add_argument("theory_b")
    s.set_defaults(fn=cmd_compare)

    s = sub.add_parser("replicate", help="evaluate an A/B replication record (JSON spec)")
    s.add_argument("spec")
    s.set_defaults(fn=cmd_replicate)

    s = sub.add_parser("attest", help="record a review attestation bound to artifact hashes")
    s.add_argument("--reviewer", required=True)
    s.add_argument("--scope", required=True)
    s.add_argument("--manifest-hash", required=True)
    s.add_argument("--result-hash", required=True)
    s.add_argument("--revision", required=True)
    s.add_argument("--verdict", required=True)
    s.add_argument("--notes", default="")
    s.add_argument("-o", "--output", default="attestation.json")
    s.set_defaults(fn=cmd_attest)

    s = sub.add_parser("verify-attestation",
                       help="check an attestation still applies to given artifacts")
    s.add_argument("attestation")
    s.add_argument("--manifest-hash", required=True)
    s.add_argument("--result-hash", required=True)
    s.add_argument("--revision", required=True)
    s.set_defaults(fn=cmd_verify_attestation)

    s = sub.add_parser("schema", help="print the R2A2 schema version")
    s.set_defaults(fn=cmd_schema)

    s = sub.add_parser("import-theory",
                       help="validate a theory from YAML/JSON transport")
    s.add_argument("file")
    s.set_defaults(fn=cmd_import_theory)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
