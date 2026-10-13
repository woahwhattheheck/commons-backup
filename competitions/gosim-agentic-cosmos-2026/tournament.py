from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable

FOUNDATION_SCHEMA_VERSION = "agentic-cosmos-foundation/v1"
CORPUS_SCHEMA_VERSION = "agentic-cosmos-tournament-corpus/v1"
RECEIPT_SCHEMA_VERSION = "agentic-cosmos-policy-tournament/v1"
MAX_CANDIDATES = 32
MAX_EPISODES = 512
MAX_ABS_UTILITY = 10**15
MAX_COUNTER = 10**12

POLICY_KEYS = {
    "horizon_ticks",
    "beam_width",
    "switch_penalty",
    "repeat_penalty",
    "revisit_bonus_per_tick",
    "revisit_bonus_cap",
    "new_tag_bonus",
    "idle_score",
}
CANDIDATE_KEYS = {"candidate_id", "policy"}
CORPUS_KEYS = {"schema_version", "foundation_schema_version", "episodes"}
EPISODE_KEYS = {"episode_id", "split", "outcomes"}
OUTCOME_KEYS = {
    "candidate_id",
    "utility",
    "budget_spent",
    "action_count",
    "constraint_violations",
}

FOUNDATION_DEFAULT_POLICY = {
    "horizon_ticks": 4,
    "beam_width": 96,
    "switch_penalty": 1,
    "repeat_penalty": 25_000,
    "revisit_bonus_per_tick": 2_000,
    "revisit_bonus_cap": 40_000,
    "new_tag_bonus": 8_000,
    "idle_score": -1,
}


