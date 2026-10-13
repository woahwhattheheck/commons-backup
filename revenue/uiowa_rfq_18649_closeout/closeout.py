#!/usr/bin/env python3
"""Offline evidence-lifecycle closeout validator for UIOWA-099.

This tool validates records only. It never deletes, moves, returns, or changes access
to evidence.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from typing import Iterable

INVENTORY_COLUMNS = (
    "evidence_id", "source_owner", "custodian", "description", "sensitivity",
    "received", "custody_location", "authorized_purpose", "received_date",
    "last_verified_date", "digest", "derived_copies", "planned_disposition",
    "confirmation_ref", "exception_ref", "notes",
)
DISPOSITION_COLUMNS = (
    "evidence_id", "action", "action_date", "method", "performed_by",
    "verified_by", "verification_artifact", "exception_or_instruction_ref", "notes",
)
SENSITIVITIES = {"public", "internal", "confidential", "restricted", "credential"}
NAMED_CLOSEOUT_KINDS = ("returned", "destroyed", "retained_by_instruction", "never_received")
PROTECTED = {"internal", "confidential", "restricted", "credential"}


class ValidationError(ValueError):
    pass


def parse_date(value: str, field: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValidationError(f"{field}: expected YYYY-MM-DD, got {value!r}") from exc


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_csv(path: Path, required: Iterable[str]) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = set(reader.fieldnames or [])
        missing = set(required) - fields
        if missing:
            raise ValidationError(f"{path.name}: missing columns {sorted(missing)}")
        return [{k: (v or "").strip() for k, v in row.items()} for row in reader]


def bool_field(value: str, field: str) -> bool:
    normalized = value.strip().lower()
    if normalized == "yes":
        return True
    if normalized == "no":
        return False
    raise ValidationError(f"{field}: expected yes/no, got {value!r}")


def deadline_for(engagement: dict) -> date:
    completion = parse_date(str(engagement["completion_date"]), "completion_date")
    days = int(engagement.get("closeout_days", 30))
    if days <= 0:
        raise ValidationError("closeout_days must be a positive integer")
    return completion + timedelta(days=days)


def _looks_public_repo(location: str) -> bool:
    text = location.lower().replace("-", "_").replace(" ", "_")
    return "public_repo" in text or "github.com/woahwhattheheck/commons" in text


def evaluate(
    engagement: dict,
    inventory: list[dict[str, str]],
    dispositions: list[dict[str, str]],
    as_of: date,
) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    due = deadline_for(engagement)

    primary_status = str(engagement.get("primary_requirement_locator_status", "")).strip()
    if primary_status != "verified_controlling_source":
        warnings.append(
            "30-day rule is carried from the current UIOWA-099 work order; "
            "replace the pending locator with the controlling RFQ/agreement clause before live use."
        )

    inv_by_id: dict[str, dict[str, str]] = {}
    for idx, row in enumerate(inventory, start=2):
        eid = row["evidence_id"]
        if not eid:
            errors.append(f"inventory line {idx}: evidence_id is required")
            continue
        if eid in inv_by_id:
            errors.append(f"inventory line {idx}: duplicate evidence_id {eid}")
            continue
        inv_by_id[eid] = row

        sensitivity = row["sensitivity"].lower()
        if sensitivity not in SENSITIVITIES:
            errors.append(f"{eid}: unsupported sensitivity {row['sensitivity']!r}")
            continue

        try:
            received = bool_field(row["received"], f"{eid}.received")
        except ValidationError as exc:
            errors.append(str(exc))
            continue

        if sensitivity in PROTECTED and received and _looks_public_repo(row["custody_location"]):
            errors.append(f"{eid}: protected evidence cannot use a public repository custody location")

        if sensitivity == "credential" and received:
            errors.append(
                f"{eid}: credential material must not be ingested into this assessment evidence register; "
                "record it as never_received and use an authorized credential-management boundary"
            )

        if received:
            if not row["custody_location"]:
                errors.append(f"{eid}: received evidence requires custody_location")
            if not row["received_date"]:
                errors.append(f"{eid}: received evidence requires received_date")
            else:
                try:
                    parse_date(row["received_date"], f"{eid}.received_date")
                except ValidationError as exc:
                    errors.append(str(exc))
        else:
            if row["digest"]:
                errors.append(f"{eid}: never-received evidence must not claim a content digest")
            if row["custody_location"]:
                errors.append(f"{eid}: never-received evidence must not claim a custody location")

    disp_by_id: dict[str, dict[str, str]] = {}
    for idx, row in enumerate(dispositions, start=2):
        eid = row["evidence_id"]
        if not eid:
            errors.append(f"disposition line {idx}: evidence_id is required")
            continue
        if eid in disp_by_id:
            errors.append(f"disposition line {idx}: duplicate evidence_id {eid}")
            continue
        disp_by_id[eid] = row

        if eid not in inv_by_id:
            errors.append(f"{eid}: disposition references unknown evidence")
            continue

        disposition_kind = row["action"]
        inv = inv_by_id[eid]
        try:
            received = bool_field(inv["received"], f"{eid}.received")
        except ValidationError:
            continue

        if not disposition_kind:
            errors.append(f"{eid}: disposition row requires a kind")
            continue

        if disposition_kind == "never_received":
            if received:
                errors.append(f"{eid}: never_received conflicts with inventory received=yes")
            if row["action_date"]:
                try:
                    parse_date(row["action_date"], f"{eid}.action_date")
                except ValidationError as exc:
                    errors.append(str(exc))
            continue

        if disposition_kind not in NAMED_CLOSEOUT_KINDS:
            warnings.append(
                f"{eid}: disposition kind {disposition_kind!r} is recorded without a named closeout handler"
            )
            continue

        if not received:
            errors.append(f"{eid}: {disposition_kind} conflicts with inventory received=no")

        if not row["action_date"]:
            errors.append(f"{eid}: {disposition_kind} requires action_date")
            action_date = None
        else:
            try:
                action_date = parse_date(row["action_date"], f"{eid}.action_date")
            except ValidationError as exc:
                errors.append(str(exc))
                action_date = None

        if disposition_kind == "returned" or disposition_kind == "destroyed":
            if not row["performed_by"]:
                errors.append(f"{eid}: {disposition_kind} requires performed_by")
            if not row["verified_by"]:
                errors.append(f"{eid}: {disposition_kind} requires verified_by")
            if not row["verification_artifact"]:
                errors.append(f"{eid}: {disposition_kind} requires verification_artifact")
            if action_date and action_date > due:
                errors.append(
                    f"{eid}: {disposition_kind} on {action_date.isoformat()} is after closeout deadline {due.isoformat()}"
                )

        if disposition_kind == "retained_by_instruction":
            ref = row["exception_or_instruction_ref"] or inv["exception_ref"]
            if not ref:
                errors.append(
                    f"{eid}: retained_by_instruction requires a written exception/instruction reference"
                )

    protected_received = 0
    protected_accounted = 0
    pending: list[str] = []
    for eid, inv in inv_by_id.items():
        sensitivity = inv["sensitivity"].lower()
        try:
            received = bool_field(inv["received"], f"{eid}.received")
        except ValidationError:
            continue
        disp = disp_by_id.get(eid)

        if sensitivity in PROTECTED and received:
            protected_received += 1
            if disp and disp["action"] in {"returned", "destroyed", "retained_by_instruction"}:
                protected_accounted += 1
            else:
                pending.append(eid)

        if not received:
            if not disp:
                warnings.append(f"{eid}: received=no but no explicit never_received disposition row")
            elif disp["action"] != "never_received":
                errors.append(f"{eid}: received=no should use never_received disposition")

    if as_of > due and pending:
        errors.append(
            "closeout deadline has passed with unaccounted protected evidence: "
            + ", ".join(sorted(pending))
        )
    elif pending:
        warnings.append(
            "protected evidence remains pending before the closeout deadline: "
            + ", ".join(sorted(pending))
        )

    action_counts = Counter(row["action"] for row in dispositions if row["action"])
    status = "PASS" if not errors else "FAIL"
    return {
        "schema": "uiowa.closeout.v1",
        "status": status,
        "engagement_id": engagement.get("engagement_id", ""),
        "completion_date": engagement.get("completion_date", ""),
        "closeout_days": int(engagement.get("closeout_days", 30)),
        "closeout_deadline": due.isoformat(),
        "as_of": as_of.isoformat(),
        "primary_requirement_locator_status": primary_status or "missing",
        "inventory_count": len(inventory),
        "disposition_count": len(dispositions),
        "protected_received_count": protected_received,
        "protected_accounted_count": protected_accounted,
        "pending_protected_evidence": sorted(pending),
        "action_counts": dict(sorted(action_counts.items())),
        "errors": errors,
        "warnings": warnings,
        "safety": {
            "mutates_evidence": False,
            "deletes_files": False,
            "changes_access": False,
        },
    }


def render_markdown(report: dict) -> str:
    lines = [
        "# Evidence closeout validation report",
        "",
        "**Preparation artifact only — this report does not itself return or destroy evidence.**",
        "",
        f"- Engagement: `{report['engagement_id']}`",
        f"- Completion date: `{report['completion_date']}`",
        f"- Closeout rule: `{report['closeout_days']}` calendar days",
        f"- Deadline: `{report['closeout_deadline']}`",
        f"- Evaluated as of: `{report['as_of']}`",
        f"- Result: **{report['status']}**",
        f"- Protected evidence accounted: `{report['protected_accounted_count']}/{report['protected_received_count']}`",
        f"- Primary locator status: `{report['primary_requirement_locator_status']}`",
        "",
        "## Disposition counts",
        "",
    ]
    for action, count in report["action_counts"].items():
        lines.append(f"- `{action}`: {count}")
    if not report["action_counts"]:
        lines.append("- none")
    lines.extend(["", "## Errors", ""])
    lines.extend([f"- {item}" for item in report["errors"]] or ["- none"])
    lines.extend(["", "## Warnings", ""])
    lines.extend([f"- {item}" for item in report["warnings"]] or ["- none"])
    lines.extend(
        [
            "",
            "## Safety boundary",
            "",
            "The validator reads metadata records only. It never deletes, moves, returns, uploads, "
            "or changes access to evidence. Actual disposition requires authorized operators and "
            "separately retained proof.",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate UIOWA-099 evidence closeout records.")
    parser.add_argument("engagement", type=Path)
    parser.add_argument("inventory", type=Path)
    parser.add_argument("dispositions", type=Path)
    parser.add_argument("--as-of", help="YYYY-MM-DD; defaults to today")
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--md-out", type=Path)
    args = parser.parse_args(argv)

    engagement = load_json(args.engagement)
    inventory = load_csv(args.inventory, INVENTORY_COLUMNS)
    dispositions = load_csv(args.dispositions, DISPOSITION_COLUMNS)
    as_of = parse_date(args.as_of, "as_of") if args.as_of else date.today()
    report = evaluate(engagement, inventory, dispositions, as_of)

    if args.json_out:
        args.json_out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    else:
        print(json.dumps(report, indent=2, sort_keys=True))

    if args.md_out:
        args.md_out.write_text(render_markdown(report), encoding="utf-8")

    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
