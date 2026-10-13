#!/usr/bin/env python3
"""Offline, provenance-preserving reporting for Kaggriculture hosted replays.

Does not simulate games, invoke agents, fetch data, or change a submission. An
explicit provider-feed manifest is required for a *latest* N claim. Episode IDs,
UUIDs, upload times and filesystem times are never treated as chronology.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

NAME = re.compile(r"^(?P<episode>[0-9]+)(?:-(?P<seat>[0-9]+))?(?:\([0-9]+\))?\.json$")
TERMINAL = frozenset({"DONE", "ERROR", "INVALID", "TIMEOUT"})
FAULT = TERMINAL - {"DONE"}


class InputError(ValueError):
    """An input cannot safely contribute to the requested report."""


def positive_id(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise InputError(f"{field} must be a positive integer")
    return value


def finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def strict_json(data: bytes) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for k, v in items:
            if k in result:
                raise InputError(f"duplicate JSON key: {k}")
            result[k] = v
        return result
    def bad_constant(value: str) -> None:
        raise InputError(f"non-finite JSON constant: {value}")
    try:
        return json.loads(data, object_pairs_hook=pairs, parse_constant=bad_constant)
    except (ValueError, UnicodeError) as exc:
        raise InputError(str(exc)) from exc


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def semantic_digest(value: Any) -> str:
    return digest(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode())


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    index = (len(values) - 1) * q
    lo, hi = math.floor(index), math.ceil(index)
    return values[lo] + (values[hi] - values[lo]) * (index - lo)


def resolve_seat(replay: dict[str, Any], team: str) -> int:
    info = replay.get("info")
    if not isinstance(info, dict):
        raise InputError("replay info is missing")
    names = info.get("TeamNames")
    if not isinstance(names, list) or len(names) != 2 or not all(isinstance(n, str) for n in names):
        raise InputError("exact two-player TeamNames are required")
    hits = [i for i, name in enumerate(names) if name == team]
    if len(hits) != 1:
        raise InputError(f"team {team!r} must identify exactly one seat")
    agents = info.get("Agents")
    if agents is not None:
        if not isinstance(agents, list) or len(agents) != 2 or any(
            not isinstance(a, dict) or a.get("Name") != names[i] for i, a in enumerate(agents)
        ):
            raise InputError("Agents names and TeamNames disagree")
    return hits[0]


def parse_replay(value: Any, team: str, filename_id: int) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("name") != "kaggriculture":
        raise InputError("not a Kaggriculture replay")
    seat = resolve_seat(value, team)
    episode = positive_id(value["info"].get("EpisodeId"), "EpisodeId")
    if episode != filename_id:
        raise InputError("filename episode ID does not match replay EpisodeId")
    steps = value.get("steps")
    if not isinstance(steps, list) or not steps:
        raise InputError("replay steps are missing")
    faults = [[], []]
    for index, step in enumerate(steps):
        if not isinstance(step, list) or len(step) != 2 or not all(isinstance(s, dict) for s in step):
            raise InputError(f"step {index} is not a two-player state")
        for s, state in enumerate(step):
            if not isinstance(state.get("status"), str):
                raise InputError(f"step {index} has a missing or non-text status")
            if state.get("status") in FAULT:
                faults[s].append({"step_index": index, "status": state["status"]})
    final = steps[-1]
    statuses = value.get("statuses")
    final_statuses = [s.get("status") for s in final]
    if statuses is None:
        statuses = final_statuses
    if not isinstance(statuses, list) or len(statuses) != 2 or statuses != final_statuses:
        raise InputError("top-level statuses disagree with terminal states")
    rewards = value.get("rewards")
    final_rewards = [s.get("reward") for s in final]
    if rewards is None:
        rewards = final_rewards
    if not isinstance(rewards, list) or len(rewards) != 2 or rewards != final_rewards:
        raise InputError("top-level rewards disagree with terminal states")
    done = all(s in TERMINAL for s in statuses)
    scored = done and all(finite_number(r) for r in rewards)
    margin = float(rewards[seat] - rewards[1 - seat]) if scored else None
    outcome = ("win" if margin > 0 else "loss" if margin < 0 else "tie") if scored else None
    config = value.get("configuration", {})
    timeout = config.get("actTimeout") if isinstance(config, dict) else None
    return {
        "episode_id": episode, "own_seat": seat, "own_team": team,
        "opponent": value["info"]["TeamNames"][1 - seat],
        "status": "scored_terminal" if scored else "unscored_terminal" if done else "incomplete",
        "statuses": statuses, "rewards_by_seat": rewards,
        "own_reward": rewards[seat], "opponent_reward": rewards[1 - seat],
        "cash_margin": margin, "outcome": outcome,
        "replay_frames": len(steps), "expected_own_log_frames": len(steps) - 1,
        "own_fault_statuses": faults[seat], "opponent_fault_statuses": faults[1 - seat],
        "act_timeout_seconds": float(timeout) if finite_number(timeout) and timeout >= 0 else None,
        "source_module_version": value.get("module_version"),
        "own_submission_id": None, "finished_at": None, "opponent_rating": None,
        "own_log": {"status": "missing"},
    }


def parse_log(value: Any) -> dict[str, Any]:
    if not isinstance(value, list):
        raise InputError("agent log must be a list of per-action frames")
    durations: list[float] = []
    stdout_count = stderr_count = empty_frames = 0
    for index, frame in enumerate(value):
        if not isinstance(frame, list):
            raise InputError(f"log frame {index} must be a list")
        if not frame:
            empty_frames += 1
        for item in frame:
            if not isinstance(item, dict) or not finite_number(item.get("duration")) or item["duration"] < 0:
                raise InputError(f"log frame {index} has an invalid duration")
            for field in ("stdout", "stderr"):
                if not isinstance(item.get(field, ""), str):
                    raise InputError(f"log frame {index} has non-text {field}")
            durations.append(float(item["duration"]))
            stdout_count += bool(item.get("stdout"))
            stderr_count += bool(item.get("stderr"))
    return {
        "status": "available", "binding": "filename_episode_id_and_seat; log has no embedded identity",
        "frames": len(value), "empty_frames": empty_frames, "duration_samples": len(durations),
        "total_duration_seconds": sum(durations), "p50_seconds": percentile(durations, .50),
        "p95_seconds": percentile(durations, .95), "p99_seconds": percentile(durations, .99),
        "max_seconds": max(durations, default=None),
        "stdout_nonempty_entries": stdout_count, "stderr_nonempty_entries": stderr_count,
        "note": "Recorded duration is not an independent measurement of evaluator deadline enforcement.",
    }


def source_paths(inputs: Iterable[Path]) -> list[Path]:
    paths: set[Path] = set()
    for path in inputs:
        if path.is_dir():
            paths.update(p.resolve() for p in path.rglob("*.json") if NAME.fullmatch(p.name) and p.is_file())
        elif path.is_file() and NAME.fullmatch(path.name):
            paths.add(path.resolve())
        else:
            raise InputError(f"not a supported input file or directory: {path}")
    return sorted(paths)


def load_inputs(inputs: Iterable[Path], team: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    found: dict[tuple[int, int | None], tuple[str, dict[str, Any]]] = {}
    conflicts: set[tuple[int, int | None]] = set()
    issues: list[dict[str, Any]] = []
    for path in source_paths(inputs):
        match = NAME.fullmatch(path.name)
        assert match is not None
        key = (int(match["episode"]), int(match["seat"]) if match["seat"] is not None else None)
        try:
            data = path.read_bytes()
            value = strict_json(data)
            parsed = parse_replay(value, team, key[0]) if key[1] is None else parse_log(value)
            if key[1] not in (None, 0, 1):
                raise InputError("log seat must be 0 or 1")
            source = {"name": path.name, "path": str(path), "bytes": len(data), "sha256": digest(data)}
            signature = semantic_digest(value)
            if key in conflicts:
                issues.append({"source": source, "error": "excluded: identity already has conflicting content"})
                continue
            if key in found:
                old_signature, old_parsed = found[key]
                if old_signature == signature:
                    old_parsed["sources"].append(source)
                else:
                    conflicts.add(key)
                    del found[key]
                    issues.append({"episode_id": key[0], "log_seat": key[1], "sources": old_parsed["sources"] + [source],
                                   "error": "conflicting content for the same episode/seat; excluded"})
            else:
                parsed["sources"] = [source]
                found[key] = signature, parsed
        except (InputError, OSError, OverflowError) as exc:
            issues.append({"source": str(path), "episode_id": key[0], "log_seat": key[1], "error": str(exc)})
    rows = []
    for (episode, seat), (_, row) in found.items():
        if seat is not None:
            continue
        log_key = (episode, row["own_seat"])
        if log_key in found:
            row["own_log"] = found[log_key][1]
            row["own_log"]["frame_count_matches_replay"] = row["own_log"]["frames"] == row["expected_own_log_frames"]
            maximum, timeout = row["own_log"]["max_seconds"], row["act_timeout_seconds"]
            row["own_log"]["max_recorded_duration_exceeds_act_timeout"] = maximum > timeout if maximum is not None and timeout is not None else None
        elif log_key in conflicts:
            row["own_log"] = {"status": "conflicting_sources"}
        rows.append(row)
    for (episode, seat), (_, log) in found.items():
        if seat is not None and (episode, None) not in found:
            issues.append({"episode_id": episode, "log_seat": seat, "sources": log["sources"],
                           "error": "orphan log: no valid matching replay; not used as result or another game's log"})
    return sorted(rows, key=lambda row: row["episode_id"]), issues


def summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    scored = [row for row in rows if row["outcome"] is not None]
    return {
        "episodes": len(rows), "scored_terminal": len(scored),
        "wins": sum(r["outcome"] == "win" for r in scored),
        "ties": sum(r["outcome"] == "tie" for r in scored),
        "losses": sum(r["outcome"] == "loss" for r in scored),
        "unscored_or_incomplete": len(rows) - len(scored),
        "win_fraction": sum(r["outcome"] == "win" for r in scored) / len(scored) if scored else None,
        "cash_margin_sum": sum(r["cash_margin"] for r in scored),
        "own_fault_status_episodes": sum(bool(r["own_fault_statuses"]) for r in rows),
        "own_log_available": sum(r["own_log"]["status"] == "available" for r in rows),
        "opponent_rating_available": sum(r["opponent_rating"] is not None for r in rows),
    }


def zoned_timestamp(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise InputError(f"{field} must be a timezone-qualified ISO 8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise InputError(f"invalid {field}") from exc
    if parsed.tzinfo is None:
        raise InputError(f"{field} must contain a timezone")
    return value


def apply_feed(rows: list[dict[str, Any]], feed: Any) -> tuple[list[int], str, int]:
    if not isinstance(feed, dict) or feed.get("schema_version") != 1:
        raise InputError("feed manifest schema_version must be 1")
    as_of = zoned_timestamp(feed.get("as_of"), "as_of")
    submission = positive_id(feed.get("own_submission_id"), "own_submission_id")
    if not isinstance(feed.get("source_reference"), str) or not feed["source_reference"].strip():
        raise InputError("feed source_reference is required")
    ids = feed.get("latest_completed_episode_ids_newest_first")
    if not isinstance(ids, list) or not ids:
        raise InputError("feed must contain an explicitly ordered completed-episode ID list")
    ids = [positive_id(i, "episode ID") for i in ids]
    if len(set(ids)) != len(ids):
        raise InputError("feed ordered episode IDs contain duplicates")
    details = feed.get("episodes")
    if not isinstance(details, list):
        raise InputError("feed episodes metadata is required")
    metadata = {}
    for detail in details:
        if not isinstance(detail, dict):
            raise InputError("feed episode metadata must be an object")
        episode = positive_id(detail.get("episode_id"), "episode_id")
        if episode in metadata:
            raise InputError("duplicate episode metadata in feed")
        positive_id(detail.get("own_submission_id"), "episode own_submission_id")
        if detail.get("finished_at") is not None:
            zoned_timestamp(detail["finished_at"], "finished_at")
        if detail.get("opponent_rating") is not None and not finite_number(detail["opponent_rating"]):
            raise InputError("opponent_rating must be finite or absent")
        metadata[episode] = detail
    as_of_dt = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
    prior_finished = None
    for episode in ids:
        finished = metadata.get(episode, {}).get("finished_at")
        if finished is None:
            continue
        parsed_finished = datetime.fromisoformat(finished.replace("Z", "+00:00"))
        if parsed_finished > as_of_dt:
            raise InputError("episode completion is later than the feed as_of time")
        if prior_finished is not None and parsed_finished > prior_finished:
            raise InputError("explicit feed order contradicts supplied completion timestamps")
        prior_finished = parsed_finished
    for row in rows:
        detail = metadata.get(row["episode_id"], {})
        for key in ("own_submission_id", "finished_at", "opponent_rating"):
            row[key] = detail.get(key)
    return ids, as_of, submission


def build_report(inputs: Iterable[Path], team: str, windows: Iterable[int] = (20, 50), feed: Any = None) -> dict[str, Any]:
    if not isinstance(team, str) or not team.strip():
        raise InputError("an explicit team name is required")
    sizes = list(windows)
    if not sizes or any(isinstance(n, bool) or not isinstance(n, int) or n <= 0 for n in sizes):
        raise InputError("windows must be positive integers")
    rows, issues = load_inputs(inputs, team)
    latest = {}
    feed_info = None
    if feed is not None:
        ids, as_of, submission = apply_feed(rows, feed)
        feed_info = {"as_of": as_of, "own_submission_id": submission, "source_reference": feed["source_reference"],
                     "basis": "caller-supplied provider-feed manifest; no live request made by this tool"}
    by_id = {r["episode_id"]: r for r in rows}
    for n in sizes:
        reason = None
        if feed is None:
            reason = "no_explicit_latest_feed_manifest"
        elif len(ids) < n:
            reason = "feed_has_fewer_than_requested_completed_episodes"
        else:
            chosen = ids[:n]
            missing = [i for i in chosen if i not in by_id]
            unscored = [i for i in chosen if i in by_id and by_id[i]["outcome"] is None]
            mismatch = [i for i in chosen if i in by_id and by_id[i]["own_submission_id"] != submission]
            if missing or unscored or mismatch:
                latest[str(n)] = {"status": "withheld", "missing_replay_ids": missing,
                                  "unscored_episode_ids": unscored, "submission_mismatch_or_missing_metadata_ids": mismatch}
                continue
            latest[str(n)] = {"status": "computed_from_supplied_feed", "as_of": as_of,
                              "episode_ids_newest_first": chosen, **summary([by_id[i] for i in chosen])}
            continue
        latest[str(n)] = {"status": "withheld", "reason": reason, "available_replay_count": len(rows)}
    return {
        "schema_version": 1, "team": team, "scope": "supplied_replay_sample_not_population_win_rate",
        "row_order": "episode_id_for_stable_display_only_not_chronology",
        "feed": feed_info, "sample": summary(rows), "latest_windows": latest,
        "episodes": rows, "input_issues": issues,
        "limits": ["Selected replays do not establish the latest 20/50 matches or a population win rate.",
                   "No opponent ratings, submission bindings, or completion timestamps are inferred.",
                   "DONE status and log durations are observations, not proof of absence of all runtime faults.",
                   "A missing own log is never replaced by another episode or another seat."],
    }


def markdown(report: dict[str, Any]) -> str:
    s = report["sample"]
    out = ["# Private hosted replay report", "", f"Team: {report['team']}", "",
           f"Supplied development sample: {s['episodes']} distinct episodes; {s['wins']} win(s), {s['ties']} tie(s), {s['losses']} loss(es).",
           "This is not the current overall or recent-20/50 win rate.", "",
           "| Episode | Own seat | Opponent | Own reward | Opponent reward | Margin | Own log |",
           "|---|---:|---|---:|---:|---:|---|"]
    def safe(value: Any) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ")
    for r in report["episodes"]:
        out.append("| " + " | ".join(safe(x) for x in (r['episode_id'], r['own_seat'], r['opponent'], r['own_reward'],
                       r['opponent_reward'], r['cash_margin'], r['own_log']['status'])) + " |")
    out += ["", "## Latest-window coverage", ""]
    for n, w in report["latest_windows"].items():
        out.append(f"Latest {n}: {w['status']}; {w.get('reason', 'see JSON coverage details')}.")
    out += ["", "## Recorded own-agent timings", ""]
    for r in report["episodes"]:
        log = r["own_log"]
        if log["status"] == "available" and log["duration_samples"]:
            out.append(f"Episode {r['episode_id']}, seat {r['own_seat']}: {log['duration_samples']} samples, "
                       f"p99 {log['p99_seconds']:.6f}s, max {log['max_seconds']:.6f}s; "
                       f"nonempty stderr entries {log['stderr_nonempty_entries']}. "
                       f"Log frame count matches replay: {log['frame_count_matches_replay']}.")
    out += ["", "## Limits", ""] + report["limits"]
    out += ["", f"Input issues: {len(report['input_issues'])}. Full source hashes, aliases, and exclusions are in the JSON report.", ""]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--team", required=True, help="Exact TeamNames entry; identifies either seat")
    parser.add_argument("--windows", nargs="+", type=int, default=[20, 50])
    parser.add_argument("--feed-manifest", type=Path, help="Explicit provider feed snapshot; never inferred from replay IDs")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown", type=Path)
    args = parser.parse_args(argv)
    try:
        feed = strict_json(args.feed_manifest.read_bytes()) if args.feed_manifest else None
        report = build_report(args.inputs, args.team, args.windows, feed)
        encoded = json.dumps(report, indent=2, allow_nan=False) + "\n"
        rendered = markdown(report) if args.markdown else None
        if args.output.exists() or (args.markdown and args.markdown.exists()):
            raise InputError("output already exists; choose new paths to preserve earlier reports")
        if args.markdown and args.output.resolve() == args.markdown.resolve():
            raise InputError("JSON and Markdown output paths must differ")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as f:
            f.write(encoded)
        if args.markdown:
            args.markdown.parent.mkdir(parents=True, exist_ok=True)
            with args.markdown.open("x", encoding="utf-8") as f:
                f.write(rendered or "")
        print(json.dumps({"output": str(args.output), "sample": report["sample"], "latest_windows": report["latest_windows"]}))
        return 2 if report["input_issues"] or not report["episodes"] else 0
    except (InputError, OSError, OverflowError) as exc:
        print(f"Input error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
