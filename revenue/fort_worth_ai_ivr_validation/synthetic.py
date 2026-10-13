"""Synthetic municipal AI-IVR acceptance portfolio."""

from __future__ import annotations

import hashlib
from typing import Any

from .core import SCHEMA_VERSION


def h(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _scenario(
    scenario_id: str,
    channel: str,
    language: str,
    intent_class: str,
    expected_action: str,
    *,
    refs: list[str] | None = None,
    route: str | None = None,
    effect_key: str | None = None,
    generation: int = 7,
    note: str | None = None,
) -> dict[str, Any]:
    return {
        "scenario_id": scenario_id,
        "channel": channel,
        "language": language,
        "intent_class": intent_class,
        "prompt_sha256": h(f"prompt:{scenario_id}"),
        "current_source_generation": generation,
        "allowed_source_refs": refs or [],
        "expected_action": expected_action,
        "expected_route": route,
        "effect_key": effect_key,
        "note": note,
    }


def _event(scenario: dict[str, Any], event_id: str, *, provider_state: str | None = None) -> dict[str, Any]:
    effect = scenario["expected_action"] in {"ESCALATE", "NOTIFY"}
    if provider_state is None:
        provider_state = "COMMITTED" if effect else "NOT_APPLICABLE"
    return {
        "event_id": event_id,
        "scenario_id": scenario["scenario_id"],
        "channel": scenario["channel"],
        "response_language": scenario["language"],
        "action": scenario["expected_action"],
        "source_generation": scenario["current_source_generation"],
        "source_refs": list(scenario["allowed_source_refs"]),
        "route": scenario["expected_route"],
        "effect_key": scenario["effect_key"],
        "logical_effects": 1 if provider_state == "COMMITTED" and effect else 0,
        "provider_state": provider_state,
        "adapter_generation": "synthetic-adapter/v1",
        "model_id": "synthetic-candidate/v1",
    }


def ready_packet() -> dict[str, Any]:
    scenarios = [
        _scenario("svc-trash-en-voice", "VOICE", "en-US", "service_navigation", "ANSWER", refs=["city:solid-waste:g7"]),
        _scenario("permit-es-chat", "CHAT", "es-US", "permit_information", "ANSWER", refs=["city:permits:g7"]),
        _scenario("library-fr-sms", "SMS", "fr", "facility_information", "ANSWER", refs=["city:library:g7"]),
        _scenario("unknown-chat", "CHAT", "en-US", "ambiguous_service", "ASK_CLARIFY"),
        _scenario("stale-sensitive-voice", "VOICE", "en-US", "source_sensitive", "ABSTAIN"),
        _scenario("after-hours-escalation", "VOICE", "en-US", "after_hours_human", "ESCALATE", route="route:311-after-hours", effect_key="effect:after-hours-311"),
        _scenario("emergency-escalation", "VOICE", "es-US", "emergency", "ESCALATE", route="route:911-emergency", effect_key="effect:emergency-911"),
        _scenario("accessibility-escalation", "CHAT", "en-US", "accessibility_support", "ESCALATE", route="route:accessibility-human", effect_key="effect:accessibility-human"),
        _scenario("road-closure-notify", "OUTBOUND", "en-US", "approved_notification", "NOTIFY", route="route:synthetic-notification", effect_key="effect:road-closure-notify"),
        _scenario("legal-advice-abstain", "CHAT", "en-US", "legal_advice", "ABSTAIN"),
        _scenario("conflicting-source-clarify", "CHAT", "es-US", "conflicting_source", "ASK_CLARIFY"),
        _scenario("permit-workflow-en-chat", "CHAT", "en-US", "workflow_lookup", "ANSWER", refs=["city:accela-permit:g7"]),
    ]
    events = [_event(scenario, f"evt:{scenario['scenario_id']}") for scenario in scenarios]
    # Exact replay is deliberate and must collapse without a second effect.
    events.append(dict(events[5]))
    return {
        "schema_version": SCHEMA_VERSION,
        "operation": "FORTWORTH-26-0263-IVR-EVIDENCE-ZHQR9T4-20260914",
        "policy": {
            "policy_id": "fort-worth-ivr-validation-policy-v1",
            "policy_generation": 1,
            "allowed_channels": ["VOICE", "CHAT", "SMS", "OUTBOUND"],
            "allowed_languages": ["en-US", "es-US", "fr"],
            "effect_actions": ["ESCALATE", "NOTIFY"],
            "no_effect_actions": ["ANSWER", "ABSTAIN", "ASK_CLARIFY"],
            "source_authority": "SYNTHETIC_FIXTURE",
            "external_authority": {
                "buyer_contact": False,
                "provider_send": False,
                "portal_submission": False,
                "production_write": False,
                "payment": False,
                "revenue_claim": False,
            },
        },
        "scenarios": scenarios,
        "events": events,
    }
