"""Identity-free rolling mixture over public rival-flow stress hypotheses.

The module calibrates scenario weights, not opponent identities. It consumes only
attributable public flow intervals and optional public timing relations. Ambiguous
or censored observations remain diagnostics. Callers keep the incumbent policy
whenever ``ready`` is false.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Iterable, Mapping, Sequence

PPM = 1_000_000
ALIGNMENTS = frozenset((
    "any",
    "before_absorption",
    "near_absorption",
    "after_absorption",
))
SAMPLE_ALIGNMENTS = ALIGNMENTS - {"any"}


@dataclass(frozen=True)
class StressScenario:
    """One public stress hypothesis used only for seller scenario weighting."""
    name: str
    quantity: int
    alignment: str = "any"


@dataclass(frozen=True)
class PublicFlowSample:
    """One prior public-flow receipt suitable for causal calibration."""
    step: int
    product: str
    lower: int
    upper: int | None
    reason: str
    alignment: str | None = None
    ambiguous: bool = False

    @property
    def exact(self) -> bool:
        return (
            not self.ambiguous
            and self.reason == "identified"
            and self.upper is not None
            and self.lower == self.upper
        )


def _validate_scenarios(scenarios: Sequence[StressScenario]) -> tuple[StressScenario, ...]:
    result = tuple(scenarios)
    if not result:
        raise ValueError("at least one stress scenario is required")
    names = set()
    for scenario in result:
        if not isinstance(scenario, StressScenario):
            raise ValueError("scenarios must be StressScenario values")
        if not isinstance(scenario.name, str) or not scenario.name:
            raise ValueError("scenario names must be non-empty strings")
        if scenario.name in names:
            raise ValueError("scenario names must be unique")
        names.add(scenario.name)
        if isinstance(scenario.quantity, bool) or not isinstance(scenario.quantity, int):
            raise ValueError("scenario quantities must be integers")
        if scenario.quantity < 0:
            raise ValueError("scenario quantities must be non-negative")
        if not isinstance(scenario.alignment, str) or scenario.alignment not in ALIGNMENTS:
            raise ValueError("unsupported public timing alignment")
    return result


def _validate_sample(sample: PublicFlowSample) -> None:
    if not isinstance(sample, PublicFlowSample):
        raise ValueError("samples must be PublicFlowSample values")
    if isinstance(sample.step, bool) or not isinstance(sample.step, int) or sample.step < 0:
        raise ValueError("sample step must be a non-negative integer")
    if not isinstance(sample.product, str) or not sample.product:
        raise ValueError("sample product must be a non-empty string")
    if isinstance(sample.lower, bool) or not isinstance(sample.lower, int) or sample.lower < 0:
        raise ValueError("sample lower bound must be a non-negative integer")
    if sample.upper is not None:
        if isinstance(sample.upper, bool) or not isinstance(sample.upper, int) or sample.upper < 0:
            raise ValueError("sample upper bound must be a non-negative integer or None")
        if sample.upper < sample.lower:
            raise ValueError("sample interval is invalid")
    if not isinstance(sample.reason, str) or not sample.reason:
        raise ValueError("sample reason must be a non-empty string")
    if sample.alignment is not None:
        if not isinstance(sample.alignment, str) or sample.alignment not in SAMPLE_ALIGNMENTS:
            raise ValueError("sample has unsupported public timing alignment")
    if not isinstance(sample.ambiguous, bool):
        raise ValueError("sample ambiguous flag must be boolean")


def _normalize_ppm(raw: Mapping[str, Fraction], order: Sequence[str]) -> dict[str, int]:
    total = sum(raw.values(), Fraction(0, 1))
    if total <= 0:
        raise ValueError("mixture scores must have positive mass")
    scaled = {name: raw[name] * PPM / total for name in order}
    weights = {name: int(scaled[name]) for name in order}
    remainder = PPM - sum(weights.values())
    rank = sorted(
        range(len(order)),
        key=lambda i: (-(scaled[order[i]] - int(scaled[order[i]])), i),
    )
    for i in rank[:remainder]:
        weights[order[i]] += 1
    return weights


def fixed_diverse_mixture(scenarios: Sequence[StressScenario]) -> dict:
    """Return a deterministic equal-weight experimental mixture."""
    scenarios = _validate_scenarios(scenarios)
    order = [scenario.name for scenario in scenarios]
    weights = _normalize_ppm({name: Fraction(1, 1) for name in order}, order)
    return {
        "ready": True,
        "mode": "fixed_diverse",
        "support": 0,
        "ambiguous": 0,
        "weights_ppm": weights,
        "top": max(order, key=lambda name: (weights[name], -order.index(name))),
        "interpretation": "equal public stress hypotheses; not opponent identity probabilities",
    }


def scenarios_from_public_stress(signal: Mapping, *, capacity: int = 100) -> tuple[StressScenario, ...]:
    """Build a small deduplicated quantity family from public stress diagnostics."""
    if not isinstance(signal, Mapping):
        raise ValueError("public stress signal must be a mapping")
    if isinstance(capacity, bool) or not isinstance(capacity, int) or capacity < 0:
        raise ValueError("capacity must be a non-negative integer")
    candidates = (
        ("no_flow", 0),
        ("visible", signal.get("visible", 0)),
        ("short", signal.get("short", 0)),
        ("repeat", signal.get("long_rate", 0)),
        ("capacity", capacity),
    )
    scenarios = []
    seen_quantities = set()
    for name, quantity in candidates:
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 0:
            raise ValueError("public stress quantities must be non-negative integers")
        quantity = min(capacity, quantity)
        if quantity in seen_quantities:
            continue
        seen_quantities.add(quantity)
        scenarios.append(StressScenario(name, quantity))
    return tuple(scenarios)


def rolling_public_mixture(
    product: str,
    scenarios: Sequence[StressScenario],
    samples: Iterable[PublicFlowSample],
    *,
    now: int,
    window: int = 24,
    minimum_support: int = 3,
    timing_mismatch_cost: int = 25,
) -> dict:
    """Calibrate public stress weights from exact, prior, same-product receipts."""
    scenarios = _validate_scenarios(scenarios)
    if not isinstance(product, str) or not product:
        raise ValueError("product must be a non-empty string")
    for name, value in (
        ("now", now),
        ("window", window),
        ("minimum_support", minimum_support),
        ("timing_mismatch_cost", timing_mismatch_cost),
    ):
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{name} must be an integer")
    if now < 0:
        raise ValueError("now must be non-negative")
    if window < 1 or minimum_support < 1 or timing_mismatch_cost < 0:
        raise ValueError("window/support must be positive and timing cost non-negative")

    cutoff = now - window
    exact = []
    ambiguous = 0
    for sample in samples:
        _validate_sample(sample)
        if sample.product != product or sample.step >= now or sample.step < cutoff:
            continue
        if not sample.exact:
            ambiguous += 1
            continue
        exact.append(sample)

    exact.sort(key=lambda sample: sample.step)
    if len(exact) < minimum_support:
        return {
            "ready": False,
            "mode": "rolling_public",
            "support": len(exact),
            "ambiguous": ambiguous,
            "latest_training_step": exact[-1].step if exact else None,
            "weights_ppm": {},
            "top": None,
            "interpretation": "insufficient attributable public evidence; preserve incumbent assumptions",
        }

    raw = {}
    losses = {}
    for scenario in scenarios:
        loss = 0
        for sample in exact:
            loss += abs(scenario.quantity - sample.lower)
            if (
                sample.alignment is not None
                and scenario.alignment != "any"
                and scenario.alignment != sample.alignment
            ):
                loss += timing_mismatch_cost
        losses[scenario.name] = loss
        raw[scenario.name] = Fraction(1, 1 + loss)

    order = [scenario.name for scenario in scenarios]
    weights = _normalize_ppm(raw, order)
    top = min(order, key=lambda name: (-weights[name], losses[name], order.index(name)))
    return {
        "ready": True,
        "mode": "rolling_public",
        "support": len(exact),
        "ambiguous": ambiguous,
        "latest_training_step": exact[-1].step,
        "weights_ppm": weights,
        "loss": losses,
        "top": top,
        "interpretation": "calibrated public stress-hypothesis weights; not opponent identity probabilities",
    }
