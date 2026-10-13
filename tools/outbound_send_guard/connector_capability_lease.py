"""Connector-native proof-of-possession lease for one-touch outbound seams.

V3 preserves the private-capability property of capability_lease v2 while using
Git objects exposed by ordinary connector catalogs: blob/tree/commit plus an
atomic create-exclusive branch ref. It never authorizes an external send.
"""
from __future__ import annotations

import hashlib
import json
import secrets
from typing import Any, Callable, Mapping

from .atomic_lease import (
    Claim as PublicClaim,
    LeaseError,
    _canon_json,
    _sha256,
    _validate_sha,
    _validate_sha256,
)

SCHEMA = "outbound-send-lease/v3"
PLAN_SCHEMA = "outbound-send-lease-plan/v3"
INTENT_SCHEMA = "outbound-send-lease-intent/v3"
RECEIPT_SCHEMA = "outbound-send-lease-receipt/v3"
METADATA_SCHEMA = "outbound-send-lease-metadata/v3"
REF_PREFIX = "refs/heads/outbound-lease-v3/"
BRANCH_PREFIX = "outbound-lease-v3/"
METADATA_PREFIX = ".tjlabs/outbound-send-lease-v3/"
CAPABILITY_BYTES = 32
CapabilitySink = Callable[[str], None]
ConnectorCapabilityLeaseError = LeaseError


def _capability(value: Any) -> str:
    return _validate_sha256(value, "claim capability")


def capability_commitment(capability: str) -> str:
    return hashlib.sha256(bytes.fromhex(_capability(capability))).hexdigest()


def _new_capability() -> str:
    return secrets.token_hex(CAPABILITY_BYTES)


def _seam(claim: PublicClaim) -> dict[str, str]:
    return {
        "schema": SCHEMA,
        "buyer_scope": claim.buyer_scope,
        "offer_scope": claim.offer_scope,
    }


def seam_sha256(claim_raw: Mapping[str, Any]) -> str:
    return _sha256(_seam(PublicClaim.parse(claim_raw)))


def branch_name(claim_raw: Mapping[str, Any]) -> str:
    return BRANCH_PREFIX + seam_sha256(claim_raw)


def lease_ref(claim_raw: Mapping[str, Any]) -> str:
    return REF_PREFIX + seam_sha256(claim_raw)


def metadata_path(claim_raw: Mapping[str, Any]) -> str:
    return METADATA_PREFIX + seam_sha256(claim_raw) + ".json"


def _metadata(claim: PublicClaim, commitment: str) -> dict[str, Any]:
    seam = _sha256(_seam(claim))
    return {
        "schema": METADATA_SCHEMA,
        "lease_schema": SCHEMA,
        "repo": claim.repo,
        "buyer_scope": claim.buyer_scope,
        "offer_scope": claim.offer_scope,
        "seam_sha256": seam,
        "lease_ref": REF_PREFIX + seam,
        "claimant": claim.claimant,
        "claim_id": claim.claim_id,
        "claim_started_at": claim.claim_started_at,
        "anchor_sha": claim.anchor_sha,
        "preflight_sha256": claim.preflight_sha256,
        "claim_capability_sha256": _validate_sha256(
            commitment, "claim_capability_sha256"
        ),
        "external_send_authorized": False,
    }


def _text_sha256(text: str) -> str:
    if not isinstance(text, str) or not text.isascii():
        raise LeaseError("metadata text must be ASCII")
    return hashlib.sha256(text.encode("ascii")).hexdigest()


def _strict_object(items):
    out: dict[str, Any] = {}
    for key, value in items:
        if key in out:
            raise LeaseError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def _strict_load_object(raw: str, field: str) -> Mapping[str, Any]:
    if not isinstance(raw, str) or not raw.isascii():
        raise LeaseError(f"{field}: ASCII JSON object required")
    try:
        value = json.loads(
            raw,
            object_pairs_hook=_strict_object,
            parse_constant=lambda token: (_ for _ in ()).throw(
                LeaseError(f"non-finite JSON number: {token}")
            ),
        )
    except (TypeError, ValueError, json.JSONDecodeError, LeaseError) as exc:
        raise LeaseError(f"{field}: invalid canonical JSON") from exc
    if not isinstance(value, Mapping):
        raise LeaseError(f"{field}: JSON object required")
    return value


