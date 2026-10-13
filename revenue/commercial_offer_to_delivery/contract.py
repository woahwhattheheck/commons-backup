from __future__ import annotations

import copy
from datetime import datetime
from typing import Any, Callable, Mapping

from .primitives import BridgeError, digest, exact, fail, identifier, secret, sha, text, timestamp

ContractVerifier = Callable[[Mapping[str, Any], bytes], Mapping[str, Any]]


def default_contract_verifier(contract: Mapping[str, Any], owner_secret: bytes) -> Mapping[str, Any]:
    try:
        from revenue.commercial_offer_contract.offer_contract import verify_send_authority
    except Exception as exc:  # pragma: no cover
        raise BridgeError("commercial offer verifier is unavailable") from exc
    try:
        return verify_send_authority(contract, owner_secret)
    except Exception as exc:
        raise BridgeError(f"commercial offer verification failed: {exc}") from exc


def contract_snapshot(
    contract: Mapping[str, Any], owner_secret: bytes, trusted_now: str,
    contract_verifier: ContractVerifier | None,
) -> tuple[dict[str, Any], str, datetime]:
    secret(owner_secret, "owner_secret")
    _, now_dt = timestamp(trusted_now, "trusted_now")
    verifier = contract_verifier or default_contract_verifier
    try:
        verified = copy.deepcopy(dict(verifier(contract, owner_secret)))
    except BridgeError:
        raise
    except Exception as exc:
        raise BridgeError(f"commercial offer verification failed: {exc}") from exc

    exact(verified, {
        "kind", "schema_version", "state", "offer", "offer_sha256", "owner_approval",
        "send_authority", "buyer_acceptance", "authority",
    }, "contract")
    if verified["kind"] != "commercial_offer_contract" or verified["schema_version"] != 1:
        fail("unsupported commercial offer contract")
    if verified["state"] != "BUYER_ACCEPTANCE_EVIDENCE_CAPTURED":
        fail("contract must be BUYER_ACCEPTANCE_EVIDENCE_CAPTURED")

    offer = exact(verified["offer"], {
        "schema_version", "offer_id", "opportunity_id", "buyer_ref", "created_at", "valid_until",
        "currency", "total_amount_minor", "deliverables", "milestones", "assumptions", "exclusions",
    }, "contract.offer")
    if offer["schema_version"] != 1:
        fail("unsupported offer schema")
    identifier(offer["offer_id"], "offer.offer_id")
    identifier(offer["opportunity_id"], "offer.opportunity_id")
    buyer_ref = identifier(offer["buyer_ref"], "offer.buyer_ref")
    timestamp(offer["created_at"], "offer.created_at")
    _, valid_until_dt = timestamp(offer["valid_until"], "offer.valid_until")
    if offer["currency"] != "USD":
        fail("v1 bridge supports only USD offers")
    if type(offer["total_amount_minor"]) is not int:
        fail("offer.total_amount_minor must be an exact integer")
    if not 0 <= offer["total_amount_minor"] <= 10**15:
        fail("offer.total_amount_minor is out of range")
    if type(offer["exclusions"]) is not list or not offer["exclusions"]:
        fail("accepted offer must contain explicit exclusions for scope-to-delivery compatibility")
    for i, item in enumerate(offer["exclusions"]):
        text(item, f"offer.exclusions[{i}]")
    if type(offer["deliverables"]) is not list or not offer["deliverables"]:
        fail("accepted offer requires deliverables")

    sha(verified["offer_sha256"], "contract.offer_sha256")
    acceptance = exact(verified["buyer_acceptance"], {
        "offer_sha256", "buyer_ref", "accepted_at", "evidence_sha256", "identity_verification_sha256",
    }, "contract.buyer_acceptance")
    if sha(acceptance["offer_sha256"], "buyer_acceptance.offer_sha256") != verified["offer_sha256"]:
        fail("buyer acceptance is bound to a different offer")
    if identifier(acceptance["buyer_ref"], "buyer_acceptance.buyer_ref") != buyer_ref:
        fail("buyer acceptance buyer_ref mismatch")
    _, accepted_dt = timestamp(acceptance["accepted_at"], "buyer_acceptance.accepted_at")
    sha(acceptance["evidence_sha256"], "buyer_acceptance.evidence_sha256")
    sha(acceptance["identity_verification_sha256"], "buyer_acceptance.identity_verification_sha256")
    send = exact(verified["send_authority"], {
        "offer_sha256", "owner_approval_hmac", "destination_sha256", "channel", "authorized_at", "hmac_sha256",
    }, "contract.send_authority")
    _, authorized_dt = timestamp(send["authorized_at"], "send_authority.authorized_at")
    if accepted_dt < authorized_dt or accepted_dt > valid_until_dt or accepted_dt > now_dt:
        fail("buyer acceptance time is outside authorized bounds")

    authority = exact(verified["authority"], {
        "external_send_authorized", "buyer_acceptance_verified", "fulfillment_authorized",
        "payment_collected", "revenue_recognized",
    }, "contract.authority")
    if any(type(value) is not bool for value in authority.values()):
        fail("contract authority values must be boolean")
    if authority != {
        "external_send_authorized": True,
        "buyer_acceptance_verified": False,
        "fulfillment_authorized": False,
        "payment_collected": False,
        "revenue_recognized": False,
    }:
        fail("captured contract contains unexpected authority escalation")
    return verified, digest(verified), now_dt
