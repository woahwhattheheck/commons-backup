#!/usr/bin/env python3
"""Bolt custom-tool app: tagged Slack messages drive the named service.

Does not replace host/slack_service_tag.py. That module routes @tags.
This module executes SLACK_CUSTOM_TOOL jobs: official Graph/API intents
when a session exists, otherwise the installed provider-sign-in exact-action queue.

Live HTTP is opt-in (http_request callback). Default is dry-run READY.
Secrets never appear in returned dicts or Slack text.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from typing import Any, Callable

from needs_bryce_login_queue import format_item, provider_signin_item, signin_url


ENV_KEYS: dict[str, tuple[str, ...]] = {
    "facebook": ("FACEBOOK_ACCESS_TOKEN", "META_ACCESS_TOKEN"),
    "instagram": ("INSTAGRAM_ACCESS_TOKEN",),
    "discord": ("DISCORD_BOT_TOKEN", "DISCORD_WEBHOOK_URL"),
    "github": ("GITHUB_TOKEN", "GH_TOKEN"),
    "gmail": ("GMAIL_ACCESS_TOKEN",),
    "x": ("X_ACCESS_TOKEN", "TWITTER_ACCESS_TOKEN"),
    "slack": ("SLACK_BOT_TOKEN",),
}

GRAPH_V = "v21.0"
GRAPH = f"https://graph.facebook.com/{GRAPH_V}"
GITHUB_API = "https://api.github.com"

HttpFn = Callable[..., Any]


def sessions_from_env(environ: dict[str, str] | None = None) -> dict[str, bool]:
    """Presence-only map. Values are never returned."""
    env = environ if environ is not None else os.environ
    present: dict[str, bool] = {}
    for tag, keys in ENV_KEYS.items():
        present[tag] = any(bool(str(env.get(k) or "").strip()) for k in keys)
    return present


def _env_token(tag: str, environ: dict[str, str] | None = None) -> str:
    env = environ if environ is not None else os.environ
    for key in ENV_KEYS.get(tag, ()):
        val = str(env.get(key) or "").strip()
        if val:
            return val
    return ""


def parse_svctool_text(text: str) -> tuple[str, str]:
    """'/svctool facebook post hi' or '@facebook post hi' → (facebook, post hi)."""
    raw = str(text or "").strip()
    raw = re.sub(r"^/svctool\s+", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"^<@[A-Z0-9]+>\s*", "", raw)
    match = re.match(r"^@?([A-Za-z][A-Za-z0-9_-]{0,31})\s*(.*)$", raw, re.DOTALL)
    if not match:
        return "", raw
    return match.group(1).lower(), match.group(2).strip()


def facebook_intent(body: str) -> dict[str, Any]:
    text = str(body or "").strip()
    low = text.lower()
    if low.startswith("post ") or low.startswith("publish "):
        message = text.split(None, 1)[1] if " " in text else text
        return {
            "method": "POST",
            "url": f"{GRAPH}/me/feed",
            "form_keys": ["message"],
            "message_len": len(message),
        }
    return {
        "method": "GET",
        "url": f"{GRAPH}/me",
        "form_keys": [],
        "message_len": len(text),
    }


def github_intent(body: str) -> dict[str, Any]:
    return {
        "method": "GET",
        "url": f"{GITHUB_API}/user",
        "form_keys": [],
        "message_len": len(str(body or "")),
    }


def _needs_owner_signin(tag: str) -> tuple[bool, bool]:
    """Return (needs_owner, known_in_catalog). Unknown tags are not a Commons gate."""
    try:
        import slack_service_tag as sst

        cat = sst.load_catalog()
        services = cat.get("services") or {}
        if tag not in services:
            return False, False
        spec = services.get(tag) or {}
        return bool(spec.get("needs_owner_signin", True)), True
    except Exception:
        return signin_url(tag) is not None, signin_url(tag) is not None


def _public_intent(tag: str, body: str) -> dict[str, Any] | None:
    if tag == "facebook":
        return facebook_intent(body)
    if tag == "github":
        return github_intent(body)
    url = signin_url(tag)
    if not url:
        return None
    return {
        "method": "GET",
        "url": url,
        "form_keys": [],
        "message_len": len(str(body or "")),
    }


def _redact_result(state: str, tag: str, detail: str) -> str:
    return f"{state} @{tag} {detail}".strip()


def _provider_signin_surface(tag: str, body: str) -> tuple[str, str, str]:
    """Return the current provider-session queue and secret-free blocker text."""
    try:
        import slack_service_tag as sst

        cat = sst.load_catalog()
        signin = sst._signin_channel(cat)
        channel_id = str(signin.get("id") or "C0BUFA9G23E")
        channel_name = str(signin.get("name") or "#provider-sign-in")
        text = sst.format_owner_blocker({"tag": tag, "body": body})
        return channel_id, channel_name, text
    except Exception:
        url = signin_url(tag) or "official provider console"
        text = (
            f"NEED: complete the official {tag} provider session in that provider's UI\n"
            f"WHY ONLY BRYCE: this harness has Slack, not an in-harness {tag} tool\n"
            f"SMALLEST ACTION: sign in at {url}, then reply in thread\n"
            f"EVIDENCE: Slack custom-tool job @{tag}\n"
            f"AFTER: peer resumes the tagged body through @{tag}\n"
            f"BODY: {str(body or '').strip()}\n"
            "Do not paste a password, API key, session token, or other secret into Slack."
        )
        return "C0BUFA9G23E", "#provider-sign-in", text


def drive(
    tag: str,
    body: str,
    sessions: dict[str, bool] | None = None,
    environ: dict[str, str] | None = None,
    http_request: HttpFn | None = None,
    execute: bool = False,
    resume_worker_url: str = "",
) -> dict[str, Any]:
    name = str(tag or "").lower().strip()
    present = sessions if sessions is not None else sessions_from_env(environ)
    intent = _public_intent(name, body)
    out: dict[str, Any] = {
        "tag": name,
        "copy_secrets": False,
        "commons_admission": False,
        "intent": intent,
        "needs_bryce_text": None,
        "owner_signin_text": None,
        "http_called": False,
    }
    if not name:
        out["state"] = "UNKNOWN"
        out["result"] = "UNKNOWN missing tag"
        return out
    has_session = bool(present.get(name))
    if not has_session:
        needs_owner, known = _needs_owner_signin(name)
        if not known:
            out["state"] = "UNKNOWN"
            out["result"] = _redact_result(
                "UNKNOWN", name, "add the service to the catalog"
            )
            return out
        if needs_owner:
            channel_id, channel_name, signin_text = _provider_signin_surface(name, body)
            out["state"] = "NEEDS_OWNER_SIGNIN"
            # Preserve the legacy key for existing callers while routing to the
            # current provider-session queue rather than the owner-exclusive queue.
            out["needs_bryce_text"] = signin_text
            out["owner_signin_text"] = signin_text
            out["channel_id"] = channel_id
            out["channel_name"] = channel_name
            out["result"] = _redact_result(
                "NEEDS_OWNER_SIGNIN",
                name,
                f"queue {channel_name} " + (signin_url(name) or ""),
            )
            return out
        out["state"] = "READY"
        out["result"] = _redact_result(
            "READY", name, "no local session; catalog does not queue owner sign-in"
        )
        return out
    if not execute or http_request is None:
        out["state"] = "READY"
        out["result"] = _redact_result("READY", name, (intent or {}).get("url", ""))
        return out
    token = _env_token(name, environ)
    headers = {"Authorization": "Bearer REDACTED"}
    # Pass the real token only into the injected http_request. Never store it.
    call_headers = {"Authorization": "Bearer " + token} if token else {}
    url = str((intent or {}).get("url") or "")
    method = str((intent or {}).get("method") or "GET")
    http_request(method=method, url=url, headers=call_headers)
    out["http_called"] = True
    out["state"] = "DRIVEN"
    out["result"] = _redact_result("DRIVEN", name, url)
    out["request_header_keys"] = sorted(headers.keys())
    return out


def drive_tagged_jobs(
    jobs: list[dict[str, Any]],
    sessions: dict[str, bool] | None = None,
    **kwargs: Any,
) -> list[dict[str, Any]]:
    """Execute router jobs. IN_HARNESS stays with the harness; we drive the rest."""
    outcomes: list[dict[str, Any]] = []
    custom_tags = {
        str(j.get("tag") or "")
        for j in (jobs or [])
        if str(j.get("road") or "") == "SLACK_CUSTOM_TOOL"
    }
    for job in jobs or []:
        road = str(job.get("road") or "")
        tag = str(job.get("tag") or "")
        body = str(job.get("body") or "")
        if road == "OWNER_SIGNIN" and tag in custom_tags:
            # drive() on the custom-tool job emits the same provider-session
            # blocker on the installed provider-sign-in queue when needed.
            continue
        if road == "IN_HARNESS":
            outcomes.append(
                {
                    "tag": tag,
                    "state": "IN_HARNESS",
                    "result": f"IN_HARNESS @{tag}",
                    "copy_secrets": False,
                }
            )
            continue
        outcomes.append(drive(tag, body, sessions=sessions, **kwargs))
    return outcomes


def handle_channel_text(
    text: str,
    connected: list[str] | None = None,
    sessions: dict[str, bool] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Route via peer catalog when present, then drive custom-tool jobs."""
    try:
        import slack_service_tag as sst
    except ImportError:
        tag, body = parse_svctool_text(text)
        jobs = [
            {
                "tag": tag,
                "road": "SLACK_CUSTOM_TOOL",
                "body": body,
            }
        ]
        route = {"tags": [tag] if tag else [], "jobs": jobs, "gate": False}
    else:
        route = sst.route(text, connected=connected or ["slack"])
        jobs = list(route.get("jobs") or [])
    outcomes = drive_tagged_jobs(jobs, sessions=sessions, **kwargs)
    return {
        "gate": False,
        "commons_admission": False,
        "route": route,
        "outcomes": outcomes,
    }


