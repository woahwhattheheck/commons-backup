from __future__ import annotations

import hashlib
from typing import Any

from .codec import BATCH_SCHEMA, RECORD_SCHEMA, REFERENCE_SCHEMA


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _clean_record(i: int) -> dict[str, Any]:
    code = f"TLCK-{i:03d}"
    return {
        "schema": RECORD_SCHEMA,
        "record_id": f"REC-{i:03d}",
        "code": code,
        "ingredient_id": f"ING-{(i % 12) + 1:02d}",
        "spec_revision": "SPEC-7",
        "region": "NA",
        "use_ref": f"USE-{i:03d}",
        "use_level": "0.40",
        "claim_ref": "CLAIM-A",
        "allergen_label_hash": _hash(f"label-{i}"),
        "legacy_code": f"LEG-{i:03d}",
        "stability_result": "STABLE",
        "stability_protocol_version": "STAB-2",
        "commercial_owner": "COMM-OWNER-1",
        "science_owner": "SCI-OWNER-1",
        "owner_version": "OV-3",
    }


def _reference(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "record_id": record["record_id"],
        "code": record["code"],
        "ingredient_id": record["ingredient_id"],
        "approved_spec_revision": "SPEC-7",
        "approved_region": "NA",
        "use_ref": record["use_ref"],
        "max_use_level": "0.50",
        "approved_claim_ref": "CLAIM-A",
        "legacy_code": record["legacy_code"],
        "target_code": record["code"],
        "mapping_version": "MAP-4",
        "stability_protocol_version": "STAB-2",
        "accepted_stability_result": "STABLE",
        "commercial_owner": "COMM-OWNER-1",
        "science_owner": "SCI-OWNER-1",
        "owner_version": "OV-3",
    }


def make_acceptance_reference_set() -> dict[str, Any]:
    records = [_clean_record(i) for i in range(1, 121)]
    return {
        "schema": REFERENCE_SCHEMA,
        "generation": "SYNTHETIC-REFERENCE-GEN-20260913-A",
        "records": [_reference(record) for record in records],
    }


def make_acceptance_batch() -> dict[str, Any]:
    """120 synthetic packs: 90 PASS, 30 HOLD, 75 seeded defects."""
    records = [_clean_record(i) for i in range(1, 121)]
    for i in range(91, 111):
        records[i - 1]["spec_revision"] = "SPEC-6"
    for i in range(91, 106):
        records[i - 1]["region"] = "EU"
    for i in range(106, 121):
        records[i - 1]["legacy_code"] = f"UNMAPPED-{i:03d}"
    for i in range(96, 111):
        records[i - 1]["stability_result"] = "INCOMPLETE"
    for i in range(111, 121):
        records[i - 1]["owner_version"] = "OV-2"
    return {"schema": BATCH_SCHEMA, "records": records}
