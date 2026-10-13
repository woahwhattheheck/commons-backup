from __future__ import annotations

import math
from statistics import median
from typing import Iterable, Sequence


def _finite_nonnegative(value: float, name: str) -> float:
    out = float(value)
    if not math.isfinite(out) or out < 0:
        raise ValueError(f"{name} must be finite and non-negative")
    return out


def triangular_fd_flow_cap(
    speed_kmh: float,
    *,
    lanes: int,
    free_speed_kmh: float,
    capacity_per_lane_vph: float,
    backward_wave_kmh: float = 20.0,
) -> float:
    """A deterministic triangular-FD upper-envelope projection.

    This is a model helper, not the organizer's hidden Task 3 evaluator.
    """
    speed = _finite_nonnegative(speed_kmh, "speed_kmh")
    vf = _finite_nonnegative(free_speed_kmh, "free_speed_kmh")
    cap = _finite_nonnegative(capacity_per_lane_vph, "capacity_per_lane_vph")
    wave = _finite_nonnegative(backward_wave_kmh, "backward_wave_kmh")
    if lanes <= 0 or vf <= 0 or cap <= 0 or wave <= 0:
        raise ValueError("lanes/free speed/capacity/wave must be positive")
    critical_density = cap / vf
    jam_density = critical_density + cap / wave
    q_from_speed = speed * wave * jam_density / max(speed + wave, 1e-12)
    return lanes * min(cap, max(0.0, q_from_speed))


def reconstruct_state(
    *,
    historical_speed_kmh: float,
    historical_flow_vph: float,
    observed_neighbors: Iterable[tuple[float, float]],
    lanes: int,
    free_speed_kmh: float,
    capacity_per_lane_vph: float,
    neighbor_weight: float = 0.8,
) -> tuple[float, float]:
    """Blend visible local structure with a historical profile, then FD-project flow."""
    hs = _finite_nonnegative(historical_speed_kmh, "historical_speed_kmh")
    hf = _finite_nonnegative(historical_flow_vph, "historical_flow_vph")
    if not (0 <= neighbor_weight <= 1):
        raise ValueError("neighbor_weight must be in [0, 1]")
    neighbors = [(float(s), float(f)) for s, f in observed_neighbors]
    if not neighbors:
        speed, flow = hs, hf
    else:
        if any(not math.isfinite(s) or not math.isfinite(f) or s < 0 or f < 0 for s, f in neighbors):
            raise ValueError("observed_neighbors contains invalid state")
        ns = median(s for s, _ in neighbors)
        nf = median(f for _, f in neighbors)
        speed = neighbor_weight * ns + (1.0 - neighbor_weight) * hs
        flow = neighbor_weight * nf + (1.0 - neighbor_weight) * hf
    cap = triangular_fd_flow_cap(
        speed,
        lanes=lanes,
        free_speed_kmh=free_speed_kmh,
        capacity_per_lane_vph=capacity_per_lane_vph,
    )
    return max(0.0, min(speed, free_speed_kmh * 1.25)), max(0.0, min(flow, cap))


def queue_wave_forecast(
    speed_history_kmh: Sequence[Sequence[float]],
    free_speed_kmh: Sequence[float],
    *,
    horizons: int = 6,
) -> list[list[int]]:
    """Forecast an upstream-moving queue from only visible speed history.

    Link order is upstream -> downstream. A low/falling link seeds a wave; each
    horizon may grow the wave one link upstream. This intentionally consumes no
    future label.
    """
    if horizons <= 0:
        raise ValueError("horizons must be positive")
    if len(speed_history_kmh) < 4:
        raise ValueError("at least four history rows are required")
    n_links = len(free_speed_kmh)
    if n_links == 0 or any(len(row) != n_links for row in speed_history_kmh):
        raise ValueError("speed history shape mismatch")
    vf = [float(v) for v in free_speed_kmh]
    if any(not math.isfinite(v) or v <= 0 for v in vf):
        raise ValueError("free speeds must be positive finite values")
    rows = [[float(v) for v in row] for row in speed_history_kmh]
    if any(not math.isfinite(v) or v < 0 for row in rows for v in row):
        raise ValueError("history contains invalid speed")
    last = rows[-1]
    prev = rows[-2]
    prev2 = rows[-3]
    queued = {i for i, (s, f) in enumerate(zip(last, vf)) if s <= 0.60 * f}
    incipient = {
        i
        for i, f in enumerate(vf)
        if last[i] <= 0.75 * f and (last[i] - prev[i]) <= -3.0 and (prev[i] - prev2[i]) <= -2.0
    }
    wave = set(queued) | set(incipient)
    out: list[list[int]] = []
    for h in range(horizons):
        if h > 0:
            wave |= {i - 1 for i in list(wave) if i > 0}
        out.append([1 if i in wave else 0 for i in range(n_links)])
    return out


def projected_ridge_odme(
    incidence: Sequence[Sequence[float]],
    link_counts: Iterable[float],
    weak_prior: Iterable[float],
    *,
    regularization: float = 0.05,
    iterations: int = 1200,
) -> list[float]:
    """Solve ||Af-c||^2 + lambda||f-b||^2, f>=0 via projected gradient.

    The caller must pass the split-local weak prior from the same split as the
    link counts. The 2026-09-11 upstream correction makes this boundary explicit.
    """
    prior = [float(v) for v in weak_prior]
    counts = [float(v) for v in link_counts]
    if not prior or not counts or len(incidence) != len(counts):
        raise ValueError("invalid ODME dimensions")
    if any(len(row) != len(prior) for row in incidence):
        raise ValueError("incidence columns must match prior")
    if any(not math.isfinite(v) or v < 0 for v in prior + counts):
        raise ValueError("counts/prior must be finite and non-negative")
    if regularization < 0 or not math.isfinite(regularization) or iterations <= 0:
        raise ValueError("invalid solver parameters")
    a = [[float(x) for x in row] for row in incidence]
    if any(not math.isfinite(x) for row in a for x in row):
        raise ValueError("incidence contains non-finite values")
    # Conservative fixed step from an upper bound on ||A||_2^2.
    frob2 = sum(x * x for row in a for x in row)
    step = 0.24 / max(frob2 + regularization, 1e-12)
    f = list(prior)
    for _ in range(iterations):
        residual = [sum(x * y for x, y in zip(row, f)) - c for row, c in zip(a, counts)]
        grad = [2.0 * regularization * (f[j] - prior[j]) for j in range(len(f))]
        for row, r in zip(a, residual):
            for j, x in enumerate(row):
                grad[j] += 2.0 * x * r
        candidate = [max(0.0, x - step * g) for x, g in zip(f, grad)]
        if max(abs(x - y) for x, y in zip(candidate, f)) < 1e-10:
            f = candidate
            break
        f = candidate
    return f
