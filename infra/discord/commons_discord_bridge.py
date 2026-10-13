#!/usr/bin/env python3
"""Durable multi-surface Commons <-> Discord bridge (stdlib only).

Ingress is normalized into an append-only SQLite event journal. Delivery
receipts are separate, making retries safe and preventing bridge echo loops.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from commons_publication_policy import check_publication

RUNTIME_LOG = Path(os.environ.get("LOCALAPPDATA", str(ROOT))) / "Commons" / "discord-runtime.log"


def runtime_log(message: str) -> None:
    """Append a secret-free startup/restart trace for unattended Windows runs."""
    try:
        RUNTIME_LOG.parent.mkdir(parents=True, exist_ok=True)
        with RUNTIME_LOG.open("a", encoding="utf-8") as stream:
            stream.write(f"{time.time():.3f} {message}\n")
    except OSError:
        pass


def operational_log(message: str) -> None:
    """Log every runtime message without blocking unattended task execution."""
    runtime_log(message)
    if sys.stdout is not None and sys.stdout.isatty():
        print(message, flush=True)

import discord_ingest

runtime_log("module-loaded")


def load_local_env() -> None:
    path = Path(__file__).with_name(".env.local")
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


load_local_env()
runtime_log("local-env-loaded")


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def event_id(source: str, native_id: str, payload: Any) -> str:
    seed = native_id.encode() if native_id else canonical(payload)
    return f"{source}:{hashlib.sha256(seed).hexdigest()}"


@dataclass(frozen=True)
class Event:
    id: str
    source: str
    kind: str
    native_id: str
    payload: dict[str, Any]
    created: float


class Journal:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS events(
          id TEXT PRIMARY KEY, source TEXT NOT NULL, kind TEXT NOT NULL,
          native_id TEXT NOT NULL, payload TEXT NOT NULL, created REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS deliveries(
          event_id TEXT NOT NULL, destination TEXT NOT NULL, remote_id TEXT,
          delivered REAL NOT NULL, PRIMARY KEY(event_id,destination)
        );
        CREATE TABLE IF NOT EXISTS cursors(
          surface TEXT PRIMARY KEY, value TEXT NOT NULL, updated REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS publication_rejections(
          event_id TEXT NOT NULL, destination TEXT NOT NULL, rule TEXT NOT NULL,
          rejected REAL NOT NULL, PRIMARY KEY(event_id,destination)
        );
        """)
        self.db.commit()
        self.lock = threading.Lock()

    def append(self, source: str, kind: str, native_id: str, payload: dict[str, Any]) -> tuple[Event, bool]:
        eid = event_id(source, native_id, payload)
        created = time.time()
        with self.lock:
            cur = self.db.execute(
                "INSERT OR IGNORE INTO events VALUES(?,?,?,?,?,?)",
                (eid, source, kind, native_id, canonical(payload).decode(), created),
            )
            self.db.commit()
        return Event(eid, source, kind, native_id, payload, created), cur.rowcount == 1

    def pending(self, destination: str, limit: int = 100) -> list[Event]:
        rows = self.db.execute("""
          SELECT e.id,e.source,e.kind,e.native_id,e.payload,e.created
          FROM events e LEFT JOIN deliveries d
            ON d.event_id=e.id AND d.destination=?
          LEFT JOIN publication_rejections r
            ON r.event_id=e.id AND r.destination=?
          WHERE d.event_id IS NULL AND r.event_id IS NULL
          ORDER BY e.created LIMIT ?
        """, (destination, destination, limit)).fetchall()
        return [Event(r[0], r[1], r[2], r[3], json.loads(r[4]), r[5]) for r in rows]

    def delivered(self, event: Event, destination: str, remote_id: str = "") -> None:
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO deliveries VALUES(?,?,?,?)",
                            (event.id, destination, remote_id, time.time()))
            self.db.commit()

    def reject_publication(self, event: Event, destination: str, rule: str) -> None:
        """Terminal delivery state; never record a rejected message as sent."""
        with self.lock:
            self.db.execute(
                "INSERT OR REPLACE INTO publication_rejections VALUES(?,?,?,?)",
                (event.id, destination, rule, time.time()),
            )
            self.db.commit()

    def delivery_event_for_canonical(
        self, canonical_id: str, destination: str
    ) -> tuple[str, Event | None]:
        needle = canonical({"canonical_id": canonical_id}).decode("utf-8")[1:-1]
        rows = self.db.execute("""
          SELECT e.id,e.source,e.kind,e.native_id,e.payload,e.created,d.remote_id
          FROM events e JOIN deliveries d ON d.event_id=e.id
          WHERE d.destination=? AND d.remote_id<>'' AND instr(e.payload,?)>0
          ORDER BY d.delivered DESC
        """, (destination, needle)).fetchall()
        for event_id_, source, kind, native_id, raw, created, remote_id in rows:
            payload = json.loads(raw)
            if str(payload.get("canonical_id") or "") == canonical_id:
                event = Event(event_id_, source, kind, native_id, payload, created)
                return str(remote_id), event
        return "", None

    def delivery_for_canonical(self, canonical_id: str, destination: str) -> str:
        return self.delivery_event_for_canonical(canonical_id, destination)[0]

    def cursor(self, surface: str, default: str = "") -> str:
        row = self.db.execute("SELECT value FROM cursors WHERE surface=?", (surface,)).fetchone()
        return row[0] if row else default

    def set_cursor(self, surface: str, value: str) -> None:
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO cursors VALUES(?,?,?)", (surface, value, time.time()))
            self.db.commit()


