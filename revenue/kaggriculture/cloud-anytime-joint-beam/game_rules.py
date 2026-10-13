# SPDX-License-Identifier: Apache-2.0
"""Game-agnostic interface between the joint-action beam core and title rules.

``joint_action_beam`` is a proposer/scorer: it ranks candidate unit actions and
never reads title-specific state fields or action vocabularies. A title plugs
in by implementing :class:`MechanicsProvider` (rules) and :class:`Scorer`
(evaluation). The worker-phase adapter in ``mechanics_adapter`` is one
implementation; ``toy_grid_game`` is a second, deliberately tiny one that
shares no vocabulary with the first.

Behavioral contract (enforced by :func:`run_provider_checks`):

- ``transition(state, idx, action)`` returns a fresh successor state for a
  legal/effective action, or ``None`` for an illegal or resource-conflicting
  one. PASS-style no-ops may return a fresh state equal to the input. The
  input state's game fields are never mutated and the input object itself is
  never returned as the successor. Keys beginning with ``"__"`` are
  provider-internal search bookkeeping: they are ignored by the non-mutation
  check, but they are included in ``state_key`` so that equal keys imply
  identical future transition behavior.
- ``legal_actions(state, idx, canonical)`` deterministically enumerates a
  bounded candidate family; it may be empty when the title only searches the
  canonical action.
- ``state_key(state)`` returns a stable, hashable identity: deep copies share
  keys, and an effective action changes the key. The beam core does not consume
  it yet; it exists for future second-title work (frontier dedupe,
  transposition caches).
"""
from __future__ import annotations

import copy
from collections.abc import Hashable
from dataclasses import dataclass, field
from typing import Any, Iterable, NamedTuple, Protocol, runtime_checkable

from joint_action_beam import Action, State

_INTERNAL_PREFIX = "__"


@runtime_checkable
class MechanicsProvider(Protocol):
    """Title rules behind the search/evaluator interface."""

    def legal_actions(
        self, state: State, idx: int, canonical: Action
    ) -> Iterable[Action]:
        """Deterministically enumerate a bounded candidate family for unit ``idx``."""
        ...

    def transition(
        self, state: State, idx: int, action: Action
    ) -> State | None:
        """Fresh successor state for a legal action; ``None`` when illegal/ineffective."""
        ...

    def state_key(self, state: State) -> Hashable:
        """Stable hashable identity of a state, including provider bookkeeping."""
        ...


@runtime_checkable
class Scorer(Protocol):
    """Evaluator: integer score of a (state, action-prefix) pair."""

    def __call__(self, state: State, actions: tuple[Action, ...]) -> int:
        ...


def provider_callbacks(rules: MechanicsProvider):
    """Return ``(candidates, transition)`` callables shaped for ``search_joint_actions``.

    Scorers already match the beam's ``Scorer`` signature, so they are passed
    through unwrapped.
    """
    def candidates(state: State, idx: int, canonical: Action) -> Iterable[Action]:
        return rules.legal_actions(state, idx, canonical)

    def transition(state: State, idx: int, action: Action) -> State | None:
        return rules.transition(state, idx, action)

    return candidates, transition


def _game_view(state: Any) -> Any:
    """State with provider-internal bookkeeping stripped, for equality checks."""
    if isinstance(state, dict):
        return {
            key: _game_view(value)
            for key, value in state.items()
            if not (isinstance(key, str) and key.startswith(_INTERNAL_PREFIX))
        }
    if isinstance(state, (list, tuple)):
        return [_game_view(value) for value in state]
    return state


@dataclass
class ProviderScenario:
    """One concrete situation used to exercise a provider's contract."""

    name: str
    initial_state: State
    canonical: tuple[Action, ...]
    probes: list[tuple[int, Action]] = field(default_factory=list)
    effective_probe: tuple[int, Action] | None = None
    max_candidates: int = 64


class Check(NamedTuple):
    name: str
    passed: bool
    detail: str


def run_provider_checks(
    rules: MechanicsProvider, scenario: ProviderScenario
) -> list[Check]:
    """Run the implementation-agnostic contract battery against one provider.

    Returns one :class:`Check` per invariant; callers decide how to report.
    """
    checks: list[Check] = []

    def record(name: str, passed: bool, detail: str = "") -> None:
        checks.append(Check(name, bool(passed), detail))

    record(
        "implements-protocol",
        isinstance(rules, MechanicsProvider),
        type(rules).__name__,
    )

    first = list(
        rules.legal_actions(
            copy.deepcopy(scenario.initial_state), 0, scenario.canonical[0]
        )
    )
    second = list(
        rules.legal_actions(
            copy.deepcopy(scenario.initial_state), 0, scenario.canonical[0]
        )
    )
    record("legal-actions-iterable", first is not None, f"{len(first)} candidates")
    record("legal-actions-deterministic", first == second, f"{len(first)} candidates")
    record(
        "legal-actions-bounded",
        len(first) <= scenario.max_candidates,
        f"{len(first)} <= {scenario.max_candidates}",
    )

    key0 = rules.state_key(scenario.initial_state)
    record("state-key-hashable", isinstance(key0, Hashable), type(key0).__name__)
    record(
        "state-key-stable-on-copy",
        rules.state_key(copy.deepcopy(scenario.initial_state)) == key0,
    )

    for number, (idx, action) in enumerate(scenario.probes):
        probe_state = copy.deepcopy(scenario.initial_state)
        before = _game_view(probe_state)
        first_out = rules.transition(probe_state, idx, action)
        second_out = rules.transition(
            copy.deepcopy(scenario.initial_state), idx, action
        )
        label = f"probe-{number} {action!r}"
        if first_out is None or second_out is None:
            record(
                f"probe-{number}-none-deterministic",
                (first_out is None) == (second_out is None),
                label,
            )
            continue
        record(
            f"probe-{number}-deterministic",
            rules.state_key(first_out) == rules.state_key(second_out),
            label,
        )
        record(
            f"probe-{number}-fresh-successor",
            first_out is not probe_state,
            label,
        )
        record(
            f"probe-{number}-input-unmutated",
            _game_view(probe_state) == before,
            label,
        )

    if scenario.effective_probe is not None:
        eff_idx, eff_action = scenario.effective_probe
        label = f"effective {eff_action!r}"
        effective = rules.transition(
            copy.deepcopy(scenario.initial_state), eff_idx, eff_action
        )
        record("effective-probe-legal", effective is not None, label)
        if effective is not None:
            record(
                "effective-probe-changes-state",
                _game_view(effective) != _game_view(scenario.initial_state),
                label,
            )
            record(
                "effective-probe-changes-key",
                rules.state_key(effective) != key0,
                label,
            )

    return checks
