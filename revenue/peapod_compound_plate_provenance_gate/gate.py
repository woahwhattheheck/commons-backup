from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Iterable, Mapping, Sequence

from .model import (
    DEFECT_CODES,
    DUPLICATE_ASSIGNMENT,
    HOLD,
    ORPHANED_RUN_LINK,
    READY_FOR_SCREEN,
    RECORD_SCHEMA,
    SCHEMA,
    SOURCE_DESTINATION_MISMATCH,
    STALE_PROTOCOL,
    VOLUME_BALANCE_FAILURE,
    WRONG_POOL_MEMBERSHIP,
    canonical_bytes,
    digest,
    normalize_context,
    normalize_transfer,
)

TRANSFER_OUTPUT_FIELDS = (
    "sequence transfer_id compound_master_id source_vial_id source_plate_id source_well "
    "source_plate_lot source_volume_ul_before transfer_volume_ul source_volume_ul_after "
    "source_concentration_um membership_type pool_id destination_plate_id destination_well "
    "destination_plate_lot destination_compound_master_id assay_protocol_id "
    "assay_protocol_version control_well_map_hash instrument_run_id"
).split()
CSV_FIELDS = TRANSFER_OUTPUT_FIELDS + [
    "decision", "codes", "input_sha256", "previous_record_sha256", "record_sha256"
]


def defect_codes(row: Mapping[str, Any], context: Mapping[str, Any], seen: set[tuple[str, str]]) -> list[str]:
    codes: list[str] = []
    assignment = (row["destination_plate_id"], row["destination_well"])
    if assignment in seen:
        codes.append(DUPLICATE_ASSIGNMENT)
    else:
        seen.add(assignment)
    compound = context["compounds"].get(row["compound_master_id"])
    source_keys = (
        "source_vial_id", "source_plate_id", "source_well",
        "source_plate_lot", "source_concentration_um",
    )
    if compound is None or any(row[key] != compound[key] for key in source_keys) or (
        row["destination_compound_master_id"] != row["compound_master_id"]
    ):
        codes.append(SOURCE_DESTINATION_MISMATCH)
    if row["membership_type"] == "pool":
        members = context["pools"].get(row["pool_id"])
        if members is None or row["compound_master_id"] not in members:
            codes.append(WRONG_POOL_MEMBERSHIP)
    before = Decimal(row["source_volume_ul_before"])
    moved = Decimal(row["transfer_volume_ul"])
    after = Decimal(row["source_volume_ul_after"])
    if moved <= 0 or moved > before or before - moved != after:
        codes.append(VOLUME_BALANCE_FAILURE)
    protocol = context["protocols"].get(row["assay_protocol_id"])
    if protocol is None or (
        row["assay_protocol_version"] != protocol["current_version"]
        or row["control_well_map_hash"] != protocol["control_well_map_hash"]
    ):
        codes.append(STALE_PROTOCOL)
    run = context["runs"].get(row["instrument_run_id"])
    if run is None or (
        row["destination_plate_id"] != run["destination_plate_id"]
        or row["assay_protocol_id"] != run["assay_protocol_id"]
    ):
        codes.append(ORPHANED_RUN_LINK)
    return [code for code in DEFECT_CODES if code in codes]


def make_record(row: Mapping[str, Any], codes: Sequence[str], previous: str) -> dict[str, Any]:
    record = {
        "schema": RECORD_SCHEMA,
        **{key: row[key] for key in TRANSFER_OUTPUT_FIELDS},
        "decision": READY_FOR_SCREEN if not codes else HOLD,
        "codes": list(codes),
        "input_sha256": digest(canonical_bytes(row)),
        "previous_record_sha256": previous,
    }
    record["record_sha256"] = digest(canonical_bytes(record))
    return record


