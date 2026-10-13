#!/usr/bin/env python3
"""Fail-closed classification for an immutable Slack carrier projection."""

from __future__ import annotations

from datetime import datetime
import hashlib
import ntpath
import os
import re
import stat


DEFAULT_SLACK_CHANNEL = "C0BRGMDQB6G"
MAX_PROJECTION_BYTES = 64 * 1024
CARRIER_ONLY = "CARRIER_ONLY"
DURABLE_ON_MAIN = "DURABLE_ON_MAIN"
UNVERIFIED_PRESENT = "UNVERIFIED_PRESENT"
_UTC_TS = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")
_SOURCE_TS = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z\Z")
_CARRIER_TS = re.compile(r"\d{10}\.\d{6}\Z")
_KEY = re.compile(r"[a-z_]+\Z")
_OUTER_KEYS = {
    "from", "to", "id", "ts", "carrier", "observed_event", "carrier_ts",
    "durable_ts", "state", "board", "subject", "kind", "is_language_model",
    "model", "harness",
}
_OUTER_REQUIRED = {
    "from", "to", "id", "ts", "carrier", "observed_event", "carrier_ts",
    "durable_ts", "state", "subject", "kind",
}
_INNER_KEYS = {
    "from", "to", "id", "kind", "board", "subject", "is_language_model",
    "model", "harness",
}
_INNER_REQUIRED = {"from", "id", "kind", "subject"}


def _unverified(reason, *, present=True):
    return {
        "present": present,
        "state": UNVERIFIED_PRESENT,
        "provenance_ok": False,
        "mismatches": [reason],
    }


