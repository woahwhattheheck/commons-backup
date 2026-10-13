#!/usr/bin/env python3
"""Synthetic/read-only controlled-sample accession documentation gate.

This module validates *documentation metadata* only. It does not classify,
handle, acquire, transfer, release, or instruct use of controlled substances.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = "triclinic-controlled-sample-intake/v1"
MANIFEST_VERSION = "triclinic-controlled-sample-fixtures/v1"
RESERVED_HUMAN_LABELS = {"SYSTEM", "AUTO", "AUTOMATION", "AI", "MODEL", "BOT", "NONE", "UNASSIGNED"}
HOLD_ORDER = (
    "MISSING_QUOTE",
    "MISSING_SDS",
    "MISSING_LOT",
    "MISSING_STORAGE",
    "MISSING_CONTROLLED_CLASSIFICATION_OR_FORM_222",
    "CONFLICTING_HANDLING_INSTRUCTIONS",
)
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,95}$")
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")

class GateError(ValueError):
    pass


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")


def sha256_hex(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def semantic_digest(value: Any) -> str:
    return sha256_hex(canonical_bytes(value))


def _expect_obj(value: Any, field: str, required: Iterable[str]) -> dict[str, Any]:
    if type(value) is not dict:
        raise GateError(f"{field} must be an object")
    wanted = set(required)
    got = set(value)
    if got != wanted:
        raise GateError(f"{field} fields mismatch missing={sorted(wanted-got)} extra={sorted(got-wanted)}")
    return value


def _identifier(value: Any, field: str) -> str:
    if type(value) is not str or not _ID_RE.fullmatch(value):
        raise GateError(f"{field} must be a canonical opaque identifier")
    return value


def _bool(value: Any, field: str) -> bool:
    if type(value) is not bool:
        raise GateError(f"{field} must be boolean")
    return value


def _text(value: Any, field: str, max_len: int = 500) -> str:
    if type(value) is not str or not value or len(value) > max_len or any(ord(ch) < 32 for ch in value):
        raise GateError(f"{field} must be bounded printable text")
    return value


def _parse_local(value: Any, field: str) -> datetime:
    if type(value) is not str:
        raise GateError(f"{field} must be ISO-8601 text")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise GateError(f"{field} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise GateError(f"{field} must include a UTC offset")
    if parsed.microsecond:
        raise GateError(f"{field} must be whole-second precision")
    return parsed


def _parse_date(value: Any, field: str) -> date:
    if type(value) is not str:
        raise GateError(f"{field} must be YYYY-MM-DD")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise GateError(f"{field} must be YYYY-MM-DD") from exc
    if parsed.isoformat() != value:
        raise GateError(f"{field} must be canonical YYYY-MM-DD")
    return parsed


@dataclass(frozen=True)
class BusinessCalendar:
    calendar_id: str
    holidays: frozenset[date]
    cutoff: time = time(12, 0, 0)

    @classmethod
    def from_manifest(cls, raw: Any) -> "BusinessCalendar":
        obj = _expect_obj(raw, "calendar", ("calendar_id", "cutoff_local", "holidays"))
        calendar_id = _identifier(obj["calendar_id"], "calendar.calendar_id")
        if obj["cutoff_local"] != "12:00:00":
            raise GateError("calendar cutoff must be the signed noon boundary 12:00:00")
        if type(obj["holidays"]) is not list or len(obj["holidays"]) > 64:
            raise GateError("calendar.holidays must be a bounded list")
        holidays = [_parse_date(v, "calendar.holidays") for v in obj["holidays"]]
        if len(holidays) != len(set(holidays)):
            raise GateError("calendar.holidays contains duplicates")
        return cls(calendar_id=calendar_id, holidays=frozenset(holidays))

    def is_business_day(self, day: date) -> bool:
        return day.weekday() < 5 and day not in self.holidays

    def next_business_day(self, day: date) -> date:
        candidate = day + timedelta(days=1)
        for _ in range(370):
            if self.is_business_day(candidate):
                return candidate
            candidate += timedelta(days=1)
        raise GateError("business calendar failed to resolve next business day")

    def queue_date(self, submitted_local: datetime) -> date:
        day = submitted_local.date()
        if not self.is_business_day(day):
            cursor = day
            while not self.is_business_day(cursor):
                cursor += timedelta(days=1)
            return cursor
        # Exact noon belongs to the next business day. Only strictly before noon stays same-day.
        if submitted_local.timetz().replace(tzinfo=None) < self.cutoff:
            return day
        return self.next_business_day(day)


def normalize_intake(raw: Any) -> dict[str, Any]:
    obj = _expect_obj(raw, "intake", (
        "schema_version", "intake_id", "submitted_local", "quote_id", "sds_present",
        "lot_id", "storage_condition", "controlled_classification_required",
        "controlled_classification_present", "form_222_required", "form_222_present",
        "handling_instruction_primary", "handling_instruction_secondary", "human_disposition_owner",
    ))
    if obj["schema_version"] != SCHEMA_VERSION:
        raise GateError("unsupported schema_version")
    intake_id = _identifier(obj["intake_id"], "intake.intake_id")
    submitted = _parse_local(obj["submitted_local"], "intake.submitted_local")
    owner = _identifier(obj["human_disposition_owner"], "intake.human_disposition_owner")
    if owner.upper() in RESERVED_HUMAN_LABELS:
        raise GateError("human_disposition_owner must name a human review actor")
    def maybe_text(v: Any, field: str) -> str | None:
        if v is None:
            return None
        return _text(v, field)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "intake_id": intake_id,
        "submitted_local": submitted.isoformat(timespec="seconds"),
        "quote_id": maybe_text(obj["quote_id"], "intake.quote_id"),
        "sds_present": _bool(obj["sds_present"], "intake.sds_present"),
        "lot_id": maybe_text(obj["lot_id"], "intake.lot_id"),
        "storage_condition": maybe_text(obj["storage_condition"], "intake.storage_condition"),
        "controlled_classification_required": _bool(obj["controlled_classification_required"], "intake.controlled_classification_required"),
        "controlled_classification_present": _bool(obj["controlled_classification_present"], "intake.controlled_classification_present"),
        "form_222_required": _bool(obj["form_222_required"], "intake.form_222_required"),
        "form_222_present": _bool(obj["form_222_present"], "intake.form_222_present"),
        "handling_instruction_primary": maybe_text(obj["handling_instruction_primary"], "intake.handling_instruction_primary"),
        "handling_instruction_secondary": maybe_text(obj["handling_instruction_secondary"], "intake.handling_instruction_secondary"),
        "human_disposition_owner": owner,
    }
    return normalized


def hold_code(intake: dict[str, Any]) -> str | None:
    if not intake["quote_id"]:
        return "MISSING_QUOTE"
    if not intake["sds_present"]:
        return "MISSING_SDS"
    if not intake["lot_id"]:
        return "MISSING_LOT"
    if not intake["storage_condition"]:
        return "MISSING_STORAGE"
    if (
        (intake["controlled_classification_required"] and not intake["controlled_classification_present"])
        or (intake["form_222_required"] and not intake["form_222_present"])
    ):
        return "MISSING_CONTROLLED_CLASSIFICATION_OR_FORM_222"
    primary = intake["handling_instruction_primary"]
    secondary = intake["handling_instruction_secondary"]
    if primary and secondary and primary != secondary:
        return "CONFLICTING_HANDLING_INSTRUCTIONS"
    return None


@dataclass
class Ledger:
    source_digests: dict[str, str] = field(default_factory=dict)
    accessions: dict[str, dict[str, Any]] = field(default_factory=dict)
    jobs: dict[str, dict[str, Any]] = field(default_factory=dict)
    reports: dict[str, dict[str, Any]] = field(default_factory=dict)

    def snapshot(self) -> dict[str, Any]:
        return {
            "source_digests": copy.deepcopy(self.source_digests),
            "accessions": copy.deepcopy(self.accessions),
            "jobs": copy.deepcopy(self.jobs),
            "reports": copy.deepcopy(self.reports),
        }

    def digest(self) -> str:
        return semantic_digest(self.snapshot())


def process_batch(raw_intakes: Any, calendar: BusinessCalendar, ledger: Ledger | None = None) -> dict[str, Any]:
    if ledger is None:
        ledger = Ledger()
    if type(raw_intakes) is not list or not raw_intakes or len(raw_intakes) > 5000:
        raise GateError("intakes must be a non-empty bounded list")
    normalized = [normalize_intake(item) for item in raw_intakes]
    ids = [item["intake_id"] for item in normalized]
    if len(ids) != len(set(ids)):
        raise GateError("batch contains duplicate intake_id")

    # Preflight every identity before any mutation. A same-ID content change fails atomically.
    digests = {item["intake_id"]: semantic_digest(item) for item in normalized}
    for intake_id, digest in digests.items():
        prior = ledger.source_digests.get(intake_id)
        if prior is not None and prior != digest:
            raise GateError(f"changed-content replay for existing intake_id {intake_id}")

    before_counts = (len(ledger.accessions), len(ledger.jobs), len(ledger.reports))
    outcomes: list[dict[str, Any]] = []
    added = 0
    held = 0
    idempotent = 0
    for intake in normalized:
        intake_id = intake["intake_id"]
        digest = digests[intake_id]
        code = hold_code(intake)
        if intake_id in ledger.source_digests:
            idempotent += 1
            outcomes.append({"intake_id": intake_id, "status": "IDEMPOTENT", "hold_code": code})
            continue
        ledger.source_digests[intake_id] = digest
        if code is not None:
            held += 1
            outcomes.append({"intake_id": intake_id, "status": "HOLD", "hold_code": code})
            continue
        submitted = _parse_local(intake["submitted_local"], "intake.submitted_local")
        queue_date = calendar.queue_date(submitted).isoformat()
        accession_id = "ACC-" + intake_id
        job_id = "JOB-" + intake_id
        report_id = "RPT-" + intake_id
        ledger.accessions[intake_id] = {
            "accession_id": accession_id,
            "intake_id": intake_id,
            "queue_date": queue_date,
            "calendar_id": calendar.calendar_id,
            "source_digest": digest,
            "state": "ACCESSIONED_DOCUMENTATION_READY",
        }
        ledger.jobs[intake_id] = {
            "job_id": job_id,
            "accession_id": accession_id,
            "state": "STAGED_NOT_RUN",
            "production_execution_authorized": False,
        }
        ledger.reports[intake_id] = {
            "report_id": report_id,
            "accession_id": accession_id,
            "queue_date": queue_date,
            "state": "STAGED_HUMAN_DISPOSITION",
            "human_disposition_owner": intake["human_disposition_owner"],
            "delivery_state": "UNSENT",
            "automatic_release_authorized": False,
        }
        added += 1
        outcomes.append({"intake_id": intake_id, "status": "READY", "hold_code": None, "queue_date": queue_date})

    after_counts = (len(ledger.accessions), len(ledger.jobs), len(ledger.reports))
    if not (after_counts[0] == after_counts[1] == after_counts[2]):
        raise GateError("ledger state count invariant violated")
    return {
        "schema_version": "triclinic-controlled-sample-result/v1",
        "calendar_id": calendar.calendar_id,
        "input_count": len(normalized),
        "added_ready": added,
        "new_holds": held,
        "idempotent": idempotent,
        "before_counts": list(before_counts),
        "after_counts": list(after_counts),
        "outcomes": outcomes,
        "ledger_digest": ledger.digest(),
        "authority": {
            "synthetic_or_deidentified_only": True,
            "classifies_controlled_substances": False,
            "handles_or_transfers_controlled_substances": False,
            "authorizes_testing": False,
            "automatic_release": False,
            "customer_or_regulator_transmission": False,
            "human_disposition_required": True,
        },
    }


def _expand_fixture_spec(spec: Any) -> list[dict[str, Any]]:
    obj = _expect_obj(spec, "fixture_spec", ("count", "base_submitted_local", "submission_overrides", "defect_ranges"))
    if type(obj["count"]) is not int or obj["count"] != 180:
        raise GateError("fixture_spec.count must be exactly 180")
    base_submitted = _parse_local(obj["base_submitted_local"], "fixture_spec.base_submitted_local").isoformat(timespec="seconds")
    if type(obj["submission_overrides"]) is not dict or type(obj["defect_ranges"]) is not list:
        raise GateError("fixture_spec overrides/ranges have invalid shape")
    intakes: list[dict[str, Any]] = []
    for i in range(obj["count"]):
        n = i + 1
        intakes.append({
            "schema_version": SCHEMA_VERSION,
            "intake_id": f"SYN-{n:03d}",
            "submitted_local": base_submitted,
            "quote_id": f"Q-{n:03d}",
            "sds_present": True,
            "lot_id": f"LOT-{n:03d}",
            "storage_condition": "AMBIENT-SYNTHETIC",
            "controlled_classification_required": False,
            "controlled_classification_present": False,
            "form_222_required": False,
            "form_222_present": False,
            "handling_instruction_primary": "STANDARD-SYNTHETIC",
            "handling_instruction_secondary": "STANDARD-SYNTHETIC",
            "human_disposition_owner": f"QA-HUMAN-{(i % 5) + 1}",
        })
    for key, submitted in obj["submission_overrides"].items():
        try:
            index = int(key) - 1
        except (TypeError, ValueError) as exc:
            raise GateError("submission override key must be 1-based integer text") from exc
        if not 0 <= index < len(intakes):
            raise GateError("submission override index outside fixture range")
        intakes[index]["submitted_local"] = _parse_local(submitted, "fixture_spec.submission_overrides").isoformat(timespec="seconds")
    allowed = {
        "MISSING_QUOTE", "MISSING_SDS", "MISSING_LOT", "MISSING_STORAGE",
        "MISSING_CONTROLLED_CLASSIFICATION_OR_FORM_222", "CONFLICTING_HANDLING_INSTRUCTIONS",
    }
    touched: set[int] = set()
    for j, raw_range in enumerate(obj["defect_ranges"]):
        rng = _expect_obj(raw_range, f"fixture_spec.defect_ranges[{j}]", ("start", "end", "kind"))
        if type(rng["start"]) is not int or type(rng["end"]) is not int or rng["kind"] not in allowed:
            raise GateError("invalid fixture defect range")
        if not (1 <= rng["start"] <= rng["end"] <= len(intakes)):
            raise GateError("fixture defect range outside bounds")
        indexes = set(range(rng["start"] - 1, rng["end"]))
        if indexes & touched:
            raise GateError("fixture defect ranges overlap")
        touched |= indexes
        for index in indexes:
            row = intakes[index]
            kind = rng["kind"]
            if kind == "MISSING_QUOTE": row["quote_id"] = None
            elif kind == "MISSING_SDS": row["sds_present"] = False
            elif kind == "MISSING_LOT": row["lot_id"] = None
            elif kind == "MISSING_STORAGE": row["storage_condition"] = None
            elif kind == "MISSING_CONTROLLED_CLASSIFICATION_OR_FORM_222":
                row["controlled_classification_required"] = True
                row["controlled_classification_present"] = False
            elif kind == "CONFLICTING_HANDLING_INSTRUCTIONS":
                row["handling_instruction_secondary"] = "CONFLICTING-SYNTHETIC"
    if len(touched) != 40:
        raise GateError("fixture_spec must encode exactly 40 defect rows")
    return intakes


def expand_bundle(raw: Any) -> dict[str, Any]:
    obj = _expect_obj(raw, "bundle", ("manifest_version", "calendar", "fixture_spec"))
    if obj["manifest_version"] != MANIFEST_VERSION:
        raise GateError("unsupported manifest_version")
    return {"manifest_version": MANIFEST_VERSION, "calendar": obj["calendar"], "intakes": _expand_fixture_spec(obj["fixture_spec"])}


def load_bundle(path: Path) -> tuple[BusinessCalendar, list[dict[str, Any]]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    expanded = expand_bundle(raw)
    return BusinessCalendar.from_manifest(expanded["calendar"]), expanded["intakes"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args(argv)
    try:
        calendar, intakes = load_bundle(args.bundle)
        ledger = Ledger()
        first = process_batch(intakes, calendar, ledger)
        replay = process_batch(intakes, calendar, ledger)
        payload = {
            "first": {k: v for k, v in first.items() if k != "outcomes"},
            "replay": {k: v for k, v in replay.items() if k != "outcomes"},
        }
        print(json.dumps(payload, sort_keys=True, indent=2 if args.pretty else None))
        return 0
    except (GateError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
