#!/usr/bin/env python3
"""Provider-neutral federated CI receipt engine.

The muhlnickel is the computer. This module plans shards, wraps a runner-neutral
command envelope, normalizes receipts, and reconciles them. It does not activate
a CI provider. Provider names are observations, not gates. Unknown providers
remain legal manifest targets. A config file or a fixture is not a measured run.

Cite PLUMB/Opus 5 #commons 2026-08-23. Do not remint. Do not invent run URLs,
quota, success, failover, or another provider going LIVE.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MANIFEST_SCHEMA_VERSION = "commons-federated-job-manifest/v1"
RECEIPT_SCHEMA_VERSION = "commons-federated-receipt/v1"
RECONCILE_SCHEMA_VERSION = "commons-federated-reconciliation/v1"
SCANNER_VERSION = "commons-federated-ci-scan/v1"
ENGINE_VERSION = "commons-federated-ci/v1"

HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")

TERMINAL_STATES = frozenset(
    {"PASSED", "FAILED", "CANCELLED", "SKIPPED", "TIMED_OUT", "FIXTURE"}
)
# FIXTURE means the receipt is a shape/config observation, not an executed job.

SUPPORTED_BY_CONTRACT = (
    "github-actions",
    "cirrus",
    "gitlab",
    "woodpecker",
    "local-fixture",
)

SCAN_PATTERNS = {
    "PRIVATE_KEY": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "GITHUB_TOKEN": re.compile(rb"gh[pousr]_[A-Za-z0-9_]{20,}"),
    "SLACK_TOKEN": re.compile(rb"xox[baprs]-[A-Za-z0-9-]{10,}"),
    "AWS_KEY": re.compile(rb"AKIA[0-9A-Z]{16}"),
    "STRIPE_SECRET": re.compile(rb"(?:sk|rk)_live_[A-Za-z0-9]{16,}"),
    "BEARER": re.compile(rb"Bearer\s+[A-Za-z0-9._~+/=-]{16,}", re.IGNORECASE),
    "PASSWORD": re.compile(rb"(?:password|passwd|pwd)\s*[:=]\s*[^\s,;]{4,}", re.IGNORECASE),
    "EMAIL": re.compile(rb"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
    "PHONE": re.compile(
        rb"(?<!\d)(?:\+?1[-. ]?)?\(?[2-9]\d{2}\)?[-. ]?\d{3}[-. ]?\d{4}(?!\d)"
    ),
}

MANIFEST_KEYS = {
    "schema_version", "kind", "job_id", "source_sha", "repository", "tests",
    "shard_count", "command_template", "providers", "timeout_s", "claim_boundary",
}
RECEIPT_KEYS = {
    "schema_version", "kind", "receipt_id", "job_id", "shard_id", "attempt",
    "parent_receipt_id", "source_sha", "test_identity", "command", "exit_code",
    "duration_ms", "artifacts", "provider", "run_url", "terminal_state",
    "measured", "claim_boundary", "scan",
}
COMMAND_KEYS = {"argv", "cwd", "env", "timeout_s", "shell"}
ARTIFACT_KEYS = {"path", "sha256", "bytes"}
CLAIM_KEYS = {
    "measured_live_run", "provider_activated_by_this_engine",
    "other_provider_activated", "fabricated_url", "quota_claimed",
}


class FederatedError(ValueError):
    """Schema, planning, receipt, or reconciliation boundary violation."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FederatedError(message)


def _exact_keys(value: Any, required: set[str], at: str) -> None:
    _require(isinstance(value, dict), f"{at} must be an object")
    missing = sorted(required - set(value))
    extra = sorted(set(value) - required)
    _require(not missing, f"{at} missing keys {missing!r}")
    _require(not extra, f"{at} has extra keys {extra!r}")


def scan_bytes(raw: bytes) -> dict[str, int]:
    return {name: len(pattern.findall(raw)) for name, pattern in SCAN_PATTERNS.items()}


