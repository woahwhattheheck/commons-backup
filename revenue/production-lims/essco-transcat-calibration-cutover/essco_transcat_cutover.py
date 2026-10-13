"""Synthetic, read-only Essco/Transcat calibration cutover reconciliation.

This module intentionally has no production adapter and no automatic release path.
Existing Essco/Transcat systems remain authoritative; this is a deterministic shadow
replay over frozen synthetic histories only.
"""
from __future__ import annotations

import copy
import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

DEMAND_ID = "essco-transcat-calibration-cutover-lims-01"
MANIFEST_PREFIX = "ESSCO-TRANSCAT-SYNTHETIC-MANIFEST-V1\n"
HOLD_CODES = (
    "DUPLICATE_ASSET_ID",
    "CUSTOMER_SITE_MISMATCH",
    "OUT_OF_SCOPE_PROCEDURE",
    "MISSING_AS_FOUND",
    "CERTIFICATE_VERSION_CONFLICT",
    "COURIER_CUSTODY_BREAK",
    "LEGACY_NEW_SYSTEM_MISMATCH",
)
END_TO_END_PATH = (
    "instrument",
    "customer_site",
    "service_order",
    "pickup_receipt",
    "scope_procedure",
    "met_cal_run",
    "as_found_as_left",
    "certificate",
    "essconet_document",
    "transcat_receipt",
)

PROCEDURE_SPECS = (
    ("PROC-TEMP", "R3", "degC"),
    ("PROC-PRESS", "R5", "kPa"),
    ("PROC-ELEC", "R2", "V"),
)


class IntegrityError(ValueError):
    """Frozen fixture or manifest content did not match its integrity contract."""


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _record_hash(record: dict[str, Any]) -> str:
    return _sha256_text(_canonical(record))


def _manifest_envelope(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "demand_id": manifest["demand_id"],
        "fixture_version": manifest["fixture_version"],
        "dataset_sha256": manifest["dataset_sha256"],
        "expanded_records_sha256": manifest["expanded_records_sha256"],
        "record_count": manifest["record_count"],
        "expected_clean": manifest["expected_clean"],
        "expected_hold": manifest["expected_hold"],
        "expected_hold_codes": manifest["expected_hold_codes"],
        "allowed_procedures": manifest["allowed_procedures"],
    }


def verify_manifest_signature(manifest: dict[str, Any]) -> None:
    if manifest.get("signature_alg") != "sha256-content-envelope-v1":
        raise IntegrityError("unsupported manifest signature algorithm")
    expected = _sha256_text(MANIFEST_PREFIX + _canonical(_manifest_envelope(manifest)))
    if manifest.get("signature") != expected:
        raise IntegrityError("manifest content-envelope signature mismatch")


def verify_records(records: list[dict[str, Any]], manifest: dict[str, Any]) -> None:
    verify_manifest_signature(manifest)
    if manifest.get("demand_id") != DEMAND_ID:
        raise IntegrityError("manifest demand id mismatch")
    if len(records) != manifest.get("record_count"):
        raise IntegrityError("record count mismatch")

    ids = [record["history_id"] for record in records]
    if len(set(ids)) != len(ids):
        raise IntegrityError("duplicate history_id")
    expanded_digest = _sha256_text(_canonical(records))
    if expanded_digest != manifest.get("expanded_records_sha256"):
        raise IntegrityError("expanded record-set hash mismatch")

    expected_holds = Counter(manifest["expected_hold_codes"])
    actual_truth = Counter(
        record["truth_hold"] for record in records if record.get("truth_hold") is not None
    )
    if actual_truth != expected_holds:
        raise IntegrityError("truth-set hold distribution mismatch")
    if len(records) - sum(actual_truth.values()) != manifest["expected_clean"]:
        raise IntegrityError("truth-set clean count mismatch")