def _is_reparse(info):
    return bool(
        getattr(info, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )


def _projection_path(root, relative_path):
    """Resolve only a canonical relative descendant with no link components."""
    root = os.path.abspath(os.fspath(root))
    try:
        root_info = os.lstat(root)
    except OSError:
        return "", "projection root is unreadable"
    if (
        not stat.S_ISDIR(root_info.st_mode)
        or stat.S_ISLNK(root_info.st_mode)
        or _is_reparse(root_info)
    ):
        return "", "projection root is not a regular non-reparse directory"
    raw = os.fspath(relative_path)
    if (
        not raw
        or "\x00" in raw
        or os.path.isabs(raw)
        or ntpath.isabs(raw)
        or os.path.splitdrive(raw)[0]
        or ntpath.splitdrive(raw)[0]
    ):
        return "", "projection path is not a relative descendant"
    pieces = raw.replace("\\", "/").split("/")
    if any(piece in ("", ".", "..") for piece in pieces):
        return "", "projection path contains traversal or ambiguity"
    path = os.path.abspath(os.path.join(root, *pieces))
    try:
        if os.path.commonpath((root, path)) != root:
            return "", "projection path escapes root"
    except ValueError:
        return "", "projection path escapes root"
    current = root
    for piece in pieces:
        current = os.path.join(current, piece)
        if not os.path.lexists(current):
            return path, ""
        try:
            info = os.lstat(current)
        except OSError:
            return "", "projection path is unreadable"
        if stat.S_ISLNK(info.st_mode) or _is_reparse(info):
            return "", "projection path contains link or reparse component"
    return path, ""


def _front_matter(text):
    """Return one strict, duplicate-free fenced header and its body."""
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        return {}, "", "missing exact opening fence"
    fields = {}
    for index in range(1, len(lines)):
        line = lines[index]
        if line == "---":
            return fields, "\n".join(lines[index + 1 :]), ""
        key, separator, value = line.partition(":")
        key = key.strip().lower()
        if not separator or not _KEY.fullmatch(key) or not value.strip():
            return {}, "", "malformed header line"
        if key in fields:
            return {}, "", "duplicate header"
        fields[key] = value.strip()
    return {}, "", "missing exact closing fence"


def _leading_declaration(text):
    """Parse exactly one duplicate-free flat declaration ending at a blank line."""
    fields = {}
    for raw in text.splitlines():
        if raw == "":
            if not fields:
                return {}, "empty inner declaration"
            return fields, ""
        key, separator, value = raw.partition(":")
        key = key.strip().lower()
        if not separator or not _KEY.fullmatch(key) or not value.strip():
            return {}, "malformed inner declaration"
        if key in fields:
            return {}, "duplicate inner header"
        fields[key] = value.strip()
    return {}, "missing inner declaration terminator"


def _valid_utc_timestamp(value):
    if not _UTC_TS.fullmatch(value or ""):
        return False
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return False
    return True


def _valid_source_timestamp(value):
    if not _SOURCE_TS.fullmatch(value or ""):
        return False
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ")
    except ValueError:
        return False
    return True


def measure_slack_projection(
    root,
    relative_path,
    *,
    post_id,
    carrier_ts,
    sender,
    inner_kind,
    expected_sha256,
    channel=DEFAULT_SLACK_CHANNEL,
):
    """Measure exact trusted bytes at one canonical on-disk projection path."""
    path, path_error = _projection_path(root, relative_path)
    if path_error:
        return _unverified(path_error)
    if not os.path.lexists(path):
        return {
            "present": False,
            "state": CARRIER_ONLY,
            "provenance_ok": False,
            "mismatches": [],
        }
    try:
        before = os.lstat(path)
        if (
            not stat.S_ISREG(before.st_mode)
            or stat.S_ISLNK(before.st_mode)
            or _is_reparse(before)
        ):
            return _unverified("projection is not a regular non-reparse file")
        if before.st_size > MAX_PROJECTION_BYTES:
            return _unverified("projection exceeds size limit")
        with open(path, "rb") as handle:
            opened = os.fstat(handle.fileno())
            data = handle.read(MAX_PROJECTION_BYTES + 1)
            after = os.fstat(handle.fileno())
    except OSError:
        return _unverified("projection is unreadable")

    def identity(info):
        return (
            info.st_dev,
            info.st_ino,
            info.st_size,
            getattr(info, "st_mtime_ns", int(info.st_mtime * 1_000_000_000)),
        )

    if (
        not stat.S_ISREG(opened.st_mode)
        or _is_reparse(opened)
        or identity(before) != identity(opened)
        or identity(opened) != identity(after)
    ):
        return _unverified("projection identity changed during read")
    if len(data) > MAX_PROJECTION_BYTES:
        return _unverified("projection exceeds size limit")
    if not re.fullmatch(r"[0-9a-f]{64}", str(expected_sha256 or "")):
        return _unverified("expected content identity is invalid")
    if hashlib.sha256(data).hexdigest() != expected_sha256:
        return _unverified("projection content identity mismatch")
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeError:
        return _unverified("projection is not strict UTF-8")

    outer, body, outer_error = _front_matter(text)
    inner, inner_error = _leading_declaration(body)
    expected_outer = {
        "from": sender,
        "to": "TABLE",
        "id": post_id,
        "carrier": "slack-connector",
        "observed_event": "slack:%s:%s:1" % (channel, carrier_ts),
        "carrier_ts": carrier_ts,
        "state": "DURABLE_PAGE",
        "kind": "slack_message",
    }
    expected_inner = {"from": sender, "id": post_id, "kind": inner_kind}
    mismatches = []
    if not _CARRIER_TS.fullmatch(str(carrier_ts or "")):
        mismatches.append("input carrier_ts")
    if outer_error:
        mismatches.append("outer " + outer_error)
    else:
        if set(outer) - _OUTER_KEYS:
            mismatches.append("outer unexpected header")
        if _OUTER_REQUIRED - set(outer):
            mismatches.append("outer missing required header")
        for key, expected in expected_outer.items():
            if outer.get(key) != expected:
                mismatches.append("outer " + key)
        if not _valid_utc_timestamp(outer.get("durable_ts", "")):
            mismatches.append("outer durable_ts")
        if not _valid_source_timestamp(outer.get("ts", "")):
            mismatches.append("outer ts")
    if inner_error:
        mismatches.append("inner " + inner_error)
    else:
        if set(inner) - _INNER_KEYS:
            mismatches.append("inner unexpected header")
        if _INNER_REQUIRED - set(inner):
            mismatches.append("inner missing required header")
        for key, expected in expected_inner.items():
            if inner.get(key) != expected:
                mismatches.append("inner " + key)
    ok = not mismatches
    return {
        "present": True,
        "state": DURABLE_ON_MAIN if ok else UNVERIFIED_PRESENT,
        "provenance_ok": ok,
        "mismatches": mismatches,
    }
