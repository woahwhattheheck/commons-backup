"""Dated town demand from public state and explicitly supplied future draws.

No prices, route ranking, stochastic forecasting, seed access, or agent calls.
Consumption rows occur AFTER the market at their step. Shop arrivals occur
AFTER that step's consumption, so they cannot affect the arrival turn's trades.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from itertools import islice, product
from typing import Any, Iterable, Mapping, Sequence


def _get(obj: Any, name: str, default: Any = None) -> Any:
    return obj.get(name, default) if isinstance(obj, Mapping) else getattr(obj, name, default)


def _positive_config(config: Any, name: str, default: int) -> int:
    return max(1, int(_get(config, name, default)))


@dataclass(frozen=True)
class DemandRules:
    shops: tuple[tuple[str, tuple[str, ...]], ...]
    products: tuple[str, ...]
    center_products: tuple[str, ...]
    max_instances: int

    @classmethod
    def from_engine(cls, mechanics: Any) -> DemandRules:
        """Read constants from the caller's already-pinned official mechanics."""
        return cls(
            tuple((name, tuple(items)) for name, items in sorted(mechanics.SHOPS.items())),
            tuple(mechanics.PRODUCTS), tuple(mechanics.TOWN_CENTER_PRODUCTS),
            int(mechanics.MAX_SHOP_INSTANCES),
        )

    def signature(self, shop: str, products: Sequence[str]) -> tuple[int, ...]:
        try:
            items = dict(self.shops)[shop]
        except KeyError as exc:
            raise ValueError(f"Unknown shop: {shop}") from exc
        factor = 2 if len(items) == 1 else 1
        return tuple(factor if item in items else 0 for item in products)


@dataclass(frozen=True)
class DemandRow:
    step: int
    inventory_delta: tuple[int, ...]
    phase: str = "after_market"


@dataclass(frozen=True)
class DemandSchedule:
    start_step: int
    end_step: int
    products: tuple[str, ...]
    observed_shops: tuple[str, ...]
    unlock_after_steps: tuple[int, ...]
    future_shops: tuple[str, ...]
    coverage: str
    rows: tuple[DemandRow, ...]

    def before_market(self, step: int) -> dict[str, int]:
        """Cumulative town-only delta BEFORE market at step, never same-turn demand.

        The observation is the initial pre-action state. Query through end+1 is
        supported; queries outside the represented time window are explicit errors.
        """
        if not self.start_step <= step <= self.end_step + 1:
            raise ValueError("Requested step lies outside the represented window")
        totals = [0] * len(self.products)
        for row in self.rows:
            if row.step >= step:
                break
            for i, value in enumerate(row.inventory_delta):
                totals[i] += value
        return dict(zip(self.products, totals))

    def as_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["rows"] = [
            {"step": row.step, "phase": row.phase,
             "inventory_delta": dict(zip(self.products, row.inventory_delta))}
            for row in self.rows
        ]
        out["is_probability_forecast"] = False
        out["unknown_future_draws"] = self.coverage != "specified_future_scenario"
        return out


