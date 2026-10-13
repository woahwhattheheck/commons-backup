#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Fail-closed audit that every direct Gemini/Antigravity Slack post is covered."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import check_ledger as C

HISTORY_SCHEMA = "titan-v4-gemini-antigravity-direct-history/v1"
HISTORICAL_IDS = frozenset({
    "gemini.analyzer-margin-clipping",
    "gemini.fert-high-quote-liquidation",
    "gemini.terminal-mass-hire",
    "gemini.wheat-starvation-buyout",
})
MESSAGE_CLASSIFICATIONS = frozenset({
    "proposition",
    "refinement",
    "coordination",
    "rollup",
})
EXPECTED_PAGE_COUNTS = [20, 20, 4]
EXPECTED_MESSAGE_COUNT = 44
EXPECTED_FIRST_LOCAL = "2026-09-11 23:15:02 EDT"
EXPECTED_LAST_LOCAL = "2026-09-12 00:23:23 EDT"
EXPECTED_QUERY = "from:<@U0C17K9ALP7> in:titan-kaggriculture"


class FullCoverageError(C.ConvergenceError):
    """Direct-author coverage failed a completeness invariant."""


def _nonempty(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FullCoverageError(f"{field} must be a non-empty string")
    return value


def _plain_positive_ints(values: Any, field: str) -> list[int]:
    if not isinstance(values, list) or not values:
        raise FullCoverageError(f"{field} must be a non-empty list")
    if any(type(value) is not int or value <= 0 for value in values):
        raise FullCoverageError(f"{field} must contain exact positive ints")
    if values != sorted(set(values)):
        raise FullCoverageError(f"{field} must be sorted and unique")
    return values


def validate_history(history: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    if history.get("schema") != HISTORY_SCHEMA:
        raise FullCoverageError(f"history schema must be {HISTORY_SCHEMA}")

    master_ledger = history.get("master_ledger")
    if master_ledger != C.V4_PREFIX + "research/gemini-antigravity-convergence/GEMINI-ANTIGRAVITY.json":
        raise FullCoverageError("master_ledger path drift")

    scan = history.get("scan")
    if not isinstance(scan, dict):
        raise FullCoverageError("scan must be an object")
    if scan.get("slack_channel_id") != "C0C0Z8AHGP2":
        raise FullCoverageError("unexpected direct-author source channel")
    if scan.get("gemini_author_id") != "U0C17K9ALP7":
        raise FullCoverageError("unexpected direct-author id")
    if scan.get("query") != EXPECTED_QUERY:
        raise FullCoverageError("direct-author query drift")
    if scan.get("sort") != "timestamp asc":
        raise FullCoverageError("direct-author sort drift")
    if scan.get("page_counts") != EXPECTED_PAGE_COUNTS:
        raise FullCoverageError("direct-author page counts drift")
    if scan.get("author_message_count") != EXPECTED_MESSAGE_COUNT:
        raise FullCoverageError("direct-author message count drift")
    if scan.get("first_message_local") != EXPECTED_FIRST_LOCAL:
        raise FullCoverageError("first direct-author message drift")
    if scan.get("last_message_local") != EXPECTED_LAST_LOCAL:
        raise FullCoverageError("last direct-author message drift")
    if scan.get("earlier_author_search_result_count") != 0:
        raise FullCoverageError("earlier direct-author search must remain empty")
    _nonempty(scan.get("audit_note"), "scan.audit_note")

    if history.get("master_entry_count") != len(C.REQUIRED_IDS):
        raise FullCoverageError("master_entry_count drift")
    if history.get("historical_entry_count") != len(HISTORICAL_IDS):
        raise FullCoverageError("historical_entry_count drift")
    combined_ids = C.REQUIRED_IDS | HISTORICAL_IDS
    if history.get("combined_distinct_proposition_count") != len(combined_ids):
        raise FullCoverageError("combined_distinct_proposition_count drift")

    entries = history.get("historical_entries")
    if not isinstance(entries, list):
        raise FullCoverageError("historical_entries must be a list")
    if len(entries) != len(HISTORICAL_IDS):
        raise FullCoverageError("historical_entries cardinality drift")

    entry_ids: list[str] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise FullCoverageError(f"historical_entries[{index}] must be an object")
        entry_id = _nonempty(entry.get("id"), f"historical_entries[{index}].id")
        entry_ids.append(entry_id)
        _nonempty(entry.get("gemini_label"), f"{entry_id}.gemini_label")
        _nonempty(entry.get("literal_claim"), f"{entry_id}.literal_claim")
        _nonempty(entry.get("best_form"), f"{entry_id}.best_form")
        _nonempty(entry.get("next_gate"), f"{entry_id}.next_gate")

        origins = entry.get("origin_buckets")
        if origins != ["pre_manifest_antigravity"]:
            raise FullCoverageError(f"{entry_id} must be direct pre-manifest Antigravity")

        source_ts = entry.get("source_slack_ts")
        if not isinstance(source_ts, list) or not source_ts:
            raise FullCoverageError(f"{entry_id} must have source_slack_ts")
        if len(source_ts) != len(set(source_ts)):
            raise FullCoverageError(f"{entry_id} has duplicate source Slack timestamps")
        for value in source_ts:
            _nonempty(value, f"{entry_id}.source_slack_ts[]")

        disposition = entry.get("disposition")
        if disposition not in C.ALLOWED_DISPOSITIONS:
            raise FullCoverageError(f"{entry_id} has invalid disposition {disposition!r}")
        activation = entry.get("activation")
        if activation not in C.ALLOWED_ACTIVATIONS:
            raise FullCoverageError(f"{entry_id} has invalid activation {activation!r}")
        if disposition == "FALSIFIED":
            if activation != "FALSIFIED":
                raise FullCoverageError(f"{entry_id} falsified claim must use FALSIFIED activation")
            if entry.get("do_not_repeat_without_new_evidence") is not True:
                raise FullCoverageError(f"{entry_id} falsified claim must be durably fenced")
        if disposition == "FIELD_BLOCKED":
            if activation != "BLOCKED":
                raise FullCoverageError(f"{entry_id} field-blocked claim must use BLOCKED activation")
            if entry.get("do_not_repeat_without_new_evidence") is not True:
                raise FullCoverageError(f"{entry_id} field-blocked claim must be durably fenced")

        evidence = entry.get("canonical_evidence")
        if not isinstance(evidence, list) or not evidence:
            raise FullCoverageError(f"{entry_id} must have canonical_evidence")
        if len(evidence) != len(set(evidence)):
            raise FullCoverageError(f"{entry_id} has duplicate canonical evidence")
        for rel in evidence:
            C._regular_file_under_v4(repo_root, rel, entry_id)

        _plain_positive_ints(entry.get("provenance_pull_numbers"), f"{entry_id}.provenance_pull_numbers")

    if len(entry_ids) != len(set(entry_ids)):
        raise FullCoverageError("duplicate historical entry id")
    if set(entry_ids) != HISTORICAL_IDS:
        raise FullCoverageError(
            f"historical coverage mismatch missing={sorted(HISTORICAL_IDS - set(entry_ids))} "
            f"extra={sorted(set(entry_ids) - HISTORICAL_IDS)}"
        )
    if entry_ids != sorted(entry_ids):
        raise FullCoverageError("historical_entries must be sorted by id")

    message_map = history.get("message_map")
    if not isinstance(message_map, list) or len(message_map) != EXPECTED_MESSAGE_COUNT:
        raise FullCoverageError("message_map must contain exactly 44 direct-author messages")

    ordinals: list[int] = []
    mapped_ids: set[str] = set()
    historical_mapped: set[str] = set()
    for index, row in enumerate(message_map):
        if not isinstance(row, dict):
            raise FullCoverageError(f"message_map[{index}] must be an object")
        ordinal = row.get("ordinal")
        if type(ordinal) is not int or ordinal <= 0:
            raise FullCoverageError(f"message_map[{index}].ordinal must be an exact positive int")
        ordinals.append(ordinal)
        _nonempty(row.get("seen_at_local"), f"message_map[{index}].seen_at_local")
        classification = row.get("classification")
        if classification not in MESSAGE_CLASSIFICATIONS:
            raise FullCoverageError(f"message_map[{index}] has invalid classification")
        proposition_ids = row.get("proposition_ids")
        if not isinstance(proposition_ids, list):
            raise FullCoverageError(f"message_map[{index}].proposition_ids must be a list")
        if len(proposition_ids) != len(set(proposition_ids)):
            raise FullCoverageError(f"message_map[{index}] has duplicate proposition ids")
        unknown = set(proposition_ids) - combined_ids
        if unknown:
            raise FullCoverageError(f"message_map[{index}] references unknown propositions {sorted(unknown)}")
        if classification == "coordination" and proposition_ids:
            raise FullCoverageError(f"message_map[{index}] coordination row cannot carry propositions")
        if classification in {"proposition", "refinement"} and not proposition_ids:
            raise FullCoverageError(f"message_map[{index}] {classification} row must map a proposition")
        _nonempty(row.get("note"), f"message_map[{index}].note")
        mapped_ids.update(proposition_ids)
        historical_mapped.update(set(proposition_ids) & HISTORICAL_IDS)

    if ordinals != list(range(1, EXPECTED_MESSAGE_COUNT + 1)):
        raise FullCoverageError("message_map ordinals must be exactly 1..44 in order")
    if mapped_ids != combined_ids:
        raise FullCoverageError(
            f"message_map proposition coverage mismatch missing={sorted(combined_ids - mapped_ids)} "
            f"extra={sorted(mapped_ids - combined_ids)}"
        )
    if historical_mapped != HISTORICAL_IDS:
        raise FullCoverageError("every historical proposition must be anchored by a direct-author message")

    return {
        "status": "PASS",
        "schema": HISTORY_SCHEMA,
        "direct_author_messages": EXPECTED_MESSAGE_COUNT,
        "master_propositions": len(C.REQUIRED_IDS),
        "historical_propositions": len(HISTORICAL_IDS),
        "combined_distinct_propositions": len(combined_ids),
        "coordination_messages": sum(1 for row in message_map if row["classification"] == "coordination"),
        "rollup_messages": sum(1 for row in message_map if row["classification"] == "rollup"),
    }


def validate_paths(
    master_path: Path,
    history_path: Path,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    master_path = master_path.resolve()
    history_path = history_path.resolve()
    root = repo_root if repo_root is not None else C.find_repo_root(master_path.parent)
    master = C.load_strict_json(master_path)
    C.validate_document(master, root)
    history = C.load_strict_json(history_path)
    return validate_history(history, root)


def main() -> int:
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser()
    parser.add_argument("--master", type=Path, default=here / "GEMINI-ANTIGRAVITY.json")
    parser.add_argument("--history", type=Path, default=here / "HISTORICAL-DIRECT.json")
    parser.add_argument("--repo-root", type=Path, default=None)
    args = parser.parse_args()
    try:
        result = validate_paths(args.master, args.history, args.repo_root)
    except C.ConvergenceError as exc:
        print(f"FAIL: {exc}")
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
