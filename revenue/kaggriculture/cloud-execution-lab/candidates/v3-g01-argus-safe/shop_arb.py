# SPDX-License-Identifier: Apache-2.0
"""Shop-demand signal kept separate from exact engine absorption."""
from __future__ import annotations

import os
from typing import Any, Mapping, Sequence


def enabled() -> bool:
    return os.environ.get("TITAN_SHOP_ARB", "0") in ("1", "true", "True")


def priority_multiplier(
    item: str,
    shops: Sequence[str],
    mechanics_shops: Mapping[str, Sequence[str]],
    multiplier: float = 1.5,
) -> float:
    """Return a scoring hint only; never feed this into engine inventory math."""
    if not enabled():
        return 1.0
    for shop in shops or []:
        if item in mechanics_shops.get(shop, ()):
            return max(1.0, float(multiplier))
    return 1.0


def preserve_exact_absorption(observed_absorption: int) -> int:
    """Explicit quarantine boundary for the old n *= 1.5 transition patch."""
    if isinstance(observed_absorption, bool) or not isinstance(observed_absorption, int):
        raise TypeError("official absorption must be an integer count")
    if observed_absorption < 0:
        raise ValueError("official absorption cannot be negative")
    return observed_absorption
