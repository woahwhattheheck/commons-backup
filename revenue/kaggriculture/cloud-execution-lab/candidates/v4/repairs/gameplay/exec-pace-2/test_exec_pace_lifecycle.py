# SPDX-License-Identifier: Apache-2.0
"""Focused EXEC-PACE-2 lifecycle/activation regressions for the current composer."""
from __future__ import annotations

from copy import deepcopy
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import textwrap
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("execpace_composer", HERE / "compose_current_runtime.py")
composer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(composer)


class FakeFrozenSelected:
    pass


class FakeTrendState:
    """Tiny contiguous-step model used to test integration lifecycle only."""

    created = 0

    def __init__(self):
        type(self).created += 1
        self.serial = type(self).created
        self.steps = []
        self.last_step = -1
        self.last_player = None
        self.last_prices = None

    def note_prices(self, obs):
        step = obs.get("step") if isinstance(obs, dict) else None
        player = obs.get("player") if isinstance(obs, dict) else None
        market = obs.get("market") if isinstance(obs, dict) else None
        prices = market.get("prices") if isinstance(market, dict) else None
        if type(step) is not int or type(player) is not int or not isinstance(prices, dict):
            self.steps = []
            self.last_step = -1
            self.last_player = None
            self.last_prices = None
            return False
        values = tuple(sorted(prices.items()))
        if step == self.last_step and player == self.last_player:
            if values == self.last_prices:
                return True
            self.steps = []
        elif self.last_step != -1 and (player != self.last_player or step != self.last_step + 1):
            self.steps = []
        self.steps.append(step)
        self.steps = self.steps[-25:]
        self.last_step = step
        self.last_player = player
        self.last_prices = values
        return True

    @property
    def warm(self):
        return len(self.steps) == 25


class FakePace:
    PriceTrendState = FakeTrendState
    apply_candidate = staticmethod(lambda *args: args)


def price_obs(step, price=None, player=0):
    return {
        "step": step,
        "player": player,
        "market": {"prices": {"WOOL": 100 + step if price is None else price}},
    }


def consumer_probe():
    fragment = textwrap.dedent(composer.CONSUMER_INSERT)
    namespace = {"HERE": Path("/tmp")}
    exec(compile(
        "def run(self, f, FrozenSelected, load):\n" + textwrap.indent(fragment, "    "),
        "exec_pace_consumer_fragment.py", "exec"), namespace)
    return namespace["run"]