_PLAN_FIELDS = {
    "schema", "repo", "buyer_scope", "offer_scope", "seam_sha256", "lease_ref",
    "branch_name", "metadata_path", "claimant", "claim_id", "claim_started_at",
    "anchor_sha", "preflight_sha256", "claim_capability_sha256", "metadata_sha256",
    "metadata_json", "external_send_authorized", "plan_sha256",
}


def prepare_acquisition(
    claim_raw: Mapping[str, Any], *, retain_capability: CapabilitySink
) -> dict[str, Any]:
    """Generate and retain the private capability before acquisition mutations.

    The returned plan is safe to publish: it contains only the capability
    commitment. The raw capability is delivered exactly once to the supplied
    private retention callback and is never returned.
    """
    claim = PublicClaim.parse(claim_raw)
    if not callable(retain_capability):
        raise LeaseError("retain_capability: callable required")
    capability = _new_capability()
    commitment = capability_commitment(capability)
    try:
        retain_capability(capability)
    except Exception as exc:
        raise LeaseError("capability retention failed before provider mutation") from exc
    metadata = _canon_json(_metadata(claim, commitment)).decode("ascii") + "\n"
    seam = _sha256(_seam(claim))
    plan: dict[str, Any] = {
        "schema": PLAN_SCHEMA,
        "repo": claim.repo,
        "buyer_scope": claim.buyer_scope,
        "offer_scope": claim.offer_scope,
        "seam_sha256": seam,
        "lease_ref": REF_PREFIX + seam,
        "branch_name": BRANCH_PREFIX + seam,
        "metadata_path": METADATA_PREFIX + seam + ".json",
        "claimant": claim.claimant,
        "claim_id": claim.claim_id,
        "claim_started_at": claim.claim_started_at,
        "anchor_sha": claim.anchor_sha,
        "preflight_sha256": claim.preflight_sha256,
        "claim_capability_sha256": commitment,
        "metadata_sha256": _text_sha256(metadata),
        "metadata_json": metadata,
        "external_send_authorized": False,
    }
    plan["plan_sha256"] = _sha256(plan)
    return plan


def _claim_from_values(raw: Mapping[str, Any]) -> PublicClaim:
    return PublicClaim.parse(
        {
            "repo": raw["repo"],
            "buyer_scope": raw["buyer_scope"],
            "offer_scope": raw["offer_scope"],
            "claimant": raw["claimant"],
            "claim_id": raw["claim_id"],
            "claim_started_at": raw["claim_started_at"],
            "anchor_sha": raw["anchor_sha"],
            "preflight_sha256": raw["preflight_sha256"],
        }
    )


def verify_plan(raw: Mapping[str, Any]) -> bool:
    if not isinstance(raw, Mapping) or set(raw) != _PLAN_FIELDS:
        raise LeaseError("v3 plan: exact fields required")
    if raw["schema"] != PLAN_SCHEMA:
        raise LeaseError("v3 plan: unsupported schema")
    claim = _claim_from_values(raw)
    seam = _sha256(_seam(claim))
    if _validate_sha256(raw["seam_sha256"], "plan seam_sha256") != seam:
        raise LeaseError("v3 plan: seam mismatch")
    if raw["lease_ref"] != REF_PREFIX + seam or raw["branch_name"] != BRANCH_PREFIX + seam:
        raise LeaseError("v3 plan: ref/branch mismatch")
    if raw["metadata_path"] != METADATA_PREFIX + seam + ".json":
        raise LeaseError("v3 plan: metadata path mismatch")
    commitment = _validate_sha256(
        raw["claim_capability_sha256"], "plan claim_capability_sha256"
    )
    if raw["external_send_authorized"] is not False:
        raise LeaseError("v3 plan: lease may never authorize external send")
    metadata = raw["metadata_json"]
    expected_metadata = _canon_json(_metadata(claim, commitment)).decode("ascii") + "\n"
    if metadata != expected_metadata:
        raise LeaseError("v3 plan: metadata content mismatch")
    if _validate_sha256(raw["metadata_sha256"], "plan metadata_sha256") != _text_sha256(metadata):
        raise LeaseError("v3 plan: metadata digest mismatch")
    digest = _validate_sha256(raw["plan_sha256"], "plan plan_sha256")
    material = dict(raw)
    material.pop("plan_sha256")
    if _sha256(material) != digest:
        raise LeaseError("v3 plan: digest mismatch")
    return True


