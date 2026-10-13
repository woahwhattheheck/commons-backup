"""Deterministic synthetic stress cases for the streaming detector."""

from __future__ import annotations

import math
import random
from statistics import median
from typing import Dict, List, Optional, Tuple

from detector import OnlineBreakDetector


def make_case(
    kind: str,
    seed: int,
    *,
    history_length: int = 1200,
    online_length: int = 240,
    tau: int = 60,
) -> Tuple[List[float], List[float], Optional[int]]:
    if history_length < 32:
        raise ValueError("history_length must be >= 32")
    if online_length < 16:
        raise ValueError("online_length must be >= 16")
    if not (8 <= tau < online_length):
        raise ValueError("tau out of range")

    rng = random.Random(seed)
    historical = [rng.gauss(0.0, 1.0) for _ in range(history_length)]
    prefix = [rng.gauss(0.0, 1.0) for _ in range(tau)]

    if kind == "null":
        online = prefix + [rng.gauss(0.0, 1.0) for _ in range(online_length - tau)]
        return historical, online, None

    if kind == "mean":
        suffix = [rng.gauss(2.0, 1.0) for _ in range(online_length - tau)]
    elif kind == "variance":
        suffix = [rng.gauss(0.0, 3.0) for _ in range(online_length - tau)]
    elif kind == "trend":
        count = online_length - tau
        suffix = [
            rng.gauss(0.0, 1.0) + 0.035 * (index + 1)
            for index in range(count)
        ]
    elif kind == "persistence":
        rho = 0.82
        innovation_scale = math.sqrt(1.0 - rho * rho)
        current = prefix[-1] if prefix else 0.0
        suffix = []
        for _ in range(online_length - tau):
            current = rho * current + innovation_scale * rng.gauss(0.0, 1.0)
            suffix.append(current)
    elif kind == "outlier_only":
        suffix = [rng.gauss(0.0, 1.0) for _ in range(online_length - tau)]
        suffix[2] = 18.0
        return historical, prefix + suffix, None
    else:
        raise ValueError(f"unknown synthetic kind: {kind}")

    return historical, prefix + suffix, tau


def score_series(historical: List[float], online: List[float]) -> List[float]:
    detector = OnlineBreakDetector(historical)
    return [detector.update(value) for value in online]


def first_crossing(scores: List[float], threshold: float = 0.5) -> Optional[int]:
    for index, score in enumerate(scores):
        if score >= threshold:
            return index
    return None


def benchmark(seed_count: int = 16) -> Dict[str, object]:
    """Return deterministic public-data-free smoke metrics."""
    result: Dict[str, object] = {}
    null_maxima = []
    for seed in range(seed_count):
        history, online, _ = make_case("null", 1000 + seed)
        null_maxima.append(max(score_series(history, online)))
    result["nullMaxMedian"] = median(null_maxima)
    result["nullFalseAlarmRateAt0_5"] = sum(v >= 0.5 for v in null_maxima) / seed_count

    for kind in ("mean", "variance", "trend", "persistence"):
        delays = []
        hits = 0
        for seed in range(seed_count):
            history, online, tau = make_case(kind, 2000 + seed)
            assert tau is not None
            crossing = first_crossing(score_series(history, online))
            if crossing is not None and crossing >= tau:
                hits += 1
                delays.append(crossing - tau)
        result[kind] = {
            "hitRate": hits / seed_count,
            "medianDelay": median(delays) if delays else None,
        }
    return result
