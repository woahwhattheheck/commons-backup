from __future__ import annotations
import math
from typing import Any
from managed_common import DEFAULT_FPS, ManagedClippingError

def normalize_kestrel_segments(document: Any) -> list[dict[str, Any]]:
    if isinstance(document, dict) and "document" in document and isinstance(document["document"], dict):
        document = document["document"]
    if isinstance(document, dict):
        segments = document.get("segments", [])
    elif isinstance(document, list):
        segments = document
    else:
        raise ManagedClippingError("transcript input must be a KESTREL document or segment list")
    if not isinstance(segments, list):
        raise ManagedClippingError("transcript segments must be a list of {id,start,end} objects")
    out: list[dict[str, Any]] = []
    last_end = -1.0
    seen: set[str] = set()
    for idx, row in enumerate(segments):
        if not isinstance(row, dict):
            raise ManagedClippingError(f"segment {idx + 1} is not an object with start and end seconds")
        sid = str(row.get("id", f"s{idx+1}"))
        if sid in seen:
            raise ManagedClippingError(f"duplicate segment id: {sid}")
        seen.add(sid)
        try:
            start = float(row["start"])
            end = float(row["end"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ManagedClippingError(
                f"segment {sid} needs numeric start and end seconds"
            ) from exc
        if not (math.isfinite(start) and math.isfinite(end) and 0 <= start < end):
            raise ManagedClippingError(
                f"invalid segment range for {sid}: start={start} end={end} (seconds, 0 <= start < end)"
            )
        if start < last_end - 1e-9:
            raise ManagedClippingError(
                f"transcript segments overlap or are not chronological at {sid}"
            )
        last_end = end
        out.append({
            "id": sid,
            "start_ms": int(round(start * 1000)),
            "end_ms": int(round(end * 1000)),
            "speaker": row.get("speaker"),
            "text": str(row.get("text", "")),
            "verified": bool(row.get("verified", False)),
        })
    return out


def normalize_cedar_keeps(raw: Any, fps: float = DEFAULT_FPS) -> list[tuple[int, int]]:
    if isinstance(raw, dict):
        if "kept" in raw:
            rows = raw["kept"]
            if not isinstance(rows, list):
                raise ManagedClippingError("CEDAR kept rows must be a list")
            intervals = []
            for idx, row in enumerate(rows):
                if not isinstance(row, dict) or "source_start" not in row or "source_end" not in row:
                    raise ManagedClippingError(
                        f"CEDAR kept row {idx + 1} needs source_start and source_end frame indexes"
                    )
                try:
                    start_ms = int(round(float(row["source_start"]) / fps * 1000))
                    end_ms = int(round(float(row["source_end"]) / fps * 1000))
                except (TypeError, ValueError) as exc:
                    raise ManagedClippingError(
                        f"CEDAR kept row {idx + 1} has non-numeric source_start/source_end"
                    ) from exc
                intervals.append((start_ms, end_ms))
        elif "timeline" in raw and isinstance(raw["timeline"], dict) and "kept" in raw["timeline"]:
            return normalize_cedar_keeps(raw["timeline"], fps=fps)
        elif "keep" in raw:
            return normalize_cedar_keeps(raw["keep"], fps=fps)
        else:
            raise ManagedClippingError("CEDAR keep input missing kept/keep rows")
    elif isinstance(raw, list):
        intervals = []
        for idx, pair in enumerate(raw):
            if not (isinstance(pair, (list, tuple)) and len(pair) == 2):
                raise ManagedClippingError(
                    f"CEDAR keep row {idx + 1} must be [start_seconds, end_seconds]"
                )
            try:
                start_ms = int(round(float(pair[0]) * 1000))
                end_ms = int(round(float(pair[1]) * 1000))
            except (TypeError, ValueError) as exc:
                raise ManagedClippingError(
                    f"CEDAR keep row {idx + 1} needs numeric start and end seconds"
                ) from exc
            intervals.append((start_ms, end_ms))
    else:
        raise ManagedClippingError("CEDAR keep input must be a list or timeline object")
    clean: list[tuple[int, int]] = []
    prev_end = -1
    for idx, (start, end) in enumerate(intervals):
        if start < 0 or end <= start:
            raise ManagedClippingError(
                f"invalid CEDAR keep range {idx + 1}: {start}ms–{end}ms (need 0 <= start < end)"
            )
        if start < prev_end:
            raise ManagedClippingError(
                f"CEDAR keep ranges must be chronological and nonoverlapping (row {idx + 1})"
            )
        clean.append((start, end))
        prev_end = end
    return clean


_PAD_MS = 150
_MIN_DISTINCT_MS = 250


def _containing_keep(
    start_ms: int, end_ms: int, keeps: list[tuple[int, int]]
) -> tuple[int, int] | None:
    for start, end in keeps:
        if start <= start_ms and end_ms <= end:
            return (start, end)
    return None


def _unique_spread(items: list[Any], count: int) -> list[Any]:
    n = len(items)
    if count > n:
        raise ManagedClippingError(
            f"only {n} distinct item(s) available; {count} requested"
        )
    if count == n:
        return list(items)
    if count == 1:
        return [items[n // 2]]
    used: set[int] = set()
    chosen_at: list[int] = []
    for i in range(count):
        idx = int(round(i * (n - 1) / (count - 1)))
        if idx in used:
            idx = -1
            for delta in range(1, n):
                for cand in (int(round(i * (n - 1) / (count - 1))) - delta,
                             int(round(i * (n - 1) / (count - 1))) + delta):
                    if 0 <= cand < n and cand not in used:
                        idx = cand
                        break
                if idx >= 0:
                    break
        if idx < 0 or idx in used:
            raise ManagedClippingError("could not choose distinct items without repetition")
        used.add(idx)
        chosen_at.append(idx)
    chosen_at.sort()
    return [items[i] for i in chosen_at]


def _choose_transcript_moments(
    segments: list[dict[str, Any]], keeps: list[tuple[int, int]], count: int, duration_ms: int
) -> list[dict[str, Any]]:
    """Unique source-contained cues. Keep ranges bound the cue and its padding.

    Never repeats a cue and never invents generic footage to fill `count`.
    """
    if duration_ms <= 0:
        raise ManagedClippingError("source duration must be positive before choosing cues")
    eligible: list[tuple[dict[str, Any], int, int]] = []
    for seg in segments:
        if seg["start_ms"] < 0 or seg["end_ms"] > duration_ms or seg["end_ms"] <= seg["start_ms"]:
            raise ManagedClippingError(
                f"segment {seg['id']} ({seg['start_ms']}–{seg['end_ms']}ms) "
                f"is outside the {duration_ms}ms source"
            )
        if keeps:
            bounds = _containing_keep(seg["start_ms"], seg["end_ms"], keeps)
            if bounds is None:
                continue
            bound_start, bound_end = bounds
        else:
            bound_start, bound_end = 0, duration_ms
        start = max(bound_start, seg["start_ms"] - _PAD_MS, 0)
        end = min(bound_end, seg["end_ms"] + _PAD_MS, duration_ms)
        if end <= start:
            continue
        eligible.append((seg, start, end))
    if len(eligible) < count:
        raise ManagedClippingError(
            f"only {len(eligible)} source-contained transcript cue(s) fit the keep ranges; "
            f"{count} distinct clip(s) were requested. "
            "Not repeating cues and not substituting generic footage."
        )
    picks = _unique_spread(eligible, count)
    moments: list[dict[str, Any]] = []
    seen: set[str] = set()
    for idx, (seg, start, end) in enumerate(picks, 1):
        if seg["id"] in seen:
            raise ManagedClippingError(f"refusing to repeat transcript cue {seg['id']}")
        seen.add(seg["id"])
        moments.append({
            "id": f"clip-{idx:03d}",
            "source_filename": None,
            "start_ms": start,
            "end_ms": end,
            "caption": seg["text"],
            "hook": seg["text"][:100],
            "crop": {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0},
            "transcript_refs": [seg["id"]],
            "enabled": True,
            "renders": [],
        })
    return moments


def _allocate_distinct(spans: list[tuple[int, int]], count: int) -> list[int]:
    lengths = [end - start for start, end in spans]
    total = sum(lengths)
    caps = [length // _MIN_DISTINCT_MS for length in lengths]
    if sum(caps) < count:
        raise ManagedClippingError(
            f"source/keep ranges have {total}ms usable across {len(spans)} span(s); "
            f"need at least {count * _MIN_DISTINCT_MS}ms for {count} distinct clips"
        )
    raw = [count * length / total for length in lengths]
    alloc = [min(cap, int(share)) for share, cap in zip(raw, caps)]
    leftover = count - sum(alloc)
    order = sorted(range(len(spans)), key=lambda i: (raw[i] - int(raw[i]), lengths[i]), reverse=True)
    guard = 0
    while leftover > 0 and guard < count + len(spans) + 2:
        progressed = False
        for i in order:
            if leftover <= 0:
                break
            if alloc[i] < caps[i]:
                alloc[i] += 1
                leftover -= 1
                progressed = True
        if not progressed:
            break
        guard += 1
    if leftover:
        raise ManagedClippingError(
            f"could not place {count} distinct in-range windows without overlap"
        )
    return alloc


def _choose_even_moments(keeps: list[tuple[int, int]], count: int, duration_ms: int) -> list[dict[str, Any]]:
    """Distinct non-overlapping windows. Used only when no transcript is supplied."""
    if duration_ms <= 0:
        raise ManagedClippingError("source duration must be positive before choosing clips")
    raw = keeps or [(0, duration_ms)]
    spans: list[tuple[int, int]] = []
    for start, end in raw:
        start = max(0, start)
        end = min(duration_ms, end)
        if end - start >= _MIN_DISTINCT_MS:
            spans.append((start, end))
    total = sum(end - start for start, end in spans)
    if not spans or total < count * _MIN_DISTINCT_MS:
        raise ManagedClippingError(
            f"source/keep ranges are too short to create {count} distinct clips "
            f"({total}ms usable, need {count * _MIN_DISTINCT_MS}ms)"
        )
    alloc = _allocate_distinct(spans, count)
    moments: list[dict[str, Any]] = []
    placed: list[tuple[int, int]] = []
    for (span_start, span_end), n in zip(spans, alloc):
        if n <= 0:
            continue
        span = span_end - span_start
        for j in range(n):
            start = span_start + (j * span) // n
            end = span_start + ((j + 1) * span) // n
            if end <= start:
                raise ManagedClippingError("distinct window collapsed to an empty range")
            if any(not (end <= prev_s or start >= prev_e) for prev_s, prev_e in placed):
                raise ManagedClippingError("refusing overlapping generic clip windows")
            placed.append((start, end))
            i = len(moments) + 1
            moments.append({
                "id": f"clip-{i:03d}",
                "source_filename": None,
                "start_ms": start,
                "end_ms": end,
                "caption": f"Clip {i}",
                "hook": f"Moment {i}",
                "crop": {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0},
                "transcript_refs": [],
                "enabled": True,
                "renders": [],
            })
    if len(moments) != count:
        raise ManagedClippingError(
            f"expected {count} distinct generic clips, placed {len(moments)}"
        )
    return moments
