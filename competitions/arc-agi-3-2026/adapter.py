"""Adapter between SAGE's dependency-free contract and the official ARC-AGI toolkit.

No network action occurs on import.  `run_official_episode` requires a caller-created
environment and never loads API keys or opens a scorecard itself.
"""
from __future__ import annotations

from typing import Any, Iterable, Sequence

from sage import ActionToken, Observation, SAGEAgent, validate_grid


def _as_grid(frame: Any):
    # Pydantic/toolkit frame objects are intentionally handled structurally.
    if hasattr(frame, "grid"):
        frame = frame.grid
    if hasattr(frame, "data") and not isinstance(frame, (list, tuple)):
        frame = frame.data
    return validate_grid(frame)


def normalize_frame_data(raw: Any, *, action_names: Iterable[str] | None = None) -> Observation:
    """Normalize FrameDataRaw-like objects while retaining every returned animation frame."""
    if raw is None:
        raise ValueError("ARC observation is None")
    frames_raw = getattr(raw, "frame", None)
    if frames_raw is None:
        frames_raw = getattr(raw, "frames", None)
    if frames_raw is None:
        raise ValueError("ARC observation has no frame(s)")

    # The ARC API returns an array of frames. Some wrappers expose one settled grid only.
    if isinstance(frames_raw, Sequence) and frames_raw and isinstance(frames_raw[0], Sequence):
        first = frames_raw[0]
        # Distinguish Grid[row][cell] from Frames[frame][row][cell].
        if first and isinstance(first[0], int):
            frames = (_as_grid(frames_raw),)
        else:
            frames = tuple(_as_grid(f) for f in frames_raw)
    else:
        frames = (_as_grid(frames_raw),)

    if action_names is None:
        available = getattr(raw, "available_actions", None)
        if available is None:
            raise ValueError("available actions missing")
        names: list[str] = []
        for item in available:
            name = getattr(item, "name", None) or str(item)
            if "." in name:
                name = name.rsplit(".", 1)[-1]
            names.append(name)
        action_names = names

    state = getattr(raw, "state", "NOT_FINISHED")
    state = getattr(state, "name", state)
    return Observation(
        frames=frames,
        available_actions=tuple(action_names),
        state=str(state),
        levels_completed=int(getattr(raw, "levels_completed", 0)),
        win_levels=int(getattr(raw, "win_levels", 0)),
    )


def toolkit_action(action: ActionToken):
    """Translate an ActionToken to `(GameAction, data)` only when arcengine is installed."""
    try:
        from arcengine import GameAction  # type: ignore
    except ImportError as exc:  # pragma: no cover - official environment path
        raise RuntimeError("arcengine is required for official environment execution") from exc
    try:
        enum_action = getattr(GameAction, action.name)
    except AttributeError as exc:
        raise ValueError(f"unknown toolkit action {action.name}") from exc
    data = None if action.x is None else {"x": action.x, "y": action.y}
    return enum_action, data


def run_official_episode(env: Any, agent: SAGEAgent, *, max_actions: int = 80) -> tuple[Observation, ...]:
    """Run against an already-authorized official environment.

    The caller owns scorecard/API-key/account authority.  This function only invokes
    reset/step on the supplied environment and cannot create credentials or submit Kaggle.
    """
    if type(max_actions) is not int or not 1 <= max_actions <= 10_000:
        raise ValueError("max_actions outside safe bound")
    raw = env.reset()
    # Official wrapper action_space is authoritative and can change every step.
    names = tuple(a.name for a in env.action_space)
    obs = normalize_frame_data(raw, action_names=names)
    history = [obs]
    for step in range(max_actions):
        if obs.state in {"WIN", "GAME_OVER"}:
            break
        decision = agent.decide(obs, actions_left=max_actions - step)
        enum_action, data = toolkit_action(decision.action)
        raw_next = env.step(enum_action, data=data, reasoning={"sage_mode": decision.mode})
        names = tuple(a.name for a in env.action_space)
        after = normalize_frame_data(raw_next, action_names=names)
        agent.learn(obs, decision, after)
        history.append(after)
        obs = after
    return tuple(history)
