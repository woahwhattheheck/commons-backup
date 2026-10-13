from __future__ import annotations

import copy
import hashlib
from typing import Any, Callable, Mapping

from .contract import ContractVerifier
from .primitives import (
    BRIDGE_KIND, SCHEMA_VERSION, SCOPE_ACCEPTANCE_ATTESTATION, SCOPE_KIND, SCOPE_SCHEMA,
    BridgeError, canonical, digest, exact, fail, load_json_strict, sha,
)
from .terms import build_scope_terms, scope_buyer_ref, terms_digest
from .verification import create_operator_verification, verify_operator_verification

AgreementValidator = Callable[[Mapping[str, Any], Mapping[str, Any]], Mapping[str, Any]]


def default_agreement_validator(agreement: Mapping[str, Any], catalog: Mapping[str, Any]) -> Mapping[str, Any]:
    try:
        from host.scope_to_delivery import validate_agreement
    except Exception as exc:  # pragma: no cover
        raise BridgeError("scope-to-delivery validator is unavailable") from exc
    try:
        return validate_agreement(copy.deepcopy(dict(agreement)), copy.deepcopy(dict(catalog)))
    except Exception as exc:
        raise BridgeError(f"scope-to-delivery compatibility failed: {exc}") from exc


def build_scope_bridge(
    contract: Mapping[str, Any], operator_verification: Mapping[str, Any], owner_secret: bytes,
    verification_secret: bytes, *, catalog: Mapping[str, Any], trusted_now: str,
    contract_verifier: ContractVerifier | None = None,
    agreement_validator: AgreementValidator | None = None,
) -> dict[str, Any]:
    verified, receipt = verify_operator_verification(
        contract, operator_verification, owner_secret, verification_secret,
        catalog=catalog, trusted_now=trusted_now, contract_verifier=contract_verifier,
    )
    offer = verified["offer"]
    scope_terms = build_scope_terms(verified, catalog, receipt["service_window"])
    accepted_terms_digest = receipt["scope_terms_acceptance"]["terms_digest"]
    if terms_digest(scope_terms) != accepted_terms_digest:
        fail("derived scope terms do not equal buyer-accepted exact terms")

    agreement: dict[str, Any] = {
        "schema_version": SCOPE_SCHEMA,
        "kind": SCOPE_KIND,
        "agreement_id": "offer_" + verified["offer_sha256"][:32],
        **copy.deepcopy(scope_terms),
        "written_acceptance": {
            "status": "PRESENT",
            "attestation": SCOPE_ACCEPTANCE_ATTESTATION,
            "terms_digest": accepted_terms_digest,
            "public_ref": receipt["public_ref"],
            "accepted_at": receipt["scope_terms_acceptance"]["accepted_at"],
        },
        "buyer_ref": scope_buyer_ref(offer["buyer_ref"]),
    }
    validator = agreement_validator or default_agreement_validator
    try:
        validated = validator(copy.deepcopy(agreement), copy.deepcopy(dict(catalog)))
    except BridgeError:
        raise
    except Exception as exc:
        raise BridgeError(f"scope-to-delivery compatibility failed: {exc}") from exc
    if canonical(validated) != canonical(agreement):
        fail("scope-to-delivery validator altered the derived agreement")

    bridge_core = {
        "schema_version": SCHEMA_VERSION,
        "kind": BRIDGE_KIND,
        "state": "SCOPE_AGREEMENT_READY",
        "contract_sha256": digest(verified),
        "operator_verification_sha256": digest(receipt),
        "offer_sha256": verified["offer_sha256"],
        "scope_terms_sha256": accepted_terms_digest,
        "source_buyer_ref_sha256": hashlib.sha256(offer["buyer_ref"].encode()).hexdigest(),
        "agreement_sha256": digest(agreement),
        "agreement_id": agreement["agreement_id"],
        "sku_id": scope_terms["sku_id"],
        "service_window": copy.deepcopy(scope_terms["window"]),
        "authority": {
            "scope_agreement_ready": True,
            "external_send_performed": False,
            "fulfillment_performed": False,
            "payment_collected": False,
            "revenue_recognized": False,
        },
    }
    return {
        "agreement": agreement,
        "operator_verification": receipt,
        "bridge_receipt": {**bridge_core, "bridge_sha256": digest(bridge_core)},
    }


def verify_scope_bridge(
    bundle: Mapping[str, Any], contract: Mapping[str, Any], owner_secret: bytes,
    verification_secret: bytes, *, catalog: Mapping[str, Any], trusted_now: str,
    contract_verifier: ContractVerifier | None = None,
    agreement_validator: AgreementValidator | None = None,
) -> dict[str, Any]:
    bundle = exact(bundle, {"agreement", "operator_verification", "bridge_receipt"}, "bundle")
    receipt = exact(bundle["bridge_receipt"], {
        "schema_version", "kind", "state", "contract_sha256", "operator_verification_sha256",
        "offer_sha256", "scope_terms_sha256", "source_buyer_ref_sha256", "agreement_sha256",
        "agreement_id", "sku_id", "service_window", "authority", "bridge_sha256",
    }, "bridge_receipt")
    if (
        receipt["schema_version"] != SCHEMA_VERSION
        or receipt["kind"] != BRIDGE_KIND
        or receipt["state"] != "SCOPE_AGREEMENT_READY"
    ):
        fail("unsupported bridge receipt")
    core = {key: value for key, value in receipt.items() if key != "bridge_sha256"}
    if sha(receipt["bridge_sha256"], "bridge_receipt.bridge_sha256") != digest(core):
        fail("bridge_sha256 mismatch")
    if sha(receipt["scope_terms_sha256"], "bridge_receipt.scope_terms_sha256") != bundle["agreement"]["written_acceptance"]["terms_digest"]:
        fail("bridge scope terms digest mismatch")
    expected_authority = {
        "scope_agreement_ready": True,
        "external_send_performed": False,
        "fulfillment_performed": False,
        "payment_collected": False,
        "revenue_recognized": False,
    }
    if exact(receipt["authority"], set(expected_authority), "bridge_receipt.authority") != expected_authority:
        fail("bridge receipt contains authority escalation")
    rebuilt = build_scope_bridge(
        contract, bundle["operator_verification"], owner_secret, verification_secret,
        catalog=catalog, trusted_now=trusted_now, contract_verifier=contract_verifier,
        agreement_validator=agreement_validator,
    )
    if canonical(rebuilt) != canonical(bundle):
        fail("bridge bundle does not round-trip to canonical bytes")
    return copy.deepcopy(dict(bundle))
