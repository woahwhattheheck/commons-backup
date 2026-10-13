from __future__ import annotations

import copy
import hmac
from datetime import datetime
from typing import Any, Mapping

from .contract import ContractVerifier, contract_snapshot
from .primitives import (
    SCHEMA_VERSION, VERIFICATION_ATTESTATION, VERIFICATION_DECISION, VERIFICATION_KIND,
    exact, fail, hmac_sha256, identifier, public_ref as validate_public_ref, secret, sha, timestamp,
)
from .terms import build_scope_terms, normalize_service_window, terms_digest


def normalize_scope_terms_acceptance(
    value: Mapping[str, Any], where: str = "scope_terms_acceptance",
) -> tuple[dict[str, Any], datetime]:
    value = exact(value, {
        "terms_digest", "accepted_at", "evidence_sha256", "identity_verification_sha256",
    }, where)
    accepted_at, accepted_dt = timestamp(value["accepted_at"], f"{where}.accepted_at")
    return {
        "terms_digest": sha(value["terms_digest"], f"{where}.terms_digest"),
        "accepted_at": accepted_at,
        "evidence_sha256": sha(value["evidence_sha256"], f"{where}.evidence_sha256"),
        "identity_verification_sha256": sha(
            value["identity_verification_sha256"], f"{where}.identity_verification_sha256"
        ),
    }, accepted_dt


def create_operator_verification(
    contract: Mapping[str, Any], owner_secret: bytes, verification_secret: bytes, *,
    verifier_id: str, key_id: str, verified_at: str, public_ref: str,
    catalog: Mapping[str, Any], service_window: Mapping[str, Any],
    scope_terms_acceptance: Mapping[str, Any], trusted_now: str,
    contract_verifier: ContractVerifier | None = None,
) -> dict[str, Any]:
    verified, contract_sha, now_dt = contract_snapshot(contract, owner_secret, trusted_now, contract_verifier)
    secret(verification_secret, "verification_secret")
    verified_at, verified_dt = timestamp(verified_at, "verified_at")
    window, service_start_dt = normalize_service_window(service_window)
    scope_terms = build_scope_terms(verified, catalog, window)
    expected_terms_digest = terms_digest(scope_terms)
    acceptance, scope_accepted_dt = normalize_scope_terms_acceptance(scope_terms_acceptance)
    if acceptance["terms_digest"] != expected_terms_digest:
        fail("buyer scope-terms acceptance is bound to different exact terms")
    _, offer_accepted_dt = timestamp(verified["buyer_acceptance"]["accepted_at"], "buyer_acceptance.accepted_at")
    if scope_accepted_dt < offer_accepted_dt:
        fail("scope terms acceptance cannot predate offer acceptance")
    if service_start_dt < scope_accepted_dt:
        fail("service cannot start before exact scope terms acceptance")
    if verified_dt < scope_accepted_dt:
        fail("operator verification cannot predate exact scope terms acceptance")
    if verified_dt > now_dt or scope_accepted_dt > now_dt:
        fail("verification evidence is future relative to trusted_now")
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": VERIFICATION_KIND,
        "decision": VERIFICATION_DECISION,
        "attestation": VERIFICATION_ATTESTATION,
        "verifier_id": identifier(verifier_id, "verifier_id"),
        "key_id": identifier(key_id, "key_id"),
        "verified_at": verified_at,
        "public_ref": public_ref and validate_public_ref(public_ref, "public_ref"),
        "contract_sha256": contract_sha,
        "offer_sha256": verified["offer_sha256"],
        "buyer_ref": verified["offer"]["buyer_ref"],
        "offer_acceptance_evidence_sha256": verified["buyer_acceptance"]["evidence_sha256"],
        "offer_identity_verification_sha256": verified["buyer_acceptance"]["identity_verification_sha256"],
        "service_window": window,
        "scope_terms_acceptance": acceptance,
    }
    return {
        **payload,
        "hmac_sha256": hmac_sha256(
            verification_secret, "commercial-offer-scope-acceptance-verification-v2", payload
        ),
    }


