#!/usr/bin/env python3
"""Read-only LeRobot v2.1 data-quality and training-value audit."""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import html
import json
import math
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Sequence

V21 = "v2.1"
EP_RE = re.compile(r"episode_(\d{6})\.(?:parquet|mp4)$")
SEVERITY_PENALTY = {"info": 1.0, "warning": 4.0, "error": 12.0}
CATEGORY_WEIGHTS = {"structure": .20, "timing": .20, "synchronization": .20, "visual": .20, "vectors": .20}
CODE_CATEGORY = {
    "missing_file":"structure", "missing_directory":"structure", "invalid_info":"structure",
    "wrong_version":"structure", "episode_index_gap":"structure", "episode_index_duplicate":"structure",
    "episode_length_mismatch":"structure", "camera_count_mismatch":"structure", "decoder_unavailable":"structure",
    "parquet_unavailable":"structure", "frame_loss":"timing", "fps_jitter":"timing",
    "timestamp_reversal":"timing", "frame_order":"timing", "timestamp_duplicate":"timing",
    "stream_offset":"synchronization", "stream_drift":"synchronization", "stream_overlap":"synchronization",
    "video_frame_count":"synchronization", "corrupt_visual":"visual", "black_frame":"visual",
    "occluded_frame":"visual", "nonfinite_vector":"vectors", "malformed_vector":"vectors",
    "out_of_range_vector":"vectors", "low_dynamic_range":"vectors",
}
SEVERITY_RANK = {"error": 0, "warning": 1, "info": 2}

class AuditError(RuntimeError):
    pass

@dataclasses.dataclass(frozen=True)
class Fault:
    code: str
    severity: str
    reason: str
    episode_index: int | None = None
    frame_index: int | None = None
    modality: str = "dataset"
    metric: float | int | str | None = None
    def as_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

@dataclasses.dataclass(frozen=True)
class FrameRow:
    episode_index: int
    frame_index: int
    timestamp: float
    state: tuple[float, ...]
    action: tuple[float, ...]

@dataclasses.dataclass(frozen=True)
class VisualFrame:
    episode_index: int
    frame_index: int
    camera: str
    timestamp: float
    mean_luma: float
    std_luma: float
    edge_fraction: float
    decodable: bool = True

@dataclasses.dataclass
class AuditConfig:
    expected_vector_dim: int = 20
    expected_cameras: int = 3
    jitter_ratio: float = .15
    max_offset_ms: float = 50.0
    max_drift_ms: float = 50.0
    min_overlap_ratio: float = .95
    vector_abs_limit: float = 1_000_000.0
    black_luma: float = 8.0
    occlusion_std_luma: float = 4.0
    occlusion_edge_fraction: float = .003
    visual_sample_stride: int = 1

def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise AuditError(f"{path}:{lineno}: invalid JSON: {exc}") from exc
            if not isinstance(obj, dict):
                raise AuditError(f"{path}:{lineno}: expected JSON object")
            rows.append(obj)
    return rows

def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def _episode_index(path: Path) -> int | None:
    m = EP_RE.search(path.name)
    return int(m.group(1)) if m else None

def _feature_names(info: dict[str, Any]) -> tuple[str | None, str | None, list[str]]:
    features = info.get("features", {})
    if not isinstance(features, dict):
        return None, None, []
    state_key = action_key = None
    cameras = []
    for key, spec in sorted(features.items()):
        if not isinstance(spec, dict):
            continue
        dtype = str(spec.get("dtype", "")).lower()
        if key in {"observation.state", "state"} or key.endswith(".state"):
            state_key = state_key or key
        if key == "action" or key.endswith(".action"):
            action_key = action_key or key
        if dtype in {"video", "image"} or "image" in key.lower() or "camera" in key.lower():
            cameras.append(key)
    return state_key, action_key, cameras

