"""Pure P24 matrix, validation, and interaction-analysis helpers."""
from __future__ import annotations

import hashlib
import itertools
import json
import math
import os
from pathlib import Path
import shutil
import statistics
import tarfile
from typing import Any, Iterable, Mapping, Sequence

FACTORS = ("early_capital", "crop_release", "operating_stock", "idle_fertilizer")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def powerset(items: Sequence[str]):
    return [part for size in range(len(items) + 1) for part in itertools.combinations(items, size)]


def variant_matrix():
    rows = []
    for enabled in powerset(FACTORS):
        name = "baseline" if not enabled else "joint_all" if len(enabled) == len(FACTORS) else "+".join(enabled)
        rows.append({"name": name, "enabled": list(enabled),
                     "flags": {factor: factor in enabled for factor in FACTORS}})
    return rows


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def safe_extract(archive: Path, destination: Path):
    """Extract only in-root regular files/directories; reject links, devices, duplicates."""
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:gz") as bundle:
        members = bundle.getmembers()
        names = [member.name for member in members]
        if len(names) != len(set(names)):
            raise ValueError("Archive contains duplicate member names")
        root = destination.resolve()
        regular_files = []
        for member in members:
            target = (destination / member.name).resolve()
            try:
                target.relative_to(root)
            except ValueError as exc:
                raise ValueError(f"Unsafe archive path: {member.name!r}") from exc
            if not member.name or member.name.startswith("/"):
                raise ValueError(f"Unsafe archive path: {member.name!r}")
            if member.issym() or member.islnk() or member.isdev() or member.isfifo():
                raise ValueError(f"Unsupported archive member type: {member.name!r}")
            if not (member.isdir() or member.isfile()):
                raise ValueError(f"Unsupported archive member: {member.name!r}")
            if member.isfile():
                regular_files.append(member.name)
        bundle.extractall(destination, members=members, filter="data")
    return regular_files