JOURNAL = Journal(ROOT / env("COMMONS_JOURNAL", "infra/discord/commons-bridge.sqlite3"))
runtime_log("journal-ready")


RATE_LIMIT_RETRIES = 3
MAX_RATE_LIMIT_DELAY_SECONDS = 60.0


def rate_limit_delay(error: urllib.error.HTTPError) -> float:
    """Return Discord/Slack's requested 429 delay within a bounded retry window."""
    delay: Any = None
    try:
        payload = json.loads(error.read().decode("utf-8"))
        if isinstance(payload, dict):
            delay = payload.get("retry_after")
    except (UnicodeDecodeError, json.JSONDecodeError):
        pass
    if delay is None and error.headers:
        delay = error.headers.get("Retry-After")
    try:
        seconds = float(delay)
    except (TypeError, ValueError):
        seconds = 1.0
    return min(MAX_RATE_LIMIT_DELAY_SECONDS, max(0.05, seconds))


def request_json(url: str, *, token: str = "", method: str = "GET", body: Any = None,
                 headers: dict[str, str] | None = None) -> Any:
    hdr = {"User-Agent": "commons-discord-node/1", **(headers or {})}
    if token:
        hdr["Authorization"] = token
    data = None if body is None else canonical(body)
    if data is not None:
        hdr["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=hdr, method=method)
    retries = RATE_LIMIT_RETRIES
    while True:
        try:
            with urllib.request.urlopen(req, timeout=20) as response:
                raw = response.read()
                if not raw:
                    return {}
                text = raw.decode("utf-8")
                if text.lstrip().startswith("data:"):
                    chunks = [line[5:].strip() for line in text.splitlines() if line.startswith("data:")]
                    text = next((line for line in reversed(chunks) if line and line != "[DONE]"), "{}")
                return json.loads(text)
        except urllib.error.HTTPError as error:
            if error.code != 429 or retries == 0:
                raise
            retries -= 1
            time.sleep(rate_limit_delay(error))


CHANNELS = {
    "github": env("DISCORD_CHANNEL_GITHUB"),
    "slack": env("DISCORD_CHANNEL_SLACK"),
    "repository": env("DISCORD_CHANNEL_REPOSITORIES"),
    "machine": env("DISCORD_CHANNEL_MACHINE"),
    "model": env("DISCORD_CHANNEL_MODELS"),
    "operations": env("DISCORD_CHANNEL_OPERATIONS"),
    "archive": env("DISCORD_CHANNEL_ARCHIVE"),
}


def route(event: Event) -> str:
    return CHANNELS.get(event.source) or CHANNELS.get(event.kind) or CHANNELS["operations"]


def render(event: Event) -> str:
    p = event.payload
    title = p.get("title") or p.get("subject") or p.get("name") or event.kind
    url = p.get("url") or p.get("html_url") or ""
    body = p.get("text") or p.get("body") or p.get("summary") or ""
    body = str(body).replace("@everyone", "@\u200beveryone").replace("@here", "@\u200bhere")
    marker = f"`commons:{event.id}`"
    return f"**[{event.source}] {title}**\n{body[:1600]}\n{url}\n{marker}"[:1999]


def allow_publication(event: Event, destination: str, body: str, subject: str = "") -> bool:
    verdict = check_publication(body, subject)
    if verdict["allowed"]:
        return True
    # Retain only the terminal operation and rule; do not repeat the rejected
    # content in logs or keep retrying the same publication every poll cycle.
    JOURNAL.reject_publication(event, destination, verdict["rule"])
    operational_log(f"publication-rejected destination={destination} rule={verdict['rule']}")
    return False


def deliver_discord() -> None:
    token = env("DISCORD_BOT_TOKEN")
    if not token:
        return
    for event in JOURNAL.pending("discord"):
        if event.source == "discord":
            JOURNAL.delivered(event, "discord", event.native_id)
            continue
        channel = route(event)
        if not channel:
            continue
        body: dict[str, Any] = {"content": render(event)}
        if not allow_publication(event, "discord", body["content"]):
            continue
        target = str(event.payload.get("target") or "")
        parent, parent_event = (
            JOURNAL.delivery_event_for_canonical(target, "discord")
            if target else ("", None)
        )
        if parent and parent_event is not None and route(parent_event) == channel:
            body["message_reference"] = {"message_id": parent}
        out = request_json(f"https://discord.com/api/v10/channels/{channel}/messages",
                           token=f"Bot {token}", method="POST", body=body)
        JOURNAL.delivered(event, "discord", str(out.get("id", "")))


def deliver_slack() -> None:
    token, channel = env("SLACK_BOT_TOKEN"), env("SLACK_COMMONS_CHANNEL")
    if not token or not channel:
        return
    for event in JOURNAL.pending("slack"):
        if event.source == "slack":
            JOURNAL.delivered(event, "slack", event.native_id)
            continue
        text = render(event)
        if not allow_publication(event, "slack", text):
            continue
        out = request_json("https://slack.com/api/chat.postMessage", token=f"Bearer {token}",
                           method="POST", body={"channel": channel, "text": text})
        if out.get("ok"):
            JOURNAL.delivered(event, "slack", str(out.get("ts", "")))


def discord_event_from_journal(event: Event) -> dict[str, Any]:
    """Recover the exact Discord-shaped event used by canonical issue ingest."""
    raw = event.payload.get("discord_event")
    if isinstance(raw, dict):
        return raw
    # Compatibility for journals written by the first bridge revision.
    return {
        "id": event.native_id,
        "channel_id": event.payload.get("channel_id", ""),
        "guild_id": event.payload.get("guild_id", ""),
        "timestamp": event.payload.get("timestamp", ""),
        "content": event.payload.get("text", ""),
        "author": {"username": event.payload.get("author", "")},
        "message_reference": event.payload.get("message_reference", {}),
        "referenced_message": event.payload.get("referenced_message", {}),
    }


class CommonsMCPClient:
    """No-auth canonical Commons ingress used by the Discord runtime."""

    def __init__(self, url: str = ""):
        self.url = url or env("COMMONS_MCP_URL", "https://commons-spark-mcp.vercel.app/mcp")

    def append_record(self, record: discord_ingest.IssueRecord) -> str:
        response = request_json(
            self.url,
            method="POST",
            body={
                "jsonrpc": "2.0", "id": record.title, "method": "tools/call",
                "params": {"name": "append_post", "arguments": record.as_commons_arguments()},
            },
            headers={"Accept": "application/json, text/event-stream"},
        )
        result = response.get("result") if isinstance(response, dict) else None
        if not isinstance(result, dict) or result.get("isError"):
            raise discord_ingest.IngestError("Commons MCP append_post failed")
        content = result.get("structuredContent") or {}
        return str(content.get("git_sha") or content.get("id") or record.title)


def deliver_commons_issue(client: Any = None) -> None:
    """Carry Discord messages onto one canonical Commons ingest road.

    The public no-auth MCP is the default. The existing GitHub issue client
    remains an explicit compatibility mode. Neither path writes ``p/`` here.
    """
    if client is None:
        mode = env("COMMONS_DISCORD_INGRESS", "mcp").lower()
        token = env("GITHUB_TOKEN") or env("COMMONS_GITHUB_TOKEN")
        client = discord_ingest.GitHubClient(token) if mode == "github-issue" and token else CommonsMCPClient()
    for event in JOURNAL.pending("commons-issue"):
        if event.source != "discord":
            JOURNAL.delivered(event, "commons-issue", "not-discord")
            continue
        source = discord_event_from_journal(event)
        if discord_ingest.should_skip(source):
            JOURNAL.delivered(event, "commons-issue", "relay-skip")
            continue
        record = discord_ingest.issue_record(source)
        if not allow_publication(event, "commons-issue", record.body, record.title):
            continue
        if hasattr(client, "append_record"):
            remote = client.append_record(record)
            JOURNAL.delivered(event, "commons-issue", remote)
            continue
        path = ROOT / "p" / (record.title + ".md")
        if discord_ingest.verify_existing(path, record):
            JOURNAL.delivered(event, "commons-issue", "durable-page")
            continue
        if client.issue_exists(record.title):
            JOURNAL.delivered(event, "commons-issue", "existing-issue")
            continue
        remote = client.create_issue(record)
        JOURNAL.delivered(event, "commons-issue", remote)


def poll_slack() -> None:
    """Backfill Slack history so temporary webhook outages do not lose posts."""
    token, channel = env("SLACK_BOT_TOKEN"), env("SLACK_COMMONS_CHANNEL")
    if not token or not channel:
        return
    oldest = JOURNAL.cursor(f"slack:{channel}", "0")
    query = urllib.parse.urlencode({"channel": channel, "oldest": oldest, "limit": 100,
                                    "inclusive": "false"})
    out = request_json(f"https://slack.com/api/conversations.history?{query}",
                       token=f"Bearer {token}")
    if not out.get("ok"):
        raise OSError(f"Slack history failed: {out.get('error', 'unknown_error')}")
    rows = out.get("messages", [])
    for row in reversed(rows):
        ts = str(row.get("ts", ""))
        if not ts or row.get("bot_id") or "`commons:" in row.get("text", ""):
            continue
        JOURNAL.append("slack", "message", f"{channel}:{ts}", {
            "title": f"Slack #{channel}", "text": row.get("text", ""),
            "channel_id": channel, "author": row.get("user", ""),
            "files": row.get("files", []), "thread_ts": row.get("thread_ts", ""),
            "url": "",
        })
    if rows:
        JOURNAL.set_cursor(f"slack:{channel}", max(str(row.get("ts", "0")) for row in rows))


def repo_event(repo: Path, head: str, status: str, path: str) -> tuple[str, str, dict[str, Any]]:
    payload: dict[str, Any] = {
        "title": f"{status} {path}", "summary": f"Commons git HEAD {head}",
        "url": f"https://github.com/woahwhattheheck/commons/blob/{head}/{urllib.parse.quote(path)}",
        "sha": head, "path": path, "status": status,
    }
    if status != "D" and path.startswith("p/") and path.endswith(".md"):
        raw = (repo / path).read_text(encoding="utf-8", errors="replace")
        fields = discord_ingest.leading_fields(raw)
        payload.update({
            "title": fields.get("subject") or fields.get("id") or Path(path).stem,
            "text": discord_ingest._record_body(raw),
            "canonical_id": fields.get("id") or Path(path).stem,
            "target": fields.get("target") or fields.get("supersedes") or "",
            "source_from": fields.get("from") or "UNKNOWN",
        })
        if fields.get("carrier") == "slack-connector":
            return "slack", "commons.post", payload
        if fields.get("is_language_model") == "YES" or fields.get("model"):
            return "model", "commons.post", payload
        return "operations", "commons.post", payload
    if path.startswith(("actions/", "lda/", "muhl/", "titan")):
        return "machine", "file.change", payload
    return "repository", "file.change", payload


def poll_git() -> None:
    repo = Path(env("COMMONS_REPO", str(ROOT)))
    try:
        head = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=repo, text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        ).strip()
    except Exception:
        return
    previous = JOURNAL.cursor("git-head")
    if head == previous:
        return
    names = subprocess.check_output(
        ["git", "diff", "--name-status", previous or f"{head}^", head], cwd=repo, text=True,
        errors="replace", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    ).splitlines()
    for line in names:
        status, _, path = line.partition("\t")
        source, kind, payload = repo_event(repo, head, status, path)
        JOURNAL.append(source, kind, f"{head}:{path}", payload)
    JOURNAL.set_cursor("git-head", head)


