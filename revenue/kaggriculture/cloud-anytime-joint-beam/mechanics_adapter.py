# SPDX-License-Identifier: Apache-2.0
"""Interpreter-faithful worker-prefix adapter and bounded economics scorer.

This module depends only on the preserved ``mechanics.py`` primitives. It does
not own the canonical controller and never touches market order emission.
"""
from __future__ import annotations

from dataclasses import dataclass
import copy
import json
from typing import Any, Callable, Hashable, Iterable, Mapping

from joint_action_beam import Action, State

# The generic short-horizon scorer cannot infer the canonical controller's
# downstream route/production intent. The core beam remains fully general, but
# this default mechanics provider is therefore PASS-fill only: existing selected
# work is immutable unless a caller supplies an explicit downstream-aware model.

# Prefix metadata is internal to one beam search. It is ignored by the scorer and
# never appears in the emitted Kaggriculture action object. The tuple fields are:
# origin farm/private immediately before the first tentative PLANT, that worker
# index, replay suffix, aggregate PLANT demand, and blocked crops.
_TRANSITION_META_KEY = "__s01_mechanics_transition__"
_ROLLBACK_SENSITIVE_NOOPS = ("BUILD_COOP", "BUILD_PASTURE")


@dataclass(frozen=True)
class MechanicsContext:
    board_size: int
    day: int
    turns_per_day: int = 24
    shed_capacity: int = 100


@dataclass(frozen=True)
class ScoreWeights:
    cash: int = 100
    liquid_value: int = 10
    production: int = 12
    survival: int = 80
    travel: int = 8
    obligations: int = 120


@dataclass(frozen=True)
class ScoreContext:
    """Small immutable scoring contract; mappings are represented as tuples."""
    targets: tuple[tuple[int, int] | None, ...] = ()
    required_goods: tuple[tuple[str, int], ...] = ()
    min_cash: int = 0
    weights: ScoreWeights = ScoreWeights()


def _plant_crop(action: Action) -> str | None:
    if isinstance(action, list) and len(action) >= 2 and action[0] == "PLANT":
        return action[1]
    return None


def _clone_worker_state(farm: Any, private: Any) -> tuple[Any, Any]:
    """Clone the mutable worker-phase state without recursive deepcopy cost.

    The pinned ``_apply_unit_action`` primitive can mutate only farmer/hand
    positions, one flat tile record, seeds, shed contents, and flat worker
    inventories. Cloning those complete structures preserves sibling-state
    isolation while avoiding a recursive walk through every scalar board cell.
    """
    next_farm = dict(farm)
    farmer = farm.get("farmer")
    if isinstance(farmer, list):
        next_farm["farmer"] = list(farmer)
    hands = farm.get("hands")
    if isinstance(hands, list):
        next_farm["hands"] = [
            list(pos) if isinstance(pos, list) else pos for pos in hands
        ]
    tiles = farm.get("tiles")
    if isinstance(tiles, list):
        next_farm["tiles"] = [
            [dict(tile) if isinstance(tile, dict) else tile for tile in row]
            if isinstance(row, list) else row
            for row in tiles
        ]

    next_private = dict(private)
    for key in ("shed", "seeds"):
        value = private.get(key)
        if isinstance(value, dict):
            next_private[key] = dict(value)
    inventories = private.get("inventories")
    if isinstance(inventories, list):
        next_private["inventories"] = [
            dict(inv) if isinstance(inv, dict) else inv for inv in inventories
        ]
    return next_farm, next_private


def _replay_worker_prefix(
    mechanics: Any,
    context: MechanicsContext,
    origin_farm: Any,
    origin_private: Any,
    start_idx: int,
    actions: tuple[Action, ...],
    blocked_plants: frozenset[str],
) -> tuple[Any, Any]:
    """Replay one tentative worker suffix with interpreter-level PLANT gating."""
    farm, private = _clone_worker_state(origin_farm, origin_private)
    for offset, action in enumerate(actions):
        crop = _plant_crop(action)
        effective = ["PASS"] if crop in blocked_plants else action
        mechanics._apply_unit_action(
            farm,
            private,
            start_idx + offset,
            effective,
            context.board_size,
            context.day,
            context.turns_per_day,
            context.shed_capacity,
        )
    return farm, private


