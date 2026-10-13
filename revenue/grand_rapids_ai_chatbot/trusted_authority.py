#!/usr/bin/env python3
"""Retained authority verifier for Grand Rapids RFP 920-45-269.

Proposal state and process environment are untrusted. This module never acquires
an authority root from CLI flags, environment variables, or proposal bytes.
Trusted host integration must independently authenticate the current generation
and authority digest, then pass those values explicitly to
``load_current_authority``. The public preflight CLI never calls that loader.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

AUTHORITY_SCHEMA = "grand-rapids-920-45-269-authority/v1"
SOLICITATION_ID = "920-45-269"
MAX_AUTHORITY_BYTES = 1_048_576
HEX64 = re.compile(r"[0-9a-f]{64}")
SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}")

REQUIRED_GATES = (
    "controlling_packet_acquired", "packet_sha256_verified",
    "question_channel_resolved", "addenda_reconciled",
    "bidder_eligibility_resolved", "vss_registration_resolved",
    "ebo_requirements_resolved", "certifications_resolved",
    "references_resolved", "mandatory_forms_complete",
    "technical_narrative_complete", "integration_scope_resolved",
    "security_requirements_resolved", "acceptance_plan_complete",
    "pricing_form_complete", "owner_release_to_submit",
)

GATE_EVIDENCE_KIND = MappingProxyType({
    "controlling_packet_acquired": "CONTROLLING_PACKET",
    "packet_sha256_verified": "PACKET_SHA256_VERIFICATION",
    "question_channel_resolved": "QUESTION_CHANNEL_AUTHORITY",
    "addenda_reconciled": "ADDENDA_RECONCILIATION",
    "bidder_eligibility_resolved": "BIDDER_ELIGIBILITY",
    "vss_registration_resolved": "VSS_REGISTRATION",
    "ebo_requirements_resolved": "EBO_REQUIREMENTS",
    "certifications_resolved": "CERTIFICATION_SET",
    "references_resolved": "REFERENCE_AUTHORITY",
    "mandatory_forms_complete": "MANDATORY_FORMS",
    "technical_narrative_complete": "TECHNICAL_NARRATIVE",
    "integration_scope_resolved": "INTEGRATION_SCOPE",
    "security_requirements_resolved": "SECURITY_REQUIREMENTS",
    "acceptance_plan_complete": "ACCEPTANCE_PLAN",
    "pricing_form_complete": "PRICING_FORM",
    "owner_release_to_submit": "OWNER_RELEASE",
})

_MATERIAL_KEYS = {
    "schema_version", "solicitation_id", "generation", "packet_sha256",
    "addenda", "required_gates", "evidence",
}
_ADDENDUM_KEYS = {"id", "sha256"}
_EVIDENCE_KEYS = {"id", "gate", "kind", "sha256", "source_generation_sha256"}
_CONSTRUCTOR_TOKEN = object()


class AuthorityError(ValueError):
    """Authority input is malformed, stale, forked, or mismatched to a trusted root."""


@dataclass(frozen=True)
class EvidenceRecord:
    id: str
    gate: str
    kind: str
    sha256: str
    source_generation_sha256: str


class VerifiedAuthority:
    __slots__ = (
        "generation", "authority_sha256", "source_generation_sha256",
        "packet_sha256", "_evidence",
    )

    def __init__(
        self, *, _token: object, generation: int, authority_sha256: str,
        source_generation_sha256: str, packet_sha256: str,
        evidence: tuple[EvidenceRecord, ...],
    ) -> None:
        if _token is not _CONSTRUCTOR_TOKEN:
            raise TypeError("VerifiedAuthority can only be created by trusted-root verification")
        self.generation = generation
        self.authority_sha256 = authority_sha256
        self.source_generation_sha256 = source_generation_sha256
        self.packet_sha256 = packet_sha256
        self._evidence = MappingProxyType({row.id: row for row in evidence})

    def evidence(self, evidence_id: str) -> EvidenceRecord | None:
        return self._evidence.get(evidence_id)


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _strict_int(value: Any, *, name: str) -> int:
    if type(value) is not int or value < 1:
        raise AuthorityError(f"{name} must be an integer >= 1")
    return value


def _hex64(value: Any, *, name: str) -> str:
    if not isinstance(value, str) or HEX64.fullmatch(value) is None:
        raise AuthorityError(f"{name} must be lowercase 64-hex")
    return value


def _safe_id(value: Any, *, name: str) -> str:
    if not isinstance(value, str) or SAFE_ID.fullmatch(value) is None:
        raise AuthorityError(f"{name} is not a canonical authority identifier")
    return value


def source_generation_sha256(material: Mapping[str, Any]) -> str:
    packet = _hex64(material.get("packet_sha256"), name="packet_sha256")
    addenda = material.get("addenda")
    if not isinstance(addenda, list):
        raise AuthorityError("addenda must be a list")
    normalized: list[dict[str, str]] = []
    previous: str | None = None
    for index, row in enumerate(addenda):
        if not isinstance(row, dict) or set(row) != _ADDENDUM_KEYS:
            raise AuthorityError(f"addenda[{index}] must have exact id/sha256 keys")
        ident = _safe_id(row.get("id"), name=f"addenda[{index}].id")
        digest = _hex64(row.get("sha256"), name=f"addenda[{index}].sha256")
        if previous is not None and ident <= previous:
            raise AuthorityError("addenda must be strictly sorted by unique id")
        previous = ident
        normalized.append({"id": ident, "sha256": digest})
    return hashlib.sha256(
        canonical_json({"packet_sha256": packet, "addenda": normalized})
    ).hexdigest()


def release_subject_sha256(
    *,
    solicitation_id: str,
    source_generation: str,
    evidence: tuple[EvidenceRecord, ...] | list[EvidenceRecord],
) -> str:
    """Digest of solicitation + packet/addenda generation + non-release evidence."""
    projection = [
        {
            "id": row.id,
            "gate": row.gate,
            "kind": row.kind,
            "sha256": row.sha256,
            "source_generation_sha256": row.source_generation_sha256,
        }
        for row in evidence
        if row.gate != "owner_release_to_submit" and row.kind != "OWNER_RELEASE"
    ]
    projection.sort(key=lambda row: row["id"])
    return hashlib.sha256(
        canonical_json(
            {
                "solicitation_id": solicitation_id,
                "source_generation_sha256": source_generation,
                "required_gates": list(REQUIRED_GATES),
                "evidence": projection,
            }
        )
    ).hexdigest()


def _validated_material(
    value: Any,
) -> tuple[dict[str, Any], tuple[EvidenceRecord, ...], str]:
    if not isinstance(value, dict) or set(value) != _MATERIAL_KEYS:
        raise AuthorityError("authority material has unexpected or missing keys")
    if value.get("schema_version") != AUTHORITY_SCHEMA:
        raise AuthorityError(f"schema_version must be {AUTHORITY_SCHEMA!r}")
    if value.get("solicitation_id") != SOLICITATION_ID:
        raise AuthorityError(f"solicitation_id must be exactly {SOLICITATION_ID!r}")
    _strict_int(value.get("generation"), name="generation")
    packet_sha = _hex64(value.get("packet_sha256"), name="packet_sha256")
    source_digest = source_generation_sha256(value)

    if value.get("required_gates") != list(REQUIRED_GATES):
        raise AuthorityError("required_gates must exactly equal the canonical gate universe")
    evidence = value.get("evidence")
    if not isinstance(evidence, list):
        raise AuthorityError("evidence must be a list")

    records: list[EvidenceRecord] = []
    seen: set[str] = set()
    for index, row in enumerate(evidence):
        if not isinstance(row, dict) or set(row) != _EVIDENCE_KEYS:
            raise AuthorityError(f"evidence[{index}] has unexpected or missing keys")
        ident = _safe_id(row.get("id"), name=f"evidence[{index}].id")
        if ident in seen:
            raise AuthorityError(f"duplicate evidence id {ident!r}")
        seen.add(ident)
        gate = row.get("gate")
        if gate not in GATE_EVIDENCE_KIND:
            raise AuthorityError(f"evidence[{index}].gate is not canonical")
        kind = row.get("kind")
        expected_kind = GATE_EVIDENCE_KIND[gate]
        if kind != expected_kind:
            raise AuthorityError(
                f"evidence {ident!r} kind must be {expected_kind!r} for gate {gate!r}"
            )
        digest = _hex64(row.get("sha256"), name=f"evidence[{index}].sha256")
        row_source = _hex64(
            row.get("source_generation_sha256"),
            name=f"evidence[{index}].source_generation_sha256",
        )
        if row_source != source_digest:
            raise AuthorityError(f"evidence {ident!r} is bound to a stale source generation")
        if gate == "controlling_packet_acquired" and digest != packet_sha:
            raise AuthorityError("CONTROLLING_PACKET evidence digest must equal packet_sha256")
        if gate == "packet_sha256_verified" and digest != packet_sha:
            raise AuthorityError(
                "PACKET_SHA256_VERIFICATION evidence digest must equal packet_sha256"
            )
        records.append(EvidenceRecord(ident, gate, kind, digest, row_source))

    subject = release_subject_sha256(
        solicitation_id=SOLICITATION_ID,
        source_generation=source_digest,
        evidence=tuple(records),
    )
    for row in records:
        if row.gate == "owner_release_to_submit" and row.sha256 != subject:
            raise AuthorityError(
                "OWNER_RELEASE evidence digest must equal the current release-subject digest"
            )

    detached = json.loads(canonical_json(value))
    return detached, tuple(records), source_digest


def authority_sha256(material: Mapping[str, Any]) -> str:
    detached, _, _ = _validated_material(dict(material))
    return hashlib.sha256(canonical_json(detached)).hexdigest()


def _parse_json_strict(raw: bytes) -> Any:
    if len(raw) > MAX_AUTHORITY_BYTES:
        raise AuthorityError(f"authority envelope exceeds {MAX_AUTHORITY_BYTES} bytes")
    try:
        text = raw.decode("utf-8", "strict")
    except UnicodeDecodeError as exc:
        raise AuthorityError("authority envelope must be strict UTF-8") from exc

    def no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in pairs:
            if key in out:
                raise AuthorityError(f"authority envelope contains duplicate key {key!r}")
            out[key] = value
        return out

    try:
        return json.loads(text, object_pairs_hook=no_duplicates)
    except json.JSONDecodeError as exc:
        raise AuthorityError("authority envelope is not valid JSON") from exc


def load_current_authority(
    path: str | Path,
    *,
    trusted_generation: int,
    trusted_authority_sha256: str,
) -> VerifiedAuthority:
    """Verify authority bytes against a root authenticated by trusted host code.

    This function does not authenticate the root parameters themselves. They are
    explicit capability inputs that trusted host integration must obtain outside
    proposal bytes, CLI arguments, and caller-controlled process environment.
    """
    expected_generation = _strict_int(trusted_generation, name="trusted_generation")
    expected_digest = _hex64(
        trusted_authority_sha256,
        name="trusted_authority_sha256",
    )
    material = _parse_json_strict(Path(path).read_bytes())
    detached, records, source_digest = _validated_material(material)
    digest = hashlib.sha256(canonical_json(detached)).hexdigest()
    generation = detached["generation"]
    if generation != expected_generation:
        raise AuthorityError("authority generation does not match the trusted host root")
    if digest != expected_digest:
        raise AuthorityError("authority digest does not match the trusted host root")
    return VerifiedAuthority(
        _token=_CONSTRUCTOR_TOKEN,
        generation=generation,
        authority_sha256=digest,
        source_generation_sha256=source_digest,
        packet_sha256=detached["packet_sha256"],
        evidence=records,
    )
