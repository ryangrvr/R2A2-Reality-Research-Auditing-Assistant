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



def cmd_schema_json(args) -> int:
    from .schema_json import build_schema
    import json
    print(json.dumps(build_schema(), indent=2))
    return 0


def cmd_validate_artifact(args) -> int:
    from .schema_json import validate_artifact, schema_version_check
    with open(args.file) as f:
        doc = json.load(f)
    errors = schema_version_check(doc) + validate_artifact(doc, kind=args.type)
    if errors:
        for e in errors:
            print(f"X {e}")
        return 1
    print(f"{args.file}: valid against the public schema ({args.type})")
    return 0


def _full_export_data(theory):
    """Assemble manifest + results + bindings for exports."""
    m, led = compile_theory(theory, seeds={"default": 0})
    m.freeze()
    from .runner import run_manifest
    res = run_manifest(theory, m, led)
    from .transport import theory_to_dict
    return theory_to_dict(theory), m.to_dict(), res.records


def cmd_export_rocrate(args) -> int:
    from .rocrate import export_rocrate, write_crate, check_conformance
    theory_dict, manifest_dict, records = _full_export_data(_load_theory(args.theory))
    crate = export_rocrate(
        theory_dict, manifest_dict, records,
        authors=args.author or [], code_revision=args.revision or "")
    files = write_crate(crate, args.output)
    # self-check conformance AFTER materializing the attached crate
    import json as _json
    doc = _json.load(open(os.path.join(args.output, "ro-crate-metadata.json")))
    errs = check_conformance(doc, crate_dir=args.output)
    if errs:
        for e in errs:
            print(f"X crate conformance: {e}")
        return 1
    print(f"RO-Crate written to {args.output}/ ({len(files)} files); "
          "structural conformance check passed")
    return 0


def cmd_export_prov(args) -> int:
    from .prov_export import export_prov, check_prov_conformance
    import json
    theory_dict, manifest_dict, records = _full_export_data(_load_theory(args.theory))
    prov = export_prov(theory_dict, manifest_dict, records,
                       authors=args.author or [], code_revision=args.revision or "")
    errs = check_prov_conformance(prov)
    if errs:
        for e in errs:
            print(f"X PROV conformance: {e}")
        return 1
    if args.output:
        with open(args.output, "w") as f:
            json.dump(prov, f, indent=2)
        print(f"PROV document written to {args.output}")
    else:
        print(json.dumps(prov, indent=2))
    return 0


def cmd_init_project(args) -> int:
    import os
    os.makedirs(args.dir, exist_ok=True)
    for sub in ("data", "tests"):
        os.makedirs(os.path.join(args.dir, sub), exist_ok=True)
    theory = """\"\"\"My theory project. Edit every part of this file.\"\"\"
from r2a2.api import Theory, Parameter, Assumption, Prediction, Test, Comparator

def measure(**kw):
    # replace with your real computation; must return a machine-readable dict
    return {"observable": 0.0}

def identity_check(**kw):
    return {"residual": 0.0}

THEORY = Theory(
    id="my-theory",
    version="0.0.1",
    description="What does your theory claim?",
    validity_domain="Under what conditions does it hold?",
    parameters=[
        # kind: commitment | imported-constant | fitted-parameter | external-prior | sector-input
        Parameter("alpha", kind="commitment", value=1.0),
    ],
    assumptions=[
        Assumption("A1", "state the assumption precisely", kind="assumption", priced=True),
    ],
    comparators=[Comparator("null-model", "what existing model are you comparing against?")],
    predictions=[
        Prediction(
            "P1", "what do you predict, quantitatively?",
            experiment="measure", observable="observable",
            kill_condition="what observed result would prove you wrong?",
            assumptions=["A1"], parameters=["alpha"],
            evidence_grade="numerical", comparator="null-model"),
    ],
    tests=[
        Test("T-identity", kind="identity", experiment="identity_check", exact=True,
             description="an exact check of the numerical pipeline"),
        # add a hostile control: a test designed to FAIL if a confounder explains P1
    ],
    experiments={"measure": measure, "identity_check": identity_check},
    sources={"my-source": "where did your parameter values/inputs come from?"},
)
"""
    with open(os.path.join(args.dir, "theory.py"), "w") as f:
        f.write(theory)
    with open(os.path.join(args.dir, "README.md"), "w") as f:
        f.write("""# My theory project

Start by editing `theory.py`. Then:

    r2a2 doctor .
    r2a2 compile theory.theory:THEORY
    r2a2 run theory.theory:THEORY
    r2a2 audit theory.theory:THEORY

R2A2 verifies discipline, not truth: a passing audit means your claims are
well-provenanced and falsifiable, not that your theory is correct.
""")
    with open(os.path.join(args.dir, "r2a2.toml"), "w") as f:
        f.write('[project]\nname = "my-theory"\nr2a2_schema = "%s"\n' % __import__("r2a2.schema", fromlist=["SCHEMA_VERSION"]).SCHEMA_VERSION)
    print(f"project scaffolded in {args.dir}/ — run: r2a2 doctor {args.dir}")
    return 0


