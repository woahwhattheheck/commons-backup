#!/usr/bin/env python3
"""Evidence-bound work terminality compiler.

This module is intentionally offline. It classifies retained provider observations and
owner-heartbeat evidence; it does not mutate GitHub, Slack, Muse, or any provider.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

SCHEMA = "commons.swarm-terminality-snapshot/v1"
REPORT_SCHEMA = "commons.swarm-terminality-report/v1"
RECEIPT_SCHEMA = "commons.swarm-terminality-receipt/v1"
COMPILER = "swarm-terminality-registry/1.0.0"
CLASSIFICATIONS = {
    "TERMINAL_MERGED",
    "TERMINAL_CLOSED",
    "SUPERSEDED",
    "ACTIVE_CUSTODY",
    "RECOVERY_ELIGIBLE",
    "HOLD_INCOMPLETE_EVIDENCE",
}
NEXT_ACTIONS = {"NONE", "CLOSE_STALE_CARRIER", "REVIEW_SUCCESSOR", "RECOVER", "REFRESH_EVIDENCE"}
AUTHORITY_CEILING = {k: False for k in (
    "github_merge_authorized",
    "github_close_authorized",
    "github_ref_mutation_authorized",
    "slack_ownership_granted",
    "muse_outbound_authorized",
    "external_send_authorized",
    "provider_mutation_authorized",
    "spend_authorized",
    "payment_authorized",
    "cash_proven",
    "revenue_recognition_authorized",
)}
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/#-]{0,191}$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
HEX40_RE = re.compile(r"^[0-9a-f]{40}$")
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")

class RegistryError(ValueError):
    pass

@dataclass(frozen=True)
class CompiledBundle:
    report_json: str
    report_markdown: str
    receipt_json: str


def _pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise RegistryError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def _constant(value):
    raise RegistryError(f"non-finite JSON number: {value}")


def load_strict_json(text: str) -> Any:
    try:
        value = json.loads(text, object_pairs_hook=_pairs, parse_constant=_constant)
    except RegistryError:
        raise
    except json.JSONDecodeError as exc:
        raise RegistryError(f"invalid JSON: {exc.msg}") from exc

    def walk(v):
        if type(v) is float and not math.isfinite(v):
            raise RegistryError("non-finite JSON number")
        if type(v) is dict:
            for x in v.values():
                walk(x)
        elif type(v) is list:
            for x in v:
                walk(x)
    walk(value)
    return value


def _obj(value, label: str, fields: set[str]):
    if type(value) is not dict:
        raise RegistryError(f"{label} must be an object")
    unknown = set(value) - fields
    missing = fields - set(value)
    if unknown:
        raise RegistryError(f"{label} has unknown fields: {sorted(unknown)!r}")
    if missing:
        raise RegistryError(f"{label} missing fields: {sorted(missing)!r}")
    return value


def _arr(value, label):
    if type(value) is not list:
        raise RegistryError(f"{label} must be an array")
    return value


def _text(value, label, maximum=2048, allow_empty=False):
    if type(value) is not str:
        raise RegistryError(f"{label} must be a string")
    if value != value.strip() or (not value and not allow_empty):
        raise RegistryError(f"{label} must be trim-stable and nonempty")
    if len(value) > maximum:
        raise RegistryError(f"{label} exceeds maximum length")
    if any(ord(ch) < 32 and ch not in "\t\n" for ch in value):
        raise RegistryError(f"{label} contains control characters")
    return value


def _id(value, label):
    text = _text(value, label, 192)
    if not ID_RE.fullmatch(text):
        raise RegistryError(f"{label} has invalid identifier syntax")
    return text


def _enum(value, label, allowed):
    text = _text(value, label, 64)
    if text not in allowed:
        raise RegistryError(f"{label} must be one of {sorted(allowed)!r}")
    return text


def _positive_int(value, label, maximum=31_536_000):
    if type(value) is not int or value <= 0 or value > maximum:
        raise RegistryError(f"{label} must be a positive bounded integer (bool rejected)")
    return value


def _timestamp(value, label):
    text = _text(value, label, 64)
    parsed = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        dt = datetime.fromisoformat(parsed)
    except ValueError as exc:
        raise RegistryError(f"{label} must be ISO-8601") from exc
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise RegistryError(f"{label} must include timezone")
    return dt.astimezone(timezone.utc)


def _https(value, label):
    text = _text(value, label, 2048)
    parsed = urlparse(text)
    if parsed.scheme != "https" or not parsed.hostname or "@" in parsed.netloc:
        raise RegistryError(f"{label} must be an https URL without userinfo")
    if any(token in text for token in ("\\", "\x00", "../", "/..")):
        raise RegistryError(f"{label} contains unsafe path material")
    return text


def _sha256(value, label):
    text = _text(value, label, 64)
    if not SHA_RE.fullmatch(text):
        raise RegistryError(f"{label} must be lowercase SHA-256")
    return text


def _git_sha(value, label):
    if value is None:
        return None
    text = _text(value, label, 64)
    if not (HEX40_RE.fullmatch(text) or HEX64_RE.fullmatch(text)):
        raise RegistryError(f"{label} must be a 40/64 lowercase hex Git object id or null")
    return text


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"


def _digest(text: str):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _index(rows, label):
    out = {}
    for row in rows:
        if row["id"] in out:
            raise RegistryError(f"duplicate {label} id: {row['id']}")
        out[row["id"]] = row
    return out


