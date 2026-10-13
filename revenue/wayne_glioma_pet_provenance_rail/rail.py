"""Synthetic, side-effect-free provenance rail for Wayne State R01CA309136.

This module models only lineage evidence over synthetic identifiers and SHA-256
pointers. It does not process images, PHI, dose quantities, clinical findings,
or treatment decisions, and it performs no external effects.
"""

from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
import hashlib
import json
import re
from typing import Any, Iterable, Mapping, Sequence

SCHEMA_VERSION = 1
MAX_EVENTS = 20_000
MAX_TEXT = 160
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
NONE = "NONE"

FORBIDDEN_PII_KEYS = frozenset(
    {
        "name", "first_name", "last_name", "full_name", "email", "phone",
        "address", "ssn", "social_security_number", "dob", "date_of_birth",
        "patient_id", "participant_id", "student_id", "mrn",
        "medical_record_number", "medical_record", "diagnosis", "treatment",
        "dose_amount", "administered_activity", "birth_date",
    }
)

SCHEMAS: dict[str, frozenset[str]] = {
    "tracer_batch": frozenset(
        {
            "event_id", "kind", "batch_id", "protocol_id", "synthesis_run_id",
            "batch_revision", "supersedes_batch_id", "release_evidence_sha256",
        }
    ),
    "dose_receipt": frozenset(
        {
            "event_id", "kind", "dose_receipt_id", "synthetic_subject_id",
            "batch_id", "protocol_id", "administration_record_sha256",
        }
    ),
    "acquisition": frozenset(
        {
            "event_id", "kind", "acquisition_id", "synthetic_subject_id",
            "dose_receipt_id", "protocol_id", "scanner_id",
            "acquisition_evidence_sha256", "acquisition_label",
        }
    ),
    "scan_qc": frozenset(
        {
            "event_id", "kind", "qc_id", "synthetic_subject_id",
            "acquisition_id", "qc_evidence_sha256",
        }
    ),
    "map_version": frozenset(
        {
            "event_id", "kind", "map_id", "synthetic_subject_id",
            "acquisition_id", "qc_id", "map_version", "method_id",
            "segmentation_sha256", "parameters_sha256", "map_sha256",
            "supersedes_map_id",
        }
    ),
    "handoff_receipt": frozenset(
        {
            "event_id", "kind", "handoff_id", "synthetic_subject_id",
            "map_id", "handoff_role", "receipt_sha256",
        }
    ),
}

ID_FIELDS = frozenset(
    {
        "event_id", "batch_id", "protocol_id", "synthesis_run_id",
        "supersedes_batch_id", "dose_receipt_id", "synthetic_subject_id",
        "acquisition_id", "scanner_id", "acquisition_label", "qc_id",
        "map_id", "method_id", "supersedes_map_id", "handoff_id",
        "handoff_role",
    }
)
HASH_FIELDS = frozenset(
    {
        "release_evidence_sha256", "administration_record_sha256",
        "acquisition_evidence_sha256", "qc_evidence_sha256",
        "segmentation_sha256", "parameters_sha256", "map_sha256",
        "receipt_sha256",
    }
)


