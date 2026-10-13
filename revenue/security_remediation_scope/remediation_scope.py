#!/usr/bin/env python3
"""Compile verified source findings into an owner-review security remediation SOW."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from typing import Any

SCOPE_SCHEMA = "security-remediation-scope-v2"
FINDINGS_SCHEMA = "security-remediation-findings-v1"
REPORT_SCHEMA = "security-remediation-sow-v2"
ACTIONABLE = {"PARTIAL", "HOLD_MISSING_EVIDENCE", "HOLD_STALE_EVIDENCE"}
NON_ACTIONABLE = {"SUPPORTED", "NOT_APPLICABLE"}
ALL_STATUSES = ACTIONABLE | NON_ACTIONABLE
MIN_FIXED_CENTS = 500_000
MAX_FIXED_CENTS = 3_000_000
MAX_FINDINGS = 100
MAX_INPUT_BYTES = 2_000_000
ID_RE = re.compile(r"^[A-Z][A-Z0-9_.-]{0,63}$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
PROHIBITED_OUTCOME_RE = re.compile(
    r"(?:\bcertif(?:y|ied|ication)\b|\bguarantee(?:d)?\s+compliance\b|"
    r"\bsoc\s*2\s+compliant\b|\bhipaa\s+compliant\b|"
    r"\biso\s*27001\s+certified\b|\bpci(?:-dss)?\s+compliant\b|"
    r"\bpass(?:es|ed)?\s+(?:an?\s+)?audit\b)",
    re.IGNORECASE,
)
AUTHORITY = {
    "buyer_contact_authorized": False,
    "contract_acceptance_authorized": False,
    "compliance_certification_authorized": False,
    "security_attestation_authorized": False,
    "deployment_authorized": False,
    "invoice_authorized": False,
    "payment_authorized": False,
    "revenue_recognition_authorized": False,
}


class ScopeError(ValueError):
    pass


def _reject_float(value: str) -> None:
    raise ScopeError(f"floating-point JSON is not allowed: {value}")


def _reject_constant(value: str) -> None:
    raise ScopeError(f"non-finite JSON is not allowed: {value}")


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ScopeError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def loads_strict(raw: bytes) -> Any:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ScopeError("input must be UTF-8") from exc
    try:
        return json.loads(text, object_pairs_hook=_pairs, parse_float=_reject_float, parse_constant=_reject_constant)
    except ScopeError:
        raise
    except (json.JSONDecodeError, ValueError) as exc:
        raise ScopeError(f"invalid JSON: {exc}") from exc


def canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ScopeError(f"value is not canonical JSON: {exc}") from exc


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _object(value: Any, required: set[str], optional: set[str], where: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise ScopeError(f"{where} must be an object")
    actual = set(value)
    missing = required - actual
    extra = actual - required - optional
    if missing or extra:
        raise ScopeError(f"{where} keys invalid: missing={sorted(missing)} extra={sorted(extra)}")
    return value


def _text(value: Any, where: str, max_len: int = 1200) -> str:
    if type(value) is not str or not value.strip() or len(value) > max_len:
        raise ScopeError(f"{where} must be a non-empty string <= {max_len} chars")
    return value


def _id(value: Any, where: str) -> str:
    text = _text(value, where, 64)
    if not ID_RE.fullmatch(text):
        raise ScopeError(f"{where} has invalid identifier syntax")
    return text


def _utc(value: Any, where: str) -> dt.datetime:
    text = _text(value, where, 40)
    if not text.endswith("Z"):
        raise ScopeError(f"{where} must be an explicit UTC Z timestamp")
    try:
        parsed = dt.datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        raise ScopeError(f"{where} is not a valid timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != dt.timedelta(0):
        raise ScopeError(f"{where} must be UTC")
    return parsed


def _sha256(value: Any, where: str) -> str:
    text = _text(value, where, 64)
    if not SHA_RE.fullmatch(text):
        raise ScopeError(f"{where} must be lowercase SHA-256")
    return text


def _id_list(value: Any, where: str) -> list[str]:
    if type(value) is not list or len(value) > 100:
        raise ScopeError(f"{where} must be a list with <= 100 items")
    out = [_id(item, f"{where}[{index}]") for index, item in enumerate(value)]
    if len(set(out)) != len(out):
        raise ScopeError(f"{where} must not contain duplicates")
    return sorted(out)


def _string_list(value: Any, where: str) -> list[str]:
    if type(value) is not list or len(value) > 50:
        raise ScopeError(f"{where} must be a list with <= 50 items")
    out = [_text(item, f"{where}[{index}]", 500) for index, item in enumerate(value)]
    if len(set(out)) != len(out):
        raise ScopeError(f"{where} must not contain duplicates")
    return sorted(out)


def _price(value: Any, where: str) -> int:
    if type(value) is not int or value <= 0 or value > MAX_FIXED_CENTS:
        raise ScopeError(f"{where} must be integer cents from 1 to {MAX_FIXED_CENTS}")
    return value


def _safe_outcome(text: str, where: str) -> str:
    if PROHIBITED_OUTCOME_RE.search(text):
        raise ScopeError(f"{where} promises a prohibited certification/compliance/audit outcome")
    return text


def validate_source_packet(value: Any) -> dict[str, Any]:
    packet = _object(value, {"schema", "packet_id", "observed_at", "findings"}, set(), "source_packet")
    if packet["schema"] != FINDINGS_SCHEMA:
        raise ScopeError(f"source_packet.schema must equal {FINDINGS_SCHEMA}")
    packet_id = _id(packet["packet_id"], "source_packet.packet_id")
    _utc(packet["observed_at"], "source_packet.observed_at")
    if type(packet["findings"]) is not list or len(packet["findings"]) > MAX_FINDINGS:
        raise ScopeError(f"source_packet.findings must be a list with <= {MAX_FINDINGS} items")
    seen: set[str] = set()
    findings: list[dict[str, Any]] = []
    for index, raw in enumerate(packet["findings"]):
        row = _object(
            raw,
            {"id", "source_status", "requirement", "source_evidence_ids", "current_state", "gap"},
            set(),
            f"source_packet.findings[{index}]",
        )
        fid = _id(row["id"], f"source_packet.findings[{index}].id")
        if fid in seen:
            raise ScopeError(f"duplicate source finding id: {fid}")
        seen.add(fid)
        status = row["source_status"]
        if status not in ALL_STATUSES:
            raise ScopeError(f"source finding {fid} has unsupported status")
        evidence_ids = _id_list(row["source_evidence_ids"], f"source finding {fid}.source_evidence_ids")
        if status in {"PARTIAL", "HOLD_STALE_EVIDENCE", "SUPPORTED"} and not evidence_ids:
            raise ScopeError(f"source finding {fid} status {status} requires at least one evidence id")
        findings.append(
            {
                "id": fid,
                "source_status": status,
                "requirement": _text(row["requirement"], f"source finding {fid}.requirement"),
                "source_evidence_ids": evidence_ids,
                "current_state": _text(row["current_state"], f"source finding {fid}.current_state"),
                "gap": _text(row["gap"], f"source finding {fid}.gap"),
            }
        )
    return {
        "schema": FINDINGS_SCHEMA,
        "packet_id": packet_id,
        "observed_at": packet["observed_at"],
        "findings": sorted(findings, key=lambda row: row["id"]),
    }


def validate_scope(value: Any) -> dict[str, Any]:
    manifest = _object(value, {"schema", "scope_id", "as_of", "currency", "source_packet", "remediations"}, set(), "manifest")
    if manifest["schema"] != SCOPE_SCHEMA:
        raise ScopeError(f"schema must equal {SCOPE_SCHEMA}")
    scope_id = _id(manifest["scope_id"], "manifest.scope_id")
    _utc(manifest["as_of"], "manifest.as_of")
    if manifest["currency"] != "USD":
        raise ScopeError("manifest.currency must equal USD")
    source = _object(manifest["source_packet"], {"packet_id", "sha256", "observed_at"}, set(), "manifest.source_packet")
    source_meta = {
        "packet_id": _id(source["packet_id"], "manifest.source_packet.packet_id"),
        "sha256": _sha256(source["sha256"], "manifest.source_packet.sha256"),
        "observed_at": source["observed_at"],
    }
    _utc(source_meta["observed_at"], "manifest.source_packet.observed_at")
    if type(manifest["remediations"]) is not list or len(manifest["remediations"]) > MAX_FINDINGS:
        raise ScopeError(f"manifest.remediations must be a list with <= {MAX_FINDINGS} items")
    seen: set[str] = set()
    remediations: list[dict[str, Any]] = []
    for index, raw in enumerate(manifest["remediations"]):
        rem = _object(
            raw,
            {"finding_id", "deliverable", "acceptance_test", "dependencies", "change_control_trigger", "owner_proposed_price_cents"},
            set(),
            f"remediations[{index}]",
        )
        fid = _id(rem["finding_id"], f"remediations[{index}].finding_id")
        if fid in seen:
            raise ScopeError(f"duplicate remediation finding id: {fid}")
        seen.add(fid)
        deliverable = _text(rem["deliverable"], f"remediation {fid}.deliverable")
        acceptance = _text(rem["acceptance_test"], f"remediation {fid}.acceptance_test")
        change = _text(rem["change_control_trigger"], f"remediation {fid}.change_control_trigger")
        remediations.append(
            {
                "finding_id": fid,
                "deliverable": _safe_outcome(deliverable, f"remediation {fid}.deliverable"),
                "acceptance_test": _safe_outcome(acceptance, f"remediation {fid}.acceptance_test"),
                "dependencies": _string_list(rem["dependencies"], f"remediation {fid}.dependencies"),
                "change_control_trigger": _safe_outcome(change, f"remediation {fid}.change_control_trigger"),
                "owner_proposed_price_cents": _price(rem["owner_proposed_price_cents"], f"remediation {fid}.owner_proposed_price_cents"),
            }
        )
    return {
        "schema": SCOPE_SCHEMA,
        "scope_id": scope_id,
        "as_of": manifest["as_of"],
        "currency": "USD",
        "source_packet": source_meta,
        "remediations": sorted(remediations, key=lambda row: row["finding_id"]),
    }


def compile_bytes(scope_raw: bytes, source_raw: bytes) -> tuple[dict[str, Any], str]:
    manifest = validate_scope(loads_strict(scope_raw))
    source = validate_source_packet(loads_strict(source_raw))
    if _sha(source_raw) != manifest["source_packet"]["sha256"]:
        raise ScopeError("exact source packet SHA-256 does not match manifest")
    if source["packet_id"] != manifest["source_packet"]["packet_id"]:
        raise ScopeError("source packet id does not match manifest")
    if source["observed_at"] != manifest["source_packet"]["observed_at"]:
        raise ScopeError("source packet observed_at does not match manifest")
    if _utc(source["observed_at"], "source_packet.observed_at") > _utc(manifest["as_of"], "manifest.as_of"):
        raise ScopeError("source packet cannot be observed after manifest.as_of")

    source_by_id = {row["id"]: row for row in source["findings"]}
    rem_by_id = {row["finding_id"]: row for row in manifest["remediations"]}
    unknown = sorted(set(rem_by_id) - set(source_by_id))
    if unknown:
        raise ScopeError(f"remediation references unknown source findings: {unknown}")
    non_actionable = sorted(fid for fid in rem_by_id if source_by_id[fid]["source_status"] in NON_ACTIONABLE)
    if non_actionable:
        raise ScopeError(f"non-actionable source findings cannot be monetized: {non_actionable}")

    work_items: list[dict[str, Any]] = []
    excluded: list[dict[str, str]] = []
    unscoped: list[dict[str, Any]] = []
    total = 0
    for source_row in source["findings"]:
        fid = source_row["id"]
        if source_row["source_status"] in NON_ACTIONABLE:
            excluded.append({"finding_id": fid, "reason": source_row["source_status"]})
            continue
        rem = rem_by_id.get(fid)
        if rem is None:
            unscoped.append({
                "finding_id": fid,
                "source_status": source_row["source_status"],
                "requirement": source_row["requirement"],
                "gap": source_row["gap"],
            })
            continue
        total += rem["owner_proposed_price_cents"]
        work_items.append({**source_row, **rem})

    actionable_count = sum(1 for row in source["findings"] if row["source_status"] in ACTIONABLE)
    if actionable_count == 0:
        scope_status = "NO_ACTIONABLE_FINDINGS"
    elif unscoped:
        scope_status = "HOLD_UNSCOPED_FINDINGS"
    elif not (MIN_FIXED_CENTS <= total <= MAX_FIXED_CENTS):
        scope_status = "HOLD_PRICE_OUTSIDE_FIXED_SCOPE"
    else:
        scope_status = "OWNER_REVIEW_READY"

    body = {
        "schema": REPORT_SCHEMA,
        "scope_id": manifest["scope_id"],
        "as_of": manifest["as_of"],
        "currency": "USD",
        "source_packet": {
            **manifest["source_packet"],
            "exact_bytes_verified": True,
            "semantic_sha256": _sha(canonical_bytes(source)),
        },
        "evidence_time_semantics": "HISTORICAL_OWNER_REVIEW_ONLY",
        "scope_status": scope_status,
        "work_items": work_items,
        "unscoped_findings": unscoped,
        "excluded_findings": excluded,
        "commercial": {
            "proposed_total_cents": total,
            "fixed_scope_min_cents": MIN_FIXED_CENTS,
            "fixed_scope_max_cents": MAX_FIXED_CENTS,
            "commercial_state": "PROPOSED_NOT_ACCEPTED",
            "pricing_authority": "OWNER_PROPOSED_INPUT_ONLY",
        },
        "authority": dict(AUTHORITY),
    }
    report = {
        **body,
        "receipt": {
            "scope_raw_sha256": _sha(scope_raw),
            "scope_semantic_sha256": _sha(canonical_bytes(manifest)),
            "source_packet_raw_sha256": _sha(source_raw),
            "source_packet_semantic_sha256": _sha(canonical_bytes(source)),
            "report_body_sha256": _sha(canonical_bytes(body)),
        },
    }
    return report, render_markdown(report)


def verify_bytes(scope_raw: bytes, source_raw: bytes, report_raw: bytes) -> None:
    expected, _ = compile_bytes(scope_raw, source_raw)
    supplied = loads_strict(report_raw)
    if canonical_bytes(expected) != canonical_bytes(supplied):
        raise ScopeError("report does not exactly match deterministic recompilation")


def _money(cents: int) -> str:
    return f"${cents // 100:,}.{cents % 100:02d}"


def _md(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Security Remediation Scope — Owner Review",
        "",
        f"Scope: `{report['scope_id']}`  ",
        f"Verified source packet: `{report['source_packet']['packet_id']}` / `{report['source_packet']['sha256']}`  ",
        f"Evidence as-of: `{report['as_of']}`  ",
        f"Decision: `{report['scope_status']}`  ",
        f"Commercial state: `{report['commercial']['commercial_state']}`  ",
        f"Owner-proposed total: **{_money(report['commercial']['proposed_total_cents'])}**",
        "",
        "| Finding | Source status | Proposed price | Deliverable |",
        "| --- | --- | ---: | --- |",
    ]
    for item in report["work_items"]:
        lines.append(f"| `{item['id']}` | `{item['source_status']}` | {_money(item['owner_proposed_price_cents'])} | {_md(item['deliverable'])} |")
    if not report["work_items"]:
        lines.append("| — | — | $0.00 | No scoped actionable findings. |")
    if report["unscoped_findings"]:
        lines += ["", "## Unscoped actionable findings", ""]
        for row in report["unscoped_findings"]:
            lines.append(f"- `{row['finding_id']}` / `{row['source_status']}` — {row['gap']}")
    lines += ["", "## Work items", ""]
    for item in report["work_items"]:
        lines += [
            f"### {item['id']}", "",
            f"**Requirement:** {item['requirement']}", "",
            f"**Verified source current state:** {item['current_state']}", "",
            f"**Evidence/control gap:** {item['gap']}", "",
            f"**Source evidence IDs:** {', '.join('`' + value + '`' for value in item['source_evidence_ids']) or 'none declared'}", "",
            f"**Deliverable:** {item['deliverable']}", "",
            f"**Acceptance test:** {item['acceptance_test']}", "",
            f"**Dependencies:** {', '.join(item['dependencies']) or 'none declared'}", "",
            f"**Change control:** {item['change_control_trigger']}", "",
        ]
    lines += [
        "## Truth and authority boundary", "",
        "The source packet bytes are SHA-256 verified and source finding fields are derived from those bytes rather than restated by the scope manifest. This remains a historical owner-review artifact: it does not certify compliance, attest security posture, guarantee audit passage, contact a buyer, accept a contract, authorize deployment/invoicing/payment, or recognize revenue. Pricing is owner-proposed input and remains `PROPOSED_NOT_ACCEPTED`.", "",
        f"Receipt: `{report['receipt']['report_body_sha256']}`", "",
    ]
    return "\n".join(lines)


def _read_limited(path: Path) -> bytes:
    raw = path.read_bytes()
    if len(raw) > MAX_INPUT_BYTES:
        raise ScopeError(f"{path} exceeds byte ceiling")
    return raw


def _write_exclusive(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise ScopeError(f"refusing to overwrite existing output: {path}") from exc


def cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    compile_p = sub.add_parser("compile")
    compile_p.add_argument("--input", required=True, type=Path)
    compile_p.add_argument("--source-packet", required=True, type=Path)
    compile_p.add_argument("--report-json", required=True, type=Path)
    compile_p.add_argument("--report-md", required=True, type=Path)
    verify_p = sub.add_parser("verify")
    verify_p.add_argument("--input", required=True, type=Path)
    verify_p.add_argument("--source-packet", required=True, type=Path)
    verify_p.add_argument("--report-json", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        scope_raw = _read_limited(args.input)
        source_raw = _read_limited(args.source_packet)
        if args.command == "compile":
            if args.report_json.exists() or args.report_md.exists():
                raise ScopeError("refusing to overwrite an existing report output")
            report, markdown = compile_bytes(scope_raw, source_raw)
            _write_exclusive(args.report_json, canonical_bytes(report) + b"\n")
            _write_exclusive(args.report_md, markdown.encode("utf-8"))
        else:
            verify_bytes(scope_raw, source_raw, _read_limited(args.report_json))
    except (ScopeError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())
