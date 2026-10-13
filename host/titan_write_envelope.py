#!/usr/bin/env python3
"""Compile bounded Titan write intentions without touching a file or device.

This module is deliberately incapable of mutation.  It validates a complete,
reversible write description and emits a content-free receipt that a separate
executor may later consume after independently checking the live preimage.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import pathlib
import re
import sys
from typing import Any


SCHEMA = "commons-titan-write-envelope/v1"
RECEIPT_SCHEMA = "commons-titan-write-envelope-receipt/v1"
MAX_OPERATION_BYTES = 1_048_576
MAX_TOTAL_BYTES = 4_194_304
HEX64 = re.compile(r"^[0-9a-f]{64}$")


class EnvelopeError(ValueError):
    """Raised when an intent cannot be proven bounded and reversible."""


def _exact_int(value: Any, field: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise EnvelopeError(f"{field} must be an integer >= {minimum}")
    return value


def _exact_text(value: Any, field: str) -> str:
    if type(value) is not str or not value:
        raise EnvelopeError(f"{field} must be a non-empty string")
    return value


def _digest(value: Any, field: str) -> str:
    text = _exact_text(value, field)
    if not HEX64.fullmatch(text):
        raise EnvelopeError(f"{field} must be a lowercase SHA-256 hex digest")
    return text


def _bytes(value: Any, field: str) -> bytes:
    text = _exact_text(value, field)
    try:
        return base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise EnvelopeError(f"{field} must be strict base64") from exc


def _target(value: Any) -> str:
    text = _exact_text(value, "target")
    if "\\" in text or pathlib.PurePosixPath(text).is_absolute():
        raise EnvelopeError("target must be a canonical relative POSIX path")
    parts = pathlib.PurePosixPath(text).parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise EnvelopeError("target must not contain empty, dot, or traversal segments")
    canonical = pathlib.PurePosixPath(*parts).as_posix()
    if canonical != text:
        raise EnvelopeError("target must already be canonical")
    return canonical


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def compile_envelope(raw: Any) -> dict[str, Any]:
    """Validate *raw* and return a deterministic content-free receipt."""
    if type(raw) is not dict:
        raise EnvelopeError("envelope must be an object")
    allowed = {
        "schema", "target", "expected_preimage", "expected_postimage",
        "operations", "reversible", "reason", "intent_id",
    }
    extras = sorted(set(raw) - allowed)
    if extras:
        raise EnvelopeError(f"unknown envelope fields: {', '.join(extras)}")
    if raw.get("schema") != SCHEMA:
        raise EnvelopeError(f"schema must equal {SCHEMA}")
    target = _target(raw.get("target"))
    if raw.get("reversible") is not True:
        raise EnvelopeError("reversible must be exactly true")
    reason = _exact_text(raw.get("reason"), "reason").strip()
    if not reason or len(reason) > 500:
        raise EnvelopeError("reason must contain 1..500 non-whitespace characters")

    pre = raw.get("expected_preimage")
    post = raw.get("expected_postimage")
    if type(pre) is not dict or set(pre) != {"size", "sha256"}:
        raise EnvelopeError("expected_preimage must contain exactly size and sha256")
    if type(post) is not dict or set(post) != {"size", "sha256"}:
        raise EnvelopeError("expected_postimage must contain exactly size and sha256")
    pre_size = _exact_int(pre["size"], "expected_preimage.size")
    post_size = _exact_int(post["size"], "expected_postimage.size")
    pre_sha = _digest(pre["sha256"], "expected_preimage.sha256")
    post_sha = _digest(post["sha256"], "expected_postimage.sha256")
    if pre_sha == post_sha:
        raise EnvelopeError("preimage and postimage digests must differ")

    operations = raw.get("operations")
    if type(operations) is not list or not operations:
        raise EnvelopeError("operations must be a non-empty list")
    normalized: list[dict[str, Any]] = []
    spans: list[tuple[int, int]] = []
    total = 0
    for index, item in enumerate(operations):
        prefix = f"operations[{index}]"
        required = {"offset", "length", "content_base64", "sha256", "rollback_base64", "rollback_sha256"}
        if type(item) is not dict or set(item) != required:
            raise EnvelopeError(f"{prefix} must contain exactly {', '.join(sorted(required))}")
        offset = _exact_int(item["offset"], f"{prefix}.offset")
        length = _exact_int(item["length"], f"{prefix}.length", minimum=1)
        if length > MAX_OPERATION_BYTES:
            raise EnvelopeError(f"{prefix}.length exceeds {MAX_OPERATION_BYTES}")
        content = _bytes(item["content_base64"], f"{prefix}.content_base64")
        rollback = _bytes(item["rollback_base64"], f"{prefix}.rollback_base64")
        if len(content) != length or len(rollback) != length:
            raise EnvelopeError(f"{prefix} payload and rollback lengths must equal length")
        sha = _digest(item["sha256"], f"{prefix}.sha256")
        rollback_sha = _digest(item["rollback_sha256"], f"{prefix}.rollback_sha256")
        if _hash(content) != sha or _hash(rollback) != rollback_sha:
            raise EnvelopeError(f"{prefix} payload or rollback digest mismatch")
        if offset + length > pre_size or post_size != pre_size:
            raise EnvelopeError(f"{prefix} exceeds fixed-size pre/post image")
        spans.append((offset, offset + length))
        total += length
        normalized.append({
            "offset": offset,
            "length": length,
            "sha256": sha,
            "rollback_sha256": rollback_sha,
        })
    if total > MAX_TOTAL_BYTES:
        raise EnvelopeError(f"total write bytes exceed {MAX_TOTAL_BYTES}")
    ordered = sorted(spans)
    if any(right_start < left_end for (_, left_end), (right_start, _) in zip(ordered, ordered[1:])):
        raise EnvelopeError("operation spans must not overlap")

    identity_body = {
        "schema": SCHEMA,
        "target": target,
        "expected_preimage": {"size": pre_size, "sha256": pre_sha},
        "expected_postimage": {"size": post_size, "sha256": post_sha},
        "operations": normalized,
        "reversible": True,
        "reason": reason,
    }
    intent_id = "titan-write-" + _hash(canonical_bytes(identity_body))
    supplied_id = raw.get("intent_id")
    if supplied_id is not None and supplied_id != intent_id:
        raise EnvelopeError("intent_id does not match canonical envelope")
    return {
        "schema": RECEIPT_SCHEMA,
        "intent_id": intent_id,
        "target": target,
        "preimage": {"size": pre_size, "sha256": pre_sha},
        "postimage": {"size": post_size, "sha256": post_sha},
        "operation_count": len(normalized),
        "total_write_bytes": total,
        "operations": normalized,
        "reversible": True,
        "mutation_performed": False,
        "executor_requirements": [
            "recheck exact live preimage size and sha256",
            "apply once with crash-safe journal",
            "read back exact postimage size and sha256",
            "retain rollback bytes until terminal receipt",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", help="JSON envelope path; stdin when omitted")
    args = parser.parse_args(argv)
    try:
        text = pathlib.Path(args.input).read_text(encoding="utf-8") if args.input else sys.stdin.read()
        receipt = compile_envelope(json.loads(text))
    except (OSError, json.JSONDecodeError, EnvelopeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps({"ok": True, "receipt": receipt}, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
