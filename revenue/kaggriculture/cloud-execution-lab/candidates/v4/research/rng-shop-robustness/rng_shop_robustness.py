# SPDX-License-Identifier: Apache-2.0
"""Exact, source-pinned research helpers for town-shop RNG robustness.

This module models only the pinned reference engine's end-of-day RNG contract. It
is deliberately not a policy hook: callers must supply empty-tile counts that are
already known to be legally reachable in the state they are studying.
"""

from dataclasses import dataclass
import random
from typing import FrozenSet, Iterable, Optional, Sequence, Tuple

ENGINE_SOURCE_BLOB = "3c202c7ee921da239356789e266b694635103fc4"
SEED_MULTIPLIER = 1_000_003
DEFAULT_SHOP_INTERVAL = 3
MAX_SHOP_INSTANCES = 8
SHOPS: Tuple[str, ...] = tuple(sorted((
    "BAKERY",
    "PIZZA_SHOP",
    "BRUNCH_SPOT",
    "YARN_STORE",
    "ICE_CREAM_SHOP",
    "PET_CAFE",
    "SMOOTHIE_SHOP",
    "FARMERS_MARKET",
)))


def _exact_nonnegative_int(name: str, value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative plain int")
    return value


def _plain_positive_int(name: str, value: int) -> int:
    value = _exact_nonnegative_int(name, value)
    if value == 0:
        raise ValueError(f"{name} must be positive")
    return value


def shop_unlock_due(
    day: int,
    unlocked_count: int,
    *,
    interval: int = DEFAULT_SHOP_INTERVAL,
    cap: int = MAX_SHOP_INSTANCES,
) -> bool:
    """Return the exact pinned-engine unlock predicate for an end-of-day call."""
    day = _exact_nonnegative_int("day", day)
    unlocked_count = _exact_nonnegative_int("unlocked_count", unlocked_count)
    interval = _plain_positive_int("interval", interval)
    cap = _plain_positive_int("cap", cap)
    next_day = day + 1
    return next_day > 0 and next_day % interval == 0 and unlocked_count < cap


def shop_draw(seed: int, day: int, empty_counts_by_player: Sequence[int]) -> str:
    """Predict the next shop from the exact pinned end-of-day RNG cursor.

    `_spawn_weeds` calls `rng.random()` exactly once for every `None` tile on
    every farm, then the engine calls `rng.choice(sorted(SHOPS))`. Plant/animal
    refreshes contain no RNG calls in the pinned source, so only the total number
    of `None` tiles matters to the shop cursor.
    """
    seed = _exact_nonnegative_int("seed", seed)
    day = _exact_nonnegative_int("day", day)
    if not isinstance(empty_counts_by_player, (list, tuple)) or not empty_counts_by_player:
        raise ValueError("empty_counts_by_player must be a non-empty list/tuple")
    counts = tuple(
        _exact_nonnegative_int(f"empty_counts_by_player[{index}]", count)
        for index, count in enumerate(empty_counts_by_player)
    )
    rng = random.Random((seed * SEED_MULTIPLIER) ^ day)
    for _ in range(sum(counts)):
        rng.random()
    return rng.choice(SHOPS)


@dataclass(frozen=True)
class RobustOption:
    """Outcome certificate for one reachable own empty-tile count."""

    own_empty_count: int
    rival_outcomes: Tuple[Tuple[int, str], ...]
    exact_shop: Optional[str]
    all_in_target_set: bool
    target_hits: int


def robust_options(
    seed: int,
    day: int,
    own_empty_counts: Iterable[int],
    rival_empty_counts: Iterable[int],
    *,
    target_shops: Iterable[str] = (),
) -> Tuple[RobustOption, ...]:
    """Evaluate own choices against every explicitly supplied rival count.

    No probability distribution is invented. `all_in_target_set` means every
    rival count in the supplied uncertainty set yields a member of
    `target_shops`; `exact_shop` is populated only when all rival counts yield
    the same shop.
    """
    seed = _exact_nonnegative_int("seed", seed)
    day = _exact_nonnegative_int("day", day)
    own = tuple(sorted({_exact_nonnegative_int("own_empty_count", value) for value in own_empty_counts}))
    rival = tuple(sorted({_exact_nonnegative_int("rival_empty_count", value) for value in rival_empty_counts}))
    if not own:
        raise ValueError("own_empty_counts must not be empty")
    if not rival:
        raise ValueError("rival_empty_counts must not be empty")
    targets: FrozenSet[str] = frozenset(target_shops)
    if any(shop not in SHOPS for shop in targets):
        raise ValueError("target_shops contains an unknown shop")

    results = []
    for own_count in own:
        outcomes = tuple((rival_count, shop_draw(seed, day, (own_count, rival_count)))
                         for rival_count in rival)
        unique = {shop for _, shop in outcomes}
        exact = next(iter(unique)) if len(unique) == 1 else None
        hits = sum(1 for _, shop in outcomes if shop in targets)
        results.append(RobustOption(
            own_empty_count=own_count,
            rival_outcomes=outcomes,
            exact_shop=exact,
            all_in_target_set=bool(targets) and hits == len(outcomes),
            target_hits=hits,
        ))
    return tuple(results)


def stable_shop_intervals(
    seed: int,
    day: int,
    total_empty_min: int,
    total_empty_max: int,
) -> Tuple[Tuple[int, int, str], ...]:
    """Return maximal consecutive total-empty windows with one exact shop."""
    seed = _exact_nonnegative_int("seed", seed)
    day = _exact_nonnegative_int("day", day)
    lo = _exact_nonnegative_int("total_empty_min", total_empty_min)
    hi = _exact_nonnegative_int("total_empty_max", total_empty_max)
    if lo > hi:
        raise ValueError("total_empty_min must be <= total_empty_max")

    intervals = []
    start = lo
    current = shop_draw(seed, day, (lo,))
    for total in range(lo + 1, hi + 1):
        value = shop_draw(seed, day, (total,))
        if value != current:
            intervals.append((start, total - 1, current))
            start = total
            current = value
    intervals.append((start, hi, current))
    return tuple(intervals)
