#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
import copy
import importlib.util
import sys
import types
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from e7_post_tick_evening_flush import (  # noqa: E402
    PostTickEveningFlush,
    ROUTER_BLOB_SHA,
    ROUTER_PATH,
    _git_blob_sha,
    install,
    r04,
)


class Parent:
    def __init__(self, actions=None):
        self.actions = actions or {}

    def __call__(self, observation, configuration=None):
        action = self.actions.get(
            observation["step"],
            {"farmer": ["PASS"], "hands": [], "market": []},
        )
        return copy.deepcopy(action)


def config(**patch):
    value = {
        "turnsPerDay": 24,
        "shedCapacity": 100,
        "maxMarketOrdersPerTurn": 10,
        "townCenterSellInterval": 24,
    }
    value.update(patch)
    return value


def obs(step, milk_price=10):
    return {
        "step": step,
        "player": 0,
        "farms": [{
            "tiles": [[None for _ in range(10)] for _ in range(10)],
            "farmer": [0, 0],
            "hands": [],
        }],
        "private": {
            "shed": {"MILK": 5},
            "inventories": [{}],
        },
        "market": {"prices": {"MILK": milk_price}},
        "town": {"unlocked_shops": []},
    }


class E7FailClosedTests(unittest.TestCase):
    def test_only_literal_true_activates(self):
        for enabled in (False, 0, 1, "true", [True], object()):
            with self.subTest(enabled=repr(enabled)):
                parent = Parent()
                self.assertIs(parent, install(parent, enabled=enabled))

        parent = Parent()
        self.assertIsInstance(install(parent, enabled=True), PostTickEveningFlush)

    def test_truthy_poison_never_validates_parent(self):
        for enabled in (1, "enabled", {"enabled": True}):
            with self.subTest(enabled=repr(enabled)):
                self.assertIsNone(install(None, enabled=enabled))
        with self.assertRaises(TypeError):
            install(None, enabled=True)

    def test_zero_quantity_sell_is_release_barrier(self):
        parent = Parent({
            49: {
                "farmer": ["PASS"],
                "hands": [],
                "market": [["SELL", "MILK", 0]],
            }
        })
        agent = install(parent, enabled=True)

        self.assertEqual([], agent(obs(47, milk_price=10), config())["market"])
        self.assertEqual([], agent(obs(48, milk_price=11), config())["market"])

        released = agent(obs(49, milk_price=12), config())
        self.assertEqual([["SELL", "MILK", 0]], released["market"])
        self.assertEqual(1, agent.telemetry["release_malformed_sell"])
        self.assertEqual(0, agent.telemetry["released_units"])

    def test_router_binding_is_canonical_v4_donor(self):
        self.assertEqual(ROUTER_PATH.name, "r04_full_router.py")
        self.assertEqual(Path(r04.__file__).resolve(), ROUTER_PATH.resolve())
        self.assertEqual(ROUTER_BLOB_SHA, _git_blob_sha(ROUTER_PATH))

    def test_ambient_r04_shadow_is_refused(self):
        canonical = sys.modules.get("r04_full_router")
        shadow = types.ModuleType("r04_full_router")
        shadow.__file__ = "/tmp/e7-shadow/r04_full_router.py"
        sys.modules["r04_full_router"] = shadow
        try:
            spec = importlib.util.spec_from_file_location(
                "_e7_shadow_probe", HERE / "e7_post_tick_evening_flush.py"
            )
            self.assertIsNotNone(spec)
            self.assertIsNotNone(spec.loader)
            probe = importlib.util.module_from_spec(spec)
            with self.assertRaisesRegex(ImportError, "shadowed"):
                spec.loader.exec_module(probe)
        finally:
            if canonical is None:
                sys.modules.pop("r04_full_router", None)
            else:
                sys.modules["r04_full_router"] = canonical


if __name__ == "__main__":
    unittest.main()