def csv_bytes(records: Sequence[Mapping[str, Any]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    for record in records:
        row = {key: record[key] for key in CSV_FIELDS}
        row["pool_id"] = row["pool_id"] or ""
        row["codes"] = "|".join(row["codes"])
        writer.writerow(row)
    return stream.getvalue().encode()


@dataclass(frozen=True)
class GateArtifacts:
    manifest: dict[str, Any]
    json_bytes: bytes
    csv_bytes: bytes
    manifest_sha256: str
    csv_sha256: str

    @property
    def ready_count(self) -> int:
        return int(self.manifest["summary"]["ready_count"])

    @property
    def hold_count(self) -> int:
        return int(self.manifest["summary"]["hold_count"])


def build_gate_artifacts(transfers: Iterable[Mapping[str, Any]], context: Mapping[str, Any]) -> GateArtifacts:
    context = normalize_context(context)
    rows = sorted(
        (normalize_transfer(row) for row in transfers),
        key=lambda row: (row["sequence"], row["transfer_id"]),
    )
    sequences = [row["sequence"] for row in rows]
    transfer_ids = [row["transfer_id"] for row in rows]
    if len(sequences) != len(set(sequences)):
        raise ValueError("duplicate sequence")
    if len(transfer_ids) != len(set(transfer_ids)):
        raise ValueError("duplicate transfer_id")
    seen: set[tuple[str, str]] = set()
    records: list[dict[str, Any]] = []
    counts = {code: 0 for code in DEFECT_CODES}
    previous = "0" * 64
    for row in rows:
        codes = defect_codes(row, context, seen)
        for code in codes:
            counts[code] += 1
        record = make_record(row, codes, previous)
        records.append(record)
        previous = record["record_sha256"]
    ready = sum(record["decision"] == READY_FOR_SCREEN for record in records)
    manifest = {
        "schema": SCHEMA,
        "context_sha256": digest(canonical_bytes(context)),
        "authority": {
            "research_metadata_only": True,
            "scientific_release_authorized": False,
            "hit_selection_authorized": False,
            "potency_toxicity_efficacy_judgment_authorized": False,
            "buyer_acceptance_claimed": False,
            "revenue_claimed": False,
            "external_effect_authorized": False,
        },
        "summary": {
            "transfer_count": len(records),
            "ready_count": ready,
            "hold_count": len(records) - ready,
            "defect_counts": counts,
            "last_record_sha256": previous,
        },
        "records": records,
    }
    payload = canonical_bytes(manifest)
    csv = csv_bytes(records)
    return GateArtifacts(manifest, payload, csv, digest(payload), digest(csv))


def verify_gate_artifacts(
    json_bytes: bytes,
    csv: bytes,
    *,
    manifest_sha256: str,
    csv_sha256: str,
) -> bool:
    if digest(json_bytes) != manifest_sha256 or digest(csv) != csv_sha256:
        return False
    try:
        manifest = json.loads(json_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return False
    if canonical_bytes(manifest) != json_bytes or manifest.get("schema") != SCHEMA:
        return False
    if set(manifest) != {"schema", "context_sha256", "authority", "summary", "records"}:
        return False
    expected_authority = {
        "research_metadata_only": True,
        "scientific_release_authorized": False,
        "hit_selection_authorized": False,
        "potency_toxicity_efficacy_judgment_authorized": False,
        "buyer_acceptance_claimed": False,
        "revenue_claimed": False,
        "external_effect_authorized": False,
    }
    if manifest["authority"] != expected_authority:
        return False
    records = manifest.get("records")
    summary = manifest.get("summary")
    if not isinstance(records, list) or not isinstance(summary, dict):
        return False
    expected_summary_keys = {
        "transfer_count", "ready_count", "hold_count", "defect_counts", "last_record_sha256"
    }
    if set(summary) != expected_summary_keys:
        return False
    previous = "0" * 64
    counts = {code: 0 for code in DEFECT_CODES}
    ready = 0
    sequences: set[int] = set()
    transfer_ids: set[str] = set()
    record_keys = frozenset(CSV_FIELDS) | {"schema"}
    for record in records:
        if not isinstance(record, dict) or set(record) != record_keys or record.get("schema") != RECORD_SCHEMA:
            return False
        if record["previous_record_sha256"] != previous:
            return False
        unsigned = dict(record)
        recorded = unsigned.pop("record_sha256")
        if digest(canonical_bytes(unsigned)) != recorded:
            return False
        if record["sequence"] in sequences or record["transfer_id"] in transfer_ids:
            return False
        sequences.add(record["sequence"])
        transfer_ids.add(record["transfer_id"])
        codes = record["codes"]
        if not isinstance(codes, list) or len(codes) != len(set(codes)):
            return False
        if any(code not in DEFECT_CODES for code in codes):
            return False
        expected = READY_FOR_SCREEN if not codes else HOLD
        if record["decision"] != expected:
            return False
        ready += expected == READY_FOR_SCREEN
        for code in codes:
            counts[code] += 1
        previous = recorded
    expected_summary = {
        "transfer_count": len(records),
        "ready_count": ready,
        "hold_count": len(records) - ready,
        "defect_counts": counts,
        "last_record_sha256": previous,
    }
    return summary == expected_summary and csv_bytes(records) == csv
