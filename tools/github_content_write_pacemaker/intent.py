"""Mutation intent normalization and descriptor-bound input capture."""

from __future__ import annotations
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict
from .codec import canonical_json, digest
from .constants import MAX_BYTES, SCHEMA
from .errors import PacemakerError

KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$")
METHOD = re.compile(r"^[A-Z][A-Z0-9_-]{0,15}$")

@dataclass(frozen=True)
class Intent:
    mutation_key: str
    method: str
    api_path: str
    description: str
    body: Any
    body_bytes: bytes
    body_sha256: str
    semantic_sha256: str
    intent_sha256: str

@dataclass(frozen=True)
class Claim:
    mutation_key: str
    method: str
    api_path: str
    body: Any
    attempt: int
    claimed_at: str
    semantic_sha256: str
    def envelope(self) -> Dict[str, Any]:
        return {
            "schema": "commons-github-connector-claim/v1",
            "mutationKey": self.mutation_key,
            "method": self.method,
            "apiPath": self.api_path,
            "body": self.body,
            "attempt": self.attempt,
            "claimedAt": self.claimed_at,
            "semanticSha256": self.semantic_sha256,
        }

def _text(value: Any, label: str, maximum: int) -> str:
    if type(value) is not str or not value or len(value) > maximum:
        raise PacemakerError(f"{label} has invalid type or length")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise PacemakerError(f"{label} contains control characters")
    return value

def normalize_intent(value: Any) -> Intent:
    fields = {"schema", "mutationKey", "method", "apiPath", "description", "body"}
    if type(value) is not dict or set(value) != fields or value.get("schema") != SCHEMA:
        raise PacemakerError("invalid intent shape or schema")
    key = _text(value["mutationKey"], "mutationKey", 200)
    method = _text(value["method"], "method", 16)
    path = _text(value["apiPath"], "apiPath", 4096)
    description = _text(value["description"], "description", 4096)
    if not KEY.fullmatch(key) or not METHOD.fullmatch(method):
        raise PacemakerError("invalid mutation key or method syntax")
    if not path.startswith("/") or path.startswith("//") or "#" in path:
        raise PacemakerError("apiPath must be one relative provider path")
    body_bytes = canonical_json(value["body"])
    body_sha = digest(body_bytes)
    semantic = digest(canonical_json({"method": method, "apiPath": path,
                                      "bodySha256": body_sha}))
    intent_bytes = canonical_json({"schema": SCHEMA, "mutationKey": key,
                                   "method": method, "apiPath": path,
                                   "description": description, "body": value["body"]})
    return Intent(key, method, path, description, value["body"], body_bytes,
                  body_sha, semantic, digest(intent_bytes))

def read_regular_bytes(path: Path, maximum: int = MAX_BYTES) -> bytes:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_NONBLOCK"):
        flags |= os.O_NONBLOCK
    fd = os.open(path, flags)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise PacemakerError("input must be one ordinary single-link file")
        raw = b""
        while len(raw) <= maximum:
            chunk = os.read(fd, min(65536, maximum + 1 - len(raw)))
            if not chunk:
                break
            raw += chunk
        if len(raw) > maximum:
            raise PacemakerError("input exceeds byte limit")
        after = os.fstat(fd)
        visible = os.stat(path, follow_symlinks=False)
        fields = ("st_dev", "st_ino", "st_mode", "st_nlink", "st_size",
                  "st_mtime_ns", "st_ctime_ns")
        if any(getattr(before, f) != getattr(after, f) for f in fields):
            raise PacemakerError("input changed while reading")
        if any(getattr(before, f) != getattr(visible, f) for f in fields):
            raise PacemakerError("input path changed while reading")
        return raw
    finally:
        os.close(fd)
