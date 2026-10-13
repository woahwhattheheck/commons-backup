#!/usr/bin/env python3
"""Slack-side custom-tool worker for @service tags.

Bryce 1788319997.911589: install the tools. This worker is the installed
runtime: read channel history, route @facebook (and the rest) through
slack_service_tag, drive what this process can, queue provider sessions on
#provider-sign-in. Missing tags never reject a Commons post. No secrets in git.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from commons_publication_policy import check_publication
sys.path.insert(0, str(ROOT / "host"))

import slack_service_drivers as drivers  # noqa: E402
import slack_service_tag as sst  # noqa: E402

JOB_MARKER = "service-tag-job"
DEFAULT_CHANNELS = ("C0BU51F1PL3", "C0BRGMDQB6G", "C0BUFA9G23E")
LOGIN_CHANNEL = "C0BUFA9G23E"
API = "https://slack.com/api/"


def load_install(catalog: dict[str, Any] | None = None) -> dict[str, Any]:
    cat = catalog if catalog is not None else sst.load_catalog()
    install = cat.get("install") if isinstance(cat.get("install"), dict) else {}
    return {
        "login_channel_id": str(install.get("login_channel", {}).get("id") or LOGIN_CHANNEL),
        "job_marker": str(install.get("job_marker") or JOB_MARKER),
        "watch_channels": list(install.get("watch_channels") or DEFAULT_CHANNELS),
        "gate": False,
    }


def already_handled(replies: list[dict[str, Any]], marker: str = JOB_MARKER) -> bool:
    needle = str(marker or JOB_MARKER)
    for row in replies or []:
        text = str((row or {}).get("text") or "")
        if needle in text:
            return True
    return False


def connected_from_env(env: dict[str, str] | None = None) -> list[str]:
    src = env if env is not None else os.environ
    found = ["slack"]
    if str(src.get("GITHUB_TOKEN") or src.get("GH_TOKEN") or "").strip():
        found.append("github")
    if str(src.get("FACEBOOK_PAGE_ACCESS_TOKEN") or src.get("FACEBOOK_ACCESS_TOKEN") or "").strip():
        found.append("facebook")
    extra = str(src.get("SLACK_SERVICE_TAG_CONNECTED") or "").strip()
    for part in extra.split(","):
        name = part.strip().lower()
        if name and name not in found:
            found.append(name)
    return found


def _delivery_marker(
    token: str, channel: str, ts: str, marker: str, call: Callable, page_limit: int
) -> dict[str, Any]:
    """Read enough of the thread to find a marker or establish its absence."""
    cursor = ""
    seen: set[str] = set()
    for _ in range(page_limit):
        payload = {"channel": channel, "ts": ts, "limit": "20"}
        if cursor:
            payload["cursor"] = cursor
        response = call(token, "conversations.replies", payload)
        if not response.get("ok"):
            return response
        replies = response.get("messages")
        if not isinstance(replies, list) or any(not isinstance(row, dict) for row in replies):
            return {"ok": False, "error": "invalid_replies"}
        if already_handled(replies, marker):
            return {"ok": True, "handled": True}
        metadata = response.get("response_metadata") or {}
        if not isinstance(metadata, dict) or not isinstance(metadata.get("next_cursor", ""), str):
            return {"ok": False, "error": "invalid_replies_cursor"}
        cursor = metadata.get("next_cursor", "").strip()
        if not cursor:
            if response.get("has_more"):
                return {"ok": False, "error": "incomplete_replies"}
            return {"ok": True, "handled": False}
        if cursor in seen:
            return {"ok": False, "error": "repeated_replies_cursor"}
        seen.add(cursor)
    return {"ok": False, "error": "replies_page_limit"}


def posts_for_message(
    text: str,
    *,
    channel: str,
    ts: str,
    connected: list[str] | None = None,
    catalog: dict[str, Any] | None = None,
    drive: Callable[[str, str], dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Turn one Slack message into chat.postMessage payloads. Never a Commons gate."""
    cat = catalog if catalog is not None else sst.load_catalog()
    install = load_install(cat)
    result = sst.route(text, connected=connected or ["slack"], catalog=cat)
    if not result.get("tags"):
        return []
    drive_fn = drive or drivers.drive
    marker = install["job_marker"]
    login = install["login_channel_id"]
    posts: list[dict[str, Any]] = []
    roads = [str(j.get("road")) for j in result.get("jobs") or []]
    posts.append(
        {
            "channel": channel,
            "thread_ts": ts,
            "text": (
                "%s tags=%s roads=%s gate=false\n"
                "Slack custom-tool job — remainder:\n%s"
                % (marker, ",".join(result["tags"]), ",".join(roads), result.get("body") or "")
            ),
        }
    )
    for job in result.get("slack_jobs") or []:
        kind = str(job.get("kind") or "")
        tag = str(job.get("tag") or "")
        body = str(job.get("text") or result.get("body") or "")
        if kind == "OWNER_BLOCKER":
            posts.append(
                {
                    "channel": login,
                    "thread_ts": None,
                    "text": (
                        "%s OWNER_BLOCKER @%s from %s ts=%s\n%s"
                        % (marker, tag, channel, ts, job.get("text") or "")
                    ),
                }
            )
        if kind == "SLACK_CUSTOM_TOOL":
            outcome = drive_fn(tag, body)
            peer_desk = str(job.get("peer_desk") or "")
            extra = (" peer_desk=%s this_process_tools=false" % peer_desk) if peer_desk else ""
            posts.append(
                {
                    "channel": channel,
                    "thread_ts": ts,
                    "text": (
                        "%s drive @%s ok=%s road=%s reason=%s%s"
                        % (
                            marker,
                            tag,
                            outcome.get("ok"),
                            outcome.get("road"),
                            outcome.get("reason") or "ran",
                            extra,
                        )
                    ),
                }
            )
            # Route already queued OWNER_BLOCKER for needs-session tags.
            # Do not double-post that queue when the driver also reports sign-in.
    return posts


