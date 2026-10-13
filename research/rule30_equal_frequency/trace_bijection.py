"""Exact finite-horizon trace maps for Wolfram Rule 30.

Coordinates use
    X_i(t+1) = F(X_{i-1}(t), X_i(t), X_{i+1}(t))
with
    F(l, c, r) = l XOR (c OR r).

For horizon T, ``right`` contains X_0(0),...,X_T(0), while
``left`` contains X_-1(0),...,X_-T(0). Cells outside [-T,T] are
irrelevant to X_0(1),...,X_0(T) and are treated as zero by the finite
simulator.

The key fact is Rule 30's left permutivity: for fixed c,r, flipping l
flips F. At time t, the newly exposed initial bit X_-t(0) can reach
X_0(t) only along the unique path that moves one cell right at every
step. On that path it is always the left argument. Hence, with all
closer initial bits held fixed, X_0(t) flips exactly when X_-t(0)
flips. Earlier center cells cannot depend on X_-t(0). This triangular
property makes the negative-prefix -> future-center-trace map a
bijection for every fixed nonnegative initial prefix.
"""

from __future__ import annotations

from collections.abc import Sequence


def _bit(value: int, *, name: str) -> int:
    if value not in (0, 1):
        raise ValueError(f"{name} must contain only 0/1 bits")
    return int(value)


def rule30(left: int, center: int, right: int) -> int:
    """Return one Rule-30 update bit."""
    l = _bit(left, name="left")
    c = _bit(center, name="center")
    r = _bit(right, name="right")
    return l ^ (c | r)


def _validated(bits: Sequence[int], *, name: str) -> tuple[int, ...]:
    return tuple(_bit(bit, name=name) for bit in bits)


def center_trace(right: Sequence[int], left: Sequence[int]) -> tuple[int, ...]:
    """Return X_0(1),...,X_0(T) for a finite horizon.

    ``left[k-1]`` is X_-k(0). At least T+1 right bits are required,
    representing X_0(0),...,X_T(0).
    """
    left_bits = _validated(left, name="left")
    horizon = len(left_bits)
    right_bits = _validated(right, name="right")
    if len(right_bits) < horizon + 1:
        raise ValueError("right must contain X_0(0)..X_T(0)")

    current: dict[int, int] = {}
    for j, bit in enumerate(right_bits[: horizon + 1]):
        if bit:
            current[j] = 1
    for k, bit in enumerate(left_bits, start=1):
        if bit:
            current[-k] = 1

    trace: list[int] = []
    for _ in range(horizon):
        nxt: dict[int, int] = {}
        # No site outside [-T,T] can enter the center light cone by
        # time T, so this fixed range is sufficient and deterministic.
        for j in range(-horizon, horizon + 1):
            value = rule30(
                current.get(j - 1, 0),
                current.get(j, 0),
                current.get(j + 1, 0),
            )
            if value:
                nxt[j] = 1
        current = nxt
        trace.append(current.get(0, 0))
    return tuple(trace)


def deepest_bit_flip(
    right: Sequence[int],
    closer_left: Sequence[int],
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """Return depth-t traces for the two choices of X_-t(0).

    If ``closer_left`` has length t-1, this compares the two traces
    produced by appending 0 or 1 as the newly exposed deepest bit.
    The theorem predicts equal prefixes through time t-1 and opposite
    final bits at time t.
    """
    closer = _validated(closer_left, name="closer_left")
    depth = len(closer) + 1
    right_bits = _validated(right, name="right")
    if len(right_bits) < depth + 1:
        raise ValueError("right must contain X_0(0)..X_t(0)")
    zero = center_trace(right_bits[: depth + 1], closer + (0,))
    one = center_trace(right_bits[: depth + 1], closer + (1,))
    return zero, one


def reconstruct_left_prefix(
    right: Sequence[int],
    target_future_trace: Sequence[int],
) -> tuple[int, ...]:
    """Construct the unique negative initial prefix for a target trace.

    The reconstruction is deliberately proof-transparent rather than
    optimized: at depth t it tries the only two values of X_-t(0).
    Left permutivity guarantees exactly one matches the requested
    center bit while all already-fixed earlier center bits remain
    unchanged.
    """
    target = _validated(target_future_trace, name="target_future_trace")
    horizon = len(target)
    right_bits = _validated(right, name="right")
    if len(right_bits) < horizon + 1:
        raise ValueError("right must contain X_0(0)..X_T(0)")

    chosen: list[int] = []
    for depth, desired in enumerate(target, start=1):
        matches: list[int] = []
        for candidate in (0, 1):
            trial = tuple(chosen) + (candidate,)
            trace = center_trace(right_bits[: depth + 1], trial)
            if trace[-1] == desired:
                matches.append(candidate)
        if len(matches) != 1:
            raise RuntimeError(
                f"triangular Rule-30 invariant failed at depth {depth}: "
                f"matches={matches}"
            )
        chosen.append(matches[0])
    result = tuple(chosen)
    if center_trace(right_bits[: horizon + 1], result) != target:
        raise RuntimeError("reconstructed prefix does not replay target trace")
    return result


def lone_seed_trace(horizon: int) -> tuple[int, ...]:
    """Return time-0 through time-T center bits for the lone-seed state."""
    if not isinstance(horizon, int) or isinstance(horizon, bool) or horizon < 0:
        raise ValueError("horizon must be a nonnegative integer")
    if horizon == 0:
        return (1,)
    right = (1,) + (0,) * horizon
    future = center_trace(right, (0,) * horizon)
    return (1,) + future
