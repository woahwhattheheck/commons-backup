"""Deterministic, execution-free agent capability and constraint registry."""
from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

INPUT_SCHEMA = "agent-capability-constraint-registry/input/v1"
RESULT_SCHEMA = "agent-capability-constraint-registry/result/v1"
RECEIPT_SCHEMA = "agent-capability-constraint-registry/receipt/v1"
VALID_STATUSES = ("READY", "TOOLING_NEEDED", "OWNER_DECISION", "HOLD")
OWNER_VERDICTS = {"APPROVED", "PENDING", "DENIED", "NOT_REQUIRED"}
CAPABILITY_CONDITIONS = {"PASS", "PARTIAL", "FAIL"}
_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,127}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_TS = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


class RegistryError(ValueError):
    """Fail-closed registry validation or verification error."""


@dataclass(frozen=True)
class CompiledRegistry:
    result: dict[str, Any]
    result_bytes: bytes
    markdown_bytes: bytes
    receipt: dict[str, Any]
    receipt_bytes: bytes


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in items:
        if key in out:
            raise RegistryError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def _bad_number(value: str) -> None:
    raise RegistryError(f"non-finite JSON number forbidden: {value}")


def _bad_float(value: str) -> None:
    raise RegistryError(f"floating-point JSON number forbidden: {value}")


def load_json_bytes(raw: bytes, label: str = "input") -> dict[str, Any]:
    if not isinstance(raw, (bytes, bytearray)):
        raise RegistryError(f"{label}: bytes required")
    if bytes(raw).startswith(b"\xef\xbb\xbf"):
        raise RegistryError(f"{label}: UTF-8 BOM forbidden")
    try:
        text = bytes(raw).decode("utf-8", errors="strict")
        value = json.loads(text, object_pairs_hook=_pairs, parse_constant=_bad_number, parse_float=_bad_float)
    except RegistryError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise RegistryError(f"{label}: invalid JSON/UTF-8") from exc
    if not isinstance(value, dict):
        raise RegistryError(f"{label}: top level must be an object")
    return value


