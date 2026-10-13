#!/usr/bin/env python3
"""Microsoft Teams transport primitives for Commons (stdlib only).

Outbound Commons events use a Teams Workflow webhook and Adaptive Cards.
Inbound Teams outgoing-webhook activities can be normalized for the existing
Commons append roads. Microsoft signs that provider callback with HMAC-SHA256;
the verifier here implements that wire contract without restricting Commons
callers, verbs, or content.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Callable


MAX_MESSAGE_BYTES = 28 * 1024
CONTENT_TYPE = "application/vnd.microsoft.card.adaptive"
USER_AGENT = "commons-microsoft-teams/1"


def canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def _card(title: str, text: str, url: str, marker: str) -> dict[str, Any]:
    body: list[dict[str, Any]] = [
        {
            "type": "TextBlock",
            "text": title,
            "weight": "Bolder",
            "size": "Medium",
            "wrap": True,
        },
        {"type": "TextBlock", "text": text, "wrap": True},
        {"type": "TextBlock", "text": marker, "isSubtle": True, "wrap": True},
    ]
    content: dict[str, Any] = {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.2",
        "body": body,
    }
    if url:
        content["actions"] = [
            {"type": "Action.OpenUrl", "title": "Open in Commons", "url": url}
        ]
    return {
        "type": "message",
        "attachments": [
            {"contentType": CONTENT_TYPE, "contentUrl": None, "content": content}
        ],
    }


def adaptive_card(
    *,
    title: str,
    text: str,
    url: str = "",
    event_id: str = "",
    max_bytes: int = MAX_MESSAGE_BYTES,
) -> dict[str, Any]:
    """Build a Teams Adaptive Card envelope within the connector byte limit.

    Only the free-form body is shortened. The title, Commons event marker, and
    destination URL remain intact so a delivered card is attributable.
    """
    title, text, url = str(title), str(text), str(url)
    marker = f"commons:{event_id or hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]}"
    full = _card(title, text, url, marker)
    if len(canonical(full)) <= max_bytes:
        return full

    empty = _card(title, "", url, marker)
    if len(canonical(empty)) > max_bytes:
        raise ValueError("Teams card metadata exceeds the message byte limit")

    suffix = "…"
    low, high = 0, len(text)
    while low < high:
        middle = (low + high + 1) // 2
        candidate = _card(title, text[:middle] + suffix, url, marker)
        if len(canonical(candidate)) <= max_bytes:
            low = middle
        else:
            high = middle - 1
    return _card(title, text[:low] + suffix, url, marker)


def post_workflow(
    webhook_url: str,
    payload: dict[str, Any],
    *,
    attempts: int = 5,
    timeout: float = 20,
    opener: Callable[..., Any] = urllib.request.urlopen,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, int]:
    """POST a card to a Teams Workflow, retrying throttles/server errors."""
    data = canonical(payload)
    if len(data) > MAX_MESSAGE_BYTES:
        raise ValueError("Teams payload exceeds the 28 KB message limit")
    if attempts < 1:
        raise ValueError("attempts must be positive")

    request = urllib.request.Request(
        webhook_url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
    )
    for attempt in range(1, attempts + 1):
        try:
            with opener(request, timeout=timeout) as response:
                status = int(getattr(response, "status", response.getcode()))
                response.read()
            if status < 200 or status >= 300:
                raise OSError(f"Teams Workflow returned HTTP {status}")
            return {"status": status, "attempts": attempt, "bytes": len(data)}
        except urllib.error.HTTPError as error:
            retryable = error.code == 429 or 500 <= error.code <= 599
            if not retryable or attempt == attempts:
                raise
            retry_after = error.headers.get("Retry-After", "") if error.headers else ""
            try:
                delay = max(float(retry_after), 0.0)
            except ValueError:
                delay = min(2 ** (attempt - 1), 16)
            if not retry_after:
                delay = min(2 ** (attempt - 1), 16)
            sleep(delay)
    raise AssertionError("unreachable")


def verify_outgoing_hmac(
    raw_body: bytes, authorization: str, signing_key_base64: str
) -> bool:
    """Check the HMAC signature required by the Teams outgoing-webhook wire."""
    supplied = authorization.strip()
    if supplied.lower().startswith("hmac "):
        supplied = supplied[5:].strip()
    try:
        key = base64.b64decode(signing_key_base64, validate=True)
    except (ValueError, base64.binascii.Error):
        return False
    expected = base64.b64encode(
        hmac.new(key, raw_body, hashlib.sha256).digest()
    ).decode("ascii")
    return hmac.compare_digest(supplied, expected)


def normalize_outgoing_activity(payload: dict[str, Any]) -> dict[str, Any]:
    """Preserve a Teams activity while exposing stable Commons event fields."""
    sender = payload.get("from") if isinstance(payload.get("from"), dict) else {}
    conversation = (
        payload.get("conversation")
        if isinstance(payload.get("conversation"), dict)
        else {}
    )
    channel_data = (
        payload.get("channelData")
        if isinstance(payload.get("channelData"), dict)
        else {}
    )
    return {
        "source": "microsoft-teams",
        "kind": str(payload.get("type", "message")),
        "native_id": str(payload.get("id", "")),
        "text": str(payload.get("text", "")),
        "author": {"id": str(sender.get("id", "")), "name": str(sender.get("name", ""))},
        "conversation_id": str(conversation.get("id", "")),
        "service_url": str(payload.get("serviceUrl", "")),
        "channel_data": channel_data,
        "raw": payload,
    }


def outgoing_response(text: str) -> dict[str, str]:
    """Return the synchronous message shape accepted by outgoing webhooks."""
    return {"type": "message", "text": str(text)}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Commons Microsoft Teams transport")
    sub = parser.add_subparsers(dest="command", required=True)
    card = sub.add_parser("card", help="render an Adaptive Card envelope")
    card.add_argument("--title", required=True)
    card.add_argument("--text", required=True)
    card.add_argument("--url", default="")
    card.add_argument("--event-id", default="")
    send = sub.add_parser("send", help="send an Adaptive Card to a Teams Workflow")
    send.add_argument("--title", required=True)
    send.add_argument("--text", required=True)
    send.add_argument("--url", default="")
    send.add_argument("--event-id", default="")
    send.add_argument("--webhook-env", default="TEAMS_WORKFLOW_URL")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    payload = adaptive_card(
        title=args.title, text=args.text, url=args.url, event_id=args.event_id
    )
    if args.command == "card":
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    webhook_url = os.environ.get(args.webhook_env, "").strip()
    if not webhook_url:
        print(f"{args.webhook_env} is not set", file=sys.stderr)
        return 2
    receipt = post_workflow(webhook_url, payload)
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
