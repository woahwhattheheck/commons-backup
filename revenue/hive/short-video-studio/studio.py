#!/usr/bin/env python3
"""Local-first short-video project validator and FFmpeg renderer.

Projects stay editable as JSON + SRT. Rendering accepts only local files under the
project directory and never performs network access or publishing.
"""
from __future__ import annotations

import argparse
import json
import math
import pathlib
import re
import shutil
import subprocess
import tempfile
from typing import Any

PRESETS = {
    "vertical": (360, 640),
    "square": (480, 480),
    "landscape": (640, 360),
}
HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".aac", ".ogg", ".flac"}


class ProjectError(ValueError):
    pass


def _finite_number(value: Any, label: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ProjectError(f"{label} must be a finite number")
    try:
        number = float(value)
    except (OverflowError, ValueError) as exc:
        raise ProjectError(f"{label} must be a finite number") from exc
    if not math.isfinite(number):
        raise ProjectError(f"{label} must be a finite number")
    return number


def _within(root: pathlib.Path, candidate: pathlib.Path) -> pathlib.Path:
    root = root.resolve()
    candidate = candidate.resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ProjectError(f"path escapes project directory: {candidate}") from exc
    return candidate


def _local_file(root: pathlib.Path, value: str, allowed: set[str]) -> pathlib.Path:
    if not isinstance(value, str) or not value.strip():
        raise ProjectError("local file path must be a nonempty string")
    path = _within(root, root / value)
    if path.suffix.lower() not in allowed:
        raise ProjectError(f"unsupported file type: {path.suffix}")
    if not path.is_file():
        raise ProjectError(f"missing local file: {value}")
    return path


def validate_project(project: dict[str, Any], project_dir: pathlib.Path) -> dict[str, Any]:
    if not isinstance(project, dict):
        raise ProjectError("project must be a JSON object")
    title = project.get("title")
    if not isinstance(title, str) or not title.strip():
        raise ProjectError("title is required")
    preset = project.get("preset", "vertical")
    if preset not in PRESETS:
        raise ProjectError(f"preset must be one of {', '.join(PRESETS)}")
    fps = project.get("fps", 12)
    if not isinstance(fps, int) or not 6 <= fps <= 60:
        raise ProjectError("fps must be an integer from 6 to 60")
    segments = project.get("segments")
    if not isinstance(segments, list) or not segments:
        raise ProjectError("segments must be a nonempty list")

    cursor = 0.0
    normalized: list[dict[str, Any]] = []
    for index, raw in enumerate(segments, 1):
        if not isinstance(raw, dict):
            raise ProjectError(f"segment {index} must be an object")
        duration = _finite_number(raw.get("duration"), f"segment {index} duration")
        if duration <= 0:
            raise ProjectError(f"segment {index} duration must be positive")
        text = raw.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ProjectError(f"segment {index} text is required")
        color = raw.get("color", "#20242a")
        if not isinstance(color, str) or not HEX_COLOR.fullmatch(color):
            raise ProjectError(f"segment {index} color must be #RRGGBB")
        asset = raw.get("asset")
        asset_path = None
        if asset is not None:
            asset_path = _local_file(project_dir, asset, IMAGE_EXTS)
        start = cursor
        cursor += duration
        normalized.append(
            {
                "duration": duration,
                "text": text.strip(),
                "color": color,
                "asset": str(asset_path) if asset_path else None,
                "start": start,
                "end": cursor,
            }
        )

    if not 30.0 <= cursor <= 60.0:
        raise ProjectError(f"total duration must be 30-60 seconds; got {cursor:.3f}")

    audio = project.get("audio", {"kind": "tone", "frequency": 220, "volume": 0.03})
    if not isinstance(audio, dict):
        raise ProjectError("audio must be an object")
    kind = audio.get("kind", "tone")
    normalized_audio: dict[str, Any]
    if kind == "tone":
        frequency = _finite_number(audio.get("frequency", 220), "tone frequency")
        volume = _finite_number(audio.get("volume", 0.03), "tone volume")
        if not 40 <= frequency <= 2000:
            raise ProjectError("tone frequency must be 40-2000 Hz")
        if not 0 <= volume <= 1:
            raise ProjectError("tone volume must be 0-1")
        normalized_audio = {"kind": "tone", "frequency": frequency, "volume": volume}
    elif kind == "file":
        source = _local_file(project_dir, audio.get("path"), AUDIO_EXTS)
        normalized_audio = {"kind": "file", "path": str(source)}
    else:
        raise ProjectError("audio.kind must be tone or file")

    return {
        "title": title.strip(),
        "preset": preset,
        "width": PRESETS[preset][0],
        "height": PRESETS[preset][1],
        "fps": fps,
        "duration": cursor,
        "segments": normalized,
        "audio": normalized_audio,
    }


def _srt_stamp(seconds: float) -> str:
    milliseconds = max(0, int(round(seconds * 1000)))
    hours, milliseconds = divmod(milliseconds, 3_600_000)
    minutes, milliseconds = divmod(milliseconds, 60_000)
    secs, milliseconds = divmod(milliseconds, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"


def write_srt(normalized: dict[str, Any], path: pathlib.Path) -> None:
    blocks = []
    for index, segment in enumerate(normalized["segments"], 1):
        blocks.append(
            f"{index}\n{_srt_stamp(segment['start'])} --> {_srt_stamp(segment['end'])}\n{segment['text']}\n"
        )
    path.write_text("\n".join(blocks) + "\n", encoding="utf-8")


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=True, text=True, capture_output=True)


def _paths_alias(left: pathlib.Path, right: pathlib.Path) -> bool:
    """Return True for the same canonical path or the same existing file."""
    left = left.resolve()
    right = right.resolve()
    if left == right:
        return True
    try:
        return left.exists() and right.exists() and left.samefile(right)
    except OSError:
        return False


def _guard_render_outputs(
    project_path: pathlib.Path,
    output_path: pathlib.Path,
    srt_path: pathlib.Path,
    normalized: dict[str, Any],
) -> None:
    protected: list[tuple[str, pathlib.Path]] = [("project", project_path)]
    for index, segment in enumerate(normalized["segments"], 1):
        if segment["asset"]:
            protected.append((f"segment {index} asset", pathlib.Path(segment["asset"])))
    if normalized["audio"]["kind"] == "file":
        protected.append(("audio source", pathlib.Path(normalized["audio"]["path"])))

    if _paths_alias(output_path, srt_path):
        raise ProjectError("render output and caption output must be distinct files")
    for output_label, candidate in (("render output", output_path), ("caption output", srt_path)):
        for source_label, source in protected:
            if _paths_alias(candidate, source):
                raise ProjectError(f"{output_label} aliases protected {source_label}: {candidate}")


def render_project(project_path: pathlib.Path, output_path: pathlib.Path) -> dict[str, Any]:
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise RuntimeError("ffmpeg and ffprobe are required")
    project_path = project_path.resolve()
    project_dir = project_path.parent
    project = json.loads(project_path.read_text(encoding="utf-8"))
    normalized = validate_project(project, project_dir)
    output_path = output_path.resolve()
    srt_path = output_path.with_suffix(".srt")
    _guard_render_outputs(project_path, output_path, srt_path, normalized)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_srt(normalized, srt_path)

    width, height, fps = normalized["width"], normalized["height"], normalized["fps"]
    total = normalized["duration"]
    inputs: list[str] = []
    filters: list[str] = []
    video_labels: list[str] = []
    for index, segment in enumerate(normalized["segments"]):
        if segment["asset"]:
            inputs += ["-loop", "1", "-t", f"{segment['duration']:.3f}", "-i", segment["asset"]]
            filters.append(
                f"[{index}:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps},"
                f"trim=duration={segment['duration']:.3f},setpts=PTS-STARTPTS[v{index}]"
            )
        else:
            color = segment["color"].replace("#", "0x")
            inputs += ["-f", "lavfi", "-i", f"color=c={color}:s={width}x{height}:r={fps}:d={segment['duration']:.3f}"]
            filters.append(f"[{index}:v]setsar=1,setpts=PTS-STARTPTS[v{index}]")
        video_labels.append(f"[v{index}]")
    filters.append("".join(video_labels) + f"concat=n={len(video_labels)}:v=1:a=0[vout]")

    audio_input_index = len(normalized["segments"])
    audio = normalized["audio"]
    if audio["kind"] == "tone":
        inputs += [
            "-f", "lavfi", "-i",
            f"sine=frequency={audio['frequency']:.3f}:sample_rate=48000:duration={total:.3f}",
        ]
        audio_filter = f"[{audio_input_index}:a]volume={audio['volume']:.6f}[aout]"
    else:
        inputs += ["-i", audio["path"]]
        audio_filter = f"[{audio_input_index}:a]atrim=duration={total:.3f},asetpts=PTS-STARTPTS[aout]"
    filters.append(audio_filter)

    with tempfile.TemporaryDirectory(prefix="short-video-") as temp_dir:
        base = pathlib.Path(temp_dir) / "base.mp4"
        render_cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            *inputs,
            "-filter_complex", ";".join(filters),
            "-map", "[vout]", "-map", "[aout]",
            "-t", f"{total:.3f}",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "34",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "32k",
            "-movflags", "+faststart", str(base),
        ]
        _run(render_cmd)
        mux_cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(base), "-i", str(srt_path),
            "-map", "0:v", "-map", "0:a", "-map", "1:0",
            "-c:v", "copy", "-c:a", "copy", "-c:s", "mov_text",
            "-metadata:s:s:0", "language=eng", "-movflags", "+faststart",
            str(output_path),
        ]
        _run(mux_cmd)

    probe = _run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration,size:stream=codec_type,codec_name,width,height",
        "-of", "json", str(output_path),
    ])
    metadata = json.loads(probe.stdout)
    return {
        "project": normalized,
        "output": str(output_path),
        "captions": str(srt_path),
        "probe": metadata,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("validate")
    check.add_argument("project", type=pathlib.Path)
    render = sub.add_parser("render")
    render.add_argument("project", type=pathlib.Path)
    render.add_argument("output", type=pathlib.Path)
    args = parser.parse_args()
    if args.command == "validate":
        project_path = args.project.resolve()
        project = json.loads(project_path.read_text(encoding="utf-8"))
        normalized = validate_project(project, project_path.parent)
        print(json.dumps(normalized, indent=2, ensure_ascii=False))
        return 0
    result = render_project(args.project, args.output)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