def register(app: Any, environ: dict[str, str] | None = None) -> Any:
    """Attach Bolt listeners. slack_bolt is imported by the caller."""

    @app.function("drive_tagged_service")
    def handle_drive(inputs: dict, complete: Any, fail: Any) -> None:
        try:
            tag = str((inputs or {}).get("tag") or "")
            body = str((inputs or {}).get("body") or "")
            out = drive(tag, body, environ=environ)
            complete({"state": out["state"], "result": out["result"]})
        except Exception as exc:  # noqa: BLE001 — Bolt fail() needs a string
            fail(type(exc).__name__)

    @app.event("app_mention")
    def handle_mention(event: dict, say: Any) -> None:
        text = str((event or {}).get("text") or "")
        payload = handle_channel_text(text, connected=["slack"], environ=environ)
        lines = [row.get("result") or row.get("state") for row in payload["outcomes"]]
        say("\n".join(str(x) for x in lines if x))

    @app.command("/svctool")
    def handle_slash(ack: Any, command: dict, say: Any) -> None:
        ack()
        tag, body = parse_svctool_text(str((command or {}).get("text") or ""))
        out = drive(tag, body, environ=environ)
        say(out["result"])

    return app


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--text", default="")
    parser.add_argument("--tag", default="")
    parser.add_argument("--body", default="")
    parser.add_argument(
        "--connected",
        default="slack",
        help="comma-separated in-harness tools",
    )
    args = parser.parse_args(argv)
    connected = [p.strip() for p in args.connected.split(",") if p.strip()]
    if args.text:
        payload = handle_channel_text(args.text, connected=connected)
        print(json.dumps(payload, indent=2))
        return 0
    out = drive(args.tag, args.body)
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())