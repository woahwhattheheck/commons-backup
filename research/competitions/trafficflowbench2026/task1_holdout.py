#!/usr/bin/env python3
"""Blocked-month A/B evaluator for TrafficFlowBench 2026 Task 1.

Fit the organizer historical profile on public train months *excluding* one
calendar month, then score that held-out month's published Task 1 masked targets
against the train truth. Compare the official historical-mean prediction with
the already-landed Commons bounded short-gap candidate on exactly the same
cells. This avoids letting the evaluation month contribute to the historical
profile statistics.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.util
import json
import re
try:
    import resource
except ImportError:  # Windows
    resource = None
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
PATH_MONTH_RE = re.compile(r"(?:year_month=|synthetic_mainline_)(\d{4})[-_](\d{2})")
KEYS = ["timestamp", "station_id", "link_id"]
REGIME_ORDER = ("R1", "R2", "R3")


def _load_official(official_repo: Path):
    src = official_repo.resolve() / "src"
    if not src.is_dir():
        raise SystemExit(f"--official-repo has no src/ directory: {official_repo}")
    sys.path.insert(0, str(src))
    return importlib.import_module("task1.baseline_task1_historical_mean")


def _load_shortgap(path: Path):
    path = path.resolve()
    spec = importlib.util.spec_from_file_location("commons_tfb_shortgap", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot import short-gap candidate: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _path_month(path: Path) -> str | None:
    text = str(path).replace("\\", "/")
    match = PATH_MONTH_RE.search(text)
    if match:
        return f"{match.group(1)}-{match.group(2)}"
    return None


def _frame_month(path: Path) -> str:
    inferred = _path_month(path)
    if inferred:
        return inferred
    first = pd.read_parquet(path, columns=["timestamp"]).head(1)
    if first.empty:
        raise ValueError(f"cannot infer month from empty parquet: {path}")
    ts = str(first.iloc[0]["timestamp"])
    if len(ts) < 7:
        raise ValueError(f"unexpected timestamp in {path}: {ts!r}")
    return ts[:7]


def _profile_without_month(panel: str, panel_dir: Path, holdout_month: str, official):
    train_files = official.files(panel_dir, "train")
    if not train_files:
        raise FileNotFoundError(f"{panel}: no unmasked train files")
    fit_files = [p for p in train_files if _frame_month(p) != holdout_month]
    held_files = [p for p in train_files if _frame_month(p) == holdout_month]
    if not held_files:
        available = sorted({_frame_month(p) for p in train_files})
        raise ValueError(
            f"{panel}: holdout month {holdout_month} not found; available={available}"
        )
    if not fit_files:
        raise ValueError(f"{panel}: no train data remains after holding out {holdout_month}")

    first = pd.read_parquet(train_files[0], columns=["link_id"])
    link_ids = sorted(first["link_id"].astype(str).unique())
    link_index = {link_id: i for i, link_id in enumerate(link_ids)}
    n_links = len(link_ids)
    n_slots = 7 * 288
    speed_sum = np.zeros((n_links, n_slots), dtype=np.float64)
    speed_count = np.zeros((n_links, n_slots), dtype=np.int64)
    flow_sum = np.zeros((n_links, n_slots), dtype=np.float64)
    flow_count = np.zeros((n_links, n_slots), dtype=np.int64)

    for path in fit_files:
        frame = pd.read_parquet(
            path,
            columns=["timestamp", "link_id", "speed_kmh", "flow_vph", "pct_observed"],
        )
        frame["link_id"] = frame["link_id"].astype(str)
        li = frame["link_id"].map(link_index).fillna(-1).to_numpy(dtype=np.int64)
        known = li >= 0
        weekday, tod = official.slot_values(frame)
        slot = weekday * 288 + tod
        eligible = (
            pd.to_numeric(frame["pct_observed"], errors="coerce").ge(75)
            & frame["speed_kmh"].notna()
            & frame["flow_vph"].notna()
        ).to_numpy()
        speed = pd.to_numeric(frame["speed_kmh"], errors="coerce").to_numpy(dtype=float)
        flow = pd.to_numeric(frame["flow_vph"], errors="coerce").to_numpy(dtype=float)
        valid_speed = known & eligible & np.isfinite(speed)
        valid_flow = known & eligible & np.isfinite(flow)
        np.add.at(speed_sum, (li[valid_speed], slot[valid_speed]), speed[valid_speed])
        np.add.at(speed_count, (li[valid_speed], slot[valid_speed]), 1)
        np.add.at(flow_sum, (li[valid_flow], slot[valid_flow]), flow[valid_flow])
        np.add.at(flow_count, (li[valid_flow], slot[valid_flow]), 1)

    speed_mean = np.zeros_like(speed_sum)
    flow_mean = np.zeros_like(flow_sum)
    np.divide(speed_sum, speed_count, out=speed_mean, where=speed_count > 0)
    np.divide(flow_sum, flow_count, out=flow_mean, where=flow_count > 0)
    speed_link = np.divide(
        speed_sum.sum(axis=1),
        np.maximum(speed_count.sum(axis=1), 1),
    )
    flow_link = np.divide(
        flow_sum.sum(axis=1),
        np.maximum(flow_count.sum(axis=1), 1),
    )
    return (
        {"link_ids": link_ids, "link_index": link_index, "mean": speed_mean, "fallback": speed_link},
        {"link_ids": link_ids, "link_index": link_index, "mean": flow_mean, "fallback": flow_link},
        {"speed_count": speed_count, "flow_count": flow_count},
        held_files,
        fit_files,
    )


def _historical_predictions(frame, official, speed_profile, flow_profile, counts):
    link_index = speed_profile["link_index"]
    weekday, tod = official.slot_values(frame)
    slot = weekday * 288 + tod
    li = frame["link_id"].astype(str).map(link_index).fillna(-1).to_numpy(dtype=np.int64)
    known = li >= 0
    safe_li = np.where(known, li, 0)
    speed = speed_profile["mean"][safe_li, slot]
    flow = flow_profile["mean"][safe_li, slot]
    speed = np.where(
        counts["speed_count"][safe_li, slot] == 0,
        speed_profile["fallback"][safe_li],
        speed,
    )
    flow = np.where(
        counts["flow_count"][safe_li, slot] == 0,
        flow_profile["fallback"][safe_li],
        flow,
    )
    return np.where(known, speed, np.nan), np.where(known, flow, np.nan)


def _load_truth(held_files: list[Path], holdout_month: str) -> pd.DataFrame:
    pieces = []
    cols = ["timestamp", "station_id", "link_id", "speed_kmh", "flow_vph", "is_score_eligible"]
    for path in held_files:
        frame = pd.read_parquet(path, columns=cols)
        frame = frame[frame["timestamp"].astype(str).str.startswith(holdout_month)]
        if not frame.empty:
            pieces.append(frame)
    if not pieces:
        raise ValueError(f"no truth rows found for holdout month {holdout_month}")
    truth = pd.concat(pieces, ignore_index=True)
    truth["timestamp"] = truth["timestamp"].astype(str)
    truth["station_id"] = truth["station_id"].astype(str)
    truth["link_id"] = truth["link_id"].astype(str)
    truth = truth.drop_duplicates(KEYS)
    return truth


def _template_keys(release: Path, panel: str, holdout_month: str) -> set[tuple[str, str, str, str]]:
    path = release / "task1" / panel / "train" / "sample_submission_state.csv"
    frame = pd.read_csv(
        path,
        usecols=["timestamp", "station_id", "link_id", "mask_regime"],
        dtype=str,
    )
    frame = frame[frame["timestamp"].str.startswith(holdout_month)]
    return set(
        map(
            tuple,
            frame[["timestamp", "station_id", "link_id", "mask_regime"]].itertuples(
                index=False, name=None
            ),
        )
    )


def _masked_holdout_files(panel_dir: Path, official, holdout_month: str) -> list[Path]:
    out = []
    for path in official.masked_files(panel_dir, "train"):
        month = _path_month(path)
        if month is None:
            try:
                month = _frame_month(path)
            except Exception:
                continue
        if month == holdout_month:
            out.append(path)
    if not out:
        raise ValueError(f"no masked train partitions found for {holdout_month}")
    return out


def _metric_row(
    panel: str,
    regime: str,
    model: str,
    true_speed: np.ndarray,
    true_flow: np.ndarray,
    pred_speed: np.ndarray,
    pred_flow: np.ndarray,
    lanes: np.ndarray,
    official,
) -> dict[str, object]:
    usable = (
        np.isfinite(true_speed)
        & np.isfinite(true_flow)
        & np.isfinite(pred_speed)
        & np.isfinite(pred_flow)
        & np.isfinite(lanes)
        & (lanes > 0)
    )
    n = int(usable.sum())
    if n == 0:
        return {
            "panel": panel,
            "regime": regime,
            "model": model,
            "n_cells": 0,
            "rmse_speed_kmh": float("nan"),
            "rmse_flow_vph_per_lane": float("nan"),
            "S_speed": 0.0,
            "S_flow": 0.0,
            "S_state": 0.0,
        }
    ds = pred_speed[usable] - true_speed[usable]
    dq = (pred_flow[usable] - true_flow[usable]) / lanes[usable]
    rmse_speed = float(np.sqrt(np.mean(ds * ds)))
    rmse_flow = float(np.sqrt(np.mean(dq * dq)))
    s_speed = max(0.0, 1.0 - rmse_speed / official.SPEED_NORMALIZER)
    s_flow = max(0.0, 1.0 - rmse_flow / official.FLOW_NORMALIZER)
    s_state = official.SPEED_WEIGHT * s_speed + official.FLOW_WEIGHT * s_flow
    return {
        "panel": panel,
        "regime": regime,
        "model": model,
        "n_cells": n,
        "rmse_speed_kmh": rmse_speed,
        "rmse_flow_vph_per_lane": rmse_flow,
        "S_speed": s_speed,
        "S_flow": s_flow,
        "S_state": s_state,
    }


def _fingerprint(paths: list[Path], root: Path) -> str:
    h = hashlib.sha256()
    for path in sorted(set(p.resolve() for p in paths), key=lambda p: str(p)):
        st = path.stat()
        try:
            rel = path.relative_to(root.resolve())
        except ValueError:
            rel = path
        h.update(f"{rel.as_posix()}\0{st.st_size}\n".encode("utf-8"))
    return h.hexdigest()


def evaluate_panel(
    panel: str,
    release: Path,
    holdout_month: str,
    official,
    shortgap,
    max_gap_steps: int,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    panel_dir = release / "corridors" / panel
    official.check_release_root(release, panel)
    speed_profile, flow_profile, counts, held_files, fit_files = _profile_without_month(
        panel, panel_dir, holdout_month, official
    )
    truth = _load_truth(held_files, holdout_month)
    template = _template_keys(release, panel, holdout_month)
    masked_files = _masked_holdout_files(panel_dir, official, holdout_month)
    lanes_by_station = official.station_lanes(panel_dir)

    rows_by_regime: dict[str, list[pd.DataFrame]] = {r: [] for r in REGIME_ORDER}
    temporal_used = 0
    target_total = 0

    for path in masked_files:
        frame = pd.read_parquet(
            path,
            columns=[
                "timestamp",
                "station_id",
                "link_id",
                "speed_kmh",
                "flow_vph",
                "mask_regime",
            ],
        ).copy()
        frame["timestamp"] = frame["timestamp"].astype(str)
        frame["station_id"] = frame["station_id"].astype(str)
        frame["link_id"] = frame["link_id"].astype(str)
        frame["mask_regime"] = frame["mask_regime"].astype(str)
        frame = frame[frame["timestamp"].str.startswith(holdout_month)].reset_index(drop=True)
        if frame.empty:
            continue

        base_speed, base_flow = _historical_predictions(
            frame, official, speed_profile, flow_profile, counts
        )
        temporal_speed, temporal_flow = shortgap._temporal_estimates(
            frame, max_gap_steps
        )
        temporal_pair = np.isfinite(temporal_speed) & np.isfinite(temporal_flow)
        cand_speed = np.maximum(
            np.where(temporal_pair, temporal_speed, base_speed), 0.0
        )
        cand_flow = np.maximum(
            np.where(temporal_pair, temporal_flow, base_flow), 0.0
        )

        keys = list(
            zip(
                frame["timestamp"],
                frame["station_id"],
                frame["link_id"],
                frame["mask_regime"],
            )
        )
        target = np.fromiter((k in template for k in keys), dtype=bool, count=len(frame))
        if not target.any():
            continue
        temporal_used += int(np.count_nonzero(target & temporal_pair))
        target_total += int(target.sum())

        pred = frame.loc[target, KEYS + ["mask_regime"]].copy()
        pred["base_speed"] = base_speed[target]
        pred["base_flow"] = base_flow[target]
        pred["candidate_speed"] = cand_speed[target]
        pred["candidate_flow"] = cand_flow[target]
        pred = pred.merge(
            truth[KEYS + ["speed_kmh", "flow_vph", "is_score_eligible"]],
            on=KEYS,
            how="left",
            validate="one_to_one",
        )
        pred = pred[pred["is_score_eligible"].astype(bool)].copy()
        if pred.empty:
            continue
        pred["lanes"] = official.lane_vector(
            pred["station_id"], pred["link_id"], lanes_by_station
        )
        for regime, group in pred.groupby("mask_regime", sort=False):
            if regime in rows_by_regime:
                rows_by_regime[regime].append(group)

    metrics: list[dict[str, object]] = []
    for regime in REGIME_ORDER:
        if rows_by_regime[regime]:
            group = pd.concat(rows_by_regime[regime], ignore_index=True)
        else:
            group = pd.DataFrame(
                columns=[
                    "speed_kmh",
                    "flow_vph",
                    "base_speed",
                    "base_flow",
                    "candidate_speed",
                    "candidate_flow",
                    "lanes",
                ]
            )
        true_speed = pd.to_numeric(
            group.get("speed_kmh"), errors="coerce"
        ).to_numpy(dtype=float)
        true_flow = pd.to_numeric(
            group.get("flow_vph"), errors="coerce"
        ).to_numpy(dtype=float)
        lanes = pd.to_numeric(group.get("lanes"), errors="coerce").to_numpy(
            dtype=float
        )
        for model, sc, fl in [
            ("historical_mean_holdout", "base_speed", "base_flow"),
            ("shortgap_holdout", "candidate_speed", "candidate_flow"),
        ]:
            pred_speed = pd.to_numeric(
                group.get(sc), errors="coerce"
            ).to_numpy(dtype=float)
            pred_flow = pd.to_numeric(
                group.get(fl), errors="coerce"
            ).to_numpy(dtype=float)
            metrics.append(
                _metric_row(
                    panel,
                    regime,
                    model,
                    true_speed,
                    true_flow,
                    pred_speed,
                    pred_flow,
                    lanes,
                    official,
                )
            )

    manifest_paths = fit_files + held_files + masked_files + [
        release / "task1" / panel / "train" / "sample_submission_state.csv",
        panel_dir / "network" / "fd_parameters.csv",
        panel_dir / "network" / "links.csv",
    ]
    manifest_paths = [p for p in manifest_paths if p.exists()]
    meta = {
        "panel": panel,
        "holdout_month": holdout_month,
        "fit_unmasked_files": len(fit_files),
        "holdout_unmasked_files": len(held_files),
        "holdout_masked_files": len(masked_files),
        "target_rows_seen": target_total,
        "shortgap_temporal_pair_rows": temporal_used,
        "shortgap_temporal_pair_share": (
            temporal_used / target_total if target_total else 0.0
        ),
        "input_manifest_sha256": _fingerprint(manifest_paths, release),
    }
    return metrics, meta


def _aggregate(metrics: pd.DataFrame, families: dict[str, str]) -> dict[str, object]:
    out: dict[str, object] = {}
    panel_macro = (
        metrics.groupby(["panel", "model"], as_index=False)["S_state"]
        .mean()
        .rename(columns={"S_state": "panel_S_state"})
    )
    panel_macro["family_id"] = panel_macro["panel"].map(families)
    family = panel_macro.groupby(
        ["family_id", "model"], as_index=False
    )["panel_S_state"].mean()
    overall = family.groupby("model", as_index=False)["panel_S_state"].mean()
    scores = dict(zip(overall["model"], overall["panel_S_state"]))
    out["overall_S_state"] = scores
    if "historical_mean_holdout" in scores and "shortgap_holdout" in scores:
        out["overall_delta"] = float(
            scores["shortgap_holdout"] - scores["historical_mean_holdout"]
        )
    out["panel_macro"] = panel_macro.to_dict(orient="records")
    out["family_macro"] = family.to_dict(orient="records")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--official-repo", type=Path, required=True)
    ap.add_argument("--release-root", type=Path, required=True)
    ap.add_argument("--shortgap", type=Path, required=True)
    ap.add_argument("--holdout-month", default="2031-02")
    ap.add_argument("--max-gap-steps", type=int, default=6)
    ap.add_argument("--panel", action="append")
    ap.add_argument("--output-dir", type=Path, required=True)
    args = ap.parse_args()
    if not MONTH_RE.fullmatch(args.holdout_month):
        raise SystemExit("--holdout-month must be YYYY-MM")
    if args.max_gap_steps < 1:
        raise SystemExit("--max-gap-steps must be >=1")

    started = time.perf_counter()
    official = _load_official(args.official_repo)
    shortgap = _load_shortgap(args.shortgap)
    release = args.release_root.resolve()
    manifest_path = args.official_repo.resolve() / "config" / "corridors.json"
    contract = json.loads(manifest_path.read_text(encoding="utf-8"))
    panels = [p["corridor_id"] for p in contract["panels"]]
    if args.panel:
        requested = set(args.panel)
        unknown = sorted(requested - set(panels))
        if unknown:
            raise SystemExit(f"unknown --panel values: {unknown}")
        panels = [p for p in panels if p in requested]
    families = {p["corridor_id"]: p["family_id"] for p in contract["panels"]}

    all_metrics: list[dict[str, object]] = []
    panel_meta = []
    for panel in panels:
        print(
            f"[TrafficFlowBench holdout] {panel} month={args.holdout_month}",
            flush=True,
        )
        metrics, meta = evaluate_panel(
            panel,
            release,
            args.holdout_month,
            official,
            shortgap,
            args.max_gap_steps,
        )
        all_metrics.extend(metrics)
        panel_meta.append(meta)

    metrics_df = pd.DataFrame(all_metrics)
    aggregate = _aggregate(metrics_df, families)
    elapsed = time.perf_counter() - started
    rss_kib = (
        int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        if resource is not None
        else None
    )
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    metrics_path = output_dir / "task1_holdout_metrics.csv"
    metrics_df.to_csv(metrics_path, index=False)
    report = {
        "evidence_boundary": (
            "public train only; blocked calendar month excluded from profile fit; "
            "no leaderboard/private claim"
        ),
        "holdout_month": args.holdout_month,
        "max_gap_steps": args.max_gap_steps,
        "panels": panels,
        "panel_receipts": panel_meta,
        "aggregate": aggregate,
        "wall_seconds": elapsed,
        "peak_rss_kib": rss_kib,
        "metrics_csv": str(metrics_path),
    }
    report_path = output_dir / "task1_holdout_receipt.json"
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report["aggregate"], indent=2, sort_keys=True))
    print(f"Wrote {metrics_path}")
    print(f"Wrote {report_path}")


if __name__ == "__main__":
    main()
