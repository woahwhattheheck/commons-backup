"""Provider-turn generation lease for collision-safe outbound replies.

This module is a prerequisite control only.  It serializes one provider thread
*generation* (provider/account/thread/latest inbound message) so parallel workers
cannot both act on the same human/provider event while still allowing a genuinely
new inbound message to create a distinct turn.  It never authorizes an external
send; existing buyer/offer possession, DNR, content, route, owner and provider
policy gates remain mandatory.

The connector executor performs Git object/ref mutations and provider-history
reads.  This module only compiles and verifies deterministic plans/receipts, so it
cannot itself send email or mutate a provider.
"""
from __future__ import annotations

import hashlib
import json
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

SCHEMA = "outbound-turn-generation-lease/v1"
PLAN_SCHEMA = "outbound-turn-generation-plan/v1"
INTENT_SCHEMA = "outbound-turn-generation-intent/v1"
RECEIPT_SCHEMA = "outbound-turn-generation-receipt/v1"
METADATA_SCHEMA = "outbound-turn-generation-metadata/v1"
HISTORY_SCHEMA = "outbound-provider-history/v1"
FINALIZATION_SCHEMA = "outbound-turn-generation-finalization/v1"
RESULT_SCHEMA = "outbound-provider-send-result/v1"
REF_PREFIX = "refs/heads/outbound-turn-generation-v1/"
BRANCH_PREFIX = "outbound-turn-generation-v1/"
METADATA_PREFIX = ".tjlabs/outbound-turn-generation-v1/"
CAPABILITY_BYTES = 32

_MACHINE_RE = re.compile(r"^[a-z0-9][a-z0-9._:@/+\-]{0,191}$")
_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")
_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}(?:[0-9a-fA-F]{24})?$")
_PROVIDER_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/+\-=]{0,255}$")

CapabilitySink = Callable[[str], None]


class TurnLeaseError(ValueError):
    pass


def _canon_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError) as exc:
        raise TurnLeaseError("value is not canonical-JSON serializable") from exc


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canon_json(value)).hexdigest()


def _text_sha256(text: str) -> str:
    if not isinstance(text, str) or not text.isascii():
        raise TurnLeaseError("metadata text must be ASCII")
    return hashlib.sha256(text.encode("ascii")).hexdigest()


def _validate_sha(value: Any, field: str) -> str:
    if not isinstance(value, str) or _SHA_RE.fullmatch(value) is None:
        raise TurnLeaseError(f"{field}: expected 40/64 hex object id")
    return value.lower()


def _validate_sha256(value: Any, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value != value.lower()
        or any(ch not in "0123456789abcdef" for ch in value)
    ):
        raise TurnLeaseError(f"{field}: expected 64 lowercase hex characters")
    return value


