#!/usr/bin/env python3
"""Fail-closed custody verifier for Kaggriculture episode 107983535.

This does not infer gameplay root cause. It authenticates replay identity and
creates a deterministic evidence envelope suitable for downstream autopsy.
"""
from __future__ import annotations
import argparse, hashlib, json, math
from pathlib import Path
from typing import Any, Mapping, Sequence

TARGET_EPISODE_ID = 107983535
SCHEMA_VERSION = "kuro0315-episode-custody/v1"

class ReplayError(ValueError):
    pass

def _finite_number(v: Any, label: str) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ReplayError(f"{label} must be numeric")
    f=float(v)
    if not math.isfinite(f):
        raise ReplayError(f"{label} must be finite")
    return f

def _episode_id(replay: Mapping[str, Any]) -> int:
    info = replay.get("info")
    info = info if isinstance(info, Mapping) else {}
    vals = [
        replay.get("episodeId"), replay.get("episode_id"),
        info.get("EpisodeId"), info.get("episodeId"), info.get("episode_id"),
    ]
    explicit = [v for v in vals if v is not None]
    if not explicit:
        legacy = replay.get("id")
        if isinstance(legacy, int) and not isinstance(legacy, bool):
            explicit=[legacy]
    clean=[]
    for v in explicit:
        if isinstance(v, bool) or not isinstance(v, int):
            raise ReplayError("episode id must be a non-boolean integer")
        clean.append(v)
    if not clean:
        raise ReplayError("numeric EpisodeId is missing")
    if len(set(clean)) != 1:
        raise ReplayError(f"conflicting episode ids: {clean}")
    return clean[0]

def _players(replay: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    steps = replay.get("steps")
    if not isinstance(steps, list) or len(steps) < 2:
        raise ReplayError("steps must contain at least two states")
    for t, raw_step in enumerate(steps):
        if not isinstance(raw_step, list) or len(raw_step) != 2:
            raise ReplayError(f"steps[{t}] must contain exactly two player states")
        for seat, state in enumerate(raw_step):
            if not isinstance(state, Mapping):
                raise ReplayError(f"steps[{t}][{seat}] must be an object")
            obs = state.get("observation")
            if not isinstance(obs, Mapping):
                raise ReplayError(f"steps[{t}][{seat}].observation must be an object")
            p = obs.get("player")
            if isinstance(p, bool) or not isinstance(p, int) or p != seat:
                raise ReplayError(f"steps[{t}][{seat}].observation.player must equal {seat}")
    return steps[-1]

def _reward(state: Mapping[str, Any], seat: int) -> float:
    return _finite_number(state.get("reward"), f"terminal reward seat {seat}")

def canonical_json(v: Any) -> bytes:
    return json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()

def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

def verify_replay_bytes(
    raw: bytes, *, candidate_seat: int | None = None,
    expected_margin: float | None = None
) -> dict[str, Any]:
    try:
        replay=json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ReplayError(f"invalid replay JSON: {e}") from e
    if not isinstance(replay, Mapping):
        raise ReplayError("replay root must be an object")
    episode_id=_episode_id(replay)
    if episode_id != TARGET_EPISODE_ID:
        raise ReplayError(f"expected episode {TARGET_EPISODE_ID}, got {episode_id}")
    terminal=_players(replay)
    rewards=[_reward(terminal[i], i) for i in (0,1)]
    if candidate_seat is not None:
        if isinstance(candidate_seat, bool) or candidate_seat not in (0,1):
            raise ReplayError("candidate_seat must be 0 or 1")
        margin=rewards[candidate_seat]-rewards[1-candidate_seat]
        if expected_margin is not None and not math.isclose(
            margin, _finite_number(expected_margin, "expected_margin"),
            rel_tol=0.0, abs_tol=1e-9
        ):
            raise ReplayError(f"candidate margin mismatch: expected {expected_margin}, got {margin}")
    else:
        if expected_margin is not None:
            raise ReplayError("expected_margin requires candidate_seat")
        margin=None
    info=replay.get("info") if isinstance(replay.get("info"), Mapping) else {}
    teams=info.get("TeamNames") or info.get("teams") or replay.get("teams")
    if not (isinstance(teams, list) and len(teams)==2 and all(isinstance(x,str) for x in teams)):
        teams=None
    payload={
        "schema_version": SCHEMA_VERSION,
        "status": "EVIDENCE_AUTHENTICATED",
        "episode_id": episode_id,
        "replay_sha256": sha256_bytes(raw),
        "replay_bytes": len(raw),
        "states": len(replay["steps"]),
        "terminal_rewards": rewards,
        "teams": teams,
        "candidate_seat": candidate_seat,
        "candidate_margin": margin,
        "root_cause": None,
        "authority": {
            "replay_identity_authenticated": True,
            "root_cause_established": False,
            "gameplay_change_authorized": False,
            "competition_submission_authorized": False,
        },
    }
    unsigned=dict(payload)
    payload["receipt_sha256"]=sha256_bytes(canonical_json(unsigned))
    return payload

def main(argv: Sequence[str] | None=None) -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("replay", type=Path)
    p.add_argument("--candidate-seat", type=int, choices=(0,1))
    p.add_argument("--expected-margin", type=float)
    p.add_argument("--output", type=Path)
    a=p.parse_args(argv)
    if a.expected_margin is not None and a.candidate_seat is None:
        p.error("--expected-margin requires --candidate-seat")
    receipt=verify_replay_bytes(
        a.replay.read_bytes(), candidate_seat=a.candidate_seat,
        expected_margin=a.expected_margin
    )
    text=json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False)+"\n"
    if a.output:
        a.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