def cmd_doctor(args) -> int:
    import importlib, sys, os
    sys.path.insert(0, args.project)
    mod_name = args.module or "theory"
    mod = importlib.import_module(mod_name)
    theory = getattr(mod, "THEORY", None)
    if theory is None:
        print(f"X no THEORY found in {mod_name}")
        return 1
    from .doctor import run_doctor
    findings = run_doctor(theory)
    counts = {}
    for cat, msg in findings:
        counts[cat] = counts.get(cat, 0) + 1
        print(f"[{cat}] {msg}")
    print("-" * 70)
    print(f"{len(findings)} findings: " + ", ".join(f"{k}: {v}" for k, v in counts.items()))
    if any(cat == "BLOCKING" for cat, _ in findings):
        return 1
    return 0


def cmd_inspect(args) -> int:
    import json
    with open(args.artifact) as f:
        doc = json.load(f)
    if "theory_id" in doc and "hash" in doc:       # execution manifest
        print(f"manifest for {doc['theory_id']} v{doc.get('theory_version')}")
        print(f"  manifest hash:       {doc.get('hash')}")
        print(f"  declaration hash:    {doc.get('theory_declaration_hash')}")
        print(f"  backend:             {doc.get('backend')}")
        for name, b in doc.get("experiment_bindings", {}).items():
            print(f"  experiment {name}: {b.get('ref')} [{str(b.get('source_hash'))[:12]}]")
    elif "result_hash" in doc:                      # result record
        print(f"result {doc.get('experiment')}")
        print(f"  result hash:    {doc.get('result_hash')}")
        print(f"  manifest hash:  {doc.get('manifest_hash')}")
        print(f"  value:          {json.dumps(doc.get('result'))}")
    elif "record_hash" in doc:                      # replication record
        print(f"replication of {doc.get('test_id')}")
        print(f"  agrees:               {doc.get('agrees')}")
        print(f"  independence level:   {doc.get('independence_level')}")
        print(f"  record hash:          {doc.get('record_hash')}")
    elif "seal" in doc:                             # attestation
        print(f"attestation by {doc.get('reviewer')}")
        print(f"  scope:          {doc.get('scope')}")
        print(f"  verdict:        {doc.get('verdict')}")
        print(f"  issues:         {doc.get('issues') or 'none'}")
        print(f"  seal:           {str(doc.get('seal'))[:16]}…")
    else:
        print(json.dumps(doc, indent=2)[:2000])
    return 0


def cmd_verify(args) -> int:
    """Validate schema + hashes + attestations without executing."""
    import json
    from .schema_json import validate_artifact, schema_version_check
    from .trust import ReviewAttestation, verify_attestation
    from .transport import theory_from_dict
    ok = True
    with open(args.artifact) as f:
        doc = json.load(f)
    errors = schema_version_check(doc) + validate_artifact(doc, kind=args.type)
    for e in errors:
        print(f"X {e}"); ok = False
    if "seal" in doc:
        att = ReviewAttestation(
            reviewer=doc["reviewer"], scope=doc["scope"],
            manifest_hash=doc["manifest_hash"], result_hash=doc["result_hash"],
            code_revision=doc["code_revision"], verdict=doc["verdict"],
            notes=doc.get("notes", ""), issues=doc.get("issues", []))
        res = verify_attestation(att, doc["manifest_hash"], doc["result_hash"],
                                 doc["code_revision"], sealed_as=doc["seal"])
        print(f"attestation seal: {'intact' if res['seal_intact'] else 'BROKEN'}; "
              f"applies: {res['applies']}")
        ok = ok and res["applies"]
    if ok:
        print(f"{args.artifact}: verified (no execution performed)")
    return 0 if ok else 1



