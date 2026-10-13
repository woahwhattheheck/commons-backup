from __future__ import annotations

import unittest

from tools.revenue_proof_ledger.ledger import reduce_ledger
from tools.revenue_proof_ledger.test_ledger import (
    delivery,
    lookup,
    opportunity,
    payload,
    row,
    settlement,
)


class PartialAuthorityTests(unittest.TestCase):
    def test_partial_settlement_lookup_preserves_partial_authority_and_zero_cash(self):
        ledger = reduce_ledger(
            payload(
                opportunity("github"),
                delivery(),
                lookup("delivery"),
                lookup("settlement", authority="partial"),
                settlement("stripe:pi_1", "500"),
            )
        )
        proof = row(ledger)
        self.assertEqual(proof["authority"], "partial")
        self.assertEqual(proof["observed_net_cash"], "500")
        self.assertEqual(proof["cash_settled"], "0")
        self.assertEqual(proof["earned_unsettled"], "500")


if __name__ == "__main__":
    unittest.main()
