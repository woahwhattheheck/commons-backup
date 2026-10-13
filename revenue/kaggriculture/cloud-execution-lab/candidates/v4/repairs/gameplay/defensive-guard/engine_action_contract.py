# SPDX-License-Identifier: Apache-2.0
"""Offline, source-pinned full-interpreter oracle for defensive-action gates.

This is validation tooling, NOT the missing defensive-guard donor or a runtime
sanitizer. No source is downloaded, no submitted action is rewritten, and no
feature is enabled. Supply the existing reference engine directory and loader.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

ENGINE_REF = "28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c"
PINS = {
    "kaggriculture.py": "bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e",
    "kaggriculture.json": "a82c89c1a2315b93f39775d8e025471a01b738647c9772658368ee6b1b6f4867",
    "utils.py": "537b627b11784d424147ef57ebb0369b039bf83c9f891e81f10486b1f552334b",
    "loader.py": "cd113a94ae99b03492502e425bdcf09c3db17a2aa2a8fd866f0d78caec9e311e",
}
ENGINE_BLOB = "3c202c7ee921da239356789e266b694635103fc4"


def file_identity(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
            "git_blob": hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()}


def verify_inputs(engine_dir: Path, loader_path: Path) -> dict[str, Any]:
    """Authenticate every executable/input dependency BEFORE importing anything."""
    paths = {name: engine_dir / name for name in PINS if name != "loader.py"}
    paths["loader.py"] = loader_path
    identities = {}
    for name, path in paths.items():
        if not path.is_file():
            raise ValueError(f"missing offline dependency: {name}: {path}")
        identity = file_identity(path)
        if identity["sha256"] != PINS[name]:
            raise ValueError(f"source pin mismatch: {name}: {identity['sha256']}")
        identities[name] = identity
    return identities


def import_path(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f"cannot load source: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class EngineOracle:
    """Execute cloned fixture worlds through the complete pinned interpreter."""

    def __init__(self, engine_dir: str | Path, loader_path: str | Path):
        self.engine_dir = Path(engine_dir).resolve()
        self.loader_path = Path(loader_path).resolve()
        self.identities = verify_inputs(self.engine_dir, self.loader_path)
        self.loader = import_path("_bridge_pinned_loader", self.loader_path)
        self.engine = self.load_engine(self.engine_dir)
        self.initializations = 0
        self.transition_attempts = 0
        self.transitions_completed = 0
        self.transition_errors: dict[str, int] = {}

    def load_engine(self, directory: Path):
        # The existing loader installs upstream seed-helper modules. Restore the
        # caller's registry afterwards; the engine retains the actual helper.
        names = ("kaggle_environments", "kaggle_environments.utils")
        before = {name: sys.modules.get(name) for name in names}
        try:
            engine, _ = self.loader.get_engine(directory)
            return engine
        finally:
            for name, module in before.items():
                if module is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = module

    def world(self, *, cap: Any = 10, step: int = 0, seed: int = 2027):
        cfg = self.loader.Struct({key: value.get("default") if isinstance(value, dict) else value
                                  for key, value in self.engine.specification["configuration"].items()})
        cfg.update(seed=seed, weedSpawnChance=0, maxMarketOrdersPerTurn=cap)
        env = self.loader.Struct(configuration=cfg, done=False, info={})
        state = [self.loader.Struct(observation=self.loader.Struct(), action={},
                                    status="ACTIVE", reward=0) for _ in range(2)]
        self.engine.interpreter(state, env)
        self.initializations += 1
        for seat in (0, 1):
            obs = state[seat].observation
            obs.step = step
            obs.day, obs.hour = divmod(step, cfg.turnsPerDay)
            farm = obs.farms[seat]
            farm.update(money=10000.0, farmer=[4, 4], hands=[])
            obs.private["seeds"] = {crop: 0 for crop in self.engine.CROPS}
            obs.private["shed"] = {item: 0 for item in self.engine.PRODUCTS + list(self.engine.ANIMALS)}
            obs.private["inventories"] = [{}]
        return state, env

    @staticmethod
    def actors(world, seat: int, positions: list[tuple[int, int]]) -> None:
        if not positions:
            raise ValueError("fixture requires a main farmer")
        state, _ = world
        farm = state[seat].observation.farms[seat]
        farm["farmer"] = list(positions[0])
        farm["hands"] = [list(pos) for pos in positions[1:]]
        state[seat].observation.private["inventories"] = [{} for _ in positions]

    def run(self, world, seat: int, action: Any, rival_action: Any = None):
        """Clone input world/action; errors are intentionally exposed, not hidden."""
        if seat not in (0, 1):
            raise ValueError("seat must be 0 or 1")
        state, env = copy.deepcopy(world)
        state[seat].action = copy.deepcopy(action)
        state[1 - seat].action = copy.deepcopy({} if rival_action is None else rival_action)
        self.transition_attempts += 1
        try:
            self.engine.interpreter(state, env)
        except Exception as error:
            name = type(error).__name__
            self.transition_errors[name] = self.transition_errors.get(name, 0) + 1
            raise
        self.transitions_completed += 1
        return state, env

    @staticmethod
    def snapshot(world) -> str:
        """All endogenous state, not only bank; exclude the submitted action itself."""
        state, env = world
        return json.dumps({"state": [{k: v for k, v in row.items() if k != "action"} for row in state],
                           "env": env}, sort_keys=True, separators=(",", ":"), allow_nan=False)

    def counts(self) -> dict[str, Any]:
        return {"initializations": self.initializations, "transition_attempts": self.transition_attempts,
                "transitions_completed": self.transitions_completed,
                "expected_or_unexpected_errors": dict(sorted(self.transition_errors.items()))}
