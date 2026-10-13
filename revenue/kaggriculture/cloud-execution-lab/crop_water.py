# SPDX-License-Identifier: Apache-2.0
"""Public-state crop watering obligations for the canonical TITAN producer.

The policy mirrors Kaggriculture's public crop lifecycle at the engine pin used
by TITAN V2.5.  It does not schedule actors or mutate routes; it returns dated,
reason-coded obligations that the existing producer can use when deciding which
WATER actions may be delayed and which must stay ahead of competing work.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Optional, Sequence


class WaterPolicyError(ValueError):
    """Raised when a caller supplies malformed public crop state/spec data."""


@dataclass(frozen=True)
class WaterObligation:
    crop: str
    day: int
    due_today: bool
    latest_safe_day: Optional[int]
    survival_due: bool
    annual_yield_units: int
    ongoing_bonus_units: int
    marginal_units: int
    priority: tuple[int, int, int]
    reason: str

    def as_dict(self) -> dict:
        return {
            "crop": self.crop,
            "day": self.day,
            "due_today": self.due_today,
            "latest_safe_day": self.latest_safe_day,
            "survival_due": self.survival_due,
            "annual_yield_units": self.annual_yield_units,
            "ongoing_bonus_units": self.ongoing_bonus_units,
            "marginal_units": self.marginal_units,
            "priority": list(self.priority),
            "reason": self.reason,
        }


def _plain_int(value, name: str, *, minimum: Optional[int] = None) -> int:
    if type(value) is not int:
        raise WaterPolicyError(f"{name} must be an int")
    if minimum is not None and value < minimum:
        raise WaterPolicyError(f"{name} must be >= {minimum}")
    return value


def _crop_spec(crop: str, specs: Mapping[str, Mapping]) -> Mapping:
    if not isinstance(crop, str) or not crop:
        raise WaterPolicyError("crop must be a non-empty string")
    if not isinstance(specs, Mapping) or crop not in specs:
        raise WaterPolicyError(f"unknown crop: {crop!r}")
    spec = specs[crop]
    if not isinstance(spec, Mapping):
        raise WaterPolicyError(f"crop spec for {crop!r} must be a mapping")
    for key in ("first_yield_day", "max_yield_day", "interval", "max_yield"):
        _plain_int(spec.get(key), f"{crop}.{key}", minimum=0)
    if type(spec.get("ongoing")) is not bool:
        raise WaterPolicyError(f"{crop}.ongoing must be a bool")
    if spec["ongoing"] and spec["interval"] <= 0:
        raise WaterPolicyError(f"{crop}.interval must be positive for ongoing crops")
    return spec


def _plant_state(tile: Mapping, specs: Mapping[str, Mapping]) -> tuple[str, Mapping]:
    if not isinstance(tile, Mapping) or tile.get("kind") != "PLANT":
        raise WaterPolicyError("tile must be a PLANT mapping")
    crop = tile.get("crop")
    spec = _crop_spec(crop, specs)
    _plain_int(tile.get("planted_day"), "planted_day", minimum=0)
    _plain_int(tile.get("consecutive_unwatered"), "consecutive_unwatered", minimum=0)
    _plain_int(tile.get("yield_units"), "yield_units", minimum=0)
    if type(tile.get("watered_today")) is not bool:
        raise WaterPolicyError("watered_today must be a bool")
    fertilized_until = tile.get("fertilized_until_day", -1)
    _plain_int(fertilized_until, "fertilized_until_day")
    return crop, spec


def _ongoing_production_due(tile: Mapping, spec: Mapping, day: int) -> bool:
    """Whether tonight's refresh is a still-live scheduled production event."""
    if not spec["ongoing"]:
        return False
    next_day = day + 1
    days_since_first = next_day - tile["planted_day"] - spec["first_yield_day"]
    if days_since_first < 0:
        return False
    if days_since_first % spec["interval"] != 0:
        return False
    production_count = days_since_first // spec["interval"] + 1
    return production_count <= spec["max_yield"]