def mechanics_transition(mechanics: Any, context: MechanicsContext) -> Callable[[State, int, Action], State | None]:
    """Return an interpreter-faithful incremental worker-prefix transition.

    Kaggriculture validates PLANT requests atomically across the whole worker
    tuple before applying any unit action: if requests for one crop exceed the
    pre-turn seed count, every PLANT for that crop becomes PASS. That rule is not
    prefix-monotone, so merely calling ``_apply_unit_action`` sequentially is not
    exact. This adapter records a tentative suffix beginning at the first PLANT
    and replays it whenever a crop first becomes oversubscribed. Replay also
    restores downstream actions whose legality changes when an earlier tentative
    PLANT is rolled back.

    Actions before the first PLANT are applied normally and become the immutable
    replay origin because the atomic prepass cannot alter non-PLANT work. This
    keeps the common no-PLANT path as cheap as the preserved primitive adapter.

    The official interpreter treats invalid worker actions as silent no-ops.
    Most ineffective non-PLANT candidates are still returned as ``None`` for
    bounded-search pruning. Only empty-tile BUILD actions can become effective
    when a tentative plant is later removed under the pinned mechanics; those
    no-ops remain in the suffix while any unblocked PLANT request exists.
    Syntactic PLANT requests are always retained because even an otherwise
    ineffective request contributes to atomic demand.
    """
    def transition(state: State, idx: int, action: Action) -> State | None:
        # idx==0 starts a fresh worker tuple, which also permits callers to reuse
        # a prior successor as the initial state of a later turn. A pruned idx==0
        # call drops any surviving prefix metadata from the input state: the
        # metadata can only describe a previous turn, and the prune yields no
        # successor to overwrite it, so leaving it would make a later idx>0
        # call on the same state raise on the stale prefix.
        metadata = None if idx == 0 else state.get(_TRANSITION_META_KEY)
        crop = _plant_crop(action)
        op = action[0] if isinstance(action, list) and action else None

        # Until the first PLANT request, official atomic validation cannot alter
        # any predecessor. Preserve the original fast sequential transition and
        # do not allocate replay metadata on this common path.
        if metadata is None and crop is None:
            farm, private = _clone_worker_state(state["farm"], state["private"])
            mechanics._apply_unit_action(
                farm,
                private,
                idx,
                action,
                context.board_size,
                context.day,
                context.turns_per_day,
                context.shed_capacity,
            )
            changed = farm != state["farm"] or private != state["private"]
            if not changed and op != "PASS":
                if idx == 0:
                    # A fresh worker tuple starts here, so any prefix metadata
                    # still present must be stale: the caller reused a successor
                    # from a previous turn (documented multi-turn use). This
                    # pruned call produces no successor to overwrite it, so
                    # drop the stale key from the input state now; otherwise a
                    # later idx>0 call on the same state (the beam continues
                    # canonical prunes on the unchanged state) would read the
                    # stale prefix and raise. The key is internal to one beam
                    # search and ignored by the scorer.
                    state.pop(_TRANSITION_META_KEY, None)
                return None
            out = dict(state)
            out["farm"] = farm
            out["private"] = private
            out.pop(_TRANSITION_META_KEY, None)
            return out

        if metadata is None:
            origin_farm = state["farm"]
            origin_private = state["private"]
            start_idx = idx
            prior_actions: tuple[Action, ...] = ()
            prior_demand: Mapping[str, int] = {}
            prior_blocked: frozenset[str] = frozenset()
        else:
            (
                origin_farm,
                origin_private,
                start_idx,
                prior_actions,
                prior_demand,
                prior_blocked,
            ) = metadata
            expected_idx = start_idx + len(prior_actions)
            if idx < expected_idx:
                raise ValueError("mechanics transition requires increasing worker indices")
            if idx > expected_idx:
                # Missing entries can only be pruned state-equivalent no-ops.
                # PASS is replay-equivalent because rollback cannot activate any
                # no-op except BUILD, and rollback-sensitive BUILD is retained.
                prior_actions += tuple(["PASS"] for _ in range(idx - expected_idx))

        next_action = copy.deepcopy(action)
        actions = prior_actions + (next_action,)
        newly_blocked = False
        if crop is None:
            demand = prior_demand
            blocked_plants = prior_blocked
        else:
            demand = dict(prior_demand)
            demand[crop] = demand.get(crop, 0) + 1
            available = int(origin_private.get("seeds", {}).get(crop, 0))
            if demand[crop] > available and crop not in prior_blocked:
                blocked_plants = prior_blocked | {crop}
                newly_blocked = True
            else:
                blocked_plants = prior_blocked

        if newly_blocked:
            farm, private = _replay_worker_prefix(
                mechanics,
                context,
                origin_farm,
                origin_private,
                start_idx,
                actions,
                blocked_plants,
            )
        else:
            farm, private = _clone_worker_state(state["farm"], state["private"])
            effective = ["PASS"] if crop in blocked_plants else next_action
            mechanics._apply_unit_action(
                farm,
                private,
                idx,
                effective,
                context.board_size,
                context.day,
                context.turns_per_day,
                context.shed_capacity,
            )

        changed = farm != state["farm"] or private != state["private"]
        active_tentative_plant = any(
            crop_name not in blocked_plants for crop_name in demand
        )
        rollback_sensitive_noop = (
            active_tentative_plant and op in _ROLLBACK_SENSITIVE_NOOPS
        )
        if (
            not changed
            and op not in ("PASS", "PLANT")
            and not rollback_sensitive_noop
        ):
            if idx == 0:
                # Same stale-metadata drop as the fast path above: idx==0
                # starts a fresh worker tuple, so surviving prefix metadata is
                # from a previous turn and this pruned call yields no successor
                # to overwrite it.
                state.pop(_TRANSITION_META_KEY, None)
            return None

        out = dict(state)
        out["farm"] = farm
        out["private"] = private
        out[_TRANSITION_META_KEY] = (
            origin_farm,
            origin_private,
            start_idx,
            actions,
            demand,
            blocked_plants,
        )
        return out
    return transition


