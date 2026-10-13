#!/usr/bin/env python3
"""Drive tagged services. Never invent a Facebook post or copy secrets.

A Slack custom-tool job calls drive(tag, body). If this process has no
provider session, the result is OWNER_SIGNIN — not a fake in-harness call.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


FACEBOOK_GRAPH = "https://graph.facebook.com/v21.0/me/feed"
TOKEN_ENV = (
    "FACEBOOK_PAGE_ACCESS_TOKEN",
    "FACEBOOK_ACCESS_TOKEN",
    "META_PAGE_ACCESS_TOKEN",
)


def _token_from_env() -> str:
    for key in TOKEN_ENV:
        value = str(os.environ.get(key) or "").strip()
        if value:
            return value
    return ""


def drive_facebook(body: str) -> dict[str, Any]:
    """Post the tagged remainder to Facebook Graph. No token → sign-in queue."""
    message = str(body or "").strip()
    token = _token_from_env()
    if not token:
        return {
            "ok": False,
            "tag": "facebook",
            "road": "OWNER_SIGNIN",
            "reason": "no_facebook_session_in_this_process",
            "copy_secrets": False,
        }
    payload = urllib.parse.urlencode({"message": message, "access_token": token}).encode(
        "utf-8"
    )
    req = urllib.request.Request(FACEBOOK_GRAPH, data=payload, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            data = json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="replace")
        return {
            "ok": False,
            "tag": "facebook",
            "road": "OWNER_SIGNIN",
            "reason": "facebook_graph_http_%s" % exc.code,
            "error_class": type(exc).__name__,
            "copy_secrets": False,
            "provider_error": err_body[:500],
        }
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return {
            "ok": False,
            "tag": "facebook",
            "road": "OWNER_SIGNIN",
            "reason": "facebook_graph_transport",
            "error_class": type(exc).__name__,
            "copy_secrets": False,
        }
    post_id = ""
    if isinstance(data, dict):
        post_id = str(data.get("id") or "")
    if not post_id:
        return {
            "ok": False,
            "tag": "facebook",
            "road": "OWNER_SIGNIN",
            "reason": "facebook_graph_no_id",
            "copy_secrets": False,
        }
    return {
        "ok": True,
        "tag": "facebook",
        "road": "SLACK_CUSTOM_TOOL",
        "facebook_post_id": post_id,
        "copy_secrets": False,
    }


def drive(tag: str, body: str) -> dict[str, Any]:
    name = str(tag or "").lower().strip()
    if name == "facebook":
        return drive_facebook(body)
    return {
        "ok": False,
        "tag": name,
        "road": "SLACK_CUSTOM_TOOL",
        "reason": "driver_queued",
        "copy_secrets": False,
    }