def poll_discord() -> None:
    token = env("DISCORD_BOT_TOKEN")
    if not token:
        return
    for lane, channel in CHANNELS.items():
        if not channel:
            continue
        after = JOURNAL.cursor(f"discord:{channel}")
        query = f"?limit=100" + (f"&after={after}" if after else "")
        rows = request_json(f"https://discord.com/api/v10/channels/{channel}/messages{query}",
                            token=f"Bot {token}")
        for row in reversed(rows):
            if row.get("author", {}).get("bot"):
                continue
            text = row.get("content", "")
            if "`commons:" in text:
                continue
            row.setdefault("channel_id", channel)
            row.setdefault("guild_id", env("DISCORD_GUILD_ID"))
            edited = str(row.get("edited_timestamp") or "")
            revision = hashlib.sha256((edited + "\n" + text).encode()).hexdigest()[:10] if edited else ""
            native = str(row["id"]) + ((":edit:" + revision) if revision else "")
            JOURNAL.append("discord", "message.edit" if edited else "message", native, {
                "title": f"#{lane}", "text": text, "channel_id": channel,
                "guild_id": row.get("guild_id", ""), "timestamp": row.get("timestamp", ""),
                "author": row.get("author", {}).get("username", ""),
                "attachments": row.get("attachments", []),
                "message_reference": row.get("message_reference", {}),
                "referenced_message": row.get("referenced_message", {}),
                "discord_event": row,
                "url": f"https://discord.com/channels/{env('DISCORD_GUILD_ID')}/{channel}/{row['id']}",
            })
            JOURNAL.set_cursor(f"discord:{channel}", str(row["id"]))


