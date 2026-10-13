import unittest

from qualifier import QualificationError, compile_qualification, normalized_source_sha256
from test_qualifier import AS_OF, E, complete_packet


class ManifestIntegrityTests(unittest.TestCase):
    def test_manifest_digest_must_match_source_digest(self):
        packet = complete_packet()
        packet["packetManifest"]["files"][0]["sha256"] = "e" * 64
        with self.assertRaises(QualificationError):
            compile_qualification(packet, as_of=AS_OF)

    def test_every_controlling_source_must_be_manifested(self):
        packet = complete_packet()
        packet["sources"].append({
            "id": "addendum-one",
            "kind": "ADDENDUM",
            "url": "https://app01.jaggaer.com/apps/Router/ViewSourcingEvent",
            "capturedAt": "2026-09-13T10:40:00Z",
            "contentSha256": E,
            "controlling": True,
            "label": "Addendum one",
        })
        trusted = normalized_source_sha256(packet, as_of=AS_OF)
        out = compile_qualification(packet, as_of=AS_OF, expected_source_packet_sha256=trusted)
        self.assertEqual(out["receipt"]["disposition"], "HOLD_RAW_PACKET_REQUIRED")
        self.assertIn("CONTROLLING_SOURCE_NOT_IN_MANIFEST:addendum-one", out["receipt"]["reasons"])


if __name__ == "__main__":
    unittest.main()
