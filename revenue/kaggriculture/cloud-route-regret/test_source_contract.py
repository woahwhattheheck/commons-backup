# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import unittest

from source_contract import checkpoints, load_json, SOURCE


class SourceContractTests(unittest.TestCase):
    def test_checkpoint_table_is_exact_and_ordered(self):
        self.assertEqual(
            checkpoints(),
            (
                (226, "shop_YARN_STORE", 1, "dc76e4003029ac51"),
                (360, "px_CARROT", 42, "ab9669b9abfbea4e"),
                (433, "inv_MILK", 10067, "a84d06f1d12add7c"),
            ),
        )

    def test_contract_names_current_base_and_no_automatic_promotion(self):
        contract = load_json(SOURCE)
        self.assertEqual(
            contract["authored_base"],
            "2e2e7e52fd2d5c62117ac49c7f1eabb505078ffb",
        )
        self.assertIs(contract["invariants"]["promotion_is_never_automatic"], True)


if __name__ == "__main__":
    unittest.main()
