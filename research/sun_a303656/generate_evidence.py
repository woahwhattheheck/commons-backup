"""Regenerate the deterministic A303656 negative-evidence receipt."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path

from .modular import greedy_congruence_cover, local_census
from .oracle import find_witness

SCHEMA = "commons-sun-a303656-negative-evidence/v1"
SEED = 303656


def _smooth_numbers(limit: int, primes: tuple[int, ...]) -> tuple[int, ...]:
    values = {1}
    for p in primes:
        expanded: set[int] = set()
        for value in values:
            current = value
            while current <= limit:
                expanded.add(current)
                current *= p
        values = expanded
    return tuple(sorted(value for value in values if 2 <= value <= limit))


def build_receipt() -> dict[str, object]:
    moduli = sorted(
        set(range(2, 501))
        | set(_smooth_numbers(30_000, (2, 3, 5, 7, 11)))
    )
    census = local_census(moduli)
    census["modulusFamily"] = (
        "all 2..500 plus all 2,3,5,7,11-smooth moduli <=30000"
    )

    cover = greedy_congruence_cover(160, 110, 5000)
    cover["meaning"] = (
        "Each selected prime p=3 mod 4 is assigned one residue n mod p. "
        "Covered exponent pairs satisfy p | n-3^c-5^d; odd p-adic "
        "valuation is not established. Uncovered pairs prevent this finite "
        "recipe from certifying a counterexample."
    )

    rng = random.Random(SEED)
    witness_stats: list[dict[str, object]] = []
    for scale in (10**9, 10**12, 10**15, 10**18):
        rows: list[tuple[int, int, int]] = []
        for _ in range(250):
            n = scale + rng.randrange(scale)
            witness = find_witness(n)
            if witness is None:
                raise RuntimeError(f"no witness for sampled n={n}")
            witness.verify(n)
            rows.append((n, witness.c, witness.d))
        witness_stats.append(
            {
                "scale": scale,
                "sampleCount": len(rows),
                "allRepresented": True,
                "maximumC": max(c for _, c, _ in rows),
                "maximumD": max(d for _, _, d in rows),
                "sampleInputSha256": hashlib.sha256(
                    "\n".join(str(n) for n, _, _ in rows).encode("ascii")
                ).hexdigest(),
            }
        )

    return {
        "schema": SCHEMA,
        "claimBoundary": {
            "proof": False,
            "counterexample": False,
            "meaning": (
                "Finite exact computation and a failed covering search only; "
                "this receipt does not settle A303656."
            ),
        },
        "localObstructionCensus": census,
        "oneResiduePerPrimeGreedyCover": cover,
        "seededWitnessSamples": witness_stats,
        "seed": SEED,
    }


def render_receipt(receipt: dict[str, object]) -> bytes:
    return (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode("utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).with_name("evidence") / "negative_evidence_v1.json",
    )
    args = parser.parse_args(argv)
    payload = render_receipt(build_receipt())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(payload)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "sha256": hashlib.sha256(payload).hexdigest(),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
