from __future__ import annotations

import copy
import unittest

from .ledger import (
    INPUT_SCHEMA,
    canonical_json,
    compile_funnel,
    verify_artifacts_current,
)

AS_OF = "2026-09-13T10:10:00Z"


def _source(name: str) -> dict:
    return {
        "repository": "example/fixture",
        "commit": "1" * 40,
        "path": f"synthetic/{name}.json",
        "sha256": "b" * 64,
    }


def _payload() -> dict:
    return {
        "schema": INPUT_SCHEMA,
        "opportunities": [{
            "id": "opp-casefold",
            "family": "SERVICE",
            "offer": {"id": "offer-casefold", "version": "v1", "source": _source("offer")},
            "events": [{
                "id": "evt-traffic",
                "stage": "TRAFFIC",
                "observed_at": "2026-09-12T10:00:00Z",
                "evidence": _source("traffic"),
            }],
        }],
    }


class CasefoldPacketIdentityTests(unittest.TestCase):
    def test_case_only_exact_replay_preserves_packet_and_receipt_identity(self):
        single_input = _payload()
        single_input["opportunities"][0]["events"][0]["evidence"]["repository"] = "Example/Fixture"

        replay_input = copy.deepcopy(single_input)
        replay = copy.deepcopy(replay_input["opportunities"][0]["events"][0])
        replay["evidence"]["repository"] = "EXAMPLE/fixture"
        replay_input["opportunities"][0]["events"].append(replay)

        single = compile_funnel(single_input, as_of=AS_OF)
        replayed = compile_funnel(replay_input, as_of=AS_OF)
        self.assertEqual(canonical_json(single["packet"]), canonical_json(replayed["packet"]))
        self.assertEqual(canonical_json(single["receipt"]), canonical_json(replayed["receipt"]))
        self.assertEqual(len(replayed["packet"]["opportunities"][0]["events"]), 1)

    def test_mixed_case_artifact_verifies_against_same_lowercase_github_identity(self):
        mixed = _payload()
        mixed["opportunities"][0]["offer"]["source"]["repository"] = "Example/Fixture"
        mixed["opportunities"][0]["events"][0]["evidence"]["repository"] = "EXAMPLE/Fixture"
        artifact = compile_funnel(mixed, as_of=AS_OF)

        lowercase = copy.deepcopy(mixed)
        lowercase["opportunities"][0]["offer"]["source"]["repository"] = "example/fixture"
        lowercase["opportunities"][0]["events"][0]["evidence"]["repository"] = "example/fixture"

        self.assertTrue(
            verify_artifacts_current(
                lowercase,
                trusted_now=AS_OF,
                packet=artifact["packet"],
                receipt=artifact["receipt"],
                report_json=artifact["json"],
                report_csv=artifact["csv"],
                report_markdown=artifact["markdown"],
            )
        )

    def test_digest_still_binds_non_case_same_id_conflict(self):
        single_input = _payload()
        conflict_input = copy.deepcopy(single_input)
        conflicting = copy.deepcopy(conflict_input["opportunities"][0]["events"][0])
        conflicting["evidence"] = _source("different-traffic-object")
        conflict_input["opportunities"][0]["events"].append(conflicting)

        single = compile_funnel(single_input, as_of=AS_OF)
        conflict = compile_funnel(conflict_input, as_of=AS_OF)
        self.assertNotEqual(single["packet"]["input_sha256"], conflict["packet"]["input_sha256"])
        row = conflict["packet"]["opportunities"][0]
        self.assertEqual(row["state"], "HOLD")
        self.assertIn("EVENT_ID_CONFLICT", row["hold_reasons"])

    def test_same_id_conflict_permutations_bind_one_packet_meaning(self):
        forward = _payload()
        first = forward["opportunities"][0]["events"][0]
        first["evidence"]["repository"] = "Example/Fixture"

        conflicting = copy.deepcopy(first)
        conflicting["stage"] = "REPLY"
        conflicting["observed_at"] = "2026-09-12T11:00:00Z"
        conflicting["evidence"] = _source("reply-conflict")
        conflicting["evidence"]["repository"] = "EXAMPLE/fixture"
        conflicting["proves"] = ["TRAFFIC"]
        forward["opportunities"][0]["events"].append(conflicting)

        reverse = copy.deepcopy(forward)
        reverse["opportunities"][0]["events"].reverse()

        a = compile_funnel(forward, as_of=AS_OF)
        b = compile_funnel(reverse, as_of=AS_OF)
        self.assertEqual(a["packet"]["input_sha256"], b["packet"]["input_sha256"])
        self.assertEqual(canonical_json(a["packet"]), canonical_json(b["packet"]))
        self.assertEqual(canonical_json(a["receipt"]), canonical_json(b["receipt"]))

        row = a["packet"]["opportunities"][0]
        self.assertEqual(row["state"], "HOLD")
        self.assertIn("EVENT_ID_CONFLICT", row["hold_reasons"])
        self.assertEqual(row["events"], [])
        self.assertIsNone(row["strongest_evidenced_stage"])
        self.assertEqual(row["gross_cash_by_currency"], {})

        self.assertTrue(
            verify_artifacts_current(
                reverse,
                trusted_now=AS_OF,
                packet=a["packet"],
                receipt=a["receipt"],
                report_json=a["json"],
                report_csv=a["csv"],
                report_markdown=a["markdown"],
            )
        )


if __name__ == "__main__":
    unittest.main()
