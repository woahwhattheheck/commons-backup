# SPDX-License-Identifier: Apache-2.0
"""Pinned H3c old-prefix/new-raw-action equivalence; not an economics gate."""
from __future__ import annotations

import copy
import hashlib
import itertools
from pathlib import Path
import types
import unittest

import h3c_goose_eod_cap_rescue as current
from test_v4_h3c_market_prefix import fixture

OLD_BLOB = "2044d6cf1e0c51f95027229863f910aa43ac7008"
NEW_BLOB = "79c3fd029054a2db5931609db06f6b9aa4d4be3c"
PREFIX_PATCH = (
    '    # The standard engine executes ten raw slots, not ten nonempty rows.\n'
    '    # A capped suffix cannot add shed inflow; keep it untouched in the action.\n'
    '    for order in market[:STANDARD_CONFIG["maxMarketOrdersPerTurn"]]:\n'
)


def blob(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def predecessor():
    """Recover the exact reviewed predecessor, not an approximate oracle."""
    data = Path(current.__file__).read_bytes()
    if blob(data) != NEW_BLOB:
        raise ValueError("H3c source changed: re-audit this differential proof")
    text = data.decode("utf-8")
    old_sentence = "worker has another non-PASS command on that same animal,"
    if text.count(PREFIX_PATCH) != 1 or text.count(old_sentence) != 1:
        raise ValueError("H3c inverse patch anchors are not unique")
    text = text.replace(PREFIX_PATCH, "    for order in market:\n", 1)
    text = text.replace(old_sentence, "worker has another non-PASS command on the same animal,", 1)
    if blob(text.encode("utf-8")) != OLD_BLOB:
        raise ValueError("H3c predecessor reconstruction hash mismatch")
    module = types.ModuleType("h3c_exact_predecessor")
    exec(compile(text, "<h3c-exact-predecessor>", "exec"), module.__dict__)
    return module


class TestH3cPrefixDifferential(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old = predecessor()

    def test_current_source_has_only_the_reviewed_delta(self):
        self.assertIsNot(self.old, current)
        self.assertEqual(self.old.STANDARD_CONFIG, current.STANDARD_CONFIG)

    def test_prefix_and_inert_suffix_equivalence(self):
        prefixes = [
            [[] for _ in range(10)],
            [["SELL", "EGG", 1]] + [[] for _ in range(9)],
            [[] for _ in range(9)] + [["BUY_PRODUCT", "WHEAT", 1]],
            [[] for _ in range(9)] + [["BUY_ANIMAL", "GOOSE", 1]],
            [[] for _ in range(9)] + [None],
        ]
        suffixes = [[], [["BUY_PRODUCT", "WHEAT", 100]],
                    [["BUY_ANIMAL", "COW", 100]],
                    [None, {}, False, "bad", [1], {"nested": [1, 2]}]]
        cells = itertools.product((0, 1), (False, True), (0, 94, 96, 97, 100),
                                  (0, 1), (0, 2, 4), (0, 1),
                                  range(len(prefixes)), range(len(suffixes)))
        count = 0
        for player, hand, shed, carried, units, bonus, pi, si in cells:
            with self.subTest(player=player, hand=hand, shed=shed, carried=carried,
                              units=units, bonus=bonus, prefix=pi, suffix=si):
                action, observation, config = fixture(player=player, hand=hand, shed_units=shed)
                tile = observation["farms"][player]["tiles"][1][1]
                tile["yield_units"], tile["pending_care_bonus"] = units, bonus
                observation["private"]["inventories"][int(hand)] = {"WHEAT": carried}
                action["market"] = copy.deepcopy(prefixes[pi])
                self.old.telemetry.clear()
                expected = self.old.apply_goose_eod_cap_rescue(action, observation, config, enabled=True)
                expected_trace = dict(self.old.telemetry)
                extended = copy.deepcopy(action)
                extended["market"] += copy.deepcopy(suffixes[si])
                snapshot = copy.deepcopy((extended, observation, config))
                current.telemetry.clear()
                actual = current.apply_goose_eod_cap_rescue(extended, observation, config, enabled=True)
                self.assertEqual(actual["farmer"], expected["farmer"])
                self.assertEqual(actual["hands"], expected["hands"])
                self.assertEqual(actual is extended, expected is action)
                self.assertEqual(actual["market"], extended["market"])
                self.assertEqual(dict(current.telemetry), expected_trace)
                self.assertEqual((extended, observation, config), snapshot)
                self.assertIs(current.apply_goose_eod_cap_rescue(extended, observation, config), extended)
                count += 1
        self.assertEqual(count, 4800)


if __name__ == "__main__":
    unittest.main()
