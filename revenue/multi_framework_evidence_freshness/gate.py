from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = "commons.multi-framework-evidence-freshness/v1"
PACKET_SCHEMA = "commons.multi-framework-evidence-freshness-packet/v1"
STATES = ("REUSABLE", "STALE", "SCOPE_MISMATCH", "MISSING_OWNER", "INCOMPLETE")
FRAMEWORKS = ("SOC2", "ISO27001", "HITRUST", "PCI-DSS")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+-]{0,159}$")
_CONTROL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+-]{0,79}$")
_MAX_ROWS = 10_000
_MAX_CONTROLS = 2_000


class GateError(ValueError):
    pass


def _pairs_hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise GateError(f"duplicate_json_key:{key}")
        out[key] = value
    return out


def _read_bounded_regular(path: str | Path, max_bytes: int) -> bytes:
    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_NONBLOCK"):
        flags |= os.O_NONBLOCK
    fd = os.open(Path(path), flags)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise GateError("input_not_regular")
        if before.st_size > max_bytes:
            raise GateError("input_too_large")
        out = bytearray()
        while True:
            remaining = max_bytes + 1 - len(out)
            if remaining <= 0:
                raise GateError("input_too_large")
            chunk = os.read(fd, min(65536, remaining))
            if not chunk:
                break
            out.extend(chunk)
            if len(out) > max_bytes:
                raise GateError("input_too_large")
        after = os.fstat(fd)
        identity_before = (before.st_dev, before.st_ino, before.st_size, getattr(before, "st_mtime_ns", None))
        identity_after = (after.st_dev, after.st_ino, after.st_size, getattr(after, "st_mtime_ns", None))
        if identity_before != identity_after or after.st_size != len(out):
            raise GateError("input_changed_during_read")
        return bytes(out)
    finally:
        os.close(fd)


def load_strict_json(path: str | Path, *, max_bytes: int = 4_000_000) -> Any:
    if type(max_bytes) is not int or max_bytes < 1:
        raise GateError("max_bytes:positive_integer_required")
    data = _read_bounded_regular(path, max_bytes)
    try:
        text = data.decode("utf-8", "strict")
    except UnicodeDecodeError as exc:
        raise GateError("invalid_utf8") from exc
    if text.startswith("\ufeff"):
        raise GateError("bom_forbidden")
    try:
        return json.loads(
            text,
            object_pairs_hook=_pairs_hook,
            parse_constant=lambda token: (_ for _ in ()).throw(GateError(f"non_finite:{token}")),
        )
    except json.JSONDecodeError as exc:
        raise GateError(f"invalid_json:{exc.msg}") from exc


def _canon(obj: Any) -> bytes:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha(obj: Any) -> str:
    return hashlib.sha256(_canon(obj)).hexdigest()


def _exact(obj: Any, keys: set[str], where: str) -> None:
    if type(obj) is not dict:
        raise GateError(f"{where}:object_required")
    got = set(obj)
    if got != keys:
        raise GateError(f"{where}:keys:missing={sorted(keys-got)}:extra={sorted(got-keys)}")


def _text(value: Any, where: str, *, max_len: int = 160, allow_empty: bool = False) -> str:
    if type(value) is not str:
        raise GateError(f"{where}:string_required")
    if len(value) > max_len or (not allow_empty and not value):
        raise GateError(f"{where}:bad_length")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise GateError(f"{where}:control_char")
    return value


def _ref(value: Any, where: str, *, allow_empty: bool = False) -> str:
    text = _text(value, where, allow_empty=allow_empty)
    if allow_empty and text == "":
        return text
    if not _REF_RE.fullmatch(text):
        raise GateError(f"{where}:bad_ref")
    low = text.lower()
    if any(marker in low for marker in ("password", "passwd", "secret", "api_key", "apikey", "bearer", "token=")):
        raise GateError(f"{where}:secret_shaped")
    return text


def _sha256(value: Any, where: str, *, allow_empty: bool = False) -> str:
    text = _text(value, where, max_len=64, allow_empty=allow_empty)
    if allow_empty and text == "":
        return text
    if not _SHA256_RE.fullmatch(text):
        raise GateError(f"{where}:bad_sha256")
    return text


