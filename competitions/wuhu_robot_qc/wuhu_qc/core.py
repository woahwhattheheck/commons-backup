from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import cv2
import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Finding:
    category: str
    code: str
    severity: str
    episode_index: int
    start_frame: int | None
    end_frame: int | None
    detail: str
    metric: float | None = None


@dataclass
class EpisodeReport:
    episode_index: int
    frame_count: int
    duration_s: float | None
    findings: list[Finding] = field(default_factory=list)
    quality_score: float = 100.0
    value_score: float = 100.0
    category_scores: dict[str, float] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["findings"] = [asdict(f) for f in self.findings]
        return d


SEVERITY_WEIGHT = {"info": 0.0, "low": 0.35, "medium": 0.7, "high": 1.0}
CATEGORY_BUDGET = {
    "temporal": 25.0,
    "sync": 20.0,
    "structure": 20.0,
    "visual": 20.0,
    "dynamics": 15.0,
}


def _finite_scalar(value: Any) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _as_numeric_matrix(series: pd.Series) -> np.ndarray | None:
    rows: list[np.ndarray] = []
    width: int | None = None
    for value in series.tolist():
        try:
            arr = np.asarray(value, dtype=np.float64).reshape(-1)
        except (TypeError, ValueError):
            return None
        if width is None:
            width = arr.size
        if arr.size != width:
            return None
        rows.append(arr)
    if not rows:
        return np.empty((0, 0), dtype=np.float64)
    return np.vstack(rows)


def validate_schema(df: pd.DataFrame, episode_index: int, expected_shapes: Mapping[str, Sequence[int]] | None = None) -> list[Finding]:
    findings: list[Finding] = []
    required = ["timestamp", "frame_index", "episode_index", "task_index"]
    for name in required:
        if name not in df.columns:
            findings.append(Finding("structure", "MISSING_COLUMN", "high", episode_index, None, None, f"missing required column {name}"))
    if df.empty:
        findings.append(Finding("structure", "EMPTY_EPISODE", "high", episode_index, None, None, "episode has zero rows"))
        return findings

    if "episode_index" in df.columns:
        values = pd.unique(df["episode_index"])
        bad = [v for v in values if _finite_scalar(v) is None or int(v) != episode_index]
        if bad or len(values) != 1:
            findings.append(Finding("structure", "EPISODE_ID_MISMATCH", "high", episode_index, None, None, f"episode_index column does not equal file episode {episode_index}"))

    if expected_shapes:
        for key, shape in expected_shapes.items():
            if key not in df.columns or not shape:
                continue
            expected = int(np.prod(shape))
            mat = _as_numeric_matrix(df[key])
            if mat is None:
                findings.append(Finding("structure", "INCONSISTENT_VECTOR_SHAPE", "high", episode_index, None, None, f"{key} contains inconsistent/non-numeric vectors"))
            elif mat.shape[1] != expected:
                findings.append(Finding("structure", "FEATURE_SHAPE_MISMATCH", "high", episode_index, None, None, f"{key} width={mat.shape[1]} expected={expected}"))
    return findings


