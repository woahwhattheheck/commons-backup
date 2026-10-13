#!/usr/bin/env python3
"""Deterministic resolver for TITAN V5's public frontier opponent identities.

This module never fabricates opponent code. It turns the saved Kaggle top-30
evidence into exact submission identities, marks what evidence is actually
available, and refuses ambiguous leaderboard aliases for competitive screens.
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Mapping, Sequence

TOP30_CSV = "top30-opponent-targets.csv"
LEADER_REPLAY = "leader-reference-replay-manifest.json"
LIVE_LOSS_BANK = "live-public-loss-bank.json"
PACK_MANIFEST = "frontier-opponent-pack.json"

_CONFIRMED_TARGET_BASIS = "unique_leaderboard_score_match"


class OpponentPackError(ValueError):
    """Raised when saved opponent identity evidence is incomplete or ambiguous."""


@dataclass(frozen=True)
class OpponentIdentity:
    rank: int
    team_id: int
    team_name: str
    leaderboard_score: str
    target_submission_id: int
    target_public_score: str
    latest_submission_id: int
    latest_public_score: str
    target_is_latest: bool | None
    target_is_highest: bool | None
    match_basis: str
    target_basis: str

    @property
    def identity_confirmed(self) -> bool:
        return (
            self.target_basis == _CONFIRMED_TARGET_BASIS
            and Decimal(self.target_public_score) == Decimal(self.leaderboard_score)
        )

    @property
    def latest_drifted(self) -> bool:
        return self.target_is_latest is False or (
            self.target_submission_id != self.latest_submission_id
        )


def _plain_int(value: object, *, field: str, minimum: int = 1) -> int:
    if isinstance(value, bool):
        raise OpponentPackError(f"{field} must be an integer, not bool")
    try:
        parsed = int(str(value))
    except (TypeError, ValueError) as exc:
        raise OpponentPackError(f"{field} must be an integer") from exc
    if str(parsed) != str(value).strip():
        raise OpponentPackError(f"{field} must use exact integer syntax")
    if parsed < minimum:
        raise OpponentPackError(f"{field} must be >= {minimum}")
    return parsed


def _score(value: object, *, field: str) -> str:
    text = str(value).strip()
    try:
        parsed = Decimal(text)
    except (InvalidOperation, ValueError) as exc:
        raise OpponentPackError(f"{field} must be decimal numeric") from exc
    if not parsed.is_finite() or parsed < 0:
        raise OpponentPackError(f"{field} must be finite and nonnegative")
    return text


def _optional_bool(value: object, *, field: str) -> bool | None:
    text = str(value).strip()
    if text == "":
        return None
    if text == "True":
        return True
    if text == "False":
        return False
    raise OpponentPackError(f"{field} must be True, False, or blank")


def load_top30(path: Path) -> tuple[OpponentIdentity, ...]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise OpponentPackError("top-30 target table is empty")

    identities: list[OpponentIdentity] = []
    ranks: set[int] = set()
    for row in rows:
        rank = _plain_int(row.get("rank"), field="rank")
        if rank in ranks:
            raise OpponentPackError(f"duplicate rank {rank}")
        ranks.add(rank)
        identity = OpponentIdentity(
            rank=rank,
            team_id=_plain_int(row.get("team_id"), field=f"rank {rank} team_id"),
            team_name=str(row.get("team_name", "")).strip(),
            leaderboard_score=_score(
                row.get("leaderboard_score"), field=f"rank {rank} leaderboard_score"
            ),
            target_submission_id=_plain_int(
                row.get("target_submission_id"),
                field=f"rank {rank} target_submission_id",
            ),
            target_public_score=_score(
                row.get("target_public_score"),
                field=f"rank {rank} target_public_score",
            ),
            latest_submission_id=_plain_int(
                row.get("latest_submission_id"),
                field=f"rank {rank} latest_submission_id",
            ),
            latest_public_score=_score(
                row.get("latest_public_score"),
                field=f"rank {rank} latest_public_score",
            ),
            target_is_latest=_optional_bool(
                row.get("target_is_latest"), field=f"rank {rank} target_is_latest"
            ),
            target_is_highest=_optional_bool(
                row.get("target_is_highest"), field=f"rank {rank} target_is_highest"
            ),
            match_basis=str(row.get("match_basis", "")).strip(),
            target_basis=str(row.get("target_basis", "")).strip(),
        )
        if not identity.team_name:
            raise OpponentPackError(f"rank {rank} missing team_name")
        identities.append(identity)

    identities.sort(key=lambda item: item.rank)
    if len(identities) != 30:
        raise OpponentPackError(f"expected 30 opponent rows, got {len(identities)}")
    expected = list(range(1, 31))
    actual = [item.rank for item in identities]
    if actual != expected:
        raise OpponentPackError(f"rank sequence must be exactly 1..30: {actual}")
    submission_ids = [item.target_submission_id for item in identities]
    if len(set(submission_ids)) != len(submission_ids):
        raise OpponentPackError("target submission ids must be unique")
    return tuple(identities)


def confirmed_rated_targets(
    identities: Sequence[OpponentIdentity],
    *,
    minimum_score: Decimal = Decimal("3000"),
) -> tuple[OpponentIdentity, ...]:
    return tuple(
        item
        for item in identities
        if item.identity_confirmed and Decimal(item.leaderboard_score) >= minimum_score
    )


def resolve_competitive_target(
    identities: Sequence[OpponentIdentity],
    *,
    rank: int | None = None,
    team_id: int | None = None,
) -> OpponentIdentity:
    if (rank is None) == (team_id is None):
        raise OpponentPackError("provide exactly one of rank or team_id")
    matches = [
        item
        for item in identities
        if (rank is not None and item.rank == rank)
        or (team_id is not None and item.team_id == team_id)
    ]
    if len(matches) != 1:
        raise OpponentPackError("opponent identity not uniquely found")
    item = matches[0]
    if not item.identity_confirmed:
        raise OpponentPackError(
            f"rank {item.rank} identity is unconfirmed; refusing latest/fallback substitution"
        )
    return item


def _load_json(path: Path) -> Mapping[str, object]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise OpponentPackError(f"{path.name} must contain a JSON object")
    return value


def build_pack(evidence_dir: Path) -> dict[str, object]:
    identities = load_top30(evidence_dir / TOP30_CSV)
    rated = confirmed_rated_targets(identities)

    replay = _load_json(evidence_dir / LEADER_REPLAY)
    episode = replay.get("episode")
    if not isinstance(episode, dict):
        raise OpponentPackError("leader replay manifest missing episode")
    agents = episode.get("agents")
    if not isinstance(agents, list):
        raise OpponentPackError("leader replay manifest missing agents")
    replay_submission_ids = {
        _plain_int(agent.get("submissionId"), field="leader replay submissionId")
        for agent in agents
        if isinstance(agent, dict)
    }
    replay_episode_id = _plain_int(episode.get("id"), field="leader replay episode id")

    loss_bank = _load_json(evidence_dir / LIVE_LOSS_BANK)
    losses = loss_bank.get("losses")
    if not isinstance(losses, list):
        raise OpponentPackError("live loss bank missing losses")
    loss_targets: list[dict[str, object]] = []
    for loss in losses:
        if not isinstance(loss, dict) or not isinstance(loss.get("opponent"), dict):
            raise OpponentPackError("malformed live loss record")
        opponent = loss["opponent"]
        seat = _plain_int(
            loss.get("titan_seat"), field="loss titan_seat", minimum=0
        )
        if seat not in (0, 1):
            raise OpponentPackError("loss titan_seat must be 0 or 1")
        loss_targets.append(
            {
                "episode_id": _plain_int(loss.get("episode_id"), field="loss episode_id"),
                "seed": _plain_int(loss.get("seed"), field="loss seed", minimum=0),
                "titan_seat": seat,
                "opponent_name": str(opponent.get("name", "")).strip(),
                "submission_id": _plain_int(
                    opponent.get("submission_id"), field="loss opponent submission_id"
                ),
                "provenance": "exact_public_loss_episode",
            }
        )

    ambiguous = [
        {
            "rank": item.rank,
            "team_id": item.team_id,
            "team_name": item.team_name,
            "leaderboard_score": item.leaderboard_score,
            "fallback_submission_id": item.target_submission_id,
            "status": "identity_unconfirmed_not_competitive",
        }
        for item in identities
        if not item.identity_confirmed
    ]

    targets: list[dict[str, object]] = []
    for item in rated:
        targets.append(
            {
                "rank": item.rank,
                "team_id": item.team_id,
                "team_name": item.team_name,
                "leaderboard_score": item.leaderboard_score,
                "rated_submission_id": item.target_submission_id,
                "latest_submission_id": item.latest_submission_id,
                "latest_public_score": item.latest_public_score,
                "rated_is_latest": item.target_is_latest,
                "identity_basis": item.target_basis,
                "latest_drifted": item.latest_drifted,
                "materialization": (
                    {
                        "kind": "public_action_replay_manifest",
                        "episode_id": replay_episode_id,
                        "payload_in_repo": False,
                    }
                    if item.target_submission_id in replay_submission_ids
                    else {
                        "kind": "public_submission_identity",
                        "payload_in_repo": False,
                    }
                ),
            }
        )

    return {
        "schema_version": 1,
        "kind": "titan-v5-frontier-opponent-pack",
        "policy": {
            "competitive_identity": "unique leaderboard-score-matched public submission only",
            "never_substitute_latest": True,
            "minimum_frontier_score": "3000",
            "executable_code_claimed": False,
            "approximation_allowed": False,
        },
        "sources": {
            "top30_targets": TOP30_CSV,
            "leader_replay_manifest": LEADER_REPLAY,
            "live_loss_bank": LIVE_LOSS_BANK,
        },
        "frontier_targets": targets,
        "exact_live_loss_rematches": loss_targets,
        "ambiguous_targets": ambiguous,
    }


def validate_pack(evidence_dir: Path, manifest_path: Path | None = None) -> dict[str, object]:
    built = build_pack(evidence_dir)
    expected_ids = [56156662, 56161578, 56145462, 56161402, 56114097, 56097405]
    actual_ids = [item["rated_submission_id"] for item in built["frontier_targets"]]
    if actual_ids != expected_ids:
        raise OpponentPackError(
            f"3000+ frontier identity drift: expected {expected_ids}, got {actual_ids}"
        )
    identities = load_top30(evidence_dir / TOP30_CSV)
    confirmed = [item for item in identities if item.identity_confirmed]
    if len(confirmed) != 28:
        raise OpponentPackError(f"expected 28 confirmed score matches, got {len(confirmed)}")
    drifted = [item for item in confirmed if item.latest_drifted]
    if len(drifted) != 14:
        raise OpponentPackError(f"expected 14 rated-vs-latest drifts, got {len(drifted)}")
    ambiguous_ranks = [item["rank"] for item in built["ambiguous_targets"]]
    if ambiguous_ranks != [18, 30]:
        raise OpponentPackError(
            f"ambiguity set drift: expected [18, 30], got {ambiguous_ranks}"
        )
    if manifest_path is not None:
        saved = _load_json(manifest_path)
        if saved != built:
            raise OpponentPackError(
                f"{manifest_path.name} is stale; regenerate from saved evidence"
            )
    return built


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--evidence-dir",
        type=Path,
        default=Path(__file__).resolve().parent,
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate the checked-in frontier-opponent-pack.json",
    )
    args = parser.parse_args(argv)
    manifest_path = args.evidence_dir / PACK_MANIFEST if args.check else None
    pack = validate_pack(args.evidence_dir, manifest_path)
    if not args.check:
        print(json.dumps(pack, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
