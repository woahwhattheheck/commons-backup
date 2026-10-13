#!/usr/bin/env python3
"""Drive every catalog @tag. Does not steal facebook-only or CLI install organs.

Owner hub 1788319779.597119: Slack custom-tool jobs drive the named service
from the tagged remainder. This module covers the whole catalog. Facebook
Graph POST stays the peer organ in slack_service_drivers.py. Slack CLI /
Bolt install stays PR 7452. @magicpath with peer_harness_connected stays a
Slack custom-tool remainder — no new NEED.

Missing tags never reject a Commons post. Secrets never appear in results.
Live HTTP is opt-in. Default is dry-run READY or OWNER_SIGNIN.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "host"))

import slack_service_drivers as facebook_peer  # noqa: E402
import slack_service_tag as sst  # noqa: E402
import slack_spark_mcp_driver as spark_peer  # noqa: E402


HttpFn = Callable[..., Any]

ENV_KEYS: dict[str, tuple[str, ...]] = {
    "facebook": facebook_peer.TOKEN_ENV,
    "instagram": ("INSTAGRAM_ACCESS_TOKEN",),
    "linkedin": ("LINKEDIN_ACCESS_TOKEN",),
    "x": ("X_ACCESS_TOKEN", "TWITTER_ACCESS_TOKEN"),
    "threads": ("THREADS_ACCESS_TOKEN",),
    "tiktok": ("TIKTOK_ACCESS_TOKEN",),
    "youtube": ("YOUTUBE_ACCESS_TOKEN",),
    "reddit": ("REDDIT_ACCESS_TOKEN",),
    "bluesky": ("BLUESKY_APP_PASSWORD",),
    "discord": ("DISCORD_BOT_TOKEN", "DISCORD_WEBHOOK_URL"),
    "whatsapp": ("WHATSAPP_ACCESS_TOKEN",),
    "telegram": ("TELEGRAM_BOT_TOKEN",),
    "github": ("GITHUB_TOKEN", "GH_TOKEN"),
    "gmail": ("GMAIL_ACCESS_TOKEN",),
    "google": ("GOOGLE_ACCESS_TOKEN",),
    "calendar": ("GOOGLE_CALENDAR_ACCESS_TOKEN", "GOOGLE_ACCESS_TOKEN"),
    "drive": ("GOOGLE_DRIVE_ACCESS_TOKEN", "GOOGLE_ACCESS_TOKEN"),
    "dropbox": ("DROPBOX_ACCESS_TOKEN",),
    "notion": ("NOTION_TOKEN",),
    "linear": ("LINEAR_API_KEY",),
    "figma": ("FIGMA_ACCESS_TOKEN",),
    "stripe": ("STRIPE_SECRET_KEY",),
    "shopify": ("SHOPIFY_ACCESS_TOKEN",),
    "paypal": ("PAYPAL_ACCESS_TOKEN",),
    "salesforce": ("SALESFORCE_ACCESS_TOKEN",),
    "hubspot": ("HUBSPOT_ACCESS_TOKEN",),
    "zoom": ("ZOOM_ACCESS_TOKEN",),
    "heygen": ("HEYGEN_API_KEY",),
    "magicpath": ("MAGICPATH_API_KEY",),
    "roboflow": ("ROBOFLOW_API_KEY",),
    "agentmail": ("AGENTMAIL_API_KEY",),
    "openai": ("OPENAI_API_KEY",),
    "anthropic": ("ANTHROPIC_API_KEY",),
    "xai": ("XAI_API_KEY",),
    "cursor": (),
    "commons": (),
    "spark": (),
    "slack": ("SLACK_BOT_TOKEN",),
}

# Official public consoles / APIs. Never a password field. Never a Commons login.
SIGNIN_URLS: dict[str, str] = {
    "facebook": "https://developers.facebook.com/apps/",
    "instagram": "https://developers.facebook.com/docs/instagram-platform/",
    "linkedin": "https://www.linkedin.com/developers/apps",
    "x": "https://developer.x.com/en/portal/dashboard",
    "threads": "https://developers.facebook.com/docs/threads",
    "tiktok": "https://developers.tiktok.com/",
    "youtube": "https://console.cloud.google.com/apis/library/youtube.googleapis.com",
    "reddit": "https://www.reddit.com/prefs/apps",
    "bluesky": "https://bsky.app/settings",
    "discord": "https://discord.com/developers/applications",
    "whatsapp": "https://developers.facebook.com/docs/whatsapp/cloud-api/get-started",
    "telegram": "https://my.telegram.org/apps",
    "google": "https://console.cloud.google.com/",
    "calendar": "https://console.cloud.google.com/apis/library/calendar-json.googleapis.com",
    "drive": "https://console.cloud.google.com/apis/library/drive.googleapis.com",
    "dropbox": "https://www.dropbox.com/developers/apps",
    "notion": "https://www.notion.so/my-integrations",
    "linear": "https://linear.app/settings/api",
    "figma": "https://www.figma.com/developers",
    "stripe": "https://dashboard.stripe.com/apikeys",
    "shopify": "https://partners.shopify.com/",
    "paypal": "https://developer.paypal.com/dashboard/",
    "salesforce": "https://login.salesforce.com/",
    "hubspot": "https://app.hubspot.com/",
    "zoom": "https://marketplace.zoom.us/develop/create",
    "heygen": "https://app.heygen.com/settings",
    "roboflow": "https://app.roboflow.com/settings/api",
    "openai": "https://platform.openai.com/api-keys",
    "anthropic": "https://console.anthropic.com/",
    "xai": "https://console.x.ai/",
}

INTENTS: dict[str, dict[str, str]] = {
    "facebook": {"method": "POST", "url": "https://graph.facebook.com/v21.0/me/feed"},
    "instagram": {"method": "GET", "url": "https://graph.facebook.com/v21.0/me"},
    "linkedin": {"method": "GET", "url": "https://api.linkedin.com/v2/me"},
    "x": {"method": "GET", "url": "https://api.x.com/2/users/me"},
    "threads": {"method": "GET", "url": "https://graph.threads.net/v1.0/me"},
    "tiktok": {"method": "GET", "url": "https://open.tiktokapis.com/v2/user/info/"},
    "youtube": {
        "method": "GET",
        "url": "https://www.googleapis.com/youtube/v3/channels?part=id&mine=true",
    },
    "reddit": {"method": "GET", "url": "https://oauth.reddit.com/api/v1/me"},
    "bluesky": {
        "method": "GET",
        "url": "https://bsky.social/xrpc/com.atproto.server.getSession",
    },
    "discord": {"method": "GET", "url": "https://discord.com/api/v10/users/@me"},
    "whatsapp": {"method": "GET", "url": "https://graph.facebook.com/v21.0/me"},
    "telegram": {"method": "GET", "url": "https://api.telegram.org/bot/getMe"},
    "github": {"method": "GET", "url": "https://api.github.com/user"},
    "gmail": {
        "method": "GET",
        "url": "https://gmail.googleapis.com/gmail/v1/users/me/profile",
    },
    "google": {"method": "GET", "url": "https://www.googleapis.com/oauth2/v2/userinfo"},
    "calendar": {
        "method": "GET",
        "url": "https://www.googleapis.com/calendar/v3/users/me/calendarList",
    },
    "drive": {
        "method": "GET",
        "url": "https://www.googleapis.com/drive/v3/about?fields=user",
    },
    "dropbox": {
        "method": "POST",
        "url": "https://api.dropboxapi.com/2/users/get_current_account",
    },
    "notion": {"method": "GET", "url": "https://api.notion.com/v1/users/me"},
    "linear": {"method": "POST", "url": "https://api.linear.app/graphql"},
    "figma": {"method": "GET", "url": "https://api.figma.com/v1/me"},
    "stripe": {"method": "GET", "url": "https://api.stripe.com/v1/balance"},
    "shopify": {"method": "GET", "url": "https://partners.shopify.com/"},
    "paypal": {
        "method": "GET",
        "url": "https://api-m.paypal.com/v1/identity/oauth2/userinfo",
    },
    "salesforce": {
        "method": "GET",
        "url": "https://login.salesforce.com/services/oauth2/userinfo",
    },
    "hubspot": {
        "method": "GET",
        "url": "https://api.hubapi.com/crm/v3/objects/contacts?limit=1",
    },
    "zoom": {"method": "GET", "url": "https://api.zoom.us/v2/users/me"},
    "heygen": {"method": "GET", "url": "https://api.heygen.com/v2/user/remaining_quota"},
    "magicpath": {"method": "GET", "url": "https://www.magicpath.ai/"},
    "roboflow": {"method": "GET", "url": "https://api.roboflow.com/"},
    "agentmail": {"method": "GET", "url": "https://api.agentmail.to/v0/inboxes"},
    "openai": {"method": "GET", "url": "https://api.openai.com/v1/models"},
    "anthropic": {"method": "GET", "url": "https://api.anthropic.com/v1/models"},
    "xai": {"method": "GET", "url": "https://api.x.ai/v1/models"},
    "cursor": {"method": "GET", "url": "https://cursor.com/"},
    "commons": {
        "method": "GET",
        "url": "https://woahwhattheheck.github.io/commons/",
    },
    "spark": {"method": "POST", "url": spark_peer.SPARK_MCP_URL},
    "slack": {"method": "GET", "url": "https://slack.com/api/auth.test"},
}


def _base() -> dict[str, Any]:
    return {
        "ok": False,
        "gate": False,
        "commons_admission": False,
        "copy_secrets": False,
        "http_called": False,
    }


def _env_present(tag: str, environ: dict[str, str] | None = None) -> bool:
    env = environ if environ is not None else os.environ
    keys = ENV_KEYS.get(tag, ())
    return any(bool(str(env.get(key) or "").strip()) for key in keys)


def _env_token(tag: str, environ: dict[str, str] | None = None) -> str:
    env = environ if environ is not None else os.environ
    for key in ENV_KEYS.get(tag, ()):
        val = str(env.get(key) or "").strip()
        if val:
            return val
    return ""


def _peer_harness(spec: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(spec, dict):
        return None
    raw = spec.get("peer_harness_connected")
    if not isinstance(raw, dict):
        return None
    if not str(raw.get("desk") or "").strip() and not str(raw.get("source_ts") or "").strip():
        return None
    return raw


def catalog_services(catalog: dict[str, Any] | None = None) -> dict[str, Any]:
    cat = catalog if catalog is not None else sst.load_catalog()
    services = cat.get("services") or {}
    return services if isinstance(services, dict) else {}


def drive(
    tag: str,
    body: str = "",
    *,
    connected: list[str] | tuple[str, ...] | None = None,
    catalog: dict[str, Any] | None = None,
    environ: dict[str, str] | None = None,
    execute: bool = False,
    http_request: HttpFn | None = None,
) -> dict[str, Any]:
    """Drive one catalog tag. Never invent a provider post. Never copy secrets."""
    cat = catalog if catalog is not None else sst.load_catalog()
    name = sst.canonical_tag(tag, cat)
    services = catalog_services(cat)
    spec = services.get(name) if name in services else None
    intent = dict(INTENTS.get(name) or {})
    out = _base()
    out.update(
        {
            "tag": name,
            "slack_tool": "@" + name if name else "",
            "body": str(body or "").strip(),
            "intent": intent or None,
        }
    )
    if not name:
        out["road"] = "UNKNOWN"
        out["reason"] = "missing_tag"
        return out
    if spec is None:
        out["road"] = "UNKNOWN"
        out["reason"] = "unknown_tag"
        return out

    connected_ids = {str(x).lower() for x in (connected or []) if str(x).strip()}
    in_when = {str(x).lower() for x in (spec.get("in_harness_when") or [])}
    if in_when & connected_ids:
        out["ok"] = True
        out["road"] = "IN_HARNESS"
        out["reason"] = "in_harness"
        return out

    peer = _peer_harness(spec)
    if peer:
        out["ok"] = True
        out["road"] = "SLACK_CUSTOM_TOOL"
        out["reason"] = "peer_harness_remainder"
        out["peer_desk"] = str(peer.get("desk") or "")
        out["this_process_tools"] = False
        out["reopen_need"] = False
        seats = peer.get("measured_cloud_seats")
        if isinstance(seats, list) and seats:
            out["measured_cloud_seats"] = [
                str(seat).strip() for seat in seats if str(seat).strip()
            ]
        return out

    if name == "facebook":
        # Peer organ: real Graph POST when a token exists. Do not remint it.
        peer_out = facebook_peer.drive_facebook(str(body or ""))
        out.update(peer_out)
        out["gate"] = False
        out["commons_admission"] = False
        out["copy_secrets"] = False
        return out

    if name == "spark":
        # Unique organ: live no-auth Commons Spark MCP. Do not steal it back.
        peer_out = spark_peer.drive_spark(
            str(body or ""),
            execute=execute,
            http_request=http_request,
        )
        out.update(peer_out)
        out["gate"] = False
        out["commons_admission"] = False
        out["copy_secrets"] = False
        return out

    if _env_present(name, environ):
        if execute and http_request is not None and intent:
            token = _env_token(name, environ)
            headers = {"Authorization": "Bearer " + token} if token else {}
            http_request(
                method=str(intent.get("method") or "GET"),
                url=str(intent.get("url") or ""),
                headers=headers,
            )
            out["http_called"] = True
            out["ok"] = True
            out["road"] = "SLACK_CUSTOM_TOOL"
            out["reason"] = "driven"
            out["request_header_keys"] = ["Authorization"] if token else []
            return out
        out["ok"] = True
        out["road"] = "SLACK_CUSTOM_TOOL"
        out["reason"] = "ready_dry_run"
        return out

    if spec.get("needs_owner_signin"):
        url = SIGNIN_URLS.get(name) or ""
        out["road"] = "OWNER_SIGNIN"
        out["reason"] = "no_%s_session_in_this_process" % name
        out["signin_url"] = url
        out["channel_id"] = "C0BUFA9G23E"
        out["channel_name"] = "#provider-sign-in"
        return out

    out["ok"] = True
    out["road"] = "SLACK_CUSTOM_TOOL"
    out["reason"] = "no_local_session"
    return out


def drive_text(
    text: str,
    *,
    connected: list[str] | tuple[str, ...] | None = None,
    catalog: dict[str, Any] | None = None,
    environ: dict[str, str] | None = None,
    execute: bool = False,
    http_request: HttpFn | None = None,
) -> dict[str, Any]:
    """Route a Slack body, then drive every catalog tag. Not a Commons gate."""
    cat = catalog if catalog is not None else sst.load_catalog()
    conn = list(connected or ["slack"])
    route = sst.route(text, connected=conn, catalog=cat)
    outcomes: list[dict[str, Any]] = []
    seen: set[str] = set()
    for job in route.get("jobs") or []:
        tag = str(job.get("tag") or "")
        if not tag or tag in seen:
            continue
        seen.add(tag)
        if str(job.get("road") or "") == "IN_HARNESS":
            outcomes.append(
                {
                    "ok": True,
                    "tag": tag,
                    "road": "IN_HARNESS",
                    "reason": "in_harness",
                    "gate": False,
                    "commons_admission": False,
                    "copy_secrets": False,
                    "body": str(job.get("body") or ""),
                }
            )
            continue
        outcomes.append(
            drive(
                tag,
                str(job.get("body") or route.get("body") or ""),
                connected=conn,
                catalog=cat,
                environ=environ,
                execute=execute,
                http_request=http_request,
            )
        )
    return {
        "gate": False,
        "commons_admission": False,
        "copy_secrets": False,
        "tags": list(route.get("tags") or []),
        "body": str(route.get("body") or ""),
        "route": route,
        "outcomes": outcomes,
    }


def format_slack_posts(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Harness-facing Slack posts. MagicPath peer remainder never opens NEED."""
    posts: list[dict[str, Any]] = []
    tags = payload.get("tags") or []
    roads = [str(row.get("road") or "") for row in payload.get("outcomes") or []]
    if tags:
        posts.append(
            {
                "channel": None,
                "kind": "SLACK_CUSTOM_TOOL",
                "text": (
                    "service-tag-job tags=%s roads=%s gate=false\n"
                    "Slack custom-tool job — remainder:\n%s"
                    % (",".join(tags), ",".join(roads), payload.get("body") or "")
                ),
                "copy_secrets": False,
            }
        )
    for row in payload.get("outcomes") or []:
        tag = str(row.get("tag") or "")
        road = str(row.get("road") or "")
        if road == "OWNER_SIGNIN":
            posts.append(
                {
                    "channel": "C0BUFA9G23E",
                    "kind": "OWNER_BLOCKER",
                    "tag": tag,
                    "text": (
                        "service-tag-job OWNER_BLOCKER @%s\n"
                        "NEED: complete the official %s provider session\n"
                        "SMALLEST ACTION: open %s\n"
                        "Do not paste a password, API key, session token, or other secret into Slack."
                        % (tag, tag, row.get("signin_url") or "")
                    ),
                    "copy_secrets": False,
                }
            )
        else:
            extra = ""
            if row.get("peer_desk"):
                extra = " peer_desk=%s reopen_need=false" % row.get("peer_desk")
            posts.append(
                {
                    "channel": None,
                    "kind": road or "SLACK_CUSTOM_TOOL",
                    "tag": tag,
                    "text": (
                        "service-tag-job drive @%s ok=%s road=%s reason=%s%s"
                        % (
                            tag,
                            row.get("ok"),
                            road,
                            row.get("reason") or "ran",
                            extra,
                        )
                    ),
                    "copy_secrets": False,
                }
            )
    return posts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--text", default="", help="Slack message with @tags")
    parser.add_argument("--tag", default="", help="single catalog tag")
    parser.add_argument("--body", default="", help="tagged remainder")
    parser.add_argument(
        "--connected",
        default="slack",
        help="comma-separated in-harness tools",
    )
    args = parser.parse_args(argv)
    connected = [p.strip() for p in str(args.connected).split(",") if p.strip()]
    if args.text:
        payload = drive_text(args.text, connected=connected)
        print(json.dumps(payload, indent=2))
        return 0
    out = drive(args.tag, args.body, connected=connected)
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