def validate_layout(root: Path, cfg: AuditConfig) -> tuple[dict[str, Any], dict[int, dict[str, Any]], list[Fault]]:
    faults = []
    if not root.is_dir():
        raise AuditError(f"dataset root is not a directory: {root}")
    for name in ("meta", "data", "videos"):
        if not (root / name).is_dir():
            faults.append(Fault("missing_directory", "error", f"required v2.1 directory missing: {name}/"))
    info_path = root / "meta/info.json"
    if not info_path.is_file():
        faults.append(Fault("missing_file", "error", "required v2.1 metadata missing: meta/info.json"))
        return {}, {}, faults
    try:
        info = _load_json(info_path)
    except (OSError, json.JSONDecodeError) as exc:
        return {}, {}, faults + [Fault("invalid_info", "error", f"cannot parse meta/info.json: {exc}")]
    if not isinstance(info, dict):
        faults.append(Fault("invalid_info", "error", "meta/info.json must contain an object")); info = {}
    if info.get("codebase_version") != V21:
        faults.append(Fault("wrong_version", "error", f"codebase_version={info.get('codebase_version')!r}; expected {V21!r}"))
    fps = info.get("fps")
    if not isinstance(fps, (int, float)) or isinstance(fps, bool) or fps <= 0:
        faults.append(Fault("invalid_info", "error", f"fps must be positive, got {fps!r}"))
    episodes_path = root / "meta/episodes.jsonl"
    episodes: dict[int, dict[str, Any]] = {}
    if not episodes_path.is_file():
        faults.append(Fault("missing_file", "error", "required v2.1 metadata missing: meta/episodes.jsonl"))
    else:
        try: records = _load_jsonl(episodes_path)
        except (OSError, AuditError) as exc:
            faults.append(Fault("invalid_info", "error", str(exc))); records = []
        seen = set()
        for rec in records:
            idx = rec.get("episode_index")
            if not isinstance(idx, int) or isinstance(idx, bool) or idx < 0:
                faults.append(Fault("invalid_info", "error", f"invalid episode_index: {idx!r}")); continue
            if idx in seen:
                faults.append(Fault("episode_index_duplicate", "error", f"episode index {idx} appears more than once", idx))
            seen.add(idx); episodes[idx] = rec
        if seen:
            for idx in sorted(set(range(min(seen), max(seen) + 1)) - seen):
                faults.append(Fault("episode_index_gap", "error", f"episode index {idx} is missing", idx))
        declared = info.get("total_episodes")
        if isinstance(declared, int) and not isinstance(declared, bool) and declared != len(seen):
            faults.append(Fault("episode_length_mismatch", "warning", f"total_episodes={declared}, metadata has {len(seen)}"))
    _, _, cameras = _feature_names(info)
    if len(cameras) != cfg.expected_cameras:
        faults.append(Fault("camera_count_mismatch", "warning", f"info exposes {len(cameras)} camera/image features; expected {cfg.expected_cameras}", metric=len(cameras)))
    return info, episodes, faults

def _coerce_vector(value: Any) -> tuple[float, ...] | None:
    if hasattr(value, "tolist"):
        value = value.tolist()
    if not isinstance(value, (list, tuple)):
        return None
    out = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            return None
        out.append(float(item))
    return tuple(out)

def load_parquet_rows(root: Path, info: dict[str, Any], episodes: dict[int, dict[str, Any]]) -> tuple[dict[int, list[FrameRow]], list[Fault], dict[str, str]]:
    try:
        import pyarrow.parquet as pq  # type: ignore
    except ImportError:
        return {}, [Fault("parquet_unavailable", "error", "PyArrow is required to inspect episode parquet files")], {}
    state_key, action_key, _ = _feature_names(info)
    state_key = state_key or "observation.state"; action_key = action_key or "action"
    rows_by_ep: dict[int, list[FrameRow]] = defaultdict(list); faults = []; provenance = {}; found = set()
    for path in sorted((root / "data").glob("chunk-*/episode_*.parquet")):
        ep_name = _episode_index(path)
        if ep_name is not None: found.add(ep_name)
        provenance[str(path.relative_to(root))] = _sha256_file(path)
        try: data = pq.read_table(path).to_pylist()
        except Exception as exc:
            faults.append(Fault("missing_file", "error", f"cannot read {path.relative_to(root)}: {exc}", ep_name)); continue
        for row_no, raw in enumerate(data):
            if not isinstance(raw, dict): continue
            ep = raw.get("episode_index", ep_name); fi = raw.get("frame_index", row_no); ts = raw.get("timestamp")
            ep = ep if isinstance(ep, int) and not isinstance(ep, bool) else (ep_name if ep_name is not None else -1)
            fi = fi if isinstance(fi, int) and not isinstance(fi, bool) else row_no
            ts = float(ts) if isinstance(ts, (int, float)) and not isinstance(ts, bool) else float("nan")
            rows_by_ep[int(ep)].append(FrameRow(int(ep), int(fi), ts, _coerce_vector(raw.get(state_key)) or (), _coerce_vector(raw.get(action_key)) or ()))
    for idx in sorted(set(episodes) - found):
        faults.append(Fault("missing_file", "error", "episode has no data/chunk-*/episode_*.parquet", idx))
    for idx in sorted(found - set(episodes)):
        faults.append(Fault("episode_index_gap", "warning", "data file exists for undeclared episode", idx))
    return dict(rows_by_ep), faults, provenance