def water_obligation(tile: Mapping, specs: Mapping[str, Mapping], day: int) -> WaterObligation:
    """Classify today's WATER value using only public crop state.

    Engine facts reflected here:
      * an unwatered plant with consecutive_unwatered >= 1 dies at tonight's
        refresh if WATER is omitted;
      * annual crops gain yield immediately from WATER inside their bonus window;
      * ongoing crops produce at their refresh cadence without WATER, but a
        fertilized, watered production day gets one extra unit when storage has
        room for that marginal unit;
      * a second WATER on the same day is a no-op.

    The returned priority is lexicographic: survival first, then current marginal
    units, then the nearest survival deadline.  Larger tuples rank first.
    """
    day = _plain_int(day, "day", minimum=0)
    crop, spec = _plant_state(tile, specs)

    if tile["watered_today"]:
        return WaterObligation(
            crop=crop,
            day=day,
            due_today=False,
            latest_safe_day=None,
            survival_due=False,
            annual_yield_units=0,
            ongoing_bonus_units=0,
            marginal_units=0,
            priority=(0, 0, 0),
            reason="already_watered_today",
        )

    survival_due = tile["consecutive_unwatered"] >= 1
    current_yield = tile["yield_units"]
    room = max(0, spec["max_yield"] - current_yield)

    annual_units = 0
    if not spec["ongoing"] and room:
        age_days = day - tile["planted_day"]
        window_start = (spec["max_yield_day"] + 1) // 2
        if window_start <= age_days <= spec["max_yield_day"]:
            raw_bonus = 2 if tile.get("fertilized_until_day", -1) >= day else 1
            annual_units = min(room, raw_bonus)

    ongoing_bonus = 0
    if (
        spec["ongoing"]
        and room >= 2
        and tile.get("fertilized_until_day", -1) >= day
        and _ongoing_production_due(tile, spec, day)
    ):
        # Tonight's base +1 happens whether or not the crop was watered.  WATER
        # changes that refresh from +1 to +2, so its marginal value is exactly 1.
        ongoing_bonus = 1

    marginal = annual_units + ongoing_bonus
    due_today = survival_due or marginal > 0
    latest = day if due_today else day + 1
    reason_parts = []
    if survival_due:
        reason_parts.append("survival")
    if annual_units:
        reason_parts.append("annual_yield")
    if ongoing_bonus:
        reason_parts.append("fertilized_ongoing_bonus")
    if not reason_parts:
        reason_parts.append("deferrable_survival")

    # A crop that can safely skip today still has a hard survival deadline next
    # day unless it is harvested/removed first; route owners decide that later.
    urgency = 1 if survival_due else 0
    deadline_score = -latest if latest is not None else -10**9
    return WaterObligation(
        crop=crop,
        day=day,
        due_today=due_today,
        latest_safe_day=latest,
        survival_due=survival_due,
        annual_yield_units=annual_units,
        ongoing_bonus_units=ongoing_bonus,
        marginal_units=marginal,
        priority=(urgency, marginal, deadline_score),
        reason="+".join(reason_parts),
    )


def rank_water_obligations(
    tiles: Iterable[Mapping], specs: Mapping[str, Mapping], day: int
) -> list[WaterObligation]:
    """Return deterministic high-value-first obligations for resource contention."""
    obligations = [water_obligation(tile, specs, day) for tile in tiles]
    return sorted(
        obligations,
        key=lambda o: (o.priority, o.crop, o.reason),
        reverse=True,
    )


def can_defer_water(
    tile: Mapping,
    specs: Mapping[str, Mapping],
    day: int,
    *,
    next_water_day: Optional[int],
    removal_day: Optional[int] = None,
) -> tuple[bool, str]:
    """Bounded route-level deferral check for an incumbent WATER action.

    This never invents a future service.  A non-marginal WATER may move out of
    today only when the incumbent route already contains a WATER no later than
    the physical survival deadline, or the crop is removed before that deadline.
    """
    obligation = water_obligation(tile, specs, day)
    if obligation.reason == "already_watered_today":
        return True, "same_day_water_is_engine_noop"
    if obligation.due_today:
        return False, obligation.reason

    deadline = obligation.latest_safe_day
    if removal_day is not None:
        removal_day = _plain_int(removal_day, "removal_day", minimum=day)
        if removal_day <= deadline:
            return True, "removed_before_survival_deadline"
    if next_water_day is None:
        return False, "no_incumbent_future_water"
    next_water_day = _plain_int(next_water_day, "next_water_day", minimum=day)
    if next_water_day <= deadline:
        return True, "incumbent_water_meets_survival_deadline"
    return False, "future_water_after_survival_deadline"


def classify_tiles(
    farm_tiles: Sequence[Sequence], specs: Mapping[str, Mapping], day: int
) -> list[dict]:
    """Serialize all observed plants for logs/tests without mutating farm state."""
    if not isinstance(farm_tiles, Sequence):
        raise WaterPolicyError("farm_tiles must be a sequence")
    out = []
    for y, row in enumerate(farm_tiles):
        if not isinstance(row, Sequence):
            raise WaterPolicyError("each farm row must be a sequence")
        for x, tile in enumerate(row):
            if isinstance(tile, Mapping) and tile.get("kind") == "PLANT":
                item = water_obligation(tile, specs, day).as_dict()
                item["tile"] = [x, y]
                out.append(item)
    out.sort(key=lambda item: (item["tile"][1], item["tile"][0]))
    return out
