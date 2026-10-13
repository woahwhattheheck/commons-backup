#!/usr/bin/env python3
"""Build deterministic Slack destination handoffs without sending them.

This adapter is for local bridges that do not own a Slack connection. It
normalizes the existing relay envelope and returns either a synthetic receipt
or an exact packet for a separately connected carrier. It never reads process
environment values, classifies message text, invokes a supplied callable,
opens Slack HTTP, or starts Socket Mode.

The existing relay and integration modules remain the source of origin
formatting, the default destination, and integration provenance. They are not
modified or reimplemented here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ntfy_relays
from integrations.gemini_slack import bridge as gemini_slack_bridge
from integrations.grok_slack.bridge import DEFAULT_CHANNEL

RECEIPT_SCHEMA = "commons-slack-relay-receipt/v2"
PACKET_SCHEMA = "commons-slack-destination-handoff/v1"
ADAPTER_PATH = "host/slack_relay_adapter.py"
WIRED_PATHS = (
    "ntfy_relays.py",
    "integrations/grok_slack/bridge.py",
    "integrations/gemini_slack/bridge.py",
)
MODES = ("test", "handoff")
SYNTHETIC_STATE = "SYNTHETIC_DELIVERED"
HANDOFF_STATE = "HANDOFF_READY"
INVALID_EVENT_STATE = "INVALID_EVENT"
INVALID_MODE_STATE = "INVALID_MODE"
GEMINI_BRIDGE_NAME = gemini_slack_bridge.__name__
SELF_TEST_EVENT = {
    "id": "caliper-slack-relay-adapter-01",
    "text": "synthetic Slack destination ping",
    "source_host": "local-uncredentialed",
    "carrier_origin": "local-uncredentialed",
    "channel": DEFAULT_CHANNEL,
}


class SlackRelayAdapterError(ValueError):
    """The source event cannot be converted into a destination packet."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _synthetic_ts(event_id: str) -> str:
    digest = hashlib.sha256(event_id.encode("utf-8")).hexdigest()[:10]
    return f"synthetic.{digest}"


def _origin(event: dict[str, Any]) -> tuple[str, str]:
    source_host = ntfy_relays._host(
        event.get("source_host") or event.get("host") or "local-uncredentialed"
    )
    carrier_origin = ntfy_relays._host(event.get("carrier_origin") or source_host)
    return source_host, carrier_origin


def _compose_text(event: dict[str, Any], event_id: str, source_host: str, carrier_origin: str) -> str:
    text = event.get("text")
    if isinstance(text, str) and text.strip():
        return text
    payload = event.get("payload")
    if not isinstance(payload, dict) and event.get("message"):
        try:
            candidate = json.loads(event.get("message") or "")
        except (json.JSONDecodeError, TypeError):
            candidate = None
        if isinstance(candidate, dict):
            payload = candidate
    if not isinstance(payload, dict):
        raise SlackRelayAdapterError("event has no text or relay payload")
    row = {
        "id": event_id,
        "payload": payload,
        "message": event.get("message") or "",
        "source_host": source_host,
        "host": source_host,
        "carrier_origin": carrier_origin,
        "source_hosts": event.get("source_hosts") or [source_host],
        "carrier_origins": event.get("carrier_origins") or [carrier_origin],
    }
    try:
        return ntfy_relays.relay_message(row)
    except ValueError as exc:
        raise SlackRelayAdapterError(str(exc)) from exc


def normalize_event(event: object) -> dict[str, Any]:
    if not isinstance(event, dict):
        raise SlackRelayAdapterError("event must be an object")
    event_id = event.get("id")
    if not isinstance(event_id, str) or not event_id.strip():
        raise SlackRelayAdapterError("event id must be nonempty text")
    event_id = event_id.strip()
    source_host, carrier_origin = _origin(event)
    channel = str(event.get("channel") or DEFAULT_CHANNEL).strip() or DEFAULT_CHANNEL
    thread_ts = str(event.get("thread_ts") or "").strip()
    text = _compose_text(event, event_id, source_host, carrier_origin)
    return {
        "id": event_id,
        "text": text,
        "source_host": source_host,
        "carrier_origin": carrier_origin,
        "channel": channel,
        "thread_ts": thread_ts,
    }


def _packet(normalized: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": PACKET_SCHEMA,
        "id": normalized["id"],
        "channel": normalized["channel"],
        "text": normalized["text"],
        "thread_ts": normalized["thread_ts"],
        "source_host": normalized["source_host"],
        "carrier_origin": normalized["carrier_origin"],
    }


