"""Buyer-contract acceptance wrapper for the MRHD evidence rail.

The core rail deliberately avoids treating repeated applicant IDs as invalid:
MRHD's public rules allow some entity types to submit distinct projects. The
buyer acceptance contract does, however, require duplicate applicant/project
pairs to remain visibly ambiguous. This wrapper adds that evidence-only HOLD
without dropping either approved award state.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from copy import deepcopy
from typing import Any, Iterable

from .fixture import FIXTURE_EVENT_COUNT, build_acceptance_fixture as _base_fixture
from .rail import EvidenceInputError, reconcile as _core_reconcile


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def build_buyer_acceptance_fixture() -> list[dict[str, Any]]:
    """Return the exact 180-event fixture including duplicate applicant/project IDs."""
    records = deepcopy(_base_fixture())
    approvals = [r for r in records if r.get("event_type") == "AWARD_APPROVED"]
    baseline = next(r for r in approvals if r.get("award_id") == "SYN-AWARD-01")
    duplicate = next(r for r in approvals if r.get("award_id") == "SYN-AWARD-20")
    duplicate["payload"]["applicant_id"] = baseline["payload"]["applicant_id"]
    duplicate["payload"]["project_id"] = baseline["payload"]["project_id"]
    if len(records) != FIXTURE_EVENT_COUNT:
        raise AssertionError("buyer acceptance fixture must remain exactly 180 events")
    return records


def reconcile(
    records: Iterable[dict[str, Any]], *, signing_key: bytes
) -> dict[str, Any]:
    """Run the core rail and add duplicate applicant/project ambiguity receipts."""
    if not isinstance(signing_key, (bytes, bytearray)) or not signing_key:
        raise EvidenceInputError("signing_key must be non-empty bytes")
    materialized = [deepcopy(record) for record in records]
    manifest = _core_reconcile(materialized, signing_key=bytes(signing_key))

    admitted = {
        (a["award_id"], a["applicant_id"], a["project_id"])
        for a in manifest.get("awards", [])
    }
    pairs: dict[tuple[str, str], str] = {}
    extra_holds: list[dict[str, Any]] = []
    for event in sorted(
        materialized,
        key=lambda e: (
            e.get("sequence") if isinstance(e, dict) and isinstance(e.get("sequence"), int) else -1,
            e.get("event_id") if isinstance(e, dict) else "",
        ),
    ):
        if not isinstance(event, dict) or event.get("event_type") != "AWARD_APPROVED":
            continue
        award_id = event.get("award_id")
        payload = event.get("payload")
        if not isinstance(award_id, str) or not isinstance(payload, dict):
            continue
        applicant_id = payload.get("applicant_id")
        project_id = payload.get("project_id")
        if not isinstance(applicant_id, str) or not isinstance(project_id, str):
            continue
        if (award_id, applicant_id, project_id) not in admitted:
            continue

        pair = (applicant_id, project_id)
        prior_award = pairs.get(pair)
        if prior_award is not None and prior_award != award_id:
            extra_holds.append(
                {
                    "code": "DUPLICATE_APPLICANT_PROJECT",
                    "event_id": str(event.get("event_id")),
                    "award_id": award_id,
                    "action": "REVIEW",
                    "owner_role": "MRHD_STAFF",
                    "message": (
                        "applicant_id/project_id pair is already bound to "
                        f"{prior_award}; both approved award states remain visible "
                        "pending named review"
                    ),
                }
            )
        else:
            pairs[pair] = award_id

    if not extra_holds:
        return manifest

    body = {
        key: deepcopy(value)
        for key, value in manifest.items()
        if key not in {"manifest_sha256", "manifest_hmac_sha256"}
    }
    existing = {
        (h.get("code"), h.get("event_id"), h.get("award_id"))
        for h in body.get("holds", [])
        if isinstance(h, dict)
    }
    for hold in extra_holds:
        key = (hold["code"], hold["event_id"], hold["award_id"])
        if key not in existing:
            body["holds"].append(hold)
            existing.add(key)
    body["holds"].sort(
        key=lambda h: (
            "" if h.get("award_id") is None else str(h.get("award_id")),
            str(h.get("event_id")),
            str(h.get("code")),
        )
    )
    body["disposition"] = "HOLD"
    payload = _canonical_json(body)
    return {
        **body,
        "manifest_sha256": hashlib.sha256(payload).hexdigest(),
        "manifest_hmac_sha256": hmac.new(
            bytes(signing_key), payload, hashlib.sha256
        ).hexdigest(),
    }