def temporal_findings(df: pd.DataFrame, episode_index: int, fps: float) -> list[Finding]:
    findings: list[Finding] = []
    if df.empty or "frame_index" not in df or "timestamp" not in df:
        return findings
    frames = pd.to_numeric(df["frame_index"], errors="coerce").to_numpy(dtype=np.float64)
    ts = pd.to_numeric(df["timestamp"], errors="coerce").to_numpy(dtype=np.float64)
    if not np.all(np.isfinite(frames)) or not np.all(np.isfinite(ts)):
        findings.append(Finding("temporal", "NONFINITE_INDEX_OR_TIMESTAMP", "high", episode_index, None, None, "frame_index/timestamp contains NaN or infinity"))
        return findings
    frame_steps = np.diff(frames)
    bad_order = np.where(frame_steps <= 0)[0]
    if bad_order.size:
        i = int(bad_order[0])
        findings.append(Finding("temporal", "FRAME_ORDER_REGRESSION", "high", episode_index, int(frames[i]), int(frames[i+1]), "frame_index is repeated or decreases", float(frame_steps[i])))
    gaps = np.where(frame_steps > 1)[0]
    if gaps.size:
        missing = float(np.sum(frame_steps[gaps] - 1))
        findings.append(Finding("temporal", "FRAME_GAP", "high", episode_index, int(frames[gaps[0]]), int(frames[gaps[-1]+1]), f"estimated {int(missing)} missing frame indices", missing))

    dt = np.diff(ts)
    reg = np.where(dt <= 0)[0]
    if reg.size:
        i = int(reg[0])
        findings.append(Finding("temporal", "TIMESTAMP_REGRESSION", "high", episode_index, int(frames[i]), int(frames[i+1]), "timestamp is repeated or decreases", float(dt[i])))
    if dt.size and fps > 0 and np.all(dt > 0):
        expected = 1.0 / fps
        median = float(np.median(dt))
        jitter = float(np.median(np.abs(dt - median)))
        rel = jitter / max(expected, 1e-12)
        if abs(median - expected) / expected > 0.15:
            findings.append(Finding("temporal", "FPS_MISMATCH", "medium", episode_index, int(frames[0]), int(frames[-1]), f"median dt={median:.6g}s differs from declared fps={fps:g}", median))
        if rel > 0.10:
            findings.append(Finding("temporal", "TIMESTAMP_JITTER", "medium", episode_index, int(frames[0]), int(frames[-1]), f"median absolute dt jitter is {rel:.1%} of expected interval", rel))
    return findings


def numeric_findings(df: pd.DataFrame, episode_index: int, feature_keys: Iterable[str]) -> list[Finding]:
    findings: list[Finding] = []
    for key in feature_keys:
        if key not in df.columns:
            continue
        mat = _as_numeric_matrix(df[key])
        if mat is None:
            findings.append(Finding("structure", "NON_NUMERIC_FEATURE", "high", episode_index, None, None, f"{key} could not be represented as a fixed numeric vector"))
            continue
        if mat.size == 0:
            continue
        nonfinite = ~np.isfinite(mat)
        if np.any(nonfinite):
            rows = np.unique(np.where(nonfinite)[0])
            findings.append(Finding("structure", "NONFINITE_FEATURE", "high", episode_index, int(rows[0]), int(rows[-1]), f"{key} contains {int(nonfinite.sum())} NaN/inf values", float(nonfinite.sum())))
            continue
        if len(mat) >= 3:
            delta = np.diff(mat, axis=0)
            mag = np.linalg.norm(delta, axis=1)
            med = float(np.median(mag))
            mad = float(np.median(np.abs(mag - med)))
            scale = max(1.4826 * mad, 1e-9)
            robust_z = (mag - med) / scale
            spikes = np.where(robust_z > 12.0)[0]
            if spikes.size:
                findings.append(Finding("dynamics", "MOTION_SPIKE", "medium", episode_index, int(spikes[0]), int(spikes[-1]+1), f"{key} has {len(spikes)} extreme frame-to-frame jumps", float(np.max(robust_z[spikes]))))
            near_zero = mag <= max(1e-9, med * 0.02)
            longest = _longest_run(near_zero)
            if longest >= max(10, int(0.35 * len(mag))):
                findings.append(Finding("dynamics", "LOW_MOTION_RUN", "low", episode_index, None, None, f"{key} has a near-static run of {longest} transitions", float(longest)))
    return findings


def _longest_run(mask: np.ndarray) -> int:
    best = cur = 0
    for value in mask.tolist():
        if value:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