def prepare_variants(base: Path, destination: Path):
    config = json.loads((base / "TITAN-CONFIG.json").read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise TypeError("TITAN-CONFIG.json must contain an object")
    missing = [factor for factor in FACTORS if factor not in config]
    if missing:
        raise ValueError(f"Archive is missing P24 factors: {missing}")
    bad = [factor for factor in FACTORS if not isinstance(config[factor], bool)]
    if bad:
        raise TypeError(f"P24 factors must be booleans: {bad}")
    fixed = {key: value for key, value in config.items() if key not in FACTORS}
    rows = variant_matrix()
    for row in rows:
        root = destination / row["name"]
        shutil.copytree(base, root)
        built = dict(config)
        built.update(row["flags"])
        if {key: value for key, value in built.items() if key not in FACTORS} != fixed:
            raise AssertionError("Variant changed a non-factor setting")
        write_json(root / "TITAN-CONFIG.json", built)
        row["config_sha256"] = sha256_file(root / "TITAN-CONFIG.json")
        row["candidate"] = str((root / "main.py").resolve()) + "::agent"
    return rows, config


def valid_hash(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def validate_games(games, variants, opponents, seeds) -> None:
    expected = {(row["name"], opponent, seed, seat) for row in variants
                for opponent in opponents for seed in seeds for seat in (0, 1)}
    if len(games) != len(expected):
        raise AssertionError(f"Expected {len(expected)} games, received {len(games)}")
    observed = set()
    for game in games:
        key = (game.get("variant"), game.get("opponent"), game.get("seed"), game.get("candidate_seat"))
        if key in observed:
            raise AssertionError(f"Duplicate game cell: {key}")
        observed.add(key)
        scores = game.get("scores")
        if game.get("status") != "complete" or game.get("failure") is not None:
            raise AssertionError(f"Incomplete game cell: {key}; {game.get('failure')}")
        if not isinstance(scores, list) or len(scores) != 2 or not all(
                isinstance(score, (int, float)) and math.isfinite(score) for score in scores):
            raise AssertionError(f"Invalid terminal scores: {key}")
        if game.get("steps") != game.get("episode_steps") - 1 or not valid_hash(game.get("trace_sha256")):
            raise AssertionError(f"Invalid terminal receipt: {key}")
    if observed != expected:
        raise AssertionError(f"Cell mismatch; missing={sorted(expected - observed)[:3]}")


def margin(game: Mapping[str, Any]) -> float:
    seat = int(game["candidate_seat"])
    return float(game["scores"][seat]) - float(game["scores"][1 - seat])


def own(game):
    return float(game["scores"][int(game["candidate_seat"])])


def rival(game):
    return float(game["scores"][1 - int(game["candidate_seat"])])


def mean(values: Iterable[float]):
    values = list(values)
    return statistics.mean(values) if values else None


def mobius(values: Mapping[frozenset[str], float], subset: frozenset[str]) -> float:
    total = 0.0
    items = tuple(sorted(subset))
    for lower in powerset(items):
        lower = frozenset(lower)
        total += (-1.0) ** (len(subset) - len(lower)) * values[lower]
    return total


def summarize(games, matrix):
    by_variant = {}
    for variant in matrix:
        rows = [game for game in games if game["variant"] == variant["name"]]
        margins = [margin(game) for game in rows]
        by_variant[variant["name"]] = {
            "games": len(rows), "wins": sum(x > 0 for x in margins), "ties": sum(x == 0 for x in margins),
            "losses": sum(x < 0 for x in margins), "mean_margin": mean(margins),
            "mean_candidate_score": mean(own(game) for game in rows),
            "mean_opponent_score": mean(rival(game) for game in rows),
            "max_candidate_rpc_seconds": max((game["actors"][int(game["candidate_seat"])]["max_rpc_seconds"]
                                               for game in rows), default=0.0),
        }
    sets = {row["name"]: frozenset(row["enabled"]) for row in matrix}
    names = {enabled: name for name, enabled in sets.items()}
    index = {(game["opponent"], game["seed"], game["candidate_seat"], sets[game["variant"]]): game
             for game in games}
    cells = sorted({(game["opponent"], game["seed"], game["candidate_seat"]) for game in games})
    empty, full = frozenset(), frozenset(FACTORS)
    paired, effects = [], {frozenset(part): [] for part in powerset(FACTORS) if part}
    toggle = {factor: {"comparisons": 0, "trace_changed": 0, "margin": [], "own": [], "rival": []}
              for factor in FACTORS}
    for cell in cells:
        values = {enabled: margin(index[cell + (enabled,)]) for enabled in names}
        base, joint = index[cell + (empty,)], index[cell + (full,)]
        singles = sum(values[frozenset((factor,))] - values[empty] for factor in FACTORS)
        paired.append({"opponent": cell[0], "seed": cell[1], "candidate_seat": cell[2],
                       "baseline_margin": values[empty], "joint_margin": values[full],
                       "joint_margin_delta": values[full] - values[empty],
                       "joint_minus_sum_singles": values[full] - values[empty] - singles,
                       "joint_trace_changed": joint["trace_sha256"] != base["trace_sha256"],
                       "joint_candidate_score_delta": own(joint) - own(base),
                       "joint_opponent_score_delta": rival(joint) - rival(base)})
        for subset in effects:
            effects[subset].append(mobius(values, subset))
        for factor in FACTORS:
            for background in powerset(tuple(item for item in FACTORS if item != factor)):
                low_set = frozenset(background); high_set = low_set | {factor}
                low, high = index[cell + (low_set,)], index[cell + (high_set,)]
                bucket = toggle[factor]; bucket["comparisons"] += 1
                bucket["trace_changed"] += high["trace_sha256"] != low["trace_sha256"]
                bucket["margin"].append(margin(high) - margin(low))
                bucket["own"].append(own(high) - own(low)); bucket["rival"].append(rival(high) - rival(low))
    return {
        "by_variant": by_variant,
        "joint_vs_baseline": {"cells": len(paired), "trace_changed": sum(x["joint_trace_changed"] for x in paired),
                              "mean_margin_delta": mean(x["joint_margin_delta"] for x in paired),
                              "mean_candidate_score_delta": mean(x["joint_candidate_score_delta"] for x in paired),
                              "mean_opponent_score_delta": mean(x["joint_opponent_score_delta"] for x in paired),
                              "mean_joint_minus_sum_singles": mean(x["joint_minus_sum_singles"] for x in paired)},
        "factor_toggle": {factor: {"comparisons": data["comparisons"], "trace_changed": data["trace_changed"],
                                   "trace_change_rate": data["trace_changed"] / data["comparisons"],
                                   "mean_margin_delta": mean(data["margin"]), "mean_candidate_score_delta": mean(data["own"]),
                                   "mean_opponent_score_delta": mean(data["rival"])} for factor, data in toggle.items()},
        "mobius_margin_effects": {"+".join(sorted(subset)): {"order": len(subset), "cells": len(values),
                                   "mean_margin_effect": mean(values), "min_margin_effect": min(values),
                                   "max_margin_effect": max(values), "nonzero_cells": sum(x != 0 for x in values)}
                                  for subset, values in sorted(effects.items(), key=lambda item: (len(item[0]), sorted(item[0])))},
        "paired_cells": paired,
    }


def markdown(report) -> str:
    summary = report["summary"]
    lines = ["# TITAN P24 configuration factorial", "", f"- Dispatch: `{report['dispatch_commit']}`",
             f"- Archive: `{report['archive']['sha256']}` ({report['archive']['bytes']} bytes; {report['archive'].get('runtime_member_count', report['archive'].get('member_count'))} files)",
             f"- Source: `{report['archive']['source_manifest_sha256']}`", f"- Engine: `{report['engine']['ref']}`",
             f"- Seeds: `{', '.join(map(str, report['seeds']))}`", f"- Opponents: `{', '.join(report['opponents'])}`",
             f"- Games: `{report.get('scheduled_games', report.get('expected_cells'))}` complete (fail-closed)", "", "## Outcomes", "",
             "| Variant | W-T-L | Mean margin | Mean own | Mean rival | Max RPC |",
             "|---|---:|---:|---:|---:|---:|"]
    for row in report["variants"]:
        value = summary["by_variant"][row["name"]]
        lines.append(f"| `{row['name']}` | {value['wins']}-{value['ties']}-{value['losses']} | "
                     f"{value['mean_margin']:.3f} | {value['mean_candidate_score']:.3f} | "
                     f"{value['mean_opponent_score']:.3f} | {value['max_candidate_rpc_seconds']:.6f}s |")
    joint = summary["joint_vs_baseline"]
    lines += ["", "## Joint interaction", "", f"- Trace changed: **{joint['trace_changed']}/{joint['cells']}** cells.",
              f"- Mean joint minus baseline margin: **{joint['mean_margin_delta']:.3f}**.",
              f"- Mean joint minus summed singles: **{joint['mean_joint_minus_sum_singles']:.3f}**.", "",
              "Development evidence only: official pinned interpreter, not hosted Kaggle scoring or promotion authority. "
              "Trace divergence is observable game behavior, not an internal callback counter. Held seeds stay untouched "
              "until selection is frozen.", ""]
    return "\n".join(lines)
