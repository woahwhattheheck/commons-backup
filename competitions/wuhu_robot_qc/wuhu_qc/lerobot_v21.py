from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .core import EpisodeReport, Finding, analyze_episode, fit_reference, score_findings, write_reports
from .provenance import BOUND_REFERENCE_VERSION, CLEAN_REFERENCE_ROLE, TEST_ROLE, UNSCOPED_ROLE, BoundReferenceProfile, CorpusManifest, assert_no_reference_overlap, build_corpus_manifest


def _require_parquet_engine() -> None:
    try:
        import pyarrow  # noqa: F401
        return
    except ImportError:
        try:
            import fastparquet  # noqa: F401
            return
        except ImportError as exc:
            raise RuntimeError("Parquet support required: install pyarrow (preferred) or fastparquet") from exc


def _read_info(root: Path) -> dict[str, Any]:
    path = root / "meta" / "info.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    version = str(data.get("codebase_version", ""))
    if version not in {"v2.0", "v2.1"}:
        raise ValueError(f"expected LeRobot v2.x dataset, got codebase_version={version!r}")
    return data


def _episode_indices(root: Path, info: dict[str, Any]) -> list[int]:
    path = root / "meta" / "episodes.jsonl"
    if path.exists():
        out: list[int] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip(): out.append(int(json.loads(line)["episode_index"]))
        values = sorted(set(out))
    else:
        values = list(range(int(info.get("total_episodes", 0))))
    if not values: raise ValueError("dataset declares no episodes")
    return values