def _load_policy(path):
    from r2a2.signing import IdentityPolicy
    if path and os.path.exists(path):
        with open(path) as f:
            d = json.load(f)
        return IdentityPolicy(**d)
    # default dev policy: offline mode allowed explicitly
    return IdentityPolicy(allow_unsigned=True)


def cmd_sign_attestation(args) -> int:
    from r2a2.signing import sign_payload, SIGNER_OFFLINE
    with open(args.file) as f:
        att = json.load(f)
    envelope = sign_payload(
        {"kind": "r2a2.review-attestation", "attestation": att},
        signer_backend=args.backend,
        identity=args.identity, issuer=args.issuer)
    with open(args.file, "w") as f:
        json.dump(envelope, f, indent=2)
    backend = envelope.get("signer_backend")
    note = ("UNAUTHENTICATED offline dev signature" if backend == SIGNER_OFFLINE
            else "identity-backed signature")
    print(f"signed: {args.file} [{backend}] {note}")
    return 0


def cmd_verify_attestation_signed(args) -> int:
    from r2a2.signing import verify_envelope, _payload_digest
    with open(args.file) as f:
        envelope = json.load(f)
    # re-verify the CONTENT SEAL of the inner attestation first (independent
    # of the signature), then the identity layer
    from r2a2.trust import ReviewAttestation, verify_attestation
    att = envelope["payload"]["attestation"]
    inner = ReviewAttestation(
        reviewer=att["reviewer"], scope=att["scope"],
        manifest_hash=att["manifest_hash"], result_hash=att["result_hash"],
        code_revision=att["code_revision"], verdict=att["verdict"],
        notes=att.get("notes", ""), issues=att.get("issues", []))
    seal_res = verify_attestation(inner, args.manifest_hash, args.result_hash,
                                  args.revision, sealed_as=att["seal"])
    policy = _load_policy(args.policy)
    res = verify_envelope(envelope, policy)
    print(f"content seal: {'INTACT' if seal_res['applies'] else 'BROKEN'}")
    print(f"signature content: {res['content']}")
    print(f"identity: {res['identity']} (claim: {res.get('identity_claim')})")
    print(f"overall trusted: {res['trusted']}")
    ok = seal_res["applies"] and res["content"] == "CONTENT VALID" and \
        (res["trusted"] or (res["identity"] == "UNAUTHENTICATED (offline dev mode)"))
    return 0 if ok else 1


def cmd_ci_verify(args) -> int:
    from r2a2.ci_verify import ci_verify, EXIT_NAMES
    theory = _load_theory(args.theory)
    policy, atts = None, None
    if args.policy:
        policy = _load_policy(args.policy)
    if args.attestations:
        with open(args.attestations) as f:
            atts = json.load(f)
    code, report = ci_verify(theory, policy, atts)
    for st in report["steps"]:
        status = "OK " if st["ok"] else "FAIL"
        line = f"[{status}] {st['step']}"
        if not st["ok"]:
            line += f" ({st['failure_kind']}) {st['error'][:120]}"
        elif st.get("detail"):
            line += f": {st['detail']}"
        print(line)
    print(f"CI result: {EXIT_NAMES.get(code, code)}")
    return code


def cmd_plugins_list(args):
    from r2a2.plugins import PluginPolicy, PluginManifest
    import glob as g
    found = []
    for mf in g.glob(os.path.join(args.dir, "*.plugin.json")):
        with open(mf) as f:
            found.append(PluginManifest.from_dict(json.load(f)))
    policy = PluginPolicy(allow_unsigned=True, trusted_ids=args.trusted or [])
    for m in found:
        rep = policy.evaluate(m)
        print(f"{m.plugin_id} v{m.version} [{m.execution_class}] "
              f"api={m.extension_api} trusted={rep['trusted']}")
    if not found:
        print("no plugin manifests (*.plugin.json) found")
    return 0


def cmd_plugins_inspect(args):
    from r2a2.plugins import PluginManifest, inspect_plugin
    with open(args.manifest) as f:
        print(inspect_plugin(PluginManifest.from_dict(json.load(f))))
    return 0