def _api(token: str, method: str, payload: dict[str, Any]) -> dict[str, Any]:
    data = urllib.parse.urlencode({k: v for k, v in payload.items() if v is not None}).encode(
        "utf-8"
    )
    req = urllib.request.Request(
        API + method,
        data=data,
        method="POST",
        headers={"Authorization": "Bearer " + token},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        result = {"ok": False, "error": "http_%s" % exc.code, "http_status": exc.code}
        if exc.code == 429:
            result["error"] = "ratelimited"
            try:
                result["retry_after"] = max(0, int(exc.headers.get("Retry-After", "")))
            except (AttributeError, TypeError, ValueError):
                result["retry_after"] = None
        return result
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {"ok": False, "error": type(exc).__name__}
    try:
        parsed = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        return {"ok": False, "error": "bad_json"}
    return parsed if isinstance(parsed, dict) else {"ok": False, "error": "not_object"}


def poll_and_dispatch(
    token: str,
    *,
    channels: list[str] | None = None,
    connected: list[str] | None = None,
    catalog: dict[str, Any] | None = None,
    api: Callable[[str, str, dict[str, Any]], dict[str, Any]] | None = None,
    limit: int = 20,
    reply_page_limit: int = 10,
) -> dict[str, Any]:
    cat = catalog if catalog is not None else sst.load_catalog()
    install = load_install(cat)
    marker = install["job_marker"]
    watch = channels or install["watch_channels"]
    conn = connected if connected is not None else connected_from_env()
    call = api or _api
    handled = 0
    skipped = 0
    errors: list[str] = []

    def failed(response: dict[str, Any], where: str, method: str) -> dict[str, Any] | None:
        errors.append("%s:%s" % (where, response.get("error") or "failed"))
        if response.get("http_status") == 429 or response.get("error") in (
            "ratelimited", "rate_limited"
        ):
            # Return control to the caller; do not turn one exhausted allowance
            # into a request for every remaining channel, thread, and post.
            return {
                "ok": False,
                "gate": False,
                "handled": handled,
                "skipped": skipped,
                "errors": errors,
                "rate_limited": True,
                "retry_after": response.get("retry_after"),
                "retry_method": method,
            }
        return None

    for channel in watch:
        hist = call(token, "conversations.history", {"channel": channel, "limit": str(limit)})
        if not hist.get("ok"):
            stopped = failed(hist, channel, "conversations.history")
            if stopped is not None:
                return stopped
            continue
        for msg in hist.get("messages") or []:
            if not isinstance(msg, dict):
                continue
            ts = str(msg.get("ts") or "")
            text = str(msg.get("text") or "")
            if not ts or JOB_MARKER in text:
                continue
            if not check_publication(text)["allowed"]:
                skipped += 1
                continue
            if not sst.extract_tags(text, cat):
                continue
            replies_pack = _delivery_marker(token, channel, ts, marker, call, reply_page_limit)
            if not replies_pack.get("ok"):
                # An unreadable deduplication record is unknown, not empty.
                # Leave the message for a later successful poll before driving
                # its services again.
                stopped = failed(replies_pack, "%s:%s:replies" % (channel, ts), "conversations.replies")
                if stopped is not None:
                    return stopped
                continue
            if replies_pack.get("handled"):
                skipped += 1
                continue
            for post in posts_for_message(
                text, channel=channel, ts=ts, connected=conn, catalog=cat
            ):
                publication = check_publication(str(post.get("text") or ""))
                if not publication["allowed"]:
                    errors.append(publication["code"])
                    continue
                sent = call(token, "chat.postMessage", post)
                if not sent.get("ok"):
                    stopped = failed(sent, "post", "chat.postMessage")
                    if stopped is not None:
                        return stopped
            handled += 1
    return {
        "ok": not errors,
        "gate": False,
        "handled": handled,
        "skipped": skipped,
        "errors": errors,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--text", default="", help="dispatch one body without polling")
    parser.add_argument("--channel", default="C0BU51F1PL3")
    parser.add_argument("--ts", default="")
    parser.add_argument("--connected", default="")
    parser.add_argument("--poll", action="store_true")
    parser.add_argument("--reply-pages", type=int, default=10,
                        help="maximum deduplication reply pages per message (default: 10)")
    args = parser.parse_args(argv)
    if args.reply_pages < 1:
        parser.error("--reply-pages must be positive")
    connected = [p.strip() for p in str(args.connected).split(",") if p.strip()] or connected_from_env()
    if args.poll:
        token = str(os.environ.get("SLACK_BOT_TOKEN") or "").strip()
        if not token:
            print("idle: SLACK_BOT_TOKEN is not configured", flush=True)
            return 0
        result = poll_and_dispatch(token, connected=connected, reply_page_limit=args.reply_pages)
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok") else 1
    if args.text:
        posts = posts_for_message(args.text, channel=args.channel, ts=args.ts, connected=connected)
        print(json.dumps({"gate": False, "posts": posts}, indent=2))
        return 0
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
