"""Read-only GitHub/Gmail ingestion; durable, content-bearing Slack delivery.

Run once from a scheduler. No model calls, source writes, or source read/done
mutations. State contains hashes, timestamps and counters, never message bodies.
Existing gh/gws sessions and Commons Slack custody work without copying tokens.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.errors import HeaderParseError
from email.header import decode_header
from email.message import Message
from email.policy import default as mail_policy
from email.utils import parseaddr, parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable, Iterator

# Allow existing Commons custody imports when launched as a file or module.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
UTC = timezone.utc
SECRET = re.compile(r"(?:xox[baprs]-[A-Za-z0-9-]+|xapp-[A-Za-z0-9-]+|gh[pousr]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+|AIza[\w-]{30,}|sk_(?:live|test)_[\w]+|-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----)", re.S)
SECRET_FIELD = re.compile(r"(?im)(\b(?:access_token|refresh_token|client_secret|api[_ -]?key|password|authorization|cookie)\b\s*[:=]\s*)[^\s,;]+")
AUTH_MAIL = re.compile(r"(?i)\b(sign.?in|log.?in|one.?time|passcode|password|passkey|2fa|two.factor|security (?:code|alert)|verification code|verify (?:your |the )?(?:email|identity)|unrecognized device)\b")
PRIVATE_MAIL = re.compile(r"(?i)\b(patient|medical record|social security|account statement|bank statement|insurance claim)\b")
WORK_MAIL = re.compile(r"(?i)\b(rfp|rfq|bid\s+\d|addend\w*|proposal|deadline|submission|registration|qualification|review|pull request|invoice|ticket|contract|tasks? due|automation|usage limit|interview|application)\b")
# Keep bracketed authorities and generated redaction markers inside URL tokens.
# Other closing prose/Markdown brackets still terminate the URL.
URL = re.compile(
    r"https?://(?:"
    r"(?:[^\s<>/?#@\[\]\)]*@)?\[[^\s<>/?#\[\]\)]+\](?:\[REDACTED\]|[^\s<>\]\)])*"
    r"|(?:\[REDACTED\]|[^\s<>\]\)])+)"
)
TOKEN_QUERY = re.compile(r"(?i)(token|secret|password|signature|sig|code|key|auth|credential)")


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def iso(value: datetime | None = None) -> str:
    return (value or datetime.now(UTC)).isoformat(timespec="seconds").replace("+00:00", "Z")


def clean(text: Any) -> str:
    """Bounded secret scrub plus inert Slack text; not a universal DLP claim."""
    text = SECRET.sub("[REDACTED]", str(text or ""))
    text = SECRET_FIELD.sub(r"\1[REDACTED]", text)
    text = re.sub(r"(?im)^.*(?:one.?time (?:code|password)|verification code|security code|your (?:login|sign.?in) code).*$", "[authentication material omitted]", text)
    def url_filter(match: re.Match) -> str:
        raw = match.group(0)
        try:
            parsed = urllib.parse.urlsplit(raw)
        except ValueError:
            # Malformed source links must not abort the surrounding work item.
            return "[malformed URL omitted]"
        if parsed.username or parsed.password or re.search(r"(?i)/(?:reset-password|password/reset|verify-email|magic-link|login/verify|auth/callback)(?:/|$)", parsed.path):
            return "[credential-bearing URL omitted]"
        if any(TOKEN_QUERY.search(key) for key, _ in urllib.parse.parse_qsl(parsed.query)):
            return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", "")) + " [query omitted]"
        # Tracking and unsubscribe URLs often encode recipient identifiers in paths.
        if any(x in parsed.netloc.lower() for x in ("customeriomail", "sendgrid.net", "email.mail.cursor", "click.")) or "unsubscribe" in parsed.path.lower():
            return "[tracking/action link omitted]"
        return raw
    text = URL.sub(url_filter, text)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    return text.replace("<!", "＜!").replace("<@", "＜@").replace("@channel", "＠channel").replace("@here", "＠here").replace("@everyone", "＠everyone")


class RelayError(RuntimeError):
    def __init__(self, code: str, *, uncertain: bool = False, retry_after: int = 0):
        super().__init__(code)
        self.code, self.uncertain, self.retry_after = code, uncertain, retry_after


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def http_retry_after(code: int, headers: Any, host: str) -> int:
    """Honor provider retry deadlines without capping them to the poll interval."""
    headers = headers or {}
    delay = 60 if code == 429 else 0
    value = headers.get("Retry-After")
    if value is not None:
        delay = 60
        try:
            value = str(value).strip()
            if re.fullmatch(r"[0-9]+", value):
                delay = max(1, int(value))
            else:
                deadline = parsedate_to_datetime(value)
                if deadline.tzinfo is None:
                    deadline = deadline.replace(tzinfo=UTC)
                delay = max(1, math.ceil(deadline.timestamp() - time.time()))
        except (TypeError, ValueError, OverflowError):
            pass
    # An exhausted primary budget can coexist with a secondary Retry-After.
    if host == "api.github.com" and code in {403, 429} and headers.get("X-RateLimit-Remaining") == "0":
        try:
            reset = int(headers.get("X-RateLimit-Reset", ""))
            delay = max(delay, 1, math.ceil(reset - time.time()))
        except (TypeError, ValueError, OverflowError):
            delay = max(delay, 60)
    return delay


def request_json(url: str, *, token: str = "", data: dict | None = None,
                 form: bool = False) -> dict | list:
    """Fixed provider URLs only; caller data never controls a destination host."""
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.netloc not in {
        "api.github.com", "slack.com", "gmail.googleapis.com", "oauth2.googleapis.com"
    }:
        raise RelayError("unexpected_provider_url")
    headers = {"Accept": "application/json", "User-Agent": "commons-inbox-visibility/1"}
    if token:
        headers["Authorization"] = "Bearer " + token
    payload = None
    if data is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded" if form else "application/json; charset=utf-8"
        payload = (urllib.parse.urlencode(data) if form else json.dumps(data)).encode()
    req = urllib.request.Request(url, data=payload, headers=headers)
    try:
        with urllib.request.build_opener(NoRedirect()).open(req, timeout=30) as response:
            raw = response.read(10_000_001)
        if len(raw) > 10_000_000:
            raise RelayError("provider_payload_too_large", uncertain=data is not None)
        return json.loads(raw)
    except urllib.error.HTTPError as exc:
        code = exc.code
        retry = http_retry_after(code, exc.headers, parsed.hostname or "")
        exc.close()
        raise RelayError(f"http_{code}", uncertain=data is not None and code >= 500, retry_after=retry) from None
    except (OSError, ValueError) as exc:
        raise RelayError("transport_or_json_error", uncertain=data is not None) from None


def command_json(args: list[str]) -> Any:
    try:
        result = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", timeout=90,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired):
        raise RelayError("native_cli_unavailable") from None
    if result.returncode:
        # CLI diagnostics can echo secrets or source bodies. Never print them.
        raise RelayError("native_cli_request_failed")
    try:
        return json.loads(result.stdout)
    except ValueError:
        raise RelayError("native_cli_invalid_json") from None


class Providers:
    def __init__(self):
        self.gh_token = os.environ.get("GH_NOTIFICATIONS_TOKEN") or os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN", "")
        self.slack_token = os.environ.get("SLACK_BOT_TOKEN", "")
        self.gmail_token = os.environ.get("GMAIL_ACCESS_TOKEN", "")
        self._equipment = None
        self._github_equipment = None

    def github(self, endpoint: str) -> Any:
        if not endpoint.startswith(("repos/", "notifications?", "search/issues?")) and endpoint != "user":
            raise RelayError("unexpected_github_resource")
        if self.gh_token:
            return request_json("https://api.github.com/" + endpoint, token=self.gh_token)
        from integrations.shared_equipment.provider_io import EquipmentError, GitHubSlackEquipment
        if self._github_equipment is None:
            self._github_equipment = GitHubSlackEquipment()
        try:
            return self._github_equipment.github(endpoint)
        except EquipmentError as exc:
            # Reuse typed status/header parsing; never expose native stderr or
            # provider response bodies through the relay's fixed-code report.
            headers = {name: str(value) for name, value in (
                ("Retry-After", exc.retry_after),
                ("X-RateLimit-Remaining", exc.rate_limit_remaining),
                ("X-RateLimit-Reset", exc.rate_limit_reset),
            ) if value is not None}
            retry = http_retry_after(exc.http_status or 0, headers, "api.github.com")
            if exc.code == "github_rate_limited" and retry <= 0:
                retry = 60
            code = {"github_transport_failed": "native_cli_unavailable",
                    "github_response_invalid": "native_cli_invalid_json",
                    "github_request_failed": f"http_{exc.http_status}" if exc.http_status else "native_cli_request_failed"}.get(exc.code, exc.code)
            raise RelayError(code, retry_after=retry) from None

    def slack(self, method: str, data: dict) -> dict:
        if method not in {"auth.test", "conversations.history", "conversations.replies", "chat.postMessage", "chat.update"}:
            raise RelayError("unexpected_slack_method")
        if not self.slack_token:
            try:
                if self._equipment is None:
                    from integrations.shared_equipment.services import ServiceEquipment
                    self._equipment = ServiceEquipment()
                result = self._equipment.slack(method, data)
            except Exception:
                raise RelayError("slack_existing_custody_unavailable", uncertain=method.startswith("chat.")) from None
        else:
            url = "https://slack.com/api/" + method
            if method in {"auth.test", "conversations.history", "conversations.replies"}:
                result = request_json(url + "?" + urllib.parse.urlencode(data), token=self.slack_token)
            else:
                result = request_json(url, token=self.slack_token, data=data)
        if not isinstance(result, dict) or not result.get("ok"):
            error = str(result.get("error", "invalid_response")) if isinstance(result, dict) else "invalid_response"
            retry = 0
            if error in {"ratelimited", "slack_http_error"}:
                try:
                    status = 429 if error == "ratelimited" else int(result.get("status") or 0)
                except (TypeError, ValueError):
                    status = 0
                # Existing custody returns the original header, including an
                # HTTP date. Preserve the same deadline as the direct route.
                retry = http_retry_after(status, {"Retry-After": result.get("retry_after")}, "slack.com")
            raise RelayError("slack_" + re.sub(r"[^a-zA-Z0-9_]", "", error)[:80],
                             uncertain=(bool(result.get("uncertain")) if isinstance(result, dict) else method.startswith("chat.")) or error in {"internal_error", "fatal_error"}, retry_after=retry)
        return result

    def gmail(self, resource: str, params: dict | None = None) -> dict:
        params = params or {}
        if not self.gmail_token and os.environ.get("GMAIL_AUTHORIZED_USER_JSON"):
            try:
                grant = json.loads(os.environ["GMAIL_AUTHORIZED_USER_JSON"])
                refreshed = request_json("https://oauth2.googleapis.com/token", form=True, data={
                    "grant_type": "refresh_token", "client_id": grant["client_id"],
                    "client_secret": grant["client_secret"], "refresh_token": grant["refresh_token"]})
                self.gmail_token = refreshed["access_token"]
            except RelayError as exc:
                raise RelayError("gmail_existing_grant_unavailable", retry_after=exc.retry_after) from None
            except (KeyError, ValueError):
                raise RelayError("gmail_existing_grant_unavailable") from None
        if self.gmail_token:
            return request_json("https://gmail.googleapis.com/gmail/v1/users/me/" + resource +
                                ("?" + urllib.parse.urlencode(params) if params else ""), token=self.gmail_token)
        if not shutil.which("gws"):
            raise RelayError("gmail_existing_reader_unavailable")
        if resource == "profile":
            command = ["gws", "gmail", "users", "getProfile"]
        elif resource == "messages":
            command = ["gws", "gmail", "users", "messages", "list"]
        elif re.fullmatch(r"messages/[A-Za-z0-9_-]+", resource):
            command = ["gws", "gmail", "users", "messages", "get"]
            params = {**params, "id": resource.split("/")[1]}
        else:
            raise RelayError("unsupported_gmail_resource")
        return command_json(command + ["--params", json.dumps({"userId": "me", **params})])


class PlainHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden = 0
    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "head"}:
            self.hidden += 1
        if tag in {"br", "p", "div", "li", "tr", "h1", "h2"} and not self.hidden:
            self.parts.append("\n")
    def handle_endtag(self, tag):
        if tag in {"script", "style", "head"}:
            self.hidden = max(0, self.hidden - 1)
    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def mail_body(payload: dict) -> str:
    """No image/link retrieval, attachments, or duplicate HTML alternatives."""
    return _mail_body_content(payload)[0]


def _mail_body_content(payload: dict) -> tuple[str, bool]:
    """Return rendered text and whether it contains readable source content.

    Diagnostics are retained when no alternative is readable, but are not
    themselves source content. Keep this fact separate from the text so a
    literal diagnostic-looking message remains an ordinary readable message.
    """
    if payload.get("filename"):
        return "", False
    parts = payload.get("parts", [])
    if parts:
        if payload.get("mimeType") == "multipart/alternative":
            # Prefer readable plain text, then the last usable alternative.
            ordered = [p for p in parts if p.get("mimeType") == "text/plain"]
            ordered.extend(p for p in reversed(parts) if p.get("mimeType") != "text/plain")
            diagnostic = ""
            for candidate in ordered:
                body, readable = _mail_body_content(candidate)
                if readable:
                    return body, True
                if body.strip() and not diagnostic:
                    diagnostic = body
            return diagnostic, False
        rendered = [_mail_body_content(p) for p in parts]
        return "\n".join(body for body, _ in rendered if body), any(readable for _, readable in rendered)
    encoded = payload.get("body", {}).get("data", "")
    if not encoded:
        diagnostic = "[Body stored as an attachment; read original in Gmail.]" if payload.get("body", {}).get("attachmentId") else ""
        return diagnostic, False
    try:
        data = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
    except (ValueError, TypeError):
        return "[Body decoding failed; read original in Gmail.]", False
    # Gmail returns MIME-part bytes, not necessarily UTF-8. Read the leaf's
    # Content-Type; a container's charset does not override its child parts.
    mime = Message()
    for header in payload.get("headers", []):
        if header.get("name", "").lower() == "content-type":
            mime["Content-Type"] = header.get("value", "")
            break
    try:
        raw = data.decode(mime.get_content_charset() or "utf-8", errors="replace")
    except (LookupError, ValueError):
        # Unknown, malformed, and non-text codec names must not drop work mail.
        raw = data.decode("utf-8", errors="replace")
    if payload.get("mimeType") == "text/html":
        parser = PlainHTML()
        parser.feed(raw)
        body = "".join(parser.parts).strip()
    else:
        body = raw if payload.get("mimeType", "text/plain") == "text/plain" else ""
    return body, bool(body.strip())

def attachment_names(payload: dict) -> list[str]:
    found = [payload["filename"]] if payload.get("filename") else []
    for part in payload.get("parts", []):
        found.extend(attachment_names(part))
    return found


@dataclass(frozen=True)
class Event:
    provider: str
    item: str
    event_id: str
    title: str
    body: str
    url: str
    author: str = ""
    updated: str = ""
    action: str = "Existing owner: read, claim next action, then reply DONE with evidence or BLOCKED."

    @property
    def key(self) -> str:
        return digest(self.provider + ":" + self.item)

    def messages(self) -> list[str]:
        return [text for text, _ in self.message_parts()]

    def message_parts(self) -> list[tuple[str, tuple[str, ...]]]:
        # Include the sanitized *contents*, not only subject/latest_comment_url.
        source_header = f"{self.provider.upper()} | {self.title[:300]}\nSource: {self.url[:800]}\nAuthor: {self.author[:300]} | Updated: {self.updated[:80]}"
        header = clean(source_header + f"\nNext: {self.action[:500]}")
        body = clean(self.body or "[No text body provided by the source.]")
        # Slack supports long threads; normal bodies are not silently truncated.
        chunks = [body[i:i + 2800] for i in range(0, len(body), 2800)] or [""]
        is_comment = self.provider == "github" and re.fullmatch(r"(?:issue-comment|review|inline-review):[0-9]+", self.event_id)
        # A parent closing/merging changes routing text, not historical comment
        # contents. The separate subject event still versions that transition.
        version_header = clean(source_header) if is_comment else header
        versions = [digest(self.event_id + "\0" + version_header + "\0" + body)]
        if is_comment:
            # Recognize already delivered pre-upgrade parts under every former
            # parent action. Body, author, timestamp and review context must match.
            for action in (self.action,
                           "Existing owner: inspect this update and post CLAIM / DONE + evidence / BLOCKED in this thread.",
                           "Existing owner: verify acceptance/payment conditions; merge is not payment. Do not duplicate a collection request.",
                           "Existing owner: inspect the closure reason; do not assume accepted or paid."):
                legacy_header = clean(source_header + f"\nNext: {action[:500]}")
                versions.append(digest(self.event_id + "\0" + legacy_header + "\0" + body))
        parts = []
        for i, chunk in enumerate(chunks):
            key = digest(versions[0] + ':' + str(i))
            keys = (key, *sorted({digest(version + ':' + str(i)) for version in versions[1:]} - {key}))
            parts.append((f"{header}\n\nContents ({i + 1}/{len(chunks)}):\n{chunk}\n\nrelay.part={keys[0]}", keys))
        return parts


class State:
    def __init__(self, path: str | Path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=1)
        try:
            self.db.executescript("""
              CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS items (key TEXT PRIMARY KEY, channel TEXT NOT NULL, ts TEXT NOT NULL DEFAULT '', attempted REAL NOT NULL);
              CREATE TABLE IF NOT EXISTS parts (key TEXT PRIMARY KEY, ts TEXT NOT NULL DEFAULT '', attempted REAL NOT NULL, uncertain INTEGER NOT NULL DEFAULT 0);
            """)
            self.db.commit()
            if os.name != "nt":
                path.chmod(0o600)
        except BaseException:
            self.db.close()
            raise
    def get(self, key: str, default: str = "") -> str:
        row = self.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row[0] if row else default
    def set(self, key: str, value: Any):
        self.db.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (key, str(value)))
        self.db.commit()
    def discard(self, key: str):
        self.db.execute("DELETE FROM meta WHERE key=?", (key,))
        self.db.commit()
    def close(self):
        self.db.close()


class Delivery:
    def __init__(self, state: State, slack: Callable, *, max_pages: int = 20, max_posts: int = 100, min_interval: float = 1.05):
        self.state, self.slack = state, slack
        self.max_pages, self.max_posts, self.posts = max_pages, max_posts, 0
        self.min_interval, self.next_post = min_interval, 0.0
        self.cooldown_until = 0.0

    def call_slack(self, method: str, data: dict) -> dict:
        """One observed Slack cooldown covers source and health delivery."""
        remaining = self.cooldown_until - time.time()
        if remaining > 0:
            raise RelayError("slack_retry_after_active", retry_after=math.ceil(remaining))
        try:
            return self.slack(method, data)
        except RelayError as exc:
            if exc.retry_after > 0:
                self.cooldown_until = max(self.cooldown_until, time.time() + exc.retry_after)
            raise

    def find(self, channel: str, marker: str | tuple[str, ...], attempted: float, thread: str = "") -> str:
        # Resume a bounded scan instead of rereading its first pages forever.
        # Freeze the time window so a growing channel cannot move those pages.
        markers = (marker,) if isinstance(marker, str) else marker
        scan_key = "slack.scan." + digest(json.dumps([channel, thread, marker, attempted]))
        retained = self.state.get(scan_key)
        resumed = bool(retained)
        scan = json.loads(retained) if retained else {
            "cursor": "", "oldest": str(max(0, attempted - 120)), "latest": str(time.time()),
        }
        if retained and not scan["cursor"]:
            # No page in this window has been consumed yet. Refresh its upper
            # bound now, including when a catch-up window exhausted the budget.
            scan["latest"] = str(time.time())
            resumed = False
        self.state.set(scan_key, json.dumps(scan))
        for _ in range(self.max_pages):
            data = {"channel": channel, "limit": 100, "oldest": scan["oldest"],
                    "latest": scan["latest"], "inclusive": "true"}
            if scan["cursor"]:
                data["cursor"] = scan["cursor"]
            if thread:
                data["ts"] = thread
            try:
                result = self.call_slack("conversations.replies" if thread else "conversations.history", data)
            except RelayError as exc:
                if exc.code == "slack_invalid_cursor":
                    # Expired provider cursors require a fresh scan, never a send.
                    self.state.discard(scan_key)
                raise
            for message in result.get("messages", []):
                if any(candidate in message.get("text", "") for candidate in markers):
                    self.state.discard(scan_key)
                    return str(message["ts"])
            cursor = result.get("response_metadata", {}).get("next_cursor", "")
            if not cursor and not result.get("has_more"):
                if resumed:
                    # Check messages arriving between polls before concluding
                    # absence. Inclusive endpoints preserve the window boundary.
                    scan = {"cursor": "", "oldest": scan["latest"], "latest": str(time.time())}
                    self.state.set(scan_key, json.dumps(scan))
                    resumed = False
                    continue
                self.state.discard(scan_key)
                return ""
            if not cursor:
                raise RelayError("slack_reconcile_incomplete")
            scan["cursor"] = cursor
            self.state.set(scan_key, json.dumps(scan))
        raise RelayError("slack_reconcile_page_limit")

    def post(self, channel: str, text: str, thread: str = "", *, budgeted: bool = True) -> str:
        if budgeted and self.posts >= self.max_posts:
            raise RelayError("delivery_budget_pending")
        if budgeted:
            self.posts += 1
        time.sleep(max(0.0, self.next_post - time.monotonic()))
        self.next_post = time.monotonic() + self.min_interval
        data = {"channel": channel, "text": text, "mrkdwn": False, "parse": "none",
                "link_names": False, "unfurl_links": False, "unfurl_media": False,
                "client_msg_id": str(uuid.uuid5(uuid.NAMESPACE_URL, channel + "\0" + text))}
        if thread:
            data["thread_ts"] = thread
        result = self.call_slack("chat.postMessage", data)
        if not result.get("ts"):
            raise RelayError("slack_missing_receipt", uncertain=True)
        return str(result["ts"])

    def deliver_health(self, channel: str, text: str, thread: str = "") -> str:
        """Recover an interrupted initial health post before updating it.

        The marker identifies the destination, not this poll's changing report.
        Older ledgers retain their health_ts; their next update adds the marker.
        """
        marker = "relay.health=" + digest(channel + "\0" + thread)
        text += "\n\n" + marker
        ts = self.state.get("health_ts")
        if not ts:
            attempted = float(self.state.get("health_attempted", "0"))
            ts = self.find(channel, marker, attempted, thread)
            if ts:
                # Keep the recovered receipt even if the following update fails.
                self.state.set("health_ts", ts)
        if ts:
            time.sleep(max(0.0, self.next_post - time.monotonic()))
            self.next_post = time.monotonic() + self.min_interval
            self.call_slack("chat.update", {
                "channel": channel, "ts": ts, "text": text, "mrkdwn": False,
                "parse": "none", "link_names": False,
                "unfurl_links": False, "unfurl_media": False,
            })
        else:
            # Persist before the remote effect: a timeout or process exit must
            # reconcile the same destination on the next run, not create a root.
            self.state.set("health_attempted", time.time())
            # Health must still report a source backlog after its post cap.
            ts = self.post(channel, text, thread, budgeted=False)
            self.state.set("health_ts", ts)
        return ts

    def deliver(self, event: Event, channel: str) -> int:
        item = self.state.db.execute("SELECT channel,ts,attempted FROM items WHERE key=?", (event.key,)).fetchone()
        marker = "relay.item=" + event.key
        if item and item[0] != channel:
            raise RelayError("channel_change_requires_state_migration")
        if not item:
            self.state.db.execute("INSERT INTO items VALUES (?,?,?,?)", (event.key, channel, "", time.time()))
            self.state.db.commit()
            item = (channel, "", time.time())
        thread = item[1]
        if not thread:
            thread = self.find(channel, marker, 0 if not item[1] else item[2])
            if not thread:
                text = clean(f"{event.provider.upper()} | {event.title[:300]}\n{event.url[:800]}\n{event.action[:500]}\nRead the contents below; preserve the existing owner. Delivery is not resolution.") + "\n" + marker
                thread = self.post(channel, text)
            self.state.db.execute("UPDATE items SET ts=? WHERE key=?", (thread, event.key))
            self.state.db.commit()
        delivered = 0
        for text, keys in event.message_parts():
            key = keys[0]
            part = self.state.db.execute("SELECT ts,attempted,uncertain FROM parts WHERE key=?", (key,)).fetchone()
            if part and part[0]:
                continue
            if len(keys) > 1:
                legacy = self.state.db.execute(
                    "SELECT ts FROM parts WHERE key IN (" + ",".join("?" for _ in keys[1:]) + ") AND ts<>'' LIMIT 1", keys[1:]
                ).fetchone()
                if legacy:
                    self.state.db.execute("INSERT OR REPLACE INTO parts VALUES (?,?,?,?)", (key, legacy[0], time.time(), 0))
                    self.state.db.commit()
                    continue
            markers = tuple("relay.part=" + candidate for candidate in keys)
            marker = markers[0] if len(markers) == 1 else markers
            if not part:
                # A restored/evicted ledger must recover previously posted parts too.
                ts = self.find(channel, marker, 0, thread)
                self.state.db.execute("INSERT INTO parts VALUES (?,?,?,?)", (key, ts, time.time(), 0 if ts else 1))
                self.state.db.commit()
                if ts:
                    continue
            else:
                ts = self.find(channel, marker, part[1], thread) if part[2] else ""
                if ts:
                    self.state.db.execute("UPDATE parts SET ts=?,uncertain=0 WHERE key=?", (ts, key))
                    self.state.db.commit()
                    continue
            try:
                # Journal uncertainty before the remote effect (including retries).
                self.state.db.execute("UPDATE parts SET attempted=?,uncertain=1 WHERE key=?", (time.time(), key))
                self.state.db.commit()
                ts = self.post(channel, text, thread)
            except RelayError as exc:
                self.state.db.execute("UPDATE parts SET uncertain=? WHERE key=?", (int(exc.uncertain), key))
                self.state.db.commit()
                raise
            self.state.db.execute("UPDATE parts SET ts=?,uncertain=0 WHERE key=?", (ts, key))
            self.state.db.commit()
            delivered += 1
        return delivered


def github_pages(get: Callable, endpoint: str, max_pages: int = 20) -> list:
    rows: list = []
    for page in range(1, max_pages + 1):
        data = get(endpoint + ("&" if "?" in endpoint else "?") + f"per_page=100&page={page}")
        if not isinstance(data, list):
            raise RelayError("github_list_shape")
        rows.extend(data)
        if len(data) < 100:
            return rows
    raise RelayError("github_page_limit_pending")


def collect_delivery_groups(source: Callable, get: Callable, config: dict, since: str, seen: Callable) -> tuple[list[Event], dict]:
    """Keep the materialized collector interface for callers outside the relay."""
    info, groups = source(get, config, since, seen)
    events: list[Event] = []
    counts = []
    for version, batch in groups:
        events.extend(batch)
        counts.append((version, len(batch)))
    info["_delivery_groups"] = counts
    return events, info


def github_events(get: Callable, config: dict, since: str, seen: Callable = lambda key: "") -> tuple[list[Event], dict]:
    return collect_delivery_groups(github_delivery_groups, get, config, since, seen)


def github_delivery_groups(get: Callable, config: dict, since: str, seen: Callable = lambda key: "",
                           checkpoint: Callable = lambda key, value: None) -> tuple[dict, Iterator[tuple[str, list[Event]]]]:
    account = get("user")
    if str(account.get("login", "")).lower() != config["github_login"].lower():
        raise RelayError("github_account_mismatch")
    scan_key = "github.listing." + digest(json.dumps([
        config["github_login"].lower(), config.get("github_channel", ""),
        config.get("coordination_repository", "")]))
    retained = seen(scan_key)
    try:
        scan = json.loads(retained) if retained else {
            "since": since, "before": iso(), "feed": "changed", "page": 1, "pending": False,
        }
        if (not isinstance(scan, dict) or scan["feed"] not in {"changed", "unread"}
                or type(scan["page"]) is not int or scan["page"] < 1
                or type(scan.get("pending", False)) is not bool):
            raise ValueError
        for field in ("since", "before"):
            if not isinstance(scan[field], str):
                raise ValueError
            datetime.fromisoformat(scan[field].replace("Z", "+00:00"))
    except (KeyError, TypeError, ValueError):
        raise RelayError("github_listing_checkpoint_invalid") from None
    info = {"mode": "native-notifications", "private_omitted": 0, "carrier_noise": 0,
            "notifications": 0, "unchanged": 0, "source_items_pending": 0, "error_codes": [],
            "prior_source_items_pending": bool(scan.get("pending")), "listing_pages": 0,
            "listing_complete": False, "listing_resumed": bool(retained)}

    def groups() -> Iterator[tuple[str, list[Event]]]:
        observed: set[str] = set()
        for _ in range(20):
            # Freeze the listing window across finite runs. Keep this page until
            # every yielded group returns from the caller's successful delivery.
            checkpoint(scan_key, json.dumps(scan))
            params = {"all": "true" if scan["feed"] == "changed" else "false",
                      "before": scan["before"], "per_page": 50, "page": scan["page"]}
            if scan["feed"] == "changed":
                # Include activity another peer has already marked read.
                params["since"] = scan["since"]
            notices = get("notifications?" + urllib.parse.urlencode(params))
            if not isinstance(notices, list):
                raise RelayError("github_list_shape")
            info["listing_pages"] += 1
            for notice in notices:
                if not isinstance(notice, dict) or not notice.get("id"):
                    raise RelayError("github_notice_shape")
                notice_id = str(notice["id"])
                if notice_id not in observed:
                    info["notifications"] += 1
                    observed.add(notice_id)
                version = "gh.notice." + digest(notice_id + ":" + str(notice.get("updated_at", "")))
                # Preserve existing content-level deduplication when replaying a
                # partly delivered page or the overlapping unread collection.
                if seen(version):
                    info["unchanged"] += 1
                    continue
                try:
                    batch, included = github_notice_events(get, config, notice, info)
                except RelayError as exc:
                    info["source_items_pending"] += 1
                    scan["pending"] = True
                    checkpoint(scan_key, json.dumps(scan))
                    if exc.code not in info["error_codes"]:
                        info["error_codes"].append(exc.code)
                    if exc.retry_after:
                        raise
                    continue
                if included:
                    yield version, batch
            # The global notifications endpoint caps pages at 50, unlike issue
            # comments. A short server-capped page must not imply end of source.
            if len(notices) >= 50:
                scan["page"] += 1
            elif scan["feed"] == "changed":
                scan.update(feed="unread", page=1)
            else:
                info["listing_complete"] = True
                info["completed_until"] = scan["before"]
                checkpoint(scan_key, "")
                return
            checkpoint(scan_key, json.dumps(scan))
        raise RelayError("github_page_limit_pending")
    return info, groups()


def github_notice_events(get: Callable, config: dict, notice: dict, info: dict) -> tuple[list[Event], bool]:
    events: list[Event] = []
    repo = notice.get("repository", {})
    if repo.get("private", True):
        info["private_omitted"] += 1
        return [], False
    subject = notice.get("subject", {})
    name = str(repo.get("full_name", ""))
    title = str(subject.get("title", ""))
    if name == config.get("coordination_repository") and re.match(r"(?i)^(slack-|SWEEP_RECEIPT|relay\.)", title):
        info["carrier_noise"] += 1
        return [], False
    raw = str(subject.get("url", ""))
    expected = "https://api.github.com/repos/" + name + "/"
    if not raw.startswith(expected) or not re.fullmatch(r"[\w.-]+/[\w.-]+", name):
        raise RelayError("github_subject_content_unavailable")
    endpoint = raw.removeprefix("https://api.github.com/")
    obj = get(endpoint)
    kind = subject.get("type", "")
    number = obj.get("number")
    url = obj.get("html_url") or "https://github.com/" + name
    if not str(url).startswith("https://github.com/" + name + "/"):
        url = "https://github.com/" + name
    action = "Existing owner: inspect this update and post CLAIM / DONE + evidence / BLOCKED in this thread."
    if obj.get("merged_at"):
        action = "Existing owner: verify acceptance/payment conditions; merge is not payment. Do not duplicate a collection request."
    elif obj.get("state") == "closed":
        action = "Existing owner: inspect the closure reason; do not assume accepted or paid."
    body = str(obj.get("body") or obj.get("description") or "")
    body += "\n\nSource state: " + str(obj.get("state", obj.get("status", "unknown"))) + "; notification reason: " + str(notice.get("reason", "unknown"))
    events.append(Event("github", endpoint, "subject:" + str(notice["id"]), f"{name} #{number or kind}: {title}", body, url,
                        obj.get("user", {}).get("login", ""), str(obj.get("updated_at", notice.get("updated_at", ""))), action))
    if kind not in {"PullRequest", "Issue"} or not isinstance(number, int):
        return events, True
    root = f"repos/{name}"
    feeds = [(f"{root}/issues/{number}/comments", "issue-comment")]
    if kind == "PullRequest":
        feeds += [(f"{root}/pulls/{number}/reviews", "review"), (f"{root}/pulls/{number}/comments", "inline-review")]
    for feed, label in feeds:
        for comment in github_pages(get, feed):
            if comment.get("state") == "PENDING":
                continue
            content = str(comment.get("body") or "")
            if not content.strip() and label != "review":
                continue
            state = comment.get("state", "")
            context = (f"Review state: {state}\n" if state else "")
            if comment.get("path"):
                context += f"File: {comment['path']} | line: {comment.get('line', comment.get('original_line'))}\n"
                context += str(comment.get("diff_hunk", "")) + "\n\n"
            review_action = action
            if state == "CHANGES_REQUESTED":
                review_action = "ACTION REQUIRED: existing PR owner address the review, test, and reply with the fix receipt."
            elif state == "APPROVED":
                review_action = "Approval received: existing owner check remaining required checks/maintainer merge actions; do not re-edit passed work without new feedback."
            events.append(Event("github", endpoint, label + ":" + str(comment["id"]), f"{name} #{number} — {label}",
                                context + content, str(comment.get("html_url") or url), comment.get("user", {}).get("login", ""),
                                str(comment.get("updated_at") or comment.get("submitted_at") or comment.get("created_at") or ""), review_action))
    return events, True

def mail_header(value: str) -> str:
    """Decode RFC 2047 display text before the existing mail classification."""
    try:
        # Keep malformed encoded words literal; then use the modern parser so
        # mixed native Unicode and encoded words do not lose non-ASCII text.
        decode_header(value)
        unfolded = re.sub(r"\r?\n(?=[ \t])", "", value)
        return str(mail_policy.header_factory("Subject", unfolded))
    except (HeaderParseError, LookupError, ValueError):
        return value


def gmail_events(get: Callable, config: dict, since: str, seen: Callable = lambda key: "") -> tuple[list[Event], dict]:
    return collect_delivery_groups(gmail_delivery_groups, get, config, since, seen)


def gmail_message_ids(get: Callable, query: str, info: dict, scope: str,
                      seen: Callable, checkpoint: Callable | None = None) -> Iterator[str]:
    """Yield ID pages with a scoped continuation after successful consumption."""
    key = "gmail.listing." + scope
    saved = seen(key)
    try:
        prior = json.loads(saved) if saved else {}
    except (TypeError, ValueError):
        raise RelayError("gmail_listing_checkpoint_invalid") from None
    if (not isinstance(prior, dict) or (prior and prior.get("scope") != scope)
            or type(prior.get("pending", False)) is not bool):
        raise RelayError("gmail_listing_checkpoint_invalid")
    token = prior.get("page_token", "")
    if not isinstance(token, str):
        raise RelayError("gmail_listing_checkpoint_invalid")
    info["message_listing_resumed"] = bool(token)
    info["prior_source_items_pending"] = bool(prior.get("pending"))
    def save(next_token: str | None):
        if checkpoint is not None:
            checkpoint(key, "" if next_token is None else json.dumps({
                "scope": scope, "page_token": next_token,
                "pending": bool(prior.get("pending") or info.get("source_items_pending"))}, sort_keys=True))
    requested_tokens: set[str] = set()
    seen_ids: set[str] = set()
    for _ in range(20):
        if token in requested_tokens:
            raise RelayError("gmail_page_cursor_repeated")
        requested_tokens.add(token)
        params = {"q": query, "maxResults": 100}
        if token:
            params["pageToken"] = token
        try:
            page = get("messages", params)
        except RelayError as exc:
            if token and exc.code == "http_400":
                # An expired/invalid continuation must not trap every future
                # pass. Retain item markers and report this provider error;
                # the next pass can restart the same query from page one.
                save(None)
            raise
        if not isinstance(page, dict) or not isinstance(page.get("messages", []), list):
            raise RelayError("gmail_list_shape")
        # Until every yielded group returns from delivery, a retry must start
        # with this page; per-message markers skip its completed deliveries.
        save(token)
        info["message_pages"] += 1
        for item in page.get("messages", []):
            mid = item.get("id") if isinstance(item, dict) else None
            if not isinstance(mid, str) or not mid:
                raise RelayError("gmail_list_shape")
            if mid in seen_ids:
                info["duplicate_message_ids"] += 1
                continue
            seen_ids.add(mid)
            info["messages"] += 1
            yield mid
        token = page.get("nextPageToken", "")
        if not isinstance(token, str):
            raise RelayError("gmail_list_shape")
        if not token:
            save(None)
            info["message_listing_complete"] = True
            return
        if token in requested_tokens:
            raise RelayError("gmail_page_cursor_repeated")
        save(token)
    raise RelayError("gmail_page_limit_pending")


def gmail_delivery_groups(get: Callable, config: dict, since: str, seen: Callable = lambda key: "",
                          checkpoint: Callable | None = None) -> tuple[dict, Iterator[tuple[str, list[Event]]]]:
    profile = get("profile")
    if str(profile.get("emailAddress", "")).lower() != config["gmail_address"].lower():
        raise RelayError("gmail_account_mismatch")
    # Sliding overlap intentionally re-reads IDs; per-part dedup prevents repeat posts.
    query = config.get("gmail_query", "{newer_than:14d is:unread is:starred} -in:spam -in:trash -in:sent -in:drafts")
    info = {"mode": "work-mail-poll", "messages": 0, "message_pages": 0,
            "message_listing_complete": False, "message_listing_resumed": False, "duplicate_message_ids": 0,
            "unchanged": 0, "private_or_auth_omitted": 0,
            "promotional_omitted": 0, "github_mail_deduped": 0, "unclassified_pending": 0, "source_items_pending": 0, "body_pending": 0}
    def groups() -> Iterator[tuple[str, list[Event]]]:
        scope = digest(json.dumps([config["gmail_address"].lower(),
                                   config.get("gmail_channel", ""), query]))
        for mid in gmail_message_ids(get, query, info, scope, seen, checkpoint):
            # Received message IDs are immutable. Skip only a completed content
            # delivery; omitted/partial mail remains eligible on every poll.
            version = "gmail.delivered." + digest(json.dumps([
                config["gmail_address"].lower(), config.get("gmail_channel", ""), mid]))
            if seen(version):
                info["unchanged"] += 1
                continue
            try:
                message = get("messages/" + mid, {"format": "full"})
            except RelayError as exc:
                if exc.retry_after:
                    raise
                info["source_items_pending"] += 1
                continue
            labels = set(message.get("labelIds", []))
            if labels.intersection({"SENT", "DRAFT", "SPAM", "TRASH"}):
                continue
            headers = {h["name"].lower(): h["value"] for h in message.get("payload", {}).get("headers", [])}
            title = mail_header(headers.get("subject", "(no subject)"))
            raw_sender = headers.get("from", "")
            # Encoded display-name punctuation must not change address selection.
            address = parseaddr(raw_sender)[1].lower()
            sender = mail_header(raw_sender)
            domain = address.rpartition("@")[2]
            if AUTH_MAIL.search(title) or PRIVATE_MAIL.search(title):
                info["private_or_auth_omitted"] += 1
                continue
            if domain == "github.com" or domain.endswith(".github.com"):
                info["github_mail_deduped"] += 1
                continue
            if "CATEGORY_PROMOTIONS" in labels:
                info["promotional_omitted"] += 1
                continue
            payload = message.get("payload", {})
            body = mail_body(payload)
            complete_body = bool(body) and "[Body stored as an attachment;" not in body and "[Body decoding failed;" not in body
            if not complete_body:
                info["body_pending"] += 1
            if not (WORK_MAIL.search(title) or domain in config.get("work_sender_domains", []) or address in config.get("work_senders", [])):
                info["unclassified_pending"] += 1
                continue
            # For selected work messages, suppress embedded login/secret material too.
            if AUTH_MAIL.search(body[:700]) and not WORK_MAIL.search(title):
                info["private_or_auth_omitted"] += 1
                continue
            names = attachment_names(payload)
            if names:
                body += "\n\nAttachments (not downloaded or published by relay):\n" + "\n".join(names)
            action = "Existing relationship owner: inspect and claim the next action. Check sent-thread history/holds before replying; no automatic outbound email."
            if re.search(r"(?i)(automatic reply|auto.?reply|received|registration request)", title):
                action = "Acknowledgement only: existing owner track the promised next step; do not treat this as acceptance or payment."
            event = Event("gmail", str(message.get("threadId") or mid), mid, title, body,
                                "https://mail.google.com/mail/#all/" + mid, sender, headers.get("date", ""), action)
            yield version if complete_body else "", [event]
    return info, groups()


def run(config: dict, state: State, providers: Providers) -> dict:
    now = datetime.now(UTC)
    report: dict = {"observed_at": iso(now), "status": "BLOCKED", "posted_parts": 0, "errors": {}, "sources": {}}
    if float(state.get("retry_after", "0")) > time.time():
        report["errors"]["delivery"] = "provider_retry_after_active"
        return report
    slack_identity = providers.slack("auth.test", {})
    workspace = urllib.parse.urlsplit(str(slack_identity.get("url", ""))).hostname
    if workspace != config["slack_workspace"]:
        raise RelayError("slack_workspace_mismatch")
    delivery = Delivery(state, providers.slack, max_posts=int(config.get("max_posts_per_run", 100)), min_interval=float(config.get("min_post_interval", 1.05)))
    since = state.get("github_since", iso(now - timedelta(days=int(config.get("backfill_days", 14)))))
    sources = [("github", github_delivery_groups, config["github_channel"]), ("gmail", gmail_delivery_groups, config["gmail_channel"])]
    if state.get("next_source") == "gmail":
        sources.reverse()
    next_source = None
    for name, source, channel in sources:
        retry_key = "retry_after." + name
        if float(state.get(retry_key, "0")) > time.time():
            report["errors"][name] = "provider_retry_after_active"
            continue
        if delivery.posts >= delivery.max_posts:
            # No source bodies are needed when this pass cannot deliver them.
            # Give the unserved source the first turn on the next finite pass.
            next_source = next_source or name
            report["errors"][name] = "delivery_budget_pending"
            continue
        collecting = True
        try:
            getter = providers.github if name == "github" else providers.gmail
            info, groups = source(getter, config, since, state.get, state.set)
            report["sources"][name] = info
            while True:
                collecting = False
                # Do not advance a lazy source when no delivery allowance remains.
                if delivery.posts >= delivery.max_posts:
                    raise RelayError("delivery_budget_pending")
                collecting = True
                try:
                    version, batch = next(groups)
                except StopIteration:
                    break
                collecting = False
                for event in batch:
                    report["posted_parts"] += delivery.deliver(event, channel)
                if version:
                    state.set(version, "1")
            state.set(name + "_last_poll", iso())
            if info.get("source_items_pending", 0) or info.get("prior_source_items_pending"):
                report["errors"][name] = "source_items_pending"
            else:
                state.set(name + "_last_success", iso())
                if name == "github":
                    # A resumed listing may have started in an earlier run.
                    # Advancing to wall time would skip arrivals during that scan.
                    completed = datetime.fromisoformat(info["completed_until"].replace("Z", "+00:00"))
                    state.set("github_since", iso(completed - timedelta(minutes=10)))
        except RelayError as exc:
            report["errors"][name] = exc.code
            if exc.code == "delivery_budget_pending":
                next_source = next_source or ("gmail" if name == "github" else "github")
            if exc.retry_after:
                # A source's API budget is independent of the other source.
                # Slack delivery (and legacy global deadlines) still pause all.
                state.set(retry_key if collecting else "retry_after", time.time() + exc.retry_after)
                if not collecting:
                    break
        except Exception:
            report["errors"][name] = "unexpected_source_error"
    if next_source:
        state.set("next_source", next_source)
        report["next_source"] = next_source
    report["last_success"] = {name: state.get(name + "_last_success", "never") for name in ("github", "gmail")}
    pending = state.db.execute("SELECT COUNT(*) FROM parts WHERE ts='' ").fetchone()[0]
    report["pending_parts"] = pending
    incomplete = any(info.get("unclassified_pending", 0) or info.get("private_omitted", 0) or info.get("body_pending", 0) for info in report["sources"].values())
    report["status"] = "DEGRADED" if report["errors"] or pending or incomplete else "LIVE"
    if delivery.cooldown_until > time.time():
        # Keep the local receipt; the next scheduled pass can update Slack
        # after its persisted Retry-After boundary. A source-provider cooldown
        # does not set this Slack-only boundary.
        report["health_delivery"] = "deferred_slack_retry_after"
        return report
    health = ("INBOX VISIBILITY — " + report["status"] + "\n" + json.dumps(report, indent=2) +
              "\nDelivered is not resolved. CLAIM / DONE + evidence / BLOCKED live in each source thread. "
              "Private GitHub notifications and unclassified mail require a separate permitted review; zero public deliveries is not an empty inbox. "
              "A receipt older than 30 minutes is STALE even if its stored status says LIVE. Attachments are listed, not read.")
    delivery.deliver_health(config["health_channel"], health, config.get("health_thread") or "")
    return report


class RunLock:
    """Serialize the finite job on an existing runtime, including manual runs."""
    def __init__(self, path):
        self.path, self.handle = Path(str(path) + ".lock"), None
    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a+b")
        self.handle.write(b"0")
        self.handle.flush()
        self.handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.handle.close()
            raise RelayError("another_poll_is_running") from None
        return self
    def __exit__(self, *args):
        if self.handle is not None:
            self.handle.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="host/inbox_visibility.json")
    parser.add_argument("--state", default=str(Path.home() / ".commons" / "inbox-visibility" / "state.sqlite3"))
    args = parser.parse_args()
    # One finite run. The OS scheduler/workflow owns cadence and single-flight.
    try:
        with RunLock(args.state):
            config = json.loads(Path(args.config).read_text(encoding="utf-8"))
            # A competing poll must not open, initialize, or chmod the ledger.
            # Keep SQLite's entire lifetime inside the process lock.
            state = State(args.state)
            try:
                try:
                    report = run(config, state, Providers())
                except RelayError as exc:
                    # Initial Slack reads and final health writes are outside the
                    # source loop. Persist their cooldown before releasing the lock.
                    if exc.retry_after > 0:
                        state.set("retry_after", max(float(state.get("retry_after", "0")),
                                                     time.time() + exc.retry_after))
                    raise
            finally:
                state.close()
    except RelayError as exc:
        report = {"observed_at": iso(), "status": "BLOCKED", "error": exc.code}
    except sqlite3.Error:
        report = {"observed_at": iso(), "status": "BLOCKED", "error": "state_database_error"}
    except Exception:
        report = {"observed_at": iso(), "status": "BLOCKED", "error": "configuration_or_runtime_error"}
    rendered = json.dumps(report, indent=2)
    print(rendered)  # Counters and fixed codes only; never source contents or tokens.
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as handle:
            handle.write("## Inbox visibility receipt\n```json\n" + rendered + "\n```\n")
    return 0 if report["status"] == "LIVE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
