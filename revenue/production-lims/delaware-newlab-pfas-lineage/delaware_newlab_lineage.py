"""Synthetic, read-only Delaware new-lab PFAS/microbiology lineage LIMS.

This module is a deterministic shadow over frozen synthetic requests. It has no
production adapter, no regulatory/public-health decision path, and no automatic
report release.
"""
from __future__ import annotations

import copy
import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEMAND_ID = "delaware-newlab-pfas-lineage-lims-01"
MANIFEST_PREFIX = "DELAWARE-NEWLAB-SYNTHETIC-MANIFEST-V1\n"
HOLD_CODES = (
    "MISSING_MATRIX_SDS_CUSTODY",
    "DUPLICATE_CONTAINER",
    "METHOD_MATRIX_MISMATCH",
    "CALIBRATION_QC_FAIL",
    "LEGACY_NEW_FACILITY_ID_COLLISION",
)
METHOD_SPECS = (
    ("PFAS", "WATER", "EPA-1633", "R1", "ng/L"),
    ("MICROBIOLOGY", "WATER", "SM-9223B", "R2", "MPN/100mL"),
    ("MOLECULAR", "WATER", "PCR-ENTERO", "R1", "copies/mL"),
)
RESERVED_RELEASE_ACTORS = {
    "agent",
    "automation",
    "system",
    "bot",
    "autonomous",
    "auto",
}


class IntegrityError(ValueError):
    """Frozen fixture or manifest content violated the integrity contract."""


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
        "expected_ready": manifest["expected_ready"],
        "expected_hold": manifest["expected_hold"],
        "expected_hold_codes": manifest["expected_hold_codes"],
        "allowed_methods": manifest["allowed_methods"],
    }


def verify_manifest_signature(manifest: dict[str, Any]) -> None:
    if manifest.get("signature_alg") != "sha256-content-envelope-v1":
        raise IntegrityError("unsupported manifest signature algorithm")
    expected = _sha256_text(MANIFEST_PREFIX + _canonical(_manifest_envelope(manifest)))
    if manifest.get("signature") != expected:
        raise IntegrityError("manifest content-envelope signature mismatch")


def _lineage_hashes(
    *,
    request_id: str,
    quote_id: str,
    container_id: str,
    matrix: str,
    sds_hash: str,
    custody_chain: list[str],
    route: str,
    method_id: str,
    method_version: str,
    value: float,
    unit: str,
    qualifier: str,
) -> dict[str, str]:
    source = {
        "request_id": request_id,
        "quote_id": quote_id,
        "container_id": container_id,
        "matrix": matrix,
        "sds_hash": sds_hash,
        "custody_chain": custody_chain,
    }
    method = {
        "route": route,
        "matrix": matrix,
        "method_id": method_id,
        "method_version": method_version,
    }
    result = {"value": value, "unit": unit, "qualifier": qualifier}
    return {
        "source_sha256": _sha256_text(_canonical(source)),
        "method_sha256": _sha256_text(_canonical(method)),
        "value_unit_qualifier_sha256": _sha256_text(_canonical(result)),
    }


