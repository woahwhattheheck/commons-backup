"""One-shot initial outreach at the provider-mutation boundary.

The terminal exclusion key is an independently retained canonical opportunity
key resolved from the repository-carried alias registry, not caller-authored
opportunity_id / authority_scope aliases or a caller-supplied key.  A winner
must hold current outreach custody and prove possession of the private v2 lease
capability.  The winner then consumes one immutable Git ref *before* one
synchronous send_once callback is invoked.  This module guarantees one
callback invocation, not one unconstrained provider mutation.  No reusable
send-authority receipt is ever emitted; all durable/result evidence keeps
external_send_authorized false.  Callback return is discarded without
repr/str/serialization.  If the callback errors or the process dies after ref
creation, the slot stays consumed and the route is reconciliation-only.

Original product/source: Z-PascalEstuary-2210-S4Q8 (ZPE-S4Q8).  Recovery
closes ZMK-Q9V4 and ZHBW-R7C4.  It consumes landed
revenue.opportunity_identity_alias and does not remint that registry.
"""
from __future__ import annotations

import urllib.parse
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Optional

from revenue.commercial_opportunity_custody import custody as coc
from revenue.opportunity_identity_alias import resolver as alias_v1
from revenue.opportunity_identity_alias.strict import OBSERVATION_SCHEMA
from tools.outbound_send_guard import capability_lease as lease_v2

SCHEMA = "initial-outreach-slot/v1"
RECEIPT_SCHEMA = "initial-outreach-slot-receipt/v1"
INSPECTION_SCHEMA = "initial-outreach-slot-inspection/v1"
REF_PREFIX = "refs/tags/initial-outreach-v1/"
TAGGER_NAME = "initial-outreach-slot"
TAGGER_EMAIL = "outreach-slot@tokenjunkielabs.invalid"
ACTION = "initial_outreach"
INDETERMINATE = frozenset({0, 408, 500, 502, 503, 504})

Transport = coc.Transport
SendOnce = Callable[[], Any]


