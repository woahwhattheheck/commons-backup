#!/usr/bin/env python3
"""Local-first creative review and approval operations desk.

This module records owner-supplied workflow facts.  It does not infer creative
quality, rights, compliance, publication authority, or commercial acceptance.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from datetime import datetime, timezone
from typing import Any

SCHEMA = "tjlabs.creative-review-approval.v1"
BUNDLE_SCHEMA = "tjlabs.creative-review-approval.bundle.v1"
RECEIPT_SCHEMA = "tjlabs.creative-review-approval.receipt.v1"
MAX_JSON_BYTES = 1_000_000
MAX_ASSET_BYTES = 128 * 1024 * 1024
MAX_TEXT = 2_000
MAX_ARRAY = 2_000
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
MEDIA_TYPES = {"image", "video", "audio", "document", "copy"}
DECISIONS = {"APPROVE", "CHANGES_REQUESTED", "COMMENT_ONLY"}
ANNOTATION_CATEGORIES = {
    "CONTENT",
    "FORMAT",
    "BRAND_REVIEW_REQUIRED",
    "ACCESSIBILITY_REVIEW_REQUIRED",
    "LEGAL_REVIEW_REQUIRED",
    "OTHER",
}
AUTHORITY = {
    "creative_quality_conclusion": False,
    "brand_or_compliance_conclusion": False,
    "rights_or_licensing_conclusion": False,
    "external_send": False,
    "external_publication": False,
    "provider_mutation": False,
    "payment_or_spend": False,
    "buyer_acceptance": False,
    "recognized_revenue": False,
}


class DeskError(Exception):
    """Base class for bounded workflow failures."""


class InvalidInput(DeskError):
    pass


class InvalidState(DeskError):
    pass


class IdempotencyConflict(DeskError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _require_scalar_unicode(value: Any, label: str = "value") -> None:
    """Reject lone UTF-16 surrogate code points before UTF-8 canonicalization."""
    if type(value) is str:
        if any(0xD800 <= ord(ch) <= 0xDFFF for ch in value):
            raise InvalidInput(f"{label} contains a non-scalar Unicode surrogate")
        return
    if type(value) is list:
        for item in value:
            _require_scalar_unicode(item, label)
        return
    if type(value) is dict:
        for key, item in value.items():
            _require_scalar_unicode(key, label)
            _require_scalar_unicode(item, label)


def canonical_json(value: Any) -> str:
    _require_scalar_unicode(value, "canonical JSON")
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def canonical_bytes(value: Any) -> bytes:
    return (canonical_json(value) + "\n").encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_json(value: Any) -> str:
    return sha256_bytes(canonical_bytes(value))


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise InvalidInput(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def strict_json_loads(raw: bytes | str) -> Any:
    if isinstance(raw, bytes):
        if len(raw) > MAX_JSON_BYTES:
            raise InvalidInput("JSON input exceeds size cap")
        try:
            raw = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise InvalidInput("JSON input must be UTF-8") from exc
    if not isinstance(raw, str):
        raise InvalidInput("JSON input must be bytes or text")
    _require_scalar_unicode(raw, "JSON input")
    if len(raw.encode("utf-8")) > MAX_JSON_BYTES:
        raise InvalidInput("JSON input exceeds size cap")
    try:
        value = json.loads(
            raw,
            object_pairs_hook=_pairs,
            parse_constant=lambda token: (_ for _ in ()).throw(InvalidInput(f"non-finite JSON number: {token}")),
        )
        _require_scalar_unicode(value, "JSON value")
        return value
    except InvalidInput:
        raise
    except Exception as exc:
        raise InvalidInput(f"invalid JSON: {exc}") from exc


def _exact_dict(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != keys:
        raise InvalidInput(f"{label} must contain exactly: {', '.join(sorted(keys))}")
    return value


def _id(label: str, value: Any) -> str:
    if type(value) is not str or not ID_RE.fullmatch(value):
        raise InvalidInput(f"invalid {label}")
    return value


def _text(label: str, value: Any, *, maximum: int = MAX_TEXT, empty: bool = False) -> str:
    if type(value) is not str or len(value) > maximum or (not empty and not value):
        raise InvalidInput(f"invalid {label}")
    _require_scalar_unicode(value, label)
    if any(ord(ch) < 32 and ch not in "\t" for ch in value):
        raise InvalidInput(f"invalid control character in {label}")
    return value


def _positive_int(label: str, value: Any, *, allow_none: bool = False) -> int | None:
    if value is None and allow_none:
        return None
    if type(value) is not int or value <= 0 or value > 2_147_483_647:
        raise InvalidInput(f"{label} must be a positive integer")
    return value


def _nonnegative_int(label: str, value: Any) -> int:
    if type(value) is not int or value < 0 or value > 2_147_483_647:
        raise InvalidInput(f"{label} must be a non-negative integer")
    return value


def _string_array(label: str, value: Any, *, maximum: int = 64) -> list[str]:
    if type(value) is not list or not value or len(value) > maximum:
        raise InvalidInput(f"{label} must be a non-empty bounded array")
    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        item = _id(label, item)
        if item in seen:
            raise InvalidInput(f"duplicate {label}: {item}")
        seen.add(item)
        out.append(item)
    return sorted(out)


def normalize_metadata(value: Any) -> dict[str, int | None]:
    value = _exact_dict(value, {"width", "height", "duration_ms", "page_count"}, "metadata")
    return {
        "width": _positive_int("metadata.width", value["width"], allow_none=True),
        "height": _positive_int("metadata.height", value["height"], allow_none=True),
        "duration_ms": _positive_int("metadata.duration_ms", value["duration_ms"], allow_none=True),
        "page_count": _positive_int("metadata.page_count", value["page_count"], allow_none=True),
    }


def normalize_spec(value: Any) -> dict[str, Any]:
    value = _exact_dict(value, {"campaign_id", "name", "policy", "assets"}, "campaign spec")
    campaign_id = _id("campaign_id", value["campaign_id"])
    name = _text("campaign name", value["name"], maximum=200)
    policy = _exact_dict(
        value["policy"],
        {"require_distinct_reviewers", "prohibit_author_review"},
        "policy",
    )
    for key in policy:
        if type(policy[key]) is not bool:
            raise InvalidInput(f"policy.{key} must be a boolean")
    assets_raw = value["assets"]
    if type(assets_raw) is not list or not assets_raw or len(assets_raw) > 1_000:
        raise InvalidInput("assets must be a non-empty bounded array")
    assets: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(assets_raw):
        raw = _exact_dict(
            raw,
            {
                "asset_id",
                "title",
                "media_type",
                "destinations",
                "required_roles",
                "constraints",
            },
            f"assets[{index}]",
        )
        asset_id = _id("asset_id", raw["asset_id"])
        if asset_id in seen:
            raise InvalidInput(f"duplicate asset_id: {asset_id}")
        seen.add(asset_id)
        media_type = raw["media_type"]
        if type(media_type) is not str or media_type not in MEDIA_TYPES:
            raise InvalidInput(f"invalid media_type for {asset_id}")
        assets.append(
            {
                "asset_id": asset_id,
                "title": _text("asset title", raw["title"], maximum=200),
                "media_type": media_type,
                "destinations": _string_array("destination", raw["destinations"]),
                "required_roles": _string_array("reviewer role", raw["required_roles"]),
                "constraints": normalize_metadata(raw["constraints"]),
            }
        )
    assets.sort(key=lambda item: item["asset_id"])
    return {
        "campaign_id": campaign_id,
        "name": name,
        "policy": {
            "prohibit_author_review": policy["prohibit_author_review"],
            "require_distinct_reviewers": policy["require_distinct_reviewers"],
        },
        "assets": assets,
    }


def _open_regular_no_symlink_components(path: os.PathLike[str] | str) -> int:
    """Open one regular-file candidate without following any pathname component."""
    if os.name != "posix" or not getattr(os, "O_NOFOLLOW", 0) or not getattr(os, "O_DIRECTORY", 0):
        raise InvalidInput("secure input custody is unavailable on this platform")
    if os.open not in getattr(os, "supports_dir_fd", set()):
        raise InvalidInput("descriptor-relative input custody is unavailable on this platform")

    absolute = os.path.abspath(os.fspath(path))
    parent, leaf = os.path.split(absolute)
    if not leaf or leaf in {".", ".."}:
        raise InvalidInput("input path must name a file")

    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    leaf_flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    directory_fd = os.open(os.path.sep, directory_flags)
    try:
        relative_parent = parent.removeprefix(os.path.sep)
        for component in relative_parent.split(os.path.sep):
            if not component or component == ".":
                continue
            if component == "..":
                raise InvalidInput("input path traversal is not allowed")
            next_fd = os.open(component, directory_flags, dir_fd=directory_fd)
            os.close(directory_fd)
            directory_fd = next_fd
        return os.open(leaf, leaf_flags, dir_fd=directory_fd)
    except OSError as exc:
        raise InvalidInput("input path must not traverse symlinks") from exc
    finally:
        os.close(directory_fd)


def _read_regular(path: os.PathLike[str] | str, cap: int) -> bytes:
    fd = _open_regular_no_symlink_components(path)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise InvalidInput("input must be a regular file")
        if info.st_size > cap:
            raise InvalidInput("input file exceeds size cap")
        chunks: list[bytes] = []
        remaining = info.st_size
        while remaining:
            chunk = os.read(fd, min(1_048_576, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        if len(data) != info.st_size:
            raise InvalidInput("input changed or truncated while reading")
        after = os.fstat(fd)
        if (after.st_dev, after.st_ino, after.st_size) != (info.st_dev, info.st_ino, info.st_size):
            raise InvalidInput("input identity changed while reading")
        return data
    finally:
        os.close(fd)


def read_json_file(path: os.PathLike[str] | str) -> Any:
    return strict_json_loads(_read_regular(path, MAX_JSON_BYTES))


def read_asset(path: os.PathLike[str] | str) -> tuple[bytes, str, int, str]:
    data = _read_regular(path, MAX_ASSET_BYTES)
    return data, sha256_bytes(data), len(data), os.path.basename(os.fspath(path))


def _metadata_matches(actual: dict[str, Any], constraints: dict[str, Any]) -> list[str]:
    holds: list[str] = []
    for key, expected in constraints.items():
        if expected is not None and actual.get(key) != expected:
            holds.append(f"METADATA_MISMATCH:{key}")
    return holds


def normalize_location(value: Any, media_type: str, metadata: dict[str, Any]) -> dict[str, Any]:
    if type(value) is not dict or "kind" not in value or type(value["kind"]) is not str:
        raise InvalidInput("annotation location requires a kind")
    kind = value["kind"]
    if kind == "GLOBAL":
        _exact_dict(value, {"kind"}, "GLOBAL location")
        return {"kind": "GLOBAL"}
    if kind == "TIME_MS":
        _exact_dict(value, {"kind", "start_ms", "end_ms"}, "TIME_MS location")
        if media_type not in {"video", "audio"} or metadata["duration_ms"] is None:
            raise InvalidInput("TIME_MS requires video/audio duration metadata")
        start = _nonnegative_int("start_ms", value["start_ms"])
        end = _positive_int("end_ms", value["end_ms"])
        if start >= end or end > metadata["duration_ms"]:
            raise InvalidInput("TIME_MS range is outside retained duration")
        return {"kind": kind, "start_ms": start, "end_ms": end}
    if kind == "PIXEL_RECT":
        _exact_dict(value, {"kind", "x", "y", "width", "height"}, "PIXEL_RECT location")
        if media_type not in {"image", "video"} or metadata["width"] is None or metadata["height"] is None:
            raise InvalidInput("PIXEL_RECT requires image/video dimensions")
        x = _nonnegative_int("x", value["x"])
        y = _nonnegative_int("y", value["y"])
        width = _positive_int("width", value["width"])
        height = _positive_int("height", value["height"])
        if x + width > metadata["width"] or y + height > metadata["height"]:
            raise InvalidInput("PIXEL_RECT is outside retained dimensions")
        return {"kind": kind, "x": x, "y": y, "width": width, "height": height}
    if kind == "PAGE":
        _exact_dict(value, {"kind", "page"}, "PAGE location")
        if media_type != "document" or metadata["page_count"] is None:
            raise InvalidInput("PAGE requires document page_count metadata")
        page = _positive_int("page", value["page"])
        if page > metadata["page_count"]:
            raise InvalidInput("PAGE is outside retained page count")
        return {"kind": kind, "page": page}
    if kind == "TEXT_RANGE":
        _exact_dict(value, {"kind", "start_char", "end_char"}, "TEXT_RANGE location")
        if media_type != "copy":
            raise InvalidInput("TEXT_RANGE requires copy media type")
        start = _nonnegative_int("start_char", value["start_char"])
        end = _positive_int("end_char", value["end_char"])
        if start >= end or end > 1_000_000:
            raise InvalidInput("invalid TEXT_RANGE")
        return {"kind": kind, "start_char": start, "end_char": end}
    raise InvalidInput(f"unsupported annotation location kind: {kind}")