def _machine(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.isascii() or value != value.casefold():
        raise TurnLeaseError(f"{field}: lowercase ASCII machine token required")
    if _MACHINE_RE.fullmatch(value) is None:
        raise TurnLeaseError(f"{field}: invalid machine token")
    return value


def _provider_id(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.isascii() or _PROVIDER_ID_RE.fullmatch(value) is None:
        raise TurnLeaseError(f"{field}: provider identifier required")
    return value


def _display(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.isascii() or not (3 <= len(value) <= 192):
        raise TurnLeaseError(f"{field}: 3..192 printable ASCII chars required")
    if any(ord(ch) < 0x20 or ch == "\x7f" for ch in value):
        raise TurnLeaseError(f"{field}: control characters forbidden")
    return value


def _repo(value: Any) -> str:
    if not isinstance(value, str) or _REPO_RE.fullmatch(value) is None:
        raise TurnLeaseError("repo: expected owner/name")
    return value


def _rfc3339(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise TurnLeaseError(f"{field}: RFC3339 timestamp required")
    raw = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise TurnLeaseError(f"{field}: invalid RFC3339 timestamp") from exc
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise TurnLeaseError(f"{field}: timezone required")
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _capability(value: Any) -> str:
    return _validate_sha256(value, "turn capability")


def capability_commitment(capability: str) -> str:
    return hashlib.sha256(bytes.fromhex(_capability(capability))).hexdigest()


def _new_capability() -> str:
    return secrets.token_hex(CAPABILITY_BYTES)


def _strict_object(items):
    out: dict[str, Any] = {}
    for key, value in items:
        if key in out:
            raise TurnLeaseError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def _strict_load_object(raw: str, field: str) -> Mapping[str, Any]:
    if not isinstance(raw, str) or not raw.isascii():
        raise TurnLeaseError(f"{field}: ASCII JSON object required")
    try:
        value = json.loads(
            raw,
            object_pairs_hook=_strict_object,
            parse_constant=lambda token: (_ for _ in ()).throw(
                TurnLeaseError(f"non-finite JSON number: {token}")
            ),
        )
    except (TypeError, ValueError, json.JSONDecodeError, TurnLeaseError) as exc:
        raise TurnLeaseError(f"{field}: invalid canonical JSON") from exc
    if not isinstance(value, Mapping):
        raise TurnLeaseError(f"{field}: JSON object required")
    return value


@dataclass(frozen=True)
class TurnClaim:
    repo: str
    provider: str
    account_scope: str
    provider_thread_id: str
    latest_inbound_message_id: str
    send_intent_sha256: str
    body_sha256: str
    claimant: str
    claim_id: str
    claim_started_at: str
    anchor_sha: str
    preflight_sha256: str

    @classmethod
    def parse(cls, raw: Mapping[str, Any]) -> "TurnClaim":
        expected = {
            "repo",
            "provider",
            "account_scope",
            "provider_thread_id",
            "latest_inbound_message_id",
            "send_intent_sha256",
            "body_sha256",
            "claimant",
            "claim_id",
            "claim_started_at",
            "anchor_sha",
            "preflight_sha256",
        }
        if not isinstance(raw, Mapping) or set(raw) != expected:
            raise TurnLeaseError("turn claim: exact fields required")
        return cls(
            _repo(raw["repo"]),
            _machine(raw["provider"], "provider"),
            _machine(raw["account_scope"], "account_scope"),
            _provider_id(raw["provider_thread_id"], "provider_thread_id"),
            _provider_id(raw["latest_inbound_message_id"], "latest_inbound_message_id"),
            _validate_sha256(raw["send_intent_sha256"], "send_intent_sha256"),
            _validate_sha256(raw["body_sha256"], "body_sha256"),
            _display(raw["claimant"], "claimant"),
            _machine(raw["claim_id"], "claim_id"),
            _rfc3339(raw["claim_started_at"], "claim_started_at"),
            _validate_sha(raw["anchor_sha"], "anchor_sha"),
            _validate_sha256(raw["preflight_sha256"], "preflight_sha256"),
        )

    @property
    def seam(self) -> dict[str, str]:
        # Deliberately excludes route, body and claimant.  One exact provider
        # generation has one authority seam regardless of recipient aliases or
        # competing prose.  A newer provider inbound creates a new seam.
        return {
            "schema": SCHEMA,
            "provider": self.provider,
            "account_scope": self.account_scope,
            "provider_thread_id": self.provider_thread_id,
            "latest_inbound_message_id": self.latest_inbound_message_id,
        }

    @property
    def seam_sha256(self) -> str:
        return _sha256(self.seam)

    @property
    def branch_name(self) -> str:
        return BRANCH_PREFIX + self.seam_sha256

    @property
    def lease_ref(self) -> str:
        return REF_PREFIX + self.seam_sha256

    @property
    def metadata_path(self) -> str:
        return METADATA_PREFIX + self.seam_sha256 + ".json"


def seam_sha256(claim_raw: Mapping[str, Any]) -> str:
    return TurnClaim.parse(claim_raw).seam_sha256


def branch_name(claim_raw: Mapping[str, Any]) -> str:
    return TurnClaim.parse(claim_raw).branch_name


def lease_ref(claim_raw: Mapping[str, Any]) -> str:
    return TurnClaim.parse(claim_raw).lease_ref


def metadata_path(claim_raw: Mapping[str, Any]) -> str:
    return TurnClaim.parse(claim_raw).metadata_path


def _metadata(claim: TurnClaim, commitment: str) -> dict[str, Any]:
    return {
        "schema": METADATA_SCHEMA,
        "lease_schema": SCHEMA,
        "repo": claim.repo,
        "provider": claim.provider,
        "account_scope": claim.account_scope,
        "provider_thread_id": claim.provider_thread_id,
        "latest_inbound_message_id": claim.latest_inbound_message_id,
        "seam_sha256": claim.seam_sha256,
        "lease_ref": claim.lease_ref,
        "claimant": claim.claimant,
        "claim_id": claim.claim_id,
        "claim_started_at": claim.claim_started_at,
        "anchor_sha": claim.anchor_sha,
        "preflight_sha256": claim.preflight_sha256,
        "send_intent_sha256": claim.send_intent_sha256,
        "body_sha256": claim.body_sha256,
        "turn_capability_sha256": _validate_sha256(commitment, "turn_capability_sha256"),
        "external_send_authorized": False,
    }


_PLAN_FIELDS = {
    "schema",
    "repo",
    "provider",
    "account_scope",
    "provider_thread_id",
    "latest_inbound_message_id",
    "send_intent_sha256",
    "body_sha256",
    "seam_sha256",
    "lease_ref",
    "branch_name",
    "metadata_path",
    "claimant",
    "claim_id",
    "claim_started_at",
    "anchor_sha",
    "preflight_sha256",
    "turn_capability_sha256",
    "metadata_sha256",
    "metadata_json",
    "external_send_authorized",
    "plan_sha256",
}


def prepare_acquisition(
    claim_raw: Mapping[str, Any], *, retain_capability: CapabilitySink
) -> dict[str, Any]:
    """Create a public acquisition plan after privately retaining capability.

    The raw capability is retained before any connector mutation and never
    appears in the returned plan.  The deterministic branch is the eventual
    create-exclusive provider authority event.
    """
    claim = TurnClaim.parse(claim_raw)
    if not callable(retain_capability):
        raise TurnLeaseError("retain_capability: callable required")
    capability = _new_capability()
    commitment = capability_commitment(capability)
    try:
        retain_capability(capability)
    except Exception as exc:
        raise TurnLeaseError("capability retention failed before provider mutation") from exc
    metadata_json = _canon_json(_metadata(claim, commitment)).decode("ascii") + "\n"
    plan: dict[str, Any] = {
        "schema": PLAN_SCHEMA,
        "repo": claim.repo,
        "provider": claim.provider,
        "account_scope": claim.account_scope,
        "provider_thread_id": claim.provider_thread_id,
        "latest_inbound_message_id": claim.latest_inbound_message_id,
        "send_intent_sha256": claim.send_intent_sha256,
        "body_sha256": claim.body_sha256,
        "seam_sha256": claim.seam_sha256,
        "lease_ref": claim.lease_ref,
        "branch_name": claim.branch_name,
        "metadata_path": claim.metadata_path,
        "claimant": claim.claimant,
        "claim_id": claim.claim_id,
        "claim_started_at": claim.claim_started_at,
        "anchor_sha": claim.anchor_sha,
        "preflight_sha256": claim.preflight_sha256,
        "turn_capability_sha256": commitment,
        "metadata_sha256": _text_sha256(metadata_json),
        "metadata_json": metadata_json,
        "external_send_authorized": False,
    }
    plan["plan_sha256"] = _sha256(plan)
    return plan


def _claim_from_values(raw: Mapping[str, Any]) -> TurnClaim:
    return TurnClaim.parse(
        {
            "repo": raw["repo"],
            "provider": raw["provider"],
            "account_scope": raw["account_scope"],
            "provider_thread_id": raw["provider_thread_id"],
            "latest_inbound_message_id": raw["latest_inbound_message_id"],
            "send_intent_sha256": raw["send_intent_sha256"],
            "body_sha256": raw["body_sha256"],
            "claimant": raw["claimant"],
            "claim_id": raw["claim_id"],
            "claim_started_at": raw["claim_started_at"],
            "anchor_sha": raw["anchor_sha"],
            "preflight_sha256": raw["preflight_sha256"],
        }
    )


def verify_plan(raw: Mapping[str, Any]) -> bool:
    if not isinstance(raw, Mapping) or set(raw) != _PLAN_FIELDS:
        raise TurnLeaseError("turn plan: exact fields required")
    if raw["schema"] != PLAN_SCHEMA:
        raise TurnLeaseError("turn plan: unsupported schema")
    claim = _claim_from_values(raw)
    if _validate_sha256(raw["seam_sha256"], "seam_sha256") != claim.seam_sha256:
        raise TurnLeaseError("turn plan: seam mismatch")
    if raw["lease_ref"] != claim.lease_ref or raw["branch_name"] != claim.branch_name:
        raise TurnLeaseError("turn plan: ref/branch mismatch")
    if raw["metadata_path"] != claim.metadata_path:
        raise TurnLeaseError("turn plan: metadata path mismatch")
    commitment = _validate_sha256(raw["turn_capability_sha256"], "turn_capability_sha256")
    if raw["external_send_authorized"] is not False:
        raise TurnLeaseError("turn plan: lease may never authorize external send")
    expected_metadata = _canon_json(_metadata(claim, commitment)).decode("ascii") + "\n"
    if raw["metadata_json"] != expected_metadata:
        raise TurnLeaseError("turn plan: metadata mismatch")
    if _validate_sha256(raw["metadata_sha256"], "metadata_sha256") != _text_sha256(expected_metadata):
        raise TurnLeaseError("turn plan: metadata digest mismatch")
    digest = _validate_sha256(raw["plan_sha256"], "plan_sha256")
    material = dict(raw)
    material.pop("plan_sha256")
    if _sha256(material) != digest:
        raise TurnLeaseError("turn plan: digest mismatch")
    return True


_INTENT_FIELDS = (_PLAN_FIELDS - {"metadata_json", "external_send_authorized", "plan_sha256"}) | {
    "plan_sha256",
    "lease_commit_sha",
    "external_send_authorized",
    "intent_sha256",
}


def bind_lease_commit(plan_raw: Mapping[str, Any], lease_commit_sha: str) -> dict[str, Any]:
    verify_plan(plan_raw)
    intent = {key: plan_raw[key] for key in _PLAN_FIELDS if key not in {"metadata_json", "plan_sha256"}}
    intent["plan_sha256"] = plan_raw["plan_sha256"]
    intent["lease_commit_sha"] = _validate_sha(lease_commit_sha, "lease_commit_sha")
    intent["schema"] = INTENT_SCHEMA
    intent["external_send_authorized"] = False
    intent["intent_sha256"] = _sha256(intent)
    return intent


def verify_intent(raw: Mapping[str, Any]) -> bool:
    if not isinstance(raw, Mapping) or set(raw) != _INTENT_FIELDS:
        raise TurnLeaseError("turn intent: exact fields required")
    if raw["schema"] != INTENT_SCHEMA:
        raise TurnLeaseError("turn intent: unsupported schema")
    claim = _claim_from_values(raw)
    if _validate_sha256(raw["seam_sha256"], "seam_sha256") != claim.seam_sha256:
        raise TurnLeaseError("turn intent: seam mismatch")
    if raw["lease_ref"] != claim.lease_ref or raw["branch_name"] != claim.branch_name:
        raise TurnLeaseError("turn intent: ref/branch mismatch")
    if raw["metadata_path"] != claim.metadata_path:
        raise TurnLeaseError("turn intent: metadata path mismatch")
    _validate_sha256(raw["turn_capability_sha256"], "turn_capability_sha256")
    _validate_sha256(raw["metadata_sha256"], "metadata_sha256")
    _validate_sha256(raw["plan_sha256"], "plan_sha256")
    _validate_sha(raw["lease_commit_sha"], "lease_commit_sha")
    if raw["external_send_authorized"] is not False:
        raise TurnLeaseError("turn intent: lease may never authorize external send")
    digest = _validate_sha256(raw["intent_sha256"], "intent_sha256")
    material = dict(raw)
    material.pop("intent_sha256")
    if _sha256(material) != digest:
        raise TurnLeaseError("turn intent: digest mismatch")
    return True


def _expected_metadata(raw: Mapping[str, Any]) -> str:
    claim = _claim_from_values(raw)
    commitment = _validate_sha256(raw["turn_capability_sha256"], "turn_capability_sha256")
    return _canon_json(_metadata(claim, commitment)).decode("ascii") + "\n"


_RECEIPT_FIELDS = (_INTENT_FIELDS - {"external_send_authorized", "intent_sha256"}) | {
    "intent_sha256",
    "observed_branch_sha",
    "observed_parent_sha",
    "lease_held_by_claimant",
    "decision",
    "reason",
    "external_send_authorized",
    "receipt_sha256",
}


def receipt_from_readback(
    intent_raw: Mapping[str, Any], *, observed_branch_sha: str | None,
    observed_parent_sha: str | None, observed_metadata_json: str | None,
) -> dict[str, Any]:
    """Compile one public receipt from exact post-create connector readback."""
    verify_intent(intent_raw)
    branch_sha = None if observed_branch_sha is None else _validate_sha(
        observed_branch_sha, "observed_branch_sha"
    )
    parent_sha = None if observed_parent_sha is None else _validate_sha(
        observed_parent_sha, "observed_parent_sha"
    )
    expected_metadata = _expected_metadata(intent_raw)
    held = False
    if branch_sha is None:
        reason = "BRANCH_MISSING_OR_UNREADABLE"
    elif branch_sha != intent_raw["lease_commit_sha"]:
        reason = "HELD_BY_OTHER_OR_REF_DRIFT"
    elif parent_sha != intent_raw["anchor_sha"]:
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
    receipt = {
        key: intent_raw[key]
        for key in _INTENT_FIELDS
        if key not in {"external_send_authorized"}
    }
    receipt["schema"] = RECEIPT_SCHEMA
    receipt.update(
        {
            "observed_branch_sha": branch_sha,
            "observed_parent_sha": parent_sha,
            "lease_held_by_claimant": held,
            "decision": "LEASE_HELD" if held else "HOLD",
            "reason": reason,
            "external_send_authorized": False,
        }
    )
    receipt["receipt_sha256"] = _sha256(receipt)
    return receipt


def verify_receipt(raw: Mapping[str, Any]) -> bool:
    if not isinstance(raw, Mapping) or set(raw) != _RECEIPT_FIELDS:
        raise TurnLeaseError("turn receipt: exact fields required")
    if raw["schema"] != RECEIPT_SCHEMA:
        raise TurnLeaseError("turn receipt: unsupported schema")
    claim = _claim_from_values(raw)
    if _validate_sha256(raw["seam_sha256"], "seam_sha256") != claim.seam_sha256:
        raise TurnLeaseError("turn receipt: seam mismatch")
    if raw["lease_ref"] != claim.lease_ref or raw["branch_name"] != claim.branch_name:
        raise TurnLeaseError("turn receipt: ref/branch mismatch")
    if raw["metadata_path"] != claim.metadata_path:
        raise TurnLeaseError("turn receipt: metadata path mismatch")
    _validate_sha256(raw["turn_capability_sha256"], "turn_capability_sha256")
    _validate_sha256(raw["metadata_sha256"], "metadata_sha256")
    _validate_sha256(raw["plan_sha256"], "plan_sha256")
    _validate_sha256(raw["intent_sha256"], "intent_sha256")
    commit_sha = _validate_sha(raw["lease_commit_sha"], "lease_commit_sha")
    observed = raw["observed_branch_sha"]
    if observed is not None:
        observed = _validate_sha(observed, "observed_branch_sha")
    parent = raw["observed_parent_sha"]
    if parent is not None:
        parent = _validate_sha(parent, "observed_parent_sha")
    held = raw["lease_held_by_claimant"]
    if type(held) is not bool:
        raise TurnLeaseError("turn receipt: lease_held_by_claimant must be bool")
    if raw["decision"] != ("LEASE_HELD" if held else "HOLD"):
        raise TurnLeaseError("turn receipt: inconsistent decision")
    if not isinstance(raw["reason"], str) or not raw["reason"]:
        raise TurnLeaseError("turn receipt: reason required")
    if raw["external_send_authorized"] is not False:
        raise TurnLeaseError("turn receipt: lease may never authorize external send")
    if held and (observed != commit_sha or parent != claim.anchor_sha):
        raise TurnLeaseError("turn receipt: held state lacks exact branch/parent proof")
    digest = _validate_sha256(raw["receipt_sha256"], "receipt_sha256")
    material = dict(raw)
    material.pop("receipt_sha256")
    if _sha256(material) != digest:
        raise TurnLeaseError("turn receipt: digest mismatch")
    return True


def verify_possession(
    raw: Mapping[str, Any], *, turn_capability: str,
    live_branch_sha: str | None, live_parent_sha: str | None,
    live_metadata_json: str | None,
) -> bool:
    """Require private capability plus exact *current* connector readback."""
    verify_receipt(raw)
    if capability_commitment(_capability(turn_capability)) != raw["turn_capability_sha256"]:
        return False
    if live_branch_sha is None or live_parent_sha is None or live_metadata_json is None:
        return False
    try:
        branch = _validate_sha(live_branch_sha, "live_branch_sha")
        parent = _validate_sha(live_parent_sha, "live_parent_sha")
    except TurnLeaseError:
        return False
    if branch != raw["lease_commit_sha"] or parent != raw["anchor_sha"]:
        return False
    expected = _expected_metadata(raw)
    return live_metadata_json == expected and _text_sha256(live_metadata_json) == raw["metadata_sha256"]


@dataclass(frozen=True)
class ProviderHistory:
    provider: str
    account_scope: str
    provider_thread_id: str
    status: str
    latest_inbound_message_id: str | None
    provider_sent_after_bound_inbound: bool | None
    observed_at: str

    @classmethod
    def parse(cls, raw: Mapping[str, Any]) -> "ProviderHistory":
        expected = {
            "schema",
            "provider",
            "account_scope",
            "provider_thread_id",
            "status",
            "latest_inbound_message_id",
            "provider_sent_after_bound_inbound",
            "observed_at",
            "history_sha256",
        }
        if not isinstance(raw, Mapping) or set(raw) != expected:
            raise TurnLeaseError("provider history: exact fields required")
        if raw["schema"] != HISTORY_SCHEMA:
            raise TurnLeaseError("provider history: unsupported schema")
        provider = _machine(raw["provider"], "history provider")
        account = _machine(raw["account_scope"], "history account_scope")
        thread = _provider_id(raw["provider_thread_id"], "history provider_thread_id")
        status = raw["status"]
        if status not in {"COMPLETE", "UNKNOWN", "THROTTLED"}:
            raise TurnLeaseError("provider history: invalid status")
        latest = raw["latest_inbound_message_id"]
        sent = raw["provider_sent_after_bound_inbound"]
        if status == "COMPLETE":
            latest = _provider_id(latest, "history latest_inbound_message_id")
            if type(sent) is not bool:
                raise TurnLeaseError("provider history: COMPLETE requires bool sent flag")
        else:
            if latest is not None or sent is not None:
                raise TurnLeaseError("provider history: incomplete state must not assert provider facts")
        observed = _rfc3339(raw["observed_at"], "history observed_at")
        digest = _validate_sha256(raw["history_sha256"], "history_sha256")
        material = dict(raw)
        material.pop("history_sha256")
        if _sha256(material) != digest:
            raise TurnLeaseError("provider history: digest mismatch")
        return cls(provider, account, thread, status, latest, sent, observed)


def make_provider_history(
    *, provider: str, account_scope: str, provider_thread_id: str,
    status: str, latest_inbound_message_id: str | None,
    provider_sent_after_bound_inbound: bool | None, observed_at: str,
) -> dict[str, Any]:
    raw: dict[str, Any] = {
        "schema": HISTORY_SCHEMA,
        "provider": provider,
        "account_scope": account_scope,
        "provider_thread_id": provider_thread_id,
        "status": status,
        "latest_inbound_message_id": latest_inbound_message_id,
        "provider_sent_after_bound_inbound": provider_sent_after_bound_inbound,
        "observed_at": observed_at,
    }
    # Parse canonicalized fields before committing digest, then regenerate so
    # equivalent RFC3339 offsets do not yield multiple receipts.
    provider_v = _machine(provider, "history provider")
    account_v = _machine(account_scope, "history account_scope")
    thread_v = _provider_id(provider_thread_id, "history provider_thread_id")
    if status not in {"COMPLETE", "UNKNOWN", "THROTTLED"}:
        raise TurnLeaseError("provider history: invalid status")
    if status == "COMPLETE":
        latest_v = _provider_id(latest_inbound_message_id, "history latest_inbound_message_id")
        if type(provider_sent_after_bound_inbound) is not bool:
            raise TurnLeaseError("provider history: COMPLETE requires bool sent flag")
        sent_v = provider_sent_after_bound_inbound
    else:
        if latest_inbound_message_id is not None or provider_sent_after_bound_inbound is not None:
            raise TurnLeaseError("provider history: incomplete state must not assert provider facts")
        latest_v = None
        sent_v = None
    raw = {
        "schema": HISTORY_SCHEMA,
        "provider": provider_v,
        "account_scope": account_v,
        "provider_thread_id": thread_v,
        "status": status,
        "latest_inbound_message_id": latest_v,
        "provider_sent_after_bound_inbound": sent_v,
        "observed_at": _rfc3339(observed_at, "history observed_at"),
    }
    raw["history_sha256"] = _sha256(raw)
    ProviderHistory.parse(raw)
    return raw


_FINALIZATION_FIELDS = {
    "schema",
    "turn_receipt_sha256",
    "history_sha256",
    "provider",
    "account_scope",
    "provider_thread_id",
    "bound_inbound_message_id",
    "send_intent_sha256",
    "body_sha256",
    "live_branch_sha",
    "live_parent_sha",
    "live_metadata_sha256",
    "current_worker_possession_proven",
    "provider_history_complete",
    "bound_generation_still_latest",
    "provider_sent_after_bound_inbound",
    "decision",
    "reason",
    "external_send_authorized",
    "finalization_sha256",
}


def finalize_turn(
    receipt_raw: Mapping[str, Any], *, turn_capability: str,
    live_branch_sha: str | None, live_parent_sha: str | None,
    live_metadata_json: str | None, provider_history: Mapping[str, Any],
) -> dict[str, Any]:
    """Fail-closed last-mile gate immediately before a provider send attempt.

    `TURN_READY_FOR_POLICY` means only that this worker still owns the exact
    provider generation and fresh provider history shows no send since the bound
    inbound.  It is *not* permission to send: external_send_authorized remains
    hard-false and the caller must separately satisfy all normal send policies.
    """
    verify_receipt(receipt_raw)
    history = ProviderHistory.parse(provider_history)
    possession = verify_possession(
        receipt_raw,
        turn_capability=turn_capability,
        live_branch_sha=live_branch_sha,
        live_parent_sha=live_parent_sha,
        live_metadata_json=live_metadata_json,
    )
    scope_match = (
        history.provider == receipt_raw["provider"]
        and history.account_scope == receipt_raw["account_scope"]
        and history.provider_thread_id == receipt_raw["provider_thread_id"]
    )
    complete = history.status == "COMPLETE"
    same_generation = bool(
        complete
        and scope_match
        and history.latest_inbound_message_id == receipt_raw["latest_inbound_message_id"]
    )
    sent_after = history.provider_sent_after_bound_inbound if complete and scope_match else None

    if not possession:
        decision, reason = "HOLD", "CURRENT_WORKER_POSSESSION_UNPROVEN"
    elif not scope_match:
        decision, reason = "HOLD", "PROVIDER_SCOPE_MISMATCH"
    elif not complete:
        decision, reason = "HOLD", f"PROVIDER_HISTORY_{history.status}"
    elif not same_generation:
        decision, reason = "HOLD", "INBOUND_GENERATION_ADVANCED"
    elif sent_after is not False:
        decision, reason = "HOLD", "PROVIDER_SEND_ALREADY_EXISTS_AFTER_BOUND_INBOUND"
    else:
        decision, reason = "TURN_READY_FOR_POLICY", "EXACT_GENERATION_UNSENT_AND_POSSESSED"

    final: dict[str, Any] = {
        "schema": FINALIZATION_SCHEMA,
        "turn_receipt_sha256": receipt_raw["receipt_sha256"],
        "history_sha256": provider_history["history_sha256"],
        "provider": receipt_raw["provider"],
        "account_scope": receipt_raw["account_scope"],
        "provider_thread_id": receipt_raw["provider_thread_id"],
        "bound_inbound_message_id": receipt_raw["latest_inbound_message_id"],
        "send_intent_sha256": receipt_raw["send_intent_sha256"],
        "body_sha256": receipt_raw["body_sha256"],
        "live_branch_sha": None if live_branch_sha is None else _validate_sha(live_branch_sha, "live_branch_sha"),
        "live_parent_sha": None if live_parent_sha is None else _validate_sha(live_parent_sha, "live_parent_sha"),
        "live_metadata_sha256": None if live_metadata_json is None else _text_sha256(live_metadata_json),
        "current_worker_possession_proven": possession,
        "provider_history_complete": complete and scope_match,
        "bound_generation_still_latest": same_generation,
        "provider_sent_after_bound_inbound": sent_after,
        "decision": decision,
        "reason": reason,
        "external_send_authorized": False,
    }
    final["finalization_sha256"] = _sha256(final)
    return final


def verify_finalization(raw: Mapping[str, Any]) -> bool:
    if not isinstance(raw, Mapping) or set(raw) != _FINALIZATION_FIELDS:
        raise TurnLeaseError("finalization: exact fields required")
    if raw["schema"] != FINALIZATION_SCHEMA:
        raise TurnLeaseError("finalization: unsupported schema")
    _validate_sha256(raw["turn_receipt_sha256"], "turn_receipt_sha256")
    _validate_sha256(raw["history_sha256"], "history_sha256")
    _machine(raw["provider"], "provider")
    _machine(raw["account_scope"], "account_scope")
    _provider_id(raw["provider_thread_id"], "provider_thread_id")
    _provider_id(raw["bound_inbound_message_id"], "bound_inbound_message_id")
    _validate_sha256(raw["send_intent_sha256"], "send_intent_sha256")
    _validate_sha256(raw["body_sha256"], "body_sha256")
    for field in ("live_branch_sha", "live_parent_sha"):
        if raw[field] is not None:
            _validate_sha(raw[field], field)
    if raw["live_metadata_sha256"] is not None:
        _validate_sha256(raw["live_metadata_sha256"], "live_metadata_sha256")
    for field in (
        "current_worker_possession_proven",
        "provider_history_complete",
        "bound_generation_still_latest",
    ):
        if type(raw[field]) is not bool:
            raise TurnLeaseError(f"finalization: {field} must be bool")
    sent = raw["provider_sent_after_bound_inbound"]
    if sent is not None and type(sent) is not bool:
        raise TurnLeaseError("finalization: provider_sent_after_bound_inbound must be bool/null")
    if raw["decision"] not in {"HOLD", "TURN_READY_FOR_POLICY"}:
        raise TurnLeaseError("finalization: invalid decision")
    if raw["decision"] == "TURN_READY_FOR_POLICY":
        if not (
            raw["current_worker_possession_proven"]
            and raw["provider_history_complete"]
            and raw["bound_generation_still_latest"]
            and raw["provider_sent_after_bound_inbound"] is False
        ):
            raise TurnLeaseError("finalization: ready state lacks required evidence")
    if not isinstance(raw["reason"], str) or not raw["reason"]:
        raise TurnLeaseError("finalization: reason required")
    if raw["external_send_authorized"] is not False:
        raise TurnLeaseError("finalization: may never authorize external send")
    digest = _validate_sha256(raw["finalization_sha256"], "finalization_sha256")
    material = dict(raw)
    material.pop("finalization_sha256")
    if _sha256(material) != digest:
        raise TurnLeaseError("finalization: digest mismatch")
    return True


_RESULT_FIELDS = {
    "schema",
    "finalization_sha256",
    "provider",
    "account_scope",
    "provider_thread_id",
    "bound_inbound_message_id",
    "status",
    "provider_message_id",
    "observed_at",
    "external_send_authorized",
    "result_sha256",
}


def record_provider_result(
    finalization_raw: Mapping[str, Any], *, status: str,
    provider_message_id: str | None, observed_at: str,
) -> dict[str, Any]:
    """Bind the provider outcome after an independently-authorized send attempt."""
    verify_finalization(finalization_raw)
    if finalization_raw["decision"] != "TURN_READY_FOR_POLICY":
        raise TurnLeaseError("provider result: cannot attach to HOLD finalization")
    if status not in {"SENT", "BOUNCE", "REJECTED", "UNKNOWN"}:
        raise TurnLeaseError("provider result: invalid status")
    if status == "SENT":
        message = _provider_id(provider_message_id, "provider_message_id")
    else:
        message = None if provider_message_id is None else _provider_id(provider_message_id, "provider_message_id")
    result: dict[str, Any] = {
        "schema": RESULT_SCHEMA,
        "finalization_sha256": finalization_raw["finalization_sha256"],
        "provider": finalization_raw["provider"],
        "account_scope": finalization_raw["account_scope"],
        "provider_thread_id": finalization_raw["provider_thread_id"],
        "bound_inbound_message_id": finalization_raw["bound_inbound_message_id"],
        "status": status,
        "provider_message_id": message,
        "observed_at": _rfc3339(observed_at, "result observed_at"),
        "external_send_authorized": False,
    }
    result["result_sha256"] = _sha256(result)
    return result


def verify_provider_result(raw: Mapping[str, Any]) -> bool:
    if not isinstance(raw, Mapping) or set(raw) != _RESULT_FIELDS:
        raise TurnLeaseError("provider result: exact fields required")
    if raw["schema"] != RESULT_SCHEMA:
        raise TurnLeaseError("provider result: unsupported schema")
    _validate_sha256(raw["finalization_sha256"], "finalization_sha256")
    _machine(raw["provider"], "provider")
    _machine(raw["account_scope"], "account_scope")
    _provider_id(raw["provider_thread_id"], "provider_thread_id")
    _provider_id(raw["bound_inbound_message_id"], "bound_inbound_message_id")
    if raw["status"] not in {"SENT", "BOUNCE", "REJECTED", "UNKNOWN"}:
        raise TurnLeaseError("provider result: invalid status")
    if raw["status"] == "SENT" and raw["provider_message_id"] is None:
        raise TurnLeaseError("provider result: SENT requires provider message id")
    if raw["provider_message_id"] is not None:
        _provider_id(raw["provider_message_id"], "provider_message_id")
    _rfc3339(raw["observed_at"], "observed_at")
    if raw["external_send_authorized"] is not False:
        raise TurnLeaseError("provider result: may never authorize external send")
    digest = _validate_sha256(raw["result_sha256"], "result_sha256")
    material = dict(raw)
    material.pop("result_sha256")
    if _sha256(material) != digest:
        raise TurnLeaseError("provider result: digest mismatch")
    return True


def public_capability_absent(value: Any, capability: str) -> bool:
    secret = _capability(capability)
    return secret not in json.dumps(value, sort_keys=True, separators=(",", ":"))
