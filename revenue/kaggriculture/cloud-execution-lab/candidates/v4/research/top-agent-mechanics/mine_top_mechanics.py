#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Mine mechanics enriched among an explicitly supplied top-agent cohort.

Input is event-level CSV from Kaggriculture replays (farmer actions and/or
market orders).  Column names are alias-resolved; top-team identity is always
explicit so leaderboard membership is never inferred from event volume.

The unit of support is a UNIQUE TEAM: a feature counts once for a team no
matter how many matches/events that team contributed.  This prevents prolific
teams from dominating the enrichment ranking.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from sequence_contract import sequence_windows

ALIASES = {
    "match": ("match_id", "episode_id", "episode", "game_id", "match", "replay_id"),
    "team": ("team", "team_id", "team_name", "submission_id", "agent", "agent_id", "submission"),
    "player": ("player", "seat", "player_index", "agent_index", "player_id"),
    "step": ("step", "timestep", "turn", "turn_id", "step_id"),
    "verb": ("action_verb", "verb", "action", "action_type", "order_type", "command"),
    "target": ("target", "item", "product", "crop", "animal", "building", "resource"),
    "qty": ("qty", "quantity", "amount", "units", "count"),
    "actor": ("actor", "actor_id", "farmer_id", "hand_id", "unit_id", "worker_id"),
    "slot": ("raw_slot", "market_index", "order_index", "order_slot"),
}

PHASES = ((0, 239, "early"), (240, 479, "mid"), (480, 719, "late"), (720, 10**9, "post"))

class DataError(ValueError):
    pass

@dataclass(frozen=True)
class Event:
    match: str
    team: str
    player: str
    step: int
    source: str
    verb: str
    target: str
    qty: float | None
    ordinal: int
    actor: str | None = None
    slot: int | None = None


def _norm_name(s: str) -> str:
    return s.strip().lower().replace(" ", "_").replace("-", "_")


def _column(fieldnames: list[str], logical: str, *, required: bool) -> str | None:
    norm = {_norm_name(name): name for name in fieldnames if name is not None}
    for alias in ALIASES[logical]:
        if alias in norm:
            return norm[alias]
    if required:
        raise DataError(f"missing {logical!r} column; accepted aliases={ALIASES[logical]!r}; got={fieldnames!r}")
    return None


def _strict_step(raw: str, *, path: Path, row_no: int) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise DataError(f"{path}:{row_no}: invalid step {raw!r}") from exc
    if value < 0:
        raise DataError(f"{path}:{row_no}: negative step")
    return value


def _qty(raw: str | None) -> float | None:
    if raw is None or raw == "":
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def read_events(path: Path, source: str) -> list[Event]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise DataError(f"{path}: missing header")
        cols = {
            "match": _column(reader.fieldnames, "match", required=True),
            "team": _column(reader.fieldnames, "team", required=True),
            "player": _column(reader.fieldnames, "player", required=False),
            "step": _column(reader.fieldnames, "step", required=True),
            "verb": _column(reader.fieldnames, "verb", required=True),
            "target": _column(reader.fieldnames, "target", required=False),
            "qty": _column(reader.fieldnames, "qty", required=False),
            "actor": _column(reader.fieldnames, "actor", required=False),
            "slot": _column(reader.fieldnames, "slot", required=False),
        }
        out: list[Event] = []
        for ordinal, row in enumerate(reader):
            row_no = ordinal + 2
            match = (row.get(cols["match"]) or "").strip()
            team = (row.get(cols["team"]) or "").strip()
            verb = (row.get(cols["verb"]) or "").strip().upper()
            if not match or not team or not verb:
                raise DataError(f"{path}:{row_no}: empty match/team/verb")
            player = (row.get(cols["player"]) or "?").strip() if cols["player"] else "?"
            target = (row.get(cols["target"]) or "").strip().upper() if cols["target"] else ""
            actor = (row.get(cols["actor"]) or "").strip() if cols["actor"] else ""
            raw_slot = (row.get(cols["slot"]) or "").strip() if cols["slot"] else ""
            slot = _strict_step(raw_slot, path=path, row_no=row_no) if raw_slot else None
            out.append(Event(
                match=match,
                team=team,
                player=player,
                step=_strict_step(row.get(cols["step"]), path=path, row_no=row_no),
                source=source,
                verb=verb,
                target=target,
                qty=_qty(row.get(cols["qty"])) if cols["qty"] else None,
                ordinal=ordinal,
                actor=actor or None,
                slot=slot,
            ))
    return out


