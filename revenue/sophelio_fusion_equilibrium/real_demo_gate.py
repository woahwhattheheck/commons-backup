#!/usr/bin/env python3
"""Run target-blind feature extraction on the starter's six public demo shots.

The demo parquets are Git-LFS objects in the pinned organizer starter. This
script intentionally does not fetch them: run ``git lfs pull`` in a checkout of
``Sophelio/fusion-equilibrium-challenge-starter`` and point ``--demo-dir`` at
its ``parquet_data`` directory. It records exact byte hashes and proves that
mutating released target columns cannot alter the feature matrix.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

try:
    from .toolkit import OFFICIAL_STARTER_SHA, extract_features
except ImportError:  # direct script execution from repository root
    from toolkit import OFFICIAL_STARTER_SHA, extract_features

EXPECTED = {
    "d3d_shot_203702.parquet": "DIII-D",
    "d3d_shot_203703.parquet": "DIII-D",
    "d3d_shot_203704.parquet": "DIII-D",
    "mast_shot_28348.parquet": "MAST",
    "mast_shot_28350.parquet": "MAST",
    "mast_shot_28351.parquet": "MAST",
}
TARGET_KEYS = ("efit_psirz", "efit_q95", "efit_beta_n")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _poison_targets(row: dict) -> dict:
    out = dict(row)
    for key in TARGET_KEYS:
        if key in out:
            out[key] = object()  # feature extraction must never inspect targets
    return out


def run(demo_dir: Path) -> dict:
    try:
        import pandas as pd
    except ImportError as exc:  # pragma: no cover - environment diagnostic
        raise SystemExit("pandas is required for the real demo gate") from exc

    rows = []
    for name, machine in EXPECTED.items():
        path = demo_dir / name
        if not path.is_file():
            raise SystemExit(f"missing organizer demo parquet: {path}")
        try:
            frame = pd.read_parquet(path)
        except ImportError as exc:  # pandas reports missing parquet engine here
            raise SystemExit(
                "a parquet engine is required (organizer starter uses pyarrow); "
                "install the starter dependencies before this gate"
            ) from exc
        if len(frame) != 1:
            raise SystemExit(f"{name}: expected exactly one shot row, got {len(frame)}")
        row = frame.iloc[0].to_dict()
        x = extract_features(row, machine)
        poisoned = extract_features(_poison_targets(row), machine)
        if not np.array_equal(x, poisoned):
            raise SystemExit(f"{name}: target mutation changed input features")
        if x.shape[0] != len(np.asarray(row["efit_times"])) or x.shape[1] != 46:
            raise SystemExit(f"{name}: feature shape mismatch {x.shape}")
        if not np.isfinite(x).all():
            raise SystemExit(f"{name}: non-finite feature output")
        rows.append({
            "file": name,
            "machine": machine,
            "sha256": sha256_file(path),
            "bytes": path.stat().st_size,
            "frames": int(x.shape[0]),
            "features": int(x.shape[1]),
            "feature_min": float(np.min(x)),
            "feature_max": float(np.max(x)),
            "target_blind_invariant": True,
        })
    receipt = {
        "starter_sha": OFFICIAL_STARTER_SHA,
        "demo_dir": str(demo_dir.resolve()),
        "shots": rows,
        "all_six_passed": len(rows) == 6,
        "truth": "public organizer demo input gate only; not leaderboard evidence",
    }
    return receipt


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--demo-dir", type=Path, required=True)
    ap.add_argument("--receipt", type=Path)
    args = ap.parse_args()
    receipt = run(args.demo_dir)
    text = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