_INTENT_FIELDS = {
    "schema", "repo", "buyer_scope", "offer_scope", "seam_sha256", "lease_ref",
    "branch_name", "metadata_path", "claimant", "claim_id", "claim_started_at",
    "anchor_sha", "preflight_sha256", "claim_capability_sha256", "metadata_sha256",
    "plan_sha256", "lease_commit_sha", "external_send_authorized", "intent_sha256",
}


def bind_lease_commit(plan_raw: Mapping[str, Any], lease_commit_sha: str) -> dict[str, Any]:
    """Bind the exact off-main metadata commit before atomic branch creation."""
    verify_plan(plan_raw)
    commit_sha = _validate_sha(lease_commit_sha, "lease_commit_sha")
    intent = {
        "schema": INTENT_SCHEMA,
        "repo": plan_raw["repo"],
        "buyer_scope": plan_raw["buyer_scope"],
        "offer_scope": plan_raw["offer_scope"],
        "seam_sha256": plan_raw["seam_sha256"],
        "lease_ref": plan_raw["lease_ref"],
        "branch_name": plan_raw["branch_name"],
        "metadata_path": plan_raw["metadata_path"],
        "claimant": plan_raw["claimant"],
        "claim_id": plan_raw["claim_id"],
        "claim_started_at": plan_raw["claim_started_at"],
        "anchor_sha": plan_raw["anchor_sha"],
        "preflight_sha256": plan_raw["preflight_sha256"],
        "claim_capability_sha256": plan_raw["claim_capability_sha256"],
        "metadata_sha256": plan_raw["metadata_sha256"],
        "plan_sha256": plan_raw["plan_sha256"],
        "lease_commit_sha": commit_sha,
        "external_send_authorized": False,
    }
    intent["intent_sha256"] = _sha256(intent)
    return intent


def verify_intent(raw: Mapping[str, Any]) -> bool:
    if not isinstance(raw, Mapping) or set(raw) != _INTENT_FIELDS:
        raise LeaseError("v3 intent: exact fields required")
    if raw["schema"] != INTENT_SCHEMA:
        raise LeaseError("v3 intent: unsupported schema")
    claim = _claim_from_values(raw)
    seam = _sha256(_seam(claim))
    if _validate_sha256(raw["seam_sha256"], "intent seam_sha256") != seam:
        raise LeaseError("v3 intent: seam mismatch")
    if raw["lease_ref"] != REF_PREFIX + seam or raw["branch_name"] != BRANCH_PREFIX + seam:
        raise LeaseError("v3 intent: ref/branch mismatch")
    if raw["metadata_path"] != METADATA_PREFIX + seam + ".json":
        raise LeaseError("v3 intent: metadata path mismatch")
    _validate_sha256(raw["claim_capability_sha256"], "intent claim_capability_sha256")
    _validate_sha256(raw["metadata_sha256"], "intent metadata_sha256")
    _validate_sha256(raw["plan_sha256"], "intent plan_sha256")
    _validate_sha(raw["lease_commit_sha"], "intent lease_commit_sha")
    if raw["external_send_authorized"] is not False:
        raise LeaseError("v3 intent: lease may never authorize external send")
    digest = _validate_sha256(raw["intent_sha256"], "intent intent_sha256")
    material = dict(raw)
    material.pop("intent_sha256")
    if _sha256(material) != digest:
        raise LeaseError("v3 intent: digest mismatch")
    return True


