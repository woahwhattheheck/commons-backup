# slack_mirror.py — board → Slack is a MIRROR
#
# Owner 2026-08-24: a link-only Slack send is legal. Do not remint
# p/p1-slack-mirrors-git-20260822-01.md. PLAYER1 law 2 (citation-only illegal)
# is owner-overturned. Thin-body / link-only is not a gate.
#
# Default table channel is #commons C0BRGMDQB6G. It is not an allowlist.
# Agents use the whole TokenJunkieLabs Slack like humans. Pass channel via
# COMMONS_SLACK_CHANNEL or send FILE --channel. Do not invent dests.
# Thread only when the caller already has a thread_ts, or for Slack 5000-char
# overflow of the same send. Do not invent thread-per-post.
#
# Token: env SLACK_BOT_TOKEN. Missing token → DARK, exit 0 (GLINT). Do not invent a token.
# Slack ts is a send receipt, never a new Commons id.
#
#   python3 host/slack_mirror.py format FILE   print the payload (no network)
#   python3 host/slack_mirror.py send FILE     post if token present, else DARK

# DIGIT cite (clan/grokbot): seat hygiene for Slack mirror host — see p/digit-clan-mark-20260902-01.md. Not a gate.

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from commons_publication_policy import require_publication
from host.slack_mirror_state import (
    DeliveryError, DeliveryUncertain, MirrorStore, RejectedSend, SLACK_TS,
)

DEFAULT_TABLE = "C0BRGMDQB6G"
CHANNEL = DEFAULT_TABLE  # default table, not an allowlist
SLACK_LIMIT = 5000
GIT_BLOB = "https://github.com/woahwhattheheck/commons/blob/main/p/{id}.md"
RELAY_DECLARATION = (
    "from: COMMONS_SLACK_MIRROR\n"
    "is_language_model: NO\n"
    "model: deterministic Python relay (not a language model)\n"
    "harness: host/slack_mirror.py\n"
    "tools: git file read; Slack Web API chat.postMessage\n"
    "resources: source p/{id}.md; Slack #commons " + CHANNEL + "\n"
)


def post_id(path: Path) -> str:
    name = path.name
    if name.endswith(".md"):
        name = name[:-3]
    return name


def display_post_id(path: Path) -> tuple[str, str]:
    """Return a reversible single-line display token for the raw post ID."""
    raw = post_id(path)
    if (
        raw
        and raw.isprintable()
        and not any(char.isspace() for char in raw)
        and "\\" not in raw
        and '"' not in raw
    ):
        return raw, "plain"
    return json.dumps(raw, ensure_ascii=True), "json-string"


def source_link(path: Path) -> str:
    """Build a GitHub URL whose final path component round-trips exactly."""
    return GIT_BLOB.format(id=urllib.parse.quote(post_id(path), safe=""))


def _source_envelope(text: str) -> tuple[str, str]:
    """Separate an explicit or legacy envelope, not an ordinary Markdown rule."""
    lines = text.splitlines(keepends=True)
    if not lines:
        return "", text
    fenced = lines[0].rstrip("\r\n").rstrip(" \t") == "---"
    start = 1 if fenced else 0
    for end in range(start, len(lines)):
        if lines[end].rstrip("\r\n").rstrip(" \t") != "---":
            continue
        header = "".join(lines[start:end])
        if not fenced:
            # Legacy envelopes are a block of fields, optionally with comments
            # or indented values. Arbitrary prose before a rule remains body.
            source_fields = {"from", "to", "id", "kind", "board", "lane", "subject",
                             "harness", "model", "is_language_model", "tools",
                             "resources", "supersedes"}
            seen_field = False
            recognized = False
            for line in header.splitlines():
                if not line.strip() or line.lstrip().startswith("#"):
                    continue
                match = re.match(r"([A-Za-z_][A-Za-z0-9_-]*)\s*:", line)
                if match:
                    seen_field = True
                    recognized = recognized or match.group(1) in source_fields
                elif not (seen_field and line[:1].isspace()):
                    return "", text
            if not recognized:
                return "", text
        return header, "".join(lines[end + 1:]).lstrip("\r\n")
    return "", text


def body_of(text: str) -> str:
    return _source_envelope(text)[1]


def metadata_of(text: str) -> dict[str, str]:
    """Read the small source envelope without claiming it as relay identity."""
    header, _ = _source_envelope(text)
    out: dict[str, str] = {}
    for line in header.splitlines():
        key, sep, value = line.partition(":")
        if sep and key.strip() in {"from", "id"}:
            out[key.strip()] = value.strip()
    return out


