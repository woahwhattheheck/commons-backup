# SPDX-License-Identifier: Apache-2.0
"""Source-pinned bounded identifiability oracle for Kaggriculture EOD weed RNG.

Research-only tooling for the one canonical TITAN V4. This module does not
modify policy/runtime/defaults and never treats bounded-domain uniqueness as
proof that the hidden episode seed is globally identifiable.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import sys
import types
from pathlib import Path
from typing import Sequence

ENGINE_SHA256 = "bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e"
_HERE = Path(__file__).resolve()
_LAB_ROOT = _HERE.parents[4] if len(_HERE.parents) > 4 else _HERE.parent
DEFAULT_ENGINE = _LAB_ROOT / "reference" / "engine" / "kaggriculture.py"
DEFAULT_WEED_CHANCE = 0.005
DEFAULT_BOARD_SIZE = 10
SEED_MULTIPLIER = 1_000_003


def _load_engine(path: Path):
    raw = path.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != ENGINE_SHA256:
        raise ValueError(f"official engine identity mismatch: {actual}")
    source = raw.decode("utf-8")
    required = (
        'state[i].observation.farms = farms',
        'rng = random.Random((seed * 1_000_003) ^ day)',
        'if farm["tiles"][y][x] is None and rng.random() < weed_chance:',
    )
    missing = [anchor for anchor in required if anchor not in source]
    if missing:
        raise ValueError(f"authenticated engine missing required semantics: {missing}")

    package = types.ModuleType("kaggle_environments")
    utils = types.ModuleType("kaggle_environments.utils")
    utils.resolve_episode_seed = lambda env: env.info.get("seed", 0)
    old_pkg = sys.modules.get("kaggle_environments")
    old_utils = sys.modules.get("kaggle_environments.utils")
    sys.modules["kaggle_environments"] = package
    sys.modules["kaggle_environments.utils"] = utils
    try:
        module = types.ModuleType("_seedident_engine")
        module.__file__ = str(path)
        module.__package__ = ""
        code = compile(raw, str(path), "exec", dont_inherit=True)
        exec(code, module.__dict__, module.__dict__)
        return module
    finally:
        if old_pkg is None:
            sys.modules.pop("kaggle_environments", None)
        else:
            sys.modules["kaggle_environments"] = old_pkg
        if old_utils is None:
            sys.modules.pop("kaggle_environments.utils", None)
        else:
            sys.modules["kaggle_environments.utils"] = old_utils


def initial_empty_positions(engine, board_size: int = DEFAULT_BOARD_SIZE):
    """Return source-real day-0 empty positions in exact farm/y/x RNG scan order."""
    farm = engine._new_farm(board_size, 3000)
    return tuple(
        (y, x)
        for y in range(board_size)
        for x in range(board_size)
        if farm["tiles"][y][x] is None
    )


def weed_bits_for_seed(seed: int, *, day: int, empty_counts: Sequence[int], weed_chance: float):
    """Model exact threshold bits consumed by `_spawn_weeds`, farm by farm."""
    if not 0.0 <= weed_chance <= 1.0:
        raise ValueError("weed_chance must be in [0, 1]")
    if any(n < 0 for n in empty_counts):
        raise ValueError("empty_counts must be non-negative")
    rng = random.Random((int(seed) * SEED_MULTIPLIER) ^ int(day))
    return tuple(rng.random() < weed_chance for n in empty_counts for _ in range(n))


def candidate_seeds(observed_bits: Sequence[bool], *, seed_start: int, seed_stop: int,
                    day: int, empty_counts: Sequence[int], weed_chance: float):
    """Enumerate matching seeds only inside an explicitly bounded candidate domain."""
    if seed_start < 0 or seed_stop <= seed_start:
        raise ValueError("seed domain must satisfy 0 <= start < stop")
    expected = sum(empty_counts)
    bits = tuple(bool(x) for x in observed_bits)
    if len(bits) != expected:
        raise ValueError(f"observed_bits has {len(bits)} bits; expected {expected}")
    return [
        seed for seed in range(seed_start, seed_stop)
        if weed_bits_for_seed(seed, day=day, empty_counts=empty_counts,
                              weed_chance=weed_chance) == bits
    ]


def bernoulli_entropy_bits(p: float) -> float:
    if not 0.0 <= p <= 1.0:
        raise ValueError("p must be in [0, 1]")
    if p in (0.0, 1.0):
        return 0.0
    return -(p * math.log2(p) + (1.0 - p) * math.log2(1.0 - p))


def pattern_probability(bits: Sequence[bool], p: float) -> float:
    ones = sum(bool(x) for x in bits)
    zeros = len(bits) - ones
    return (p ** ones) * ((1.0 - p) ** zeros)


def _parse_bits(text: str) -> tuple[bool, ...]:
    compact = "".join(ch for ch in text if ch not in " ,_\t\n")
    if not compact or any(ch not in "01" for ch in compact):
        raise ValueError("observed bits must contain only 0/1 separators")
    return tuple(ch == "1" for ch in compact)


def _parse_empty_counts(text: str) -> tuple[int, int]:
    parts = [part.strip() for part in text.split(",") if part.strip()]
    if len(parts) != 2:
        raise ValueError("empty counts must provide exactly two comma-separated farms")
    counts = tuple(int(part) for part in parts)
    if any(n < 0 for n in counts):
        raise ValueError("empty counts must be non-negative")
    return counts


def bounded_verdict(candidate_count: int) -> str:
    if candidate_count == 0:
        return "NO_MATCH_IN_BOUNDED_DOMAIN"
    if candidate_count == 1:
        return "BOUNDED_UNIQUE_NOT_GLOBAL"
    return "AMBIGUOUS_IN_BOUNDED_DOMAIN"


def run(engine_path: Path, *, seed_start: int = 0, seed_stop: int = 65536,
        day: int = 0, weed_chance: float = DEFAULT_WEED_CHANCE,
        true_seed: int = 1, observed_bits: Sequence[bool] | None = None,
        empty_counts: Sequence[int] | None = None):
    engine = _load_engine(engine_path)
    per_farm = len(initial_empty_positions(engine))
    if empty_counts is None:
        empty_counts = (per_farm, per_farm)
    else:
        empty_counts = tuple(int(n) for n in empty_counts)
        if len(empty_counts) != 2 or any(n < 0 for n in empty_counts):
            raise ValueError("empty_counts must contain exactly two non-negative farm counts")
    if observed_bits is None:
        observed_bits = weed_bits_for_seed(true_seed, day=day, empty_counts=empty_counts,
                                           weed_chance=weed_chance)
    observed_bits = tuple(observed_bits)
    matches = candidate_seeds(observed_bits, seed_start=seed_start, seed_stop=seed_stop,
                              day=day, empty_counts=empty_counts, weed_chance=weed_chance)
    n = len(observed_bits)
    entropy = n * bernoulli_entropy_bits(weed_chance)
    probability = pattern_probability(observed_bits, weed_chance)
    all_zero_probability = (1.0 - weed_chance) ** n
    return {
        "schema": "titan-v4-seed-identifiability/v1",
        "engine_sha256": ENGINE_SHA256,
        "source_semantics": {
            "both_farms_public": True,
            "rng_key": "(seed * 1000003) ^ day",
            "rng_draws_only_on_empty_tiles": True,
            "baseline_initial_empty_per_farm": per_farm,
            "modeled_pre_eod_empty_counts": list(empty_counts),
            "modeled_total_threshold_bits": n,
        },
        "observation": {
            "day": day,
            "weed_chance": weed_chance,
            "weed_count": sum(observed_bits),
            "pattern_probability_under_iid_threshold_model": probability,
            "all_zero_pattern_probability": all_zero_probability,
            "expected_shannon_information_bits": entropy,
        },
        "bounded_search": {
            "seed_start": seed_start,
            "seed_stop_exclusive": seed_stop,
            "domain_size": seed_stop - seed_start,
            "candidate_count": len(matches),
            "first_candidates": matches[:32],
            "verdict": bounded_verdict(len(matches)),
            "global_identifiability_proved": False,
        },
        "interpretation": {
            "turn1_omniscience_established": False,
            "reason": (
                "weed observations are Bernoulli threshold bits, not raw RNG outputs; "
                "candidate uniqueness must be proved over the actual complete seed domain"
            ),
            "production_seed_cracker_authorized": False,
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", type=Path, default=DEFAULT_ENGINE)
    parser.add_argument("--seed-start", type=int, default=0)
    parser.add_argument("--seed-stop", type=int, default=65536)
    parser.add_argument("--day", type=int, default=0)
    parser.add_argument("--weed-chance", type=float, default=DEFAULT_WEED_CHANCE)
    parser.add_argument("--true-seed", type=int, default=1)
    parser.add_argument("--observed-bits")
    parser.add_argument("--empty-counts", help="pre-EOD empty cells as farm0,farm1; default is authenticated no-expansion opening")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    bits = _parse_bits(args.observed_bits) if args.observed_bits is not None else None
    counts = _parse_empty_counts(args.empty_counts) if args.empty_counts is not None else None
    report = run(args.engine, seed_start=args.seed_start, seed_stop=args.seed_stop,
                 day=args.day, weed_chance=args.weed_chance, true_seed=args.true_seed,
                 observed_bits=bits, empty_counts=counts)
    text = json.dumps(report, sort_keys=True, indent=2) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