def scan_obj(obj: Any) -> dict[str, int]:
    return scan_bytes(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def receipt_id_for(job_id, shard_id, attempt, provider, source_sha, test_identity) -> str:
    material = f"{job_id}|{shard_id}|{attempt}|{provider}|{source_sha}|{test_identity}"
    return "fcr-" + sha256_text(material)[:16]


def command_envelope(argv, cwd=".", env=None, timeout_s=60, shell=False):
    _require(isinstance(argv, list) and argv and all(isinstance(x, str) for x in argv), "argv invalid")
    _require(isinstance(cwd, str) and cwd and ".." not in Path(cwd).parts, "cwd escapes")
    _require(shell is False, "shell envelopes are refused")
    env = env or {}
    _require(isinstance(env, dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in env.items()), "env invalid")
    banned = {k.upper() for k in env}
    _require(not (banned & {"GITHUB_TOKEN", "GH_TOKEN", "AWS_SECRET_ACCESS_KEY", "SLACK_BOT_TOKEN"}), "env carries a secret name")
    _require(isinstance(timeout_s, int) and 1 <= timeout_s <= 21600, "timeout_s out of range")
    envelope = {"argv": list(argv), "cwd": cwd, "env": dict(sorted(env.items())), "timeout_s": timeout_s, "shell": False}
    _exact_keys(envelope, COMMAND_KEYS, "command")
    return envelope


def plan_shards(tests, shard_count):
    _require(isinstance(tests, list) and tests, "tests must be a non-empty list")
    _require(all(isinstance(t, str) and t.strip() and t == t.strip() for t in tests), "test identity invalid")
    _require(len(set(tests)) == len(tests), "duplicate test identities")
    _require(isinstance(shard_count, int) and shard_count >= 1, "shard_count must be >= 1")
    _require(shard_count <= len(tests), "shard_count exceeds test count")
    ordered = sorted(tests)
    shards = [[] for _ in range(shard_count)]
    for index, identity in enumerate(ordered):
        shards[index % shard_count].append(identity)
    return [{"shard_id": i, "tests": m, "test_identity": "+".join(m)} for i, m in enumerate(shards)]


def validate_claim_boundary(boundary, at="claim_boundary"):
    _exact_keys(boundary, CLAIM_KEYS, at)
    for key in CLAIM_KEYS:
        _require(isinstance(boundary[key], bool), f"{at}.{key} must be bool")
    _require(boundary["fabricated_url"] is False, "fabricated_url must stay false")
    _require(boundary["quota_claimed"] is False, "quota_claimed must stay false")
    if boundary["measured_live_run"] is False:
        _require(boundary["provider_activated_by_this_engine"] is False, "unmeasured run cannot claim activation")
    _require(boundary["other_provider_activated"] is False, "must not claim another provider was activated")
    return boundary


def validate_manifest(manifest):
    _exact_keys(manifest, MANIFEST_KEYS, "manifest")
    _require(manifest["schema_version"] == MANIFEST_SCHEMA_VERSION, "manifest schema_version drift")
    _require(manifest["kind"] == "FEDERATED_JOB_MANIFEST", "manifest kind drift")
    _require(isinstance(manifest["job_id"], str) and manifest["job_id"], "job_id invalid")
    _require(bool(HEX40.fullmatch(manifest["source_sha"])), "source_sha invalid")
    _require(manifest["repository"] == "woahwhattheheck/commons", "repository drift")
    _require(isinstance(manifest["timeout_s"], int) and manifest["timeout_s"] >= 1, "timeout_s invalid")
    tmpl = manifest["command_template"]
    _require(isinstance(tmpl, dict) and isinstance(tmpl.get("argv"), list), "command_template invalid")
    command_envelope(list(tmpl["argv"]), cwd=tmpl.get("cwd", "."), env=tmpl.get("env") or {}, timeout_s=int(tmpl.get("timeout_s", manifest["timeout_s"])), shell=bool(tmpl.get("shell", False)))
    providers = manifest["providers"]
    _require(isinstance(providers, list) and providers, "providers must be a list")
    _require(all(isinstance(p, str) and p.strip() for p in providers), "provider name invalid")
    validate_claim_boundary(manifest["claim_boundary"], "manifest.claim_boundary")
    _require(manifest["claim_boundary"]["measured_live_run"] is False, "manifest is a plan, not a measured run")
    plan_shards(list(manifest["tests"]), int(manifest["shard_count"]))
    hits = scan_obj(manifest)
    _require(not any(hits.values()), f"manifest secret/PII scan hits {hits}")
    return manifest


def validate_receipt(receipt, expected_source_sha=None):
    _exact_keys(receipt, RECEIPT_KEYS, "receipt")
    _require(receipt["schema_version"] == RECEIPT_SCHEMA_VERSION, "receipt schema_version drift")
    _require(receipt["kind"] == "FEDERATED_CI_RECEIPT", "receipt kind drift")
    _require(isinstance(receipt["receipt_id"], str) and receipt["receipt_id"].startswith("fcr-"), "receipt_id invalid")
    _require(isinstance(receipt["job_id"], str) and receipt["job_id"], "job_id invalid")
    _require(isinstance(receipt["shard_id"], int) and receipt["shard_id"] >= 0, "shard_id invalid")
    _require(isinstance(receipt["attempt"], int) and receipt["attempt"] >= 1, "attempt invalid")
    parent = receipt["parent_receipt_id"]
    _require(parent is None or (isinstance(parent, str) and parent.startswith("fcr-")), "parent_receipt_id invalid")
    if receipt["attempt"] == 1:
        _require(parent is None, "attempt 1 cannot carry parent lineage")
    else:
        _require(isinstance(parent, str), "retry missing parent_receipt_id")
    _require(bool(HEX40.fullmatch(receipt["source_sha"])), "source_sha invalid")
    if expected_source_sha is not None:
        _require(receipt["source_sha"] == expected_source_sha, "stale-source run")
    _require(isinstance(receipt["test_identity"], str) and receipt["test_identity"], "test_identity invalid")
    cmd = receipt["command"]
    _exact_keys(cmd, COMMAND_KEYS, "receipt.command")
    command_envelope(cmd["argv"], cmd["cwd"], cmd["env"], cmd["timeout_s"], cmd["shell"])
    _require(isinstance(receipt["exit_code"], int), "exit_code invalid")
    _require(isinstance(receipt["duration_ms"], int) and receipt["duration_ms"] >= 0, "duration_ms invalid")
    artifacts = receipt["artifacts"]
    _require(isinstance(artifacts, list), "artifacts must be a list")
    for i, art in enumerate(artifacts):
        _exact_keys(art, ARTIFACT_KEYS, f"artifacts[{i}]")
        _require(isinstance(art["path"], str) and art["path"] and ".." not in Path(art["path"]).parts, "artifact path escapes")
        _require(bool(HEX64.fullmatch(art["sha256"])), "artifact sha256 invalid")
        _require(isinstance(art["bytes"], int) and art["bytes"] >= 0, "artifact bytes invalid")
    _require(isinstance(receipt["provider"], str) and receipt["provider"].strip(), "provider invalid")
    run_url = receipt["run_url"]
    _require(run_url is None or (isinstance(run_url, str) and run_url.startswith(("https://", "fixture://"))), "run_url invalid")
    _require(receipt["terminal_state"] in TERMINAL_STATES, "terminal_state invalid")
    _require(isinstance(receipt["measured"], bool), "measured invalid")
    validate_claim_boundary(receipt["claim_boundary"], "receipt.claim_boundary")
    if receipt["measured"] is True:
        _require(receipt["terminal_state"] != "FIXTURE", "measured receipt cannot be FIXTURE")
        _require(receipt["claim_boundary"]["measured_live_run"] is True, "measured flag disagrees with claim_boundary")
    else:
        _require(receipt["claim_boundary"]["measured_live_run"] is False, "unmeasured receipt claims live run")
        _require(receipt["run_url"] is None or str(receipt["run_url"]).startswith("fixture://"), "unmeasured receipt has a live URL")
    scan = receipt["scan"]
    _require(isinstance(scan, dict) and scan.get("scanner_version") == SCANNER_VERSION, "scan header drift")
    _require(scan.get("status") == "PASS_ZERO_HITS", "scan status drift")
    _require(not any(scan.get("hit_counts", {}).values()), "recorded scan contains hits")
    hits = scan_obj({k: receipt[k] for k in receipt if k != "scan"})
    _require(not any(hits.values()), f"receipt secret/PII scan hits {hits}")
    expected_id = receipt_id_for(receipt["job_id"], receipt["shard_id"], receipt["attempt"], receipt["provider"], receipt["source_sha"], receipt["test_identity"])
    _require(receipt["receipt_id"] == expected_id, "receipt_id not deterministic")
    return receipt


def make_receipt(*, job_id, shard_id, attempt, source_sha, test_identity, command, exit_code, duration_ms, artifacts, provider, run_url, terminal_state, measured, parent_receipt_id=None, claim_boundary=None):
    boundary = claim_boundary or {
        "measured_live_run": bool(measured),
        "provider_activated_by_this_engine": False,
        "other_provider_activated": False,
        "fabricated_url": False,
        "quota_claimed": False,
    }
    receipt = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "kind": "FEDERATED_CI_RECEIPT",
        "receipt_id": receipt_id_for(job_id, shard_id, attempt, provider, source_sha, test_identity),
        "job_id": job_id,
        "shard_id": shard_id,
        "attempt": attempt,
        "parent_receipt_id": parent_receipt_id,
        "source_sha": source_sha,
        "test_identity": test_identity,
        "command": command_envelope(command["argv"], command.get("cwd", "."), command.get("env") or {}, command.get("timeout_s", 60), command.get("shell", False)),
        "exit_code": int(exit_code),
        "duration_ms": int(duration_ms),
        "artifacts": artifacts,
        "provider": provider,
        "run_url": run_url,
        "terminal_state": terminal_state,
        "measured": bool(measured),
        "claim_boundary": boundary,
        "scan": {"scanner_version": SCANNER_VERSION, "rules": list(SCAN_PATTERNS), "hit_counts": {name: 0 for name in SCAN_PATTERNS}, "status": "PASS_ZERO_HITS"},
    }
    hits = scan_obj({k: receipt[k] for k in receipt if k != "scan"})
    receipt["scan"]["hit_counts"] = hits
    receipt["scan"]["status"] = "PASS_ZERO_HITS" if not any(hits.values()) else "FAIL_HITS"
    return validate_receipt(receipt)