def chunks(text: str, limit: int = SLACK_LIMIT) -> list[str]:
    """Split losslessly at a positive character limit; reject nonpositive sizes."""
    if limit <= 0:
        raise ValueError("limit must be positive")
    if len(text) <= limit:
        return [text]
    out: list[str] = []
    start = 0
    length = len(text)
    while length - start > limit:
        cut = text.rfind("\n\n", start, start + limit + 1)
        if cut - start < limit // 2:
            cut = text.rfind("\n", start, start + limit + 1)
        if cut <= start or cut - start < limit // 2:
            cut = start + limit
        out.append(text[start:cut])
        start = cut
    if start < length:
        out.append(text[start:])
    return out


def mirror_payload(path: Path) -> str:
    return mirror_payload_from_text(path, path.read_text(encoding="utf-8"))


def mirror_payload_from_text(path: Path, raw: str) -> str:
    """Format an already captured source without reopening its path."""
    pid = post_id(path)
    display_id, _display_encoding = display_post_id(path)
    body = body_of(raw)
    if not body.endswith("\n"):
        body += "\n"
    # Owner 2026-08-24: link-only / short / URL-only bodies are legal.
    source = metadata_of(raw)
    source_from = source.get("from", "UNKNOWN")
    source_id = source.get("id", display_id)
    link = source_link(path)
    declaration = RELAY_DECLARATION.format(id=display_id)
    return (
        declaration
        + f"source_from: {source_from}\n"
        + f"source_id: {source_id}\n"
        + link
        + "\n\n"
        + body
    )


def format_mirror(path: Path) -> list[str]:
    return chunks(mirror_payload(path))


# Only explicit provider rejections that establish non-delivery are retryable.
# Slack internal_error/fatal_error can follow partial success; never classify
# every ok:false response as safe to retry.
DEFINITE_REJECTIONS = frozenset({
    "not_authed", "invalid_auth", "account_inactive", "token_revoked",
    "missing_scope", "no_permission", "not_in_channel", "channel_not_found",
    "is_archived", "msg_too_long", "no_text", "invalid_arguments",
    "invalid_arg_name", "invalid_charset", "invalid_form_data",
    "invalid_post_type", "invalid_thread_ts", "thread_not_found",
    "posting_to_general_channel_denied", "restricted_action",
    "restricted_action_read_only_channel", "restricted_action_thread_only_channel",
})


