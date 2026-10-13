"""Deterministic bounded symbolic lookahead for the ARC3 SAGE evidence model.

The planner is deliberately provider-free: it never calls an ARC environment and never
spends a real action.  It searches over symbolic effect evidence supplied by an adapter.
The bundled :class:`SageEvidenceAdapter` consumes the public SAGE transition/model
interfaces but does not invent unseen pixels; exact observed successors are reused only
when their bytes were already present in model evidence, otherwise simulation advances
to an abstract effect state.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
from typing import Any, Callable, Iterable, Protocol, Sequence

PLANNER_SCHEMA = "commons.arc3-sage-symbolic-planner/v1"
PLANNER_VERSION = 1
RECEIPT_KEYS = frozenset({
    "schema", "planner_version", "state_digest", "model_digest", "candidate_order",
    "budget", "weights", "simulated_nodes", "selected_prefix", "selected_score",
    "selected_progress", "confidence_bps", "risk_bps", "real_action_ceiling",
    "planned_real_actions", "real_actions_spent_by_simulation", "authority",
    "receipt_sha256",
})


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return sha256(_canonical_bytes(value)).hexdigest()


def _exact_int(value: Any, name: str, *, minimum: int = 0, maximum: int = 1_000_000) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an exact int in [{minimum},{maximum}]")
    return value


def _action_key(action: Any) -> str:
    key = getattr(action, "key", None)
    if isinstance(key, str) and key:
        return key
    name = getattr(action, "name", None)
    if not isinstance(name, str) or not name:
        raise ValueError("action must expose non-empty name/key")
    x = getattr(action, "x", None)
    y = getattr(action, "y", None)
    if x is None and y is None:
        return name
    if type(x) is not int or type(y) is not int:
        raise ValueError("action coordinates must be exact ints")
    return f"{name}@{x},{y}"


def _action_name(action: Any) -> str:
    name = getattr(action, "name", None)
    if not isinstance(name, str) or not name:
        raise ValueError("action must expose non-empty name")
    return name


def _grid_payload(frame: Any) -> list[list[int]]:
    rows: list[list[int]] = []
    if not isinstance(frame, Sequence) or isinstance(frame, (str, bytes)) or not frame:
        raise ValueError("observation frame must be a non-empty row sequence")
    width: int | None = None
    for row in frame:
        if not isinstance(row, Sequence) or isinstance(row, (str, bytes)) or not row:
            raise ValueError("observation rows must be non-empty sequences")
        vals: list[int] = []
        for value in row:
            if type(value) is not int or not 0 <= value <= 255:
                raise ValueError("observation cells must be exact byte ints")
            vals.append(value)
        if width is None:
            width = len(vals)
        elif width != len(vals):
            raise ValueError("observation frame must be rectangular")
        rows.append(vals)
    return rows


def _observation_payload(obs: Any) -> dict[str, Any]:
    frame = _grid_payload(getattr(obs, "frame"))
    actions_raw = getattr(obs, "available_actions")
    if not isinstance(actions_raw, Sequence) or isinstance(actions_raw, (str, bytes)):
        raise ValueError("available_actions must be a sequence")
    actions = tuple(sorted(actions_raw))
    if any(not isinstance(v, str) or not v for v in actions) or len(actions) != len(set(actions)):
        raise ValueError("available_actions must be unique non-empty strings")
    state = getattr(obs, "state", "NOT_FINISHED")
    if not isinstance(state, str) or not state:
        raise ValueError("observation state must be a non-empty string")
    levels = _exact_int(getattr(obs, "levels_completed", 0), "levels_completed")
    wins = _exact_int(getattr(obs, "win_levels", 0), "win_levels")
    return {
        "frame": frame,
        "available_actions": list(actions),
        "state": state,
        "levels_completed": levels,
        "win_levels": wins,
    }


def observation_digest(obs: Any) -> str:
    """Content digest for one normalized SAGE-style observation."""
    return _digest(_observation_payload(obs))


def _scene_key(obs: Any) -> str:
    """Compact semantics-free scene class: shape, palette histogram and action names."""
    payload = _observation_payload(obs)
    frame = payload["frame"]
    hist: dict[int, int] = {}
    for row in frame:
        for value in row:
            hist[value] = hist.get(value, 0) + 1
    return _digest({
        "shape": [len(frame), len(frame[0])],
        "histogram": [[k, hist[k]] for k in sorted(hist)],
        "available_actions": payload["available_actions"],
    })


@dataclass(frozen=True)
class PlannerBudget:
    max_depth: int = 4
    max_width: int = 6
    max_nodes: int = 96
    max_plan_actions: int = 8

    def validate(self) -> "PlannerBudget":
        _exact_int(self.max_depth, "max_depth", minimum=1, maximum=32)
        _exact_int(self.max_width, "max_width", minimum=1, maximum=128)
        _exact_int(self.max_nodes, "max_nodes", minimum=1, maximum=100_000)
        _exact_int(self.max_plan_actions, "max_plan_actions", minimum=1, maximum=64)
        return self


@dataclass(frozen=True)
class ScoreWeights:
    win: int = 100_000
    progress: int = 12_000
    novelty: int = 900
    confidence: int = 1_100
    changed: int = 250
    uncertainty: int = 180
    risk: int = 1_500
    loop: int = 25_000
    depth: int = 120

    def validate(self) -> "ScoreWeights":
        for name, value in asdict(self).items():
            _exact_int(value, name, minimum=0, maximum=10_000_000)
        if self.win <= self.loop:
            raise ValueError("win weight must exceed loop penalty")
        return self


@dataclass(frozen=True)
class SymbolicState:
    digest: str
    available_actions: tuple[str, ...]
    terminal: str = "NOT_FINISHED"
    cumulative_progress: int = 0
    observation_digest: str | None = None
    observation: Any = field(default=None, compare=False, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.digest, str) or len(self.digest) != 64:
            raise ValueError("state digest must be sha256 hex")
        if tuple(sorted(set(self.available_actions))) != self.available_actions:
            raise ValueError("available_actions must be sorted and unique")
        _exact_int(self.cumulative_progress, "cumulative_progress")


@dataclass(frozen=True)
class ActionHypothesis:
    action: Any = field(compare=False, repr=False)
    action_key: str
    effect_digest: str
    support: int
    total: int
    confidence_bps: int
    uncertainty_bps: int
    changed_bps: int
    progress: int
    terminal: str
    novelty_bps: int
    risk_bps: int
    evidence_scope: str
    successor_observation_digest: str | None = None
    successor_observation: Any = field(default=None, compare=False, repr=False)

    def __post_init__(self) -> None:
        if not self.action_key:
            raise ValueError("action_key required")
        if not isinstance(self.effect_digest, str) or len(self.effect_digest) != 64:
            raise ValueError("effect_digest must be sha256 hex")
        for name in ("support", "total", "confidence_bps", "uncertainty_bps", "changed_bps", "progress", "novelty_bps", "risk_bps"):
            value = getattr(self, name)
            maximum = 10_000 if name.endswith("_bps") else 1_000_000
            _exact_int(value, name, minimum=0, maximum=maximum)
        if self.support > self.total:
            raise ValueError("support cannot exceed total")
        if self.confidence_bps + self.uncertainty_bps != 10_000:
            raise ValueError("confidence and uncertainty must sum to 10000 bps")
        if self.evidence_scope not in {"EXACT", "SCENE", "GLOBAL", "UNOBSERVED", "SYNTHETIC"}:
            raise ValueError("invalid evidence_scope")


class PlanningAdapter(Protocol):
    @property
    def model_digest(self) -> str: ...
    def root_state(self) -> SymbolicState: ...
    def hypotheses(self, state: SymbolicState) -> tuple[ActionHypothesis, ...]: ...
    def simulate(self, state: SymbolicState, hypothesis: ActionHypothesis) -> SymbolicState: ...


@dataclass(frozen=True)
class _SearchNode:
    state: SymbolicState
    path: tuple[ActionHypothesis, ...]
    score: int
    risk_bps: int
    confidence_bps: int
    seen_states: frozenset[str]
    blocked_by_transposition: bool = False

    @property
    def keys(self) -> tuple[str, ...]:
        return tuple(step.action_key for step in self.path)


@dataclass(frozen=True)
class PlanDecision:
    first_action: Any = field(compare=False, repr=False)
    selected_prefix: tuple[str, ...]
    simulated_nodes: int
    receipt: dict[str, Any]

    def receipt_bytes(self) -> bytes:
        return _canonical_bytes(self.receipt)


def _hypothesis_score(h: ActionHypothesis, weights: ScoreWeights, *, depth: int, looped: bool) -> int:
    score = 0
    if h.terminal == "WIN":
        score += weights.win
    score += h.progress * weights.progress
    score += h.novelty_bps * weights.novelty // 10_000
    score += h.confidence_bps * weights.confidence // 10_000
    score += h.changed_bps * weights.changed // 10_000
    score += h.uncertainty_bps * weights.uncertainty // 10_000
    score -= h.risk_bps * weights.risk // 10_000
    score -= depth * weights.depth
    if looped:
        score -= weights.loop
    return score


def _better(node: _SearchNode, incumbent: _SearchNode | None) -> bool:
    if incumbent is None:
        return True
    left = (
        int(node.state.terminal == "WIN"), node.state.cumulative_progress, node.score,
        node.confidence_bps, -node.risk_bps, -len(node.path),
    )
    right = (
        int(incumbent.state.terminal == "WIN"), incumbent.state.cumulative_progress, incumbent.score,
        incumbent.confidence_bps, -incumbent.risk_bps, -len(incumbent.path),
    )
    if left != right:
        return left > right
    return node.keys < incumbent.keys


def _frontier_order(node: _SearchNode) -> tuple[Any, ...]:
    # sort() is ascending; negate reward dimensions and use lexical path as final tie-break.
    return (
        -int(node.state.terminal == "WIN"), -node.state.cumulative_progress, -node.score,
        node.risk_bps, -node.confidence_bps, len(node.path), node.keys,
    )


def _hypothesis_order(h: ActionHypothesis, weights: ScoreWeights, depth: int) -> tuple[Any, ...]:
    return (-_hypothesis_score(h, weights, depth=depth, looped=False), h.action_key, h.effect_digest)


def _budget_payload(budget: PlannerBudget) -> dict[str, int]:
    return asdict(budget)


def _weights_payload(weights: ScoreWeights) -> dict[str, int]:
    return asdict(weights)


def _seal_receipt(payload: dict[str, Any]) -> dict[str, Any]:
    if "receipt_sha256" in payload:
        raise ValueError("receipt payload must be unsealed")
    sealed = dict(payload)
    sealed["receipt_sha256"] = sha256(_canonical_bytes(payload)).hexdigest()
    return sealed


def plan(
    adapter: PlanningAdapter,
    *,
    actions_left: int,
    budget: PlannerBudget = PlannerBudget(),
    weights: ScoreWeights = ScoreWeights(),
) -> PlanDecision:
    """Search a bounded symbolic tree without executing any real environment action."""
    _exact_int(actions_left, "actions_left", minimum=1, maximum=1_000_000)
    budget.validate()
    weights.validate()
    root = adapter.root_state()
    model_digest = adapter.model_digest
    if not isinstance(model_digest, str) or len(model_digest) != 64:
        raise ValueError("adapter model_digest must be sha256 hex")

    root_hypotheses = tuple(sorted(adapter.hypotheses(root), key=lambda h: (h.action_key, h.effect_digest)))
    if len({h.action_key for h in root_hypotheses}) != len(root_hypotheses):
        raise ValueError("adapter emitted duplicate root action keys")
    candidate_order = tuple(h.action_key for h in root_hypotheses)
    if not root_hypotheses:
        raise ValueError("planner requires at least one candidate action")

    frontier = [_SearchNode(root, (), 0, 0, 10_000, frozenset({root.digest}))]
    best: _SearchNode | None = None
    simulated_nodes = 0
    best_score_by_state: dict[str, int] = {root.digest: 0}
    depth_ceiling = min(budget.max_depth, budget.max_plan_actions, actions_left)

    while frontier and simulated_nodes < budget.max_nodes:
        frontier.sort(key=_frontier_order)
        node = frontier.pop(0)
        if node.path and _better(node, best):
            best = node
        if (
            node.state.terminal == "WIN"
            or len(node.path) >= depth_ceiling
            or node.blocked_by_transposition
        ):
            continue
        hypotheses = adapter.hypotheses(node.state)
        ranked = sorted(hypotheses, key=lambda h: _hypothesis_order(h, weights, len(node.path) + 1))
        for hypothesis in ranked[: budget.max_width]:
            if simulated_nodes >= budget.max_nodes:
                break
            successor = adapter.simulate(node.state, hypothesis)
            simulated_nodes += 1
            looped = successor.digest in node.seen_states
            score = node.score + _hypothesis_score(
                hypothesis, weights, depth=len(node.path) + 1, looped=looped
            )
            prior = best_score_by_state.get(successor.digest)
            transposed = prior is not None and prior >= score
            if prior is None or score > prior:
                best_score_by_state[successor.digest] = score
            child = _SearchNode(
                successor,
                node.path + (hypothesis,),
                score,
                min(10_000, node.risk_bps + hypothesis.risk_bps),
                min(node.confidence_bps, hypothesis.confidence_bps),
                node.seen_states | {successor.digest},
                blocked_by_transposition=looped or transposed,
            )
            if _better(child, best):
                best = child
            if not child.blocked_by_transposition and successor.terminal != "WIN":
                frontier.append(child)

    if best is None or not best.path:
        raise ValueError("planner could not simulate any candidate")
    selected = best.keys
    if len(selected) > actions_left:
        raise RuntimeError("internal error: selected plan exceeds real-action ceiling")
    payload = {
        "schema": PLANNER_SCHEMA,
        "planner_version": PLANNER_VERSION,
        "state_digest": root.digest,
        "model_digest": model_digest,
        "candidate_order": list(candidate_order),
        "budget": _budget_payload(budget),
        "weights": _weights_payload(weights),
        "simulated_nodes": simulated_nodes,
        "selected_prefix": list(selected),
        "selected_score": best.score,
        "selected_progress": best.state.cumulative_progress,
        "confidence_bps": best.confidence_bps,
        "risk_bps": best.risk_bps,
        "real_action_ceiling": actions_left,
        "planned_real_actions": len(selected),
        "real_actions_spent_by_simulation": 0,
        "authority": {
            "real_action_execution": False,
            "arc_or_kaggle_account_action": False,
            "submission": False,
            "leaderboard_or_prize_claim": False,
        },
    }
    receipt = _seal_receipt(payload)
    return PlanDecision(best.path[0].action, selected, simulated_nodes, receipt)


class ReceiptVerificationError(ValueError):
    pass


def verify_receipt(
    adapter: PlanningAdapter,
    receipt: dict[str, Any],
    *,
    actions_left: int,
    budget: PlannerBudget = PlannerBudget(),
    weights: ScoreWeights = ScoreWeights(),
) -> str:
    """Recompute the plan and reject tamper, model/state drift, or budget drift."""
    if not isinstance(receipt, dict) or frozenset(receipt) != RECEIPT_KEYS:
        raise ReceiptVerificationError("receipt field set mismatch")
    supplied_digest = receipt.get("receipt_sha256")
    if not isinstance(supplied_digest, str) or len(supplied_digest) != 64:
        raise ReceiptVerificationError("receipt digest malformed")
    unsealed = {k: receipt[k] for k in receipt if k != "receipt_sha256"}
    expected_digest = sha256(_canonical_bytes(unsealed)).hexdigest()
    if supplied_digest != expected_digest:
        raise ReceiptVerificationError("receipt digest mismatch")
    if receipt.get("schema") != PLANNER_SCHEMA or receipt.get("planner_version") != PLANNER_VERSION:
        raise ReceiptVerificationError("receipt schema/version mismatch")
    recomputed = plan(adapter, actions_left=actions_left, budget=budget, weights=weights).receipt
    if _canonical_bytes(recomputed) != _canonical_bytes(receipt):
        raise ReceiptVerificationError("receipt no longer matches state/model/budget/policy")
    return "VERIFIED_OFFLINE"


class SageEvidenceAdapter:
    """Adapter from landed SAGE observations/transitions to conservative symbolic effects.

    It prefers exact observed predecessor+action evidence, then semantics-free scene class,
    then global action evidence.  An exact successor observation is carried into deeper
    search only if all modal-evidence rows agree on its content digest.  Otherwise the
    successor is abstract and no unseen pixel frame is fabricated.
    """

    def __init__(
        self,
        model: Any,
        observation: Any,
        *,
        candidate_factory: Callable[[Any], Iterable[Any]] | None = None,
    ) -> None:
        self.model = model
        self.observation = observation
        self._candidate_factory = candidate_factory
        transitions = getattr(model, "transitions", None)
        if not isinstance(transitions, list):
            raise ValueError("SAGE model must expose transitions list")
        self._observations: dict[str, Any] = {observation_digest(observation): observation}
        rows: list[dict[str, Any]] = []
        for transition in transitions:
            before = getattr(transition, "before")
            after = getattr(transition, "after")
            action = getattr(transition, "action")
            effect = getattr(transition, "effect")
            before_digest = observation_digest(before)
            after_digest = observation_digest(after)
            self._observations[before_digest] = before
            self._observations[after_digest] = after
            effect_digest = getattr(effect, "digest", None)
            if not isinstance(effect_digest, str) or len(effect_digest) != 64:
                raise ValueError("transition effect must expose sha256 digest")
            rows.append({
                "before": before_digest,
                "after": after_digest,
                "scene": _scene_key(before),
                "action": _action_key(action),
                "action_name": _action_name(action),
                "effect": effect_digest,
                "changed": _exact_int(getattr(effect, "changed_count", 0), "changed_count"),
                "progress": _exact_int(max(0, getattr(effect, "level_delta", 0)), "level_delta"),
                "terminal": str(getattr(effect, "terminal", "NOT_FINISHED")),
            })
        self._rows = tuple(sorted(rows, key=lambda r: _canonical_bytes(r)))
        self._model_digest = _digest({"schema": "sage-evidence/v1", "rows": list(self._rows)})

    @property
    def model_digest(self) -> str:
        return self._model_digest

    def _state_from_observation(self, obs: Any, *, cumulative_progress: int) -> SymbolicState:
        payload = _observation_payload(obs)
        digest = observation_digest(obs)
        return SymbolicState(
            digest=digest,
            available_actions=tuple(payload["available_actions"]),
            terminal=payload["state"],
            cumulative_progress=cumulative_progress,
            observation_digest=digest,
            observation=obs,
        )

    def root_state(self) -> SymbolicState:
        return self._state_from_observation(self.observation, cumulative_progress=0)

    def _candidate_actions(self, obs: Any) -> tuple[Any, ...]:
        if self._candidate_factory is not None:
            actions = tuple(self._candidate_factory(obs))
        else:
            # Import lazily so the generic planner and its receipt verifier remain
            # dependency-free and separately testable.
            from sage_policy import Policy  # type: ignore
            actions = tuple(Policy.candidate_actions(obs))
        keyed = sorted(((_action_key(action), action) for action in actions), key=lambda row: row[0])
        if len({key for key, _ in keyed}) != len(keyed):
            raise ValueError("candidate factory emitted duplicate actions")
        return tuple(action for _, action in keyed)

    @staticmethod
    def _modal_effect(rows: Sequence[dict[str, Any]]) -> tuple[str, tuple[dict[str, Any], ...]]:
        groups: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            groups.setdefault(row["effect"], []).append(row)
        effect = min(groups, key=lambda d: (-len(groups[d]), d))
        return effect, tuple(sorted(groups[effect], key=lambda r: (r["after"], r["action"])))

    def _evidence_rows(self, obs: Any, action: Any) -> tuple[str, tuple[dict[str, Any], ...]]:
        before = observation_digest(obs)
        key = _action_key(action)
        name = _action_name(action)
        exact = tuple(r for r in self._rows if r["before"] == before and r["action"] == key)
        if exact:
            return "EXACT", exact
        scene = _scene_key(obs)
        local = tuple(r for r in self._rows if r["scene"] == scene and r["action_name"] == name)
        if local:
            return "SCENE", local
        global_rows = tuple(r for r in self._rows if r["action_name"] == name)
        if global_rows:
            return "GLOBAL", global_rows
        return "UNOBSERVED", ()

    def hypotheses(self, state: SymbolicState) -> tuple[ActionHypothesis, ...]:
        obs = state.observation
        if obs is None:
            obs = self._observations.get(state.observation_digest or "")
        if obs is None:
            # Abstract effect state: reuse global action evidence only.  We deliberately
            # do not fabricate a frame merely to obtain a scene-specific prediction.
            actions = []
            names = state.available_actions
            for name in names:
                action_rows = [r for r in self._rows if r["action_name"] == name]
                # Reuse a previously observed token object when possible; otherwise
                # abstract states cannot construct an ACTION object safely.
                token = None
                for transition in getattr(self.model, "transitions"):
                    if _action_name(getattr(transition, "action")) == name:
                        token = getattr(transition, "action")
                        break
                if token is not None and action_rows:
                    actions.append(token)
            candidate_actions = tuple(actions)
        else:
            candidate_actions = self._candidate_actions(obs)

        hypotheses: list[ActionHypothesis] = []
        for action in candidate_actions:
            key = _action_key(action)
            name = _action_name(action)
            if obs is None:
                scope = "GLOBAL"
                rows = tuple(r for r in self._rows if r["action_name"] == name)
            else:
                scope, rows = self._evidence_rows(obs, action)
            if not rows:
                effect_digest = sha256(f"UNOBSERVED|{key}".encode("utf-8")).hexdigest()
                hypotheses.append(ActionHypothesis(
                    action, key, effect_digest, 0, 0, 0, 10_000, 0, 0,
                    "NOT_FINISHED", 10_000, 10_000, "UNOBSERVED",
                ))
                continue
            effect_digest, modal = self._modal_effect(rows)
            support = len(modal)
            total = len(rows)
            confidence = support * 10_000 // total
            representative = modal[0]
            successor_digests = {r["after"] for r in modal}
            successor_digest = next(iter(successor_digests)) if len(successor_digests) == 1 else None
            successor = self._observations.get(successor_digest or "")
            novelty = 0
            if successor is not None:
                try:
                    novelty = int(max(0.0, min(1.0, float(self.model.novelty(successor)))) * 10_000)
                except (AttributeError, TypeError, ValueError):
                    novelty = 0
            global_rows = tuple(r for r in self._rows if r["action_name"] == name)
            contradictory = False
            if scope in {"EXACT", "SCENE"} and global_rows:
                global_effect, _ = self._modal_effect(global_rows)
                contradictory = global_effect != effect_digest
            diversity = len({r["effect"] for r in rows})
            risk = min(10_000, (10_000 - confidence) + (2_500 if contradictory else 0) + max(0, diversity - 1) * 400)
            hypotheses.append(ActionHypothesis(
                action=action,
                action_key=key,
                effect_digest=effect_digest,
                support=support,
                total=total,
                confidence_bps=confidence,
                uncertainty_bps=10_000 - confidence,
                changed_bps=10_000 if representative["changed"] > 0 else 0,
                progress=representative["progress"],
                terminal=representative["terminal"],
                novelty_bps=novelty,
                risk_bps=risk,
                evidence_scope=scope,
                successor_observation_digest=successor_digest,
                successor_observation=successor,
            ))
        return tuple(sorted(hypotheses, key=lambda h: (h.action_key, h.effect_digest)))

    def simulate(self, state: SymbolicState, hypothesis: ActionHypothesis) -> SymbolicState:
        progress = state.cumulative_progress + hypothesis.progress
        successor = hypothesis.successor_observation
        if successor is not None:
            return self._state_from_observation(successor, cumulative_progress=progress)
        available = state.available_actions
        digest = _digest({
            "parent": state.digest,
            "action": hypothesis.action_key,
            "effect": hypothesis.effect_digest,
            "terminal": hypothesis.terminal,
            "progress": progress,
            "available_actions": list(available),
        })
        return SymbolicState(
            digest=digest,
            available_actions=available,
            terminal=hypothesis.terminal,
            cumulative_progress=progress,
            observation_digest=None,
            observation=None,
        )
