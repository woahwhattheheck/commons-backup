# SPDX-License-Identifier: Apache-2.0
"""Fail-closed repair for atomic PLANT poisoning by non-existent hand rows.

The official interpreter counts every raw ``hands`` PLANT request when deciding
whether same-crop demand exceeds private seed inventory, then later executes only
hands that have a live position.  A surplus raw hand row can therefore block all
otherwise-feasible live PLANTs.  This helper edits only the minimum number of
non-existent suffix PLANT rows required to restore admission.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, asdict
from typing import Any


@dataclass(frozen=True)
class GhostPlantReport:
    enabled: bool
    changed: bool
    certified: bool
    reason: str
    live_hands: int | None = None
    replaced_hand_indexes: tuple[int, ...] = ()
    repaired_crops: tuple[str, ...] = ()
    raw_demand: tuple[tuple[str, int], ...] = ()
    live_demand: tuple[tuple[str, int], ...] = ()
    seeds: tuple[tuple[str, int], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["replaced_hand_indexes"] = list(self.replaced_hand_indexes)
        out["repaired_crops"] = list(self.repaired_crops)
        out["raw_demand"] = dict(self.raw_demand)
        out["live_demand"] = dict(self.live_demand)
        out["seeds"] = dict(self.seeds)
        return out


def _plant_crop(row: Any) -> tuple[str | None, bool]:
    """Return (crop, malformed_plant). Non-PLANT rows are (None, False)."""
    if not isinstance(row, list) or not row or row[0] != "PLANT":
        return None, False
    if len(row) < 2 or not isinstance(row[1], str):
        return None, True
    return row[1], False


def _counts(rows: list[Any]) -> tuple[dict[str, int], bool]:
    counts: dict[str, int] = {}
    malformed = False
    for row in rows:
        crop, bad = _plant_crop(row)
        malformed = malformed or bad
        if crop is not None:
            counts[crop] = counts.get(crop, 0) + 1
    return counts, malformed


def repair_ghost_plant_poisoning(
    observation: Any,
    action: Any,
    *,
    enabled: bool = False,
) -> tuple[Any, dict[str, Any]]:
    """Repair only certified surplus-hand atomic-PLANT poisoning.

    Certification requires:
      * exact player/farm/private seed state is present;
      * ``action['hands']`` is a list;
      * all PLANT crop arguments are strings;
      * for a crop, live demand is positive and feasible, while raw demand is
        infeasible solely because suffix rows beyond ``len(farm['hands'])`` add
        demand: ``live_demand <= seeds < raw_demand``.

    For each certified crop, the function replaces the minimum number of latest
    ghost PLANT rows with ``['PASS']`` needed to make raw demand admissible.
    It never edits a live actor row, market order, farmer row, or a genuinely
    over-subscribed live crop.  Disabled and non-certified paths return the exact
    input action object.
    """
    if not enabled:
        return action, GhostPlantReport(False, False, False, "disabled").to_dict()
    if not isinstance(observation, dict) or not isinstance(action, dict):
        return action, GhostPlantReport(True, False, False, "invalid_top_level").to_dict()

    farms = observation.get("farms")
    private = observation.get("private")
    player = observation.get("player")
    hands_rows = action.get("hands", [])
    if not isinstance(farms, list) or not isinstance(player, int) or not (0 <= player < len(farms)):
        return action, GhostPlantReport(True, False, False, "invalid_player_farms").to_dict()
    farm = farms[player]
    if not isinstance(farm, dict) or not isinstance(farm.get("hands"), list):
        return action, GhostPlantReport(True, False, False, "invalid_live_hands").to_dict()
    if not isinstance(private, dict) or not isinstance(private.get("seeds"), dict):
        return action, GhostPlantReport(True, False, False, "invalid_private_seeds").to_dict()
    if not isinstance(hands_rows, list):
        return action, GhostPlantReport(True, False, False, "invalid_action_hands").to_dict()

    live_hands = len(farm["hands"])
    farmer_row = action.get("farmer", ["PASS"])
    raw_rows = [farmer_row, *hands_rows]
    live_rows = [farmer_row, *hands_rows[:live_hands]]
    raw_demand, raw_bad = _counts(raw_rows)
    live_demand, live_bad = _counts(live_rows)
    if raw_bad or live_bad:
        return action, GhostPlantReport(True, False, False, "malformed_plant_crop",
                                        live_hands=live_hands).to_dict()

    relevant = set(raw_demand) | set(live_demand)
    seeds: dict[str, int] = {}
    for crop in relevant:
        value = private["seeds"].get(crop, 0)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return action, GhostPlantReport(True, False, False, "invalid_seed_count",
                                            live_hands=live_hands).to_dict()
        seeds[crop] = value

    repair_counts: dict[str, int] = {}
    for crop, live_n in live_demand.items():
        raw_n = raw_demand.get(crop, 0)
        available = seeds.get(crop, 0)
        if 0 < live_n <= available < raw_n:
            # Because raw-live consists solely of suffix rows, this many latest
            # suffix rows are sufficient and no live row needs to move.
            repair_counts[crop] = raw_n - available

    if not repair_counts:
        return action, GhostPlantReport(
            True, False, True, "no_certified_poisoning", live_hands=live_hands,
            raw_demand=tuple(sorted(raw_demand.items())),
            live_demand=tuple(sorted(live_demand.items())),
            seeds=tuple(sorted(seeds.items())),
        ).to_dict()

    result = deepcopy(action)
    result_hands = result["hands"]
    replaced: list[int] = []
    remaining = dict(repair_counts)
    for idx in range(len(result_hands) - 1, live_hands - 1, -1):
        crop, bad = _plant_crop(result_hands[idx])
        if bad or crop is None or remaining.get(crop, 0) <= 0:
            continue
        result_hands[idx] = ["PASS"]
        remaining[crop] -= 1
        replaced.append(idx)
    if any(remaining.values()):
        # Defensive impossible case: never emit a partial repair.
        return action, GhostPlantReport(
            True, False, False, "suffix_proof_failed", live_hands=live_hands,
            raw_demand=tuple(sorted(raw_demand.items())),
            live_demand=tuple(sorted(live_demand.items())),
            seeds=tuple(sorted(seeds.items())),
        ).to_dict()

    repaired_raw, malformed = _counts([result.get("farmer", ["PASS"]), *result_hands])
    if malformed or any(repaired_raw.get(c, 0) > seeds.get(c, 0) for c in repair_counts):
        return action, GhostPlantReport(True, False, False, "postcondition_failed",
                                        live_hands=live_hands).to_dict()

    return result, GhostPlantReport(
        True, True, True, "ghost_suffix_unblocked_live_plants",
        live_hands=live_hands,
        replaced_hand_indexes=tuple(sorted(replaced)),
        repaired_crops=tuple(sorted(repair_counts)),
        raw_demand=tuple(sorted(raw_demand.items())),
        live_demand=tuple(sorted(live_demand.items())),
        seeds=tuple(sorted(seeds.items())),
    ).to_dict()
