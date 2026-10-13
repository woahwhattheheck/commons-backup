from __future__ import annotations

import json
import unittest

from revenue.procurement_award_price_intelligence import adapters, engine
from revenue.procurement_award_price_intelligence.test_adapters import (
    FIXED_NOW,
    MWRD_HTML,
    base_request,
    raw,
)


class AdapterUriCustodyTests(unittest.TestCase):
    def decode_uri(self, uri):
        request = base_request()
        request["source"]["uri"] = uri
        return request, adapters._decode_request(raw(request))

    def test_checked_in_public_query_shapes_remain_admissible(self):
        public_uris = (
            "https://mwrd.legistar.com/LegislationDetail.aspx?GUID=7526F541-6494-4623-882D-E8BF33DEB675&ID=8197080&Options=&Search=",
            "https://coralgables.legistar.com/LegislationDetail.aspx?GUID=9731C991-BDCE-4DF9-8E59-76BCD74B2831&ID=7996401&Options=&Search=",
            "https://mwrd.legistar.com:443/LegislationDetail.aspx?GUID=abc&ID=123",
        )
        for uri in public_uris:
            with self.subTest(uri=uri):
                request = base_request()
                request["source"]["uri"] = uri
                decoded = adapters._decode_request(raw(request))
                self.assertEqual(uri, decoded["uri"])

        coweta = base_request("BUYER_BID_TABULATION_PDF_V1")
        decoded = adapters._decode_request(raw(coweta))
        self.assertEqual(coweta["source"]["uri"], decoded["uri"])

        topeka = base_request("BUYER_BID_TABULATION_PDF_V1")
        topeka["source"]["uri"] = (
            "https://files.topeka.gov/business/procurement/bid-tabulations/2026/Bid%206.pdf"
        )
        decoded = adapters._decode_request(raw(topeka))
        self.assertEqual(topeka["source"]["uri"], decoded["uri"])

    def test_sensitive_unknown_duplicate_and_fragment_query_material_fail_closed(self):
        bad = (
            "https://mwrd.legistar.com/LegislationDetail.aspx?GUID=abc&ID=123&token=secret",
            "https://mwrd.legistar.com/LegislationDetail.aspx?GUID=abc&ID=123&X-Amz-Signature=deadbeef",
            "https://mwrd.legistar.com/LegislationDetail.aspx?GUID=abc&ID=123&access_token=secret",
            "https://mwrd.legistar.com/LegislationDetail.aspx?GUID=abc&ID=123&%58-Amz-Signature=deadbeef",
            "https://mwrd.legistar.com/LegislationDetail.aspx?GUID=abc&GUID=def&ID=123",
            "https://mwrd.legistar.com/LegislationDetail.aspx?GUID=abc&ID=123#access_token=secret",
            "https://u:p@mwrd.legistar.com/LegislationDetail.aspx?GUID=abc&ID=123",
            "https://mwrd.legistar.com/LegislationDetail.aspx?",
        )
        for uri in bad:
            request = base_request()
            request["source"]["uri"] = uri
            with self.subTest(uri=uri):
                with self.assertRaises(adapters.AdapterError):
                    adapters._decode_request(raw(request))

    def test_nondefault_ports_and_opaque_paths_fail_before_fetch(self):
        bad_legistar = (
            "https://mwrd.legistar.com:8443/LegislationDetail.aspx?GUID=abc&ID=123",
            "https://mwrd.legistar.com/download/token-secret/LegislationDetail.aspx?GUID=abc&ID=123",
            "https://mwrd.legistar.com/X-Amz-Signature/deadbeef/LegislationDetail.aspx?GUID=abc&ID=123",
            "https://mwrd.legistar.com/LegislationDetail.aspx/secret?GUID=abc&ID=123",
        )
        for uri in bad_legistar:
            request = base_request()
            request["source"]["uri"] = uri
            with self.subTest(uri=uri):
                with self.assertRaises(adapters.AdapterError):
                    adapters._decode_request(raw(request))

        bad_pdf = (
            "https://www.cityofcoweta-ok.gov:8443/DocumentCenter/View/2084/260427-Bid-Tab-PDF?bidId=",
            "https://www.cityofcoweta-ok.gov/DocumentCenter/View/2084/token-secret/260427-Bid-Tab-PDF?bidId=",
            "https://files.topeka.gov/business/procurement/bid-tabulations/2026/token-secret/Bid%206.pdf",
        )
        for uri in bad_pdf:
            request = base_request("BUYER_BID_TABULATION_PDF_V1")
            request["source"]["uri"] = uri
            with self.subTest(uri=uri):
                with self.assertRaises(adapters.AdapterError):
                    adapters._decode_request(raw(request))

    def test_public_query_values_are_shape_bound_not_freeform_secret_channels(self):
        bad = (
            "https://mwrd.legistar.com/LegislationDetail.aspx?GUID=secret&ID=123",
            "https://mwrd.legistar.com/LegislationDetail.aspx?GUID=abc&ID=secret",
            "https://mwrd.legistar.com/LegislationDetail.aspx?GUID=abc&ID=123&Search=secret",
            "https://mwrd.legistar.com/LegislationDetail.aspx?GUID=abc&ID=123&Options=secret",
        )
        for uri in bad:
            request = base_request()
            request["source"]["uri"] = uri
            with self.subTest(uri=uri):
                with self.assertRaises(adapters.AdapterError):
                    adapters._decode_request(raw(request))

        coweta = base_request("BUYER_BID_TABULATION_PDF_V1")
        coweta["source"]["uri"] = (
            "https://www.cityofcoweta-ok.gov/DocumentCenter/View/2084/260427-Bid-Tab-PDF?bidId=secret"
        )
        with self.assertRaises(adapters.AdapterError):
            adapters._decode_request(raw(coweta))

    def test_redirect_cannot_add_signed_or_token_query_before_artifact_generation(self):
        request = base_request()
        encoded = raw(request)
        decoded = adapters._decode_request(encoded)
        bad_final = (
            "https://mwrd.legistar.com/LegislationDetail.aspx?GUID=abc&ID=123&token=secret",
            "https://mwrd.legistar.com/LegislationDetail.aspx?GUID=abc&ID=123#access_token=secret",
        )
        for final_uri in bad_final:
            with self.subTest(final_uri=final_uri):
                with self.assertRaises(adapters.AdapterError):
                    adapters._compile_fetched(
                        encoded, decoded, MWRD_HTML, final_uri, "text/html", FIXED_NOW
                    )

    def test_redirect_cannot_change_to_nondefault_port_or_opaque_path(self):
        request = base_request()
        encoded = raw(request)
        decoded = adapters._decode_request(encoded)
        bad_final = (
            "https://mwrd.legistar.com:8443/LegislationDetail.aspx?GUID=abc&ID=123",
            "https://mwrd.legistar.com/download/token-secret/LegislationDetail.aspx?GUID=abc&ID=123",
            "https://mwrd.legistar.com/X-Amz-Signature/deadbeef/LegislationDetail.aspx?GUID=abc&ID=123",
        )
        for final_uri in bad_final:
            with self.subTest(final_uri=final_uri):
                with self.assertRaises(adapters.AdapterError):
                    adapters._compile_fetched(
                        encoded, decoded, MWRD_HTML, final_uri, "text/html", FIXED_NOW
                    )

    def test_public_final_uri_is_durable_and_no_secret_material_is_present(self):
        public_uri = (
            "https://mwrd.legistar.com/LegislationDetail.aspx?"
            "GUID=7526F541-6494-4623-882D-E8BF33DEB675&ID=8197080&Options=&Search="
        )
        request = base_request()
        request["source"]["uri"] = public_uri
        encoded = raw(request)
        decoded = adapters._decode_request(encoded)
        normalized_bytes, receipt_bytes = adapters._compile_fetched(
            encoded, decoded, MWRD_HTML, public_uri, "text/html", FIXED_NOW
        )
        normalized = json.loads(normalized_bytes)
        receipt = json.loads(receipt_bytes)
        self.assertEqual(public_uri, normalized["sources"][0]["uri"])
        self.assertEqual(public_uri, receipt["source_uri"])
        self.assertNotIn(b"token=", normalized_bytes + receipt_bytes)
        self.assertNotIn(b"X-Amz-Signature", normalized_bytes + receipt_bytes)
        self.assertNotIn(b"access_token", normalized_bytes + receipt_bytes)

    def test_source_identity_is_live_byte_owned_not_caller_uri_owned(self):
        uris = (
            "https://mwrd.legistar.com/LegislationDetail.aspx?GUID=abc&ID=123",
            "https://mwrd.legistar.com/LegislationDetail.aspx?GUID=def&ID=456",
        )
        ids = []
        for uri in uris:
            request = base_request()
            request["source"]["uri"] = uri
            encoded = raw(request)
            decoded = adapters._decode_request(encoded)
            normalized_bytes, _ = adapters._compile_fetched(
                encoded, decoded, MWRD_HTML, uri, "text/html", FIXED_NOW
            )
            source = json.loads(normalized_bytes)["sources"][0]
            ids.append(source["source_id"])
            self.assertEqual(engine.digest(MWRD_HTML), source["sha256"])
        self.assertEqual(ids[0], ids[1])


if __name__ == "__main__":
    unittest.main()