def verify_operator_verification(
    contract: Mapping[str, Any], receipt: Mapping[str, Any], owner_secret: bytes,
    verification_secret: bytes, *, catalog: Mapping[str, Any], trusted_now: str,
    contract_verifier: ContractVerifier | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    verified, contract_sha, now_dt = contract_snapshot(contract, owner_secret, trusted_now, contract_verifier)
    secret(verification_secret, "verification_secret")
    receipt = exact(receipt, {
        "schema_version", "kind", "decision", "attestation", "verifier_id", "key_id", "verified_at",
        "public_ref", "contract_sha256", "offer_sha256", "buyer_ref", "offer_acceptance_evidence_sha256",
        "offer_identity_verification_sha256", "service_window", "scope_terms_acceptance", "hmac_sha256",
    }, "operator_verification")
    if receipt["schema_version"] != SCHEMA_VERSION or receipt["kind"] != VERIFICATION_KIND:
        fail("unsupported operator verification receipt")
    if receipt["decision"] != VERIFICATION_DECISION or receipt["attestation"] != VERIFICATION_ATTESTATION:
        fail("operator verification does not assert the required decision/attestation")
    verified_at, verified_dt = timestamp(receipt["verified_at"], "operator_verification.verified_at")
    window, service_start_dt = normalize_service_window(receipt["service_window"], "operator_verification.service_window")
    scope_terms = build_scope_terms(verified, catalog, window)
    expected_terms_digest = terms_digest(scope_terms)
    acceptance, scope_accepted_dt = normalize_scope_terms_acceptance(
        receipt["scope_terms_acceptance"], "operator_verification.scope_terms_acceptance"
    )
    if acceptance["terms_digest"] != expected_terms_digest:
        fail("operator verification scope terms digest mismatch")
    _, offer_accepted_dt = timestamp(verified["buyer_acceptance"]["accepted_at"], "buyer_acceptance.accepted_at")
    if (
        scope_accepted_dt < offer_accepted_dt
        or service_start_dt < scope_accepted_dt
        or verified_dt < scope_accepted_dt
        or verified_dt > now_dt
    ):
        fail("operator verification time is outside allowed bounds")
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": VERIFICATION_KIND,
        "decision": VERIFICATION_DECISION,
        "attestation": VERIFICATION_ATTESTATION,
        "verifier_id": identifier(receipt["verifier_id"], "operator_verification.verifier_id"),
        "key_id": identifier(receipt["key_id"], "operator_verification.key_id"),
        "verified_at": verified_at,
        "public_ref": validate_public_ref(receipt["public_ref"], "operator_verification.public_ref"),
        "contract_sha256": sha(receipt["contract_sha256"], "operator_verification.contract_sha256"),
        "offer_sha256": sha(receipt["offer_sha256"], "operator_verification.offer_sha256"),
        "buyer_ref": identifier(receipt["buyer_ref"], "operator_verification.buyer_ref"),
        "offer_acceptance_evidence_sha256": sha(
            receipt["offer_acceptance_evidence_sha256"],
            "operator_verification.offer_acceptance_evidence_sha256",
        ),
        "offer_identity_verification_sha256": sha(
            receipt["offer_identity_verification_sha256"],
            "operator_verification.offer_identity_verification_sha256",
        ),
        "service_window": window,
        "scope_terms_acceptance": acceptance,
    }
    expected = {
        "contract_sha256": contract_sha,
        "offer_sha256": verified["offer_sha256"],
        "buyer_ref": verified["offer"]["buyer_ref"],
        "offer_acceptance_evidence_sha256": verified["buyer_acceptance"]["evidence_sha256"],
        "offer_identity_verification_sha256": verified["buyer_acceptance"]["identity_verification_sha256"],
    }
    if any(payload[key] != value for key, value in expected.items()):
        fail("operator verification binding mismatch")
    expected_sig = hmac_sha256(
        verification_secret, "commercial-offer-scope-acceptance-verification-v2", payload
    )
    if not hmac.compare_digest(
        sha(receipt["hmac_sha256"], "operator_verification.hmac_sha256"), expected_sig
    ):
        fail("operator verification HMAC invalid")
    return verified, copy.deepcopy(dict(receipt))