def _window(observation: Any, config: Any, rules: DemandRules,
            end_step: int | None) -> tuple[int, int, tuple[str, ...], tuple[int, ...]]:
    raw_step = _get(observation, "step")
    if not isinstance(raw_step, int) or isinstance(raw_step, bool) or raw_step < 0:
        raise ValueError("A delivered nonnegative integer observation.step is required")
    terminal = int(_get(config, "episodeSteps", 720)) - 2
    end = terminal if end_step is None else min(int(end_step), terminal)
    if end < raw_step - 1:
        raise ValueError("end_step is before the current observation")
    town = _get(observation, "town")
    shops_value = _get(town, "unlocked_shops")
    if not isinstance(shops_value, (list, tuple)):
        raise ValueError("Public town.unlocked_shops is required; missing is not empty")
    shops = tuple(shops_value)
    if len(shops) > rules.max_instances:
        raise ValueError("Observed instance count exceeds the pinned engine maximum")
    for shop in shops:
        rules.signature(shop, ())
    tpd = _positive_config(config, "turnsPerDay", 24)
    interval = _positive_config(config, "townShopUnlockInterval", 3)
    period = tpd * interval
    # EOD action k*period-1 unlocks the shop for observation k*period.
    first_k = max(1, (raw_step + 1 + period - 1) // period)
    arrivals = tuple(islice(range(first_k * period - 1, end + 1, period),
                            rules.max_instances - len(shops)))
    return raw_step, end, shops, arrivals


def _products(rules: DemandRules, selected: Sequence[str] | None) -> tuple[str, ...]:
    names = rules.products if selected is None else tuple(selected)
    if not names or len(set(names)) != len(names):
        raise ValueError("Select a nonempty sequence of distinct products")
    unknown = set(names) - set(rules.products)
    if unknown:
        raise ValueError(f"Unknown products: {sorted(unknown)}")
    return names


def build_schedule(observation: Any, config: Any, rules: DemandRules, *,
                   future_shops: Sequence[str] | None,
                   products: Sequence[str] | None = None,
                   end_step: int | None = None) -> DemandSchedule:
    """Return an exact town-only schedule conditional on a complete draw sequence.

    Pass future_shops=None ONLY for the known-existing-shop lower envelope. It
    omits unresolved future draws and is labelled accordingly. It is not a full
    future town scenario. An explicit sequence must cover every possible unlock
    in the requested window, including duplicate shop instances.
    """
    start, end, observed, unlocks = _window(observation, config, rules, end_step)
    selected = _products(rules, products)
    supplied = () if future_shops is None else tuple(future_shops)
    if future_shops is not None and len(supplied) != len(unlocks):
        raise ValueError(f"Expected {len(unlocks)} future draws, got {len(supplied)}")
    for shop in supplied:
        rules.signature(shop, selected)
    coverage = ("known_shops_only" if future_shops is None and unlocks
                else "specified_future_scenario")
    shop_interval = _positive_config(config, "townShopSellInterval", 4)
    center_interval = _positive_config(config, "townCenterSellInterval", 24)
    rates = [sum(rules.signature(shop, selected)[i] for shop in observed)
             for i in range(len(selected))]
    arrivals = dict(zip(unlocks, supplied))
    rows: list[DemandRow] = []
    for step in range(start, end + 1):
        delta = [0] * len(selected)
        if step % shop_interval == 0:
            delta = [-value for value in rates]
        if step % center_interval == 0:
            for i, item in enumerate(selected):
                if item in rules.center_products:
                    delta[i] -= 1
        if any(delta):
            rows.append(DemandRow(step, tuple(delta)))
        # Arrival must not affect the demand row above, even on a shared tick.
        if step in arrivals:
            signature = rules.signature(arrivals[step], selected)
            rates = [a + b for a, b in zip(rates, signature)]
    return DemandSchedule(start, end, selected, observed, unlocks, supplied,
                          coverage, tuple(rows))


@dataclass(frozen=True)
class DemandGroup:
    per_shop_tick: tuple[int, ...]
    shop_names: tuple[str, ...]


@dataclass(frozen=True)
class DemandFamily:
    products: tuple[str, ...]
    unlock_after_steps: tuple[int, ...]
    groups: tuple[DemandGroup, ...]
    equivalence: str = "projected_town_consumption_only"
    public_observations_interchangeable: bool = False

    @property
    def total_scenarios(self) -> int:
        return len(self.groups) ** len(self.unlock_after_steps)

    def representatives(self, limit: int | None = None) -> Iterable[tuple[str, ...]]:
        """Lazy signatures, not probabilities or observation-information classes.

        A limited prefix is incomplete when limit < total_scenarios. Group names
        remain available because identical selected-product demand does NOT make
        different public shop observations interchangeable for an adaptive policy.
        """
        if limit is not None and (not isinstance(limit, int) or limit < 0):
            raise ValueError("limit must be a nonnegative integer or None")
        representatives = tuple(group.shop_names[0] for group in self.groups)
        paths = product(representatives, repeat=len(self.unlock_after_steps))
        return paths if limit is None else islice(paths, limit)

    def coverage(self, supplied_count: int) -> dict[str, Any]:
        if not 0 <= supplied_count <= self.total_scenarios:
            raise ValueError("Invalid enumerated count")
        return {"enumerated": supplied_count, "total": self.total_scenarios,
                "complete": supplied_count == self.total_scenarios,
                "equivalence": self.equivalence,
                "public_observations_interchangeable": False,
                "probabilities": None}


def scenario_family(observation: Any, config: Any, rules: DemandRules, *,
                    products: Sequence[str], end_step: int | None = None) -> DemandFamily:
    """Enumerate per-product absorption support, including repeated shop draws."""
    _, _, _, unlocks = _window(observation, config, rules, end_step)
    selected = _products(rules, products)
    signatures: dict[tuple[int, ...], list[str]] = {}
    for name, _ in rules.shops:
        signatures.setdefault(rules.signature(name, selected), []).append(name)
    groups = tuple(DemandGroup(signature, tuple(names))
                   for signature, names in sorted(signatures.items()))
    return DemandFamily(selected, unlocks, groups)
