"""#commons same-table wake TIP formatter for GET-only peers.

Formats a durable table TIP peers can paste or an injected post_fn can
carry. Reuses the peer wake bus and Slack access canary roads. Never
puts tokens in git. Never fabricates a live ChatGPT or Claude resume.
Doorbell stays EXTERNAL_PLATFORM_ACTION.

Cite: grok-peer-wake-bus-20260828-01, rivet-ship-slack-access-20260825-01.
Do not remint the peer_wake bus or ping poll adapters.
"""
from __future__ import annotations

from typing import Any, Callable


CHANNEL = "C0BRGMDQB6G"
CHANNEL_NAME = "#commons"
REUSED = (
    "peer_wake/bus.py",
    "peer_wake/adapters/poll.py",
    "host/slack_access_canary.py",
    "ground/PEER_WAKE_BUS.md",
    "p/grok-peer-wake-bus-20260828-01.md",
    "p/rivet-ship-slack-access-20260825-01.md",
)


def format_tip(
    target: dict[str, Any],
    job: dict[str, Any],
    *,
    tick: dict[str, Any] | None = None,
) -> str:
    """Build a same-table TIP string. No network. No tokens."""
    peer = str(target.get("peer") or "PEER").upper()
    job_id = job.get("job_id") or ""
    attempt = (tick or {}).get("attempt_id") or ""
    wake = target.get("wake_target") or {}
    path = wake.get("path") or "ping/last.json"
    prompt = wake.get("prompt") or ""
    lines = [
        "TIP — Commons same-table wake (GET-only peer)",
        "channel: %s (%s)" % (CHANNEL_NAME, CHANNEL),
        "peer: %s" % peer,
        "job_id: %s" % job_id,
        "attempt_id: %s" % attempt,
        "poll: GET %s" % path,
    ]
    if prompt:
        lines.append("prompt: %s" % prompt)
    lines.extend(
        [
            "doorbell: EXTERNAL_PLATFORM_ACTION",
            "note: Slack connector write is mail, not ChatGPT/Claude resume.",
            "cite: grok-peer-wake-bus-20260828-01, rivet-ship-slack-access-20260825-01",
        ]
    )
    return "\n".join(lines)


def signal(
    target: dict[str, Any],
    job: dict[str, Any],
    *,
    tick: dict[str, Any] | None = None,
    deliver: bool = False,
    env: dict[str, str] | None = None,
    http: Callable[..., Any] | None = None,
    post_fn: Callable[[dict[str, Any]], Any] | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    """Format a TIP; optionally hand it to an injected post_fn.

    ``http`` is accepted for bus signature parity and is never used as a
    live doorbell. ``post_fn`` is the only injectable carrier; tests inject
    it. Production ChatGPT/Claude doorbell remains EXTERNAL_PLATFORM_ACTION.
    """
    del env  # never read tokens; presence is irrelevant for format-only TIP
    doorbell = str(target.get("doorbell") or "EXTERNAL_PLATFORM_ACTION")
    tip = format_tip(target, job, tick=tick)
    wake = target.get("wake_target") or {}
    base: dict[str, Any] = {
        "ok": True,
        "state": "TIP_FORMATTED",
        "capability": "EXTERNAL_PLATFORM_ACTION",
        "code": "CODE_READY",
        "runtime": "RUNTIME_READY",
        "doorbell": "EXTERNAL_PLATFORM_ACTION",
        "live_wake": False,
        "invoke_model": False,
        "process_model_invocations": 0,
        "network_calls": 0,
        "deliver_requested": bool(deliver),
        "job_id": job.get("job_id"),
        "attempt_id": (tick or {}).get("attempt_id"),
        "channel": wake.get("channel") or CHANNEL,
        "channel_name": CHANNEL_NAME,
        "tip": tip,
        "reused": list(REUSED),
        "now": now,
        "note": (
            "Formatted #commons same-table TIP for a GET-only peer. "
            "Doorbell stays EXTERNAL_PLATFORM_ACTION. "
            "Never claims live ChatGPT/Claude resume. deliver=%s."
        )
        % bool(deliver),
    }
    if doorbell != "EXTERNAL_PLATFORM_ACTION":
        # Even if a target mislabels doorbell, this adapter refuses to ring.
        base["note"] = (
            "slack_table_tip refuses non-EXTERNAL doorbells. "
            "TIP formatted only; no resume fabricated."
        )
        return base
    # ``http`` is bus signature parity only. Never call it. ``post_fn`` is
    # the only injectable carrier.
    del http
    if not deliver or post_fn is None:
        return base
    payload = {
        "channel": base["channel"],
        "channel_name": CHANNEL_NAME,
        "text": tip,
        "job_id": job.get("job_id"),
        "doorbell": "EXTERNAL_PLATFORM_ACTION",
        "live_wake": False,
    }
    result = post_fn(payload) or {}
    base["network_calls"] = 1
    base["state"] = result.get("state") or "TIP_POSTED_VIA_INJECTED"
    base["http_status"] = result.get("status")
    base["live_wake"] = False
    base["note"] = (
        "Injected post_fn carried the TIP. Token values are not logged. "
        "Still not a ChatGPT/Claude resume (EXTERNAL_PLATFORM_ACTION)."
    )
    return base
