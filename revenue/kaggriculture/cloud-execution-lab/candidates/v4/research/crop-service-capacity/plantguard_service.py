"""PLANTGUARD descendant: prove PLANT -> same-EOD WATER service custody.

Research only. CROPSCALE already proves a one-sided action-count ceiling. This
module adds the missing per-site service-sequence witness for Gemini/Antigravity
PLANTGUARD without turning a clock cutoff into policy.

A positive result means only that caller-supplied normalized projected unit rows
contain a PLANT followed by WATER on every proposed site before a reachable
current EOD, and that the proposal does not exceed CROPSCALE's selected
action-count ceiling. It does not prove movement, seed inventory, cash, tile
legality, crop choice, future service, market execution, profitability, or
runtime reachability.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

import crop_service_capacity as C

SCHEMA = "titan-v4-plantguard-service-proof/v1"
DEFAULT_TURNS_PER_DAY = 24
DEFAULT_EPISODE_STEPS = 720
SAFE_SAME_SITE_SERVICE_OPS = frozenset({"FERTILIZE", "WATER"})


class PlantguardEvidenceError(ValueError):
    """Raised when projected service evidence is malformed or ambiguous."""


def _int(value: Any, label: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise PlantguardEvidenceError(f"{label}_must_be_int_ge_{minimum}")
    return value


def _config_int(
    configuration: Mapping[str, Any] | None,
    key: str,
    default: int,
    *,
    minimum: int = 1,
) -> int:
    if configuration is None:
        return default
    if not isinstance(configuration, Mapping):
        raise PlantguardEvidenceError("configuration_must_be_mapping")
    return _int(configuration.get(key, default), key, minimum=minimum)


def _site(value: Any, label: str = "site") -> tuple[int, int]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise PlantguardEvidenceError(f"{label}_must_be_xy")
    return (_int(value[0], f"{label}_row"), _int(value[1], f"{label}_col"))


def _op(row: Mapping[str, Any]) -> str:
    value = row.get("op")
    if not isinstance(value, str) or not value:
        raise PlantguardEvidenceError("projected_op_must_be_nonempty_string")
    return value.upper()


def _board_shape(observation: Mapping[str, Any]) -> tuple[int, int, int]:
    player, farm, _ = C._farm_from_observation(observation)
    tiles = farm["tiles"]
    return player, len(tiles), len(tiles[0])


def _proposed_sites(
    observation: Mapping[str, Any], values: Any
) -> tuple[tuple[int, int], ...]:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        raise PlantguardEvidenceError("proposed_sites_must_be_sequence")
    _, height, width = _board_shape(observation)
    out: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()
    for index, raw in enumerate(values):
        site = _site(raw, f"proposed_site_{index}")
        if site[0] >= height or site[1] >= width:
            raise PlantguardEvidenceError("proposed_site_outside_observed_board")
        if site in seen:
            raise PlantguardEvidenceError("duplicate_proposed_site")
        seen.add(site)
        out.append(site)
    return tuple(out)


def _projected_rows(
    observation: Mapping[str, Any], rows: Any, turns_per_day: int
) -> list[dict[str, Any]]:
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        raise PlantguardEvidenceError("projected_rows_must_be_sequence")
    current_hour = _int(observation.get("hour"), "observation_hour")
    normalized: list[dict[str, Any]] = []
    last_key: tuple[int, int] | None = None
    for index, raw in enumerate(rows):
        if not isinstance(raw, Mapping):
            raise PlantguardEvidenceError("projected_row_must_be_mapping")
        hour = _int(raw.get("hour"), f"row_{index}_hour")
        order = _int(raw.get("order"), f"row_{index}_order")
        if hour < current_hour or hour >= turns_per_day:
            raise PlantguardEvidenceError("projected_row_hour_outside_current_day_suffix")
        key = (hour, order)
        if last_key is not None and key <= last_key:
            raise PlantguardEvidenceError("projected_rows_must_be_strict_execution_order")
        last_key = key
        site_raw = raw.get("site")
        normalized.append(
            {
                "hour": hour,
                "order": order,
                "op": _op(raw),
                "site": None if site_raw is None else _site(site_raw, f"row_{index}_site"),
            }
        )
    return normalized


def _terminal_unproved(site_count: int, reason: str) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "verdict": "SERVICE_SEQUENCE_UNPROVED",
        "proposed_site_count": site_count,
        "proved_pair_count": 0,
        "pairs": [],
        "failures": [{"reason": reason}],
        "research_only": True,
        "decision_authority": False,
        "runtime_mutation_authority": False,
    }


def prove_same_eod_establishment(
    observation: Mapping[str, Any],
    proposed_sites: Sequence[Sequence[int]],
    projected_rows: Sequence[Mapping[str, Any]],
    configuration: Mapping[str, Any] | None = None,
    *,
    no_future_hires: bool = False,
) -> dict[str, Any]:
    """Prove only the PLANT/WATER service sequence for proposed new sites.

    Rows use the normalized research ABI ``{hour, order, op, site?}``, where
    ``order`` is the caller's total execution order inside a callback. This
    permits a later actor in the same callback to WATER a site planted earlier
    in that callback without pretending all same-hour actions are simultaneous.

    A positive witness also requires the projected same-site service history to
    remain unambiguous through the rest of the current-day projection. WATER is
    not an early-return authorization: a later same-site DIG/HARVEST/PLANT/BUILD
    (or any unmodelled same-site op) fails closed rather than certifying a plant
    that may no longer exist at EOD.

    The current EOD itself must be reachable inside the official episode
    horizon. The interpreter's final executable callback is ``episodeSteps-2``;
    nominal clock rows after that boundary cannot provide phantom WATER labor.
    """
    if not isinstance(no_future_hires, bool):
        raise PlantguardEvidenceError("no_future_hires_must_be_bool")
    sites = _proposed_sites(observation, proposed_sites)
    if not sites:
        return {
            "schema": SCHEMA,
            "verdict": "NO_PROPOSAL",
            "proposed_site_count": 0,
            "pairs": [],
            "research_only": True,
            "decision_authority": False,
            "runtime_mutation_authority": False,
        }

    turns_per_day = _config_int(
        configuration, "turnsPerDay", DEFAULT_TURNS_PER_DAY
    )
    episode_steps = _config_int(
        configuration, "episodeSteps", DEFAULT_EPISODE_STEPS, minimum=2
    )
    hour = _int(observation.get("hour"), "observation_hour")
    step = _int(observation.get("step"), "observation_step")
    if hour >= turns_per_day:
        raise PlantguardEvidenceError("observation_hour_out_of_day")
    if hour != step % turns_per_day:
        raise PlantguardEvidenceError("observation_hour_step_mismatch")
    final_executable_step = episode_steps - 2
    if step > final_executable_step:
        raise PlantguardEvidenceError("observation_step_after_final_executable_callback")
    eod_step = step + (turns_per_day - hour - 1)
    if eod_step > final_executable_step:
        return _terminal_unproved(len(sites), "eod_not_reachable_before_terminal")

    capacity = C.assess_proposed_expansion(
        observation,
        len(sites),
        configuration,
        no_future_hires=no_future_hires,
    )
    if capacity["verdict"] == "IMPOSSIBLE_ACTION_BUDGET":
        return {
            "schema": SCHEMA,
            "verdict": "IMPOSSIBLE_ACTION_BUDGET",
            "proposed_site_count": len(sites),
            "pairs": [],
            "capacity": capacity,
            "research_only": True,
            "decision_authority": False,
            "runtime_mutation_authority": False,
        }

    rows = _projected_rows(observation, projected_rows, turns_per_day)
    pairs: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    for site in sites:
        plant: dict[str, Any] | None = None
        invalidator: dict[str, Any] | None = None
        water: dict[str, Any] | None = None
        for row in rows:
            if row["site"] != site:
                continue
            if plant is None:
                if row["op"] == "PLANT":
                    plant = row
                continue
            if row["op"] == "WATER":
                if water is None:
                    water = row
                continue
            if row["op"] in SAFE_SAME_SITE_SERVICE_OPS:
                continue
            invalidator = row
            break

        if plant is None:
            failures.append({"site": list(site), "reason": "missing_plant"})
            continue
        if invalidator is not None:
            failures.append(
                {
                    "site": list(site),
                    "reason": (
                        "site_action_between_plant_and_water"
                        if water is None
                        else "site_action_after_water_before_eod"
                    ),
                    "op": invalidator["op"],
                    "hour": invalidator["hour"],
                    "order": invalidator["order"],
                }
            )
            continue
        if water is None:
            failures.append({"site": list(site), "reason": "missing_same_eod_water"})
            continue
        pairs.append(
            {
                "site": list(site),
                "plant_hour": plant["hour"],
                "plant_order": plant["order"],
                "water_hour": water["hour"],
                "water_order": water["order"],
            }
        )

    proved = not failures and len(pairs) == len(sites)
    return {
        "schema": SCHEMA,
        "verdict": "ESTABLISHMENT_SERVICE_PROVED" if proved else "SERVICE_SEQUENCE_UNPROVED",
        "proposed_site_count": len(sites),
        "proved_pair_count": len(pairs),
        "pairs": pairs,
        "failures": failures,
        "capacity": capacity,
        "research_only": True,
        "decision_authority": False,
        "runtime_mutation_authority": False,
        "movement_certified": False,
        "seed_certified": False,
        "cash_certified": False,
        "tile_legality_certified": False,
        "future_service_certified": False,
        "economics_certified": False,
        "limitations": [
            "service proof is not a route or movement proof",
            "service proof does not prove BUY_SEED, cash, crop choice, or tile legality",
            "service proof ends at a reachable current EOD and does not guarantee later WATER/HARVEST",
            "runtime admission requires a separately authenticated scheduler/LOOM consumer",
        ],
    }
