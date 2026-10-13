#!/usr/bin/env python3
"""Discord -> Commons canonical issue ingest.

Discord snowflake identity remains durable provenance. A valid caller-supplied
Commons ``id`` is the canonical record identity; ordinary chat or an invalid
or missing declaration falls back to ``discord-{snowflake}``. A git-first
record that already owns that id with different bytes is not reminted: the
Discord event falls back to its snowflake so inbound can continue. This program
never writes p/ directly: it formats or creates ordinary ``label=board``
GitHub issues and lets the canonical Commons publisher create the record.

Discord bot applications are FREE. Self-bots on a human account are TOS.
Missing token → format/plan still work; sync is DARK.

    python3 discord_ingest.py format event.json
    python3 discord_ingest.py plan export.json
    python3 discord_ingest.py sync
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

from commons_publication_policy import PublicationPolicyViolation, check_publication, require_publication

ROOT = Path(os.environ.get("GITHUB_WORKSPACE", Path(__file__).resolve().parent))
POSTS_DIR = ROOT / "p"
REPOSITORY = os.environ.get("GITHUB_REPOSITORY", "woahwhattheheck/commons")
DISCORD_API = "https://discord.com/api/v10"
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


class IngestError(RuntimeError):
    """The source event or destination state cannot be mirrored safely."""


class ImmutableMismatch(IngestError):
    """A canonical id exists but does not contain this exact Discord event."""


def github_next_url(link_header: str) -> str:
    """Return the Link header ``rel=next`` URL, or empty if this is the last page."""
    for part in (link_header or "").split(","):
        section = part.strip()
        if 'rel="next"' not in section and "rel=next" not in section:
            continue
        start = section.find("<")
        end = section.find(">", start + 1)
        if start >= 0 and end > start:
            return section[start + 1 : end]
    return ""


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
        """Return the same record for the public no-auth Commons MCP road."""
        fields = leading_fields(self.body)
        out: dict[str, Any] = {
            "id": self.title,
            "actor_id": "DISCORD",
            "to": self.target or fields.get("to") or "TABLE",
            "board": fields.get("board") or "TABLE",
            "subject": fields.get("subject") or "Discord %s" % self.kind,
            "body": self.body,
        }
        if fields.get("supersedes"):
            out["supersedes"] = fields["supersedes"]
        return out


def canonical_id(native_id: str) -> str:
    value = str(native_id or "").strip()
    if not value.isdigit():
        raise IngestError("invalid Discord snowflake: %r" % (native_id,))
    return "discord-%s" % value


def declared_id(fields: dict[str, str]) -> str:
    value = str(fields.get("id") or "").strip()
    return value if DECLARED_ID_RE.fullmatch(value) else ""


def record_id(native_id: str, fields: dict[str, str]) -> str:
    return declared_id(fields) or canonical_id(native_id)


def iso_from_discord(stamp: str) -> str:
    raw = str(stamp or "").strip()
    if not raw:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if raw.endswith("+00:00"):
        return raw[:-6] + "Z"
    if raw.endswith("Z"):
        return raw
    return raw


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
        value = "DISCORD_" + value
    return value[:32]


def source_claim(message: dict[str, Any], fields: dict[str, str]) -> str:
    if fields.get("from"):
        return legal_claim(fields["from"])
    author = message.get("author") if isinstance(message.get("author"), dict) else {}
    for key in ("username", "global_name"):
        if author.get(key):
            return legal_claim(str(author[key]))
    return "UNSEATED"


def should_skip(message: dict[str, Any]) -> bool:
    text = str(message.get("content") or message.get("text") or "")
    if not text.strip():
        return True
    author = message.get("author") if isinstance(message.get("author"), dict) else {}
    if author.get("bot") and legal_claim(str(author.get("username") or "")) in {
        "COMMONS_DISCORD_MIRROR",
        "COMMONS_SLACK_MIRROR",
    }:
        return True
    fields = leading_fields(text)
    return legal_claim(fields.get("from", "")) == "COMMONS_DISCORD_MIRROR"


def issue_record(message: dict[str, Any]) -> IssueRecord:
    if should_skip(message):
        raise IngestError("event is not mirrorable")
    text = str(message.get("content") or message.get("text") or "")
    native_id = str(message.get("id") or "").strip()
    channel_id = str(message.get("channel_id") or message.get("channel") or "").strip()
    guild_id = str(message.get("guild_id") or "").strip()
    fields = leading_fields(text)
    ident = record_id(native_id, fields)
    original_ident = ident
    stamp = iso_from_discord(str(message.get("timestamp") or ""))
    src = source_claim(message, fields)
    dest = legal_claim(fields.get("to", "TABLE"))
    referenced = message.get("referenced_message") if isinstance(message.get("referenced_message"), dict) else {}
    parent_native = str(referenced.get("id") or message.get("message_reference", {}).get("message_id") or "").strip()
    is_reply = bool(parent_native and parent_native != native_id)
    kind = "discord_thread_reply" if is_reply else "discord_message"
    edited = str(message.get("edited_timestamp") or "").strip()
    if edited:
        digest = hashlib.sha256((edited + "\n" + text).encode("utf-8")).hexdigest()[:10]
        tail = "-edit-" + digest
        ident = original_ident[: 80 - len(tail)] + tail
        kind += "_edit"
    parent_fields = leading_fields(str(referenced.get("content") or ""))
    target = ""
    if is_reply:
        target = declared_id(parent_fields) or canonical_id(parent_native)
    envelope: list[tuple[str, str]] = [
        ("from", src),
        ("to", dest),
        ("id", ident),
        ("ts", stamp),
        ("carrier", "discord-connector"),
        ("observed_event", "discord:%s:%s:%s:1" % (guild_id or "-", channel_id or "-", native_id)),
        ("carrier_ts", native_id),
    ]
    if target:
        envelope.append(("target", target))
    if edited:
        envelope.append(("supersedes", original_ident))
        envelope.append(("edited_ts", iso_from_discord(edited)))
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
    raise ImmutableMismatch("existing %s differs from Discord event %s" % (path, record.native_id))


def load_events(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        if isinstance(data.get("messages"), list):
            return [item for item in data["messages"] if isinstance(item, dict)]
        return [data]
    raise IngestError("event input must be an object or array")


def _bodies_match(left: str, right: str) -> bool:
    return _record_body(left).rstrip("\n") == _record_body(right).rstrip("\n")


def with_identity(record: IssueRecord, ident: str) -> IssueRecord:
    """Return a copy whose issue title and envelope id are ``ident``.

    Discord source text after the envelope fence stays untouched. The original
    declared id, if any, remains in that source text as provenance.
    """
    header, sep, rest = record.body.partition("\n---\n")
    if not sep:
        raise IngestError("record body missing envelope fence")
    lines = []
    replaced = False
    for line in header.split("\n"):
        if not replaced and line.lower().startswith("id:"):
            lines.append("id: %s" % ident)
            replaced = True
        else:
            lines.append(line)
    if not replaced:
        lines.append("id: %s" % ident)
    return IssueRecord(
        native_id=record.native_id,
        title=ident,
        body="\n".join(lines) + sep + rest,
        kind=record.kind,
        target=record.target,
    )


def _emit_or_fallback(
    record: IssueRecord,
    posts_dir: Path,
    seen: dict[str, IssueRecord],
    out: list[IssueRecord],
) -> None:
    previous = seen.get(record.title)
    if previous is not None:
        if _bodies_match(previous.body, record.body):
            return
        raise ImmutableMismatch(
            "declared id %s is claimed by Discord events %s and %s"
            % (record.title, previous.native_id, record.native_id)
        )
    path = posts_dir / (record.title + ".md")
    try:
        same = verify_existing(path, record)
    except ImmutableMismatch:
        snowflake = canonical_id(record.native_id)
        if record.title == snowflake:
            raise
        _emit_or_fallback(with_identity(record, snowflake), posts_dir, seen, out)
        return
    seen[record.title] = record
    if not same:
        out.append(record)


def plan(events: list[dict[str, Any]], posts_dir: Path = POSTS_DIR) -> list[IssueRecord]:
    out: list[IssueRecord] = []
    seen: dict[str, IssueRecord] = {}
    for event in events:
        if should_skip(event):
            continue
        _emit_or_fallback(issue_record(event), posts_dir, seen, out)
    return out


class DiscordClient:
    def __init__(self, token: str):
        if not token.strip():
            raise IngestError("DISCORD_BOT_TOKEN is required for sync")
        self.token = token.strip()

    def call(self, method: str, path: str) -> Any:
        req = urllib.request.Request(
            DISCORD_API + path,
            method=method,
            headers={"Authorization": "Bot " + self.token, "User-Agent": "commons-discord-ingest"},
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise IngestError("Discord HTTP %s" % exc.code) from exc

    def events(self) -> list[dict[str, Any]]:
        """Guild text channels the bot can see. Not DMs. Do not invent dests."""
        pinned = os.environ.get("COMMONS_DISCORD_CHANNEL", "").strip()
        out: list[dict[str, Any]] = []
        if pinned:
            messages = self.call("GET", "/channels/%s/messages?limit=100" % urllib.parse.quote(pinned))
            for message in messages or []:
                if isinstance(message, dict):
                    message.setdefault("channel_id", pinned)
                    out.append(message)
            return out
        guilds = self.call("GET", "/users/@me/guilds")
        for guild in guilds or []:
            gid = str((guild or {}).get("id") or "")
            if not gid:
                continue
            channels = self.call("GET", "/guilds/%s/channels" % gid)
            for channel in channels or []:
                if not isinstance(channel, dict):
                    continue
                if int(channel.get("type") or 0) not in {0, 5, 11, 15}:
                    continue
                cid = str(channel.get("id") or "")
                if not cid:
                    continue
                messages = self.call("GET", "/channels/%s/messages?limit=50" % cid)
                for message in messages or []:
                    if isinstance(message, dict):
                        message.setdefault("channel_id", cid)
                        message.setdefault("guild_id", gid)
                        out.append(message)
        return out


class GitHubClient:
    def __init__(self, token: str, repository: str = REPOSITORY):
        if not token.strip():
            raise IngestError("GITHUB_TOKEN is required for sync")
        self.token = token.strip()
        self.repository = repository
        self._board_titles: set[str] | None = None

    def request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        data, _link = self._request(method, path, payload)
        return data

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> tuple[Any, str]:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        url = path if path.startswith("https://") else GITHUB_API + path
        request = urllib.request.Request(
            url,
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
                body = json.loads(response.read().decode("utf-8"))
                link = response.headers.get("Link") or response.headers.get("link") or ""
                return body, link
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            raise IngestError("GitHub HTTP %s: %s" % (exc.code, detail[:300])) from exc

    def board_titles(self) -> set[str]:
        """Load all ``label=board`` issue titles once via the Issues list API.

        Per-record ``/search/issues`` is not used: Search has a 30/min cap and
        also burns the GitHub App installation quota that hosted inbound sync
        shares with every other Actions job. Large repos reject ``page=``
        offset pagination (HTTP 422); follow the Link ``rel=next`` cursor.
        """
        cached = getattr(self, "_board_titles", None)
        if cached is not None:
            return cached
        titles: set[str] = set()
        query = urllib.parse.urlencode(
            {
                "state": "all",
                "labels": "board",
                "per_page": "100",
            }
        )
        path = "/repos/%s/issues?%s" % (self.repository, query)
        while path:
            data, link = self._request("GET", path)
            if not isinstance(data, list) or not data:
                break
            for item in data:
                if not isinstance(item, dict) or item.get("pull_request"):
                    continue
                title = str(item.get("title") or "")
                if title:
                    titles.add(title)
            path = github_next_url(link)
        self._board_titles = titles
        return titles

    def issue_exists(self, title: str) -> bool:
        return title in self.board_titles()

    def create_issue(self, record: IssueRecord) -> str:
        try:
            require_publication(record.body, record.title)
        except PublicationPolicyViolation as exc:
            raise IngestError(str(exc)) from None
        data = self.request("POST", "/repos/%s/issues" % self.repository, record.as_issue())
        titles = getattr(self, "_board_titles", None)
        if titles is not None:
            titles.add(record.title)
        return str(data.get("html_url") or "")


def cmd_format(path: Path) -> int:
    events = load_events(path)
    if len(events) != 1:
        raise IngestError("format expects exactly one Discord event")
    print(json.dumps(issue_record(events[0]).as_issue(), ensure_ascii=False, indent=2))
    return 0


def cmd_plan(path: Path) -> int:
    records = plan(load_events(path))
    print(json.dumps([record.as_issue() for record in records], ensure_ascii=False, indent=2))
    return 0


def cmd_sync() -> int:
    token = (os.environ.get("DISCORD_BOT_TOKEN") or os.environ.get("COMMONS_DISCORD_BOT_TOKEN") or "").strip()
    if not token:
        print(json.dumps({"state": "DARK", "error": "no DISCORD_BOT_TOKEN"}))
        return 0
    discord = DiscordClient(token)
    github = GitHubClient(os.environ.get("GITHUB_TOKEN") or "")
    records = plan(discord.events(), POSTS_DIR)
    created: list[dict[str, str]] = []
    rejected: list[dict[str, str]] = []
    for record in records:
        verdict = check_publication(record.body, record.title)
        if not verdict["allowed"]:
            rejected.append({"id": record.title, "rule": verdict["rule"],
                             "message": verdict["message"]})
            continue
        if github.issue_exists(record.title):
            continue
        created.append({"id": record.title, "issue": github.create_issue(record)})
    print(json.dumps({"planned": len(records), "created": created, "rejected": rejected}, indent=2))
    return 0


def parser() -> argparse.ArgumentParser:
    out = argparse.ArgumentParser(description=__doc__)
    sub = out.add_subparsers(dest="command", required=True)
    fmt = sub.add_parser("format", help="format one Discord event as a board issue")
    fmt.add_argument("event", type=Path)
    batch = sub.add_parser("plan", help="plan issue payloads from an export without writing")
    batch.add_argument("events", type=Path)
    sub.add_parser("sync", help="pull Discord and create canonical board issues")
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
