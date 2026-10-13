from __future__ import annotations
import csv, json, shutil
from pathlib import Path
from typing import Any, Iterable
from managed_common import ManagedClippingError, _json_dump, _run, _sha256, _utc_now, load_project, save_project, verify_source
from managed_project import _find_moment

def _crop_filter(source: dict[str, Any], crop: dict[str, Any]) -> str | None:
    if crop == {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0}:
        return None
    width, height = int(source["width"]), int(source["height"])
    x = max(0, min(width - 2, int(round(width * float(crop["x"])))))
    y = max(0, min(height - 2, int(round(height * float(crop["y"])))))
    w = max(2, min(width - x, int(round(width * float(crop["w"])))))
    h = max(2, min(height - y, int(round(height * float(crop["h"])))))
    x -= x % 2
    y -= y % 2
    w -= w % 2
    h -= h % 2
    if w < 2 or h < 2:
        raise ManagedClippingError("crop resolves to an empty frame")
    return f"crop={w}:{h}:{x}:{y}"


def _srt_text(caption: str, duration_ms: int) -> str:
    def stamp(ms: int) -> str:
        hours, ms = divmod(ms, 3_600_000)
        minutes, ms = divmod(ms, 60_000)
        seconds, millis = divmod(ms, 1000)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"
    clean = caption.replace("\r\n", "\n").replace("\r", "\n").strip() or "(no caption)"
    return f"1\n00:00:00,000 --> {stamp(duration_ms)}\n{clean}\n"


def _probe_render(path: Path) -> dict[str, Any]:
    proc = _run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)])
    raw = json.loads(proc.stdout)
    duration = float(raw["format"]["duration"])
    return {"duration_ms": int(round(duration * 1000)), "size": path.stat().st_size, "sha256": _sha256(path)}


def render_project(project_path: Path, output_root: Path, clip_ids: Iterable[str] | None = None) -> list[dict[str, Any]]:
    project = load_project(project_path)
    source_path = verify_source(project)
    selected = list(clip_ids or [m["id"] for m in project["moments"] if m.get("enabled", True)])
    if not selected:
        raise ManagedClippingError("no clips selected for rendering")
    revision = int(project["edit_revision"])
    revision_dir = output_root.resolve() / f"rev-{revision:04d}"
    revision_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    for clip_id in selected:
        moment = _find_moment(project, clip_id)
        if not moment.get("enabled", True):
            continue
        destination = revision_dir / f"{clip_id}.mp4"
        caption_path = revision_dir / f"{clip_id}.srt"
        metadata_path = revision_dir / f"{clip_id}.json"
        for path in (destination, caption_path, metadata_path):
            if path.exists():
                raise ManagedClippingError(f"refusing to overwrite existing render artifact: {path}")
        start_seconds = moment["start_ms"] / 1000.0
        duration_seconds = (moment["end_ms"] - moment["start_ms"]) / 1000.0
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-ss", f"{start_seconds:.3f}", "-i", str(source_path), "-t", f"{duration_seconds:.3f}",
        ]
        vf = _crop_filter(project["source"], moment["crop"])
        if vf:
            cmd += ["-vf", vf]
        cmd += [
            "-map", "0:v:0", "-map", "0:a?", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
            "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(destination),
        ]
        _run(cmd)
        if not destination.is_file() or destination.stat().st_size == 0:
            raise ManagedClippingError(f"render failed to produce playable bytes: {clip_id}")
        info = _probe_render(destination)
        if info["duration_ms"] < 80:
            raise ManagedClippingError(f"render duration too short: {clip_id}")
        caption_path.write_text(_srt_text(moment["caption"], info["duration_ms"]), encoding="utf-8")
        record = {
            "clip_id": clip_id,
            "edit_revision": revision,
            "source_filename": project["source"]["filename"],
            "source_sha256": project["source"]["sha256"],
            "start_ms": moment["start_ms"],
            "end_ms": moment["end_ms"],
            "caption": moment["caption"],
            "hook": moment["hook"],
            "crop": moment["crop"],
            "video_path": str(destination),
            "caption_path": str(caption_path),
            "render": info,
            "created_at": _utc_now(),
        }
        _json_dump(metadata_path, record)
        moment.setdefault("renders", []).append(record)
        results.append(record)
    save_project(project_path, project)
    return results


