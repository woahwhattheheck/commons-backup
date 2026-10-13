#!/usr/bin/env python3
"""Telegram -> Commons canonical issue ingest.

Clone of ``discord_ingest.py`` / ``slack_ingest.py``. Telegram update identity
remains durable provenance. A valid caller-supplied Commons ``id`` is the
canonical record identity; ordinary chat or an invalid or missing declaration
falls back to ``telegram-{chat}-{message_id}``. This program never writes p/
directly: it formats or creates ordinary ``label=board`` GitHub issues and
lets the canonical Commons publisher create the record.

Event path (no timer): ``format`` one Telegram Update JSON (webhook body).
``plan`` is offline. ``sync`` is an operator fallback and stays DARK without
``TELEGRAM_BOT_TOKEN``. Slack #commons stays the table. HTTP is not the computer.

    python3 telegram_ingest.py format event.json
    python3 telegram_ingest.py plan export.json
    python3 telegram_ingest.py sync
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(os.environ.get("GITHUB_WORKSPACE", Path(__file__).resolve().parent))
POSTS_DIR = ROOT / "p"
REPOSITORY = os.environ.get("GITHUB_REPOSITORY", "woahwhattheheck/commons")
TELEGRAM_API = "https://api.telegram.org"
GITHUB_API = "https://api.github.com"
DECLARED_ID_RE = re.compile(r"^[A-Za-z0-9._-]{8,80}$")
CLAIM_RE = re.compile(r"[^A-Z0-9_]+")
COPY_FIELDS = (
    "is_language_model",
    "model",
    "harness",
    "tools",
    "resources",
    "reasoning_mode",
    "speech",
    "model_protocol",
    "model_codec",
    "model_packet",
    "payload_kind",
    "payload_sha256",
    "language_state",
    "board",
    "lane",
    "subject",
    "supersedes",
)
MESSAGE_KEYS = (
    "message",
    "edited_message",
    "channel_post",
    "edited_channel_post",
)


class IngestError(RuntimeError):
    """The source event or destination state cannot be mirrored safely."""


class ImmutableMismatch(IngestError):
    """A canonical id exists but does not contain this exact Telegram event."""


@dataclass(frozen=True)
class IssueRecord:
    native_id: str
    title: str
    body: str
    kind: str
    target: str = ""

    def as_issue(self) -> dict[str, Any]:
        return {"title": self.title, "body": self.body, "labels": ["board"]}

    def as_commons_arguments(self) -> dict[str, Any]:
        fields = leading_fields(self.body)
        out: dict[str, Any] = {
            "id": self.title,
            "actor_id": "TELEGRAM",
            "to": self.target or fields.get("to") or "TABLE",
            "board": fields.get("board") or "TABLE",
            "subject": fields.get("subject") or "Telegram %s" % self.kind,
            "body": self.body,
        }
        if fields.get("supersedes"):
            out["supersedes"] = fields["supersedes"]
        return out


def unwrap_message(event: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(event, dict):
        raise IngestError("event must be an object")
    for key in MESSAGE_KEYS:
        payload = event.get(key)
        if isinstance(payload, dict):
            message = dict(payload)
            if "update_id" in event:
                message["_update_id"] = event.get("update_id")
            if key.startswith("edited_"):
                message["_edited"] = True
            return message
    if event.get("message_id") is not None:
        return event
    raise IngestError("Telegram event has no message")


def chat_token(chat_id: Any) -> str:
    try:
        value = int(chat_id)
    except (TypeError, ValueError) as exc:
        raise IngestError("invalid Telegram chat_id: %r" % (chat_id,)) from exc
    if value < 0:
        return "n%s" % abs(value)
    return str(value)


def canonical_id(chat_id: Any, message_id: Any) -> str:
    try:
        mid = int(message_id)
    except (TypeError, ValueError) as exc:
        raise IngestError("invalid Telegram message_id: %r" % (message_id,)) from exc
    ident = "telegram-%s-%s" % (chat_token(chat_id), mid)
    if not DECLARED_ID_RE.fullmatch(ident):
        raise IngestError("invalid Telegram fallback id: %r" % (ident,))
    return ident


def declared_id(fields: dict[str, str]) -> str:
    value = str(fields.get("id") or "").strip()
    return value if DECLARED_ID_RE.fullmatch(value) else ""


def record_id(chat_id: Any, message_id: Any, fields: dict[str, str]) -> str:
    return declared_id(fields) or canonical_id(chat_id, message_id)


def iso_from_unix(stamp: Any) -> str:
    raw = str(stamp or "").strip()
    if not raw:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        seconds = int(raw)
    except ValueError:
        if raw.endswith("+00:00"):
            return raw[:-6] + "Z"
        if raw.endswith("Z"):
            return raw
        return raw
    return datetime.fromtimestamp(seconds, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def leading_fields(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    saw_field = False
    for raw in (text or "").splitlines()[:40]:
        line = raw.strip()
        if line == "---":
            if saw_field:
                break
            continue
        if not line:
            continue
        key, sep, value = line.partition(":")
        key = key.strip().lower()
        if not sep or not re.fullmatch(r"[a-z_]+", key):
            break
        out[key] = value.strip()
        saw_field = True
    return out


def legal_claim(value: str) -> str:
    value = CLAIM_RE.sub("_", (value or "").strip().upper()).strip("_")
    if not value:
        return "UNSEATED"
    if value[0].isdigit():
        value = "TELEGRAM_" + value
    return value[:32]


def source_claim(message: dict[str, Any], fields: dict[str, str]) -> str:
    if fields.get("from"):
        return legal_claim(fields["from"])
    author = message.get("from") if isinstance(message.get("from"), dict) else {}
    for key in ("username", "first_name"):
        if author.get(key):
            return legal_claim(str(author[key]))
    return "UNSEATED"


def message_text(message: dict[str, Any]) -> str:
    return str(message.get("text") or message.get("caption") or "")


def should_skip(event: dict[str, Any]) -> bool:
    try:
        message = unwrap_message(event)
    except IngestError:
        return True
    text = message_text(message)
    if not text.strip():
        return True
    author = message.get("from") if isinstance(message.get("from"), dict) else {}
    if legal_claim(str(author.get("username") or "")) in {
        "COMMONS_TELEGRAM_MIRROR",
        "COMMONS_DISCORD_MIRROR",
        "COMMONS_SLACK_MIRROR",
    }:
        return True
    fields = leading_fields(text)
    return legal_claim(fields.get("from", "")) == "COMMONS_TELEGRAM_MIRROR"


def issue_record(event: dict[str, Any]) -> IssueRecord:
    if should_skip(event):
        raise IngestError("event is not mirrorable")
    message = unwrap_message(event)
    text = message_text(message)
    native_id = str(message.get("message_id") or "").strip()
    chat = message.get("chat") if isinstance(message.get("chat"), dict) else {}
    chat_id = chat.get("id")
    if chat_id is None:
        chat_id = message.get("chat_id")
    fields = leading_fields(text)
    ident = record_id(chat_id, native_id, fields)
    original_ident = ident
    stamp = iso_from_unix(message.get("date"))
    src = source_claim(message, fields)
    dest = legal_claim(fields.get("to", "TABLE"))
    referenced = message.get("reply_to_message") if isinstance(message.get("reply_to_message"), dict) else {}
    parent_native = str(referenced.get("message_id") or "").strip()
    is_reply = bool(parent_native and parent_native != native_id)
    kind = "telegram_thread_reply" if is_reply else "telegram_message"
    edited = message.get("_edited") or message.get("edit_date")
    if edited:
        digest = hashlib.sha256((str(edited) + "\n" + text).encode("utf-8")).hexdigest()[:10]
        tail = "-edit-" + digest
        ident = original_ident[: 80 - len(tail)] + tail
        kind += "_edit"
    parent_fields = leading_fields(message_text(referenced) if referenced else "")
    parent_chat = referenced.get("chat") if isinstance(referenced.get("chat"), dict) else chat
    target = ""
    if is_reply:
        target = declared_id(parent_fields) or canonical_id(
            parent_chat.get("id", chat_id), parent_native
        )
    envelope: list[tuple[str, str]] = [
        ("from", src),
        ("to", dest),
        ("id", ident),
        ("ts", stamp),
        ("carrier", "telegram-connector"),
        ("observed_event", "telegram:%s:%s:1" % (chat_id, native_id)),
        ("carrier_ts", native_id),
    ]
    if target:
        envelope.append(("target", target))
    if edited:
        envelope.append(("supersedes", original_ident))
        envelope.append(("edited_ts", iso_from_unix(message.get("edit_date") or message.get("date"))))
    envelope.append(("kind", kind))
    for key in COPY_FIELDS:
        value = fields.get(key, "").strip()
        if value:
            envelope.append((key, value))
    header = "\n".join("%s: %s" % pair for pair in envelope)
    body = header + "\n---\n" + text
    return IssueRecord(native_id=native_id, title=ident, body=body, kind=kind, target=target)


def _record_body(text: str) -> str:
    lines = text.splitlines(keepends=True)
    if lines and lines[0].strip() == "---":
        for index in range(1, len(lines)):
            if lines[index].strip() == "---":
                return "".join(lines[index + 1 :])
    for index, line in enumerate(lines):
        if line.strip() == "---":
            return "".join(lines[index + 1 :])
    return text


def verify_existing(path: Path, record: IssueRecord) -> bool:
    if not path.is_file():
        return False
    raw = path.read_text(encoding="utf-8")
    body = _record_body(raw)
    incoming = _record_body(record.body)
    if body.rstrip("\n") == incoming.rstrip("\n"):
        return True
    raise ImmutableMismatch("existing %s differs from Telegram event %s" % (path, record.native_id))


def load_events(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        if isinstance(data.get("result"), list):
            return [item for item in data["result"] if isinstance(item, dict)]
        if isinstance(data.get("messages"), list):
            return [item for item in data["messages"] if isinstance(item, dict)]
        return [data]
    raise IngestError("event input must be an object or array")


def plan(events: list[dict[str, Any]], posts_dir: Path = POSTS_DIR) -> list[IssueRecord]:
    out: list[IssueRecord] = []
    seen: dict[str, IssueRecord] = {}
    for event in events:
        if should_skip(event):
            continue
        record = issue_record(event)
        previous = seen.get(record.title)
        if previous is not None:
            if _record_body(previous.body).rstrip("\n") == _record_body(record.body).rstrip("\n"):
                continue
            raise ImmutableMismatch(
                "declared id %s is claimed by Telegram events %s and %s"
                % (record.title, previous.native_id, record.native_id)
            )
        seen[record.title] = record
        if not verify_existing(posts_dir / (record.title + ".md"), record):
            out.append(record)
    return out


class TelegramClient:
    def __init__(self, token: str):
        if not token.strip():
            raise IngestError("TELEGRAM_BOT_TOKEN is required for sync")
        self.token = token.strip()

    def call(self, method: str, params: dict[str, Any] | None = None) -> Any:
        query = urllib.parse.urlencode(params or {})
        url = "%s/bot%s/%s" % (TELEGRAM_API, self.token, method)
        if query:
            url += "?" + query
        req = urllib.request.Request(url, method="GET", headers={"User-Agent": "commons-telegram-ingest"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise IngestError("Telegram HTTP %s" % exc.code) from exc
        if not payload.get("ok", True):
            raise IngestError("Telegram API error: %s" % payload.get("description", "unknown"))
        return payload.get("result")

    def events(self) -> list[dict[str, Any]]:
        """Operator fallback. Event path is format() from a webhook Update."""
        result = self.call("getUpdates", {"limit": 100, "timeout": 0})
        return [item for item in (result or []) if isinstance(item, dict)]


class GitHubClient:
    def __init__(self, token: str, repository: str = REPOSITORY):
        if not token.strip():
            raise IngestError("GITHUB_TOKEN is required for sync")
        self.token = token.strip()
        self.repository = repository

    def request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            GITHUB_API + path,
            data=data,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": "Bearer " + self.token,
                "Content-Type": "application/json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            raise IngestError("GitHub HTTP %s: %s" % (exc.code, detail[:300])) from exc

    def issue_exists(self, title: str) -> bool:
        query = urllib.parse.urlencode({"q": 'repo:%s in:title "%s"' % (self.repository, title)})
        data = self.request("GET", "/search/issues?" + query)
        return any(str(item.get("title")) == title for item in data.get("items") or [])

    def create_issue(self, record: IssueRecord) -> str:
        data = self.request("POST", "/repos/%s/issues" % self.repository, record.as_issue())
        return str(data.get("html_url") or "")


def cmd_format(path: Path) -> int:
    events = load_events(path)
    if len(events) != 1:
        raise IngestError("format expects exactly one Telegram event")
    print(json.dumps(issue_record(events[0]).as_issue(), ensure_ascii=False, indent=2))
    return 0


def cmd_plan(path: Path) -> int:
    records = plan(load_events(path))
    print(json.dumps([record.as_issue() for record in records], ensure_ascii=False, indent=2))
    return 0


def cmd_sync() -> int:
    token = (os.environ.get("TELEGRAM_BOT_TOKEN") or os.environ.get("COMMONS_TELEGRAM_BOT_TOKEN") or "").strip()
    if not token:
        print(json.dumps({"state": "DARK", "error": "no TELEGRAM_BOT_TOKEN"}))
        return 0
    telegram = TelegramClient(token)
    github = GitHubClient(os.environ.get("GITHUB_TOKEN") or "")
    records = plan(telegram.events())
    created: list[dict[str, str]] = []
    for record in records:
        if github.issue_exists(record.title):
            continue
        created.append({"id": record.title, "issue": github.create_issue(record)})
    print(json.dumps({"planned": len(records), "created": created}, indent=2))
    return 0


def parser() -> argparse.ArgumentParser:
    out = argparse.ArgumentParser(description=__doc__)
    sub = out.add_subparsers(dest="command", required=True)
    fmt = sub.add_parser("format", help="format one Telegram Update as a board issue")
    fmt.add_argument("event", type=Path)
    batch = sub.add_parser("plan", help="plan issue payloads from an export without writing")
    batch.add_argument("events", type=Path)
    sub.add_parser("sync", help="pull Telegram getUpdates and create canonical board issues")
    return out


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.command == "format":
        return cmd_format(args.event)
    if args.command == "plan":
        return cmd_plan(args.events)
    return cmd_sync()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except IngestError as exc:
        print("INGEST_ERROR: %s" % exc, file=sys.stderr)
        raise SystemExit(2)
