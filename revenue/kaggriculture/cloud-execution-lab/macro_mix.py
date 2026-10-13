# SPDX-License-Identifier: Apache-2.0
"""Identity-free, deterministic multiplicative weights for TITAN macro mixes.

This is an additive policy primitive, not a controller.  It accepts only
step-indexed public loss feedback for the fixed macro vocabulary below.  It
never accepts opponent names, account identifiers, or opaque labels.  Mixed
selection requires an explicit caller-supplied ticket, so the same evidence
always produces the same result and no hidden RNG can change actions.
"""
from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

MACROS = (
    "conservative_expansion",
    "production_acceleration",
    "market_pressure",
    "survival",
)
MACRO_SET = frozenset(MACROS)
LOSS_MAX_BP = 10_000
WEIGHT_TOTAL = 1_000_000
UPDATE_DENOMINATOR = 100_000_000  # 10_000 bp * 10_000 bp.
STEP_MAX = 2_147_483_647


class UnsafeMacroFeedback(ValueError):
    """Raised when feedback could leak identity or break deterministic bounds."""


def _bounded_int(value: Any, name: str, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise UnsafeMacroFeedback(f"{name} must be an int in [{low}, {high}]")
    return value


def _exact_macro_row(row: Mapping[str, Any], name: str) -> tuple[int, ...]:
    if not isinstance(row, Mapping):
        raise UnsafeMacroFeedback(f"{name} must be a mapping")
    keys = frozenset(row)
    if keys != MACRO_SET:
        missing = sorted(MACRO_SET - keys)
        extra = sorted(keys - MACRO_SET, key=repr)
        raise UnsafeMacroFeedback(f"{name} macro fields mismatch: missing={missing} extra={extra}")
    return tuple(_bounded_int(row[macro], f"{name}[{macro!r}]", 0, LOSS_MAX_BP) for macro in MACROS)


def _normalize(weights: Sequence[int]) -> tuple[int, ...]:
    """Largest-remainder normalization to exactly WEIGHT_TOTAL, stable by macro order."""
    if len(weights) != len(MACROS) or any(isinstance(v, bool) or not isinstance(v, int) or v <= 0 for v in weights):
        raise UnsafeMacroFeedback("weights must be positive ints for every macro")
    total = sum(weights)
    floors = [v * WEIGHT_TOTAL // total for v in weights]
    remainder = WEIGHT_TOTAL - sum(floors)
    residues = [(v * WEIGHT_TOTAL) % total for v in weights]
    order = sorted(range(len(weights)), key=lambda i: (-residues[i], i))
    for index in order[:remainder]:
        floors[index] += 1
    return tuple(floors)


@dataclass(frozen=True)
class PublicFeedback:
    """One identity-free in-game feedback observation.

    ``loss_bp`` is a public-evidence-derived loss vector in basis points.  Lower
    is better.  ``step`` must increase strictly so stale/replayed observations
    cannot be counted twice.
    """

    step: int
    loss_bp: Mapping[str, int]

    def __post_init__(self) -> None:
        _bounded_int(self.step, "step", 0, STEP_MAX)
        # Validate on every construction path, including direct objects.
        _exact_macro_row(self.loss_bp, "loss_bp")

    @classmethod
    def from_mapping(cls, row: Mapping[str, Any]) -> "PublicFeedback":
        if not isinstance(row, Mapping):
            raise UnsafeMacroFeedback("feedback must be a mapping")
        keys = frozenset(row)
        expected = frozenset({"step", "loss_bp"})
        if keys != expected:
            missing = sorted(expected - keys)
            extra = sorted(keys - expected, key=repr)
            raise UnsafeMacroFeedback(f"feedback fields mismatch: missing={missing} extra={extra}")
        return cls(step=row["step"], loss_bp=row["loss_bp"])

    def losses(self) -> tuple[int, ...]:
        return _exact_macro_row(self.loss_bp, "loss_bp")


@dataclass(frozen=True)
class MacroMixer:
    """Immutable fixed-point multiplicative-weights state."""

    weights: tuple[int, ...] = (250_000, 250_000, 250_000, 250_000)
    learning_rate_bp: int = 2_000
    last_step: int = -1
    observations: int = 0

    def __post_init__(self) -> None:
        if len(self.weights) != len(MACROS):
            raise UnsafeMacroFeedback("weights length must match macro vocabulary")
        normalized = _normalize(self.weights)
        if normalized != self.weights:
            raise UnsafeMacroFeedback(f"weights must already sum exactly to {WEIGHT_TOTAL}")
        _bounded_int(self.learning_rate_bp, "learning_rate_bp", 1, 5_000)
        if isinstance(self.last_step, bool) or not isinstance(self.last_step, int) or not -1 <= self.last_step <= STEP_MAX:
            raise UnsafeMacroFeedback(f"last_step must be an int in [-1, {STEP_MAX}]")
        if isinstance(self.observations, bool) or not isinstance(self.observations, int) or self.observations < 0:
            raise UnsafeMacroFeedback("observations must be a nonnegative int")

    @classmethod
    def uniform(cls, *, learning_rate_bp: int = 2_000) -> "MacroMixer":
        return cls(learning_rate_bp=learning_rate_bp)

    def distribution_ppm(self) -> dict[str, int]:
        return dict(zip(MACROS, self.weights))

    def deterministic_macro(self) -> str:
        best = max(self.weights)
        return MACROS[next(i for i, weight in enumerate(self.weights) if weight == best)]

    def mixed_macro(self, ticket_ppm: int) -> str:
        """Select from the current distribution using an explicit deterministic ticket."""
        ticket = _bounded_int(ticket_ppm, "ticket_ppm", 0, WEIGHT_TOTAL - 1)
        cursor = 0
        for macro, weight in zip(MACROS, self.weights):
            cursor += weight
            if ticket < cursor:
                return macro
        raise AssertionError("normalized weights failed to cover the ticket")

    def observe(self, feedback: PublicFeedback | Mapping[str, Any]) -> "MacroMixer":
        if not isinstance(feedback, PublicFeedback):
            feedback = PublicFeedback.from_mapping(feedback)
        else:
            # Revalidate the object surface even if a caller bypassed from_mapping.
            _bounded_int(feedback.step, "step", 0, STEP_MAX)
            feedback.losses()
        if feedback.step <= self.last_step:
            raise UnsafeMacroFeedback("feedback step must increase strictly")
        losses = feedback.losses()
        raw = []
        for weight, loss in zip(self.weights, losses):
            factor = UPDATE_DENOMINATOR - self.learning_rate_bp * loss
            # learning_rate<=5000 and loss<=10000 guarantee factor>=50,000,000.
            raw.append(max(1, weight * factor // UPDATE_DENOMINATOR))
        return MacroMixer(
            weights=_normalize(raw),
            learning_rate_bp=self.learning_rate_bp,
            last_step=feedback.step,
            observations=self.observations + 1,
        )

    def observe_many(self, feedback: Iterable[PublicFeedback | Mapping[str, Any]]) -> "MacroMixer":
        state = self
        for row in feedback:
            state = state.observe(row)
        return state


def expected_loss_bp(distribution_ppm: Mapping[str, Any], losses_bp: Mapping[str, Any]) -> int:
    """Deterministic floor of expected loss under a normalized macro distribution."""
    distribution = _exact_macro_distribution(distribution_ppm)
    losses = _exact_macro_row(losses_bp, "losses_bp")
    return sum(prob * loss for prob, loss in zip(distribution, losses)) // WEIGHT_TOTAL


def _exact_macro_distribution(row: Mapping[str, Any]) -> tuple[int, ...]:
    if not isinstance(row, Mapping):
        raise UnsafeMacroFeedback("distribution must be a mapping")
    keys = frozenset(row)
    if keys != MACRO_SET:
        missing = sorted(MACRO_SET - keys)
        extra = sorted(keys - MACRO_SET, key=repr)
        raise UnsafeMacroFeedback(f"distribution macro fields mismatch: missing={missing} extra={extra}")
    values = tuple(_bounded_int(row[macro], f"distribution[{macro!r}]", 0, WEIGHT_TOTAL) for macro in MACROS)
    if sum(values) != WEIGHT_TOTAL:
        raise UnsafeMacroFeedback(f"distribution must sum exactly to {WEIGHT_TOTAL}")
    return values


def worst_family_regret_bp(distribution_ppm: Mapping[str, Any], family_losses: Sequence[Mapping[str, Any]]) -> int:
    """Maximum regret versus each held-out behavior family's best fixed macro."""
    if not family_losses:
        raise UnsafeMacroFeedback("family_losses must be nonempty")
    distribution = _exact_macro_distribution(distribution_ppm)
    worst = 0
    for index, row in enumerate(family_losses):
        losses = _exact_macro_row(row, f"family_losses[{index}]")
        expected = sum(prob * loss for prob, loss in zip(distribution, losses)) // WEIGHT_TOTAL
        regret = expected - min(losses)
        if regret < 0:
            raise AssertionError("expected loss cannot beat the row minimum")
        worst = max(worst, regret)
    return worst


def compare_policies(
    mixer: MacroMixer,
    canonical_distribution_ppm: Mapping[str, Any],
    family_losses: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Compare canonical, learned mixed, and learned deterministic policies on identical rows."""
    learned = mixer.distribution_ppm()
    deterministic = {macro: (WEIGHT_TOTAL if macro == mixer.deterministic_macro() else 0) for macro in MACROS}
    canonical_regret = worst_family_regret_bp(canonical_distribution_ppm, family_losses)
    mixed_regret = worst_family_regret_bp(learned, family_losses)
    deterministic_regret = worst_family_regret_bp(deterministic, family_losses)
    return {
        "canonical_worst_regret_bp": canonical_regret,
        "mixed_worst_regret_bp": mixed_regret,
        "deterministic_worst_regret_bp": deterministic_regret,
        # S09 promotes robustness only: equal or worse held-out max regret is a rejection.
        "mixed_beats_canonical_worst_family": mixed_regret < canonical_regret,
        "distribution_ppm": learned,
        "deterministic_macro": mixer.deterministic_macro(),
        "observations": mixer.observations,
        "last_step": mixer.last_step,
    }