def _latest_render(moment: dict[str, Any]) -> dict[str, Any] | None:
    renders = moment.get("renders", [])
    return renders[-1] if renders else None


def export_handoff(project_path: Path, destination: Path) -> dict[str, Any]:
    project = load_project(project_path)
    verify_source(project)
    if destination.exists():
        raise ManagedClippingError(f"handoff destination already exists: {destination}")
    selected = []
    for moment in project["moments"]:
        if not moment.get("enabled", True):
            continue
        render = _latest_render(moment)
        if render is None:
            raise ManagedClippingError(f"clip has no rendered video: {moment['id']}")
        expected = {
            "clip_id": moment["id"],
            "source_filename": moment["source_filename"],
            "source_sha256": project["source"]["sha256"],
            "start_ms": moment["start_ms"],
            "end_ms": moment["end_ms"],
            "caption": moment["caption"],
            "crop": moment["crop"],
        }
        changed = [key for key, value in expected.items() if render.get(key) != value]
        if changed:
            raise ManagedClippingError(
                f"clip {moment['id']} render is stale ({', '.join(changed)}); "
                "rerender that clip before handoff"
            )
        src_video = Path(render["video_path"])
        src_caption = Path(render["caption_path"])
        if not src_video.is_file() or not src_caption.is_file():
            raise ManagedClippingError(f"render artifact missing for {moment['id']}")
        selected.append((moment, render, src_video, src_caption))
    if not selected:
        raise ManagedClippingError("no enabled clips selected for handoff")

    destination.mkdir(parents=True)
    videos_dir = destination / "videos"
    captions_dir = destination / "captions"
    videos_dir.mkdir()
    captions_dir.mkdir()
    rows: list[dict[str, Any]] = []
    manifest_clips: list[dict[str, Any]] = []
    for moment, render, src_video, src_caption in selected:
        video_dst = videos_dir / f"{moment['id']}.mp4"
        caption_dst = captions_dir / f"{moment['id']}.srt"
        shutil.copy2(src_video, video_dst)
        shutil.copy2(src_caption, caption_dst)
        rows.append({
            "clip_id": moment["id"],
            "source_filename": moment["source_filename"],
            "start_ms": moment["start_ms"],
            "end_ms": moment["end_ms"],
            "caption": moment["caption"],
            "hook": moment["hook"],
            "crop_x": moment["crop"]["x"],
            "crop_y": moment["crop"]["y"],
            "crop_w": moment["crop"]["w"],
            "crop_h": moment["crop"]["h"],
            "video": f"videos/{video_dst.name}",
            "caption_file": f"captions/{caption_dst.name}",
            "render_revision": render["edit_revision"],
        })
        manifest_clips.append({
            "clip_id": moment["id"],
            "video_sha256": _sha256(video_dst),
            "caption_sha256": _sha256(caption_dst),
            "render_revision": render["edit_revision"],
        })
    with (destination / "clips.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    _json_dump(destination / "project.json", project)
    manifest = {
        "schema": "managed-clipping-handoff-v1",
        "created_at": _utc_now(),
        "synthetic_demo": project["synthetic_demo"],
        "source": {
            "filename": project["source"]["filename"],
            "sha256": project["source"]["sha256"],
            "size": project["source"]["size"],
        },
        "clip_count": len(rows),
        "clips": manifest_clips,
    }
    _json_dump(destination / "manifest.json", manifest)
    (destination / "README.txt").write_text(
        "Managed Clipping customer handoff\n"
        "\n"
        "videos/ contains the latest playable render for each clip.\n"
        "captions/ contains editable SRT caption files.\n"
        "clips.csv and project.json preserve source filename, millisecond boundaries, captions, hooks and crops.\n"
        "Synthetic demo: " + ("YES\n" if project["synthetic_demo"] else "NO\n"),
        encoding="utf-8",
    )
    return manifest
