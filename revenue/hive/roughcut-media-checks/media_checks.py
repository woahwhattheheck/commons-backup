#!/usr/bin/env python3
"""Generate owned A/V pulse fixtures and measure edited renders against source-time keep ranges.

This is a companion to a real editor, not an editor or a natural-speech quality score.
Requires Python 3.10+, FFmpeg (libx264), and ffprobe. No Python dependencies.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
import uuid
from pathlib import Path


class MediaCheckError(ValueError):
    pass


def finite(value, label):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise MediaCheckError(f"{label} must be a finite number")
    return float(value)


def command(args, timeout=600):
    try:
        result = subprocess.run(args, text=True, capture_output=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise MediaCheckError(f"Media command unavailable or timed out: {exc}") from exc
    if result.returncode:
        raise MediaCheckError(result.stderr[-3000:] or "Media command failed")
    return result.stdout


def sha256(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def probe(path):
    data = json.loads(command(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)], 60))
    duration = finite(float(data.get("format", {}).get("duration", 0)), "media duration")
    if not 0 < duration <= 7200:
        raise MediaCheckError("Media duration must be in (0, 7200] seconds")
    kinds = {s.get("codec_type") for s in data.get("streams", [])}
    if not {"audio", "video"}.issubset(kinds):
        raise MediaCheckError("The pulse fixture/render must have both audio and video")
    return {"duration": duration, "streams": data["streams"]}


def generate(path, seconds=1200, fps=25, first=2, period=60, pulse=.24):
    """Generate black video with white flashes and aligned 997 Hz audio pulses."""
    seconds, first, period, pulse = (finite(v, n) for v, n in [(seconds, "seconds"), (first, "first"), (period, "period"), (pulse, "pulse")])
    if type(fps) is not int or not 10 <= fps <= 60:
        raise MediaCheckError("fps must be an integer from 10 through 60")
    if not (0 < seconds <= 7200 and 0 <= first and 2 / fps <= pulse < period and first + pulse < seconds):
        raise MediaCheckError("Use 0 < seconds <= 7200, first >= 0, 2/fps <= pulse < period, and first+pulse < seconds")
    path = Path(path).resolve()
    manifest_path = path.with_suffix(path.suffix + ".fixture.json")
    if path.exists() or manifest_path.exists():
        raise MediaCheckError("Choose a new output filename; existing media and manifests are preserved")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(uuid.uuid4().hex + ".mp4")
    count = math.floor((seconds - first - pulse) / period) + 1
    last_end = first + (count - 1) * period + pulse
    gate = f"gte(t,{first})*lt(t,{last_end})*lt(mod(t-{first},{period}),{pulse})"
    audio_gate = gate.replace(",", "\\,")
    args = ["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=black:size=160x90:rate={fps}:duration={seconds}", "-f", "lavfi", "-i", f"aevalsrc=0.6*sin(2*PI*997*t)*{audio_gate}:s=48000:d={seconds}", "-vf", f"drawbox=x=0:y=0:w=iw:h=ih:color=white:t=fill:enable='{gate}'", "-c:v", "libx264", "-threads", "1", "-preset", "fast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-t", str(seconds), "-movflags", "+faststart", str(temporary)]
    try:
        command(args)
        # Exclusive creation preserves another writer's media, rather than replacing it.
        with path.open("xb") as target, temporary.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                target.write(chunk)
    finally:
        temporary.unlink(missing_ok=True)
    manifest = {"schema": "roughcut-pulse-fixture/1", "synthetic": True, "source_sha256": sha256(path), "duration": seconds, "fps": fps, "pulse_seconds": pulse, "source_markers": [round(first + i * period, 9) for i in range(count)], "description": "Internally generated white flashes and 997 Hz tones, not a person or customer recording."}
    with manifest_path.open("x", encoding="utf-8") as target:
        json.dump(manifest, target, indent=2, allow_nan=False)
        target.write("\n")
    return manifest


def _rising_edges(text, key, threshold):
    """Use decoded frame/block presentation timestamps, not assumed constant-rate indices."""
    output, timestamp, was_high = [], None, False
    for line in text.splitlines():
        match = re.search(r"\bpts_time:([^\s]+)", line)
        if match:
            timestamp = float(match[1])
        elif line.startswith(key + "=") and timestamp is not None:
            value = float(line.split("=", 1)[1])
            high = value > threshold
            if high and not was_high:
                output.append(timestamp)
            was_high = high
    return output


def detect(path):
    """Decode actual pixels and 10 ms audio RMS blocks; only meaningful for pulse fixtures."""
    probe(path)
    video = command(["ffmpeg", "-nostdin", "-v", "error", "-i", str(path), "-an", "-vf", "scale=8:8:flags=area,signalstats,metadata=print:key=lavfi.signalstats.YAVG:file=-", "-f", "null", "-"])
    audio = command(["ffmpeg", "-nostdin", "-v", "error", "-i", str(path), "-vn", "-af", "aresample=8000,asetnsamples=n=80:p=0,astats=metadata=1:reset=1,ametadata=print:key=lavfi.astats.Overall.RMS_level:file=-", "-f", "null", "-"])
    return {"video": _rising_edges(video, "lavfi.signalstats.YAVG", 128), "audio": _rising_edges(audio, "lavfi.astats.Overall.RMS_level", -25)}


def plan(manifest, keep):
    """Map retained marker events into contiguous output time. Cuts must avoid marker pulses."""
    if not isinstance(manifest, dict) or manifest.get("schema") != "roughcut-pulse-fixture/1" or manifest.get("synthetic") is not True:
        raise MediaCheckError("A generated roughcut-pulse-fixture/1 manifest is required")
    duration = finite(manifest.get("duration"), "source duration")
    pulse = finite(manifest.get("pulse_seconds"), "pulse duration")
    fps = finite(manifest.get("fps"), "fps")
    markers = manifest.get("source_markers")
    if duration <= 0 or pulse <= 0 or fps <= 0 or not isinstance(markers, list) or not markers:
        raise MediaCheckError("Manifest needs positive timing fields and a nonempty marker list")
    previous = -1.0
    for value in markers:
        value = finite(value, "source marker")
        if not previous < value or not 0 <= value < value + pulse <= duration:
            raise MediaCheckError("Source markers must increase and fit inside the recording")
        previous = value
    if not isinstance(keep, list) or not keep or len(keep) > 256:
        raise MediaCheckError("keep must be a nonempty array of at most 256 [start, end] ranges")
    segments, expected, offset, previous_end = [], [], 0.0, 0.0
    for row in keep:
        if not isinstance(row, list) or len(row) != 2:
            raise MediaCheckError("Each keep range must be [source_start, source_end]")
        start, end = finite(row[0], "range start"), finite(row[1], "range end")
        if not previous_end <= start < end <= duration:
            raise MediaCheckError("Keep ranges must be ordered, nonoverlapping and within the source")
        for marker in markers:
            # Leave one video frame beyond a pulse for encoder/filter rounding.
            protected_end = min(duration, marker + pulse + 1 / fps)
            if start < protected_end and end > marker:
                if start > marker or end < protected_end:
                    raise MediaCheckError("A cut intersects a marker pulse; move this synthetic-test cut into a gap")
                expected.append(round(offset + marker - start, 9))
        segments.append({"source_start": start, "source_end": end, "output_start": offset, "output_end": offset + end - start})
        offset += end - start
        previous_end = end
    if not expected:
        raise MediaCheckError("Keep at least one complete pulse to measure synchronization")
    return {"segments": segments, "duration": offset, "expected_markers": expected}


def verify(source, rendered, manifest, keep, tolerance=.08):
    tolerance = finite(tolerance, "tolerance")
    if not 0 < tolerance <= 1:
        raise MediaCheckError("Tolerance must be in (0, 1] seconds")
    expected = plan(manifest, keep)
    source_before = sha256(source)
    expected_hash = manifest.get("source_sha256")
    if not isinstance(expected_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_hash):
        raise MediaCheckError("Manifest source_sha256 must be a lowercase SHA-256 digest")
    if source_before != expected_hash:
        return {"passed": False, "source_unchanged": False, "reason": "Original source differs from the generated fixture manifest"}
    render_before = sha256(rendered)
    observed = detect(rendered)
    metadata = probe(rendered)
    target = expected["expected_markers"]
    counts_match = len(target) == len(observed["video"]) == len(observed["audio"])
    errors = {kind: [round(actual - planned, 9) for actual, planned in zip(observed[kind], target)] for kind in ("video", "audio")}
    av_offsets = [round(audio - video, 9) for audio, video in zip(observed["audio"], observed["video"])]
    duration_error = metadata["duration"] - expected["duration"]
    source_unchanged = sha256(source) == source_before
    render_after = sha256(rendered)
    checks = {"render_unchanged_during_check": render_before == render_after, "source_unchanged": source_unchanged, "marker_counts_match": counts_match, "video_timing": counts_match and all(abs(v) <= tolerance for v in errors["video"]), "audio_timing": counts_match and all(abs(v) <= tolerance for v in errors["audio"]), "av_alignment": counts_match and all(abs(v) <= tolerance for v in av_offsets), "duration": abs(duration_error) <= max(tolerance, 2 / manifest["fps"])}
    return {"passed": all(checks.values()), "checks": checks, "source_sha256": source_before, "render_sha256": render_after, "expected": expected, "observed_markers": observed, "timing_errors_seconds": errors, "audio_minus_video_seconds": av_offsets, "measured_duration": metadata["duration"], "duration_error_seconds": round(duration_error, 9), "tolerance_seconds": tolerance, "scope": "Decoded synthetic pulse timing and source preservation only; not natural-speech coherence, browser acceptance, or customer delivery."}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    generate_parser = commands.add_parser("generate", help="Create an owned synthetic recording and checksum manifest")
    generate_parser.add_argument("output", type=Path)
    generate_parser.add_argument("--seconds", type=float, default=1200)
    generate_parser.add_argument("--fps", type=int, default=25)
    generate_parser.add_argument("--first", type=float, default=2)
    generate_parser.add_argument("--period", type=float, default=60)
    generate_parser.add_argument("--pulse", type=float, default=.24)
    verify_parser = commands.add_parser("verify", help="Check an editor-produced render")
    verify_parser.add_argument("source", type=Path)
    verify_parser.add_argument("rendered", type=Path)
    verify_parser.add_argument("--manifest", type=Path, required=True)
    verify_parser.add_argument("--keep", type=Path, required=True, help="JSON array of original-source [start, end] seconds")
    verify_parser.add_argument("--tolerance", type=float, default=.08)
    verify_parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.action == "generate":
            result = generate(args.output, args.seconds, args.fps, args.first, args.period, args.pulse)
        else:
            result = verify(args.source, args.rendered, json.loads(args.manifest.read_text(encoding="utf-8")), json.loads(args.keep.read_text(encoding="utf-8")), args.tolerance)
        text = json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
        if args.action == "verify" and args.report:
            args.report.write_text(text, encoding="utf-8")
        print(text, end="")
        return 0 if result.get("passed", True) else 1
    except (MediaCheckError, OSError, ValueError, KeyError) as exc:
        print(json.dumps({"passed": False, "input_or_execution_error": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
