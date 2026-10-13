#!/usr/bin/env python3
"""Hardened public ProofPatch facade.

Important trust split:
- verify_bundle() proves schema/chain/semantic consistency only.
- verify_with_executor() additionally replays every claimed command through a
  verifier-owned executor boundary and compares exact results.
No local function grants cloud, network, repository, or submission authority.
"""
from __future__ import annotations

import json
import sys

import _proofpatch_core as _core
from _proofpatch_core import *  # public primitives, narrowed below

_ORIG_VALIDATE_PATCH = _core.validate_patch
_ORIG_VERIFY_RECEIPTS = _core.verify_receipts
_ORIG_VERIFY_BUNDLE = _core.verify_bundle
_ORIG_ADAPTER = _core.NebiusTokenFactoryAdapter


def validate_patch(value, baseline, patched):
    """Require the declared change set to equal *all* repository-root differences."""
    out = _ORIG_VALIDATE_PATCH(value, baseline, patched)
    base_hashes = _core.snapshot_hashes(baseline)
    post_hashes = _core.snapshot_hashes(patched)
    if set(base_hashes) != set(post_hashes):
        raise ProofError("patch may not hide file additions/deletions")
    actual = {path for path in base_hashes if base_hashes[path] != post_hashes[path]}
    declared = {row["path"] for row in out["changes"]}
    if actual != declared:
        raise ProofError("declared patch must enumerate every repository-root difference")
    return out


def verify_receipts(receipts, task, baseline, patched):
    """Retain core semantics and require focused phase to rerun the killer test."""
    out = _ORIG_VERIFY_RECEIPTS(receipts, task, baseline, patched)
    checked_task = _core.validate_task(task)
    if out[1]["command"] != checked_task["reproduction"]:
        raise ProofError("focused test must rerun the predecessor-discriminating reproduction")
    return out


class NebiusTokenFactoryAdapter(_ORIG_ADAPTER):
    """Pinned-model adapter: one frozen request generation reaches transport."""
    def execute(self, request, transport):
        # Freeze/reject the entire caller-owned request before this facade makes
        # any semantic read. Core execute() independently repeats this fence so
        # fresh direct-core imports retain the same transport boundary.
        frozen = _core.freeze_plain_json(request)
        if type(frozen) is not dict:
            raise ProofError("request must be mapping")
        body = frozen.get("body")
        if type(body) is not dict or body.get("model") != self.model or body.get("temperature") != 0:
            raise ProofError("request body escaped pinned model/generation policy")
        return super().execute(frozen, transport)


def verify_bundle(value):
    """Verify self-consistency without claiming provenance for caller-authored outputs."""
    result = _ORIG_VERIFY_BUNDLE(value)
    result["status"] = "STRUCTURAL_EVIDENCE_VERIFIED"
    result["executor_replay_verified"] = False
    result["replay_required"] = True
    result["receipt_provenance"] = "CALLER_AUTHORED_UNAUTHENTICATED"
    return result


def verify_with_executor(value, executor, executor_id):
    """Freeze once, then replay that exact structurally verified generation.

    The caller/verifier owns the trust decision for `executor`; this function
    does not pretend a Python object is cryptographic provider attestation.
    """
    snapshot = _core.freeze_plain_json(value)
    structural = verify_bundle(snapshot)
    executor_id = _core.valid_id(executor_id, "executor_id")
    if not hasattr(executor, "run") or not callable(executor.run):
        raise ProofError("executor must expose run(command, repo_digest)")
    for receipt in snapshot["receipts"]:
        actual = _core.validate_result(executor.run(receipt["command"], receipt["repo_before"]))
        claimed = _core.validate_result(receipt["result"])
        if actual != claimed:
            raise ProofError("executor replay disagrees with claimed receipt")
    structural["status"] = "EXECUTOR_REPLAY_VERIFIED"
    structural["executor_replay_verified"] = True
    structural["replay_required"] = False
    structural["executor_id"] = executor_id
    structural["receipt_provenance"] = "REPLAYED_BY_VERIFIER_SELECTED_EXECUTOR"
    return structural


def demo_executor():
    """Code-owned deterministic executor for the synthetic demo only."""
    baseline = _core.snapshot_from_files({"calc.py": _core.BASE_CALC, "test_calc.py": _core.TEST_CALC})
    patched = _core.snapshot_from_files({"calc.py": _core.PATCHED_CALC, "test_calc.py": _core.TEST_CALC})
    task = _core.validate_task({
        "schema": _core.TASK_SCHEMA,
        "task_id": "demo-ratio-floor-division",
        "issue_ref": "synthetic:ratio",
        "allowed_paths": ["calc.py"],
        "reproduction": {"argv": ["python", "-m", "unittest", "test_calc.py"], "timeout_s": 30},
        "regression": {"argv": ["python", "-m", "unittest", "discover"], "timeout_s": 30},
    })
    outcomes = {
        _core.HermeticFakeSandbox.key(task["reproduction"], baseline["digest"]):
            {"exit_code": 1, "stdout": "", "stderr": "AssertionError: 2 != 2.5", "timed_out": False},
        _core.HermeticFakeSandbox.key(task["reproduction"], patched["digest"]):
            {"exit_code": 0, "stdout": "OK", "stderr": "", "timed_out": False},
        _core.HermeticFakeSandbox.key(task["regression"], patched["digest"]):
            {"exit_code": 0, "stdout": "OK", "stderr": "", "timed_out": False},
    }
    return _core.HermeticFakeSandbox(outcomes)


def verify_demo_bundle(value):
    return verify_with_executor(value, demo_executor(), "proofpatch-hermetic-demo-v1")


# Core construction functions resolve validators through core module globals.
_core.validate_patch = validate_patch
_core.verify_receipts = verify_receipts
_core.NebiusTokenFactoryAdapter = NebiusTokenFactoryAdapter
_core.verify_bundle = verify_bundle


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print("usage: proofpatch.py {demo|verify|demo-verify|real-process|real-process-verify} [bundle]", file=sys.stderr)
        return 2
    try:
        if argv == ["demo"]:
            print(json.dumps(_core.demo_bundle(), sort_keys=True, indent=2))
            return 0
        if argv == ["demo-verify"]:
            print(json.dumps(verify_demo_bundle(_core.demo_bundle()), sort_keys=True, indent=2))
            return 0
        if argv == ["real-process"]:
            from _proofpatch_process import run_rehearsal
            report = run_rehearsal()
            print(json.dumps(report, sort_keys=True, indent=2))
            if not report["ok"]:
                print("proofpatch: " + report["error"], file=sys.stderr)
                return 2
            return 0
        if len(argv) == 2 and argv[0] == "real-process-verify":
            from _proofpatch_process import verify_rehearsal
            with open(argv[1], "r", encoding="utf-8") as handle:
                value = json.load(handle)
            report = verify_rehearsal(value)
            print(json.dumps(report, sort_keys=True, indent=2))
            if not report["ok"]:
                print("proofpatch: " + report["error"], file=sys.stderr)
                return 2
            return 0
        if len(argv) == 2 and argv[0] == "verify":
            with open(argv[1], "r", encoding="utf-8") as handle:
                value = json.load(handle)
            print(json.dumps(verify_bundle(value), sort_keys=True, indent=2))
            return 0
        print("usage: proofpatch.py {demo|verify|demo-verify|real-process|real-process-verify} [bundle]", file=sys.stderr)
        return 2
    except (OSError, json.JSONDecodeError, ProofError) as exc:
        print("proofpatch: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
