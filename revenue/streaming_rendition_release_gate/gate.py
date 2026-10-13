from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any, Iterable

SCHEMA = "streaming-rendition-release-gate/v1"
RELEASE_READY = "RELEASE_READY"
HOLD = "HOLD"

REASON_INVALID_SCHEMA = "INVALID_SCHEMA"
REASON_MISSING_RENDITION = "MISSING_RENDITION"
REASON_CODEC_PROFILE_MISMATCH = "CODEC_PROFILE_MISMATCH"
REASON_SEGMENT_DISCONTINUITY = "SEGMENT_DISCONTINUITY"
REASON_CAPTION_AUDIO_ALIGNMENT_GAP = "CAPTION_AUDIO_ALIGNMENT_GAP"
REASON_DRM_REFERENCE_MISMATCH = "DRM_REFERENCE_MISMATCH"
REASON_CHECKSUM_ORPHAN_ARTIFACT = "CHECKSUM_ORPHAN_ARTIFACT"
REASON_PUBLICATION_WINDOW_CONFLICT = "PUBLICATION_WINDOW_CONFLICT"
REASON_CDN_REGION_MISMATCH = "CDN_REGION_MISMATCH"

REASON_ORDER = (
    REASON_INVALID_SCHEMA,
    REASON_MISSING_RENDITION,
    REASON_CODEC_PROFILE_MISMATCH,
    REASON_SEGMENT_DISCONTINUITY,
    REASON_CAPTION_AUDIO_ALIGNMENT_GAP,
    REASON_DRM_REFERENCE_MISMATCH,
    REASON_CHECKSUM_ORPHAN_ARTIFACT,
    REASON_PUBLICATION_WINDOW_CONFLICT,
    REASON_CDN_REGION_MISMATCH,
)

_ASSET_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_LANG_RE = re.compile(r"^[a-z]{2}(?:-[A-Z]{2})?$")
_DRMPOLICY_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._:/-]{0,127}$")
_REGION_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,31}$")

_TOP_KEYS = {
    "schema",
    "asset_id",
    "mode",
    "expected",
    "variants",
    "artifacts",
    "publication_window",
    "cdn_region",
}
_EXPECTED_KEYS = {
    "renditions",
    "caption_languages",
    "audio_languages",
    "drm_ref",
    "publication_window",
    "cdn_region",
}
_RENDITION_KEYS = {"name", "codec", "profile"}
_VARIANT_KEYS = {
    "name",
    "codec",
    "profile",
    "segments",
    "caption_languages",
    "audio_languages",
    "caption_audio_alignment_ms",
    "drm_ref",
    "artifact_id",
    "sha256",
}
_SEGMENT_KEYS = {"index", "start_ms", "duration_ms"}
_WINDOW_KEYS = {"start", "end"}


class SchemaError(ValueError):
    pass


