from __future__ import annotations

import copy
import unittest
from support import *


class VerifierTests(unittest.TestCase):
    def test_result_tamper_fails_offline_recompile_verifier(self):
        scenario = load_fixture("scenario_good.json")
        result = compile_result(scenario)
        self.assertTrue(verify_result(scenario, result))
        tampered = copy.deepcopy(result)
        tampered["mechanisms"][0]["realized_surplus"] += 1
        self.assertFalse(verify_result(scenario, tampered))

    def test_action_or_receipt_transplant_fails(self):
        scenario = load_fixture("scenario_good.json")
        result = compile_result(scenario)
        tampered = copy.deepcopy(result)
        tampered["mechanisms"][0]["provenance"]["orders"][0]["price"] += 1
        self.assertFalse(verify_result(scenario, tampered))
        tampered2 = copy.deepcopy(result)
        tampered2["receipt"]["scenario_sha256"] = "0" * 64
        self.assertFalse(verify_result(scenario, tampered2))