def run_local_fixture(manifest, shard_id, *, attempt=1, parent_receipt_id=None, extra_env=None):
    validate_manifest(manifest)
    planned = plan_shards(list(manifest["tests"]), int(manifest["shard_count"]))
    _require(0 <= shard_id < len(planned), "shard_id out of range")
    shard = planned[shard_id]
    tmpl = manifest["command_template"]
    argv = [part.replace("{shard_id}", str(shard_id)).replace("{test_identity}", shard["test_identity"]) for part in tmpl["argv"]]
    env = dict(tmpl.get("env") or {})
    if extra_env:
        env.update(extra_env)
    envelope = command_envelope(argv, tmpl.get("cwd", "."), env, int(tmpl.get("timeout_s", manifest["timeout_s"])), False)
    started = time.monotonic()
    try:
        completed = subprocess.run(envelope["argv"], cwd=os.path.join(ROOT, envelope["cwd"]) if envelope["cwd"] != "." else ROOT, env={**os.environ, **envelope["env"]}, capture_output=True, timeout=envelope["timeout_s"], check=False)
        duration_ms = int((time.monotonic() - started) * 1000)
        stdout, stderr, exit_code = completed.stdout, completed.stderr, int(completed.returncode)
        state = "PASSED" if exit_code == 0 else "FAILED"
    except subprocess.TimeoutExpired as exc:
        duration_ms = int((time.monotonic() - started) * 1000)
        stdout, stderr, exit_code, state = exc.stdout or b"", exc.stderr or b"", 124, "TIMED_OUT"
    artifacts = [
        {"path": f"ci/federated/artifacts/{manifest['job_id']}/shard-{shard_id}.stdout", "sha256": sha256_bytes(stdout), "bytes": len(stdout)},
        {"path": f"ci/federated/artifacts/{manifest['job_id']}/shard-{shard_id}.stderr", "sha256": sha256_bytes(stderr), "bytes": len(stderr)},
    ]
    return make_receipt(job_id=manifest["job_id"], shard_id=shard_id, attempt=attempt, source_sha=manifest["source_sha"], test_identity=shard["test_identity"], command=envelope, exit_code=exit_code, duration_ms=duration_ms, artifacts=artifacts, provider="local-fixture", run_url=None, terminal_state=state, measured=True, parent_receipt_id=parent_receipt_id, claim_boundary={"measured_live_run": True, "provider_activated_by_this_engine": False, "other_provider_activated": False, "fabricated_url": False, "quota_claimed": False})


