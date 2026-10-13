"""Transparent production/supply-chain scenario model for DOE Storage Design STEP.

This module does NOT model electrochemistry and does not claim measured performance.
It compares user-supplied manufacturing scenarios. Monetary inputs are exact decimal
strings. Authority labels identify the intended evidence class but do not authenticate
supplier quotes, purchase records, or measured observations.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
from typing import Any

ZERO = Decimal("0")
HUNDRED = Decimal("100")
MINUTES_PER_HOUR = Decimal("60")
AUTHORITIES = frozenset({"SYNTHETIC_SCENARIO", "QUOTE_BACKED", "PURCHASE_EVIDENCE", "MEASURED_ROUTER"})


class ModelError(ValueError):
    pass


def _decimal(value: Any, name: str, *, positive: bool = False) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, str):
        raise ModelError(f"{name} must be a decimal string")
    try:
        out = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise ModelError(f"{name} is not a valid decimal") from exc
    if not out.is_finite():
        raise ModelError(f"{name} must be finite")
    if positive and out <= ZERO:
        raise ModelError(f"{name} must be > 0")
    if not positive and out < ZERO:
        raise ModelError(f"{name} must be >= 0")
    return out


def _integer(value: Any, name: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ModelError(f"{name} must be an integer")
    if value < minimum:
        raise ModelError(f"{name} must be >= {minimum}")
    return value


@dataclass(frozen=True)
class Component:
    name: str
    quantity: int
    unit_cost_usd: Decimal
    qualified_suppliers: int
    bespoke: bool

    @property
    def extended_cost(self) -> Decimal:
        return self.unit_cost_usd * self.quantity


@dataclass(frozen=True)
class Scenario:
    name: str
    authority: str
    evidence_ref: str
    power_kw: Decimal
    energy_kwh: Decimal
    components: tuple[Component, ...]
    assembly_minutes: int
    direct_labor_usd_per_hour: Decimal
    annualized_tooling_usd_per_unit: Decimal

    @property
    def material_cost(self) -> Decimal:
        return sum((c.extended_cost for c in self.components), ZERO)

    @property
    def labor_cost(self) -> Decimal:
        return Decimal(self.assembly_minutes) / MINUTES_PER_HOUR * self.direct_labor_usd_per_hour

    @property
    def conversion_cost(self) -> Decimal:
        return self.material_cost + self.labor_cost + self.annualized_tooling_usd_per_unit

    @property
    def single_source_cost(self) -> Decimal:
        return sum((c.extended_cost for c in self.components if c.qualified_suppliers == 1), ZERO)

    @property
    def single_source_value_pct(self) -> Decimal:
        if self.material_cost == ZERO:
            return ZERO
        return self.single_source_cost / self.material_cost * HUNDRED

    @property
    def bespoke_sku_count(self) -> int:
        return sum(1 for c in self.components if c.bespoke)

    @property
    def sku_count(self) -> int:
        return len(self.components)

    def metrics(self) -> dict[str, str | int]:
        return {
            "scenario": self.name,
            "authority": self.authority,
            "evidence_ref": self.evidence_ref,
            "material_cost_usd": str(self.material_cost.quantize(Decimal("0.01"))),
            "labor_cost_usd": str(self.labor_cost.quantize(Decimal("0.01"))),
            "conversion_cost_usd": str(self.conversion_cost.quantize(Decimal("0.01"))),
            "conversion_cost_usd_per_kw": str((self.conversion_cost / self.power_kw).quantize(Decimal("0.01"))),
            "conversion_cost_usd_per_kwh": str((self.conversion_cost / self.energy_kwh).quantize(Decimal("0.01"))),
            "single_source_value_pct": str(self.single_source_value_pct.quantize(Decimal("0.01"))),
            "sku_count": self.sku_count,
            "bespoke_sku_count": self.bespoke_sku_count,
            "assembly_minutes": self.assembly_minutes,
        }


def _component(raw: dict[str, Any], i: int) -> Component:
    if not isinstance(raw, dict):
        raise ModelError(f"components[{i}] must be an object")
    expected = {"name", "quantity", "unit_cost_usd", "qualified_suppliers", "bespoke"}
    if set(raw) != expected:
        raise ModelError(f"components[{i}] keys must equal {sorted(expected)}")
    name = raw["name"]
    if not isinstance(name, str) or not name.strip() or len(name) > 120:
        raise ModelError(f"components[{i}].name invalid")
    bespoke = raw["bespoke"]
    if not isinstance(bespoke, bool):
        raise ModelError(f"components[{i}].bespoke must be boolean")
    return Component(
        name=name.strip(),
        quantity=_integer(raw["quantity"], f"components[{i}].quantity", minimum=1),
        unit_cost_usd=_decimal(raw["unit_cost_usd"], f"components[{i}].unit_cost_usd"),
        qualified_suppliers=_integer(raw["qualified_suppliers"], f"components[{i}].qualified_suppliers", minimum=1),
        bespoke=bespoke,
    )


def parse_scenario(raw: dict[str, Any]) -> Scenario:
    if not isinstance(raw, dict):
        raise ModelError("scenario must be an object")
    expected = {
        "name", "authority", "evidence_ref", "power_kw", "energy_kwh", "components",
        "assembly_minutes", "direct_labor_usd_per_hour", "annualized_tooling_usd_per_unit",
    }
    if set(raw) != expected:
        raise ModelError(f"scenario keys must equal {sorted(expected)}")
    authority = raw["authority"]
    if authority not in AUTHORITIES:
        raise ModelError(f"authority must be one of {sorted(AUTHORITIES)}")
    evidence_ref = raw["evidence_ref"]
    if not isinstance(evidence_ref, str) or not evidence_ref.strip() or len(evidence_ref) > 240:
        raise ModelError("evidence_ref must be a non-empty string <= 240 characters")
    evidence_ref = evidence_ref.strip()
    if authority == "SYNTHETIC_SCENARIO" and not evidence_ref.startswith("synthetic:"):
        raise ModelError("synthetic scenarios require a synthetic: evidence_ref")
    if authority != "SYNTHETIC_SCENARIO" and evidence_ref.startswith("synthetic:"):
        raise ModelError("non-synthetic authority cannot use a synthetic: evidence_ref")
    if not isinstance(raw["name"], str) or not raw["name"].strip():
        raise ModelError("name must be a non-empty string")
    components = raw["components"]
    if not isinstance(components, list) or not components:
        raise ModelError("components must be a non-empty list")
    parsed = tuple(_component(c, i) for i, c in enumerate(components))
    names = [c.name.casefold() for c in parsed]
    if len(names) != len(set(names)):
        raise ModelError("component names must be unique")
    return Scenario(
        name=raw["name"].strip(),
        authority=authority,
        evidence_ref=evidence_ref,
        power_kw=_decimal(raw["power_kw"], "power_kw", positive=True),
        energy_kwh=_decimal(raw["energy_kwh"], "energy_kwh", positive=True),
        components=parsed,
        assembly_minutes=_integer(raw["assembly_minutes"], "assembly_minutes"),
        direct_labor_usd_per_hour=_decimal(raw["direct_labor_usd_per_hour"], "direct_labor_usd_per_hour"),
        annualized_tooling_usd_per_unit=_decimal(raw["annualized_tooling_usd_per_unit"], "annualized_tooling_usd_per_unit"),
    )


def compare(baseline: Scenario, candidate: Scenario) -> dict[str, Any]:
    if baseline.power_kw != candidate.power_kw or baseline.energy_kwh != candidate.energy_kwh:
        raise ModelError("baseline and candidate must represent the same power/energy rating")
    if baseline.authority != candidate.authority:
        raise ModelError("baseline and candidate must use the same evidence authority")
    if baseline.conversion_cost == ZERO:
        raise ModelError("baseline conversion cost must be > 0")
    cost_delta = candidate.conversion_cost - baseline.conversion_cost
    cost_reduction_pct = -cost_delta / baseline.conversion_cost * HUNDRED
    single_source_delta = candidate.single_source_value_pct - baseline.single_source_value_pct
    if baseline.authority == "SYNTHETIC_SCENARIO":
        boundary = (
            "Synthetic scenario only. Values are not supplier quotes, measured performance, DOE scores, "
            "or a claim that the candidate savings have been achieved."
        )
    else:
        boundary = (
            f"Evidence class {baseline.authority} is caller-labeled and bound to the returned evidence_ref fields; "
            "the model does not authenticate the referenced evidence. Human evidence review remains required."
        )
    return {
        "baseline": baseline.metrics(),
        "candidate": candidate.metrics(),
        "delta": {
            "conversion_cost_usd": str(cost_delta.quantize(Decimal("0.01"))),
            "conversion_cost_reduction_pct": str(cost_reduction_pct.quantize(Decimal("0.01"))),
            "single_source_value_pct_points": str(single_source_delta.quantize(Decimal("0.01"))),
            "sku_count": candidate.sku_count - baseline.sku_count,
            "bespoke_sku_count": candidate.bespoke_sku_count - baseline.bespoke_sku_count,
            "assembly_minutes": candidate.assembly_minutes - baseline.assembly_minutes,
        },
        "truth_boundary": boundary,
    }


def load(path: str | Path) -> Scenario:
    return parse_scenario(json.loads(Path(path).read_text(encoding="utf-8")))


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("baseline")
    parser.add_argument("candidate")
    args = parser.parse_args()
    print(json.dumps(compare(load(args.baseline), load(args.candidate)), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