def _video_files(root: Path) -> dict[tuple[int, str], Path]:
    out = {}
    for path in sorted((root / "videos").glob("chunk-*/*/episode_*.mp4")):
        idx = _episode_index(path)
        if idx is not None: out[(idx, path.parent.name)] = path
    return out

def _decode_video(path: Path, episode_index: int, camera: str, stride: int) -> tuple[list[VisualFrame], list[Fault], dict[str, float]]:
    try:
        import av  # type: ignore
        import numpy as np  # type: ignore
    except ImportError:
        return [], [Fault("decoder_unavailable", "error", "PyAV + NumPy are required for full video quality inspection", episode_index, modality=camera)], {}
    frames = []; faults = []; metrics = {}
    try:
        with av.open(str(path)) as container:
            streams = [s for s in container.streams if s.type == "video"]
            if not streams:
                return [], [Fault("corrupt_visual", "error", f"{path.name} has no video stream", episode_index, modality=camera)], {}
            stream = streams[0]
            if stream.average_rate: metrics["fps"] = float(stream.average_rate)
            decoded = 0
            for decoded, frame in enumerate(container.decode(stream), 1):
                idx = decoded - 1
                if idx % max(1, stride): continue
                try:
                    arr = frame.to_ndarray(format="gray").astype("float64", copy=False)
                    mean = float(arr.mean()); std = float(arr.std())
                    edge = 0.0 if min(arr.shape) <= 1 else float(((np.abs(np.diff(arr, axis=1)) > 12).mean() + (np.abs(np.diff(arr, axis=0)) > 12).mean()) / 2)
                    ts = float(frame.time) if frame.time is not None else float(idx)
                    frames.append(VisualFrame(episode_index, idx, camera, ts, mean, std, edge, True))
                except Exception as exc:
                    faults.append(Fault("corrupt_visual", "error", f"cannot decode frame pixels: {exc}", episode_index, idx, camera))
            metrics["decoded_frames"] = float(decoded)
    except Exception as exc:
        faults.append(Fault("corrupt_visual", "error", f"cannot decode video {path.name}: {exc}", episode_index, modality=camera))
    return frames, faults, metrics

def load_visuals(root: Path, info: dict[str, Any], episodes: dict[int, dict[str, Any]], cfg: AuditConfig):
    _, _, declared_cameras = _feature_names(info); files = _video_files(root); discovered = sorted({c for _, c in files}); cameras = declared_cameras or discovered
    by_ep: dict[int, dict[str, list[VisualFrame]]] = defaultdict(dict); faults = []; metrics = {}; provenance = {}
    for idx in sorted(episodes):
        for camera in cameras:
            path = files.get((idx, camera))
            if path is None:
                faults.append(Fault("missing_file", "error", f"missing video for camera {camera}", idx, modality=camera)); continue
            provenance[str(path.relative_to(root))] = _sha256_file(path)
            frames, local_faults, local_metrics = _decode_video(path, idx, camera, cfg.visual_sample_stride)
            by_ep[idx][camera] = frames; faults.extend(local_faults); metrics[(idx, camera)] = local_metrics
    return dict(by_ep), faults, metrics, provenance

def _vector_faults(rows: Sequence[FrameRow], cfg: AuditConfig) -> list[Fault]:
    faults = []
    for row in rows:
        for modality, vec in (("state", row.state), ("action", row.action)):
            if len(vec) != cfg.expected_vector_dim:
                faults.append(Fault("malformed_vector", "error", f"{modality} vector has {len(vec)} dimensions; expected {cfg.expected_vector_dim}", row.episode_index, row.frame_index, modality, len(vec))); continue
            for i, value in enumerate(vec):
                if not math.isfinite(value):
                    faults.append(Fault("nonfinite_vector", "error", f"{modality}[{i}] is non-finite", row.episode_index, row.frame_index, modality, repr(value)))
                elif abs(value) > cfg.vector_abs_limit:
                    faults.append(Fault("out_of_range_vector", "error", f"{modality}[{i}]={value:g} exceeds limit {cfg.vector_abs_limit:g}", row.episode_index, row.frame_index, modality, value))
    return faults

