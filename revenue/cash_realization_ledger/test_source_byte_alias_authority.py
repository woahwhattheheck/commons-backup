import unittest

import cash_realization_ledger as crl
from test_cash_realization_ledger import add_event, packet


class SourceByteAliasAuthorityTests(unittest.TestCase):
    def test_same_source_bytes_cannot_split_across_authority_labels(self):
        p = packet()
        add_event(
            p,
            event_id="ev-cash-a",
            kind="PAYMENT_RECEIVED_EVIDENCE",
            time="2026-09-08T12:00:00Z",
            evidence_id="e-cash-a",
            authority="bank_record",
            amount=4500,
            reference="bank://statement/tx-1",
            source_sha="e" * 64,
        )
        add_event(
            p,
            event_id="ev-cash-b",
            kind="PAYMENT_RECEIVED_EVIDENCE",
            time="2026-09-08T13:00:00Z",
            evidence_id="e-cash-b",
            authority="payment_provider_evidence",
            amount=4500,
            reference="provider://receipt/tx-1",
            source_sha="e" * 64,
        )
        with self.assertRaisesRegex(ValueError, "source identity reused"):
            crl.compile_ledger(p)


if __name__ == "__main__":
    unittest.main()
