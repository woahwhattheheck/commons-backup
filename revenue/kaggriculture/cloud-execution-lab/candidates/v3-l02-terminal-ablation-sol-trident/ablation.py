# SPDX-License-Identifier: Apache-2.0
"""Fail-closed temporal/component ablations for the rejected TITAN L02 tranche."""
from __future__ import annotations

from typing import Any, Mapping

ARMS = (
    "once_all",
    "day28_all",
    "once_carrot",
    "once_wheat",
    "once_noncarrot",
)
DAY = 28
DEFAULT_TURNS_PER_DAY = 24
DEFAULT_EPISODE_STEPS = 720


def _positive_int(value: Any, default: int) -> int:
    if value is None:
        value = default
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("expected positive integer")
    return value


def arm_window(arm: str, step: int, configuration: Mapping[str, Any] | None = None) -> tuple[bool, int, int]:
    """Return the exact ablation window without weakening L02's episode bound."""
    if arm not in ARMS:
        raise ValueError(f"unknown arm: {arm}")
    if isinstance(step, bool) or not isinstance(step, int) or step < 0:
        raise ValueError("step must be a nonnegative integer")
    cfg = dict(configuration or {})
    turns = _positive_int(cfg.get("turnsPerDay"), DEFAULT_TURNS_PER_DAY)
    episode = _positive_int(cfg.get("episodeSteps"), DEFAULT_EPISODE_STEPS)
    last = episode - 2
    if arm == "day28_all":
        enabled = step // turns == DAY and step < last
    else:
        enabled = step == DAY * turns and step < last
    return enabled, turns, last


def _unchanged(reason: str):
    def apply(selected_action, *_args, **_kwargs):
        return selected_action, {"changed": False, "reason": reason}
    return apply


def configure_overlay(overlay: Any, arm: str) -> dict[str, Any]:
    """Configure one freshly loaded L02 module for a single isolated arm."""
    if arm not in ARMS:
        raise ValueError(f"unknown arm: {arm}")
    required = (
        "_late_window",
        "apply_product_tranche",
        "apply_wheat_before_feed_guard",
        "SELL_ALL_WHEN_ABSENT",
        "CARROT_FLOOR",
        "install",
    )
    missing = [name for name in required if not hasattr(overlay, name)]
    if missing:
        raise AttributeError("L02 overlay missing: " + ", ".join(missing))

    def late_window(step: int, configuration: Mapping[str, Any] | None):
        return arm_window(arm, step, configuration)

    overlay._late_window = late_window
    components = {"carrot": True, "noncarrot": True, "wheat": True}
    if arm == "once_carrot":
        overlay.SELL_ALL_WHEN_ABSENT = ()
        overlay.apply_wheat_before_feed_guard = _unchanged("ablation_wheat_disabled")
        components.update(noncarrot=False, wheat=False)
    elif arm == "once_wheat":
        overlay.apply_product_tranche = _unchanged("ablation_products_disabled")
        components.update(carrot=False, noncarrot=False)
    elif arm == "once_noncarrot":
        overlay.CARROT_FLOOR = 0
        overlay.apply_wheat_before_feed_guard = _unchanged("ablation_wheat_disabled")
        components.update(carrot=False, wheat=False)

    return {
        "arm": arm,
        "day": DAY,
        "mode": "whole_day" if arm == "day28_all" else "single_step",
        "components": components,
    }
