#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Bounded multi-day public inference for Kaggriculture's EOD RNG stream.

Research-only. It never treats bounded-domain uniqueness as global seed recovery,
and forecasts only outcomes shared by every surviving bounded candidate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path
from typing import Sequence

ENGINE_SHA256 = "bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e"
ENGINE_GIT_BLOB = "3c202c7ee921da239356789e266b694635103fc4"
SEED_IDENTIFIABILITY_GIT_BLOB = "19ce8936451a20dbf0eaa9944b8a918f41fb3cbc"
SEED_MULTIPLIER = 1_000_003
DEFAULT_WEED_CHANCE = 0.005
DEFAULT_SHOP_UNLOCK_INTERVAL = 3
DEFAULT_MAX_SHOP_INSTANCES = 8
SHOP_NAMES = (
    "BAKERY", "BRUNCH_SPOT", "FARMERS_MARKET", "ICE_CREAM_SHOP",
    "PET_CAFE", "PIZZA_SHOP", "SMOOTHIE_SHOP", "YARN_STORE",
)
HERE = Path(__file__).resolve()
LAB_ROOT = HERE.parents[4] if len(HERE.parents) > 4 else HERE.parent
DEFAULT_ENGINE = LAB_ROOT / "reference" / "engine" / "kaggriculture.py"


class EvidenceError(ValueError):
    pass


def _blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def authenticate_engine(path: Path) -> dict:
    """Single-read bind the exact engine bytes and required source chronology."""
    raw = path.read_bytes()
    sha256, blob = hashlib.sha256(raw).hexdigest(), _blob(raw)
    if (sha256, blob) != (ENGINE_SHA256, ENGINE_GIT_BLOB):
        raise EvidenceError(f"engine identity mismatch: {sha256}/{blob}")
    text = raw.decode("utf-8")
    anchors = (
        'rng = random.Random((seed * 1_000_003) ^ day)',
        'if farm["tiles"][y][x] is None and rng.random() < weed_chance:',
        'for player_id, farm in enumerate(obs0.farms):',
        'town["unlocked_shops"].append(rng.choice(sorted(SHOPS)))',
    )
    if any(anchor not in text for anchor in anchors):
        raise EvidenceError("authenticated engine missing required RNG chronology")
    return {"sha256": sha256, "git_blob": blob}