def _inventory(private: Mapping[str, Any], idx: int) -> Mapping[str, int]:
    inventories = private.get("inventories", [])
    if isinstance(inventories, list) and idx < len(inventories) and isinstance(inventories[idx], dict):
        return inventories[idx]
    return {}


def bounded_worker_candidates(mechanics: Any, state: State, idx: int, canonical: Action) -> Iterable[Action]:
    """Deterministically enumerate a bounded, locally realizable worker family.

    The beam core inserts canonical first and caps the family. Exact mechanics
    transition remains the authority for legality and shared-resource conflicts.

    Existing non-PASS selected actions are canonical-only. In official-game
    diagnosis, changing route moves, HARVEST, and destination-specific PICKUPs
    under this coarse one-stage score caused large downstream regressions. The
    safe default only searches a worker the canonical controller left idle.
    Callers with an explicit downstream-aware route/obligation model may provide
    their own candidate provider to search non-PASS actions through the same core.
    """
    if isinstance(canonical, list) and canonical and canonical[0] != "PASS":
        return ()
    farm = state["farm"]
    private = state["private"]
    pos = mechanics._farmer_position(farm, idx)
    if pos is None:
        return (["PASS"],)

    fx, fy = int(pos[0]), int(pos[1])
    board_size = len(farm.get("tiles", []))
    inv = _inventory(private, idx)
    offered: list[Action] = [["PASS"]]

    # Movement is cheap to enumerate. Exact mechanics prunes edges.
    offered.extend([[name] for name in ("NORTH", "SOUTH", "EAST", "WEST")])

    if mechanics._is_shed_adjacent((fx, fy), board_size):
        if any(int(n) > 0 for n in inv.values()):
            offered.append(["DROP"])
        for item, n in sorted(private.get("shed", {}).items()):
            n = int(n)
            if n > 0:
                offered.append(["PICKUP", item, 1])
                if n > 1:
                    offered.append(["PICKUP", item, n])
        for item, n in sorted(inv.items()):
            n = int(n)
            if n > 0:
                offered.append(["PLACE", item, 1])
                if n > 1:
                    offered.append(["PLACE", item, n])

    tiles = farm.get("tiles", [])
    if not (0 <= fy < len(tiles) and 0 <= fx < len(tiles[fy])):
        return tuple(offered)
    tile = tiles[fy][fx]
    if tile == "LOCKED":
        return tuple(offered)

    if tile is None:
        for crop in sorted(mechanics.CROPS):
            if int(private.get("seeds", {}).get(crop, 0)) > 0:
                offered.append(["PLANT", crop])
        offered.extend((["BUILD_COOP"], ["BUILD_PASTURE"]))
        return tuple(offered)

    if isinstance(tile, dict) and tile.get("kind") == "PLANT":
        offered.extend((["WATER"], ["HARVEST"], ["DIG"]))
        if int(inv.get("FERTILIZER", 0)) > 0:
            offered.append(["FERTILIZE"])
        return tuple(offered)

    if isinstance(tile, dict) and "animal" in tile:
        offered.extend((["HARVEST"], ["CARE"], ["COLLECT_FERTILIZER"]))
        if int(inv.get("WHEAT", 0)) > 0:
            offered.append(["FEED"])
        return tuple(offered)

    if isinstance(tile, dict) and tile.get("kind") in {"COOP", "PASTURE"}:
        structure = tile["kind"]
        for animal, spec in sorted(mechanics.ANIMALS.items()):
            if spec["structure"] == structure and int(inv.get(animal, 0)) > 0:
                offered.append(["PLACE", animal])
        offered.append(["DIG"])
        return tuple(offered)

    offered.append(["DIG"])
    return tuple(offered)


