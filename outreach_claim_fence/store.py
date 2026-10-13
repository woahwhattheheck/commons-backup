"""GitHub Contents compare-and-swap claim store for outreach-claim-fence/v2."""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import json
import secrets
import urllib.parse
from typing import Any, Mapping, Optional

from .core import (
    API_VERSION, AUTHORITY_DIGEST, AUTHORITY_GENERATION, CANONICAL_API_URL,
    CANONICAL_REPOSITORY, DEFAULT_BRANCH, DEFAULT_ROOT, MAX_COOLDOWN_SECONDS,
    MAX_LEASE_SECONDS, MAX_RETRIES, MIN_COOLDOWN_SECONDS, MIN_LEASE_SECONDS,
    SCHEMA, ClaimConflict, ClaimNotFound, ClaimReceipt, HttpResponse, OwnershipError,
    ProtocolError, RemoteError, StoredClaim, TargetIdentity, UrllibTransport,
    ValidationError, _CasConflict, _HEX_64, _canonical_json_bytes, _clean_text,
    _format_timestamp, _has_concrete_compensation_signal, _parse_timestamp,
    _record_digest, _safe_hex, _safe_label, _safe_owner, _seal_record, _server_time,
    _sha256_hex, _validate_duration, normalize_target, verify_unsent_reconciliation,
)

_RECORD_FIELDS = {
    "schema", "authority_generation", "authority_digest", "api_origin", "repository", "branch", "root",
    "claim_key", "target_kind", "target_hint", "state", "revision", "agent_id", "operation_id",
    "opportunity_label", "opportunity_digest", "claimed_at", "last_action_at", "ownership_expires_at",
    "contact_not_before", "prior_record_digest", "record_digest", "contact_count", "last_contacted_at",
    "last_message_digest", "last_channel", "compensation_path", "release_reason", "armed_message_digest",
    "armed_channel", "armed_compensation_path", "dispatch_token_digest", "dispatch_started_at",
    "provider_history_digest", "reconciliation_signature",
}


