"""Deterministic, non-authorizing AI-IVR validation evidence compiler.

This module evaluates synthetic or separately captured candidate traces. It never
places calls, sends messages, contacts a buyer, or authenticates procurement facts.
"""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

SCHEMA_VERSION = "fort-worth-ai-ivr-validation/v1"
RECEIPT_SCHEMA = "fort-worth-ai-ivr-validation-receipt/v1"

CHANNELS = {"VOICE", "CHAT", "SMS", "OUTBOUND"}
ACTIONS = {"ANSWER", "ABSTAIN", "ASK_CLARIFY", "ESCALATE", "NOTIFY"}
PROVIDER_STATES = {"NOT_APPLICABLE", "NOT_COMMITTED", "COMMITTED", "UNKNOWN"}
EFFECT_ACTIONS = {"ESCALATE", "NOTIFY"}
NO_EFFECT_ACTIONS = ACTIONS - EFFECT_ACTIONS
SOURCE_AUTHORITIES = {"SYNTHETIC_FIXTURE", "CAPTURED_TEST_FIXTURE", "PROVISIONAL_PUBLIC_MIRROR"}


class ValidationError(ValueError):
    """Raised for malformed or ambiguous candidate evidence."""


class VerificationError(ValueError):
    """Raised when a receipt/report does not recompile exactly."""


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_hex(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _is_plain_int(value: Any) -> bool:
    return type(value) is int


def _is_plain_bool(value: Any) -> bool:
    return type(value) is bool


def _mapping(value: Any, path: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise ValidationError(f"{path} must be an object")
    return value


def _list(value: Any, path: str, *, max_items: int) -> list[Any]:
    if type(value) is not list:
        raise ValidationError(f"{path} must be an array")
    if len(value) > max_items:
        raise ValidationError(f"{path} exceeds {max_items} items")
    return value


def _text(value: Any, path: str, *, max_length: int = 512, nonempty: bool = True) -> str:
    if type(value) is not str:
        raise ValidationError(f"{path} must be text")
    if nonempty and not value:
        raise ValidationError(f"{path} must not be empty")
    if len(value) > max_length:
        raise ValidationError(f"{path} exceeds {max_length} characters")
    if any(ord(ch) < 32 for ch in value):
        raise ValidationError(f"{path} contains control characters")
    return value


def _bool(value: Any, path: str) -> bool:
    if not _is_plain_bool(value):
        raise ValidationError(f"{path} must be boolean")
    return value


def _int(value: Any, path: str, *, minimum: int, maximum: int) -> int:
    if not _is_plain_int(value):
        raise ValidationError(f"{path} must be an integer")
    if value < minimum or value > maximum:
        raise ValidationError(f"{path} must be in [{minimum},{maximum}]")
    return value


def _exact_keys(value: dict[str, Any], path: str, expected: set[str]) -> None:
    keys = set(value)
    if keys != expected:
        missing = sorted(expected - keys)
        extra = sorted(keys - expected)
        raise ValidationError(f"{path} keys mismatch; missing={missing}, extra={extra}")


def _hex64(value: Any, path: str) -> str:
    text = _text(value, path, max_length=64)
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise ValidationError(f"{path} must be lowercase sha256 hex")
    return text


def _opaque(value: Any, path: str, *, max_length: int = 128) -> str:
    text = _text(value, path, max_length=max_length)
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.:/"
    if any(ch not in allowed for ch in text):
        raise ValidationError(f"{path} contains unsupported characters")
    return text


def _validate_policy(value: Any) -> dict[str, Any]:
    policy = _mapping(value, "policy")
    _exact_keys(
        policy,
        "policy",
        {
            "policy_id",
            "policy_generation",
            "allowed_channels",
            "allowed_languages",
            "effect_actions",
            "no_effect_actions",
            "source_authority",
            "external_authority",
        },
    )
    channels = sorted({_text(v, "policy.allowed_channels[]", max_length=16) for v in _list(policy["allowed_channels"], "policy.allowed_channels", max_items=16)})
    if not channels or any(v not in CHANNELS for v in channels):
        raise ValidationError("policy.allowed_channels contains unsupported channel")
    languages = sorted({_opaque(v, "policy.allowed_languages[]", max_length=32) for v in _list(policy["allowed_languages"], "policy.allowed_languages", max_items=128)})
    if not languages:
        raise ValidationError("policy.allowed_languages must not be empty")
    effect_actions = sorted({_text(v, "policy.effect_actions[]", max_length=32) for v in _list(policy["effect_actions"], "policy.effect_actions", max_items=16)})
    no_effect_actions = sorted({_text(v, "policy.no_effect_actions[]", max_length=32) for v in _list(policy["no_effect_actions"], "policy.no_effect_actions", max_items=16)})
    if set(effect_actions) != EFFECT_ACTIONS or set(no_effect_actions) != NO_EFFECT_ACTIONS:
        raise ValidationError("policy action partitions must equal the fixed v1 protocol")
    source_authority = _text(policy["source_authority"], "policy.source_authority", max_length=64)
    if source_authority not in SOURCE_AUTHORITIES:
        raise ValidationError("policy.source_authority unsupported")
    authority = _mapping(policy["external_authority"], "policy.external_authority")
    _exact_keys(
        authority,
        "policy.external_authority",
        {"buyer_contact", "provider_send", "portal_submission", "production_write", "payment", "revenue_claim"},
    )
    normalized_authority = {key: _bool(authority[key], f"policy.external_authority.{key}") for key in sorted(authority)}
    if any(normalized_authority.values()):
        raise ValidationError("this evidence carrier cannot carry external authority")
    return {
        "policy_id": _opaque(policy["policy_id"], "policy.policy_id"),
        "policy_generation": _int(policy["policy_generation"], "policy.policy_generation", minimum=1, maximum=2**31 - 1),
        "allowed_channels": channels,
        "allowed_languages": languages,
        "effect_actions": effect_actions,
        "no_effect_actions": no_effect_actions,
        "source_authority": source_authority,
        "external_authority": normalized_authority,
    }


def _validate_scenario(value: Any, index: int, policy: dict[str, Any]) -> dict[str, Any]:
    path = f"scenarios[{index}]"
    scenario = _mapping(value, path)
    _exact_keys(
        scenario,
        path,
        {
            "scenario_id",
            "channel",
            "language",
            "intent_class",
            "prompt_sha256",
            "current_source_generation",
            "allowed_source_refs",
            "expected_action",
            "expected_route",
            "effect_key",
            "note",
        },
    )
    channel = _text(scenario["channel"], f"{path}.channel", max_length=16)
    if channel not in policy["allowed_channels"]:
        raise ValidationError(f"{path}.channel not allowed")
    language = _opaque(scenario["language"], f"{path}.language", max_length=32)
    if language not in policy["allowed_languages"]:
        raise ValidationError(f"{path}.language not allowed")
    expected_action = _text(scenario["expected_action"], f"{path}.expected_action", max_length=32)
    if expected_action not in ACTIONS:
        raise ValidationError(f"{path}.expected_action unsupported")
    refs = sorted({_opaque(v, f"{path}.allowed_source_refs[]", max_length=160) for v in _list(scenario["allowed_source_refs"], f"{path}.allowed_source_refs", max_items=32)})
    route = scenario["expected_route"]
    if route is not None:
        route = _opaque(route, f"{path}.expected_route", max_length=160)
    effect_key = scenario["effect_key"]
    if effect_key is not None:
        effect_key = _opaque(effect_key, f"{path}.effect_key", max_length=160)
    if expected_action in EFFECT_ACTIONS:
        if route is None or effect_key is None:
            raise ValidationError(f"{path} effect action requires route and effect_key")
    else:
        if effect_key is not None:
            raise ValidationError(f"{path} non-effect action cannot declare effect_key")
        if expected_action != "ASK_CLARIFY" and expected_action != "ABSTAIN" and route is not None:
            raise ValidationError(f"{path} route is only expected for effect or clarify/abstain semantics")
    if expected_action == "ANSWER" and not refs:
        raise ValidationError(f"{path} ANSWER requires allowed source refs")
    if expected_action != "ANSWER" and refs:
        raise ValidationError(f"{path} non-ANSWER cannot declare allowed source refs")
    note = scenario["note"]
    if note is not None:
        note = _text(note, f"{path}.note", max_length=512, nonempty=False)
    return {
        "scenario_id": _opaque(scenario["scenario_id"], f"{path}.scenario_id"),
        "channel": channel,
        "language": language,
        "intent_class": _opaque(scenario["intent_class"], f"{path}.intent_class", max_length=96),
        "prompt_sha256": _hex64(scenario["prompt_sha256"], f"{path}.prompt_sha256"),
        "current_source_generation": _int(scenario["current_source_generation"], f"{path}.current_source_generation", minimum=0, maximum=2**31 - 1),
        "allowed_source_refs": refs,
        "expected_action": expected_action,
        "expected_route": route,
        "effect_key": effect_key,
        "note": note,
    }


def _validate_event(value: Any, index: int, policy: dict[str, Any]) -> dict[str, Any]:
    path = f"events[{index}]"
    event = _mapping(value, path)
    _exact_keys(
        event,
        path,
        {
            "event_id",
            "scenario_id",
            "channel",
            "response_language",
            "action",
            "source_generation",
            "source_refs",
            "route",
            "effect_key",
            "logical_effects",
            "provider_state",
            "adapter_generation",
            "model_id",
        },
    )
    channel = _text(event["channel"], f"{path}.channel", max_length=16)
    if channel not in policy["allowed_channels"]:
        raise ValidationError(f"{path}.channel not allowed")
    language = _opaque(event["response_language"], f"{path}.response_language", max_length=32)
    if language not in policy["allowed_languages"]:
        raise ValidationError(f"{path}.response_language not allowed")
    action = _text(event["action"], f"{path}.action", max_length=32)
    if action not in ACTIONS:
        raise ValidationError(f"{path}.action unsupported")
    refs = sorted({_opaque(v, f"{path}.source_refs[]", max_length=160) for v in _list(event["source_refs"], f"{path}.source_refs", max_items=32)})
    route = event["route"]
    if route is not None:
        route = _opaque(route, f"{path}.route", max_length=160)
    effect_key = event["effect_key"]
    if effect_key is not None:
        effect_key = _opaque(effect_key, f"{path}.effect_key", max_length=160)
    provider_state = _text(event["provider_state"], f"{path}.provider_state", max_length=32)
    if provider_state not in PROVIDER_STATES:
        raise ValidationError(f"{path}.provider_state unsupported")
    logical_effects = _int(event["logical_effects"], f"{path}.logical_effects", minimum=0, maximum=1)
    if action in EFFECT_ACTIONS:
        if route is None or effect_key is None:
            raise ValidationError(f"{path} effect action requires route and effect_key")
        if provider_state == "COMMITTED" and logical_effects != 1:
            raise ValidationError(f"{path} committed effect must have logical_effects=1")
        if provider_state in {"NOT_COMMITTED", "NOT_APPLICABLE"} and logical_effects != 0:
            raise ValidationError(f"{path} noncommitted effect must have logical_effects=0")
    else:
        if effect_key is not None:
            raise ValidationError(f"{path} non-effect action cannot declare effect_key")
        if logical_effects != 0:
            raise ValidationError(f"{path} non-effect action must have logical_effects=0")
        if provider_state != "NOT_APPLICABLE":
            raise ValidationError(f"{path} non-effect action must use NOT_APPLICABLE provider state")
    return {
        "event_id": _opaque(event["event_id"], f"{path}.event_id", max_length=160),
        "scenario_id": _opaque(event["scenario_id"], f"{path}.scenario_id", max_length=160),
        "channel": channel,
        "response_language": language,
        "action": action,
        "source_generation": _int(event["source_generation"], f"{path}.source_generation", minimum=0, maximum=2**31 - 1),
        "source_refs": refs,
        "route": route,
        "effect_key": effect_key,
        "logical_effects": logical_effects,
        "provider_state": provider_state,
        "adapter_generation": _opaque(event["adapter_generation"], f"{path}.adapter_generation", max_length=160),
        "model_id": _opaque(event["model_id"], f"{path}.model_id", max_length=160),
    }


def validate_packet(value: Any) -> dict[str, Any]:
    packet = _mapping(copy.deepcopy(value), "packet")
    _exact_keys(packet, "packet", {"schema_version", "operation", "policy", "scenarios", "events"})
    if packet["schema_version"] != SCHEMA_VERSION:
        raise ValidationError("unsupported schema_version")
    policy = _validate_policy(packet["policy"])
    scenarios = [_validate_scenario(v, i, policy) for i, v in enumerate(_list(packet["scenarios"], "scenarios", max_items=500))]
    if not scenarios:
        raise ValidationError("at least one scenario is required")
    scenario_ids = [row["scenario_id"] for row in scenarios]
    if len(scenario_ids) != len(set(scenario_ids)):
        raise ValidationError("scenario_id values must be unique")
    scenarios.sort(key=lambda row: row["scenario_id"])

    events = [_validate_event(v, i, policy) for i, v in enumerate(_list(packet["events"], "events", max_items=5000))]
    known_scenarios = set(scenario_ids)
    for event in events:
        if event["scenario_id"] not in known_scenarios:
            raise ValidationError(f"event {event['event_id']} references unknown scenario")

    # Event identity is replay-safe: exact duplicates collapse, same-ID drift rejects.
    event_by_id: dict[str, dict[str, Any]] = {}
    replay_counts: dict[str, int] = {}
    for event in events:
        event_id = event["event_id"]
        if event_id in event_by_id:
            if canonical_json_bytes(event_by_id[event_id]) != canonical_json_bytes(event):
                raise ValidationError(f"event_id {event_id!r} reused with conflicting generation")
            replay_counts[event_id] += 1
        else:
            event_by_id[event_id] = event
            replay_counts[event_id] = 1
    normalized_events = sorted(event_by_id.values(), key=lambda row: (row["scenario_id"], row["event_id"]))

    return {
        "schema_version": SCHEMA_VERSION,
        "operation": _opaque(packet["operation"], "operation", max_length=160),
        "policy": policy,
        "scenarios": scenarios,
        "events": normalized_events,
        "event_replay_counts": {key: replay_counts[key] for key in sorted(replay_counts)},
    }


def _fail(reasons: list[str], reason: str) -> None:
    if reason not in reasons:
        reasons.append(reason)


def _evaluate_scenario(scenario: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    reasons: list[str] = []
    if not events:
        return {
            "scenario_id": scenario["scenario_id"],
            "result": "FAIL",
            "reasons": ["MISSING_CANDIDATE_EVENT"],
            "event_ids": [],
            "effect_key": scenario["effect_key"],
            "logical_effects": 0,
        }

    if len(events) > 1:
        _fail(reasons, "MULTIPLE_DISTINCT_EVENTS_FOR_SCENARIO")

    # Evaluate every distinct observation so a second effect cannot hide behind a good one.
    committed_effects = 0
    unknown_effect = False
    for event in events:
        if event["channel"] != scenario["channel"]:
            _fail(reasons, "CHANNEL_MISMATCH")
        if event["response_language"] != scenario["language"]:
            _fail(reasons, "LANGUAGE_MISMATCH")
        if event["action"] != scenario["expected_action"]:
            _fail(reasons, "ACTION_MISMATCH")
        if event["source_generation"] != scenario["current_source_generation"]:
            _fail(reasons, "SOURCE_GENERATION_MISMATCH")

        if scenario["expected_action"] == "ANSWER":
            if event["source_refs"] != scenario["allowed_source_refs"]:
                _fail(reasons, "GROUNDING_SOURCE_MISMATCH")
            if event["route"] is not None:
                _fail(reasons, "UNEXPECTED_ROUTE")
        else:
            if event["source_refs"]:
                _fail(reasons, "NONANSWER_HAS_SOURCE_CITATIONS")

        if event["route"] != scenario["expected_route"]:
            _fail(reasons, "ROUTE_MISMATCH")
        if event["effect_key"] != scenario["effect_key"]:
            _fail(reasons, "EFFECT_KEY_MISMATCH")

        if event["action"] in EFFECT_ACTIONS:
            if event["provider_state"] == "UNKNOWN":
                unknown_effect = True
                _fail(reasons, "PROVIDER_OUTCOME_UNKNOWN")
            elif event["provider_state"] == "COMMITTED":
                committed_effects += event["logical_effects"]
            elif scenario["expected_action"] in EFFECT_ACTIONS:
                _fail(reasons, "EXPECTED_EFFECT_NOT_COMMITTED")

    if committed_effects > 1:
        _fail(reasons, "DUPLICATE_LOGICAL_EFFECT")
    if unknown_effect and committed_effects:
        _fail(reasons, "AMBIGUOUS_RETRY_AFTER_UNKNOWN")
    if scenario["expected_action"] in EFFECT_ACTIONS and committed_effects != 1:
        _fail(reasons, "EXACTLY_ONE_EFFECT_REQUIRED")
    if scenario["expected_action"] in NO_EFFECT_ACTIONS and committed_effects != 0:
        _fail(reasons, "NON_EFFECT_SCENARIO_MUTATED")

    return {
        "scenario_id": scenario["scenario_id"],
        "result": "PASS" if not reasons else "FAIL",
        "reasons": sorted(reasons),
        "event_ids": sorted(event["event_id"] for event in events),
        "effect_key": scenario["effect_key"],
        "logical_effects": committed_effects,
    }


def compile_receipt(value: Any) -> tuple[dict[str, Any], str]:
    packet = validate_packet(value)
    packet_for_hash = dict(packet)
    packet_sha256 = sha256_hex(canonical_json_bytes(packet_for_hash))

    by_scenario: dict[str, list[dict[str, Any]]] = {row["scenario_id"]: [] for row in packet["scenarios"]}
    for event in packet["events"]:
        by_scenario[event["scenario_id"]].append(event)

    results = [_evaluate_scenario(scenario, by_scenario[scenario["scenario_id"]]) for scenario in packet["scenarios"]]
    results.sort(key=lambda row: row["scenario_id"])
    passed = sum(row["result"] == "PASS" for row in results)
    failed = len(results) - passed
    replayed_events = sum(count - 1 for count in packet["event_replay_counts"].values())
    logical_effects = sum(row["logical_effects"] for row in results)

    status = "EVIDENCE_READY_FOR_PRIME_REVIEW" if failed == 0 else "HOLD"
    receipt: dict[str, Any] = {
        "receipt_schema": RECEIPT_SCHEMA,
        "input_schema": SCHEMA_VERSION,
        "operation": packet["operation"],
        "packet_sha256": packet_sha256,
        "policy_sha256": sha256_hex(canonical_json_bytes(packet["policy"])),
        "source_authority": packet["policy"]["source_authority"],
        "status": status,
        "counts": {
            "scenarios": len(results),
            "passed": passed,
            "failed": failed,
            "distinct_events": len(packet["events"]),
            "exact_event_replays_collapsed": replayed_events,
            "logical_effects_observed": logical_effects,
        },
        "results": results,
        "truth_ceiling": {
            "prime_qualification_proven": False,
            "buyer_requirements_authenticated": False,
            "buyer_contact_authorized": False,
            "provider_send_authorized": False,
            "portal_submission_authorized": False,
            "production_write_authorized": False,
            "buyer_acceptance_claimed": False,
            "payment_claimed": False,
            "booked_revenue_claimed": False,
            "recognized_revenue_claimed": False,
        },
    }
    receipt["receipt_sha256"] = sha256_hex(canonical_json_bytes(receipt))
    report = render_markdown(receipt)
    return receipt, report


def render_markdown(receipt: dict[str, Any]) -> str:
    lines = [
        "# Fort Worth AI-IVR validation evidence",
        "",
        f"- **Status:** `{receipt['status']}`",
        f"- **Source authority:** `{receipt['source_authority']}`",
        f"- **Packet SHA-256:** `{receipt['packet_sha256']}`",
        f"- **Receipt SHA-256:** `{receipt['receipt_sha256']}`",
        "",
        "> Offline validation evidence only. This receipt does not authenticate the City of Fort Worth solicitation, prime qualifications, buyer acceptance, provider sends, portal submission, production writes, payment, or revenue.",
        "",
        "## Acceptance summary",
        "",
        f"- Scenarios: {receipt['counts']['scenarios']}",
        f"- Passed: {receipt['counts']['passed']}",
        f"- Failed: {receipt['counts']['failed']}",
        f"- Exact event replays collapsed: {receipt['counts']['exact_event_replays_collapsed']}",
        f"- Logical effects observed in candidate traces: {receipt['counts']['logical_effects_observed']}",
        "",
        "## Scenario matrix",
        "",
        "| Scenario | Result | Logical effects | Reasons |",
        "|---|---|---:|---|",
    ]
    for row in receipt["results"]:
        reasons = ", ".join(row["reasons"]) if row["reasons"] else "-"
        lines.append(f"| `{row['scenario_id']}` | **{row['result']}** | {row['logical_effects']} | {reasons} |")
    lines.extend(
        [
            "",
            "## External authority",
            "",
            "Every external-action / commercial-claim authority bit is mechanically false in this v1 carrier.",
            "",
        ]
    )
    return "\n".join(lines)


def verify_receipt(value: Any, receipt: Any, report: Any) -> bool:
    if type(receipt) is not dict:
        raise VerificationError("receipt must be an object")
    if type(report) is not str:
        raise VerificationError("report must be text")
    expected_receipt, expected_report = compile_receipt(value)
    if canonical_json_bytes(receipt) != canonical_json_bytes(expected_receipt):
        raise VerificationError("receipt differs from deterministic recompilation")
    if report.encode("utf-8") != expected_report.encode("utf-8"):
        raise VerificationError("report differs from deterministic recompilation")
    detached = dict(receipt)
    provided = detached.pop("receipt_sha256", None)
    expected_digest = sha256_hex(canonical_json_bytes(detached))
    if provided != expected_digest:
        raise VerificationError("receipt_sha256 invalid")
    return True
