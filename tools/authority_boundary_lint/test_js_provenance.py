import unittest

from tools.authority_boundary_lint import lint


class JavaScriptAuthorityProvenanceTests(unittest.TestCase):
    def test_candidate_derived_receipt_name_does_not_suppress(self):
        source = """
function compile(candidate) {
  const diagnosticReceipt = candidate.receipt;
  if (candidate.diagnostic_passed && diagnosticReceipt.verified) {
    return "QUALIFIED_FOR_OWNER_SALES_REVIEW";
  }
  return "HOLD";
}
"""
        rows = lint.scan_javascript("case.js", source)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].field, "diagnostic_passed")

    def test_closed_sibling_function_cannot_donate_authority(self):
        source = """
function prior(candidate, diagnosticReceipt) {
  return candidate;
}
if (candidate.diagnostic_passed && diagnosticReceipt.verified) {
  const state = "QUALIFIED_FOR_OWNER_SALES_REVIEW";
}
"""
        rows = lint.scan_javascript("case.js", source)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].function, "<module>")

    def test_direct_independent_receipt_parameter_still_suppresses(self):
        source = """
function compile(candidate, diagnosticReceipt) {
  if (candidate.diagnostic_passed && diagnosticReceipt.verified) {
    return "QUALIFIED_FOR_OWNER_SALES_REVIEW";
  }
  return "HOLD";
}
"""
        self.assertEqual(lint.scan_javascript("case.js", source), [])


if __name__ == "__main__":
    unittest.main()
