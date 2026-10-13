#!/usr/bin/env python3
"""Prein&Newhof PFAS field-blank and custody gate.

COC/bottle reconciliation across Grand Rapids, Holland, and Muskegon
drop-off paths. PFAS field-blank binding. Preservation and receipt-window
checks. Method routing. Staged portal result. Human release only.

Demand: preinnewhof-pfas-fieldblank-gate-lims-01
Buyer pairing: Prein&Newhof Environmental Laboratory / Steve Bylsma

Public intake facts used as fixture constants (not a live interface):
- Three drop-off locations: Grand Rapids, Holland, Muskegon
- PFAS-certified drinking-water / wastewater testing
- Field blank required before a result may enter the portal
- Downloadable general/residential chain-of-custody forms

AquaTrace HOLD / BUILD-AND-VERIFY. Synthetic fixtures only.
Adapters stay simulated/read-only. No production writes. No outreach.
No automatic portal release. PRE-SALE TRANSPORT: NONE.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime, time, timedelta
from typing import Any

DEMAND_ID = "preinnewhof-pfas-fieldblank-gate-lims-01"
SCHEMA = "commons-preinnewhof-pfas-fieldblank-gate-lims/v1"
TRUTH_GATE = "HOLD / BUILD-AND-VERIFY"
HUMAN_RELEASER = "RELEASER"
FIXTURE_COUNT = 150
VALID_COUNT = 120
HOLD_COUNT = 30
HOLD_PER_CODE = 5
RECEIPT_HOLD_DAYS = 14
DROPOFF_OPEN = time(8, 0)
DROPOFF_CLOSE = time(17, 0)

HOLD_MISSING_FIELD_BLANK = "HOLD_MISSING_FIELD_BLANK"
HOLD_BOTTLE_COC_MISMATCH = "HOLD_BOTTLE_COC_MISMATCH"
HOLD_DUPLICATE_SAMPLE_ID = "HOLD_DUPLICATE_SAMPLE_ID"
HOLD_INVALID_RECEIPT_WINDOW = "HOLD_INVALID_RECEIPT_WINDOW"
HOLD_WRONG_PRESERVATION = "HOLD_WRONG_PRESERVATION"
HOLD_UNSUPPORTED_METHOD_LOCATION = "HOLD_UNSUPPORTED_METHOD_LOCATION"

HOLD_CODES = (
    HOLD_MISSING_FIELD_BLANK,
    HOLD_BOTTLE_COC_MISMATCH,
    HOLD_DUPLICATE_SAMPLE_ID,
    HOLD_INVALID_RECEIPT_WINDOW,
    HOLD_WRONG_PRESERVATION,
    HOLD_UNSUPPORTED_METHOD_LOCATION,
)

LOCATIONS: dict[str, dict[str, Any]] = {
    "GRAND_RAPIDS": {
        "code": "GR",
        "name": "Grand Rapids drop-off",
        "offset": "-04:00",
        "methods": ("EPA_533", "EPA_537_1"),
        "matrix": "DRINKING_WATER",
        "preservation": "PFAS_TRIZMA",
    },
    "HOLLAND": {
        "code": "HOL",
        "name": "Holland drop-off",
        "offset": "-04:00",
        "methods": ("EPA_533", "EPA_537_1"),
        "matrix": "DRINKING_WATER",
        "preservation": "PFAS_TRIZMA",
    },
    "MUSKEGON": {
        "code": "MUS",
        "name": "Muskegon drop-off",
        "offset": "-04:00",
        "methods": ("EPA_1633",),
        "matrix": "WASTEWATER",
        "preservation": "PFAS_ICE_METHANOL",
    },
}

LOCATION_ORDER = ("GRAND_RAPIDS", "HOLLAND", "MUSKEGON")
METHOD_PANEL = {
    "EPA_533": "PFAS_DRINKING_WATER_533",
    "EPA_537_1": "PFAS_DRINKING_WATER_537",
    "EPA_1633": "PFAS_WASTEWATER_1633",
}


def _text(value: Any) -> str:
    return str("" if value is None else value).strip()


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_hex(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def parse_ts(value: Any) -> datetime | None:
    text = _text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def accession_id(location: str, sample_id: str, method: str) -> str:
    digest = sha256_hex(
        {
            "demand_id": DEMAND_ID,
            "location": location,
            "sample_id": sample_id,
            "method": method,
        }
    )
    code = LOCATIONS[location]["code"]
    return f"PN-{code}-{digest[:10]}"


def field_blank_parentage(sample_id: str, field_blank_id: str, method: str) -> dict[str, Any]:
    payload = {
        "sample_id": sample_id,
        "field_blank_id": field_blank_id,
        "method": method,
        "kind": "pfas_field_blank_bind",
    }
    return {
        "sample_id": sample_id,
        "field_blank_id": field_blank_id,
        "method": method,
        "parentage_sha256": sha256_hex(payload),
    }


def source_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "sample_id": _text(row.get("sample_id")),
        "location": _text(row.get("location")),
        "method": _text(row.get("method")),
        "matrix": _text(row.get("matrix")),
        "bottle_id": _text(row.get("bottle_id")),
        "coc_id": _text(row.get("coc_id")),
        "field_blank_id": _text(row.get("field_blank_id")),
        "preservation": _text(row.get("preservation")),
        "collected_at": _text(row.get("collected_at")),
        "received_at": _text(row.get("received_at")),
        "source_image_id": _text(row.get("source_image_id")),
    }


def custody_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "sample_id": _text(row.get("sample_id")),
        "location": _text(row.get("location")),
        "custody_location": _text(row.get("custody_location")),
        "coc_id": _text(row.get("coc_id")),
        "coc_bottles": list(row.get("coc_bottles") or []),
        "bottle_id": _text(row.get("bottle_id")),
        "field_blank_bottle_id": _text(row.get("field_blank_bottle_id")),
        "collected_at": _text(row.get("collected_at")),
        "received_at": _text(row.get("received_at")),
    }


def source_hash(row: dict[str, Any]) -> str:
    return sha256_hex(source_payload(row))


def custody_hash(row: dict[str, Any]) -> str:
    return sha256_hex(custody_payload(row))


def image_hash(row: dict[str, Any]) -> str:
    return sha256_hex(
        {
            "source_image_id": _text(row.get("source_image_id")),
            "coc_id": _text(row.get("coc_id")),
            "bottle_id": _text(row.get("bottle_id")),
            "location": _text(row.get("location")),
        }
    )


def hashes_reconcile(row: dict[str, Any]) -> bool:
    if _text(row.get("source_hash")) != source_hash(row):
        return False
    if _text(row.get("custody_hash")) != custody_hash(row):
        return False
    if _text(row.get("image_sha256")) != image_hash(row):
        return False
    if _text(row.get("custody_location")) != _text(row.get("location")):
        return False
    return True


def _stamp_hashes(row: dict[str, Any]) -> dict[str, Any]:
    row["source_hash"] = source_hash(row)
    row["custody_hash"] = custody_hash(row)
    row["image_sha256"] = image_hash(row)
    return row


def _valid_times(location: str) -> tuple[str, str]:
    offset = LOCATIONS[location]["offset"]
    return (
        f"2026-07-14T08:15:00{offset}",
        f"2026-07-14T14:30:00{offset}",
    )


def _late_times(location: str) -> tuple[str, str]:
    offset = LOCATIONS[location]["offset"]
    return (
        f"2026-07-14T08:15:00{offset}",
        f"2026-08-04T10:00:00{offset}",
    )


def _base_row(
    *,
    index: int,
    location: str,
    method: str,
    sample_id: str,
    field_blank_id: str,
    bottle_id: str,
    field_blank_bottle_id: str,
    coc_id: str,
    coc_bottles: list[str],
    collected_at: str,
    received_at: str,
    preservation: str,
    truth: str,
    custody_location: str | None = None,
) -> dict[str, Any]:
    spec = LOCATIONS[location]
    row = {
        "row_id": f"R{index:03d}",
        "sample_id": sample_id,
        "field_blank_id": field_blank_id,
        "location": location,
        "custody_location": custody_location or location,
        "method": method,
        "matrix": spec["matrix"],
        "panel": METHOD_PANEL[method],
        "preservation": preservation,
        "bottle_id": bottle_id,
        "field_blank_bottle_id": field_blank_bottle_id,
        "coc_id": coc_id,
        "coc_bottles": list(coc_bottles),
        "collected_at": collected_at,
        "received_at": received_at,
        "source_image_id": f"IMG-{index:03d}",
        "truth": truth,
    }
    return _stamp_hashes(row)


def _valid_row(index: int, slot: int) -> dict[str, Any]:
    location = LOCATION_ORDER[slot % 3]
    methods = LOCATIONS[location]["methods"]
    method = methods[slot % len(methods)]
    collected_at, received_at = _valid_times(location)
    sample_id = f"PN-W-{slot + 1:04d}"
    field_blank_id = f"PN-FB-{slot + 1:04d}"
    bottle_id = f"B-{slot + 1:04d}"
    fb_bottle = f"FB-{slot + 1:04d}"
    return _base_row(
        index=index,
        location=location,
        method=method,
        sample_id=sample_id,
        field_blank_id=field_blank_id,
        bottle_id=bottle_id,
        field_blank_bottle_id=fb_bottle,
        coc_id=f"COC-{slot + 1:04d}",
        coc_bottles=[bottle_id, fb_bottle],
        collected_at=collected_at,
        received_at=received_at,
        preservation=LOCATIONS[location]["preservation"],
        truth="VALID",
    )


def build_acceptance_fixture() -> list[dict[str, Any]]:
    """150 frozen water submissions: 120 valid, 30 exact HOLD codes."""
    rows: list[dict[str, Any]] = []
    index = 1

    for slot in range(VALID_COUNT):
        rows.append(_valid_row(index, slot))
        index += 1

    for i in range(HOLD_PER_CODE):
        location = LOCATION_ORDER[i % 3]
        methods = LOCATIONS[location]["methods"]
        method = methods[i % len(methods)]
        collected_at, received_at = _valid_times(location)
        bottle_id = f"B-MFB-{i + 1:02d}"
        fb_bottle = f"FB-MFB-{i + 1:02d}"
        rows.append(
            _base_row(
                index=index,
                location=location,
                method=method,
                sample_id=f"PN-H-MFB-{i + 1:02d}",
                field_blank_id="",
                bottle_id=bottle_id,
                field_blank_bottle_id=fb_bottle,
                coc_id=f"COC-MFB-{i + 1:02d}",
                coc_bottles=[bottle_id, fb_bottle],
                collected_at=collected_at,
                received_at=received_at,
                preservation=LOCATIONS[location]["preservation"],
                truth=HOLD_MISSING_FIELD_BLANK,
            )
        )
        index += 1

    for i in range(HOLD_PER_CODE):
        location = LOCATION_ORDER[i % 3]
        methods = LOCATIONS[location]["methods"]
        method = methods[i % len(methods)]
        collected_at, received_at = _valid_times(location)
        bottle_id = f"B-COC-{i + 1:02d}"
        other = f"B-OTHER-{i + 1:02d}"
        fb_bottle = f"FB-COC-{i + 1:02d}"
        rows.append(
            _base_row(
                index=index,
                location=location,
                method=method,
                sample_id=f"PN-H-COC-{i + 1:02d}",
                field_blank_id=f"PN-FB-COC-{i + 1:02d}",
                bottle_id=bottle_id,
                field_blank_bottle_id=fb_bottle,
                coc_id=f"COC-MIS-{i + 1:02d}",
                coc_bottles=[other, fb_bottle],
                collected_at=collected_at,
                received_at=received_at,
                preservation=LOCATIONS[location]["preservation"],
                truth=HOLD_BOTTLE_COC_MISMATCH,
            )
        )
        index += 1

    for i in range(HOLD_PER_CODE):
        original = rows[i]
        collected_at, received_at = _valid_times(original["location"])
        rows.append(
            _base_row(
                index=index,
                location=original["location"],
                method=original["method"],
                sample_id=original["sample_id"],
                field_blank_id=original["field_blank_id"],
                bottle_id=original["bottle_id"],
                field_blank_bottle_id=original["field_blank_bottle_id"],
                coc_id=original["coc_id"],
                coc_bottles=list(original["coc_bottles"]),
                collected_at=collected_at,
                received_at=received_at,
                preservation=original["preservation"],
                truth=HOLD_DUPLICATE_SAMPLE_ID,
            )
        )
        index += 1

    for i in range(HOLD_PER_CODE):
        location = LOCATION_ORDER[i % 3]
        methods = LOCATIONS[location]["methods"]
        method = methods[i % len(methods)]
        collected_at, received_at = _late_times(location)
        bottle_id = f"B-WIN-{i + 1:02d}"
        fb_bottle = f"FB-WIN-{i + 1:02d}"
        rows.append(
            _base_row(
                index=index,
                location=location,
                method=method,
                sample_id=f"PN-H-WIN-{i + 1:02d}",
                field_blank_id=f"PN-FB-WIN-{i + 1:02d}",
                bottle_id=bottle_id,
                field_blank_bottle_id=fb_bottle,
                coc_id=f"COC-WIN-{i + 1:02d}",
                coc_bottles=[bottle_id, fb_bottle],
                collected_at=collected_at,
                received_at=received_at,
                preservation=LOCATIONS[location]["preservation"],
                truth=HOLD_INVALID_RECEIPT_WINDOW,
            )
        )
        index += 1

    for i in range(HOLD_PER_CODE):
        location = LOCATION_ORDER[i % 3]
        methods = LOCATIONS[location]["methods"]
        method = methods[i % len(methods)]
        collected_at, received_at = _valid_times(location)
        bottle_id = f"B-PRE-{i + 1:02d}"
        fb_bottle = f"FB-PRE-{i + 1:02d}"
        rows.append(
            _base_row(
                index=index,
                location=location,
                method=method,
                sample_id=f"PN-H-PRE-{i + 1:02d}",
                field_blank_id=f"PN-FB-PRE-{i + 1:02d}",
                bottle_id=bottle_id,
                field_blank_bottle_id=fb_bottle,
                coc_id=f"COC-PRE-{i + 1:02d}",
                coc_bottles=[bottle_id, fb_bottle],
                collected_at=collected_at,
                received_at=received_at,
                preservation="HNO3",
                truth=HOLD_WRONG_PRESERVATION,
            )
        )
        index += 1

    for i in range(HOLD_PER_CODE):
        if i % 2 == 0:
            location = "GRAND_RAPIDS"
            method = "EPA_1633"
        else:
            location = "MUSKEGON"
            method = "EPA_533"
        preservation = LOCATIONS[location]["preservation"]
        collected_at, received_at = _valid_times(location)
        bottle_id = f"B-LOC-{i + 1:02d}"
        fb_bottle = f"FB-LOC-{i + 1:02d}"
        rows.append(
            _base_row(
                index=index,
                location=location,
                method=method,
                sample_id=f"PN-H-LOC-{i + 1:02d}",
                field_blank_id=f"PN-FB-LOC-{i + 1:02d}",
                bottle_id=bottle_id,
                field_blank_bottle_id=fb_bottle,
                coc_id=f"COC-LOC-{i + 1:02d}",
                coc_bottles=[bottle_id, fb_bottle],
                collected_at=collected_at,
                received_at=received_at,
                preservation=preservation,
                truth=HOLD_UNSUPPORTED_METHOD_LOCATION,
            )
        )
        index += 1

    if len(rows) != FIXTURE_COUNT:
        raise RuntimeError(
            "acceptance fixture must be exactly %s rows, got %s" % (FIXTURE_COUNT, len(rows))
        )
    return rows


def empty_journal() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "mode": "SIMULATED",
        "accessions": {},
        "holds": [],
        "events": [],
        "worksheets": {},
        "portal_results": {},
        "production_writes": 0,
    }


def _event(journal: dict[str, Any], kind: str, payload: dict[str, Any]) -> None:
    journal["events"].append(
        {
            "seq": len(journal["events"]) + 1,
            "kind": kind,
            **deepcopy(payload),
        }
    )


def _receipt_window_ok(row: dict[str, Any]) -> bool:
    collected = parse_ts(row.get("collected_at"))
    received = parse_ts(row.get("received_at"))
    if collected is None or received is None:
        return False
    if received < collected:
        return False
    if received - collected > timedelta(days=RECEIPT_HOLD_DAYS):
        return False
    local = received.timetz().replace(tzinfo=None)
    if local < DROPOFF_OPEN or local > DROPOFF_CLOSE:
        return False
    return True


def classify_submission(row: dict[str, Any], seen_sample_ids: set[str] | None = None) -> dict[str, Any]:
    sample_id = _text(row.get("sample_id"))
    location = _text(row.get("location"))
    method = _text(row.get("method"))
    field_blank_id = _text(row.get("field_blank_id"))
    bottle_id = _text(row.get("bottle_id"))
    coc_bottles = [_text(item) for item in (row.get("coc_bottles") or [])]
    seen = seen_sample_ids if seen_sample_ids is not None else set()

    if sample_id and sample_id in seen:
        return {"ok": False, "code": HOLD_DUPLICATE_SAMPLE_ID, "sample_id": sample_id}

    if not field_blank_id:
        return {
            "ok": False,
            "code": HOLD_MISSING_FIELD_BLANK,
            "sample_id": sample_id,
            "location": location,
            "method": method,
        }

    if not bottle_id or bottle_id not in coc_bottles:
        return {
            "ok": False,
            "code": HOLD_BOTTLE_COC_MISMATCH,
            "sample_id": sample_id,
            "bottle_id": bottle_id,
            "coc_id": _text(row.get("coc_id")),
        }

    if not _receipt_window_ok(row):
        return {
            "ok": False,
            "code": HOLD_INVALID_RECEIPT_WINDOW,
            "sample_id": sample_id,
            "collected_at": _text(row.get("collected_at")),
            "received_at": _text(row.get("received_at")),
        }

    spec = LOCATIONS.get(location)
    expected_pres = spec["preservation"] if spec else ""
    if _text(row.get("preservation")) != expected_pres:
        return {
            "ok": False,
            "code": HOLD_WRONG_PRESERVATION,
            "sample_id": sample_id,
            "preservation": _text(row.get("preservation")),
            "expected": expected_pres,
        }

    allowed = spec["methods"] if spec else ()
    if method not in allowed:
        return {
            "ok": False,
            "code": HOLD_UNSUPPORTED_METHOD_LOCATION,
            "sample_id": sample_id,
            "location": location,
            "method": method,
        }

    parentage = field_blank_parentage(sample_id, field_blank_id, method)
    return {
        "ok": True,
        "sample_id": sample_id,
        "field_blank_id": field_blank_id,
        "location": location,
        "custody_location": _text(row.get("custody_location")) or location,
        "method": method,
        "matrix": _text(row.get("matrix")) or (spec["matrix"] if spec else ""),
        "panel": _text(row.get("panel")) or METHOD_PANEL.get(method),
        "preservation": _text(row.get("preservation")),
        "bottle_id": bottle_id,
        "coc_id": _text(row.get("coc_id")),
        "accession_id": accession_id(location, sample_id, method),
        "parentage": parentage,
        "source_hash": source_hash(row),
        "custody_hash": custody_hash(row),
        "image_sha256": image_hash(row),
        "hashes_ok": hashes_reconcile(row),
        "collected_at": _text(row.get("collected_at")),
        "received_at": _text(row.get("received_at")),
    }


def report_status(record: dict[str, Any]) -> str:
    if record.get("released"):
        return "RELEASED"
    if not record.get("analyst_result"):
        return "STAGED_BLOCKED_MISSING_RESULT"
    if not record.get("qc_signoff"):
        return "STAGED_BLOCKED_MISSING_QC"
    return "STAGED_READY_FOR_HUMAN_RELEASE"


def ingest_row(journal: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    sample_id = _text(row.get("sample_id"))
    row_id = _text(row.get("row_id"))
    by_sample = {
        item["sample_id"]: item
        for item in journal["accessions"].values()
        if item.get("sample_id")
    }
    if sample_id and sample_id in by_sample:
        existing = by_sample[sample_id]
        if existing.get("row_id") == row_id:
            _event(
                journal,
                "REPLAY_NOOP",
                {
                    "accession_id": existing["accession_id"],
                    "sample_id": sample_id,
                    "row_id": row_id,
                },
            )
            return {
                "kind": "REPLAY_NOOP",
                "accession_id": existing["accession_id"],
                "sample_id": sample_id,
            }
        verdict = {
            "ok": False,
            "code": HOLD_DUPLICATE_SAMPLE_ID,
            "sample_id": sample_id,
        }
    else:
        verdict = classify_submission(row, set(by_sample))

    if not verdict["ok"]:
        hold = {
            "row_id": row_id,
            "sample_id": verdict.get("sample_id") or None,
            "code": verdict["code"],
            "location": _text(row.get("location")) or None,
            "method": _text(row.get("method")) or None,
            "source_hash": source_hash(row),
            "custody_hash": custody_hash(row),
            "image_sha256": image_hash(row),
            "worksheet_id": None,
            "portal_result": None,
        }
        fingerprint = sha256_hex(hold)
        existing = {sha256_hex(item) for item in journal["holds"]}
        if fingerprint not in existing:
            journal["holds"].append(hold)
            _event(journal, "HOLD", hold)
        return {"kind": "HOLD", "duplicate": fingerprint in existing, **hold}

    acc_id = verdict["accession_id"]
    existing_acc = journal["accessions"].get(acc_id)
    if existing_acc is not None:
        _event(
            journal,
            "REPLAY_NOOP",
            {"accession_id": acc_id, "sample_id": verdict["sample_id"]},
        )
        return {"kind": "REPLAY_NOOP", "accession_id": acc_id, "sample_id": verdict["sample_id"]}

    worksheet_id = f"WS-{acc_id}"
    record = {
        "accession_id": acc_id,
        "row_id": row_id,
        "sample_id": verdict["sample_id"],
        "field_blank_id": verdict["field_blank_id"],
        "field_blank_parentage": verdict["parentage"],
        "location": verdict["location"],
        "custody_location": verdict["custody_location"],
        "method": verdict["method"],
        "matrix": verdict["matrix"],
        "panel": verdict["panel"],
        "preservation": verdict["preservation"],
        "bottle_id": verdict["bottle_id"],
        "coc_id": verdict["coc_id"],
        "collected_at": verdict["collected_at"],
        "received_at": verdict["received_at"],
        "source_hash": verdict["source_hash"],
        "custody_hash": verdict["custody_hash"],
        "image_sha256": verdict["image_sha256"],
        "hashes_ok": verdict["hashes_ok"],
        "state": "ACCESSIONED",
        "worksheet_id": worksheet_id,
        "portal_result": "STAGED",
        "analyst_result": None,
        "qc_signoff": False,
        "released": False,
        "released_by": None,
        "report_status": "STAGED_BLOCKED_MISSING_RESULT",
        "interface_state": "SIMULATED",
        "interface_live": False,
        "production_write": False,
    }
    journal["accessions"][acc_id] = record
    journal["worksheets"][acc_id] = {
        "worksheet_id": worksheet_id,
        "accession_id": acc_id,
        "method": verdict["method"],
        "field_blank_id": verdict["field_blank_id"],
        "state": "OPEN",
    }
    journal["portal_results"][acc_id] = {
        "accession_id": acc_id,
        "state": "STAGED",
        "released": False,
    }
    _event(
        journal,
        "ACCESSION",
        {
            "accession_id": acc_id,
            "sample_id": verdict["sample_id"],
            "method": verdict["method"],
            "field_blank_id": verdict["field_blank_id"],
            "location": verdict["location"],
        },
    )
    return {
        "kind": "ACCESSION",
        "accession_id": acc_id,
        "method": verdict["method"],
        "sample_id": verdict["sample_id"],
        "field_blank_id": verdict["field_blank_id"],
    }


def attach_result(journal: dict[str, Any], accession_id_value: str, result: Any) -> dict[str, Any]:
    record = journal["accessions"].get(accession_id_value)
    if record is None:
        return {"ok": False, "code": "UNKNOWN_ACCESSION"}
    if result in (None, ""):
        return {"ok": False, "code": "EMPTY_RESULT"}
    record["analyst_result"] = deepcopy(result)
    record["report_status"] = report_status(record)
    _event(journal, "ANALYST_RESULT", {"accession_id": accession_id_value})
    return {"ok": True, "report_status": record["report_status"]}


def qc_signoff(journal: dict[str, Any], accession_id_value: str) -> dict[str, Any]:
    record = journal["accessions"].get(accession_id_value)
    if record is None:
        return {"ok": False, "code": "UNKNOWN_ACCESSION"}
    record["qc_signoff"] = True
    record["report_status"] = report_status(record)
    _event(journal, "QC_SIGNOFF", {"accession_id": accession_id_value})
    return {"ok": True, "report_status": record["report_status"]}


def release_report(
    journal: dict[str, Any],
    accession_id_value: str,
    *,
    actor_role: str,
    actor: str,
) -> dict[str, Any]:
    record = journal["accessions"].get(accession_id_value)
    if record is None:
        return {"ok": False, "code": "UNKNOWN_ACCESSION"}
    role = _text(actor_role).upper()
    if role != HUMAN_RELEASER:
        _event(
            journal,
            "RELEASE_DENIED",
            {
                "accession_id": accession_id_value,
                "code": "AUTONOMOUS_RELEASE_DENIED",
                "actor_role": role or None,
            },
        )
        return {
            "ok": False,
            "code": "AUTONOMOUS_RELEASE_DENIED",
            "report_status": report_status(record),
        }
    status = report_status(record)
    if status != "STAGED_READY_FOR_HUMAN_RELEASE" and status != "RELEASED":
        _event(
            journal,
            "RELEASE_DENIED",
            {
                "accession_id": accession_id_value,
                "code": "REPORT_BLOCKED",
                "report_status": status,
            },
        )
        return {"ok": False, "code": "REPORT_BLOCKED", "report_status": status}
    if record["released"]:
        return {"ok": True, "duplicate": True, "report_status": "RELEASED"}
    record["released"] = True
    record["released_by"] = _text(actor) or "human-releaser"
    record["report_status"] = "RELEASED"
    record["portal_result"] = "RELEASED"
    portal = journal["portal_results"].get(accession_id_value)
    if portal is not None:
        portal["state"] = "RELEASED"
        portal["released"] = True
        portal["released_by"] = record["released_by"]
    _event(
        journal,
        "RELEASED",
        {
            "accession_id": accession_id_value,
            "released_by": record["released_by"],
        },
    )
    return {"ok": True, "duplicate": False, "report_status": "RELEASED"}


def run_gate(rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    inbound = deepcopy(rows if rows is not None else build_acceptance_fixture())
    journal = empty_journal()
    effects = [ingest_row(journal, row) for row in inbound]
    autonomous = [
        release_report(journal, acc_id, actor_role="SYSTEM", actor="autonomous")
        for acc_id in journal["accessions"]
    ]

    accessioned = sorted(
        journal["accessions"].values(),
        key=lambda item: (item["location"], item["sample_id"]),
    )
    hold_codes = sorted(item["code"] for item in journal["holds"])
    hold_counts = {code: hold_codes.count(code) for code in HOLD_CODES}
    routes = {item["sample_id"]: item["method"] for item in accessioned}
    parentage = {
        item["sample_id"]: item["field_blank_parentage"] for item in accessioned
    }
    locations = {item["sample_id"]: item["location"] for item in accessioned}
    staged = [item for item in accessioned if item["report_status"] != "RELEASED"]
    held_worksheets = sum(1 for item in journal["holds"] if item.get("worksheet_id"))
    held_portal = sum(1 for item in journal["holds"] if item.get("portal_result"))

    body = {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "truth_gate": TRUTH_GATE,
        "mode": "SIMULATED",
        "input_rows": len(inbound),
        "accessioned": len(accessioned),
        "held": len(journal["holds"]),
        "hold_codes": hold_codes,
        "hold_counts": hold_counts,
        "routes": routes,
        "locations": locations,
        "parentage": parentage,
        "accession_ids": [item["accession_id"] for item in accessioned],
        "hashes_ok_count": sum(1 for item in accessioned if item.get("hashes_ok")),
        "custody_match_count": sum(
            1 for item in accessioned if item.get("custody_location") == item.get("location")
        ),
        "held_worksheets": held_worksheets,
        "held_portal_results": held_portal,
        "blocked_reports": len(staged),
        "released_reports": 0,
        "replay_noops": sum(1 for item in effects if item.get("kind") == "REPLAY_NOOP"),
        "effects": effects,
        "autonomous_release_effects": autonomous,
        "accessions": accessioned,
        "holds": deepcopy(journal["holds"]),
        "interface_live": False,
        "interfaces": "SIMULATED",
        "production_writes": journal["production_writes"],
        "autonomous_certification": False,
        "autonomous_release": False,
        "pre_sale_transport": "NONE",
        "cash_usd": 0,
    }
    body["fixture_sha256"] = sha256_hex(inbound)
    body["manifest_sha256"] = sha256_hex(
        {key: value for key, value in body.items() if key != "manifest_sha256"}
    )
    return body


def replay_into(journal: dict[str, Any], rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    inbound = deepcopy(rows if rows is not None else build_acceptance_fixture())
    before = set(journal["accessions"])
    before_holds = len(journal["holds"])
    effects = [ingest_row(journal, row) for row in inbound]
    added = set(journal["accessions"]) - before
    return {
        "added_accessions": sorted(added),
        "added_accession_count": len(added),
        "added_holds": len(journal["holds"]) - before_holds,
        "replay_noops": sum(1 for item in effects if item.get("kind") == "REPLAY_NOOP"),
        "accession_count": len(journal["accessions"]),
        "hold_count": len(journal["holds"]),
    }


def pass_contract(result: dict[str, Any]) -> list[str]:
    failures = []
    if result.get("input_rows") != FIXTURE_COUNT:
        failures.append("input_rows!=150")
    if result.get("accessioned") != VALID_COUNT:
        failures.append("accessioned!=120")
    if result.get("held") != HOLD_COUNT:
        failures.append("held!=30")
    expected_counts = {code: HOLD_PER_CODE for code in HOLD_CODES}
    if result.get("hold_counts") != expected_counts:
        failures.append("hold_counts")
    ids = result.get("accession_ids") or []
    if len(ids) != VALID_COUNT or len(set(ids)) != VALID_COUNT:
        failures.append("accession_ids_not_unique")
    locations = result.get("locations") or {}
    if len(locations) != VALID_COUNT:
        failures.append("location_map")
    if any(value not in LOCATIONS for value in locations.values()):
        failures.append("unknown_location")
    splits = {name: sum(1 for value in locations.values() if value == name) for name in LOCATION_ORDER}
    if splits != {"GRAND_RAPIDS": 40, "HOLLAND": 40, "MUSKEGON": 40}:
        failures.append("location_split")
    fixture = {
        row["sample_id"]: row
        for row in build_acceptance_fixture()
        if row["truth"] == "VALID"
    }
    parentage = result.get("parentage") or {}
    routes = result.get("routes") or {}
    if len(parentage) != VALID_COUNT:
        failures.append("parentage_count")
    for sample_id, row in fixture.items():
        expected = field_blank_parentage(sample_id, row["field_blank_id"], row["method"])
        if parentage.get(sample_id) != expected:
            failures.append("field_blank_parentage")
            break
        if routes.get(sample_id) != row["method"]:
            failures.append("method_route")
            break
    if result.get("hashes_ok_count") != VALID_COUNT:
        failures.append("hashes_not_reconciled")
    if result.get("custody_match_count") != VALID_COUNT:
        failures.append("custody_locations")
    if result.get("held_worksheets") != 0:
        failures.append("held_created_worksheet")
    if result.get("held_portal_results") != 0:
        failures.append("held_created_portal")
    if any(item.get("worksheet_id") for item in result.get("holds") or []):
        failures.append("hold_worksheet_id")
    if any(item.get("portal_result") for item in result.get("holds") or []):
        failures.append("hold_portal_result")
    if result.get("released_reports") != 0:
        failures.append("released_reports!=0")
    if result.get("blocked_reports") != VALID_COUNT:
        failures.append("blocked_reports!=120")
    if result.get("replay_noops") != 0:
        failures.append("fresh_run_replay_noops")
    if result.get("interface_live") is not False:
        failures.append("interface_live")
    if result.get("interfaces") != "SIMULATED":
        failures.append("interfaces")
    if result.get("production_writes") != 0:
        failures.append("production_writes")
    if result.get("autonomous_certification") is not False:
        failures.append("autonomous_certification")
    if result.get("autonomous_release") is not False:
        failures.append("autonomous_release")
    if not all(
        item.get("code") == "AUTONOMOUS_RELEASE_DENIED"
        for item in result.get("autonomous_release_effects") or []
    ):
        failures.append("autonomous_release_not_denied")
    if result.get("fixture_sha256") != sha256_hex(build_acceptance_fixture()):
        failures.append("fixture_sha256")
    return failures


def main() -> int:
    first = run_gate()
    second = run_gate()
    journal = empty_journal()
    fixture = build_acceptance_fixture()
    for row in fixture:
        ingest_row(journal, row)
    replay = replay_into(journal, fixture)
    failures = pass_contract(first)
    if sha256_hex(first) != sha256_hex(second):
        failures.append("replay_mismatch")
    if first.get("manifest_sha256") != second.get("manifest_sha256"):
        failures.append("manifest_sha256_mismatch")
    if replay.get("added_accession_count") != 0:
        failures.append("replay_added_accessions")
    if replay.get("added_holds") != 0:
        failures.append("replay_added_holds")
    report = {
        "ok": not failures,
        "failures": failures,
        "manifest_sha256": first.get("manifest_sha256"),
        "fixture_sha256": first.get("fixture_sha256"),
        "accessioned": first.get("accessioned"),
        "held": first.get("held"),
        "hold_counts": first.get("hold_counts"),
        "hashes_ok_count": first.get("hashes_ok_count"),
        "blocked_reports": first.get("blocked_reports"),
        "held_worksheets": first.get("held_worksheets"),
        "held_portal_results": first.get("held_portal_results"),
        "replay_added_accessions": replay.get("added_accession_count"),
        "replay_added_holds": replay.get("added_holds"),
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