def _timing_faults(rows: Sequence[FrameRow], fps: float, cfg: AuditConfig) -> list[Fault]:
    if not rows: return []
    faults = []; expected_dt = 1.0 / fps; previous = rows[0]
    if previous.frame_index != 0:
        faults.append(Fault("frame_loss", "warning", f"episode starts at frame_index={previous.frame_index}, expected 0", previous.episode_index, previous.frame_index, "frame_index"))
    for row in rows[1:]:
        if row.frame_index <= previous.frame_index:
            faults.append(Fault("frame_order", "error", f"frame_index {row.frame_index} follows {previous.frame_index}", row.episode_index, row.frame_index, "frame_index"))
        elif row.frame_index != previous.frame_index + 1:
            faults.append(Fault("frame_loss", "error", f"frame_index jumped {previous.frame_index}->{row.frame_index}", row.episode_index, row.frame_index, "frame_index", row.frame_index - previous.frame_index - 1))
        if not math.isfinite(row.timestamp):
            faults.append(Fault("timestamp_reversal", "error", "timestamp is non-finite", row.episode_index, row.frame_index, "timestamp", repr(row.timestamp)))
        elif math.isfinite(previous.timestamp):
            dt = row.timestamp - previous.timestamp
            if dt < 0:
                faults.append(Fault("timestamp_reversal", "error", f"timestamp moved backwards by {-dt:.6f}s", row.episode_index, row.frame_index, "timestamp", dt))
            elif dt == 0:
                faults.append(Fault("timestamp_duplicate", "warning", "timestamp duplicated", row.episode_index, row.frame_index, "timestamp", dt))
            elif abs(dt - expected_dt) > expected_dt * cfg.jitter_ratio:
                code = "frame_loss" if dt > expected_dt * 1.75 else "fps_jitter"; sev = "error" if code == "frame_loss" else "warning"
                faults.append(Fault(code, sev, f"frame interval {dt:.6f}s differs from expected {expected_dt:.6f}s", row.episode_index, row.frame_index, "timestamp", dt))
        previous = row
    return faults

def _visual_faults(visuals: dict[str, list[VisualFrame]], cfg: AuditConfig) -> list[Fault]:
    faults = []
    for camera, frames in sorted(visuals.items()):
        for frame in frames:
            if not frame.decodable:
                faults.append(Fault("corrupt_visual", "error", "frame is not decodable", frame.episode_index, frame.frame_index, camera))
            elif frame.mean_luma <= cfg.black_luma:
                faults.append(Fault("black_frame", "error", f"mean luminance {frame.mean_luma:.2f} <= {cfg.black_luma:.2f}", frame.episode_index, frame.frame_index, camera, round(frame.mean_luma, 4)))
            elif frame.std_luma <= cfg.occlusion_std_luma and frame.edge_fraction <= cfg.occlusion_edge_fraction:
                faults.append(Fault("occluded_frame", "warning", f"low variation std={frame.std_luma:.2f}, edge_fraction={frame.edge_fraction:.5f}", frame.episode_index, frame.frame_index, camera, round(frame.edge_fraction, 6)))
    return faults

def _sync_faults(rows: Sequence[FrameRow], visuals: dict[str, list[VisualFrame]], cfg: AuditConfig) -> list[Fault]:
    if not rows: return []
    row_ts = [r.timestamp for r in rows if math.isfinite(r.timestamp)]
    if not row_ts: return []
    faults = []; b0, b1 = min(row_ts), max(row_ts); base_duration = max(0.0, b1 - b0); ep = rows[0].episode_index
    for camera, frames in sorted(visuals.items()):
        ts = [f.timestamp for f in frames if math.isfinite(f.timestamp)]
        if not ts: continue
        c0, c1 = min(ts), max(ts); offset_ms = (c0-b0)*1000; drift_ms = ((c1-c0)-base_duration)*1000
        overlap = max(0.0, min(b1,c1)-max(b0,c0)); ratio = overlap/max(base_duration,c1-c0,1e-9)
        if abs(offset_ms) > cfg.max_offset_ms:
            faults.append(Fault("stream_offset", "warning", f"{camera} starts {offset_ms:.2f}ms from state/action timeline", ep, modality=camera, metric=round(offset_ms,4)))
        if abs(drift_ms) > cfg.max_drift_ms:
            faults.append(Fault("stream_drift", "warning", f"{camera} duration drifts {drift_ms:.2f}ms", ep, modality=camera, metric=round(drift_ms,4)))
        if ratio < cfg.min_overlap_ratio:
            faults.append(Fault("stream_overlap", "error", f"{camera} overlap ratio {ratio:.4f} < {cfg.min_overlap_ratio:.4f}", ep, modality=camera, metric=round(ratio,6)))
    return faults

