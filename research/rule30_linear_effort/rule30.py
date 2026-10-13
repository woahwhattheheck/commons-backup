"""Exact small-horizon cellular-automaton oracles and model lemmas."""

from __future__ import annotations


def _step(row: dict[int, int], rule: int) -> dict[int, int]:
    if not row:
        return {}
    lo = min(row) - 1
    hi = max(row) + 1
    out: dict[int, int] = {}
    for i in range(lo, hi + 1):
        left = row.get(i - 1, 0)
        center = row.get(i, 0)
        right = row.get(i + 1, 0)
        neighborhood = (left << 2) | (center << 1) | right
        value = (rule >> neighborhood) & 1
        if value:
            out[i] = 1
    return out


def center_bit(rule: int, n: int) -> int:
    """Return the time-n center bit from the lone-1 initial condition."""
    if not (0 <= rule <= 255):
        raise ValueError("elementary rule must be in 0..255")
    if n < 0:
        raise ValueError("n must be nonnegative")
    row = {0: 1}
    for _ in range(n):
        row = _step(row, rule)
    return row.get(0, 0)


def center_prefix(rule: int, horizon: int) -> tuple[int, ...]:
    if horizon < 0:
        raise ValueError("horizon must be nonnegative")
    row = {0: 1}
    out = [1]
    for _ in range(horizon):
        row = _step(row, rule)
        out.append(row.get(0, 0))
    return tuple(out)


def binary_mod(n: int, modulus: int) -> int:
    """Compute n mod modulus by one left-to-right pass over binary digits."""
    if n < 0:
        raise ValueError("n must be nonnegative")
    if modulus <= 0:
        raise ValueError("modulus must be positive")
    residue = 0
    for bit in bin(n)[2:]:
        residue = (2 * residue + (bit == "1")) % modulus
    return int(residue)


def eventually_periodic_predictor(
    n: int, prefix: tuple[int, ...], period: tuple[int, ...]
) -> int:
    """Exact predictor for a sequence specified by finite prefix + period.

    This is a constructive witness for the conditional theorem:
    eventual periodicity implies an O(log n)-step predictor on a standard
    binary-input model, because comparison with a fixed threshold and
    reduction modulo a fixed period can be implemented by finite-state scans.
    """
    if n < 0:
        raise ValueError("n must be nonnegative")
    if not period:
        raise ValueError("period must be nonempty")
    if n < len(prefix):
        return prefix[n]
    return period[binary_mod(n - len(prefix), len(period))]


def rule150_center_closed_form(_n: int) -> int:
    """The lone-seed center column of Rule 150 is identically 1."""
    if _n < 0:
        raise ValueError("n must be nonnegative")
    return 1
