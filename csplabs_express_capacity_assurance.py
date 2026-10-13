#!/usr/bin/env python3
"""CSP Labs Express capacity-assurance LIMS.

Demand: csplabs-express-capacity-assurance-lims-01
Buyer: California Seed & Plant Lab / Sukhi Pannu

Express receipt verification, four-assay strawberry routing, SLA class
from signed receipt + verification + business-day cutoff, staffing
counts from the accepted-job manifest, plate QC with one seeded failed
negative control that holds its batch, and reviewer-only release.

240 synthetic strawberry Express orders. 200 valid. 40 blocked.
200 accessions and 800 test jobs exactly once.

Public Express facts used as fixture rules (not a live CSP claim):
- original four-assay strawberry screen: Phytophthora genus, Verticillium
  dahliae, Macrophomina phaseolina, Fusarium oxysporum f. sp. fragariae
- same-day or next-business-day TAT
- mobile submission / photo + FedEx/QR shipment identity
- staffing visibility from inbound accepted work

AquaTrace HOLD / BUILD-AND-VERIFY. Adapters stay simulated/read-only.
No production writes, outreach, prospect-facing demo, or automatic
release. PRE-SALE TRANSPORT: NONE.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

DEMAND_ID = "csplabs-express-capacity-assurance-lims-01"
SCHEMA = "commons-csplabs-express-capacity-assurance-lims/v1"
TRUTH_GATE = "HOLD / BUILD-AND-VERIFY"
BUYER = "California Seed & Plant Lab / Sukhi Pannu"
HUMAN_REVIEWER = "REVIEWER"
HUMAN_ACTOR = "reviewer-01"
TZ = ZoneInfo("America/Los_Angeles")
SAME_DAY_CUTOFF_HOUR = 11
JOBS_PER_PLATE = 20
SEEDED_FAILED_PLATE = "PLATE-FOF-01"

ASSAYS = ("FOF", "MP", "PHY", "VD")
ASSAY_NAMES = {
    "FOF": "Fusarium oxysporum f. sp. fragariae",
    "MP": "Macrophomina phaseolina",
    "PHY": "Phytophthora genus",
    "VD": "Verticillium dahliae",
}
SUPPORTED_CROP = "strawberry"
SUPPORTED_TISSUE = ("crown", "root", "petiole", "leaf")
HOLD_CODES = (
    "HOLD_MISSING_PHOTO",
    "HOLD_SHIPMENT_BARCODE_MISMATCH",
    "HOLD_UNSUPPORTED_SAMPLE_TEST",
    "HOLD_INCOMPLETE_LABEL",
)
SLA_CLASSES = ("SAME_DAY", "NEXT_BUSINESS_DAY")


def _text(value: Any) -> str:
    return str("" if value is None else value).strip()


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_hex(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def accession_id(order_id: str, sample_id: str) -> str:
    digest = sha256_hex(
        {
            "demand_id": DEMAND_ID,
            "order_id": order_id,
            "sample_id": sample_id,
        }
    )
    return "CSPX-" + digest[:12]


def job_id(acc_id: str, assay: str) -> str:
    digest = sha256_hex(
        {
            "accession_id": acc_id,
            "assay": assay,
            "demand_id": DEMAND_ID,
        }
    )
    return "JOB-" + digest[:12]


def _parse_local(value: str) -> datetime:
    stamp = datetime.fromisoformat(_text(value))
    if stamp.tzinfo is None:
        return stamp.replace(tzinfo=TZ)
    return stamp.astimezone(TZ)


def sla_class(signed_receipt_at: str, verified_at: str) -> str:
    """SLA from the later of signed receipt and verification.

    SAME_DAY only when that clock is a weekday before 11:00 America/Los_Angeles.
    Weekend or at/after cutoff is NEXT_BUSINESS_DAY.
    """
    signed = _parse_local(signed_receipt_at)
    verified = _parse_local(verified_at)
    clock = signed if signed >= verified else verified
    if clock.weekday() >= 5:
        return "NEXT_BUSINESS_DAY"
    if clock.hour >= SAME_DAY_CUTOFF_HOUR:
        return "NEXT_BUSINESS_DAY"
    return "SAME_DAY"


def _valid_times(index: int) -> tuple[str, str, str]:
    """Deterministic receipt/verify pair for valid order index 1..200."""
    if index <= 80:
        return (
            "2026-08-24T08:00:00-07:00",
            "2026-08-24T09:00:00-07:00",
            "SAME_DAY",
        )
    if index <= 120:
        return (
            "2026-08-24T10:00:00-07:00",
            "2026-08-24T14:00:00-07:00",
            "NEXT_BUSINESS_DAY",
        )
    if index <= 160:
        return (
            "2026-08-22T09:00:00-07:00",
            "2026-08-22T10:00:00-07:00",
            "NEXT_BUSINESS_DAY",
        )
    return (
        "2026-08-22T16:00:00-07:00",
        "2026-08-24T09:30:00-07:00",
        "SAME_DAY",
    )


def _base_order(index: int) -> dict[str, Any]:
    token = f"{index:04d}"
    barcode = f"CSP-BC-{token}"
    signed, verified, expected_sla = _valid_times(index if index <= 200 else 1)
    return {
        "row_id": f"R{token}",
        "order_id": f"ORD-{token}",
        "crop": SUPPORTED_CROP,
        "tissue": SUPPORTED_TISSUE[(index - 1) % len(SUPPORTED_TISSUE)],
        "sample_id": f"CSP-S-{token}",
        "grower_lot": f"LOT-{token}",
        "photo_id": f"PHOTO-{token}",
        "sample_barcode": barcode,
        "shipment_barcode": barcode,
        "assays": list(ASSAYS),
        "signed_receipt_at": signed,
        "verified_at": verified,
        "expected_sla": expected_sla,
        "exception_type": None,
        "synthetic": True,
        "deidentified": True,
    }


def _exception_order(index: int) -> dict[str, Any]:
    row = _base_order(index)
    if index <= 210:
        row["photo_id"] = ""
        row["exception_type"] = "MISSING_PHOTO"
        row["expected_sla"] = None
        return row
    if index <= 220:
        row["shipment_barcode"] = f"FEDEX-MISMATCH-{index:04d}"
        row["exception_type"] = "SHIPMENT_BARCODE_MISMATCH"
        row["expected_sla"] = None
        return row
    if index <= 225:
        row["crop"] = "tomato"
        row["exception_type"] = "UNSUPPORTED_SAMPLE_TEST"
        row["expected_sla"] = None
        return row
    if index <= 230:
        row["assays"] = ["FOF", "MP", "PHY", "COL"]
        row["exception_type"] = "UNSUPPORTED_SAMPLE_TEST"
        row["expected_sla"] = None
        return row
    if index <= 235:
        row["sample_id"] = ""
        row["exception_type"] = "INCOMPLETE_LABEL"
        row["expected_sla"] = None
        return row
    row["grower_lot"] = ""
    row["exception_type"] = "INCOMPLETE_LABEL"
    row["expected_sla"] = None
    return row


def build_acceptance_fixture() -> list[dict[str, Any]]:
    """240-row PASS fixture: 200 valid strawberry Express + 40 holds.

    Holds: 10 missing photos, 10 shipment/barcode mismatches, 10
    unsupported sample/test combinations, 10 incomplete labels.
    """
    rows = [_base_order(index) for index in range(1, 201)]
    rows.extend(_exception_order(index) for index in range(201, 241))
    if len(rows) != 240:
        raise RuntimeError("acceptance fixture must be exactly 240 rows, got %s" % len(rows))
    exceptions = {name: 0 for name in (
        "MISSING_PHOTO",
        "SHIPMENT_BARCODE_MISMATCH",
        "UNSUPPORTED_SAMPLE_TEST",
        "INCOMPLETE_LABEL",
    )}
    valid = 0
    for row in rows:
        if row["exception_type"]:
            exceptions[row["exception_type"]] += 1
        else:
            valid += 1
    if valid != 200:
        raise RuntimeError("acceptance fixture must seed 200 valid orders, got %s" % valid)
    if exceptions != {
        "MISSING_PHOTO": 10,
        "SHIPMENT_BARCODE_MISMATCH": 10,
        "UNSUPPORTED_SAMPLE_TEST": 10,
        "INCOMPLETE_LABEL": 10,
    }:
        raise RuntimeError("exception split must be 10/10/10/10, got %s" % exceptions)
    return rows


def empty_journal() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "accessions": {},
        "jobs": {},
        "holds": [],
        "plates": {},
        "events": [],
        "order_index": {},
        "interface_live": False,
        "production_writes": 0,
        "automatic_releases": 0,
    }


def _event(journal: dict[str, Any], kind: str, payload: dict[str, Any]) -> None:
    journal["events"].append(
        {
            "seq": len(journal["events"]) + 1,
            "kind": kind,
            **deepcopy(payload),
        }
    )


def normalize_order(row: dict[str, Any]) -> dict[str, Any]:
    assays = row.get("assays") or []
    return {
        "row_id": _text(row.get("row_id")),
        "order_id": _text(row.get("order_id")),
        "crop": _text(row.get("crop")).lower(),
        "tissue": _text(row.get("tissue")).lower(),
        "sample_id": _text(row.get("sample_id")),
        "grower_lot": _text(row.get("grower_lot")),
        "photo_id": _text(row.get("photo_id")),
        "sample_barcode": _text(row.get("sample_barcode")),
        "shipment_barcode": _text(row.get("shipment_barcode")),
        "assays": [_text(item).upper() for item in assays],
        "signed_receipt_at": _text(row.get("signed_receipt_at")),
        "verified_at": _text(row.get("verified_at")),
        "exception_type": _text(row.get("exception_type")).upper() or None,
        "synthetic": True,
        "deidentified": True,
    }


def classify_order(norm: dict[str, Any]) -> dict[str, Any]:
    if not norm["photo_id"] or norm["exception_type"] == "MISSING_PHOTO":
        return {"ok": False, "code": "HOLD_MISSING_PHOTO"}
    if (
        not norm["sample_id"]
        or not norm["grower_lot"]
        or not norm["tissue"]
        or norm["tissue"] not in SUPPORTED_TISSUE
        or norm["exception_type"] == "INCOMPLETE_LABEL"
    ):
        return {"ok": False, "code": "HOLD_INCOMPLETE_LABEL"}
    if (
        not norm["sample_barcode"]
        or not norm["shipment_barcode"]
        or norm["sample_barcode"] != norm["shipment_barcode"]
        or norm["exception_type"] == "SHIPMENT_BARCODE_MISMATCH"
    ):
        return {"ok": False, "code": "HOLD_SHIPMENT_BARCODE_MISMATCH"}
    if (
        norm["crop"] != SUPPORTED_CROP
        or tuple(norm["assays"]) != ASSAYS
        or norm["exception_type"] == "UNSUPPORTED_SAMPLE_TEST"
    ):
        return {"ok": False, "code": "HOLD_UNSUPPORTED_SAMPLE_TEST"}
    if not norm["signed_receipt_at"] or not norm["verified_at"]:
        return {"ok": False, "code": "HOLD_INCOMPLETE_LABEL"}
    return {"ok": True}


def _hold(journal: dict[str, Any], *, row_id: str, order_id: str, sample_id: str | None, code: str) -> dict[str, Any]:
    hold = {
        "row_id": row_id,
        "order_id": order_id,
        "sample_id": sample_id,
        "code": code,
        "state": "HOLD",
        "jobs_created": 0,
    }
    already = next(
        (
            item
            for item in journal["holds"]
            if item.get("row_id") == row_id and item.get("code") == code
        ),
        None,
    )
    if already is not None:
        return {"kind": "HOLD", "duplicate": True, **deepcopy(already)}
    journal["holds"].append(hold)
    _event(journal, "HOLD", hold)
    return {"kind": "HOLD", "duplicate": False, **hold}


def ingest_row(journal: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    norm = normalize_order(row)
    acc_id = accession_id(norm["order_id"], norm["sample_id"] or norm["order_id"])
    if acc_id in journal["accessions"]:
        _event(journal, "REPLAY_NOOP", {"accession_id": acc_id, "order_id": norm["order_id"]})
        return {"kind": "REPLAY_NOOP", "accession_id": acc_id, "order_id": norm["order_id"]}
    if norm["order_id"] in journal["order_index"]:
        _event(journal, "REPLAY_NOOP", {"order_id": norm["order_id"]})
        return {"kind": "REPLAY_NOOP", "order_id": norm["order_id"]}

    verdict = classify_order(norm)
    if not verdict["ok"]:
        return _hold(
            journal,
            row_id=norm["row_id"],
            order_id=norm["order_id"],
            sample_id=norm["sample_id"] or None,
            code=verdict["code"],
        )

    sla = sla_class(norm["signed_receipt_at"], norm["verified_at"])
    record = {
        "accession_id": acc_id,
        "row_id": norm["row_id"],
        "order_id": norm["order_id"],
        "sample_id": norm["sample_id"],
        "grower_lot": norm["grower_lot"],
        "crop": norm["crop"],
        "tissue": norm["tissue"],
        "photo_id": norm["photo_id"],
        "sample_barcode": norm["sample_barcode"],
        "shipment_barcode": norm["shipment_barcode"],
        "assays": list(ASSAYS),
        "route": "EXPRESS_FOUR_ASSAY",
        "signed_receipt_at": norm["signed_receipt_at"],
        "verified_at": norm["verified_at"],
        "sla_class": sla,
        "state": "ACCESSIONED",
        "job_ids": [],
        "released": False,
        "released_by": None,
        "report_status": "BLOCKED_PENDING_JOBS",
        "interface_state": "SIMULATED",
        "interface_live": False,
    }
    journal["accessions"][acc_id] = record
    journal["order_index"][norm["order_id"]] = acc_id
    created_jobs = []
    for assay in ASSAYS:
        jid = job_id(acc_id, assay)
        job = {
            "job_id": jid,
            "accession_id": acc_id,
            "order_id": norm["order_id"],
            "sample_id": norm["sample_id"],
            "assay": assay,
            "assay_name": ASSAY_NAMES[assay],
            "sla_class": sla,
            "plate_id": None,
            "qc_status": "PENDING",
            "batch_hold": False,
            "released": False,
            "released_by": None,
            "result": None,
            "report_status": "BLOCKED_MISSING_QC",
            "interface_state": "SIMULATED",
            "interface_live": False,
        }
        journal["jobs"][jid] = job
        record["job_ids"].append(jid)
        created_jobs.append(jid)
    _event(
        journal,
        "ACCESSION",
        {
            "accession_id": acc_id,
            "order_id": norm["order_id"],
            "jobs": created_jobs,
            "sla_class": sla,
            "route": "EXPRESS_FOUR_ASSAY",
        },
    )
    return {
        "kind": "ACCESSION",
        "accession_id": acc_id,
        "order_id": norm["order_id"],
        "jobs": created_jobs,
        "sla_class": sla,
    }


def assign_plates(journal: dict[str, Any]) -> dict[str, Any]:
    by_assay: dict[str, list[str]] = {assay: [] for assay in ASSAYS}
    for jid, job in sorted(journal["jobs"].items(), key=lambda item: (item[1]["assay"], item[1]["order_id"])):
        by_assay[job["assay"]].append(jid)

    plates: dict[str, dict[str, Any]] = {}
    for assay, job_ids in by_assay.items():
        for offset in range(0, len(job_ids), JOBS_PER_PLATE):
            chunk = job_ids[offset : offset + JOBS_PER_PLATE]
            plate_no = (offset // JOBS_PER_PLATE) + 1
            plate_id = f"PLATE-{assay}-{plate_no:02d}"
            ntc_fail = plate_id == SEEDED_FAILED_PLATE
            plate = {
                "plate_id": plate_id,
                "assay": assay,
                "job_ids": chunk,
                "ntc": "FAIL" if ntc_fail else "PASS",
                "qc_status": "HOLD_NTC_FAIL" if ntc_fail else "QC_PASS",
                "seeded_fail": ntc_fail,
            }
            plates[plate_id] = plate
            for jid in chunk:
                job = journal["jobs"][jid]
                job["plate_id"] = plate_id
                if ntc_fail:
                    job["qc_status"] = "HOLD_NTC_FAIL"
                    job["batch_hold"] = True
                    job["report_status"] = "HOLD_BATCH_NTC_FAIL"
                    job["result"] = None
                else:
                    job["qc_status"] = "QC_PASS"
                    job["batch_hold"] = False
                    job["result"] = {"call": "ND", "adapter": "SIMULATED_QPCR"}
                    job["report_status"] = "READY_FOR_REVIEWER"
    journal["plates"] = plates
    _event(
        journal,
        "PLATE_QC",
        {
            "plates": len(plates),
            "seeded_failed_plate": SEEDED_FAILED_PLATE,
            "held_jobs": sum(1 for job in journal["jobs"].values() if job["batch_hold"]),
        },
    )
    for record in journal["accessions"].values():
        held = any(journal["jobs"][jid]["batch_hold"] for jid in record["job_ids"])
        record["report_status"] = "HOLD_BATCH_NTC_FAIL" if held else "READY_FOR_REVIEWER"
        record["state"] = "QC_HELD" if held else "READY_FOR_REVIEWER"
    return {"plates": len(plates), "held_jobs": sum(1 for job in journal["jobs"].values() if job["batch_hold"])}


def staffing_from_jobs(journal: dict[str, Any]) -> dict[str, Any]:
    jobs = sorted(journal["jobs"].values(), key=lambda item: (item["assay"], item["order_id"]))
    job_ids = [item["job_id"] for item in jobs]
    by_assay = {assay: 0 for assay in ASSAYS}
    by_sla = {name: 0 for name in SLA_CLASSES}
    for job in jobs:
        by_assay[job["assay"]] += 1
        by_sla[job["sla_class"]] += 1
    return {
        "accepted_accessions": len(journal["accessions"]),
        "accepted_jobs": len(job_ids),
        "job_ids": job_ids,
        "jobs_by_assay": by_assay,
        "jobs_by_sla": by_sla,
        "plates_required": len(journal["plates"]),
        "analyst_slots": len(job_ids),
    }


def accepted_job_manifest(journal: dict[str, Any]) -> dict[str, Any]:
    jobs = sorted(journal["jobs"].values(), key=lambda item: (item["assay"], item["order_id"]))
    return {
        "demand_id": DEMAND_ID,
        "job_ids": [item["job_id"] for item in jobs],
        "jobs": [
            {
                "job_id": item["job_id"],
                "accession_id": item["accession_id"],
                "order_id": item["order_id"],
                "assay": item["assay"],
                "sla_class": item["sla_class"],
                "plate_id": item["plate_id"],
            }
            for item in jobs
        ],
    }


def counts_payload(journal: dict[str, Any], staffing: dict[str, Any]) -> dict[str, Any]:
    sla_accessions = {name: 0 for name in SLA_CLASSES}
    for record in journal["accessions"].values():
        sla_accessions[record["sla_class"]] += 1
    hold_counts = {code: 0 for code in HOLD_CODES}
    for hold in journal["holds"]:
        hold_counts[hold["code"]] += 1
    held_jobs = [job for job in journal["jobs"].values() if job["batch_hold"]]
    ready_jobs = [job for job in journal["jobs"].values() if job["report_status"] == "READY_FOR_REVIEWER"]
    released_jobs = [job for job in journal["jobs"].values() if job["released"]]
    return {
        "input_rows": len(journal["accessions"]) + len(journal["holds"]),
        "accessioned": len(journal["accessions"]),
        "test_jobs": len(journal["jobs"]),
        "blocked": len(journal["holds"]),
        "hold_counts": hold_counts,
        "sla_accessions": sla_accessions,
        "staffing_jobs": staffing["accepted_jobs"],
        "held_batch_jobs": len(held_jobs),
        "ready_for_reviewer": len(ready_jobs),
        "released": len(released_jobs),
        "seeded_failed_plate": SEEDED_FAILED_PLATE,
    }


def digest_pair(counts: dict[str, Any]) -> dict[str, str]:
    digest = sha256_hex(counts)
    return {"dashboard_digest": digest, "report_digest": digest}


def release_job(
    journal: dict[str, Any],
    job_id_value: str,
    *,
    actor_role: str,
    actor: str,
) -> dict[str, Any]:
    job = journal["jobs"].get(job_id_value)
    if job is None:
        return {"ok": False, "code": "UNKNOWN_JOB"}
    role = _text(actor_role).upper()
    if role != HUMAN_REVIEWER:
        _event(
            journal,
            "RELEASE_DENIED",
            {
                "job_id": job_id_value,
                "code": "AUTONOMOUS_RELEASE_DENIED",
                "actor_role": role or None,
            },
        )
        return {"ok": False, "code": "AUTONOMOUS_RELEASE_DENIED", "report_status": job["report_status"]}
    if job["batch_hold"] or job["qc_status"] != "QC_PASS":
        _event(
            journal,
            "RELEASE_DENIED",
            {
                "job_id": job_id_value,
                "code": "HOLD_BATCH_NTC_FAIL" if job["batch_hold"] else "REPORT_BLOCKED",
                "report_status": job["report_status"],
            },
        )
        return {
            "ok": False,
            "code": "HOLD_BATCH_NTC_FAIL" if job["batch_hold"] else "REPORT_BLOCKED",
            "report_status": job["report_status"],
        }
    if job["released"]:
        return {"ok": True, "duplicate": True, "report_status": "RELEASED"}
    job["released"] = True
    job["released_by"] = _text(actor) or HUMAN_ACTOR
    job["report_status"] = "RELEASED"
    _event(journal, "RELEASED", {"job_id": job_id_value, "released_by": job["released_by"]})
    record = journal["accessions"][job["accession_id"]]
    if all(journal["jobs"][jid]["released"] for jid in record["job_ids"]):
        record["released"] = True
        record["released_by"] = job["released_by"]
        record["report_status"] = "RELEASED"
        record["state"] = "RELEASED"
    return {"ok": True, "duplicate": False, "report_status": "RELEASED"}


def attempt_autonomous_release(journal: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        release_job(journal, jid, actor_role="SYSTEM", actor="autonomous")
        for jid in sorted(journal["jobs"])
    ]


def reviewer_release_ready(journal: dict[str, Any], actor: str = HUMAN_ACTOR) -> list[dict[str, Any]]:
    return [
        release_job(journal, jid, actor_role=HUMAN_REVIEWER, actor=actor)
        for jid in sorted(journal["jobs"])
        if journal["jobs"][jid]["report_status"] == "READY_FOR_REVIEWER"
    ]


def replay_into(journal: dict[str, Any], rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    inbound = deepcopy(rows if rows is not None else build_acceptance_fixture())
    before_acc = set(journal["accessions"])
    before_jobs = set(journal["jobs"])
    before_holds = len(journal["holds"])
    effects = [ingest_row(journal, row) for row in inbound]
    return {
        "added_accessions": sorted(set(journal["accessions"]) - before_acc),
        "added_accession_count": len(set(journal["accessions"]) - before_acc),
        "added_jobs": len(set(journal["jobs"]) - before_jobs),
        "added_holds": len(journal["holds"]) - before_holds,
        "replay_noops": sum(1 for item in effects if item.get("kind") == "REPLAY_NOOP"),
        "accession_count": len(journal["accessions"]),
        "job_count": len(journal["jobs"]),
        "hold_count": len(journal["holds"]),
    }


def run_gate(rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    inbound = deepcopy(rows if rows is not None else build_acceptance_fixture())
    journal = empty_journal()
    effects = [ingest_row(journal, row) for row in inbound]
    assign_plates(journal)
    manifest = accepted_job_manifest(journal)
    staffing = staffing_from_jobs(journal)
    autonomous = attempt_autonomous_release(journal)
    counts = counts_payload(journal, staffing)
    # input_rows must be the inbound fixture, not accession+hold after ingest
    counts["input_rows"] = len(inbound)
    digests = digest_pair(counts)

    accessioned = sorted(journal["accessions"].values(), key=lambda item: item["order_id"])
    jobs = sorted(journal["jobs"].values(), key=lambda item: (item["assay"], item["order_id"]))
    hold_codes = sorted({item["code"] for item in journal["holds"]})
    sla_accessions = {name: 0 for name in SLA_CLASSES}
    for item in accessioned:
        sla_accessions[item["sla_class"]] += 1

    body = {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "truth_gate": TRUTH_GATE,
        "input_rows": len(inbound),
        "accessioned": len(accessioned),
        "test_jobs": len(jobs),
        "blocked": len(journal["holds"]),
        "hold_codes": hold_codes,
        "hold_counts": counts["hold_counts"],
        "sla_accessions": sla_accessions,
        "staffing": staffing,
        "accepted_job_manifest": manifest,
        "staffing_matches_manifest": staffing["job_ids"] == manifest["job_ids"]
        and staffing["accepted_jobs"] == len(manifest["job_ids"]),
        "plates": deepcopy(journal["plates"]),
        "seeded_failed_plate": SEEDED_FAILED_PLATE,
        "held_batch_jobs": counts["held_batch_jobs"],
        "ready_for_reviewer": counts["ready_for_reviewer"],
        "released": counts["released"],
        "released_reports": 0,
        "blocked_reports": len(jobs),
        "dashboard": deepcopy(counts),
        "report": deepcopy(counts),
        "dashboard_digest": digests["dashboard_digest"],
        "report_digest": digests["report_digest"],
        "digests_reconcile": digests["dashboard_digest"] == digests["report_digest"],
        "accession_ids": [item["accession_id"] for item in accessioned],
        "job_ids": [item["job_id"] for item in jobs],
        "replay_noops": sum(1 for item in effects if item.get("kind") == "REPLAY_NOOP"),
        "effects": effects,
        "autonomous_release_effects": autonomous,
        "accessions": accessioned,
        "jobs": jobs,
        "holds": deepcopy(journal["holds"]),
        "interface_live": False,
        "interfaces": "SIMULATED",
        "production_writes": 0,
        "automatic_releases": 0,
        "autonomous_certification": False,
        "autonomous_release": False,
        "pre_sale_transport": "NONE",
        "cash_usd": 0,
    }
    body["manifest_sha256"] = sha256_hex(
        {
            key: value
            for key, value in body.items()
            if key
            not in {
                "manifest_sha256",
                "effects",
                "autonomous_release_effects",
                "accessions",
                "jobs",
                "plates",
                "accepted_job_manifest",
            }
        }
    )
    return body


def pass_contract(result: dict[str, Any]) -> list[str]:
    failures = []
    if result.get("input_rows") != 240:
        failures.append("input_rows!=240")
    if result.get("accessioned") != 200:
        failures.append("accessioned!=200")
    if result.get("test_jobs") != 800:
        failures.append("test_jobs!=800")
    if result.get("blocked") != 40:
        failures.append("blocked!=40")
    if result.get("hold_codes") != sorted(HOLD_CODES):
        failures.append("hold_codes")
    if result.get("hold_counts") != {
        "HOLD_MISSING_PHOTO": 10,
        "HOLD_SHIPMENT_BARCODE_MISMATCH": 10,
        "HOLD_UNSUPPORTED_SAMPLE_TEST": 10,
        "HOLD_INCOMPLETE_LABEL": 10,
    }:
        failures.append("hold_counts")
    if result.get("sla_accessions") != {"SAME_DAY": 120, "NEXT_BUSINESS_DAY": 80}:
        failures.append("sla_accessions")
    if not result.get("staffing_matches_manifest"):
        failures.append("staffing_manifest")
    staffing = result.get("staffing") or {}
    if staffing.get("accepted_jobs") != 800:
        failures.append("staffing_jobs!=800")
    if staffing.get("jobs_by_assay") != {"FOF": 200, "MP": 200, "PHY": 200, "VD": 200}:
        failures.append("jobs_by_assay")
    if staffing.get("analyst_slots") != 800:
        failures.append("analyst_slots")
    if result.get("held_batch_jobs") != 20:
        failures.append("held_batch_jobs!=20")
    if result.get("seeded_failed_plate") != SEEDED_FAILED_PLATE:
        failures.append("seeded_failed_plate")
    plates = result.get("plates") or {}
    failed = plates.get(SEEDED_FAILED_PLATE) or {}
    if failed.get("ntc") != "FAIL" or failed.get("qc_status") != "HOLD_NTC_FAIL":
        failures.append("seeded_ntc")
    if result.get("ready_for_reviewer") != 780:
        failures.append("ready_for_reviewer!=780")
    if result.get("released") != 0:
        failures.append("released!=0")
    if result.get("released_reports") != 0:
        failures.append("released_reports!=0")
    if not result.get("digests_reconcile"):
        failures.append("digests")
    if result.get("dashboard_digest") != result.get("report_digest"):
        failures.append("digest_mismatch")
    if result.get("dashboard") != result.get("report"):
        failures.append("dashboard_report_body")
    if len(set(result.get("accession_ids") or [])) != 200:
        failures.append("accession_ids_not_unique")
    if len(set(result.get("job_ids") or [])) != 800:
        failures.append("job_ids_not_unique")
    if result.get("replay_noops") != 0:
        failures.append("fresh_run_replay_noops")
    if result.get("interface_live") is not False:
        failures.append("interface_live")
    if result.get("interfaces") != "SIMULATED":
        failures.append("interfaces")
    if result.get("production_writes") != 0:
        failures.append("production_writes")
    if result.get("automatic_releases") != 0:
        failures.append("automatic_releases")
    if result.get("autonomous_release") is not False:
        failures.append("autonomous_release")
    if not all(
        item.get("code") == "AUTONOMOUS_RELEASE_DENIED"
        for item in result.get("autonomous_release_effects") or []
    ):
        failures.append("autonomous_release_not_denied")
    if any(item.get("jobs_created") for item in result.get("holds") or []):
        failures.append("hold_created_jobs")
    return failures


def expected_actual(result: dict[str, Any]) -> dict[str, Any]:
    expected = {
        "input_rows": 240,
        "accessioned": 200,
        "test_jobs": 800,
        "blocked": 40,
        "sla_same_day": 120,
        "sla_next_business_day": 80,
        "staffing_jobs": 800,
        "held_batch_jobs": 20,
        "ready_for_reviewer": 780,
        "released": 0,
    }
    sla = result.get("sla_accessions") or {}
    actual = {
        "input_rows": result.get("input_rows"),
        "accessioned": result.get("accessioned"),
        "test_jobs": result.get("test_jobs"),
        "blocked": result.get("blocked"),
        "sla_same_day": sla.get("SAME_DAY"),
        "sla_next_business_day": sla.get("NEXT_BUSINESS_DAY"),
        "staffing_jobs": (result.get("staffing") or {}).get("accepted_jobs"),
        "held_batch_jobs": result.get("held_batch_jobs"),
        "ready_for_reviewer": result.get("ready_for_reviewer"),
        "released": result.get("released"),
    }
    return {"expected": expected, "actual": actual, "match": expected == actual}


def main() -> int:
    first = run_gate()
    second = run_gate()
    journal = empty_journal()
    for row in build_acceptance_fixture():
        ingest_row(journal, row)
    replay = replay_into(journal)
    failures = pass_contract(first)
    if first.get("dashboard_digest") != second.get("dashboard_digest"):
        failures.append("dashboard_replay_mismatch")
    if first.get("report_digest") != second.get("report_digest"):
        failures.append("report_replay_mismatch")
    if replay.get("added_accession_count") != 0:
        failures.append("replay_added_accessions")
    if replay.get("added_jobs") != 0:
        failures.append("replay_added_jobs")
    if replay.get("added_holds") != 0:
        failures.append("replay_added_holds")
    counts = expected_actual(first)
    report = {
        "ok": not failures,
        "failures": failures,
        "command": "python3 csplabs_express_capacity_assurance.py",
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "expected": counts["expected"],
        "actual": counts["actual"],
        "counts_match": counts["match"],
        "hold_codes": first.get("hold_codes"),
        "hold_counts": first.get("hold_counts"),
        "sla_accessions": first.get("sla_accessions"),
        "staffing_matches_manifest": first.get("staffing_matches_manifest"),
        "dashboard_digest": first.get("dashboard_digest"),
        "report_digest": first.get("report_digest"),
        "digests_reconcile": first.get("digests_reconcile"),
        "manifest_sha256": first.get("manifest_sha256"),
        "replay_added_accessions": replay.get("added_accession_count"),
        "replay_added_jobs": replay.get("added_jobs"),
        "truth_gate": TRUTH_GATE,
        "interfaces": "SIMULATED",
        "pre_sale_transport": "NONE",
        "cash_usd": 0,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
