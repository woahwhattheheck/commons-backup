"""Normalize raw RFC delivery-status notifications into route-lifecycle events.

This module is side-effect free except for the optional CLI output file. It does
not send email and does not authorize a send.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from email import policy
from email.message import Message
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

SCHEMA = "outbound-dsn-binding/v1"
RECEIPT_SCHEMA = "outbound-dsn-normalizer-receipt/v1"
MAX_RAW_BYTES = 10 * 1024 * 1024
_MAX_PARTS = 128
_EMAIL_RE = re.compile(r"^[^\s@<>(),;:]+@[^\s@<>(),;:]+$")
_STATUS_RE = re.compile(r"^[45]\.[0-9]{1,3}\.[0-9]{1,3}$")
_SMTP_RE = re.compile(r"(?<![0-9])([45][0-9]{2})(?![0-9])")
_MSGID_RE = re.compile(r"^<[^<>\r\n]{1,998}>$")
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")


class DsnError(ValueError):
    """Malformed, ambiguous, or insufficient DSN evidence."""


def canonical_bytes(value: Any) -> bytes:
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            + "\n"
        ).encode("ascii")
    except (TypeError, ValueError) as exc:
        raise DsnError("value is not canonical-JSON serializable") from exc


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_json(value: Any) -> str:
    return sha256_bytes(canonical_bytes(value))


def _exact(obj: Mapping[str, Any], expected: set[str], label: str) -> None:
    if not isinstance(obj, Mapping):
        raise DsnError(f"{label}: must be an object")
    missing = expected - set(obj)
    extra = set(obj) - expected
    if missing:
        raise DsnError(f"{label}: missing fields {sorted(missing)}")
    if extra:
        raise DsnError(f"{label}: unexpected fields {sorted(extra)}")


def _text(value: Any, label: str, max_len: int = 512) -> str:
    if not isinstance(value, str):
        raise DsnError(f"{label}: must be string")
    if not value or len(value) > max_len:
        raise DsnError(f"{label}: invalid length")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise DsnError(f"{label}: control characters forbidden")
    return value


def _email(value: Any, label: str) -> str:
    text = _text(value, label, 320)
    if text.count("@") != 1 or _EMAIL_RE.fullmatch(text) is None:
        raise DsnError(f"{label}: expected one plain email address")
    local, domain = text.rsplit("@", 1)
    if not local or not domain or domain.startswith(".") or domain.endswith(".") or ".." in domain:
        raise DsnError(f"{label}: malformed email address")
    return f"{local}@{domain}".casefold()


def _msgid(value: Any, label: str) -> str:
    text = _text(value, label, 1000)
    if _MSGID_RE.fullmatch(text) is None:
        raise DsnError(f"{label}: expected RFC Message-ID in angle brackets")
    return text


def _iso(value: Any, label: str) -> tuple[str, datetime]:
    text = _text(value, label, 64)
    raw = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise DsnError(f"{label}: invalid ISO-8601") from exc
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise DsnError(f"{label}: timezone required")
    dt = dt.astimezone(timezone.utc)
    return dt.isoformat(timespec="microseconds" if dt.microsecond else "seconds").replace("+00:00", "Z"), dt


@dataclass(frozen=True)
class Binding:
    source_id: str
    provider_message_id: str
    original_rfc822_message_id: str
    recipient: str
    sent_at_text: str
    sent_at: datetime
    captured_at_text: str
    captured_at: datetime

    @classmethod
    def parse(cls, raw: Mapping[str, Any]) -> "Binding":
        _exact(
            raw,
            {
                "schema_version",
                "source_id",
                "provider_message_id",
                "original_rfc822_message_id",
                "recipient",
                "sent_at",
                "captured_at",
            },
            "binding",
        )
        if raw["schema_version"] != SCHEMA:
            raise DsnError(f"binding.schema_version must equal {SCHEMA!r}")
        source_id = _text(raw["source_id"], "binding.source_id", 256)
        provider_message_id = _text(raw["provider_message_id"], "binding.provider_message_id", 256)
        original = _msgid(raw["original_rfc822_message_id"], "binding.original_rfc822_message_id")
        recipient = _email(raw["recipient"], "binding.recipient")
        sent_text, sent = _iso(raw["sent_at"], "binding.sent_at")
        captured_text, captured = _iso(raw["captured_at"], "binding.captured_at")
        if captured < sent:
            raise DsnError("binding.captured_at precedes sent_at")
        return cls(source_id, provider_message_id, original, recipient, sent_text, sent, captured_text, captured)


def _plain_header(msg: Message, name: str, *, max_len: int = 2000) -> str | None:
    values = msg.get_all(name, [])
    if not values:
        return None
    if len(values) != 1:
        raise DsnError(f"{name}: duplicate header is ambiguous")
    value = str(values[0]).strip()
    if not value or len(value) > max_len or any(ch in value for ch in "\r\n"):
        raise DsnError(f"{name}: malformed header")
    return value


def _recipient_field(value: str, label: str) -> str:
    if ";" not in value:
        raise DsnError(f"{label}: expected address-type; address")
    kind, address = value.split(";", 1)
    if kind.strip().casefold() != "rfc822":
        raise DsnError(f"{label}: only rfc822 recipients are supported")
    return _email(address.strip(), label)


def _parse_outer_date(msg: Message, binding: Binding) -> str:
    date = _plain_header(msg, "Date", max_len=200)
    if date is None:
        raise DsnError("Date: DSN outer message date required")
    try:
        dt = parsedate_to_datetime(date)
    except (TypeError, ValueError) as exc:
        raise DsnError("Date: invalid RFC5322 date") from exc
    if dt is None or dt.tzinfo is None or dt.utcoffset() is None:
        raise DsnError("Date: timezone required")
    dt = dt.astimezone(timezone.utc)
    if dt < binding.sent_at:
        raise DsnError("Date: DSN predates original send")
    if dt > binding.captured_at:
        raise DsnError("Date: DSN is after capture boundary")
    return dt.isoformat(timespec="microseconds" if dt.microsecond else "seconds").replace("+00:00", "Z")


def _message_id_bindings(msg: Message, per_message: Message, expected: str) -> tuple[str, ...]:
    evidence: list[tuple[str, str]] = []
    x_original = _plain_header(per_message, "X-Original-Message-ID", max_len=1000)
    if x_original is not None:
        evidence.append(("X-Original-Message-ID", _msgid(x_original, "X-Original-Message-ID")))
    in_reply = _plain_header(msg, "In-Reply-To", max_len=1000)
    if in_reply is not None:
        evidence.append(("In-Reply-To", _msgid(in_reply, "In-Reply-To")))
    if not evidence:
        raise DsnError("DSN has no supported original-message binding")
    wrong = [source for source, value in evidence if value != expected]
    if wrong:
        raise DsnError(f"original-message binding mismatch in {', '.join(wrong)}")
    return tuple(source for source, _ in evidence)


def _delivery_status_blocks(part: Message) -> list[Message]:
    payload = part.get_payload()
    if not isinstance(payload, list) or not payload:
        raise DsnError("message/delivery-status payload is missing blocks")
    blocks: list[Message] = []
    for item in payload:
        if not isinstance(item, Message):
            raise DsnError("message/delivery-status contains non-message block")
        blocks.append(item)
    return blocks


def _smtp_code(diagnostic: str | None, status: str) -> int:
    if diagnostic is None:
        raise DsnError("Diagnostic-Code: required to bind SMTP failure code")
    if ";" not in diagnostic:
        raise DsnError("Diagnostic-Code: expected diagnostic-type; value")
    kind, detail = diagnostic.split(";", 1)
    if kind.strip().casefold() != "smtp":
        raise DsnError("Diagnostic-Code: only smtp diagnostics are supported")
    matches = [int(value) for value in _SMTP_RE.findall(detail)]
    if not matches:
        raise DsnError("Diagnostic-Code: no 4xx/5xx SMTP code found")
    unique = sorted(set(matches))
    if len(unique) != 1:
        raise DsnError("Diagnostic-Code: multiple SMTP failure codes are ambiguous")
    code = unique[0]
    if code // 100 != int(status[0]):
        raise DsnError("Diagnostic-Code and Status classes disagree")
    return code


def normalize(raw_mime: bytes, binding_raw: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize one raw RFC DSN into one route-lifecycle `dsn` event + receipt."""
    if not isinstance(raw_mime, (bytes, bytearray)):
        raise DsnError("raw_mime must be bytes")
    raw_mime = bytes(raw_mime)
    if not raw_mime or len(raw_mime) > MAX_RAW_BYTES:
        raise DsnError(f"raw_mime must be 1..{MAX_RAW_BYTES} bytes")

    binding = Binding.parse(binding_raw)
    try:
        msg = BytesParser(policy=policy.default).parsebytes(raw_mime)
    except Exception as exc:
        raise DsnError("raw_mime could not be parsed") from exc
    if msg.defects:
        raise DsnError("raw_mime has parser defects")
    if msg.get_content_type().casefold() != "multipart/report":
        raise DsnError("outer MIME must be multipart/report")
    report_type = msg.get_param("report-type", header="content-type")
    if not isinstance(report_type, str) or report_type.casefold() != "delivery-status":
        raise DsnError("multipart/report must declare report-type=delivery-status")

    parts = list(msg.walk())
    if len(parts) > _MAX_PARTS:
        raise DsnError(f"raw_mime exceeds {_MAX_PARTS} MIME parts")
    delivery_parts = [part for part in parts if part.get_content_type().casefold() == "message/delivery-status"]
    if len(delivery_parts) != 1:
        raise DsnError("raw_mime must contain exactly one message/delivery-status part")
    blocks = _delivery_status_blocks(delivery_parts[0])
    per_message = blocks[0]
    if _plain_header(per_message, "Final-Recipient") is not None:
        raise DsnError("per-message delivery-status block unexpectedly has Final-Recipient")
    binding_sources = _message_id_bindings(msg, per_message, binding.original_rfc822_message_id)

    recipient_blocks = blocks[1:]
    if not recipient_blocks:
        raise DsnError("delivery-status has no per-recipient blocks")
    matches: list[Message] = []
    for index, block in enumerate(recipient_blocks):
        final = _plain_header(block, "Final-Recipient", max_len=500)
        if final is None:
            raise DsnError(f"recipient block {index}: Final-Recipient required")
        parsed = _recipient_field(final, f"recipient block {index} Final-Recipient")
        if parsed == binding.recipient:
            matches.append(block)
    if len(matches) != 1:
        raise DsnError(
            f"expected recipient must match exactly one delivery-status block; matched {len(matches)}"
        )
    block = matches[0]
    action = _plain_header(block, "Action", max_len=64)
    if action is None or action.casefold() not in {"failed", "delayed"}:
        raise DsnError("Action: only failed or delayed DSNs normalize to failure events")
    status = _plain_header(block, "Status", max_len=32)
    if status is None or _STATUS_RE.fullmatch(status) is None:
        raise DsnError("Status: expected enhanced failure status such as 5.1.1")
    if action.casefold() == "failed" and not status.startswith("5."):
        raise DsnError("Action failed must carry 5.x.x Status")
    if action.casefold() == "delayed" and not status.startswith("4."):
        raise DsnError("Action delayed must carry 4.x.x Status")
    diagnostic = _plain_header(block, "Diagnostic-Code", max_len=4000)
    smtp_code = _smtp_code(diagnostic, status)
    observed_at = _parse_outer_date(msg, binding)

    raw_sha = sha256_bytes(raw_mime)
    event_identity = {
        "source_id": binding.source_id,
        "provider_message_id": binding.provider_message_id,
        "recipient": binding.recipient,
        "original_rfc822_message_id": binding.original_rfc822_message_id,
        "smtp_code": smtp_code,
        "enhanced_status": status,
        "observed_at": observed_at,
        "source_sha256": raw_sha,
    }
    event = {
        "event_id": "dsn-" + sha256_json(event_identity)[:40],
        "kind": "dsn",
        "provider_message_id": binding.provider_message_id,
        "recipient": binding.recipient,
        "observed_at": observed_at,
        "source_id": binding.source_id,
        "source_sha256": raw_sha,
        "smtp_code": smtp_code,
        "enhanced_status": status,
    }
    receipt: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA,
        "binding_sha256": sha256_json(dict(binding_raw)),
        "source_sha256": raw_sha,
        "source_id": binding.source_id,
        "original_rfc822_message_id": binding.original_rfc822_message_id,
        "original_message_binding_sources": list(binding_sources),
        "recipient_block_count": len(recipient_blocks),
        "matched_recipient_block_count": 1,
        "event": event,
        "event_sha256": sha256_json(event),
        "side_effects_authorized": False,
    }
    material = dict(receipt)
    receipt["receipt_sha256"] = sha256_json(material)
    return receipt


