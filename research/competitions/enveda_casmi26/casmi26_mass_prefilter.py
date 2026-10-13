from __future__ import annotations

import argparse
import json
import time
from typing import Sequence, Tuple

import numpy as np

from casmi26_hybrid_ranker import ADDUCT_DELTA


def neutral_masses_numpy(
    precursor_mz: Sequence[float] | np.ndarray,
    adducts: Sequence[str] | np.ndarray,
) -> np.ndarray:
    """Convert a whole precursor/adduct batch to neutral masses.

    Unsupported adducts, non-finite precursors, and non-positive neutral masses
    are emitted as NaN so callers can reject them without branching per row.
    """
    prec = np.asarray(precursor_mz, dtype=np.float64)
    ads = np.asarray(adducts, dtype=object)
    if prec.shape != ads.shape:
        raise ValueError("precursor_mz and adducts must have the same shape")

    delta = np.full(prec.shape, np.nan, dtype=np.float64)
    for adduct, value in ADDUCT_DELTA.items():
        delta[ads == adduct] = value

    neutral = prec - delta
    valid = np.isfinite(prec) & np.isfinite(neutral) & (neutral > 0)
    neutral[~valid] = np.nan
    return neutral


def mass_window_mask(
    neutral_masses: Sequence[float] | np.ndarray,
    query_masses: Sequence[float] | np.ndarray,
    *,
    ppm: float = 15.0,
) -> np.ndarray:
    """Return rows lying inside at least one query neutral-mass window.

    Two nearest sorted targets are checked because ppm error uses the target as
    denominator. Complexity is O(N log Q) in vectorized NumPy search rather than
    O(N * Python-row-overhead).
    """
    neutral = np.asarray(neutral_masses, dtype=np.float64)
    targets = np.asarray(query_masses, dtype=np.float64)
    targets = targets[np.isfinite(targets) & (targets > 0)]
    if targets.size == 0:
        return np.zeros(neutral.shape, dtype=bool)
    targets = np.unique(np.sort(targets))

    valid = np.isfinite(neutral) & (neutral > 0)
    safe = np.where(valid, neutral, targets[0])
    pos = np.searchsorted(targets, safe, side="left")
    left_idx = np.clip(pos - 1, 0, targets.size - 1)
    right_idx = np.clip(pos, 0, targets.size - 1)
    left = targets[left_idx]
    right = targets[right_idx]

    err_left = np.abs(safe - left) / left * 1e6
    err_right = np.abs(safe - right) / right * 1e6
    return valid & (np.minimum(err_left, err_right) <= float(ppm))


def prefilter_batch(
    precursor_mz: Sequence[float] | np.ndarray,
    adducts: Sequence[str] | np.ndarray,
    query_masses: Sequence[float] | np.ndarray,
    *,
    ppm: float = 15.0,
) -> Tuple[np.ndarray, np.ndarray]:
    """Return (mask, neutral_masses) for a record batch.

    Only rows selected by mask should be converted to the heavier Python row
    representation used by the R1 spectral scorer.
    """
    neutral = neutral_masses_numpy(precursor_mz, adducts)
    return mass_window_mask(neutral, query_masses, ppm=ppm), neutral


def _scalar_reference(neutral: np.ndarray, targets: np.ndarray, ppm: float) -> np.ndarray:
    """Slow reference used only for focused correctness checks."""
    out = np.zeros(neutral.shape, dtype=bool)
    sorted_targets = np.sort(targets)
    for i, mass in enumerate(neutral):
        if not np.isfinite(mass) or mass <= 0:
            continue
        pos = int(np.searchsorted(sorted_targets, mass, side="left"))
        for j in (pos - 1, pos):
            if 0 <= j < len(sorted_targets):
                target = float(sorted_targets[j])
                if abs(mass - target) / target * 1e6 <= ppm:
                    out[i] = True
                    break
    return out


def selftest() -> None:
    q = np.array([250.0, 300.0, 350.0])
    ads = np.array(["[M+H]+", "[M-H]-", "bad", "[M+Na]+"], dtype=object)
    expected_neutral = np.array([250.0, 300.0, np.nan, 350.0])
    prec = np.array([
        expected_neutral[0] + ADDUCT_DELTA[ads[0]],
        expected_neutral[1] + ADDUCT_DELTA[ads[1]],
        300.0,
        expected_neutral[3] + ADDUCT_DELTA[ads[3]],
    ])
    neutral = neutral_masses_numpy(prec, ads)
    assert np.allclose(neutral[[0, 1, 3]], expected_neutral[[0, 1, 3]])
    assert np.isnan(neutral[2])
    mask = mass_window_mask(neutral, q, ppm=5.0)
    assert mask.tolist() == [True, True, False, True]

    rng = np.random.default_rng(41)
    targets = np.sort(rng.uniform(180.0, 600.0, size=137))
    masses = rng.uniform(180.0, 600.0, size=5000)
    masses[:200] = targets[rng.integers(0, len(targets), size=200)] * (
        1.0 + rng.uniform(-9.0, 9.0, size=200) * 1e-6
    )
    masses[200] = np.nan
    fast = mass_window_mask(masses, targets, ppm=10.0)
    slow = _scalar_reference(masses, targets, ppm=10.0)
    assert np.array_equal(fast, slow)


def benchmark(rows: int = 2_500_000, queries: int = 400, ppm: float = 15.0, seed: int = 17) -> dict:
    rng = np.random.default_rng(seed)
    query_masses = np.sort(rng.uniform(220.0, 470.0, size=queries))
    keys = np.array(list(ADDUCT_DELTA), dtype=object)
    adduct_idx = rng.integers(0, len(keys), size=rows)
    adducts = keys[adduct_idx]
    deltas = np.array([ADDUCT_DELTA[k] for k in keys], dtype=np.float64)[adduct_idx]

    neutral = rng.uniform(220.0, 470.0, size=rows)
    injected = min(queries * 4, rows)
    chosen = np.resize(query_masses, injected)
    neutral[:injected] = chosen * (1.0 + rng.uniform(-10.0, 10.0, size=injected) * 1e-6)
    precursor = neutral + deltas

    t0 = time.perf_counter()
    mask, converted = prefilter_batch(precursor, adducts, query_masses, ppm=ppm)
    elapsed = time.perf_counter() - t0

    return {
        "rows": int(rows),
        "query_masses": int(queries),
        "ppm": float(ppm),
        "retained_rows": int(mask.sum()),
        "retained_fraction": float(mask.mean()),
        "injected_near_hits": int(injected),
        "injected_retained": int(mask[:injected].sum()),
        "elapsed_seconds": elapsed,
        "rows_per_second": rows / max(elapsed, 1e-12),
        "neutral_finite_fraction": float(np.isfinite(converted).mean()),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="CASMI26 vectorized mass-window prefilter")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--benchmark", action="store_true")
    ap.add_argument("--rows", type=int, default=2_500_000)
    ap.add_argument("--queries", type=int, default=400)
    args = ap.parse_args()
    if args.selftest:
        selftest()
        print("selftest: PASS")
    if args.benchmark:
        print(json.dumps(benchmark(rows=args.rows, queries=args.queries), indent=2))
    if not args.selftest and not args.benchmark:
        ap.print_help()


if __name__ == "__main__":
    main()