def _expected_metadata_from_values(raw: Mapping[str, Any]) -> str:
    claim = _claim_from_values(raw)
    commitment = _validate_sha256(
        raw["claim_capability_sha256"], "claim_capability_sha256"
    )
    return _canon_json(_metadata(claim, commitment)).decode("ascii") + "\n"


_RECEIPT_FIELDS = {
    "schema", "repo", "buyer_scope", "offer_scope", "seam_sha256", "lease_ref",
    "branch_name", "metadata_path", "claimant", "claim_id", "claim_started_at",
    "anchor_sha", "preflight_sha256", "claim_capability_sha256", "metadata_sha256",
    "plan_sha256", "intent_sha256", "lease_commit_sha", "observed_branch_sha",
    "observed_parent_sha", "lease_held_by_claimant", "decision", "reason",
    "external_send_authorized", "receipt_sha256",
}


def receipt_from_readback(
    intent_raw: Mapping[str, Any], *, observed_branch_sha: str | None,
    observed_parent_sha: str | None, observed_metadata_json: str | None,
) -> dict[str, Any]:
    """Compile public lease state from exact live connector readback evidence."""
    verify_intent(intent_raw)
    branch_sha = None if observed_branch_sha is None else _validate_sha(
        observed_branch_sha, "observed_branch_sha"
    )
    parent_sha = None if observed_parent_sha is None else _validate_sha(
        observed_parent_sha, "observed_parent_sha"
    )
    expected_commit = intent_raw["lease_commit_sha"]
    expected_parent = intent_raw["anchor_sha"]
    expected_metadata = _expected_metadata_from_values(intent_raw)
    held = False
    if branch_sha is None:
        reason = "BRANCH_MISSING_OR_UNREADABLE"
    elif branch_sha != expected_commit:
        reason = "HELD_BY_OTHER_OR_REF_DRIFT"
    elif parent_sha != expected_parent:
        reason = "ANCHOR_PARENT_MISMATCH"
    elif observed_metadata_json is None:
        reason = "METADATA_MISSING_OR_UNREADABLE"
    elif observed_metadata_json != expected_metadata:
        reason = "METADATA_MISMATCH"
    elif _text_sha256(observed_metadata_json) != intent_raw["metadata_sha256"]:
        reason = "METADATA_DIGEST_MISMATCH"
    else:
        held = True
        reason = "ACQUIRED_EXACT_READBACK"
    receipt: dict[str, Any] = {
        "schema": RECEIPT_SCHEMA,
        "repo": intent_raw["repo"],
        "buyer_scope": intent_raw["buyer_scope"],
        "offer_scope": intent_raw["offer_scope"],
        "seam_sha256": intent_raw["seam_sha256"],
        "lease_ref": intent_raw["lease_ref"],
        "branch_name": intent_raw["branch_name"],
        "metadata_path": intent_raw["metadata_path"],
        "claimant": intent_raw["claimant"],
        "claim_id": intent_raw["claim_id"],
        "claim_started_at": intent_raw["claim_started_at"],
        "anchor_sha": intent_raw["anchor_sha"],
        "preflight_sha256": intent_raw["preflight_sha256"],
        "claim_capability_sha256": intent_raw["claim_capability_sha256"],
        "metadata_sha256": intent_raw["metadata_sha256"],
        "plan_sha256": intent_raw["plan_sha256"],
        "intent_sha256": intent_raw["intent_sha256"],
        "lease_commit_sha": intent_raw["lease_commit_sha"],
        "observed_branch_sha": branch_sha,
        "observed_parent_sha": parent_sha,
        "lease_held_by_claimant": held,
        "decision": "LEASE_HELD" if held else "HOLD",
        "reason": reason,
        "external_send_authorized": False,
    }
    receipt["receipt_sha256"] = _sha256(receipt)
    return receipt


