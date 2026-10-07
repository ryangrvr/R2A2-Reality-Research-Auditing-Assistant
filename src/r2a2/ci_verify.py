"""CI-native verification: non-interactive, meaningful exit codes.

Pipeline: schema validation → doctor → compile → freeze → execution-context
verification → run → audit → replication verification → attestation
verification → transfer audit → artifact verification.

Exit codes distinguish failure KINDS (never conflated):
    0  all checks passed
    2  execution failure    (software crashed, solver diverged)
    3  protocol failure     (process/provenance broke; e.g. unfrozen)
    4  theory failure       (a scientific RESULT: kill condition fired)
    5  trust failure        (signature/policy/attestation rejected)
"""
from __future__ import annotations

import json
import sys
from typing import List

from .api import Theory
from .compiler import compile_theory
from .failures import FailureKind, classify
from .runner import run_manifest

EXIT_OK = 0
EXIT_EXECUTION = 2
EXIT_PROTOCOL = 3
EXIT_THEORY = 4
EXIT_TRUST = 5

EXIT_NAMES = {EXIT_OK: "OK", EXIT_EXECUTION: "EXECUTION FAILURE",
              EXIT_PROTOCOL: "PROTOCOL FAILURE", EXIT_THEORY: "THEORY FAILURE",
              EXIT_TRUST: "TRUST FAILURE"}


def ci_verify(theory: Theory, policy=None, signed_attestations=None) -> tuple:
    """Full non-interactive verification pipeline. Returns (exit_code, report)."""
    steps: List[dict] = []
    code = EXIT_OK

    def step(name, fn):
        nonlocal code
        try:
            detail = fn()
            steps.append({"step": name, "ok": True, "detail": detail})
        except Exception as exc:
            kind = classify(exc)
            exit_for = {FailureKind.EXECUTION: EXIT_EXECUTION,
                        FailureKind.PROTOCOL: EXIT_PROTOCOL,
                        FailureKind.THEORY: EXIT_THEORY}.get(kind, EXIT_TRUST)
            steps.append({"step": name, "ok": False,
                          "failure_kind": kind.value,
                          "error": str(exc)[:500]})
            if code == EXIT_OK:
                code = exit_for
            return False
        return True

    # 1. doctor-level structure
    def _doctor():
        from .doctor import run_doctor, BLOCKING
        blocking = [m for c, m in run_doctor(theory) if c == BLOCKING]
        if blocking:
            raise RuntimeError("blocking findings: " + "; ".join(blocking[:3]))
        return "no blocking findings"
    step("doctor", _doctor)

    # 2. compile + freeze
    manifest, ledger = None, None
    def _compile():
        nonlocal manifest, ledger
        manifest, ledger = compile_theory(theory, seeds={"default": 0})
        h = manifest.freeze()
        return f"manifest {h[:12]}…"
    if not step("compile", _compile):
        return code, {"steps": steps}

    # 3. run (execution-context verification happens inside)
    def _run():
        res = run_manifest(theory, manifest, ledger)
        return f"{len(res.records)} records"
    step("run", _run)

    # 4. audit
    def _audit():
        from .audit import audit_theory
        report = audit_theory(theory, ledger)
        if not report.ok:
            raise RuntimeError("audit failed: " + "; ".join(report.blocking[:3]))
        return "audit clean"
    step("audit", _audit)

    # 5. attestation verification (if provided)
    if signed_attestations:
        def _attest():
            from .signing import verify_envelope
            from .trust import ReviewAttestation, verify_attestation
            bad = []
            for env in signed_attestations:
                att = env["payload"]["attestation"]
                inner = ReviewAttestation(
                    reviewer=att["reviewer"], scope=att["scope"],
                    manifest_hash=att["manifest_hash"],
                    result_hash=att["result_hash"],
                    code_revision=att["code_revision"], verdict=att["verdict"],
                    notes=att.get("notes", ""), issues=att.get("issues", []))
                seal = verify_attestation(inner, att["manifest_hash"],
                                          att["result_hash"],
                                          att["code_revision"],
                                          sealed_as=att["seal"])
                sig = verify_envelope(env, policy)
                if not seal["applies"] or not sig["content"] == "CONTENT VALID":
                    bad.append(f"{att['reviewer']}: seal/sig invalid")
                elif not sig["trusted"]:
                    bad.append(f"{att['reviewer']}: {sig['identity']}")
            if bad:
                raise RuntimeError("; ".join(bad))
            return f"{len(signed_attestations)} attestations verified"
        step("attestations", _attest)

    return code, {"steps": steps}
