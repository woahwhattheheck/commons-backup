#!/usr/bin/env python3
"""Chemtech-Ford Short-Hold Sample Intake Clock.

Demand: chemtechford-short-hold-intake-lims-01
Buyer: Chemtech-Ford Laboratories / Reed Hendricks

Working intake clock for drinking-water and wastewater submissions.
Normalizes portal and chain-of-custody records, applies container /
preservation / temperature / signature gates, evaluates the fixture
six-hour wastewater and 24-hour drinking-water collection-to-receipt
clocks, mints exactly one accession per valid sample with those
timestamps, reconciles portal and state-delivery records to the signed
manifest, and blocks release until a named human signs.

Adapters stay synthetic and read-only / simulated. Actual holding-time
and preservation rules require buyer validation. HOLD / BUILD-AND-VERIFY.
No outreach. PRE-SALE TRANSPORT: NONE. cash_usd=0.

Official command:
    python3 chemtechford_short_hold_intake_lims.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any

DEMAND_ID = "chemtechford-short-hold-intake-lims-01"
SCHEMA = "commons-chemtechford-short-hold-intake-lims/v1"
TRUTH_GATE = "HOLD / BUILD-AND-VERIFY"
BUYER = "Chemtech-Ford Laboratories / Reed Hendricks"
HUMAN_APPROVER = "SYN-CFL-RELEASER"
HUMAN_ROLE = "NAMED_HUMAN_RELEASER"

VALID_COUNT = 450
TEMPERATURE_COUNT = 25
CONTAINER_COUNT = 25
PRESERVATION_COUNT = 25
SIGNATURE_COUNT = 25
DUPLICATE_COUNT = 25
HOLDING_TIME_COUNT = 25
REJECT_COUNT = (
    TEMPERATURE_COUNT
    + CONTAINER_COUNT
    + PRESERVATION_COUNT
    + SIGNATURE_COUNT
    + DUPLICATE_COUNT
    + HOLDING_TIME_COUNT
)
INPUT_COUNT = VALID_COUNT + REJECT_COUNT
WW_VALID_COUNT = 225
DW_VALID_COUNT = 225
WW_EXACT_BOUNDARY = 15
DW_EXACT_BOUNDARY = 15
WW_HOLDING_OVER = 13
DW_HOLDING_OVER = 12

WW_HOLDING_HOURS = 6
DW_HOLDING_HOURS = 24
WW_HOLDING_SECONDS = WW_HOLDING_HOURS * 3600
DW_HOLDING_SECONDS = DW_HOLDING_HOURS * 3600
TEMP_MIN_C = 0.0
TEMP_MAX_C = 6.0

REJECT_CODES = (
    "TEMPERATURE",
    "CONTAINER",
    "PRESERVATION",
    "SIGNATURE",
    "DUPLICATE_ID",
    "HOLDING_TIME",
)
REJECT_FAMILY_COUNTS = {
    "TEMPERATURE": TEMPERATURE_COUNT,
    "CONTAINER": CONTAINER_COUNT,
    "PRESERVATION": PRESERVATION_COUNT,
    "SIGNATURE": SIGNATURE_COUNT,
    "DUPLICATE_ID": DUPLICATE_COUNT,
    "HOLDING_TIME": HOLDING_TIME_COUNT,
}

MATRICES = ("WASTEWATER", "DRINKING_WATER")

# Synthetic fixture catalog. Not a live Chemtech-Ford method menu.
METHOD_CATALOG: dict[str, dict[str, Any]] = {
    "SYN-CFL-WW-FC": {
        "matrix": "WASTEWATER",
        "container": "STERILE_HDPE",
        "preservation": "NA2S2O3",
        "family": "fecal_coliform",
    },
    "SYN-CFL-WW-BOD": {
        "matrix": "WASTEWATER",
        "container": "HDPE",
        "preservation": "NONE",
        "family": "biochemical_oxygen_demand",
    },
    "SYN-CFL-WW-NH3": {
        "matrix": "WASTEWATER",
        "container": "HDPE",
        "preservation": "H2SO4",
        "family": "ammonia",
    },
    "SYN-CFL-DW-TC": {
        "matrix": "DRINKING_WATER",
        "container": "STERILE_HDPE",
        "preservation": "NA2S2O3",
        "family": "total_coliform",
    },
    "SYN-CFL-DW-CL2": {
        "matrix": "DRINKING_WATER",
        "container": "HDPE",
        "preservation": "NONE",
        "family": "chlorine_residual",
    },
    "SYN-CFL-DW-NO3": {
        "matrix": "DRINKING_WATER",
        "container": "HDPE",
        "preservation": "H2SO4",
        "family": "nitrate",
    },
}
WW_METHODS = tuple(code for code, spec in METHOD_CATALOG.items() if spec["matrix"] == "WASTEWATER")
DW_METHODS = tuple(code for code, spec in METHOD_CATALOG.items() if spec["matrix"] == "DRINKING_WATER")
WRONG_CONTAINER = "GLASS_AMBER"
WRONG_PRESERVATION = "HNO3"

AUTONOMOUS_NAMES = frozenset({"SYSTEM", "AUTO", "AUTONOMOUS", "BOT", "MACHINE"})

EPOCH = datetime(2026, 8, 1, 12, 0, 0, tzinfo=timezone.utc)

GOLDEN_FIXTURE_SHA256 = "8417c082454e8e4efabaf84598e9a6252e17b88fcbdbdbd40f4d19069ed25787"
GOLDEN_CATALOG_SHA256 = "05a87605889e3098f93ab40faad58066bbf00355b52732042a27995d5c53fc2c"
GOLDEN_MANIFEST_SHA256 = "3e72ae5bd33ae6b0bc9cd0e88a0c7c804e6fdf30e7ceb731013195d44d7c9645"
GOLDEN_SIGNED_MANIFEST_ROLLUP = "04bfd92d84f5a4536017e10cac1a053149ee19106af4c875f08d658cc5d837c7"

EXPECTED_COUNTS = {
    "input_rows": INPUT_COUNT,
    "accessioned": VALID_COUNT,
    "rejected": REJECT_COUNT,
    "reject_temperature": TEMPERATURE_COUNT,
    "reject_container": CONTAINER_COUNT,
    "reject_preservation": PRESERVATION_COUNT,
    "reject_signature": SIGNATURE_COUNT,
    "reject_duplicate_id": DUPLICATE_COUNT,
    "reject_holding_time": HOLDING_TIME_COUNT,
    "ww_accessioned": WW_VALID_COUNT,
    "dw_accessioned": DW_VALID_COUNT,
    "ww_exact_6h": WW_EXACT_BOUNDARY,
    "dw_exact_24h": DW_EXACT_BOUNDARY,
    "duplicates": 0,
    "replay_added_accessions": 0,
    "reconcile_ok": VALID_COUNT,
    "reconcile_fail": 0,
    "released": 0,
    "production_writes": 0,
}

OFFICIAL_BINARY = "python3 chemtechford_short_hold_intake_lims.py"
OFFICIAL_TEST = "python3 test_chemtechford_short_hold_intake_lims.py"


def _text(value: Any) -> str:
    return str("" if value is None else value).strip()


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_hex(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def iso(moment: datetime) -> str:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(value: str) -> datetime:
    text = _text(value).replace("Z", "+00:00")
    return datetime.fromisoformat(text).astimezone(timezone.utc)


def holding_limit_seconds(matrix: str) -> int:
    if matrix == "WASTEWATER":
        return WW_HOLDING_SECONDS
    if matrix == "DRINKING_WATER":
        return DW_HOLDING_SECONDS
    raise ValueError(f"unknown matrix {matrix!r}")


CATALOG_SHA256 = sha256_hex(METHOD_CATALOG)


def _method_for(matrix: str, index: int) -> str:
    pool = WW_METHODS if matrix == "WASTEWATER" else DW_METHODS
    return pool[(index - 1) % len(pool)]


def _clock_pair(matrix: str, seconds: int, offset_index: int) -> tuple[str, str]:
    collected = EPOCH + timedelta(seconds=offset_index * 60)
    received = collected + timedelta(seconds=seconds)
    return iso(collected), iso(received)


def _source_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "sample_id": row["sample_id"],
        "matrix": row["matrix"],
        "method": row["method"],
        "container": row["container"],
        "preservation": row["preservation"],
        "temp_c": row["temp_c"],
        "collector_signature": row["collector_signature"],
        "collected_at": row["collected_at"],
        "received_at": row["received_at"],
        "portal_record_id": row["portal_record_id"],
        "state_delivery_id": row["state_delivery_id"],
        "coc_id": row["coc_id"],
    }


def _portal_view(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "Sample ID": row["sample_id"],
        "Date/Time Collected": row["collected_at"],
        "Date/Time Received": row["received_at"],
        "Matrix": "Wastewater" if row["matrix"] == "WASTEWATER" else "Drinking Water",
        "Method": row["method"],
        "Bottle": row["container"],
        "Preservative": row["preservation"],
        "Temperature (°C)": row["temp_c"],
        "Collected By": row["collector_signature"],
        "Portal Record": row["portal_record_id"],
        "State Delivery": row["state_delivery_id"],
        "COC": row["coc_id"],
    }


def _coc_view(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "sample_id": row["sample_id"],
        "collected_at": row["collected_at"],
        "received_at": row["received_at"],
        "matrix": row["matrix"],
        "method": row["method"],
        "container": row["container"],
        "preservation": row["preservation"],
        "temp_c": row["temp_c"],
        "collector_signature": row["collector_signature"],
        "portal_record_id": row["portal_record_id"],
        "state_delivery_id": row["state_delivery_id"],
        "coc_id": row["coc_id"],
    }


def _state_view(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "state_delivery_id": row["state_delivery_id"],
        "sample_id": row["sample_id"],
        "collected_at": row["collected_at"],
        "received_at": row["received_at"],
        "matrix": row["matrix"],
        "method": row["method"],
    }


def _base_row(
    index: int,
    *,
    sample_id: str,
    matrix: str,
    method: str,
    collected_at: str,
    received_at: str,
    expected_state: str,
    expected_reason: str | None,
    temp_c: float = 4.0,
    container: str | None = None,
    preservation: str | None = None,
    collector_signature: str | None = None,
) -> dict[str, Any]:
    spec = METHOD_CATALOG[method]
    row = {
        "index": index,
        "sample_id": sample_id,
        "matrix": matrix,
        "method": method,
        "container": container if container is not None else spec["container"],
        "preservation": preservation if preservation is not None else spec["preservation"],
        "temp_c": temp_c,
        "collector_signature": collector_signature if collector_signature is not None else f"SYN-COLLECTOR-{index:04d}",
        "collected_at": collected_at,
        "received_at": received_at,
        "portal_record_id": f"SYN-PORTAL-{index:04d}",
        "state_delivery_id": f"SYN-STATE-{index:04d}",
        "coc_id": f"SYN-COC-{index:04d}",
        "expected_state": expected_state,
        "expected_reason": expected_reason,
    }
    row["clock_seconds"] = int((parse_iso(received_at) - parse_iso(collected_at)).total_seconds())
    row["holding_limit_seconds"] = holding_limit_seconds(matrix)
    row["source_hash"] = sha256_hex(_source_payload(row))
    return row


def build_acceptance_fixture() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    # 450 valid: odd = wastewater, even = drinking water. First 15 of each
    # matrix sit on the exact fixture clock; the rest stay two hours under.
    for index in range(1, VALID_COUNT + 1):
        matrix = "WASTEWATER" if index % 2 == 1 else "DRINKING_WATER"
        method = _method_for(matrix, index)
        if matrix == "WASTEWATER":
            ww_n = (index + 1) // 2
            seconds = WW_HOLDING_SECONDS if ww_n <= WW_EXACT_BOUNDARY else 2 * 3600
        else:
            dw_n = index // 2
            seconds = DW_HOLDING_SECONDS if dw_n <= DW_EXACT_BOUNDARY else 3 * 3600
        collected_at, received_at = _clock_pair(matrix, seconds, index)
        rows.append(
            _base_row(
                index,
                sample_id=f"CFL-S-{index:04d}",
                matrix=matrix,
                method=method,
                collected_at=collected_at,
                received_at=received_at,
                expected_state="ACCESSIONED",
                expected_reason=None,
            )
        )

    cursor = VALID_COUNT
    for offset in range(TEMPERATURE_COUNT):
        cursor += 1
        matrix = "WASTEWATER" if offset % 2 == 0 else "DRINKING_WATER"
        method = _method_for(matrix, cursor)
        collected_at, received_at = _clock_pair(matrix, 2 * 3600, cursor)
        rows.append(
            _base_row(
                cursor,
                sample_id=f"CFL-S-{cursor:04d}",
                matrix=matrix,
                method=method,
                collected_at=collected_at,
                received_at=received_at,
                expected_state="REJECTED",
                expected_reason="TEMPERATURE",
                temp_c=10.5,
            )
        )
    for offset in range(CONTAINER_COUNT):
        cursor += 1
        matrix = "WASTEWATER" if offset % 2 == 0 else "DRINKING_WATER"
        method = _method_for(matrix, cursor)
        collected_at, received_at = _clock_pair(matrix, 2 * 3600, cursor)
        rows.append(
            _base_row(
                cursor,
                sample_id=f"CFL-S-{cursor:04d}",
                matrix=matrix,
                method=method,
                collected_at=collected_at,
                received_at=received_at,
                expected_state="REJECTED",
                expected_reason="CONTAINER",
                container=WRONG_CONTAINER,
            )
        )
    for offset in range(PRESERVATION_COUNT):
        cursor += 1
        matrix = "WASTEWATER" if offset % 2 == 0 else "DRINKING_WATER"
        method = _method_for(matrix, cursor)
        collected_at, received_at = _clock_pair(matrix, 2 * 3600, cursor)
        rows.append(
            _base_row(
                cursor,
                sample_id=f"CFL-S-{cursor:04d}",
                matrix=matrix,
                method=method,
                collected_at=collected_at,
                received_at=received_at,
                expected_state="REJECTED",
                expected_reason="PRESERVATION",
                preservation=WRONG_PRESERVATION,
            )
        )
    for offset in range(SIGNATURE_COUNT):
        cursor += 1
        matrix = "WASTEWATER" if offset % 2 == 0 else "DRINKING_WATER"
        method = _method_for(matrix, cursor)
        collected_at, received_at = _clock_pair(matrix, 2 * 3600, cursor)
        rows.append(
            _base_row(
                cursor,
                sample_id=f"CFL-S-{cursor:04d}",
                matrix=matrix,
                method=method,
                collected_at=collected_at,
                received_at=received_at,
                expected_state="REJECTED",
                expected_reason="SIGNATURE",
                collector_signature="",
            )
        )
    for offset in range(DUPLICATE_COUNT):
        cursor += 1
        source = rows[offset]
        collected_at, received_at = _clock_pair(source["matrix"], 2 * 3600, cursor)
        rows.append(
            _base_row(
                cursor,
                sample_id=source["sample_id"],
                matrix=source["matrix"],
                method=source["method"],
                collected_at=collected_at,
                received_at=received_at,
                expected_state="REJECTED",
                expected_reason="DUPLICATE_ID",
            )
        )
        rows[-1]["portal_record_id"] = f"SYN-PORTAL-{cursor:04d}"
        rows[-1]["state_delivery_id"] = f"SYN-STATE-{cursor:04d}"
        rows[-1]["coc_id"] = f"SYN-COC-{cursor:04d}"
        rows[-1]["source_hash"] = sha256_hex(_source_payload(rows[-1]))
    for offset in range(HOLDING_TIME_COUNT):
        cursor += 1
        if offset < WW_HOLDING_OVER:
            matrix = "WASTEWATER"
            seconds = WW_HOLDING_SECONDS + 1
        else:
            matrix = "DRINKING_WATER"
            seconds = DW_HOLDING_SECONDS + 1
        method = _method_for(matrix, cursor)
        collected_at, received_at = _clock_pair(matrix, seconds, cursor)
        rows.append(
            _base_row(
                cursor,
                sample_id=f"CFL-S-{cursor:04d}",
                matrix=matrix,
                method=method,
                collected_at=collected_at,
                received_at=received_at,
                expected_state="REJECTED",
                expected_reason="HOLDING_TIME",
            )
        )
    if len(rows) != INPUT_COUNT:
        raise RuntimeError(f"fixture size {len(rows)} != {INPUT_COUNT}")
    return rows


def fixture_sha256(rows: list[dict[str, Any]] | None = None) -> str:
    inbound = rows if rows is not None else build_acceptance_fixture()
    return sha256_hex([_source_payload(row) | {"expected_state": row["expected_state"], "expected_reason": row["expected_reason"]} for row in inbound])


def fixture_manifest() -> dict[str, Any]:
    rows = build_acceptance_fixture()
    return {
        "demand_id": DEMAND_ID,
        "input_rows": len(rows),
        "fixture_sha256": fixture_sha256(rows),
        "catalog_sha256": CATALOG_SHA256,
    }


PORTAL_ALIASES = {
    "sample_id": ("sample_id", "Sample ID", "sampleId"),
    "collected_at": ("collected_at", "Date/Time Collected", "collectedAt"),
    "received_at": ("received_at", "Date/Time Received", "receivedAt"),
    "matrix": ("matrix", "Matrix"),
    "method": ("method", "Method"),
    "container": ("container", "Bottle"),
    "preservation": ("preservation", "Preservative"),
    "temp_c": ("temp_c", "Temperature (°C)", "temperatureC"),
    "collector_signature": ("collector_signature", "Collected By", "collectorSignature"),
    "portal_record_id": ("portal_record_id", "Portal Record", "portalRecordId"),
    "state_delivery_id": ("state_delivery_id", "State Delivery", "stateDeliveryId"),
    "coc_id": ("coc_id", "COC", "cocId"),
}

MATRIX_ALIASES = {
    "wastewater": "WASTEWATER",
    "ww": "WASTEWATER",
    "drinking water": "DRINKING_WATER",
    "drinking-water": "DRINKING_WATER",
    "dw": "DRINKING_WATER",
    "WASTEWATER": "WASTEWATER",
    "DRINKING_WATER": "DRINKING_WATER",
}


def _pick(record: dict[str, Any], names: tuple[str, ...]) -> Any:
    for name in names:
        if name in record and record[name] not in (None, ""):
            return record[name]
    for name in names:
        if name in record:
            return record[name]
    return None


def normalize_submission(portal: dict[str, Any], coc: dict[str, Any] | None = None) -> dict[str, Any]:
    merged = {}
    if coc:
        merged.update(coc)
    merged.update(portal)
    canonical: dict[str, Any] = {}
    for field, names in PORTAL_ALIASES.items():
        canonical[field] = _pick(merged, names)
    matrix = MATRIX_ALIASES.get(_text(canonical.get("matrix")), _text(canonical.get("matrix")).upper().replace(" ", "_"))
    canonical["matrix"] = matrix
    temp = canonical.get("temp_c")
    canonical["temp_c"] = float(temp) if temp not in (None, "") else None
    canonical["collector_signature"] = _text(canonical.get("collector_signature"))
    for key in ("sample_id", "method", "container", "preservation", "collected_at", "received_at", "portal_record_id", "state_delivery_id", "coc_id"):
        canonical[key] = _text(canonical.get(key))
    if canonical["collected_at"] and canonical["received_at"]:
        canonical["clock_seconds"] = int(
            (parse_iso(canonical["received_at"]) - parse_iso(canonical["collected_at"])).total_seconds()
        )
    else:
        canonical["clock_seconds"] = None
    canonical["holding_limit_seconds"] = holding_limit_seconds(matrix) if matrix in MATRICES else None
    return canonical


class ReadOnlyPortalAdapter:
    mode = "READ_ONLY"
    live = False

    def __init__(self, rows: list[dict[str, Any]]):
        self._records = [_portal_view(row) for row in rows]
        self.writes = 0

    def list_submissions(self) -> list[dict[str, Any]]:
        return deepcopy(self._records)

    def write(self, record: dict[str, Any]) -> None:
        raise RuntimeError("portal adapter is read-only")


class ReadOnlyCocAdapter:
    mode = "READ_ONLY"
    live = False

    def __init__(self, rows: list[dict[str, Any]]):
        self._records = {row["coc_id"]: _coc_view(row) for row in rows}
        self.writes = 0

    def get(self, coc_id: str) -> dict[str, Any] | None:
        record = self._records.get(coc_id)
        return deepcopy(record) if record is not None else None

    def write(self, record: dict[str, Any]) -> None:
        raise RuntimeError("coc adapter is read-only")


class ReadOnlyStateDeliveryAdapter:
    mode = "READ_ONLY"
    live = False

    def __init__(self, rows: list[dict[str, Any]]):
        self._by_delivery = {row["state_delivery_id"]: _state_view(row) for row in rows}
        self._by_sample: dict[str, dict[str, Any]] = {}
        for row in rows:
            self._by_sample.setdefault(row["sample_id"], _state_view(row))
        self.writes = 0

    def get(self, sample_id: str) -> dict[str, Any] | None:
        record = self._by_sample.get(sample_id)
        return deepcopy(record) if record is not None else None

    def get_delivery(self, state_delivery_id: str) -> dict[str, Any] | None:
        record = self._by_delivery.get(state_delivery_id)
        return deepcopy(record) if record is not None else None

    def write(self, record: dict[str, Any]) -> None:
        raise RuntimeError("state-delivery adapter is read-only")


class ReadOnlyInstrumentAdapter:
    mode = "READ_ONLY"
    live = False

    def __init__(self, rows: list[dict[str, Any]]):
        self._temps: dict[str, float] = {}
        for row in rows:
            self._temps.setdefault(row["sample_id"], float(row["temp_c"]))
        self.writes = 0

    def temperature_c(self, sample_id: str) -> float | None:
        return self._temps.get(sample_id)

    def write(self, record: dict[str, Any]) -> None:
        raise RuntimeError("instrument adapter is read-only")


class ReadOnlyDeliveryAdapter:
    mode = "READ_ONLY"
    live = False

    def __init__(self, rows: list[dict[str, Any]]):
        self._receipts: dict[str, dict[str, Any]] = {}
        for row in rows:
            self._receipts.setdefault(
                row["sample_id"],
                {"received_at": row["received_at"], "state_delivery_id": row["state_delivery_id"]},
            )
        self.writes = 0

    def receipt(self, sample_id: str) -> dict[str, Any] | None:
        record = self._receipts.get(sample_id)
        return deepcopy(record) if record is not None else None

    def write(self, record: dict[str, Any]) -> None:
        raise RuntimeError("delivery adapter is read-only")


class SimulatedLimsAdapter:
    mode = "SIMULATED"
    live = False

    def __init__(self) -> None:
        self.accessions: dict[str, dict[str, Any]] = {}
        self.by_sample: dict[str, str] = {}
        self.production_writes = 0

    def put(self, accession: dict[str, Any]) -> None:
        self.accessions[accession["accession_id"]] = deepcopy(accession)
        self.by_sample[accession["sample_id"]] = accession["accession_id"]

    def get_by_sample(self, sample_id: str) -> dict[str, Any] | None:
        accession_id = self.by_sample.get(sample_id)
        if not accession_id:
            return None
        return deepcopy(self.accessions[accession_id])


def empty_journal() -> dict[str, Any]:
    return {
        "accessions": {},
        "rejects": [],
        "released": {},
        "events": [],
        "seen_sample_ids": set(),
    }


def _event(journal: dict[str, Any], kind: str, payload: dict[str, Any]) -> None:
    journal["events"].append({"kind": kind, **payload})


def classify(canonical: dict[str, Any], journal: dict[str, Any], instrument: ReadOnlyInstrumentAdapter) -> str | None:
    sample_id = canonical.get("sample_id") or ""
    if not sample_id:
        return "DUPLICATE_ID"
    if sample_id in journal["accessions"]:
        return "DUPLICATE_ID"
    if not canonical.get("collector_signature"):
        return "SIGNATURE"
    temp = instrument.temperature_c(sample_id)
    if temp is None:
        temp = canonical.get("temp_c")
    if temp is None or temp < TEMP_MIN_C or temp > TEMP_MAX_C:
        return "TEMPERATURE"
    spec = METHOD_CATALOG.get(canonical.get("method") or "")
    if spec is None or canonical.get("container") != spec["container"]:
        return "CONTAINER"
    if spec is None or canonical.get("preservation") != spec["preservation"]:
        return "PRESERVATION"
    clock = canonical.get("clock_seconds")
    limit = canonical.get("holding_limit_seconds")
    if clock is None or limit is None or clock > limit:
        return "HOLDING_TIME"
    return None


def signed_manifest_body(accession: dict[str, Any]) -> dict[str, Any]:
    return {
        "accession_id": accession["accession_id"],
        "sample_id": accession["sample_id"],
        "collected_at": accession["collected_at"],
        "received_at": accession["received_at"],
        "accessioned_at": accession["accessioned_at"],
        "clock_seconds": accession["clock_seconds"],
        "matrix": accession["matrix"],
        "method": accession["method"],
        "portal_hash": accession["portal_hash"],
        "state_hash": accession["state_hash"],
    }


def ingest_submission(
    journal: dict[str, Any],
    lims: SimulatedLimsAdapter,
    portal_record: dict[str, Any],
    coc_record: dict[str, Any],
    state_record: dict[str, Any] | None,
    instrument: ReadOnlyInstrumentAdapter,
) -> dict[str, Any]:
    canonical = normalize_submission(portal_record, coc_record)
    sample_id = canonical["sample_id"]
    portal_record_id = canonical["portal_record_id"]
    existing_same_portal = next(
        (item for item in journal["accessions"].values() if item["portal_record_id"] == portal_record_id),
        None,
    )
    if existing_same_portal is None:
        stored = lims.get_by_sample(sample_id)
        if stored is not None and stored.get("portal_record_id") == portal_record_id:
            existing_same_portal = stored
    if existing_same_portal is not None:
        _event(journal, "REPLAY_NOOP", {"sample_id": sample_id, "accession_id": existing_same_portal["accession_id"]})
        return {"kind": "REPLAY_NOOP", "sample_id": sample_id, "accession_id": existing_same_portal["accession_id"]}
    prior_reject = next(
        (item for item in journal["rejects"] if item.get("portal_record_id") == portal_record_id),
        None,
    )
    if prior_reject is not None:
        _event(journal, "REPLAY_NOOP", {"sample_id": sample_id, "reason": prior_reject["reason"]})
        return {"kind": "REPLAY_NOOP", "sample_id": sample_id, "reason": prior_reject["reason"]}
    reason = classify(canonical, journal, instrument)
    if reason is not None:
        record = {
            "sample_id": sample_id,
            "reason": reason,
            "state": "REJECTED",
            "clock_seconds": canonical.get("clock_seconds"),
            "holding_limit_seconds": canonical.get("holding_limit_seconds"),
            "matrix": canonical.get("matrix"),
            "method": canonical.get("method"),
            "portal_record_id": canonical["portal_record_id"],
            "source_hash": sha256_hex(_source_payload({**canonical, "portal_record_id": canonical["portal_record_id"], "state_delivery_id": canonical["state_delivery_id"], "coc_id": canonical["coc_id"]})),
        }
        journal["rejects"].append(record)
        _event(journal, "REJECTED", {"sample_id": sample_id, "reason": reason})
        return {"kind": "REJECTED", "sample_id": sample_id, "reason": reason}

    accession_seq = len(journal["accessions"]) + 1
    accession_id = f"CFL-ACC-{accession_seq:06d}"
    portal_hash = sha256_hex({
        "sample_id": canonical["sample_id"],
        "collected_at": canonical["collected_at"],
        "received_at": canonical["received_at"],
        "matrix": canonical["matrix"],
        "method": canonical["method"],
        "portal_record_id": canonical["portal_record_id"],
    })
    state_body = state_record or {}
    state_hash = sha256_hex({
        "sample_id": state_body.get("sample_id") or canonical["sample_id"],
        "collected_at": state_body.get("collected_at") or canonical["collected_at"],
        "received_at": state_body.get("received_at") or canonical["received_at"],
        "matrix": state_body.get("matrix") or canonical["matrix"],
        "method": state_body.get("method") or canonical["method"],
        "state_delivery_id": state_body.get("state_delivery_id") or canonical["state_delivery_id"],
    })
    accession = {
        "accession_id": accession_id,
        "sample_id": sample_id,
        "collected_at": canonical["collected_at"],
        "received_at": canonical["received_at"],
        "accessioned_at": canonical["received_at"],
        "clock_seconds": canonical["clock_seconds"],
        "holding_limit_seconds": canonical["holding_limit_seconds"],
        "matrix": canonical["matrix"],
        "method": canonical["method"],
        "container": canonical["container"],
        "preservation": canonical["preservation"],
        "temp_c": canonical["temp_c"],
        "collector_signature": canonical["collector_signature"],
        "portal_record_id": canonical["portal_record_id"],
        "state_delivery_id": canonical["state_delivery_id"],
        "coc_id": canonical["coc_id"],
        "portal_hash": portal_hash,
        "state_hash": state_hash,
        "released": False,
        "released_by": None,
    }
    accession["signed_manifest_sha256"] = sha256_hex(signed_manifest_body(accession))
    accession["source_hash"] = sha256_hex(_source_payload(canonical))
    journal["accessions"][sample_id] = accession
    journal["seen_sample_ids"].add(sample_id)
    lims.put(accession)
    _event(journal, "ACCESSIONED", {"sample_id": sample_id, "accession_id": accession_id})
    return {"kind": "ACCESSIONED", "sample_id": sample_id, "accession_id": accession_id}


def reconcile_accession(
    accession: dict[str, Any],
    portal: dict[str, Any],
    state: dict[str, Any],
) -> dict[str, Any]:
    canonical = normalize_submission(portal)
    portal_hash = sha256_hex({
        "sample_id": canonical["sample_id"],
        "collected_at": canonical["collected_at"],
        "received_at": canonical["received_at"],
        "matrix": canonical["matrix"],
        "method": canonical["method"],
        "portal_record_id": canonical["portal_record_id"],
    })
    state_hash = sha256_hex({
        "sample_id": state.get("sample_id"),
        "collected_at": state.get("collected_at"),
        "received_at": state.get("received_at"),
        "matrix": state.get("matrix"),
        "method": state.get("method"),
        "state_delivery_id": state.get("state_delivery_id"),
    })
    expected = signed_manifest_body({
        **accession,
        "portal_hash": portal_hash,
        "state_hash": state_hash,
    })
    expected_hash = sha256_hex(expected)
    ok = (
        expected_hash == accession["signed_manifest_sha256"]
        and portal_hash == accession["portal_hash"]
        and state_hash == accession["state_hash"]
        and canonical["collected_at"] == accession["collected_at"]
        and canonical["received_at"] == accession["received_at"]
        and canonical["clock_seconds"] == accession["clock_seconds"]
    )
    return {"ok": ok, "expected_hash": expected_hash, "actual_hash": accession["signed_manifest_sha256"]}


def release_accession(journal: dict[str, Any], sample_id: str, *, named_approver: str) -> dict[str, Any]:
    record = journal["accessions"].get(sample_id)
    if record is None:
        return {"ok": False, "code": "UNKNOWN_SAMPLE"}
    name = _text(named_approver)
    if not name:
        _event(journal, "RELEASE_DENIED", {"sample_id": sample_id, "code": "MISSING_NAMED_APPROVAL"})
        return {"ok": False, "code": "MISSING_NAMED_APPROVAL"}
    if name.upper() in AUTONOMOUS_NAMES:
        _event(journal, "RELEASE_DENIED", {"sample_id": sample_id, "code": "AUTONOMOUS_RELEASE_DENIED"})
        return {"ok": False, "code": "AUTONOMOUS_RELEASE_DENIED"}
    if record.get("released"):
        return {"ok": True, "duplicate": True, "released_by": record.get("released_by")}
    record["released"] = True
    record["released_by"] = name
    journal["released"][sample_id] = name
    _event(journal, "RELEASED", {"sample_id": sample_id, "released_by": name})
    return {"ok": True, "duplicate": False, "released_by": name}


def compact_accession(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "accession_id": record["accession_id"],
        "sample_id": record["sample_id"],
        "collected_at": record["collected_at"],
        "received_at": record["received_at"],
        "accessioned_at": record["accessioned_at"],
        "clock_seconds": record["clock_seconds"],
        "holding_limit_seconds": record["holding_limit_seconds"],
        "matrix": record["matrix"],
        "method": record["method"],
        "portal_record_id": record["portal_record_id"],
        "state_delivery_id": record["state_delivery_id"],
        "portal_hash": record["portal_hash"],
        "state_hash": record["state_hash"],
        "signed_manifest_sha256": record["signed_manifest_sha256"],
        "source_hash": record["source_hash"],
        "released": record["released"],
        "released_by": record["released_by"],
    }


def run_gate(rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    inbound = deepcopy(rows if rows is not None else build_acceptance_fixture())
    portal = ReadOnlyPortalAdapter(inbound)
    coc = ReadOnlyCocAdapter(inbound)
    state = ReadOnlyStateDeliveryAdapter(inbound)
    instrument = ReadOnlyInstrumentAdapter(inbound)
    delivery = ReadOnlyDeliveryAdapter(inbound)
    lims = SimulatedLimsAdapter()
    journal = empty_journal()

    portal_rows = portal.list_submissions()
    effects = []
    for portal_record in portal_rows:
        coc_id = _pick(portal_record, PORTAL_ALIASES["coc_id"])
        sample_id = _text(_pick(portal_record, PORTAL_ALIASES["sample_id"]))
        effects.append(
            ingest_submission(
                journal,
                lims,
                portal_record,
                coc.get(_text(coc_id)) or {},
                state.get(sample_id),
                instrument,
            )
        )

    first_accession_count = len(journal["accessions"])
    replay_effects = []
    for portal_record in portal_rows:
        coc_id = _pick(portal_record, PORTAL_ALIASES["coc_id"])
        sample_id = _text(_pick(portal_record, PORTAL_ALIASES["sample_id"]))
        replay_effects.append(
            ingest_submission(
                journal,
                lims,
                portal_record,
                coc.get(_text(coc_id)) or {},
                state.get(sample_id),
                instrument,
            )
        )

    accessions = [compact_accession(item) for item in sorted(journal["accessions"].values(), key=lambda item: item["accession_id"])]
    reconcile = []
    for record in accessions:
        portal_record = next(
            item
            for item in portal_rows
            if _text(_pick(item, PORTAL_ALIASES["portal_record_id"])) == journal["accessions"][record["sample_id"]]["portal_record_id"]
        )
        stored = journal["accessions"][record["sample_id"]]
        state_record = state.get_delivery(stored["state_delivery_id"]) or state.get(record["sample_id"]) or {}
        check = reconcile_accession(journal["accessions"][record["sample_id"]], portal_record, state_record)
        delivery_receipt = delivery.receipt(record["sample_id"]) or {}
        check["delivery_received_at"] = delivery_receipt.get("received_at")
        check["delivery_matches"] = delivery_receipt.get("received_at") == record["received_at"]
        check["ok"] = check["ok"] and check["delivery_matches"]
        reconcile.append({"sample_id": record["sample_id"], **check})

    ready_ids = [item["sample_id"] for item in accessions]
    autonomous = []
    if ready_ids:
        autonomous.append(release_accession(journal, ready_ids[0], named_approver="SYSTEM"))
        autonomous.append(release_accession(journal, ready_ids[0], named_approver="AUTO"))
        autonomous.append(release_accession(journal, ready_ids[0], named_approver=""))

    reject_codes = [item["reason"] for item in journal["rejects"]]
    reject_code_counts = {code: reject_codes.count(code) for code in REJECT_CODES}
    ww_exact = sum(1 for item in accessions if item["matrix"] == "WASTEWATER" and item["clock_seconds"] == WW_HOLDING_SECONDS)
    dw_exact = sum(1 for item in accessions if item["matrix"] == "DRINKING_WATER" and item["clock_seconds"] == DW_HOLDING_SECONDS)
    ww_over = sum(1 for item in journal["rejects"] if item["reason"] == "HOLDING_TIME" and item["matrix"] == "WASTEWATER")
    dw_over = sum(1 for item in journal["rejects"] if item["reason"] == "HOLDING_TIME" and item["matrix"] == "DRINKING_WATER")

    signed_rollup = sha256_hex([item["signed_manifest_sha256"] for item in accessions])
    body = {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "truth_gate": TRUTH_GATE,
        "input_rows": len(inbound),
        "accessioned": len(accessions),
        "rejected": len(journal["rejects"]),
        "reject_codes": sorted(reject_codes),
        "reject_code_counts": reject_code_counts,
        "ww_accessioned": sum(1 for item in accessions if item["matrix"] == "WASTEWATER"),
        "dw_accessioned": sum(1 for item in accessions if item["matrix"] == "DRINKING_WATER"),
        "ww_exact_6h": ww_exact,
        "dw_exact_24h": dw_exact,
        "ww_holding_over": ww_over,
        "dw_holding_over": dw_over,
        "duplicates": len(accessions) - len({item["accession_id"] for item in accessions}),
        "accession_ids": [item["accession_id"] for item in accessions],
        "sample_ids": ready_ids,
        "replay_added_accessions": len(journal["accessions"]) - first_accession_count,
        "replay_noops": sum(1 for item in replay_effects if item.get("kind") == "REPLAY_NOOP"),
        "reconcile_ok": sum(1 for item in reconcile if item["ok"]),
        "reconcile_fail": sum(1 for item in reconcile if not item["ok"]),
        "released": len(journal["released"]),
        "autonomous_release_effects": autonomous,
        "effects": [{"kind": item.get("kind"), "sample_id": item.get("sample_id"), "reason": item.get("reason")} for item in effects],
        "accessions": accessions,
        "reject_records": deepcopy(journal["rejects"]),
        "reconcile": reconcile,
        "catalog_sha256": CATALOG_SHA256,
        "fixture_sha256": fixture_sha256(inbound),
        "signed_manifest_rollup": signed_rollup,
        "interface_live": False,
        "interfaces": "SIMULATED",
        "shadowing": "READ_ONLY",
        "source_writes": portal.writes + coc.writes + state.writes + instrument.writes + delivery.writes,
        "production_writes": lims.production_writes,
        "autonomous_release": False,
        "pre_sale_transport": "NONE",
        "cash_usd": 0,
        "official_binary": OFFICIAL_BINARY,
        "official_test": OFFICIAL_TEST,
    }
    body["manifest_sha256"] = sha256_hex({key: value for key, value in body.items() if key != "manifest_sha256"})
    return body


def pass_contract(result: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if result.get("input_rows") != INPUT_COUNT:
        failures.append("input_rows!=600")
    if result.get("accessioned") != VALID_COUNT:
        failures.append("accessioned!=450")
    if result.get("rejected") != REJECT_COUNT:
        failures.append("rejected!=150")
    counts = result.get("reject_code_counts") or {}
    if counts.get("TEMPERATURE") != TEMPERATURE_COUNT:
        failures.append("reject_temperature")
    if counts.get("CONTAINER") != CONTAINER_COUNT:
        failures.append("reject_container")
    if counts.get("PRESERVATION") != PRESERVATION_COUNT:
        failures.append("reject_preservation")
    if counts.get("SIGNATURE") != SIGNATURE_COUNT:
        failures.append("reject_signature")
    if counts.get("DUPLICATE_ID") != DUPLICATE_COUNT:
        failures.append("reject_duplicate_id")
    if counts.get("HOLDING_TIME") != HOLDING_TIME_COUNT:
        failures.append("reject_holding_time")
    if result.get("ww_accessioned") != WW_VALID_COUNT:
        failures.append("ww_accessioned")
    if result.get("dw_accessioned") != DW_VALID_COUNT:
        failures.append("dw_accessioned")
    if result.get("ww_exact_6h") != WW_EXACT_BOUNDARY:
        failures.append("ww_exact_6h")
    if result.get("dw_exact_24h") != DW_EXACT_BOUNDARY:
        failures.append("dw_exact_24h")
    if result.get("ww_holding_over") != WW_HOLDING_OVER:
        failures.append("ww_holding_over")
    if result.get("dw_holding_over") != DW_HOLDING_OVER:
        failures.append("dw_holding_over")
    if result.get("duplicates") != 0:
        failures.append("duplicates")
    if len(set(result.get("accession_ids") or [])) != VALID_COUNT:
        failures.append("accession_ids_not_unique")
    if len(set(result.get("sample_ids") or [])) != VALID_COUNT:
        failures.append("sample_ids_not_unique")
    if result.get("replay_added_accessions") != 0:
        failures.append("replay_added_accessions")
    if result.get("replay_noops") != INPUT_COUNT:
        failures.append("replay_noops")
    if result.get("reconcile_ok") != VALID_COUNT:
        failures.append("reconcile_ok")
    if result.get("reconcile_fail") != 0:
        failures.append("reconcile_fail")
    if result.get("released") != 0:
        failures.append("released")
    if result.get("interface_live") is not False:
        failures.append("interface_live")
    if result.get("interfaces") != "SIMULATED":
        failures.append("interfaces")
    if result.get("shadowing") != "READ_ONLY":
        failures.append("shadowing")
    if result.get("source_writes") != 0:
        failures.append("source_writes")
    if result.get("production_writes") != 0:
        failures.append("production_writes")
    if result.get("autonomous_release") is not False:
        failures.append("autonomous_release")
    autos = result.get("autonomous_release_effects") or []
    if not autos:
        failures.append("autonomous_release_effects_missing")
    elif not all(
        item.get("ok") is False and item.get("code") in {"AUTONOMOUS_RELEASE_DENIED", "MISSING_NAMED_APPROVAL"}
        for item in autos
    ):
        failures.append("autonomous_release_not_denied")
    for item in result.get("accessions") or []:
        if item.get("collected_at") != item.get("accessioned_at") and item.get("received_at") != item.get("accessioned_at"):
            failures.append("accession_timestamp_mismatch")
            break
        if item.get("clock_seconds") > item.get("holding_limit_seconds"):
            failures.append("accessioned_over_holding_time")
            break
        if item.get("released"):
            failures.append("autonomous_released_record")
            break
    if result.get("fixture_sha256") != GOLDEN_FIXTURE_SHA256 and GOLDEN_FIXTURE_SHA256 != "pending":
        failures.append("fixture_sha256")
    if result.get("catalog_sha256") != GOLDEN_CATALOG_SHA256 and GOLDEN_CATALOG_SHA256 != "pending":
        failures.append("catalog_sha256")
    if result.get("manifest_sha256") != GOLDEN_MANIFEST_SHA256 and GOLDEN_MANIFEST_SHA256 != "pending":
        failures.append("manifest_sha256")
    if result.get("signed_manifest_rollup") != GOLDEN_SIGNED_MANIFEST_ROLLUP and GOLDEN_SIGNED_MANIFEST_ROLLUP != "pending":
        failures.append("signed_manifest_rollup")
    return failures


def expected_actual(result: dict[str, Any]) -> dict[str, Any]:
    actual = {
        "input_rows": result.get("input_rows"),
        "accessioned": result.get("accessioned"),
        "rejected": result.get("rejected"),
        "reject_temperature": (result.get("reject_code_counts") or {}).get("TEMPERATURE"),
        "reject_container": (result.get("reject_code_counts") or {}).get("CONTAINER"),
        "reject_preservation": (result.get("reject_code_counts") or {}).get("PRESERVATION"),
        "reject_signature": (result.get("reject_code_counts") or {}).get("SIGNATURE"),
        "reject_duplicate_id": (result.get("reject_code_counts") or {}).get("DUPLICATE_ID"),
        "reject_holding_time": (result.get("reject_code_counts") or {}).get("HOLDING_TIME"),
        "ww_accessioned": result.get("ww_accessioned"),
        "dw_accessioned": result.get("dw_accessioned"),
        "ww_exact_6h": result.get("ww_exact_6h"),
        "dw_exact_24h": result.get("dw_exact_24h"),
        "duplicates": result.get("duplicates"),
        "replay_added_accessions": result.get("replay_added_accessions"),
        "reconcile_ok": result.get("reconcile_ok"),
        "reconcile_fail": result.get("reconcile_fail"),
        "released": result.get("released"),
        "production_writes": result.get("production_writes"),
    }
    return {"expected": EXPECTED_COUNTS, "actual": actual, "match": actual == EXPECTED_COUNTS}


def cli_payload(result: dict[str, Any]) -> dict[str, Any]:
    failures = pass_contract(result)
    counts = expected_actual(result)
    return {
        "ok": not failures,
        "failures": failures,
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "truth_gate": TRUTH_GATE,
        "counts": counts,
        "reject_code_counts": result.get("reject_code_counts"),
        "ww_exact_6h": result.get("ww_exact_6h"),
        "dw_exact_24h": result.get("dw_exact_24h"),
        "ww_holding_over": result.get("ww_holding_over"),
        "dw_holding_over": result.get("dw_holding_over"),
        "duplicates": result.get("duplicates"),
        "replay_added_accessions": result.get("replay_added_accessions"),
        "replay_noops": result.get("replay_noops"),
        "reconcile_ok": result.get("reconcile_ok"),
        "reconcile_fail": result.get("reconcile_fail"),
        "released": result.get("released"),
        "manifest_sha256": result.get("manifest_sha256"),
        "fixture_sha256": result.get("fixture_sha256"),
        "catalog_sha256": result.get("catalog_sha256"),
        "signed_manifest_rollup": result.get("signed_manifest_rollup"),
        "interfaces": result.get("interfaces"),
        "shadowing": result.get("shadowing"),
        "cash_usd": 0,
        "pre_sale_transport": "NONE",
        "official_binary": OFFICIAL_BINARY,
        "official_test": OFFICIAL_TEST,
    }


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if "--print-goldens" in args:
        first = run_gate()
        sys.stdout.write(
            _canonical(
                {
                    "fixture_sha256": first["fixture_sha256"],
                    "catalog_sha256": first["catalog_sha256"],
                    "manifest_sha256": first["manifest_sha256"],
                    "signed_manifest_rollup": first["signed_manifest_rollup"],
                    "counts": expected_actual(first),
                    "reject_code_counts": first["reject_code_counts"],
                    "ww_exact_6h": first["ww_exact_6h"],
                    "dw_exact_24h": first["dw_exact_24h"],
                    "failures": pass_contract(first),
                }
            )
            + "\n"
        )
        return 0
    first = run_gate()
    second = run_gate()
    failures = pass_contract(first)
    if sha256_hex(cli_payload(first)) != sha256_hex(cli_payload(second)):
        failures.append("replay_mismatch")
    if first.get("manifest_sha256") != second.get("manifest_sha256"):
        failures.append("manifest_sha256_mismatch")
    report = cli_payload(first)
    report["failures"] = failures
    report["ok"] = not failures
    sys.stdout.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
