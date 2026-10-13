from __future__ import annotations

import json

from tournament import CORPUS_SCHEMA_VERSION, FOUNDATION_SCHEMA_VERSION, build_policy_family, run_tournament


def synthetic_corpus(family):
    episodes = []
    for split, count, split_adjustment in (("TRAIN", 4, 0), ("HOLDOUT", 2, -11)):
        for episode_index in range(count):
            outcomes = []
            for rank, candidate in enumerate(family):
                policy = candidate["policy"]
                utility = (
                    100_000
                    + policy["new_tag_bonus"] // 10
                    + policy["revisit_bonus_per_tick"] // 20
                    - policy["repeat_penalty"] // 100
                    - policy["switch_penalty"] * 13
                    + split_adjustment
                    + episode_index
                    - rank
                )
                outcomes.append(
                    {
                        "candidate_id": candidate["candidate_id"],
                        "utility": utility,
                        "budget_spent": 500 + policy["switch_penalty"] * 7 + rank,
                        "action_count": 24 + rank % 4,
                        "constraint_violations": 0,
                    }
                )
            episodes.append(
                {"episode_id": f"synthetic-{split.lower()}-{episode_index}", "split": split, "outcomes": outcomes}
            )
    return {
        "schema_version": CORPUS_SCHEMA_VERSION,
        "foundation_schema_version": FOUNDATION_SCHEMA_VERSION,
        "episodes": episodes,
    }


def main() -> int:
    family = build_policy_family()
    receipt = run_tournament(synthetic_corpus(family), family)
    print(json.dumps(receipt, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