def _expand_fixture_row(row: list[Any]) -> dict[str, Any]:
    if len(row) != 7:
        raise IntegrityError("fixture row width mismatch")
    n, customer_n, site_n, procedure_index, value, truth_hold, duplicate_of = row
    if not isinstance(n, int) or not 1 <= n <= 500:
        raise IntegrityError("fixture row number out of range")
    try:
        procedure_id, procedure_revision, unit = PROCEDURE_SPECS[procedure_index]
    except (IndexError, TypeError):
        raise IntegrityError("fixture procedure index out of range") from None

    if truth_hold == "OUT_OF_SCOPE_PROCEDURE":
        procedure_id, procedure_revision = "PROC-UNAPPROVED", "R0"

    asset_n = duplicate_of if duplicate_of is not None else n
    asset_id = f"ASSET{asset_n:04d}"
    customer_id = f"CUST{customer_n:03d}"
    site_customer_id = customer_id
    if truth_hold == "CUSTOMER_SITE_MISMATCH":
        site_customer_id = f"CUST{(customer_n % 20) + 1:03d}"

    as_found = None if truth_hold == "MISSING_AS_FOUND" else value
    certificate_version = 1
    essconet_version = 2 if truth_hold == "CERTIFICATE_VERSION_CONFLICT" else 1
    certificate_payload = {
        "certificate_id": f"CERT{n:04d}",
        "version": certificate_version,
        "asset_id": asset_id,
        "procedure_id": procedure_id,
        "procedure_revision": procedure_revision,
        "as_found": as_found,
        "as_left": value,
        "unit": unit,
        "uncertainty": 0.05,
    }
    custody_chain = (
        ["PICKUP"]
        if truth_hold == "COURIER_CUSTODY_BREAK"
        else ["PICKUP", "RECEIVE"]
    )
    new_asset_id = (
        asset_id + "-NEW"
        if truth_hold == "LEGACY_NEW_SYSTEM_MISMATCH"
        else asset_id
    )

    return {
        "history_id": f"H{n:04d}",
        "asset_id": asset_id,
        "customer_id": customer_id,
        "site_id": f"SITE{site_n:02d}",
        "site_customer_id": site_customer_id,
        "service_order": f"SO{n:05d}",
        "pickup_receipt": f"PU{n:05d}",
        "receipt_receipt": f"RC{n:05d}",
        "procedure_id": procedure_id,
        "procedure_revision": procedure_revision,
        "met_cal_run": f"MC{n:05d}",
        "as_found": as_found,
        "as_left": value,
        "unit": unit,
        "uncertainty": 0.05,
        "certificate_id": f"CERT{n:04d}",
        "certificate_version": certificate_version,
        "essconet_version": essconet_version,
        "certificate_hash": _sha256_text(_canonical(certificate_payload)),
        "essconet_document": f"EDOC{n:05d}",
        "transcat_receipt": f"TR{n:05d}",
        "custody_chain": custody_chain,
        "legacy_asset_id": asset_id,
        "new_asset_id": new_asset_id,
        "truth_hold": truth_hold,
    }


def _rows_from_generator(compact: dict[str, Any]) -> list[list[Any]]:
    if compact.get("schema") != "deterministic-generator-v1":
        raise IntegrityError("fixture schema mismatch")
    generator = compact.get("generator")
    if not isinstance(generator, dict):
        raise IntegrityError("fixture generator missing")
    record_count = generator.get("record_count")
    clean_count = generator.get("clean_count")
    customers = generator.get("customers")
    sites = generator.get("sites")
    base_value = generator.get("base_value")
    value_step = generator.get("value_step")
    if (record_count, clean_count, customers, sites) != (500, 400, 20, 3):
        raise IntegrityError("fixture generator dimensions mismatch")
    if base_value != 10.0 or value_step != 0.125:
        raise IntegrityError("fixture generator numeric contract mismatch")

    holds: dict[int, tuple[str, int | None]] = {}
    for segment in generator.get("hold_segments", []):
        code = segment.get("code")
        start = segment.get("start")
        count = segment.get("count")
        if code not in HOLD_CODES or not isinstance(start, int) or not isinstance(count, int):
            raise IntegrityError("invalid HOLD segment")
        for offset in range(count):
            n = start + offset
            if n in holds or not 1 <= n <= record_count:
                raise IntegrityError("overlapping or out-of-range HOLD segment")
            duplicate_of = None
            if code == "DUPLICATE_ASSET_ID":
                duplicate_start = segment.get("duplicate_start")
                if not isinstance(duplicate_start, int):
                    raise IntegrityError("duplicate segment missing duplicate_start")
                duplicate_of = duplicate_start + offset
            holds[n] = (code, duplicate_of)

    if set(holds) != set(range(clean_count + 1, record_count + 1)):
        raise IntegrityError("HOLD segments must cover exactly the final 100 histories")

    rows: list[list[Any]] = []
    for n in range(1, record_count + 1):
        truth_hold, duplicate_of = holds.get(n, (None, None))
        identity_n = duplicate_of if duplicate_of is not None else n
        customer_n = ((identity_n - 1) % customers) + 1
        site_n = ((identity_n - 1) % sites) + 1
        procedure_index = (identity_n - 1) % len(PROCEDURE_SPECS)
        value = base_value + n * value_step
        rows.append(
            [n, customer_n, site_n, procedure_index, value, truth_hold, duplicate_of]
        )
    return rows


