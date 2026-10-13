from __future__ import annotations

import copy
import unittest
from support import *


class ContractSequenceTests(unittest.TestCase):
    def test_duplicate_action_step_rejected(self):
        scenario = load_fixture("scenario_good.json")
        scenario["traders"][1]["action_step"] = scenario["traders"][0]["action_step"]
        with self.assertRaisesRegex(ContractError, "action_step must be unique"):
            validate_scenario(scenario)

    def test_duplicate_news_identity_and_step_rejected(self):
        scenario = load_fixture("scenario_good.json")
        scenario["news"].append(copy.deepcopy(scenario["news"][0]))
        with self.assertRaisesRegex(ContractError, "duplicate news_id"):
            validate_scenario(scenario)

    def test_negative_quantity_rejected(self):
        scenario = load_fixture("scenario_good.json")
        scenario["traders"][0]["quantity"] = -1
        with self.assertRaises(ContractError):
            validate_scenario(scenario)
