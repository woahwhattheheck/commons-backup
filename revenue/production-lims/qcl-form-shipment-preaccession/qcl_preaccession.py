"""Synthetic/deidentified QCL form/email/shipment pre-accession shadow."""
from __future__ import annotations

import copy
import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEMAND_ID = "qcl-form-shipment-preaccession-lims-01"
MANIFEST_PREFIX = "QCL-PREACCESSION-SYNTHETIC-MANIFEST-V1\n"
HOLD_CODES = (
    "QUOTE_MISSING_OR_CONFLICT",
    "PO_MISSING_OR_CONFLICT",
    "METHOD_MISSING_OR_CONFLICT",
    "LOT_MISSING_OR_CONFLICT",
    "SAMPLE_QUANTITY_MISSING_OR_CONFLICT",
    "STORAGE_MISSING_OR_CONFLICT",
)
WORKFLOWS = ("PRODUCT", "RAW_MATERIAL", "STABILITY")
FORBIDDEN_PHI_KEYS = {
    "patient", "patient_name", "dob", "date_of_birth", "mrn",
    "medical_record_number", "ssn", "diagnosis",
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
    keys = (
        "demand_id", "fixture_version", "dataset_sha256", "expanded_records_sha256",
        "record_count", "expected_ready", "expected_hold", "expected_hold_codes",
        "workflows",
    )
    return {key: manifest[key] for key in keys}

def verify_manifest_signature(manifest: dict[str, Any]) -> None:
    if manifest.get("signature_alg") != "sha256-content-envelope-v1":
        raise IntegrityError("unsupported manifest signature algorithm")
    expected = _sha256_text(MANIFEST_PREFIX + _canonical(_manifest_envelope(manifest)))
    if manifest.get("signature") != expected:
        raise IntegrityError("manifest content-envelope signature mismatch")

def _source_pointer(document_type: str, n: int, field: str) -> dict[str, str]:
    if document_type == "PDF":
        coordinates = f"page:{1 + ((n + len(field)) % 4)};bbox:{10+n%20},{20+n%30},{110+n%20},{36+n%30}"
    elif document_type == "WORD":
        coordinates = f"paragraph:{1 + ((n + len(field)) % 12)};run:{1 + n % 3}"
    elif document_type == "EMAIL":
        coordinates = f"message:{n:04d};header-or-line:{1 + ((n + len(field)) % 20)}"
    else:
        coordinates = f"package-label:{n:04d};field:{field}"
    document_id = f"{document_type}-SYN-{n:04d}"
    return {
        "document_type": document_type,
        "document_id": document_id,
        "document_sha256": _sha256_text(f"{document_id}:{field}:synthetic"),
        "coordinates": coordinates,
    }

def _field(value: Any, document_type: str, n: int, field: str) -> dict[str, Any]:
    return {
        "value": value,
        "source": _source_pointer(document_type, n, field),
    }

def _normalized_hash(fields: dict[str, dict[str, Any]]) -> str:
    return _sha256_text(_canonical(fields))

def _expand_fixture_row(row: list[Any]) -> dict[str, Any]:
    if len(row) != 2:
        raise IntegrityError("fixture row width mismatch")
    n, truth_hold = row
    if not isinstance(n, int) or not 1 <= n <= 200:
        raise IntegrityError("fixture row number out of range")

    workflow = WORKFLOWS[(n - 1) % len(WORKFLOWS)]
    quote = f"Q-{n:04d}"
    po = f"PO-{n:04d}"
    method = {
        "PRODUCT": "QCL-PROD-R3",
        "RAW_MATERIAL": "QCL-RM-R2",
        "STABILITY": "QCL-STAB-R4",
    }[workflow]
    lot = f"LOT-{n:04d}"
    quantity = round(5.0 + (n % 8) * 2.5, 2)
    storage = {
        "PRODUCT": "CONTROLLED_ROOM_TEMP",
        "RAW_MATERIAL": "CONTROLLED_ROOM_TEMP",
        "STABILITY": "2-8C",
    }[workflow]

    docs = {
        "quote": "PDF",
        "po": "EMAIL",
        "method": "WORD",
        "lot": "SHIPMENT",
        "sample_quantity": "SHIPMENT",
        "storage": "WORD",
    }
    values = {
        "quote": quote,
        "po": po,
        "method": method,
        "lot": lot,
        "sample_quantity": quantity,
        "storage": storage,
    }

    field_for_code = {
        "QUOTE_MISSING_OR_CONFLICT": "quote",
        "PO_MISSING_OR_CONFLICT": "po",
        "METHOD_MISSING_OR_CONFLICT": "method",
        "LOT_MISSING_OR_CONFLICT": "lot",
        "SAMPLE_QUANTITY_MISSING_OR_CONFLICT": "sample_quantity",
        "STORAGE_MISSING_OR_CONFLICT": "storage",
    }
    if truth_hold:
        field = field_for_code[truth_hold]
        # Alternate missing vs conflict deterministically inside each hold family.
        if n % 2:
            values[field] = None
        else:
            values[field] = f"CONFLICT::{values[field]}"

    fields = {name: _field(values[name], docs[name], n, name) for name in values}
    normalized = {
        "intake_id": f"QCL-INTAKE-{n:04d}",
        "deidentified": True,
        "workflow": workflow,
        "fields": fields,
    }
    normalized["normalized_sha256"] = _normalized_hash(fields)
    normalized["truth_hold"] = truth_hold
    return normalized

def _rows_from_generator(compact: dict[str, Any]) -> list[list[Any]]:
    if compact.get("schema") != "deterministic-generator-v1":
        raise IntegrityError("fixture schema mismatch")
    generator = compact.get("generator")
    if not isinstance(generator, dict):
        raise IntegrityError("fixture generator missing")
    if (generator.get("record_count"), generator.get("clean_count")) != (200, 160):
        raise IntegrityError("fixture generator dimensions mismatch")

    holds: dict[int, str] = {}
    for segment in generator.get("hold_segments", []):
        code, start, count = segment.get("code"), segment.get("start"), segment.get("count")
        if code not in HOLD_CODES or not isinstance(start, int) or not isinstance(count, int):
            raise IntegrityError("invalid HOLD segment")
        for offset in range(count):
            n = start + offset
            if n in holds or not 1 <= n <= 200:
                raise IntegrityError("overlapping or out-of-range HOLD segment")
            holds[n] = code
    if set(holds) != set(range(161, 201)):
        raise IntegrityError("HOLD segments must cover exactly intakes 161..200")
    return [[n, holds.get(n)] for n in range(1, 201)]

def verify_records(records: list[dict[str, Any]], manifest: dict[str, Any]) -> None:
    verify_manifest_signature(manifest)
    if manifest.get("demand_id") != DEMAND_ID:
        raise IntegrityError("manifest demand mismatch")
    if len(records) != manifest.get("record_count"):
        raise IntegrityError("record count mismatch")
    ids = [record["intake_id"] for record in records]
    if len(ids) != len(set(ids)):
        raise IntegrityError("duplicate intake_id")
    if _sha256_text(_canonical(records)) != manifest.get("expanded_records_sha256"):
        raise IntegrityError("expanded record-set hash mismatch")

    truth = Counter(record["truth_hold"] for record in records if record["truth_hold"])
    if truth != Counter(manifest["expected_hold_codes"]):
        raise IntegrityError("truth-set hold distribution mismatch")
    if len(records) - sum(truth.values()) != manifest["expected_ready"]:
        raise IntegrityError("truth-set ready count mismatch")

    for record in records:
        if not record.get("deidentified"):
            raise IntegrityError("fixture must remain deidentified")
        if {key.lower() for key in record} & FORBIDDEN_PHI_KEYS:
            raise IntegrityError("PHI-shaped top-level fixture field rejected")
        if record["workflow"] not in manifest["workflows"]:
            raise IntegrityError("unknown workflow")
        fields = record["fields"]
        if set(fields) != {"quote", "po", "method", "lot", "sample_quantity", "storage"}:
            raise IntegrityError("normalized field set mismatch")
        for field_name, field in fields.items():
            source = field.get("source", {})
            if not source.get("document_sha256") or not source.get("coordinates"):
                raise IntegrityError(f"missing source provenance for {field_name}")
        if record["normalized_sha256"] != _normalized_hash(fields):
            raise IntegrityError("normalized field/source hash mismatch")

def load_fixture(
    fixture_path: str | Path | None = None,
    manifest_path: str | Path | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    base = Path(__file__).resolve().parent / "fixtures"
    fixture_path = Path(fixture_path) if fixture_path else base / "qcl_200_intakes.json"
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

def _is_conflict(value: Any) -> bool:
    return isinstance(value, str) and value.startswith("CONFLICT::")

def _classify(record: dict[str, Any]) -> str | None:
    code_for_field = (
        ("quote", "QUOTE_MISSING_OR_CONFLICT"),
        ("po", "PO_MISSING_OR_CONFLICT"),
        ("method", "METHOD_MISSING_OR_CONFLICT"),
        ("lot", "LOT_MISSING_OR_CONFLICT"),
        ("sample_quantity", "SAMPLE_QUANTITY_MISSING_OR_CONFLICT"),
        ("storage", "STORAGE_MISSING_OR_CONFLICT"),
    )
    for field_name, code in code_for_field:
        value = record["fields"][field_name]["value"]
        if value is None or _is_conflict(value):
            return code
    return None

@dataclass
class ReplayReport:
    ready: int
    hold: int
    replayed: int
    hold_counts: dict[str, int]
    accessions_added: int
    workflows_added: int
    test_jobs_added: int
    staged_reports_added: int
    holds_added: int
    events_added: int
    state_digest: str
    outcomes: list[dict[str, Any]]

class QCLPreaccessionShadow:
    """Idempotent synthetic shadow; no production adapter exists here."""

    def __init__(self, authoritative_state: dict[str, Any] | None = None) -> None:
        self.authoritative_state = copy.deepcopy(authoritative_state or {})
        self._authoritative_fingerprint = _sha256_text(_canonical(self.authoritative_state))
        self.accessions: dict[str, dict[str, Any]] = {}
        self.workflows: dict[str, dict[str, Any]] = {}
        self.test_jobs: dict[str, dict[str, Any]] = {}
        self.staged_reports: dict[str, dict[str, Any]] = {}
        self.holds: dict[str, dict[str, Any]] = {}
        self.events: list[dict[str, Any]] = []
        self._seen: set[str] = set()

    @property
    def authoritative_fingerprint(self) -> str:
        current = _sha256_text(_canonical(self.authoritative_state))
        if current != self._authoritative_fingerprint:
            raise IntegrityError("authoritative state changed inside read-only shadow")
        return current

    def state_digest(self) -> str:
        payload = {
            "accessions": self.accessions,
            "workflows": self.workflows,
            "test_jobs": self.test_jobs,
            "staged_reports": self.staged_reports,
            "holds": self.holds,
            "events": self.events,
            "seen": sorted(self._seen),
        }
        return _sha256_text(_canonical(payload))

    def replay(self, records: list[dict[str, Any]], manifest: dict[str, Any]) -> ReplayReport:
        verify_records(records, manifest)
        self.authoritative_fingerprint
        ready = hold = replayed = 0
        accessions_added = workflows_added = test_jobs_added = staged_reports_added = holds_added = events_added = 0
        hold_counts: Counter[str] = Counter()
        outcomes: list[dict[str, Any]] = []

        for record in records:
            intake_id = record["intake_id"]
            if intake_id in self._seen:
                replayed += 1
                outcomes.append({
                    "intake_id": intake_id,
                    "status": "IDEMPOTENT_REPLAY",
                    "hold_code": self.holds.get(intake_id, {}).get("hold_code"),
                    "record_sha256": _record_hash(record),
                })
                continue

            hold_code = _classify(record)
            if hold_code != record["truth_hold"]:
                raise IntegrityError(
                    f"classifier/truth mismatch for {intake_id}: {hold_code!r} != {record['truth_hold']!r}"
                )
            self._seen.add(intake_id)

            if hold_code:
                hold += 1
                hold_counts[hold_code] += 1
                self.holds[intake_id] = {
                    "intake_id": intake_id,
                    "hold_code": hold_code,
                    "workflow_created": 0,
                    "test_job_created": 0,
                    "report_created": 0,
                }
                holds_added += 1
                outcome = {
                    "intake_id": intake_id,
                    "status": "HOLD",
                    "hold_code": hold_code,
                    "workflow_created": 0,
                    "test_job_created": 0,
                    "report_created": 0,
                    "record_sha256": _record_hash(record),
                }
            else:
                ready += 1
                workflow = record["workflow"]
                provenance = {
                    field_name: copy.deepcopy(field["source"])
                    for field_name, field in record["fields"].items()
                }
                self.accessions[intake_id] = {
                    "intake_id": intake_id,
                    "accession_id": f"ACC-{intake_id[-4:]}",
                    "workflow": workflow,
                    "normalized_sha256": record["normalized_sha256"],
                    "field_provenance": provenance,
                }
                self.workflows[intake_id] = {
                    "intake_id": intake_id,
                    "workflow": workflow,
                    "state": "PREACCESSION_READY",
                }
                self.test_jobs[intake_id] = {
                    "intake_id": intake_id,
                    "workflow": workflow,
                    "state": "STAGED_NOT_STARTED",
                }
                self.staged_reports[intake_id] = {
                    "intake_id": intake_id,
                    "workflow": workflow,
                    "state": "STAGED_HUMAN_REVIEW",
                    "released_by": None,
                    "normalized_sha256": record["normalized_sha256"],
                }
                accessions_added += 1
                workflows_added += 1
                test_jobs_added += 1
                staged_reports_added += 1
                outcome = {
                    "intake_id": intake_id,
                    "status": "READY",
                    "hold_code": None,
                    "workflow": workflow,
                    "workflow_created": 1,
                    "test_job_created": 1,
                    "report_created": 1,
                    "record_sha256": _record_hash(record),
                    "normalized_sha256": record["normalized_sha256"],
                }

            self.events.append({
                "sequence": len(self.events) + 1,
                "intake_id": intake_id,
                "status": outcome["status"],
                "hold_code": outcome["hold_code"],
                "record_sha256": outcome["record_sha256"],
            })
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
            workflows_added=workflows_added,
            test_jobs_added=test_jobs_added,
            staged_reports_added=staged_reports_added,
            holds_added=holds_added,
            events_added=events_added,
            state_digest=self.state_digest(),
            outcomes=outcomes,
        )

    def release_report(self, intake_id: str, reviewer_name: str) -> dict[str, str]:
        reviewer = reviewer_name.strip()
        if not reviewer:
            raise PermissionError("named human reviewer is required")
        report = self.staged_reports.get(intake_id)
        if report is None:
            raise KeyError(intake_id)
        if intake_id in self.holds:
            raise PermissionError("held intake cannot release a report")
        report["state"] = "RELEASED_BY_NAMED_HUMAN"
        report["released_by"] = reviewer
        return {
            "intake_id": intake_id,
            "state": report["state"],
            "released_by": reviewer,
        }

    def automatic_release(self, *_: Any, **__: Any) -> None:
        raise PermissionError("automatic release is disabled; named human review is required")
