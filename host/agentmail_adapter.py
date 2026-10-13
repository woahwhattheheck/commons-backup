#!/usr/bin/env python3
"""Project AgentMail MCP observations into a public-safe canary receipt.

This adapter makes no network calls. The existing MCP connectors own inbox,
send, and read operations; only bounded states, timestamps, safe provider IDs,
and optional hashes cross this boundary.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


SCHEMA = "commons-agentmail-round-trip/v1"
ORDER = "agentmail-first-inbox-road-20260901-01"
CONNECTOR = {"AVAILABLE", "UNAVAILABLE"}
FALLBACK = {"NOT_NEEDED", "AVAILABLE", "UNAVAILABLE"}
STATES = {
    "inbox": {"NOT_ATTEMPTED", "CREATED", "CREATE_FAILED"},
    "outbound": {"NOT_ATTEMPTED", "PROVIDER_ACCEPTED", "SEND_FAILED"},
    "inbound": {"NOT_ATTEMPTED", "PROVIDER_OBSERVED", "NOT_OBSERVED"},
}
POSITIVE = {
    "inbox": "CREATED",
    "outbound": "PROVIDER_ACCEPTED",
    "inbound": "PROVIDER_OBSERVED",
}
STAGE_KEYS = {
    "inbox": {"state", "occurred_at", "provider_inbox_id"},
    "outbound": {"state", "occurred_at", "provider_message_id", "payload_sha256"},
    "inbound": {"state", "occurred_at", "provider_message_id", "payload_sha256"},
}
OBSERVATION_KEYS = {
    "build_order_id", "observed_at", "agentmail_connector_state",
    "gmail_fallback_state", "inbox", "outbound", "inbound",
}
RECEIPT_KEYS = {
    "schema_version", "kind", "build_order_id", "consumer", "observed_at",
    "connectors", "inbox", "outbound", "inbound", "terminal_state", "proof", "policy",
}
SAFE_ID = re.compile(r"^[A-Za-z0-9._:-]{1,200}$")
HASH = re.compile(r"^sha256:[0-9a-f]{64}$")
UTC_TIMESTAMP = re.compile(
    r"\A[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]+)?Z\Z",
    re.ASCII,
)


class AgentMailReceiptError(ValueError):
    """The supplied observation is not safe or internally consistent."""


def _time(value: object, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or UTC_TIMESTAMP.fullmatch(value) is None:
        raise AgentMailReceiptError("invalid UTC timestamp")
    try:
        datetime.fromisoformat(value[:-1] + "+00:00")
    except (OverflowError, ValueError) as exc:
        raise AgentMailReceiptError("invalid UTC timestamp") from exc
    return value


def _match(value: object, pattern: re.Pattern[str], label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise AgentMailReceiptError(f"invalid public-safe {label}")
    return value


def _stage(name: str, raw: object) -> dict[str, Any]:
    if not isinstance(raw, dict) or set(raw) != STAGE_KEYS[name]:
        raise AgentMailReceiptError(f"invalid {name} surface")
    state = raw["state"]
    if not isinstance(state, str) or state not in STATES[name]:
        raise AgentMailReceiptError(f"invalid {name} state")
    at = _time(raw["occurred_at"], nullable=True)
    id_key = "provider_inbox_id" if name == "inbox" else "provider_message_id"
    provider_id = _match(raw[id_key], SAFE_ID, "provider id")
    result = {"state": state, "occurred_at": at, id_key: provider_id}
    if name != "inbox":
        result["payload_sha256"] = _match(raw["payload_sha256"], HASH, "payload hash")
    if state == POSITIVE[name] and (at is None or provider_id is None):
        raise AgentMailReceiptError(f"{name} proof requires timestamp and provider id")
    if state != POSITIVE[name] and provider_id is not None:
        raise AgentMailReceiptError(f"{name} state cannot claim a provider id")
    if state == "NOT_ATTEMPTED" and result.get("payload_sha256") is not None:
        raise AgentMailReceiptError(f"{name} was not attempted but has a payload hash")
    return result


def project_receipt(observation: object) -> dict[str, Any]:
    """Return the canonical public projection of one private observation."""
    if not isinstance(observation, dict) or set(observation) != OBSERVATION_KEYS:
        raise AgentMailReceiptError("invalid observation surface")
    if observation["build_order_id"] != ORDER:
        raise AgentMailReceiptError("assigned build order id does not match")
    observed_at = _time(observation["observed_at"])
    agentmail = observation["agentmail_connector_state"]
    gmail = observation["gmail_fallback_state"]
    if (
        not isinstance(agentmail, str) or agentmail not in CONNECTOR
        or not isinstance(gmail, str) or gmail not in FALLBACK
    ):
        raise AgentMailReceiptError("invalid connector state")
    stages = {name: _stage(name, observation[name]) for name in STAGE_KEYS}
    if agentmail == "UNAVAILABLE":
        if any(row["state"] != "NOT_ATTEMPTED" for row in stages.values()):
            raise AgentMailReceiptError("unavailable connector cannot claim operations")
        terminal = "ROAD_UNAVAILABLE"
    elif all(stages[name]["state"] == POSITIVE[name] for name in STAGE_KEYS):
        terminal = "ROUND_TRIP_PROVEN"
    else:
        terminal = "INCOMPLETE"
    return {
        "schema_version": SCHEMA,
        "kind": "AGENTMAIL_CANARY_ROUND_TRIP_RECEIPT",
        "build_order_id": ORDER,
        "consumer": "COMMONS_TRANSACTION_AND_AGENT_DELIVERY",
        "observed_at": observed_at,
        "connectors": {"agentmail": agentmail, "gmail_inbound_fallback": gmail},
        **stages,
        "terminal_state": terminal,
        "proof": {
            "outbound_provider_accepted": stages["outbound"]["state"] == POSITIVE["outbound"],
            "inbound_provider_observed": stages["inbound"]["state"] == POSITIVE["inbound"],
            "round_trip_proven": terminal == "ROUND_TRIP_PROVEN",
        },
        "policy": {
            "recipient_role": "OWNER_CANARY",
            "send_attempts": int(stages["outbound"]["state"] != "NOT_ATTEMPTED"),
            "resend_permitted": False,
            "external_prospect_contact": False,
            "message_content_persisted": False,
            "secrets_persisted": False,
        },
    }


def validate_public_receipt(receipt: object) -> None:
    """Require an exact canonical projection, with no expanded data surface."""
    if not isinstance(receipt, dict) or set(receipt) != RECEIPT_KEYS:
        raise AgentMailReceiptError("invalid receipt surface")
    connectors = receipt.get("connectors")
    if not isinstance(connectors, dict) or set(connectors) != {"agentmail", "gmail_inbound_fallback"}:
        raise AgentMailReceiptError("invalid connector surface")
    observation = {
        "build_order_id": receipt.get("build_order_id"),
        "observed_at": receipt.get("observed_at"),
        "agentmail_connector_state": connectors["agentmail"],
        "gmail_fallback_state": connectors["gmail_inbound_fallback"],
        **{name: receipt.get(name) for name in STAGE_KEYS},
    }
    if project_receipt(observation) != receipt:
        raise AgentMailReceiptError("receipt is not the canonical public projection")
    encoded = json.dumps(receipt, sort_keys=True).lower()
    if any(word in encoded for word in ("@", "subject", "body", "header", "oauth", "password")):
        raise AgentMailReceiptError("receipt contains forbidden private mail material")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Project a public-safe AgentMail receipt")
    parser.add_argument("observation", type=Path)
    args = parser.parse_args(argv)
    try:
        raw = json.loads(args.observation.read_text(encoding="utf-8"))
        receipt = project_receipt(raw)
        validate_public_receipt(receipt)
    except (OSError, json.JSONDecodeError, AgentMailReceiptError) as exc:
        print(json.dumps({"ok": False, "state": "RECEIPT_REJECTED", "error_type": type(exc).__name__}))
        return 1
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
