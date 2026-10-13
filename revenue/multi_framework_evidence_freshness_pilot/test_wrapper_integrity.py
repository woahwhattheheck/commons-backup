from __future__ import annotations

import copy
import unittest

from revenue.multi_framework_evidence_freshness.golden import build_golden_input

from . import wrapper
from .wrapper import DiagnosticError, compile_diagnostic, render_buyer_page, verify_diagnostic


class WrapperIntegrityTests(unittest.TestCase):
    def test_engine_reason_codes_are_preserved(self) -> None:
        envelope = compile_diagnostic(build_golden_input())
        reason_codes = {row["reason"] for row in envelope["diagnostic"]["summary"]["non_reusable"]}
        self.assertIn("FRESHNESS_WINDOW_EXCEEDED", reason_codes)
        self.assertIn("MISSING_OWNER", reason_codes)
        self.assertNotIn("UNSPECIFIED", reason_codes)

    def test_forged_counts_rejected_even_with_redigested_body(self) -> None:
        envelope = compile_diagnostic(build_golden_input())
        forged = copy.deepcopy(envelope)
        forged["diagnostic"]["summary"]["counts"] = {state: 0 for state in wrapper.STATES}
        forged["diagnostic"]["summary"]["counts"]["REUSABLE"] = 400
        forged["diagnostic_sha256"] = wrapper._sha(forged["diagnostic"])
        with self.assertRaisesRegex(DiagnosticError, "diagnostic_packet_mismatch"):
            verify_diagnostic(forged)

    def test_forged_engine_binding_rejected_even_with_redigested_body(self) -> None:
        envelope = compile_diagnostic(build_golden_input())
        forged = copy.deepcopy(envelope)
        forged["diagnostic"]["binding"]["input_sha256"] = "0" * 64
        forged["diagnostic"]["binding"]["projection_sha256"] = "1" * 64
        forged["diagnostic_sha256"] = wrapper._sha(forged["diagnostic"])
        with self.assertRaisesRegex(DiagnosticError, "diagnostic_packet_mismatch"):
            verify_diagnostic(forged)

    def test_forged_scope_rejected_even_with_redigested_body(self) -> None:
        envelope = compile_diagnostic(build_golden_input())
        forged = copy.deepcopy(envelope)
        forged["diagnostic"]["scope"]["objects_submitted"] = 499
        forged["diagnostic"]["scope"]["objects_evaluated"] = 499
        forged["diagnostic_sha256"] = wrapper._sha(forged["diagnostic"])
        with self.assertRaisesRegex(DiagnosticError, "diagnostic_packet_mismatch"):
            verify_diagnostic(forged)

    def test_offer_and_authority_contract_is_machine_readable(self) -> None:
        envelope = compile_diagnostic(build_golden_input())
        offer = envelope["diagnostic"]["offer"]
        self.assertFalse(offer["free_custom_adapter"])
        self.assertIn("PAID_DIAGNOSTIC", offer["integration_sprint_condition"])
        authority = envelope["diagnostic"]["authority"]
        self.assertFalse(authority["outbound"])
        self.assertFalse(authority["evidence_mutation"])

    def test_buyer_page_aggregates_reasons_without_evidence_ids(self) -> None:
        envelope = compile_diagnostic(build_golden_input())
        page = render_buyer_page(envelope)
        self.assertIn("FRESHNESS_WINDOW_EXCEEDED", page)
        self.assertNotIn("STALE-000", page)


if __name__ == "__main__":
    unittest.main()
