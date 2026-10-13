from __future__ import annotations

import unittest
from support import *


class ContractJsonTests(unittest.TestCase):
    def test_duplicate_json_key_rejected(self):
        with self.assertRaisesRegex(ContractError, "duplicate JSON key"):
            loads_strict(b'{"schema":"x","schema":"y"}')

    def test_nonfinite_json_rejected(self):
        with self.assertRaisesRegex(ContractError, "non-finite JSON constant"):
            loads_strict(b'{"x":NaN}')

    def test_bool_is_not_integer(self):
        scenario = load_fixture("scenario_good.json")
        scenario["reference_price"] = True
        with self.assertRaises(ContractError):
            validate_scenario(scenario)
