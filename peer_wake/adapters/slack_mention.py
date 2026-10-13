"""Slack mention / Socket Mode adapter.

Reuses integrations/grok_slack credential presence and the same env names
as integrations/gemini_slack. Credentials stay in the process environment.
This module never writes tokens, never starts Socket Mode from doctor or
tests, and never fabricates a ChatGPT or Claude resume.
"""
from __future__ import annotations

from typing import Any, Callable

from integrations.grok_slack.bridge import SECRET_ENV, credential_presence


def _presence(env: dict[str, str] | None) -> dict[str, str]:
    return credential_presence(env)


def signal(
    target: dict[str, Any],
    job: dict[str, Any],
    *,
    tick: dict[str, Any] | None = None,
    deliver: bool = False,
    env: dict[str, str] | None = None,
    http: Callable[..., Any] | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    presence = _presence(env)
    missing = any(presence.get(name) == "missing" for name in SECRET_ENV)
    doorbell = str(target.get("doorbell") or "EXTERNAL_PLATFORM_ACTION")
    wake = target.get("wake_target") or {}
    base = {
        "ok": True,
        "live_wake": False,
        "invoke_model": False,
        "process_model_invocations": 0,
        "network_calls": 0,
        "credential_presence": presence,
        "secrets_in_config": False,
        "socket_mode": wake.get("kind") == "slack_socket",
        "channel": wake.get("channel") or "C0BRGMDQB6G",
        "job_id": job.get("job_id"),
        "attempt_id": (tick or {}).get("attempt_id"),
        "deliver_requested": bool(deliver),
        "reused": [
            "integrations/grok_slack/bridge.py",
            "integrations/gemini_slack/bridge.py",
            "host/slack_access_canary.py",
        ],
        "now": now,
    }
    if target.get("sibling"):
        base.update({
            "state": "SIBLING_IN_PROGRESS",
            "capability": "SIBLING_IN_PROGRESS",
            "code": "CODE_READY",
            "runtime": "RUNTIME_UNCONFIGURED" if missing else "RUNTIME_READY",
            "doorbell": doorbell,
            "note": (
                "Grok.com Slack / Gemini Slack stay their own lanes. "
                "This bus names them and does not remint them."
            ),
        })
        return base
    if missing:
        base.update({
            "state": "RUNTIME_UNCONFIGURED",
            "capability": "RUNTIME_UNCONFIGURED",
            "code": "CODE_READY",
            "runtime": "RUNTIME_UNCONFIGURED",
            "doorbell": doorbell,
            "note": "Slack credentials missing. Zero Slack calls. Public GET poll stays.",
        })
        return base
    if doorbell == "EXTERNAL_PLATFORM_ACTION":
        base.update({
            "state": "EXTERNAL_PLATFORM_ACTION",
            "capability": "EXTERNAL_PLATFORM_ACTION",
            "code": "CODE_READY",
            "runtime": "RUNTIME_READY",
            "doorbell": doorbell,
            "note": (
                "Runtime credentials are present, but ChatGPT/Claude resume is a "
                "platform action Commons cannot perform. Mention is not a doorbell. "
                "No live wake was sent."
            ),
        })
        return base
    if not deliver:
        base.update({
            "state": "RUNTIME_READY",
            "capability": "RUNTIME_READY",
            "code": "CODE_READY",
            "runtime": "RUNTIME_READY",
            "doorbell": doorbell,
            "note": "Dry run. Credentials present. No Slack call.",
        })
        return base
    # Only a peer whose platform actually accepts mention-as-wake, and only
    # when deliver=True. Tests inject http. Production ChatGPT/Claude never
    # reach here because their doorbell is EXTERNAL_PLATFORM_ACTION.
    payload = {
        "channel": wake.get("channel") or "C0BRGMDQB6G",
        "text": "WAKE job_id=%s attempt_id=%s. Open the checkpoint. Do not bounce this to Bryce."
        % (job.get("job_id"), (tick or {}).get("attempt_id") or ""),
        "job_id": job.get("job_id"),
    }
    poster = http
    if poster is None:
        base.update({
            "state": "RUNTIME_READY",
            "capability": "RUNTIME_READY",
            "code": "CODE_READY",
            "runtime": "RUNTIME_READY",
            "doorbell": doorbell,
            "note": "No Slack transport injected. Refusing to open a live Socket Mode or Web API session from this tick.",
        })
        return base
    result = poster(payload)
    base["network_calls"] = 1
    base.update({
        "state": result.get("state") or "MAILED",
        "capability": "RUNTIME_READY",
        "code": "CODE_READY",
        "runtime": "RUNTIME_READY",
        "doorbell": doorbell,
        "http_status": result.get("status"),
        "note": "Injected transport only. Token values are not logged.",
    })
    return base
