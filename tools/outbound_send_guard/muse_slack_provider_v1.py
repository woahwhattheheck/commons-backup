#!/usr/bin/env python3
"""Read-only Slack provider evidence for canonical Muse publication election v2.

This module authenticates the *source* of a current-visible Muse election
snapshot by reading the pinned Slack workspace and pinned Muse DM directly. It
deliberately does not claim Slack Web API history is append-only: edited rows
are rejected, while deleted rows are not recoverable from this transport.

It also does not turn a provider observation into outbound authority. Canonical
v2 still owns request/candidate/decision semantics; the separate retained
prior-receipt ledger remains an independent authority root and is not invented
here. Terminal election, external send and side-effect authority stay false.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

TEAM_ID = "T0BRETUB5TK"
MUSE_USER_ID = "U0C0TKRTQHZ"
MUSE_DM_CONVERSATION_ID = "D0C1U7TUZEC"
TOKEN_ENV = "MUSE_SLACK_TOKEN"
PROVIDER_SCHEMA = "outbound-muse-slack-provider-evidence/v1"
AUTHORITY_MODE = "PROVIDER_AUTHENTICATED_SLACK_DM_EVIDENCE_V1"
VISIBILITY_MODEL = "CURRENT_VISIBLE_SLACK_WEB_API_ONLY"
CONTROL_SCHEMA = "MUSE PUBLICATION CONTROL v1"
VALID_CONTROL_ACTIONS = frozenset({"HOLD", "WITHDRAW", "CANCEL", "RESUME"})
PROVIDER_EVIDENCE_TTL_SECONDS = 30
MAX_PROVIDER_PAGES = 64
MAX_PROVIDER_MESSAGES = 2048
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
CONTROL_RE = re.compile(
    r"^MUSE PUBLICATION CONTROL v1\n"
    r"action=(HOLD|WITHDRAW|CANCEL|RESUME)\n"
    r"request_id=([^\n]{1,160})\n"
    r"publication_key=([0-9a-f]{64})\n"
    r"candidate_sha256=([0-9a-f]{64})$"
)


class MuseSlackProviderError(ValueError):
    pass


def _load_core() -> dict[str, Any]:
    path = Path(__file__).with_name("_muse_election_v2_core.py.inc")
    source = path.read_text(encoding="utf-8")
    namespace: dict[str, Any] = {"__name__": __name__ + "._canonical_v2_core"}
    exec(compile(source, str(path), "exec"), namespace, namespace)
    return namespace


_CORE = _load_core()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _fmt(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_utc(value: Any, label: str) -> datetime:
    if type(value) is not str:
        raise MuseSlackProviderError(f"{label}: UTC string required")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise MuseSlackProviderError(f"{label}: canonical UTC required") from exc
    if _fmt(parsed) != value:
        raise MuseSlackProviderError(f"{label}: canonical UTC required")
    return parsed


def _canon(value: Any) -> bytes:
    try:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError, RecursionError) as exc:
        raise MuseSlackProviderError("value is not canonical JSON") from exc
    return (text + "\n").encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canon(value)).hexdigest()


def _token() -> str:
    token = os.environ.get(TOKEN_ENV)
    if type(token) is not str or not token or len(token) > 4096 or any(ord(ch) < 0x21 or ord(ch) > 0x7E for ch in token):
        raise MuseSlackProviderError(f"{TOKEN_ENV}: non-empty printable token required")
    return token


def _slack_api(method: str, params: Mapping[str, Any], token: str) -> dict[str, Any]:
    if method not in {"auth.test", "conversations.info", "conversations.history", "conversations.replies"}:
        raise MuseSlackProviderError("unsupported Slack read method")
    body = urllib.parse.urlencode({str(k): str(v) for k, v in params.items()}).encode("ascii")
    request = urllib.request.Request(
        "https://slack.com/api/" + method,
        data=body,
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise MuseSlackProviderError(f"Slack {method}: transport failure") from exc
    if len(raw) > MAX_RESPONSE_BYTES:
        raise MuseSlackProviderError(f"Slack {method}: response too large")
    try:
        value = json.loads(raw.decode("utf-8", "strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MuseSlackProviderError(f"Slack {method}: invalid JSON") from exc
    if type(value) is not dict or value.get("ok") is not True:
        code = value.get("error") if type(value) is dict and type(value.get("error")) is str else "provider_error"
        raise MuseSlackProviderError(f"Slack {method}: {code}")
    return value


def _provider_identity(token: str) -> None:
    auth = _slack_api("auth.test", {}, token)
    if auth.get("team_id") != TEAM_ID:
        raise MuseSlackProviderError("Slack auth.test: wrong workspace")
    info = _slack_api("conversations.info", {"channel": MUSE_DM_CONVERSATION_ID}, token)
    channel = info.get("channel")
    if type(channel) is not dict:
        raise MuseSlackProviderError("Slack conversations.info: channel object required")
    if channel.get("id") != MUSE_DM_CONVERSATION_ID or channel.get("is_im") is not True or channel.get("user") != MUSE_USER_ID:
        raise MuseSlackProviderError("Slack conversations.info: pinned Muse DM mismatch")


def _slack_epoch(value: Any, label: str) -> float:
    if type(value) is not str or not re.fullmatch(r"[0-9]{1,16}\.[0-9]{6}", value):
        raise MuseSlackProviderError(f"{label}: canonical Slack timestamp required")
    try:
        parsed = float(value)
    except ValueError as exc:
        raise MuseSlackProviderError(f"{label}: canonical Slack timestamp required") from exc
    if parsed < 0:
        raise MuseSlackProviderError(f"{label}: timestamp must be nonnegative")
    return parsed


def _cursor(response: Mapping[str, Any], method: str) -> str:
    meta = response.get("response_metadata", {})
    if meta is None:
        meta = {}
    if type(meta) is not dict:
        raise MuseSlackProviderError(f"Slack {method}: invalid response_metadata")
    cursor = meta.get("next_cursor", "")
    if type(cursor) is not str:
        raise MuseSlackProviderError(f"Slack {method}: invalid next_cursor")
    if response.get("has_more") is True and not cursor:
        raise MuseSlackProviderError(f"Slack {method}: incomplete pagination")
    return cursor


def _raw_message(row: Any, label: str, *, oldest: float, latest: float) -> dict[str, Any]:
    if type(row) is not dict:
        raise MuseSlackProviderError(f"{label}: message object required")
    subtype = row.get("subtype")
    if subtype not in (None, ""):
        raise MuseSlackProviderError(f"{label}: unsupported Slack subtype")
    # conversations.history/replies normally return the current edited message
    # as an ordinary row plus `edited` metadata rather than as Events API
    # `message_changed`. Authenticating edited text under the original ts would
    # erase the mutation, so current-visible evidence rejects it entirely.
    if "edited" in row:
        raise MuseSlackProviderError(f"{label}: edited Slack message unsupported")
    ts = row.get("ts")
    user = row.get("user")
    text = row.get("text")
    value = _slack_epoch(ts, label + ".ts")
    if value < oldest or value > latest:
        raise MuseSlackProviderError(f"{label}: provider returned message outside requested window")
    if type(user) is not str or not re.fullmatch(r"[UW][A-Z0-9]{5,32}", user):
        raise MuseSlackProviderError(f"{label}: attributable Slack user required")
    if type(text) is not str or len(text) > 4096:
        raise MuseSlackProviderError(f"{label}: bounded text required")
    try:
        text.encode("utf-8", "strict")
    except UnicodeEncodeError as exc:
        raise MuseSlackProviderError(f"{label}: Unicode scalar text required") from exc
    reply_count = row.get("reply_count", 0)
    if type(reply_count) is bool or type(reply_count) is not int or reply_count < 0 or reply_count > MAX_PROVIDER_MESSAGES:
        raise MuseSlackProviderError(f"{label}: invalid reply_count")
    return {"message_ts": ts, "author_user_id": user, "text": text, "reply_count": reply_count}


def _fetch_pages(method: str, base: Mapping[str, Any], token: str) -> list[Any]:
    rows: list[Any] = []
    cursor = ""
    seen_cursors: set[str] = set()
    for _ in range(MAX_PROVIDER_PAGES):
        params = dict(base)
        if cursor:
            params["cursor"] = cursor
        response = _slack_api(method, params, token)
        page = response.get("messages")
        if type(page) is not list:
            raise MuseSlackProviderError(f"Slack {method}: messages array required")
        rows.extend(page)
        if len(rows) > MAX_PROVIDER_MESSAGES:
            raise MuseSlackProviderError(f"Slack {method}: too many messages")
        cursor = _cursor(response, method)
        if not cursor:
            return rows
        if cursor in seen_cursors:
            raise MuseSlackProviderError(f"Slack {method}: pagination cursor loop")
        seen_cursors.add(cursor)
    raise MuseSlackProviderError(f"Slack {method}: pagination limit exceeded")


def _fetch_snapshot(request: Mapping[str, Any], *, captured_at: datetime, token: str) -> tuple[dict[str, Any], str, str]:
    req, request_sha, request_message = _CORE["_validate_request"](request)
    requested = _parse_utc(req["requested_at"], "request.requested_at")
    coverage = requested - timedelta(seconds=int(_CORE["COLLISION_LOOKBACK_SECONDS"]))
    oldest = coverage.timestamp()
    latest = captured_at.timestamp()
    if latest < requested.timestamp():
        raise MuseSlackProviderError("capture precedes request")

    history = _fetch_pages(
        "conversations.history",
        {
            "channel": MUSE_DM_CONVERSATION_ID,
            "oldest": f"{oldest:.6f}",
            "latest": f"{latest:.6f}",
            "inclusive": "true",
            "limit": "200",
        },
        token,
    )
    canonical: dict[str, dict[str, str]] = {}
    threaded_parents: list[str] = []
    for index, raw in enumerate(history):
        row = _raw_message(raw, f"history[{index}]", oldest=oldest, latest=latest)
        prior = canonical.get(row["message_ts"])
        stripped = {k: row[k] for k in ("message_ts", "author_user_id", "text")}
        if prior is not None and prior != stripped:
            raise MuseSlackProviderError("conflicting Slack message timestamp")
        canonical[row["message_ts"]] = stripped
        if row["reply_count"]:
            threaded_parents.append(row["message_ts"])

    for parent_ts in sorted(set(threaded_parents), key=float):
        replies = _fetch_pages(
            "conversations.replies",
            {"channel": MUSE_DM_CONVERSATION_ID, "ts": parent_ts, "limit": "200"},
            token,
        )
        for index, raw in enumerate(replies):
            row = _raw_message(raw, f"replies[{parent_ts}][{index}]", oldest=oldest, latest=latest)
            stripped = {k: row[k] for k in ("message_ts", "author_user_id", "text")}
            prior = canonical.get(row["message_ts"])
            if prior is not None and prior != stripped:
                raise MuseSlackProviderError("conflicting Slack thread timestamp")
            canonical[row["message_ts"]] = stripped

    if len(canonical) > int(_CORE["MAX_MESSAGES"]):
        raise MuseSlackProviderError("canonical Muse snapshot exceeds v2 message bound")
    snapshot = {
        "schema_version": _CORE["SNAPSHOT_SCHEMA"],
        "complete": True,
        "channel_id": MUSE_DM_CONVERSATION_ID,
        "coverage_started_at": _fmt(coverage),
        "captured_at": _fmt(captured_at),
        "messages": sorted(canonical.values(), key=lambda row: float(row["message_ts"])),
    }
    normalized = _CORE["normalize_snapshot"](snapshot)
    exact_requests = [row for row in normalized["messages"] if row["text"] == request_message]
    if len(exact_requests) != 1:
        raise MuseSlackProviderError("provider snapshot must contain exactly one exact request event")
    requester = exact_requests[0]["author_user_id"]
    if requester == MUSE_USER_ID:
        raise MuseSlackProviderError("Muse cannot be the requester")
    return normalized, request_sha, requester


def _control_text(action: str, request_payload: Mapping[str, Any]) -> str:
    if action not in VALID_CONTROL_ACTIONS:
        raise MuseSlackProviderError("unsupported requester control action")
    return (
        CONTROL_SCHEMA + "\n"
        + f"action={action}\n"
        + f"request_id={request_payload['request_id']}\n"
        + f"publication_key={request_payload['publication_key']}\n"
        + f"candidate_sha256={request_payload['candidate_sha256']}"
    )


def _requester_controls(snapshot: Mapping[str, Any], request: Mapping[str, Any], requester: str) -> tuple[str | None, str | None, list[str]]:
    req = request["payload"]
    request_message = request["message"]
    request_rows = [row for row in snapshot["messages"] if row["text"] == request_message]
    request_ts = float(request_rows[0]["message_ts"])
    controls: list[tuple[float, str, str]] = []
    ambiguous: list[str] = []
    for row in snapshot["messages"]:
        if row["author_user_id"] != requester or float(row["message_ts"]) <= request_ts or row["text"] == request_message:
            continue
        match = CONTROL_RE.fullmatch(row["text"])
        if match:
            action, rid, pub, cand = match.groups()
            if rid == req["request_id"] and pub == req["publication_key"] and cand == req["candidate_sha256"]:
                controls.append((float(row["message_ts"]), action, row["message_ts"]))
                continue
        if req["request_id"] in row["text"]:
            ambiguous.append(row["message_ts"])
    reasons: list[str] = []
    if ambiguous:
        reasons.append("AMBIGUOUS_REQUESTER_FOLLOWUP:" + ",".join(sorted(ambiguous, key=float)))
    if not controls:
        return None, None, reasons
    controls.sort()
    _, action, ts = controls[-1]
    reasons.append("REQUESTER_CONTROL_" + action)
    return action, ts, reasons


def _compile_payload(request: Mapping[str, Any], *, captured_at: datetime, token: str) -> dict[str, Any]:
    _provider_identity(token)
    snapshot, request_sha, requester = _fetch_snapshot(request, captured_at=captured_at, token=token)
    req = request["payload"]

    # This compile is observation-only. `ledger_complete=True` answers only the
    # counterfactual "what do the currently visible provider bytes say if the
    # independent receipt ledger is complete?". The result is never serialized
    # as a canonical receipt and cannot authorize a terminal election.
    observed = _CORE["compile_receipt"](
        request,
        snapshot,
        observed_at=_fmt(captured_at),
        prior_receipts=(),
        ledger_complete=True,
    )["payload"]
    observed_decision = observed["decision"]
    effective = observed_decision
    control_action, control_ts, provider_reasons = _requester_controls(snapshot, request, requester)
    provider_reasons.append("SLACK_WEB_API_HISTORY_CURRENT_VISIBLE_ONLY")
    if provider_reasons and any(reason.startswith("AMBIGUOUS_REQUESTER_FOLLOWUP:") for reason in provider_reasons):
        effective = "HOLD"
    if control_action in {"HOLD", "WITHDRAW", "CANCEL"}:
        effective = "HOLD"
    if control_action == "RESUME":
        selection_ts = observed.get("selection_message_ts")
        if selection_ts is None or float(selection_ts) <= float(control_ts):
            effective = "HOLD"
            provider_reasons.append("REQUESTER_RESUME_REQUIRES_LATER_MUSE_DECISION")

    snapshot_sha = _digest(snapshot)
    authentication = {
        "schema_version": PROVIDER_SCHEMA,
        "visibility_model": VISIBILITY_MODEL,
        "team_id": TEAM_ID,
        "muse_user_id": MUSE_USER_ID,
        "muse_dm_conversation_id": MUSE_DM_CONVERSATION_ID,
        "request_sha256": request_sha,
        "snapshot_sha256": snapshot_sha,
        "coverage_started_at": snapshot["coverage_started_at"],
        "captured_at": snapshot["captured_at"],
    }
    payload = {
        "schema_version": PROVIDER_SCHEMA,
        "authority_mode": AUTHORITY_MODE,
        "visibility_model": VISIBILITY_MODEL,
        "deleted_history_authenticated": False,
        "requester_control_history_authenticated": False,
        "team_id": TEAM_ID,
        "muse_user_id": MUSE_USER_ID,
        "muse_dm_conversation_id": MUSE_DM_CONVERSATION_ID,
        "request_sha256": request_sha,
        "request_id": req["request_id"],
        "publication_key": req["publication_key"],
        "candidate_sha256": req["candidate_sha256"],
        "requester_user_id": requester,
        "request_message_ts": observed.get("request_message_ts"),
        "snapshot_sha256": snapshot_sha,
        "snapshot_authentication_sha256": _digest(authentication),
        "coverage_started_at": snapshot["coverage_started_at"],
        "compiled_at": _fmt(captured_at),
        "valid_until": _fmt(captured_at + timedelta(seconds=PROVIDER_EVIDENCE_TTL_SECONDS)),
        "muse_observed_decision": observed_decision,
        "current_visible_effective_observation": effective,
        "selection_message_ts": observed.get("selection_message_ts"),
        "selected_at": observed.get("selected_at"),
        "winner_request_id": observed.get("winner_request_id"),
        "winner_candidate_sha256": observed.get("winner_candidate_sha256"),
        "winner_message_ts": observed.get("winner_message_ts"),
        "control_action": control_action,
        "control_message_ts": control_ts,
        "source_reasons": list(observed.get("reasons", [])),
        "provider_reasons": sorted(set(provider_reasons)),
        "prior_receipt_ledger_authenticated": False,
        "terminal_election_authorized": False,
        "requires_current_worker_lease_possession": True,
        "requires_fresh_provider_preflight": True,
        "external_send_authorized": False,
        "side_effects_authorized": False,
    }
    return payload


def compile_provider_evidence(request: Mapping[str, Any]) -> dict[str, Any]:
    """Fetch current-visible Slack evidence and return a read-only receipt."""
    payload = _compile_payload(request, captured_at=_utc_now(), token=_token())
    return {"payload": payload, "receipt_sha256": _digest(payload)}


def verify_provider_evidence(request: Mapping[str, Any], receipt: Mapping[str, Any]) -> bool:
    """Re-read current-visible Slack bytes at the retained boundary exactly."""
    try:
        if type(receipt) is not dict or set(receipt) != {"payload", "receipt_sha256"}:
            return False
        payload = receipt["payload"]
        if type(payload) is not dict:
            return False
        expected_fields = {
            "schema_version", "authority_mode", "visibility_model", "deleted_history_authenticated",
            "requester_control_history_authenticated", "team_id", "muse_user_id", "muse_dm_conversation_id",
            "request_sha256", "request_id", "publication_key", "candidate_sha256", "requester_user_id",
            "request_message_ts", "snapshot_sha256", "snapshot_authentication_sha256", "coverage_started_at",
            "compiled_at", "valid_until", "muse_observed_decision", "current_visible_effective_observation",
            "selection_message_ts", "selected_at", "winner_request_id", "winner_candidate_sha256",
            "winner_message_ts", "control_action", "control_message_ts", "source_reasons", "provider_reasons",
            "prior_receipt_ledger_authenticated", "terminal_election_authorized",
            "requires_current_worker_lease_possession", "requires_fresh_provider_preflight",
            "external_send_authorized", "side_effects_authorized",
        }
        if set(payload) != expected_fields:
            return False
        if payload.get("schema_version") != PROVIDER_SCHEMA or payload.get("authority_mode") != AUTHORITY_MODE:
            return False
        if payload.get("visibility_model") != VISIBILITY_MODEL:
            return False
        if payload.get("deleted_history_authenticated") is not False or payload.get("requester_control_history_authenticated") is not False:
            return False
        if payload.get("team_id") != TEAM_ID or payload.get("muse_user_id") != MUSE_USER_ID or payload.get("muse_dm_conversation_id") != MUSE_DM_CONVERSATION_ID:
            return False
        if payload.get("prior_receipt_ledger_authenticated") is not False or payload.get("terminal_election_authorized") is not False:
            return False
        if payload.get("external_send_authorized") is not False or payload.get("side_effects_authorized") is not False:
            return False
        if payload.get("requires_current_worker_lease_possession") is not True or payload.get("requires_fresh_provider_preflight") is not True:
            return False
        if type(receipt["receipt_sha256"]) is not str or not HEX64_RE.fullmatch(receipt["receipt_sha256"]):
            return False
        if _digest(payload) != receipt["receipt_sha256"]:
            return False
        compiled = _parse_utc(payload.get("compiled_at"), "receipt.compiled_at")
        valid_until = _parse_utc(payload.get("valid_until"), "receipt.valid_until")
        now = _utc_now()
        if valid_until != compiled + timedelta(seconds=PROVIDER_EVIDENCE_TTL_SECONDS) or now > valid_until or compiled > now + timedelta(seconds=30):
            return False
        rebuilt = _compile_payload(request, captured_at=compiled, token=_token())
        return rebuilt == payload
    except (MuseSlackProviderError, KeyError, TypeError, ValueError, OverflowError, OSError):
        return False


__all__ = [
    "AUTHORITY_MODE",
    "CONTROL_SCHEMA",
    "MUSE_DM_CONVERSATION_ID",
    "MUSE_USER_ID",
    "MuseSlackProviderError",
    "PROVIDER_SCHEMA",
    "TEAM_ID",
    "VISIBILITY_MODEL",
    "compile_provider_evidence",
    "verify_provider_evidence",
]
