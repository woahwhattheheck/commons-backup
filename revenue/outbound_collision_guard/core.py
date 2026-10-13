"""Deterministic outbound single-writer lease and replay guard.

Muse selection is accepted only from an HMAC-authenticated trusted registry.
The module contains verifier logic only: no Muse signer, network integration,
provider mutation, payment authority, or revenue authority.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import unicodedata
from datetime import datetime, timezone

SCHEMA = "outbound-collision-replay-guard/v2"
LEGACY_SCHEMA = "outbound-collision-replay-guard/v1"
MUSE_REGISTRY_SCHEMA = "outbound-collision-muse-registry/v1"
MUSE_TRUST_KEY_ENV = "OUTBOUND_MUSE_TRUST_KEY"
STATES = {"CLAIMED", "YIELD_EXISTING", "WAIT_MUSE", "READY_SINGLE_WRITER", "SENT_TERMINAL", "RELEASED_UNSENT", "HOLD_AMBIGUOUS_COUNTERPARTY"}
AUTHORITY = {"external_send": False, "muse_arbitration": False, "provider_mutation": False, "payment": False, "revenue": False}
_MAX_TEXT = 1024
_SAFE_KEY = re.compile(r"^[a-z0-9][a-z0-9._:@/+~-]{0,511}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_DECISIONS = {"SELECTED", "YIELD", "HOLD"}


class GuardError(ValueError):
    pass


def _strict_obj(value, *, name, keys):
    if type(value) is not dict:
        raise GuardError(f"{name} must be an object")
    actual, expected = set(value), set(keys)
    if actual != expected:
        raise GuardError(f"{name} keys mismatch; missing={sorted(expected-actual)!r} extra={sorted(actual-expected)!r}")
    return value


def _text(value, name):
    if type(value) is not str:
        raise GuardError(f"{name} must be text")
    value = unicodedata.normalize("NFKC", value).strip()
    if not value:
        raise GuardError(f"{name} must be non-empty")
    if len(value.encode("utf-8")) > _MAX_TEXT:
        raise GuardError(f"{name} too long")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise GuardError(f"{name} contains control characters")
    return value


def _key(value, name):
    value = " ".join(_text(value, name).casefold().split())
    if not _SAFE_KEY.fullmatch(value):
        raise GuardError(f"{name} has unsafe/ambiguous characters")
    return value


def _hex64(value, name):
    if type(value) is not str or _HEX64.fullmatch(value) is None:
        raise GuardError(f"{name} must be lowercase sha256 hex")
    return value


def _utc(value, name):
    value = _text(value, name)
    if not value.endswith("Z"):
        raise GuardError(f"{name} must be canonical UTC ending Z")
    try:
        dt = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise GuardError(f"{name} invalid timestamp") from exc
    if dt.tzinfo != timezone.utc or value != dt.isoformat(timespec="seconds").replace("+00:00", "Z"):
        raise GuardError(f"{name} must use second-resolution canonical UTC")
    return dt


def _canon(obj):
    try:
        return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise GuardError("value is not canonical JSON") from exc


def _sha(obj):
    return hashlib.sha256(_canon(obj).encode("utf-8")).hexdigest()


def canonical_intent(intent):
    keys = ("counterparty_key", "route_key", "thread_key", "purpose_key")
    _strict_obj(intent, name="intent", keys=keys)
    out = {k: _key(intent.get(k), f"intent.{k}") for k in keys}
    ambiguous = {"unknown", "tbd", "n/a", "na", "*", "any", "general"}
    if out["counterparty_key"] in ambiguous or out["route_key"] in ambiguous or out["thread_key"] in ambiguous:
        raise GuardError("counterparty/route/thread is ambiguous")
    return out


def intent_fingerprint(intent):
    return _sha({"schema": LEGACY_SCHEMA, "intent": canonical_intent(intent)})


def _claimant(claimant):
    keys = ("claimant_id", "session_id")
    _strict_obj(claimant, name="claimant", keys=keys)
    return {k: _key(claimant.get(k), f"claimant.{k}") for k in keys}


def _trust_key():
    value = os.environ.get(MUSE_TRUST_KEY_ENV, "")
    if type(value) is not str or len(value.encode("utf-8")) < 16:
        raise GuardError(f"{MUSE_TRUST_KEY_ENV} is missing or too short")
    return value.encode("utf-8")


def _muse_receipt(raw, index):
    keys = (
        "receipt_id", "request_key", "intent_fingerprint", "selected_claimant_id",
        "selected_session_id", "lease_generation", "decision", "arbitrated_at",
        "expires_at", "source_ref", "source_sha256",
    )
    value = _strict_obj(raw, name=f"muse.receipts[{index}]", keys=keys)
    decision = value["decision"]
    if type(decision) is not str or decision not in _DECISIONS:
        raise GuardError("Muse decision unsupported")
    generation = value["lease_generation"]
    if type(generation) is not int or isinstance(generation, bool) or generation < 1:
        raise GuardError("Muse lease_generation must be a positive int")
    arbitrated = _utc(value["arbitrated_at"], f"muse.receipts[{index}].arbitrated_at")
    expires = _utc(value["expires_at"], f"muse.receipts[{index}].expires_at")
    if expires <= arbitrated:
        raise GuardError("Muse receipt expiry must be after arbitration")
    source_ref = _text(value["source_ref"], f"muse.receipts[{index}].source_ref")
    return {
        "receipt_id": _key(value["receipt_id"], f"muse.receipts[{index}].receipt_id"),
        "request_key": _key(value["request_key"], f"muse.receipts[{index}].request_key"),
        "intent_fingerprint": _hex64(value["intent_fingerprint"], f"muse.receipts[{index}].intent_fingerprint"),
        "selected_claimant_id": _key(value["selected_claimant_id"], f"muse.receipts[{index}].selected_claimant_id"),
        "selected_session_id": _key(value["selected_session_id"], f"muse.receipts[{index}].selected_session_id"),
        "lease_generation": generation,
        "decision": decision,
        "arbitrated_at": value["arbitrated_at"],
        "expires_at": value["expires_at"],
        "source_ref": source_ref,
        "source_sha256": _hex64(value["source_sha256"], f"muse.receipts[{index}].source_sha256"),
    }


def _verify_muse_registry(registry, *, now):
    value = _strict_obj(
        registry,
        name="muse",
        keys=("schema", "generated_at", "receipts", "signature_hmac_sha256"),
    )
    if value["schema"] != MUSE_REGISTRY_SCHEMA:
        raise GuardError("Muse registry schema mismatch")
    generated = _utc(value["generated_at"], "muse.generated_at")
    if generated > now:
        raise GuardError("Muse registry is from the future")
    receipts = value["receipts"]
    if type(receipts) is not list or not 1 <= len(receipts) <= 1024:
        raise GuardError("Muse receipts must be a bounded non-empty list")
    normalized = []
    ids = set()
    fingerprints = {}
    for index, raw in enumerate(receipts):
        row = _muse_receipt(raw, index)
        if row["receipt_id"] in ids:
            raise GuardError("duplicate Muse receipt_id")
        ids.add(row["receipt_id"])
        source_fp = (row["source_ref"], row["source_sha256"], row["arbitrated_at"])
        prior = fingerprints.get(source_fp)
        if prior is not None and prior != row["receipt_id"]:
            raise GuardError("Muse source evidence was reminted under another receipt_id")
        fingerprints[source_fp] = row["receipt_id"]
        if _utc(row["arbitrated_at"], "muse.arbitrated_at") > generated:
            raise GuardError("Muse registry predates included arbitration evidence")
        normalized.append(row)
    body = {"schema": MUSE_REGISTRY_SCHEMA, "generated_at": value["generated_at"], "receipts": normalized}
    signature = _hex64(value["signature_hmac_sha256"], "muse.signature_hmac_sha256")
    expected = hmac.new(_trust_key(), _canon(body).encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise GuardError("Muse registry signature invalid")
    normalized.sort(key=lambda row: row["receipt_id"])
    return normalized, _sha(body), value["generated_at"]


def _muse(muse, *, fingerprint, claimant, generation, now):
    if muse is None:
        return None
    receipts, registry_sha, generated_at = _verify_muse_registry(muse, now=now)
    bound = [row for row in receipts if (
        row["intent_fingerprint"] == fingerprint
        and row["selected_claimant_id"] == claimant["claimant_id"]
        and row["selected_session_id"] == claimant["session_id"]
        and row["lease_generation"] == generation
    )]
    if len(bound) != 1:
        raise GuardError("Muse registry must contain exactly one receipt for this claimant/session/generation")
    row = bound[0]
    if row["decision"] != "SELECTED":
        raise GuardError("Muse did not select this claimant")
    arbitrated = _utc(row["arbitrated_at"], "muse.arbitrated_at")
    expiry = _utc(row["expires_at"], "muse.expires_at")
    if arbitrated > now or expiry <= now:
        raise GuardError("Muse receipt is future or expired")
    return row, expiry, registry_sha, generated_at


def _validate_attempt(attempt):
    _strict_obj(attempt, name="attempt", keys=("attempt_id", "body_sha256", "provider", "started_at"))
    _key(attempt["attempt_id"], "attempt.attempt_id")
    _hex64(attempt["body_sha256"], "attempt.body_sha256")
    _key(attempt["provider"], "attempt.provider")
    _utc(attempt["started_at"], "attempt.started_at")


def _validate_result(result):
    _strict_obj(result, name="terminal_result", keys=("attempt_id", "provider_status", "provider_message_id", "observed_at"))
    _key(result["attempt_id"], "terminal_result.attempt_id")
    if result["provider_status"] != "SENT":
        raise GuardError("terminal result must be provider SENT")
    _key(result["provider_message_id"], "terminal_result.provider_message_id")
    _utc(result["observed_at"], "terminal_result.observed_at")


def _validate_lease(lease):
    if lease is None:
        return None
    if type(lease) is dict and lease.get("schema") == LEGACY_SCHEMA:
        legacy_keys = ("schema", "fingerprint", "intent", "claimant", "generation", "taken_at", "expires_at", "state", "muse_receipt_id", "attempt", "terminal_result")
        _strict_obj(lease, name="legacy lease", keys=legacy_keys)
        if lease.get("state") == "READY_SINGLE_WRITER":
            raise GuardError("legacy READY lease is unauthenticated; reacquire under signed Muse evidence")
        lease = {
            "schema": SCHEMA, "fingerprint": lease["fingerprint"], "intent": lease["intent"],
            "claimant": lease["claimant"], "generation": lease["generation"],
            "taken_at": lease["taken_at"], "expires_at": lease["expires_at"],
            "state": lease["state"], "muse_receipt_id": None, "muse_request_key": None,
            "muse_registry_sha256": None, "muse_registry_generated_at": None,
            "muse_source_ref": None, "muse_source_sha256": None,
            "attempt": lease["attempt"], "terminal_result": lease["terminal_result"],
        }
    keys = (
        "schema", "fingerprint", "intent", "claimant", "generation", "taken_at",
        "expires_at", "state", "muse_receipt_id", "muse_request_key",
        "muse_registry_sha256", "muse_registry_generated_at", "muse_source_ref",
        "muse_source_sha256", "attempt", "terminal_result",
    )
    _strict_obj(lease, name="lease", keys=keys)
    if lease["schema"] != SCHEMA:
        raise GuardError("lease schema mismatch; v1 READY leases must be reacquired under authenticated Muse evidence")
    intent = canonical_intent(lease["intent"])
    fp = intent_fingerprint(intent)
    if lease["fingerprint"] != fp:
        raise GuardError("lease fingerprint mismatch")
    claimant = _claimant(lease["claimant"])
    generation = lease["generation"]
    if type(generation) is not int or isinstance(generation, bool) or generation < 1:
        raise GuardError("lease generation invalid")
    state = lease["state"]
    if state not in STATES:
        raise GuardError("lease state invalid")
    taken = _utc(lease["taken_at"], "lease.taken_at")
    expires = _utc(lease["expires_at"], "lease.expires_at")
    if expires < taken or (expires == taken and state != "RELEASED_UNSENT"):
        raise GuardError("lease expiry invalid")
    muse_fields = ("muse_receipt_id", "muse_request_key", "muse_registry_sha256", "muse_registry_generated_at", "muse_source_ref", "muse_source_sha256")
    present = [lease[name] is not None for name in muse_fields]
    if any(present) and not all(present):
        raise GuardError("Muse binding fields must be all present or all absent")
    if all(present):
        _key(lease["muse_receipt_id"], "lease.muse_receipt_id")
        _key(lease["muse_request_key"], "lease.muse_request_key")
        _hex64(lease["muse_registry_sha256"], "lease.muse_registry_sha256")
        _utc(lease["muse_registry_generated_at"], "lease.muse_registry_generated_at")
        _text(lease["muse_source_ref"], "lease.muse_source_ref")
        _hex64(lease["muse_source_sha256"], "lease.muse_source_sha256")
    if state == "READY_SINGLE_WRITER" and not all(present):
        raise GuardError("READY_SINGLE_WRITER requires authenticated Muse binding")
    attempt = lease["attempt"]
    if attempt is not None:
        _validate_attempt(attempt)
    terminal = lease["terminal_result"]
    if terminal is not None:
        _validate_result(terminal)
    return {
        "schema": SCHEMA, "fingerprint": fp, "intent": intent, "claimant": claimant,
        "generation": generation, "taken_at": lease["taken_at"], "expires_at": lease["expires_at"],
        "state": state, **{name: lease[name] for name in muse_fields},
        "attempt": attempt, "terminal_result": terminal,
    }


def _envelope(state, lease, reason, *, preserve_lease_state=False):
    if state not in STATES:
        raise GuardError("internal state invalid")
    lease = _validate_lease(lease)
    if not preserve_lease_state:
        lease["state"] = state
    body = {"schema": SCHEMA, "state": state, "reason": _text(reason, "reason"), "lease": lease, "authority": dict(AUTHORITY)}
    body["receipt_sha256"] = _sha(body)
    return body


def acquire(*, intent, claimant, now, ttl_s, existing=None, muse=None):
    if type(ttl_s) is not int or isinstance(ttl_s, bool) or not 30 <= ttl_s <= 7200:
        raise GuardError("ttl_s must be an int in [30,7200]")
    now_dt = _utc(now, "now")
    intent = canonical_intent(intent)
    fp = intent_fingerprint(intent)
    claimant = _claimant(claimant)
    old = _validate_lease(existing)
    if old is not None and old["fingerprint"] != fp:
        raise GuardError("existing lease is for a different intent")
    if old is not None and old["state"] == "SENT_TERMINAL":
        return _envelope("SENT_TERMINAL", old, "provider-confirmed send is terminal")
    if old is not None:
        expiry = _utc(old["expires_at"], "lease.expires_at")
        live = expiry > now_dt
        same = old["claimant"] == claimant
        if live and not same:
            return _envelope("YIELD_EXISTING", old, "live lease belongs to another claimant", preserve_lease_state=True)
        if live and same:
            generation, taken_at, attempt = old["generation"], old["taken_at"], old["attempt"]
        else:
            generation, taken_at, attempt = old["generation"] + 1, now, None
    else:
        generation, taken_at, attempt = 1, now, None
    expires_dt = datetime.fromtimestamp(now_dt.timestamp() + ttl_s, tz=timezone.utc)
    expires = expires_dt.isoformat(timespec="seconds").replace("+00:00", "Z")
    base = {
        "schema": SCHEMA, "fingerprint": fp, "intent": intent, "claimant": claimant,
        "generation": generation, "taken_at": taken_at, "expires_at": expires,
        "state": "CLAIMED", "muse_receipt_id": None, "muse_request_key": None,
        "muse_registry_sha256": None, "muse_registry_generated_at": None,
        "muse_source_ref": None, "muse_source_sha256": None,
        "attempt": attempt, "terminal_result": None,
    }
    try:
        muse_checked = _muse(muse, fingerprint=fp, claimant=claimant, generation=generation, now=now_dt)
    except GuardError:
        base["state"] = "WAIT_MUSE"
        return _envelope("WAIT_MUSE", base, "Muse evidence absent, unauthenticated, stale, or mismatched")
    if muse_checked is None:
        base["state"] = "WAIT_MUSE"
        return _envelope("WAIT_MUSE", base, "authenticated exact Muse arbitration required")
    muse_norm, muse_expiry, registry_sha, registry_generated_at = muse_checked
    if muse_expiry < expires_dt:
        base["expires_at"] = muse_expiry.isoformat(timespec="seconds").replace("+00:00", "Z")
    base.update({
        "muse_receipt_id": muse_norm["receipt_id"],
        "muse_request_key": muse_norm["request_key"],
        "muse_registry_sha256": registry_sha,
        "muse_registry_generated_at": registry_generated_at,
        "muse_source_ref": muse_norm["source_ref"],
        "muse_source_sha256": muse_norm["source_sha256"],
        "state": "READY_SINGLE_WRITER",
    })
    return _envelope("READY_SINGLE_WRITER", base, "authenticated exact claimant/session/intent arbitration is current")


def begin_send(*, lease, body_sha256, provider, now):
    now_dt = _utc(now, "now")
    row = _validate_lease(lease)
    if row["state"] == "SENT_TERMINAL":
        return _envelope("SENT_TERMINAL", row, "already sent")
    if _utc(row["expires_at"], "lease.expires_at") <= now_dt:
        raise GuardError("lease expired before send attempt")
    if row["state"] != "READY_SINGLE_WRITER":
        raise GuardError("lease is not READY_SINGLE_WRITER")
    body_sha256 = _hex64(body_sha256, "body_sha256")
    provider = _key(provider, "provider")
    current = row.get("attempt")
    if current is not None:
        if current["body_sha256"] != body_sha256 or current["provider"] != provider:
            raise GuardError("in-flight retry changed body/provider")
        return _envelope("READY_SINGLE_WRITER", row, "same send attempt replayed idempotently")
    seed = {"fingerprint": row["fingerprint"], "generation": row["generation"], "claimant": row["claimant"], "body_sha256": body_sha256, "provider": provider}
    row["attempt"] = {"attempt_id": _sha(seed)[:32], "body_sha256": body_sha256, "provider": provider, "started_at": now}
    return _envelope("READY_SINGLE_WRITER", row, "send attempt reserved; provider call remains external")


def observe_send(*, lease, attempt_id, provider_status, provider_message_id, now):
    _utc(now, "now")
    row = _validate_lease(lease)
    if row["state"] == "SENT_TERMINAL":
        return _envelope("SENT_TERMINAL", row, "already terminal")
    attempt = row.get("attempt")
    if attempt is None:
        raise GuardError("no send attempt is reserved")
    attempt_id = _key(attempt_id, "attempt_id")
    if attempt_id != attempt["attempt_id"]:
        raise GuardError("provider result binds a different attempt")
    if provider_status == "UNKNOWN":
        if provider_message_id not in (None, ""):
            raise GuardError("UNKNOWN must not assert provider message id")
        return _envelope("READY_SINGLE_WRITER", row, "provider result unresolved; reconcile exact attempt before retry")
    if provider_status != "SENT":
        raise GuardError("provider_status must be SENT or UNKNOWN")
    provider_message_id = _key(provider_message_id, "provider_message_id")
    row["terminal_result"] = {"attempt_id": attempt_id, "provider_status": "SENT", "provider_message_id": provider_message_id, "observed_at": now}
    row["state"] = "SENT_TERMINAL"
    return _envelope("SENT_TERMINAL", row, "provider-confirmed send; exact intent is hard terminal")


def release_unsent(*, lease, claimant, now):
    now_dt = _utc(now, "now")
    row = _validate_lease(lease)
    claimant = _claimant(claimant)
    if row["state"] == "SENT_TERMINAL":
        return _envelope("SENT_TERMINAL", row, "sent lease cannot be released as unsent")
    if row["claimant"] != claimant:
        raise GuardError("only exact claimant/session may release")
    if row.get("attempt") is not None:
        raise GuardError("cannot release with unresolved send attempt")
    row["state"] = "RELEASED_UNSENT"
    row["expires_at"] = now_dt.isoformat(timespec="seconds").replace("+00:00", "Z")
    return _envelope("RELEASED_UNSENT", row, "lease released without provider send")


def ambiguous_hold(*, raw_counterparty, raw_route, purpose_key):
    evidence = {"raw_counterparty": _text(raw_counterparty, "raw_counterparty"), "raw_route": _text(raw_route, "raw_route"), "purpose_key": _key(purpose_key, "purpose_key")}
    body = {"schema": SCHEMA, "state": "HOLD_AMBIGUOUS_COUNTERPARTY", "reason": "counterparty/route aliases require upstream canonical resolution", "evidence": evidence, "authority": dict(AUTHORITY)}
    return {**body, "receipt_sha256": _sha(body)}


def verify(envelope):
    _strict_obj(envelope, name="envelope", keys=("schema", "state", "reason", "lease", "authority", "receipt_sha256"))
    if envelope["schema"] != SCHEMA or envelope["state"] not in STATES:
        raise GuardError("envelope schema/state invalid")
    if envelope["authority"] != AUTHORITY:
        raise GuardError("authority must remain exactly all-false")
    lease = _validate_lease(envelope["lease"])
    expected = _sha({"schema": SCHEMA, "state": envelope["state"], "reason": envelope["reason"], "lease": lease, "authority": AUTHORITY})
    if envelope["receipt_sha256"] != expected:
        raise GuardError("receipt digest mismatch")
    return True