def verify_receipt(raw: Mapping[str, Any]) -> bool:
    if not isinstance(raw, Mapping) or set(raw) != _RECEIPT_FIELDS:
        raise LeaseError("v3 receipt: exact fields required")
    if raw["schema"] != RECEIPT_SCHEMA:
        raise LeaseError("v3 receipt: unsupported schema")
    claim = _claim_from_values(raw)
    seam = _sha256(_seam(claim))
    if _validate_sha256(raw["seam_sha256"], "receipt seam_sha256") != seam:
        raise LeaseError("v3 receipt: seam mismatch")
    if raw["lease_ref"] != REF_PREFIX + seam or raw["branch_name"] != BRANCH_PREFIX + seam:
        raise LeaseError("v3 receipt: ref/branch mismatch")
    if raw["metadata_path"] != METADATA_PREFIX + seam + ".json":
        raise LeaseError("v3 receipt: metadata path mismatch")
    _validate_sha256(raw["claim_capability_sha256"], "receipt claim_capability_sha256")
    _validate_sha256(raw["metadata_sha256"], "receipt metadata_sha256")
    _validate_sha256(raw["plan_sha256"], "receipt plan_sha256")
    _validate_sha256(raw["intent_sha256"], "receipt intent_sha256")
    commit_sha = _validate_sha(raw["lease_commit_sha"], "receipt lease_commit_sha")
    observed = raw["observed_branch_sha"]
    if observed is not None:
        observed = _validate_sha(observed, "receipt observed_branch_sha")
    parent = raw["observed_parent_sha"]
    if parent is not None:
        parent = _validate_sha(parent, "receipt observed_parent_sha")
    held = raw["lease_held_by_claimant"]
    if type(held) is not bool:
        raise LeaseError("v3 receipt: lease_held_by_claimant must be bool")
    if raw["decision"] != ("LEASE_HELD" if held else "HOLD"):
        raise LeaseError("v3 receipt: decision inconsistent with lease state")
    if not isinstance(raw["reason"], str) or not raw["reason"]:
        raise LeaseError("v3 receipt: reason required")
    if raw["external_send_authorized"] is not False:
        raise LeaseError("v3 receipt: lease may never authorize external send")
    if held and (observed != commit_sha or parent != claim.anchor_sha):
        raise LeaseError("v3 receipt: held lease lacks exact commit/parent evidence")
    digest = _validate_sha256(raw["receipt_sha256"], "receipt receipt_sha256")
    material = dict(raw)
    material.pop("receipt_sha256")
    if _sha256(material) != digest:
        raise LeaseError("v3 receipt: digest mismatch")
    return True


def verify_possession(
    raw: Mapping[str, Any], *, claim_capability: str,
    live_branch_sha: str | None, live_parent_sha: str | None,
    live_metadata_json: str | None,
) -> bool:
    """Require private capability and exact current provider evidence.

    Provider reads are intentionally supplied by the connector executor. This
    function has no network transport and therefore cannot accidentally mutate
    provider state or leak the raw capability.
    """
    verify_receipt(raw)
    capability = _capability(claim_capability)
    if capability_commitment(capability) != raw["claim_capability_sha256"]:
        return False
    if live_branch_sha is None or live_parent_sha is None or live_metadata_json is None:
        return False
    try:
        branch_sha = _validate_sha(live_branch_sha, "live_branch_sha")
        parent_sha = _validate_sha(live_parent_sha, "live_parent_sha")
    except LeaseError:
        return False
    if branch_sha != raw["lease_commit_sha"] or parent_sha != raw["anchor_sha"]:
        return False
    expected_metadata = _expected_metadata_from_values(raw)
    if live_metadata_json != expected_metadata:
        return False
    if _text_sha256(live_metadata_json) != raw["metadata_sha256"]:
        return False
    return True


def public_capability_absent(value: Any, capability: str) -> bool:
    """Convenience test helper: recursively prove the raw capability is absent."""
    secret = _capability(capability)
    return secret not in json.dumps(value, sort_keys=True, separators=(",", ":"))
