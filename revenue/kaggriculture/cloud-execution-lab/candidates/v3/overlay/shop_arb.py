# SPDX-License-Identifier: Apache-2.0
"""O02 shop-demand signal, kept separate from exact engine absorption.

Lineage: TESSERA (Gemini) O02 -> G01 (Grok Build #2, PR #11371) -> ARGUS
semantic-safety repair (candidates/v3-g01-argus-safe, finding A7) -> V3.

ARGUS finding A7: multiplying the schedulers' exact integer absorption by 1.5
creates fractional market inventory the official engine can never produce.  V3
therefore ships this as a tested scoring-only callable with no production seam
and no package key.  A future scoring owner composes it; absorption() is never
patched.  No environment reads.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence


def priority_multiplier(
    item: str,
    shops: Sequence[str],
    mechanics_shops: Mapping[str, Sequence[str]],
    multiplier: float = 1.5,
    *,
    enabled: bool = False,
) -> float:
    """Return a scoring hint only; never feed this into engine inventory math."""
    if not enabled:
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
