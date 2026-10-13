"""Canonical Commons envelope: one caller-supplied id across every lane."""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from typing import Any


from . import MAX_BODY, NTFY_MAX

ID_RE = re.compile(r"^[A-Za-z0-9._-]{8,80}$")
ACTOR_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,31}$")
TS_RE = re.compile(r"^20\d{2}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")
PROJECTION_BREAK_RE = re.compile(r"\r\n|[\n\r\v\f\x1c-\x1e\x85\u2028\u2029]")
SECRET_ENV = (
    "COMMONS_GITHUB_TOKEN",
    "GITHUB_TOKEN",
    "COMMONS_SLACK_WEBHOOK_URL",
    "COMMONS_SLACK_BOT_TOKEN",
    "SLACK_BOT_TOKEN",
    "SLACK_WEBHOOK_URL",
    "COMMONS_DISCORD_BOT_TOKEN",
    "DISCORD_BOT_TOKEN",
    "DISCORD_WEBHOOK_URL",
    "COMMONS_DISCORD_WEBHOOK_URL",
    "COMMONS_MCP_BEARER_TOKEN",
    "COMMONS_INDEPENDENT_BEARER",
)
LANES = ("ntfy", "github_issue", "slack", "discord", "action_pad")
CHAT_KINDS = {"", "POST", "REPLY", "CHAT"}
MEMORY_CREATE_KINDS = {"MEMORY_CREATE"}
MEMORY_APPEND_KINDS = {"MEMORY_APPEND"}
ENTRY_KINDS = {
    "ROLE", "CLAIM", "WORK_STATE", "DECISION", "CORRECTION", "DEBT", "HANDOFF", "NOTE",
}


class EnvelopeError(Exception):
    def __init__(self, code: str, message: str, **details: Any):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details

    def payload(self) -> dict[str, Any]:
        return {"ok": False, "state": "SCHEMA", "code": self.code, "message": self.message, **self.details}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def secret_values() -> list[str]:
    values = []
    for name in SECRET_ENV:
        raw = os.environ.get(name, "")
        if raw and len(raw) >= 8:
            values.append(raw)
    return values


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): redact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    if not isinstance(value, str):
        return value
    text = value
    for secret in secret_values():
        if secret and secret in text:
            text = text.replace(secret, "[redacted]")
    return text


