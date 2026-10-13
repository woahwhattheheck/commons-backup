# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json

LEGACY_SPATIAL = b'''\
class SpatialTempo:
    def __init__(self, mechanics, pathing=True, tempo=True):
        self.pathing = pathing
        self.tempo = tempo
    def _continue_weed(self, obs, selected, controller, end):
        return False
    def transform(self, obs, selected, controller):
        end = 24
        if self._continue_weed(obs, selected, controller, end):
            return selected
        if not self.pathing and not self.tempo:
            return selected
        return selected
'''

LEGACY_RUNTIME = b'''\
from dataclasses import dataclass
@dataclass(frozen=True)
class Features:
    spatial_pathing: bool = False
    spatial_tempo: bool = False
class TitanAgent:
    def make(self):
        f = self.features
        return SpatialTempo(m, pathing=f.spatial_pathing, tempo=f.spatial_tempo)
'''

LEGACY_CONFIG = b'{"spatial_pathing": false, "spatial_tempo": false}\n'

FIXED_SPATIAL = b'''\
class SpatialTempo:
    def __init__(self, mechanics, pathing=True, tempo=True, weed_continuation=False):
        self.pathing = pathing
        self.tempo = tempo
        self.weed_continuation = weed_continuation
    def _continue_weed(self, obs, selected, controller, end):
        return False
    def transform(self, obs, selected, controller):
        end = 24
        if self.weed_continuation and self._continue_weed(obs, selected, controller, end):
            return selected
        if not self.pathing and not self.tempo:
            return selected
        return selected
'''

CONSTANT_STORE_SPATIAL = b'''\
class SpatialTempo:
    def __init__(self, mechanics, weed_continuation=False):
        self.weed_continuation = False
    def _continue_weed(self, obs, selected, controller, end):
        return False
    def transform(self, obs, selected, controller):
        if self.weed_continuation and self._continue_weed(obs, selected, controller, 24):
            return selected
        return selected
'''

EARLY_RETURN_FIXED_SPATIAL = b'''\
class SpatialTempo:
    def __init__(self, mechanics, pathing=True, tempo=True, weed_continuation=False):
        self.pathing = pathing
        self.tempo = tempo
        self.weed_continuation = weed_continuation
    def _continue_weed(self, obs, selected, controller, end):
        return False
    def transform(self, obs, selected, controller):
        if not self.weed_continuation:
            return selected
        if self._continue_weed(obs, selected, controller, 24):
            return selected
        return selected
'''

FIXED_RUNTIME = b'''\
from dataclasses import dataclass
@dataclass(frozen=True)
class Features:
    spatial_pathing: bool = False
    spatial_tempo: bool = False
    weed_continuation: bool = False
class TitanAgent:
    def make(self):
        f = self.features
        return SpatialTempo(m, pathing=f.spatial_pathing, tempo=f.spatial_tempo,
                            weed_continuation=f.weed_continuation)
'''

FIXED_ENTRYPOINT = b'''\
import json
def _new_instance(root, feature_data):
    from titan_runtime import Features
    return Features(**feature_data)
def agent(observation, configuration=None):
    root = ROOT
    feature_data = json.loads((root / "TITAN-CONFIG.json").read_text())
    return _new_instance(root, feature_data)
'''

NO_EXPANSION_ENTRYPOINT = FIXED_ENTRYPOINT.replace(
    b"Features(**feature_data)", b"Features()"
)
NO_LOAD_ENTRYPOINT = FIXED_ENTRYPOINT.replace(
    b'feature_data = json.loads((root / "TITAN-CONFIG.json").read_text())',
    b"feature_data = {}",
)
NO_FORWARD_ENTRYPOINT = FIXED_ENTRYPOINT.replace(
    b"return _new_instance(root, feature_data)", b"return _new_instance(root, {})"
)

COUPLED_SPATIAL = b'''\
class SpatialTempo:
    def __init__(self, mechanics, pathing=True, tempo=True):
        self.pathing = pathing
        self.tempo = tempo
    def _continue_weed(self, obs, selected, controller, end):
        return False
    def transform(self, obs, selected, controller):
        if (self.pathing or self.tempo) and self._continue_weed(obs, selected, controller, 24):
            return selected
        return selected
'''

UNGUARDED_WITH_BIT_SPATIAL = b'''\
class SpatialTempo:
    def __init__(self, mechanics, pathing=True, tempo=True, weed_continuation=False):
        self.pathing = pathing
        self.tempo = tempo
        self.weed_continuation = weed_continuation
    def _continue_weed(self, obs, selected, controller, end):
        return False
    def transform(self, obs, selected, controller):
        if self._continue_weed(obs, selected, controller, 24):
            return selected
        return selected
'''

OR_GUARD_SPATIAL = b'''\
class SpatialTempo:
    def __init__(self, mechanics, weed_continuation=False):
        self.weed_continuation = weed_continuation
    def _continue_weed(self, obs, selected, controller, end):
        return False
    def transform(self, obs, selected, controller):
        if self.weed_continuation or self._continue_weed(obs, selected, controller, 24):
            return selected
        return selected
'''

NO_WEED_SPATIAL = b'''\
class SpatialTempo:
    def __init__(self, mechanics):
        self.mechanics = mechanics
    def transform(self, obs, selected, controller):
        return selected
'''


def config(value: bool) -> bytes:
    return json.dumps({"weed_continuation": value}).encode() + b"\n"

REASSIGNED_ENTRYPOINT = FIXED_ENTRYPOINT.replace(
    b"return _new_instance(root, feature_data)",
    b"feature_data = {}\n    return _new_instance(root, feature_data)",
)
MUTATED_ENTRYPOINT = FIXED_ENTRYPOINT.replace(
    b"return _new_instance(root, feature_data)",
    b"feature_data.update({'weed_continuation': True})\n    return _new_instance(root, feature_data)",
)
MUTATED_NEW_INSTANCE_ENTRYPOINT = FIXED_ENTRYPOINT.replace(
    b"from titan_runtime import Features\n    return Features(**feature_data)",
    b"from titan_runtime import Features\n    feature_data.pop('weed_continuation', None)\n    return Features(**feature_data)",
)
FAKE_LOADS_ENTRYPOINT = FIXED_ENTRYPOINT.replace(
    b"import json\n", b"class Fake:\n    loads = staticmethod(lambda value: {})\njson = Fake()\n"
)