def _packet_digest(packet: dict[str, Any]) -> str:
    raw = json.dumps(packet, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _receipt(
    *,
    normalized: dict[str, Any] | None,
    mode: str,
    state: str,
    ok: bool,
    reason: str,
    fail_closed: bool,
    slack_ts: str,
    observed_at: str,
) -> dict[str, Any]:
    packet = _packet(normalized) if normalized is not None else None
    return {
        "schema": RECEIPT_SCHEMA,
        "adapter": ADAPTER_PATH,
        "wired": list(WIRED_PATHS),
        "mode": mode,
        "ok": ok,
        "state": state,
        "reason": reason,
        "fail_closed": fail_closed,
        "silent_skip": False,
        "id": (normalized or {}).get("id") or "",
        "channel": (normalized or {}).get("channel") or DEFAULT_CHANNEL,
        "thread_ts": (normalized or {}).get("thread_ts") or "",
        "source_host": (normalized or {}).get("source_host") or "",
        "carrier_origin": (normalized or {}).get("carrier_origin") or "",
        "packet": packet,
        "packet_sha256": _packet_digest(packet) if packet is not None else "",
        "network_calls": 0,
        "transport_invocations": 0,
        "environment_reads": 0,
        "text_classifications": 0,
        "real_send": False,
        "delivery_pending": state == HANDOFF_STATE,
        "synthetic": state == SYNTHETIC_STATE,
        "slack_ts": slack_ts,
        "observed_at": observed_at,
        "gemini_slack_module": GEMINI_BRIDGE_NAME,
    }


def deliver(
    event: object,
    *,
    mode: str = "test",
    env: object | None = None,
    transport: object | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    """Return one synthetic result or one read-only carrier handoff.

    ``env`` and ``transport`` remain accepted for call-site compatibility. Their
    values are deliberately not inspected or invoked.
    """
    del env, transport
    observed_at = now or _utc_now()
    requested_mode = str(mode or "").strip().lower()
    if requested_mode not in MODES:
        return _receipt(
            normalized=None,
            mode=requested_mode,
            state=INVALID_MODE_STATE,
            ok=False,
            reason="mode must be test or handoff",
            fail_closed=True,
            slack_ts="",
            observed_at=observed_at,
        )
    try:
        normalized = normalize_event(event)
    except SlackRelayAdapterError as exc:
        return _receipt(
            normalized=None,
            mode=requested_mode,
            state=INVALID_EVENT_STATE,
            ok=False,
            reason=str(exc),
            fail_closed=True,
            slack_ts="",
            observed_at=observed_at,
        )

    if requested_mode == "test":
        return _receipt(
            normalized=normalized,
            mode="test",
            state=SYNTHETIC_STATE,
            ok=True,
            reason="synthetic destination receipt; no external effect",
            fail_closed=False,
            slack_ts=_synthetic_ts(normalized["id"]),
            observed_at=observed_at,
        )

    return _receipt(
        normalized=normalized,
        mode="handoff",
        state=HANDOFF_STATE,
        ok=True,
        reason="exact destination packet prepared for a separately connected carrier",
        fail_closed=False,
        slack_ts="",
        observed_at=observed_at,
    )


def self_test() -> dict[str, Any]:
    """Prove both read-only modes produce the same normalized packet."""
    fixed = "2026-09-01T00:00:00Z"
    synthetic = deliver(SELF_TEST_EVENT, mode="test", now=fixed)
    handoff = deliver(SELF_TEST_EVENT, mode="handoff", now=fixed)
    ok = (
        synthetic.get("ok") is True
        and synthetic.get("state") == SYNTHETIC_STATE
        and handoff.get("ok") is True
        and handoff.get("state") == HANDOFF_STATE
        and synthetic.get("packet") == handoff.get("packet")
        and synthetic.get("packet_sha256") == handoff.get("packet_sha256")
        and synthetic.get("network_calls") == handoff.get("network_calls") == 0
        and synthetic.get("transport_invocations") == handoff.get("transport_invocations") == 0
        and synthetic.get("real_send") is handoff.get("real_send") is False
    )
    return {"ok": ok, "synthetic": synthetic, "handoff": handoff}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a read-only Slack destination handoff")
    parser.add_argument("--mode", choices=MODES, default="test")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--input", help="JSON event file; default is the synthetic fixture")
    args = parser.parse_args(argv)
    if args.self_test:
        report = self_test()
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if report["ok"] else 1
    if args.input:
        event = json.loads(Path(args.input).read_text(encoding="utf-8"))
    else:
        event = SELF_TEST_EVENT
    receipt = deliver(event, mode=args.mode)
    print(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if receipt.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
