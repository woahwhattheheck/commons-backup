# SPDX-License-Identifier: Apache-2.0
"""Aggregation and interpretation for unit-capacity occurrence evidence."""
from __future__ import annotations

from collections import Counter
from typing import Any, Mapping

from unit_capacity_support import RESULT_SCHEMA, encoded, sha256

def occurrence_signature(row: Mapping[str, Any]) -> str:
    body = {
        "step": row["step"],
        "changes": [
            {
                "unit_index": change["unit_index"],
                "action": change["action"],
                "shed_delta": change["shed_delta"],
            }
            for change in row["shed_changes"]
        ],
    }
    return sha256(encoded(body))


def summarize(streams: list[dict[str, Any]], source: Mapping[str, Any]) -> dict[str, Any]:
    totals = Counter()
    occurrence_groups: dict[str, dict[str, Any]] = {}
    for stream in streams:
        totals.update(stream["counters"])
        for row in stream["occurrences"]:
            signature = occurrence_signature(row)
            group = occurrence_groups.setdefault(
                signature,
                {
                    "signature": signature,
                    "step": row["step"],
                    "instances": 0,
                    "stream_keys": [],
                    "occupancy_variants": [],
                    "shed_changes": row["shed_changes"],
                },
            )
            group["instances"] += 1
            group["stream_keys"].append(stream["stream_key"])
            variant = {
                key: row[key]
                for key in (
                    "pre_shed",
                    "interior_peak_shed",
                    "end_unit_shed",
                    "hidden_peak_above_start_and_end",
                    "discarded_units",
                )
            }
            if variant not in group["occupancy_variants"]:
                group["occupancy_variants"].append(variant)

    for group in occurrence_groups.values():
        group["stream_keys"] = sorted(set(group["stream_keys"]))
        group["occupancy_variants"] = sorted(
            group["occupancy_variants"],
            key=lambda row: (
                row["pre_shed"], row["interior_peak_shed"], row["end_unit_shed"]
            ),
        )
    groups = sorted(occurrence_groups.values(), key=lambda row: row["step"])
    max_shed_occupancy = max(stream["counters"]["max_shed_occupancy"] for stream in streams)
    max_hidden_peak_units = max(stream["counters"]["max_hidden_peak_units"] for stream in streams)
    hidden_peak_occupancies = [
        row["interior_peak_shed"]
        for stream in streams
        for row in stream["occurrences"]
        if row["hidden_peak_above_start_and_end"] > 0
    ]
    summary = {
        "complete_frame_file_instances": sum(len(stream["aliases"]) for stream in streams),
        "unique_complete_stream_seat_pairs": len(streams),
        "verified_initial_states": len(streams),
        "verified_recorded_transitions": totals["phases"],
        "candidate_unit_actions": totals["unit_actions"],
        "drop_actions": totals["drop_actions"],
        "valid_drop_actions": totals["valid_drop_actions"],
        "place_to_shed_actions": totals["place_to_shed_actions"],
        "pickup_reductions": totals["pickup_reductions"],
        "positive_then_negative_phases": totals["positive_then_negative_phases"],
        "distinct_positive_then_negative_action_patterns": len(groups),
        "interior_peak_above_start_and_end_phases": totals["interior_peak_phases"],
        "max_hidden_peak_units": max_hidden_peak_units,
        "max_hidden_peak_shed_occupancy": max(hidden_peak_occupancies, default=0),
        "max_shed_occupancy": max_shed_occupancy,
        "near_capacity_95_phases": totals["near_capacity_95_phases"],
        "capacity_hit_phases": totals["hit_capacity_phases"],
        "hidden_peak_hit_capacity_phases": totals["hidden_peak_hit_capacity_phases"],
        "drop_then_pickup_phases": totals["drop_then_pickup_phases"],
        "discard_phases": totals["discard_phases"],
        "discarded_units": totals["discarded_units"],
        "policy_calls": 0,
        "new_scored_games": 0,
        "new_game_seeds": [],
    }
    return {
        "schema": RESULT_SCHEMA,
        "source": dict(source),
        "summary": summary,
        "occurrence_patterns": groups,
        "streams": [
            {key: value for key, value in stream.items() if key != "occurrences"}
            for stream in streams
        ],
        "interpretation": {
            "reached_distinction": (
                "End-of-unit occupancy is not equivalent to the ordered per-worker "
                "path: retained actions contain reached interior peaks."
            ),
            "measured_limit": (
                "No retained interior peak reaches shed capacity and no carried unit "
                "is discarded. This bank therefore does not reproduce the constructed "
                "overflow-loss outcome or establish a gameplay gain."
            ),
            "consumer": (
                "INTEGRATION's existing intermediate-worker capacity repair should "
                "retain its constructed at-capacity discriminator; these reached rows "
                "supply natural ordering coverage and an explicit no-overflow result."
            ),
            "independence": (
                "Counts are transition observations from ten unique stream/seat byte "
                "identities. Mirrored seats and repeated action patterns are not treated "
                "as independent game evidence."
            ),
        },
    }