def _unit_positions(farm: Mapping[str, Any]) -> list[tuple[int, int]]:
    positions = [farm.get("farmer")]
    hands = farm.get("hands", [])
    if isinstance(hands, list):
        positions.extend(hands)
    out = []
    for pos in positions:
        if isinstance(pos, (list, tuple)) and len(pos) >= 2:
            out.append((int(pos[0]), int(pos[1])))
        else:
            out.append((0, 0))
    return out


def score_components(mechanics: Any, state: State, context: ScoreContext = ScoreContext()) -> dict[str, int]:
    """Score only observable deterministic worker-state economics."""
    farm = state["farm"]
    private = state["private"]
    market = state.get("market") or {}
    market_inventory = market.get("inventory", {}) if isinstance(market, dict) else {}

    def price(item: str) -> int:
        if item not in mechanics.MARKET_PARAMS:
            return 0
        inventory = int(market_inventory.get(item, mechanics.MARKET_PARAMS[item]["I0"]))
        return int(mechanics.market_price(item, inventory))

    cash = int(farm.get("money", 0))
    holdings: dict[str, int] = {}
    for item, n in private.get("shed", {}).items():
        holdings[item] = holdings.get(item, 0) + max(0, int(n))
    for inv in private.get("inventories", []):
        if not isinstance(inv, dict):
            continue
        for item, n in inv.items():
            holdings[item] = holdings.get(item, 0) + max(0, int(n))
    liquid_value = sum(n * price(item) for item, n in holdings.items())

    production = 0
    survival = 0
    for row in farm.get("tiles", []):
        for tile in row:
            if not isinstance(tile, dict):
                continue
            if tile.get("kind") == "PLANT":
                product = tile.get("crop")
                production += max(0, int(tile.get("yield_units", 0))) * price(product)
                survival += 2 if tile.get("watered_today") else -max(1, int(tile.get("consecutive_unwatered", 0)))
            elif "animal" in tile:
                product = mechanics.ANIMALS.get(tile.get("animal"), {}).get("product")
                if product:
                    production += max(0, int(tile.get("yield_units", 0))) * price(product)
                survival += 2 if tile.get("fed_today") else -max(1, int(tile.get("consecutive_unfed", 0)))
                if tile.get("cared_today"):
                    survival += 1

    travel = 0
    positions = _unit_positions(farm)
    for idx, target in enumerate(context.targets):
        if target is None or idx >= len(positions):
            continue
        travel -= abs(positions[idx][0] - int(target[0])) + abs(positions[idx][1] - int(target[1]))

    obligation = -max(0, int(context.min_cash) - cash)
    for item, need in context.required_goods:
        shortage = max(0, int(need) - holdings.get(item, 0))
        obligation -= shortage * max(1, price(item))

    return {
        "cash": cash,
        "liquid_value": liquid_value,
        "production": production,
        "survival": survival,
        "travel": travel,
        "obligations": obligation,
    }


