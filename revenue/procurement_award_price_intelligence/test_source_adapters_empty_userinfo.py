from __future__ import annotations

import unittest

from revenue.procurement_award_price_intelligence.source_adapters import Error, compile
from revenue.procurement_award_price_intelligence.test_source_adapters import award, document, raw, request


class SourceAdapterEmptyUserinfoGuardTests(unittest.TestCase):
    def test_literal_encoded_and_double_encoded_empty_userinfo_fail_closed(self):
        hostile_uris = (
            "https://@buyer.example.gov/award",
            "https://:@buyer.example.gov/award",
            "https://%40buyer.example.gov/award",
            "https://%3A%40buyer.example.gov/award",
            "https://%2540buyer.example.gov/award",
            "https://%253A%2540buyer.example.gov/award",
        )
        for uri in hostile_uris:
            doc = document("AWARD_NOTICE_JSON_V1", award(), "AWARD_NOTICE")
            doc["source"]["uri"] = uri
            with self.subTest(uri=uri):
                with self.assertRaisesRegex(Error, "credential|query|fragment"):
                    compile(raw(request([doc])))


if __name__ == "__main__":
    unittest.main()