def cmd_plugins_verify(args):
    from r2a2.plugins import PluginManifest, PluginPolicy
    with open(args.manifest) as f:
        m = PluginManifest.from_dict(json.load(f))
    rep = PluginPolicy(allow_unsigned=args.allow_unsigned,
                       trusted_ids=args.trusted or [],
                       identity_policy=_load_policy(args.policy)).evaluate(m)
    print(json.dumps(rep, indent=2))
    return 0 if rep["trusted"] else 1

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

    s = sub.add_parser("sign-attestation", help="sign a review attestation (identity-backed or offline dev mode)")
    s.add_argument("file")
    s.add_argument("--backend", default=None)
    s.add_argument("--identity", default=None)
    s.add_argument("--issuer", default=None)
    s.set_defaults(fn=cmd_sign_attestation)

    s = sub.add_parser("verify-signed-attestation",
                       help="verify signature + content seal of a signed attestation")
    s.add_argument("file")
    s.add_argument("--policy", default=None)
    s.add_argument("--manifest-hash", required=True)
    s.add_argument("--result-hash", required=True)
    s.add_argument("--revision", required=True)
    s.set_defaults(fn=cmd_verify_attestation_signed)

    s = sub.add_parser("verify-attestation",
                       help="check an attestation still applies to given artifacts")
    s.add_argument("attestation")
    s.add_argument("--manifest-hash", required=True)
    s.add_argument("--result-hash", required=True)
    s.add_argument("--revision", required=True)
    s.set_defaults(fn=cmd_verify_attestation)

    s = sub.add_parser("schema", help="print the R2A2 schema version; --json for the public JSON Schema")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=lambda a: cmd_schema_json(a) if a.json else cmd_schema(a))


    s = sub.add_parser("validate-artifact", help="validate a JSON artifact against the public schema")
    s.add_argument("file")
    s.add_argument("--type", default="auto")
    s.set_defaults(fn=cmd_validate_artifact)

    s = sub.add_parser("export-rocrate", help="export a research object (RO-Crate)")
    s.add_argument("theory")
    s.add_argument("-o", "--output", default="ro-crate")
    s.add_argument("--author", action="append")
    s.add_argument("--revision", default="")
    s.set_defaults(fn=cmd_export_rocrate)

    s = sub.add_parser("export-prov", help="export W3C PROV provenance")
    s.add_argument("theory")
    s.add_argument("-o", "--output", default=None)
    s.add_argument("--author", action="append")
    s.add_argument("--revision", default="")
    s.set_defaults(fn=cmd_export_prov)

    s = sub.add_parser("ci", help="non-interactive CI verification with failure-kind exit codes")
    s.add_argument("verify")
    s.add_argument("theory")
    s.add_argument("--policy", default=None)
    s.add_argument("--attestations", default=None)
    s.set_defaults(fn=cmd_ci_verify)

    s = sub.add_parser("plugins", help="plugin management")
    sub2 = s.add_subparsers(dest="plugin_cmd", required=True)
    p2 = sub2.add_parser("list"); p2.add_argument("--dir", default="."); p2.add_argument("--trusted", nargs="*"); p2.set_defaults(fn=cmd_plugins_list)
    p2 = sub2.add_parser("inspect"); p2.add_argument("manifest"); p2.set_defaults(fn=cmd_plugins_inspect)
    p2 = sub2.add_parser("verify"); p2.add_argument("manifest"); p2.add_argument("--allow-unsigned", action="store_true"); p2.add_argument("--trusted", nargs="*"); p2.add_argument("--policy", default=None); p2.set_defaults(fn=cmd_plugins_verify)

    s = sub.add_parser("init-project", help="scaffold a full external-user theory project")
    s.add_argument("dir")
    s.set_defaults(fn=cmd_init_project)

    s = sub.add_parser("doctor", help="diagnose a project in plain scientific language")
    s.add_argument("project")
    s.add_argument("--module", default="theory")
    s.set_defaults(fn=cmd_doctor)

    s = sub.add_parser("inspect", help="inspect someone else's artifact (no Python needed)")
    s.add_argument("artifact")
    s.add_argument("--type", default="auto")
    s.set_defaults(fn=cmd_inspect)

    s = sub.add_parser("verify", help="verify an artifact's hashes/schema/attestations without executing")
    s.add_argument("artifact")
    s.add_argument("--type", default="auto")
    s.set_defaults(fn=cmd_verify)
    s = sub.add_parser("import-theory",
                       help="validate a theory from YAML/JSON transport")
    s.add_argument("file")
    s.set_defaults(fn=cmd_import_theory)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
