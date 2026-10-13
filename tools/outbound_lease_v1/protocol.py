"""Deterministic, mutation-free verifier for #outbound-leases v1.

The Slack channel is a fallback visibility rail, not canonical custody.  Canonical
custody remains the Commons contact-custody protocol family pinned below.  This
module only converts a retained, complete channel read plus separately-computed
canonical-custody/provider/relationship/DNR gates into a deterministic receipt.
It performs no network or provider mutation and cannot grant authority that is
absent from its supplied evidence.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
import unicodedata
from typing import Any, Mapping, Sequence

CHANNEL_ID = "C0C2X8CSYEQ"
PROTOCOL_ROOT_TS = "1789718513.003999"
CANONICAL_CUSTODY_REFS = ("commons#14421", "commons#15969", "commons#15988", "commons#15944")
SCHEMA = "outbound-lease-v1/snapshot"
REPORT_SCHEMA = "outbound-lease-v1/report"
KEY_DOMAIN = b"outbound-lease-v1\0organization\0"
ROUTE_DOMAIN = b"outbound-lease-v1\0route\0"
PURPOSE_DOMAIN = b"outbound-lease-v1\0purpose\0"
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
TS_RE = re.compile(r"^[0-9]+\.[0-9]{6}$")
LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
TOKEN_RE = re.compile(r"^[^\s=]{1,256}$")
CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
PRIMARY = {"SENT", "OUTCOME_UNKNOWN", "UNSENT_RELEASED"}
LIFECYCLE = {"INBOUND", "BOUNCED", "DNR"}
KNOWN = PRIMARY | LIFECYCLE
GATES = {"CLEAN", "BLOCK", "UNKNOWN", "EVENT_AUTHORIZES"}
CUSTODY_GATES = {"CLEAN", "BLOCK", "UNKNOWN"}


class LeaseError(ValueError):
    """Raised when retained coordination evidence is malformed or ambiguous."""


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def _digest_bytes(prefix: bytes, text: str) -> str:
    return hashlib.sha256(prefix + text.encode("utf-8")).hexdigest()


def _semantic_digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _token(value: Any, name: str, *, max_len: int = 256) -> str:
    if type(value) is not str:
        raise LeaseError(f"{name} must be text")
    value = unicodedata.normalize("NFKC", value.strip())
    if not value or len(value) > max_len or CONTROL_RE.search(value):
        raise LeaseError(f"{name} invalid")
    return value


def _hex64(value: Any, name: str) -> str:
    value = _token(value, name, max_len=64).lower()
    if not HEX64_RE.fullmatch(value):
        raise LeaseError(f"{name} must be 64 lowercase hex characters")
    return value


def _ts(value: Any, name: str = "ts") -> str:
    value = _token(value, name, max_len=40)
    if not TS_RE.fullmatch(value):
        raise LeaseError(f"{name} must be a Slack timestamp")
    try:
        Decimal(value)
    except InvalidOperation as exc:
        raise LeaseError(f"{name} invalid") from exc
    return value


def organization_key(root_domain: str) -> str:
    """Return a privacy-safe organization lock key from a caller-supplied root domain.

    This function deliberately does not guess the registrable/root domain.  Callers must
    supply the organization boundary they already use for retained relationship evidence.
    """
    domain = _token(root_domain, "root_domain", max_len=253).casefold()
    if domain.endswith("."):
        domain = domain[:-1]
    if any(mark in domain for mark in ("://", "/", "@", ":", "*")):
        raise LeaseError("root_domain must be a bare hostname")
    try:
        ascii_domain = domain.encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise LeaseError("root_domain IDNA conversion failed") from exc
    labels = ascii_domain.split(".")
    if len(labels) < 2 or any(not LABEL_RE.fullmatch(label) for label in labels):
        raise LeaseError("root_domain must be a syntactically valid multi-label hostname")
    if len(ascii_domain) > 253:
        raise LeaseError("root_domain too long")
    return _digest_bytes(KEY_DOMAIN, ascii_domain)


def route_fingerprint(canonical_route: str) -> str:
    route = _token(canonical_route, "canonical_route", max_len=1000)
    return _digest_bytes(ROUTE_DOMAIN, route)


def purpose_fingerprint(canonical_purpose: str) -> str:
    purpose = _token(canonical_purpose, "canonical_purpose", max_len=2000)
    return _digest_bytes(PURPOSE_DOMAIN, purpose)


def _reject_float(value: str) -> None:
    raise LeaseError("floating-point JSON values are forbidden")


def _pairs(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise LeaseError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def strict_loads(raw: str) -> Any:
    if type(raw) is not str:
        raise LeaseError("JSON input must be text")
    try:
        return json.loads(
            raw,
            object_pairs_hook=_pairs,
            parse_float=_reject_float,
            parse_constant=lambda value: (_ for _ in ()).throw(LeaseError(f"non-finite JSON value: {value}")),
        )
    except LeaseError:
        raise
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise LeaseError("invalid JSON") from exc


def render_intent(*, key: str, seat: str, nonce: str, route: str, purpose: str, source: str) -> str:
    key = _hex64(key, "key")
    route = _hex64(route, "route")
    purpose = _hex64(purpose, "purpose")
    fields = {
        "seat": _token(seat, "seat"),
        "nonce": _token(nonce, "nonce"),
        "source": _token(source, "source"),
    }
    for name, value in fields.items():
        if not TOKEN_RE.fullmatch(value):
            raise LeaseError(f"{name} must be one whitespace-free token")
    return f"INTENT v1 key={key} seat={fields['seat']} nonce={fields['nonce']} route={route} purpose={purpose} source={fields['source']}"


def _parse_fields(parts: list[str], *, required: set[str], allowed: set[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in parts:
        if "=" not in part:
            raise LeaseError("lease record field missing '='")
        key, value = part.split("=", 1)
        if key not in allowed or key in out:
            raise LeaseError("lease record has unexpected or duplicate field")
        if not TOKEN_RE.fullmatch(value):
            raise LeaseError(f"lease field {key} invalid")
        out[key] = value
    if set(out) != required:
        raise LeaseError("lease record field set mismatch")
    return out


def parse_record(text: str) -> dict[str, str] | None:
    text = _token(text, "message_text", max_len=5000)
    first = text.split(None, 1)[0]
    if first not in {"INTENT", *KNOWN}:
        return None
    parts = text.split()
    if len(parts) < 3 or parts[1] != "v1":
        raise LeaseError("recognized lease record has invalid version")
    kind = parts[0]
    if kind == "INTENT":
        required = {"key", "seat", "nonce", "route", "purpose", "source"}
        fields = _parse_fields(parts[2:], required=required, allowed=required)
        fields["key"] = _hex64(fields["key"], "key")
        fields["route"] = _hex64(fields["route"], "route")
        fields["purpose"] = _hex64(fields["purpose"], "purpose")
    else:
        required = {"key", "claim_ts", "evidence"}
        fields = _parse_fields(parts[2:], required=required, allowed=required)
        fields["key"] = _hex64(fields["key"], "key")
        fields["claim_ts"] = _ts(fields["claim_ts"], "claim_ts")
    return {"kind": kind, **fields}


def _bool(value: Any, name: str) -> bool:
    if type(value) is not bool:
        raise LeaseError(f"{name} must be boolean")
    return value


def _gate(value: Any, name: str) -> str:
    value = _token(value, name, max_len=32).upper()
    if value not in GATES:
        raise LeaseError(f"{name} invalid")
    return value


def _custody_gate(value: Any) -> str:
    value = _token(value, "canonical_custody_gate", max_len=32).upper()
    if value not in CUSTODY_GATES:
        raise LeaseError("canonical_custody_gate invalid")
    return value


def _candidate(raw: Mapping[str, Any]) -> dict[str, str]:
    if type(raw) is not dict:
        raise LeaseError("candidate must be an object")
    if set(raw) != {"key", "seat", "nonce"}:
        raise LeaseError("candidate field set mismatch")
    return {
        "key": _hex64(raw["key"], "candidate.key"),
        "seat": _token(raw["seat"], "candidate.seat"),
        "nonce": _token(raw["nonce"], "candidate.nonce"),
    }


def compile_snapshot(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Compile fallback visibility plus external gate evidence into a deterministic preflight report."""
    if type(snapshot) is not dict:
        raise LeaseError("snapshot must be an object")
    required = {
        "schema", "channel_id", "protocol_root_ts", "read_ok", "history_complete",
        "canonical_custody_gate", "provider_gate", "relationship_gate", "dnr_gate", "candidate", "messages",
    }
    if set(snapshot) != required:
        raise LeaseError("snapshot field set mismatch")
    if snapshot["schema"] != SCHEMA:
        raise LeaseError("snapshot schema mismatch")
    if snapshot["channel_id"] != CHANNEL_ID or snapshot["protocol_root_ts"] != PROTOCOL_ROOT_TS:
        raise LeaseError("snapshot not bound to the pinned outbound-leases v1 protocol")

    read_ok = _bool(snapshot["read_ok"], "read_ok")
    complete = _bool(snapshot["history_complete"], "history_complete")
    canonical_custody_gate = _custody_gate(snapshot["canonical_custody_gate"])
    provider_gate = _gate(snapshot["provider_gate"], "provider_gate")
    relationship_gate = _gate(snapshot["relationship_gate"], "relationship_gate")
    dnr_gate = _gate(snapshot["dnr_gate"], "dnr_gate")
    candidate = _candidate(snapshot["candidate"])

    if type(snapshot["messages"]) is not list:
        raise LeaseError("messages must be a list")
    seen_ts: set[str] = set()
    intents: dict[str, dict[str, Any]] = {}
    terminals: list[dict[str, Any]] = []
    for raw in snapshot["messages"]:
        if type(raw) is not dict or set(raw) != {"ts", "is_root", "text"}:
            raise LeaseError("message field set mismatch")
        ts = _ts(raw["ts"])
        if ts in seen_ts:
            raise LeaseError("duplicate message timestamp")
        seen_ts.add(ts)
        is_root = _bool(raw["is_root"], "is_root")
        record = parse_record(raw["text"])
        if record is None:
            continue
        record = {**record, "ts": ts, "is_root": is_root}
        if record["kind"] == "INTENT":
            if not is_root:
                raise LeaseError("INTENT must be a root message")
            if ts in intents:
                raise LeaseError("duplicate INTENT timestamp")
            intents[ts] = record
        else:
            terminals.append(record)

    primary_by_claim: dict[str, dict[str, Any]] = {}
    lifecycle_by_claim: dict[str, list[dict[str, Any]]] = {}
    for terminal in sorted(terminals, key=lambda item: Decimal(item["ts"])):
        claim_ts = terminal["claim_ts"]
        intent = intents.get(claim_ts)
        if intent is None or intent["key"] != terminal["key"]:
            raise LeaseError("terminal references missing or mismatched INTENT")
        if Decimal(terminal["ts"]) <= Decimal(claim_ts):
            raise LeaseError("terminal must follow its INTENT")
        if terminal["kind"] in PRIMARY:
            if claim_ts in primary_by_claim:
                raise LeaseError("claim has multiple primary terminals")
            primary_by_claim[claim_ts] = terminal
        else:
            lifecycle_by_claim.setdefault(claim_ts, []).append(terminal)

    key_intents = [item for item in intents.values() if item["key"] == candidate["key"]]
    key_intents.sort(key=lambda item: Decimal(item["ts"]))
    active = [item for item in key_intents if item["ts"] not in primary_by_claim]
    winner = active[0] if active else None

    candidate_intents = [
        item for item in key_intents
        if item["seat"] == candidate["seat"] and item["nonce"] == candidate["nonce"]
    ]
    if len(candidate_intents) > 1:
        raise LeaseError("candidate seat/nonce has multiple INTENTs")
    candidate_intent = candidate_intents[0] if candidate_intents else None

    blockers: list[str] = []
    if not read_ok:
        blockers.append("CHANNEL_READ_FAILED")
    if not complete:
        blockers.append("HISTORY_INCOMPLETE")
    if canonical_custody_gate != "CLEAN":
        blockers.append(f"CANONICAL_CUSTODY_GATE_{canonical_custody_gate}")
    if provider_gate != "CLEAN":
        blockers.append(f"PROVIDER_GATE_{provider_gate}")
    if dnr_gate != "CLEAN":
        blockers.append(f"DNR_GATE_{dnr_gate}")
    if candidate_intent is None:
        blockers.append("CANDIDATE_INTENT_MISSING")
    elif candidate_intent["ts"] in primary_by_claim:
        blockers.append("CANDIDATE_ALREADY_TERMINAL")
    if winner is None:
        blockers.append("NO_ACTIVE_WINNER")
    elif candidate_intent is None or winner["ts"] != candidate_intent["ts"]:
        blockers.append("LATER_CLAIM_YIELDS")

    unknown_claims = [
        claim_ts for claim_ts, terminal in primary_by_claim.items()
        if intents[claim_ts]["key"] == candidate["key"] and terminal["kind"] == "OUTCOME_UNKNOWN"
    ]
    if unknown_claims:
        # A genuine inbound can reconcile uncertainty; anything else remains a permanent hold.
        reconciled = False
        for claim_ts in unknown_claims:
            if any(event["kind"] == "INBOUND" for event in lifecycle_by_claim.get(claim_ts, [])):
                reconciled = True
        if not reconciled or relationship_gate != "EVENT_AUTHORIZES":
            blockers.append("OUTCOME_UNKNOWN_BLOCKS_RETRY")

    sent_claims = [
        claim_ts for claim_ts, terminal in primary_by_claim.items()
        if intents[claim_ts]["key"] == candidate["key"] and terminal["kind"] == "SENT"
    ]
    if sent_claims and relationship_gate != "EVENT_AUTHORIZES":
        blockers.append("PRIOR_SENT_REQUIRES_RELATIONSHIP_EVENT")
    elif not sent_claims and relationship_gate not in {"CLEAN", "EVENT_AUTHORIZES"}:
        blockers.append(f"RELATIONSHIP_GATE_{relationship_gate}")

    # Dedupe while preserving deterministic order.
    blockers = list(dict.fromkeys(blockers))
    coordination_clean = not blockers
    report_core = {
        "schema": REPORT_SCHEMA,
        "channel_id": CHANNEL_ID,
        "protocol_root_ts": PROTOCOL_ROOT_TS,
        "canonical_custody_refs": list(CANONICAL_CUSTODY_REFS),
        "candidate": candidate,
        "winner": None if winner is None else {
            "ts": winner["ts"], "seat": winner["seat"], "nonce": winner["nonce"],
            "route": winner["route"], "purpose": winner["purpose"], "source": winner["source"],
        },
        "candidate_claim_ts": None if candidate_intent is None else candidate_intent["ts"],
        "active_claim_count": len(active),
        "coordination_clean": coordination_clean,
        "blockers": blockers,
        "gates": {
            "read_ok": read_ok, "history_complete": complete, "canonical_custody": canonical_custody_gate, "provider": provider_gate,
            "relationship": relationship_gate, "dnr": dnr_gate,
        },
        "primary_terminal_count": len(primary_by_claim),
        "lifecycle_event_count": sum(len(events) for events in lifecycle_by_claim.values()),
        "external_send_authorized": False,
        "provider_send_completed": False,
        "payment_or_revenue_inferred": False,
    }
    report_core["semantic_sha256"] = _semantic_digest(report_core)
    return report_core
