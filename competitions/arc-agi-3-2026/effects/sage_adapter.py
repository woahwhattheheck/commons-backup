"""Thin adapter from the landed SAGE Transition contract to the visual factorizer."""
from __future__ import annotations

from factorizer import ActionEffect, ActionSequence, factor_action


def sequence_from_transition(transition: object) -> ActionSequence:
    before = getattr(getattr(transition, "before"), "frame")
    after = getattr(transition, "after")
    frames = getattr(after, "frames")
    action = getattr(transition, "action")
    key = getattr(action, "key")
    return ActionSequence(action_key=key, before=before, frames=tuple(frames))


def factor_transition(transition: object) -> ActionEffect:
    """Factor one exact SAGE Transition without mutating its WorldModel or policy."""
    return factor_action(sequence_from_transition(transition))
