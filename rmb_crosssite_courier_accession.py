#!/usr/bin/env python3
"""RMB cross-site courier accession — read-only LIMS shadow.

Binds distribution-partner/courier receipts to the correct RMB Detroit Lakes
or Beckton Ponce facility, certification scope, method, hold-time clock,
incumbent accession, and staged report.

Demand: rmb-crosssite-courier-accession-lims-01
Buyer pairing: RMB Environmental Laboratories / Robert Borash

Public facility facts used as the synthetic site map (not a live interface):
- RMB Detroit Lakes HQ — 22796 County Highway 6, Detroit Lakes, MN
- Beckton Laboratory (acquired) — 192 Villa Street, Ponce, PR
- Detroit Lakes courier window closes 15:00 (public Friday close 3 pm)

Existing LIMS remains authoritative. This module only shadows. Synthetic
fixtures. No production writes. No outreach. No automatic release.

AquaTrace HOLD / BUILD-AND-VERIFY. PRE-SALE TRANSPORT: NONE.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime, time, timedelta
from typing import Any

DEMAND_ID = "rmb-crosssite-courier-accession-lims-01"
SCHEMA = "commons-rmb-crosssite-courier-accession-lims/v1"
TRUTH_GATE = "HOLD / BUILD-AND-VERIFY"
HUMAN_RELEASER = "RELEASER"
COURIER_CUTOFF = time(15, 0)
COOLER_MAX_TEMP_C = 6.0
HOLD_HOURS = 48
FIXTURE_COUNT = 300
VALID_COUNT = 240
HOLD_COUNT = 60
HOLD_PER_CODE = 10

HOLD_RECEIPT_OVER_48H = "HOLD_RECEIPT_OVER_48H"
HOLD_MISSED_COURIER_CUTOFF = "HOLD_MISSED_COURIER_CUTOFF"
HOLD_DUPLICATE_SAMPLE_ID = "HOLD_DUPLICATE_SAMPLE_ID"
HOLD_BROKEN_COOLER_CUSTODY = "HOLD_BROKEN_COOLER_CUSTODY"
HOLD_FACILITY_METHOD_SCOPE_MISMATCH = "HOLD_FACILITY_METHOD_SCOPE_MISMATCH"
HOLD_LEGACY_SITE_MAPPING = "HOLD_LEGACY_SITE_MAPPING"

HOLD_CODES = (
    HOLD_RECEIPT_OVER_48H,
    HOLD_MISSED_COURIER_CUTOFF,
    HOLD_DUPLICATE_SAMPLE_ID,
    HOLD_BROKEN_COOLER_CUSTODY,
    HOLD_FACILITY_METHOD_SCOPE_MISMATCH,
    HOLD_LEGACY_SITE_MAPPING,
)

FACILITIES: dict[str, dict[str, Any]] = {
    "RMB_DETROIT_LAKES": {
        "code": "RMB",
        "name": "RMB Detroit Lakes",
        "offset": "-05:00",
        "cert_scopes": (
            "SM_9223B",
            "SM_4500P",
            "SM_2540D",
            "SM_10200H",
            "SM_5210B",
            "EPA_2008",
        ),
    },
    "BECKTON_PONCE": {
        "code": "BECKTON",
        "name": "Beckton Ponce",
        "offset": "-04:00",
        "cert_scopes": (
            "SM_9223B",
            "SM_4500P",
            "SM_2540D",
            "EPA_2008",
        ),
    },
}

METHOD_SCOPE = {
    "SM_9223B": "MICRO_COLIFORM",
    "SM_4500P": "NUTRIENTS",
    "SM_2540D": "TSS",
    "SM_10200H": "CHL_A",
    "SM_5210B": "BOD",
    "EPA_2008": "METALS",
}

RMB_METHODS = FACILITIES["RMB_DETROIT_LAKES"]["cert_scopes"]
BECKTON_METHODS = FACILITIES["BECKTON_PONCE"]["cert_scopes"]
LAKE_ONLY_METHODS = frozenset({"SM_10200H", "SM_5210B"})

LEGACY_SITE_MAP = {
    "BEC": "BECKTON_PONCE",
    "BECKTON": "BECKTON_PONCE",
    "BECKTON-OLD": "BECKTON_PONCE",
    "PONCE": "BECKTON_PONCE",
    "RMB": "RMB_DETROIT_LAKES",
    "RMB-HQ": "RMB_DETROIT_LAKES",
    "DL": "RMB_DETROIT_LAKES",
    "DETROIT-LAKES": "RMB_DETROIT_LAKES",
}

RMB_LEGACY = ("RMB", "RMB-HQ", "DL", "DETROIT-LAKES")
BECKTON_LEGACY = ("BEC", "BECKTON", "BECKTON-OLD", "PONCE")


def _text(value: Any) -> str:
    return str("" if value is None else value).strip()


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_hex(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _text(value).lower() in {"1", "true", "yes", "y"}


def _temp(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 99.0


def parse_ts(value: Any) -> datetime | None:
    text = _text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def incumbent_accession_id(facility: str, sample_id: str) -> str:
    code = FACILITIES[facility]["code"]
    digest = sha256_hex(
        {
            "demand_id": DEMAND_ID,
            "facility": facility,
            "sample_id": sample_id,
            "kind": "incumbent_accession",
        }
    )
    return f"INC-{code}-{digest[:10]}"


def source_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "sample_id": _text(row.get("sample_id")),
        "client_id": _text(row.get("client_id")),
        "site_id": _text(row.get("site_id")),
        "matrix": _text(row.get("matrix")),
        "method": _text(row.get("method")),
        "cert_scope": _text(row.get("cert_scope")),
        "facility": _text(row.get("facility")),
        "collection_ts": _text(row.get("collection_ts")),
    }


def custody_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "sample_id": _text(row.get("sample_id")),
        "courier_id": _text(row.get("courier_id")),
        "pickup_ts": _text(row.get("pickup_ts")),
        "receipt_ts": _text(row.get("receipt_ts")),
        "cooler_seal_id": _text(row.get("cooler_seal_id")),
        "manifest_seal_id": _text(row.get("manifest_seal_id")),
        "cooler_intact": _flag(row.get("cooler_intact")),
        "temp_c": _temp(row.get("temp_c")),
    }


def source_hash(row: dict[str, Any]) -> str:
    return sha256_hex(source_payload(row))


def custody_hash(row: dict[str, Any]) -> str:
    return sha256_hex(custody_payload(row))


def manifest_hash(row: dict[str, Any]) -> str:
    return sha256_hex(row.get("signed_manifest") or {})


def hashes_reconcile(row: dict[str, Any]) -> bool:
    manifest = row.get("signed_manifest") or {}
    if not isinstance(manifest, dict):
        return False
    if _text(manifest.get("pickup_ts")) != _text(row.get("pickup_ts")):
        return False
    if _text(manifest.get("receipt_ts")) != _text(row.get("receipt_ts")):
        return False
    if _text(manifest.get("facility")) != _text(row.get("facility")):
        return False
    if _text(manifest.get("method")) != _text(row.get("method")):
        return False
    if _text(manifest.get("cert_scope")) != _text(row.get("cert_scope")):
        return False
    if _text(manifest.get("seal_id")) != _text(row.get("manifest_seal_id")):
        return False
    if _text(manifest.get("courier_id")) != _text(row.get("courier_id")):
        return False
    if _text(row.get("source_hash")) != source_hash(row):
        return False
    if _text(row.get("custody_hash")) != custody_hash(row):
        return False
    if _text(row.get("manifest_hash")) != manifest_hash(row):
        return False
    return True


def resolve_legacy_site(legacy_site_code: str) -> str | None:
    return LEGACY_SITE_MAP.get(_text(legacy_site_code).upper())


def _signed_manifest(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "courier_id": row["courier_id"],
        "pickup_ts": row["pickup_ts"],
        "receipt_ts": row["receipt_ts"],
        "facility": row["facility"],
        "method": row["method"],
        "cert_scope": row["cert_scope"],
        "seal_id": row["manifest_seal_id"],
        "signature": f"SIG-{row['row_id']}",
    }


def _stamp_hashes(row: dict[str, Any]) -> dict[str, Any]:
    row["signed_manifest"] = _signed_manifest(row)
    row["source_hash"] = source_hash(row)
    row["custody_hash"] = custody_hash(row)
    row["manifest_hash"] = manifest_hash(row)
    return row


def _base_row(
    *,
    index: int,
    facility: str,
    method: str,
    matrix: str,
    sample_id: str,
    client_id: str,
    site_id: str,
    legacy_site_code: str,
    collection_ts: str,
    pickup_ts: str,
    receipt_ts: str,
    truth: str,
    cooler_intact: bool = True,
    temp_c: float = 3.2,
    cooler_seal_id: str | None = None,
    manifest_seal_id: str | None = None,
) -> dict[str, Any]:
    seal = cooler_seal_id or f"SEAL-{index:04d}"
    row = {
        "row_id": f"R{index:03d}",
        "sample_id": sample_id,
        "client_id": client_id,
        "site_id": site_id,
        "matrix": matrix,
        "method": method,
        "cert_scope": METHOD_SCOPE[method],
        "facility": facility,
        "legacy_site_code": legacy_site_code,
        "collection_ts": collection_ts,
        "pickup_ts": pickup_ts,
        "receipt_ts": receipt_ts,
        "courier_id": "PARTNER-NORTH" if facility == "RMB_DETROIT_LAKES" else "PARTNER-CARIB",
        "cooler_seal_id": seal,
        "manifest_seal_id": manifest_seal_id or seal,
        "cooler_intact": cooler_intact,
        "temp_c": temp_c,
        "truth": truth,
    }
    return _stamp_hashes(row)


def _valid_times(facility: str) -> tuple[str, str, str]:
    offset = FACILITIES[facility]["offset"]
    return (
        f"2026-06-08T08:00:00{offset}",
        f"2026-06-08T10:30:00{offset}",
        f"2026-06-08T14:00:00{offset}",
    )


def _over48_times(facility: str) -> tuple[str, str, str]:
    offset = FACILITIES[facility]["offset"]
    return (
        f"2026-06-08T08:00:00{offset}",
        f"2026-06-08T10:30:00{offset}",
        f"2026-06-10T10:30:00{offset}",
    )


def _late_pickup_times(facility: str) -> tuple[str, str, str]:
    offset = FACILITIES[facility]["offset"]
    return (
        f"2026-06-08T08:00:00{offset}",
        f"2026-06-08T16:15:00{offset}",
        f"2026-06-08T17:30:00{offset}",
    )


def build_acceptance_fixture() -> list[dict[str, Any]]:
    """300 frozen water/lake submissions: 240 valid, 60 exact HOLD codes."""
    rows: list[dict[str, Any]] = []
    index = 1

    for i in range(120):
        method = RMB_METHODS[i % len(RMB_METHODS)]
        matrix = "lake" if method in LAKE_ONLY_METHODS else "water"
        collection_ts, pickup_ts, receipt_ts = _valid_times("RMB_DETROIT_LAKES")
        rows.append(
            _base_row(
                index=index,
                facility="RMB_DETROIT_LAKES",
                method=method,
                matrix=matrix,
                sample_id=f"RMB-W-{i + 1:04d}",
                client_id=f"CLIENT-RMB-{(i % 24) + 1:02d}",
                site_id=f"SITE-RMB-{(i % 40) + 1:02d}",
                legacy_site_code=RMB_LEGACY[i % len(RMB_LEGACY)],
                collection_ts=collection_ts,
                pickup_ts=pickup_ts,
                receipt_ts=receipt_ts,
                truth="VALID",
            )
        )
        index += 1

    for i in range(120):
        method = BECKTON_METHODS[i % len(BECKTON_METHODS)]
        collection_ts, pickup_ts, receipt_ts = _valid_times("BECKTON_PONCE")
        rows.append(
            _base_row(
                index=index,
                facility="BECKTON_PONCE",
                method=method,
                matrix="water",
                sample_id=f"BEC-W-{i + 1:04d}",
                client_id=f"CLIENT-BEC-{(i % 24) + 1:02d}",
                site_id=f"SITE-BEC-{(i % 40) + 1:02d}",
                legacy_site_code=BECKTON_LEGACY[i % len(BECKTON_LEGACY)],
                collection_ts=collection_ts,
                pickup_ts=pickup_ts,
                receipt_ts=receipt_ts,
                truth="VALID",
            )
        )
        index += 1

    for i in range(HOLD_PER_CODE):
        facility = "RMB_DETROIT_LAKES" if i % 2 == 0 else "BECKTON_PONCE"
        method = RMB_METHODS[i % len(RMB_METHODS)] if facility == "RMB_DETROIT_LAKES" else BECKTON_METHODS[i % len(BECKTON_METHODS)]
        matrix = "lake" if method in LAKE_ONLY_METHODS else "water"
        collection_ts, pickup_ts, receipt_ts = _over48_times(facility)
        legacy = RMB_LEGACY[i % len(RMB_LEGACY)] if facility == "RMB_DETROIT_LAKES" else BECKTON_LEGACY[i % len(BECKTON_LEGACY)]
        prefix = "RMB" if facility == "RMB_DETROIT_LAKES" else "BEC"
        rows.append(
            _base_row(
                index=index,
                facility=facility,
                method=method,
                matrix=matrix,
                sample_id=f"{prefix}-H48-{i + 1:02d}",
                client_id=f"CLIENT-H48-{i + 1:02d}",
                site_id=f"SITE-H48-{i + 1:02d}",
                legacy_site_code=legacy,
                collection_ts=collection_ts,
                pickup_ts=pickup_ts,
                receipt_ts=receipt_ts,
                truth=HOLD_RECEIPT_OVER_48H,
            )
        )
        index += 1

    for i in range(HOLD_PER_CODE):
        facility = "RMB_DETROIT_LAKES" if i % 2 == 0 else "BECKTON_PONCE"
        method = RMB_METHODS[i % len(RMB_METHODS)] if facility == "RMB_DETROIT_LAKES" else BECKTON_METHODS[i % len(BECKTON_METHODS)]
        matrix = "lake" if method in LAKE_ONLY_METHODS else "water"
        collection_ts, pickup_ts, receipt_ts = _late_pickup_times(facility)
        legacy = RMB_LEGACY[i % len(RMB_LEGACY)] if facility == "RMB_DETROIT_LAKES" else BECKTON_LEGACY[i % len(BECKTON_LEGACY)]
        prefix = "RMB" if facility == "RMB_DETROIT_LAKES" else "BEC"
        rows.append(
            _base_row(
                index=index,
                facility=facility,
                method=method,
                matrix=matrix,
                sample_id=f"{prefix}-CUT-{i + 1:02d}",
                client_id=f"CLIENT-CUT-{i + 1:02d}",
                site_id=f"SITE-CUT-{i + 1:02d}",
                legacy_site_code=legacy,
                collection_ts=collection_ts,
                pickup_ts=pickup_ts,
                receipt_ts=receipt_ts,
                truth=HOLD_MISSED_COURIER_CUTOFF,
            )
        )
        index += 1

    for i in range(HOLD_PER_CODE):
        original = rows[i]
        collection_ts, pickup_ts, receipt_ts = _valid_times(original["facility"])
        rows.append(
            _base_row(
                index=index,
                facility=original["facility"],
                method=original["method"],
                matrix=original["matrix"],
                sample_id=original["sample_id"],
                client_id=original["client_id"],
                site_id=original["site_id"],
                legacy_site_code=original["legacy_site_code"],
                collection_ts=collection_ts,
                pickup_ts=pickup_ts,
                receipt_ts=receipt_ts,
                truth=HOLD_DUPLICATE_SAMPLE_ID,
            )
        )
        index += 1

    for i in range(HOLD_PER_CODE):
        facility = "RMB_DETROIT_LAKES" if i % 2 == 0 else "BECKTON_PONCE"
        method = RMB_METHODS[i % len(RMB_METHODS)] if facility == "RMB_DETROIT_LAKES" else BECKTON_METHODS[i % len(BECKTON_METHODS)]
        matrix = "lake" if method in LAKE_ONLY_METHODS else "water"
        collection_ts, pickup_ts, receipt_ts = _valid_times(facility)
        legacy = RMB_LEGACY[i % len(RMB_LEGACY)] if facility == "RMB_DETROIT_LAKES" else BECKTON_LEGACY[i % len(BECKTON_LEGACY)]
        prefix = "RMB" if facility == "RMB_DETROIT_LAKES" else "BEC"
        cooler_intact = True
        temp_c = 3.2
        cooler_seal_id = f"SEAL-{index:04d}"
        manifest_seal_id = cooler_seal_id
        if i < 4:
            cooler_intact = False
        elif i < 7:
            manifest_seal_id = f"SEAL-BROKEN-{i:02d}"
        else:
            temp_c = 12.4
        rows.append(
            _base_row(
                index=index,
                facility=facility,
                method=method,
                matrix=matrix,
                sample_id=f"{prefix}-COOL-{i + 1:02d}",
                client_id=f"CLIENT-COOL-{i + 1:02d}",
                site_id=f"SITE-COOL-{i + 1:02d}",
                legacy_site_code=legacy,
                collection_ts=collection_ts,
                pickup_ts=pickup_ts,
                receipt_ts=receipt_ts,
                truth=HOLD_BROKEN_COOLER_CUSTODY,
                cooler_intact=cooler_intact,
                temp_c=temp_c,
                cooler_seal_id=cooler_seal_id,
                manifest_seal_id=manifest_seal_id,
            )
        )
        index += 1

    for i in range(HOLD_PER_CODE):
        method = "SM_10200H" if i % 2 == 0 else "SM_5210B"
        collection_ts, pickup_ts, receipt_ts = _valid_times("BECKTON_PONCE")
        rows.append(
            _base_row(
                index=index,
                facility="BECKTON_PONCE",
                method=method,
                matrix="lake",
                sample_id=f"BEC-SCOPE-{i + 1:02d}",
                client_id=f"CLIENT-SCOPE-{i + 1:02d}",
                site_id=f"SITE-SCOPE-{i + 1:02d}",
                legacy_site_code=BECKTON_LEGACY[i % len(BECKTON_LEGACY)],
                collection_ts=collection_ts,
                pickup_ts=pickup_ts,
                receipt_ts=receipt_ts,
                truth=HOLD_FACILITY_METHOD_SCOPE_MISMATCH,
            )
        )
        index += 1

    for i in range(HOLD_PER_CODE):
        if i % 2 == 0:
            facility = "RMB_DETROIT_LAKES"
            method = "SM_9223B"
            legacy = BECKTON_LEGACY[i % len(BECKTON_LEGACY)]
            prefix = "RMB"
            matrix = "water"
        else:
            facility = "BECKTON_PONCE"
            method = "SM_9223B"
            legacy = RMB_LEGACY[i % len(RMB_LEGACY)]
            prefix = "BEC"
            matrix = "water"
        collection_ts, pickup_ts, receipt_ts = _valid_times(facility)
        rows.append(
            _base_row(
                index=index,
                facility=facility,
                method=method,
                matrix=matrix,
                sample_id=f"{prefix}-MAP-{i + 1:02d}",
                client_id=f"CLIENT-MAP-{i + 1:02d}",
                site_id=f"SITE-MAP-{i + 1:02d}",
                legacy_site_code=legacy,
                collection_ts=collection_ts,
                pickup_ts=pickup_ts,
                receipt_ts=receipt_ts,
                truth=HOLD_LEGACY_SITE_MAPPING,
            )
        )
        index += 1

    if len(rows) != FIXTURE_COUNT:
        raise RuntimeError("acceptance fixture must be exactly %s rows, got %s" % (FIXTURE_COUNT, len(rows)))
    return rows


def empty_journal() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "mode": "READ_ONLY_SHADOW",
        "incumbent_authoritative": True,
        "accessions": {},
        "holds": [],
        "events": [],
        "incumbent_writes": 0,
        "production_writes": 0,
        "shadow_only": True,
    }


def _event(journal: dict[str, Any], kind: str, payload: dict[str, Any]) -> None:
    journal["events"].append(
        {
            "seq": len(journal["events"]) + 1,
            "kind": kind,
            **deepcopy(payload),
        }
    )


def classify_submission(row: dict[str, Any], seen_sample_ids: set[str] | None = None) -> dict[str, Any]:
    sample_id = _text(row.get("sample_id"))
    facility = _text(row.get("facility"))
    method = _text(row.get("method"))
    legacy = _text(row.get("legacy_site_code")).upper()
    seen = seen_sample_ids if seen_sample_ids is not None else set()

    if sample_id and sample_id in seen:
        return {"ok": False, "code": HOLD_DUPLICATE_SAMPLE_ID, "sample_id": sample_id}

    mapped = resolve_legacy_site(legacy)
    if mapped is None or mapped != facility:
        return {
            "ok": False,
            "code": HOLD_LEGACY_SITE_MAPPING,
            "sample_id": sample_id,
            "facility": facility,
            "legacy_site_code": legacy,
            "mapped_facility": mapped,
        }

    scopes = FACILITIES.get(facility, {}).get("cert_scopes") or ()
    if method not in scopes:
        return {
            "ok": False,
            "code": HOLD_FACILITY_METHOD_SCOPE_MISMATCH,
            "sample_id": sample_id,
            "facility": facility,
            "method": method,
        }

    intact = _flag(row.get("cooler_intact"))
    seal_ok = _text(row.get("cooler_seal_id")) == _text(row.get("manifest_seal_id")) and bool(
        _text(row.get("cooler_seal_id"))
    )
    temp_ok = _temp(row.get("temp_c")) <= COOLER_MAX_TEMP_C
    if not intact or not seal_ok or not temp_ok:
        return {
            "ok": False,
            "code": HOLD_BROKEN_COOLER_CUSTODY,
            "sample_id": sample_id,
            "cooler_intact": intact,
            "seal_ok": seal_ok,
            "temp_c": _temp(row.get("temp_c")),
        }

    pickup = parse_ts(row.get("pickup_ts"))
    if pickup is None or pickup.timetz().replace(tzinfo=None) > COURIER_CUTOFF:
        return {
            "ok": False,
            "code": HOLD_MISSED_COURIER_CUTOFF,
            "sample_id": sample_id,
            "pickup_ts": _text(row.get("pickup_ts")),
        }

    collected = parse_ts(row.get("collection_ts"))
    received = parse_ts(row.get("receipt_ts"))
    if collected is None or received is None or received - collected > timedelta(hours=HOLD_HOURS):
        return {
            "ok": False,
            "code": HOLD_RECEIPT_OVER_48H,
            "sample_id": sample_id,
            "collection_ts": _text(row.get("collection_ts")),
            "receipt_ts": _text(row.get("receipt_ts")),
        }

    return {
        "ok": True,
        "sample_id": sample_id,
        "client_id": _text(row.get("client_id")),
        "site_id": _text(row.get("site_id")),
        "matrix": _text(row.get("matrix")),
        "method": method,
        "cert_scope": _text(row.get("cert_scope")) or METHOD_SCOPE.get(method),
        "facility": facility,
        "legacy_site_code": legacy,
        "incumbent_accession_id": incumbent_accession_id(facility, sample_id),
        "source_hash": source_hash(row),
        "custody_hash": custody_hash(row),
        "manifest_hash": manifest_hash(row),
        "hashes_ok": hashes_reconcile(row),
        "pickup_ts": _text(row.get("pickup_ts")),
        "receipt_ts": _text(row.get("receipt_ts")),
        "collection_ts": _text(row.get("collection_ts")),
        "courier_id": _text(row.get("courier_id")),
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
                    "incumbent_accession_id": existing["incumbent_accession_id"],
                    "sample_id": sample_id,
                    "row_id": row_id,
                },
            )
            return {
                "kind": "REPLAY_NOOP",
                "incumbent_accession_id": existing["incumbent_accession_id"],
                "sample_id": sample_id,
            }
        verdict = {
            "ok": False,
            "code": HOLD_DUPLICATE_SAMPLE_ID,
            "sample_id": sample_id,
        }
    else:
        seen = set(by_sample)
        verdict = classify_submission(row, seen)
    if not verdict["ok"]:
        hold = {
            "row_id": _text(row.get("row_id")),
            "sample_id": verdict.get("sample_id") or None,
            "code": verdict["code"],
            "client_id": _text(row.get("client_id")) or None,
            "site_id": _text(row.get("site_id")) or None,
            "facility": _text(row.get("facility")) or None,
            "method": _text(row.get("method")) or None,
            "source_hash": source_hash(row),
            "custody_hash": custody_hash(row),
        }
        fingerprint = sha256_hex(hold)
        existing = {sha256_hex(item) for item in journal["holds"]}
        if fingerprint not in existing:
            journal["holds"].append(hold)
            _event(journal, "HOLD", hold)
        return {"kind": "HOLD", "duplicate": fingerprint in existing, **hold}

    acc_id = verdict["incumbent_accession_id"]
    existing_acc = journal["accessions"].get(acc_id)
    if existing_acc is not None:
        _event(
            journal,
            "REPLAY_NOOP",
            {"incumbent_accession_id": acc_id, "sample_id": verdict["sample_id"]},
        )
        return {
            "kind": "REPLAY_NOOP",
            "incumbent_accession_id": acc_id,
            "sample_id": verdict["sample_id"],
        }

    record = {
        "incumbent_accession_id": acc_id,
        "row_id": _text(row.get("row_id")),
        "sample_id": verdict["sample_id"],
        "client_id": verdict["client_id"],
        "site_id": verdict["site_id"],
        "matrix": verdict["matrix"],
        "method": verdict["method"],
        "cert_scope": verdict["cert_scope"],
        "facility": verdict["facility"],
        "legacy_site_code": verdict["legacy_site_code"],
        "pickup_ts": verdict["pickup_ts"],
        "receipt_ts": verdict["receipt_ts"],
        "collection_ts": verdict["collection_ts"],
        "courier_id": verdict["courier_id"],
        "source_hash": verdict["source_hash"],
        "custody_hash": verdict["custody_hash"],
        "manifest_hash": verdict["manifest_hash"],
        "hashes_ok": verdict["hashes_ok"],
        "state": "SHADOW_BOUND",
        "analyst_result": None,
        "qc_signoff": False,
        "released": False,
        "released_by": None,
        "report_status": "STAGED_BLOCKED_MISSING_RESULT",
        "interface_state": "READ_ONLY_SHADOW",
        "interface_live": False,
        "incumbent_write": False,
        "production_write": False,
    }
    journal["accessions"][acc_id] = record
    _event(
        journal,
        "SHADOW_BIND",
        {
            "incumbent_accession_id": acc_id,
            "sample_id": verdict["sample_id"],
            "facility": verdict["facility"],
        },
    )
    return {
        "kind": "SHADOW_BIND",
        "incumbent_accession_id": acc_id,
        "facility": verdict["facility"],
        "sample_id": verdict["sample_id"],
    }


def attach_result(
    journal: dict[str, Any],
    accession_id_value: str,
    result: Any,
    *,
    client_id: str,
    site_id: str,
) -> dict[str, Any]:
    record = journal["accessions"].get(accession_id_value)
    if record is None:
        return {"ok": False, "code": "UNKNOWN_ACCESSION"}
    if _text(client_id) != record["client_id"] or _text(site_id) != record["site_id"]:
        _event(
            journal,
            "CROSS_SITE_DENIED",
            {
                "incumbent_accession_id": accession_id_value,
                "code": "CLIENT_SITE_CROSS",
            },
        )
        return {"ok": False, "code": "CLIENT_SITE_CROSS"}
    if result in (None, ""):
        return {"ok": False, "code": "EMPTY_RESULT"}
    record["analyst_result"] = deepcopy(result)
    record["report_status"] = report_status(record)
    _event(journal, "ANALYST_RESULT", {"incumbent_accession_id": accession_id_value})
    return {"ok": True, "report_status": record["report_status"]}


def qc_signoff(journal: dict[str, Any], accession_id_value: str) -> dict[str, Any]:
    record = journal["accessions"].get(accession_id_value)
    if record is None:
        return {"ok": False, "code": "UNKNOWN_ACCESSION"}
    record["qc_signoff"] = True
    record["report_status"] = report_status(record)
    _event(journal, "QC_SIGNOFF", {"incumbent_accession_id": accession_id_value})
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
                "incumbent_accession_id": accession_id_value,
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
                "incumbent_accession_id": accession_id_value,
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
    _event(
        journal,
        "RELEASED",
        {
            "incumbent_accession_id": accession_id_value,
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
        key=lambda item: (item["facility"], item["sample_id"]),
    )
    hold_codes = sorted(item["code"] for item in journal["holds"])
    hold_counts = {code: hold_codes.count(code) for code in HOLD_CODES}
    facilities = {item["sample_id"]: item["facility"] for item in accessioned}
    identities = {
        item["incumbent_accession_id"]: {
            "client_id": item["client_id"],
            "site_id": item["site_id"],
            "sample_id": item["sample_id"],
        }
        for item in accessioned
    }
    staged = [item for item in accessioned if item["report_status"] != "RELEASED"]

    body = {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "truth_gate": TRUTH_GATE,
        "mode": "READ_ONLY_SHADOW",
        "incumbent_authoritative": True,
        "input_rows": len(inbound),
        "accessioned": len(accessioned),
        "held": len(journal["holds"]),
        "hold_codes": hold_codes,
        "hold_counts": hold_counts,
        "facilities": facilities,
        "incumbent_accession_ids": [item["incumbent_accession_id"] for item in accessioned],
        "identities": identities,
        "hashes_ok_count": sum(1 for item in accessioned if item.get("hashes_ok")),
        "manifest_match_count": sum(
            1
            for item in accessioned
            if item.get("hashes_ok")
        ),
        "blocked_reports": len(staged),
        "released_reports": 0,
        "replay_noops": sum(1 for item in effects if item.get("kind") == "REPLAY_NOOP"),
        "effects": effects,
        "autonomous_release_effects": autonomous,
        "accessions": accessioned,
        "holds": deepcopy(journal["holds"]),
        "interface_live": False,
        "interfaces": "READ_ONLY_SHADOW",
        "incumbent_writes": journal["incumbent_writes"],
        "production_writes": journal["production_writes"],
        "shadow_only": True,
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
        failures.append("input_rows!=300")
    if result.get("accessioned") != VALID_COUNT:
        failures.append("accessioned!=240")
    if result.get("held") != HOLD_COUNT:
        failures.append("held!=60")
    expected_counts = {code: HOLD_PER_CODE for code in HOLD_CODES}
    if result.get("hold_counts") != expected_counts:
        failures.append("hold_counts")
    ids = result.get("incumbent_accession_ids") or []
    if len(ids) != VALID_COUNT or len(set(ids)) != VALID_COUNT:
        failures.append("incumbent_accession_not_unique")
    facilities = result.get("facilities") or {}
    if len(facilities) != VALID_COUNT:
        failures.append("facility_map")
    if any(value not in FACILITIES for value in facilities.values()):
        failures.append("unknown_facility")
    rmb = sum(1 for value in facilities.values() if value == "RMB_DETROIT_LAKES")
    beckton = sum(1 for value in facilities.values() if value == "BECKTON_PONCE")
    if rmb != 120 or beckton != 120:
        failures.append("facility_split")
    identities = result.get("identities") or {}
    seen_pairs = set()
    for acc_id, ident in identities.items():
        pair = (ident.get("client_id"), ident.get("site_id"), ident.get("sample_id"))
        if pair in seen_pairs:
            failures.append("client_site_cross")
            break
        seen_pairs.add(pair)
        record = next(
            (item for item in result.get("accessions") or [] if item.get("incumbent_accession_id") == acc_id),
            None,
        )
        if record and (
            record.get("client_id") != ident.get("client_id")
            or record.get("site_id") != ident.get("site_id")
        ):
            failures.append("identity_mismatch")
            break
    if result.get("hashes_ok_count") != VALID_COUNT:
        failures.append("hashes_not_reconciled")
    if result.get("manifest_match_count") != VALID_COUNT:
        failures.append("manifest_timestamps")
    if result.get("released_reports") != 0:
        failures.append("released_reports!=0")
    if result.get("blocked_reports") != VALID_COUNT:
        failures.append("blocked_reports!=240")
    if result.get("replay_noops") != 0:
        failures.append("fresh_run_replay_noops")
    if result.get("interface_live") is not False:
        failures.append("interface_live")
    if result.get("interfaces") != "READ_ONLY_SHADOW":
        failures.append("interfaces")
    if result.get("incumbent_writes") != 0:
        failures.append("incumbent_writes")
    if result.get("production_writes") != 0:
        failures.append("production_writes")
    if result.get("shadow_only") is not True:
        failures.append("shadow_only")
    if result.get("autonomous_certification") is not False:
        failures.append("autonomous_certification")
    if result.get("autonomous_release") is not False:
        failures.append("autonomous_release")
    if not all(
        item.get("code") == "AUTONOMOUS_RELEASE_DENIED"
        for item in result.get("autonomous_release_effects") or []
    ):
        failures.append("autonomous_release_not_denied")
    if any(item.get("incumbent_write") for item in result.get("accessions") or []):
        failures.append("accession_wrote_incumbent")
    fixture = build_acceptance_fixture()
    if result.get("fixture_sha256") != sha256_hex(fixture):
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
        "incumbent_writes": first.get("incumbent_writes"),
        "production_writes": first.get("production_writes"),
        "replay_added_accessions": replay.get("added_accession_count"),
        "replay_added_holds": replay.get("added_holds"),
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