class SlotError(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _opp(raw: Mapping[str, Any]) -> coc.Identity:
    return coc.Identity.parse(dict(raw))


def _canonical_key(value: Any) -> str:
    """Independently retained key. Fail-closed; never derived from opportunity_id."""
    try:
        return coc._machine(value, "canonical_opportunity_key")
    except coc.CustodyError as exc:
        raise SlotError("independently retained canonical_opportunity_key required") from exc


def _observation(identity: coc.Identity) -> dict[str, Any]:
    return {
        "schema": OBSERVATION_SCHEMA,
        "buyer_organization_key": identity.buyer_scope,
        "aliases": [
            {"type": "official_id", "value": identity.opportunity_id},
            {"type": "authority_url", "value": f"https://{identity.authority_scope}/"},
        ],
    }


def _resolve_key(identity: coc.Identity) -> str:
    """Resolve via co-located registry only. Caller maps/keys cannot mint a slot."""
    try:
        result = alias_v1.resolve_current(_observation(identity))
    except Exception as exc:
        raise SlotError("canonical opportunity unresolved") from exc
    if type(result) is not dict or result.get("state") != "RESOLVED":
        raise SlotError("canonical opportunity unresolved")
    if result.get("external_action_authorized") is not False or result.get("provider_mutation_authorized") is not False:
        raise SlotError("alias result may not mint action authority")
    if result.get("buyer_contact_authorized") is not False or result.get("payment_or_revenue_inferred") is not False:
        raise SlotError("alias result may not mint action authority")
    return _canonical_key(result.get("canonical_opportunity_key"))


def _slot_seam(identity: coc.Identity, canonical_opportunity_key: str) -> str:
    # Exclusion key is repo + buyer + independently retained canonical key.
    # authority_scope and opportunity_id are aliases and MUST NOT mint a second slot.
    return coc._sha256({
        "schema": SCHEMA,
        "action": ACTION,
        "repo": identity.repo,
        "buyer_scope": identity.buyer_scope,
        "canonical_opportunity_key": canonical_opportunity_key,
    })


def _slot_ref(identity: coc.Identity, canonical_opportunity_key: str) -> str:
    return REF_PREFIX + _slot_seam(identity, canonical_opportunity_key)


def _object_sha(body: Any) -> Optional[str]:
    if not isinstance(body, Mapping) or not isinstance(body.get("object"), Mapping):
        return None
    try:
        return coc._git_sha(body["object"].get("sha"), "ref object sha")
    except coc.CustodyError:
        return None


def _custody(identity: coc.Identity, actor: str, operation: str, transport: Transport) -> dict[str, Any]:
    check = coc.authorize_internal_work(
        identity.document,
        actor_owner=actor,
        actor_operation=operation,
        lane="outreach",
        transport=transport,
    )
    required = {
        "schema": "commercial-opportunity-custody-work-check/v1",
        "seam_sha256": identity.seam_sha256,
        "actor_owner": actor,
        "actor_operation": operation,
        "lane": "outreach",
        "internal_work_authorized": True,
        "external_send_authorized": False,
        "proposal_submission_authorized": False,
        "payment_or_revenue_inferred": False,
    }
    if any(check.get(key) != value for key, value in required.items()):
        raise SlotError("current outreach custody not proven")
    generation = check.get("generation")
    if type(generation) is not int or isinstance(generation, bool) or generation < 1:
        raise SlotError("custody generation invalid")
    if check.get("basis") not in {"WHOLE", "DELEGATE:outreach"}:
        raise SlotError("custody basis invalid")
    history = coc._sha256_hex(check.get("history_sha256"), "custody history")
    check_sha = coc._sha256_hex(check.get("check_sha256"), "custody check")
    return {"generation": generation, "history_sha256": history, "check_sha256": check_sha, "basis": check["basis"]}


def _same_custody(a: Mapping[str, Any], b: Mapping[str, Any]) -> bool:
    return dict(a) == dict(b)


def _lease(raw: Mapping[str, Any], identity: coc.Identity, actor: str, capability: str, transport: Transport) -> dict[str, str]:
    lease_v2.verify_receipt(raw)
    if raw["repo"].casefold() != identity.repo:
        raise SlotError("lease repository mismatch")
    if raw["buyer_scope"] != identity.buyer_scope:
        raise SlotError("lease buyer mismatch")
    if raw["claimant"] != actor:
        raise SlotError("lease claimant mismatch")
    if not lease_v2.verify_possession(raw, claim_capability=capability, transport=transport):
        raise SlotError("lease possession not proven")
    return {
        "lease_ref": raw["lease_ref"],
        "tag_object_sha": raw["tag_object_sha"],
        "claim_capability_sha256": raw["claim_capability_sha256"],
        "preflight_sha256": raw["preflight_sha256"],
        "claim_id": raw["claim_id"],
        "offer_scope": raw["offer_scope"],
        "anchor_sha": raw["anchor_sha"],
    }


def _metadata(identity: coc.Identity, canonical_opportunity_key: str, actor: str, operation: str, custody: Mapping[str, Any], lease: Mapping[str, str], acquired_at: str) -> dict[str, Any]:
    return {
        **identity.document,
        "schema": SCHEMA,
        "canonical_opportunity_key": canonical_opportunity_key,
        "opportunity_seam_sha256": _slot_seam(identity, canonical_opportunity_key),
        "action": ACTION,
        "actor_owner": actor,
        "actor_operation": operation,
        "custody_generation": custody["generation"],
        "custody_history_sha256": custody["history_sha256"],
        "custody_check_sha256": custody["check_sha256"],
        "custody_basis": custody["basis"],
        "lease_ref": lease["lease_ref"],
        "lease_tag_object_sha": lease["tag_object_sha"],
        "lease_claim_capability_sha256": lease["claim_capability_sha256"],
        "lease_preflight_sha256": lease["preflight_sha256"],
        "lease_claim_id": lease["claim_id"],
        "lease_offer_scope": lease["offer_scope"],
        "anchor_sha": lease["anchor_sha"],
        "acquired_at": acquired_at,
        "external_send_authorized": False,
    }


def _tag_name(identity: coc.Identity, canonical_opportunity_key: str, metadata: Mapping[str, Any]) -> str:
    return f"initial-outreach-{_slot_seam(identity, canonical_opportunity_key)[:16]}-{coc._sha256(metadata)[:16]}"


def _receipt(
    identity: coc.Identity,
    canonical_opportunity_key: Optional[str],
    actor: str,
    operation: str,
    *,
    decision: str,
    reason: str,
    consumed: bool,
    custody: Optional[Mapping[str, Any]] = None,
    lease: Optional[Mapping[str, str]] = None,
    tag_sha: Optional[str] = None,
    observed_sha: Optional[str] = None,
    callback_invoked: bool = False,
) -> dict[str, Any]:
    seam = None if canonical_opportunity_key is None else _slot_seam(identity, canonical_opportunity_key)
    ref = None if canonical_opportunity_key is None else _slot_ref(identity, canonical_opportunity_key)
    result = {
        **identity.document,
        "schema": RECEIPT_SCHEMA,
        "canonical_opportunity_key": canonical_opportunity_key,
        "opportunity_seam_sha256": seam,
        "slot_ref": ref,
        "actor_owner": actor,
        "actor_operation": operation,
        "custody_generation": None if custody is None else custody.get("generation"),
        "custody_history_sha256": None if custody is None else custody.get("history_sha256"),
        "custody_check_sha256": None if custody is None else custody.get("check_sha256"),
        "custody_basis": None if custody is None else custody.get("basis"),
        "lease_ref": None if lease is None else lease.get("lease_ref"),
        "lease_tag_object_sha": None if lease is None else lease.get("tag_object_sha"),
        "lease_claim_capability_sha256": None if lease is None else lease.get("claim_capability_sha256"),
        "lease_preflight_sha256": None if lease is None else lease.get("preflight_sha256"),
        "lease_claim_id": None if lease is None else lease.get("claim_id"),
        "lease_offer_scope": None if lease is None else lease.get("offer_scope"),
        "slot_tag_sha": tag_sha,
        "observed_ref_sha": observed_sha,
        "slot_consumed": bool(consumed),
        "provider_callback_invoked": bool(callback_invoked),
        "decision": decision,
        "reason": reason,
        "one_initial_outreach_only": True,
        "replay_or_retry_authorized": False,
        "external_send_authorized": False,
        "provider_send_completed": False,
    }
    result["receipt_sha256"] = coc._sha256(result)
    return result


def verify_receipt(raw: Mapping[str, Any]) -> bool:
    if type(raw) is not dict or raw.get("schema") != RECEIPT_SCHEMA:
        raise SlotError("unsupported receipt")
    if "provider_callback_return_sha256" in raw:
        raise SlotError("receipt may not carry callback-return digest")
    identity = _opp({key: raw[key] for key in ("schema", "repo", "buyer_scope", "authority_scope", "opportunity_id")} | {"schema": coc.SCHEMA})
    key = _canonical_key(raw.get("canonical_opportunity_key"))
    if raw.get("opportunity_seam_sha256") != _slot_seam(identity, key) or raw.get("slot_ref") != _slot_ref(identity, key):
        raise SlotError("receipt opportunity seam mismatch")
    if raw.get("external_send_authorized") is not False or raw.get("provider_send_completed") is not False:
        raise SlotError("receipt may not mint durable send/completion authority")
    if raw.get("replay_or_retry_authorized") is not False or raw.get("one_initial_outreach_only") is not True:
        raise SlotError("receipt one-shot invariant missing")
    digest = coc._sha256_hex(raw.get("receipt_sha256"), "receipt sha256")
    material = dict(raw); material.pop("receipt_sha256")
    if coc._sha256(material) != digest:
        raise SlotError("receipt digest mismatch")
    return True


def execute_initial_outreach(
    opportunity_raw: Mapping[str, Any],
    *,
    actor_owner: str,
    actor_operation: str,
    lease_receipt: Mapping[str, Any],
    claim_capability: str,
    transport: Transport,
    send_once: SendOnce,
) -> dict[str, Any]:
    """Consume one canonical first-contact slot, then synchronously call send_once once.

    Guarantees one callback invocation by this boundary. Does not prove one
    provider mutation inside an arbitrary callback. Never inspects callback return.
    Canonical key comes from the landed alias registry, never from the caller.
    """
    identity = _opp(opportunity_raw)
    actor = coc._actor(actor_owner, "actor_owner")
    operation = coc._operation(actor_operation, "actor_operation")
    if not callable(send_once):
        raise SlotError("send_once callable required")
    try:
        key = _resolve_key(identity)
    except Exception as exc:
        return _receipt(identity, None, actor, operation, decision="HOLD", reason=f"HOLD_UNRESOLVED_ALIAS:{type(exc).__name__}", consumed=False)

    def rec(**kw: Any) -> dict[str, Any]:
        return _receipt(identity, key, actor, operation, **kw)

    try:
        custody1 = _custody(identity, actor, operation, transport)
    except Exception as exc:
        return rec(decision="HOLD", reason=f"HOLD_CUSTODY_PRECHECK:{type(exc).__name__}", consumed=False)
    try:
        lease = _lease(lease_receipt, identity, actor, claim_capability, transport)
    except Exception as exc:
        return rec(decision="HOLD", reason=f"HOLD_LEASE:{type(exc).__name__}", consumed=False, custody=custody1)
    try:
        custody2 = _custody(identity, actor, operation, transport)
    except Exception as exc:
        return rec(decision="HOLD", reason=f"HOLD_CUSTODY_REREAD:{type(exc).__name__}", consumed=False, custody=custody1, lease=lease)
    if not _same_custody(custody1, custody2):
        return rec(decision="HOLD", reason="HOLD_CUSTODY_CHANGED_BEFORE_CONSUME", consumed=False, custody=custody2, lease=lease)

    owner, repo = identity.repo.split("/", 1)
    ref = _slot_ref(identity, key)
    quoted = urllib.parse.quote(ref.removeprefix("refs/"), safe="/")
    get_path = f"/repos/{owner}/{repo}/git/ref/{quoted}"
    status, body = transport("GET", get_path, None)
    if status == 200:
        return rec(decision="HOLD", reason="HOLD_ALREADY_CONSUMED", consumed=True, custody=custody2, lease=lease, observed_sha=_object_sha(body))
    if status != 404:
        return rec(decision="HOLD", reason=f"HOLD_SLOT_PREFLIGHT_READ_{status}", consumed=False, custody=custody2, lease=lease)

    acquired_at = _now()
    metadata = _metadata(identity, key, actor, operation, custody2, lease, acquired_at)
    tag_payload = {
        "tag": _tag_name(identity, key, metadata),
        "message": coc.canon_json(metadata).decode("ascii") + "\n",
        "object": lease["anchor_sha"],
        "type": "commit",
        "tagger": {"name": TAGGER_NAME, "email": TAGGER_EMAIL, "date": acquired_at},
    }
    tag_status, tag_body = transport("POST", f"/repos/{owner}/{repo}/git/tags", tag_payload)
    if tag_status != 201 or not isinstance(tag_body, Mapping):
        return rec(decision="HOLD", reason=f"HOLD_SLOT_TAG_CREATE_{tag_status}", consumed=False, custody=custody2, lease=lease)
    try:
        tag_sha = coc._git_sha(tag_body.get("sha"), "slot tag sha")
    except coc.CustodyError:
        return rec(decision="HOLD", reason="HOLD_SLOT_TAG_RESPONSE_INVALID", consumed=False, custody=custody2, lease=lease)

    ref_status, ref_body = transport("POST", f"/repos/{owner}/{repo}/git/refs", {"ref": ref, "sha": tag_sha})
    observed = _object_sha(ref_body) if ref_status == 201 else None
    if ref_status == 201 and observed == tag_sha:
        consume_reason = "CONSUMED_CREATE_201"
    elif ref_status == 201 or ref_status in INDETERMINATE:
        read_status, read_body = transport("GET", get_path, None)
        observed = _object_sha(read_body) if read_status == 200 else None
        if observed != tag_sha:
            return rec(decision="HOLD", reason=f"HOLD_CREATE_OUTCOME_UNPROVEN_{ref_status}_{read_status}", consumed=read_status == 200, custody=custody2, lease=lease, tag_sha=tag_sha, observed_sha=observed)
        consume_reason = f"CONSUMED_READBACK_SELF_{ref_status}"
    else:
        read_status, read_body = transport("GET", get_path, None)
        observed = _object_sha(read_body) if read_status == 200 else None
        return rec(decision="HOLD", reason="HOLD_ALREADY_CONSUMED" if read_status == 200 else f"HOLD_SLOT_REF_CREATE_{ref_status}", consumed=read_status == 200, custody=custody2, lease=lease, tag_sha=tag_sha, observed_sha=observed)

    try:
        custody3 = _custody(identity, actor, operation, transport)
    except Exception as exc:
        return rec(decision="HOLD", reason=f"HOLD_CUSTODY_POSTCONSUME:{type(exc).__name__}", consumed=True, custody=custody2, lease=lease, tag_sha=tag_sha, observed_sha=observed)
    if not _same_custody(custody2, custody3):
        return rec(decision="HOLD", reason="HOLD_CUSTODY_CHANGED_AFTER_CONSUME", consumed=True, custody=custody3, lease=lease, tag_sha=tag_sha, observed_sha=observed)

    # One callback invocation. Do not bind, repr, str, serialize, or hash the
    # return: a caller object's __repr__/__str__ must never run (ZMK-Q9V4).
    try:
        send_once()
    except BaseException as exc:
        return rec(decision="SEND_OUTCOME_UNKNOWN", reason=f"{consume_reason}:CALLBACK_RAISED:{type(exc).__name__}", consumed=True, custody=custody3, lease=lease, tag_sha=tag_sha, observed_sha=observed, callback_invoked=True)
    return rec(decision="PROVIDER_CALLBACK_RETURNED", reason=consume_reason, consumed=True, custody=custody3, lease=lease, tag_sha=tag_sha, observed_sha=observed, callback_invoked=True)


_METADATA_FIELDS = {
    "schema", "repo", "buyer_scope", "authority_scope", "opportunity_id",
    "canonical_opportunity_key",
    "opportunity_seam_sha256", "action", "actor_owner", "actor_operation",
    "custody_generation", "custody_history_sha256", "custody_check_sha256",
    "custody_basis", "lease_ref", "lease_tag_object_sha",
    "lease_claim_capability_sha256", "lease_preflight_sha256", "lease_claim_id",
    "lease_offer_scope", "anchor_sha", "acquired_at", "external_send_authorized",
}


def inspect_initial_outreach(
    opportunity_raw: Mapping[str, Any],
    *,
    transport: Transport,
) -> dict[str, Any]:
    """Read-only DNR/reconciliation evidence; never authorizes a send."""
    identity = _opp(opportunity_raw)
    try:
        key = _resolve_key(identity)
    except Exception:
        return {"schema": INSPECTION_SCHEMA, "canonical_opportunity_key": None, "opportunity_seam_sha256": None, "slot_ref": None, "decision": "HOLD", "reason": "HOLD_UNRESOLVED_ALIAS", "slot_consumed": False, "evidence_valid": False, "external_send_authorized": False}
    owner, repo = identity.repo.split("/", 1)
    ref = _slot_ref(identity, key)
    quoted = urllib.parse.quote(ref.removeprefix("refs/"), safe="/")
    status, body = transport("GET", f"/repos/{owner}/{repo}/git/ref/{quoted}", None)
    if status == 404:
        return {"schema": INSPECTION_SCHEMA, "canonical_opportunity_key": key, "opportunity_seam_sha256": _slot_seam(identity, key), "slot_ref": ref, "decision": "UNCONSUMED", "slot_consumed": False, "evidence_valid": True, "external_send_authorized": False}
    tag_sha = _object_sha(body) if status == 200 else None
    valid = False
    metadata_digest = None
    if tag_sha is not None:
        tag_status, tag_body = transport("GET", f"/repos/{owner}/{repo}/git/tags/{tag_sha}", None)
        if tag_status == 200 and isinstance(tag_body, Mapping):
            try:
                if coc._git_sha(tag_body.get("sha"), "inspection tag sha") != tag_sha:
                    raise SlotError("tag sha mismatch")
                metadata = coc.strict_json_loads(tag_body.get("message"))
                if type(metadata) is not dict or set(metadata) != _METADATA_FIELDS:
                    raise SlotError("metadata fields")
                embedded = coc.Identity.parse({field: metadata[field] for field in ("schema", "repo", "buyer_scope", "authority_scope", "opportunity_id")} | {"schema": coc.SCHEMA})
                if metadata.get("canonical_opportunity_key") != key:
                    raise SlotError("canonical key mismatch")
                if embedded.repo != identity.repo or embedded.buyer_scope != identity.buyer_scope:
                    raise SlotError("opportunity mismatch")
                if metadata["opportunity_seam_sha256"] != _slot_seam(identity, key):
                    raise SlotError("opportunity mismatch")
                if metadata["schema"] != SCHEMA or metadata["action"] != ACTION or metadata["external_send_authorized"] is not False:
                    raise SlotError("metadata authority/schema")
                if metadata["custody_basis"] not in {"WHOLE", "DELEGATE:outreach"}:
                    raise SlotError("custody basis")
                coc._actor(metadata["actor_owner"], "actor_owner"); coc._operation(metadata["actor_operation"], "actor_operation")
                coc._sha256_hex(metadata["custody_history_sha256"], "custody history"); coc._sha256_hex(metadata["custody_check_sha256"], "custody check")
                coc._sha256_hex(metadata["lease_claim_capability_sha256"], "capability commitment"); coc._sha256_hex(metadata["lease_preflight_sha256"], "preflight")
                coc._git_sha(metadata["lease_tag_object_sha"], "lease tag"); coc._git_sha(metadata["anchor_sha"], "anchor")
                acquired_at = coc._rfc3339(metadata["acquired_at"], "acquired_at")
                obj = tag_body.get("object"); tagger = tag_body.get("tagger")
                if not isinstance(obj, Mapping) or obj.get("type") != "commit" or coc._git_sha(obj.get("sha"), "target") != metadata["anchor_sha"]:
                    raise SlotError("target mismatch")
                if not isinstance(tagger, Mapping) or tagger.get("name") != TAGGER_NAME or tagger.get("email") != TAGGER_EMAIL or coc._rfc3339(tagger.get("date"), "tagger date") != acquired_at:
                    raise SlotError("tagger mismatch")
                if tag_body.get("tag") != _tag_name(identity, key, metadata):
                    raise SlotError("tag name mismatch")
                valid = True; metadata_digest = coc._sha256(metadata)
            except (Exception,):
                valid = False
    return {"schema": INSPECTION_SCHEMA, "canonical_opportunity_key": key, "opportunity_seam_sha256": _slot_seam(identity, key), "slot_ref": ref, "decision": "CONSUMED" if valid else "HOLD", "slot_consumed": True, "evidence_valid": valid, "slot_tag_sha": tag_sha, "metadata_sha256": metadata_digest, "external_send_authorized": False}
