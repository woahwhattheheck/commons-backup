# SPDX-License-Identifier: Apache-2.0
"""Equivalence classification with explicit statistical non-authority."""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Mapping, Sequence

from .core import REPORT_SCHEMA, _seal, preflight_family, validate_family
from .observations import CandidateObservation, validate_observations

def _group_by(
    observations: Sequence[CandidateObservation], attribute: str
) -> Mapping[str, list[CandidateObservation]]:
    grouped: dict[str, list[CandidateObservation]] = defaultdict(list)
    for observation in observations:
        grouped[str(getattr(observation, attribute))].append(observation)
    return grouped


def analyze_equivalence(
    family_raw: Mapping[str, Any], observations_raw: Mapping[str, Any]
) -> dict[str, Any]:
    """Classify exact and observational aliases without changing statistics."""
    preflight = preflight_family(family_raw)
    family = validate_family(family_raw)
    if preflight["verdict"] != "PASS":
        return _seal(
            {
                "schema": REPORT_SCHEMA,
                "verdict": "REFUSED_DUPLICATE_EXECUTABLES",
                "family_id": family.family_id,
                "family_sha256": family.family_sha256,
                "preflight_receipt_sha256": preflight["receipt_sha256"],
                "duplicate_executable_groups": preflight["duplicate_executable_groups"],
                "observations_consumed": False,
                "reason": "duplicate executable identities must be removed before result analysis",
                "familywise_semantics": preflight["familywise_semantics"],
            }
        )

    observations, observations_digest = validate_observations(observations_raw, family)
    action_groups = _group_by(observations, "action_signature_sha256")
    behavior_groups = _group_by(observations, "behavior_signature_sha256")
    score_groups = _group_by(observations, "score_signature_sha256")

    observational_aliases: list[dict[str, Any]] = []
    aliased_ids: set[str] = set()
    for signature, members in sorted(behavior_groups.items()):
        if len(members) < 2:
            continue
        ordered = sorted(members, key=lambda member: member.spec.candidate_id)
        ids = [member.spec.candidate_id for member in ordered]
        aliased_ids.update(ids)
        observational_aliases.append(
            {
                "behavior_signature_sha256": signature,
                "representative_candidate_id": ids[0],
                "candidate_ids": ids,
                "distinct_executable_closures": len(
                    {member.spec.executable_closure_sha256 for member in ordered}
                ),
                "complete_grid_only": True,
                "safe_for_retroactive_multiplicity_collapse": False,
                "safe_for_validation_seed_reuse": False,
            }
        )

    action_only_conflicts: list[dict[str, Any]] = []
    for signature, members in sorted(action_groups.items()):
        behavior_signatures = {
            member.behavior_signature_sha256 for member in members
        }
        if len(members) < 2 or len(behavior_signatures) == 1:
            continue
        action_only_conflicts.append(
            {
                "action_signature_sha256": signature,
                "candidate_ids": sorted(member.spec.candidate_id for member in members),
                "behavior_signature_sha256": sorted(behavior_signatures),
                "code": "EQUAL_ACTIONS_UNEQUAL_EFFECTS",
                "disposition": "HOLD_HARNESS_OR_STATE_DRIFT",
            }
        )

    score_only_aliases: list[dict[str, Any]] = []
    for signature, members in sorted(score_groups.items()):
        behavior_signatures = {
            member.behavior_signature_sha256 for member in members
        }
        if len(members) < 2 or len(behavior_signatures) == 1:
            continue
        score_only_aliases.append(
            {
                "score_signature_sha256": signature,
                "candidate_ids": sorted(member.spec.candidate_id for member in members),
                "behavior_signature_sha256": sorted(behavior_signatures),
                "collapsible": False,
            }
        )

    signatures = [
        {
            "candidate_id": observation.spec.candidate_id,
            "archive_sha256": observation.spec.archive_sha256,
            "executable_closure_sha256": observation.spec.executable_closure_sha256,
            "invocation_sha256": observation.spec.invocation_sha256,
            "action_signature_sha256": observation.action_signature_sha256,
            "behavior_signature_sha256": observation.behavior_signature_sha256,
            "score_signature_sha256": observation.score_signature_sha256,
            "cells": len(observation.cells),
        }
        for observation in observations
    ]
    verdict = "HOLD_ACTION_EFFECT_CONTRADICTION" if action_only_conflicts else "PASS"
    distinct = sorted(
        observation.spec.candidate_id
        for observation in observations
        if observation.spec.candidate_id not in aliased_ids
    )
    return _seal(
        {
            "schema": REPORT_SCHEMA,
            "verdict": verdict,
            "family_id": family.family_id,
            "family_sha256": family.family_sha256,
            "preflight_receipt_sha256": preflight["receipt_sha256"],
            "observations_sha256": observations_digest,
            "engine_sha256": family.engine_sha256,
            "evaluator_sha256": family.evaluator_sha256,
            "schedule_sha256": family.schedule_sha256,
            "declared_candidates": len(observations),
            "behavior_class_count": len(behavior_groups),
            "candidate_signatures": signatures,
            "observational_behavior_aliases": observational_aliases,
            "action_only_conflicts": action_only_conflicts,
            "score_only_aliases": score_only_aliases,
            "distinct_candidate_ids": distinct,
            "familywise_semantics": {
                "exact_executable_duplicates_blocked_pre_result": True,
                "observational_aliases_are_reporting_only": True,
                "retroactive_multiplicity_reduction_allowed": False,
                "validation_seed_reuse_authorized": False,
                "selection_or_promotion_authorized": False,
            },
        }
    )
