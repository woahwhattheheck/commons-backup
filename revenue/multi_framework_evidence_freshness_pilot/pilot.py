from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import stat
from pathlib import Path
from typing import Any

from revenue.multi_framework_evidence_freshness import gate

REQUEST_SCHEMA = "commons.multi-framework-evidence-freshness-fixed-diagnostic-request/v1"
DIAGNOSTIC_SCHEMA = "commons.multi-framework-evidence-freshness-fixed-diagnostic/v1"
MAX_EVIDENCE_OBJECTS = 500
FIXED_PRICE_USD = 3500
INTEGRATION_SPRINT_USD = 10000
MAX_JSON_BYTES = 4_000_000
MAX_MARKDOWN_BYTES = 1_000_000
ENGAGEMENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,79}$")
STATES = ("REUSABLE", "STALE", "SCOPE_MISMATCH", "MISSING_OWNER", "INCOMPLETE")


class PilotError(ValueError):
    pass


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise PilotError(f"duplicate_json_key:{key}")
        out[key] = value
    return out


def canonical(obj: Any) -> bytes:
    try:
        return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError, RecursionError) as exc:
        raise PilotError(f"canonicalization_failed:{exc}") from exc


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_obj(obj: Any) -> str:
    return sha256_bytes(canonical(obj))


