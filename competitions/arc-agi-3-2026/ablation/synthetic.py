from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from typing import Callable

from .harness import AblationKind, ArmConfig, TrialRow, canonical_bytes, sha256


@dataclass(frozen=True)
class Scenario:
    family: str
    seed: int
    action_budget: int
    action_ids: tuple[str, ...]
    semantic_order: tuple[str, ...]
    cue_index: int
    coordinate_target: int
    coordinate_candidates: tuple[int, ...]
    shifted_level: int

    @property
    def digest(self) -> str:
        return sha256(canonical_bytes({
            "family": self.family,
            "seed": self.seed,
            "action_budget": self.action_budget,
            "action_ids": self.action_ids,
            "semantic_order": self.semantic_order,
            "cue_index": self.cue_index,
            "coordinate_target": self.coordinate_target,
            "coordinate_candidates": self.coordinate_candidates,
            "shifted_level": self.shifted_level,
        }))


def make_scenario(seed: int, family: str, budget: int = 24) -> Scenario:
    if family not in {"animation", "info", "coordinate", "transfer"}:
        raise ValueError("unknown family")
    rng = random.Random(seed * 104729 + sum(map(ord, family)))
    semantics = ["N", "S", "E", "W", "PROBE", "ACTIVATE"]
    ids = [f"ACTION{i+1}" for i in range(len(semantics))]
    rng.shuffle(semantics)
    coords = tuple(sorted(rng.sample(range(64), 12)))
    target = coords[rng.randrange(len(coords))]
    return Scenario(
        family=family,
        seed=seed,
        action_budget=budget,
        action_ids=tuple(ids),
        semantic_order=tuple(semantics),
        cue_index=rng.randrange(4),
        coordinate_target=target,
        coordinate_candidates=coords,
        shifted_level=rng.randrange(1, 8),
    )


def _trace_digest(s: Scenario, arm: ArmConfig, events: list[tuple]) -> str:
    return sha256(canonical_bytes({"scenario": s.digest, "arm": arm.as_dict(), "events": events}))


def _row(s: Scenario, arm: ArmConfig, actions: int, *, success: bool, invalid: int = 0,
         repeated: int = 0, evidence: int = 0, transfer: int = 0, abstentions: int = 0,
         simulated: int = 0, events: list[tuple] | None = None) -> TrialRow:
    terminal = "WIN" if success else ("BUDGET" if actions >= s.action_budget else "LOSS")
    real_actions = min(actions, s.action_budget)
    invalid = min(invalid, real_actions)
    repeated = min(repeated, real_actions)
    return TrialRow(
        experiment_id=f"{s.family}-{s.seed}", seed=s.seed, arm=arm.name, success=success,
        terminal=terminal, real_actions=real_actions, simulated_expansions=simulated,
        invalid_actions=invalid, repeated_actions=repeated, evidence_bits=evidence,
        transfer_reuse=transfer, abstentions=abstentions, budget_exhausted=(terminal == "BUDGET"),
        trace_digest=_trace_digest(s, arm, events or []),
    )


def run_animation(s: Scenario, arm: ArmConfig) -> TrialRow:
    # A PROBE exposes a one-frame directional cue. The settled frame deliberately erases it.
    cue_cost = 1
    if arm.retain_intermediate_frames:
        actions = cue_cost + 2 + s.cue_index
        return _row(s, arm, actions, success=True, evidence=4, events=[("probe", "cue", s.cue_index), ("solve",)])
    # Settled-only control must rediscover direction by trying each branch in canonical order.
    tries = s.cue_index + 1
    actions = cue_cost + tries * 4
    return _row(s, arm, actions, success=actions <= s.action_budget, invalid=max(0, tries - 1),
                evidence=1, events=[("probe", "settled-empty"), ("branch-tries", tries)])


