# SPDX-License-Identifier: Apache-2.0
"""Bind the P02 candidate to its exact-slot and retry guard."""
from __future__ import annotations

from land_unlock_runtime_strict import LandUnlockOverlay
import p02_candidate_base as _base

# The base module is an exact copy of the first published candidate. Its mixin
# resolves this global when constructing each match-scoped instance.
_base.LandUnlockOverlay = LandUnlockOverlay


def agent(observation, configuration=None):
    return _base.agent(observation, configuration)