def _regular_read(path: str | Path, max_bytes: int) -> bytes:
    if type(max_bytes) is not int or max_bytes < 1:
        raise PilotError("max_bytes:positive_integer_required")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(Path(path), flags)
    except OSError as exc:
        raise PilotError(f"input_open_failed:{exc.errno}") from exc
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise PilotError("input_not_regular")
        if before.st_size > max_bytes:
            raise PilotError("input_too_large")
        data = bytearray()
        while True:
            chunk = os.read(fd, min(65536, max_bytes + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
            if len(data) > max_bytes:
                raise PilotError("input_too_large")
        after = os.fstat(fd)
        a = (before.st_dev, before.st_ino, before.st_mode, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
        b = (after.st_dev, after.st_ino, after.st_mode, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
        if a != b or len(data) != after.st_size:
            raise PilotError("input_changed_during_read")
        return bytes(data)
    finally:
        os.close(fd)


def load_json(path: str | Path) -> Any:
    raw = _regular_read(path, MAX_JSON_BYTES)
    try:
        text = raw.decode("utf-8", "strict")
    except UnicodeDecodeError as exc:
        raise PilotError("invalid_utf8") from exc
    if text.startswith("\ufeff"):
        raise PilotError("bom_forbidden")
    try:
        return json.loads(text, object_pairs_hook=_pairs, parse_constant=lambda token: (_ for _ in ()).throw(PilotError(f"non_finite:{token}")))
    except PilotError:
        raise
    except (json.JSONDecodeError, ValueError, RecursionError) as exc:
        raise PilotError(f"invalid_json:{exc}") from exc


def load_markdown(path: str | Path) -> str:
    raw = _regular_read(path, MAX_MARKDOWN_BYTES)
    try:
        return raw.decode("utf-8", "strict")
    except UnicodeDecodeError as exc:
        raise PilotError("invalid_markdown_utf8") from exc


def _exact(obj: Any, keys: set[str], where: str) -> dict[str, Any]:
    if type(obj) is not dict:
        raise PilotError(f"{where}:object_required")
    got = set(obj)
    if got != keys:
        raise PilotError(f"{where}:keys:missing={sorted(keys-got)}:extra={sorted(got-keys)}")
    return obj


def _source_path(module: Any) -> Path:
    raw = getattr(module, "__file__", None)
    if type(raw) is not str or not raw:
        raise PilotError("engine_source_path_unavailable")
    path = Path(raw)
    if path.suffix in {".pyc", ".pyo"}:
        try:
            path = Path(importlib.util.source_from_cache(str(path)))
        except (ValueError, NotImplementedError) as exc:
            raise PilotError("engine_source_path_unavailable") from exc
    return path


def _module_source_sha256(module: Any) -> str:
    path = _source_path(module)
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise PilotError("engine_source_unreadable") from exc
    return sha256_bytes(data)


def _self_source_sha256() -> str:
    try:
        return sha256_bytes(Path(__file__).read_bytes())
    except OSError as exc:
        raise PilotError("pilot_source_unreadable") from exc


def validate_request(raw: Any) -> dict[str, Any]:
    req = _exact(raw, {"schema", "engagement_ref", "sanitized_export_attested", "evidence_input"}, "request")
    if req["schema"] != REQUEST_SCHEMA:
        raise PilotError("request:schema")
    engagement_ref = req["engagement_ref"]
    if type(engagement_ref) is not str or not ENGAGEMENT_RE.fullmatch(engagement_ref):
        raise PilotError("request.engagement_ref:invalid")
    if type(req["sanitized_export_attested"]) is not bool or req["sanitized_export_attested"] is not True:
        raise PilotError("request.sanitized_export_attested:true_required")
    evidence_input = req["evidence_input"]
    if type(evidence_input) is not dict:
        raise PilotError("request.evidence_input:object_required")
    evidence = evidence_input.get("evidence")
    if type(evidence) is not list:
        raise PilotError("request.evidence_input.evidence:list_required")
    if not evidence:
        raise PilotError("request.evidence_input.evidence:at_least_one_required")
    if len(evidence) > MAX_EVIDENCE_OBJECTS:
        raise PilotError("request.evidence_input.evidence:fixed_diagnostic_limit_500")
    return req


def _reason_counts(packet: dict[str, Any]) -> dict[str, int]:
    out: dict[str, int] = {}
    results = packet.get("results")
    if type(results) is not list:
        raise PilotError("engine_packet.results:list_required")
    for row in results:
        if type(row) is not dict:
            raise PilotError("engine_packet.results:row_object_required")
        state = row.get("state")
        if state not in STATES:
            raise PilotError("engine_packet.results:unknown_state")
        reasons = row.get("reasons")
        if type(reasons) is not list:
            raise PilotError("engine_packet.results.reasons:list_required")
        if state != "REUSABLE":
            for reason in reasons:
                if type(reason) is not str or not reason or len(reason) > 120:
                    raise PilotError("engine_packet.results.reasons:invalid")
                out[reason] = out.get(reason, 0) + 1
    return dict(sorted(out.items()))


def _validate_counts(packet: dict[str, Any], object_count: int) -> dict[str, int]:
    counts = packet.get("counts")
    if type(counts) is not dict or set(counts) != set(STATES):
        raise PilotError("engine_packet.counts:shape")
    normalized: dict[str, int] = {}
    for state in STATES:
        value = counts[state]
        if type(value) is not int or value < 0 or value > MAX_EVIDENCE_OBJECTS:
            raise PilotError("engine_packet.counts:value")
        normalized[state] = value
    if sum(normalized.values()) != object_count:
        raise PilotError("engine_packet.counts:total_mismatch")
    return normalized


def _engine_binding(packet: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
    required = {"schema", "evaluated_at", "input", "input_sha256", "projection_sha256", "markdown_sha256", "receipt_sha256"}
    if type(packet) is not dict or not required.issubset(packet):
        raise PilotError("engine_packet:missing_binding_fields")
    for key in ("input_sha256", "projection_sha256", "markdown_sha256", "receipt_sha256"):
        value = packet[key]
        if type(value) is not str or not re.fullmatch(r"[0-9a-f]{64}", value):
            raise PilotError(f"engine_packet.{key}:invalid")
    return {
        "package": "revenue.multi_framework_evidence_freshness.gate",
        "packet_schema": packet["schema"],
        "engine_source_sha256": _module_source_sha256(gate),
        "request_evidence_input_sha256": sha256_obj(request["evidence_input"]),
        "normalized_input_sha256": packet["input_sha256"],
        "packet_sha256": sha256_obj(packet),
        "projection_sha256": packet["projection_sha256"],
        "engine_markdown_sha256": packet["markdown_sha256"],
        "engine_receipt_sha256": packet["receipt_sha256"],
    }


def _diagnostic_core(request: dict[str, Any], packet: dict[str, Any]) -> dict[str, Any]:
    object_count = len(request["evidence_input"]["evidence"])
    counts = _validate_counts(packet, object_count)
    reason_counts = _reason_counts(packet)
    if type(packet.get("evaluated_at")) is not str:
        raise PilotError("engine_packet.evaluated_at:invalid")
    return {
        "schema": DIAGNOSTIC_SCHEMA,
        "engagement_ref": request["engagement_ref"],
        "evaluated_at": packet["evaluated_at"],
        "offer": {
            "fixed_diagnostic_usd": FIXED_PRICE_USD,
            "integration_sprint_usd": INTEGRATION_SPRINT_USD,
            "integration_sprint_condition": "ONLY_AFTER_PAID_DIAGNOSTIC_ESTABLISHES_VALUE_AND_ACTUAL_ADAPTER_SCOPE",
            "commercial_state": "PROPOSED_NOT_ACCEPTED",
            "max_sanitized_evidence_objects": MAX_EVIDENCE_OBJECTS,
            "free_custom_adapter": False,
        },
        "scope": {
            "sanitized_export_attested": True,
            "evidence_object_count": object_count,
        },
        "classification_counts": counts,
        "non_reusable_reason_counts": reason_counts,
        "engine_binding": _engine_binding(packet, request),
        "compiler_source_sha256": _self_source_sha256(),
        "request_sha256": sha256_obj(request),
        "authority": {
            "audit_opinion": False,
            "certification_opinion": False,
            "control_effectiveness_rating": False,
            "customer_or_assessor_contact": False,
            "provider_or_account_mutation": False,
            "evidence_mutation": False,
            "payment": False,
            "accepted_revenue": False,
            "outbound": False,
        },
    }


def render_buyer_report(core: dict[str, Any]) -> str:
    counts = core["classification_counts"]
    reasons = core["non_reusable_reason_counts"]
    lines = [
        "# Evidence Freshness Diagnostic",
        "",
        f"Engagement: `{core['engagement_ref']}`",
        f"Evaluated at: `{core['evaluated_at']}`",
        f"Sanitized evidence objects: **{core['scope']['evidence_object_count']} / {MAX_EVIDENCE_OBJECTS}**",
        "",
        "## Freshness classification",
        "",
    ]
    for state in STATES:
        lines.append(f"- {state}: **{counts[state]}**")
    lines += ["", "## Non-reusable reasons", ""]
    if reasons:
        for reason in sorted(reasons):
            lines.append(f"- `{reason}`: **{reasons[reason]}**")
    else:
        lines.append("- None")
    binding = core["engine_binding"]
    lines += [
        "",
        "## Evidence binding",
        "",
        f"- Engine input: `{binding['normalized_input_sha256']}`",
        f"- Engine projection: `{binding['projection_sha256']}`",
        f"- Engine receipt: `{binding['engine_receipt_sha256']}`",
        f"- Engine source: `{binding['engine_source_sha256']}`",
        "",
        "## Commercial boundary",
        "",
        f"Fixed diagnostic hypothesis: **${FIXED_PRICE_USD:,}** for one sanitized export up to {MAX_EVIDENCE_OBJECTS} evidence objects.",
        f"Optional integration sprint hypothesis: **${INTEGRATION_SPRINT_USD:,}**, only after a paid diagnostic establishes value and actual adapter scope. No free custom adapter is included. Commercial state: **PROPOSED_NOT_ACCEPTED**.",
        "",
        "## Authority boundary",
        "",
        "This is deterministic read-only evidence-freshness QA. It is not an audit or certification opinion, does not conclude control effectiveness, and grants no authority to contact customers/assessors, mutate evidence/providers/accounts, accept payment, recognize revenue, or send outbound messages.",
        "",
    ]
    return "\n".join(lines)


def build_diagnostic(request: Any, packet: Any) -> tuple[dict[str, Any], str]:
    req = validate_request(request)
    if type(packet) is not dict:
        raise PilotError("engine_packet:object_required")
    try:
        verified = gate.verify_packet(packet)
    except Exception as exc:
        raise PilotError(f"engine_verify_failed:{type(exc).__name__}:{exc}") from exc
    if verified is not True:
        raise PilotError("engine_verify_failed:false")
    try:
        rebound = gate.compile_packet(req["evidence_input"])
    except Exception as exc:
        raise PilotError(f"engine_request_rebind_failed:{type(exc).__name__}:{exc}") from exc
    if rebound.get("input") != packet.get("input") or rebound.get("input_sha256") != packet.get("input_sha256"):
        raise PilotError("engine_packet:request_input_mismatch")
    core = _diagnostic_core(req, packet)
    report = render_buyer_report(core)
    diagnostic = dict(core)
    diagnostic["buyer_report_sha256"] = sha256_bytes(report.encode("utf-8"))
    diagnostic["receipt_sha256"] = sha256_obj(diagnostic)
    return diagnostic, report


def compile_diagnostic(request: Any) -> tuple[dict[str, Any], dict[str, Any], str]:
    req = validate_request(request)
    try:
        packet = gate.compile_packet(req["evidence_input"])
        if gate.verify_packet(packet) is not True:
            raise PilotError("engine_verify_failed:false")
    except PilotError:
        raise
    except Exception as exc:
        raise PilotError(f"engine_compile_or_verify_failed:{type(exc).__name__}:{exc}") from exc
    diagnostic, report = build_diagnostic(req, packet)
    return packet, diagnostic, report


def verify_diagnostic(request: Any, packet: Any, diagnostic: Any, report: str) -> bool:
    req = validate_request(request)
    if type(diagnostic) is not dict:
        raise PilotError("diagnostic:object_required")
    expected, expected_report = build_diagnostic(req, packet)
    if report != expected_report:
        raise PilotError("buyer_report:mismatch")
    if diagnostic != expected:
        raise PilotError("diagnostic:mismatch")
    receipt = diagnostic.get("receipt_sha256")
    body = dict(diagnostic)
    body.pop("receipt_sha256", None)
    if type(receipt) is not str or receipt != sha256_obj(body):
        raise PilotError("diagnostic:receipt_mismatch")
    return True


def _parent_leaf(path: str | Path) -> tuple[Path, str]:
    p = Path(path)
    leaf = p.name
    if not leaf or leaf in {".", ".."}:
        raise PilotError("output:bad_leaf")
    return p.parent if str(p.parent) else Path("."), leaf


def write_exclusive(path: str | Path, data: bytes) -> None:
    parent, leaf = _parent_leaf(path)
    pflags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        pfd = os.open(parent, pflags)
    except OSError as exc:
        raise PilotError(f"output_parent_open_failed:{exc.errno}") from exc
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(leaf, flags, 0o600, dir_fd=pfd)
        except OSError as exc:
            raise PilotError(f"output_create_failed:{exc.errno}") from exc
        try:
            view = memoryview(data)
            while view:
                wrote = os.write(fd, view)
                if wrote <= 0:
                    raise PilotError("output_short_write")
                view = view[wrote:]
            os.fsync(fd)
        finally:
            os.close(fd)
        os.fsync(pfd)
    finally:
        os.close(pfd)
