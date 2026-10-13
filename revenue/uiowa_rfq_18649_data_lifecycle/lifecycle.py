"""Offline, metadata-only development data-lifecycle assessment (UIOWA-059)."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any

SCHEMA = "uiowa.data-lifecycle/v1"
REPORT_SCHEMA = "uiowa.data-lifecycle-report/v1"
STAGES = ("classification", "minimization", "transfer", "retention", "disposal", "disposal_verification")
BASE_STAGES = ("classification", "minimization", "retention")
STATUSES = ("OBSERVED_SUPPORTED", "OBSERVED_GAP", "DOCUMENTED_ONLY", "DOCUMENTED_GAP", "UNKNOWN", "CONTRADICTORY")
MAX_BYTES = 2_000_000
ITEM_FIELDS = {"id", "group", "use_case", "parent_id", "created_at", "owner", "purpose", "classification", "location", "retained_categories", "retention_due_at"}
EVIDENCE_FIELDS = {"id", "item_id", "stage", "basis", "outcome", "at", "reference", "recorded_by", "statement"}
ROOT_FIELDS = {"schema", "assessment_id", "as_of", "evidence_mode", "items", "evidence"}
GUIDANCE = {
    "classification": ("Review the data categories and classification decision with the accountable steward.", "0.5-1 team-days", "Data steward; purpose and category inventory"),
    "minimization": ("Walk through why each retained category is needed and record a minimization decision.", "0.5-2 team-days", "Service owner; representative metadata; test/support purpose"),
    "transfer": ("Trace this copy to its source, destination, responsible role and transfer-review record.", "0.5-2 team-days", "Source and destination owners; copy inventory"),
    "retention": ("Agree a purpose-bound retention decision and a review or disposal date for this copy.", "0.5-2 team-days", "Service owner; relevant records-policy specialist; operational dependencies"),
    "disposal": ("Reconcile expiry with operational needs, then obtain records of the disposition actually performed.", "1-3 team-days", "Copy owners; dependency review; approved operational process"),
    "disposal_verification": ("Obtain a separate verification record for the same copy after the disposition event.", "0.5-2 team-days", "Operator; verifier; location and backup/derived-copy scope"),
    "ownership": ("Identify the accountable organizational role and record its acceptance of lifecycle responsibility.", "0.5-1 team-days", "Service lead; destination owner"),
    "purpose": ("Record the specific development or support purpose before interpreting necessity or retention.", "0.5-1 team-days", "Requesting team; service owner"),
}


class InputError(ValueError):
    """A malformed or internally impossible metadata packet."""


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise InputError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _not_number(value: str) -> Any:
    raise InputError("numeric JSON values are not part of this metadata schema")


def loads(raw: str) -> dict[str, Any]:
    if type(raw) is not str:
        raise InputError("input must be UTF-8 JSON text")
    try:
        if len(raw.encode("utf-8")) > MAX_BYTES:
            raise InputError("input exceeds 2 MB")
        value = json.loads(raw, object_pairs_hook=_pairs, parse_int=_not_number,
                           parse_float=_not_number, parse_constant=_not_number)
    except (UnicodeError, RecursionError, ValueError) as exc:
        if isinstance(exc, InputError):
            raise
        raise InputError(f"invalid JSON: {exc}") from exc
    validate(value)
    return value


def _obj(value: Any, fields: set[str], label: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != fields:
        raise InputError(f"{label}: expected exactly {sorted(fields)}")
    return value


def _text(value: Any, label: str, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if type(value) is not str or not value.strip() or len(value) > 1000:
        raise InputError(f"{label}: expected nonblank text up to 1000 characters")
    if any(ord(c) < 32 or 0xD800 <= ord(c) <= 0xDFFF for c in value):
        raise InputError(f"{label}: control characters and invalid Unicode are not allowed")
    return value


def _id(value: Any, label: str) -> str:
    if type(value) is not str or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", value) is None:
        raise InputError(f"{label}: expected a stable identifier")
    return value


def _time(value: Any, label: str) -> datetime:
    if type(value) is not str or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", value) is None:
        raise InputError(f"{label}: expected UTC YYYY-MM-DDTHH:MM:SSZ using ASCII digits")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise InputError(f"{label}: invalid calendar timestamp") from exc


def _enum(value: Any, choices: tuple[str, ...], label: str) -> str:
    if type(value) is not str or value not in choices:
        raise InputError(f"{label}: expected one of {choices}")
    return value


def validate(packet: Any) -> None:
    _obj(packet, ROOT_FIELDS, "packet")
    if packet["schema"] != SCHEMA:
        raise InputError("unsupported schema")
    _id(packet["assessment_id"], "assessment_id")
    as_of = _time(packet["as_of"], "as_of")
    _enum(packet["evidence_mode"], ("SYNTHETIC", "SUPPLIED_METADATA_UNVERIFIED"), "evidence_mode")
    items, evidence = packet["items"], packet["evidence"]
    if type(items) is not list or not 1 <= len(items) <= 200:
        raise InputError("items: expected 1..200 records")
    if type(evidence) is not list or len(evidence) > 4000:
        raise InputError("evidence: expected at most 4000 records")
    by_id: dict[str, Any] = {}
    for item in items:
        _obj(item, ITEM_FIELDS, "item")
        ident = _id(item["id"], "item.id")
        if ident in by_id:
            raise InputError(f"duplicate item id: {ident}")
        by_id[ident] = item
        _enum(item["group"], ("ESS", "RIS", "IAM"), "group")
        _enum(item["use_case"], ("TEST_DATA", "DIAGNOSTIC_EXPORT", "TROUBLESHOOTING_COPY"), "use_case")
        _enum(item["classification"], ("PUBLIC", "INTERNAL", "SENSITIVE", "UNKNOWN"), "classification")
        for name in ("owner", "purpose"):
            _text(item[name], name, nullable=True)
        _text(item["location"], "location")
        if _time(item["created_at"], "created_at") > as_of:
            raise InputError(f"{ident}: creation is after as_of")
        if item["parent_id"] is not None:
            _id(item["parent_id"], "parent_id")
        due = item["retention_due_at"]
        if due is not None and _time(due, "retention_due_at") < _time(item["created_at"], "created_at"):
            raise InputError(f"{ident}: retention date precedes creation")
        categories = item["retained_categories"]
        if type(categories) is not list or not 1 <= len(categories) <= 40:
            raise InputError("retained_categories: expected 1..40 category labels, not data values")
        for category in categories:
            _text(category, "retained category")
        if len(set(categories)) != len(categories):
            raise InputError("duplicate retained category")
    for item in items:
        seen = {item["id"]}
        current = item
        while current["parent_id"] is not None:
            parent = current["parent_id"]
            if parent not in by_id:
                raise InputError(f"unknown parent: {parent}")
            if parent in seen:
                raise InputError("copy lineage contains a cycle")
            seen.add(parent)
            if by_id[parent]["created_at"] > current["created_at"]:
                raise InputError("copy predates its source")
            current = by_id[parent]
    evidence_ids: set[str] = set()
    for row in evidence:
        _obj(row, EVIDENCE_FIELDS, "evidence")
        ident = _id(row["id"], "evidence.id")
        if ident in evidence_ids:
            raise InputError(f"duplicate evidence id: {ident}")
        evidence_ids.add(ident)
        subject = _id(row["item_id"], "evidence.item_id")
        if subject not in by_id:
            raise InputError(f"unknown evidence subject: {subject}")
        _enum(row["stage"], STAGES, "stage")
        _enum(row["basis"], ("DOCUMENTED", "OBSERVED"), "basis")
        _enum(row["outcome"], ("SUPPORTED", "GAP", "UNKNOWN"), "outcome")
        at = _time(row["at"], "evidence.at")
        if not _time(by_id[subject]["created_at"], "created_at") <= at <= as_of:
            raise InputError(f"{ident}: evidence is outside the item's assessment window")
        if row["stage"] == "transfer" and by_id[subject]["parent_id"] is None:
            raise InputError("transfer evidence must name the derived copy, not its source")
        for name in ("reference", "recorded_by", "statement"):
            _text(row[name], name)


def _latest(rows: list[dict[str, Any]], basis: str) -> tuple[str | None, str | None, list[str]]:
    selected = [row for row in rows if row["basis"] == basis]
    if not selected:
        return None, None, []
    at = max(row["at"] for row in selected)
    latest = [row for row in selected if row["at"] == at]
    outcomes = {row["outcome"] for row in latest}
    return (next(iter(outcomes)) if len(outcomes) == 1 else "CONTRADICTORY",
            at, sorted(row["id"] for row in latest))


def _check(rows: list[dict[str, Any]], stage: str) -> dict[str, Any]:
    selected = [row for row in rows if row["stage"] == stage]
    observed, at, current_ids = _latest(selected, "OBSERVED")
    documented, doc_at, doc_ids = _latest(selected, "DOCUMENTED")
    if observed is not None:
        status = {"SUPPORTED": "OBSERVED_SUPPORTED", "GAP": "OBSERVED_GAP",
                  "UNKNOWN": "UNKNOWN", "CONTRADICTORY": "CONTRADICTORY"}[observed]
    else:
        status = {None: "UNKNOWN", "SUPPORTED": "DOCUMENTED_ONLY", "GAP": "DOCUMENTED_GAP",
                  "UNKNOWN": "UNKNOWN", "CONTRADICTORY": "CONTRADICTORY"}[documented]
    return {"stage": stage, "status": status, "latest_observed_at": at,
            "latest_observed_ids": current_ids, "documented_outcome": documented,
            "latest_documented_at": doc_at, "latest_documented_ids": doc_ids,
            "evidence_ids": sorted(row["id"] for row in selected)}


def assess(packet: dict[str, Any]) -> dict[str, Any]:
    """Classify supplied records at explicit as_of; do not attest their authenticity."""
    validate(packet)
    # Freeze ordinary validated JSON values so all report sections share one input.
    packet = json.loads(canonical(packet))
    packet["items"].sort(key=lambda item: item["id"])
    packet["evidence"].sort(key=lambda row: row["id"])
    for item in packet["items"]:
        item["retained_categories"].sort()
    results, findings = [], []

    def finding(item: dict[str, Any], code: str, stage: str, severity: str, detail: str,
                evidence_ids: list[str] | None = None) -> None:
        action, effort, dependencies = GUIDANCE[stage]
        findings.append({"item_id": item["id"], "group": item["group"], "code": code,
                         "stage": stage, "severity": severity, "detail": detail,
                         "evidence_ids": evidence_ids or [], "next_step": action,
                         "effort_hint": effort, "effort_is_planning_assumption": True,
                         "dependencies": dependencies})

    for item in packet["items"]:
        rows = [row for row in packet["evidence"] if row["item_id"] == item["id"]]
        checks = {stage: _check(rows, stage) for stage in STAGES}
        disposal, verification = checks["disposal"], checks["disposal_verification"]
        done = disposal["status"] == "OBSERVED_SUPPORTED"
        verified = verification["status"] == "OBSERVED_SUPPORTED"
        coherent = done and verified and verification["latest_observed_at"] >= disposal["latest_observed_at"]
        state = ("SUPPLIED_RECORDS_SUPPORT_DISPOSAL" if coherent else
                 "DISPOSAL_REPORTED_UNVERIFIED" if done else "ACTIVE_OR_UNKNOWN")
        due = item["retention_due_at"]
        expired = due is not None and due <= packet["as_of"]
        applicable = list(BASE_STAGES)
        if item["parent_id"] is not None:
            applicable.append("transfer")
        if expired or disposal["evidence_ids"] or verification["evidence_ids"]:
            applicable.extend(("disposal", "disposal_verification"))
        for stage in applicable:
            check = checks[stage]
            if check["status"] != "OBSERVED_SUPPORTED":
                severity = "GAP" if check["status"] == "OBSERVED_GAP" else "UNKNOWN"
                if check["status"] == "CONTRADICTORY":
                    severity = "CONTRADICTION"
                finding(item, f"{stage.upper()}_{check['status']}", stage, severity,
                        f"{stage}: {check['status']}; a recorded procedure alone does not establish practice.",
                        check["evidence_ids"])
        for name in ("owner", "purpose"):
            if item[name] is None:
                finding(item, f"{name.upper()}_NOT_RECORDED", "ownership" if name == "owner" else "purpose",
                        "UNKNOWN", f"No {name} is recorded; this does not establish that none exists.")
        if item["classification"] == "UNKNOWN":
            finding(item, "CLASSIFICATION_NOT_RECORDED", "classification", "UNKNOWN",
                    "The classification metadata is unresolved even if a review record exists.")
        if due is None:
            finding(item, "RETENTION_DATE_NOT_RECORDED", "retention", "UNKNOWN",
                    "No review/disposal date is recorded; no unlimited-retention decision is inferred.")
        if expired and not coherent:
            finding(item, "EXPIRY_WITHOUT_VERIFIED_DISPOSITION", "disposal", "FOLLOW_UP",
                    "The supplied review/disposal date has arrived; current disposition needs reconciliation.",
                    disposal["evidence_ids"] + verification["evidence_ids"])
        if verified and not coherent:
            severity = ("CONTRADICTION" if done or disposal["status"] in
                        ("OBSERVED_GAP", "CONTRADICTORY") else "UNKNOWN")
            finding(item, "DISPOSAL_VERIFICATION_UNCORROBORATED", "disposal_verification", severity,
                    "The latest observations do not jointly support current same-copy disposition "
                    "in chronological order; this does not rule out earlier supporting disposal "
                    "records, which remain in the retained evidence history.",
                    disposal["evidence_ids"] + verification["evidence_ids"])
        results.append({"item": item, "state": state, "expiry_reached": expired,
                        "applicable_checks": [checks[stage] for stage in applicable]})
    by_id = {result["item"]["id"]: result for result in results}
    for result in results:
        item = result["item"]
        parent_id = item["parent_id"]
        if parent_id is not None and by_id[parent_id]["state"] == "SUPPLIED_RECORDS_SUPPORT_DISPOSAL" and result["state"] != "SUPPLIED_RECORDS_SUPPORT_DISPOSAL":
            finding(item, "SOURCE_DISPOSAL_DOES_NOT_COVER_COPY", "disposal", "FOLLOW_UP",
                    f"Source {parent_id} has disposition records; this separately tracked copy does not. Separate retention may be justified.")
    findings.sort(key=lambda row: (row["item_id"], row["stage"], row["code"]))
    counts = Counter(check["status"] for result in results for check in result["applicable_checks"])
    report = {"schema": REPORT_SCHEMA, "assessment_id": packet["assessment_id"],
              "as_of": packet["as_of"], "evidence_mode": packet["evidence_mode"],
              "input_sha256": digest(packet), "authority": "OFFLINE_SUPPLIED_RECORDS_ONLY",
              "limitations": ["No live-system or source authenticity verification.",
                              "Evidence labels are assessor-supplied assertions, not independently established findings.",
                              "No compliance, maturity ranking, data deletion or operational action is authorized.",
                              "Effort ranges are illustrative team-day planning assumptions requiring local estimates."],
              "summary": {"items": len(results), "evidence_records": len(packet["evidence"]),
                          "applicable_checks": sum(counts.values()),
                          "check_counts": {status: counts[status] for status in STATUSES},
                          "findings": len(findings)},
              "items": results, "evidence": packet["evidence"], "findings": findings}
    report["report_sha256"] = digest(report)
    return report


def verify_report(packet: dict[str, Any], report: dict[str, Any]) -> bool:
    """Verify deterministic semantics, not authenticity of the supplied evidence."""
    try:
        return canonical(assess(packet)) == canonical(report)
    except (InputError, TypeError, ValueError, RecursionError):
        return False


def _md(value: Any) -> str:
    text = str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return re.sub(r"([\\`*_\[\]()|#!])", r"\\\1", text).replace("\n", " ").replace("\r", " ")


def markdown(report: dict[str, Any]) -> str:
    lines = ["# Development data-lifecycle evidence assessment", "",
             f"Assessment: {_md(report['assessment_id'])} | As of: {_md(report['as_of'])}",
             f"Evidence: **{_md(report['evidence_mode'])}**. Offline supplied records only.", "",
             "No compliance conclusion, maturity score, authenticity claim or operational action.", "",
             "## Per-copy lifecycle matrix", "", "| Copy | Group | Purpose | Owner | Disposition |",
             "|---|---|---|---|---|"]
    for row in report["items"]:
        item = row["item"]
        lines.append("| " + " | ".join(_md(value) for value in (item["id"], item["group"], item["purpose"] or "UNKNOWN", item["owner"] or "UNKNOWN", row["state"])) + " |")
    lines += ["", "## Evidence coverage (not a maturity score)", "",
              f"Applicable checks: {report['summary']['applicable_checks']}.", ""]
    for status, count in report["summary"]["check_counts"].items():
        lines.append(f"{status}: {count}  ")
    lines += ["", "## Interview and improvement follow-ups", ""]
    for row in report["findings"]:
        lines += [f"### {_md(row['item_id'])}: {_md(row['code'])}",
                  f"Evidence classification: {_md(row['severity'])}. {_md(row['detail'])}",
                  f"Next step: {_md(row['next_step'])}",
                  f"Dependencies: {_md(row['dependencies'])}.",
                  f"Illustrative effort: {_md(row['effort_hint'])}; obtain a local estimate.",
                  f"Evidence IDs: {_md(', '.join(row['evidence_ids']) or 'none supplied')}.", ""]
    lines += ["## Retained source index", "", "| Evidence | Copy | Basis | Stage | Time | Reference |",
              "|---|---|---|---|---|---|"]
    for row in report["evidence"]:
        lines.append("| " + " | ".join(_md(row[key]) for key in ("id", "item_id", "basis", "stage", "at", "reference")) + " |")
    lines += ["", f"Input SHA-256: `{report['input_sha256']}`", f"Report SHA-256: `{report['report_sha256']}`", ""]
    return "\n".join(lines)


def findings_csv(report: dict[str, Any]) -> str:
    fields = ("item_id", "group", "code", "stage", "severity", "detail", "evidence_ids", "next_step", "effort_hint", "dependencies")
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(fields)
    for row in report["findings"]:
        values = []
        for field in fields:
            value = ", ".join(row[field]) if field == "evidence_ids" else str(row[field])
            if value.lstrip().startswith(("=", "+", "-", "@")):
                value = "'" + value
            values.append(value)
        writer.writerow(values)
    return output.getvalue()
