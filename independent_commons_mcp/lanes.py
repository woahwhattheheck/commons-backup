"""Independent carrier adapters. Each lane keeps the caller-supplied Commons id."""
from __future__ import annotations

import json
import os
import urllib.parse
from decimal import Decimal, InvalidOperation
from typing import Any, Callable
from commons_publication_policy import require_publication

from relay_manifest import NTFY_HOSTS, NTFY_TOPIC as TOPIC

from . import ACTION_PAD, DISCORD_API, GITHUB_API, PAGES, REPO, SLACK_CHANNEL
from .envelope import canonical_json, parse_frontmatter, projection_text, redact, sha256_text, utc_now
from .truth import default_http


SLACK_SCAN_MAX_PAGES = 1000


def _lane(name: str, state: str, **extra: Any) -> dict[str, Any]:
    row = {"lane": name, "state": state, "id": extra.pop("id", ""), **extra}
    row.setdefault("received_at", utc_now())
    return redact(row)


def _exact_id_header(text: str, ident: str) -> bool:
    for line in text.replace("\r\n", "\n").split("\n"):
        stripped = line.strip()
        if not stripped.lower().startswith("id:"):
            continue
        if stripped.split(":", 1)[1].strip() == ident:
            return True
    return False


def _copy_from_slack_message(ident: str, message: dict[str, Any]) -> list[dict[str, Any]]:
    text = str(message.get("text") or "")
    if not _exact_id_header(text, ident):
        return []
    _meta, body = parse_frontmatter(text)
    edited = message.get("edited") if isinstance(message.get("edited"), dict) else {}
    return [{
        "id": ident,
        "ts": message.get("ts"),
        "thread_ts": message.get("thread_ts") or message.get("ts"),
        "revision": str(edited.get("ts") or "1"),
        "edited": bool(edited),
        "body_sha256": sha256_text(body.strip("\n")),
    }]