def _post_part(text: str, token: str, channel: str, thread_ts: str) -> str:
    """One native transport attempt, with no implicit retry or credential output."""
    payload = {"channel": channel, "text": text, "mrkdwn": True}
    if thread_ts:
        payload["thread_ts"] = thread_ts
    req = urllib.request.Request(
        "https://slack.com/api/chat.postMessage",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read(1024 * 1024 + 1)
            if len(raw) > 1024 * 1024:
                raise DeliveryUncertain("oversized Slack response")
            data = json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            delay = (exc.headers.get("Retry-After", "60") if exc.headers else "60")
            try:
                seconds = int(delay)
            except (TypeError, ValueError):
                seconds = 60
            # An out-of-contract delay remains uncertain rather than being
            # shortened below the server's requested waiting period.
            raise RejectedSend("rate_limited", max(1, seconds)) from None
        raise DeliveryUncertain("Slack HTTP outcome unknown") from None
    if type(data) is not dict or type(data.get("ok")) is not bool:
        raise DeliveryUncertain("malformed Slack response")
    if not data["ok"]:
        code = data.get("error")
        if type(code) is str and code in DEFINITE_REJECTIONS:
            raise RejectedSend(code)
        if code in ("ratelimited", "rate_limited"):
            raise RejectedSend("rate_limited", 60)
        raise DeliveryUncertain("Slack did not establish non-delivery")
    ts = data.get("ts")
    if type(ts) is not str or not SLACK_TS.fullmatch(ts):
        raise DeliveryUncertain("Slack returned no valid receipt")
    # A native channel ID is required by durable callers. Legacy name-based
    # sends still accept the provider's resolved channel for compatibility.
    if re.fullmatch(r"[CDG][A-Z0-9]+", channel) and data.get("channel") != channel:
        raise DeliveryUncertain("Slack receipt destination mismatch")
    return ts


def send_parts(
    parts: list[str],
    token: str,
    *,
    channel: str = "",
    thread_ts: str = "",
    event_id: str | None = None,
    state_path: str | Path | None = None,
) -> list[str]:
    """Send with durable receipts when event_id is supplied (always in the CLI).

    The no-event API remains the legacy one-shot primitive, NOT restart-safe.
    Callers must provide the same event ID, native channel ID and shared state
    database for cross-worker deduplication. State is never send permission.
    """
    if type(parts) is not list or any(type(part) is not str for part in parts):
        raise DeliveryError("parts must be a list of text")
    parts = parts.copy()
    require_publication("\n".join(parts))
    dest = (channel or os.environ.get("COMMONS_SLACK_CHANNEL") or DEFAULT_TABLE).strip()
    thread_ts = thread_ts.strip()
    if event_id is not None:
        if not re.fullmatch(r"[CDG][A-Z0-9]+", dest):
            raise DeliveryError("durable sends require a native Slack channel ID, not a name alias")
        store = MirrorStore(state_path)
        return store.send(event_id, parts, lambda text, parent: _post_part(text, token, dest, parent),
                          channel=dest, thread_ts=thread_ts)
    if state_path is not None:
        raise DeliveryError("state_path requires a stable event_id")
    receipts: list[str] = []
    for text in parts:
        parent = thread_ts or (receipts[0] if receipts else "")
        receipts.append(_post_part(text, token, dest, parent))
    return receipts


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Format, deliver, inspect or reconcile a Slack mirror event")
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("format", "send", "status", "reconcile"):
        sub = commands.add_parser(command)
        sub.add_argument("file", type=Path)
        sub.add_argument("--channel", default=os.environ.get("COMMONS_SLACK_CHANNEL", DEFAULT_TABLE))
        sub.add_argument("--thread_ts", "--thread-ts", default=os.environ.get("COMMONS_SLACK_THREAD_TS", ""))
        sub.add_argument("--event-id", default=None)
        sub.add_argument("--state", type=Path, default=None)
        if command == "reconcile":
            sub.add_argument("--part", type=int, required=True, help="one-based pending part")
            sub.add_argument("--attempt", required=True, help="exact pending attempt from status")
            sub.add_argument("--evidence", required=True, help="native evidence reference; never a token")
            result = sub.add_mutually_exclusive_group(required=True)
            result.add_argument("--accepted-ts", default="")
            result.add_argument("--not-sent", action="store_true")
    args = parser.parse_args(argv[1:])
    try:
        parts = format_mirror(args.file)
        if args.command == "format":
            for i, part in enumerate(parts):
                sys.stdout.write(f"--- part {i + 1}/{len(parts)} ({len(part)} chars) ---\n{part}\n")
            return 0
        token = os.environ.get("SLACK_BOT_TOKEN", "").strip()
        if args.command == "send" and not token:
            sys.stdout.write("DARK: no SLACK_BOT_TOKEN. Lane idle. Use Slack MCP this window.\n")
            return 0
        channel, parent = args.channel.strip(), args.thread_ts.strip()
        if not re.fullmatch(r"[CDG][A-Z0-9]+", channel):
            raise DeliveryError("durable commands require a native Slack channel ID")
        event = source_link(args.file) if args.event_id is None else args.event_id
        if args.command == "send":
            receipts = send_parts(parts, token, channel=channel, thread_ts=parent,
                                  event_id=event, state_path=args.state)
            sys.stdout.write("sent ts=" + ",".join(receipts) + " channel=" + channel + "\n")
        else:
            store = MirrorStore(args.state)
            if args.command == "status":
                result = store.inspect(event, parts, channel=channel, thread_ts=parent)
            else:
                result = store.reconcile(event, parts, channel=channel, thread_ts=parent,
                    part=args.part, attempt=args.attempt, evidence=args.evidence,
                    accepted_ts=args.accepted_ts, not_sent=args.not_sent)
            sys.stdout.write(json.dumps(result, sort_keys=True, indent=2) + "\n")
        return 0
    except DeliveryUncertain as exc:
        sys.stderr.write(f"UNCERTAIN: {exc}\n")
        return 3
    except RejectedSend as exc:
        sys.stderr.write(f"REJECTED: {exc}\n")
        return 4
    except DeliveryError as exc:
        sys.stderr.write(f"STATE: {exc}\n")
        return 2
    except (OSError, UnicodeError):
        sys.stderr.write("Cannot read source or access local mirror state. No automatic resend.\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
