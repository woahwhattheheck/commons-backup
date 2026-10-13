#!/usr/bin/env python3
"""Build a Task 1 TrafficFlowBench submission using bounded temporal interpolation.

This is a narrow alternative to the organizer historical-mean baseline:
- build the same train weekday/time-of-day profile as the organizer;
- on each released masked partition, linearly interpolate a target only when the
  same detector has finite observations on both sides and the complete missing
  run is no longer than --max-gap-steps five-minute cells;
- fall back to the organizer historical mean everywhere else.

The candidate never reads an unmasked validation/private layer. Task 1 is an
offline task, so using later observations from the same released masked period
is allowed by the public benchmark contract.
"""
from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

OUTPUT_COLUMNS = [
    "panel", "timestamp", "station_id", "link_id", "mask_regime",
    "speed_kmh", "flow_vph",
]


def _load_official(official_repo: Path):
    src = official_repo.resolve() / "src"
    if not src.is_dir():
        raise SystemExit(f"--official-repo has no src/ directory: {official_repo}")
    sys.path.insert(0, str(src))
    return importlib.import_module("task1.baseline_task1_historical_mean")


def _interpolate_short_gaps(
    times_ns: np.ndarray,
    values: np.ndarray,
    max_gap_steps: int,
) -> np.ndarray:
    """Fill only complete finite-bounded missing runs of at most max_gap_steps."""
    out = np.asarray(values, dtype=float).copy()
    good = np.flatnonzero(np.isfinite(out))
    if len(good) < 2:
        return out

    for left, right in zip(good[:-1], good[1:]):
        gap = int(right - left - 1)
        if gap <= 0 or gap > max_gap_steps:
            continue
        dt = int(times_ns[right] - times_ns[left])
        if dt <= 0:
            continue
        missing = np.arange(left + 1, right, dtype=np.int64)
        missing = missing[~np.isfinite(out[missing])]
        if missing.size == 0:
            continue
        alpha = (times_ns[missing] - times_ns[left]) / float(dt)
        out[missing] = out[left] + alpha * (out[right] - out[left])
    return out