def _plain_int(value, name: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise EvidenceError(f"{name} must be a plain int >= {minimum}")
    return value


def _prob(value) -> float:
    if type(value) not in (int, float) or isinstance(value, bool):
        raise EvidenceError("weed_chance must be numeric")
    value = float(value)
    if not 0.0 <= value <= 1.0:
        raise EvidenceError("weed_chance must be in [0,1]")
    return value


def _shops(value, name: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise EvidenceError(f"{name} must be a list/tuple")
    out = tuple(value)
    if any(type(x) is not str or x not in SHOP_NAMES for x in out):
        raise EvidenceError(f"{name} contains unknown shop")
    return out


def _counts(value) -> tuple[int, int]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise EvidenceError("empty_counts must contain two farms")
    return (_plain_int(value[0], "empty_counts[0]"), _plain_int(value[1], "empty_counts[1]"))


def _draw_expected(day: int, before_count: int, interval: int, cap: int) -> bool:
    day = _plain_int(day, "day")
    before_count = _plain_int(before_count, "shop count")
    interval = _plain_int(interval, "shop interval", 1)
    cap = _plain_int(cap, "shop cap")
    return (day + 1) % interval == 0 and before_count < cap


def normalize_evidence(row: dict, *, interval=DEFAULT_SHOP_UNLOCK_INTERVAL,
                       cap=DEFAULT_MAX_SHOP_INSTANCES) -> dict:
    if type(row) is not dict:
        raise EvidenceError("history row must be an object")
    day = _plain_int(row.get("day"), "day")
    counts = _counts(row.get("empty_counts"))
    bits = row.get("weed_bits")
    if not isinstance(bits, (list, tuple)) or len(bits) != sum(counts):
        raise EvidenceError("weed_bits length must equal public pre-EOD empty cells")
    if any(type(bit) is not bool for bit in bits):
        raise EvidenceError("weed_bits must contain literal booleans")
    before, after = _shops(row.get("shops_before"), "shops_before"), _shops(row.get("shops_after"), "shops_after")
    draw = _draw_expected(day, len(before), interval, cap)
    if draw:
        if len(after) != len(before) + 1 or after[:-1] != before:
            raise EvidenceError("expected exactly one public shop append")
        appended = after[-1]
    else:
        if after != before:
            raise EvidenceError("shop history changed outside authenticated draw schedule")
        appended = None
    return {"day": day, "empty_counts": counts, "weed_bits": tuple(bits),
            "shops_before": before, "shops_after": after, "appended_shop": appended}


def evidence_from_public_snapshots(*, day: int, farms_before, farms_after,
                                   shops_before, shops_after, board_size: int = 10) -> dict:
    board_size = _plain_int(board_size, "board_size", 1)
    if not isinstance(farms_before, (list, tuple)) or len(farms_before) != 2 or not isinstance(farms_after, (list, tuple)) or len(farms_after) != 2:
        raise EvidenceError("both public farms are required")
    bits, counts = [], []
    for index in range(2):
        b, a = farms_before[index].get("tiles"), farms_after[index].get("tiles")
        if not isinstance(b, list) or not isinstance(a, list) or len(b) != board_size or len(a) != board_size:
            raise EvidenceError("invalid public farm grid")
        count = 0
        for y in range(board_size):
            if len(b[y]) != board_size or len(a[y]) != board_size:
                raise EvidenceError("invalid public farm row")
            for x in range(board_size):
                if b[y][x] is None:
                    count += 1
                    post = a[y][x]
                    if post is None:
                        bits.append(False)
                    elif type(post) is dict and post.get("kind") == "WEED":
                        bits.append(True)
                    else:
                        raise EvidenceError("unexplained empty-tile transition at EOD")
        counts.append(count)
    return normalize_evidence({"day": day, "empty_counts": counts, "weed_bits": bits,
                               "shops_before": shops_before, "shops_after": shops_after})


def signature(seed: int, row: dict, *, weed_chance=DEFAULT_WEED_CHANCE) -> tuple[tuple[bool, ...], str | None]:
    seed = _plain_int(seed, "seed")
    row = normalize_evidence(row)
    chance = _prob(weed_chance)
    rng = random.Random((seed * SEED_MULTIPLIER) ^ row["day"])
    bits = tuple(rng.random() < chance for _ in range(sum(row["empty_counts"])))
    shop = rng.choice(SHOP_NAMES) if _draw_expected(row["day"], len(row["shops_before"]), DEFAULT_SHOP_UNLOCK_INTERVAL, DEFAULT_MAX_SHOP_INSTANCES) else None
    return bits, shop


def candidate_seeds_history(history: Sequence[dict], *, seed_start: int, seed_stop: int,
                            weed_chance=DEFAULT_WEED_CHANCE) -> dict:
    seed_start, seed_stop = _plain_int(seed_start, "seed_start"), _plain_int(seed_stop, "seed_stop", 1)
    if seed_stop <= seed_start:
        raise EvidenceError("seed domain must satisfy start < stop")
    if not isinstance(history, (list, tuple)) or not history:
        raise EvidenceError("history must be non-empty")
    rows = [normalize_evidence(row) for row in history]
    for left, right in zip(rows, rows[1:]):
        if right["day"] != left["day"] + 1:
            raise EvidenceError("history days must be contiguous")
        if left["shops_after"] != right["shops_before"]:
            raise EvidenceError("public shop history must join exactly")
    candidates = list(range(seed_start, seed_stop))
    counts = []
    for row in rows:
        observed = row["weed_bits"], row["appended_shop"]
        candidates = [seed for seed in candidates if signature(seed, row, weed_chance=weed_chance) == observed]
        counts.append({"day": row["day"], "candidate_count": len(candidates), "first_candidates": candidates[:16]})
        if not candidates:
            break
    verdict = "NO_MATCH_IN_BOUNDED_DOMAIN" if not candidates else "BOUNDED_UNIQUE_NOT_GLOBAL" if len(candidates) == 1 else "AMBIGUOUS_IN_BOUNDED_DOMAIN"
    return {"seed_start": seed_start, "seed_stop_exclusive": seed_stop, "domain_size": seed_stop-seed_start,
            "survivor_counts": counts, "candidates": candidates, "candidate_count": len(candidates),
            "verdict": verdict, "global_identifiability_proved": False,
            "production_seed_cracker_authorized": False}


def consensus_forecast(candidates: Sequence[int], *, day: int, empty_counts, shops_before,
                       weed_chance=DEFAULT_WEED_CHANCE) -> dict:
    if not isinstance(candidates, (list, tuple)) or not candidates:
        raise EvidenceError("forecast requires surviving candidates")
    if len(set(candidates)) != len(candidates):
        raise EvidenceError("candidate seeds must be unique")
    counts, before = _counts(empty_counts), _shops(shops_before, "shops_before")
    day = _plain_int(day, "day")
    template = {"day": day, "empty_counts": counts, "weed_bits": [False]*sum(counts),
                "shops_before": before, "shops_after": list(before)}
    draw = _draw_expected(day, len(before), DEFAULT_SHOP_UNLOCK_INTERVAL, DEFAULT_MAX_SHOP_INSTANCES)
    if draw:
        template["shops_after"] = list(before) + [SHOP_NAMES[0]]
    preds = [signature(_plain_int(seed, "candidate seed"), template, weed_chance=weed_chance) for seed in candidates]
    bitset, shops = {p[0] for p in preds}, {p[1] for p in preds}
    bits_agree, shop_agrees = len(bitset) == 1, len(shops) == 1
    bits = next(iter(bitset)) if bits_agree else None
    return {"candidate_count": len(candidates), "day": day, "shop_draw_expected": draw,
            "weed_bits_agree": bits_agree, "weed_bits": list(bits) if bits is not None else None,
            "shop_agrees": shop_agrees, "shop": next(iter(shops)) if shop_agrees else None,
            "full_public_signature_agrees": bits_agree and shop_agrees,
            "authority": "BOUNDED_CANDIDATE_CONSENSUS_ONLY", "single_seed_guess_used": False,
            "global_identifiability_proved": False}


def synthetic_history(seed: int, *, days: int, empty_counts=(25, 25), weed_chance=DEFAULT_WEED_CHANCE, shops=SHOP_NAMES) -> list[dict]:
    seed, days = _plain_int(seed, "seed"), _plain_int(days, "days", 1)
    if tuple(shops) != SHOP_NAMES:
        raise EvidenceError("shops must match authenticated sorted engine shop order")
    counts, town, out = list(_counts(empty_counts)), [], []
    chance = _prob(weed_chance)
    for day in range(days):
        before = list(town)
        rng = random.Random((seed * SEED_MULTIPLIER) ^ day)
        left = tuple(rng.random() < chance for _ in range(counts[0]))
        right = tuple(rng.random() < chance for _ in range(counts[1]))
        if _draw_expected(day, len(town), DEFAULT_SHOP_UNLOCK_INTERVAL, DEFAULT_MAX_SHOP_INSTANCES):
            town.append(rng.choice(SHOP_NAMES))
        out.append({"day": day, "empty_counts": list(counts), "weed_bits": list(left+right),
                    "shops_before": before, "shops_after": list(town)})
        counts[0] -= sum(left); counts[1] -= sum(right)
    return out


synthetic_public_history = synthetic_history


def run(*, seed_start: int, seed_stop: int, history: Sequence[dict], weed_chance=DEFAULT_WEED_CHANCE) -> dict:
    bounded = candidate_seeds_history(history, seed_start=seed_start, seed_stop=seed_stop, weed_chance=weed_chance)
    return {"schema": "titan.v4.seed-stream-identifiability/v1", "engine_sha256": ENGINE_SHA256,
            "engine_git_blob": ENGINE_GIT_BLOB, "predecessor_seed_identifiability_git_blob": SEED_IDENTIFIABILITY_GIT_BLOB,
            "evidence_authority": "PUBLIC_EOD_ONLY", "bounded_search": bounded,
            "decision_authority": False, "runtime_mutation_authority": False, "global_identifiability_proved": False}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", type=Path, default=DEFAULT_ENGINE)
    parser.add_argument("--history", type=Path)
    parser.add_argument("--seed-start", type=int, default=0)
    parser.add_argument("--seed-stop", type=int, default=65536)
    parser.add_argument("--true-seed", type=int, default=1)
    parser.add_argument("--days", type=int, default=3)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    authenticate_engine(args.engine)
    history = json.loads(args.history.read_text()) if args.history else synthetic_history(args.true_seed, days=args.days)
    report = run(seed_start=args.seed_start, seed_stop=args.seed_stop, history=history)
    report["history_rows"] = len(history)
    text = json.dumps(report, sort_keys=True, indent=2) + "\n"
    if args.output: args.output.write_text(text)
    else: print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
