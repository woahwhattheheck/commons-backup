from __future__ import annotations

import copy
import random
import unittest

from tournament import (
    CORPUS_SCHEMA_VERSION,
    FOUNDATION_SCHEMA_VERSION,
    FOUNDATION_DEFAULT_POLICY,
    TournamentError,
    build_policy_family,
    canonical_json,
    sha256_hex,
    run_tournament,
    validate_candidates,
    validate_corpus,
    verify_tournament,
)


def make_corpus(family, train_bias=None, holdout_bias=None):
    train_bias = train_bias or {}
    holdout_bias = holdout_bias or {}
    episodes = []
    for split, count, bias in (("TRAIN", 3, train_bias), ("HOLDOUT", 2, holdout_bias)):
        for episode_index in range(count):
            outcomes = []
            for rank, candidate in enumerate(family):
                cid = candidate["candidate_id"]
                base = 1000 - rank * 7 + episode_index
                utility = base + bias.get(cid, 0)
                outcomes.append(
                    {
                        "candidate_id": cid,
                        "utility": utility,
                        "budget_spent": 100 + rank,
                        "action_count": 10 + (rank % 3),
                        "constraint_violations": 0,
                    }
                )
            episodes.append(
                {"episode_id": f"{split.lower()}-{episode_index}", "split": split, "outcomes": outcomes}
            )
    return {
        "schema_version": CORPUS_SCHEMA_VERSION,
        "foundation_schema_version": FOUNDATION_SCHEMA_VERSION,
        "episodes": episodes,
    }


class TournamentTests(unittest.TestCase):
    def setUp(self):
        self.family = build_policy_family()
        self.corpus = make_corpus(self.family)

    def test_family_is_bounded_unique_and_policy_bound(self):
        clean = validate_candidates(self.family)
        self.assertGreater(len(clean), 5)
        self.assertLessEqual(len(clean), 32)
        self.assertEqual(len(clean), len({row["candidate_id"] for row in clean}))

    def test_receipt_binds_landed_foundation_default_policy_bytes(self):
        receipt = run_tournament(self.corpus, self.family)
        self.assertEqual(
            receipt["foundation_default_policy_sha256"],
            sha256_hex(canonical_json(FOUNDATION_DEFAULT_POLICY)),
        )

    def test_default_tournament_verifies(self):
        receipt = run_tournament(self.corpus, self.family)
        self.assertTrue(verify_tournament(receipt, self.corpus, self.family))
        self.assertFalse(receipt["official_score_claimed"])
        self.assertFalse(receipt["submission_claimed"])
        self.assertFalse(receipt["prize_or_revenue_claimed"])

    def test_holdout_cannot_change_selected_policy(self):
        first = run_tournament(self.corpus, self.family)
        selected = first["selected_candidate_id"]
        hostile_bias = {row["candidate_id"]: (10**9 if row["candidate_id"] != selected else -(10**9)) for row in self.family}
        hostile = make_corpus(self.family, holdout_bias=hostile_bias)
        second = run_tournament(hostile, self.family)
        self.assertEqual(selected, second["selected_candidate_id"])
        self.assertNotEqual(first["holdout_selected"]["total_utility"], second["holdout_selected"]["total_utility"])

    def test_train_changes_can_change_selected_policy(self):
        baseline = run_tournament(self.corpus, self.family)
        target = self.family[-1]["candidate_id"]
        biased = make_corpus(self.family, train_bias={target: 10**9})
        changed = run_tournament(biased, self.family)
        self.assertEqual(target, changed["selected_candidate_id"])
        self.assertNotEqual(baseline["selected_candidate_id"], changed["selected_candidate_id"])

    def test_constraint_violation_loses_to_clean_candidate(self):
        corpus = copy.deepcopy(self.corpus)
        receipt = run_tournament(corpus, self.family)
        prior = receipt["selected_candidate_id"]
        for episode in corpus["episodes"]:
            if episode["split"] == "TRAIN":
                for outcome in episode["outcomes"]:
                    if outcome["candidate_id"] == prior:
                        outcome["constraint_violations"] = 1
        new_receipt = run_tournament(corpus, self.family)
        self.assertNotEqual(prior, new_receipt["selected_candidate_id"])

    def test_input_order_is_irrelevant(self):
        baseline = run_tournament(self.corpus, self.family)
        shuffled = copy.deepcopy(self.corpus)
        random.Random(7).shuffle(shuffled["episodes"])
        for episode in shuffled["episodes"]:
            random.Random(11).shuffle(episode["outcomes"])
        family = list(reversed(copy.deepcopy(self.family)))
        self.assertEqual(canonical_json(baseline), canonical_json(run_tournament(shuffled, family)))

    def test_every_episode_requires_every_candidate(self):
        bad = copy.deepcopy(self.corpus)
        bad["episodes"][0]["outcomes"].pop()
        with self.assertRaises(TournamentError):
            validate_corpus(bad, self.family)

    def test_duplicate_episode_rejected(self):
        bad = copy.deepcopy(self.corpus)
        bad["episodes"][1]["episode_id"] = bad["episodes"][0]["episode_id"]
        with self.assertRaises(TournamentError):
            validate_corpus(bad, self.family)

    def test_duplicate_candidate_outcome_rejected(self):
        bad = copy.deepcopy(self.corpus)
        bad["episodes"][0]["outcomes"][1]["candidate_id"] = bad["episodes"][0]["outcomes"][0]["candidate_id"]
        with self.assertRaises(TournamentError):
            validate_corpus(bad, self.family)

    def test_requires_train_and_holdout(self):
        bad = copy.deepcopy(self.corpus)
        for episode in bad["episodes"]:
            episode["split"] = "TRAIN"
        with self.assertRaises(TournamentError):
            validate_corpus(bad, self.family)

    def test_unknown_split_rejected(self):
        bad = copy.deepcopy(self.corpus)
        bad["episodes"][0]["split"] = "PRIVATE_TEST"
        with self.assertRaises(TournamentError):
            validate_corpus(bad, self.family)

    def test_bool_is_not_integer_outcome(self):
        bad = copy.deepcopy(self.corpus)
        bad["episodes"][0]["outcomes"][0]["utility"] = True
        with self.assertRaises(TournamentError):
            validate_corpus(bad, self.family)

    def test_candidate_id_binds_policy(self):
        bad = copy.deepcopy(self.family)
        bad[0]["policy"]["new_tag_bonus"] += 1
        with self.assertRaises(TournamentError):
            validate_candidates(bad)

    def test_receipt_tamper_rejected(self):
        receipt = run_tournament(self.corpus, self.family)
        receipt["holdout_selected"]["total_utility"] += 1
        self.assertFalse(verify_tournament(receipt, self.corpus, self.family))

    def test_corpus_tamper_rejected_by_receipt_verifier(self):
        receipt = run_tournament(self.corpus, self.family)
        changed = copy.deepcopy(self.corpus)
        changed["episodes"][0]["outcomes"][0]["utility"] += 1
        self.assertFalse(verify_tournament(receipt, changed, self.family))

    def test_selection_rule_is_explicitly_train_only(self):
        receipt = run_tournament(self.corpus, self.family)
        self.assertTrue(receipt["selection_rule"].startswith("TRAIN_ONLY:"))
        self.assertFalse(receipt["holdout_used_for_selection"])


if __name__ == "__main__":
    unittest.main()