def mechanics_scorer(mechanics: Any, context: ScoreContext = ScoreContext()) -> Callable[[State, tuple[Action, ...]], int]:
    """Create an integer scorer with explicit stable component weights."""
    w = context.weights
    def score(state: State, actions: tuple[Action, ...]) -> int:
        c = score_components(mechanics, state, context)
        return (
            w.cash * c["cash"]
            + w.liquid_value * c["liquid_value"]
            + w.production * c["production"]
            + w.survival * c["survival"]
            + w.travel * c["travel"]
            + w.obligations * c["obligations"]
        )
    return score


def _canonical_transition_metadata(metadata: tuple) -> list:
    """Render replay metadata deterministically for state keys.

    The metadata tuple carries a frozenset of blocked crops and a demand
    mapping; both need canonical ordering so equal game situations hash equal
    regardless of insertion order.
    """
    origin_farm, origin_private, start_idx, actions, demand, blocked = metadata
    return [
        origin_farm,
        origin_private,
        start_idx,
        list(actions),
        sorted((str(crop), int(n)) for crop, n in dict(demand).items()),
        sorted(str(crop) for crop in blocked),
    ]


def _stable_state_key(state: State) -> str:
    """Stable hashable identity of a successor state.

    Provider-internal replay metadata (``_TRANSITION_META_KEY``) is included:
    two states with equal keys behave identically under future transitions of
    this provider. Unserializable leaves fall back to ``repr``.
    """
    if isinstance(state, dict):
        metadata = state.get(_TRANSITION_META_KEY)
        game = {key: value for key, value in state.items() if key != _TRANSITION_META_KEY}
        payload = [
            game,
            _canonical_transition_metadata(metadata) if metadata is not None else None,
        ]
    else:
        payload = state
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=repr)


class KaggricultureRules:
    """MechanicsProvider: the Kaggriculture worker-phase rules behind the interface.

    This is the same interpreter-faithful transition and bounded candidate
    family as the module-level functions; the class only adapts them to the
    game-agnostic protocol in ``game_rules`` so the beam core and any future
    title can share one search path.
    """

    def __init__(self, mechanics: Any, context: MechanicsContext):
        self._mechanics = mechanics
        self._context = context
        self._transition = mechanics_transition(mechanics, context)

    @property
    def mechanics(self) -> Any:
        return self._mechanics

    @property
    def context(self) -> MechanicsContext:
        return self._context

    def legal_actions(
        self, state: State, idx: int, canonical: Action
    ) -> Iterable[Action]:
        return bounded_worker_candidates(self._mechanics, state, idx, canonical)

    def transition(
        self, state: State, idx: int, action: Action
    ) -> State | None:
        return self._transition(state, idx, action)

    def state_key(self, state: State) -> Hashable:
        return _stable_state_key(state)


class KaggricultureScorer:
    """Scorer: bounded worker-state economics behind the evaluator interface."""

    def __init__(self, mechanics: Any, context: ScoreContext = ScoreContext()):
        self._score = mechanics_scorer(mechanics, context)

    def __call__(self, state: State, actions: tuple[Action, ...]) -> int:
        return self._score(state, actions)
