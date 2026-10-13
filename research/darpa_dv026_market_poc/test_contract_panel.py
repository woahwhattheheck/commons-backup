from __future__ import annotations

import copy
import unittest
from support import *


class ContractPanelTests(unittest.TestCase):
    def test_duplicate_model_identity_rejected(self):
        scenario = load_fixture("scenario_good.json")
        scenario["panel"]["slots"][1]["provider"] = scenario["panel"]["slots"][0]["provider"]
        scenario["panel"]["slots"][1]["model"] = scenario["panel"]["slots"][0]["model"]
        with self.assertRaisesRegex(ContractError, "provider/model identities"):
            validate_scenario(scenario)

    def test_panel_cannot_claim_external_execution(self):
        scenario = load_fixture("scenario_good.json")
        scenario["panel"]["external_execution"] = True
        with self.assertRaisesRegex(ContractError, "must not claim external execution"):
            validate_scenario(scenario)

    def test_human_subject_collection_rejected(self):
        scenario = load_fixture("scenario_good.json")
        scenario["benchmark"]["human_subject_collection"] = True
        with self.assertRaisesRegex(ContractError, "human-subject"):
            validate_scenario(scenario)