def phase(step: int) -> str:
    for lo, hi, name in PHASES:
        if lo <= step <= hi:
            return name
    return "post"


def token(event: Event) -> str:
    base = f"{event.source}:{event.verb}"
    return f"{base}:{event.target}" if event.target else base


def _bucket_count(n: int) -> str:
    if n == 0: return "0"
    if n == 1: return "1"
    if n <= 3: return "2-3"
    if n <= 7: return "4-7"
    return "8+"


def _bucket_qty(value: float) -> str:
    if value <= 0: return "<=0"
    if value <= 1: return "0-1"
    if value <= 3: return "1-3"
    if value <= 7: return "3-7"
    if value <= 15: return "7-15"
    return "15+"


def features_by_team(events: Iterable[Event]) -> tuple[dict[str, set[str]], dict[str, int]]:
    by_team_match: dict[tuple[str, str, str], list[Event]] = defaultdict(list)
    for event in events:
        by_team_match[(event.team, event.match, event.player)].append(event)
    if not by_team_match:
        raise DataError("no events")

    team_features: dict[str, set[str]] = defaultdict(set)
    team_matches: dict[str, int] = defaultdict(int)
    match_ids: dict[str, set[str]] = defaultdict(set)
    for (team, _match, _player), rows in by_team_match.items():
        match_ids[team].add(_match)
        team_matches[team] = len(match_ids[team])
        rows.sort(key=lambda e: (e.step, e.source, e.player, e.ordinal))
        feats: set[str] = set()
        per_verb: dict[str, int] = defaultdict(int)
        per_step: dict[tuple[str, int], set[str]] = defaultdict(set)
        per_day: dict[tuple[int, str], int] = defaultdict(int)
        seen_first: set[str] = set()
        for event in rows:
            p = phase(event.step)
            tok = token(event)
            per_verb[tok] += 1
            if event.player and event.player != "?":
                per_step[(event.player, event.step)].add(tok)
            per_day[(event.step // 24, tok)] += 1
            feats.add(f"event|{tok}")
            feats.add(f"phase|{p}|{tok}")
            if event.target:
                feats.add(f"verb_target|{event.verb}|{event.target}")
            if event.qty is not None:
                feats.add(f"qty_bucket|{_bucket_qty(event.qty)}|{tok}")
            if tok not in seen_first:
                feats.add(f"first_phase|{p}|{tok}")
                feats.add(f"first_day_bucket|{min(event.step // 24, 29)}|{tok}")
                seen_first.add(tok)

        for tok, n in per_verb.items():
            feats.add(f"count_bucket|{_bucket_count(n)}|{tok}")
        for (day, tok), n in per_day.items():
            if day <= 3 or day >= 26:
                feats.add(f"day_presence|{day}|{tok}")
                feats.add(f"day_count_bucket|{day}|{_bucket_count(n)}|{tok}")
        for _step, toks in per_step.items():
            ordered = sorted(toks)
            for i in range(len(ordered)):
                for j in range(i + 1, len(ordered)):
                    feats.add(f"same_step|{ordered[i]}+{ordered[j]}")
        # Record chronology only when the observed ordering is unambiguous.
        # actor_seq additionally proves same-actor identity; neither means fills.
        feats.update(feature for feature, _ in sequence_windows(rows, token))
        team_features[team].update(feats)
    return dict(team_features), dict(team_matches)


def rank_features(events: Iterable[Event], top_teams: set[str], *, min_top_teams: int = 2,
                  min_top_support: float = 0.2, limit: int = 250) -> dict:
    team_features, team_matches = features_by_team(events)
    known = set(team_features)
    missing = sorted(top_teams - known)
    top = sorted(known & top_teams)
    field = sorted(known - top_teams)
    if missing:
        raise DataError(f"top-team labels absent from events: {missing!r}")
    if len(top) < 2:
        raise DataError("need at least two top teams present")
    if not field:
        raise DataError("need at least one field team")

    universe = set().union(*(team_features[t] for t in known))
    rows = []
    for feat in universe:
        a = sum(feat in team_features[t] for t in top)
        c = sum(feat in team_features[t] for t in field)
        top_support = a / len(top)
        field_support = c / len(field)
        if a < min_top_teams or top_support < min_top_support:
            continue
        # Jeffreys-smoothed log odds on team support, not event counts.
        b = len(top) - a
        d = len(field) - c
        log_odds = math.log((a + 0.5) / (b + 0.5)) - math.log((c + 0.5) / (d + 0.5))
        rows.append({
            "feature": feat,
            "top_teams_with": a,
            "top_teams": len(top),
            "top_support": top_support,
            "field_teams_with": c,
            "field_teams": len(field),
            "field_support": field_support,
            "support_delta": top_support - field_support,
            "log_odds": log_odds,
        })
    rows.sort(key=lambda r: (-r["support_delta"], -r["log_odds"], -r["top_support"], r["feature"]))
    return {
        "schema": "titan-v4-top-agent-mechanics/v2",
        "sequence_contract": {
            "seq": "recorded same-player/source chronology; not necessarily same actor",
            "actor_seq": "recorded chronology of one explicitly identified unit actor",
            "ambiguity": "same-step rows without known order break sequences; no skip-through",
            "market": "equal-step order requires explicit unique raw slots",
            "scope": "observed intent, not successful execution, causal proof, or consecutive callbacks",
        },
        "top_teams": top,
        "field_team_count": len(field),
        "team_match_counts": {t: team_matches[t] for t in sorted(known)},
        "features_considered": len(universe),
        "features_returned": min(limit, len(rows)),
        "ranking": rows[:limit],
        "interpretation": (
            "Support is per unique team, not per event or match. Enrichment is candidate-generation only; "
            "each mechanic still needs an exact replay witness and current-policy overlap check before becoming a gameplay lane."
        ),
    }


def parse_top_teams(value: str) -> set[str]:
    path = Path(value)
    if path.exists():
        teams = {line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip() and not line.lstrip().startswith("#")}
    else:
        teams = {part.strip() for part in value.split(",") if part.strip()}
    if not teams:
        raise DataError("empty top-team set")
    return teams


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--farmer-actions", type=Path)
    ap.add_argument("--market-orders", type=Path)
    ap.add_argument("--top-teams", required=True, help="comma list or newline-delimited file; explicit leaderboard cohort")
    ap.add_argument("--min-top-teams", type=int, default=2)
    ap.add_argument("--min-top-support", type=float, default=0.2)
    ap.add_argument("--limit", type=int, default=250)
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()
    if args.farmer_actions is None and args.market_orders is None:
        ap.error("provide --farmer-actions and/or --market-orders")
    try:
        events = []
        if args.farmer_actions:
            events += read_events(args.farmer_actions, "unit")
        if args.market_orders:
            events += read_events(args.market_orders, "market")
        report = rank_features(events, parse_top_teams(args.top_teams),
                               min_top_teams=args.min_top_teams,
                               min_top_support=args.min_top_support, limit=args.limit)
    except (DataError, OSError) as exc:
        ap.error(str(exc))
    payload = json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
