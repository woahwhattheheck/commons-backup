"""Provider-bound authority verification for atomic outbound-send lease receipts.

`atomic_lease.verify_receipt()` proves only that a receipt is internally
well-formed and self-consistent. This module proves the live coordination-repo
state that makes a lease useful as a mutual-exclusion prerequisite.
"""
from __future__ import annotations

import hashlib
import json
import urllib.parse
from typing import Any, Mapping

from .atomic_lease import (
    SCHEMA,
    LeaseError,
    Transport,
    _display_token,
    _machine_token,
    _object_sha,
    _rfc3339,
    _validate_repo,
    _validate_sha,
    verify_receipt,
)

_METADATA_FIELDS = {
    "schema",
    "repo",
    "buyer_scope",
    "offer_scope",
    "claimant",
    "claim_id",
    "claim_started_at",
    "anchor_sha",
    "preflight_sha256",
    "seam_sha256",
}


def _canonical_sha256(value: Any) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")
    return hashlib.sha256(raw).hexdigest()


def _sha256_digest(value: Any, field: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise LeaseError(f"{field}: expected 64 lowercase hex characters")
    lowered = value.lower()
    if value != lowered or any(ch not in "0123456789abcdef" for ch in value):
        raise LeaseError(f"{field}: expected 64 lowercase hex characters")
    return value


def _metadata_from_tag(tag_body: Any) -> Mapping[str, Any] | None:
    if not isinstance(tag_body, Mapping):
        return None
    message = tag_body.get("message")
    if not isinstance(message, str):
        return None
    try:
        metadata = json.loads(message)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(metadata, Mapping) or set(metadata) != _METADATA_FIELDS:
        return None
    return metadata


def verify_authoritative_receipt(
    raw: Mapping[str, Any],
    *,
    repo: str,
    buyer_scope: str,
    offer_scope: str,
    claimant: str,
    claim_id: str,
    claim_started_at: str,
    anchor_sha: str,
    preflight_sha256: str,
    transport: Transport,
) -> bool:
    """Prove that this caller's held receipt matches authoritative GitHub state.

    The expected coordination repo, seam, durable caller identity/generation,
    and preflight digest are supplied out-of-band by the consumer. A copied
    winner receipt is insufficient: this function first binds the receipt to
    those expected caller facts, then re-reads the deterministic ref and its
    annotated tag object and requires both to bind the same facts.

    Provider/readback uncertainty fails closed as ``False``. Structurally
    invalid caller inputs or receipts raise ``LeaseError``.
    """
    verify_receipt(raw)
    expected_repo = _validate_repo(repo)
    expected_buyer = _machine_token(buyer_scope, "buyer_scope")
    expected_offer = _machine_token(offer_scope, "offer_scope")
    expected_claimant = _display_token(claimant, "claimant")
    expected_claim_id = _machine_token(claim_id, "claim_id")
    expected_started = _rfc3339(claim_started_at, "claim_started_at")
    expected_anchor = _validate_sha(anchor_sha, "anchor_sha")
    expected_preflight = _sha256_digest(preflight_sha256, "preflight_sha256")

    if raw["lease_held_by_claimant"] is not True:
        return False
    if raw["external_send_authorized"] is not False:
        return False
    if (
        raw["claimant"] != expected_claimant
        or raw["claim_id"] != expected_claim_id
        or _rfc3339(raw["claim_started_at"], "receipt claim_started_at") != expected_started
    ):
        return False

    expected_seam = _canonical_sha256(
        {
            "schema": SCHEMA,
            "buyer_scope": expected_buyer,
            "offer_scope": expected_offer,
        }
    )
    expected_ref = f"refs/tags/outbound-lease-v1/{expected_seam}"
    if raw["seam_sha256"] != expected_seam or raw["lease_ref"] != expected_ref:
        return False
    if raw["preflight_sha256"] != expected_preflight:
        return False

    owner, repo_name = expected_repo.split("/", 1)
    quoted_ref = urllib.parse.quote(
        expected_ref.removeprefix("refs/"),
        safe="/",
    )
    ref_status, ref_body = transport(
        "GET",
        f"/repos/{owner}/{repo_name}/git/ref/{quoted_ref}",
        None,
    )
    if ref_status != 200:
        return False

    live_tag_sha = _object_sha(ref_body)
    if live_tag_sha is None or live_tag_sha != raw["tag_object_sha"]:
        return False

    tag_status, tag_body = transport(
        "GET",
        f"/repos/{owner}/{repo_name}/git/tags/{live_tag_sha}",
        None,
    )
    if tag_status != 200 or not isinstance(tag_body, Mapping):
        return False
    try:
        response_sha = _validate_sha(tag_body.get("sha"), "tag response sha")
    except LeaseError:
        return False
    if response_sha != live_tag_sha:
        return False

    metadata = _metadata_from_tag(tag_body)
    if metadata is None:
        return False
    try:
        meta_repo = _validate_repo(metadata["repo"])
        meta_buyer = _machine_token(metadata["buyer_scope"], "tag buyer_scope")
        meta_offer = _machine_token(metadata["offer_scope"], "tag offer_scope")
        meta_claimant = _display_token(metadata["claimant"], "tag claimant")
        meta_claim_id = _machine_token(metadata["claim_id"], "tag claim_id")
        meta_started = _rfc3339(metadata["claim_started_at"], "tag claim_started_at")
        meta_anchor = _validate_sha(metadata["anchor_sha"], "tag anchor_sha")
        meta_preflight = _sha256_digest(metadata["preflight_sha256"], "tag preflight_sha256")
        meta_seam = _sha256_digest(metadata["seam_sha256"], "tag seam_sha256")
    except LeaseError:
        return False

    if metadata["schema"] != SCHEMA:
        return False
    if (
        meta_repo != expected_repo
        or meta_buyer != expected_buyer
        or meta_offer != expected_offer
        or meta_claimant != expected_claimant
        or meta_claim_id != expected_claim_id
        or meta_started != expected_started
        or meta_anchor != expected_anchor
        or meta_preflight != expected_preflight
        or meta_seam != expected_seam
    ):
        return False

    recomputed_meta_seam = _canonical_sha256(
        {
            "schema": SCHEMA,
            "buyer_scope": meta_buyer,
            "offer_scope": meta_offer,
        }
    )
    if recomputed_meta_seam != meta_seam:
        return False

    expected_tag_name = (
        "outbound-claim-v1-"
        f"{expected_seam[:16]}-"
        f"{hashlib.sha256(expected_claimant.encode('ascii')).hexdigest()[:16]}"
    )
    if tag_body.get("tag") != expected_tag_name:
        return False

    obj = tag_body.get("object")
    if not isinstance(obj, Mapping):
        return False
    if obj.get("type") != "commit":
        return False
    try:
        object_sha = _validate_sha(obj.get("sha"), "tag object target sha")
    except LeaseError:
        return False
    if object_sha != expected_anchor:
        return False

    tagger = tag_body.get("tagger")
    if not isinstance(tagger, Mapping):
        return False
    if tagger.get("name") != "outbound-send-lease":
        return False
    if tagger.get("email") != "lease@tokenjunkielabs.invalid":
        return False
    try:
        tagger_date = _rfc3339(tagger.get("date"), "tagger date")
    except LeaseError:
        return False
    if tagger_date != expected_started:
        return False

    return True