def _artifact_map(receipt):
    return {row["path"]: (row["sha256"], row["bytes"]) for row in receipt["artifacts"]}


def reconcile(manifest, receipts, *, expected_source_sha=None):
    validate_manifest(manifest)
    expected_source_sha = expected_source_sha or manifest["source_sha"]
    planned = plan_shards(list(manifest["tests"]), int(manifest["shard_count"]))
    wanted = {row["shard_id"]: row["test_identity"] for row in planned}
    findings, accepted = [], []
    for index, receipt in enumerate(receipts):
        at = f"receipts[{index}]"
        try:
            validate_receipt(receipt, expected_source_sha=None)
        except FederatedError as exc:
            findings.append({"code": "MALFORMED", "at": at, "detail": str(exc)})
            continue
        if receipt["job_id"] != manifest["job_id"]:
            findings.append({"code": "MALFORMED", "at": at, "detail": "job_id mismatch"})
            continue
        if receipt["source_sha"] != expected_source_sha:
            findings.append({"code": "STALE_SOURCE", "at": at, "detail": f"{receipt['source_sha']} != {expected_source_sha}", "receipt_id": receipt["receipt_id"]})
            continue
        if receipt["shard_id"] not in wanted:
            findings.append({"code": "MALFORMED", "at": at, "detail": "shard not in plan", "receipt_id": receipt["receipt_id"]})
            continue
        if receipt["test_identity"] != wanted[receipt["shard_id"]]:
            findings.append({"code": "MALFORMED", "at": at, "detail": "test_identity disagrees with planner", "receipt_id": receipt["receipt_id"]})
            continue
        if receipt["terminal_state"] == "CANCELLED":
            findings.append({"code": "CANCELLED", "at": at, "receipt_id": receipt["receipt_id"], "shard_id": receipt["shard_id"]})
        accepted.append(receipt)
    by_id = defaultdict(list)
    for receipt in accepted:
        by_id[receipt["receipt_id"]].append(receipt)
    for rid, group in sorted(by_id.items()):
        if len(group) > 1:
            findings.append({"code": "DUPLICATE_RECEIPT", "receipt_id": rid, "count": len(group), "providers": sorted({row["provider"] for row in group})})
    by_shard = defaultdict(list)
    seen_ids = set()
    for receipt in accepted:
        if receipt["receipt_id"] in seen_ids:
            continue
        seen_ids.add(receipt["receipt_id"])
        by_shard[receipt["shard_id"]].append(receipt)
    for shard_id in sorted(wanted):
        group = by_shard.get(shard_id, [])
        if not group:
            findings.append({"code": "MISSING_SHARD", "shard_id": shard_id, "test_identity": wanted[shard_id]})
            continue
        lineage = sorted(group, key=lambda row: (row["attempt"], row["receipt_id"]))
        for row in lineage:
            if row["attempt"] > 1:
                parent_ok = any(other["receipt_id"] == row["parent_receipt_id"] for other in lineage)
                findings.append({"code": "RETRY_LINEAGE", "shard_id": shard_id, "receipt_id": row["receipt_id"], "parent_receipt_id": row["parent_receipt_id"], "parent_present": parent_ok, "attempt": row["attempt"]})
        exits = {row["exit_code"] for row in lineage}
        if len(exits) > 1:
            findings.append({"code": "CONTRADICTORY_EXIT", "shard_id": shard_id, "exits": sorted(exits), "states": sorted({row["terminal_state"] for row in lineage}), "receipt_ids": [row["receipt_id"] for row in lineage]})
        maps = [_artifact_map(row) for row in lineage if row["terminal_state"] not in {"CANCELLED", "SKIPPED"}]
        if maps:
            paths = set().union(*[set(m) for m in maps])
            for path in sorted(paths):
                hashes = {m[path] for m in maps if path in m}
                if len(hashes) > 1:
                    findings.append({"code": "ARTIFACT_DRIFT", "shard_id": shard_id, "path": path, "hashes": sorted(h[0] for h in hashes)})
                present = [path in m for m in maps]
                if any(present) and not all(present):
                    findings.append({"code": "HASH_MISMATCH", "shard_id": shard_id, "path": path, "detail": "artifact missing on a sibling receipt"})
        measured = [row for row in lineage if row["measured"] and row["terminal_state"] in {"PASSED", "FAILED"}]
        fixtures = [row for row in lineage if row["terminal_state"] == "FIXTURE" or not row["measured"]]
        if len(measured) >= 2:
            first = measured[0]
            if all(other["exit_code"] == first["exit_code"] and _artifact_map(other) == _artifact_map(first) for other in measured[1:]):
                findings.append({"code": "EQUIVALENT", "shard_id": shard_id, "receipt_ids": [row["receipt_id"] for row in measured], "providers": [row["provider"] for row in measured], "exit_code": first["exit_code"]})
        elif len(measured) == 1 and fixtures:
            findings.append({"code": "EQUIVALENT", "shard_id": shard_id, "receipt_ids": [measured[0]["receipt_id"]], "providers": [measured[0]["provider"]], "exit_code": measured[0]["exit_code"], "note": "single measured execution; fixture/readback is shape only"})
    codes = [row["code"] for row in findings]
    blocking = {"MALFORMED", "STALE_SOURCE", "MISSING_SHARD", "ARTIFACT_DRIFT", "CONTRADICTORY_EXIT", "HASH_MISMATCH", "CANCELLED"}
    status = "DIVERGED" if any(code in blocking for code in codes) else "RECONCILED"
    providers_seen = sorted({row["provider"] for row in accepted})
    measured_providers = sorted({row["provider"] for row in accepted if row["measured"]})
    supported_only = sorted({p for p in manifest["providers"] if p not in measured_providers})
    report = {
        "schema_version": RECONCILE_SCHEMA_VERSION,
        "kind": "FEDERATED_RECONCILIATION",
        "engine_version": ENGINE_VERSION,
        "job_id": manifest["job_id"],
        "source_sha": expected_source_sha,
        "status": status,
        "planned_shards": len(wanted),
        "accepted_receipts": len(seen_ids),
        "findings": findings,
        "providers_seen": providers_seen,
        "providers_measured": measured_providers,
        "providers_supported_by_contract_only": supported_only,
        "claim_boundary": {"measured_live_run": bool(measured_providers), "provider_activated_by_this_engine": False, "other_provider_activated": False, "fabricated_url": False, "quota_claimed": False},
    }
    hits = scan_obj(report)
    _require(not any(hits.values()), f"reconciliation secret/PII scan hits {hits}")
    return report


