#!/usr/bin/env python3
"""Descriptive gauntlet audit. No agent execution, tuning, or promotion decision.

Two explicit schemas: titan.gauntlet.summary.v1 (published aggregates only),
and titan.gauntlet.paired.v1 (a predeclared plan plus source-bound raw games).
Hashes supplied in rows are checked against the plan, not fetched/authenticated.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from decimal import Decimal, InvalidOperation, localcontext
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

KINDS = {"recorded_trace", "archetype", "live_agent", "mirror"}
ARMS = ("baseline", "candidate")
SPLITS = {"tuning", "holdout"}
STATES = {"complete", "error", "timeout", "incomplete"}
SHA = re.compile(r"[0-9a-f]{64}\Z")
MARGIN = re.compile(r"[+-]?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?[kK]?\Z")


class AuditError(ValueError):
    """Invalid/ambiguous input; never convert this to a successful audit."""


def require(ok: bool, message: str) -> None:
    if not ok:
        raise AuditError(message)


def obj(value: Any, name: str) -> dict:
    require(isinstance(value, dict), f"{name}: expected object")
    return value


def rows(value: Any, name: str) -> list:
    require(isinstance(value, list) and bool(value), f"{name}: expected nonempty list")
    return value


def text(value: Any, name: str) -> str:
    require(isinstance(value, str) and bool(value.strip()), f"{name}: expected text")
    return value


def integer(value: Any, name: str, minimum: int | None = None) -> int:
    require(type(value) is int, f"{name}: expected integer, not bool/float")
    require(minimum is None or value >= minimum, f"{name}: below minimum")
    return value


def digest(value: Any, name: str) -> str:
    require(isinstance(value, str) and SHA.fullmatch(value) is not None,
            f"{name}: expected lowercase SHA-256")
    return value


def choice(value: Any, choices: set | tuple, name: str) -> str:
    require(isinstance(value, str) and value in choices, f"{name}: invalid value")
    return value


def mean(values: list[int | Decimal]) -> str | None:
    if not values:
        return None
    # More than sufficient for game cash, but also safe for very large exact ints.
    with localcontext() as ctx:
        ctx.prec = max(40, max(len(str(v)) for v in values) + len(str(len(values))) + 32)
        return format(sum(map(Decimal, values), Decimal(0)) / len(values), "f")


def statistics(values: list[int]) -> dict:
    return {"n": len(values), "mean": mean(values),
            "min": min(values) if values else None,
            "max": max(values) if values else None,
            "positive": sum(v > 0 for v in values),
            "zero": sum(v == 0 for v in values),
            "negative": sum(v < 0 for v in values)}


def amount(value: Any) -> tuple[Decimal, bool]:
    raw = text(value, "reported_total_margin")
    normalized = raw.replace("−", "-").replace("\u2212", "-")
    require(MARGIN.fullmatch(normalized) is not None, "invalid reported margin")
    abbreviated = normalized[-1:] in {"k", "K"}
    try:
        number = Decimal(normalized[:-1] if abbreviated else normalized)
        if abbreviated:
            number *= 1000
    except InvalidOperation as exc:
        raise AuditError("invalid reported margin") from exc
    return number, abbreviated


def audit_summary(document: dict) -> dict:
    source = text(document.get("source"), "source")
    candidate_label = text(document.get("candidate_label"), "candidate_label")
    seen, groups = set(), []
    for row in rows(document.get("opponents"), "opponents"):
        row = obj(row, "opponent")
        ident = text(row.get("id"), "opponent.id")
        require(ident not in seen, f"duplicate opponent {ident}")
        seen.add(ident)
        kind = choice(row.get("kind"), KINDS, "kind")
        counts = {key: integer(row.get(key), key, 0) for key in ("wins", "losses", "draws")}
        n = sum(counts.values())
        require(n > 0, "opponent has zero games")
        value, abbreviated = amount(row.get("reported_total_margin"))
        require(type(row.get("approximate")) is bool, "approximate must be explicit bool")
        approximate = row["approximate"] or abbreviated
        groups.append({"id": ident, "kind": kind, **counts, "games": n,
                       "reported_total_margin": row["reported_total_margin"],
                       "interpreted_total_margin": str(value),
                       "mean_reported_margin": mean([value / n]),
                       "approximate": approximate,
                       "net_losing": value < 0})
    totals = {key: sum(r[key] for r in groups) for key in ("wins", "losses", "draws", "games")}
    declared = obj(document.get("declared_totals"), "declared_totals")
    for key, value in totals.items():
        require(integer(declared.get(key), key, 0) == value, f"declared {key} mismatch")
    nonmirror = sorted((r for r in groups if r["kind"] != "mirror"),
                       key=lambda r: (Decimal(r["mean_reported_margin"]), r["id"]))
    return {"schema": "titan.gauntlet.audit.v1", "mode": "reported_summary",
            "source": source, "candidate_label": candidate_label,
            "totals": totals, "weakest_nonmirror": nonmirror[:3],
            "by_kind": {kind: [r for r in nonmirror if r["kind"] == kind]
                        for kind in sorted(KINDS - {"mirror"})},
            "mirror_controls": [r for r in groups if r["kind"] == "mirror"],
            "paired_evidence_available": False, "promotion_decision": "NOT_ASSESSED",
            "limitations": ["Transcribed reported aggregates, not executed games.",
                "Abbreviated totals are approximate; game-level variance is unavailable.",
                "No seed/seat/source/fallback custody or variant-effect evidence.",
                "Recorded action traces and archetypes are not adaptive leaderboard agents.",
                "Third-lowest positive margin is not a third losing matchup."]}


def audit_paired(document: dict) -> dict:
    artifacts = obj(document.get("artifacts"), "artifacts")
    for arm in ARMS:
        digest(artifacts.get(arm), f"artifact.{arm}")
    engine = digest(document.get("engine_sha256"), "engine_sha256")
    expected = integer(document.get("expected_callbacks"), "expected_callbacks", 1)
    opponents = {}
    for o in rows(document.get("opponents"), "opponents"):
        o = obj(o, "opponent")
        oid = text(o.get("id"), "opponent.id")
        require(oid not in opponents, f"duplicate opponent {oid}")
        choice(o.get("kind"), KINDS, "kind")
        opponents[oid] = o
    plan, balance, identities = {}, defaultdict(set), set()
    for cell in rows(document.get("cells"), "cells"):
        cell = obj(cell, "cell")
        cid = text(cell.get("id"), "cell.id")
        require(cid not in plan, f"duplicate cell {cid}")
        oid = text(cell.get("opponent_id"), "cell.opponent_id")
        require(oid in opponents, f"unknown opponent {oid}")
        integer(cell.get("seed"), "seed")
        require(integer(cell.get("seat"), "seat") in (0, 1), "seat must be 0/1")
        integer(cell.get("replicate"), "replicate", 0)
        choice(cell.get("split"), SPLITS, "split")
        digest(cell.get("opponent_sha256"), "cell.opponent_sha256")
        identity = tuple(cell[k] for k in ("opponent_id", "seed", "seat", "replicate", "split"))
        require(identity not in identities, f"duplicate planned coordinates {identity}")
        identities.add(identity)
        balance[(oid, cell["seed"], cell["replicate"], cell["split"])].add(cell["seat"])
        plan[cid] = cell
    require(set(opponents) == {c["opponent_id"] for c in plan.values()},
            "declared opponent missing from plan")
    require(all(seats == {0, 1} for seats in balance.values()), "plan lacks balanced seats")
    # Seed reuse between tuning/holdout leaks the same world; replicas are not new holdouts.
    train = {c["seed"] for c in plan.values() if c["split"] == "tuning"}
    hold = {c["seed"] for c in plan.values() if c["split"] == "holdout"}
    require(not train & hold, "tuning/holdout seed overlap")
    games = {}
    raw = document.get("games")
    require(isinstance(raw, list), "games must be a list (may be empty)")
    for game in raw:
        game = obj(game, "game")
        cid = text(game.get("cell_id"), "game.cell_id")
        require(cid in plan, f"unplanned cell {cid}")
        arm = choice(game.get("arm"), ARMS, "arm")
        require((cid, arm) not in games, f"duplicate result {cid}/{arm}")
        cell = plan[cid]
        # Equality alone accepts bool==int. Validate types before checking provenance.
        for field in ("seed", "seat", "replicate"):
            integer(game.get(field), f"game.{field}")
        for field in ("opponent_id", "split", "opponent_sha256"):
            text(game.get(field), f"game.{field}")
        for field in ("opponent_id", "seed", "seat", "replicate", "split", "opponent_sha256"):
            require(game.get(field) == cell[field], f"{cid}/{arm}: mismatched {field}")
        require(digest(game.get("agent_sha256"), "agent_sha256") == artifacts[arm],
                f"{cid}/{arm}: agent source drift")
        require(digest(game.get("engine_sha256"), "game.engine_sha256") == engine,
                f"{cid}/{arm}: engine source drift")
        status = choice(game.get("status"), STATES, "status")
        completed = integer(game.get("completed_callbacks"), "completed_callbacks", 0)
        require(completed <= expected, "callbacks exceed plan")
        integer(game.get("fallbacks"), "fallbacks", 0)
        require(game["fallbacks"] <= completed, "fallbacks exceed completed callbacks")
        banks = game.get("banks")
        if banks is not None:
            require(isinstance(banks, list) and len(banks) == 2, "banks must have two seats")
            for bank in banks:
                integer(bank, "bank")
        if status == "complete":
            require(completed == expected and banks is not None,
                    "complete result needs all callbacks and terminal banks")
        games[(cid, arm)] = game
    missing, failed, fallback, pairs = [], [], [], []
    for cid, cell in sorted(plan.items()):
        for arm in ARMS:
            game = games.get((cid, arm))
            if game is None:
                missing.append({"cell_id": cid, "arm": arm})
            elif game["status"] != "complete":
                failed.append({"cell_id": cid, "arm": arm, "status": game["status"]})
            if game and game["fallbacks"]:
                fallback.append({"cell_id": cid, "arm": arm, "count": game["fallbacks"]})
        a, b = (games.get((cid, arm)) for arm in ARMS)
        if not (a and b and a["status"] == b["status"] == "complete"):
            continue
        seat = cell["seat"]
        own = b["banks"][seat] - a["banks"][seat]
        rival = b["banks"][1-seat] - a["banks"][1-seat]
        am = a["banks"][seat] - a["banks"][1-seat]
        bm = b["banks"][seat] - b["banks"][1-seat]
        pairs.append({**cell, "kind": opponents[cell["opponent_id"]]["kind"],
                      "baseline_margin": am, "candidate_margin": bm,
                      "delta_own": own, "delta_rival": rival, "delta_margin": own-rival,
                      "new_loss": am >= 0 > bm, "lost_win": am > 0 >= bm,
                      "baseline_fallbacks": a["fallbacks"], "candidate_fallbacks": b["fallbacks"]})
    buckets = defaultdict(list)
    # Retain even wholly missing/failed opponent partitions in the visible table.
    for c in plan.values():
        buckets[(c["split"], opponents[c["opponent_id"]]["kind"], c["opponent_id"])]
    for p in pairs:
        buckets[(p["split"], p["kind"], p["opponent_id"])].append(p)
    grouped = []
    for (split, kind, oid), pp in sorted(buckets.items()):
        cluster = defaultdict(list)
        for p in pp:
            cluster[p["seed"]].append(p["delta_margin"])
        grouped.append({"split": split, "kind": kind, "opponent_id": oid,
                        "expected_pairs": sum(c["opponent_id"] == oid and c["split"] == split for c in plan.values()),
                        "observed_pairs": len(pp), "seed_clusters": len(cluster),
                        "delta_margin": statistics([p["delta_margin"] for p in pp]),
                        "delta_own": statistics([p["delta_own"] for p in pp]),
                        "delta_rival": statistics([p["delta_rival"] for p in pp]),
                        "candidate_margin": statistics([p["candidate_margin"] for p in pp]),
                        "seed_cluster_means": [{"seed": seed, "mean": mean(values), "pairs": len(values)}
                                               for seed, values in sorted(cluster.items())],
                        "new_losses": sum(p["new_loss"] for p in pp),
                        "lost_wins": sum(p["lost_win"] for p in pp)})
    return {"schema": "titan.gauntlet.audit.v1", "mode": "planned_paired",
            "expected_games": 2*len(plan), "observed_games": len(games),
            "complete_pairs": len(pairs), "missing": missing, "failed": failed,
            "fallbacks": fallback, "coverage_complete": not missing and not failed,
            "runtime_clean": not missing and not failed and not fallback,
            "groups": grouped, "pairs": pairs, "promotion_decision": "NOT_ASSESSED",
            "limitations": ["Input hashes are asserted provenance, not independently fetched bytes.",
                "Only predeclared plan coverage is audited; completeness of the broader field is unknown.",
                "Complete fallback games remain in economics; missing/error games are exposed, never assigned zero gain.",
                "No IID confidence interval: seats/replicates sharing a seed are clustered, not independent samples.",
                "Kinds and tuning/holdout partitions are reported separately, not pooled.",
                "Paired coverage or positive mean alone does not authorize promotion."]}


def audit(document: Any) -> dict:
    document = obj(document, "document")
    if document.get("schema") == "titan.gauntlet.summary.v1":
        return audit_summary(document)
    if document.get("schema") == "titan.gauntlet.paired.v1":
        return audit_paired(document)
    raise AuditError("unsupported schema; adapt explicitly rather than guessing columns")


def unique_object(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key {key}")
        result[key] = value
    return result


def reject_constant(value: str) -> None:
    raise AuditError(f"non-finite JSON constant {value}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.output is not None:
            require(args.input.resolve() != args.output.resolve(), "output must not replace input")
        raw = args.input.read_bytes()
        report = audit(json.loads(raw, object_pairs_hook=unique_object, parse_constant=reject_constant))
        report["input_sha256"] = hashlib.sha256(raw).hexdigest()
        report["input_bytes"] = len(raw)
        rendered = json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
        if args.output:
            args.output.write_text(rendered, encoding="utf-8")
        else:
            print(rendered, end="")
        if report["mode"] == "reported_summary":
            return 3  # descriptive output exists; not a raw paired coverage pass
        return 0 if report["runtime_clean"] else 1
    except (AuditError, OSError, ValueError, TypeError, KeyError) as exc:
        print(f"gauntlet audit error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