def _temporal_estimates(
    frame: pd.DataFrame,
    max_gap_steps: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Return same-detector bounded interpolants aligned to frame row order."""
    n = len(frame)
    speed_out = np.full(n, np.nan, dtype=float)
    flow_out = np.full(n, np.nan, dtype=float)
    ts = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
    times_ns = ts.astype("int64").to_numpy()

    # Keep station_id in the key: multiple detectors may map to one link.
    work = frame[["station_id", "link_id"]].astype(str)
    groups = work.groupby(["station_id", "link_id"], sort=False).indices

    speed = pd.to_numeric(frame["speed_kmh"], errors="coerce").to_numpy(dtype=float)
    flow = pd.to_numeric(frame["flow_vph"], errors="coerce").to_numpy(dtype=float)

    for idx in groups.values():
        idx = np.asarray(idx, dtype=np.int64)
        order = np.argsort(times_ns[idx], kind="stable")
        rows = idx[order]
        speed_out[rows] = _interpolate_short_gaps(
            times_ns[rows], speed[rows], max_gap_steps
        )
        flow_out[rows] = _interpolate_short_gaps(
            times_ns[rows], flow[rows], max_gap_steps
        )

    return speed_out, flow_out


def _historical_predictions(
    frame: pd.DataFrame,
    official,
    speed_profile,
    flow_profile,
    counts,
) -> tuple[np.ndarray, np.ndarray]:
    link_index = speed_profile["link_index"]
    weekday, tod = official.slot_values(frame)
    slot = weekday * 288 + tod
    li = (
        frame["link_id"].astype(str).map(link_index).fillna(-1).to_numpy(dtype=np.int64)
    )
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


def build_panel(
    panel: str,
    release: Path,
    split: str,
    output: Path,
    write_header: bool,
    official,
    max_gap_steps: int,
) -> tuple[int, int]:
    panel_dir = release / "corridors" / panel
    official.check_release_root(release, panel)
    speed_profile, flow_profile, counts = official.build_profile(panel, panel_dir)

    template = pd.read_csv(
        release / "task1" / panel / split / "sample_submission_state.csv",
        usecols=["timestamp", "station_id", "link_id"],
        dtype=str,
    )
    template_keys = set(
        zip(template["timestamp"], template["station_id"], template["link_id"])
    )

    rows_written = 0
    temporal_used = 0

    for path in official.masked_files(panel_dir, split):
        frame = pd.read_parquet(
            path,
            columns=[
                "timestamp", "station_id", "link_id", "speed_kmh", "flow_vph",
                "mask_regime",
            ],
        ).copy()
        frame["station_id"] = frame["station_id"].astype(str)
        frame["link_id"] = frame["link_id"].astype(str)

        base_speed, base_flow = _historical_predictions(
            frame, official, speed_profile, flow_profile, counts
        )
        temporal_speed, temporal_flow = _temporal_estimates(frame, max_gap_steps)

        # Use temporal information only when both submitted channels are bounded
        # by observed values. Otherwise keep the complete historical pair.
        temporal_pair = np.isfinite(temporal_speed) & np.isfinite(temporal_flow)
        pred_speed = np.maximum(
            np.where(temporal_pair, temporal_speed, base_speed), 0.0
        )
        pred_flow = np.maximum(
            np.where(temporal_pair, temporal_flow, base_flow), 0.0
        )

        target = np.fromiter(
            (
                key in template_keys
                for key in zip(
                    frame["timestamp"].astype(str),
                    frame["station_id"],
                    frame["link_id"],
                )
            ),
            dtype=bool,
            count=len(frame),
        )
        valid = target & np.isfinite(pred_speed) & np.isfinite(pred_flow)
        if not valid.any():
            continue

        temporal_used += int(np.count_nonzero(valid & temporal_pair))
        regimes = frame["mask_regime"].astype(str).to_numpy()
        out = pd.DataFrame(
            {
                "panel": panel,
                "timestamp": frame.loc[valid, "timestamp"].astype(str).to_numpy(),
                "station_id": frame.loc[valid, "station_id"].to_numpy(),
                "link_id": frame.loc[valid, "link_id"].to_numpy(),
                "mask_regime": regimes[valid],
                "speed_kmh": pred_speed[valid],
                "flow_vph": pred_flow[valid],
            },
            columns=OUTPUT_COLUMNS,
        )
        out.to_csv(
            output,
            mode="w" if write_header else "a",
            header=write_header,
            index=False,
        )
        write_header = False
        rows_written += len(out)

    return rows_written, temporal_used


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--official-repo", type=Path, required=True)
    ap.add_argument("--release-root", type=Path, required=True)
    ap.add_argument(
        "--split", choices=["train", "validation", "private"], default="train"
    )
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--panel", action="append")
    ap.add_argument(
        "--max-gap-steps",
        type=int,
        default=6,
        help="fill only complete same-detector missing runs <= this many 5-minute cells",
    )
    args = ap.parse_args()
    if args.max_gap_steps < 1:
        raise SystemExit("--max-gap-steps must be >= 1")

    official = _load_official(args.official_repo)
    manifest = json.loads(
        (args.official_repo.resolve() / "config" / "corridors.json").read_text(
            encoding="utf-8"
        )
    )
    panels = [p["corridor_id"] for p in manifest["panels"]]
    if args.panel:
        requested = set(args.panel)
        unknown = sorted(requested - set(panels))
        if unknown:
            raise SystemExit(f"unknown --panel values: {unknown}")
        panels = [p for p in panels if p in requested]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        args.output.unlink()

    total = 0
    temporal_total = 0
    first = True
    for panel in panels:
        print(f"[Task1 short-gap] {panel}", flush=True)
        n, used = build_panel(
            panel,
            args.release_root.resolve(),
            args.split,
            args.output.resolve(),
            first,
            official,
            args.max_gap_steps,
        )
        total += n
        temporal_total += used
        first = False
        print(
            f"  wrote {n:,} targets; temporal pair used for {used:,} "
            f"({(used / n if n else 0.0):.1%})",
            flush=True,
        )

    print(
        f"Wrote {total:,} rows to {args.output.resolve()}; "
        f"temporal pair coverage {(temporal_total / total if total else 0.0):.1%}"
    )


if __name__ == "__main__":
    main()
