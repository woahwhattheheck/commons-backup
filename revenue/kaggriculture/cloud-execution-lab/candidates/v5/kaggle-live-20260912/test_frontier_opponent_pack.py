#!/usr/bin/env python3
from __future__ import annotations

import unittest
from pathlib import Path

import frontier_opponent_pack as pack


class FrontierOpponentPackTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parent

    def test_checked_in_pack_matches_saved_evidence(self) -> None:
        built = pack.validate_pack(self.root, self.root / pack.PACK_MANIFEST)
        self.assertEqual(
            [item["rated_submission_id"] for item in built["frontier_targets"]],
            [56156662, 56161578, 56145462, 56161402, 56114097, 56097405],
        )

    def test_latest_upload_never_replaces_rated_variant(self) -> None:
        identities = pack.load_top30(self.root / pack.TOP30_CSV)
        rank3 = pack.resolve_competitive_target(identities, rank=3)
        self.assertEqual(rank3.target_submission_id, 56145462)
        self.assertEqual(rank3.latest_submission_id, 56158444)
        self.assertTrue(rank3.latest_drifted)

    def test_ambiguous_rows_fail_closed(self) -> None:
        identities = pack.load_top30(self.root / pack.TOP30_CSV)
        with self.assertRaisesRegex(pack.OpponentPackError, "identity is unconfirmed"):
            pack.resolve_competitive_target(identities, rank=18)
        with self.assertRaisesRegex(pack.OpponentPackError, "identity is unconfirmed"):
            pack.resolve_competitive_target(identities, rank=30)

    def test_leader_replay_is_bound_only_to_exact_participants(self) -> None:
        built = pack.build_pack(self.root)
        by_rank = {item["rank"]: item for item in built["frontier_targets"]}
        self.assertEqual(
            by_rank[1]["materialization"],
            {
                "kind": "public_action_replay_manifest",
                "episode_id": 108115160,
                "payload_in_repo": False,
            },
        )
        self.assertEqual(
            by_rank[2]["materialization"],
            {
                "kind": "public_action_replay_manifest",
                "episode_id": 108115160,
                "payload_in_repo": False,
            },
        )
        self.assertEqual(
            by_rank[3]["materialization"]["kind"],
            "public_submission_identity",
        )

    def test_loss_bank_preserves_exact_historical_submission(self) -> None:
        built = pack.build_pack(self.root)
        losses = built["exact_live_loss_rematches"]
        self.assertEqual(
            [(x["episode_id"], x["submission_id"]) for x in losses],
            [(108138386, 56165718), (108139400, 56167602)],
        )


if __name__ == "__main__":
    unittest.main()