def verify_receipt(raw: Mapping[str, Any]) -> bool:
    expected = {
        "schema_version",
        "binding_sha256",
        "source_sha256",
        "source_id",
        "original_rfc822_message_id",
        "original_message_binding_sources",
        "recipient_block_count",
        "matched_recipient_block_count",
        "event",
        "event_sha256",
        "side_effects_authorized",
        "receipt_sha256",
    }
    _exact(raw, expected, "receipt")
    if raw["schema_version"] != RECEIPT_SCHEMA:
        raise DsnError("receipt: unsupported schema")
    for field in ("binding_sha256", "source_sha256", "event_sha256", "receipt_sha256"):
        value = raw[field]
        if not isinstance(value, str) or _HEX64_RE.fullmatch(value) is None:
            raise DsnError(f"receipt.{field}: lowercase SHA-256 required")
    _text(raw["source_id"], "receipt.source_id", 256)
    _msgid(raw["original_rfc822_message_id"], "receipt.original_rfc822_message_id")
    sources = raw["original_message_binding_sources"]
    if not isinstance(sources, list) or not sources or any(
        item not in {"X-Original-Message-ID", "In-Reply-To"} for item in sources
    ):
        raise DsnError("receipt.original_message_binding_sources invalid")
    if type(raw["recipient_block_count"]) is not int or raw["recipient_block_count"] < 1:
        raise DsnError("receipt.recipient_block_count invalid")
    if raw["matched_recipient_block_count"] != 1:
        raise DsnError("receipt must bind exactly one recipient block")
    if raw["side_effects_authorized"] is not False:
        raise DsnError("receipt may never authorize side effects")
    event = raw["event"]
    if not isinstance(event, Mapping):
        raise DsnError("receipt.event must be object")
    if sha256_json(event) != raw["event_sha256"]:
        raise DsnError("receipt.event digest mismatch")
    material = dict(raw)
    digest = material.pop("receipt_sha256")
    if sha256_json(material) != digest:
        raise DsnError("receipt digest mismatch")
    return True


def _atomic_write(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    tmp_path = Path(tmp)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(raw)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, path)
        if os.name != "nt":
            flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
            dfd = os.open(path.parent, flags)
            try:
                os.fsync(dfd)
            finally:
                os.close(dfd)
    finally:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Normalize one raw RFC DSN")
    parser.add_argument("--raw-mime", required=True, type=Path)
    parser.add_argument("--binding", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        raw_mime = args.raw_mime.read_bytes()
        binding = json.loads(args.binding.read_text(encoding="utf-8"))
        if not isinstance(binding, dict):
            raise DsnError("binding root must be object")
        receipt = normalize(raw_mime, binding)
        _atomic_write(args.out, canonical_bytes(receipt))
    except (OSError, json.JSONDecodeError, DsnError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