def _exact_keys(value: Any, expected: set[str], where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SchemaError(f"{where}: expected object")
    keys = set(value)
    if keys != expected:
        missing = sorted(expected - keys)
        extra = sorted(keys - expected)
        raise SchemaError(f"{where}: key mismatch missing={missing} extra={extra}")
    return value


def _string(value: Any, where: str, pattern: re.Pattern[str] | None = None) -> str:
    if not isinstance(value, str) or not value:
        raise SchemaError(f"{where}: expected non-empty string")
    if pattern is not None and pattern.fullmatch(value) is None:
        raise SchemaError(f"{where}: malformed value")
    return value


def _strict_int(value: Any, where: str, minimum: int = 0) -> int:
    if type(value) is not int:
        raise SchemaError(f"{where}: expected integer")
    if value < minimum:
        raise SchemaError(f"{where}: must be >= {minimum}")
    return value


def _unique_strings(
    value: Any,
    where: str,
    *,
    pattern: re.Pattern[str] | None = None,
    allow_empty: bool = False,
) -> list[str]:
    if not isinstance(value, list):
        raise SchemaError(f"{where}: expected array")
    if not allow_empty and not value:
        raise SchemaError(f"{where}: must not be empty")
    result: list[str] = []
    for idx, item in enumerate(value):
        result.append(_string(item, f"{where}[{idx}]", pattern))
    if len(result) != len(set(result)):
        raise SchemaError(f"{where}: duplicate values")
    return result


def _utc_z(value: Any, where: str) -> str:
    text = _string(value, where)
    if not text.endswith("Z"):
        raise SchemaError(f"{where}: expected UTC Z timestamp")
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        raise SchemaError(f"{where}: malformed timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SchemaError(f"{where}: timezone required")
    return text


def _window(value: Any, where: str, mode: str) -> dict[str, Any]:
    window = _exact_keys(value, _WINDOW_KEYS, where)
    start = _utc_z(window["start"], f"{where}.start")
    end = window["end"]
    if mode == "LIVE":
        if end is not None:
            raise SchemaError(f"{where}.end: LIVE must be null")
    else:
        end = _utc_z(end, f"{where}.end")
        start_dt = datetime.fromisoformat(start[:-1] + "+00:00")
        end_dt = datetime.fromisoformat(end[:-1] + "+00:00")
        if end_dt <= start_dt:
            raise SchemaError(f"{where}: VOD end must be after start")
    return {"start": start, "end": end}


def _validate_schema(packet: Any) -> dict[str, Any]:
    top = _exact_keys(packet, _TOP_KEYS, "packet")
    if top["schema"] != SCHEMA:
        raise SchemaError("packet.schema: unsupported schema")
    _string(top["asset_id"], "packet.asset_id", _ASSET_ID_RE)
    mode = _string(top["mode"], "packet.mode")
    if mode not in {"LIVE", "VOD"}:
        raise SchemaError("packet.mode: expected LIVE or VOD")

    expected = _exact_keys(top["expected"], _EXPECTED_KEYS, "packet.expected")
    expected_rends = expected["renditions"]
    if not isinstance(expected_rends, list) or not expected_rends:
        raise SchemaError("packet.expected.renditions: expected non-empty array")
    expected_names: list[str] = []
    for idx, rendition in enumerate(expected_rends):
        item = _exact_keys(rendition, _RENDITION_KEYS, f"packet.expected.renditions[{idx}]")
        expected_names.append(_string(item["name"], f"packet.expected.renditions[{idx}].name", _ASSET_ID_RE))
        _string(item["codec"], f"packet.expected.renditions[{idx}].codec", _ASSET_ID_RE)
        _string(item["profile"], f"packet.expected.renditions[{idx}].profile", _ASSET_ID_RE)
    if len(expected_names) != len(set(expected_names)):
        raise SchemaError("packet.expected.renditions: duplicate names")
    _unique_strings(expected["caption_languages"], "packet.expected.caption_languages", pattern=_LANG_RE)
    _unique_strings(expected["audio_languages"], "packet.expected.audio_languages", pattern=_LANG_RE)
    _string(expected["drm_ref"], "packet.expected.drm_ref", _DRMPOLICY_RE)
    _window(expected["publication_window"], "packet.expected.publication_window", mode)
    _string(expected["cdn_region"], "packet.expected.cdn_region", _REGION_RE)

    variants = top["variants"]
    if not isinstance(variants, list) or not variants:
        raise SchemaError("packet.variants: expected non-empty array")
    variant_names: list[str] = []
    artifact_ids: list[str] = []
    for idx, variant in enumerate(variants):
        item = _exact_keys(variant, _VARIANT_KEYS, f"packet.variants[{idx}]")
        variant_names.append(_string(item["name"], f"packet.variants[{idx}].name", _ASSET_ID_RE))
        _string(item["codec"], f"packet.variants[{idx}].codec", _ASSET_ID_RE)
        _string(item["profile"], f"packet.variants[{idx}].profile", _ASSET_ID_RE)

        segments = item["segments"]
        if not isinstance(segments, list) or not segments:
            raise SchemaError(f"packet.variants[{idx}].segments: expected non-empty array")
        for sidx, segment in enumerate(segments):
            seg = _exact_keys(segment, _SEGMENT_KEYS, f"packet.variants[{idx}].segments[{sidx}]")
            _strict_int(seg["index"], f"packet.variants[{idx}].segments[{sidx}].index")
            _strict_int(seg["start_ms"], f"packet.variants[{idx}].segments[{sidx}].start_ms")
            _strict_int(seg["duration_ms"], f"packet.variants[{idx}].segments[{sidx}].duration_ms", minimum=1)
        _unique_strings(item["caption_languages"], f"packet.variants[{idx}].caption_languages", pattern=_LANG_RE)
        _unique_strings(item["audio_languages"], f"packet.variants[{idx}].audio_languages", pattern=_LANG_RE)
        _strict_int(item["caption_audio_alignment_ms"], f"packet.variants[{idx}].caption_audio_alignment_ms")
        _string(item["drm_ref"], f"packet.variants[{idx}].drm_ref", _DRMPOLICY_RE)
        artifact_ids.append(_string(item["artifact_id"], f"packet.variants[{idx}].artifact_id", _ASSET_ID_RE))
        _string(item["sha256"], f"packet.variants[{idx}].sha256", _SHA256_RE)
    if len(variant_names) != len(set(variant_names)):
        raise SchemaError("packet.variants: duplicate rendition names")
    if len(artifact_ids) != len(set(artifact_ids)):
        raise SchemaError("packet.variants: duplicate artifact ids")

    artifacts = top["artifacts"]
    if not isinstance(artifacts, dict):
        raise SchemaError("packet.artifacts: expected object")
    if not artifacts:
        raise SchemaError("packet.artifacts: must not be empty")
    for artifact_id, digest in artifacts.items():
        _string(artifact_id, "packet.artifacts key", _ASSET_ID_RE)
        _string(digest, f"packet.artifacts[{artifact_id}]", _SHA256_RE)

    _window(top["publication_window"], "packet.publication_window", mode)
    _string(top["cdn_region"], "packet.cdn_region", _REGION_RE)
    return top


def _hold(asset_id: str, reason: str, detail: str) -> dict[str, str]:
    return {
        "asset_id": asset_id,
        "status": HOLD,
        "reason": reason,
        "detail": detail,
    }


def validate_packet(packet: Any) -> dict[str, str]:
    asset_id = "<invalid>"
    if isinstance(packet, dict) and isinstance(packet.get("asset_id"), str) and packet["asset_id"]:
        asset_id = packet["asset_id"]
    try:
        top = _validate_schema(packet)
    except (SchemaError, TypeError, ValueError) as exc:
        return _hold(asset_id, REASON_INVALID_SCHEMA, str(exc))

    asset_id = top["asset_id"]
    expected = top["expected"]
    expected_by_name = {item["name"]: item for item in expected["renditions"]}
    variants_by_name = {item["name"]: item for item in top["variants"]}

    missing = sorted(set(expected_by_name) - set(variants_by_name))
    extra = sorted(set(variants_by_name) - set(expected_by_name))
    if missing or extra:
        return _hold(
            asset_id,
            REASON_MISSING_RENDITION,
            f"expected rendition set mismatch missing={missing} unexpected={extra}",
        )

    for name in expected_by_name:
        want = expected_by_name[name]
        got = variants_by_name[name]
        if got["codec"] != want["codec"] or got["profile"] != want["profile"]:
            return _hold(
                asset_id,
                REASON_CODEC_PROFILE_MISMATCH,
                f"{name}: expected {want['codec']}/{want['profile']} got {got['codec']}/{got['profile']}",
            )

    for name in expected_by_name:
        segments = variants_by_name[name]["segments"]
        expected_start = 0
        for idx, segment in enumerate(segments):
            if segment["index"] != idx or segment["start_ms"] != expected_start:
                return _hold(
                    asset_id,
                    REASON_SEGMENT_DISCONTINUITY,
                    f"{name}: segment {idx} expected index/start {idx}/{expected_start} "
                    f"got {segment['index']}/{segment['start_ms']}",
                )
            expected_start += segment["duration_ms"]

    expected_captions = set(expected["caption_languages"])
    expected_audio = set(expected["audio_languages"])
    for name in expected_by_name:
        variant = variants_by_name[name]
        if set(variant["caption_languages"]) != expected_captions:
            return _hold(
                asset_id,
                REASON_CAPTION_AUDIO_ALIGNMENT_GAP,
                f"{name}: caption language set mismatch",
            )
        if set(variant["audio_languages"]) != expected_audio:
            return _hold(
                asset_id,
                REASON_CAPTION_AUDIO_ALIGNMENT_GAP,
                f"{name}: audio language set mismatch",
            )
        if variant["caption_audio_alignment_ms"] > 100:
            return _hold(
                asset_id,
                REASON_CAPTION_AUDIO_ALIGNMENT_GAP,
                f"{name}: alignment {variant['caption_audio_alignment_ms']}ms exceeds 100ms",
            )

    for name in expected_by_name:
        if variants_by_name[name]["drm_ref"] != expected["drm_ref"]:
            return _hold(
                asset_id,
                REASON_DRM_REFERENCE_MISMATCH,
                f"{name}: DRM reference mismatch",
            )

    referenced: set[str] = set()
    for name in expected_by_name:
        variant = variants_by_name[name]
        artifact_id = variant["artifact_id"]
        referenced.add(artifact_id)
        actual_digest = top["artifacts"].get(artifact_id)
        if actual_digest is None or actual_digest != variant["sha256"]:
            return _hold(
                asset_id,
                REASON_CHECKSUM_ORPHAN_ARTIFACT,
                f"{name}: artifact digest missing or mismatched",
            )
    artifact_ids = set(top["artifacts"])
    if artifact_ids != referenced:
        orphan = sorted(artifact_ids - referenced)
        missing_artifacts = sorted(referenced - artifact_ids)
        return _hold(
            asset_id,
            REASON_CHECKSUM_ORPHAN_ARTIFACT,
            f"artifact reference mismatch orphan={orphan} missing={missing_artifacts}",
        )

    if top["publication_window"] != expected["publication_window"]:
        return _hold(
            asset_id,
            REASON_PUBLICATION_WINDOW_CONFLICT,
            "publication window differs from source contract",
        )

    if top["cdn_region"] != expected["cdn_region"]:
        return _hold(
            asset_id,
            REASON_CDN_REGION_MISMATCH,
            f"expected {expected['cdn_region']} got {top['cdn_region']}",
        )

    return {
        "asset_id": asset_id,
        "status": RELEASE_READY,
        "reason": "NONE",
        "detail": "metadata contract satisfied; media operations retain release authority",
    }


def canonical_projection(results: Iterable[dict[str, str]]) -> bytes:
    rows = list(results)
    payload = {
        "schema": SCHEMA,
        "results": rows,
        "summary": {
            "total": len(rows),
            "release_ready": sum(row["status"] == RELEASE_READY for row in rows),
            "hold": sum(row["status"] == HOLD for row in rows),
        },
    }
    return (json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("utf-8")


def validate_packets(packets: Iterable[Any]) -> dict[str, Any]:
    rows = [validate_packet(packet) for packet in packets]
    projection = canonical_projection(rows)
    return {
        "results": rows,
        "projection": projection,
        "projection_sha256": hashlib.sha256(projection).hexdigest(),
    }


__all__ = [
    "SCHEMA",
    "RELEASE_READY",
    "HOLD",
    "REASON_INVALID_SCHEMA",
    "REASON_MISSING_RENDITION",
    "REASON_CODEC_PROFILE_MISMATCH",
    "REASON_SEGMENT_DISCONTINUITY",
    "REASON_CAPTION_AUDIO_ALIGNMENT_GAP",
    "REASON_DRM_REFERENCE_MISMATCH",
    "REASON_CHECKSUM_ORPHAN_ARTIFACT",
    "REASON_PUBLICATION_WINDOW_CONFLICT",
    "REASON_CDN_REGION_MISMATCH",
    "validate_packet",
    "validate_packets",
    "canonical_projection",
]
