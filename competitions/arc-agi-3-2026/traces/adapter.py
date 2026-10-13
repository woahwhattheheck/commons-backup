"""Structural adapters between landed SAGE objects and the trace-custody contract.

This module imports no provider SDK and performs no environment actions.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core import EpisodeRecorder, TraceError, decode_frame_record, verify_manifest


@dataclass(frozen=True)
class ReplayTransition:
    action_key: str
    before: tuple[tuple[int, ...], ...]
    frames: tuple[tuple[tuple[int, ...], ...], ...]
    evidence_class: str


def append_observation_object(
    recorder: EpisodeRecorder,
    observation: object,
    *,
    evidence_class: str,
    source_ref: str,
) -> None:
    frames = getattr(observation, "frames")
    available_actions = getattr(observation, "available_actions")
    recorder.append_observation(
        frames,
        available_actions,
        state=getattr(observation, "state", "NOT_FINISHED"),
        levels_completed=getattr(observation, "levels_completed", 0),
        win_levels=getattr(observation, "win_levels", 0),
        evidence_class=evidence_class,
        source_ref=source_ref,
    )


def append_transition_object(
    recorder: EpisodeRecorder,
    transition: object,
    *,
    before_evidence_class: str,
    before_source_ref: str,
    after_evidence_class: str,
    after_source_ref: str,
) -> None:
    before = getattr(transition, "before")
    action = getattr(transition, "action")
    after = getattr(transition, "after")
    if not recorder.events:
        append_observation_object(
            recorder,
            before,
            evidence_class=before_evidence_class,
            source_ref=before_source_ref,
        )
    else:
        last_frames = recorder.events[-1]["payload"]["frames"]
        before_frames = [tuple(tuple(row) for row in frame) for frame in getattr(before, "frames")]
        recorded_frames = [decode_frame_record(frame) for frame in last_frames]
        if recorded_frames != before_frames:
            raise TraceError("transition before-state does not equal recorded tail")
    recorder.append_action(
        getattr(action, "name"),
        x=getattr(action, "x", None),
        y=getattr(action, "y", None),
    )
    append_observation_object(
        recorder,
        after,
        evidence_class=after_evidence_class,
        source_ref=after_source_ref,
    )


def replay_transition(manifest: dict[str, Any], action_index: int) -> ReplayTransition:
    verify_manifest(manifest)
    if type(action_index) is not int or action_index < 0 or action_index >= manifest["action_count"]:
        raise TraceError("action index outside manifest")
    event_index = action_index * 2 + 1
    before_event = manifest["events"][event_index - 1]
    action_event = manifest["events"][event_index]
    after_event = manifest["events"][event_index + 1]
    before = decode_frame_record(before_event["payload"]["frames"][-1])
    frames = tuple(decode_frame_record(item) for item in after_event["payload"]["frames"])
    action = action_event["payload"]["action"]
    key = action["name"] if action["x"] is None else f"{action['name']}@{action['x']},{action['y']}"
    return ReplayTransition(
        action_key=key,
        before=before,
        frames=frames,
        evidence_class=after_event["payload"]["evidence_class"],
    )


def effect_adapter_payload(manifest: dict[str, Any], action_index: int) -> dict[str, Any]:
    """Return the exact neutral shape consumed by effects.ActionSequence.

    No effect, reachability, policy, provider, or score claim is made here.
    """
    transition = replay_transition(manifest, action_index)
    return {
        "action_key": transition.action_key,
        "before": transition.before,
        "frames": transition.frames,
    }
