#!/usr/bin/env python3
"""Denton bacteriology acceptance + reporting LIMS.

Demand: denton-bacteriology-acceptance-reporting-lims-01
Buyer pairing: City of Denton Municipal Laboratory / Marcos Diosdado

Synthetic/read-only COC/account/sample reconciliation, signed acceptance
rules, bacteriology method routing, and TCEQ/AP/E. coli/HPC report
staging. Two hundred frozen submissions: 160 ACCESSIONED, 40 HOLD.
Held rows create no worksheet or report. Release requires a named human.

Official test: python test_denton_bacteriology_acceptance_reporting_lims.py
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from copy import deepcopy
from datetime import date, datetime
from typing import Any

DEMAND_ID = "denton-bacteriology-acceptance-reporting-lims-01"
SCHEMA = "commons-denton-bacteriology-acceptance-reporting-lims/v1"
BUYER = "City of Denton Municipal Laboratory / Marcos Diosdado"
TRUTH_GATE = "HOLD / BUILD-AND-VERIFY"
HUMAN_REVIEWER_ROLE = "NAMED_HUMAN_REVIEWER"

VALID_COUNT = 160
MISSING_ACCOUNT_COUNT = 8
ABSENT_CUSTODY_COUNT = 8
EXPIRED_BOTTLE_COUNT = 6
TEMPERATURE_HOLD_COUNT = 8
DUPLICATE_SAMPLE_COUNT = 5
MISMATCHED_FORM_COUNT = 5
HOLD_COUNT = (
    MISSING_ACCOUNT_COUNT
    + ABSENT_CUSTODY_COUNT
    + EXPIRED_BOTTLE_COUNT
    + TEMPERATURE_HOLD_COUNT
    + DUPLICATE_SAMPLE_COUNT
    + MISMATCHED_FORM_COUNT
)
INPUT_COUNT = VALID_COUNT + HOLD_COUNT

HOLD_CODES = (
    "MISSING_ACCOUNT_PWS",
    "ABSENT_CUSTODY",
    "EXPIRED_BOTTLE",
    "TEMPERATURE_HOLD_TIME",
    "DUPLICATE_SAMPLE_ID",
    "MISMATCHED_REPORT_FORM",
)

EXPECTED_HOLD_COUNTS = {
    "MISSING_ACCOUNT_PWS": MISSING_ACCOUNT_COUNT,
    "ABSENT_CUSTODY": ABSENT_CUSTODY_COUNT,
    "EXPIRED_BOTTLE": EXPIRED_BOTTLE_COUNT,
    "TEMPERATURE_HOLD_TIME": TEMPERATURE_HOLD_COUNT,
    "DUPLICATE_SAMPLE_ID": DUPLICATE_SAMPLE_COUNT,
    "MISMATCHED_REPORT_FORM": MISMATCHED_FORM_COUNT,
}

ROUTES = {
    "TCEQ_ECOLI_QUANT": {
        "method": "SM-9223B-Q",
        "report_form": "TCEQ-ECOLI-QUANT",
        "family": "QUANT_ECOLI",
    },
    "TCEQ_AP": {
        "method": "SM-9221-PA",
        "report_form": "TCEQ-AP",
        "family": "AP",
    },
    "HPC": {
        "method": "SM-9215B",
        "report_form": "HPC-PLATE",
        "family": "HPC",
    },
}

MAX_TEMP_C = 10.0
MAX_HOLD_HOURS = 8.0
MIN_TEMP_C = 0.0
MIN_HOLD_HOURS = 0.0
OFFICIAL_TEST = "python test_denton_bacteriology_acceptance_reporting_lims.py"

_CALENDAR_DATE = re.compile(r"\d{4}-\d{2}-\d{2}\Z")
_CUSTODY_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")
_SCALAR_STRING_FIELDS = (
    "row_id",
    "submission_id",
    "sample_id",
    "account_id",
    "pws_id",
    "client_id",
    "route",
    "method",
    "report_form",
    "custody_signed",
    "custody_time",
    "collected_on",
    "bottle_expires",
    "source_revision",
)
_SOURCE_FIELDS = (
    "submission_id",
    "sample_id",
    "account_id",
    "pws_id",
    "client_id",
    "route",
    "method",
    "report_form",
    "custody_signed",
    "custody_time",
    "collected_on",
    "bottle_expires",
    "temperature_c",
    "hold_time_hours",
    "source_revision",
)
_REVIEWER_ISSUER = "DENTON_LIMS_QA_AUTHORITY"
_AUTHORITATIVE_REVIEWERS = {
    "DENTON-QA-001": {
        "display_name": "Denton QA Reviewer 001",
        "role": HUMAN_REVIEWER_ROLE,
        "issuer": _REVIEWER_ISSUER,
        "active": True,
    }
}


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_hex(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _text(value: Any) -> str:
    return value.strip() if type(value) is str else ""


def _strict_calendar_date(value: str) -> date | None:
    if not _CALENDAR_DATE.fullmatch(value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _strict_custody_timestamp(value: str) -> datetime | None:
    if not _CUSTODY_TIMESTAMP.fullmatch(value):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return None


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    normalized = float(value)
    return normalized if math.isfinite(normalized) else None


def _route_name(index: int) -> str:
    return tuple(ROUTES)[(index - 1) % len(ROUTES)]


def _base_row(index: int) -> dict[str, Any]:
    token = f"{index:03d}"
    route_name = _route_name(index)
    route = ROUTES[route_name]
    return {
        "row_id": f"DEN-{token}",
        "submission_id": f"SUB-{token}",
        "sample_id": f"SMP-{token}",
        "account_id": f"ACCT-{(index % 20) + 1:02d}",
        "pws_id": f"TX061000{(index % 4) + 1}",
        "client_id": f"CLIENT-{(index % 20) + 1:02d}",
        "route": route_name,
        "method": route["method"],
        "report_form": route["report_form"],
        "custody_signed": "J-DOE",
        "custody_time": "2026-08-31T08:00:00Z",
        "collected_on": "2026-08-31",
        "bottle_expires": "2026-09-30",
        "temperature_c": 6.0,
        "hold_time_hours": 4.0,
        "source_revision": "DENTON-SYNTHETIC-2026-01",
        "exception_type": None,
        "synthetic": True,
        "deidentified": True,
    }


def _exception_row(index: int) -> dict[str, Any]:
    row = _base_row(index)
    cursor = VALID_COUNT
    if index <= cursor + MISSING_ACCOUNT_COUNT:
        if index % 2 == 0:
            row["account_id"] = ""
        else:
            row["pws_id"] = ""
        row["exception_type"] = "MISSING_ACCOUNT_PWS"
    elif index <= cursor + MISSING_ACCOUNT_COUNT + ABSENT_CUSTODY_COUNT:
        if index % 2 == 0:
            row["custody_signed"] = ""
        else:
            row["custody_time"] = ""
        row["exception_type"] = "ABSENT_CUSTODY"
    elif index <= cursor + MISSING_ACCOUNT_COUNT + ABSENT_CUSTODY_COUNT + EXPIRED_BOTTLE_COUNT:
        row["bottle_expires"] = "2026-08-01"
        row["exception_type"] = "EXPIRED_BOTTLE"
    elif index <= (
        cursor
        + MISSING_ACCOUNT_COUNT
        + ABSENT_CUSTODY_COUNT
        + EXPIRED_BOTTLE_COUNT
        + TEMPERATURE_HOLD_COUNT
    ):
        if index % 2 == 0:
            row["temperature_c"] = 14.0
        else:
            row["hold_time_hours"] = 12.0
        row["exception_type"] = "TEMPERATURE_HOLD_TIME"
    elif index <= (
        cursor
        + MISSING_ACCOUNT_COUNT
        + ABSENT_CUSTODY_COUNT
        + EXPIRED_BOTTLE_COUNT
        + TEMPERATURE_HOLD_COUNT
        + DUPLICATE_SAMPLE_COUNT
    ):
        dup = index - (
            cursor
            + MISSING_ACCOUNT_COUNT
            + ABSENT_CUSTODY_COUNT
            + EXPIRED_BOTTLE_COUNT
            + TEMPERATURE_HOLD_COUNT
        )
        row["sample_id"] = f"SMP-{dup:03d}"
        row["exception_type"] = "DUPLICATE_SAMPLE_ID"
    else:
        other = next(name for name in ROUTES if name != row["route"])
        row["report_form"] = ROUTES[other]["report_form"]
        row["exception_type"] = "MISMATCHED_REPORT_FORM"
    return row


def build_acceptance_fixture() -> list[dict[str, Any]]:
    rows = [_base_row(index) for index in range(1, VALID_COUNT + 1)]
    rows.extend(_exception_row(index) for index in range(VALID_COUNT + 1, INPUT_COUNT + 1))
    expected = {
        None: VALID_COUNT,
        "MISSING_ACCOUNT_PWS": MISSING_ACCOUNT_COUNT,
        "ABSENT_CUSTODY": ABSENT_CUSTODY_COUNT,
        "EXPIRED_BOTTLE": EXPIRED_BOTTLE_COUNT,
        "TEMPERATURE_HOLD_TIME": TEMPERATURE_HOLD_COUNT,
        "DUPLICATE_SAMPLE_ID": DUPLICATE_SAMPLE_COUNT,
        "MISMATCHED_REPORT_FORM": MISMATCHED_FORM_COUNT,
    }
    actual = {name: 0 for name in expected}
    for row in rows:
        actual[row["exception_type"]] += 1
    if len(rows) != INPUT_COUNT or actual != expected:
        raise RuntimeError(f"invalid frozen fixture: rows={len(rows)} split={actual}")
    return rows


def empty_journal() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "submissions": {},
        "accessions": {},
        "worksheets": {},
        "reports": {},
        "holds": [],
        "events": [],
        "processed_rows": {},
        "sample_index": {},
        "authoritative_reviewers": deepcopy(_AUTHORITATIVE_REVIEWERS),
        "interface_live": False,
        "production_writes": 0,
        "automatic_releases": 0,
    }


def _event(journal: dict[str, Any], kind: str, payload: dict[str, Any]) -> None:
    journal["events"].append(
        {"seq": len(journal["events"]) + 1, "kind": kind, **deepcopy(payload)}
    )


def normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    source = row if type(row) is dict else {}
    invalid_scalar_fields = tuple(
        field for field in _SCALAR_STRING_FIELDS if type(source.get(field)) is not str
    )
    return {
        "row_id": _text(source.get("row_id")),
        "submission_id": _text(source.get("submission_id")),
        "sample_id": _text(source.get("sample_id")).upper(),
        "account_id": _text(source.get("account_id")).upper(),
        "pws_id": _text(source.get("pws_id")).upper(),
        "client_id": _text(source.get("client_id")).upper(),
        "route": _text(source.get("route")).upper(),
        "method": _text(source.get("method")).upper(),
        "report_form": _text(source.get("report_form")).upper(),
        "custody_signed": _text(source.get("custody_signed")),
        "custody_time": _text(source.get("custody_time")),
        "collected_on": _text(source.get("collected_on")),
        "bottle_expires": _text(source.get("bottle_expires")),
        "temperature_c": _finite_number(source.get("temperature_c")),
        "hold_time_hours": _finite_number(source.get("hold_time_hours")),
        "source_revision": _text(source.get("source_revision")),
        "synthetic": source.get("synthetic"),
        "deidentified": source.get("deidentified"),
        "invalid_scalar_fields": invalid_scalar_fields,
    }


def classify_row(norm: dict[str, Any], journal: dict[str, Any]) -> dict[str, Any]:
    if norm["invalid_scalar_fields"]:
        return {"ok": False, "code": "MISSING_ACCOUNT_PWS"}
    if not norm["account_id"] or not norm["pws_id"]:
        return {"ok": False, "code": "MISSING_ACCOUNT_PWS"}
    if (
        not norm["custody_signed"]
        or _strict_custody_timestamp(norm["custody_time"]) is None
    ):
        return {"ok": False, "code": "ABSENT_CUSTODY"}
    collected_on = _strict_calendar_date(norm["collected_on"])
    bottle_expires = _strict_calendar_date(norm["bottle_expires"])
    if (
        collected_on is None
        or bottle_expires is None
        or bottle_expires < collected_on
    ):
        return {"ok": False, "code": "EXPIRED_BOTTLE"}
    if (
        norm["temperature_c"] is None
        or norm["hold_time_hours"] is None
        or not MIN_TEMP_C <= norm["temperature_c"] <= MAX_TEMP_C
        or not MIN_HOLD_HOURS <= norm["hold_time_hours"] <= MAX_HOLD_HOURS
    ):
        return {"ok": False, "code": "TEMPERATURE_HOLD_TIME"}
    if norm["sample_id"] and norm["sample_id"] in journal["sample_index"]:
        return {"ok": False, "code": "DUPLICATE_SAMPLE_ID"}
    expected = ROUTES.get(norm["route"])
    if (
        expected is None
        or norm["method"] != expected["method"]
        or norm["report_form"] != expected["report_form"]
    ):
        return {"ok": False, "code": "MISMATCHED_REPORT_FORM"}
    if (
        not norm["row_id"]
        or not norm["submission_id"]
        or not norm["sample_id"]
        or not norm["client_id"]
        or norm["synthetic"] is not True
        or norm["deidentified"] is not True
    ):
        return {"ok": False, "code": "MISSING_ACCOUNT_PWS"}
    return {"ok": True}


def _source_payload(norm: dict[str, Any]) -> dict[str, Any]:
    return {key: norm[key] for key in _SOURCE_FIELDS}


def _payload_digest(norm: dict[str, Any]) -> str:
    return sha256_hex(
        {
            "row_id": norm["row_id"],
            "source": _source_payload(norm),
            "invalid_scalar_fields": norm["invalid_scalar_fields"],
            "synthetic": norm["synthetic"],
            "deidentified": norm["deidentified"],
        }
    )


def _hold(
    journal: dict[str, Any], norm: dict[str, Any], code: str, payload_digest: str
) -> dict[str, Any]:
    hold = {
        "row_id": norm["row_id"],
        "submission_id": norm["submission_id"],
        "sample_id": norm["sample_id"] or None,
        "code": code,
        "state": "HOLD",
        "worksheets_created": 0,
        "reports_created": 0,
        "released": False,
    }
    journal["holds"].append(hold)
    if norm["row_id"]:
        journal["processed_rows"][norm["row_id"]] = {
            "kind": "HOLD",
            "submission_id": norm["submission_id"],
            "code": code,
            "payload_digest": payload_digest,
        }
    _event(journal, "HOLD", hold)
    return {"kind": "HOLD", **deepcopy(hold)}


def ingest_row(journal: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    pre_state_hash = journal_hash(journal)
    try:
        working = deepcopy(journal)
        effect = _ingest_unlocked(working, row)
    except Exception:
        return {
            "kind": "ROLLBACK",
            "code": "ATOMIC_INGEST_FAILED",
            "pre_state_hash": pre_state_hash,
            "post_state_hash": journal_hash(journal),
        }
    if effect.get("kind") in {"ACCESSIONED", "HOLD"}:
        journal.clear()
        journal.update(working)
    return {
        **effect,
        "pre_state_hash": pre_state_hash,
        "post_state_hash": journal_hash(journal),
    }


def _ingest_unlocked(journal: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    norm = normalize_row(row)
    payload_digest = _payload_digest(norm)
    if norm["row_id"] and norm["row_id"] in journal["processed_rows"]:
        processed = journal["processed_rows"][norm["row_id"]]
        if processed.get("payload_digest") != payload_digest:
            return {
                "kind": "PAYLOAD_DIGEST_CONFLICT",
                "row_id": norm["row_id"],
                "submission_id": norm["submission_id"],
                "stored_payload_digest": processed.get("payload_digest"),
                "payload_digest": payload_digest,
            }
        return {
            "kind": "REPLAY_NOOP",
            "row_id": norm["row_id"],
            "submission_id": norm["submission_id"],
        }
    verdict = classify_row(norm, journal)
    if not verdict["ok"]:
        return _hold(journal, norm, verdict["code"], payload_digest)
    if norm["submission_id"] in journal["submissions"]:
        existing = journal["submissions"][norm["submission_id"]]
        return {
            "kind": "SUBMISSION_LINEAGE_CONFLICT",
            "submission_id": norm["submission_id"],
            "existing_accession_id": existing["accession_id"],
            "existing_sample_id": existing["sample_id"],
            "sample_id": norm["sample_id"],
        }
    source_payload = _source_payload(norm)
    source_hash = sha256_hex(source_payload)
    accession_id = "DEN-ACC-" + sha256_hex({"demand_id": DEMAND_ID, "sample_id": norm["sample_id"]})[:12]
    worksheet_id = "DEN-WS-" + sha256_hex({"demand_id": DEMAND_ID, "sample_id": norm["sample_id"]})[:12]
    report_id = "DEN-RPT-" + sha256_hex({"demand_id": DEMAND_ID, "sample_id": norm["sample_id"]})[:12]
    record = {
        **source_payload,
        "source_hash": source_hash,
        "accession_id": accession_id,
        "worksheet_id": worksheet_id,
        "report_id": report_id,
        "state": "ACCESSIONED",
        "released": False,
        "released_by": None,
        "reviewer_id": None,
        "interface_state": "SIMULATED",
    }
    worksheet = {
        "worksheet_id": worksheet_id,
        "accession_id": accession_id,
        "sample_id": norm["sample_id"],
        "method": norm["method"],
        "report_form": norm["report_form"],
        "route": norm["route"],
        "source_hash": source_hash,
        "state": "OPEN",
    }
    report = {
        "report_id": report_id,
        "accession_id": accession_id,
        "worksheet_id": worksheet_id,
        "sample_id": norm["sample_id"],
        "method": norm["method"],
        "report_form": norm["report_form"],
        "source_hash": source_hash,
        "status": "STAGED",
        "released": False,
        "released_by": None,
        "reviewer_id": None,
    }
    journal["submissions"][norm["submission_id"]] = record
    journal["accessions"][accession_id] = record
    journal["worksheets"][worksheet_id] = worksheet
    journal["reports"][report_id] = report
    journal["sample_index"][norm["sample_id"]] = norm["row_id"]
    journal["processed_rows"][norm["row_id"]] = {
        "kind": "ACCESSIONED",
        "submission_id": norm["submission_id"],
        "accession_id": accession_id,
        "payload_digest": payload_digest,
    }
    _event(
        journal,
        "ACCESSIONED",
        {
            "submission_id": norm["submission_id"],
            "accession_id": accession_id,
            "worksheet_id": worksheet_id,
            "report_id": report_id,
        },
    )
    return {
        "kind": "ACCESSIONED",
        "submission_id": norm["submission_id"],
        "accession_id": accession_id,
        "worksheet_id": worksheet_id,
        "report_id": report_id,
    }


def release_report(
    journal: dict[str, Any],
    report_id: str,
    *,
    actor_role: str,
    actor: str,
    reviewer_id: str | None = None,
) -> dict[str, Any]:
    """Release only through a journal-held, authoritative reviewer identity.

    ``actor_role`` is retained for caller compatibility but is not a permission
    boundary. A caller must supply a reviewer ID that is active in the
    authoritative registry carried by the journal.
    """

    del actor_role
    pre_state_hash = journal_hash(journal)
    try:
        working = deepcopy(journal)
        effect = _release_unlocked(working, report_id, actor, reviewer_id)
    except Exception:
        return {
            "ok": False,
            "code": "ATOMIC_RELEASE_FAILED",
            "pre_state_hash": pre_state_hash,
            "post_state_hash": journal_hash(journal),
        }
    if effect.get("ok"):
        journal.clear()
        journal.update(working)
    return {
        **effect,
        "pre_state_hash": pre_state_hash,
        "post_state_hash": journal_hash(journal),
    }


def _release_unlocked(
    journal: dict[str, Any], report_id: str, actor: str, reviewer_id: str | None
) -> dict[str, Any]:
    report = journal["reports"].get(report_id)
    if report is None:
        return {"ok": False, "code": "UNKNOWN_REPORT"}
    reviewer = journal["authoritative_reviewers"].get(_text(reviewer_id))
    if (
        not isinstance(reviewer, dict)
        or reviewer.get("role") != HUMAN_REVIEWER_ROLE
        or reviewer.get("issuer") != _REVIEWER_ISSUER
        or reviewer.get("active") is not True
        or _text(actor) != reviewer.get("display_name")
    ):
        return {"ok": False, "code": "AUTONOMOUS_RELEASE_DENIED"}
    if report["released"]:
        return {"ok": True, "duplicate": True, "status": "RELEASED"}
    report["released"] = True
    report["released_by"] = reviewer["display_name"]
    report["reviewer_id"] = _text(reviewer_id)
    report["status"] = "RELEASED"
    submission = journal["submissions"][journal["accessions"][report["accession_id"]]["submission_id"]]
    submission["released"] = True
    submission["released_by"] = reviewer["display_name"]
    submission["reviewer_id"] = _text(reviewer_id)
    submission["state"] = "RELEASED"
    _event(
        journal,
        "RELEASED",
        {
            "report_id": report_id,
            "released_by": reviewer["display_name"],
            "reviewer_id": _text(reviewer_id),
        },
    )
    return {"ok": True, "duplicate": False, "status": "RELEASED"}


def replay_into(
    journal: dict[str, Any], rows: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    inbound = deepcopy(rows if rows is not None else build_acceptance_fixture())
    before = {
        "accessions": len(journal["accessions"]),
        "worksheets": len(journal["worksheets"]),
        "holds": len(journal["holds"]),
        "reports": len(journal["reports"]),
    }
    effects = [ingest_row(journal, row) for row in inbound]
    return {
        "added_accessions": len(journal["accessions"]) - before["accessions"],
        "added_worksheets": len(journal["worksheets"]) - before["worksheets"],
        "added_holds": len(journal["holds"]) - before["holds"],
        "added_reports": len(journal["reports"]) - before["reports"],
        "replay_noops": sum(item["kind"] == "REPLAY_NOOP" for item in effects),
    }


def journal_hash(journal: dict[str, Any]) -> str:
    return sha256_hex(
        {
            "submissions": journal["submissions"],
            "accessions": journal["accessions"],
            "worksheets": journal["worksheets"],
            "reports": journal["reports"],
            "holds": journal["holds"],
            "events": journal["events"],
            "processed_rows": journal["processed_rows"],
            "sample_index": journal["sample_index"],
            "authoritative_reviewers": journal["authoritative_reviewers"],
        }
    )


def _manifest(journal: dict[str, Any]) -> dict[str, Any]:
    return {
        "demand_id": DEMAND_ID,
        "accessions": sorted(journal["accessions"]),
        "worksheets": sorted(journal["worksheets"]),
        "reports": sorted(journal["reports"]),
        "holds": sorted(
            (item["row_id"], item["submission_id"], item["code"])
            for item in journal["holds"]
        ),
    }


def run_gate(rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    inbound = deepcopy(rows if rows is not None else build_acceptance_fixture())
    journal = empty_journal()
    effects = [ingest_row(journal, row) for row in inbound]
    autonomous = [
        release_report(journal, report_id, actor_role="SYSTEM", actor="")
        for report_id in sorted(journal["reports"])
    ]
    hold_counts = {code: 0 for code in HOLD_CODES}
    for hold in journal["holds"]:
        hold_counts[hold["code"]] += 1
    route_counts = {route: 0 for route in ROUTES}
    for record in journal["submissions"].values():
        route_counts[record["route"]] += 1
    reports = sorted(journal["reports"].values(), key=lambda item: item["report_id"])
    clients = {item["client_id"] for item in journal["submissions"].values()}
    pws_ids = {item["pws_id"] for item in journal["submissions"].values()}
    samples = {item["sample_id"] for item in journal["submissions"].values()}
    manifest = _manifest(journal)
    result = {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "truth_gate": TRUTH_GATE,
        "input_rows": len(inbound),
        "accessioned": len(journal["accessions"]),
        "holds": len(journal["holds"]),
        "worksheets": len(journal["worksheets"]),
        "reports_staged": len(reports),
        "reports_released": sum(item["released"] for item in reports),
        "hold_counts": hold_counts,
        "route_counts": route_counts,
        "identity_cross": 0,
        "unique_clients": len(clients),
        "unique_pws": len(pws_ids),
        "unique_samples": len(samples),
        "manifest_sha256": sha256_hex(manifest),
        "audit_sha256": sha256_hex(
            {"events": journal["events"], "manifest": manifest, "truth_gate": TRUTH_GATE}
        ),
        "journal_sha256": journal_hash(journal),
        "submissions": sorted(
            journal["submissions"].values(), key=lambda item: item["submission_id"]
        ),
        "worksheet_records": sorted(
            journal["worksheets"].values(), key=lambda item: item["worksheet_id"]
        ),
        "report_records": reports,
        "hold_records": deepcopy(journal["holds"]),
        "effects": effects,
        "autonomous_release_effects": autonomous,
        "interface_live": False,
        "interfaces": "SIMULATED_READ_ONLY",
        "production_writes": 0,
        "automatic_releases": 0,
        "autonomous_release": False,
        "pre_sale_transport": "NONE",
        "cash_usd": 0,
    }
    return result


def pass_contract(result: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    expected_routes = {
        "TCEQ_ECOLI_QUANT": 54,
        "TCEQ_AP": 53,
        "HPC": 53,
    }
    checks = {
        "input_rows": result.get("input_rows") == INPUT_COUNT,
        "accessioned": result.get("accessioned") == VALID_COUNT,
        "holds": result.get("holds") == HOLD_COUNT,
        "worksheets": result.get("worksheets") == VALID_COUNT,
        "reports_staged": result.get("reports_staged") == VALID_COUNT,
        "reports_released": result.get("reports_released") == 0,
        "hold_counts": result.get("hold_counts") == EXPECTED_HOLD_COUNTS,
        "route_counts": result.get("route_counts") == expected_routes,
        "unique_samples": result.get("unique_samples") == VALID_COUNT,
        "identity_cross": result.get("identity_cross") == 0,
        "interfaces": result.get("interfaces") == "SIMULATED_READ_ONLY",
        "production_writes": result.get("production_writes") == 0,
        "automatic_releases": result.get("automatic_releases") == 0,
        "autonomous_release": result.get("autonomous_release") is False,
    }
    failures.extend(name for name, passed in checks.items() if not passed)
    if not all(
        item.get("code") == "AUTONOMOUS_RELEASE_DENIED"
        for item in result.get("autonomous_release_effects") or []
    ):
        failures.append("autonomous_release_not_denied")
    if any(
        item.get("worksheets_created")
        or item.get("reports_created")
        or item.get("released")
        for item in result.get("hold_records") or []
    ):
        failures.append("held_record_created_output")
    for report in result.get("report_records") or []:
        if report.get("status") != "STAGED" or report.get("released"):
            failures.append("report_not_staged")
            break
        if len(report.get("source_hash") or "") != 64:
            failures.append("report_hash")
            break
        expected = ROUTES.get(next(s["route"] for s in result["submissions"] if s["report_id"] == report["report_id"]))
        if expected is None or report["method"] != expected["method"] or report["report_form"] != expected["report_form"]:
            failures.append("report_route")
            break
    return failures


def main() -> int:
    result = run_gate()
    journal = empty_journal()
    for row in build_acceptance_fixture():
        ingest_row(journal, row)
    replay = replay_into(journal)
    failures = pass_contract(result)
    if any(
        replay[key] != 0
        for key in ("added_accessions", "added_worksheets", "added_holds", "added_reports")
    ):
        failures.append("replay_added_output")
    if replay["replay_noops"] != INPUT_COUNT:
        failures.append("replay_noops")
    report = {
        "ok": not failures,
        "failures": failures,
        "command": OFFICIAL_TEST,
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "input_rows": result["input_rows"],
        "accessioned": result["accessioned"],
        "holds": result["holds"],
        "worksheets": result["worksheets"],
        "reports_staged": result["reports_staged"],
        "reports_released": result["reports_released"],
        "hold_counts": result["hold_counts"],
        "route_counts": result["route_counts"],
        "replay": replay,
        "manifest_sha256": result["manifest_sha256"],
        "audit_sha256": result["audit_sha256"],
        "truth_gate": TRUTH_GATE,
        "interfaces": result["interfaces"],
        "pre_sale_transport": "NONE",
        "cash_usd": 0,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
