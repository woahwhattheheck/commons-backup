#!/usr/bin/env python3
"""Strict opponent-panel identity and multiplicity-bias reducer for TITAN V4 gauntlets.

This module does not infer policy identity from scores.  Exact source_id/family
metadata is authority; matching outcomes are warnings only.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

PANEL_SCHEMA = "titan.gauntlet.panel.v1"
RESULTS_SCHEMA = "titan.gauntlet.results.v1"
KINDS = {"real_policy", "recorded_trace", "archetype", "mirror", "unknown"}
STATUSES = {"resolved", "unresolved"}


class DataError(ValueError):
    pass


def _object_no_dupes(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise DataError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def _reject_constant(value: str) -> None:
    raise DataError(f"non-finite JSON number: {value}")


def loads_strict(text: str) -> Any:
    try:
        return json.loads(
            text,
            object_pairs_hook=_object_no_dupes,
            parse_constant=_reject_constant,
        )
    except DataError:
        raise
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise DataError(f"invalid JSON: {exc}") from exc


def load_strict(path: str | Path) -> Any:
    return loads_strict(Path(path).read_text(encoding="utf-8"))


def _keys(obj: Any, required: set[str], optional: set[str], where: str) -> dict[str, Any]:
    if type(obj) is not dict:
        raise DataError(f"{where} must be an object")
    got = set(obj)
    missing = required - got
    extra = got - required - optional
    if missing:
        raise DataError(f"{where} missing fields: {sorted(missing)}")
    if extra:
        raise DataError(f"{where} unknown fields: {sorted(extra)}")
    return obj


def _text(value: Any, where: str) -> str:
    if type(value) is not str or not value or value.strip() != value:
        raise DataError(f"{where} must be a non-empty exact string")
    return value


def _nonneg_int(value: Any, where: str) -> int:
    if type(value) is not int or value < 0:
        raise DataError(f"{where} must be a non-negative exact integer")
    return value


def _finite_number(value: Any, where: str) -> float:
    if type(value) not in (int, float):
        raise DataError(f"{where} must be an exact finite number")
    try:
        result = float(value)
    except (OverflowError, ValueError) as exc:
        raise DataError(f"{where} must be finite") from exc
    if not math.isfinite(result):
        raise DataError(f"{where} must be finite")
    return result


def validate_panel(raw: Any) -> dict[str, Any]:
    obj = _keys(raw, {"schema", "expected_labels", "opponents"}, {"source", "notes"}, "panel")
    if obj["schema"] != PANEL_SCHEMA:
        raise DataError(f"panel.schema must equal {PANEL_SCHEMA!r}")
    expected = _nonneg_int(obj["expected_labels"], "panel.expected_labels")
    if expected < 1:
        raise DataError("panel.expected_labels must be positive")
    opponents = obj["opponents"]
    if type(opponents) is not list:
        raise DataError("panel.opponents must be a list")
    if len(opponents) > expected:
        raise DataError("panel has more labels than expected_labels")

    ids: set[str] = set()
    source_claims: dict[str, tuple[str, str]] = {}
    family_kinds: dict[str, str] = {}
    clean: list[dict[str, Any]] = []
    for index, raw_opp in enumerate(opponents):
        where = f"panel.opponents[{index}]"
        opp = _keys(raw_opp, {"id", "kind", "family", "source_id", "status"}, {"rank", "note"}, where)
        oid = _text(opp["id"], f"{where}.id")
        if oid in ids:
            raise DataError(f"duplicate opponent id: {oid}")
        ids.add(oid)
        kind = _text(opp["kind"], f"{where}.kind")
        if kind not in KINDS:
            raise DataError(f"{where}.kind is unknown: {kind}")
        status = _text(opp["status"], f"{where}.status")
        if status not in STATUSES:
            raise DataError(f"{where}.status is unknown: {status}")
        family = opp["family"]
        source_id = opp["source_id"]
        if status == "resolved":
            family = _text(family, f"{where}.family")
            source_id = _text(source_id, f"{where}.source_id")
            if kind == "unknown":
                raise DataError(f"{where} resolved opponent cannot have kind=unknown")
            prior = source_claims.get(source_id)
            claim = (family, kind)
            if prior is not None and prior != claim:
                raise DataError(
                    f"source_id {source_id!r} has conflicting identity: {prior!r} vs {claim!r}"
                )
            source_claims[source_id] = claim
            prior_kind = family_kinds.get(family)
            if prior_kind is not None and prior_kind != kind:
                raise DataError(f"family {family!r} spans conflicting kinds: {prior_kind!r} vs {kind!r}")
            family_kinds[family] = kind
        else:
            if family is not None or source_id is not None:
                raise DataError(f"{where} unresolved opponent must use null family/source_id")
        row = dict(opp)
        if "rank" in row:
            rank = row["rank"]
            if rank is not None:
                rank = _nonneg_int(rank, f"{where}.rank")
                if rank < 1:
                    raise DataError(f"{where}.rank must be positive when present")
                row["rank"] = rank
        if "note" in row and row["note"] is not None:
            _text(row["note"], f"{where}.note")
        clean.append(row)
    result = dict(obj)
    result["opponents"] = clean
    return result


def validate_results(raw: Any, panel: dict[str, Any]) -> dict[str, Any]:
    obj = _keys(raw, {"schema", "rows"}, {"candidate", "engine", "source"}, "results")
    if obj["schema"] != RESULTS_SCHEMA:
        raise DataError(f"results.schema must equal {RESULTS_SCHEMA!r}")
    rows = obj["rows"]
    if type(rows) is not list:
        raise DataError("results.rows must be a list")
    panel_ids = {o["id"] for o in panel["opponents"]}
    seen: set[str] = set()
    clean: list[dict[str, Any]] = []
    for index, raw_row in enumerate(rows):
        where = f"results.rows[{index}]"
        row = _keys(raw_row, {"opponent_id", "wins", "losses", "draws", "margin_sum"}, {"cell_digest"}, where)
        oid = _text(row["opponent_id"], f"{where}.opponent_id")
        if oid not in panel_ids:
            raise DataError(f"result references unknown opponent: {oid}")
        if oid in seen:
            raise DataError(f"duplicate result opponent_id: {oid}")
        seen.add(oid)
        wins = _nonneg_int(row["wins"], f"{where}.wins")
        losses = _nonneg_int(row["losses"], f"{where}.losses")
        draws = _nonneg_int(row["draws"], f"{where}.draws")
        if wins + losses + draws < 1:
            raise DataError(f"{where} must contain at least one game")
        margin_sum = _finite_number(row["margin_sum"], f"{where}.margin_sum")
        clean_row = dict(row)
        clean_row["margin_sum"] = margin_sum
        if "cell_digest" in clean_row and clean_row["cell_digest"] is not None:
            _text(clean_row["cell_digest"], f"{where}.cell_digest")
        clean.append(clean_row)
    result = dict(obj)
    result["rows"] = clean
    return result


def _rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def analyze(panel_raw: Any, results_raw: Any | None = None) -> dict[str, Any]:
    panel = validate_panel(panel_raw)
    opponents = panel["opponents"]
    expected = panel["expected_labels"]
    resolved = [o for o in opponents if o["status"] == "resolved"]
    unresolved = [o for o in opponents if o["status"] == "unresolved"]

    families: dict[str, list[str]] = defaultdict(list)
    sources: dict[str, list[str]] = defaultdict(list)
    for opp in resolved:
        families[opp["family"]].append(opp["id"])
        sources[opp["source_id"]].append(opp["id"])

    label_count = len(opponents)
    family_counts = [len(ids) for ids in families.values()]
    if resolved:
        denom = len(resolved)
        concentration = sum((count / denom) ** 2 for count in family_counts)
        family_ess = 1.0 / concentration if concentration else 0.0
    else:
        concentration = 0.0
        family_ess = 0.0

    report: dict[str, Any] = {
        "schema": "titan.gauntlet.panel-diversity.v1",
        "panel": {
            "expected_labels": expected,
            "observed_labels": label_count,
            "resolved_labels": len(resolved),
            "unresolved_labels": [o["id"] for o in unresolved],
            "missing_label_count": expected - label_count,
            "unique_families": len(families),
            "unique_sources": len(sources),
            "family_multiplicity_inflation": (len(resolved) / len(families)) if families else None,
            "label_weight_family_concentration_hhi": concentration,
            "label_weight_effective_family_count": family_ess,
            "max_family_multiplicity": max(family_counts, default=0),
            "family_aliases": [
                {"family": family, "labels": sorted(ids), "multiplicity": len(ids)}
                for family, ids in sorted(families.items())
                if len(ids) > 1
            ],
            "source_aliases": [
                {"source_id": source, "labels": sorted(ids), "multiplicity": len(ids)}
                for source, ids in sorted(sources.items())
                if len(ids) > 1
            ],
        },
    }

    manifest_complete = label_count == expected and not unresolved
    report["panel"]["identity_complete"] = manifest_complete

    if results_raw is None:
        report["results"] = None
        report["authoritative_family_weighting"] = False
        report["blocking_reasons"] = [] if manifest_complete else ["panel_identity_incomplete"]
        return report

    results = validate_results(results_raw, panel)
    rows = results["rows"]
    by_id = {row["opponent_id"]: row for row in rows}
    expected_ids = {opp["id"] for opp in opponents}
    missing_results = sorted(expected_ids - set(by_id))

    total_games = sum(r["wins"] + r["losses"] + r["draws"] for r in rows)
    total_wins = sum(r["wins"] for r in rows)
    total_losses = sum(r["losses"] for r in rows)
    total_draws = sum(r["draws"] for r in rows)
    total_margin = sum(r["margin_sum"] for r in rows)
    label_summary = {
        "games": total_games,
        "wins": total_wins,
        "losses": total_losses,
        "draws": total_draws,
        "win_rate": _rate(total_wins, total_games),
        "loss_rate": _rate(total_losses, total_games),
        "draw_rate": _rate(total_draws, total_games),
        "mean_margin_per_game": (total_margin / total_games) if total_games else None,
    }

    family_rows: list[dict[str, Any]] = []
    for family, ids in sorted(families.items()):
        present = [by_id[oid] for oid in ids if oid in by_id]
        if not present:
            continue
        games = sum(r["wins"] + r["losses"] + r["draws"] for r in present)
        wins = sum(r["wins"] for r in present)
        losses = sum(r["losses"] for r in present)
        draws = sum(r["draws"] for r in present)
        margin = sum(r["margin_sum"] for r in present)
        family_rows.append(
            {
                "family": family,
                "labels": sorted(ids),
                "labels_with_results": sorted(r["opponent_id"] for r in present),
                "games": games,
                "win_rate": _rate(wins, games),
                "loss_rate": _rate(losses, games),
                "draw_rate": _rate(draws, games),
                "mean_margin_per_game": margin / games,
            }
        )

    if family_rows:
        family_balanced = {
            "families": len(family_rows),
            "win_rate": sum(r["win_rate"] for r in family_rows) / len(family_rows),
            "loss_rate": sum(r["loss_rate"] for r in family_rows) / len(family_rows),
            "draw_rate": sum(r["draw_rate"] for r in family_rows) / len(family_rows),
            "mean_margin_per_game": sum(r["mean_margin_per_game"] for r in family_rows) / len(family_rows),
        }
    else:
        family_balanced = None

    signature_groups: dict[tuple[int, int, int, float], list[str]] = defaultdict(list)
    for row in rows:
        signature_groups[(row["wins"], row["losses"], row["draws"], row["margin_sum"])].append(row["opponent_id"])
    outcome_warnings = []
    opp_by_id = {o["id"]: o for o in opponents}
    for signature, ids in signature_groups.items():
        if len(ids) < 2:
            continue
        resolved_ids = [oid for oid in ids if opp_by_id[oid]["status"] == "resolved"]
        source_ids = {opp_by_id[oid]["source_id"] for oid in resolved_ids}
        if len(source_ids) > 1:
            outcome_warnings.append(
                {
                    "labels": sorted(ids),
                    "signature": {
                        "wins": signature[0],
                        "losses": signature[1],
                        "draws": signature[2],
                        "margin_sum": signature[3],
                    },
                    "note": "aggregate outcome equality is warning-only; it does not collapse source/family identity",
                }
            )

    complete_results = not missing_results and len(rows) == len(opponents)
    authoritative = manifest_complete and complete_results
    blocking: list[str] = []
    if not manifest_complete:
        blocking.append("panel_identity_incomplete")
    if not complete_results:
        blocking.append("result_coverage_incomplete")

    report["results"] = {
        "missing_opponent_results": missing_results,
        "label_weighted": label_summary,
        "family_rows": family_rows,
        "family_balanced": family_balanced,
        "outcome_equality_warnings": outcome_warnings,
    }
    report["authoritative_family_weighting"] = authoritative
    report["blocking_reasons"] = blocking
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("panel")
    parser.add_argument("--results")
    parser.add_argument("--output")
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args(argv)
    try:
        panel = load_strict(args.panel)
        results = load_strict(args.results) if args.results else None
        report = analyze(panel, results)
    except (OSError, DataError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    text = json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    if args.require_complete:
        complete = report["panel"]["identity_complete"] if results is None else report["authoritative_family_weighting"]
        if not complete:
            return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
