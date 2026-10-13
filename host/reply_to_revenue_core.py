#!/usr/bin/env python3
"""Chronology-safe reply-to-revenue authority.

This module owns the complete evidence identity, chronology, contact-state, and
surface policy used by both direct imports and the wrapper entrypoint.

Authority boundary: installed runtime callables capture their dependency graph
at module initialization. Ordinary post-import rebinding of module attributes,
helpers, constants, or historical implementation aliases cannot change the
semantics of an already-installed entrypoint. This is a software-integrity
boundary, not a Python sandbox: arbitrary trusted same-process reflection
(``function.__closure__``, ``function.__globals__``, ctypes, monkeypatching the
callable a caller chooses to invoke, etc.) is outside this claim. Code that must
be isolated from hostile same-process Python requires a process/IPC boundary.

``reply_to_revenue_core_impl.source`` is retained only as historical source
context. It is not executed and is not a production dispatch namespace.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RECEIPTS_DIR = ROOT / "revenue" / "payment_ready" / "outreach_receipts"
OBSERVATIONS_PATH = ROOT / "revenue" / "reply_to_revenue" / "observations.json"
FUNNEL_PATH = ROOT / "revenue" / "reply_to_revenue" / "funnel.json"
ACCEPTANCE_TOOL = "revenue/production_survival/acceptance.py"
REPLY_INTAKE_TOOL = "revenue/production_survival/reply_intake.py"
ROUTE_RECOVERY_TOOL = "revenue/reply_to_revenue/DELIVERY_FAILURE_RECOVERY.md"
SCHEMA_VERSION = "commons-reply-to-revenue/v1"
KIND = "REPLY_TO_REVENUE_FUNNEL"

CLASSIFICATIONS = {
    "OPT_OUT",
    "AUTO_RESPONSE",
    "NEGATIVE",
    "QUESTION",
    "POSITIVE_SCOPE",
    "NEEDS_HUMAN",
}
CLASS_TO_NEXT = {
    "OPT_OUT": "DNC/CLOSE",
    "AUTO_RESPONSE": "WAIT_FOR_HUMAN_REPLY",
    "DELIVERY_FAILURE": "RECOVER_ROUTE_OWNER_REVIEW",
    "NEGATIVE": "CLOSE",
    "QUESTION": "DRAFT_REPLY",
    "POSITIVE_SCOPE": "NEEDS_ACCEPTANCE",
    "NEEDS_HUMAN": "ESCALATE_ONLY_IF_BUYER_REQUESTS_BRYCE",
}
HUMAN_STATE_CLASSIFICATIONS = frozenset(
    {"OPT_OUT", "NEGATIVE", "QUESTION", "POSITIVE_SCOPE", "NEEDS_HUMAN"}
)
DELIVERY_FAILURE_MARKERS = (
    "mailer-daemon",
    "delivery status notification (failure)",
    "delivery failure",
    "message blocked",
    "address not found",
    "undeliverable",
    "couldn't be delivered",
    "could not be delivered",
    "recipient address rejected",
    "user unknown",
    "mail system error",
)
AUTO_ACK_MARKERS = (
    "auto-submitted",
    "automatic reply",
    "auto reply",
    "autoreply",
    "auto-replied",
    "out of office",
    "out-of-office",
    "vacation responder",
    "noreply",
    "no-reply",
    "do-not-reply",
    "ticket has been created",
    "we have received your request",
    "thank you for reaching out",
    "this is an automated",
    "automated message",
    "this email is a service",
    "delivered by zendesk",
    "ai assistant",
    "ai agent",
    "this answer was composed by",
    "a human will respond",
    "rate the support you received",
    "how would you rate",
    "customer service survey",
    "csat",
)
POSITIVE_MARKERS = (
    "please invoice",
    "send the sow",
    "we want to proceed",
    "we accept the scope",
    "yes let's run the proof",
    "this is relevant, yes",
)

OPAQUE_RE = re.compile(r"^opaque:[A-Za-z0-9._:-]{8,200}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PROSPECT_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,80}$")
FORBIDDEN_CLAIM_RE = re.compile(
    r"\b(replied|accepted|invoiced|authorized|settled|delivered|paid)\b",
    re.IGNORECASE,
)

PUBLIC_LIMITS = [
    "ingest each inbound event_ref once; collision on same ref with a different full observation envelope",
    "bind every inbound observation to one unique canonical receipt for the same prospect",
    "automated acknowledgements are not buyer interest",
    "delivery failures require owner review of an alternate route; they never auto-resend",
    "HARD DNR and completed sends are never resent",
    "stale or silent contacts are monitored without a follow-up send",
    "POSITIVE_SCOPE stops at NEEDS_ACCEPTANCE; this tool does not accept, invoice, or collect",
    "cash_usd is 0 unless a named payment evidence URL is present",
    "no mailbox send, no second CRM, no secrets, no auth gate",
]

AUTHORITY_BOUNDARY = (
    "ordinary post-import module rebinding is outside the retained runtime graph; "
    "arbitrary trusted same-process Python reflection is not a security boundary"
)


class ReplyRevenueError(ValueError):
    """A funnel, observation, or transport plan failed closed."""


class CollisionError(ReplyRevenueError):
    """The same inbound event was presented with a different observation envelope."""


class ResendError(ReplyRevenueError):
    """A plan would contact a HARD DNR or otherwise send mail."""


def _make_runtime(
    *,
    root: Path,
    receipts_dir: Path,
    observations_path: Path,
    funnel_path: Path,
    acceptance_tool: str,
    reply_intake_tool: str,
    route_recovery_tool: str,
    schema_version: str,
    kind: str,
    classifications: frozenset[str],
    class_to_next: dict[str, str],
    human_state_classifications: frozenset[str],
    delivery_failure_markers: tuple[str, ...],
    auto_ack_markers: tuple[str, ...],
    positive_markers: tuple[str, ...],
    public_limits: tuple[str, ...],
    opaque_fullmatch: Any,
    sha_fullmatch: Any,
    email_fullmatch: Any,
    prospect_fullmatch: Any,
    forbidden_search: Any,
    json_loads: Any,
    json_dumps: Any,
    json_decode_error: type[Exception],
    sha256_callable: Any,
    datetime_fromisoformat: Any,
    utc: Any,
    regex_sub: Any,
    argument_parser: Any,
    path_type: type[Path],
    reply_error: type[Exception],
    collision_error: type[Exception],
    resend_error: type[Exception],
    stderr: Any,
) -> dict[str, Any]:
    """Create runtime callables whose semantic dependencies are captured once."""

    _root = root
    _receipts_dir = receipts_dir
    _observations_path = observations_path
    _funnel_path = funnel_path
    _acceptance_tool = acceptance_tool
    _reply_intake_tool = reply_intake_tool
    _route_recovery_tool = route_recovery_tool
    _schema_version = schema_version
    _kind = kind
    _classes = frozenset(classifications)
    _class_to_next = dict(class_to_next)
    _human_classes = frozenset(human_state_classifications)
    _machine_classes = frozenset({"DELIVERY_FAILURE", "AUTO_RESPONSE"})
    _known_contact_classes = _human_classes | _machine_classes
    _failure_markers = tuple(delivery_failure_markers)
    _auto_markers = tuple(auto_ack_markers)
    _positive_markers = tuple(positive_markers)
    _public_limits = tuple(public_limits)

    _opaque_fullmatch = opaque_fullmatch
    _sha_fullmatch = sha_fullmatch
    _email_fullmatch = email_fullmatch
    _prospect_fullmatch = prospect_fullmatch
    _forbidden_search = forbidden_search
    _json_loads = json_loads
    _json_dumps = json_dumps
    _json_decode_error = json_decode_error
    _sha256 = sha256_callable
    _fromisoformat = datetime_fromisoformat
    _utc = utc
    _regex_sub = regex_sub
    _argument_parser = argument_parser
    _path_type = path_type
    _reply_error = reply_error
    _collision_error = collision_error
    _resend_error = resend_error
    _stderr = stderr

    _isinstance = isinstance
    _type = type
    _int = int
    _str = str
    _bool = bool
    _list = list
    _dict = dict
    _set = set
    _sorted = sorted
    _all = all
    _len = len
    _sum = sum
    _max = max
    _min = min
    _next_builtin = next
    _iter = iter
    _enumerate = enumerate
    _print = print
    _os_error = OSError
    _type_error = TypeError
    _value_error = ValueError

    def bounded_provenance_scalar(value: Any, where: str) -> str:
        if _type(value) is not _str:
            raise _reply_error(f"{where} must be a string")
        if not value or value != value.strip() or _len(value) > 200:
            raise _reply_error(
                f"{where} must be a nonempty trimmed string of at most 200 characters"
            )
        return value

    def canonical_text(value: Any) -> str:
        return _json_dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n"

    def sha256_text(value: str) -> str:
        return _sha256(value.encode("utf-8")).hexdigest()

    def read_object(path: Path) -> dict[str, Any]:
        try:
            value = _json_loads(path.read_text(encoding="utf-8"))
        except (_os_error, _json_decode_error) as error:
            raise _reply_error(f"cannot read JSON object {path}: {error}") from error
        if not _isinstance(value, _dict):
            raise _reply_error(f"{path} must contain one JSON object")
        return value

    def parse_time(value: str) -> Any:
        text = value[:-1] + "+00:00" if value.endswith("Z") else value
        try:
            parsed = _fromisoformat(text)
        except (_type_error, _value_error) as error:
            raise _reply_error(f"invalid date-time: {value}") from error
        if parsed.tzinfo is None:
            raise _reply_error("date-time must include a timezone")
        return parsed.astimezone(_utc)

    def assert_observation_window(
        measured_at_value: Any,
        events: list[Any],
    ) -> None:
        if not _isinstance(measured_at_value, _str):
            raise _reply_error("observations.measured_at must be a date-time string")
        measured_at = parse_time(measured_at_value)
        for index, event in _enumerate(events):
            where = f"events[{index}]"
            if not _isinstance(event, _dict):
                raise _reply_error(f"{where} must be an object")
            received_at_value = event.get("received_at")
            if not _isinstance(received_at_value, _str):
                raise _reply_error(f"{where}.received_at must be a date-time string")
            if parse_time(received_at_value) > measured_at:
                raise _reply_error(
                    f"{where}.received_at exceeds observations.measured_at"
                )

    def normalize_email(value: str) -> str:
        normalized = value.strip().lower()
        if _email_fullmatch(normalized) is None or _len(normalized) > 254:
            raise _reply_error(f"invalid email address: {value}")
        return normalized

    def organization_key(value: str) -> str:
        return "".join(character for character in value.casefold() if character.isalnum())

    def exact_keys(value: dict[str, Any], expected: set[str], where: str) -> None:
        actual = _set(value)
        if actual != expected:
            raise _reply_error(
                f"{where} fields differ: "
                f"missing={_sorted(expected - actual)} extra={_sorted(actual - expected)}"
            )

    def assert_no_forbidden_claims(blob: str) -> None:
        match = _forbidden_search(blob)
        if match:
            raise _reply_error(f"funnel emitted forbidden claim {match.group(0)!r}")

    def classify_signals(
        markers: list[str],
        requested: str | None = None,
    ) -> dict[str, Any]:
        if not _isinstance(markers, _list) or not _all(
            _isinstance(item, _str) and item.strip() for item in markers
        ):
            raise _reply_error("markers must be nonempty strings")
        blob = " ".join(item.casefold() for item in markers)

        matched_failure = [marker for marker in _failure_markers if marker in blob]
        if matched_failure:
            reason = (
                "delivery-failure markers override a human-response claim"
                if requested in {"POSITIVE_SCOPE", "QUESTION", "NEEDS_HUMAN"}
                else "delivery failed; owner must review an alternate route before any new contact"
            )
            return {
                "classification": "DELIVERY_FAILURE",
                "next_action": _class_to_next["DELIVERY_FAILURE"],
                "buyer_interest": False,
                "auto_ack": False,
                "delivery_failure": True,
                "matched_markers": matched_failure,
                "reason": reason,
            }

        matched_auto = [marker for marker in _auto_markers if marker in blob]
        if matched_auto:
            reason = (
                "auto-ack markers override a positivity or question claim"
                if requested in {"POSITIVE_SCOPE", "QUESTION"}
                else "automated acknowledgement is not buyer interest"
            )
            return {
                "classification": "AUTO_RESPONSE",
                "next_action": _class_to_next["AUTO_RESPONSE"],
                "buyer_interest": False,
                "auto_ack": True,
                "delivery_failure": False,
                "matched_markers": matched_auto,
                "reason": reason,
            }

        if requested is not None:
            if requested not in _classes:
                raise _reply_error(f"unknown classification: {requested}")
            return {
                "classification": requested,
                "next_action": _class_to_next[requested],
                "buyer_interest": requested == "POSITIVE_SCOPE",
                "auto_ack": False,
                "delivery_failure": False,
                "matched_markers": [],
                "reason": "operator classification with no delivery-failure or auto-ack markers",
            }

        matched_positive = [marker for marker in _positive_markers if marker in blob]
        if matched_positive:
            return {
                "classification": "POSITIVE_SCOPE",
                "next_action": _class_to_next["POSITIVE_SCOPE"],
                "buyer_interest": True,
                "auto_ack": False,
                "delivery_failure": False,
                "matched_markers": matched_positive,
                "reason": "explicit buyer-scope language with no delivery-failure or auto-ack markers",
            }

        return {
            "classification": "NEEDS_HUMAN",
            "next_action": _class_to_next["NEEDS_HUMAN"],
            "buyer_interest": False,
            "auto_ack": False,
            "delivery_failure": False,
            "matched_markers": [],
            "reason": "no delivery-failure, auto-ack, or explicit buyer-scope language",
        }

    def load_receipts(directory: Path = _receipts_dir) -> list[dict[str, Any]]:
        receipts: list[dict[str, Any]] = []
        seen_receipt_ids: set[str] = _set()
        for path in _sorted(directory.glob("*.json")):
            receipt = read_object(path)
            relative = (
                path.relative_to(_root).as_posix()
                if path.is_relative_to(_root)
                else path.name
            )
            raw_receipt_id = (
                receipt["receipt_id"] if "receipt_id" in receipt else path.stem
            )
            receipt_id = bounded_provenance_scalar(
                raw_receipt_id,
                f"{relative}.receipt_id",
            )
            if receipt_id in seen_receipt_ids:
                raise _reply_error(
                    f"duplicate canonical receipt_id: {receipt_id}"
                )
            seen_receipt_ids.add(receipt_id)
            recipient = receipt.get("recipient_email")
            organization = (
                receipt.get("organization") or receipt.get("target_id") or path.stem
            )
            target_id = receipt.get("target_id")
            if not _isinstance(target_id, _str) or not target_id.strip():
                target_id = path.stem.split("-")[1] if "-" in path.stem else path.stem
            prospect_key = _regex_sub(
                r"[^a-z0-9._-]",
                "-",
                _str(target_id).casefold(),
            )
            if _prospect_fullmatch(prospect_key) is None:
                prospect_key = "contact." + sha256_text(path.name)[:12]
            dedupe = receipt.get("dedupe") if _isinstance(receipt.get("dedupe"), _dict) else {}
            hard_dnr = (
                dedupe.get("do_not_resend") is True
                or receipt.get("provider_state") == "COMPLETED"
            )
            cash = 0
            facts = receipt.get("facts") if _isinstance(receipt.get("facts"), _dict) else {}
            if _type(facts.get("collected_cash_usd")) is _int:
                cash = facts["collected_cash_usd"]
            receipts.append(
                {
                    "path": relative,
                    "receipt_id": receipt_id,
                    "prospect_key": prospect_key,
                    "organization": organization
                    if _isinstance(organization, _str)
                    else prospect_key,
                    "recipient_email": normalize_email(recipient)
                    if _isinstance(recipient, _str)
                    else None,
                    "provider_reference": receipt.get("provider_reference"),
                    "provider_state": receipt.get("provider_state"),
                    "response_state": receipt.get("response_state") or "UNKNOWN",
                    "hard_dnr": _bool(hard_dnr),
                    "cash_usd": cash,
                    "observed_at": receipt.get("observed_at")
                    or receipt.get("provider_completed_at"),
                }
            )
        if not receipts:
            raise _reply_error("no canonical outreach receipts found")
        return receipts

    def load_observations(path: Path = _observations_path) -> dict[str, Any]:
        # One read defines one immutable observation generation for this call.
        value = read_object(path)
        exact_keys(
            value,
            {"schema_version", "kind", "measured_at", "monitor", "events"},
            "observations",
        )
        if value["schema_version"] != "commons-reply-to-revenue-observations/v1":
            raise _reply_error("unsupported observations version")
        if value["kind"] != "REPLY_TO_REVENUE_OBSERVATIONS":
            raise _reply_error("unsupported observations kind")
        parse_time(value["measured_at"])

        monitor = value["monitor"]
        if not _isinstance(monitor, _dict):
            raise _reply_error("monitor must be an object")
        exact_keys(
            monitor,
            {
                "connector",
                "status",
                "mailbox_claim",
                "sends",
                "queries",
                "attributed_inbound",
            },
            "monitor",
        )
        if _type(monitor["sends"]) is not _int or monitor["sends"] != 0:
            raise _reply_error("monitor.sends must be 0")
        if _type(monitor["queries"]) is not _int or monitor["queries"] < 0:
            raise _reply_error("monitor.queries must be a non-negative integer")
        if (
            _type(monitor["attributed_inbound"]) is not _int
            or monitor["attributed_inbound"] < 0
        ):
            raise _reply_error(
                "monitor.attributed_inbound must be a non-negative integer"
            )

        events = value["events"]
        if not _isinstance(events, _list):
            raise _reply_error("events must be an array")

        seen_refs: dict[str, str] = {}
        seen_hashes: dict[str, str] = {}
        cleaned: list[dict[str, Any]] = []
        fields = {
            "event_ref",
            "received_at",
            "prospect_key",
            "payload_sha256",
            "markers",
            "provider",
            "matched_receipt_id",
            "requested_classification",
        }

        for index, event in _enumerate(events):
            where = f"events[{index}]"
            if not _isinstance(event, _dict):
                raise _reply_error(f"{where} must be an object")
            exact_keys(event, fields, where)
            if _opaque_fullmatch(event["event_ref"]) is None:
                raise _reply_error(f"{where}.event_ref is invalid")
            parse_time(event["received_at"])
            if _prospect_fullmatch(event["prospect_key"]) is None:
                raise _reply_error(f"{where}.prospect_key is invalid")
            if _sha_fullmatch(event["payload_sha256"]) is None:
                raise _reply_error(f"{where}.payload_sha256 is invalid")
            if not _isinstance(event["markers"], _list):
                raise _reply_error(f"{where}.markers must be an array")
            provider = bounded_provenance_scalar(
                event["provider"],
                f"{where}.provider",
            )
            matched_receipt_id = bounded_provenance_scalar(
                event["matched_receipt_id"],
                f"{where}.matched_receipt_id",
            )
            requested = event["requested_classification"]
            if requested is not None and requested not in _classes:
                raise _reply_error(f"{where}.requested_classification is invalid")

            # Identity is the entire raw observation envelope, not only payload bytes.
            identity = sha256_text(canonical_text(event))
            previous = seen_refs.get(event["event_ref"])
            if previous is not None and previous != identity:
                raise _collision_error(
                    "duplicate event_ref with different observation envelope: "
                    f"{event['event_ref']}"
                )
            hashed = seen_hashes.get(event["payload_sha256"])
            if hashed and hashed != event["event_ref"]:
                raise _collision_error(
                    "duplicate payload_sha256 under a second event_ref"
                )
            if previous is not None:
                continue

            seen_refs[event["event_ref"]] = identity
            seen_hashes[event["payload_sha256"]] = event["event_ref"]
            verdict = classify_signals(event["markers"], requested)
            cleaned.append(
                {
                    "event_ref": event["event_ref"],
                    "received_at": event["received_at"],
                    "prospect_key": event["prospect_key"],
                    "payload_sha256": event["payload_sha256"],
                    "provider": provider,
                    "matched_receipt_id": matched_receipt_id,
                    **verdict,
                }
            )

        if monitor["attributed_inbound"] != _len(cleaned):
            raise _reply_error(
                "monitor.attributed_inbound does not match ingested unique events"
            )

        result = _dict(value)
        result["events"] = cleaned
        assert_observation_window(result["measured_at"], cleaned)
        return result

    def latest_event(events: list[dict[str, Any]]) -> dict[str, Any]:
        if not events:
            raise _reply_error("cannot select the latest event from an empty set")
        return _max(
            events,
            key=lambda item: (
                parse_time(_str(item["received_at"])),
                _str(item.get("event_ref") or ""),
            ),
        )

    def latest_human_bucket(
        events: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        semantic = [
            event
            for event in events
            if event.get("classification") in _human_classes
        ]
        if not semantic:
            return []
        stamped = [
            (parse_time(_str(event["received_at"])), event)
            for event in semantic
        ]
        latest_time = _max(stamp for stamp, _ in stamped)
        return [event for stamp, event in stamped if stamp == latest_time]

    def reduce_contact_state(events: list[dict[str, Any]]) -> dict[str, Any]:
        if not events:
            return {
                "classification": None,
                "lane": "NO_RESPONSE",
                "next_action": "MONITOR_NO_RESEND",
                "handoff": None,
                "effective_event": None,
            }

        unknown = _sorted(
            {
                _str(event.get("classification"))
                for event in events
                if event.get("classification") not in _known_contact_classes
            }
        )
        if unknown:
            raise _reply_error(
                f"contact state contains unknown classifications: {unknown}"
            )

        semantic = [
            event for event in events if event["classification"] in _human_classes
        ]
        effective_event: dict[str, Any] | None

        if semantic:
            latest_semantic = latest_human_bucket(events)
            opt_outs = [
                event
                for event in latest_semantic
                if event.get("classification") == "OPT_OUT"
            ]
            if opt_outs:
                classification = "OPT_OUT"
                effective_event = _min(
                    opt_outs,
                    key=lambda item: _str(item.get("event_ref") or ""),
                )
            else:
                latest_classes = {
                    event["classification"] for event in latest_semantic
                }
                if _len(latest_classes) != 1:
                    classification = "NEEDS_HUMAN"
                    effective_event = None
                else:
                    classification = _next_builtin(_iter(latest_classes))
                    effective_event = _min(
                        latest_semantic,
                        key=lambda item: _str(item.get("event_ref") or ""),
                    )
        else:
            failures = [
                event
                for event in events
                if event["classification"] == "DELIVERY_FAILURE"
            ]
            if failures:
                classification = "DELIVERY_FAILURE"
                effective_event = latest_event(failures)
            else:
                auto = [
                    event
                    for event in events
                    if event["classification"] == "AUTO_RESPONSE"
                ]
                classification = "AUTO_RESPONSE"
                effective_event = latest_event(auto)

        if classification == "POSITIVE_SCOPE":
            lane, next_action, handoff = (
                "HUMAN_POSITIVE",
                "NEEDS_ACCEPTANCE",
                _acceptance_tool,
            )
        elif classification == "QUESTION":
            lane, next_action, handoff = (
                "HUMAN_QUESTION",
                "DRAFT_REPLY",
                _reply_intake_tool,
            )
        elif classification == "OPT_OUT":
            lane, next_action, handoff = "CLOSED", "DNC/CLOSE", None
        elif classification == "NEGATIVE":
            lane, next_action, handoff = "CLOSED", "CLOSE", None
        elif classification == "DELIVERY_FAILURE":
            lane, next_action, handoff = (
                "DELIVERY_FAILURE",
                "RECOVER_ROUTE_OWNER_REVIEW",
                _route_recovery_tool,
            )
        elif classification == "AUTO_RESPONSE":
            lane, next_action, handoff = (
                "AUTO_ACK_WAIT",
                "WAIT_FOR_HUMAN_REPLY",
                None,
            )
        else:
            lane, next_action, handoff = (
                "NEEDS_HUMAN",
                "ESCALATE_ONLY_IF_BUYER_REQUESTS_BRYCE",
                None,
            )

        return {
            "classification": classification,
            "lane": lane,
            "next_action": next_action,
            "handoff": handoff,
            "effective_event": effective_event,
        }

    def contact_rows(
        receipts: list[dict[str, Any]],
        inbound: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not _isinstance(receipts, _list):
            raise _reply_error("receipts must be an array")
        if not _isinstance(inbound, _list):
            raise _reply_error("inbound events must be an array")

        grouped: dict[str, dict[str, Any]] = {}
        by_receipt: dict[str, str] = {}
        for index, receipt in _enumerate(receipts):
            where = f"receipts[{index}]"
            if not _isinstance(receipt, _dict):
                raise _reply_error(f"{where} must be an object")
            receipt_id = bounded_provenance_scalar(
                receipt.get("receipt_id"),
                f"{where}.receipt_id",
            )
            if receipt_id in by_receipt:
                raise _reply_error(
                    f"duplicate canonical receipt_id: {receipt_id}"
                )
            key = receipt.get("prospect_key")
            if _type(key) is not _str or _prospect_fullmatch(key) is None:
                raise _reply_error(f"{where}.prospect_key is invalid")
            by_receipt[receipt_id] = key

            row = grouped.setdefault(
                key,
                {
                    "prospect_key": key,
                    "organization": receipt["organization"],
                    "hard_dnr": False,
                    "receipt_ids": [],
                    "receipt_paths": [],
                    "cash_usd": 0,
                    "inbound_event_refs": [],
                    "events": [],
                },
            )
            row["hard_dnr"] = row["hard_dnr"] or receipt["hard_dnr"]
            row["receipt_ids"].append(receipt_id)
            row["receipt_paths"].append(receipt["path"])
            row["cash_usd"] += receipt["cash_usd"]
            if not _isinstance(row["organization"], _str) or not row["organization"].strip():
                row["organization"] = receipt["organization"]

        for index, event in _enumerate(inbound):
            where = f"inbound[{index}]"
            if not _isinstance(event, _dict):
                raise _reply_error(f"{where} must be an object")
            matched_receipt_id = bounded_provenance_scalar(
                event.get("matched_receipt_id"),
                f"{where}.matched_receipt_id",
            )
            key = event.get("prospect_key")
            if _type(key) is not _str or _prospect_fullmatch(key) is None:
                raise _reply_error(f"{where}.prospect_key is invalid")
            canonical_key = by_receipt.get(matched_receipt_id)
            if canonical_key is None:
                # Empty receipts remain a measurement path. Unmatched OPT_OUT
                # stays HARD DNR / CLOSED without a live canonical receipt.
                # Ordinary inbound with a non-empty receipt set still fails
                # closed on unknown receipt IDs.
                if _len(receipts) != 0 and event.get("classification") != "OPT_OUT":
                    raise _reply_error(
                        f"{where}.matched_receipt_id is not a canonical receipt: "
                        f"{matched_receipt_id}"
                    )
            elif canonical_key != key:
                raise _reply_error(
                    f"{where} receipt/prospect mismatch: receipt "
                    f"{matched_receipt_id} belongs to {canonical_key}, not {key}"
                )
            row = grouped.get(key)
            if row is None:
                row = {
                    "prospect_key": key,
                    "organization": key,
                    "hard_dnr": True,
                    "receipt_ids": [],
                    "receipt_paths": [],
                    "cash_usd": 0,
                    "inbound_event_refs": [],
                    "events": [],
                }
                grouped[key] = row
            row["inbound_event_refs"].append(event["event_ref"])
            row["events"].append(event)

        rows: list[dict[str, Any]] = []
        for row in grouped.values():
            state = reduce_contact_state(row["events"])
            rows.append(
                {
                    "prospect_key": row["prospect_key"],
                    "organization": row["organization"],
                    "hard_dnr": True
                    if row["hard_dnr"] or row["receipt_ids"]
                    else row["hard_dnr"],
                    "lane": state["lane"],
                    "next_action": state["next_action"],
                    "handoff": state["handoff"],
                    "receipt_count": _len(row["receipt_ids"]),
                    "inbound_count": _len(row["inbound_event_refs"]),
                    "cash_usd": row["cash_usd"],
                    "resend": False,
                }
            )
        rows.sort(key=lambda item: (item["lane"], item["prospect_key"]))
        return rows

    def positive_context(events: list[dict[str, Any]]) -> str:
        machine_classes = _sorted(
            {
                _str(event.get("classification"))
                for event in events
                if event.get("classification") in _machine_classes
            }
        )
        if not machine_classes:
            return (
                "effective human inbound classified POSITIVE_SCOPE; "
                "no machine delivery-failure or auto-response observations were recorded"
            )
        recorded = ", ".join(machine_classes)
        return (
            "effective human inbound classified POSITIVE_SCOPE; "
            f"recorded machine observations ({recorded}) do not override human semantics"
        )

    def surface_positives(
        contacts: list[dict[str, Any]],
        inbound: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        positives: list[dict[str, Any]] = []
        inbound_by_key: dict[str, list[dict[str, Any]]] = {}
        for event in inbound:
            inbound_by_key.setdefault(event["prospect_key"], []).append(event)

        for contact in contacts:
            if contact["lane"] != "HUMAN_POSITIVE":
                continue
            events = inbound_by_key.get(contact["prospect_key"], [])
            state = reduce_contact_state(events)
            effective_event = state["effective_event"]
            if state["lane"] != "HUMAN_POSITIVE" or effective_event is None:
                raise _reply_error(
                    f"positive contact {contact['prospect_key']} lacks an effective POSITIVE_SCOPE event"
                )
            if effective_event.get("classification") != "POSITIVE_SCOPE":
                raise _reply_error(
                    f"positive contact {contact['prospect_key']} resolved to non-positive evidence"
                )
            positives.append(
                {
                    "prospect_key": contact["prospect_key"],
                    "organization": contact["organization"],
                    "event_ref": effective_event["event_ref"],
                    "received_at": effective_event["received_at"],
                    "next_action": "NEEDS_ACCEPTANCE",
                    "handoff": _acceptance_tool,
                    "context": positive_context(events),
                    "buyer_interest": True,
                }
            )
        positives.sort(key=lambda item: item["prospect_key"])
        return positives

    def surface_route_recovery(
        contacts: list[dict[str, Any]],
        inbound: list[dict[str, Any]],
    ) -> dict[str, Any]:
        inbound_by_key: dict[str, list[dict[str, Any]]] = {}
        for event in inbound:
            inbound_by_key.setdefault(event["prospect_key"], []).append(event)

        items: list[dict[str, Any]] = []
        for contact in contacts:
            if contact["lane"] != "DELIVERY_FAILURE":
                continue
            failures = [
                event
                for event in inbound_by_key.get(contact["prospect_key"], [])
                if event.get("classification") == "DELIVERY_FAILURE"
            ]
            latest = latest_event(failures) if failures else None
            items.append(
                {
                    "prospect_key": contact["prospect_key"],
                    "organization": contact["organization"],
                    "event_ref": None if latest is None else latest["event_ref"],
                    "received_at": None if latest is None else latest["received_at"],
                    "next_action": "RECOVER_ROUTE_OWNER_REVIEW",
                    "handoff": _route_recovery_tool,
                    "buyer_interest": False,
                    "resend": False,
                    "authority": "OWNER_REVIEW_ONLY",
                }
            )
        items.sort(key=lambda item: item["prospect_key"])
        return {
            "classification": "DELIVERY_FAILURE",
            "count": _len(items),
            "items": items,
            "transport_actions": 0,
            "resends": 0,
            "authority": "OWNER_REVIEW_ONLY",
        }

    def build_funnel(
        receipts: list[dict[str, Any]] | None = None,
        observations: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        receipt_rows = receipts if receipts is not None else load_receipts()
        observed = observations if observations is not None else load_observations()

        if not _isinstance(observed, _dict):
            raise _reply_error("observations must be an object")
        measured_at = observed.get("measured_at")
        event_source = observed.get("events")
        if not _isinstance(event_source, _list):
            raise _reply_error("observations.events must be an array")
        inbound = [
            _dict(event) if _isinstance(event, _dict) else event
            for event in event_source
        ]
        assert_observation_window(measured_at, inbound)

        contacts = contact_rows(receipt_rows, inbound)
        for contact in contacts:
            if contact["cash_usd"] and not contact.get("payment_evidence"):
                if contact["cash_usd"] != 0:
                    raise _reply_error(
                        "cash_usd without payment evidence is forbidden"
                    )
            contact["hard_dnr"] = True
            contact["resend"] = False

        surfaces = surface_positives(contacts, inbound)
        cash = _sum(contact["cash_usd"] for contact in contacts)
        if cash != 0:
            raise _reply_error("cash_usd must stay 0 without payment evidence")

        counts = {
            "canonical_receipts": _len(receipt_rows),
            "distinct_contacts": _len(contacts),
            "hard_dnr_contacts": _sum(
                1 for contact in contacts if contact["hard_dnr"]
            ),
            "inbound_recorded": _len(inbound),
            "auto_acks": _sum(1 for event in inbound if event["auto_ack"]),
            "delivery_failures": _sum(
                1
                for event in inbound
                if event.get("delivery_failure") is True
            ),
            "human_positive": _sum(
                1 for contact in contacts if contact["lane"] == "HUMAN_POSITIVE"
            ),
            "human_question": _sum(
                1 for contact in contacts if contact["lane"] == "HUMAN_QUESTION"
            ),
            "no_response": _sum(
                1 for contact in contacts if contact["lane"] == "NO_RESPONSE"
            ),
            "scope_acceptances": 0,
            "payment_evidence": 0,
            "cash_usd": 0,
            "resends": 0,
            "transport_actions": 0,
        }
        stages = [
            {"id": "SENT_COMPLETED", "count": counts["distinct_contacts"]},
            {"id": "HARD_DNR", "count": counts["hard_dnr_contacts"]},
            {"id": "INBOUND_RECORDED", "count": counts["inbound_recorded"]},
            {"id": "AUTO_ACK", "count": counts["auto_acks"]},
            {"id": "DELIVERY_FAILURE", "count": counts["delivery_failures"]},
            {"id": "HUMAN_POSITIVE", "count": counts["human_positive"]},
            {"id": "NEEDS_ACCEPTANCE", "count": counts["human_positive"]},
            {"id": "SCOPE_ACCEPTANCE", "count": 0},
            {"id": "PAYMENT_EVIDENCE", "count": 0},
            {"id": "BANK_AVAILABLE", "count": 0},
        ]
        funnel = {
            "schema_version": _schema_version,
            "kind": _kind,
            "measured_at": measured_at,
            "truth": counts,
            "stages": stages,
            "contacts": contacts,
            "inbound": [
                {
                    "event_ref": event["event_ref"],
                    "received_at": event["received_at"],
                    "prospect_key": event["prospect_key"],
                    "classification": event["classification"],
                    "next_action": event["next_action"],
                    "auto_ack": event["auto_ack"],
                    "buyer_interest": event["buyer_interest"],
                    "reason": event["reason"],
                    "matched_receipt_id": event["matched_receipt_id"],
                }
                for event in inbound
            ],
            "surfaces": surfaces,
            "monitor": _dict(observed["monitor"]),
            "limits": _list(_public_limits),
            "handoffs": {
                "reply_intake": _reply_intake_tool,
                "acceptance": _acceptance_tool,
                "smart_outreach": "host/smart_outreach.py",
                "swarm_mail": "host/swarm_mail.py",
                "cash_now": "host/cash_now.py",
            },
        }
        assert_no_forbidden_claims(canonical_text(funnel))
        return funnel

    def assert_no_resend(
        funnel: dict[str, Any],
        *,
        send: bool = False,
    ) -> None:
        if send:
            raise _resend_error(
                "reply-to-revenue never sends; stale contacts are monitored without resend"
            )
        if (
            funnel["truth"]["resends"] != 0
            or funnel["truth"]["transport_actions"] != 0
        ):
            raise _resend_error("funnel claimed a transport action")
        for contact in funnel["contacts"]:
            if contact.get("resend"):
                raise _resend_error(
                    f"contact {contact['prospect_key']} marked resend"
                )
            if contact["hard_dnr"] is not True:
                raise _resend_error(
                    f"contact {contact['prospect_key']} is missing HARD DNR"
                )

    def validate_funnel(path: Path = _funnel_path) -> dict[str, Any]:
        expected = build_funnel()
        actual = read_object(path)
        if actual != expected:
            raise _reply_error(
                "committed funnel snapshot differs from compiled sources"
            )
        assert_no_resend(actual, send=False)
        if actual["truth"]["cash_usd"] != 0:
            raise _reply_error("cash_usd is not 0")
        if actual["truth"]["human_positive"] != _len(actual["surfaces"]):
            raise _reply_error("positive surfaces drifted from truth")
        return actual

    def build_parser() -> Any:
        parser = _argument_parser(
            description=(
                "Always-on reply-to-revenue composition for Commons. "
                "Read-only evidence reducer; never sends."
            )
        )
        subparsers = parser.add_subparsers(dest="command", required=True)
        snap = subparsers.add_parser("snapshot")
        snap.add_argument("--output", type=_path_type)
        subparsers.add_parser("validate")
        subparsers.add_parser("surface")
        subparsers.add_parser("recover")
        classify = subparsers.add_parser("classify")
        classify.add_argument(
            "--markers",
            required=True,
            help="comma-separated public-safe markers",
        )
        classify.add_argument("--requested", choices=_sorted(_classes))
        monitor = subparsers.add_parser("monitor")
        monitor.add_argument(
            "--send",
            action="store_true",
            help="illegal; always refused",
        )
        return parser

    def main(argv: list[str] | None = None) -> int:
        args = build_parser().parse_args(argv)
        try:
            if args.command == "classify":
                markers = [
                    item.strip()
                    for item in args.markers.split(",")
                    if item.strip()
                ]
                _print(
                    canonical_text(
                        classify_signals(markers, args.requested)
                    ),
                    end="",
                )
                return 0

            funnel = build_funnel()
            if args.command == "validate":
                validate_funnel()
                truth = funnel["truth"]
                _print(
                    "VALID "
                    f"{truth['distinct_contacts']} contacts "
                    f"{truth['inbound_recorded']} inbound "
                    f"{truth['auto_acks']} auto-acks "
                    f"{truth['delivery_failures']} delivery-failures "
                    f"{truth['human_positive']} human-positive "
                    f"{truth['resends']} resends "
                    f"USD {truth['cash_usd']} cash"
                )
                return 0
            if args.command == "surface":
                _print(canonical_text(funnel["surfaces"]), end="")
                return 0
            if args.command == "recover":
                _print(
                    canonical_text(
                        surface_route_recovery(
                            funnel["contacts"],
                            funnel["inbound"],
                        )
                    ),
                    end="",
                )
                return 0
            if args.command == "monitor":
                assert_no_resend(funnel, send=args.send)
                _print(canonical_text(funnel), end="")
                return 0

            rendered = canonical_text(funnel)
            if args.output:
                args.output.write_text(rendered, encoding="utf-8")
            else:
                _print(rendered, end="")
            return 0
        except _collision_error as error:
            _print(_str(error), file=_stderr)
            return 2
        except _resend_error as error:
            _print(_str(error), file=_stderr)
            return 3
        except _reply_error as error:
            _print(_str(error), file=_stderr)
            return 1

    return {
        "canonical_text": canonical_text,
        "sha256_text": sha256_text,
        "read_object": read_object,
        "parse_time": parse_time,
        "_assert_observation_window": assert_observation_window,
        "normalize_email": normalize_email,
        "organization_key": organization_key,
        "_bounded_provenance_scalar": bounded_provenance_scalar,
        "_exact_keys": exact_keys,
        "_assert_no_forbidden_claims": assert_no_forbidden_claims,
        "classify_signals": classify_signals,
        "load_receipts": load_receipts,
        "load_observations": load_observations,
        "_latest_event": latest_event,
        "_latest_human_bucket": latest_human_bucket,
        "_reduce_contact_state": reduce_contact_state,
        "_contact_rows": contact_rows,
        "_positive_context": positive_context,
        "surface_positives": surface_positives,
        "surface_route_recovery": surface_route_recovery,
        "build_funnel": build_funnel,
        "assert_no_resend": assert_no_resend,
        "validate_funnel": validate_funnel,
        "build_parser": build_parser,
        "main": main,
    }


_RUNTIME = _make_runtime(
    root=ROOT,
    receipts_dir=RECEIPTS_DIR,
    observations_path=OBSERVATIONS_PATH,
    funnel_path=FUNNEL_PATH,
    acceptance_tool=ACCEPTANCE_TOOL,
    reply_intake_tool=REPLY_INTAKE_TOOL,
    route_recovery_tool=ROUTE_RECOVERY_TOOL,
    schema_version=SCHEMA_VERSION,
    kind=KIND,
    classifications=frozenset(CLASSIFICATIONS),
    class_to_next=dict(CLASS_TO_NEXT),
    human_state_classifications=frozenset(HUMAN_STATE_CLASSIFICATIONS),
    delivery_failure_markers=tuple(DELIVERY_FAILURE_MARKERS),
    auto_ack_markers=tuple(AUTO_ACK_MARKERS),
    positive_markers=tuple(POSITIVE_MARKERS),
    public_limits=tuple(PUBLIC_LIMITS),
    opaque_fullmatch=OPAQUE_RE.fullmatch,
    sha_fullmatch=SHA256_RE.fullmatch,
    email_fullmatch=EMAIL_RE.fullmatch,
    prospect_fullmatch=PROSPECT_RE.fullmatch,
    forbidden_search=FORBIDDEN_CLAIM_RE.search,
    json_loads=json.loads,
    json_dumps=json.dumps,
    json_decode_error=json.JSONDecodeError,
    sha256_callable=hashlib.sha256,
    datetime_fromisoformat=dt.datetime.fromisoformat,
    utc=dt.timezone.utc,
    regex_sub=re.sub,
    argument_parser=argparse.ArgumentParser,
    path_type=Path,
    reply_error=ReplyRevenueError,
    collision_error=CollisionError,
    resend_error=ResendError,
    stderr=sys.stderr,
)

for _runtime_name, _runtime_value in _RUNTIME.items():
    globals()[_runtime_name] = _runtime_value

del _runtime_name, _runtime_value, _RUNTIME, _make_runtime


if __name__ == "__main__":
    raise SystemExit(main())
