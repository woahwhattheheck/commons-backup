"""Public ARC3 SAGE planner facade with evidence-conditioned reachability.

The landed planner implementation remains byte-for-byte in the private
``_sage_symbolic_planner_core`` module. This facade narrows the evidence authority
boundary and repairs exact predecessor identity for production SAGE observations:

* EXACT identity binds the full ordered animation-frame sequence plus settled
  action/state/progress metadata. Two observations with the same final frame but
  different temporal histories are not interchangeable predecessors.
* SCENE/GLOBAL fallback evidence may inform abstract effect/confidence/risk,
  but never a concrete successor, terminal state, progress or successor novelty.
* EXACT evidence carries a concrete future only when every transition matching
  the exact predecessor and full action token agrees on successor/progress/
  terminal semantics.
* unresolved abstract states have no inferred successor action space, so
  lookahead stops at the evidence boundary.
* terminal or inactive states cannot generate further hypotheses, including
  GAME_OVER observations that still advertise available action names.
"""
from __future__ import annotations

from collections.abc import Sequence as _Sequence
from dataclasses import replace as _replace

try:
    from . import _sage_symbolic_planner_core as _core
except ImportError:  # direct module execution from the competition directory
    import _sage_symbolic_planner_core as _core  # type: ignore

OBSERVATION_IDENTITY_POLICY = "ordered-animation-frames-plus-settled-metadata/v1"
REACHABILITY_POLICY = "exact-predecessor-full-animation-unanimous-active-state-reachability/v4"
PLANNER_SCHEMA = "commons.arc3-sage-symbolic-planner/v4"
PLANNER_VERSION = 4

# Preserve the historical module surface. Keep the old implementation private
# and byte-exact; exact identity, SageEvidenceAdapter, plan and verify_receipt are
# replaced below.
for _name, _value in vars(_core).items():
    if _name.startswith("__") or _name in {
        "SageEvidenceAdapter", "plan", "verify_receipt", "PLANNER_SCHEMA", "PLANNER_VERSION"
    }:
        continue
    globals()[_name] = _value
    if getattr(_value, "__module__", None) == _core.__name__:
        try:
            _value.__module__ = __name__
        except (AttributeError, TypeError):
            pass

_BaseSageEvidenceAdapter = _core.SageEvidenceAdapter


def _ordered_frames_payload(obs):
    """Return the complete ordered frame sequence for exact predecessor identity.

    Production ``sage_core.Observation`` exposes ``frames``. Small generic test
    adapters may expose only ``frame``; those are normalized as a one-frame
    sequence rather than receiving weaker identity semantics.
    """
    frames_raw = getattr(obs, "frames", None)
    if frames_raw is None:
        frames_raw = (getattr(obs, "frame"),)
    if (
        not isinstance(frames_raw, _Sequence)
        or isinstance(frames_raw, (str, bytes))
        or not frames_raw
    ):
        raise ValueError("observation frames must be a non-empty sequence")
    frames = [_core._grid_payload(frame) for frame in frames_raw]
    settled = _core._grid_payload(getattr(obs, "frame"))
    if frames[-1] != settled:
        raise ValueError("observation.frame must equal the final retained frame")
    return frames


def observation_digest(obs):
    """Exact identity digest including the full ordered animation-frame sequence."""
    settled = _core._observation_payload(obs)
    return _core._digest({
        "schema": OBSERVATION_IDENTITY_POLICY,
        "frames": _ordered_frames_payload(obs),
        "available_actions": settled["available_actions"],
        "state": settled["state"],
        "levels_completed": settled["levels_completed"],
        "win_levels": settled["win_levels"],
    })


def _strip_concrete_reachability(hypothesis):
    return _replace(
        hypothesis,
        progress=0,
        terminal="NOT_FINISHED",
        novelty_bps=0,
        successor_observation_digest=None,
        successor_observation=None,
    )


