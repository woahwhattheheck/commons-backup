"""Prepare compact edits from immutable GitHub content records, without writes."""
from __future__ import annotations

import base64
import binascii
import hashlib
import re

from .provider_io import EquipmentError


def _invalid(message: str) -> EquipmentError:
    return EquipmentError(message, code="github_edit_invalid", uncertain=False)


def require_sha(value, field: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-fA-F]{40}", value):
        raise _invalid(field + " must be a full Git SHA")
    return value.lower()


def validate_file_edits(edits) -> list[dict]:
    """Validate the entire compact request before reading or mutating providers."""
    if not isinstance(edits, list) or not edits:
        raise _invalid("edits must be a nonempty array")
    rows, paths = [], set()
    for index, edit in enumerate(edits):
        if not isinstance(edit, dict) or set(edit) != {"path", "expected_blob_sha", "replacements"}:
            raise _invalid(f"edits[{index}] must contain path, expected_blob_sha and replacements")
        path = edit["path"]
        if (not isinstance(path, str) or not path.strip() or "\\" in path
                or any(part in {"", ".", ".."} for part in path.split("/"))
                or any(ord(char) < 32 or ord(char) == 127 for char in path)):
            raise _invalid(f"edits[{index}].path must be an exact relative repository path")
        if path in paths:
            raise _invalid("duplicate edit path: " + path)
        paths.add(path)
        sha = require_sha(edit["expected_blob_sha"], "expected_blob_sha")
        replacements = edit["replacements"]
        if not isinstance(replacements, list) or not replacements:
            raise _invalid(path + ": replacements must be a nonempty array")
        normalized, anchors = [], set()
        for replacement in replacements:
            if (not isinstance(replacement, dict) or set(replacement) != {"old", "new"}
                    or not isinstance(replacement["old"], str) or not replacement["old"]
                    or not isinstance(replacement["new"], str)):
                raise _invalid(path + ": each replacement requires a nonempty old string and a new string")
            old, new = replacement["old"], replacement["new"]
            if old in anchors:
                raise _invalid(path + ": duplicate replacement anchor")
            anchors.add(old)
            try:
                old.encode("utf-8")
                new.encode("utf-8")
                path.encode("utf-8")
            except UnicodeEncodeError as exc:
                raise _invalid(path + ": edit strings must be valid UTF-8") from exc
            normalized.append({"old": old, "new": new})
        rows.append({"path": path, "expected_blob_sha": sha, "replacements": normalized})
    return rows


def prepare_file_edits(edits, sources: dict[str, dict]) -> list[dict]:
    """Apply exact single-occurrence edits to captured, SHA-verified file bytes.

    sources contains unredacted base64 GitHub records read at expected_head.
    Replacements are applied in order; no source decoding or newline conversion
    occurs until the completed UTF-8 file is passed to github_commit_files.
    """
    rows = validate_file_edits(edits)
    files = []
    for edit in rows:
        path, expected = edit["path"], edit["expected_blob_sha"]
        source = sources.get(path)
        if (not isinstance(source, dict) or source.get("path") != path
                or source.get("sha") != expected or source.get("encoding") != "base64"
                or not isinstance(source.get("content"), str)):
            raise _invalid(path + ": provider file, blob SHA or encoding does not match")
        try:
            encoded = source["content"].encode("ascii")
            content = base64.b64decode(b"".join(encoded.split()), validate=True)
            content.decode("utf-8")
        except (UnicodeError, ValueError, binascii.Error) as exc:
            raise _invalid(path + ": provider content must be base64-encoded UTF-8") from exc
        blob = b"blob " + str(len(content)).encode("ascii") + b"\0" + content
        if hashlib.sha1(blob, usedforsecurity=False).hexdigest() != expected:
            raise _invalid(path + ": source bytes do not match expected_blob_sha")
        for replacement in edit["replacements"]:
            old, new = replacement["old"].encode("utf-8"), replacement["new"].encode("utf-8")
            offset = content.find(old)
            if offset < 0 or content.find(old, offset + 1) >= 0:
                raise _invalid(path + ": old must occur exactly once before replacement")
            content = content[:offset] + new + content[offset + len(old):]
        files.append({"path": path, "content": content.decode("utf-8")})
    return files