def _dynamic_value(rows: Sequence[FrameRow], dim: int) -> float:
    if len(rows) < 2: return 0.0
    changes = []
    for attr in ("state", "action"):
        seq = [getattr(r, attr) for r in rows if len(getattr(r, attr)) == dim and all(math.isfinite(x) for x in getattr(r, attr))]
        for a, b in zip(seq, seq[1:]): changes.append(sum(abs(x-y) for x,y in zip(a,b))/dim)
    if not changes: return 0.0
    return 100.0 * sum(c > 1e-9 for c in changes) / len(changes)

def _score_faults(faults: Sequence[Fault]) -> dict[str, float]:
    penalties = defaultdict(float)
    for f in faults: penalties[CODE_CATEGORY.get(f.code, "structure")] += SEVERITY_PENALTY.get(f.severity, 4.0)
    scores = {c:max(0.0,100.0-penalties.get(c,0.0)) for c in CATEGORY_WEIGHTS}
    scores["quality"] = sum(scores[c]*w for c,w in CATEGORY_WEIGHTS.items())
    return {k:round(v,2) for k,v in scores.items()}

def analyze_episode(episode_index: int, expected_length: int | None, rows: Sequence[FrameRow], visuals: dict[str, list[VisualFrame]], fps: float, cfg: AuditConfig, inherited_faults: Sequence[Fault]=()) -> dict[str, Any]:
    faults = list(inherited_faults)
    if expected_length is not None and len(rows) != expected_length:
        faults.append(Fault("episode_length_mismatch", "warning", f"metadata length={expected_length}, parquet rows={len(rows)}", episode_index, metric=len(rows)))
    faults += _timing_faults(rows,fps,cfg) + _vector_faults(rows,cfg) + _visual_faults(visuals,cfg) + _sync_faults(rows,visuals,cfg)
    dynamic = _dynamic_value(rows,cfg.expected_vector_dim)
    if rows and dynamic < 5.0:
        faults.append(Fault("low_dynamic_range", "info", f"only {dynamic:.2f}% of state/action transitions change", episode_index, modality="state/action", metric=round(dynamic,4)))
    scores = _score_faults(faults); scores["dynamic_signal"] = round(dynamic,2); scores["training_value"] = round(.75*scores["quality"]+.25*dynamic,2)
    ordered = sorted(faults,key=lambda f:(f.frame_index if f.frame_index is not None else -1,SEVERITY_RANK.get(f.severity,9),f.modality,f.code,f.reason))
    return {"episode_index":episode_index,"frames":len(rows),"expected_frames":expected_length,"camera_streams":sorted(visuals),"scores":scores,"faults":[f.as_dict() for f in ordered]}

