#!/usr/bin/env python3
"""Benchmark Ridge alpha on the official 2026 sleep-onset Simulated proxy.

This intentionally reproduces only the public warm-up smoke contract:
- target latency is capped at 600 s;
- per-channel signal means drift linearly with latency;
- bMAE uses bins [0, 40, 90, 300, 600] and equal weight over non-empty bins.

It does NOT claim Sleep-EDF or sealed Muse performance.
"""
from __future__ import annotations

import argparse
import json

import numpy as np
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

CAP_S = 600.0
BIN_EDGES = np.asarray([0.0, 40.0, 90.0, 300.0, 600.0], dtype=np.float64)


def binned_mae(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    y_true = np.asarray(y_true, dtype=np.float64).ravel()
    y_pred = np.asarray(y_pred, dtype=np.float64).ravel()
    err = np.abs(y_pred - y_true)
    idx = np.digitize(y_true, BIN_EDGES[1:-1], right=False)
    in_range = (y_true >= BIN_EDGES[0]) & (y_true <= BIN_EDGES[-1])
    maes = [
        err[in_range & (idx == b)].mean()
        for b in range(len(BIN_EDGES) - 1)
        if np.any(in_range & (idx == b))
    ]
    return float(np.mean(maes)) if maes else float("nan")


def make_simulated(
    seed: int,
    *,
    n_chans: int = 4,
    n_times: int = 500,
    n_train: int = 300,
    n_test: int = 150,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    slope = rng.standard_normal(n_chans) * 4.0

    def make_windows(n: int) -> tuple[np.ndarray, np.ndarray]:
        y = np.minimum(rng.exponential(scale=250.0, size=n), CAP_S)
        x = rng.standard_normal((n, n_chans, n_times)).astype(np.float32)
        x += (slope[:, None] * (y[:, None, None] / CAP_S)).astype(np.float32)
        return x, y.astype(np.float32)

    x_train, y_train = make_windows(n_train)
    x_test, y_test = make_windows(n_test)
    return x_train, y_train, x_test, y_test


def evaluate(seed: int, alpha: float) -> dict[str, float]:
    x_train, y_train, x_test, y_test = make_simulated(seed)
    train_features = x_train.mean(axis=-1)
    test_features = x_test.mean(axis=-1)

    model = make_pipeline(StandardScaler(), Ridge(alpha=alpha))
    model.fit(train_features, y_train)
    pred = np.clip(model.predict(test_features), 0.0, CAP_S)
    return {
        "bmae": binned_mae(y_test, pred),
        "mae": float(np.abs(pred - y_test).mean()),
    }


def parse_seeds(value: str) -> list[int]:
    if ":" in value:
        start, stop = value.split(":", 1)
        return list(range(int(start), int(stop)))
    return [int(part) for part in value.split(",") if part.strip()]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", default="0:50")
    parser.add_argument("--alphas", default="1,0.1,0.01")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    seeds = parse_seeds(args.seeds)
    alphas = [float(v) for v in args.alphas.split(",")]
    per_seed = {
        str(seed): {str(alpha): evaluate(seed, alpha) for alpha in alphas}
        for seed in seeds
    }

    summary = {}
    for alpha in alphas:
        key = str(alpha)
        bmae = np.asarray([per_seed[str(seed)][key]["bmae"] for seed in seeds])
        mae = np.asarray([per_seed[str(seed)][key]["mae"] for seed in seeds])
        summary[key] = {
            "mean_bmae": float(bmae.mean()),
            "median_bmae": float(np.median(bmae)),
            "p95_bmae": float(np.percentile(bmae, 95)),
            "mean_mae": float(mae.mean()),
        }

    if args.json:
        print(json.dumps({"seeds": seeds, "summary": summary, "per_seed": per_seed}, indent=2))
    else:
        print("Official Simulated proxy only; lower is better.")
        for alpha in alphas:
            s = summary[str(alpha)]
            print(
                f"alpha={alpha:g}: mean bMAE={s['mean_bmae']:.6f}, "
                f"median={s['median_bmae']:.6f}, p95={s['p95_bmae']:.6f}, "
                f"mean MAE={s['mean_mae']:.6f}"
            )
        if 1.0 in alphas:
            base = summary[str(1.0)]["mean_bmae"]
            for alpha in alphas:
                if alpha == 1.0:
                    continue
                score = summary[str(alpha)]["mean_bmae"]
                print(
                    f"vs alpha=1, alpha={alpha:g} mean-bMAE delta: "
                    f"{100.0 * (base - score) / base:+.3f}%"
                )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
