from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

try:
    from .gate import SCHEMA
except ImportError:
    from gate import SCHEMA

REQUIRED_FAULT_CLASSES = (
    "MISSING_RENDITION",
    "CODEC_PROFILE_MISMATCH",
    "SEGMENT_DISCONTINUITY",
    "CAPTION_AUDIO_ALIGNMENT_GAP",
    "DRM_REFERENCE_MISMATCH",
    "CHECKSUM_ORPHAN_ARTIFACT",
    "PUBLICATION_WINDOW_CONFLICT",
)

RENDITIONS = (
    {"name": "1080p", "codec": "h264", "profile": "high"},
    {"name": "720p", "codec": "h264", "profile": "main"},
    {"name": "480p", "codec": "h264", "profile": "main"},
)


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _clean_packet(index: int) -> dict[str, Any]:
    asset_id = f"asset-{index:03d}"
    mode = "LIVE" if index % 3 == 0 else "VOD"
    day = 13 + (index % 10)
    start = f"2026-09-{day:02d}T12:00:00Z"
    end = None if mode == "LIVE" else f"2026-09-{day:02d}T13:30:00Z"
    window = {"start": start, "end": end}

    variants: list[dict[str, Any]] = []
    artifacts: dict[str, str] = {}
    for rendition in RENDITIONS:
        artifact_id = f"{asset_id}-{rendition['name']}"
        sha256 = _digest(f"{asset_id}:{rendition['name']}:payload-v1")
        artifacts[artifact_id] = sha256
        variants.append(
            {
                "name": rendition["name"],
                "codec": rendition["codec"],
                "profile": rendition["profile"],
                "segments": [
                    {"index": 0, "start_ms": 0, "duration_ms": 4000},
                    {"index": 1, "start_ms": 4000, "duration_ms": 4000},
                    {"index": 2, "start_ms": 8000, "duration_ms": 4000},
                ],
                "caption_languages": ["en", "es"],
                "audio_languages": ["en", "es"],
                "caption_audio_alignment_ms": 40,
                "drm_ref": "drm-policy-v1",
                "artifact_id": artifact_id,
                "sha256": sha256,
            }
        )

    return {
        "schema": SCHEMA,
        "asset_id": asset_id,
        "mode": mode,
        "expected": {
            "renditions": [dict(item) for item in RENDITIONS],
            "caption_languages": ["en", "es"],
            "audio_languages": ["en", "es"],
            "drm_ref": "drm-policy-v1",
            "publication_window": dict(window),
            "cdn_region": "us-east-1",
        },
        "variants": variants,
        "artifacts": artifacts,
        "publication_window": dict(window),
        "cdn_region": "us-east-1",
    }


def build_fixture() -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    packets = [_clean_packet(index) for index in range(168)]
    fault_assets: dict[str, list[str]] = {}

    for class_index, fault in enumerate(REQUIRED_FAULT_CLASSES):
        assets: list[str] = []
        for offset in range(4):
            index = 140 + class_index * 4 + offset
            packet = packets[index]
            assets.append(packet["asset_id"])

            if fault == "MISSING_RENDITION":
                removed = packet["variants"].pop()
                packet["artifacts"].pop(removed["artifact_id"])
            elif fault == "CODEC_PROFILE_MISMATCH":
                packet["variants"][0]["profile"] = "baseline"
            elif fault == "SEGMENT_DISCONTINUITY":
                packet["variants"][1]["segments"][1]["start_ms"] = 4500
            elif fault == "CAPTION_AUDIO_ALIGNMENT_GAP":
                packet["variants"][2]["caption_audio_alignment_ms"] = 250
            elif fault == "DRM_REFERENCE_MISMATCH":
                packet["variants"][0]["drm_ref"] = "drm-policy-v2"
            elif fault == "CHECKSUM_ORPHAN_ARTIFACT":
                packet["artifacts"][f"{packet['asset_id']}-orphan"] = _digest(
                    f"{packet['asset_id']}:orphan"
                )
            elif fault == "PUBLICATION_WINDOW_CONFLICT":
                packet["publication_window"]["start"] = packet["publication_window"]["start"].replace(
                    "12:00:00Z", "12:05:00Z"
                )
        fault_assets[fault] = assets

    return packets, fault_assets


def canonical_fixture_bytes() -> bytes:
    packets, _ = build_fixture()
    return (
        json.dumps(packets, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
    ).encode("utf-8")


__all__ = [
    "REQUIRED_FAULT_CLASSES",
    "RENDITIONS",
    "build_fixture",
    "canonical_fixture_bytes",
]