def _utc(value: Any, where: str) -> datetime:
    text = _text(value, where, max_len=20)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", text):
        raise GateError(f"{where}:canonical_utc_required")
    try:
        dt = datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise GateError(f"{where}:invalid_utc") from exc
    if dt.strftime("%Y-%m-%dT%H:%M:%SZ") != text:
        raise GateError(f"{where}:noncanonical_utc")
    return dt


def _utc_text(dt: datetime) -> str:
    if dt.tzinfo is None:
        raise GateError("trusted_as_of:timezone_required")
    return dt.astimezone(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _int(value: Any, where: str, *, lo: int, hi: int) -> int:
    if type(value) is not int or not (lo <= value <= hi):
        raise GateError(f"{where}:integer_range")
    return value


def _normalize_input(raw: Any) -> dict[str, Any]:
    _exact(raw, {"schema", "assessment", "freshness_policy", "evidence"}, "root")
    if raw["schema"] != SCHEMA:
        raise GateError("root:schema")
    assessment = raw["assessment"]
    _exact(assessment, {"assessment_id", "period_start", "period_end", "scope"}, "assessment")
    assessment_id = _ref(assessment["assessment_id"], "assessment.assessment_id")
    period_start = _utc(assessment["period_start"], "assessment.period_start")
    period_end = _utc(assessment["period_end"], "assessment.period_end")
    if period_end < period_start:
        raise GateError("assessment:period_order")
    scope = assessment["scope"]
    if type(scope) is not list or not scope or len(scope) > _MAX_CONTROLS:
        raise GateError("assessment.scope:bounds")
    normalized_scope: list[dict[str, str]] = []
    seen_scope: set[tuple[str, str]] = set()
    for i, row in enumerate(scope):
        _exact(row, {"framework", "control"}, f"assessment.scope[{i}]")
        framework = _text(row["framework"], f"assessment.scope[{i}].framework", max_len=16)
        if framework not in FRAMEWORKS:
            raise GateError(f"assessment.scope[{i}].framework:unsupported")
        control = _text(row["control"], f"assessment.scope[{i}].control", max_len=80)
        if not _CONTROL_RE.fullmatch(control):
            raise GateError(f"assessment.scope[{i}].control:bad_control")
        key = (framework, control)
        if key in seen_scope:
            raise GateError("assessment.scope:duplicate")
        seen_scope.add(key)
        normalized_scope.append({"framework": framework, "control": control})
    normalized_scope.sort(key=lambda x: (x["framework"], x["control"]))
    policy = raw["freshness_policy"]
    _exact(policy, {"rule_id", "max_age_days"}, "freshness_policy")
    rule_id = _ref(policy["rule_id"], "freshness_policy.rule_id")
    max_age_days = _int(policy["max_age_days"], "freshness_policy.max_age_days", lo=0, hi=3650)
    evidence = raw["evidence"]
    if type(evidence) is not list or len(evidence) > _MAX_ROWS:
        raise GateError("evidence:bounds")
    normalized_rows: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for i, row in enumerate(evidence):
        where = f"evidence[{i}]"
        _exact(row, {"evidence_id", "owner_ref", "collected_at", "coverage_start", "coverage_end", "mappings", "checksum_sha256", "freshness_rule_id", "source_ref"}, where)
        eid = _ref(row["evidence_id"], f"{where}.evidence_id")
        if eid in seen_ids:
            raise GateError(f"{where}.evidence_id:duplicate")
        seen_ids.add(eid)
        owner_ref = _ref(row["owner_ref"], f"{where}.owner_ref", allow_empty=True)
        collected_at = _utc(row["collected_at"], f"{where}.collected_at")
        coverage_start = _utc(row["coverage_start"], f"{where}.coverage_start")
        coverage_end = _utc(row["coverage_end"], f"{where}.coverage_end")
        if coverage_end < coverage_start:
            raise GateError(f"{where}:coverage_order")
        mappings = row["mappings"]
        if type(mappings) is not list or len(mappings) > 64:
            raise GateError(f"{where}.mappings:bounds")
        norm_map: list[dict[str, str]] = []
        seen_map: set[tuple[str, str]] = set()
        for j, mapping in enumerate(mappings):
            mwhere = f"{where}.mappings[{j}]"
            _exact(mapping, {"framework", "control"}, mwhere)
            framework = _text(mapping["framework"], f"{mwhere}.framework", max_len=16)
            control = _text(mapping["control"], f"{mwhere}.control", max_len=80)
            if framework not in FRAMEWORKS or not _CONTROL_RE.fullmatch(control):
                raise GateError(f"{mwhere}:bad_mapping")
            key = (framework, control)
            if key in seen_map:
                raise GateError(f"{where}.mappings:duplicate")
            seen_map.add(key)
            norm_map.append({"framework": framework, "control": control})
        norm_map.sort(key=lambda x: (x["framework"], x["control"]))
        normalized_rows.append({
            "evidence_id": eid,
            "owner_ref": owner_ref,
            "collected_at": _utc_text(collected_at),
            "coverage_start": _utc_text(coverage_start),
            "coverage_end": _utc_text(coverage_end),
            "mappings": norm_map,
            "checksum_sha256": _sha256(row["checksum_sha256"], f"{where}.checksum_sha256", allow_empty=True),
            "freshness_rule_id": _ref(row["freshness_rule_id"], f"{where}.freshness_rule_id", allow_empty=True),
            "source_ref": _ref(row["source_ref"], f"{where}.source_ref", allow_empty=True),
        })
    normalized_rows.sort(key=lambda x: x["evidence_id"])
    return {"schema": SCHEMA, "assessment": {"assessment_id": assessment_id, "period_start": _utc_text(period_start), "period_end": _utc_text(period_end), "scope": normalized_scope}, "freshness_policy": {"rule_id": rule_id, "max_age_days": max_age_days}, "evidence": normalized_rows}


def _classify(row: dict[str, Any], normalized: dict[str, Any], as_of: datetime) -> tuple[str, list[str]]:
    reasons: list[str] = []
    policy = normalized["freshness_policy"]
    assessment = normalized["assessment"]
    scope = {(x["framework"], x["control"]) for x in assessment["scope"]}
    collected = _utc(row["collected_at"], "row.collected_at")
    coverage_start = _utc(row["coverage_start"], "row.coverage_start")
    coverage_end = _utc(row["coverage_end"], "row.coverage_end")
    period_start = _utc(assessment["period_start"], "assessment.period_start")
    period_end = _utc(assessment["period_end"], "assessment.period_end")
    incomplete = False
    if not row["checksum_sha256"]:
        reasons.append("MISSING_CHECKSUM"); incomplete = True
    if not row["source_ref"]:
        reasons.append("MISSING_SOURCE_REF"); incomplete = True
    if not row["freshness_rule_id"]:
        reasons.append("MISSING_FRESHNESS_RULE"); incomplete = True
    elif row["freshness_rule_id"] != policy["rule_id"]:
        reasons.append("FRESHNESS_RULE_MISMATCH"); incomplete = True
    if not row["mappings"]:
        reasons.append("MISSING_FRAMEWORK_CONTROL_MAPPING"); incomplete = True
    if collected > as_of:
        reasons.append("FUTURE_COLLECTION"); incomplete = True
    if coverage_end > collected or coverage_end > as_of:
        reasons.append("FUTURE_COVERAGE"); incomplete = True
    if incomplete:
        return "INCOMPLETE", sorted(set(reasons))
    if not row["owner_ref"]:
        return "MISSING_OWNER", ["MISSING_OWNER"]
    mapped = {(x["framework"], x["control"]) for x in row["mappings"]}
    if not mapped.issubset(scope):
        reasons.append("MAPPING_OUTSIDE_ASSESSMENT_SCOPE")
    if coverage_start > period_start or coverage_end < period_end:
        reasons.append("ASSESSMENT_PERIOD_NOT_COVERED")
    if reasons:
        return "SCOPE_MISMATCH", sorted(reasons)
    age_seconds = int((as_of - collected).total_seconds())
    if age_seconds > policy["max_age_days"] * 86400:
        return "STALE", ["FRESHNESS_WINDOW_EXCEEDED"]
    return "REUSABLE", []


def render_markdown(packet: dict[str, Any]) -> str:
    counts = packet["counts"]
    lines = ["# Multi-Framework Evidence Freshness Review", "", f"Assessment: `{packet['assessment_id']}`", f"Evaluated at: `{packet['evaluated_at']}`", "", "## Classification counts", ""]
    for state in STATES:
        lines.append(f"- {state}: **{counts[state]}**")
    lines += ["", "## Authority boundary", "", "This is read-only pre-assessment QA. REUSABLE means only that the supplied evidence is complete, in declared scope/period, mapped, checksum-bound, owner-attributed, and current under the supplied freshness rule at the packet evaluation instant. It is not an audit opinion, certification, control-effectiveness conclusion, or independence-sensitive recommendation.", "", "## Non-reusable evidence", ""]
    non_reusable = [r for r in packet["results"] if r["state"] != "REUSABLE"]
    if not non_reusable:
        lines.append("None.")
    else:
        for row in non_reusable:
            lines.append(f"- `{row['evidence_id']}` — **{row['state']}** — {', '.join(row['reasons']) or 'none'}")
    return "\n".join(lines) + "\n"


def _compile_packet_at(raw: Any, as_of: datetime) -> dict[str, Any]:
    normalized = _normalize_input(raw)
    if as_of.tzinfo is None:
        raise GateError("trusted_as_of:timezone_required")
    as_of = as_of.astimezone(timezone.utc).replace(microsecond=0)
    results: list[dict[str, Any]] = []
    counts = {state: 0 for state in STATES}
    for row in normalized["evidence"]:
        state, reasons = _classify(row, normalized, as_of)
        counts[state] += 1
        results.append({"evidence_id": row["evidence_id"], "state": state, "reasons": reasons, "source_trace": {"source_ref": row["source_ref"], "fields": {"owner": "owner_ref", "collection_time": "collected_at", "assessment_period_coverage": ["coverage_start", "coverage_end"], "framework_control_mapping": "mappings", "checksum": "checksum_sha256", "freshness_rule": "freshness_rule_id"}, "checksum_sha256": row["checksum_sha256"]}})
    results.sort(key=lambda x: x["evidence_id"])
    base = {"schema": PACKET_SCHEMA, "assessment_id": normalized["assessment"]["assessment_id"], "evaluated_at": _utc_text(as_of), "input": normalized, "input_sha256": _sha(normalized), "counts": counts, "results": results, "authority": {"audit_opinion": False, "certification_opinion": False, "control_effectiveness_rating": False, "evidence_mutation": False, "customer_contact": False, "provider_mutation": False, "payment": False, "revenue_recognition": False}}
    projection = {k: v for k, v in base.items() if k != "input"}
    base["projection_sha256"] = _sha(projection)
    base["markdown_sha256"] = hashlib.sha256(render_markdown(base).encode("utf-8")).hexdigest()
    base["receipt_sha256"] = _sha(base)
    return base


def compile_packet(raw: Any) -> dict[str, Any]:
    """Compile a production packet using process-owned current UTC."""
    return _compile_packet_at(raw, _now_utc())


def _validate_packet_shape(packet: Any) -> datetime:
    if type(packet) is not dict or packet.get("schema") != PACKET_SCHEMA:
        raise GateError("packet:schema")
    _exact(packet, {"schema", "assessment_id", "evaluated_at", "input", "input_sha256", "counts", "results", "authority", "projection_sha256", "markdown_sha256", "receipt_sha256"}, "packet")
    for key in ("input_sha256", "projection_sha256", "markdown_sha256", "receipt_sha256"):
        _sha256(packet[key], f"packet.{key}")
    return _utc(packet["evaluated_at"], "packet.evaluated_at")


def _verify_integrity(packet: Any) -> bool:
    evaluated = _validate_packet_shape(packet)
    rebuilt = _compile_packet_at(packet["input"], evaluated)
    if _canon(rebuilt) != _canon(packet):
        raise GateError("packet:recompile_mismatch")
    return True


def _verify_packet_at(packet: Any, now: datetime) -> bool:
    _verify_integrity(packet)
    if now.tzinfo is None:
        raise GateError("trusted_now:timezone_required")
    now = now.astimezone(timezone.utc).replace(microsecond=0)
    evaluated = _utc(packet["evaluated_at"], "packet.evaluated_at")
    if evaluated > now:
        raise GateError("packet:future_evaluation")
    current = _compile_packet_at(packet["input"], now)
    if current["counts"] != packet["counts"] or current["results"] != packet["results"]:
        raise GateError("packet:not_current")
    return True


def verify_packet(packet: Any) -> bool:
    """Verify integrity and that the packet's classification is still current now."""
    return _verify_packet_at(packet, _now_utc())
