import unittest

import unc_ap_ai as m
import test_unc_ap_ai as base


class RetryMetadataBinding(unittest.TestCase):
    def test_zero_retry_metadata_is_unambiguous(self):
        case = base.valid_case()
        case["integration"]["retry_count"] = 0
        case["integration"]["retry_effect_key"] = None
        self.assertEqual(
            m.evaluate_invoice_case(
                case, extraction_threshold_basis_points=9_900
            )["disposition"],
            "PASS",
        )

        case["integration"]["retry_effect_key"] = "invoice:OTHER"
        self.assertEqual(
            m.evaluate_invoice_case(
                case, extraction_threshold_basis_points=9_900
            )["disposition"],
            "HOLD_INTEGRATION",
        )


if __name__ == "__main__":
    unittest.main()
