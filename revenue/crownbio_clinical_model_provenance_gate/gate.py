"""Deterministic, fail-closed evidence gate for synthetic study packets.

This module is deliberately authority-limited. ``STUDY_READY`` means only that the
supplied machine evidence is internally complete and consistent with the declared
scope contract. It is not a scientific, clinical, CAP/CLIA, sponsor, regulatory,
or release decision and it performs no network or external-system mutation.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
import hashlib
import hmac
import json
import re
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence, Tuple

PACKET_SCHEMA = "crownbio.provenance-gate/v1"
DECISION_SCHEMA = "crownbio.provenance-decision/v1"
MANIFEST_SCHEMA = "crownbio.provenance-manifest/v1"
READY = "STUDY_READY"
HOLD = "HOLD"

_ID_PATTERNS = {
    "packet_id": re.compile(r"^pkt_[a-z0-9_]{2,48}$"),
    "sponsor_id": re.compile(r"^spn_[a-z0-9_]{2,48}$"),
    "study_id": re.compile(r"^std_[a-z0-9_]{2,48}$"),
    "model_id": re.compile(r"^mdl_[a-z0-9_]{2,48}$"),
    "site_id": re.compile(r"^site_[a-z0-9_]{2,48}$"),
    "accreditation_scope_id": re.compile(r"^scp_[a-z0-9_]{2,48}$"),
    "sample_id": re.compile(r"^smp_[a-z0-9_]{2,48}$"),
    "artifact_id": re.compile(r"^art_[a-z0-9_]{2,48}$"),
    "event_id": re.compile(r"^evt_[a-z0-9_]{2,48}$"),
}
_MACHINE_TOKEN_RE = re.compile(r"^[a-z][a-z0-9_.:-]{0,63}$")
_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
_UTC_SECOND_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

FORBIDDEN_KEY_TOKENS = (
    "patient",
    "person",
    "name",
    "email",
    "phone",
    "address",
    "dob",
    "birth",
    "mrn",
    "diagnosis",
    "treatment",
    "therapy",
    "prognosis",
    "outcome",
    "medical_record",
    "phi",
    "pii",
    "ssn",
)

REQUIRED_FIELDS = frozenset(
    {
        "packet_id",
        "sponsor_id",
        "study_id",
        "model_id",
        "passage",
        "allowed_passage_min",
        "allowed_passage_max",
        "declared_use",
        "allowed_uses",
        "site_id",
        "assay_id",
        "assay_version",
        "accreditation_scope_id",
        "accreditation_site_id",
        "accreditation_assays",
        "accreditation_valid_through",
        "sample_id",
        "custody_study_id",
        "custody_model_id",
        "custody_passage",
        "qc_state",
        "artifact_id",
        "artifact_sha256",
        "artifact_study_id",
        "artifact_model_id",
        "artifact_passage",
        "recorded_at",
        "event_id",
    }
)


class EvidenceGateError(ValueError):
    """Raised for malformed or prohibited evidence input."""


class SensitiveEvidenceError(EvidenceGateError):
    """Raised when prohibited person/medical fields appear in input."""


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise EvidenceGateError("payload is not canonically serializable") from exc


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _normalized_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", key.lower()).strip("_")


def _reject_sensitive_keys(value: Any, path: str = "$") -> None:
    if type(value) is dict:
        for key, child in value.items():
            if not isinstance(key, str):
                raise EvidenceGateError(f"{path}: object keys must be strings")
            normalized = _normalized_key(key)
            if any(token in normalized for token in FORBIDDEN_KEY_TOKENS):
                raise SensitiveEvidenceError(f"{path}.{key}: prohibited sensitive field")
            _reject_sensitive_keys(child, f"{path}.{key}")
    elif type(value) is list:
        for index, child in enumerate(value):
            _reject_sensitive_keys(child, f"{path}[{index}]")
    elif isinstance(value, (dict, list)):
        raise EvidenceGateError(f"{path}: dict/list subclasses are not accepted")


def _require_plain_dict(value: Any, label: str) -> Dict[str, Any]:
    if type(value) is not dict:
        raise EvidenceGateError(f"{label} must be a plain object")
    return value


def _require_plain_list(value: Any, label: str) -> list[Any]:
    if type(value) is not list:
        raise EvidenceGateError(f"{label} must be a plain list")
    return value


def _require_id(value: Any, field: str) -> str:
    pattern = _ID_PATTERNS[field]
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise EvidenceGateError(f"{field} is not a valid opaque identifier")
    return value


def _require_machine_token(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _MACHINE_TOKEN_RE.fullmatch(value):
        raise EvidenceGateError(f"{field} must be a lowercase machine token")
    return value


def _require_int(value: Any, field: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise EvidenceGateError(f"{field} must be an integer >= {minimum}")
    return value


def _require_sha256(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise EvidenceGateError(f"{field} must be lowercase SHA-256 hex")
    return value


def _parse_utc_second(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not _UTC_SECOND_RE.fullmatch(value):
        raise EvidenceGateError(f"{field} must use canonical UTC-second form")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise EvidenceGateError(f"{field} is not a real UTC timestamp") from exc


def _parse_date(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise EvidenceGateError(f"{field} must use YYYY-MM-DD")
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise EvidenceGateError(f"{field} is not a real calendar date") from exc


def validate_packet(raw: Any) -> Dict[str, Any]:
    """Return a canonical deep-normalized packet after strict schema validation."""
    payload = _require_plain_dict(raw, "packet")
    _reject_sensitive_keys(payload)
    keys = set(payload)
    missing = REQUIRED_FIELDS - keys
    extra = keys - REQUIRED_FIELDS
    if missing:
        raise EvidenceGateError(f"missing fields: {sorted(missing)}")
    if extra:
        raise EvidenceGateError(f"unknown fields: {sorted(extra)}")

    for field in (
        "packet_id",
        "sponsor_id",
        "study_id",
        "model_id",
        "site_id",
        "accreditation_scope_id",
        "sample_id",
        "artifact_id",
        "event_id",
    ):
        _require_id(payload[field], field)

    for field in (
        "custody_study_id",
        "artifact_study_id",
    ):
        if not isinstance(payload[field], str) or not _ID_PATTERNS["study_id"].fullmatch(payload[field]):
            raise EvidenceGateError(f"{field} must be an opaque study identifier")
    for field in (
        "custody_model_id",
        "artifact_model_id",
    ):
        if not isinstance(payload[field], str) or not _ID_PATTERNS["model_id"].fullmatch(payload[field]):
            raise EvidenceGateError(f"{field} must be an opaque model identifier")
    if not isinstance(payload["accreditation_site_id"], str) or not _ID_PATTERNS["site_id"].fullmatch(payload["accreditation_site_id"]):
        raise EvidenceGateError("accreditation_site_id must be an opaque site identifier")

    for field in ("passage", "allowed_passage_min", "allowed_passage_max", "custody_passage", "artifact_passage"):
        _require_int(payload[field], field)
    if payload["allowed_passage_min"] > payload["allowed_passage_max"]:
        raise EvidenceGateError("allowed passage range is inverted")

    _require_machine_token(payload["declared_use"], "declared_use")
    allowed_uses = _require_plain_list(payload["allowed_uses"], "allowed_uses")
    if not allowed_uses or len(allowed_uses) != len(set(map(str, allowed_uses))):
        raise EvidenceGateError("allowed_uses must be a non-empty unique list")
    for index, item in enumerate(allowed_uses):
        _require_machine_token(item, f"allowed_uses[{index}]")

    _require_machine_token(payload["assay_id"], "assay_id")
    _require_machine_token(payload["assay_version"], "assay_version")
    assays = _require_plain_dict(payload["accreditation_assays"], "accreditation_assays")
    if not assays:
        raise EvidenceGateError("accreditation_assays may not be empty")
    normalized_assays: Dict[str, list[str]] = {}
    for assay, versions in assays.items():
        _require_machine_token(assay, "accreditation assay")
        version_list = _require_plain_list(versions, f"accreditation_assays[{assay}]")
        if not version_list or len(version_list) != len(set(map(str, version_list))):
            raise EvidenceGateError(f"accreditation assay {assay} versions must be non-empty and unique")
        normalized_versions = []
        for index, version in enumerate(version_list):
            normalized_versions.append(_require_machine_token(version, f"accreditation_assays[{assay}][{index}]"))
        normalized_assays[assay] = sorted(normalized_versions)

    _parse_date(payload["accreditation_valid_through"], "accreditation_valid_through")
    _require_machine_token(payload["qc_state"], "qc_state")
    _require_sha256(payload["artifact_sha256"], "artifact_sha256")
    _parse_utc_second(payload["recorded_at"], "recorded_at")

    canonical = dict(payload)
    canonical["allowed_uses"] = sorted(allowed_uses)
    canonical["accreditation_assays"] = {
        key: normalized_assays[key] for key in sorted(normalized_assays)
    }
    return canonical


def _reason_codes(packet: Mapping[str, Any]) -> Tuple[str, ...]:
    reasons: list[str] = []
    if packet["declared_use"] not in packet["allowed_uses"]:
        reasons.append("USE_OUT_OF_SCOPE")
    if not (packet["allowed_passage_min"] <= packet["passage"] <= packet["allowed_passage_max"]):
        reasons.append("PASSAGE_OUT_OF_SCOPE")
    if packet["custody_model_id"] != packet["model_id"] or packet["artifact_model_id"] != packet["model_id"]:
        reasons.append("MODEL_LINEAGE_MISMATCH")
    if packet["custody_passage"] != packet["passage"] or packet["artifact_passage"] != packet["passage"]:
        reasons.append("PASSAGE_LINEAGE_MISMATCH")
    if packet["custody_study_id"] != packet["study_id"] or packet["artifact_study_id"] != packet["study_id"]:
        reasons.append("STUDY_LINEAGE_MISMATCH")
    if packet["accreditation_site_id"] != packet["site_id"]:
        reasons.append("ACCREDITATION_SITE_MISMATCH")
    permitted_versions = packet["accreditation_assays"].get(packet["assay_id"], [])
    if packet["assay_version"] not in permitted_versions:
        reasons.append("ASSAY_OUT_OF_DECLARED_SCOPE")
    recorded_day = _parse_utc_second(packet["recorded_at"], "recorded_at").date()
    valid_through = _parse_date(packet["accreditation_valid_through"], "accreditation_valid_through").date()
    if recorded_day > valid_through:
        reasons.append("ACCREDITATION_SCOPE_STALE")
    if packet["qc_state"] != "released_for_study":
        reasons.append("QC_NOT_READY")
    if packet["artifact_sha256"] == "0" * 64:
        reasons.append("ARTIFACT_DIGEST_SENTINEL")
    return tuple(sorted(set(reasons)))


def _decision_core(
    *,
    event_id: str,
    packet_id: str,
    status: str,
    reasons: Sequence[str],
    packet_digest: str,
) -> Dict[str, Any]:
    return {
        "schema_version": DECISION_SCHEMA,
        "event_id": event_id,
        "packet_id": packet_id,
        "status": status,
        "reasons": list(reasons),
        "packet_digest": packet_digest,
    }


@dataclass(frozen=True)
class Decision:
    schema_version: str
    event_id: str
    packet_id: str
    status: str
    reasons: Tuple[str, ...]
    packet_digest: str
    decision_digest: str
    replayed: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "packet_id": self.packet_id,
            "status": self.status,
            "reasons": list(self.reasons),
            "packet_digest": self.packet_digest,
            "decision_digest": self.decision_digest,
            "replayed": self.replayed,
        }


def evaluate(raw: Any) -> Decision:
    packet = validate_packet(raw)
    packet_digest = _sha256(packet)
    reasons = _reason_codes(packet)
    status = READY if not reasons else HOLD
    core = _decision_core(
        event_id=packet["event_id"],
        packet_id=packet["packet_id"],
        status=status,
        reasons=reasons,
        packet_digest=packet_digest,
    )
    return Decision(
        schema_version=DECISION_SCHEMA,
        event_id=packet["event_id"],
        packet_id=packet["packet_id"],
        status=status,
        reasons=reasons,
        packet_digest=packet_digest,
        decision_digest=_sha256(core),
    )


def verify_decision(decision: Any) -> bool:
    if type(decision) is not Decision:
        return False
    try:
        if decision.schema_version != DECISION_SCHEMA:
            return False
        if decision.status not in (READY, HOLD):
            return False
        if decision.replayed:
            # A replay marker is transport/accounting state, not part of signed decision core.
            candidate = replace(decision, replayed=False)
        else:
            candidate = decision
        if not _SHA256_RE.fullmatch(candidate.packet_digest):
            return False
        if not _SHA256_RE.fullmatch(candidate.decision_digest):
            return False
        core = _decision_core(
            event_id=candidate.event_id,
            packet_id=candidate.packet_id,
            status=candidate.status,
            reasons=candidate.reasons,
            packet_digest=candidate.packet_digest,
        )
        expected = _sha256(core)
        return hmac.compare_digest(expected, candidate.decision_digest)
    except (AttributeError, EvidenceGateError, TypeError, ValueError):
        return False


@dataclass(frozen=True)
class _LedgerEntry:
    event_id: str
    packet_digest: str
    decision: Decision


class GateLedger:
    """Append-only logical ledger with exact-event replay suppression."""

    def __init__(self) -> None:
        self._entries: list[_LedgerEntry] = []
        self._by_event: Dict[str, _LedgerEntry] = {}

    @property
    def entry_count(self) -> int:
        return len(self._entries)

    def apply(self, raw: Any) -> Decision:
        packet = validate_packet(raw)
        packet_digest = _sha256(packet)
        event_id = packet["event_id"]
        existing = self._by_event.get(event_id)
        if existing is not None:
            if hmac.compare_digest(existing.packet_digest, packet_digest):
                return replace(existing.decision, replayed=True)
            conflict_core = _decision_core(
                event_id=event_id,
                packet_id=packet["packet_id"],
                status=HOLD,
                reasons=("EVENT_ID_CHANGED_PAYLOAD",),
                packet_digest=packet_digest,
            )
            conflict = Decision(
                schema_version=DECISION_SCHEMA,
                event_id=event_id,
                packet_id=packet["packet_id"],
                status=HOLD,
                reasons=("EVENT_ID_CHANGED_PAYLOAD",),
                packet_digest=packet_digest,
                decision_digest=_sha256(conflict_core),
            )
            self._entries.append(_LedgerEntry(event_id, packet_digest, conflict))
            return conflict

        decision = evaluate(packet)
        entry = _LedgerEntry(event_id, packet_digest, decision)
        self._entries.append(entry)
        self._by_event[event_id] = entry
        return decision

    def canonical_manifest(self) -> Dict[str, Any]:
        rows = [
            {
                "event_id": entry.event_id,
                "packet_digest": entry.packet_digest,
                "decision": entry.decision.to_dict(),
            }
            for entry in self._entries
        ]
        rows.sort(
            key=lambda row: (
                row["event_id"],
                row["packet_digest"],
                row["decision"]["decision_digest"],
            )
        )
        core = {
            "schema_version": MANIFEST_SCHEMA,
            "entry_count": len(rows),
            "rows": rows,
        }
        return {**core, "manifest_digest": _sha256(core)}


def verify_manifest(manifest: Any) -> bool:
    if type(manifest) is not dict:
        return False
    try:
        if set(manifest) != {"schema_version", "entry_count", "rows", "manifest_digest"}:
            return False
        if manifest["schema_version"] != MANIFEST_SCHEMA:
            return False
        if isinstance(manifest["entry_count"], bool) or not isinstance(manifest["entry_count"], int):
            return False
        rows = manifest["rows"]
        if type(rows) is not list or manifest["entry_count"] != len(rows):
            return False
        normalized_rows = []
        previous_key: Optional[Tuple[str, str, str]] = None
        for row in rows:
            if type(row) is not dict or set(row) != {"event_id", "packet_digest", "decision"}:
                return False
            if not isinstance(row["packet_digest"], str) or not _SHA256_RE.fullmatch(row["packet_digest"]):
                return False
            data = row["decision"]
            if type(data) is not dict:
                return False
            if set(data) != {
                "schema_version", "event_id", "packet_id", "status", "reasons",
                "packet_digest", "decision_digest", "replayed"
            }:
                return False
            if data["replayed"] is not False:
                return False
            decision = Decision(
                schema_version=data["schema_version"],
                event_id=data["event_id"],
                packet_id=data["packet_id"],
                status=data["status"],
                reasons=tuple(data["reasons"]),
                packet_digest=data["packet_digest"],
                decision_digest=data["decision_digest"],
                replayed=False,
            )
            if row["packet_digest"] != decision.packet_digest or row["event_id"] != decision.event_id:
                return False
            if not verify_decision(decision):
                return False
            key = (row["event_id"], row["packet_digest"], decision.decision_digest)
            if previous_key is not None and key < previous_key:
                return False
            previous_key = key
            normalized_rows.append(row)
        core = {
            "schema_version": MANIFEST_SCHEMA,
            "entry_count": manifest["entry_count"],
            "rows": normalized_rows,
        }
        expected = _sha256(core)
        return isinstance(manifest["manifest_digest"], str) and hmac.compare_digest(
            expected, manifest["manifest_digest"]
        )
    except (AttributeError, EvidenceGateError, KeyError, TypeError, ValueError):
        return False


__all__ = [
    "DECISION_SCHEMA",
    "EvidenceGateError",
    "GateLedger",
    "HOLD",
    "MANIFEST_SCHEMA",
    "PACKET_SCHEMA",
    "READY",
    "SensitiveEvidenceError",
    "Decision",
    "evaluate",
    "validate_packet",
    "verify_decision",
    "verify_manifest",
]
