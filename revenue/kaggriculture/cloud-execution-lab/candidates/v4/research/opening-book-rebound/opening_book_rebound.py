#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Independent opening-book MELON/STRAWBERRY rebound experiment.

The historical opening-book bytes were not recovered.  This module therefore
*does not* claim to reproduce that donor.  It is a new bounded schedule consumer
of the already-landed PRICE-PATH ``SeedBudget`` admission primitive.

Important ownership boundary:
- SeedBudget alone owns seed funding, raw market slots, returned-action custody,
  observed fills, plant-site legality and next-callback application.
- This module only chooses an early-game target order/quota and records which
  proposal actually reached ``plant-proposed``.
- It never buys and plants on the same callback, never credits SELL proceeds,
  and never edits a returned action after the PRICESEED custody checkpoint.

Default behavior is disabled and this is research-only: no runtime/default,
archive, production or submission wiring is performed here.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping

HERE = Path(__file__).resolve().parent
SEED_BUDGET_PATH = HERE.parent / "price-path-seed-budget" / "seed_budget.py"
EXPECTED_SEED_BUDGET_BLOB = "7cbef20f942d78e9e2bea318c74dbe06ac2f0d13"
TARGETS = ("MELON", "STRAWBERRY")
DEFAULT_QUOTA = 2
OPENING_LAST_STEP = 71


class OpeningBookError(RuntimeError):
    pass


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def _load_seed_budget() -> ModuleType:
    data = SEED_BUDGET_PATH.read_bytes()
    actual = git_blob_sha(data)
    if actual != EXPECTED_SEED_BUDGET_BLOB:
        raise OpeningBookError(
            f"PRICESEED dependency drift: expected {EXPECTED_SEED_BUDGET_BLOB}, got {actual}"
        )
    spec = importlib.util.spec_from_file_location("opening_book_price_seed", SEED_BUDGET_PATH)
    if spec is None or spec.loader is None:
        raise OpeningBookError("cannot load PRICESEED dependency")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@dataclass(frozen=True)
class OpeningBookConfig:
    quota_per_target: int = DEFAULT_QUOTA
    last_step: int = OPENING_LAST_STEP
    budget_per_proposal: int = 200
    cash_reserve: int = 500

    def validate(self) -> None:
        for name, value, minimum in (
            ("quota_per_target", self.quota_per_target, 1),
            ("last_step", self.last_step, 0),
            ("budget_per_proposal", self.budget_per_proposal, 0),
            ("cash_reserve", self.cash_reserve, 0),
        ):
            if type(value) is not int or value < minimum:
                raise OpeningBookError(f"invalid {name}")


class OpeningBookRebound:
    """Two-stage MELON then STRAWBERRY schedule over the existing SeedBudget.

    Instances are intentionally per-agent/per-seat.  ``episode`` is an explicit
    external identity and changing it resets local quotas and SeedBudget state.
    A target quota advances only after PRICESEED returns ``plant-proposed``.
    """

    def __init__(self, config: OpeningBookConfig | None = None) -> None:
        self.config = config or OpeningBookConfig()
        self.config.validate()
        module = _load_seed_budget()
        self._budget = module.SeedBudget()
        self._episode: str | None = None
        self._planted = {target: 0 for target in TARGETS}
        self._pending_target: str | None = None
        self._committed_target: str | None = None

    @property
    def planted(self) -> dict[str, int]:
        return dict(self._planted)

    def reset(self, episode: str) -> None:
        if not isinstance(episode, str) or not episode:
            raise OpeningBookError("episode must be a non-empty string")
        self._episode = episode
        self._planted = {target: 0 for target in TARGETS}
        self._pending_target = None
        self._committed_target = None
        self._budget.reset()

    def _ensure_episode(self, episode: str) -> None:
        if not isinstance(episode, str) or not episode:
            raise OpeningBookError("episode must be a non-empty string")
        if self._episode != episode:
            self.reset(episode)

    def _target(self) -> str | None:
        for target in TARGETS:
            if self._planted[target] < self.config.quota_per_target:
                return target
        return None

    def prepare(
        self,
        action: Mapping[str, Any],
        obs: Mapping[str, Any],
        cfg: Mapping[str, Any],
        next_action: Mapping[str, Any],
        *,
        episode: str,
        route: str,
        enabled: bool = False,
    ) -> tuple[Mapping[str, Any], dict]:
        """Ask PRICESEED to fund the next authored WHEAT plant as MELON/STRAWBERRY."""
        self._ensure_episode(episode)
        self._pending_target = None
        if type(enabled) is not bool:
            return action, {"status": "invalid-enabled"}
        if not enabled:
            return action, {"status": "disabled"}
        step = obs.get("step") if isinstance(obs, Mapping) else None
        if type(step) is not int or step < 0 or step > self.config.last_step:
            return action, {"status": "outside-opening-window"}
        target = self._target()
        if target is None:
            return action, {"status": "quota-complete", "planted": self.planted}
        remaining = self.config.quota_per_target - self._planted[target]
        result, report = self._budget.prepare(
            action,
            obs,
            cfg,
            next_action,
            episode=episode,
            route=route,
            source="WHEAT",
            target=target,
            budget=self.config.budget_per_proposal,
            reserve=self.config.cash_reserve,
            max_plants=remaining,
            enabled=True,
        )
        report = dict(report)
        report["opening_target"] = target
        report["source_status"] = "independently_reauthored_not_historical_donor"
        if report.get("status") == "purchase-proposed":
            self._pending_target = target
        return result, report

    def record_returned(
        self,
        action: Mapping[str, Any],
        obs: Mapping[str, Any],
        cfg: Mapping[str, Any],
        *,
        episode: str,
        route: str,
    ) -> bool:
        self._ensure_episode(episode)
        target = self._pending_target
        self._pending_target = None
        accepted = self._budget.record_returned(
            action, obs, cfg, episode=episode, route=route
        )
        self._committed_target = target if accepted else None
        return bool(accepted)

    def apply(
        self,
        action: Mapping[str, Any],
        obs: Mapping[str, Any],
        cfg: Mapping[str, Any],
        *,
        episode: str,
        route: str,
    ) -> tuple[Mapping[str, Any], dict]:
        self._ensure_episode(episode)
        target = self._committed_target
        self._committed_target = None
        result, report = self._budget.apply(
            action, obs, cfg, episode=episode, route=route
        )
        report = dict(report)
        report["opening_target"] = target
        report["source_status"] = "independently_reauthored_not_historical_donor"
        if report.get("status") == "plant-proposed" and target in self._planted:
            slots = report.get("slots")
            if type(slots) is list and all(type(slot) is int for slot in slots):
                self._planted[target] = min(
                    self.config.quota_per_target,
                    self._planted[target] + len(slots),
                )
        report["planted"] = self.planted
        return result, report