class SageEvidenceAdapter(_BaseSageEvidenceAdapter):
    """SAGE adapter with temporal exact identity and unanimous reachability authority."""

    def __init__(self, model, observation, *, candidate_factory=None) -> None:
        # Rebuild the predecessor evidence index with the hardened observation
        # identity while retaining the old core's scene/effect/action semantics.
        self.model = model
        self.observation = observation
        self._candidate_factory = candidate_factory
        transitions = getattr(model, "transitions", None)
        if not isinstance(transitions, list):
            raise ValueError("SAGE model must expose transitions list")
        self._observations = {observation_digest(observation): observation}
        rows = []
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
                "scene": _core._scene_key(before),
                "action": _core._action_key(action),
                "action_name": _core._action_name(action),
                "effect": effect_digest,
                "changed": _core._exact_int(getattr(effect, "changed_count", 0), "changed_count"),
                "progress": _core._exact_int(max(0, getattr(effect, "level_delta", 0)), "level_delta"),
                "terminal": str(getattr(effect, "terminal", "NOT_FINISHED")),
            })
        self._rows = tuple(sorted(rows, key=lambda row: _core._canonical_bytes(row)))
        evidence_digest = _core._digest({
            "schema": "sage-evidence/v2",
            "observation_identity": OBSERVATION_IDENTITY_POLICY,
            "rows": list(self._rows),
        })
        # Receipts bind evidence *and* both authority policies used to interpret it.
        self._model_digest = _core._digest({
            "schema": "sage-evidence-policy/v4",
            "evidence_digest": evidence_digest,
            "observation_identity": OBSERVATION_IDENTITY_POLICY,
            "reachability_policy": REACHABILITY_POLICY,
        })

    def _state_from_observation(self, obs, *, cumulative_progress):
        payload = _core._observation_payload(obs)
        digest = observation_digest(obs)
        return _core.SymbolicState(
            digest=digest,
            available_actions=tuple(payload["available_actions"]),
            terminal=payload["state"],
            cumulative_progress=cumulative_progress,
            observation_digest=digest,
            observation=obs,
        )

    def _evidence_rows(self, obs, action):
        before = observation_digest(obs)
        key = _core._action_key(action)
        name = _core._action_name(action)
        exact = tuple(row for row in self._rows if row["before"] == before and row["action"] == key)
        if exact:
            return "EXACT", exact
        scene = _core._scene_key(obs)
        local = tuple(row for row in self._rows if row["scene"] == scene and row["action_name"] == name)
        if local:
            return "SCENE", local
        global_rows = tuple(row for row in self._rows if row["action_name"] == name)
        if global_rows:
            return "GLOBAL", global_rows
        return "UNOBSERVED", ()

    def _resolved_observation(self, state):
        obs = state.observation
        if obs is None:
            obs = self._observations.get(state.observation_digest or "")
        return obs

    def hypotheses(self, state):
        if state.terminal != "NOT_FINISHED":
            return ()
        obs = self._resolved_observation(state)
        if obs is None:
            # An abstract effect state is an evidence boundary, not a license to
            # reuse the predecessor action space and invent a deeper future.
            return ()

        if getattr(obs, "state", "NOT_FINISHED") != "NOT_FINISHED":
            return ()
        hypotheses = super().hypotheses(state)
        hardened = []
        for hypothesis in hypotheses:
            strip = hypothesis.evidence_scope in {"SCENE", "GLOBAL"}
            if hypothesis.evidence_scope == "EXACT":
                scope, rows = self._evidence_rows(obs, hypothesis.action)
                if scope != "EXACT":
                    raise RuntimeError("internal error: exact hypothesis lost exact evidence rows")
                concrete_outcomes = {
                    (row["after"], row["progress"], row["terminal"])
                    for row in rows
                }
                # Modal agreement is useful scoring evidence but not reachability
                # authority. Every exact matching observation must agree before
                # a concrete successor/progress/terminal can enter the tree.
                strip = len(concrete_outcomes) != 1
            if strip:
                hypothesis = _strip_concrete_reachability(hypothesis)
            hardened.append(hypothesis)
        return tuple(hardened)

    def simulate(self, state, hypothesis):
        successor = super().simulate(state, hypothesis)
        if successor.observation is not None:
            return successor
        # Keep unresolved states explicitly terminal with respect to lookahead:
        # no future action space is asserted without concrete observation bytes.
        progress = successor.cumulative_progress
        digest = _core._digest({
            "schema": "sage-abstract-state/v3",
            "parent": state.digest,
            "action": hypothesis.action_key,
            "effect": hypothesis.effect_digest,
            "terminal": successor.terminal,
            "progress": progress,
            "available_actions": [],
            "observation_identity": OBSERVATION_IDENTITY_POLICY,
            "reachability_policy": REACHABILITY_POLICY,
        })
        return _core.SymbolicState(
            digest=digest,
            available_actions=(),
            terminal=successor.terminal,
            cumulative_progress=progress,
            observation_digest=None,
            observation=None,
        )