def fallback_probe():
    namespace = {"deepcopy": deepcopy}
    exec(compile(
        "class Probe:\n" + textwrap.indent(composer.FALLBACK_OBSERVER_INSERT, "    "),
        "exec_pace_fallback_fragment.py", "exec"), namespace)
    return namespace["Probe"]._remember_seller_fallback


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        FakeTrendState.created = 0
        self.run = consumer_probe()
        self.remember = fallback_probe()
        self.loads = []

    def load(self, name, path):
        self.loads.append((name, str(path)))
        return FakePace

    def enabled_holder(self):
        return SimpleNamespace(
            features=SimpleNamespace(consumer="frozen", exec_pace=True),
            _exec_pace_fallback_observations=[],
        )

    def test_only_literal_true_activates(self):
        poisons = (False, "false", "true", 0, 1, 0.0, 1.0, None, [], [True], {}, {"enabled": True})
        for value in poisons:
            with self.subTest(value=repr(value)):
                holder = SimpleNamespace()
                self.run(holder, SimpleNamespace(exec_pace=value), FakeFrozenSelected, self.load)
                self.assertFalse(hasattr(holder.consumer, "exec_pace_state"))
                self.assertFalse(hasattr(holder.consumer, "exec_pace_apply"))
                self.assertFalse(hasattr(holder, "_exec_pace_state"))
        self.assertEqual(self.loads, [])
        self.assertEqual(FakeTrendState.created, 0)

    def test_literal_true_attaches_gate(self):
        holder = SimpleNamespace()
        self.run(holder, SimpleNamespace(exec_pace=True), FakeFrozenSelected, self.load)
        self.assertIs(holder.consumer.exec_pace_apply, FakePace.apply_candidate)
        self.assertIs(holder.consumer.exec_pace_state, holder._exec_pace_state)
        self.assertEqual(holder._exec_pace_fallback_observations, [])
        self.assertEqual(FakeTrendState.created, 1)
        self.assertEqual(len(self.loads), 1)

    def test_state_survives_consumer_reconstruction(self):
        holder = SimpleNamespace()
        enabled = SimpleNamespace(exec_pace=True)
        self.run(holder, enabled, FakeFrozenSelected, self.load)
        first_consumer = holder.consumer
        first_state = first_consumer.exec_pace_state
        first_state.marker = "warm-history"
        self.run(holder, enabled, FakeFrozenSelected, self.load)
        self.assertIsNot(holder.consumer, first_consumer)
        self.assertIs(holder.consumer.exec_pace_state, first_state)
        self.assertEqual(holder.consumer.exec_pace_state.marker, "warm-history")
        self.assertEqual(FakeTrendState.created, 1)
        self.assertEqual(len(self.loads), 2)

    def test_disabled_reconstruction_does_not_attach_stale_state(self):
        holder = SimpleNamespace()
        self.run(holder, SimpleNamespace(exec_pace=True), FakeFrozenSelected, self.load)
        retained = holder._exec_pace_state
        self.run(holder, SimpleNamespace(exec_pace=False), FakeFrozenSelected, self.load)
        self.assertFalse(hasattr(holder.consumer, "exec_pace_state"))
        self.assertIs(holder._exec_pace_state, retained)
        self.run(holder, SimpleNamespace(exec_pace=True), FakeFrozenSelected, self.load)
        self.assertIs(holder.consumer.exec_pace_state, retained)
        self.assertEqual(FakeTrendState.created, 1)

    def test_fallback_capture_requires_literal_true(self):
        poisons = (False, "false", 1, 1.0, None, [True], {"enabled": True})
        for value in poisons:
            with self.subTest(value=repr(value)):
                holder = SimpleNamespace(
                    features=SimpleNamespace(consumer="frozen", exec_pace=value),
                    _exec_pace_fallback_observations=[],
                    _seller_fallback_observations=[],
                )
                self.remember(holder, price_obs(25))
                self.assertEqual(holder._exec_pace_fallback_observations, [])
        holder = self.enabled_holder()
        holder._seller_fallback_observations = []
        source = price_obs(25)
        self.remember(holder, source)
        self.assertEqual(holder._exec_pace_fallback_observations, [source])
        source["market"]["prices"]["WOOL"] = -999
        self.assertEqual(holder._exec_pace_fallback_observations[0]["market"]["prices"]["WOOL"], 125)

    def test_pretansform_timeout_preserves_warm_window(self):
        holder = self.enabled_holder()
        state = FakeTrendState()
        holder._exec_pace_state = state
        for step in range(25):
            state.note_prices(price_obs(step))
        self.assertTrue(state.warm)

        # Step 25 times out before FrozenSelected.transform can call note_prices().
        self.remember(holder, price_obs(25))
        self.assertEqual(state.last_step, 24)
        self.run(holder, SimpleNamespace(exec_pace=True), FakeFrozenSelected, self.load)
        self.assertEqual(state.last_step, 25)
        self.assertTrue(state.warm)
        self.assertEqual(holder._exec_pace_fallback_observations, [])

        # The next ordinary callback stays contiguous instead of resetting warmup.
        state.note_prices(price_obs(26))
        self.assertEqual(state.last_step, 26)
        self.assertTrue(state.warm)

    def test_post_note_timeout_replay_is_idempotent(self):
        holder = self.enabled_holder()
        state = FakeTrendState()
        holder._exec_pace_state = state
        for step in range(26):
            state.note_prices(price_obs(step))
        before = list(state.steps)

        # Transform already recorded step 25, but a later deadline still queues it.
        self.remember(holder, price_obs(25))
        self.run(holder, SimpleNamespace(exec_pace=True), FakeFrozenSelected, self.load)
        self.assertEqual(state.steps, before)
        self.assertEqual(state.last_step, 25)
        self.assertEqual(holder._exec_pace_fallback_observations, [])

        state.note_prices(price_obs(26))
        self.assertTrue(state.warm)
        self.assertEqual(state.last_step, 26)

    def test_conflicting_same_step_fallback_resets_fail_closed(self):
        holder = self.enabled_holder()
        state = FakeTrendState()
        holder._exec_pace_state = state
        for step in range(25):
            state.note_prices(price_obs(step))
        self.remember(holder, price_obs(25, 125))
        self.remember(holder, price_obs(25, 999))
        self.run(holder, SimpleNamespace(exec_pace=True), FakeFrozenSelected, self.load)
        self.assertEqual(state.last_step, 25)
        self.assertFalse(state.warm)
        self.assertEqual(state.steps, [25])
        self.assertEqual(holder._exec_pace_fallback_observations, [])

    def test_drained_fallbacks_are_not_replayed_on_later_reconstruction(self):
        holder = self.enabled_holder()
        state = FakeTrendState()
        holder._exec_pace_state = state
        for step in range(25):
            state.note_prices(price_obs(step))
        self.remember(holder, price_obs(25))
        self.run(holder, SimpleNamespace(exec_pace=True), FakeFrozenSelected, self.load)
        after_first = list(state.steps)
        self.run(holder, SimpleNamespace(exec_pace=True), FakeFrozenSelected, self.load)
        self.assertEqual(state.steps, after_first)
        self.assertEqual(state.last_step, 25)
        self.assertTrue(state.warm)

    def test_source_contract_is_literal_true_agent_owned_and_fallback_custodied(self):
        self.assertIn("if f.exec_pace is True:", composer.CONSUMER_INSERT)
        self.assertIn("getattr(self, '_exec_pace_state', None)", composer.CONSUMER_INSERT)
        self.assertIn("self._exec_pace_state = exec_pace_state", composer.CONSUMER_INSERT)
        self.assertIn("exec_pace_state.note_prices(exec_pace_obs)", composer.CONSUMER_INSERT)
        self.assertIn("self._exec_pace_fallback_observations = []", composer.CONSUMER_INSERT)
        self.assertIn("getattr(self.features, 'exec_pace', False) is True", composer.FALLBACK_OBSERVER_INSERT)
        self.assertNotIn("if f.exec_pace:\n", composer.CONSUMER_INSERT)