def default_manifest(source_sha):
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "kind": "FEDERATED_JOB_MANIFEST",
        "job_id": "federated-echo-20260828-01",
        "source_sha": source_sha,
        "repository": "woahwhattheheck/commons",
        "tests": ["federated.echo.shard-a", "federated.echo.shard-b"],
        "shard_count": 2,
        "command_template": {"argv": [sys.executable, "-c", "import sys; sys.stdout.write('ok-' + sys.argv[1])", "{shard_id}"], "cwd": ".", "env": {}, "timeout_s": 15, "shell": False},
        "providers": ["local-fixture", "github-actions", "cirrus", "gitlab", "woodpecker", "unknown-lab"],
        "timeout_s": 15,
        "claim_boundary": {"measured_live_run": False, "provider_activated_by_this_engine": False, "other_provider_activated": False, "fabricated_url": False, "quota_claimed": False},
    }


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def dumps(obj):
    return json.dumps(obj, indent=2, sort_keys=True) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("plan", "run-fixture", "validate-receipt", "reconcile"))
    parser.add_argument("--root", default=ROOT)
    parser.add_argument("--manifest")
    parser.add_argument("--receipt", action="append", default=[])
    parser.add_argument("--source-sha")
    parser.add_argument("--shard", type=int, default=0)
    parser.add_argument("--out")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    try:
        if args.command == "plan":
            source_sha = args.source_sha or "0" * 40
            if args.manifest:
                manifest = validate_manifest(load_json(root / args.manifest if not os.path.isabs(args.manifest) else args.manifest))
            else:
                _require(bool(HEX40.fullmatch(source_sha)), "pass --source-sha as 40 hex")
                manifest = default_manifest(source_sha)
                validate_manifest(manifest)
            payload = {"manifest": manifest, "shards": plan_shards(manifest["tests"], manifest["shard_count"])}
        elif args.command == "run-fixture":
            if args.manifest:
                manifest = validate_manifest(load_json(args.manifest))
            else:
                _require(args.source_sha and bool(HEX40.fullmatch(args.source_sha)), "pass --source-sha")
                manifest = default_manifest(args.source_sha)
            payload = run_local_fixture(manifest, args.shard)
        elif args.command == "validate-receipt":
            _require(args.receipt, "pass --receipt")
            payload = [validate_receipt(load_json(path)) for path in args.receipt]
        else:
            _require(args.manifest, "reconcile needs --manifest")
            _require(args.receipt, "reconcile needs --receipt")
            manifest = validate_manifest(load_json(args.manifest))
            receipts = [load_json(path) for path in args.receipt]
            payload = reconcile(manifest, receipts, expected_source_sha=args.source_sha)
        text = dumps(payload)
        if args.out:
            Path(args.out).write_text(text, encoding="utf-8")
        sys.stdout.write(text)
        if isinstance(payload, dict) and payload.get("status") == "DIVERGED":
            return 2
        return 0
    except (FederatedError, OSError, ValueError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"FEDERATED CI INVALID: {exc}\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