def aggregate_report(root: Path, info: dict[str, Any], episodes_meta: dict[int, dict[str, Any]], rows_by_episode: dict[int,list[FrameRow]], visuals_by_episode: dict[int,dict[str,list[VisualFrame]]], faults: Sequence[Fault], cfg: AuditConfig, provenance: dict[str,str]|None=None) -> dict[str, Any]:
    fps_raw=info.get("fps",0); fps=float(fps_raw) if isinstance(fps_raw,(int,float)) and not isinstance(fps_raw,bool) and fps_raw>0 else 1.0
    indices=sorted(set(episodes_meta)|set(rows_by_episode)|{f.episode_index for f in faults if f.episode_index is not None}); dataset_faults=[f for f in faults if f.episode_index is None]
    episodes=[]
    for idx in indices:
        raw=episodes_meta.get(idx,{}).get("length"); expected=raw if isinstance(raw,int) and not isinstance(raw,bool) and raw>=0 else None
        episodes.append(analyze_episode(idx,expected,rows_by_episode.get(idx,[]),visuals_by_episode.get(idx,{}),fps,cfg,[f for f in faults if f.episode_index==idx]))
    ds_scores=_score_faults(dataset_faults)
    keys=["structure","timing","synchronization","visual","vectors","quality","dynamic_signal","training_value"]
    if episodes:
        overall={k:round(statistics.fmean(ep["scores"][k] for ep in episodes),2) for k in keys}; overall["structure"]=round(min(overall["structure"],ds_scores["structure"]),2); overall["quality"]=round(sum(overall[c]*w for c,w in CATEGORY_WEIGHTS.items()),2); overall["training_value"]=round(.75*overall["quality"]+.25*overall["dynamic_signal"],2)
    else: overall={k:0.0 for k in keys}
    counts=Counter(f.severity for f in dataset_faults)
    for ep in episodes: counts.update(f["severity"] for f in ep["faults"])
    return {"schema_version":1,"tool":"wuhu-lerobot-v21-quality","dataset_root":str(root),"dataset_codebase_version":info.get("codebase_version"),"fps":info.get("fps"),"expected_vector_dim":cfg.expected_vector_dim,"expected_cameras":cfg.expected_cameras,"overall_scores":overall,"fault_counts":dict(sorted(counts.items())),"dataset_faults":[f.as_dict() for f in sorted(dataset_faults,key=lambda f:(SEVERITY_RANK.get(f.severity,9),f.code,f.reason))],"episodes":episodes,"provenance_sha256":dict(sorted((provenance or {}).items())),"scoring":{"severity_penalty":SEVERITY_PENALTY,"quality_category_weights":CATEGORY_WEIGHTS,"training_value_formula":"0.75 * quality + 0.25 * dynamic_signal","dynamic_signal":"percent of consecutive valid 20D state/action transitions with mean absolute delta > 1e-9"}}

def report_markdown(report: dict[str, Any]) -> str:
    s=report["overall_scores"]; lines=["# Wuhu LeRobot V2.1 data-quality report","",f"- Dataset: `{report['dataset_root']}`",f"- Codebase version: `{report.get('dataset_codebase_version')}`",f"- Overall quality: **{s['quality']:.2f}/100**",f"- Training value: **{s['training_value']:.2f}/100**",f"- Episodes analyzed: **{len(report['episodes'])}**","","## Subscores","","| Structure | Timing | Synchronization | Visual | Vectors | Dynamic signal |","|---:|---:|---:|---:|---:|---:|",f"| {s['structure']:.2f} | {s['timing']:.2f} | {s['synchronization']:.2f} | {s['visual']:.2f} | {s['vectors']:.2f} | {s['dynamic_signal']:.2f} |","","## Episode summary","","| Episode | Quality | Training value | Faults |","|---:|---:|---:|---:|"]
    for ep in report["episodes"]: lines.append(f"| {ep['episode_index']} | {ep['scores']['quality']:.2f} | {ep['scores']['training_value']:.2f} | {len(ep['faults'])} |")
    lines += ["","## Fault localization","","| Severity | Episode | Frame | Modality | Code | Reason |","|---|---:|---:|---|---|---|"]; faults=list(report["dataset_faults"])
    for ep in report["episodes"]: faults += ep["faults"]
    for f in faults:
        reason=str(f["reason"]).replace("|","\\|").replace("\n"," "); lines.append(f"| {f['severity']} | {'' if f['episode_index'] is None else f['episode_index']} | {'' if f['frame_index'] is None else f['frame_index']} | {f['modality']} | `{f['code']}` | {reason} |")
    lines += ["","## Scoring contract","","Quality is the fixed weighted average of five 0–100 category scores. Each localized fault subtracts the published severity penalty from its category, floored at zero. Training value is `0.75 * quality + 0.25 * dynamic_signal`. The JSON report contains the exact weights, penalties, provenance hashes and all localized faults.","","This report is an offline analysis artifact. It is not evidence of competition registration, submission, qualification, award, or prize.",""]
    return "\n".join(lines)

def report_html(report: dict[str, Any]) -> str:
    title="Wuhu LeRobot V2.1 data-quality report"; md=report_markdown(report)
    return "<!doctype html><html><head><meta charset=\"utf-8\"><title>"+html.escape(title)+"</title><style>body{font-family:system-ui,sans-serif;max-width:1100px;margin:2rem auto;padding:0 1rem}pre{white-space:pre-wrap;line-height:1.45;background:#f6f8fa;padding:1rem;border-radius:8px}</style></head><body><h1>"+html.escape(title)+"</h1><pre>"+html.escape(md)+"</pre></body></html>\n"

