from __future__ import annotations
import math
from pathlib import Path
from typing import Any
from managed_common import SCHEMA, ManagedClippingError, _utc_now, load_project, probe_source, save_project, verify_source
from managed_adapters import normalize_cedar_keeps, normalize_kestrel_segments, _choose_even_moments, _choose_transcript_moments

def create_project(
    source: Path,
    project_path: Path,
    *,
    transcript_document: Any | None = None,
    cedar_keeps: Any | None = None,
    moment_count: int = 20,
    synthetic_demo: bool = False,
) -> dict[str, Any]:
    if project_path.exists():
        raise ManagedClippingError(f"project already exists: {project_path}")
    if moment_count <= 0 or moment_count > 500:
        raise ManagedClippingError("moment_count must be between 1 and 500")
    source_info = probe_source(source)
    segments = normalize_kestrel_segments(transcript_document) if transcript_document is not None else []
    keeps = normalize_cedar_keeps(cedar_keeps) if cedar_keeps is not None else []
    if cedar_keeps is not None and not keeps:
        raise ManagedClippingError(
            "CEDAR keep selection contains no ranges; no footage is eligible. "
            "Omit keep input to use the whole source."
        )
    for start, end in keeps:
        if end > source_info["duration_ms"] + 50:
            raise ManagedClippingError("CEDAR keep range exceeds source duration")
    if transcript_document is not None:
        moments = _choose_transcript_moments(segments, keeps, moment_count, source_info["duration_ms"])
        selection_mode = "transcript"
    else:
        moments = _choose_even_moments(keeps, moment_count, source_info["duration_ms"])
        selection_mode = "generic"
    for moment in moments:
        moment["source_filename"] = source_info["filename"]
    now = _utc_now()
    project = {
        "schema": SCHEMA,
        "created_at": now,
        "updated_at": now,
        "edit_revision": 1,
        "synthetic_demo": bool(synthetic_demo),
        "source": source_info,
        "peer_contracts": {
            "cedar_trace": "kept source ranges in seconds or 30fps timeline rows",
            "kestrel_delta": "chronological nonoverlapping transcript segments {id,start,end,speaker?,text,verified?}",
        },
        "selection": {
            "mode": selection_mode,
            "requested_moments": moment_count,
            "distinct": True,
            "padding_ms": 150 if selection_mode == "transcript" else 0,
        },
        "moments": moments,
    }
    save_project(project_path, project)
    return project


def _find_moment(project: dict[str, Any], clip_id: str) -> dict[str, Any]:
    for moment in project["moments"]:
        if moment["id"] == clip_id:
            return moment
    raise ManagedClippingError(f"unknown clip id: {clip_id}")


def _parse_crop(value: str | dict[str, Any] | None) -> dict[str, float] | None:
    if value is None:
        return None
    if isinstance(value, dict):
        parts = [value.get(k) for k in ("x", "y", "w", "h")]
    else:
        parts = value.split(",")
    if len(parts) != 4:
        raise ManagedClippingError("crop must be x,y,w,h normalized fractions")
    x, y, w, h = map(float, parts)
    if not all(math.isfinite(v) for v in (x, y, w, h)):
        raise ManagedClippingError("crop values must be finite")
    if x < 0 or y < 0 or w <= 0 or h <= 0 or x + w > 1.000001 or y + h > 1.000001:
        raise ManagedClippingError("crop must fit inside normalized source frame")
    return {"x": round(x, 6), "y": round(y, 6), "w": round(w, 6), "h": round(h, 6)}


def edit_moment(
    project_path: Path,
    clip_id: str,
    *,
    start_ms: int | None = None,
    end_ms: int | None = None,
    caption: str | None = None,
    hook: str | None = None,
    crop: str | dict[str, Any] | None = None,
) -> dict[str, Any]:
    project = load_project(project_path)
    verify_source(project)
    moment = _find_moment(project, clip_id)
    new_start = int(start_ms if start_ms is not None else moment["start_ms"])
    new_end = int(end_ms if end_ms is not None else moment["end_ms"])
    if not (0 <= new_start < new_end <= project["source"]["duration_ms"]):
        raise ManagedClippingError("edited boundaries must stay inside the source")
    if new_end - new_start < 100:
        raise ManagedClippingError("clips shorter than 100ms are not supported")
    changed = False
    for key, value in (("start_ms", new_start), ("end_ms", new_end)):
        if moment[key] != value:
            moment[key] = value
            changed = True
    if caption is not None and moment["caption"] != caption:
        moment["caption"] = caption
        changed = True
    if hook is not None and moment["hook"] != hook:
        moment["hook"] = hook
        changed = True
    parsed_crop = _parse_crop(crop)
    if parsed_crop is not None and moment["crop"] != parsed_crop:
        moment["crop"] = parsed_crop
        changed = True
    if not changed:
        return project
    project["edit_revision"] += 1
    save_project(project_path, project)
    return project