def load_fixture(
    fixture_path: str | Path | None = None,
    manifest_path: str | Path | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    base = Path(__file__).resolve().parent / "fixtures"
    fixture_path = Path(fixture_path) if fixture_path else base / "essco_transcat_500_histories.json"
    manifest_path = Path(manifest_path) if manifest_path else base / "manifest.json"

    fixture_text = fixture_path.read_text(encoding="utf-8")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if _sha256_text(fixture_text) != manifest.get("dataset_sha256"):
        raise IntegrityError("dataset file hash mismatch")

    compact = json.loads(fixture_text)
    if compact.get("fixture_version") != manifest.get("fixture_version"):
        raise IntegrityError("fixture version mismatch")
    records = [_expand_fixture_row(row) for row in _rows_from_generator(compact)]
    verify_records(records, manifest)
    return records, manifest

def _certificate_hash(record: dict[str, Any]) -> str:
    payload = {
        "certificate_id": record["certificate_id"],
        "version": record["certificate_version"],
        "asset_id": record["asset_id"],
        "procedure_id": record["procedure_id"],
        "procedure_revision": record["procedure_revision"],
        "as_found": record["as_found"],
        "as_left": record["as_left"],
        "unit": record["unit"],
        "uncertainty": record["uncertainty"],
    }
    return _sha256_text(_canonical(payload))


def assert_customer_isolation(records: Iterable[dict[str, Any]]) -> None:
    asset_owner: dict[str, str] = {}
    certificate_owner: dict[str, str] = {}
    for record in records:
        customer = record["customer_id"]
        for key, index in (
            ("asset_id", asset_owner),
            ("certificate_id", certificate_owner),
        ):
            identifier = record[key]
            prior = index.setdefault(identifier, customer)
            if prior != customer:
                raise IntegrityError(
                    f"cross-customer {key}: {identifier} belongs to both {prior} and {customer}"
                )


def _classify(
    record: dict[str, Any],
    seen_assets: set[str],
    allowed_procedures: dict[str, str],
) -> str | None:
    if record["asset_id"] in seen_assets:
        return "DUPLICATE_ASSET_ID"
    if record["site_customer_id"] != record["customer_id"]:
        return "CUSTOMER_SITE_MISMATCH"
    expected_revision = allowed_procedures.get(record["procedure_id"])
    if expected_revision is None or expected_revision != record["procedure_revision"]:
        return "OUT_OF_SCOPE_PROCEDURE"
    if record["as_found"] is None:
        return "MISSING_AS_FOUND"
    if (
        record["certificate_version"] != record["essconet_version"]
        or record["certificate_hash"] != _certificate_hash(record)
    ):
        return "CERTIFICATE_VERSION_CONFLICT"
    if record["custody_chain"] != ["PICKUP", "RECEIVE"]:
        return "COURIER_CUSTODY_BREAK"
    if not (
        record["asset_id"] == record["legacy_asset_id"] == record["new_asset_id"]
    ):
        return "LEGACY_NEW_SYSTEM_MISMATCH"
    return None


def _mapping(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "instrument": {"asset_id": record["asset_id"]},
        "customer_site": {
            "customer_id": record["customer_id"],
            "site_id": record["site_id"],
        },
        "service_order": {"id": record["service_order"]},
        "pickup_receipt": {
            "pickup": record["pickup_receipt"],
            "receipt": record["receipt_receipt"],
            "custody_chain": record["custody_chain"],
        },
        "scope_procedure": {
            "procedure_id": record["procedure_id"],
            "revision": record["procedure_revision"],
        },
        "met_cal_run": {"id": record["met_cal_run"]},
        "as_found_as_left": {
            "as_found": record["as_found"],
            "as_left": record["as_left"],
            "unit": record["unit"],
            "uncertainty": record["uncertainty"],
        },
        "certificate": {
            "id": record["certificate_id"],
            "version": record["certificate_version"],
            "sha256": record["certificate_hash"],
        },
        "essconet_document": {
            "id": record["essconet_document"],
            "version": record["essconet_version"],
        },
        "transcat_receipt": {"id": record["transcat_receipt"]},
    }


@dataclass
class ReplayReport:
    clean: int
    hold: int
    hold_counts: dict[str, int]
    auto_released: int
    human_qa_required: int
    outcome_digest: str
    outcomes: list[dict[str, Any]]


class CalibrationCutoverShadow:
    """Deterministic read-only shadow state; never mutates authoritative state."""

    def __init__(self, authoritative_state: dict[str, Any] | None = None) -> None:
        self.authoritative_state = copy.deepcopy(authoritative_state or {})
        self._authoritative_fingerprint = _sha256_text(_canonical(self.authoritative_state))
        self.shadow_state: dict[str, dict[str, Any]] = {}

    @property
    def authoritative_fingerprint(self) -> str:
        current = _sha256_text(_canonical(self.authoritative_state))
        if current != self._authoritative_fingerprint:
            raise IntegrityError("authoritative state changed inside read-only shadow")
        return current

    def snapshot(self) -> str:
        return _canonical(self.shadow_state)

    def rollback(self, snapshot: str) -> None:
        restored = json.loads(snapshot)
        if not isinstance(restored, dict):
            raise IntegrityError("rollback snapshot must be a dictionary")
        self.shadow_state = restored

    def replay(
        self,
        records: list[dict[str, Any]],
        manifest: dict[str, Any],
    ) -> ReplayReport:
        verify_records(records, manifest)
        assert_customer_isolation(records)
        self.authoritative_fingerprint

        seen_assets: set[str] = set()
        outcomes: list[dict[str, Any]] = []
        next_shadow: dict[str, dict[str, Any]] = {}
        hold_counts: Counter[str] = Counter()

        for record in records:
            hold_code = _classify(record, seen_assets, manifest["allowed_procedures"])
            seen_assets.add(record["asset_id"])
            truth = record["truth_hold"]
            if hold_code != truth:
                raise IntegrityError(
                    f"classifier/truth mismatch for {record['history_id']}: "
                    f"{hold_code!r} != {truth!r}"
                )

            if hold_code is None:
                mapped = _mapping(record)
                if tuple(mapped) != END_TO_END_PATH:
                    raise IntegrityError("end-to-end mapping path drift")
                outcome = {
                    "history_id": record["history_id"],
                    "status": "CLEAN",
                    "hold_code": None,
                    "mapping_count": 1,
                    "release_state": "QA_REQUIRED",
                    "record_sha256": _record_hash(record),
                    "mapped": mapped,
                }
            else:
                hold_counts[hold_code] += 1
                outcome = {
                    "history_id": record["history_id"],
                    "status": "HOLD",
                    "hold_code": hold_code,
                    "mapping_count": 0,
                    "release_state": "HOLD",
                    "record_sha256": _record_hash(record),
                    "mapped": None,
                }
            outcomes.append(outcome)
            next_shadow[record["history_id"]] = outcome

        clean = sum(item["status"] == "CLEAN" for item in outcomes)
        hold = len(outcomes) - clean
        expected_counts = Counter(manifest["expected_hold_codes"])
        if clean != manifest["expected_clean"] or hold != manifest["expected_hold"]:
            raise IntegrityError("replay count mismatch")
        if hold_counts != expected_counts:
            raise IntegrityError("replay HOLD-code distribution mismatch")

        self.shadow_state = next_shadow
        digest = _sha256_text(_canonical(outcomes))
        self.authoritative_fingerprint
        return ReplayReport(
            clean=clean,
            hold=hold,
            hold_counts=dict(sorted(hold_counts.items())),
            auto_released=0,
            human_qa_required=clean,
            outcome_digest=digest,
            outcomes=outcomes,
        )

    def automatic_release(self, *_: Any, **__: Any) -> None:
        raise PermissionError(
            "automatic release is disabled; this synthetic cutover is human-QA-only"
        )