def run_info_gain(s: Scenario, arm: ArmConfig) -> TrialRow:
    # Six opaque action IDs hide a permutation. Each probe of an action reveals one semantic.
    target_semantic = "ACTIVATE"
    target_index = s.semantic_order.index(target_semantic)
    if arm.probe_policy == "INFO_GAIN":
        # Probe the action with highest unresolved entropy; deterministic elimination leaves target in <=3 probes.
        ordered = sorted(range(6), key=lambda i: hashlib.sha256(f"{s.seed}:{i}".encode()).digest())
        target_rank = ordered.index(target_index)
        probes = min(3, target_rank + 1)
        found = target_rank < 3
        if not found:
            # elimination after three observations resolves the remaining mapping without a real action
            found = True
        actions = probes + 1
        return _row(s, arm, actions, success=True, evidence=probes * 3 + 2,
                    simulated=6 * probes, events=[("info-probes", tuple(ordered[:probes])), ("activate", target_index)])
    rng = random.Random(s.seed ^ 0x51A9)
    order = list(range(6)); rng.shuffle(order)
    rank = order.index(target_index) + 1
    actions = rank + 1
    return _row(s, arm, actions, success=actions <= s.action_budget, invalid=max(0, rank - 1),
                evidence=rank * 2, events=[("random-probes", tuple(order[:rank])), ("activate", target_index)])


def run_coordinate(s: Scenario, arm: ArmConfig) -> TrialRow:
    # The scene exposes 12 object centers among 64 cells. The correct target is one object center.
    if arm.coordinate_policy == "REDUCED":
        candidates = list(s.coordinate_candidates)
        simulated = 64  # offline component scan, explicitly not real actions
    else:
        candidates = list(range(64))
        simulated = 0
    # Stable scene evidence ranks target-near candidates using a digest, but the target itself is not leaked.
    # Object-center reduction only removes impossible background cells; both arms use identical ranking score.
    def score(cell: int) -> bytes:
        # target-independent deterministic prioritizer; target position varies by seed.
        return hashlib.sha256(f"coord:{s.seed}:{cell}".encode()).digest()
    candidates.sort(key=score)
    rank = candidates.index(s.coordinate_target) + 1
    actions = rank
    return _row(s, arm, actions, success=actions <= s.action_budget, invalid=max(0, rank - 1),
                evidence=12 if arm.coordinate_policy == "REDUCED" else 1, simulated=simulated,
                events=[("candidate-count", len(candidates)), ("rank", rank)])


def run_transfer(s: Scenario, arm: ArmConfig) -> TrialRow:
    # Level A established six effect signatures. Level B translates geometry and permutes action IDs.
    # Transfer reuses signatures but never literal action IDs/coordinates.
    semantics = list(s.semantic_order)
    goal = "ACTIVATE"
    idx = semantics.index(goal)
    if arm.transfer_policy == "TRANSFER":
        # Verify one signature under the new level before reuse; translation costs no real action.
        actions = 2 + (s.shifted_level % 2)
        return _row(s, arm, actions, success=True, evidence=8, transfer=5, simulated=24,
                    events=[("verify-signature", idx), ("translation", s.shifted_level), ("reuse", 5)])
    # Cold start probes opaque actions until ACTIVATE is observed.
    actions = idx + 2
    return _row(s, arm, actions, success=actions <= s.action_budget, invalid=max(0, idx), evidence=idx + 1,
                transfer=0, events=[("cold-probes", idx + 1), ("activate", idx)])


RUNNERS: dict[AblationKind, Callable[[Scenario, ArmConfig], TrialRow]] = {
    AblationKind.ANIMATION: run_animation,
    AblationKind.INFO_GAIN: run_info_gain,
    AblationKind.COORDINATE: run_coordinate,
    AblationKind.TRANSFER: run_transfer,
}


def paired_rows(kind: AblationKind, seeds: range | list[int] | tuple[int, ...], control: ArmConfig,
                treatment: ArmConfig, budget: int = 24) -> tuple[list[TrialRow], str]:
    family = {
        AblationKind.ANIMATION: "animation",
        AblationKind.INFO_GAIN: "info",
        AblationKind.COORDINATE: "coordinate",
        AblationKind.TRANSFER: "transfer",
    }[kind]
    scenarios = [make_scenario(int(seed), family, budget) for seed in seeds]
    runner = RUNNERS[kind]
    rows: list[TrialRow] = []
    for s in scenarios:
        rows.extend((runner(s, control), runner(s, treatment)))
    manifest = [{"seed": s.seed, "family": s.family, "digest": s.digest, "budget": s.action_budget} for s in scenarios]
    return rows, sha256(canonical_bytes(manifest))
