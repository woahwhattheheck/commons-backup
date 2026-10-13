#!/usr/bin/env python3
"""Structural validator for the UIOWA-023 synthetic evidence register."""

from __future__ import annotations

import csv
import io
import re
import sys
from pathlib import Path

REQUIRED = {
    "evidence_id", "observation_id", "finding_id", "group", "area",
    "source_type", "source_ref", "custodian_or_owner", "content_digest",
    "captured_at", "represented_period", "claim", "scope_limit", "directness",
    "recency", "representativeness", "corroboration", "evidence_state",
    "confidence", "conflict_group", "universe_definition",
    "enumerator_authority", "completeness_basis", "follow_up",
}
GROUPS = {"ESS", "RIS", "IAM"}
AREAS = {"SD", "SEC", "DEP", "AI"}
DIRECTNESS = {"DIRECT", "NEAR_DIRECT", "INDIRECT"}
RECENCY = {"CURRENT", "AGING", "STALE", "UNKNOWN"}
REPRESENTATIVENESS = {
    "POPULATION_BOUNDED", "SAMPLED", "SINGLE", "POPULATION_UNKNOWN", "UNKNOWN"
}
CORROBORATION = {
    "INDEPENDENT", "SAME_SYSTEM", "NO_CORROBORATION", "CONTRADICTED"
}
STATES = {
    "SUPPORTING", "CONFLICTING", "EVIDENCE_OF_ABSENCE", "NO_EVIDENCE_OBSERVED"
}
CONFIDENCE = {"HIGH", "MODERATE", "LOW", "UNRESOLVED", "NOT_EVIDENCED"}
UNKNOWN_CUSTODIAN = "UNKNOWN_SYNTHETIC_CUSTODIAN"
NOT_RETAINED_DIGEST = "NOT_RETAINED_SYNTHETIC_SOURCE"

EV_RE = re.compile(r"^EV-SYN-(ESS|RIS|IAM)-(SD|SEC|DEP|AI)-[A-Z]+-[0-9]{3}$")
OBS_RE = re.compile(r"^OBS-SYN-(ESS|RIS|IAM)-(SD|SEC|DEP|AI)-[0-9]{3}$")
FND_RE = re.compile(r"^FND-SYN-(ESS|RIS|IAM)-(SD|SEC|DEP|AI)-[0-9]{3}$")
SHA256_RE = re.compile(r"^sha256:[0-9a-fA-F]{64}$")


def _enum(row_num, field, value, allowed, errors):
    if value not in allowed:
        errors.append(f"row {row_num}: {field}={value!r} is invalid")