def inspect_video(path: Path, episode_index: int, expected_frames: int, expected_fps: float, sample_limit: int = 80) -> list[Finding]:
    findings: list[Finding] = []
    if not path.exists():
        return [Finding("sync", "MISSING_VIDEO", "high", episode_index, None, None, f"missing video {path}")]
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        return [Finding("visual", "VIDEO_DECODE_FAILURE", "high", episode_index, None, None, f"cannot decode {path}")]
    count = int(round(cap.get(cv2.CAP_PROP_FRAME_COUNT)))
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    if expected_frames >= 0 and abs(count - expected_frames) > 1:
        findings.append(Finding("sync", "VIDEO_FRAME_COVERAGE_MISMATCH", "high", episode_index, None, None, f"video {path.name} frames={count}, tabular={expected_frames}", float(count - expected_frames)))
    if expected_fps > 0 and fps > 0 and abs(fps - expected_fps) / expected_fps > 0.10:
        findings.append(Finding("sync", "VIDEO_FPS_MISMATCH", "medium", episode_index, None, None, f"video {path.name} fps={fps:.3g}, declared={expected_fps:g}", fps))

    if count <= 0:
        cap.release()
        findings.append(Finding("visual", "EMPTY_VIDEO", "high", episode_index, None, None, f"video {path.name} has no frames"))
        return findings
    indices = np.unique(np.linspace(0, max(0, count - 1), min(sample_limit, count), dtype=int))
    black = blur = freeze_pairs = decoded = 0
    prev_gray: np.ndarray | None = None
    for idx in indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
        ok, frame = cap.read()
        if not ok or frame is None:
            continue
        decoded += 1
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        mean = float(np.mean(gray)); std = float(np.std(gray))
        if mean < 8.0 and std < 5.0:
            black += 1
        if float(cv2.Laplacian(gray, cv2.CV_64F).var()) < 8.0:
            blur += 1
        if prev_gray is not None and prev_gray.shape == gray.shape:
            if float(np.mean(cv2.absdiff(prev_gray, gray))) < 0.35:
                freeze_pairs += 1
        prev_gray = gray
    cap.release()
    if decoded == 0:
        findings.append(Finding("visual", "VIDEO_SAMPLE_DECODE_FAILURE", "high", episode_index, None, None, f"no sampled frames decoded from {path.name}"))
        return findings
    black_ratio = black / decoded
    blur_ratio = blur / decoded
    freeze_ratio = freeze_pairs / max(1, decoded - 1)
    if black_ratio >= 0.10:
        findings.append(Finding("visual", "BLACK_FRAME_RATE", "high" if black_ratio >= .5 else "medium", episode_index, None, None, f"{path.name} sampled black-frame rate {black_ratio:.1%}", black_ratio))
    if blur_ratio >= 0.35:
        findings.append(Finding("visual", "LOW_DETAIL_RATE", "medium", episode_index, None, None, f"{path.name} sampled low-detail/blur rate {blur_ratio:.1%}", blur_ratio))
    if freeze_ratio >= 0.30:
        findings.append(Finding("visual", "FROZEN_VIDEO_RATE", "medium", episode_index, None, None, f"{path.name} sampled unchanged-pair rate {freeze_ratio:.1%}", freeze_ratio))
    return findings


def score_findings(findings: Sequence[Finding]) -> tuple[float, float, dict[str, float]]:
    category_penalty: dict[str, float] = {k: 0.0 for k in CATEGORY_BUDGET}
    grouped: dict[tuple[str, str], list[Finding]] = {}
    for f in findings:
        grouped.setdefault((f.category, f.code), []).append(f)
    for (category, _code), rows in grouped.items():
        if category not in CATEGORY_BUDGET:
            continue
        strongest = max(SEVERITY_WEIGHT.get(row.severity, 0.0) for row in rows)
        multiplicity = min(1.0, 0.65 + 0.12 * max(0, len(rows) - 1))
        category_penalty[category] += CATEGORY_BUDGET[category] * strongest * multiplicity
    for category, budget in CATEGORY_BUDGET.items():
        category_penalty[category] = min(budget, category_penalty[category])
    total = sum(category_penalty.values())
    quality = max(0.0, 100.0 - total)
    hard = sum(8.0 for f in findings if f.severity == "high" and f.category in {"structure", "sync"})
    low_motion = sum(3.0 for f in findings if f.code == "LOW_MOTION_RUN")
    value = max(0.0, quality - min(24.0, hard) - min(9.0, low_motion))
    scores = {k: round(max(0.0, CATEGORY_BUDGET[k] - category_penalty[k]) / CATEGORY_BUDGET[k] * 100.0, 2) for k in CATEGORY_BUDGET}
    return round(quality, 2), round(value, 2), scores