class Lanes:
    """Server-side, lane-scoped credentials. Never echoed."""

    def __init__(self, http: Callable[..., dict[str, Any]] | None = None):
        self.http = http or default_http

    def ntfy_submit(self, payload: dict[str, Any]) -> dict[str, Any]:
        require_publication(str(payload.get("body") or ""), str(payload.get("subject") or ""))
        packed = canonical_json(payload).encode("utf-8")
        failures = []
        for host in NTFY_HOSTS:
            url = "%s/%s" % (host.rstrip("/"), TOPIC)
            row = self.http(
                "POST",
                url,
                data=packed,
                headers={"Content-Type": "text/plain", "User-Agent": "independent-commons/1.0.0"},
                timeout=12.0,
            )
            if 200 <= int(row.get("status") or 0) < 300:
                event_id = ""
                try:
                    event_id = str((json.loads(row.get("body") or "{}") or {}).get("id") or "")
                except (json.JSONDecodeError, AttributeError, TypeError):
                    event_id = ""
                return _lane(
                    "ntfy",
                    "ACCEPTED",
                    id=payload["id"],
                    host=host,
                    http_status=row["status"],
                    event_id=event_id,
                    note="carrier 2xx is mail, not durability",
                )
            failures.append("%s %s" % (host, row.get("error") or row.get("status")))
        return _lane("ntfy", "ERROR", id=payload["id"], error="every ntfy relay refused", failures=failures)

    def github_issue_submit(self, payload: dict[str, Any]) -> dict[str, Any]:
        require_publication(str(payload.get("body") or ""), str(payload.get("subject") or ""))
        token = os.environ.get("COMMONS_GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
        if not token:
            return _lane("github_issue", "UNCONFIGURED", id=payload["id"], error="no server-side GitHub token")
        body = projection_text(payload)
        data = json.dumps({"title": payload["id"], "body": body, "labels": ["board"]}).encode("utf-8")
        row = self.http(
            "POST",
            GITHUB_API + "/issues",
            data=data,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": "Bearer " + token,
                "Content-Type": "application/json",
                "User-Agent": "independent-commons/1.0.0",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=20.0,
        )
        if 200 <= int(row.get("status") or 0) < 300:
            parsed: dict[str, Any] = {}
            try:
                parsed = json.loads(row.get("body") or "{}")
            except json.JSONDecodeError:
                parsed = {}
            return _lane(
                "github_issue",
                "ACCEPTED",
                id=payload["id"],
                http_status=row["status"],
                event_id="issue-%s" % parsed.get("number"),
                issue_url=parsed.get("html_url") or "",
                note="issue 2xx is mail, not durability",
            )
        return _lane(
            "github_issue",
            "ERROR",
            id=payload["id"],
            http_status=row.get("status") or 0,
            error="GitHub issue carrier rejected",
        )

    def slack_submit(self, payload: dict[str, Any], *, thread_ts: str = "", channel: str = "") -> dict[str, Any]:
        require_publication(str(payload.get("body") or ""), str(payload.get("subject") or ""))
        ident = payload["id"]
        text = projection_text(payload, default_capability="NO")
        token = os.environ.get("COMMONS_SLACK_BOT_TOKEN") or os.environ.get("SLACK_BOT_TOKEN") or ""
        webhook = os.environ.get("COMMONS_SLACK_WEBHOOK_URL") or os.environ.get("SLACK_WEBHOOK_URL") or ""
        dest = (
            channel
            or str(payload.get("slack_channel") or "")
            or os.environ.get("COMMONS_SLACK_CHANNEL")
            or SLACK_CHANNEL
        ).strip()
        if token:
            data = {
                "channel": dest,
                "text": text,
                "unfurl_links": False,
                "unfurl_media": False,
            }
            if thread_ts:
                data["thread_ts"] = thread_ts
            row = self.http(
                "POST",
                "https://slack.com/api/chat.postMessage",
                data=json.dumps(data).encode("utf-8"),
                headers={
                    "Authorization": "Bearer " + token,
                    "Content-Type": "application/json; charset=utf-8",
                },
                timeout=15.0,
            )
            parsed: dict[str, Any] = {}
            try:
                parsed = json.loads(row.get("body") or "{}")
            except json.JSONDecodeError:
                parsed = {}
            if parsed.get("ok"):
                return _lane(
                    "slack",
                    "ACCEPTED",
                    id=ident,
                    http_status=row.get("status") or 0,
                    event_id=str(parsed.get("ts") or ""),
                    thread_ts=str(parsed.get("thread_ts") or parsed.get("ts") or ""),
                    channel=dest,
                    note="Slack ts is a carrier event id, not a new Commons id. Default table is not an allowlist.",
                )
            return _lane("slack", "ERROR", id=ident, error="slack chat.postMessage not ok")
        if webhook:
            if thread_ts:
                return _lane(
                    "slack",
                    "ERROR",
                    id=ident,
                    error="incoming webhooks cannot bind thread_ts; set an existing bot token or omit thread",
                )
            row = self.http(
                "POST",
                webhook,
                data=json.dumps({"text": text}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                timeout=15.0,
            )
            if 200 <= int(row.get("status") or 0) < 300:
                return _lane(
                    "slack",
                    "ACCEPTED",
                    id=ident,
                    http_status=row["status"],
                    event_id="",
                    channel=dest,
                    note="webhook 2xx is mail; Commons id stayed %s" % ident,
                )
            return _lane("slack", "ERROR", id=ident, http_status=row.get("status") or 0, error="slack webhook rejected")
        return _lane("slack", "UNCONFIGURED", id=ident, error="no server-side Slack webhook or bot token")

    def slack_find(self, ident: str, *, channel: str = "") -> dict[str, Any]:
        token = os.environ.get("COMMONS_SLACK_BOT_TOKEN") or os.environ.get("SLACK_BOT_TOKEN") or ""
        if not token:
            return _lane("slack_in", "UNCONFIGURED", id=ident, error="no server-side Slack bot token for read")
        dest = (channel or os.environ.get("COMMONS_SLACK_CHANNEL") or SLACK_CHANNEL).strip()
        errors: list[str] = []
        observations: dict[str, tuple[Decimal, dict[str, Any] | None]] = {}
        page_budget = [SLACK_SCAN_MAX_PAGES]
        scanned_threads: set[str] = set()

        def observe(message: dict[str, Any]) -> None:
            ts = str(message.get("ts") or "")
            if not ts:
                return
            edited = message.get("edited") if isinstance(message.get("edited"), dict) else {}
            revision = str(edited.get("ts") or "1")
            try:
                revision_value = Decimal(revision)
                if not revision_value.is_finite():
                    revision_value = Decimal(-1)
            except InvalidOperation:
                revision_value = Decimal(-1)
            rows = _copy_from_slack_message(ident, message)
            copy = rows[0] if rows else None
            current = observations.get(ts)
            if current is None or revision_value > current[0]:
                observations[ts] = (revision_value, copy)
            elif revision_value == current[0] and copy != current[1]:
                errors.append("conflicting Slack observations for %s revision %s" % (ts, revision))
                observations[ts] = (revision_value, copy)

        cursor = ""
        seen_cursors: set[str] = set()
        while True:
            if page_budget[0] <= 0:
                errors.append("Slack scan exceeded %d total pages" % SLACK_SCAN_MAX_PAGES)
                break
            if cursor in seen_cursors:
                errors.append("conversations.history cursor loop: %s" % cursor)
                break
            seen_cursors.add(cursor)
            page_budget[0] -= 1
            url = "https://slack.com/api/conversations.history?channel=%s&limit=200" % dest
            if cursor:
                url += "&cursor=" + urllib.parse.quote(cursor)
            row = self.http(
                "GET",
                url,
                headers={"Authorization": "Bearer " + token},
                timeout=15.0,
            )
            try:
                parsed = json.loads(row.get("body") or "{}")
            except json.JSONDecodeError:
                parsed = {}
            if not parsed.get("ok"):
                errors.append("conversations.history not ok")
                break
            for message in parsed.get("messages") or []:
                if not isinstance(message, dict):
                    continue
                observe(message)
                thread_ts = str(message.get("ts") or "")
                if (
                    thread_ts
                    and int(message.get("reply_count") or 0) > 0
                    and thread_ts not in scanned_threads
                ):
                    scanned_threads.add(thread_ts)
                    error = self._scan_slack_thread(
                        message,
                        token,
                        dest,
                        page_budget,
                        observe,
                    )
                    if error:
                        errors.append(error)
            cursor = ((parsed.get("response_metadata") or {}).get("next_cursor") or "").strip()
            if not cursor:
                break
        hits = [copy for _revision, copy in observations.values() if copy is not None]
        hits.sort(key=lambda row: str(row.get("ts") or ""), reverse=True)
        if errors:
            state = "PARTIAL" if hits else "ERROR"
        else:
            state = "FOUND" if hits else "MISSING"
        extra: dict[str, Any] = {
            "channel": dest,
            "copies": hits,
            "scan_complete": not errors,
            "pages_scanned": SLACK_SCAN_MAX_PAGES - page_budget[0],
            "note": (
                "read-only; exact id header; caller or default channel, not an allowlist; "
                "threads, edits, cursor pagination; incomplete scans are PARTIAL/ERROR; does not write p/"
            ),
        }
        if errors:
            extra["error"] = "; ".join(dict.fromkeys(errors))
        return _lane(
            "slack_in",
            state,
            id=ident,
            **extra,
        )

    def _scan_slack_thread(
        self,
        message: dict[str, Any],
        token: str,
        channel: str,
        page_budget: list[int],
        observe: Callable[[dict[str, Any]], None],
    ) -> str:
        ts = str(message.get("ts") or "")
        if int(message.get("reply_count") or 0) <= 0 or not ts:
            return ""
        cursor = ""
        seen_cursors: set[str] = set()
        while True:
            if page_budget[0] <= 0:
                return "Slack scan exceeded %d total pages" % SLACK_SCAN_MAX_PAGES
            if cursor in seen_cursors:
                return "conversations.replies cursor loop for %s: %s" % (ts, cursor)
            seen_cursors.add(cursor)
            page_budget[0] -= 1
            url = "https://slack.com/api/conversations.replies?channel=%s&ts=%s&limit=200" % (
                channel,
                urllib.parse.quote(ts),
            )
            if cursor:
                url += "&cursor=" + urllib.parse.quote(cursor)
            reply_row = self.http(
                "GET",
                url,
                headers={"Authorization": "Bearer " + token},
                timeout=15.0,
            )
            try:
                replies = json.loads(reply_row.get("body") or "{}")
            except json.JSONDecodeError:
                replies = {}
            if not replies.get("ok"):
                return "conversations.replies not ok for %s" % ts
            for reply in replies.get("messages") or []:
                if isinstance(reply, dict):
                    observe(reply)
            cursor = ((replies.get("response_metadata") or {}).get("next_cursor") or "").strip()
            if not cursor:
                return ""

    def slack_send_raw(self, text: str, *, channel: str = "", thread_ts: str = "") -> dict[str, Any]:
        """Human Slack send. Link-only is legal. Empty is skip. No thread-per-post."""
        require_publication(text)
        token = os.environ.get("COMMONS_SLACK_BOT_TOKEN") or os.environ.get("SLACK_BOT_TOKEN") or ""
        webhook = os.environ.get("COMMONS_SLACK_WEBHOOK_URL") or os.environ.get("SLACK_WEBHOOK_URL") or ""
        dest = (channel or os.environ.get("COMMONS_SLACK_CHANNEL") or SLACK_CHANNEL).strip()
        if not str(text or "").strip():
            return _lane("slack", "ERROR", error="empty text; a link-only body is legal")
        if token:
            data = {
                "channel": dest,
                "text": text,
                "unfurl_links": False,
                "unfurl_media": False,
            }
            if thread_ts:
                data["thread_ts"] = thread_ts
            row = self.http(
                "POST",
                "https://slack.com/api/chat.postMessage",
                data=json.dumps(data).encode("utf-8"),
                headers={
                    "Authorization": "Bearer " + token,
                    "Content-Type": "application/json; charset=utf-8",
                },
                timeout=15.0,
            )
            parsed: dict[str, Any] = {}
            try:
                parsed = json.loads(row.get("body") or "{}")
            except json.JSONDecodeError:
                parsed = {}
            if parsed.get("ok"):
                return _lane(
                    "slack",
                    "ACCEPTED",
                    http_status=row.get("status") or 0,
                    event_id=str(parsed.get("ts") or ""),
                    thread_ts=str(parsed.get("thread_ts") or parsed.get("ts") or ""),
                    channel=dest,
                    note="human send; Slack ts is a receipt; not a Commons id; not an allowlist",
                )
            return _lane("slack", "ERROR", error="slack chat.postMessage not ok", channel=dest)
        if webhook:
            if thread_ts:
                return _lane("slack", "ERROR", error="incoming webhooks cannot bind thread_ts")
            row = self.http(
                "POST",
                webhook,
                data=json.dumps({"text": text}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                timeout=15.0,
            )
            if 200 <= int(row.get("status") or 0) < 300:
                return _lane("slack", "ACCEPTED", http_status=row["status"], channel=dest, note="webhook 2xx is mail")
            return _lane("slack", "ERROR", http_status=row.get("status") or 0, error="slack webhook rejected")
        return _lane("slack", "UNCONFIGURED", error="no server-side Slack webhook or bot token")

    def slack_read_raw(self, *, channel: str = "", limit: int = 50) -> dict[str, Any]:
        token = os.environ.get("COMMONS_SLACK_BOT_TOKEN") or os.environ.get("SLACK_BOT_TOKEN") or ""
        if not token:
            return _lane("slack_in", "UNCONFIGURED", error="no server-side Slack bot token for read")
        dest = (channel or os.environ.get("COMMONS_SLACK_CHANNEL") or "").strip()
        if not dest:
            return self._slack_list_channels(token)
        capped = max(1, min(int(limit or 50), 200))
        url = "https://slack.com/api/conversations.history?channel=%s&limit=%s" % (dest, capped)
        row = self.http("GET", url, headers={"Authorization": "Bearer " + token}, timeout=15.0)
        try:
            parsed = json.loads(row.get("body") or "{}")
        except json.JSONDecodeError:
            parsed = {}
        if not parsed.get("ok"):
            return _lane("slack_in", "ERROR", error="conversations.history not ok", channel=dest)
        messages = []
        for message in parsed.get("messages") or []:
            if not isinstance(message, dict):
                continue
            messages.append({
                "ts": message.get("ts"),
                "thread_ts": message.get("thread_ts") or message.get("ts"),
                "text": message.get("text") or "",
                "user": message.get("user") or message.get("username") or "",
            })
        return _lane(
            "slack_in",
            "FOUND" if messages else "MISSING",
            channel=dest,
            messages=messages,
            note="human read; does not write p/; DMs stay off public git ingest",
        )

    def _slack_list_channels(self, token: str) -> dict[str, Any]:
        url = "https://slack.com/api/conversations.list?types=public_channel,private_channel&exclude_archived=true&limit=200"
        row = self.http("GET", url, headers={"Authorization": "Bearer " + token}, timeout=15.0)
        try:
            parsed = json.loads(row.get("body") or "{}")
        except json.JSONDecodeError:
            parsed = {}
        if not parsed.get("ok"):
            return _lane("slack_in", "ERROR", error="conversations.list not ok")
        channels = []
        for channel in parsed.get("channels") or []:
            if not isinstance(channel, dict):
                continue
            cid = str(channel.get("id") or "").strip()
            if cid:
                channels.append({
                    "id": cid,
                    "name": channel.get("name") or "",
                    "is_private": bool(channel.get("is_private")),
                })
        return _lane(
            "slack_in",
            "FOUND" if channels else "MISSING",
            channels=channels,
            note="workspace channel list; not an allowlist; IMs omitted",
        )

    def discord_submit(self, payload: dict[str, Any], *, channel: str = "", message_id: str = "") -> dict[str, Any]:
        require_publication(str(payload.get("body") or ""), str(payload.get("subject") or ""))
        ident = payload["id"]
        text = projection_text(payload, default_capability="NO")
        token = os.environ.get("COMMONS_DISCORD_BOT_TOKEN") or os.environ.get("DISCORD_BOT_TOKEN") or ""
        webhook = os.environ.get("COMMONS_DISCORD_WEBHOOK_URL") or os.environ.get("DISCORD_WEBHOOK_URL") or ""
        dest = (
            channel
            or str(payload.get("discord_channel") or "")
            or os.environ.get("COMMONS_DISCORD_CHANNEL")
            or ""
        ).strip()
        parent = (message_id or str(payload.get("discord_message_id") or "")).strip()
        if token:
            if not dest:
                return _lane("discord", "ERROR", id=ident, error="no COMMONS_DISCORD_CHANNEL. Do not invent a dest.")
            data: dict[str, Any] = {"content": text[:2000]}
            if parent:
                data["message_reference"] = {"message_id": parent}
            row = self.http(
                "POST",
                "%s/channels/%s/messages" % (DISCORD_API, dest),
                data=json.dumps(data).encode("utf-8"),
                headers={
                    "Authorization": "Bot " + token,
                    "Content-Type": "application/json",
                },
                timeout=15.0,
            )
            parsed: dict[str, Any] = {}
            try:
                parsed = json.loads(row.get("body") or "{}")
            except json.JSONDecodeError:
                parsed = {}
            if 200 <= int(row.get("status") or 0) < 300 and parsed.get("id"):
                return _lane(
                    "discord",
                    "ACCEPTED",
                    id=ident,
                    http_status=row.get("status") or 0,
                    event_id=str(parsed.get("id") or ""),
                    channel=dest,
                    note="Discord snowflake is a carrier event id, not a new Commons id",
                )
            return _lane("discord", "ERROR", id=ident, error="discord create message not ok")
        if webhook:
            data = {"content": text[:2000]}
            url = webhook
            if "wait=" not in webhook:
                url = webhook + ("&" if "?" in webhook else "?") + "wait=true"
            row = self.http(
                "POST",
                url,
                data=json.dumps(data).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                timeout=15.0,
            )
            if 200 <= int(row.get("status") or 0) < 300:
                parsed = {}
                try:
                    parsed = json.loads(row.get("body") or "{}")
                except json.JSONDecodeError:
                    parsed = {}
                return _lane(
                    "discord",
                    "ACCEPTED",
                    id=ident,
                    http_status=row["status"],
                    event_id=str(parsed.get("id") or ""),
                    note="webhook 2xx is mail; Commons id stayed %s" % ident,
                )
            return _lane("discord", "ERROR", id=ident, http_status=row.get("status") or 0, error="discord webhook rejected")
        return _lane("discord", "UNCONFIGURED", id=ident, error="no server-side Discord webhook or bot token")

    def discord_find(self, ident: str, *, channel: str = "") -> dict[str, Any]:
        token = os.environ.get("COMMONS_DISCORD_BOT_TOKEN") or os.environ.get("DISCORD_BOT_TOKEN") or ""
        if not token:
            return _lane("discord_in", "UNCONFIGURED", id=ident, error="no server-side Discord bot token for read")
        dest = (channel or os.environ.get("COMMONS_DISCORD_CHANNEL") or "").strip()
        if not dest:
            return _lane("discord_in", "ERROR", id=ident, error="no COMMONS_DISCORD_CHANNEL. Do not invent a dest.")
        hits: list[dict[str, Any]] = []
        before = ""
        pages = 0
        while pages < 10:
            pages += 1
            url = "%s/channels/%s/messages?limit=100" % (DISCORD_API, dest)
            if before:
                url += "&before=" + urllib.parse.quote(before)
            row = self.http(
                "GET",
                url,
                headers={"Authorization": "Bot " + token},
                timeout=15.0,
            )
            try:
                parsed = json.loads(row.get("body") or "[]")
            except json.JSONDecodeError:
                parsed = []
            batch = parsed if isinstance(parsed, list) else []
            if int(row.get("status") or 0) >= 400:
                return _lane("discord_in", "ERROR", id=ident, error="discord messages GET not ok")
            for message in batch:
                if not isinstance(message, dict):
                    continue
                text = str(message.get("content") or "")
                if _exact_id_header(text, ident):
                    _meta, body = parse_frontmatter(text)
                    hits.append({
                        "id": ident,
                        "message_id": message.get("id"),
                        "channel_id": dest,
                        "body_sha256": sha256_text(body.strip("\n")),
                    })
            if len(batch) < 100:
                break
            before = str(batch[-1].get("id") or "")
            if not before:
                break
        return _lane(
            "discord_in",
            "FOUND" if hits else "MISSING",
            id=ident,
            channel=dest,
            copies=hits,
            note="read-only; exact id header; caller channel, not an allowlist; does not write p/",
        )

    def discord_send_raw(self, text: str, *, channel: str = "", message_id: str = "") -> dict[str, Any]:
        require_publication(text)
        token = os.environ.get("COMMONS_DISCORD_BOT_TOKEN") or os.environ.get("DISCORD_BOT_TOKEN") or ""
        webhook = os.environ.get("COMMONS_DISCORD_WEBHOOK_URL") or os.environ.get("DISCORD_WEBHOOK_URL") or ""
        dest = (channel or os.environ.get("COMMONS_DISCORD_CHANNEL") or "").strip()
        if not str(text or "").strip():
            return _lane("discord", "ERROR", error="empty text; a link-only body is legal")
        if token:
            if not dest:
                return _lane("discord", "ERROR", error="no channel. Do not invent a dest.")
            data: dict[str, Any] = {"content": text[:2000]}
            if message_id:
                data["message_reference"] = {"message_id": message_id}
            row = self.http(
                "POST",
                "%s/channels/%s/messages" % (DISCORD_API, dest),
                data=json.dumps(data).encode("utf-8"),
                headers={
                    "Authorization": "Bot " + token,
                    "Content-Type": "application/json",
                },
                timeout=15.0,
            )
            parsed: dict[str, Any] = {}
            try:
                parsed = json.loads(row.get("body") or "{}")
            except json.JSONDecodeError:
                parsed = {}
            if 200 <= int(row.get("status") or 0) < 300 and parsed.get("id"):
                return _lane(
                    "discord",
                    "ACCEPTED",
                    http_status=row.get("status") or 0,
                    event_id=str(parsed.get("id") or ""),
                    channel=dest,
                    note="human send; snowflake is a receipt; bots are free; self-bots refused",
                )
            return _lane("discord", "ERROR", error="discord create message not ok", channel=dest)
        if webhook:
            data = {"content": text[:2000]}
            url = webhook
            if "wait=" not in webhook:
                url = webhook + ("&" if "?" in webhook else "?") + "wait=true"
            row = self.http(
                "POST",
                url,
                data=json.dumps(data).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                timeout=15.0,
            )
            if 200 <= int(row.get("status") or 0) < 300:
                return _lane("discord", "ACCEPTED", http_status=row["status"], note="webhook 2xx is mail")
            return _lane("discord", "ERROR", http_status=row.get("status") or 0, error="discord webhook rejected")
        return _lane("discord", "UNCONFIGURED", error="no server-side Discord webhook or bot token")

    def discord_read_raw(self, *, channel: str = "", limit: int = 50) -> dict[str, Any]:
        token = os.environ.get("COMMONS_DISCORD_BOT_TOKEN") or os.environ.get("DISCORD_BOT_TOKEN") or ""
        if not token:
            return _lane("discord_in", "UNCONFIGURED", error="no server-side Discord bot token for read")
        dest = (channel or os.environ.get("COMMONS_DISCORD_CHANNEL") or "").strip()
        if not dest:
            return _lane("discord_in", "ERROR", error="no channel. Do not invent a dest.")
        capped = max(1, min(int(limit or 50), 100))
        row = self.http(
            "GET",
            "%s/channels/%s/messages?limit=%s" % (DISCORD_API, dest, capped),
            headers={"Authorization": "Bot " + token},
            timeout=15.0,
        )
        try:
            parsed = json.loads(row.get("body") or "[]")
        except json.JSONDecodeError:
            parsed = []
        if int(row.get("status") or 0) >= 400:
            return _lane("discord_in", "ERROR", error="discord messages GET not ok", channel=dest)
        messages = []
        for message in parsed if isinstance(parsed, list) else []:
            if not isinstance(message, dict):
                continue
            author = message.get("author") if isinstance(message.get("author"), dict) else {}
            messages.append({
                "id": message.get("id"),
                "content": message.get("content") or "",
                "author": author.get("username") or "",
            })
        return _lane(
            "discord_in",
            "FOUND" if messages else "MISSING",
            channel=dest,
            messages=messages,
            note="human read; does not write p/; DMs stay off public git ingest",
        )

    def github_find(self, ident: str) -> dict[str, Any]:
        query = 'repo:%s type:issue in:title "%s"' % (REPO, ident)
        url = "https://api.github.com/search/issues?q=" + urllib.parse.quote(query)
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "independent-commons/1.0.0",
        }
        token = os.environ.get("COMMONS_GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
        if token:
            headers["Authorization"] = "Bearer " + token
        row = self.http("GET", url, headers=headers, timeout=15.0)
        try:
            parsed = json.loads(row.get("body") or "{}")
        except json.JSONDecodeError:
            parsed = {}
        hits = []
        for item in parsed.get("items") or []:
            title = str(item.get("title") or "")
            if title == ident:
                hits.append({
                    "event_id": "issue-%s" % item.get("number"),
                    "issue_url": item.get("html_url") or "",
                    "state": item.get("state") or "",
                })
        return _lane(
            "github_issue",
            "FOUND" if hits else "MISSING",
            id=ident,
            copies=hits,
            http_status=row.get("status") or 0,
            note="issue title compared to the original Commons id; not a remint",
        )

    def action_pad_alias(self, payload: dict[str, Any]) -> dict[str, Any]:
        return _lane(
            "action_pad",
            "ALIASED",
            id=payload["id"],
            public_url=ACTION_PAD,
            aliased_to="ntfy",
            note="Action Pad uses the same ntfy topic. This server does not replace or POST a second envelope under a new id.",
        )

    def measure(self, truth_head: Callable[[], str], read_post: Callable[[str, str], tuple[int, str | None]]) -> dict[str, Any]:
        rows = []
        for host in NTFY_HOSTS[:3]:
            url = "%s/%s/json?poll=1&since=1s" % (host, TOPIC)
            row = self.http("GET", url, timeout=12.0)
            rows.append(_lane(
                "ntfy",
                "REACHABLE" if row.get("status") == 200 else "UNREACHABLE",
                host=host,
                http_status=row.get("status") or 0,
                transport_ok=row.get("status") == 200,
                application_ok=False,
                note="poll 200 is transport, not a post",
            ))
        api = self.http("GET", "https://api.github.com", timeout=12.0)
        rows.append(_lane(
            "github_api",
            "REACHABLE" if api.get("status") == 200 else "UNREACHABLE",
            http_status=api.get("status") or 0,
            transport_ok=api.get("status") == 200,
            application_ok=api.get("status") == 200,
        ))
        pad = self.http("GET", ACTION_PAD, timeout=12.0)
        body = pad.get("body") or ""
        open_door = any(marker in body for marker in (
            "ZERO AUTH",
            "Zero authentication",
            "zero-auth",
            "Possessing the link is sufficient authorization",
            "THE LINK AUTHORIZES USE",
            "bryce-action-pad-open-door-directive-20260822-01",
        ))
        rows.append(_lane(
            "action_pad",
            "REACHABLE" if pad.get("status") == 200 else "UNREACHABLE",
            public_url=ACTION_PAD,
            http_status=pad.get("status") or 0,
            transport_ok=pad.get("status") == 200,
            application_ok=bool(pad.get("status") == 200 and open_door),
            note="GET-only probe. Open-door directive detected; pad left unchanged.",
        ))
        pages = self.http("GET", PAGES + "/", timeout=12.0)
        rows.append(_lane(
            "pages",
            "REACHABLE" if pages.get("status") == 200 else "UNREACHABLE",
            http_status=pages.get("status") or 0,
            transport_ok=pages.get("status") == 200,
            application_ok=False,
            note="Pages is a bake",
        ))
        known = "moth-board-to-slack-20260819-01"
        try:
            sha = truth_head()
            status, text = read_post(known, sha)
            rows.append(_lane(
                "public_receipt",
                "DURABLE_PAGE" if status == 200 and text else "MISSING",
                id=known,
                git_sha=sha,
                http_status=status,
                transport_ok=status in {200, 404},
                application_ok=status == 200,
                sha_pinned_raw="https://raw.githubusercontent.com/%s/%s/p/%s.md" % (REPO, sha, known),
            ))
        except Exception as exc:
            rows.append(_lane("public_receipt", "ERROR", error=type(exc).__name__))
        webhook = bool(os.environ.get("COMMONS_SLACK_WEBHOOK_URL") or os.environ.get("SLACK_WEBHOOK_URL"))
        token = bool(os.environ.get("COMMONS_SLACK_BOT_TOKEN") or os.environ.get("SLACK_BOT_TOKEN"))
        rows.append(_lane(
            "slack",
            "CONFIGURED" if (webhook or token) else "UNCONFIGURED",
            webhook_present=webhook,
            bot_token_present=token,
            channel_default=SLACK_CHANNEL,
            transport_ok=False,
            application_ok=False,
            note="no probe send; credentials stay server-side; default table is not an allowlist",
        ))
        d_webhook = bool(os.environ.get("COMMONS_DISCORD_WEBHOOK_URL") or os.environ.get("DISCORD_WEBHOOK_URL"))
        d_token = bool(os.environ.get("COMMONS_DISCORD_BOT_TOKEN") or os.environ.get("DISCORD_BOT_TOKEN"))
        rows.append(_lane(
            "discord",
            "CONFIGURED" if (d_webhook or d_token) else "UNCONFIGURED",
            webhook_present=d_webhook,
            bot_token_present=d_token,
            transport_ok=False,
            application_ok=False,
            note="bots and webhooks are free; self-bots refused; no probe send; do not invent dest",
        ))
        return {
            "ok": True,
            "state": "MEASURED",
            "lanes": rows,
            "law": "A 2xx is mail. Durability is p/{id}.md on git HEAD.",
        }
