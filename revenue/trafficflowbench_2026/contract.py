from __future__ import annotations

import hashlib
import json
from types import MappingProxyType
from typing import Mapping

UPSTREAM = MappingProxyType({
    "repository": "jacky850/trafficflowbench-public",
    "commit": "c88cddf533bbf0afa4ff1fc6c031d760a08e7a31",
    "verified_at_utc": "2026-09-17T06:56:00Z",
    "license": "MIT",
    "files": MappingProxyType({
        "README.md": "3e32eb8ced22de82e0d2cb1934dda6ef020c7c09",
        "docs/BASELINES.md": "1b101bfe408c40b596bee66d612f509a6e6c15a8",
        "docs/SCORING_SPEC.md": "74f15b3c94ccf0223a278e544ecfe260ff371e00",
        "docs/SUBMISSION_SCHEMAS.md": "63bfd21ae5abf2760d5adbdf2f26a185b6e08b6a",
        "src/merge_submissions.py": "971ff17a072e403cc47f7b875105c71f53bf83d9",
        "src/task1/score_task1.py": "bd5f2e90aae342cdaffa4e406cbe67597176c9eb",
        "src/task2/score_task2.py": "cdcba00326eb7ebb832a020147b3f89b93a1d9ec",
        "src/task3/score_task3.py": "afb0d1f6f8bf845b78e0ab232d01f47d2629166a",
        "src/task4/score_task4.py": "9cfe8df0ac0764d6599057610a625f86b742bb3d",
    }),
    "task_weights": MappingProxyType({"state": 0.35, "queue": 0.30, "physics": 0.15, "odme": 0.20}),
    "deadline": "2026-11-06",
    "advertised_prize_pool_usd": 3500,
    "release_class": "PUBLIC_SYNTHETIC_CONTRACT_ONLY",
    "task4_prior_rule": "use the split-local task4/<panel>/<split>/synthetic_weak_prior.csv",
})

_FALSE_AUTHORITY = (
    "kaggleJoined",
    "rulesAccepted",
    "competitionDataAcquired",
    "submissionSent",
    "officialScoreEstablished",
    "leaderboardRankEstablished",
    "prizeAwarded",
    "paymentReceived",
    "revenueRecognized",
)


def authority_ceiling() -> dict[str, bool | str]:
    ceiling: dict[str, bool | str] = {name: False for name in _FALSE_AUTHORITY}
    ceiling["evidenceClass"] = "PUBLIC_OR_LOCAL_SYNTHETIC_ONLY"
    return ceiling


def _plain(value):
    if isinstance(value, Mapping):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    return value


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(_plain(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def contract_receipt() -> dict[str, object]:
    body = {
        "schema": "trafficflowbench-public-contract/v1",
        "upstream": _plain(UPSTREAM),
        "authority": authority_ceiling(),
        "notes": [
            "Task 3 has no independent submission; it is derived from Task 1 state outputs.",
            "The pinned upstream generation includes the 2026-09-11 split-local Task 4 prior correction.",
            "Local scorer mirrors are diagnostics unless run against an organizer-authorized split with its exact assets.",
        ],
    }
    body["receiptSha256"] = hashlib.sha256(canonical_json_bytes(body)).hexdigest()
    return body


def validate_authority_claims(claims: Mapping[str, object]) -> None:
    unknown = sorted(set(claims) - set(authority_ceiling()))
    if unknown:
        raise ValueError(f"unknown authority fields: {unknown}")
    for key in _FALSE_AUTHORITY:
        if claims.get(key, False) is not False:
            raise ValueError(f"source-safe carrier cannot assert {key}=true")
    evidence = claims.get("evidenceClass", "PUBLIC_OR_LOCAL_SYNTHETIC_ONLY")
    if evidence not in {"PUBLIC_OR_LOCAL_SYNTHETIC_ONLY", "LOCAL_SYNTHETIC", "PUBLIC_CONTRACT"}:
        raise ValueError(f"unsupported evidenceClass: {evidence!r}")
