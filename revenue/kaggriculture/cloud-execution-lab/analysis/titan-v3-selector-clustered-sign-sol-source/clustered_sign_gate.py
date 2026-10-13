#!/usr/bin/env python3
"""Cluster-aware sign consistency gate for paired TITAN game panels.

A mirrored player-position panel is a matched-pair experiment.  Treating those
two position rows as independent Bernoulli sign draws creates
pseudo-replication whenever the pair shares a seed/opponent state path.  This
module validates the literal paired grid, reports the naive cell tail for
diagnosis, and makes its decision from declared clusters.  The conservative
default uses ``seed`` as the experimental unit while also retaining
``(opponent, seed)`` sensitivity.

This is an evidence classifier only.  It never loads or mutates an agent.
"""
from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from fractions import Fraction
from pathlib import Path
from statistics import fmean, median
from typing import Any, Iterable, Mapping, Sequence

SCHEMA_VERSION = 1
DEFAULT_ALPHA = Fraction(1, 20)  # 5%


class EvidenceError(ValueError):
    """Raised when a panel cannot support a fail-closed classification."""


def _number(value: Any, *, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EvidenceError(f"{field} must be a finite JSON number")
    result = float(value)
    if not math.isfinite(result):
        raise EvidenceError(f"{field} must be finite")
    return result


def _integer(value: Any, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise EvidenceError(f"{field} must be an integer")
    return value


def _fraction_receipt(value: Fraction) -> dict[str, Any]:
    return {
        "numerator": value.numerator,
        "denominator": value.denominator,
        "decimal": float(value),
    }


def exact_upper_sign_tail(positive: int, negative: int) -> Fraction:
    """Return P[X >= positive] for X~Binomial(positive+negative, 1/2).

    Ties are excluded before this function is called.  The exact rational form
    is retained so threshold decisions do not depend on floating-point roundoff.
    """
    positive = _integer(positive, field="positive")
    negative = _integer(negative, field="negative")
    if positive < 0 or negative < 0:
        raise EvidenceError("sign counts must be nonnegative")
    trials = positive + negative
    if trials == 0:
        return Fraction(1, 1)
    return Fraction(sum(math.comb(trials, k) for k in range(positive, trials + 1)), 2**trials)


def _normalized_rows(payload: Mapping[str, Any] | Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    raw: Any = payload.get("rows") if isinstance(payload, Mapping) else payload
    if not isinstance(raw, list) or not raw:
        raise EvidenceError("input must contain a nonempty rows list")

    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, int, int]] = set()
    for index, value in enumerate(raw):
        if not isinstance(value, Mapping):
            raise EvidenceError(f"row {index} must be an object")
        opponent = value.get("opponent")
        if not isinstance(opponent, str) or not opponent:
            raise EvidenceError(f"row {index} opponent must be a nonempty string")
        seed = _integer(value.get("seed"), field=f"row {index} seed")
        seat = _integer(value.get("seat"), field=f"row {index} seat")
        if seat not in (0, 1):
            raise EvidenceError(f"row {index} seat must be 0 or 1")
        key = (opponent, seed, seat)
        if key in seen:
            raise EvidenceError(f"duplicate paired cell {key!r}")
        seen.add(key)

        own_delta = _number(value.get("own_delta"), field=f"row {index} own_delta")
        rival_delta = _number(value.get("rival_delta", 0), field=f"row {index} rival_delta")
        margin_delta = _number(
            value.get("margin_delta", own_delta - rival_delta),
            field=f"row {index} margin_delta",
        )
        if not math.isclose(margin_delta, own_delta - rival_delta, rel_tol=0.0, abs_tol=1e-9):
            raise EvidenceError(f"row {index} margin_delta is inconsistent with own-rival")

        changed = value.get("candidate_action_changed")
        if changed is not None and not isinstance(changed, bool):
            raise EvidenceError(f"row {index} candidate_action_changed must be boolean")
        if (own_delta != 0 or rival_delta != 0) and changed is not True:
            raise EvidenceError(
                f"row {index} has a score delta without candidate-action activation"
            )
        rows.append(
            {
                "opponent": opponent,
                "seed": seed,
                "seat": seat,
                "own_delta": own_delta,
                "rival_delta": rival_delta,
                "margin_delta": margin_delta,
                "candidate_action_changed": bool(changed),
            }
        )

    by_pair: dict[tuple[str, int], set[int]] = defaultdict(set)
    for row in rows:
        by_pair[(row["opponent"], row["seed"])].add(row["seat"])
    incomplete = sorted((opponent, seed, sorted(seats)) for (opponent, seed), seats in by_pair.items() if seats != {0, 1})
    if incomplete:
        raise EvidenceError(f"mirrored-seat grid is incomplete: {incomplete!r}")
    return rows


def _sign(value: float) -> int:
    return 1 if value > 0 else -1 if value < 0 else 0


def _cluster_summary(rows: Iterable[Mapping[str, Any]], fields: tuple[str, ...]) -> dict[str, Any]:
    groups: dict[tuple[Any, ...], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[tuple(row[field] for field in fields)].append(row)

    clusters: list[dict[str, Any]] = []
    for key in sorted(groups, key=lambda item: tuple(str(part) for part in item)):
        members = groups[key]
        own_values = [float(row["own_delta"]) for row in members]
        rival_values = [float(row["rival_delta"]) for row in members]
        margin_values = [float(row["margin_delta"]) for row in members]
        mean_own = fmean(own_values)
        clusters.append(
            {
                "key": list(key),
                "cells": len(members),
                "mean_own_delta": mean_own,
                "mean_rival_delta": fmean(rival_values),
                "mean_margin_delta": fmean(margin_values),
                "sign": _sign(mean_own),
                "positive_cells": sum(value > 0 for value in own_values),
                "negative_cells": sum(value < 0 for value in own_values),
                "zero_cells": sum(value == 0 for value in own_values),
            }
        )

    positive = sum(cluster["sign"] > 0 for cluster in clusters)
    negative = sum(cluster["sign"] < 0 for cluster in clusters)
    ties = sum(cluster["sign"] == 0 for cluster in clusters)
    tail = exact_upper_sign_tail(positive, negative)
    return {
        "cluster_fields": list(fields),
        "clusters": len(clusters),
        "positive_clusters": positive,
        "negative_clusters": negative,
        "tie_clusters": ties,
        "nonzero_clusters": positive + negative,
        "one_sided_exact_sign_tail": _fraction_receipt(tail),
        "rows": clusters,
    }


def _leave_one_seed_out(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seeds = sorted({row["seed"] for row in rows})
    result: list[dict[str, Any]] = []
    for seed in seeds:
        retained = [row for row in rows if row["seed"] != seed]
        if not retained:
            continue
        result.append(
            {
                "omitted_seed": seed,
                "cells": len(retained),
                "mean_own_delta": fmean(row["own_delta"] for row in retained),
                "mean_margin_delta": fmean(row["margin_delta"] for row in retained),
                "positive_cells": sum(row["own_delta"] > 0 for row in retained),
                "negative_cells": sum(row["own_delta"] < 0 for row in retained),
            }
        )
    return result


def analyze(
    payload: Mapping[str, Any] | Sequence[Mapping[str, Any]],
    *,
    alpha: Fraction = DEFAULT_ALPHA,
    provenance: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate and classify one mirrored panel.

    ``SIGN_SUPPORTED`` requires all of the following:

    * no negative own-cash cell;
    * at least one candidate-action activation and positive own-cash cell;
    * the exact upper sign tail passes at both opponent×seed and seed cluster
      levels.  The seed-level check is the final selector to avoid counting the
      same environment seed repeatedly across seats or opponents.

    Sparse clean evidence that does not clear the declared alpha is retained as
    ``MORE_EVIDENCE`` rather than being mislabeled as a regression.
    """
    if not isinstance(alpha, Fraction) or alpha <= 0 or alpha >= 1:
        raise EvidenceError("alpha must be a Fraction strictly between 0 and 1")
    rows = _normalized_rows(payload)

    cell_positive = sum(row["own_delta"] > 0 for row in rows)
    cell_negative = sum(row["own_delta"] < 0 for row in rows)
    cell_ties = len(rows) - cell_positive - cell_negative
    action_changed = sum(row["candidate_action_changed"] for row in rows)
    naive_tail = exact_upper_sign_tail(cell_positive, cell_negative)
    opponent_seed = _cluster_summary(rows, ("opponent", "seed"))
    seed = _cluster_summary(rows, ("seed",))

    seed_totals: dict[int, float] = defaultdict(float)
    for row in rows:
        seed_totals[row["seed"]] += max(0.0, row["own_delta"])
    positive_total = sum(seed_totals.values())
    largest_seed = max(seed_totals, key=seed_totals.get)
    largest_share = seed_totals[largest_seed] / positive_total if positive_total else 0.0
    zero_seed_count = sum(value == 0 for value in seed_totals.values())
    seed_count = len(seed_totals)
    all_zero_bootstrap = Fraction(zero_seed_count**seed_count, seed_count**seed_count)

    opponent_seed_tail = Fraction(
        opponent_seed["one_sided_exact_sign_tail"]["numerator"],
        opponent_seed["one_sided_exact_sign_tail"]["denominator"],
    )
    seed_tail = Fraction(
        seed["one_sided_exact_sign_tail"]["numerator"],
        seed["one_sided_exact_sign_tail"]["denominator"],
    )

    if cell_negative:
        verdict = "REGRESSION_SCREEN"
        reason = "at least one paired cell lowers candidate own cash"
    elif action_changed == 0 or cell_positive == 0:
        verdict = "NO_SIGNAL"
        reason = "no action-bound positive own-cash cell"
    elif opponent_seed_tail > alpha or seed_tail > alpha:
        verdict = "MORE_EVIDENCE"
        reason = (
            "clean positive evidence is underpowered after blocking mirrored seats "
            "and clustering repeated environment seeds"
        )
    else:
        verdict = "SIGN_SUPPORTED"
        reason = (
            "zero negative cells and both declared clustered sign gates pass; "
            "this is not gameplay-promotion authority"
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "verdict": verdict,
        "reason": reason,
        "alpha": _fraction_receipt(alpha),
        "experimental_unit": "seed",
        "seat_treatment": "blocked mirrored replicate, never an independent sign draw",
        "classification_scope": (
            "clustered own-cash sign consistency only; compose with causal, margin, "
            "outcome, current-base, and package gates before any promotion decision"
        ),
        "promotion_authority": False,
        "tail_assumption": (
            "exact binomial arithmetic is conditional on the declared seed clusters "
            "being defensible exchangeable independent sign units; the receipt does "
            "not manufacture that sampling assumption"
        ),
        "overall": {
            "cells": len(rows),
            "candidate_action_changed_cells": action_changed,
            "positive_cells": cell_positive,
            "negative_cells": cell_negative,
            "tie_cells": cell_ties,
            "mean_own_delta": fmean(row["own_delta"] for row in rows),
            "median_own_delta": median(row["own_delta"] for row in rows),
            "mean_margin_delta": fmean(row["margin_delta"] for row in rows),
            "naive_cell_sign_tail_diagnostic_only": _fraction_receipt(naive_tail),
        },
        "opponent_seed_sensitivity": opponent_seed,
        "seed_selector": seed,
        "concentration": {
            "seeds": seed_count,
            "nonzero_seeds": seed["nonzero_clusters"],
            "largest_positive_seed": largest_seed,
            "largest_positive_seed_share": largest_share,
            "all_zero_seed_cluster_bootstrap_probability": _fraction_receipt(all_zero_bootstrap),
            "bootstrap_2_5_percentile_is_zero": bool(
                cell_negative == 0 and all_zero_bootstrap >= Fraction(1, 40)
            ),
        },
        "leave_one_seed_out": _leave_one_seed_out(rows),
        "provenance": dict(provenance or {}),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path, help="JSON report containing a rows list")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--alpha-numerator", type=int, default=1)
    parser.add_argument("--alpha-denominator", type=int, default=20)
    parser.add_argument("--artifact-id")
    parser.add_argument("--artifact-sha256")
    parser.add_argument("--git-head")
    args = parser.parse_args(argv)

    payload = json.loads(args.report.read_text(encoding="utf-8"))
    provenance = {
        key: value
        for key, value in {
            "artifact_id": args.artifact_id,
            "artifact_sha256": args.artifact_sha256,
            "git_head": args.git_head,
            "source_report": args.report.name,
        }.items()
        if value is not None
    }
    receipt = analyze(
        payload,
        alpha=Fraction(args.alpha_numerator, args.alpha_denominator),
        provenance=provenance,
    )
    rendered = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rend="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