def write_reports(report: dict[str, Any], out_dir: Path) -> None:
    out_dir.mkdir(parents=True,exist_ok=True); (out_dir/"report.json").write_text(json.dumps(report,indent=2,sort_keys=True,allow_nan=False)+"\n",encoding="utf-8"); (out_dir/"report.md").write_text(report_markdown(report),encoding="utf-8"); (out_dir/"report.html").write_text(report_html(report),encoding="utf-8")

def audit_dataset(root: Path, cfg: AuditConfig) -> dict[str, Any]:
    root=root.resolve(); info,episodes,faults=validate_layout(root,cfg); provenance={}
    for rel in ("meta/info.json","meta/episodes.jsonl","meta/episodes_stats.jsonl","meta/tasks.jsonl","meta/stats.json"):
        p=root/rel
        if p.is_file(): provenance[rel]=_sha256_file(p)
    rows,row_faults,row_prov=load_parquet_rows(root,info,episodes); faults+=row_faults; provenance.update(row_prov)
    visuals,vis_faults,metrics,vis_prov=load_visuals(root,info,episodes,cfg); faults+=vis_faults; provenance.update(vis_prov)
    fps_raw=info.get("fps"); fps=float(fps_raw) if isinstance(fps_raw,(int,float)) and not isinstance(fps_raw,bool) and fps_raw>0 else 1.0
    for (ep,camera),m in sorted(metrics.items()):
        expected=episodes.get(ep,{}).get("length"); decoded=m.get("decoded_frames")
        if isinstance(expected,int) and isinstance(decoded,(int,float)) and int(decoded)!=expected: faults.append(Fault("video_frame_count","warning",f"{camera} decoded {int(decoded)} frames; metadata length={expected}",ep,modality=camera,metric=int(decoded)))
        cam_fps=m.get("fps")
        if cam_fps and abs(cam_fps-fps)>fps*cfg.jitter_ratio: faults.append(Fault("fps_jitter","warning",f"{camera} container fps={cam_fps:.4f}, dataset fps={fps:.4f}",ep,modality=camera,metric=round(cam_fps,6)))
    return aggregate_report(root,info,episodes,rows,visuals,faults,cfg,provenance)

def build_parser() -> argparse.ArgumentParser:
    p=argparse.ArgumentParser(description="Read-only LeRobot v2.1 data-quality + training-value audit"); sub=p.add_subparsers(dest="command",required=True); a=sub.add_parser("audit"); a.add_argument("root",type=Path); a.add_argument("--out-dir",type=Path,required=True); a.add_argument("--expected-vector-dim",type=int,default=20); a.add_argument("--expected-cameras",type=int,default=3); a.add_argument("--jitter-ratio",type=float,default=.15); a.add_argument("--max-offset-ms",type=float,default=50.0); a.add_argument("--max-drift-ms",type=float,default=50.0); a.add_argument("--min-overlap-ratio",type=float,default=.95); a.add_argument("--vector-abs-limit",type=float,default=1_000_000.0); a.add_argument("--black-luma",type=float,default=8.0); a.add_argument("--occlusion-std-luma",type=float,default=4.0); a.add_argument("--occlusion-edge-fraction",type=float,default=.003); a.add_argument("--visual-sample-stride",type=int,default=1); return p

def main(argv: Sequence[str]|None=None) -> int:
    args=build_parser().parse_args(argv)
    if args.command!="audit": return 2
    root=args.root.resolve(); out=args.out_dir.resolve()
    if out==root or root in out.parents:
        print("error: --out-dir must be outside the immutable dataset root",file=sys.stderr); return 2
    cfg=AuditConfig(args.expected_vector_dim,args.expected_cameras,args.jitter_ratio,args.max_offset_ms,args.max_drift_ms,args.min_overlap_ratio,args.vector_abs_limit,args.black_luma,args.occlusion_std_luma,args.occlusion_edge_fraction,args.visual_sample_stride)
    try: report=audit_dataset(root,cfg); write_reports(report,out)
    except (AuditError,OSError,ValueError) as exc:
        print(f"error: {exc}",file=sys.stderr); return 2
    print(json.dumps({"quality":report["overall_scores"]["quality"],"training_value":report["overall_scores"]["training_value"],"report":str(out/"report.json")},sort_keys=True)); return 1 if report["fault_counts"].get("error",0) else 0

if __name__=="__main__": raise SystemExit(main())
