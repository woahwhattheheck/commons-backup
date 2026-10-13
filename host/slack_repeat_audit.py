#!/usr/bin/env python3
"""Read-only audit of exact, short-window repetitions in a Slack history capture.

This is an evidence tool, not an automatic deduplicator: it never sends, edits,
removes, or suppresses messages. Identical posts may have been intentional.
Input: a list of message dictionaries, or {"channel": "C...", "messages": [...]}.
Requires Python 3.10+; uses only the standard library.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Any

_TS = re.compile(r"^[0-9]+\.[0-9]{6}$")
_CHANNEL = re.compile(r"^[CDG][A-Z0-9]+$")
_USER = re.compile(r"^[UBW][A-Z0-9]+$")
_CONTENT_FIELDS = ("text", "blocks", "attachments", "files", "metadata", "edited")
_ALLOWED_SUBTYPES = {None, "", "bot_message", "me_message", "file_share"}
_MAX_BYTES = 32 * 1024 * 1024


@dataclass(frozen=True)
class Message:
    channel: str
    ts: str
    author: str
    thread: str | None
    fingerprint: str
    text_length: int

    @property
    def moment(self) -> Decimal:
        return Decimal(self.ts)

    @property
    def locator(self) -> tuple[str, str]:
        return self.channel, self.ts

    @property
    def content_key(self) -> tuple[str, str, str | None, str]:
        return self.channel, self.author, self.thread, self.fingerprint

    @property
    def observation_key(self) -> tuple[str, str | None, str]:
        return self.author, self.thread, self.fingerprint


def _timestamp(value: Any, field: str) -> str:
    # Never round Slack timestamps through a float: preserve all six digits.
    if not isinstance(value, str) or not _TS.fullmatch(value):
        raise ValueError(f"{field} must be a timestamp string with six fractional digits")
    return value


def _canonical(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("message content must contain JSON-compatible finite values") from exc


def _normalize(raw: Any, default_channel: str | None, index: int) -> tuple[Message | None, str | None]:
    if not isinstance(raw, dict):
        raise ValueError(f"messages[{index}] must be an object")
    kind = raw.get("type", "message")
    subtype = raw.get("subtype")
    if not isinstance(kind, str) or (subtype is not None and not isinstance(subtype, str)):
        raise ValueError(f"messages[{index}] has invalid type or subtype")
    if kind != "message" or subtype not in _ALLOWED_SUBTYPES:
        return None, f"messages[{index}]: unsupported event type/subtype"
    channel = raw.get("channel") or default_channel
    if not isinstance(channel, str) or not _CHANNEL.fullmatch(channel):
        raise ValueError(f"messages[{index}]: missing or invalid channel ID")
    ts = _timestamp(raw.get("ts"), f"messages[{index}].ts")
    author = raw.get("user") or raw.get("bot_id")
    if not isinstance(author, str) or not _USER.fullmatch(author):
        return None, f"messages[{index}]: missing or invalid author identity"
    thread = raw.get("thread_ts")
    if thread is not None:
        thread = _timestamp(thread, f"messages[{index}].thread_ts")
        # Slack can annotate a thread parent with its own timestamp.
        if thread == ts:
            thread = None
    text = raw.get("text", "")
    if not isinstance(text, str):
        raise ValueError(f"messages[{index}].text must be a string")
    # Conservative equality: changed text, rich blocks, files, metadata, edits,
    # or subtype must not silently become the same reportable content.
    payload = {key: raw[key] for key in _CONTENT_FIELDS if key in raw}
    payload["text"] = text
    payload["subtype"] = subtype or None
    if not text and not any(raw.get(key) for key in ("blocks", "attachments", "files")):
        return None, f"messages[{index}]: no visible message content"
    digest = hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()
    return Message(channel, ts, author, thread, digest, len(text)), None


def audit(document: Any, window_seconds: str = "2", *, channel: str | None = None) -> dict[str, Any]:
    """Return an evidence report without changing the input or remote state.

    Windows are anchored at the first message, not chained from the previous
    message. Two overlapping history pages do not constitute repeated posts.
    Conflicting snapshots of one ID (for example, an edit) are reported separately
    and excluded from content repetition groups rather than guessed about.
    """
    try:
        window = Decimal(window_seconds)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("window_seconds must be a finite nonnegative decimal") from exc
    if not window.is_finite() or window < 0:
        raise ValueError("window_seconds must be a finite nonnegative decimal")
    provenance: Any = None
    if isinstance(document, dict):
        raw_messages = document.get("messages")
        channel = channel or document.get("channel")
        provenance = document.get("provenance")
    else:
        raw_messages = document
    if not isinstance(raw_messages, list):
        raise ValueError("input must be a message list or an object with a messages list")

    # Each ID can have repeated read observations or conflicting snapshots.
    observations: dict[tuple[str, str], dict[tuple[str, str | None, str], Message]] = {}
    repeated_reads = 0
    skipped: list[str] = []
    eligible_records = 0
    for index, raw in enumerate(raw_messages):
        msg, reason = _normalize(raw, channel, index)
        if msg is None:
            skipped.append(reason or f"messages[{index}]: skipped")
            continue
        eligible_records += 1
        variants = observations.setdefault(msg.locator, {})
        if msg.observation_key in variants:
            repeated_reads += 1
        else:
            variants[msg.observation_key] = msg

    conflicts: list[dict[str, Any]] = []
    buckets: dict[tuple[str, str, str | None, str], list[Message]] = defaultdict(list)
    for (ch, ts), variants in observations.items():
        if len(variants) > 1:
            conflicts.append({"channel": ch, "ts": ts,
                              "variant_count": len(variants),
                              "content_sha256_values": sorted({m.fingerprint for m in variants.values()}),
                              "interpretation": "Conflicting snapshots; no transport-cause attribution."})
            continue
        msg = next(iter(variants.values()))
        buckets[msg.content_key].append(msg)

    groups: list[dict[str, Any]] = []

    def emit(batch: list[Message]) -> None:
        if len(batch) < 2:
            return
        first, last = batch[0], batch[-1]
        groups.append({
            "channel": first.channel, "author": first.author,
            "thread_ts": first.thread, "content_sha256": first.fingerprint,
            "text_length": first.text_length, "message_count": len(batch),
            "additional_observed_copies": len(batch) - 1,
            "span_seconds": format(last.moment - first.moment, "f"),
            "timestamps": [m.ts for m in batch],
            "source_urls": [f"https://app.slack.com/archives/{m.channel}/p{m.ts.replace('.', '')}"
                            for m in batch],
        })

    for messages in buckets.values():
        batch: list[Message] = []
        for msg in sorted(messages, key=lambda m: m.moment):
            if batch and msg.moment - batch[0].moment > window:
                emit(batch)
                batch = []
            batch.append(msg)
        emit(batch)
    groups.sort(key=lambda g: (Decimal(g["timestamps"][0]), g["channel"], g["content_sha256"]))
    distinct_eligible = len(observations) - len(conflicts)
    clustered = sum(group["message_count"] for group in groups)
    return {
        "schema": "slack-repeat-audit/v1", "mode": "read_only_evidence",
        "window_seconds": format(window, "f"), "provenance": provenance,
        "counts": {
            "input_records": len(raw_messages), "eligible_records": eligible_records,
            "skipped_records": len(skipped), "distinct_message_ids": len(observations),
            "repeated_read_observations": repeated_reads,
            "conflicting_message_ids": len(conflicts),
            "eligible_unique_messages": distinct_eligible,
            "repetition_groups": len(groups), "messages_in_repetition_groups": clustered,
            "additional_observed_copies": sum(g["additional_observed_copies"] for g in groups),
            "unclustered_unique_messages": distinct_eligible - clustered,
        },
        "groups": groups, "conflicting_snapshots": conflicts,
        "skipped": skipped,
        "limitations": [
            "Repeated visible content does not establish a retry bug, malicious activity, or a delivery failure.",
            "Distinct timestamps are preserved; intentional repeated messages remain possible.",
            "This tool does not send, edit, delete, suppress, or acknowledge messages.",
            "Results describe only the supplied capture; they do not imply complete channel coverage.",
            "Missing rich payload fields cannot be compared; rendered-text captures are not raw API payload proof.",
        ],
    }


def _write_atomic(path: Path, text: str) -> None:
    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent,
                                         prefix=f".{path.name}.", delete=False) as handle:
            temp_name = handle.name
            handle.write(text)
        os.replace(temp_name, path)
    finally:
        if temp_name and os.path.exists(temp_name):
            os.unlink(temp_name)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="Local JSON history capture; never a URL")
    parser.add_argument("--output", type=Path, help="Write JSON report atomically; defaults to stdout")
    parser.add_argument("--window-seconds", default="2", help="Maximum anchored span; default: 2")
    parser.add_argument("--channel", help="Channel ID for records lacking their own channel field")
    args = parser.parse_args(argv)
    try:
        # Bound the bytes read, even if the file changes after opening.
        with args.input.open("rb") as handle:
            raw = handle.read(_MAX_BYTES + 1)
        if len(raw) > _MAX_BYTES:
            raise ValueError("input exceeds the 32 MiB local capture limit")
        document = json.loads(raw.decode("utf-8"))
        report = audit(document, args.window_seconds, channel=args.channel)
        rendered = json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
        if args.output:
            _write_atomic(args.output, rendered)
        else:
            sys.stdout.write(rendered)
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"slack_repeat_audit: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