def _expand_fixture_row(row: list[Any]) -> dict[str, Any]:
    if len(row) != 4:
        raise IntegrityError("fixture row width mismatch")
    n, spec_index, truth_hold, duplicate_of = row
    if not isinstance(n, int) or not 1 <= n <= 200:
        raise IntegrityError("fixture row number out of range")
    try:
        route, matrix, method_id, method_version, unit = METHOD_SPECS[spec_index]
    except (IndexError, TypeError):
        raise IntegrityError("fixture method index out of range") from None

    request_id = f"DNREC-REQ-{n:04d}"
    quote_id = f"DNREC-Q-{n:04d}"
    container_n = duplicate_of if duplicate_of is not None else n
    container_id = f"DNREC-C-{container_n:04d}"
    custody_chain = ["COURIER_PICKUP", "NEW_LAB_RECEIVE"]
    sds_hash = _sha256_text(f"SDS:{n:04d}:{matrix}")
    calibration_ok = True
    qc_ok = True

    if truth_hold == "MISSING_MATRIX_SDS_CUSTODY":
        offset = (n - 151) % 3
        if offset == 0:
            matrix = ""
        elif offset == 1:
            sds_hash = ""
        else:
            custody_chain = ["COURIER_PICKUP"]
    elif truth_hold == "METHOD_MATRIX_MISMATCH":
        method_id = "SM-9223B" if route == "PFAS" else "EPA-1633"
        method_version = "R2" if method_id == "SM-9223B" else "R1"
    elif truth_hold == "CALIBRATION_QC_FAIL":
        calibration_ok = (n % 2 == 0)
        qc_ok = not calibration_ok

    value = round(0.5 + n * 0.125, 6)
    qualifier = "U" if n % 7 == 0 else ("J" if n % 5 == 0 else "NONE")
    legacy_id = f"OLD-{n:04d}"
    new_id = f"NEW-{n:04d}"
    if truth_hold == "LEGACY_NEW_FACILITY_ID_COLLISION":
        legacy_id = new_id

    hashes = _lineage_hashes(
        request_id=request_id,
        quote_id=quote_id,
        container_id=container_id,
        matrix=matrix,
        sds_hash=sds_hash,
        custody_chain=custody_chain,
        route=route,
        method_id=method_id,
        method_version=method_version,
        value=value,
        unit=unit,
        qualifier=qualifier,
    )
    return {
        "request_id": request_id,
        "quote_id": quote_id,
        "container_id": container_id,
        "facility_origin": "OLD_FACILITY" if n % 4 == 0 else "NEW_FACILITY",
        "legacy_id": legacy_id,
        "new_id": new_id,
        "matrix": matrix,
        "sds_hash": sds_hash,
        "custody_chain": custody_chain,
        "route": route,
        "method_id": method_id,
        "method_version": method_version,
        "calibration_ok": calibration_ok,
        "qc_ok": qc_ok,
        "value": value,
        "unit": unit,
        "qualifier": qualifier,
        **hashes,
        "truth_hold": truth_hold,
    }


def _rows_from_generator(compact: dict[str, Any]) -> list[list[Any]]:
    if compact.get("schema") != "deterministic-generator-v1":
        raise IntegrityError("fixture schema mismatch")
    generator = compact.get("generator")
    if not isinstance(generator, dict):
        raise IntegrityError("fixture generator missing")
    if (generator.get("record_count"), generator.get("clean_count")) != (200, 150):
        raise IntegrityError("fixture generator dimensions mismatch")

    holds: dict[int, tuple[str, int | None]] = {}
    for segment in generator.get("hold_segments", []):
        code = segment.get("code")
        start = segment.get("start")
        count = segment.get("count")
        if code not in HOLD_CODES or not isinstance(start, int) or not isinstance(count, int):
            raise IntegrityError("invalid HOLD segment")
        for offset in range(count):
            n = start + offset
            if n in holds or not 1 <= n <= 200:
                raise IntegrityError("overlapping or out-of-range HOLD segment")
            duplicate_of = None
            if code == "DUPLICATE_CONTAINER":
                duplicate_start = segment.get("duplicate_start")
                if not isinstance(duplicate_start, int):
                    raise IntegrityError("duplicate segment missing duplicate_start")
                duplicate_of = duplicate_start + offset
            holds[n] = (code, duplicate_of)

    if set(holds) != set(range(151, 201)):
        raise IntegrityError("HOLD segments must cover exactly records 151..200")

    rows: list[list[Any]] = []
    for n in range(1, 201):
        truth_hold, duplicate_of = holds.get(n, (None, None))
        identity_n = duplicate_of if duplicate_of is not None else n
        spec_index = (identity_n - 1) % len(METHOD_SPECS)
        rows.append([n, spec_index, truth_hold, duplicate_of])
    return rows


def verify_records(records: list[dict[str, Any]], manifest: dict[str, Any]) -> None:
    verify_manifest_signature(manifest)
    if manifest.get("demand_id") != DEMAND_ID:
        raise IntegrityError("manifest demand id mismatch")
    if len(records) != manifest.get("record_count"):
        raise IntegrityError("record count mismatch")
    request_ids = [record["request_id"] for record in records]
    if len(request_ids) != len(set(request_ids)):
        raise IntegrityError("duplicate request_id")
    if _sha256_text(_canonical(records)) != manifest.get("expanded_records_sha256"):
        raise IntegrityError("expanded record-set hash mismatch")
    actual_truth = Counter(
        record["truth_hold"] for record in records if record["truth_hold"] is not None
    )
    if actual_truth != Counter(manifest["expected_hold_codes"]):
        raise IntegrityError("truth-set hold distribution mismatch")
    if len(records) - sum(actual_truth.values()) != manifest["expected_ready"]:
        raise IntegrityError("truth-set ready count mismatch")

    for record in records:
        hashes = _lineage_hashes(
            request_id=record["request_id"],
            quote_id=record["quote_id"],
            container_id=record["container_id"],
            matrix=record["matrix"],
            sds_hash=record["sds_hash"],
            custody_chain=record["custody_chain"],
            route=record["route"],
            method_id=record["method_id"],
            method_version=record["method_version"],
            value=record["value"],
            unit=record["unit"],
            qualifier=record["qualifier"],
        )
        for key, expected in hashes.items():
            if record.get(key) != expected:
                raise IntegrityError(f"lineage hash mismatch: {record['request_id']} {key}")