def analyze_episode(df: pd.DataFrame, episode_index: int, fps: float, *, expected_shapes: Mapping[str, Sequence[int]] | None = None, numeric_keys: Iterable[str] = (), video_paths: Iterable[Path] = (), reference: "ReferenceProfile | None" = None) -> EpisodeReport:
    findings: list[Finding] = []
    findings += validate_schema(df, episode_index, expected_shapes)
    findings += temporal_findings(df, episode_index, fps)
    findings += numeric_findings(df, episode_index, numeric_keys)
    if reference is not None:
        findings += reference_findings(df, episode_index, reference)
    for path in video_paths:
        findings += inspect_video(path, episode_index, len(df), fps)
    duration = None
    if "timestamp" in df.columns and len(df):
        ts = pd.to_numeric(df["timestamp"], errors="coerce")
        if ts.notna().all() and np.isfinite(ts.to_numpy(dtype=float)).all():
            duration = float(ts.iloc[-1] - ts.iloc[0])
    quality, value, category = score_findings(findings)
    return EpisodeReport(episode_index, len(df), duration, findings, quality, value, category)


def write_reports(reports: Sequence[EpisodeReport], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {"version": "wuhu-robot-qc/v1", "episodes": [r.as_dict() for r in reports]}
    (out_dir / "report.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    rows: list[dict[str, Any]] = []
    for r in reports:
        if not r.findings:
            rows.append({"episode_index": r.episode_index, "anomaly_type": "NONE", "start_frame": "", "end_frame": "", "severity": "", "detail": "", "quality_score": r.quality_score, "value_score": r.value_score})
        else:
            for f in r.findings:
                rows.append({"episode_index": r.episode_index, "anomaly_type": f"{f.category}:{f.code}", "start_frame": f.start_frame if f.start_frame is not None else "", "end_frame": f.end_frame if f.end_frame is not None else "", "severity": f.severity, "detail": f.detail, "quality_score": r.quality_score, "value_score": r.value_score})
    pd.DataFrame(rows).to_csv(out_dir / "report.csv", index=False)

@dataclass(frozen=True)
class ReferenceFeature:
    median: tuple[float, ...]
    scale: tuple[float, ...]
    delta_median: float
    delta_scale: float


@dataclass(frozen=True)
class ReferenceProfile:
    version: str
    features: dict[str, ReferenceFeature]

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "features": {
                key: {
                    "median": list(value.median),
                    "scale": list(value.scale),
                    "delta_median": value.delta_median,
                    "delta_scale": value.delta_scale,
                }
                for key, value in sorted(self.features.items())
            },
        }

    @staticmethod
    def from_dict(value: Mapping[str, Any]) -> "ReferenceProfile":
        if value.get("version") != "wuhu-reference/v1" or not isinstance(value.get("features"), Mapping):
            raise ValueError("invalid reference profile")
        features: dict[str, ReferenceFeature] = {}
        for key, row in value["features"].items():
            med = tuple(float(v) for v in row["median"])
            scale = tuple(float(v) for v in row["scale"])
            if len(med) != len(scale) or not med or any((not math.isfinite(v) or v <= 0) for v in scale):
                raise ValueError(f"invalid reference feature {key}")
            dm = float(row["delta_median"]); ds = float(row["delta_scale"])
            if not math.isfinite(dm) or not math.isfinite(ds) or ds <= 0:
                raise ValueError(f"invalid reference delta feature {key}")
            features[str(key)] = ReferenceFeature(med, scale, dm, ds)
        return ReferenceProfile("wuhu-reference/v1", features)


def fit_reference(dataframes: Sequence[pd.DataFrame], feature_keys: Iterable[str]) -> ReferenceProfile:
    features: dict[str, ReferenceFeature] = {}
    for key in feature_keys:
        mats: list[np.ndarray] = []
        deltas: list[np.ndarray] = []
        width: int | None = None
        for df in dataframes:
            if key not in df.columns or df.empty:
                continue
            mat = _as_numeric_matrix(df[key])
            if mat is None or mat.size == 0 or not np.all(np.isfinite(mat)):
                continue
            if width is None: width = mat.shape[1]
            if mat.shape[1] != width: raise ValueError(f"reference feature {key} has inconsistent width")
            mats.append(mat)
            if len(mat) > 1: deltas.append(np.linalg.norm(np.diff(mat, axis=0), axis=1))
        if not mats:
            continue
        allv = np.vstack(mats)
        median = np.median(allv, axis=0)
        mad = np.median(np.abs(allv - median), axis=0) * 1.4826
        std = np.std(allv, axis=0)
        scale = np.where(mad > 1e-8, mad, np.maximum(std, 1e-8))
        alld = np.concatenate(deltas) if deltas else np.asarray([0.0])
        dm = float(np.median(alld)); dmad = float(np.median(np.abs(alld-dm)) * 1.4826); dstd = float(np.std(alld))
        ds = max(dmad, dstd, 1e-8)
        features[key] = ReferenceFeature(tuple(map(float, median)), tuple(map(float, scale)), dm, ds)
    if not features:
        raise ValueError("reference profile has no usable numeric features")
    return ReferenceProfile("wuhu-reference/v1", features)


def reference_findings(df: pd.DataFrame, episode_index: int, profile: ReferenceProfile) -> list[Finding]:
    findings: list[Finding] = []
    for key, ref in profile.features.items():
        if key not in df.columns:
            continue
        mat = _as_numeric_matrix(df[key])
        if mat is None or mat.size == 0 or not np.all(np.isfinite(mat)):
            continue
        median=np.asarray(ref.median); scale=np.asarray(ref.scale)
        if mat.shape[1] != median.size:
            findings.append(Finding("structure","REFERENCE_WIDTH_MISMATCH","high",episode_index,None,None,f"{key} width={mat.shape[1]} reference={median.size}"))
            continue
        rz=np.abs((mat-median)/scale)
        extreme=np.any(rz>12.0,axis=1)
        ratio=float(np.mean(extreme))
        if ratio>=.02:
            sev="high" if ratio>=.20 else "medium"
            rows=np.where(extreme)[0]
            findings.append(Finding("dynamics","REFERENCE_RANGE_VIOLATION",sev,episode_index,int(rows[0]),int(rows[-1]),f"{key} has {ratio:.1%} frames outside robust clean-reference range",ratio))
        if len(mat)>1:
            mag=np.linalg.norm(np.diff(mat,axis=0),axis=1)
            z=(mag-ref.delta_median)/ref.delta_scale
            extreme_d=z>12.0
            ratio_d=float(np.mean(extreme_d))
            if ratio_d>=.02:
                sev="high" if ratio_d>=.20 else "medium"
                rows=np.where(extreme_d)[0]
                findings.append(Finding("dynamics","REFERENCE_DYNAMICS_VIOLATION",sev,episode_index,int(rows[0]),int(rows[-1]+1),f"{key} has {ratio_d:.1%} transitions outside clean-reference dynamics",ratio_d))
    return findings
