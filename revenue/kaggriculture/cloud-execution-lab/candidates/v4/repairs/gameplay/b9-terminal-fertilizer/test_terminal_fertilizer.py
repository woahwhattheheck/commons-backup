import copy
import unittest

from terminal_fertilizer import make_agent


STANDARD = {"episodeSteps": 720, "turnsPerDay": 24, "maxMarketOrdersPerTurn": 10}


def obs(step=716, player=0, pos=(4, 4), fert=True, animal="COW", hands=None):
    tiles = [[None for _ in range(10)] for _ in range(10)]
    tiles[pos[1]][pos[0]] = {
        "kind": "PASTURE",
        "animal": animal,
        "fertilizer_available": fert,
    }
    hand_positions = [] if hands is None else [list(value) for value in hands]
    for hand_pos in hand_positions:
        x, y = hand_pos
        tiles[y][x] = {
            "kind": "COOP",
            "animal": "GOOSE",
            "fertilizer_available": True,
        }
    return {
        "step": step,
        "player": player,
        "farms": [{"tiles": tiles, "farmer": list(pos), "hands": hand_positions}],
    }


def parent_with(action):
    frozen = copy.deepcopy(action)

    def parent(_obs, _cfg=None):
        return copy.deepcopy(frozen)

    return parent


class T(unittest.TestCase):
    def test_collects_literal_pass_on_exact_terminal_steps(self):
        for step in (716, 717):
            a = make_agent(parent_with({"farmer": ["PASS"], "hands": [], "market": []}))
            self.assertEqual(a(obs(step=step), STANDARD)["farmer"], ["COLLECT_FERTILIZER"])

    def test_outside_window_identity(self):
        action = {"farmer": ["PASS"], "hands": [], "market": [["SELL", "WHEAT", 1]]}
        a = make_agent(parent_with(action))
        self.assertEqual(a(obs(step=715), STANDARD), action)

    def test_never_overrides_non_pass(self):
        for cmd in (["CARE"], ["FEED"], ["DROP"], ["PLACE", "MILK", 1], ["HARVEST"]):
            a = make_agent(parent_with({"farmer": cmd, "hands": [], "market": []}))
            self.assertEqual(a(obs(), STANDARD)["farmer"], cmd)

    def test_missing_empty_or_malformed_parent_commands_are_identity(self):
        cases = (
            {"hands": [], "market": []},
            {"farmer": None, "hands": [], "market": []},
            {"farmer": [], "hands": [], "market": []},
            {"farmer": [False], "hands": [], "market": []},
            {"farmer": ["PASS"], "market": []},
            {"farmer": ["PASS"], "hands": [None], "market": []},
            {"farmer": ["PASS"], "hands": [[]], "market": []},
        )
        for action in cases:
            with self.subTest(action=action):
                a = make_agent(parent_with(action))
                observation = obs(hands=[(5, 5)]) if action.get("hands") else obs()
                self.assertEqual(a(observation, STANDARD), action)

    def test_action_hand_cardinality_must_match_represented_hands(self):
        observation = obs(hands=[(5, 5)])
        too_few = {"farmer": ["PASS"], "hands": [], "market": []}
        a = make_agent(parent_with(too_few))
        self.assertEqual(a(observation, STANDARD), too_few)

        exact = {"farmer": ["CARE"], "hands": [["PASS"]], "market": []}
        a = make_agent(parent_with(exact))
        self.assertEqual(a(observation, STANDARD)["hands"], [["COLLECT_FERTILIZER"]])

    def test_requires_shed_adjacent_animal_true_fert(self):
        action = {"farmer": ["PASS"], "hands": [], "market": []}
        for o in (obs(pos=(1, 1)), obs(fert=False), obs(fert=1), obs(animal=None)):
            a = make_agent(parent_with(action))
            self.assertEqual(a(o, STANDARD)["farmer"], ["PASS"])

    def test_explicit_standard_terminal_timing_is_required(self):
        action = {"farmer": ["PASS"], "hands": [], "market": []}
        bad_configs = (
            None,
            {},
            {"episodeSteps": 720},
            {"turnsPerDay": 24},
            {"episodeSteps": True, "turnsPerDay": 24, "maxMarketOrdersPerTurn": 10},
            {"episodeSteps": 720.0, "turnsPerDay": 24, "maxMarketOrdersPerTurn": 10},
            {"episodeSteps": 719, "turnsPerDay": 24, "maxMarketOrdersPerTurn": 10},
            {"episodeSteps": 720, "turnsPerDay": True, "maxMarketOrdersPerTurn": 10},
            {"episodeSteps": 720, "turnsPerDay": 24.0, "maxMarketOrdersPerTurn": 10},
            {"episodeSteps": 720, "turnsPerDay": 23, "maxMarketOrdersPerTurn": 10},
        )
        for config in bad_configs:
            with self.subTest(config=config):
                a = make_agent(parent_with(action))
                self.assertEqual(a(obs(), config), action)
        a = make_agent(parent_with(action))
        self.assertEqual(a(obs(), dict(STANDARD))["farmer"], ["COLLECT_FERTILIZER"])

    def test_market_cap_is_explicit_and_type_strict(self):
        action = {"farmer": ["PASS"], "hands": [], "market": []}
        bad_caps = (None, True, False, 10.0, "10", [], {})
        for cap in bad_caps:
            with self.subTest(cap=cap):
                config = dict(STANDARD)
                config["maxMarketOrdersPerTurn"] = cap
                a = make_agent(parent_with(action))
                self.assertEqual(a(obs(), config), action)
        missing = dict(STANDARD)
        missing.pop("maxMarketOrdersPerTurn")
        a = make_agent(parent_with(action))
        self.assertEqual(a(obs(), missing), action)

    def test_nonstandard_timing_does_not_leave_collection_provenance(self):
        calls = {
            716: {"farmer": ["PASS"], "hands": [], "market": []},
            718: {
                "farmer": ["PASS"],
                "hands": [],
                "market": [["SELL", "FERTILIZER", 1], ["SELL", "WHEAT", 1]],
            },
        }

        def parent(o, _cfg=None):
            return copy.deepcopy(calls[o["step"]])

        a = make_agent(parent)
        a(obs(step=716), {"episodeSteps": 719, "turnsPerDay": 24, "maxMarketOrdersPerTurn": 10})
        self.assertEqual(a(obs(step=718), STANDARD)["market"], calls[718]["market"])

    def test_invalid_timing_clears_existing_collection_provenance(self):
        calls = {
            716: {"farmer": ["PASS"], "hands": [], "market": []},
            717: {"farmer": ["PASS"], "hands": [], "market": []},
            718: {
                "farmer": ["PASS"],
                "hands": [],
                "market": [["SELL", "FERTILIZER", 1], ["SELL", "WHEAT", 1]],
            },
        }

        def parent(o, _cfg=None):
            return copy.deepcopy(calls[o["step"]])

        bad_configs = (
            {"episodeSteps": 719, "turnsPerDay": 24, "maxMarketOrdersPerTurn": 10},
            {},
            None,
        )
        for config in bad_configs:
            with self.subTest(config=config):
                a = make_agent(parent)
                self.assertEqual(a(obs(step=716), STANDARD)["farmer"], ["COLLECT_FERTILIZER"])
                a(obs(step=717), config)
                self.assertEqual(a(obs(step=718), STANDARD)["market"], calls[718]["market"])

    def test_invalid_market_cap_clears_existing_collection_provenance(self):
        calls = {
            716: {"farmer": ["PASS"], "hands": [], "market": []},
            717: {"farmer": ["PASS"], "hands": [], "market": []},
            718: {
                "farmer": ["PASS"],
                "hands": [],
                "market": [["SELL", "FERTILIZER", 1], ["SELL", "WHEAT", 1]],
            },
        }

        def parent(o, _cfg=None):
            return copy.deepcopy(calls[o["step"]])

        for cap in (None, True, 10.0, "10"):
            with self.subTest(cap=cap):
                poison = dict(STANDARD)
                poison["maxMarketOrdersPerTurn"] = cap
                a = make_agent(parent)
                self.assertEqual(a(obs(step=716), STANDARD)["farmer"], ["COLLECT_FERTILIZER"])
                a(obs(step=717), poison)
                self.assertEqual(a(obs(step=718), STANDARD)["market"], calls[718]["market"])

    def test_invalid_observation_identity_clears_existing_collection_provenance(self):
        neutral = {"farmer": ["PASS"], "hands": [], "market": []}
        terminal = {
            "farmer": ["PASS"],
            "hands": [],
            "market": [["SELL", "FERTILIZER", 1], ["SELL", "WHEAT", 1]],
        }

        def parent(o, _cfg=None):
            if isinstance(o, dict) and o.get("step") == 718 and o.get("player") == 0:
                return copy.deepcopy(terminal)
            return copy.deepcopy(neutral)

        missing_step = obs(step=717)
        missing_step.pop("step")
        missing_player = obs(step=717)
        missing_player.pop("player")
        missing_farms = obs(step=717)
        missing_farms.pop("farms")
        bad_farms = obs(step=717)
        bad_farms["farms"] = None
        none_selected_farm = obs(step=717)
        none_selected_farm["farms"][0] = None
        missing_tiles = obs(step=717)
        missing_tiles["farms"][0].pop("tiles")
        bad_tiles = obs(step=717)
        bad_tiles["farms"][0]["tiles"] = None
        ragged_tiles = obs(step=717)
        ragged_tiles["farms"][0]["tiles"][0].pop()
        missing_farmer = obs(step=717)
        missing_farmer["farms"][0].pop("farmer")
        bad_farmer = obs(step=717)
        bad_farmer["farms"][0]["farmer"] = None
        bool_farmer_position = obs(step=717)
        bool_farmer_position["farms"][0]["farmer"] = [True, 4]
        out_of_bounds_farmer = obs(step=717)
        out_of_bounds_farmer["farms"][0]["farmer"] = [10, 4]
        bad_hands = obs(step=717)
        bad_hands["farms"][0]["hands"] = None
        bad_hand_position = obs(step=717, hands=[(5, 5)])
        bad_hand_position["farms"][0]["hands"] = [[5, False]]
        poisons = (
            ("missing-step", missing_step),
            ("bool-step", obs(step=True)),
            ("negative-step", obs(step=-1)),
            ("past-end-step", obs(step=720)),
            ("missing-player", missing_player),
            ("bool-player", obs(step=717, player=True)),
            ("negative-player", obs(step=717, player=-1)),
            ("out-of-range-player", obs(step=717, player=1)),
            ("missing-farms", missing_farms),
            ("bad-farms", bad_farms),
            ("none-selected-farm", none_selected_farm),
            ("missing-tiles", missing_tiles),
            ("bad-tiles", bad_tiles),
            ("ragged-tiles", ragged_tiles),
            ("missing-farmer", missing_farmer),
            ("bad-farmer", bad_farmer),
            ("bool-farmer-position", bool_farmer_position),
            ("out-of-bounds-farmer", out_of_bounds_farmer),
            ("bad-hands", bad_hands),
            ("bad-hand-position", bad_hand_position),
        )
        for label, poison in poisons:
            with self.subTest(label=label):
                a = make_agent(parent)
                self.assertEqual(a(obs(step=716), STANDARD)["farmer"], ["COLLECT_FERTILIZER"])
                self.assertEqual(a(poison, STANDARD), neutral)
                self.assertEqual(a(obs(step=718), STANDARD)["market"], terminal["market"])

    def test_valid_nonqualifying_farm_preserves_existing_collection_provenance(self):
        neutral = {"farmer": ["PASS"], "hands": [], "market": []}
        terminal = {
            "farmer": ["PASS"],
            "hands": [],
            "market": [["SELL", "FERTILIZER", 1], ["SELL", "WHEAT", 1]],
        }

        def parent(o, _cfg=None):
            return copy.deepcopy(terminal if o["step"] == 718 else neutral)

        nonqualifying = (
            ("fert-false", obs(step=717, fert=False)),
            ("fert-nonbool", obs(step=717, fert=1)),
            ("animal-none", obs(step=717, animal=None)),
            ("away-from-shed", obs(step=717, pos=(1, 1))),
        )
        for label, observation in nonqualifying:
            with self.subTest(label=label):
                a = make_agent(parent)
                self.assertEqual(a(obs(step=716), STANDARD)["farmer"], ["COLLECT_FERTILIZER"])
                self.assertEqual(a(observation, STANDARD), neutral)
                self.assertEqual(
                    a(obs(step=718), STANDARD)["market"],
                    [["SELL", "WHEAT", 1], ["SELL", "FERTILIZER", 1]],
                )

    def test_trails_only_after_collection(self):
        terminal = {
            "farmer": ["PASS"],
            "hands": [],
            "market": [
                ["SELL", "FERTILIZER", 2],
                ["SELL", "WOOL", 4],
                ["SELL", "WHEAT", 2],
            ],
        }
        a = make_agent(parent_with(terminal))
        self.assertEqual(a(obs(step=718), STANDARD)["market"], terminal["market"])
        calls = {
            716: {"farmer": ["PASS"], "hands": [], "market": []},
            718: terminal,
        }

        def parent(o, _cfg=None):
            return copy.deepcopy(calls[o["step"]])

        a = make_agent(parent)
        a(obs(step=716), STANDARD)
        self.assertEqual(
            a(obs(step=718), STANDARD)["market"],
            [
                ["SELL", "WOOL", 4],
                ["SELL", "WHEAT", 2],
                ["SELL", "FERTILIZER", 2],
            ],
        )

    def test_terminal_reorder_stays_inside_executable_prefix(self):
        terminal = {
            "farmer": ["PASS"],
            "hands": [],
            "market": [
                ["SELL", "FERTILIZER", 1],
                ["SELL", "WOOL", 2],
                ["SELL", "WHEAT", 3],
                ["SELL", "FERTILIZER", 99],
                ["SELL", "MILK", 4],
            ],
        }
        calls = {716: {"farmer": ["PASS"], "hands": [], "market": []}, 718: terminal}

        def parent(o, _cfg=None):
            return copy.deepcopy(calls[o["step"]])

        config = dict(STANDARD)
        config["maxMarketOrdersPerTurn"] = 3
        a = make_agent(parent)
        a(obs(step=716), config)
        self.assertEqual(
            a(obs(step=718), config)["market"],
            [
                ["SELL", "WOOL", 2],
                ["SELL", "WHEAT", 3],
                ["SELL", "FERTILIZER", 1],
                ["SELL", "FERTILIZER", 99],
                ["SELL", "MILK", 4],
            ],
        )

    def test_cap_one_and_clamped_caps_preserve_executable_row(self):
        terminal = {
            "farmer": ["PASS"],
            "hands": [],
            "market": [["SELL", "FERTILIZER", 1], ["SELL", "WHEAT", 1]],
        }
        calls = {716: {"farmer": ["PASS"], "hands": [], "market": []}, 718: terminal}

        def parent(o, _cfg=None):
            return copy.deepcopy(calls[o["step"]])

        for cap in (1, 0, -3):
            with self.subTest(cap=cap):
                config = dict(STANDARD)
                config["maxMarketOrdersPerTurn"] = cap
                a = make_agent(parent)
                a(obs(step=716), config)
                self.assertEqual(a(obs(step=718), config)["market"], terminal["market"])

    def test_rewind_resets_collection_provenance(self):
        calls = {
            716: {"farmer": ["PASS"], "hands": [], "market": []},
            718: {
                "farmer": ["PASS"],
                "hands": [],
                "market": [["SELL", "FERTILIZER", 1], ["SELL", "WHEAT", 1]],
            },
            0: {"farmer": ["PASS"], "hands": [], "market": []},
        }

        def parent(o, _cfg=None):
            return copy.deepcopy(calls[o["step"]])

        a = make_agent(parent)
        a(obs(step=716), STANDARD)
        a(obs(step=0), STANDARD)
        self.assertEqual(a(obs(step=718), STANDARD)["market"], calls[718]["market"])

    def test_malformed_observation_fails_closed(self):
        action = {"farmer": ["PASS"], "hands": [], "market": []}
        a = make_agent(parent_with(action))
        bad = obs()
        bad["player"] = True
        self.assertEqual(a(bad, STANDARD), action)


if __name__ == "__main__":
    unittest.main()
