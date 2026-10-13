#!/usr/bin/env python3
"""Hermetic regressions for the SSA workstream packet boundary."""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

try:
    from . import validate_packet
except ImportError:  # direct execution
    import validate_packet


class ValidatePacketTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = json.loads(
            (Path(__file__).resolve().parent / "acceptance_matrix.json").read_text(
                encoding="utf-8"
            )
        )

    def test_canonical_packet_is_valid(self):
        validate_packet.validate_packet(copy.deepcopy(self.base))

    def test_production_write_fails_closed(self):
        candidate = copy.deepcopy(self.base)
        candidate["production_write_allowed"] = True
        with self.assertRaisesRegex(validate_packet.PacketError, "production_write_allowed"):
            validate_packet.validate_packet(candidate)

    def test_direct_submission_cannot_be_silently_authorized(self):
        candidate = copy.deepcopy(self.base)
        candidate["direct_agency_submission_authorized"] = True
        with self.assertRaisesRegex(validate_packet.PacketError, "direct_agency_submission_authorized"):
            validate_packet.validate_packet(candidate)

    def test_unverified_uei_cannot_be_promoted_inside_packet(self):
        candidate = copy.deepcopy(self.base)
        candidate["qualification_evidence"]["uei_verified"] = True
        with self.assertRaisesRegex(validate_packet.PacketError, "uei_verified"):
            validate_packet.validate_packet(candidate)

    def test_forbidden_claim_cannot_be_removed(self):
        candidate = copy.deepcopy(self.base)
        candidate["forbidden_claims"].remove("production_readiness_from_synthetic_evidence")
        with self.assertRaisesRegex(validate_packet.PacketError, "mandatory non-claim"):
            validate_packet.validate_packet(candidate)

    def test_duplicate_control_id_is_rejected(self):
        candidate = copy.deepcopy(self.base)
        candidate["controls"][1]["id"] = candidate["controls"][0]["id"]
        with self.assertRaisesRegex(validate_packet.PacketError, "duplicate control id"):
            validate_packet.validate_packet(candidate)

    def test_control_without_evidence_is_rejected(self):
        candidate = copy.deepcopy(self.base)
        candidate["controls"][0]["evidence"] = []
        with self.assertRaisesRegex(validate_packet.PacketError, "at least two"):
            validate_packet.validate_packet(candidate)

    def test_human_authority_cannot_be_removed(self):
        candidate = copy.deepcopy(self.base)
        candidate["controls"][1]["human_authority_required"] = False
        with self.assertRaisesRegex(validate_packet.PacketError, "human_authority_required"):
            validate_packet.validate_packet(candidate)

    def test_measurement_requires_baseline(self):
        candidate = copy.deepcopy(self.base)
        measurement = next(
            control for control in candidate["controls"]
            if control["category"] == "measurement"
        )
        measurement["baseline_required"] = False
        with self.assertRaisesRegex(validate_packet.PacketError, "require a baseline"):
            validate_packet.validate_packet(candidate)

    def test_measurement_must_bind_observations(self):
        candidate = copy.deepcopy(self.base)
        measurement = next(
            control for control in candidate["controls"]
            if control["category"] == "measurement"
        )
        measurement["evidence"].remove("observed_values")
        with self.assertRaisesRegex(validate_packet.PacketError, "baseline and observations"):
            validate_packet.validate_packet(candidate)


if __name__ == "__main__":
    unittest.main()