def _policy_receipt_from_core(receipt):
    unsealed = {key: receipt[key] for key in receipt if key != "receipt_sha256"}
    unsealed["schema"] = PLANNER_SCHEMA
    unsealed["planner_version"] = PLANNER_VERSION
    return _core._seal_receipt(unsealed)


class _ActiveStateAdapter:
    """Apply the same terminal boundary to SAGE and generic planner adapters."""

    def __init__(self, adapter):
        self._adapter = adapter
        self._root = adapter.root_state()
        if self._root.terminal != "NOT_FINISHED":
            raise ValueError("planner requires a NOT_FINISHED root state")

    @property
    def model_digest(self):
        return self._adapter.model_digest

    def root_state(self):
        return self._root

    def hypotheses(self, state):
        if state.terminal != "NOT_FINISHED":
            return ()
        return self._adapter.hypotheses(state)

    def simulate(self, state, hypothesis):
        if state.terminal != "NOT_FINISHED":
            raise ValueError("cannot simulate from a terminal or inactive state")
        return self._adapter.simulate(state, hypothesis)


def plan(
    adapter,
    *,
    actions_left,
    budget=_core.PlannerBudget(),
    weights=_core.ScoreWeights(),
):
    """Run bounded active-state lookahead and emit a v4 policy-bound receipt."""
    decision = _core.plan(
        _ActiveStateAdapter(adapter),
        actions_left=actions_left,
        budget=budget,
        weights=weights,
    )
    receipt = _policy_receipt_from_core(decision.receipt)
    return _core.PlanDecision(
        decision.first_action,
        decision.selected_prefix,
        decision.simulated_nodes,
        receipt,
    )


def verify_receipt(
    adapter,
    receipt,
    *,
    actions_left,
    budget=_core.PlannerBudget(),
    weights=_core.ScoreWeights(),
):
    """Recompute a v4 receipt and reject tamper, drift or older semantic replay."""
    if not isinstance(receipt, dict) or frozenset(receipt) != _core.RECEIPT_KEYS:
        raise _core.ReceiptVerificationError("receipt field set mismatch")
    supplied_digest = receipt.get("receipt_sha256")
    if not isinstance(supplied_digest, str) or len(supplied_digest) != 64:
        raise _core.ReceiptVerificationError("receipt digest malformed")
    unsealed = {key: receipt[key] for key in receipt if key != "receipt_sha256"}
    expected_digest = _core.sha256(_core._canonical_bytes(unsealed)).hexdigest()
    if supplied_digest != expected_digest:
        raise _core.ReceiptVerificationError("receipt digest mismatch")
    if receipt.get("schema") != PLANNER_SCHEMA or receipt.get("planner_version") != PLANNER_VERSION:
        raise _core.ReceiptVerificationError("receipt schema/version mismatch")
    recomputed = plan(
        adapter,
        actions_left=actions_left,
        budget=budget,
        weights=weights,
    ).receipt
    if _core._canonical_bytes(recomputed) != _core._canonical_bytes(receipt):
        raise _core.ReceiptVerificationError(
            "receipt no longer matches state/model/budget/policy"
        )
    return "VERIFIED_OFFLINE"