class TournamentError(ValueError):
    pass


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _exact_keys(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TournamentError(f"{label} must be an object")
    actual = set(value)
    if actual != keys:
        raise TournamentError(
            f"{label} schema mismatch missing={sorted(keys - actual)} unknown={sorted(actual - keys)}"
        )
    return dict(value)


def _int(value: Any, label: str, lo: int, hi: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not lo <= value <= hi:
        raise TournamentError(f"{label} must be exact int in [{lo},{hi}]")
    return value


def _token(value: Any, label: str, max_len: int = 96) -> str:
    if not isinstance(value, str) or not value or len(value) > max_len:
        raise TournamentError(f"{label} must be nonempty text <= {max_len}")
    if any(ord(ch) < 33 or ord(ch) == 127 or ch.isspace() for ch in value):
        raise TournamentError(f"{label} must be an opaque token without whitespace/control characters")
    return value


def validate_policy(policy: Any) -> dict[str, int]:
    row = _exact_keys(policy, POLICY_KEYS, "policy")
    row["horizon_ticks"] = _int(row["horizon_ticks"], "horizon_ticks", 1, 8)
    row["beam_width"] = _int(row["beam_width"], "beam_width", 1, 512)
    for key in (
        "switch_penalty",
        "repeat_penalty",
        "revisit_bonus_per_tick",
        "revisit_bonus_cap",
        "new_tag_bonus",
    ):
        row[key] = _int(row[key], key, 0, 10**9)
    row["idle_score"] = _int(row["idle_score"], "idle_score", -10**9, 10**9)
    return row


def _candidate_id(policy: dict[str, int]) -> str:
    return "policy-" + sha256_hex(canonical_json(policy))[:20]


def _candidate(policy: Any) -> dict[str, Any]:
    clean = validate_policy(policy)
    return {"candidate_id": _candidate_id(clean), "policy": clean}


def _scaled_nonnegative(value: int, numerator: int, denominator: int = 4) -> int:
    if value == 0:
        return 0
    return max(0, min(10**9, value * numerator // denominator))


def build_policy_family(base_policy: Any | None = None) -> list[dict[str, Any]]:
    """Build a bounded deterministic family around the landed foundation policy.

    The family intentionally perturbs only policy weights, not organizer-private
    simulator semantics. Every candidate remains valid under the foundation's
    public policy bounds.
    """

    base = validate_policy(FOUNDATION_DEFAULT_POLICY if base_policy is None else base_policy)
    policies: list[dict[str, int]] = [dict(base)]

    for key in (
        "repeat_penalty",
        "revisit_bonus_per_tick",
        "revisit_bonus_cap",
        "new_tag_bonus",
    ):
        for numerator in (3, 5):
            row = dict(base)
            row[key] = _scaled_nonnegative(base[key], numerator)
            policies.append(row)

    # Switch penalty is often a small exact integer, so multiplicative 3/4 can
    # collapse back to the base. Use bounded +/- one alternatives instead.
    for value in sorted({max(0, base["switch_penalty"] - 1), min(10**9, base["switch_penalty"] + 1)}):
        row = dict(base)
        row["switch_penalty"] = value
        policies.append(row)

    for delta in (-1, 1):
        row = dict(base)
        row["idle_score"] = max(-10**9, min(10**9, base["idle_score"] + delta))
        policies.append(row)

    unique: dict[str, dict[str, Any]] = {}
    for policy in policies:
        item = _candidate(policy)
        unique[item["candidate_id"]] = item
    family = [unique[key] for key in sorted(unique)]
    if not 1 <= len(family) <= MAX_CANDIDATES:
        raise TournamentError("candidate family exceeded bound")
    return family


def validate_candidates(candidates: Any) -> list[dict[str, Any]]:
    if not isinstance(candidates, list) or not 1 <= len(candidates) <= MAX_CANDIDATES:
        raise TournamentError(f"candidates must contain 1..{MAX_CANDIDATES} rows")
    clean: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, value in enumerate(candidates):
        row = _exact_keys(value, CANDIDATE_KEYS, f"candidate[{index}]")
        policy = validate_policy(row["policy"])
        expected = _candidate_id(policy)
        if row["candidate_id"] != expected:
            raise TournamentError(f"candidate[{index}].candidate_id does not bind policy bytes")
        candidate_id = _token(row["candidate_id"], f"candidate[{index}].candidate_id")
        if candidate_id in seen:
            raise TournamentError("duplicate candidate_id")
        seen.add(candidate_id)
        clean.append({"candidate_id": candidate_id, "policy": policy})
    return sorted(clean, key=lambda row: row["candidate_id"])


def validate_corpus(corpus: Any, candidates: Any) -> dict[str, Any]:
    family = validate_candidates(candidates)
    candidate_ids = {row["candidate_id"] for row in family}
    root = _exact_keys(corpus, CORPUS_KEYS, "corpus")
    if root["schema_version"] != CORPUS_SCHEMA_VERSION:
        raise TournamentError("unsupported corpus schema_version")
    if root["foundation_schema_version"] != FOUNDATION_SCHEMA_VERSION:
        raise TournamentError("corpus foundation_schema_version mismatch")
    episodes = root["episodes"]
    if not isinstance(episodes, list) or not 2 <= len(episodes) <= MAX_EPISODES:
        raise TournamentError(f"episodes must contain 2..{MAX_EPISODES} rows")

    clean_episodes: list[dict[str, Any]] = []
    seen_episodes: set[str] = set()
    splits: set[str] = set()
    for index, value in enumerate(episodes):
        row = _exact_keys(value, EPISODE_KEYS, f"episode[{index}]")
        episode_id = _token(row["episode_id"], f"episode[{index}].episode_id")
        if episode_id in seen_episodes:
            raise TournamentError("duplicate episode_id")
        seen_episodes.add(episode_id)
        split = row["split"]
        if split not in {"TRAIN", "HOLDOUT"}:
            raise TournamentError("episode split must be TRAIN or HOLDOUT")
        splits.add(split)
        outcomes = row["outcomes"]
        if not isinstance(outcomes, list) or len(outcomes) != len(family):
            raise TournamentError("every episode must contain exactly one realized outcome per candidate")
        clean_outcomes: list[dict[str, Any]] = []
        seen_outcomes: set[str] = set()
        for out_index, outcome in enumerate(outcomes):
            item = _exact_keys(outcome, OUTCOME_KEYS, f"episode[{index}].outcome[{out_index}]")
            candidate_id = _token(item["candidate_id"], f"episode[{index}].outcome[{out_index}].candidate_id")
            if candidate_id not in candidate_ids:
                raise TournamentError("outcome references unknown candidate")
            if candidate_id in seen_outcomes:
                raise TournamentError("duplicate outcome candidate_id within episode")
            seen_outcomes.add(candidate_id)
            clean_outcomes.append(
                {
                    "candidate_id": candidate_id,
                    "utility": _int(item["utility"], "utility", -MAX_ABS_UTILITY, MAX_ABS_UTILITY),
                    "budget_spent": _int(item["budget_spent"], "budget_spent", 0, MAX_COUNTER),
                    "action_count": _int(item["action_count"], "action_count", 0, MAX_COUNTER),
                    "constraint_violations": _int(
                        item["constraint_violations"], "constraint_violations", 0, MAX_COUNTER
                    ),
                }
            )
        if seen_outcomes != candidate_ids:
            raise TournamentError("episode outcome set is incomplete")
        clean_episodes.append(
            {
                "episode_id": episode_id,
                "split": split,
                "outcomes": sorted(clean_outcomes, key=lambda out: out["candidate_id"]),
            }
        )

    if splits != {"TRAIN", "HOLDOUT"}:
        raise TournamentError("corpus requires at least one TRAIN and one HOLDOUT episode")
    clean_episodes.sort(key=lambda row: (row["split"], row["episode_id"]))
    return {
        "schema_version": CORPUS_SCHEMA_VERSION,
        "foundation_schema_version": FOUNDATION_SCHEMA_VERSION,
        "episodes": clean_episodes,
    }


def _metrics(episodes: Iterable[dict[str, Any]], candidate_id: str) -> dict[str, Any]:
    outcomes: list[dict[str, Any]] = []
    for episode in episodes:
        match = next(row for row in episode["outcomes"] if row["candidate_id"] == candidate_id)
        outcomes.append(match)
    if not outcomes:
        raise TournamentError("metric set may not be empty")
    utilities = [row["utility"] for row in outcomes]
    return {
        "candidate_id": candidate_id,
        "episodes": len(outcomes),
        "constraint_violations": sum(row["constraint_violations"] for row in outcomes),
        "worst_case_utility": min(utilities),
        "total_utility": sum(utilities),
        "total_budget_spent": sum(row["budget_spent"] for row in outcomes),
        "total_action_count": sum(row["action_count"] for row in outcomes),
    }


def _rank_key(metrics: dict[str, Any]) -> tuple[Any, ...]:
    violations = metrics["constraint_violations"]
    return (
        0 if violations == 0 else 1,
        violations,
        -metrics["worst_case_utility"],
        -metrics["total_utility"],
        metrics["total_budget_spent"],
        metrics["total_action_count"],
        metrics["candidate_id"],
    )


def run_tournament(corpus: Any, candidates: Any | None = None) -> dict[str, Any]:
    family = validate_candidates(build_policy_family() if candidates is None else candidates)
    clean = validate_corpus(corpus, family)
    train = [episode for episode in clean["episodes"] if episode["split"] == "TRAIN"]
    holdout = [episode for episode in clean["episodes"] if episode["split"] == "HOLDOUT"]

    train_ranking = sorted((_metrics(train, row["candidate_id"]) for row in family), key=_rank_key)
    selected_id = train_ranking[0]["candidate_id"]
    selected_policy = next(row["policy"] for row in family if row["candidate_id"] == selected_id)
    holdout_selected = _metrics(holdout, selected_id)

    body = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "foundation_schema_version": FOUNDATION_SCHEMA_VERSION,
        "foundation_default_policy_sha256": sha256_hex(canonical_json(FOUNDATION_DEFAULT_POLICY)),
        "corpus_sha256": sha256_hex(canonical_json(clean)),
        "candidate_family_sha256": sha256_hex(canonical_json(family)),
        "selected_candidate_id": selected_id,
        "selected_policy_sha256": sha256_hex(canonical_json(selected_policy)),
        "selection_rule": (
            "TRAIN_ONLY:zero-violations-first;fewest-violations;max-worst-case-utility;"
            "max-total-utility;min-budget;min-actions;lexical-id"
        ),
        "train_ranking": train_ranking,
        "holdout_selected": holdout_selected,
        "holdout_used_for_selection": False,
        "organizer_schema_claimed": False,
        "official_score_claimed": False,
        "submission_claimed": False,
        "prize_or_revenue_claimed": False,
    }
    return {**body, "receipt_sha256": sha256_hex(canonical_json(body))}


def verify_tournament(receipt: Any, corpus: Any, candidates: Any | None = None) -> bool:
    if not isinstance(receipt, dict) or not isinstance(receipt.get("receipt_sha256"), str):
        return False
    body = dict(receipt)
    digest = body.pop("receipt_sha256", None)
    if digest != sha256_hex(canonical_json(body)):
        return False
    try:
        rebuilt = run_tournament(corpus, candidates)
    except (TournamentError, TypeError, ValueError, KeyError, StopIteration):
        return False
    return canonical_json(rebuilt) == canonical_json(receipt)