def _format_path(template: str, episode: int, chunks_size: int, *, video_key: str | None = None) -> str:
    vals={"episode_index":episode,"episode_chunk":episode//max(chunks_size,1),"chunk_index":episode//max(chunks_size,1),"video_key":video_key or ""}
    return template.format(**vals)


def _contract(root: Path):
    info=_read_info(root); chunks=int(info.get("chunks_size",1000) or 1000); features=info.get("features",{}) or {}
    data_t=str(info.get("data_path","data/chunk-{episode_chunk:03d}/episode_{episode_index:06d}.parquet"))
    video_t=str(info.get("video_path","videos/chunk-{episode_chunk:03d}/{video_key}/episode_{episode_index:06d}.mp4"))
    shapes={k:v.get("shape",[]) for k,v in features.items() if isinstance(v,dict) and v.get("dtype") not in {"video","image"}}
    numeric=[k for k in features if k in {"action","observation.state"} or k.startswith("action.") or k.startswith("observation.state.")]
    videos=[k for k,v in features.items() if isinstance(v,dict) and v.get("dtype")=="video"]
    if not numeric: raise ValueError("dataset declares no modeled action/state numeric features")
    return info,chunks,data_t,video_t,shapes,numeric,videos


def _normalize_selection(all_episodes: list[int], episodes: list[int] | None) -> list[int]:
    selected=list(all_episodes if episodes is None else episodes)
    if not selected: raise ValueError("episode selection must not be empty")
    if len(set(selected)) != len(selected): raise ValueError("episode selection contains duplicates")
    unknown=sorted(set(selected)-set(all_episodes))
    if unknown: raise ValueError(f"episode selection is outside declared corpus: {unknown}")
    return sorted(selected)


def _matrix(value: pd.Series) -> np.ndarray:
    rows=[]; width=None
    for item in value.tolist():
        try: arr=np.asarray(item,dtype=np.float64).reshape(-1)
        except (TypeError,ValueError) as exc: raise ValueError("contains non-numeric vector") from exc
        if width is None: width=arr.size
        if arr.size != width: raise ValueError("contains inconsistent vector width")
        rows.append(arr)
    if not rows: raise ValueError("contains zero rows")
    out=np.vstack(rows)
    if not np.all(np.isfinite(out)): raise ValueError("contains non-finite values")
    return out


def _validate_reference_frames(frames: list[tuple[int,pd.DataFrame]], numeric: list[str], shapes: dict[str,Any]) -> None:
    widths={}
    for episode_index,df in frames:
        if df.empty: raise ValueError(f"clean-reference episode {episode_index} is empty")
        for key in numeric:
            if key not in df.columns: raise ValueError(f"clean-reference episode {episode_index} missing required modeled feature {key}")
            try: mat=_matrix(df[key])
            except ValueError as exc: raise ValueError(f"clean-reference episode {episode_index} feature {key} {exc}") from exc
            declared=shapes.get(key) or []
            if declared:
                expected=int(np.prod(declared))
                if mat.shape[1] != expected: raise ValueError(f"clean-reference episode {episode_index} feature {key} width={mat.shape[1]} expected={expected}")
            prior=widths.setdefault(key,mat.shape[1])
            if prior != mat.shape[1]: raise ValueError(f"clean-reference feature {key} changes width across episodes")


def _dataset_manifest(root: Path, *, role: str, info: dict[str,Any], chunks: int, data_t: str, selected: list[int]) -> CorpusManifest:
    declared=_episode_indices(root,info); paths={ep:root/_format_path(data_t,ep,chunks) for ep in declared}
    return build_corpus_manifest(root,role=role,declared_episode_indices=declared,selected_episode_indices=selected,data_paths=paths)


def fit_dataset_reference(root: Path, *, episodes: list[int] | None = None, role: str = CLEAN_REFERENCE_ROLE) -> BoundReferenceProfile:
    if role != CLEAN_REFERENCE_ROLE: raise ValueError("reference fitting requires role=ORGANIZER_CLEAN_REFERENCE")
    _require_parquet_engine(); root=root.resolve(); info,chunks,data_t,_,shapes,numeric,_=_contract(root)
    declared=_episode_indices(root,info); selected=_normalize_selection(declared,episodes)
    manifest=_dataset_manifest(root,role=CLEAN_REFERENCE_ROLE,info=info,chunks=chunks,data_t=data_t,selected=selected)
    frames=[]
    for ep in selected:
        path=root/_format_path(data_t,ep,chunks)
        if not path.exists(): raise FileNotFoundError(path)
        frames.append((ep,pd.read_parquet(path)))
    _validate_reference_frames(frames,numeric,shapes)
    profile=fit_reference([df for _,df in frames],numeric)
    if set(profile.features) != set(numeric): raise ValueError(f"reference fitting omitted modeled features: {sorted(set(numeric)-set(profile.features))}")
    return BoundReferenceProfile(BOUND_REFERENCE_VERSION,manifest,tuple(numeric),profile)


def _write_integrity_report(out_dir: Path, reports: list[EpisodeReport], *, scan_manifest: CorpusManifest, reference: BoundReferenceProfile | None) -> None:
    write_reports(reports,out_dir); path=out_dir/"report.json"; payload=json.loads(path.read_text(encoding="utf-8"))
    payload["competition_integrity"]={"scan_role":scan_manifest.role,"scan_manifest":scan_manifest.as_dict(),"reference_bound":reference is not None,"reference_provenance":reference.provenance.as_dict() if reference is not None else None,"reference_feature_keys":list(reference.feature_keys) if reference is not None else [],"reference_overlap_checked":reference is not None}
    path.write_text(json.dumps(payload,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")


def scan_dataset(root: Path, out_dir: Path, *, episodes: list[int] | None = None, reference: BoundReferenceProfile | None = None, dataset_role: str = UNSCOPED_ROLE) -> list[EpisodeReport]:
    _require_parquet_engine(); root=root.resolve(); info,chunks,data_t,video_t,shapes,numeric,videos=_contract(root)
    fps=float(info.get("fps",0) or 0)
    if fps<=0: raise ValueError("meta/info.json must declare positive fps")
    declared=_episode_indices(root,info); selected=_normalize_selection(declared,episodes)
    if reference is not None and not isinstance(reference,BoundReferenceProfile): raise TypeError("reference must be a provenance-bound BoundReferenceProfile")
    if reference is not None and dataset_role != TEST_ROLE: raise ValueError("bound-reference scoring requires dataset_role=ORGANIZER_TEST")
    if dataset_role not in {TEST_ROLE,UNSCOPED_ROLE}: raise ValueError(f"unsupported scan dataset role {dataset_role!r}")
    manifest=_dataset_manifest(root,role=dataset_role,info=info,chunks=chunks,data_t=data_t,selected=selected)
    if reference is not None:
        assert_no_reference_overlap(reference,manifest); missing=sorted(set(reference.feature_keys)-set(numeric))
        if missing: raise ValueError(f"test corpus lacks reference-modeled features: {missing}")
    reports=[]
    for ep in selected:
        path=root/_format_path(data_t,ep,chunks)
        if not path.exists():
            finding=Finding("structure","MISSING_PARQUET","high",ep,None,None,f"missing episode parquet {path}"); q,v,c=score_findings([finding]); reports.append(EpisodeReport(ep,0,None,[finding],q,v,c)); continue
        df=pd.read_parquet(path); video_paths=[root/_format_path(video_t,ep,chunks,video_key=k) for k in videos]
        reports.append(analyze_episode(df,ep,fps,expected_shapes=shapes,numeric_keys=numeric,video_paths=video_paths,reference=reference.profile if reference is not None else None))
    _write_integrity_report(out_dir,reports,scan_manifest=manifest,reference=reference); return reports
