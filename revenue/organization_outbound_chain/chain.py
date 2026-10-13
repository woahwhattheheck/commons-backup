"""Mandatory organization-aware composition for initial outbound provider calls.

This module is the provider-bound conjunction required by Commons #14269. It does
not mint outreach authority. It composes already-landed current organization
pressure, the exact organization-wide lease generation plus holder secret,
commercial-opportunity custody and the action-specific initial-outreach slot, then
allows one exact typed provider boundary only through outbound_send_consumer.consume_once.

No prerequisite receipt can represent a completed send. The returned chain receipt
keeps external_send_authorized false; only the terminal consumer's retained outcome
may establish whether the winning invocation completed a provider send.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Protocol

from revenue import initial_outreach_slot as initial_slot
from revenue.commercial_opportunity_custody import custody as coc
from revenue.organization_contact_pressure import READY, verify_receipt_current
from revenue.organization_outbound_lease import (
    canonical_json as lease_canonical_json,
    finalize_lease,
    holder_capability_commitment,
    verify_lease_document,
)
from revenue.outbound_send_consumer import consume_once
from tools.outbound_send_guard import capability_lease as lower_lease

from .provider_boundary import (
    ProviderBoundary,
    ProviderBoundaryError,
    invoke_provider_boundary,
    provider_name as boundary_provider_name,
)

SCHEMA = "commons.organization-outbound-chain/v1"
PROVIDER_REQUEST_SCHEMA = "commons.organization-outbound-provider-request/v1"
_INITIAL_EVENT_KIND = "initial"
_HEX = frozenset("0123456789abcdef")

class ChainError(ValueError):
    """Fail-closed structural/current-authority error."""


class LeaseStore(Protocol):
    def get_active(self, org_fingerprint: str): ...


GitTransport = Callable[[str, str, Mapping[str, Any] | None], tuple[int, Any]]


def _canon(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError) as exc:
        raise ChainError("value is not canonical JSON") from exc


def _sha(value: Any) -> str:
    raw = value if isinstance(value, bytes) else _canon(value)
    return hashlib.sha256(raw).hexdigest()


def _hex64(value: Any, field: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(ch not in _HEX for ch in value):
        raise ChainError(f"{field}: lower-case sha256 hex required")
    return value


def _private_bytes(value: Any, field: str, *, minimum: int = 1, maximum: int = 4096) -> bytes:
    if not isinstance(value, (bytes, bytearray)):
        raise ChainError(f"{field}: bytes required")
    raw = bytes(value)
    if not (minimum <= len(raw) <= maximum):
        raise ChainError(f"{field}: length outside retained bound")
    return raw


def _token(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.isascii() or value != value.casefold() or not (2 <= len(value) <= 96):
        raise ChainError(f"{field}: lower-case ASCII token required")
    allowed = frozenset("abcdefghijklmnopqrstuvwxyz0123456789._:-/@+")
    if any(ch not in allowed for ch in value):
        raise ChainError(f"{field}: unsupported token character")
    return value


def _utc_seconds() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _domain_commit(domain: bytes, organization_fingerprint: str, material: bytes) -> str:
    org = _hex64(organization_fingerprint, "organization_fingerprint")
    return hashlib.sha256(domain + bytes.fromhex(org) + b"\x00" + material).hexdigest()


def prospect_fingerprint(organization_fingerprint: str, prospect_identity: bytes) -> str:
    """Commit a host-retained canonical prospect identity for org-lease acquisition."""
    return _domain_commit(
        b"commons-org-chain-prospect-v1\x00",
        organization_fingerprint,
        _private_bytes(prospect_identity, "prospect_identity"),
    )


def route_commitment(organization_fingerprint: str, route_identity: bytes) -> str:
    """Commit the actual provider route without exporting the route itself."""
    return _domain_commit(
        b"commons-org-chain-route-v1\x00",
        organization_fingerprint,
        _private_bytes(route_identity, "route_identity"),
    )


def opportunity_commitment(organization_fingerprint: str, buyer_scope: str, canonical_opportunity_key: str) -> str:
    buyer = _token(buyer_scope, "buyer_scope")
    key = _token(canonical_opportunity_key, "canonical_opportunity_key")
    material = buyer.encode("ascii") + b"\x00" + key.encode("ascii")
    return _domain_commit(b"commons-org-chain-opportunity-v1\x00", organization_fingerprint, material)


def _event_key(organization_fingerprint: str, opportunity_sha256: str) -> str:
    digest = hashlib.sha256(
        b"commons-org-chain-initial-event-v1\x00"
        + bytes.fromhex(_hex64(organization_fingerprint, "organization_fingerprint"))
        + bytes.fromhex(_hex64(opportunity_sha256, "opportunity_commitment"))
    ).hexdigest()
    return f"initial:{digest}"


def _pressure_current(pressure_receipt_data: bytes, lease: Mapping[str, Any]) -> dict[str, Any]:
    data = _private_bytes(pressure_receipt_data, "pressure_receipt_data", maximum=512 * 1024)
    try:
        receipt = verify_receipt_current(data)
    except Exception as exc:
        raise ChainError("current organization pressure not proven") from exc
    if type(receipt) is not dict or receipt.get("decision") != READY:
        raise ChainError("organization pressure is not READY")
    if receipt.get("external_send_authorized") is not False:
        raise ChainError("pressure receipt may not mint send authority")
    if receipt.get("receipt_sha256") != lease.get("pressureReceiptSha256"):
        raise ChainError("organization lease pressure generation mismatch")
    if receipt.get("authority_sha256") != lease.get("authorityCommitment"):
        raise ChainError("organization lease authority generation mismatch")
    if receipt.get("ledger_sha256") != lease.get("ledgerCommitment"):
        raise ChainError("organization lease ledger generation mismatch")
    return receipt


def _active_organization_lease(
    *,
    store: LeaseStore,
    lease_receipt: Mapping[str, Any],
    active_generation: str,
    holder_capability: bytes,
) -> tuple[dict[str, Any], bytes]:
    if type(lease_receipt) is not dict:
        raise ChainError("organization lease receipt must be exact object")
    try:
        lease = verify_lease_document(lease_receipt)
    except Exception as exc:
        raise ChainError("organization lease receipt invalid") from exc
    capability = _private_bytes(holder_capability, "organization_holder_capability", minimum=32, maximum=32)
    if holder_capability_commitment(capability) != lease["holderCapabilityCommitment"]:
        raise ChainError("organization lease private holder capability mismatch")
    active = store.get_active(lease["organizationFingerprint"])
    if active is None or type(active) is not tuple or len(active) != 2:
        raise ChainError("organization lease is not active")
    raw, generation = active
    if not isinstance(raw, bytes) or not isinstance(generation, str):
        raise ChainError("organization lease store returned invalid active generation")
    expected_raw = lease_canonical_json(lease)
    if not hmac.compare_digest(raw, expected_raw):
        raise ChainError("active organization lease bytes differ from winner receipt")
    if not hmac.compare_digest(generation, active_generation):
        raise ChainError("active organization lease generation moved")
    return lease, raw


def _identity_and_key(opportunity_raw: Mapping[str, Any], *, transport: GitTransport) -> tuple[Any, str]:
    try:
        identity = coc.Identity.parse(dict(opportunity_raw))
    except Exception as exc:
        raise ChainError("commercial opportunity identity invalid") from exc
    try:
        inspection = initial_slot.inspect_initial_outreach(opportunity_raw, transport=transport)
    except Exception as exc:
        raise ChainError("canonical opportunity key unavailable") from exc
    if type(inspection) is not dict or inspection.get("evidence_valid") is not True:
        raise ChainError("canonical opportunity inspection is not valid")
    key = inspection.get("canonical_opportunity_key")
    _token(key, "canonical_opportunity_key")
    return identity, key


def _lower_authority_current(
    *,
    opportunity_raw: Mapping[str, Any],
    identity: Any,
    canonical_key: str,
    actor_owner: str,
    actor_operation: str,
    lease_receipt: Mapping[str, Any],
    claim_capability: str,
    transport: GitTransport,
) -> dict[str, Any]:
    try:
        inspection = initial_slot.inspect_initial_outreach(opportunity_raw, transport=transport)
        if type(inspection) is not dict or inspection.get("decision") != "CONSUMED":
            raise ChainError("action-specific initial slot is not consumed")
        if inspection.get("slot_consumed") is not True or inspection.get("evidence_valid") is not True:
            raise ChainError("action-specific initial slot evidence invalid")
        if inspection.get("canonical_opportunity_key") != canonical_key:
            raise ChainError("canonical opportunity generation moved")
        if inspection.get("external_send_authorized") is not False:
            raise ChainError("initial slot may not mint durable send authority")

        lower_lease.verify_receipt(lease_receipt)
        if lease_receipt.get("repo", "").casefold() != identity.repo:
            raise ChainError("lower lease repository mismatch")
        if lease_receipt.get("buyer_scope") != identity.buyer_scope:
            raise ChainError("lower lease buyer mismatch")
        if lease_receipt.get("claimant") != actor_owner:
            raise ChainError("lower lease claimant mismatch")
        if not lower_lease.verify_possession(
            lease_receipt,
            claim_capability=claim_capability,
            transport=transport,
        ):
            raise ChainError("lower lease private possession not current")

        custody = coc.authorize_internal_work(
            identity.document,
            actor_owner=actor_owner,
            actor_operation=actor_operation,
            lane="outreach",
            transport=transport,
        )
    except ChainError:
        raise
    except Exception as exc:
        raise ChainError("lower action-specific authority not current") from exc

    required = {
        "schema": "commercial-opportunity-custody-work-check/v1",
        "seam_sha256": identity.seam_sha256,
        "actor_owner": actor_owner,
        "actor_operation": actor_operation,
        "lane": "outreach",
        "internal_work_authorized": True,
        "external_send_authorized": False,
        "proposal_submission_authorized": False,
        "payment_or_revenue_inferred": False,
    }
    if any(custody.get(k) != v for k, v in required.items()):
        raise ChainError("commercial opportunity custody is not current")
    if custody.get("basis") not in {"WHOLE", "DELEGATE:outreach"}:
        raise ChainError("commercial opportunity custody basis invalid")
    if type(custody.get("generation")) is not int or isinstance(custody.get("generation"), bool) or custody["generation"] < 1:
        raise ChainError("commercial opportunity custody generation invalid")

    material = {
        "canonical_opportunity_key": canonical_key,
        "slot_ref": inspection.get("slot_ref"),
        "slot_tag_sha": inspection.get("slot_tag_sha"),
        "slot_metadata_sha256": inspection.get("metadata_sha256"),
        "lower_lease_ref": lease_receipt.get("lease_ref"),
        "lower_lease_tag_object_sha": lease_receipt.get("tag_object_sha"),
        "lower_lease_claim_capability_sha256": lease_receipt.get("claim_capability_sha256"),
        "lower_lease_preflight_sha256": lease_receipt.get("preflight_sha256"),
        "lower_lease_claim_id": lease_receipt.get("claim_id"),
        "custody_generation": custody.get("generation"),
        "custody_history_sha256": custody.get("history_sha256"),
        "custody_check_sha256": custody.get("check_sha256"),
        "custody_basis": custody.get("basis"),
        "anchor_sha": lease_receipt.get("anchor_sha"),
    }
    _canon(material)
    return material


def _composite_authority_digest(
    *,
    pressure: Mapping[str, Any],
    organization_lease: Mapping[str, Any],
    active_generation: str,
    lower: Mapping[str, Any],
) -> str:
    return _sha({
        "schema": "commons.organization-outbound-chain-authority/v1",
        "pressure_receipt_sha256": pressure["receipt_sha256"],
        "pressure_authority_sha256": pressure["authority_sha256"],
        "pressure_ledger_sha256": pressure["ledger_sha256"],
        "organization_lease_id": organization_lease["leaseId"],
        "organization_lease_nonce": organization_lease["leaseNonce"],
        "organization_lease_sha256": organization_lease["leaseSha256"],
        "organization_active_generation": active_generation,
        "lower_authority": dict(lower),
    })


def _terminal_outcome(consumer_receipt: Mapping[str, Any] | None, callback_failed: bool) -> str:
    if callback_failed:
        return "OUTCOME_UNKNOWN"
    if type(consumer_receipt) is not dict:
        return "HELD_AUTHORITY"
    state = consumer_receipt.get("terminal_state")
    decision = consumer_receipt.get("decision")
    if state == "SENT" and decision in {"SENT", "SUPPRESSED"}:
        return "SENT" if decision == "SENT" else "HELD_AUTHORITY"
    if state in {"REJECTED", "OUTCOME_UNKNOWN", "HELD_AUTHORITY"}:
        return state
    if decision == "RECONCILE_REQUIRED":
        return "OUTCOME_UNKNOWN"
    return "HELD_AUTHORITY"


def _finalize_organization_lease(
    *,
    store: LeaseStore,
    lease: Mapping[str, Any],
    holder_capability: bytes,
    outcome: str,
    evidence: Mapping[str, Any],
) -> dict[str, Any]:
    evidence_commitment = _sha(evidence)
    request = {
        "schema": "commons.organization-outbound-finalize/v2",
        "organizationFingerprint": lease["organizationFingerprint"],
        "leaseId": lease["leaseId"],
        "leaseNonce": lease["leaseNonce"],
        "claimId": lease["claimId"],
        "outcomeId": f"chain-{evidence_commitment[:40]}",
        "outcome": outcome,
        "observedAt": _utc_seconds(),
        "evidenceCommitment": evidence_commitment,
        "holderCapability": bytes(holder_capability).hex(),
    }
    result = finalize_lease(store, request)
    return {
        "state": result.state,
        "outcome_sha256": result.outcome["outcomeSha256"],
        "outcome_generation": result.outcome_generation,
        "active_released": result.active_released,
        "replay": result.replay,
    }


def _execute_guarded_initial_outreach_impl(
    opportunity_raw: Mapping[str, Any],
    *,
    actor_owner: str,
    actor_operation: str,
    lower_lease_receipt: Mapping[str, Any],
    lower_claim_capability: str,
    git_transport: GitTransport,
    pressure_receipt_data: bytes,
    organization_lease_store: LeaseStore,
    organization_lease_receipt: Mapping[str, Any],
    organization_lease_generation: str,
    organization_holder_capability: bytes,
    prospect_identity: bytes,
    route_identity: bytes,
    provider_boundary: ProviderBoundary,
    provider_request_bytes: bytes,
    _boundary_provider_name: Callable[[ProviderBoundary], str],
    _invoke_provider_boundary: Callable[..., Any],
    _provider_boundary_error: type[BaseException],
) -> dict[str, Any]:
    """Execute one initial provider mutation through the full mandatory chain.

    ``prospect_identity``, ``route_identity`` and ``provider_request_bytes`` are
    host-derived private bytes. They are commitment inputs only and never appear in
    the returned receipt. The organization lease must have been acquired with the
    commitment helpers exported by this module.
    """
    try:
        provider_name = _boundary_provider_name(provider_boundary)
    except _provider_boundary_error as exc:
        raise ChainError("exact registered provider boundary required") from exc
    request_bytes = _private_bytes(provider_request_bytes, "provider_request_bytes", maximum=2 * 1024 * 1024)

    organization_lease, _ = _active_organization_lease(
        store=organization_lease_store,
        lease_receipt=organization_lease_receipt,
        active_generation=organization_lease_generation,
        holder_capability=organization_holder_capability,
    )
    pressure = _pressure_current(pressure_receipt_data, organization_lease)
    identity, canonical_key = _identity_and_key(opportunity_raw, transport=git_transport)

    org = organization_lease["organizationFingerprint"]
    expected_prospect = prospect_fingerprint(org, prospect_identity)
    expected_route = route_commitment(org, route_identity)
    expected_opportunity = opportunity_commitment(org, identity.buyer_scope, canonical_key)
    if organization_lease["prospectFingerprint"] != expected_prospect:
        raise ChainError("organization lease prospect binding mismatch")
    if organization_lease["routeCommitment"] != expected_route:
        raise ChainError("organization lease route binding mismatch")
    if organization_lease["opportunityCommitment"] != expected_opportunity:
        raise ChainError("organization lease opportunity binding mismatch")

    provider_request_sha256 = hashlib.sha256(request_bytes).hexdigest()
    lower_anchor = lower_lease_receipt.get("anchor_sha")
    if not isinstance(lower_anchor, str):
        raise ChainError("lower lease anchor missing")

    consumer_receipt: dict[str, Any] | None = None
    consumer_failure = False
    finalization: dict[str, Any] | None = None

    def authority_probe() -> str | None:
        try:
            lease_now, _ = _active_organization_lease(
                store=organization_lease_store,
                lease_receipt=organization_lease_receipt,
                active_generation=organization_lease_generation,
                holder_capability=organization_holder_capability,
            )
            pressure_now = _pressure_current(pressure_receipt_data, lease_now)
            lower_now = _lower_authority_current(
                opportunity_raw=opportunity_raw,
                identity=identity,
                canonical_key=canonical_key,
                actor_owner=actor_owner,
                actor_operation=actor_operation,
                lease_receipt=lower_lease_receipt,
                claim_capability=lower_claim_capability,
                transport=git_transport,
            )
            if lower_now.get("anchor_sha") != lower_anchor:
                return None
            return _composite_authority_digest(
                pressure=pressure_now,
                organization_lease=lease_now,
                active_generation=organization_lease_generation,
                lower=lower_now,
            )
        except Exception:
            return None

    def composed_send_once() -> None:
        nonlocal consumer_receipt, consumer_failure
        lower_now = _lower_authority_current(
            opportunity_raw=opportunity_raw,
            identity=identity,
            canonical_key=canonical_key,
            actor_owner=actor_owner,
            actor_operation=actor_operation,
            lease_receipt=lower_lease_receipt,
            claim_capability=lower_claim_capability,
            transport=git_transport,
        )
        authority_sha256 = _composite_authority_digest(
            pressure=pressure,
            organization_lease=organization_lease,
            active_generation=organization_lease_generation,
            lower=lower_now,
        )
        host = {
            "repo": identity.repo,
            "buyer_scope": org,
            "opportunity_scope": expected_opportunity,
            "event_kind": _INITIAL_EVENT_KIND,
            "event_key": _event_key(org, expected_opportunity),
            "provider_request_sha256": provider_request_sha256,
            "authority_sha256": authority_sha256,
            "anchor_sha": lower_anchor,
        }
        intent = {
            "repo": identity.repo,
            "buyer_scope": org,
            "opportunity_scope": expected_opportunity,
            "event_kind": _INITIAL_EVENT_KIND,
            "event_key": host["event_key"],
            "provider_request_sha256": provider_request_sha256,
            "anchor_sha": lower_anchor,
            "claimant": actor_owner,
        }

        def terminal_provider(idempotency_key: str) -> Any:
            return _invoke_provider_boundary(
                provider_boundary,
                idempotency_key=idempotency_key,
                request_bytes=request_bytes,
            )

        try:
            consumer_receipt = consume_once(
                intent,
                host_raw=host,
                transport=git_transport,
                authority_probe=authority_probe,
                provider_callback=terminal_provider,
            )
        except BaseException:
            consumer_failure = True
            raise

    initial_receipt = initial_slot.execute_initial_outreach(
        opportunity_raw,
        actor_owner=actor_owner,
        actor_operation=actor_operation,
        lease_receipt=lower_lease_receipt,
        claim_capability=lower_claim_capability,
        transport=git_transport,
        send_once=composed_send_once,
    )

    callback_invoked = bool(initial_receipt.get("provider_callback_invoked")) if isinstance(initial_receipt, Mapping) else False
    if callback_invoked:
        terminal = _terminal_outcome(consumer_receipt, consumer_failure)
        evidence = {
            "schema": "commons.organization-outbound-chain-evidence/v1",
            "provider": provider_name,
            "organization_fingerprint": org,
            "organization_lease_sha256": organization_lease["leaseSha256"],
            "organization_active_generation": organization_lease_generation,
            "pressure_receipt_sha256": pressure["receipt_sha256"],
            "initial_slot_receipt_sha256": initial_receipt.get("receipt_sha256"),
            "consumer_receipt_sha256": None if consumer_receipt is None else consumer_receipt.get("receipt_sha256"),
            "consumer_failure": consumer_failure,
            "provider_request_sha256": provider_request_sha256,
            "terminal_outcome": terminal,
        }
        try:
            finalization = _finalize_organization_lease(
                store=organization_lease_store,
                lease=organization_lease,
                holder_capability=organization_holder_capability,
                outcome=terminal,
                evidence=evidence,
            )
        except Exception:
            finalization = None

    external_completed = bool(consumer_receipt.get("external_send_completed")) if isinstance(consumer_receipt, Mapping) else False
    prior_send_observed = bool(consumer_receipt.get("prior_send_observed")) if isinstance(consumer_receipt, Mapping) else False
    if not callback_invoked:
        decision = "HOLD_ACTION_SPECIFIC_AUTHORITY"
    elif consumer_failure or finalization is None:
        decision = "RECONCILE_REQUIRED"
    elif consumer_receipt is None:
        decision = "RECONCILE_REQUIRED"
    else:
        decision = str(consumer_receipt.get("decision"))

    result: dict[str, Any] = {
        "schema": SCHEMA,
        "provider": provider_name,
        "decision": decision,
        "organization_fingerprint": org,
        "organization_lease_id": organization_lease["leaseId"],
        "organization_lease_nonce": organization_lease["leaseNonce"],
        "organization_lease_sha256": organization_lease["leaseSha256"],
        "organization_active_generation": organization_lease_generation,
        "pressure_receipt_sha256": pressure["receipt_sha256"],
        "canonical_opportunity_key_sha256": hashlib.sha256(canonical_key.encode("ascii")).hexdigest(),
        "opportunity_commitment": expected_opportunity,
        "provider_request_sha256": provider_request_sha256,
        "initial_slot_receipt_sha256": initial_receipt.get("receipt_sha256") if isinstance(initial_receipt, Mapping) else None,
        "terminal_consumer_receipt_sha256": consumer_receipt.get("receipt_sha256") if isinstance(consumer_receipt, Mapping) else None,
        "terminal_state": consumer_receipt.get("terminal_state") if isinstance(consumer_receipt, Mapping) else ("OUTCOME_UNKNOWN" if consumer_failure else None),
        "organization_outcome_sha256": None if finalization is None else finalization["outcome_sha256"],
        "external_send_authorized": False,
        "external_send_completed": external_completed,
        "prior_send_observed": prior_send_observed,
        "replay_or_retry_authorized": False,
        "payment_or_revenue_inferred": False,
        "raw_capability_exported": False,
    }
    result["receipt_sha256"] = _sha(result)
    return result


def _build_first_load_entrypoint(
    _impl=_execute_guarded_initial_outreach_impl,
    _provider_name_fn=boundary_provider_name,
    _invoke_provider_fn=invoke_provider_boundary,
    _provider_error=ProviderBoundaryError,
):
    """Seal the production provider boundary generation at first module load."""

    def execute_guarded_initial_outreach(
        opportunity_raw: Mapping[str, Any],
        *,
        actor_owner: str,
        actor_operation: str,
        lower_lease_receipt: Mapping[str, Any],
        lower_claim_capability: str,
        git_transport: GitTransport,
        pressure_receipt_data: bytes,
        organization_lease_store: LeaseStore,
        organization_lease_receipt: Mapping[str, Any],
        organization_lease_generation: str,
        organization_holder_capability: bytes,
        prospect_identity: bytes,
        route_identity: bytes,
        provider_boundary: ProviderBoundary,
        provider_request_bytes: bytes,
    ) -> dict[str, Any]:
        return _impl(
            opportunity_raw,
            actor_owner=actor_owner,
            actor_operation=actor_operation,
            lower_lease_receipt=lower_lease_receipt,
            lower_claim_capability=lower_claim_capability,
            git_transport=git_transport,
            pressure_receipt_data=pressure_receipt_data,
            organization_lease_store=organization_lease_store,
            organization_lease_receipt=organization_lease_receipt,
            organization_lease_generation=organization_lease_generation,
            organization_holder_capability=organization_holder_capability,
            prospect_identity=prospect_identity,
            route_identity=route_identity,
            provider_boundary=provider_boundary,
            provider_request_bytes=provider_request_bytes,
            _boundary_provider_name=_provider_name_fn,
            _invoke_provider_boundary=_invoke_provider_fn,
            _provider_boundary_error=_provider_error,
        )

    return execute_guarded_initial_outreach


execute_guarded_initial_outreach = _build_first_load_entrypoint()
del _build_first_load_entrypoint