class RailError(ValueError):
    """Fail-closed error carrying a stable machine-readable code."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _fail(code: str, message: str) -> None:
    raise RailError(code, message)


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _root(items: Iterable[Any]) -> str:
    rows = sorted(canonical_json(item) for item in items)
    return sha256_text("\n".join(rows))


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str):
        _fail("INVALID_EVENT", f"{field} must be text")
    cleaned = value.strip()
    if not cleaned or len(cleaned) > MAX_TEXT:
        _fail("INVALID_EVENT", f"{field} must contain 1-{MAX_TEXT} characters")
    return cleaned


def _identifier(value: Any, field: str) -> str:
    cleaned = _text(value, field)
    if not ID_RE.fullmatch(cleaned):
        _fail("INVALID_EVENT", f"{field} is not a canonical identifier")
    if field == "synthetic_subject_id" and not cleaned.startswith("SYNTH-SUBJECT-"):
        _fail("NON_SYNTHETIC_SUBJECT", "synthetic_subject_id must begin with SYNTH-SUBJECT-")
    return cleaned


def _positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        _fail("INVALID_EVENT", f"{field} must be a positive integer")
    if value > 1_000_000:
        _fail("INVALID_EVENT", f"{field} exceeds the bounded integer range")
    return value


def _hash(value: Any, field: str) -> str:
    cleaned = _text(value, field).lower()
    if not SHA256_RE.fullmatch(cleaned):
        _fail("INVALID_EVENT", f"{field} must be a lowercase SHA-256 hex digest")
    return cleaned


def normalize_event(raw: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        _fail("INVALID_EVENT", "event must be an object")
    for key, value in raw.items():
        if not isinstance(key, str):
            _fail("INVALID_EVENT", "event keys must be text")
        if key.lower() in FORBIDDEN_PII_KEYS:
            _fail("PII_FORBIDDEN", f"field {key!r} is forbidden in the synthetic rail")
        if isinstance(value, (Mapping, list, tuple, set)):
            _fail("NESTED_DATA_FORBIDDEN", f"{key} must be scalar; raw payloads are forbidden")
        if value is None or isinstance(value, float):
            _fail("INVALID_EVENT", f"{key} uses an unsupported scalar type")

    kind = _text(raw.get("kind"), "kind")
    allowed = SCHEMAS.get(kind)
    if allowed is None:
        _fail("UNKNOWN_KIND", f"unsupported event kind {kind!r}")
    actual = frozenset(raw.keys())
    missing = allowed - actual
    extra = actual - allowed
    if missing:
        _fail("MISSING_FIELD", f"{kind} missing fields: {', '.join(sorted(missing))}")
    if extra:
        _fail("UNKNOWN_FIELD", f"{kind} contains unknown fields: {', '.join(sorted(extra))}")

    normalized: dict[str, Any] = {"kind": kind}
    for field in sorted(allowed - {"kind"}):
        value = raw[field]
        if field in ID_FIELDS:
            normalized[field] = _identifier(value, field)
        elif field in HASH_FIELDS:
            normalized[field] = _hash(value, field)
        elif field in {"batch_revision", "map_version"}:
            normalized[field] = _positive_int(value, field)
        else:
            _fail("INVALID_SCHEMA", f"normalizer missing field {field}")
    return {key: normalized[key] for key in sorted(normalized)}


def _quarantine(event: Mapping[str, Any], code: str) -> dict[str, str]:
    return {"event_id": str(event["event_id"]), "kind": str(event["kind"]), "code": code}


def _index_unique(
    events: Iterable[dict[str, Any]],
    business_field: str,
    duplicate_code: str,
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for event in events:
        key = event[business_field]
        if key in result:
            _fail(duplicate_code, f"{business_field} {key} appears more than once")
        result[key] = event
    return result


def _validate_batch_lineage(batches: Mapping[str, dict[str, Any]]) -> None:
    for batch in batches.values():
        parent_id = batch["supersedes_batch_id"]
        if parent_id == NONE:
            if batch["batch_revision"] != 1:
                _fail("BATCH_LINEAGE_INVALID", f"{batch['batch_id']} revision >1 lacks a parent batch")
            continue
        parent = batches.get(parent_id)
        if parent is None:
            _fail("BATCH_LINEAGE_INVALID", f"{batch['batch_id']} supersedes unknown batch {parent_id}")
        if parent["protocol_id"] != batch["protocol_id"]:
            _fail("BATCH_LINEAGE_INVALID", f"{batch['batch_id']} changes protocol across resynthesis lineage")
        if parent["batch_revision"] >= batch["batch_revision"]:
            _fail("BATCH_LINEAGE_INVALID", f"{batch['batch_id']} revision must increase from its parent")
        seen = {batch["batch_id"]}
        cursor = parent
        while cursor["supersedes_batch_id"] != NONE:
            cursor_id = cursor["supersedes_batch_id"]
            if cursor_id in seen:
                _fail("BATCH_LINEAGE_CYCLE", f"batch lineage cycles through {cursor_id}")
            seen.add(cursor_id)
            cursor = batches.get(cursor_id)
            if cursor is None:
                _fail("BATCH_LINEAGE_INVALID", f"batch lineage references unknown batch {cursor_id}")


def reconcile(events: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Return a deterministic manifest over a bounded synthetic event batch."""

    if isinstance(events, (str, bytes)) or not isinstance(events, Sequence):
        _fail("INVALID_BATCH", "events must be a finite sequence")
    if len(events) > MAX_EVENTS:
        _fail("BATCH_TOO_LARGE", f"event count exceeds {MAX_EVENTS}")

    by_event_id: dict[str, dict[str, Any]] = {}
    replay_collapsed = 0
    for raw in events:
        event = normalize_event(raw)
        event_id = event["event_id"]
        previous = by_event_id.get(event_id)
        if previous is None:
            by_event_id[event_id] = event
        elif previous == event:
            replay_collapsed += 1
        else:
            _fail("IDEMPOTENCY_CONFLICT", f"event_id {event_id} was reused for changed content")

    unique_events = sorted(by_event_id.values(), key=lambda row: row["event_id"])
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in unique_events:
        grouped[event["kind"]].append(event)

    batches = _index_unique(grouped["tracer_batch"], "batch_id", "DUPLICATE_BATCH_ID")
    _validate_batch_lineage(batches)

    quarantines: list[dict[str, str]] = []

    dose_candidates = _index_unique(grouped["dose_receipt"], "dose_receipt_id", "DUPLICATE_DOSE_RECEIPT_ID")
    doses: dict[str, dict[str, Any]] = {}
    for dose_id, dose in dose_candidates.items():
        batch = batches.get(dose["batch_id"])
        if batch is None:
            quarantines.append(_quarantine(dose, "DOSE_UNKNOWN_BATCH"))
            continue
        if dose["protocol_id"] != batch["protocol_id"]:
            quarantines.append(_quarantine(dose, "DOSE_PROTOCOL_MISMATCH"))
            continue
        doses[dose_id] = dose

    acquisition_candidates = _index_unique(
        grouped["acquisition"], "acquisition_id", "DUPLICATE_ACQUISITION_ID"
    )
    acquisitions: dict[str, dict[str, Any]] = {}
    for acquisition_id, acquisition in acquisition_candidates.items():
        dose = doses.get(acquisition["dose_receipt_id"])
        if dose is None:
            quarantines.append(_quarantine(acquisition, "ACQUISITION_UNAVAILABLE_DOSE"))
            continue
        if acquisition["synthetic_subject_id"] != dose["synthetic_subject_id"]:
            quarantines.append(_quarantine(acquisition, "ACQUISITION_CROSS_SUBJECT"))
            continue
        if acquisition["protocol_id"] != dose["protocol_id"]:
            quarantines.append(_quarantine(acquisition, "ACQUISITION_PROTOCOL_MISMATCH"))
            continue
        acquisitions[acquisition_id] = acquisition

    qc_candidates = _index_unique(grouped["scan_qc"], "qc_id", "DUPLICATE_QC_ID")
    qcs: dict[str, dict[str, Any]] = {}
    for qc_id, qc in qc_candidates.items():
        acquisition = acquisitions.get(qc["acquisition_id"])
        if acquisition is None:
            quarantines.append(_quarantine(qc, "QC_UNAVAILABLE_ACQUISITION"))
            continue
        if qc["synthetic_subject_id"] != acquisition["synthetic_subject_id"]:
            quarantines.append(_quarantine(qc, "QC_CROSS_SUBJECT"))
            continue
        qcs[qc_id] = qc

    map_candidates = _index_unique(grouped["map_version"], "map_id", "DUPLICATE_MAP_ID")
    prelim_maps: dict[str, dict[str, Any]] = {}
    for map_id, map_event in map_candidates.items():
        acquisition = acquisitions.get(map_event["acquisition_id"])
        qc = qcs.get(map_event["qc_id"])
        if acquisition is None:
            quarantines.append(_quarantine(map_event, "MAP_UNAVAILABLE_ACQUISITION"))
            continue
        if qc is None:
            quarantines.append(_quarantine(map_event, "MAP_UNAVAILABLE_QC"))
            continue
        if qc["acquisition_id"] != acquisition["acquisition_id"]:
            quarantines.append(_quarantine(map_event, "MAP_QC_ACQUISITION_MISMATCH"))
            continue
        if map_event["synthetic_subject_id"] != acquisition["synthetic_subject_id"]:
            quarantines.append(_quarantine(map_event, "MAP_CROSS_SUBJECT"))
            continue
        if map_event["synthetic_subject_id"] != qc["synthetic_subject_id"]:
            quarantines.append(_quarantine(map_event, "MAP_QC_CROSS_SUBJECT"))
            continue
        prelim_maps[map_id] = map_event

    # Same subject + acquisition + explicit version must identify exactly one map.
    version_groups: dict[tuple[str, str, int], list[str]] = defaultdict(list)
    for map_id, map_event in prelim_maps.items():
        key = (
            map_event["synthetic_subject_id"],
            map_event["acquisition_id"],
            map_event["map_version"],
        )
        version_groups[key].append(map_id)
    ambiguous_map_ids = {
        map_id
        for ids in version_groups.values()
        if len(ids) > 1
        for map_id in ids
    }

    maps: dict[str, dict[str, Any]] = {}
    for map_id, map_event in prelim_maps.items():
        if map_id in ambiguous_map_ids:
            quarantines.append(_quarantine(map_event, "MAP_VERSION_AMBIGUOUS"))
            continue
        parent_id = map_event["supersedes_map_id"]
        if parent_id != NONE:
            parent = prelim_maps.get(parent_id)
            if parent is None or parent_id in ambiguous_map_ids:
                quarantines.append(_quarantine(map_event, "MAP_SUPERSEDES_UNAVAILABLE"))
                continue
            if (
                parent["synthetic_subject_id"] != map_event["synthetic_subject_id"]
                or parent["acquisition_id"] != map_event["acquisition_id"]
            ):
                quarantines.append(_quarantine(map_event, "MAP_SUPERSESSION_SCOPE_MISMATCH"))
                continue
            if parent["map_version"] >= map_event["map_version"]:
                quarantines.append(_quarantine(map_event, "MAP_VERSION_REGRESSION"))
                continue
        elif map_event["map_version"] != 1:
            quarantines.append(_quarantine(map_event, "MAP_VERSION_MISSING_PARENT"))
            continue
        maps[map_id] = map_event

    # If a retained map points to a map that was later quarantined by the above
    # pass, it cannot form a complete lineage.
    stable = True
    while stable:
        stable = False
        for map_id, map_event in list(maps.items()):
            parent_id = map_event["supersedes_map_id"]
            if parent_id != NONE and parent_id not in maps:
                quarantines.append(_quarantine(map_event, "MAP_SUPERSEDES_UNAVAILABLE"))
                del maps[map_id]
                stable = True

    superseded_map_ids = {
        map_event["supersedes_map_id"]
        for map_event in maps.values()
        if map_event["supersedes_map_id"] != NONE
    }

    handoff_candidates = _index_unique(
        grouped["handoff_receipt"], "handoff_id", "DUPLICATE_HANDOFF_ID"
    )
    handoffs: dict[str, dict[str, Any]] = {}
    for handoff_id, handoff in handoff_candidates.items():
        map_event = maps.get(handoff["map_id"])
        if map_event is None:
            quarantines.append(_quarantine(handoff, "HANDOFF_UNAVAILABLE_MAP"))
            continue
        if handoff["map_id"] in superseded_map_ids:
            quarantines.append(_quarantine(handoff, "HANDOFF_SUPERSEDED_MAP"))
            continue
        if handoff["synthetic_subject_id"] != map_event["synthetic_subject_id"]:
            quarantines.append(_quarantine(handoff, "HANDOFF_CROSS_SUBJECT"))
            continue
        handoffs[handoff_id] = handoff

    batch_rows = sorted(batches.values(), key=lambda row: row["batch_id"])
    dose_rows = sorted(doses.values(), key=lambda row: row["dose_receipt_id"])
    acquisition_rows = sorted(acquisitions.values(), key=lambda row: row["acquisition_id"])
    qc_rows = sorted(qcs.values(), key=lambda row: row["qc_id"])
    map_rows = sorted(maps.values(), key=lambda row: row["map_id"])
    handoff_rows = sorted(handoffs.values(), key=lambda row: row["handoff_id"])
    quarantines.sort(key=lambda row: (row["event_id"], row["code"]))

    complete_subjects = sorted({row["synthetic_subject_id"] for row in handoff_rows})
    event_digests = sorted(sha256_text(canonical_json(event)) for event in unique_events)

    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "product": "WAYNE_R01CA309136_GLIOMA_PET_TRACER_TO_MAP_PROVENANCE_RAIL",
        "authority": "SYNTHETIC_INTERNAL_PROVENANCE_ONLY",
        "input_records": len(events),
        "unique_events": len(unique_events),
        "replay_collapsed": replay_collapsed,
        "complete_synthetic_subjects": len(complete_subjects),
        "counts": {
            "tracer_batches": len(batch_rows),
            "dose_receipts_mapped": len(dose_rows),
            "acquisitions_mapped": len(acquisition_rows),
            "scan_qc_mapped": len(qc_rows),
            "map_versions_mapped": len(map_rows),
            "handoffs_mapped": len(handoff_rows),
            "quarantined": len(quarantines),
        },
        "roots": {
            "events_sha256": sha256_text("\n".join(event_digests)),
            "batches_sha256": _root(batch_rows),
            "dose_receipts_sha256": _root(dose_rows),
            "acquisitions_sha256": _root(acquisition_rows),
            "scan_qc_sha256": _root(qc_rows),
            "map_versions_sha256": _root(map_rows),
            "handoffs_sha256": _root(handoff_rows),
            "quarantine_sha256": _root(quarantines),
        },
        "quarantines": quarantines,
    }
    manifest["receipt_sha256"] = sha256_text(canonical_json(manifest))
    return manifest


def verify_receipt(manifest: Mapping[str, Any]) -> bool:
    if not isinstance(manifest, Mapping):
        return False
    supplied = manifest.get("receipt_sha256")
    if not isinstance(supplied, str) or not SHA256_RE.fullmatch(supplied):
        return False
    unsigned = deepcopy(dict(manifest))
    unsigned.pop("receipt_sha256", None)
    return sha256_text(canonical_json(unsigned)) == supplied