class Handler(BaseHTTPRequestHandler):
    server_version = "CommonsDiscordNode/1"

    def reply(self, code: int, value: Any) -> None:
        raw = canonical(value)
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        if self.path == "/health":
            self.reply(200, {"ok": True, "node": "discord", "guild": env("DISCORD_GUILD_ID")})
        elif self.path.startswith("/events"):
            rows = JOURNAL.db.execute("SELECT id,source,kind,payload,created FROM events ORDER BY created DESC LIMIT 100").fetchall()
            self.reply(200, [{"id": r[0], "source": r[1], "kind": r[2], "payload": json.loads(r[3]), "created": r[4]} for r in rows])
        else:
            self.reply(404, {"error": "not found"})

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        source = "discord" if self.path.startswith("/discord/") else "github" if self.path.startswith("/github/") else "slack" if self.path.startswith("/slack/") else "http"
        try:
            payload = json.loads(raw or b"{}")
        except ValueError:
            self.reply(400, {"error": "invalid json"})
            return
        native = self.headers.get("X-GitHub-Delivery") or self.headers.get("X-Slack-Request-Timestamp") or str(payload.get("id", ""))
        if source == "slack" and payload.get("type") == "url_verification":
            self.reply(200, {"challenge": payload.get("challenge")})
            return
        event, inserted = JOURNAL.append(source, str(payload.get("type") or self.headers.get("X-GitHub-Event") or "webhook"), native, payload)
        self.reply(202, {"accepted": inserted, "event_id": event.id})

    def log_message(self, fmt: str, *args: Any) -> None:
        operational_log(f"bridge {self.address_string()} {fmt % args}")


def worker() -> None:
    delay = max(1, int(env("COMMONS_POLL_SECONDS", "3")))
    while True:
        for fn in (poll_git, poll_discord, poll_slack, deliver_commons_issue, deliver_discord, deliver_slack):
            try:
                fn()
            except (
                OSError,
                urllib.error.URLError,
                json.JSONDecodeError,
                discord_ingest.IngestError,
            ) as exc:
                operational_log(f"{fn.__name__} {type(exc).__name__} {str(exc)[:200]}")
        time.sleep(delay)


def main() -> None:
    host, port = env("COMMONS_BRIDGE_HOST", "127.0.0.1"), int(env("COMMONS_BRIDGE_PORT", "18787"))
    server = ThreadingHTTPServer((host, port), Handler)
    runtime_log(f"server-ready {host}:{port}")
    threading.Thread(target=worker, daemon=True).start()
    operational_log(f"Commons Discord node listening on http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
