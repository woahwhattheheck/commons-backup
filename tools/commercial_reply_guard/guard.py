#!/usr/bin/env python3
"""Deterministic, side-effect-free commercial reply handling guard.

Consumes one ``tools/inbound_reply_router`` receipt, a bounded owner policy,
and one proposed reply handling action.  It never sends mail.  Its strongest
positive decision, ``DRAFT_ALLOWED``, authorizes only creating a draft bound to
the exact proposal digest; provider send authority remains false.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROUTER_RECEIPT_SCHEMA = "inbound-reply-router-receipt/v1"
POLICY_SCHEMA = "commercial-reply-policy/v1"
PROPOSAL_SCHEMA = "commercial-reply-proposal/v1"
RECEIPT_SCHEMA = "commercial-reply-guard-receipt/v1"

DECISIONS = {
    "DRAFT_ALLOWED",
    "OWNER_REVIEW_REQUIRED",
    "SUPPRESS",
    "NO_ACTION",
    "ROUTE_REPAIR",
    "HOLD",
}
DRAFTABLE_MODES = {
    "ROUTING_CONTEXT",
    "FIT_ANSWER",
    "CLARIFYING_QUESTION",
    "SCHEDULING_COORDINATION",
}
SENSITIVE_MODES = {
    "PRICING",
    "DISCOUNT",
    "SCOPE_CHANGE",
    "CONTRACT_TERMS",
    "PAYMENT",
    "ACCEPTANCE",
    "CREDENTIALS",
    "LEGAL_TERMS",
}
MODES = DRAFTABLE_MODES | SENSITIVE_MODES
MAX_POLICY_TTL_SECONDS = 7 * 24 * 60 * 60
MAX_ROUTER_RECEIPT_AGE_SECONDS = 15 * 60
MAX_FUTURE_SKEW_SECONDS = 5 * 60
MAX_HISTORY_IDS = 10_000
_EMAIL_RE = re.compile(r"^[^\s@<>(),;:]+@[^\s@<>(),;:]+$")
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")


class GuardError(ValueError):
    """Raised when structurally invalid input cannot be evaluated safely."""


class DuplicateKeyError(GuardError):
    """Raised when JSON contains duplicate object keys."""


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise DuplicateKeyError(f"duplicate JSON object key: {key}")
        out[key] = value
    return out


def _dict(value: Any, label: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise GuardError(f"{label} must be an object")
    return value


def _list(value: Any, label: str, *, maximum: int = 10_000) -> list[Any]:
    if type(value) is not list:
        raise GuardError(f"{label} must be a list")
    if len(value) > maximum:
        raise GuardError(f"{label} exceeds {maximum} entries")
    return value


def _bool(value: Any, label: str) -> bool:
    if type(value) is not bool:
        raise GuardError(f"{label} must be a boolean")
    return value


def _text(value: Any, label: str, *, max_len: int = 512) -> str:
    if type(value) is not str:
        raise GuardError(f"{label} must be a string")
    text = value.strip()
    if not text:
        raise GuardError(f"{label} must not be empty")
    if len(text) > max_len:
        raise GuardError(f"{label} exceeds {max_len} characters")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in text):
        raise GuardError(f"{label} contains control characters")
    return text


def _time(value: Any, label: str) -> datetime:
    text = _text(value, label, max_len=64)
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise GuardError(f"{label} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise GuardError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _ftime(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _email(value: Any, label: str) -> str:
    text = _text(value, label, max_len=320)
    if text.count("@") != 1 or not _EMAIL_RE.fullmatch(text):
        raise GuardError(f"{label} must be a single email address")
    local, domain = text.rsplit("@", 1)
    if not local or not domain or "." not in domain:
        raise GuardError(f"{label} must have a routable domain")
    return f"{local}@{domain.lower()}"


def _sha(value: Any, label: str) -> str:
    text = _text(value, label, max_len=64)
    if not _HEX64_RE.fullmatch(text):
        raise GuardError(f"{label} must be lowercase SHA-256 hex")
    return text


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _exact(obj: dict[str, Any], allowed: set[str], label: str) -> None:
    extra = sorted(set(obj) - allowed)
    if extra:
        raise GuardError(f"{label} contains unknown fields: {', '.join(extra)}")


def _verify_router_receipt(raw: Any) -> dict[str, Any]:
    receipt = _dict(raw, "router_receipt")
    allowed = {
        "schema", "evaluated_at", "offer_id", "counterparty", "thread_id",
        "owner_id", "prior_outbound_message_id", "prior_outbound_observed_at",
        "evidence_captured_at", "action", "basis", "candidate_new_route",
        "do_not_resend", "hard_do_not_contact", "relevant_message_ids",
        "relevant_message_ids_sha256", "evidence_counts", "authority",
        "receipt_sha256",
    }
    _exact(receipt, allowed, "router_receipt")
    if receipt.get("schema") != ROUTER_RECEIPT_SCHEMA:
        raise GuardError(f"router_receipt.schema must be {ROUTER_RECEIPT_SCHEMA}")

    given_digest = _sha(receipt.get("receipt_sha256"), "router_receipt.receipt_sha256")
    without_digest = dict(receipt)
    without_digest.pop("receipt_sha256", None)
    if _digest(without_digest) != given_digest:
        raise GuardError("router_receipt receipt_sha256 mismatch")

    action = _text(receipt.get("action"), "router_receipt.action", max_len=64)
    if action not in {
        "HOLD", "OWNER_REPLY_REQUIRED", "OWNER_REVIEW_REQUIRED",
        "CLOSE_DO_NOT_CONTACT", "ROUTE_REPAIR_REQUIRED", "WAIT_NO_ACTION",
    }:
        raise GuardError("router_receipt.action is unsupported")

    _time(receipt.get("evaluated_at"), "router_receipt.evaluated_at")
    _time(receipt.get("evidence_captured_at"), "router_receipt.evidence_captured_at")
    _email(receipt.get("counterparty"), "router_receipt.counterparty")
    _text(receipt.get("offer_id"), "router_receipt.offer_id")
    _text(receipt.get("thread_id"), "router_receipt.thread_id")
    _text(receipt.get("owner_id"), "router_receipt.owner_id")
    _bool(receipt.get("do_not_resend"), "router_receipt.do_not_resend")
    _bool(receipt.get("hard_do_not_contact"), "router_receipt.hard_do_not_contact")

    ids = _list(receipt.get("relevant_message_ids"), "router_receipt.relevant_message_ids", maximum=MAX_HISTORY_IDS)
    normalized_ids = [_text(item, "router_receipt.relevant_message_ids[]") for item in ids]
    if len(set(normalized_ids)) != len(normalized_ids):
        raise GuardError("router_receipt.relevant_message_ids contains duplicates")
    ids_digest = hashlib.sha256("\n".join(sorted(normalized_ids)).encode("utf-8")).hexdigest()
    if _sha(receipt.get("relevant_message_ids_sha256"), "router_receipt.relevant_message_ids_sha256") != ids_digest:
        raise GuardError("router_receipt relevant_message_ids digest mismatch")

    authority = _dict(receipt.get("authority"), "router_receipt.authority")
    expected_authority = {
        "owner_queue_custody_only", "side_effects_authorized", "reply_send_authorized",
        "resend_authorized", "payment_authorized", "contract_authorized",
        "revenue_recognized", "buyer_acceptance_inferred",
    }
    _exact(authority, expected_authority, "router_receipt.authority")
    for key in expected_authority:
        _bool(authority.get(key), f"router_receipt.authority.{key}")
    if authority["owner_queue_custody_only"] is not True:
        raise GuardError("router_receipt must bind owner queue custody")
    for key in expected_authority - {"owner_queue_custody_only"}:
        if authority[key] is not False:
            raise GuardError(f"router_receipt.authority.{key} must remain false")

    return receipt


def _parse_policy(raw: Any) -> dict[str, Any]:
    obj = _dict(raw, "policy")
    allowed = {
        "schema", "policy_id", "offer_id", "counterparty", "thread_id", "owner_id",
        "issued_at", "expires_at", "allowed_draft_modes",
    }
    _exact(obj, allowed, "policy")
    if obj.get("schema") != POLICY_SCHEMA:
        raise GuardError(f"policy.schema must be {POLICY_SCHEMA}")
    issued_at = _time(obj.get("issued_at"), "policy.issued_at")
    expires_at = _time(obj.get("expires_at"), "policy.expires_at")
    if expires_at <= issued_at:
        raise GuardError("policy.expires_at must be later than issued_at")
    if expires_at - issued_at > timedelta(seconds=MAX_POLICY_TTL_SECONDS):
        raise GuardError("policy TTL exceeds hard maximum")

    modes = _list(obj.get("allowed_draft_modes"), "policy.allowed_draft_modes", maximum=16)
    parsed_modes: list[str] = []
    for index, raw_mode in enumerate(modes):
        mode = _text(raw_mode, f"policy.allowed_draft_modes[{index}]", max_len=64)
        if mode not in DRAFTABLE_MODES:
            raise GuardError("policy.allowed_draft_modes may contain only non-sensitive draft modes")
        parsed_modes.append(mode)
    if len(set(parsed_modes)) != len(parsed_modes):
        raise GuardError("policy.allowed_draft_modes contains duplicates")

    return {
        "schema": POLICY_SCHEMA,
        "policy_id": _text(obj.get("policy_id"), "policy.policy_id"),
        "offer_id": _text(obj.get("offer_id"), "policy.offer_id"),
        "counterparty": _email(obj.get("counterparty"), "policy.counterparty"),
        "thread_id": _text(obj.get("thread_id"), "policy.thread_id"),
        "owner_id": _text(obj.get("owner_id"), "policy.owner_id"),
        "issued_at": issued_at,
        "expires_at": expires_at,
        "allowed_draft_modes": tuple(sorted(parsed_modes)),
    }


def _parse_proposal(raw: Any) -> dict[str, Any]:
    obj = _dict(raw, "proposal")
    allowed = {
        "schema", "proposal_id", "offer_id", "counterparty", "thread_id", "owner_id",
        "inbound_message_id", "mode", "body_sha256", "requested_at",
        "history_complete", "handled_inbound_message_ids",
    }
    _exact(obj, allowed, "proposal")
    if obj.get("schema") != PROPOSAL_SCHEMA:
        raise GuardError(f"proposal.schema must be {PROPOSAL_SCHEMA}")
    mode = _text(obj.get("mode"), "proposal.mode", max_len=64)
    if mode not in MODES:
        raise GuardError("proposal.mode is unsupported")
    history = _list(obj.get("handled_inbound_message_ids"), "proposal.handled_inbound_message_ids", maximum=MAX_HISTORY_IDS)
    history_ids = [
        _text(value, f"proposal.handled_inbound_message_ids[{index}]")
        for index, value in enumerate(history)
    ]
    if len(set(history_ids)) != len(history_ids):
        raise GuardError("proposal.handled_inbound_message_ids contains duplicates")
    return {
        "schema": PROPOSAL_SCHEMA,
        "proposal_id": _text(obj.get("proposal_id"), "proposal.proposal_id"),
        "offer_id": _text(obj.get("offer_id"), "proposal.offer_id"),
        "counterparty": _email(obj.get("counterparty"), "proposal.counterparty"),
        "thread_id": _text(obj.get("thread_id"), "proposal.thread_id"),
        "owner_id": _text(obj.get("owner_id"), "proposal.owner_id"),
        "inbound_message_id": _text(obj.get("inbound_message_id"), "proposal.inbound_message_id"),
        "mode": mode,
        "body_sha256": _sha(obj.get("body_sha256"), "proposal.body_sha256"),
        "requested_at": _time(obj.get("requested_at"), "proposal.requested_at"),
        "history_complete": _bool(obj.get("history_complete"), "proposal.history_complete"),
        "handled_inbound_message_ids": tuple(sorted(history_ids)),
    }


def _receipt(*, decision: str, reasons: list[str], router: dict[str, Any], policy: dict[str, Any], proposal: dict[str, Any]) -> dict[str, Any]:
    if decision not in DECISIONS:
        raise AssertionError(decision)
    policy_for_digest = dict(policy)
    policy_for_digest["issued_at"] = _ftime(policy["issued_at"])
    policy_for_digest["expires_at"] = _ftime(policy["expires_at"])
    policy_for_digest["allowed_draft_modes"] = list(policy["allowed_draft_modes"])
    proposal_for_digest = dict(proposal)
    proposal_for_digest["requested_at"] = _ftime(proposal["requested_at"])
    proposal_for_digest["handled_inbound_message_ids"] = list(proposal["handled_inbound_message_ids"])
    body: dict[str, Any] = {
        "schema": RECEIPT_SCHEMA,
        "decision": decision,
        "reasons": sorted(set(reasons)),
        "offer_id": proposal["offer_id"],
        "counterparty": proposal["counterparty"],
        "thread_id": proposal["thread_id"],
        "owner_id": proposal["owner_id"],
        "inbound_message_id": proposal["inbound_message_id"],
        "mode": proposal["mode"],
        "body_sha256": proposal["body_sha256"],
        "requested_at": _ftime(proposal["requested_at"]),
        "router_receipt_sha256": router["receipt_sha256"],
        "policy_id": policy["policy_id"],
        "policy_sha256": _digest(policy_for_digest),
        "proposal_sha256": _digest(proposal_for_digest),
        "authority": {
            "draft_creation_authorized": decision == "DRAFT_ALLOWED",
            "owner_review_required": decision == "OWNER_REVIEW_REQUIRED",
            "provider_send_authorized": False,
            "new_thread_authorized": False,
            "pricing_authorized": False,
            "discount_authorized": False,
            "scope_expansion_authorized": False,
            "contract_authorized": False,
            "payment_authorized": False,
            "buyer_acceptance_inferred": False,
            "revenue_recognized": False,
        },
    }
    body["receipt_sha256"] = _digest(body)
    return body


def evaluate(router_raw: Any, policy_raw: Any, proposal_raw: Any) -> dict[str, Any]:
    """Evaluate one proposed commercial reply handling action.

    ``DRAFT_ALLOWED`` means only that the exact body digest may be prepared as a
    draft under the bound owner policy. Sending remains a separate explicit side
    effect.
    """
    router = _verify_router_receipt(router_raw)
    policy = _parse_policy(policy_raw)
    proposal = _parse_proposal(proposal_raw)
    reasons: list[str] = []

    for field in ("offer_id", "counterparty", "thread_id", "owner_id"):
        if router[field] != policy[field] or router[field] != proposal[field]:
            reasons.append(f"{field}_mismatch")
    if reasons:
        return _receipt(decision="HOLD", reasons=reasons, router=router, policy=policy, proposal=proposal)

    requested_at = proposal["requested_at"]
    router_evaluated_at = _time(router["evaluated_at"], "router_receipt.evaluated_at")
    if requested_at < policy["issued_at"]:
        reasons.append("proposal_predates_policy")
    if requested_at > policy["expires_at"]:
        reasons.append("policy_expired")
    if router_evaluated_at - requested_at > timedelta(seconds=MAX_FUTURE_SKEW_SECONDS):
        reasons.append("router_receipt_from_future")
    if requested_at - router_evaluated_at > timedelta(seconds=MAX_ROUTER_RECEIPT_AGE_SECONDS):
        reasons.append("router_receipt_stale")
    if reasons:
        return _receipt(decision="HOLD", reasons=reasons, router=router, policy=policy, proposal=proposal)

    if not proposal["history_complete"]:
        return _receipt(decision="HOLD", reasons=["reply_history_incomplete"], router=router, policy=policy, proposal=proposal)
    if proposal["inbound_message_id"] in proposal["handled_inbound_message_ids"]:
        return _receipt(decision="NO_ACTION", reasons=["inbound_event_already_handled"], router=router, policy=policy, proposal=proposal)

    action = router["action"]
    if router["hard_do_not_contact"] or action == "CLOSE_DO_NOT_CONTACT":
        return _receipt(decision="SUPPRESS", reasons=["router_do_not_contact"], router=router, policy=policy, proposal=proposal)
    if router["do_not_resend"] and action not in {"OWNER_REPLY_REQUIRED", "OWNER_REVIEW_REQUIRED"}:
        return _receipt(decision="SUPPRESS", reasons=["router_do_not_resend"], router=router, policy=policy, proposal=proposal)
    if action == "WAIT_NO_ACTION":
        return _receipt(decision="NO_ACTION", reasons=["router_wait_no_action"], router=router, policy=policy, proposal=proposal)
    if action == "ROUTE_REPAIR_REQUIRED":
        return _receipt(decision="ROUTE_REPAIR", reasons=["router_route_repair_required"], router=router, policy=policy, proposal=proposal)
    if action == "HOLD":
        return _receipt(decision="HOLD", reasons=["router_hold"], router=router, policy=policy, proposal=proposal)
    if action == "OWNER_REVIEW_REQUIRED":
        return _receipt(decision="OWNER_REVIEW_REQUIRED", reasons=["router_owner_review_required"], router=router, policy=policy, proposal=proposal)
    if action != "OWNER_REPLY_REQUIRED":
        return _receipt(decision="HOLD", reasons=["unsupported_router_action"], router=router, policy=policy, proposal=proposal)

    message_ids = router["relevant_message_ids"]
    if proposal["inbound_message_id"] not in message_ids:
        return _receipt(decision="HOLD", reasons=["inbound_message_not_bound_by_router"], router=router, policy=policy, proposal=proposal)
    if len(message_ids) != 1:
        return _receipt(decision="OWNER_REVIEW_REQUIRED", reasons=["multiple_relevant_inbound_events"], router=router, policy=policy, proposal=proposal)

    mode = proposal["mode"]
    if mode in SENSITIVE_MODES:
        return _receipt(decision="OWNER_REVIEW_REQUIRED", reasons=[f"sensitive_mode:{mode}"], router=router, policy=policy, proposal=proposal)
    if mode not in policy["allowed_draft_modes"]:
        return _receipt(decision="OWNER_REVIEW_REQUIRED", reasons=["draft_mode_not_preapproved"], router=router, policy=policy, proposal=proposal)
    return _receipt(decision="DRAFT_ALLOWED", reasons=["bound_factual_draft_mode_preapproved"], router=router, policy=policy, proposal=proposal)


def load_json(path: str | os.PathLike[str]) -> Any:
    source = Path(path)
    try:
        info = source.lstat()
    except FileNotFoundError as exc:
        raise GuardError(f"input does not exist: {source}") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise GuardError(f"input must be an ordinary regular file: {source}")
    with source.open("r", encoding="utf-8") as handle:
        return json.load(handle, object_pairs_hook=_strict_object)


def _aliases(left: Path, right: Path) -> bool:
    try:
        if os.path.abspath(left) == os.path.abspath(right):
            return True
        if left.exists() and right.exists() and os.path.samefile(left, right):
            return True
    except OSError:
        return True
    return False


def write_receipt_atomic(receipt: dict[str, Any], path: str | os.PathLike[str]) -> None:
    target = Path(path)
    if target.exists():
        info = target.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            raise GuardError("output must be an ordinary regular file")
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(receipt, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    fd, temp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent))
    temporary: Path | None = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        temporary = None
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--router-receipt", required=True)
    parser.add_argument("--policy", required=True)
    parser.add_argument("--proposal", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)

    router_path = Path(args.router_receipt)
    policy_path = Path(args.policy)
    proposal_path = Path(args.proposal)
    output_path = Path(args.output)
    inputs = [router_path, policy_path, proposal_path]
    for index, left in enumerate(inputs):
        for right in inputs[index + 1:]:
            if _aliases(left, right):
                raise GuardError("input files must be distinct")
        if _aliases(left, output_path):
            raise GuardError("output must not alias an input")

    receipt = evaluate(load_json(router_path), load_json(policy_path), load_json(proposal_path))
    write_receipt_atomic(receipt, output_path)
    print(json.dumps({"decision": receipt["decision"], "receipt_sha256": receipt["receipt_sha256"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