def load_fixture(
    fixture_path: str | Path | None = None,
    manifest_path: str | Path | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    base = Path(__file__).resolve().parent / "fixtures"
    fixture_path = Path(fixture_path) if fixture_path else base / "delaware_200_requests.json"
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


def _classify(
    record: dict[str, Any],
    seen_containers: set[str],
    allowed_methods: dict[str, dict[str, str]],
) -> str | None:
    if not record["matrix"] or not record["sds_hash"] or record["custody_chain"] != [
        "COURIER_PICKUP",
        "NEW_LAB_RECEIVE",
    ]:
        return "MISSING_MATRIX_SDS_CUSTODY"
    if record["container_id"] in seen_containers:
        return "DUPLICATE_CONTAINER"
    route_contract = allowed_methods.get(record["route"])
    if (
        route_contract is None
        or record["matrix"] != route_contract["matrix"]
        or record["method_id"] != route_contract["method_id"]
        or record["method_version"] != route_contract["method_version"]
    ):
        return "METHOD_MATRIX_MISMATCH"
    if not record["calibration_ok"] or not record["qc_ok"]:
        return "CALIBRATION_QC_FAIL"
    if record["legacy_id"] == record["new_id"]:
        return "LEGACY_NEW_FACILITY_ID_COLLISION"
    return None


@dataclass
class ReplayReport:
    ready: int
    hold: int
    replayed: int
    hold_counts: dict[str, int]
    accessions_added: int
    jobs_added: int
    reports_added: int
    holds_added: int
    events_added: int
    state_digest: str
    outcomes: list[dict[str, Any]]


class DelawareNewLabShadow:
    """Idempotent, synthetic shadow state; authoritative state remains untouched."""

    def __init__(self, authoritative_state: dict[str, Any] | None = None) -> None:
        self.authoritative_state = copy.deepcopy(authoritative_state or {})
        self._authoritative_fingerprint = _sha256_text(_canonical(self.authoritative_state))
        self.accessions: dict[str, dict[str, Any]] = {}
        self.jobs: dict[str, dict[str, Any]] = {}
        self.reports: dict[str, dict[str, Any]] = {}
        self.holds: dict[str, dict[str, Any]] = {}
        self.events: list[dict[str, Any]] = []
        self._seen_requests: set[str] = set()

    @property
    def authoritative_fingerprint(self) -> str:
        current = _sha256_text(_canonical(self.authoritative_state))
        if current != self._authoritative_fingerprint:
            raise IntegrityError("authoritative state changed inside read-only shadow")
        return current

    def state_digest(self) -> str:
        payload = {
            "accessions": self.accessions,
            "jobs": self.jobs,
            "reports": self.reports,
            "holds": self.holds,
            "events": self.events,
            "seen_requests": sorted(self._seen_requests),
        }
        return _sha256_text(_canonical(payload))

    def replay(
        self,
        records: list[dict[str, Any]],
        manifest: dict[str, Any],
    ) -> ReplayReport:
        verify_records(records, manifest)
        self.authoritative_fingerprint
        seen_containers: set[str] = {
            item["container_id"] for item in self.accessions.values()
        }

        ready = hold = replayed = 0
        hold_counts: Counter[str] = Counter()
        accessions_added = jobs_added = reports_added = holds_added = events_added = 0
        outcomes: list[dict[str, Any]] = []

        for record in records:
            request_id = record["request_id"]
            if request_id in self._seen_requests:
                replayed += 1
                outcomes.append(
                    {
                        "request_id": request_id,
                        "status": "IDEMPOTENT_REPLAY",
                        "hold_code": self.holds.get(request_id, {}).get("hold_code"),
                        "record_sha256": _record_hash(record),
                    }
                )
                continue

            hold_code = _classify(record, seen_containers, manifest["allowed_methods"])
            truth = record["truth_hold"]
            if hold_code != truth:
                raise IntegrityError(
                    f"classifier/truth mismatch for {request_id}: {hold_code!r} != {truth!r}"
                )

            self._seen_requests.add(request_id)
            seen_containers.add(record["container_id"])

            if hold_code is None:
                ready += 1
                accession = {
                    "request_id": request_id,
                    "accession_id": f"ACC-{request_id[-4:]}",
                    "container_id": record["container_id"],
                    "facility_origin": record["facility_origin"],
                    "legacy_id": record["legacy_id"],
                    "new_id": record["new_id"],
                    "source_sha256": record["source_sha256"],
                }
                job = {
                    "request_id": request_id,
                    "route": record["route"],
                    "method_id": record["method_id"],
                    "method_version": record["method_version"],
                    "method_sha256": record["method_sha256"],
                }
                report = {
                    "request_id": request_id,
                    "state": "STAGED_HUMAN_REVIEW",
                    "value": record["value"],
                    "unit": record["unit"],
                    "qualifier": record["qualifier"],
                    "value_unit_qualifier_sha256": record[
                        "value_unit_qualifier_sha256"
                    ],
                    "released_by": None,
                }
                self.accessions[request_id] = accession
                self.jobs[request_id] = job
                self.reports[request_id] = report
                accessions_added += 1
                jobs_added += 1
                reports_added += 1
                outcome = {
                    "request_id": request_id,
                    "status": "READY",
                    "hold_code": None,
                    "scheduled_jobs": 1,
                    "report_state": "STAGED_HUMAN_REVIEW",
                    "record_sha256": _record_hash(record),
                    "source_sha256": record["source_sha256"],
                    "method_sha256": record["method_sha256"],
                    "value_unit_qualifier_sha256": record[
                        "value_unit_qualifier_sha256"
                    ],
                }
            else:
                hold += 1
                hold_counts[hold_code] += 1
                self.holds[request_id] = {
                    "request_id": request_id,
                    "hold_code": hold_code,
                    "scheduled_jobs": 0,
                }
                holds_added += 1
                outcome = {
                    "request_id": request_id,
                    "status": "HOLD",
                    "hold_code": hold_code,
                    "scheduled_jobs": 0,
                    "report_state": None,
                    "record_sha256": _record_hash(record),
                }

            self.events.append(
                {
                    "sequence": len(self.events) + 1,
                    "request_id": request_id,
                    "status": outcome["status"],
                    "hold_code": outcome["hold_code"],
                    "record_sha256": outcome["record_sha256"],
                }
            )
            events_added += 1
            outcomes.append(outcome)

        if replayed == 0:
            if ready != manifest["expected_ready"] or hold != manifest["expected_hold"]:
                raise IntegrityError("replay count mismatch")
            if hold_counts != Counter(manifest["expected_hold_codes"]):
                raise IntegrityError("replay HOLD-code distribution mismatch")

        self.authoritative_fingerprint
        return ReplayReport(
            ready=ready,
            hold=hold,
            replayed=replayed,
            hold_counts=dict(sorted(hold_counts.items())),
            accessions_added=accessions_added,
            jobs_added=jobs_added,
            reports_added=reports_added,
            holds_added=holds_added,
            events_added=events_added,
            state_digest=self.state_digest(),
            outcomes=outcomes,
        )

    def release_report(self, request_id: str, reviewer_name: str) -> dict[str, str]:
        if not isinstance(reviewer_name, str):
            raise PermissionError("named human reviewer is required")
        reviewer = reviewer_name.strip()
        reviewer_key = "".join(ch for ch in reviewer.casefold() if ch.isalnum())
        if not reviewer or reviewer_key in RESERVED_RELEASE_ACTORS:
            raise PermissionError("named human reviewer is required")
        report = self.reports.get(request_id)
        if report is None:
            raise KeyError(request_id)
        if request_id in self.holds:
            raise PermissionError("held request cannot release a report")
        if report["state"] != "STAGED_HUMAN_REVIEW" or report["released_by"] is not None:
            raise PermissionError("report is not awaiting human review")
        report["state"] = "RELEASED_BY_NAMED_HUMAN"
        report["released_by"] = reviewer
        return {
            "request_id": request_id,
            "state": report["state"],
            "released_by": reviewer,
        }

    def automatic_release(self, *_: Any, **__: Any) -> None:
        raise PermissionError(
            "automatic release is disabled; a named human reviewer is required"
        )