class ComposerShapeTests(unittest.TestCase):
    TITAN = (
        "from dataclasses import dataclass\n"
        "@dataclass(frozen=True)\nclass Features:\n"
        "    consumer: str = 'frozen'\n"
        "    terminal_route: bool = False\n"
        "    early_capital: bool = False\n"
        "    def __post_init__(self):\n"
        "        bool_fields = ('terminal_route', 'early_capital')\n"
        "        for name in bool_fields:\n"
        "            if type(getattr(self, name)) is not bool:\n"
        "                raise TypeError(f'{name} must be bool')\n"
        "        if self.consumer not in ('frozen', 'ordered', 'parent'):\n"
        "            raise ValueError('consumer must be frozen, ordered or parent')\n"
        "        if self.terminal_route and self.consumer != 'frozen':\n"
        "            raise ValueError('terminal_route is the tested frozen SELL composition')\n"
        "class X:\n"
        "    def __init__(self):\n"
        "        self._completed_seller_state = None\n"
        "        self._seller_fallback_observations = []\n"
        "        self.spatial = None\n"
        "    def _remember_seller_fallback(self, obs):\n"
        "        \"\"\"Queue one completed fallback observation for a later reconstruction.\"\"\"\n"
        "        if self.features.consumer != 'frozen':\n"
        "            return\n"
        "        step = int(obs['step'])\n"
        "    def f(self,f):\n"
        "        if True:\n"
        "            self.consumer = FrozenSelected()\n"
    )
    FROZEN = (
        "class FrozenSelected:\n"
        "    def transform(self,obs,config,base):\n"
        "        self.observe(obs)\n"
        "        farm,private=post_units(obs,base,config)\n"
        "        for item in items:\n"
        "            info['baseline_horizon_end']=horizon['baseline_end'];info['horizon_end']=item_end\n"
        "            self.diagnostics['evaluations'].append(info)\n"
        "            eligible,rank=seller_choice_rank(info)\n"
    )

    def test_composer_remains_default_off_and_compilable(self):
        titan, frozen = composer.compose_sources(self.TITAN, self.FROZEN)
        self.assertEqual(titan.count("exec_pace: bool = False"), 1)
        self.assertEqual(titan.count("bool_fields = (*bool_fields, 'exec_pace')"), 1)
        self.assertEqual(titan.count("exec_pace is the tested nonterminal frozen SELL composition"), 1)
        self.assertEqual(titan.count("if f.exec_pace is True:"), 1)
        self.assertEqual(titan.count("_exec_pace_fallback_observations = []"), 2)
        self.assertIn("_exec_pace_state", titan)
        self.assertIn("exec_pace_apply(exec_pace_state,item,reference,plan,info)", frozen)
        self.assertIn('"exec_pace": false', composer.compose_config('{}'))

    def test_double_apply_still_fails_closed(self):
        titan, frozen = composer.compose_sources(self.TITAN, self.FROZEN)
        with self.assertRaises(ValueError):
            composer.compose_sources(titan, frozen)


if __name__ == "__main__":
    unittest.main(verbosity=2)