def _validate_record(value: Any, *, expected_claim_key: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ProtocolError("stored claim is not a JSON object")
    if set(value) != _RECORD_FIELDS:
        raise ProtocolError("stored claim fields do not match v2 schema", details={"unexpected": sorted(set(value)-_RECORD_FIELDS), "missing": sorted(_RECORD_FIELDS-set(value))})
    for field in ("schema", "authority_generation", "authority_digest", "api_origin", "repository", "branch", "root", "claim_key", "target_kind", "target_hint", "state", "agent_id", "operation_id", "opportunity_label", "opportunity_digest", "claimed_at", "last_action_at", "ownership_expires_at", "record_digest"):
        if not isinstance(value[field], str):
            raise ProtocolError(f"stored claim field {field!r} has invalid type")
    for field in ("contact_not_before", "prior_record_digest", "last_contacted_at", "last_message_digest", "last_channel", "compensation_path", "release_reason", "armed_message_digest", "armed_channel", "armed_compensation_path", "dispatch_token_digest", "dispatch_started_at", "provider_history_digest", "reconciliation_signature"):
        if value[field] is not None and not isinstance(value[field], str):
            raise ProtocolError(f"stored claim field {field!r} has invalid type")
    if value["schema"] != SCHEMA or value["authority_generation"] != AUTHORITY_GENERATION or value["authority_digest"] != AUTHORITY_DIGEST:
        raise ProtocolError("stored claim authority policy does not match canonical v2 authority")
    if (value["api_origin"], value["repository"], value["branch"], value["root"]) != (CANONICAL_API_URL, CANONICAL_REPOSITORY, DEFAULT_BRANCH, DEFAULT_ROOT):
        raise ProtocolError("stored claim namespace is not canonical")
    if value["claim_key"] != expected_claim_key or not _HEX_64.fullmatch(value["claim_key"]):
        raise ProtocolError("stored claim key does not match path")
    if value["state"] not in {"ACTIVE", "ARMED", "OUTCOME_UNKNOWN", "CONTACTED", "RELEASED"}:
        raise ProtocolError("stored claim state is invalid")
    if value["target_kind"] not in {"email", "domain", "github", "slack", "custom"}:
        raise ProtocolError("stored target kind is invalid")
    for field in ("agent_id", "operation_id"):
        if not value[field] or len(value[field]) > 128:
            raise ProtocolError("stored owner identity is invalid")
    if isinstance(value["revision"], bool) or not isinstance(value["revision"], int) or value["revision"] < 1:
        raise ProtocolError("stored revision is invalid")
    if isinstance(value["contact_count"], bool) or not isinstance(value["contact_count"], int) or value["contact_count"] < 0:
        raise ProtocolError("stored contact count is invalid")
    for field in ("authority_digest", "opportunity_digest", "record_digest"):
        if not _HEX_64.fullmatch(value[field]):
            raise ProtocolError(f"stored {field} is invalid")
    for field in ("prior_record_digest", "last_message_digest", "armed_message_digest", "dispatch_token_digest", "provider_history_digest", "reconciliation_signature"):
        if value[field] is not None and not _HEX_64.fullmatch(value[field]):
            raise ProtocolError(f"stored {field} is invalid")
    if _sha256_hex(value["opportunity_label"].casefold().encode()) != value["opportunity_digest"]:
        raise ProtocolError("stored opportunity digest does not match label")
    claimed = _parse_timestamp(value["claimed_at"], field="claimed_at")
    acted = _parse_timestamp(value["last_action_at"], field="last_action_at")
    _parse_timestamp(value["ownership_expires_at"], field="ownership_expires_at")
    if acted < claimed:
        raise ProtocolError("stored action chronology predates ownership")
    for field in ("contact_not_before", "last_contacted_at", "dispatch_started_at"):
        if value[field] is not None:
            _parse_timestamp(value[field], field=field)
    if value["contact_count"] == 0 and any(value[f] is not None for f in ("last_contacted_at", "last_message_digest", "last_channel", "compensation_path")):
        raise ProtocolError("zero-count claim carries contact evidence")
    if value["contact_count"] > 0 and not all(value[f] is not None for f in ("last_contacted_at", "last_message_digest", "last_channel", "compensation_path")):
        raise ProtocolError("stored contact history is incomplete")
    armed_fields = ("armed_message_digest", "armed_channel", "armed_compensation_path", "dispatch_token_digest")
    if value["state"] in {"ARMED", "OUTCOME_UNKNOWN"} and not all(value[f] is not None for f in armed_fields):
        raise ProtocolError("armed/unknown claim lacks dispatch commitment")
    if value["state"] not in {"ARMED", "OUTCOME_UNKNOWN"} and any(value[f] is not None for f in armed_fields):
        raise ProtocolError("non-armed claim carries dispatch commitment")
    if value["state"] == "OUTCOME_UNKNOWN" and value["dispatch_started_at"] is None:
        raise ProtocolError("unknown outcome lacks dispatch start time")
    if value["state"] != "OUTCOME_UNKNOWN" and value["dispatch_started_at"] is not None:
        raise ProtocolError("non-unknown claim carries dispatch start time")
    if value["state"] == "RELEASED" and not value["release_reason"]:
        raise ProtocolError("released claim lacks reason")
    if value["state"] != "RELEASED" and value["release_reason"] is not None:
        raise ProtocolError("non-released claim carries release reason")
    if (value["provider_history_digest"] is None) != (value["reconciliation_signature"] is None):
        raise ProtocolError("reconciliation evidence is incomplete")
    if value["record_digest"] != _record_digest(value):
        raise ProtocolError("stored claim digest does not verify")
    return dict(value)


class GitHubContentsClaimStore:
    """Canonical contact-level claim authority backed by GitHub Contents CAS."""

    def __init__(self, *, token: str, repository: str = CANONICAL_REPOSITORY, branch: str = DEFAULT_BRANCH, root: str = DEFAULT_ROOT, api_url: str = CANONICAL_API_URL, transport: Optional[Any] = None, reconciliation_key: Optional[bytes] = None) -> None:
        # Production namespace is code-owned. Constructor arguments exist only to fail closed
        # when old callers try to select a different coordination universe.
        if repository != CANONICAL_REPOSITORY or branch != DEFAULT_BRANCH or root != DEFAULT_ROOT or api_url.rstrip("/") != CANONICAL_API_URL:
            raise ValidationError("outreach claim v2 authority is pinned to the canonical repository/branch/root/API origin")
        if not token:
            raise ValidationError("GitHub token is required")
        self.repository = CANONICAL_REPOSITORY
        self.owner, self.repo = CANONICAL_REPOSITORY.split("/", 1)
        self.branch = DEFAULT_BRANCH
        self.root = DEFAULT_ROOT
        self.api_url = CANONICAL_API_URL
        self._token = token
        self.transport = transport or UrllibTransport()
        self._reconciliation_key = reconciliation_key

    def path_for(self, claim_key: str) -> str:
        if not _HEX_64.fullmatch(claim_key):
            raise ValidationError("claim key must be 64 lowercase hexadecimal characters")
        return f"{self.root}/{claim_key[:2]}/{claim_key}.json"

    def _url(self, path: str) -> str:
        return f"{CANONICAL_API_URL}/repos/{self.owner}/{self.repo}/contents/{urllib.parse.quote(path, safe='/')}"

    def _headers(self) -> dict[str, str]:
        return {"Accept": "application/vnd.github+json", "Authorization": f"Bearer {self._token}", "X-GitHub-Api-Version": API_VERSION, "User-Agent": "outreach-claim-fence-v2"}

    @staticmethod
    def _decode_json(response: HttpResponse, *, context: str) -> Mapping[str, Any]:
        try:
            payload = json.loads(response.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProtocolError(f"GitHub returned malformed JSON while {context}") from exc
        if not isinstance(payload, dict):
            raise ProtocolError(f"GitHub returned a non-object while {context}")
        return payload

    def _read(self, identity: TargetIdentity) -> tuple[Optional[StoredClaim], dt.datetime]:
        query = urllib.parse.urlencode({"ref": self.branch})
        response = self.transport.request("GET", f"{self._url(self.path_for(identity.claim_key))}?{query}", self._headers())
        now = _server_time(response.headers)
        if response.status == 404:
            return None, now
        if response.status != 200:
            raise RemoteError("GitHub refused the claim read", details={"status": response.status})
        payload = self._decode_json(response, context="reading a claim")
        if payload.get("type") != "file" or not isinstance(payload.get("sha"), str) or payload.get("encoding") != "base64" or not isinstance(payload.get("content"), str):
            raise ProtocolError("GitHub claim response is not a base64 file")
        try:
            raw = base64.b64decode("".join(payload["content"].split()), validate=True)
            value = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProtocolError("stored claim content is not valid JSON") from exc
        return StoredClaim(_validate_record(value, expected_claim_key=identity.claim_key), payload["sha"], now), now

    def _write(self, *, identity: TargetIdentity, record: Mapping[str, Any], previous_blob_sha: Optional[str], message: str) -> tuple[str, str, dt.datetime]:
        body: dict[str, Any] = {"message": message, "content": base64.b64encode(_canonical_json_bytes(record) + b"\n").decode("ascii"), "branch": self.branch}
        if previous_blob_sha is not None:
            body["sha"] = previous_blob_sha
        response = self.transport.request("PUT", self._url(self.path_for(identity.claim_key)), {**self._headers(), "Content-Type": "application/json"}, _canonical_json_bytes(body))
        now = _server_time(response.headers)
        if response.status in {409, 422}:
            raise _CasConflict()
        if response.status not in {200, 201}:
            raise RemoteError("GitHub refused the claim write", details={"status": response.status})
        payload = self._decode_json(response, context="writing a claim")
        content, commit = payload.get("content"), payload.get("commit")
        if not isinstance(content, dict) or not isinstance(content.get("sha"), str) or not isinstance(commit, dict) or not isinstance(commit.get("sha"), str):
            raise ProtocolError("GitHub write response omitted content/commit SHA")
        return content["sha"], commit["sha"], now

    @staticmethod
    def _owned_by(record: Mapping[str, Any], agent_id: str, operation_id: str) -> bool:
        return record["agent_id"] == agent_id and record["operation_id"] == operation_id

    @staticmethod
    def _ownership_live(record: Mapping[str, Any], now: dt.datetime) -> bool:
        return record["state"] != "RELEASED" and _parse_timestamp(record["ownership_expires_at"], field="ownership_expires_at") > now

    @staticmethod
    def _suppressed(record: Mapping[str, Any], now: dt.datetime) -> bool:
        raw = record.get("contact_not_before")
        return raw is not None and _parse_timestamp(raw, field="contact_not_before") > now

    @classmethod
    def _blocks_reassignment(cls, record: Mapping[str, Any], now: dt.datetime) -> bool:
        if record["state"] == "OUTCOME_UNKNOWN":
            return True
        if cls._suppressed(record, now):
            return True
        if record["state"] == "RELEASED":
            return False
        return cls._ownership_live(record, now)

    def _receipt(self, action: str, identity: TargetIdentity, record: Mapping[str, Any], *, blob_sha: Optional[str], commit_sha: Optional[str], dispatch_token: Optional[str] = None) -> ClaimReceipt:
        return ClaimReceipt(action=action, claim_key=identity.claim_key, state=str(record["state"]), revision=int(record["revision"]), agent_id=str(record["agent_id"]), operation_id=str(record["operation_id"]), ownership_expires_at=str(record["ownership_expires_at"]), contact_not_before=record.get("contact_not_before"), record_digest=str(record["record_digest"]), path=self.path_for(identity.claim_key), blob_sha=blob_sha, commit_sha=commit_sha, dispatch_token=dispatch_token)

    def _conflict(self, record: Mapping[str, Any]) -> ClaimConflict:
        return ClaimConflict("contact is protected by a live/suppressed/ambiguous claim", details={"state": record["state"], "agent_id": record["agent_id"], "operation_id": record["operation_id"], "ownership_expires_at": record["ownership_expires_at"], "contact_not_before": record["contact_not_before"], "target_hint": record["target_hint"], "revision": record["revision"]})

    def _base_record(self, *, identity: TargetIdentity, opportunity_label: str, agent_id: str, operation_id: str, now: dt.datetime, lease_seconds: int, revision: int, prior_digest: Optional[str], history: Optional[Mapping[str, Any]]) -> dict[str, Any]:
        history = history or {}
        stamp = _format_timestamp(now)
        return _seal_record({
            "schema": SCHEMA, "authority_generation": AUTHORITY_GENERATION, "authority_digest": AUTHORITY_DIGEST,
            "api_origin": CANONICAL_API_URL, "repository": CANONICAL_REPOSITORY, "branch": DEFAULT_BRANCH, "root": DEFAULT_ROOT,
            "claim_key": identity.claim_key, "target_kind": identity.kind, "target_hint": identity.hint, "state": "ACTIVE",
            "revision": revision, "agent_id": agent_id, "operation_id": operation_id, "opportunity_label": opportunity_label,
            "opportunity_digest": _sha256_hex(opportunity_label.casefold().encode()), "claimed_at": stamp, "last_action_at": stamp,
            "ownership_expires_at": _format_timestamp(now + dt.timedelta(seconds=lease_seconds)),
            "contact_not_before": history.get("contact_not_before"), "prior_record_digest": prior_digest, "record_digest": "",
            "contact_count": int(history.get("contact_count", 0)), "last_contacted_at": history.get("last_contacted_at"),
            "last_message_digest": history.get("last_message_digest"), "last_channel": history.get("last_channel"),
            "compensation_path": history.get("compensation_path"), "release_reason": None,
            "armed_message_digest": None, "armed_channel": None, "armed_compensation_path": None,
            "dispatch_token_digest": None, "dispatch_started_at": None,
            "provider_history_digest": history.get("provider_history_digest"), "reconciliation_signature": history.get("reconciliation_signature"),
        })

    def acquire(self, *, target_kind: str, contact: str, opportunity: str, agent_id: str, operation_id: str, lease_seconds: int) -> ClaimReceipt:
        identity = normalize_target(target_kind, contact)
        opportunity_label = _safe_label(opportunity, field="opportunity")
        agent_id = _safe_owner(agent_id, field="agent id"); operation_id = _safe_owner(operation_id, field="operation id")
        lease_seconds = _validate_duration(lease_seconds, field="lease", minimum=MIN_LEASE_SECONDS, maximum=MAX_LEASE_SECONDS)
        for _ in range(MAX_RETRIES):
            stored, now = self._read(identity)
            if stored is not None and self._blocks_reassignment(stored.record, now):
                if stored.record["state"] != "OUTCOME_UNKNOWN" and self._owned_by(stored.record, agent_id, operation_id):
                    return self._receipt("ALREADY_OWNED", identity, stored.record, blob_sha=stored.blob_sha, commit_sha=None)
                raise self._conflict(stored.record)
            history = stored.record if stored is not None else None
            record = self._base_record(identity=identity, opportunity_label=opportunity_label, agent_id=agent_id, operation_id=operation_id, now=now, lease_seconds=lease_seconds, revision=(int(stored.record["revision"])+1 if stored else 1), prior_digest=(str(stored.record["record_digest"]) if stored else None), history=history)
            try:
                blob, commit, _ = self._write(identity=identity, record=record, previous_blob_sha=(stored.blob_sha if stored else None), message=f"claim(outreach-v2): reserve {identity.claim_key[:12]} for {agent_id}")
            except _CasConflict:
                continue
            return self._receipt("ACQUIRED", identity, record, blob_sha=blob, commit_sha=commit)
        raise RemoteError("claim compare-and-swap did not converge")

    def inspect(self, *, target_kind: str, contact: str) -> Mapping[str, Any]:
        identity = normalize_target(target_kind, contact); stored, now = self._read(identity)
        if stored is None: raise ClaimNotFound("no claim exists for this contact")
        record = dict(stored.record)
        record.update({"ownership_live": self._ownership_live(record, now), "suppressed": self._suppressed(record, now), "reassignment_blocked": self._blocks_reassignment(record, now), "server_now": _format_timestamp(now), "path": self.path_for(identity.claim_key), "blob_sha": stored.blob_sha})
        return record

    def _owned_record(self, *, identity: TargetIdentity, agent_id: str, operation_id: str, allow_expired_idempotent: bool = False) -> tuple[StoredClaim, dt.datetime]:
        stored, now = self._read(identity)
        if stored is None: raise ClaimNotFound("no claim exists for this contact")
        if not self._owned_by(stored.record, agent_id, operation_id): raise OwnershipError("claim is owned by another operation")
        if not allow_expired_idempotent and not self._ownership_live(stored.record, now): raise OwnershipError("claim ownership lease is no longer live")
        return stored, now

    def _update_owned(self, *, identity: TargetIdentity, agent_id: str, operation_id: str, mutate: Any, commit_message: str, idempotent_match: Optional[Any] = None, allow_unknown: bool = False, allow_expired_idempotent: bool = False, dispatch_token: Optional[str] = None) -> ClaimReceipt:
        for _ in range(MAX_RETRIES):
            stored, now = self._owned_record(identity=identity, agent_id=agent_id, operation_id=operation_id, allow_expired_idempotent=allow_expired_idempotent)
            if idempotent_match is not None and idempotent_match(stored.record):
                return self._receipt("ALREADY_RECORDED", identity, stored.record, blob_sha=stored.blob_sha, commit_sha=None)
            if stored.record["state"] == "OUTCOME_UNKNOWN" and not allow_unknown:
                raise OwnershipError("ambiguous provider outcome blocks mutation until explicit reconciliation")
            if not self._ownership_live(stored.record, now) and stored.record["state"] != "OUTCOME_UNKNOWN":
                raise OwnershipError("claim ownership lease is no longer live")
            next_record = mutate(dict(stored.record), now)
            next_record["revision"] = int(stored.record["revision"]) + 1
            next_record["prior_record_digest"] = stored.record["record_digest"]
            next_record["last_action_at"] = _format_timestamp(now)
            next_record = _seal_record(next_record)
            try:
                blob, commit, _ = self._write(identity=identity, record=next_record, previous_blob_sha=stored.blob_sha, message=commit_message)
            except _CasConflict:
                continue
            return self._receipt("UPDATED", identity, next_record, blob_sha=blob, commit_sha=commit, dispatch_token=dispatch_token)
        raise RemoteError("claim compare-and-swap did not converge")

    def renew(self, *, target_kind: str, contact: str, agent_id: str, operation_id: str, lease_seconds: int) -> ClaimReceipt:
        identity = normalize_target(target_kind, contact); agent_id = _safe_owner(agent_id, field="agent id"); operation_id = _safe_owner(operation_id, field="operation id")
        lease_seconds = _validate_duration(lease_seconds, field="lease", minimum=MIN_LEASE_SECONDS, maximum=MAX_LEASE_SECONDS)
        def mutate(record: dict[str, Any], now: dt.datetime) -> dict[str, Any]:
            requested = now + dt.timedelta(seconds=lease_seconds)
            current = _parse_timestamp(record["ownership_expires_at"], field="ownership_expires_at")
            record["ownership_expires_at"] = _format_timestamp(max(current, requested))
            return record
        return self._update_owned(identity=identity, agent_id=agent_id, operation_id=operation_id, mutate=mutate, commit_message=f"claim(outreach-v2): renew {identity.claim_key[:12]}")

    def arm(self, *, target_kind: str, contact: str, agent_id: str, operation_id: str, message_digest: str, channel: str, compensation_path: str) -> ClaimReceipt:
        identity = normalize_target(target_kind, contact); agent_id = _safe_owner(agent_id, field="agent id"); operation_id = _safe_owner(operation_id, field="operation id")
        message_digest = _safe_hex(message_digest, field="message digest"); channel = _safe_label(channel, field="channel", max_length=80); compensation_path = _safe_label(compensation_path, field="compensation path", max_length=240)
        if not _has_concrete_compensation_signal(compensation_path): raise ValidationError("compensation path must name a concrete paid path, amount, proposal, or bounty")
        token = secrets.token_hex(32); token_digest = hashlib.sha256(token.encode()).hexdigest()
        def mutate(record: dict[str, Any], _now: dt.datetime) -> dict[str, Any]:
            if record["state"] not in {"ACTIVE", "ARMED"}: raise OwnershipError("only ACTIVE/ARMED claims can be armed")
            record.update({"state":"ARMED", "release_reason":None, "armed_message_digest":message_digest, "armed_channel":channel, "armed_compensation_path":compensation_path, "dispatch_token_digest":token_digest, "dispatch_started_at":None, "provider_history_digest":None, "reconciliation_signature":None})
            return record
        return self._update_owned(identity=identity, agent_id=agent_id, operation_id=operation_id, mutate=mutate, commit_message=f"claim(outreach-v2): arm {identity.claim_key[:12]}", dispatch_token=token)

    def begin_dispatch(self, *, target_kind: str, contact: str, agent_id: str, operation_id: str, dispatch_token: str) -> ClaimReceipt:
        identity = normalize_target(target_kind, contact); agent_id = _safe_owner(agent_id, field="agent id"); operation_id = _safe_owner(operation_id, field="operation id")
        if not isinstance(dispatch_token, str) or len(dispatch_token) < 32: raise ValidationError("dispatch token is invalid")
        supplied = hashlib.sha256(dispatch_token.encode()).hexdigest()
        def mutate(record: dict[str, Any], now: dt.datetime) -> dict[str, Any]:
            if record["state"] != "ARMED": raise OwnershipError("dispatch requires an ARMED claim")
            if not hmac.compare_digest(str(record["dispatch_token_digest"]), supplied): raise OwnershipError("dispatch token does not match the current armed generation")
            record["state"] = "OUTCOME_UNKNOWN"; record["dispatch_started_at"] = _format_timestamp(now)
            return record
        return self._update_owned(identity=identity, agent_id=agent_id, operation_id=operation_id, mutate=mutate, commit_message=f"claim(outreach-v2): begin dispatch {identity.claim_key[:12]}")

    def mark_contacted(self, *, target_kind: str, contact: str, agent_id: str, operation_id: str, message_digest: str, channel: str, compensation_path: str, cooldown_seconds: int) -> ClaimReceipt:
        identity = normalize_target(target_kind, contact); agent_id = _safe_owner(agent_id, field="agent id"); operation_id = _safe_owner(operation_id, field="operation id")
        message_digest = _safe_hex(message_digest, field="message digest"); channel = _safe_label(channel, field="channel", max_length=80); compensation_path = _safe_label(compensation_path, field="compensation path", max_length=240)
        cooldown_seconds = _validate_duration(cooldown_seconds, field="cooldown", minimum=MIN_COOLDOWN_SECONDS, maximum=MAX_COOLDOWN_SECONDS)
        if not _has_concrete_compensation_signal(compensation_path): raise ValidationError("compensation path must name a concrete paid path, amount, proposal, or bounty")
        def idem(record: Mapping[str, Any]) -> bool:
            return record["state"] == "CONTACTED" and record["last_message_digest"] == message_digest and record["last_channel"] == channel and record["compensation_path"] == compensation_path
        def mutate(record: dict[str, Any], now: dt.datetime) -> dict[str, Any]:
            if record["state"] != "OUTCOME_UNKNOWN": raise OwnershipError("contact confirmation requires a dispatch already in OUTCOME_UNKNOWN")
            if (record["armed_message_digest"], record["armed_channel"], record["armed_compensation_path"]) != (message_digest, channel, compensation_path): raise ValidationError("contact confirmation does not match armed dispatch metadata")
            not_before = now + dt.timedelta(seconds=cooldown_seconds)
            prior = record.get("contact_not_before")
            if prior is not None: not_before = max(not_before, _parse_timestamp(prior, field="contact_not_before"))
            record.update({"state":"CONTACTED", "contact_count":int(record["contact_count"])+1, "last_contacted_at":_format_timestamp(now), "last_message_digest":message_digest, "last_channel":channel, "compensation_path":compensation_path, "contact_not_before":_format_timestamp(not_before), "ownership_expires_at":_format_timestamp(max(_parse_timestamp(record["ownership_expires_at"], field="ownership_expires_at"), not_before)), "release_reason":None, "armed_message_digest":None, "armed_channel":None, "armed_compensation_path":None, "dispatch_token_digest":None, "dispatch_started_at":None, "provider_history_digest":None, "reconciliation_signature":None})
            return record
        return self._update_owned(identity=identity, agent_id=agent_id, operation_id=operation_id, mutate=mutate, idempotent_match=idem, allow_unknown=True, allow_expired_idempotent=True, commit_message=f"claim(outreach-v2): record contact {identity.claim_key[:12]}")

    def reconcile_unsent(self, *, target_kind: str, contact: str, agent_id: str, operation_id: str, provider_history_digest: str, signature: str) -> ClaimReceipt:
        if self._reconciliation_key is None: raise ValidationError("trusted reconciliation key is not configured")
        identity = normalize_target(target_kind, contact); agent_id = _safe_owner(agent_id, field="agent id"); operation_id = _safe_owner(operation_id, field="operation id")
        provider_history_digest = _safe_hex(provider_history_digest, field="provider history digest"); signature = _safe_hex(signature, field="reconciliation signature")
        def mutate(record: dict[str, Any], now: dt.datetime) -> dict[str, Any]:
            if record["state"] != "OUTCOME_UNKNOWN": raise OwnershipError("only OUTCOME_UNKNOWN can be reconciled UNSENT")
            if not verify_unsent_reconciliation(key=self._reconciliation_key, claim_key=identity.claim_key, record_digest=record["record_digest"], provider_history_digest=provider_history_digest, signature=signature): raise OwnershipError("UNSENT reconciliation signature is invalid for this exact claim generation")
            record.update({"state":"RELEASED", "ownership_expires_at":_format_timestamp(now), "release_reason":"provider-history-confirmed-unsent", "armed_message_digest":None, "armed_channel":None, "armed_compensation_path":None, "dispatch_token_digest":None, "dispatch_started_at":None, "provider_history_digest":provider_history_digest, "reconciliation_signature":signature})
            return record
        return self._update_owned(identity=identity, agent_id=agent_id, operation_id=operation_id, mutate=mutate, allow_unknown=True, allow_expired_idempotent=True, commit_message=f"claim(outreach-v2): reconcile unsent {identity.claim_key[:12]}")

    def release(self, *, target_kind: str, contact: str, agent_id: str, operation_id: str, reason: str) -> ClaimReceipt:
        identity = normalize_target(target_kind, contact); agent_id = _safe_owner(agent_id, field="agent id"); operation_id = _safe_owner(operation_id, field="operation id"); reason = _safe_label(reason, field="release reason", max_length=240)
        def idem(record: Mapping[str, Any]) -> bool: return record["state"] == "RELEASED" and record["release_reason"] == reason
        def mutate(record: dict[str, Any], now: dt.datetime) -> dict[str, Any]:
            if record["state"] == "OUTCOME_UNKNOWN": raise OwnershipError("ambiguous provider outcome cannot be released; reconcile provider history first")
            record.update({"state":"RELEASED", "ownership_expires_at":_format_timestamp(now), "release_reason":reason, "armed_message_digest":None, "armed_channel":None, "armed_compensation_path":None, "dispatch_token_digest":None, "dispatch_started_at":None})
            return record
        return self._update_owned(identity=identity, agent_id=agent_id, operation_id=operation_id, mutate=mutate, idempotent_match=idem, allow_expired_idempotent=True, commit_message=f"claim(outreach-v2): release {identity.claim_key[:12]}")