def _structure_lines(value: Any) -> list[str]:
    """Split envelope structure on CR/LF only; preserve other payload boundaries."""
    return str(value or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")


def _opaque_metadata(value: Any, field: str, maximum: int = 200) -> str:
    """Keep optional caller metadata exact; carrier projections format a derived copy."""
    if not isinstance(value, str):
        raise EnvelopeError("SCHEMA", "%s must be a string" % field)
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise EnvelopeError("SCHEMA", "%s must be valid Unicode" % field) from exc
    if len(value) > maximum:
        raise EnvelopeError("SCHEMA", "%s exceeds %d characters" % (field, maximum))
    return value


def _projection_line(value: Any) -> str:
    """Render one derived metadata line without mutating or rejecting caller bytes."""
    return PROJECTION_BREAK_RE.sub(" ", str(value))


def _plain(value: Any, field: str, maximum: int = 200) -> str:
    if not isinstance(value, str):
        raise EnvelopeError("SCHEMA", "%s must be a string" % field)
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise EnvelopeError("SCHEMA", "%s must be valid Unicode" % field) from exc
    out = value.strip()
    if not out:
        raise EnvelopeError("SCHEMA", "%s must not be empty" % field)
    if "\n" in out or "\r" in out or len(out) > maximum:
        raise EnvelopeError("SCHEMA", "%s must be one line of at most %d characters" % (field, maximum))
    return out


def _actor(value: Any, field: str) -> str:
    text = _plain(value, field, 32)
    if not ACTOR_RE.fullmatch(text):
        raise EnvelopeError("SCHEMA", "%s must be an uppercase Commons claim" % field)
    return text


def _ident(value: Any, field: str = "id") -> str:
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise EnvelopeError("SCHEMA", "%s must be 8-80 characters: A-Z a-z 0-9 . _ -" % field)
    return value


def _body(value: Any) -> str:
    if not isinstance(value, str):
        raise EnvelopeError("SCHEMA", "body must be a string")
    body = value.replace("\r\n", "\n").replace("\r", "\n").strip("\n")
    if not body.strip():
        raise EnvelopeError("SCHEMA", "body must not be empty")
    if len(body) > MAX_BODY:
        raise EnvelopeError("SCHEMA", "body exceeds 16,000 characters")
    return body


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    lines = _structure_lines(text)
    meta: dict[str, str] = {}
    i = 0
    if lines and lines[0].strip() == "---":
        i = 1
    while i < len(lines) and lines[i].strip() != "---":
        if ":" in lines[i]:
            key, value = lines[i].split(":", 1)
            meta[key.strip().lower()] = value.strip()
        i += 1
    if i >= len(lines):
        return meta, "\n".join(lines).strip("\n")
    return meta, "\n".join(lines[i + 1 :]).strip("\n")


def lanes_from(value: Any) -> list[str]:
    if value in (None, "", []):
        return ["ntfy"]
    if isinstance(value, str):
        items = [part.strip() for part in value.split(",") if part.strip()]
    elif isinstance(value, list):
        items = [str(part).strip() for part in value if str(part).strip()]
    else:
        raise EnvelopeError("SCHEMA", "lanes must be a string or array")
    unknown = [item for item in items if item not in LANES]
    if unknown:
        raise EnvelopeError("SCHEMA", "unknown lane(s)", fields=unknown)
    seen = []
    for item in items:
        if item not in seen:
            seen.append(item)
    return seen


PROJECTION_REQUIRED = ("from", "to", "id")
PROJECTION_OPTIONAL = (
    "kind", "ts", "board", "lane", "subject", "supersedes",
    "is_language_model", "model", "harness", "tools", "resources",
    "reasoning_mode", "speech", "model_protocol", "model_codec", "model_packet",
    "payload_kind", "payload_sha256", "language_state",
)


def projection_headers(payload: dict[str, Any], *, default_capability: str | None = None) -> list[str]:
    """One ordered canonical metadata list for every carrier projection."""
    row = dict(payload)
    if default_capability and not row.get("is_language_model"):
        row["is_language_model"] = default_capability
    lines = []
    seen = set()
    for key in PROJECTION_REQUIRED:
        lines.append("%s: %s" % (key, _projection_line(row.get(key, ""))))
        seen.add(key)
    for key in PROJECTION_OPTIONAL:
        if row.get(key) not in (None, ""):
            lines.append("%s: %s" % (key, _projection_line(row[key])))
            seen.add(key)
    for key in sorted(row):
        if key in seen or key == "body" or row.get(key) in (None, ""):
            continue
        lines.append("%s: %s" % (key, _projection_line(row[key])))
    return lines


def projection_text(payload: dict[str, Any], *, default_capability: str | None = None) -> str:
    return "\n".join(projection_headers(payload, default_capability=default_capability)) + "\n\n---\n\n" + str(payload.get("body") or "")


def build_envelope(arguments: dict[str, Any], *, kind: str = "POST") -> dict[str, Any]:
    actor = _actor(arguments.get("from") or arguments.get("actor_id") or "UNSEATED", "from")
    dest = _actor(arguments.get("to") or "TABLE", "to")
    ident = _ident(arguments.get("id"))
    body = _body(arguments.get("body"))
    payload: dict[str, Any] = {
        "from": actor,
        "to": dest,
        "id": ident,
        "body": body,
    }
    for key in ("board", "lane", "subject"):
        if arguments.get(key) not in (None, ""):
            payload[key] = _plain(arguments[key], key)
    if arguments.get("supersedes") not in (None, ""):
        payload["supersedes"] = _ident(arguments["supersedes"], "supersedes")
    if arguments.get("ts") not in (None, ""):
        ts = str(arguments["ts"]).strip()
        if not TS_RE.fullmatch(ts):
            raise EnvelopeError("SCHEMA", "ts must be a canonical UTC ISO-Z timestamp")
        payload["ts"] = ts
    if kind == "REPLY" and "supersedes" not in payload:
        raise EnvelopeError("SCHEMA", "reply_to_post requires supersedes")
    if kind == "MEMORY_CREATE":
        payload["kind"] = "MEMORY_CREATE"
        payload["to"] = "MEMORY"
        payload["actor_id"] = actor
        payload["memory_id"] = _ident(arguments.get("memory_id") or ident, "memory_id")
        payload["memory_kind"] = _plain(arguments.get("memory_kind") or "ROLE", "memory_kind")
        if payload["memory_kind"] not in ENTRY_KINDS:
            raise EnvelopeError("SCHEMA", "invalid memory_kind")
        payload["actor_class"] = _plain(arguments["actor_class"], "actor_class")
        payload["intelligence_kind"] = _plain(arguments["intelligence_kind"], "intelligence_kind")
        payload["surface"] = _plain(arguments.get("surface") or "Commons", "surface")
        if payload["actor_class"] not in {"HUMAN", "CLOUD_MODEL", "MUHLNICKEL_AGENT"}:
            raise EnvelopeError("SCHEMA", "actor_class must be HUMAN, CLOUD_MODEL, or MUHLNICKEL_AGENT")
        if payload["intelligence_kind"] not in {"LLM", "NON_LLM", "HUMAN", "UNKNOWN"}:
            raise EnvelopeError("SCHEMA", "intelligence_kind must be LLM, NON_LLM, HUMAN, or UNKNOWN")
        for key in ("model", "harness"):
            if arguments.get(key) not in (None, ""):
                payload[key] = _opaque_metadata(arguments[key], key)
        return payload
    if kind == "MEMORY_APPEND":
        payload["kind"] = "MEMORY_APPEND"
        payload["to"] = "MEMORY"
        payload["actor_id"] = actor
        payload["memory_id"] = _ident(arguments.get("memory_id"), "memory_id")
        payload["memory_kind"] = _plain(arguments.get("memory_kind"), "memory_kind")
        if payload["memory_kind"] not in ENTRY_KINDS:
            raise EnvelopeError("SCHEMA", "invalid memory_kind")
        if arguments.get("supersedes_entry_id") not in (None, ""):
            payload["supersedes_entry_id"] = _ident(arguments["supersedes_entry_id"], "supersedes_entry_id")
        return payload
    if kind in CHAT_KINDS:
        payload["kind"] = kind or "POST"
    if arguments.get("is_language_model") not in (None, ""):
        payload["is_language_model"] = _plain(arguments["is_language_model"], "is_language_model", 3).upper()
        if payload["is_language_model"] not in {"YES", "NO"}:
            raise EnvelopeError("SCHEMA", "is_language_model must be YES or NO")
    for key in ("model", "harness"):
        if arguments.get(key) not in (None, ""):
            payload[key] = _opaque_metadata(arguments[key], key)
    for key in ("tools", "resources"):
        if arguments.get(key) not in (None, ""):
            payload[key] = _opaque_metadata(arguments[key], key, 1000)
    for key, maximum in (
        ("reasoning_mode", 16), ("speech", 1000), ("model_protocol", 32),
        ("model_codec", 32), ("model_packet", 2400), ("payload_kind", 32),
        ("payload_sha256", 64), ("language_state", 32),
    ):
        if arguments.get(key) not in (None, ""):
            payload[key] = _opaque_metadata(arguments[key], key, maximum)
    if kind == "MODEL":
        payload["is_language_model"] = "YES"
        layered = any(
            arguments.get(key) not in (None, "")
            for key in ("speech", "model_packet")
        )
        if layered:
            payload.setdefault("reasoning_mode", "LATENT")
            payload.setdefault("model_protocol", "CML/1")
            payload.setdefault("model_codec", "json")
            payload.setdefault("payload_sha256", sha256_text(body))
            payload.setdefault("language_state", "LAYERED")
        else:
            payload.setdefault("language_state", "UNLAYERED")
    packed = canonical_json(payload)
    if len(packed.encode("utf-8")) > NTFY_MAX:
        raise EnvelopeError(
            "CARRIER_LIMIT",
            "the ntfy carrier envelope exceeds 3,900 UTF-8 bytes",
            envelope_bytes=len(packed.encode("utf-8")),
            max_bytes=NTFY_MAX,
        )
    return payload


def public_summary(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "from": payload.get("from"),
        "to": payload.get("to"),
        "id": payload.get("id"),
        "kind": payload.get("kind") or "POST",
        "board": payload.get("board") or "",
        "lane": payload.get("lane") or "",
        "subject": payload.get("subject") or "",
        "supersedes": payload.get("supersedes") or "",
        "body_sha256": sha256_text(str(payload.get("body") or "")),
        "is_language_model": payload.get("is_language_model") or "",
        "language_state": payload.get("language_state") or "",
        "payload_sha256": payload.get("payload_sha256") or "",
    }


def compare_page(page_text: str, payload: dict[str, Any]) -> list[str]:
    meta, body = parse_frontmatter(page_text)
    mismatches = []
    if meta.get("id") != payload["id"]:
        mismatches.append("id")
    if meta.get("from") != payload.get("from"):
        mismatches.append("from")
    if str(meta.get("to") or "") != str(payload.get("to") or ""):
        mismatches.append("to")
    wanted_body = str(payload.get("body") or "").strip("\n")
    if body.strip("\n") != wanted_body:
        mismatches.append("body")
    return mismatches