def _json(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _keys(obj: Any, expected: set[str], where: str) -> dict[str, Any]:
    if not isinstance(obj, dict):
        raise RegistryError(f"{where}: object required")
    got = set(obj)
    if got != expected:
        raise RegistryError(f"{where}: keys mismatch missing={sorted(expected-got)} extra={sorted(got-expected)}")
    return obj


def _str(value: Any, where: str, *, token: bool = False, limit: int = 512) -> str:
    if not isinstance(value, str) or not value or len(value) > limit or any(ord(ch) < 32 for ch in value):
        raise RegistryError(f"{where}: non-empty safe string <= {limit} chars required")
    if token and not _TOKEN.fullmatch(value):
        raise RegistryError(f"{where}: invalid token")
    return value


def _int(value: Any, where: str, lo: int = 0, hi: int = 10**9) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise RegistryError(f"{where}: integer required (bool forbidden)")
    if not lo <= value <= hi:
        raise RegistryError(f"{where}: integer out of range")
    return value


def _bool(value: Any, where: str) -> bool:
    if not isinstance(value, bool):
        raise RegistryError(f"{where}: boolean required")
    return value


def _sha(value: Any, where: str) -> str:
    value = _str(value, where, limit=64)
    if not _SHA.fullmatch(value):
        raise RegistryError(f"{where}: lowercase sha256 required")
    return value


def _dt(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _ts(value: Any, where: str) -> str:
    value = _str(value, where, limit=20)
    try:
        if not _TS.fullmatch(value):
            raise ValueError
        _dt(value)
    except ValueError as exc:
        raise RegistryError(f"{where}: RFC3339 UTC second timestamp required") from exc
    return value


def _fresh(observed: str, generated: str, max_age: int, where: str) -> None:
    age = int((_dt(generated) - _dt(observed)).total_seconds())
    if age < 0:
        raise RegistryError(f"{where}: evidence timestamp is in the future")
    if age > max_age:
        raise RegistryError(f"{where}: stale evidence age {age}s exceeds {max_age}s freshness window")


def _str_list(value: Any, where: str, limit: int = 64) -> list[str]:
    if not isinstance(value, list) or len(value) > limit:
        raise RegistryError(f"{where}: list with <= {limit} items required")
    out = [_str(item, f"{where}[{idx}]", token=True) for idx, item in enumerate(value)]
    if len(out) != len(set(out)):
        raise RegistryError(f"{where}: duplicate item")
    return sorted(out)


def _cap(value: Any, where: str) -> dict[str, Any]:
    value = _keys(value, {"capability", "evidence_ref", "evidence_sha256", "measured_at", "condition"}, where)
    condition = _str(value["condition"], f"{where}.condition", token=True)
    if condition not in CAPABILITY_CONDITIONS:
        raise RegistryError(f"{where}.condition: invalid value")
    return {
        "capability": _str(value["capability"], f"{where}.capability", token=True),
        "condition": condition,
        "evidence_ref": _str(value["evidence_ref"], f"{where}.evidence_ref"),
        "evidence_sha256": _sha(value["evidence_sha256"], f"{where}.evidence_sha256"),
        "measured_at": _ts(value["measured_at"], f"{where}.measured_at"),
    }


def _constraint(value: Any, where: str) -> dict[str, Any]:
    value = _keys(value, {"constraint", "source_ref", "source_sha256", "source_ts", "tooling_need", "owner_verdict", "estimated_fix_minutes"}, where)
    verdict = _str(value["owner_verdict"], f"{where}.owner_verdict", token=True)
    if verdict not in OWNER_VERDICTS:
        raise RegistryError(f"{where}.owner_verdict: invalid value")
    return {
        "constraint": _str(value["constraint"], f"{where}.constraint", token=True),
        "estimated_fix_minutes": _int(value["estimated_fix_minutes"], f"{where}.estimated_fix_minutes", 0, 525600),
        "owner_verdict": verdict,
        "source_ref": _str(value["source_ref"], f"{where}.source_ref"),
        "source_sha256": _sha(value["source_sha256"], f"{where}.source_sha256"),
        "source_ts": _ts(value["source_ts"], f"{where}.source_ts"),
        "tooling_need": _str(value["tooling_need"], f"{where}.tooling_need", token=True),
    }


def _record(value: Any, idx: int) -> dict[str, Any]:
    where = f"records[{idx}]"
    value = _keys(value, {"agent_id", "workstream", "provider", "model_or_harness", "revision", "measured_capabilities", "declared_constraints", "required_tools", "available_tools", "owner_decision", "blocking_reasons", "execution_requested"}, where)
    caps_raw = value["measured_capabilities"]
    cons_raw = value["declared_constraints"]
    if not isinstance(caps_raw, list) or not 1 <= len(caps_raw) <= 128:
        raise RegistryError(f"{where}.measured_capabilities: 1..128 items required")
    if not isinstance(cons_raw, list) or len(cons_raw) > 128:
        raise RegistryError(f"{where}.declared_constraints: <=128 items required")
    caps = [_cap(item, f"{where}.measured_capabilities[{i}]") for i, item in enumerate(caps_raw)]
    cons = [_constraint(item, f"{where}.declared_constraints[{i}]") for i, item in enumerate(cons_raw)]
    if len({x["capability"] for x in caps}) != len(caps):
        raise RegistryError(f"{where}.measured_capabilities: duplicate capability")
    if len({x["constraint"] for x in cons}) != len(cons):
        raise RegistryError(f"{where}.declared_constraints: duplicate constraint")
    owner = _str(value["owner_decision"], f"{where}.owner_decision", token=True)
    if owner not in OWNER_VERDICTS:
        raise RegistryError(f"{where}.owner_decision: invalid value")
    return {
        "agent_id": _str(value["agent_id"], f"{where}.agent_id", token=True),
        "available_tools": _str_list(value["available_tools"], f"{where}.available_tools"),
        "blocking_reasons": _str_list(value["blocking_reasons"], f"{where}.blocking_reasons"),
        "declared_constraints": sorted(cons, key=lambda x: x["constraint"]),
        "execution_requested": _bool(value["execution_requested"], f"{where}.execution_requested"),
        "measured_capabilities": sorted(caps, key=lambda x: x["capability"]),
        "model_or_harness": _str(value["model_or_harness"], f"{where}.model_or_harness", token=True),
        "owner_decision": owner,
        "provider": _str(value["provider"], f"{where}.provider", token=True),
        "required_tools": _str_list(value["required_tools"], f"{where}.required_tools"),
        "revision": _int(value["revision"], f"{where}.revision", 1, 10**6),
        "workstream": _str(value["workstream"], f"{where}.workstream", token=True),
    }


def normalize_input(value: dict[str, Any]) -> dict[str, Any]:
    value = _keys(value, {"schema", "registry_id", "snapshot_ref", "snapshot_sha256", "generated_at", "evidence_max_age_seconds", "records"}, "input")
    if value["schema"] != INPUT_SCHEMA:
        raise RegistryError("input.schema: unsupported schema")
    raw = value["records"]
    if not isinstance(raw, list) or not 1 <= len(raw) <= 4096:
        raise RegistryError("input.records: 1..4096 items required")
    generated = _ts(value["generated_at"], "input.generated_at")
    max_age = _int(value["evidence_max_age_seconds"], "input.evidence_max_age_seconds", 1, 31536000)
    records = [_record(item, i) for i, item in enumerate(raw)]
    seen: set[tuple[str, int]] = set()
    for rec in records:
        ident = (rec["agent_id"], rec["revision"])
        if ident in seen:
            raise RegistryError(f"input.records: duplicate agent/revision identity {ident[0]}@{ident[1]}")
        seen.add(ident)
        for cap in rec["measured_capabilities"]:
            _fresh(cap["measured_at"], generated, max_age, f"input.records[{rec['agent_id']}].measured_capabilities[{cap['capability']}].measured_at")
        for con in rec["declared_constraints"]:
            _fresh(con["source_ts"], generated, max_age, f"input.records[{rec['agent_id']}].declared_constraints[{con['constraint']}].source_ts")
    return {
        "evidence_max_age_seconds": max_age,
        "generated_at": generated,
        "records": sorted(records, key=lambda x: (x["workstream"], x["agent_id"], x["revision"])),
        "registry_id": _str(value["registry_id"], "input.registry_id", token=True),
        "schema": INPUT_SCHEMA,
        "snapshot_ref": _str(value["snapshot_ref"], "input.snapshot_ref"),
        "snapshot_sha256": _sha(value["snapshot_sha256"], "input.snapshot_sha256"),
    }


def _classify(rec: dict[str, Any]) -> tuple[str, list[str], list[str]]:
    missing = sorted(set(rec["required_tools"]) - set(rec["available_tools"]))
    reasons: list[str] = []
    if rec["execution_requested"]:
        reasons.append("EXECUTION_REQUESTED_OUTSIDE_REGISTRY_AUTHORITY")
    reasons += [f"BLOCK:{x}" for x in rec["blocking_reasons"]]
    reasons += [f"CAPABILITY_FAIL:{x['capability']}" for x in rec["measured_capabilities"] if x["condition"] == "FAIL"]
    reasons += [f"CONSTRAINT_DENIED:{x['constraint']}" for x in rec["declared_constraints"] if x["owner_verdict"] == "DENIED"]
    if reasons or rec["owner_decision"] == "DENIED":
        return "HOLD", sorted(reasons or ["OWNER_DENIED"]), missing
    pending = [x["constraint"] for x in rec["declared_constraints"] if x["owner_verdict"] == "PENDING"]
    if rec["owner_decision"] == "PENDING" or pending:
        return "OWNER_DECISION", sorted(["OWNER_DECISION_PENDING"] + [f"CONSTRAINT_PENDING:{x}" for x in pending]), missing
    needs = [x["tooling_need"] for x in rec["declared_constraints"] if x["tooling_need"] != "NONE"]
    if missing or needs:
        return "TOOLING_NEEDED", sorted([f"MISSING_TOOL:{x}" for x in missing] + [f"TOOLING_CONSTRAINT:{x}" for x in needs]), missing
    return "READY", [], []


def _project(rec: dict[str, Any]) -> dict[str, Any]:
    status, reasons, missing = _classify(rec)
    return {**deepcopy(rec), "missing_tools": missing, "status": status, "status_reasons": reasons}


def _md(value: str) -> str:
    return value.replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ")


def render_markdown(result: dict[str, Any]) -> bytes:
    lines = [
        "# Agent Capability & Constraint Registry", "",
        f"- Registry: `{_md(result['registry_id'])}`",
        f"- Generated at: `{result['generated_at']}`",
        f"- Evidence freshness window: `{result['evidence_max_age_seconds']}` seconds",
        f"- Snapshot: `{_md(result['snapshot_ref'])}` / `{result['snapshot_sha256']}`",
        f"- Input SHA-256: `{result['input_sha256']}`",
        "- Authority: **observational only; no execution, deployment, access, spend, messaging, or model-selection authority**", "",
        "| Workstream | Agent | Rev | Provider | Model/Harness | Status | Reasons |",
        "|---|---|---:|---|---|---|---|",
    ]
    for rec in result["records"]:
        reasons = ", ".join(rec["status_reasons"]) or "—"
        lines.append("| " + " | ".join((_md(rec["workstream"]), _md(rec["agent_id"]), str(rec["revision"]), _md(rec["provider"]), _md(rec["model_or_harness"]), rec["status"], _md(reasons))) + " |")
    lines += ["", "## Counts", ""] + [f"- `{status}`: {result['counts'][status]}" for status in VALID_STATUSES]
    lines += ["", "## Non-authority boundary", "", "This projection is an evidence-backed census. A `READY` row means only that the declared registry conditions are internally satisfied. It is **not** permission to run, deploy, call a tool, access data, message anyone, spend money, or change external state.", ""]
    return "\n".join(lines).encode()


def compile_registry(value: dict[str, Any]) -> CompiledRegistry:
    source = normalize_input(value)
    input_sha = _digest(_json(source))
    records = [_project(x) for x in source["records"]]
    counts = {status: sum(x["status"] == status for x in records) for status in VALID_STATUSES}
    result = {
        "authority": {key: False for key in ("access_elevation", "deployment", "external_effects", "messaging", "model_selection", "spending", "tool_execution")},
        "counts": counts,
        "evidence_max_age_seconds": source["evidence_max_age_seconds"],
        "generated_at": source["generated_at"],
        "input_sha256": input_sha,
        "records": records,
        "registry_id": source["registry_id"],
        "schema": RESULT_SCHEMA,
        "snapshot_ref": source["snapshot_ref"],
        "snapshot_sha256": source["snapshot_sha256"],
    }
    result_raw = _json(result)
    markdown_raw = render_markdown(result)
    base = {"authority": "OBSERVATIONAL_ONLY", "input_sha256": input_sha, "markdown_sha256": _digest(markdown_raw), "record_count": len(records), "registry_id": source["registry_id"], "result_sha256": _digest(result_raw), "schema": RECEIPT_SCHEMA}
    receipt = {**base, "receipt_sha256": _digest(_json(base))}
    return CompiledRegistry(result, result_raw, markdown_raw, receipt, _json(receipt))


def verify_compiled(source: dict[str, Any], result_raw: bytes, markdown_raw: bytes, receipt_raw: bytes) -> dict[str, Any]:
    expected = compile_registry(source)
    result = load_json_bytes(result_raw, "result")
    receipt = load_json_bytes(receipt_raw, "receipt")
    if result.get("schema") != RESULT_SCHEMA or receipt.get("schema") != RECEIPT_SCHEMA:
        raise RegistryError("result/receipt: unsupported schema")
    if result_raw != expected.result_bytes:
        raise RegistryError("result: bytes or semantics do not match deterministic recompile")
    if markdown_raw != expected.markdown_bytes:
        raise RegistryError("markdown: bytes do not match deterministic recompile")
    if receipt_raw != expected.receipt_bytes:
        raise RegistryError("receipt: bytes or commitments do not match deterministic recompile")
    base = dict(receipt)
    claimed = base.pop("receipt_sha256", None)
    if claimed != _digest(_json(base)):
        raise RegistryError("receipt: self commitment mismatch")
    return {"counts": expected.result["counts"], "input_sha256": expected.result["input_sha256"], "markdown_sha256": expected.receipt["markdown_sha256"], "receipt_sha256": expected.receipt["receipt_sha256"], "result_sha256": expected.receipt["result_sha256"], "verified": True}


def write_compiled(source: dict[str, Any], out_dir: str | Path) -> CompiledRegistry:
    dest = Path(out_dir)
    if dest.exists():
        raise RegistryError(f"output directory already exists: {dest}")
    compiled = compile_registry(source)
    dest.mkdir(parents=True, exist_ok=False)
    try:
        (dest / "registry.json").write_bytes(compiled.result_bytes)
        (dest / "registry.md").write_bytes(compiled.markdown_bytes)
        (dest / "receipt.json").write_bytes(compiled.receipt_bytes)
    except Exception:
        for child in dest.iterdir():
            child.unlink(missing_ok=True)
        dest.rmdir()
        raise
    return compiled
