from __future__ import annotations

import copy
import hashlib
import json
import unittest

from revenue.procurement_award_price_intelligence import engine
from revenue.procurement_award_price_intelligence.source_adapters import Error, compile
from revenue.procurement_award_price_intelligence.test_source_adapters import (
    award,
    bid,
    contract,
    document,
    raw,
    request,
)


class SourceAdapterRedClosureTests(unittest.TestCase):
    def test_query_fragment_and_encoded_secret_source_uris_fail_closed(self):
        secret_uris = (
            "https://buyer.example.gov/award?token=secret-value",
            "https://buyer.example.gov/award?X-Amz-Signature=deadbeef",
            "https://buyer.example.gov/award#access_token=secret-value",
            "https://buyer.example.gov/award?",
            "https://buyer.example.gov/award#",
            "https://buyer.example.gov/%3Ftoken%3Dsecret-value",
            "https://buyer.example.gov/%23access_token%3Dsecret-value",
            "https://buyer.example.gov/award%3FX-Amz-Signature%3Ddeadbeef",
            "https://buyer.example.gov/%253Ftoken%253Dsecret-value",
            "https://buyer.example.gov/%25%33%46token%3Dsecret-value",
            "https://user%3Asecret%40buyer.example.gov/award",
            "https://user%253Asecret%2540buyer.example.gov/award",
        )
        for uri in secret_uris:
            doc = document("AWARD_NOTICE_JSON_V1", award(), "AWARD_NOTICE")
            doc["source"]["uri"] = uri
            with self.subTest(uri=uri):
                with self.assertRaisesRegex(Error, "credential|query|fragment"):
                    compile(raw(request([doc])))

    def test_arbitrary_path_bytes_are_digest_only_and_never_reach_price_or_memo(self):
        locators = (
            "https://buyer.example.gov/download/opaque-secret-signed-path/award.pdf",
            "https://buyer.example.gov/download/%6fpaque-secret-signed-path/award.pdf",
            "https://buyer.example.gov/download/%256fpaque-secret-signed-path/award.pdf",
            "https://buyer.example.gov/award%20notice/public%2Fcopy",
        )
        for uri in locators:
            doc = document("AWARD_NOTICE_JSON_V1", award(), "AWARD_NOTICE")
            doc["source"]["uri"] = uri
            request_bytes = raw(request([doc]))
            with self.subTest(uri=uri):
                price_bytes, packet_bytes, receipt_bytes = compile(request_bytes)
                price = json.loads(price_bytes)
                packet = json.loads(packet_bytes)
                receipt = json.loads(receipt_bytes)
                locator_sha = hashlib.sha256(uri.encode("utf-8")).hexdigest()

                self.assertEqual("https://buyer.example.gov", price["sources"][0]["uri"])
                self.assertEqual(locator_sha, packet["source_audit"][0]["source_locator_sha256"])
                self.assertEqual(
                    [{"source_id": "s1", "sha256": locator_sha}],
                    receipt["source_locator_sha256s"],
                )

                for artifact in (price_bytes, packet_bytes, receipt_bytes):
                    self.assertNotIn(uri.encode("utf-8"), artifact)
                    self.assertNotIn(b"opaque-secret-signed-path", artifact)

                downstream_packet, downstream_memo, downstream_receipt = engine.compile(price_bytes)
                downstream = json.loads(downstream_packet)
                self.assertEqual(
                    "https://buyer.example.gov",
                    downstream["admissible_observations"][0]["sources"][0]["uri"],
                )
                for artifact in (downstream_packet, downstream_memo, downstream_receipt):
                    self.assertNotIn(uri.encode("utf-8"), artifact)
                    self.assertNotIn(b"opaque-secret-signed-path", artifact)

    def test_raw_source_cannot_be_reminted_under_fresh_source_identity(self):
        first = document("AWARD_NOTICE_JSON_V1", award(), "AWARD_NOTICE", source_id="source-a")
        remint = copy.deepcopy(first)
        remint["source"]["source_id"] = "source-b"
        remint["source"]["uri"] = "https://buyer.example.gov/alternate-locator"
        with self.assertRaisesRegex(Error, "duplicate retained raw source"):
            compile(raw(request([first, remint])))

    def test_payload_cannot_be_reminted_with_fresh_raw_metadata(self):
        first = document("AWARD_NOTICE_JSON_V1", award(), "AWARD_NOTICE", source_id="source-a")
        remint = copy.deepcopy(first)
        remint["source"]["source_id"] = "source-b"
        remint["source"]["uri"] = "https://buyer.example.gov/alternate-locator"
        remint["source"]["sha256"] = "b" * 64
        with self.assertRaisesRegex(Error, "duplicate structured source payload"):
            compile(raw(request([first, remint])))

    def test_same_raw_source_cannot_be_resliced_into_second_payload(self):
        first = document("AWARD_NOTICE_JSON_V1", award(), "AWARD_NOTICE", source_id="source-a")
        changed_payload = award()
        changed_payload["award_id"] = "a2"
        changed_payload["award_amount_minor"] = 999999
        second = document("AWARD_NOTICE_JSON_V1", changed_payload, "AWARD_NOTICE", source_id="source-b")
        second["source"]["sha256"] = first["source"]["sha256"]
        with self.assertRaisesRegex(Error, "duplicate retained raw source"):
            compile(raw(request([first, second])))

    def test_changed_award_identity_does_not_add_statistical_weight(self):
        first = document("AWARD_NOTICE_JSON_V1", award(), "AWARD_NOTICE", source_id="source-a")
        second_payload = award()
        second_payload["award_id"] = "a2"
        second = document("AWARD_NOTICE_JSON_V1", second_payload, "AWARD_NOTICE", source_id="source-b")
        second["source"]["sha256"] = "b" * 64
        price_bytes, _, _ = compile(raw(request([first, second])))
        packet = json.loads(engine.compile(price_bytes)[0])
        self.assertEqual("PRICE_EVIDENCE_READY", packet["status"])
        self.assertEqual(1, packet["comparable_groups"][0]["count"])
        self.assertEqual(1, len(packet["admissible_observations"]))
        self.assertEqual(
            {"source-a", "source-b"},
            set(packet["admissible_observations"][0]["source_ids"]),
        )

    def test_award_notice_and_executed_contract_corroborate_one_claim(self):
        first = document("AWARD_NOTICE_JSON_V1", award(), "AWARD_NOTICE", source_id="source-a")
        contract_payload = contract()
        contract_payload.update(
            opportunity_id="opp1",
            vendor="Vendor LLC",
            base_amount_minor=123400,
            option_amount_minor=None,
            option_term_months=None,
        )
        second = document(
            "EXECUTED_CONTRACT_JSON_V1",
            contract_payload,
            "EXECUTED_CONTRACT",
            source_id="source-b",
        )
        second["source"]["sha256"] = "b" * 64
        price_bytes, _, _ = compile(raw(request([first, second])))
        packet = json.loads(engine.compile(price_bytes)[0])
        self.assertEqual("PRICE_EVIDENCE_READY", packet["status"])
        self.assertEqual(1, packet["comparable_groups"][0]["count"])
        self.assertEqual(
            {"source-a", "source-b"},
            {source["source_id"] for source in packet["admissible_observations"][0]["sources"]},
        )

    def test_same_claim_different_signature_still_holds_conflict(self):
        first = document("AWARD_NOTICE_JSON_V1", award(), "AWARD_NOTICE", source_id="source-a")
        second_payload = award()
        second_payload.update(award_id="a2", award_amount_minor=999999)
        second = document("AWARD_NOTICE_JSON_V1", second_payload, "AWARD_NOTICE", source_id="source-b")
        second["source"]["sha256"] = "b" * 64
        price_bytes, _, _ = compile(raw(request([first, second])))
        packet = json.loads(engine.compile(price_bytes)[0])
        self.assertEqual("HOLD_SOURCE_CONFLICT", packet["status"])
        self.assertEqual(1, len(packet["conflicts"]))

    def test_distinct_claim_same_value_still_counts_twice(self):
        first = document("AWARD_NOTICE_JSON_V1", award(), "AWARD_NOTICE", source_id="source-a")
        second_payload = award()
        second_payload.update(award_id="a2", vendor="Other Vendor")
        second = document("AWARD_NOTICE_JSON_V1", second_payload, "AWARD_NOTICE", source_id="source-b")
        second["source"]["sha256"] = "b" * 64
        price_bytes, _, _ = compile(raw(request([first, second])))
        packet = json.loads(engine.compile(price_bytes)[0])
        self.assertEqual("PRICE_EVIDENCE_READY", packet["status"])
        self.assertEqual(2, packet["comparable_groups"][0]["count"])

    def test_legitimate_multiple_rows_live_inside_one_retained_source(self):
        payload = bid()
        payload["rows"] = [
            {"row_id": "r1", "vendor": "A LLC", "bid_amount_minor": 111100, "responsive": True},
            {"row_id": "r2", "vendor": "B LLC", "bid_amount_minor": 121200, "responsive": True},
        ]
        doc = document("BID_TABULATION_JSON_V1", payload, "BID_TABULATION")
        price_bytes, packet_bytes, _ = compile(raw(request([doc])))
        price = json.loads(price_bytes)
        packet = json.loads(packet_bytes)
        downstream = json.loads(engine.compile(price_bytes)[0])
        self.assertEqual(1, len(price["sources"]))
        self.assertEqual(2, len(price["observations"]))
        self.assertEqual(2, packet["emitted_observation_count"])
        self.assertEqual(2, downstream["comparable_groups"][0]["count"])
        self.assertEqual({"A LLC", "B LLC"}, {row["vendor"] for row in price["observations"]})


if __name__ == "__main__":
    unittest.main()
