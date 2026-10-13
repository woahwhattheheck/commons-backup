#!/usr/bin/env python3
"""Deterministic external-readiness compiler for the TurnBench hackathon submission.

This module intentionally does not contact lablab.ai, AssemblyAI, a deployment provider,
or a submission portal. It consumes retained evidence references and can only conclude
that the packet is ready for OWNER submission action. It never emits SUBMITTED.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Mapping

SCHEMA = "turnbench-submission-readiness/v1"
PROJECT_ID = "turnbench"
EVENT_ID = "assemblyai-voice-agent-hackathon-2026"
TURNBENCH_SOURCE_COMMIT = "aa879e2b6077a86752219a9f76ef64beaf5e701c"
EVENT_START = datetime(2026, 9, 1, tzinfo=timezone.utc)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,255}$")
MAX_BYTES = 512_000
MAX_DEPTH = 12
MAX_NODES = 2_000

GATE_SPECS = {
    "registration": {
        "source_kind": "LABLAB_REGISTRATION_RECEIPT",
        "issuer": "lablab.ai",
        "max_age": timedelta(days=31),
        "facts": {"registration_state": "REGISTERED", "team_id": None},
    },
    "public_deployment": {
        "source_kind": "PUBLIC_DEPLOYMENT_RECEIPT",
        "issuer": None,
        "max_age": timedelta(days=7),
        "facts": {"deployment_state": "LIVE", "public_url": None, "deploy_sha256": None},
    },
    "live_assemblyai": {
        "source_kind": "ASSEMBLYAI_LIVE_SESSION_RECEIPT",
        "issuer": "assemblyai.com",
        "max_age": timedelta(days=7),
        "facts": {"session_state": "COMPLETED", "turnbench_result": "PASS", "turnbench_receipt_sha256": None},
    },
    "presentation_assets": {
        "source_kind": "OWNER_RETAINED_PRESENTATION_ASSETS",
        "issuer": "owner-retained",
        "max_age": timedelta(days=7),
        "facts": {"presentation_state": "READY", "narrative_sha256": None, "demo_script_sha256": None, "demo_video_sha256": None},
    },
}

AUTHORITY = {
    "external_submission_authorized": False,
    "registration_mutation_authorized": False,
    "provider_account_mutation_authorized": False,
    "deployment_mutation_authorized": False,
    "microphone_capture_authorized": False,
    "prize_or_payment_claim_authorized": False,
    "revenue_recognition_authorized": False,
    "owner_submission_review_required": True,
}
TRUTH_BOUNDARY = "OWNER_RETAINED_EXTERNAL_RECEIPTS_NOT_PROVIDER_AUTHENTICATED_BY_THIS_COMPILER"


class ReadinessError(ValueError):
    pass


def _pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ReadinessError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def loads_strict(raw: bytes | str) -> Any:
    if isinstance(raw, bytes):
        if len(raw) > MAX_BYTES:
            raise ReadinessError("input too large")
        raw = raw.decode("utf-8")
    elif len(raw.encode("utf-8")) > MAX_BYTES:
        raise ReadinessError("input too large")
    obj = json.loads(
        raw,
        object_pairs_hook=_pairs,
        parse_float=lambda _: (_ for _ in ()).throw(ReadinessError("floats forbidden")),
        parse_constant=lambda _: (_ for _ in ()).throw(ReadinessError("non-finite forbidden")),
    )
    _bounded(obj)
    return obj


def _bounded(obj: Any, depth: int = 0, nodes: list[int] | None = None) -> None:
    if nodes is None:
        nodes = [0]
    nodes[0] += 1
    if nodes[0] > MAX_NODES:
        raise ReadinessError("too many JSON nodes")
    if depth > MAX_DEPTH:
        raise ReadinessError("JSON nesting too deep")
    if isinstance(obj, dict):
        for key, value in obj.items():
            if not isinstance(key, str):
                raise ReadinessError("object key must be string")
            _bounded(value, depth + 1, nodes)
    elif isinstance(obj, list):
        for value in obj:
            _bounded(value, depth + 1, nodes)
    elif obj is None or isinstance(obj, (str, int, bool)):
        return
    else:
        raise ReadinessError("unsupported JSON value")


def canonical_bytes(obj: Any) -> bytes:
    return (json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def sha256_obj(obj: Any) -> str:
    return hashlib.sha256(canonical_bytes(obj)).hexdigest()


def _exact(obj: Mapping[str, Any], keys: set[str], where: str) -> None:
    if not isinstance(obj, dict) or set(obj) != keys:
        raise ReadinessError(f"{where}: exact keys required {sorted(keys)}")


def _text(value: Any, where: str, *, safe_id: bool = False) -> str:
    if not isinstance(value, str) or not value or len(value) > 512:
        raise ReadinessError(f"{where}: nonempty bounded string required")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise ReadinessError(f"{where}: control characters forbidden")
    if safe_id and not SAFE_ID_RE.fullmatch(value):
        raise ReadinessError(f"{where}: unsafe identifier")
    return value


def _sha(value: Any, where: str) -> str:
    value = _text(value, where)
    if not SHA256_RE.fullmatch(value):
        raise ReadinessError(f"{where}: lowercase sha256 required")
    return value


def _time(value: Any, where: str) -> datetime:
    value = _text(value, where)
    if not value.endswith("Z"):
        raise ReadinessError(f"{where}: UTC Z timestamp required")
    try:
        dt = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ReadinessError(f"{where}: invalid timestamp") from exc
    if dt.tzinfo is None or dt.utcoffset() != timedelta(0):
        raise ReadinessError(f"{where}: UTC timestamp required")
    return dt.astimezone(timezone.utc)


def _https_url(value: Any, where: str) -> str:
    value = _text(value, where)
    if not value.startswith("https://") or "@" in value.split("/", 3)[2]:
        raise ReadinessError(f"{where}: plain https URL without userinfo required")
    return value


def _validate_facts(gate: str, facts: Any) -> dict[str, Any]:
    spec = GATE_SPECS[gate]
    expected = spec["facts"]
    _exact(facts, set(expected), f"{gate}.facts")
    out = dict(facts)
    for key, literal in expected.items():
        if literal is not None and out[key] != literal:
            raise ReadinessError(f"{gate}.facts.{key}: must be {literal}")
    if gate == "registration":
        _text(out["team_id"], "registration.facts.team_id", safe_id=True)
    elif gate == "public_deployment":
        _https_url(out["public_url"], "public_deployment.facts.public_url")
        _sha(out["deploy_sha256"], "public_deployment.facts.deploy_sha256")
    elif gate == "live_assemblyai":
        _sha(out["turnbench_receipt_sha256"], "live_assemblyai.facts.turnbench_receipt_sha256")
    elif gate == "presentation_assets":
        for key in ("narrative_sha256", "demo_script_sha256", "demo_video_sha256"):
            _sha(out[key], f"presentation_assets.facts.{key}")
    return out


def _validate_evidence(row: Any, evaluation_at: datetime) -> tuple[str, dict[str, Any], str | None]:
    keys = {"gate", "source_kind", "issuer", "project_id", "event_id", "turnbench_source_commit", "observed_at", "evidence_ref", "evidence_sha256", "facts"}
    _exact(row, keys, "evidence")
    gate = _text(row["gate"], "evidence.gate", safe_id=True)
    if gate not in GATE_SPECS:
        raise ReadinessError(f"unknown evidence gate: {gate}")
    spec = GATE_SPECS[gate]
    if row["source_kind"] != spec["source_kind"]:
        raise ReadinessError(f"{gate}: wrong source_kind")
    issuer = _text(row["issuer"], f"{gate}.issuer", safe_id=True)
    if spec["issuer"] is not None and issuer != spec["issuer"]:
        raise ReadinessError(f"{gate}: wrong issuer")
    if row["project_id"] != PROJECT_ID or row["event_id"] != EVENT_ID:
        raise ReadinessError(f"{gate}: cross-project/event evidence")
    if row["turnbench_source_commit"] != TURNBENCH_SOURCE_COMMIT:
        raise ReadinessError(f"{gate}: wrong TurnBench source generation")
    observed = _time(row["observed_at"], f"{gate}.observed_at")
    if observed < EVENT_START:
        raise ReadinessError(f"{gate}: evidence predates event")
    if observed > evaluation_at:
        raise ReadinessError(f"{gate}: future evidence")
    _text(row["evidence_ref"], f"{gate}.evidence_ref", safe_id=True)
    _sha(row["evidence_sha256"], f"{gate}.evidence_sha256")
    facts = _validate_facts(gate, row["facts"])
    stale = evaluation_at - observed > spec["max_age"]
    normalized = {
        "gate": gate,
        "source_kind": row["source_kind"],
        "issuer": issuer,
        "project_id": PROJECT_ID,
        "event_id": EVENT_ID,
        "turnbench_source_commit": TURNBENCH_SOURCE_COMMIT,
        "observed_at": row["observed_at"],
        "evidence_ref": row["evidence_ref"],
        "evidence_sha256": row["evidence_sha256"],
        "facts": facts,
    }
    return gate, normalized, (f"STALE_{gate.upper()}" if stale else None)


def validate_bundle(bundle: Any) -> dict[str, Any]:
    _exact(bundle, {"project_id", "event_id", "source_commit", "evaluation_at", "evidence"}, "bundle")
    if bundle["project_id"] != PROJECT_ID:
        raise ReadinessError("wrong project_id")
    if bundle["event_id"] != EVENT_ID:
        raise ReadinessError("wrong event_id")
    if bundle["source_commit"] != TURNBENCH_SOURCE_COMMIT:
        raise ReadinessError("wrong source_commit")
    evaluation = _time(bundle["evaluation_at"], "evaluation_at")
    if evaluation < EVENT_START:
        raise ReadinessError("evaluation predates event")
    evidence = bundle["evidence"]
    if not isinstance(evidence, list) or len(evidence) > len(GATE_SPECS):
        raise ReadinessError("evidence must be a bounded list")
    seen = {}
    stale = []
    for row in evidence:
        gate, normalized, stale_code = _validate_evidence(row, evaluation)
        if gate in seen:
            raise ReadinessError(f"duplicate evidence gate: {gate}")
        seen[gate] = normalized
        if stale_code:
            stale.append(stale_code)
    return {
        "project_id": PROJECT_ID,
        "event_id": EVENT_ID,
        "source_commit": TURNBENCH_SOURCE_COMMIT,
        "evaluation_at": bundle["evaluation_at"],
        "evidence": [seen[key] for key in sorted(seen)],
        "_stale": sorted(stale),
    }


def compile_readiness(bundle: Any) -> dict[str, Any]:
    normalized = validate_bundle(bundle)
    present = {row["gate"] for row in normalized["evidence"]}
    blockers = list(normalized.pop("_stale"))
    for gate in sorted(GATE_SPECS):
        if gate not in present:
            blockers.append(f"MISSING_{gate.upper()}")
    blockers = sorted(set(blockers))
    state = "READY_FOR_OWNER_SUBMISSION_ACTION" if not blockers else "EXTERNAL_GATES_PENDING"
    packet = {
        "schema": SCHEMA,
        "project_id": PROJECT_ID,
        "event_id": EVENT_ID,
        "turnbench_source_commit": TURNBENCH_SOURCE_COMMIT,
        "evaluation_at": normalized["evaluation_at"],
        "state": state,
        "blockers": blockers,
        "evidence_truth_boundary": TRUTH_BOUNDARY,
        "evidence_bindings": normalized["evidence"],
        "claims": {
            "registration_evidenced": "registration" in present and "STALE_REGISTRATION" not in blockers,
            "public_deployment_evidenced": "public_deployment" in present and "STALE_PUBLIC_DEPLOYMENT" not in blockers,
            "live_assemblyai_session_evidenced": "live_assemblyai" in present and "STALE_LIVE_ASSEMBLYAI" not in blockers,
            "presentation_assets_evidenced": "presentation_assets" in present and "STALE_PRESENTATION_ASSETS" not in blockers,
            "submitted": False,
            "judged": False,
            "prize_awarded": False,
            "payment_received": False,
            "recognized_revenue": False,
        },
        "authority": dict(AUTHORITY),
        "input_sha256": sha256_obj({
            "project_id": normalized["project_id"],
            "event_id": normalized["event_id"],
            "source_commit": normalized["source_commit"],
            "evaluation_at": normalized["evaluation_at"],
            "evidence": normalized["evidence"],
        }),
    }
    packet["receipt_sha256"] = sha256_obj(packet)
    return packet


def verify(bundle: Any, receipt: Any) -> bool:
    if not isinstance(receipt, dict):
        return False
    try:
        expected = compile_readiness(bundle)
    except (ReadinessError, TypeError, ValueError):
        return False
    return canonical_bytes(expected) == canonical_bytes(receipt)


def load_file(path: str | os.PathLike[str]) -> Any:
    p = Path(path)
    if p.is_symlink():
        raise ReadinessError("symlink input forbidden")
    return loads_strict(p.read_bytes())


def _write_exclusive(path: str | os.PathLike[str], obj: Any) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(os.fspath(path), flags, 0o600)
    try:
        data = canonical_bytes(obj)
        with os.fdopen(fd, "wb", closefd=False) as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
    finally:
        os.close(fd)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    cp = sp.add_parser("compile")
    cp.add_argument("--bundle", required=True)
    cp.add_argument("--out", required=True)
    vp = sp.add_parser("verify")
    vp.add_argument("--bundle", required=True)
    vp.add_argument("--receipt", required=True)
    args = ap.parse_args(argv)
    try:
        bundle = load_file(args.bundle)
        if args.cmd == "compile":
            receipt = compile_readiness(bundle)
            _write_exclusive(args.out, receipt)
            print(receipt["state"])
            return 0 if receipt["state"] == "READY_FOR_OWNER_SUBMISSION_ACTION" else 2
        receipt = load_file(args.receipt)
        ok = verify(bundle, receipt)
        print("VERIFIED" if ok else "INVALID")
        return 0 if ok else 2
    except (OSError, ReadinessError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        print(f"HOLD: {exc}")
        return 64


if __name__ == "__main__":
    raise SystemExit(main())
