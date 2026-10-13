# SPDX-License-Identifier: Apache-2.0
"""Complete-grid and seed-clustered admission for causal TITAN panels."""
from __future__ import annotations

import statistics
from typing import Any

from .strict import (
    REPORT_SCHEMA,
    SCHEMA,
    VERSION,
    EvidenceError,
    _integer,
    _mapping,
    _sequence,
    digest,
)
from .cell import analyze_cell
from .panel_support import (
    _aggregate,
    _experiment_config,
    _gate_config,
    _group,
    _mean,
    _panel_provenance,
    _positive_tail_p,
    seed_bank_sha256,
)

def analyze_panel(value: Any) -> dict[str, Any]:
    panel = _mapping(value, "panel")
    allowed = {
        "schema",
        "experiment",
        "expected_action_steps",
        "opponents",
        "seeds",
        "candidate_seats",
        "provenance",
        "gate",
        "cells",
    }
    if set(panel) != allowed:
        missing = sorted(allowed - set(panel))
        extra = sorted(set(panel) - allowed)
        raise EvidenceError(f"panel key mismatch; missing={missing}, extra={extra}")
    if panel.get("schema") != SCHEMA:
        raise EvidenceError(f"panel.schema must be {SCHEMA!r}")
    expected_actions = _integer(panel.get("expected_action_steps"), "expected_action_steps", minimum=1)
    opponents = list(_sequence(panel.get("opponents"), "opponents"))
    seeds = list(_sequence(panel.get("seeds"), "seeds"))
    seats = list(_sequence(panel.get("candidate_seats"), "candidate_seats"))
    if not opponents or any(not isinstance(name, str) or not name.strip() for name in opponents):
        raise EvidenceError("opponents must contain nonempty strings")
    if len(set(opponents)) != len(opponents):
        raise EvidenceError("opponents contains duplicates")
    normalized_seeds = [_integer(seed, f"seeds[{index}]", minimum=0) for index, seed in enumerate(seeds)]
    if len(set(normalized_seeds)) != len(normalized_seeds) or not normalized_seeds:
        raise EvidenceError("seeds must be nonempty and duplicate-free")
    normalized_seats = [_integer(seat, f"candidate_seats[{index}]") for index, seat in enumerate(seats)]
    if normalized_seats != [0, 1]:
        raise EvidenceError("candidate_seats must be exactly [0, 1]")
    experiment = _experiment_config(
        panel.get("experiment"),
        opponents=opponents,
        seeds=normalized_seeds,
        seats=normalized_seats,
    )
    provenance = _panel_provenance(panel.get("provenance"), opponents)
    gate = _gate_config(panel.get("gate"))

    raw_cells = _sequence(panel.get("cells"), "cells")
    expected_grid = {
        (opponent, seed, seat)
        for opponent in opponents
        for seed in normalized_seeds
        for seat in normalized_seats
    }
    if len(raw_cells) != len(expected_grid):
        raise EvidenceError(
            f"cells must cover the exact grid: expected {len(expected_grid)}, got {len(raw_cells)}"
        )
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, int, int]] = set()
    for index, cell in enumerate(raw_cells):
        try:
            row = analyze_cell(
                cell,
                expected_actions=expected_actions,
                panel_provenance=provenance,
            )
        except EvidenceError as exc:
            raise EvidenceError(f"cells[{index}]: {exc}") from exc
        key = (row["opponent"], row["seed"], row["candidate_seat"])
        if key in seen:
            raise EvidenceError(f"duplicate cell key: {key!r}")
        if key not in expected_grid:
            raise EvidenceError(f"unexpected cell key: {key!r}")
        seen.add(key)
        rows.append(row)
    missing = expected_grid - seen
    if missing:
        raise EvidenceError(f"missing cell keys: {sorted(missing)!r}")
    rows.sort(key=lambda row: (row["opponent"], row["seed"], row["candidate_seat"]))

    overall = _aggregate(rows)
    strata = _group(rows, ("opponent", "candidate_seat"))
    seed_groups = _group(rows, ("seed",))
    seed_own = [float(group["own_mean"]) for group in seed_groups]
    seed_margin = [float(group["margin_mean"]) for group in seed_groups]
    seed_summary = {
        "clusters": len(seed_groups),
        "own_mean_of_seed_means": _mean(seed_own),
        "own_median_of_seed_means": statistics.median(seed_own),
        "own_min_seed_mean": min(seed_own),
        "own_max_seed_mean": max(seed_own),
        "own_positive_seed_clusters": sum(value > 0 for value in seed_own),
        "own_negative_seed_clusters": sum(value < 0 for value in seed_own),
        "own_zero_seed_clusters": sum(value == 0 for value in seed_own),
        "own_effective_seed_clusters": sum(value != 0 for value in seed_own),
        "own_positive_tail_p": _positive_tail_p(seed_own),
        "margin_mean_of_seed_means": _mean(seed_margin),
        "margin_median_of_seed_means": statistics.median(seed_margin),
        "margin_min_seed_mean": min(seed_margin),
        "margin_max_seed_mean": max(seed_margin),
        "margin_positive_seed_clusters": sum(value > 0 for value in seed_margin),
        "margin_negative_seed_clusters": sum(value < 0 for value in seed_margin),
        "margin_zero_seed_clusters": sum(value == 0 for value in seed_margin),
        "margin_effective_seed_clusters": sum(value != 0 for value in seed_margin),
        "margin_positive_tail_p": _positive_tail_p(seed_margin),
    }

    failures: list[str] = []
    if overall["action_active_cells"] == 0:
        verdict = "INACTIVE"
    else:
        if overall["own_mean"] <= 0:
            failures.append("global own mean is not positive")
        if overall["margin_mean"] <= 0:
            failures.append("global margin mean is not positive")
        if overall["own_median"] < 0:
            failures.append("global own median is negative")
        if overall["own_positive"] < overall["own_negative"]:
            failures.append("negative own-cash cells outnumber positive cells")
        if overall["lost_wins"]:
            failures.append("at least one control win was lost")
        if overall["new_losses"]:
            failures.append("at least one new loss was introduced")
        for group in strata:
            label = f"opponent={group['opponent']},seat={group['candidate_seat']}"
            if group["own_mean"] < 0:
                failures.append(f"negative own mean in {label}")
            if group["margin_mean"] < 0:
                failures.append(f"negative margin mean in {label}")
            if group["outcome_balance"] < 0:
                failures.append(f"negative outcome balance in {label}")
        if seed_summary["own_min_seed_mean"] < gate["min_seed_own_mean"]:
            failures.append("seed-cluster own lower-tail floor failed")
        if seed_summary["margin_min_seed_mean"] < gate["min_seed_margin_mean"]:
            failures.append("seed-cluster margin lower-tail floor failed")
        own_tail = seed_summary["own_positive_tail_p"]
        if own_tail is None or own_tail > gate["max_seed_own_positive_tail_p"]:
            failures.append("seed-cluster own positive-tail significance failed")
        margin_tail = seed_summary["margin_positive_tail_p"]
        if (
            margin_tail is None
            or margin_tail > gate["max_seed_margin_positive_tail_p"]
        ):
            failures.append("seed-cluster margin positive-tail significance failed")
        verdict = "REJECT" if failures else "ADMIT"

    report = {
        "schema": REPORT_SCHEMA,
        "validator_version": VERSION,
        "input_sha256": digest(panel),
        "experiment": experiment,
        "provenance": provenance,
        "expected_action_steps": expected_actions,
        "expected_states_per_game": expected_actions + 1,
        "grid": {
            "opponents": opponents,
            "seeds": normalized_seeds,
            "candidate_seats": normalized_seats,
            "cells": len(rows),
        },
        "gate": gate,
        "verdict": verdict,
        "gate_failures": failures,
        "overall": overall,
        "opponent_seat_strata": strata,
        "seed_clusters": seed_groups,
        "seed_cluster_summary": seed_summary,
        "cells": rows,
    }
    report["report_sha256"] = digest(report)
    return report