def validate_records(columns: list[str], rows: list[dict[str, str]]) -> list[str]:
    """Apply the unchanged evidence semantics after checking table shape.

    Extension columns are retained. A valid empty table remains structurally
    valid, not evidence that any assessment was performed.
    """
    errors: list[str] = []
    if not isinstance(columns, list) or any(not isinstance(c, str) for c in columns):
        return ["columns must be a list of strings"]
    if any(not c.strip() for c in columns):
        errors.append("column names must not be blank")
    if len(set(columns)) != len(columns):
        errors.append("duplicate column names are not allowed")
    missing = REQUIRED - set(columns)
    if missing:
        errors.append(f"missing required columns: {sorted(missing)}")
    if not isinstance(rows, list):
        errors.append("rows must be a list")
    if errors:
        return errors
    expected = set(columns)
    for row_num, row in enumerate(rows, start=2):
        if not isinstance(row, dict) or set(row) != expected:
            errors.append(f"row {row_num}: keys must match columns exactly")
        elif any(not isinstance(value, str) for value in row.values()):
            errors.append(f"row {row_num}: all cell values must be strings")
        else:
            try:
                for value in row.values():
                    value.encode("utf-8")
            except UnicodeEncodeError:
                errors.append(f"row {row_num}: cell contains non-scalar Unicode")
    try:
        for column in columns:
            column.encode("utf-8")
    except UnicodeEncodeError:
        errors.append("column contains non-scalar Unicode")
    if errors:
        return errors
    seen = set()
    for row_num, row in enumerate(rows, start=2):
        evidence_id = row["evidence_id"].strip()
        observation_id = row["observation_id"].strip()
        finding_id = row["finding_id"].strip()

        if evidence_id in seen:
            errors.append(f"row {row_num}: duplicate evidence_id {evidence_id}")
        seen.add(evidence_id)

        if not EV_RE.fullmatch(evidence_id):
            errors.append(f"row {row_num}: malformed evidence_id {evidence_id}")
        if not OBS_RE.fullmatch(observation_id):
            errors.append(f"row {row_num}: malformed observation_id {observation_id}")
        if not FND_RE.fullmatch(finding_id):
            errors.append(f"row {row_num}: malformed finding_id {finding_id}")

        _enum(row_num, "group", row["group"], GROUPS, errors)
        _enum(row_num, "area", row["area"], AREAS, errors)
        _enum(row_num, "directness", row["directness"], DIRECTNESS, errors)
        _enum(row_num, "recency", row["recency"], RECENCY, errors)
        _enum(row_num, "representativeness", row["representativeness"], REPRESENTATIVENESS, errors)
        _enum(row_num, "corroboration", row["corroboration"], CORROBORATION, errors)
        _enum(row_num, "evidence_state", row["evidence_state"], STATES, errors)
        _enum(row_num, "confidence", row["confidence"], CONFIDENCE, errors)

        for field in (
            "source_type", "source_ref", "custodian_or_owner", "content_digest",
            "captured_at", "represented_period", "claim", "scope_limit", "follow_up"
        ):
            if not row[field].strip():
                errors.append(f"row {row_num}: {field} must not be blank")

        content_digest = row["content_digest"].strip()
        if (
            content_digest
            and content_digest != NOT_RETAINED_DIGEST
            and not SHA256_RE.fullmatch(content_digest)
        ):
            errors.append(
                f"row {row_num}: content_digest must be sha256:<64 hex> "
                f"or {NOT_RETAINED_DIGEST}"
            )

        if row["recency"] == "STALE" and row["confidence"] == "HIGH":
            errors.append(f"row {row_num}: stale evidence cannot be HIGH confidence")

        if row["evidence_state"] == "CONFLICTING":
            if row["confidence"] != "UNRESOLVED":
                errors.append(f"row {row_num}: CONFLICTING evidence must be UNRESOLVED")
            if not row["conflict_group"].strip():
                errors.append(f"row {row_num}: CONFLICTING evidence requires conflict_group")

        if row["evidence_state"] == "NO_EVIDENCE_OBSERVED":
            if row["confidence"] != "NOT_EVIDENCED":
                errors.append(
                    f"row {row_num}: NO_EVIDENCE_OBSERVED must use NOT_EVIDENCED confidence"
                )

        if row["evidence_state"] == "EVIDENCE_OF_ABSENCE":
            for field in (
                "universe_definition", "enumerator_authority", "completeness_basis"
            ):
                if not row[field].strip():
                    errors.append(
                        f"row {row_num}: EVIDENCE_OF_ABSENCE requires {field}"
                    )

        group = row["group"]
        area = row["area"]
        if group and area:
            marker = f"-{group}-{area}-"
            if marker not in evidence_id:
                errors.append(f"row {row_num}: evidence_id scope mismatch")
            if marker not in observation_id:
                errors.append(f"row {row_num}: observation_id scope mismatch")
            if marker not in finding_id:
                errors.append(f"row {row_num}: finding_id scope mismatch")

    return errors


def _read_table(handle) -> tuple[list[str], list[dict[str, str]], list[str]]:
    """Read CSV before constructing dictionaries; never discard surplus cells."""
    reader = csv.reader(handle, strict=True)
    columns: list[str] = []
    rows: list[dict[str, str]] = []
    errors: list[str] = []
    try:
        columns = next(reader, [])
        if len(set(columns)) != len(columns):
            return columns, [], ["duplicate column names are not allowed"]
        if any(not column.strip() for column in columns):
            return columns, [], ["column names must not be blank"]
        while True:
            physical_line = reader.line_num + 1
            try:
                values = next(reader)
            except StopIteration:
                break
            if not values:  # Match DictReader's blank-record behaviour.
                continue
            if len(values) != len(columns):
                errors.append(
                    f"line {physical_line}: expected {len(columns)} cells, got {len(values)}"
                )
                continue
            rows.append(dict(zip(columns, values)))
    except (csv.Error, UnicodeError) as exc:
        errors.append(f"CSV input error near line {reader.line_num}: {exc}")
    if not errors:
        errors.extend(validate_records(columns, rows))
    return columns, rows, errors


def parse_csv(text: str) -> tuple[list[str], list[dict[str, str]], list[str]]:
    """Parse scalar text without normalising embedded CR/LF or cell values."""
    if not isinstance(text, str):
        return [], [], ["CSV input must be text"]
    return _read_table(io.StringIO(text, newline=""))


def load_register(path: Path) -> tuple[list[str], list[dict[str, str]], list[str]]:
    try:
        with Path(path).open("r", encoding="utf-8", newline="") as handle:
            return _read_table(handle)
    except (OSError, UnicodeError, ValueError) as exc:
        return [], [], [f"cannot read register: {exc}"]


def validate(path: Path) -> list[str]:
    return load_register(path)[2]


def main(argv) -> int:
    path = Path(argv[1]) if len(argv) > 1 else Path(__file__).with_name(
        "23-synthetic-evidence-register.csv"
    )
    _columns, rows, errors = load_register(path)
    if errors:
        for error in errors:
            print("ERROR:", error, file=sys.stderr)
        return 1
    observations = {row["observation_id"] for row in rows}
    findings = {row["finding_id"] for row in rows}
    print(f"OK rows={len(rows)} observations={len(observations)} findings={len(findings)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
