#!/usr/bin/env python3
"""Offline, provenance-bound summaries of supplied Kaggriculture replays.

This consumes an explicit local manifest, not a guessed provider API response.
It does not download, submit, execute agents, or infer missing timestamps/ratings.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any

FAILURES = {"ERROR", "TIMEOUT", "INVALID"}
STATUSES = FAILURES | {"ACTIVE", "INACTIVE", "DONE"}


def integer(value: Any, name: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


def number(value: Any, name: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    return float(value)


def timestamp(value: Any, name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{name} must be an ISO-8601 string with timezone")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{name} must be an ISO-8601 string with timezone") from exc
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return dt.astimezone(timezone.utc).isoformat(timespec="microseconds")


def load_json(path: Path) -> Any:
    # Reject NaN/Infinity rather than silently writing nonstandard report JSON.
    def reject(value: str) -> None:
        raise ValueError(f"non-finite JSON constant: {value}")
    with path.open(encoding="utf-8") as stream:
        return json.load(stream, parse_constant=reject)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def normalize(replay: dict, entry: dict, manifest: dict, source: dict) -> dict:
    if not isinstance(replay, dict) or replay.get("name") != "kaggriculture":
        raise ValueError("expected a Kaggriculture replay object")
    if not isinstance(replay.get("info"), dict) or not isinstance(replay.get("configuration"), dict):
        raise ValueError("replay info and configuration must be objects")
    episode = integer(replay["info"].get("EpisodeId"), "info.EpisodeId", 1)
    if "episode_id" in entry and integer(entry["episode_id"], "episode_id", 1) != episode:
        raise ValueError("manifest/replay episode identity mismatch")
    seat = integer(entry.get("own_seat"), "own_seat")
    if seat not in (0, 1):
        raise ValueError("own_seat must be 0 or 1; names do not select seats")
    submission = integer(manifest.get("submission_id"), "submission_id", 1)
    expected = integer(replay.get("configuration", {}).get("episodeSteps"), "episodeSteps", 2)
    steps = replay.get("steps")
    if not isinstance(steps, list) or not steps or len(steps) > expected:
        raise ValueError("steps must be a nonempty list no longer than episodeSteps")
    observed_failures = set()
    for index, frame in enumerate(steps):
        if not isinstance(frame, list) or len(frame) != 2:
            raise ValueError(f"frame {index} must contain two seats")
        for position, state in enumerate(frame):
            if not isinstance(state, dict) or state.get("status") not in STATUSES:
                raise ValueError(f"unrecognized state/status at {index}/{position}")
            observation = state.get("observation", {})
            if not isinstance(observation, dict):
                raise ValueError(f"invalid observation at {index}/{position}")
            if "step" in observation and integer(observation["step"], "observation.step") != index:
                raise ValueError(f"noncontiguous replay step at {index}/{position}")
            if state["status"] in FAILURES:
                observed_failures.add((position, state["status"]))
    final = steps[-1]
    statuses = [state["status"] for state in final]
    if replay.get("statuses") != statuses:
        raise ValueError("top-level and final-frame statuses disagree")
    rewards = replay.get("rewards")
    if not isinstance(rewards, list) or len(rewards) != 2:
        raise ValueError("rewards must contain two seats (null allowed for non-results)")
    for i, value in enumerate(rewards):
        if value is not None:
            number(value, "reward")
        if final[i].get("reward") != value:
            raise ValueError("top-level and final-frame rewards disagree")
    clean = statuses == ["DONE", "DONE"] and len(steps) == expected and not observed_failures
    kind = "completed" if clean else "runtime_failure" if observed_failures else "incomplete"
    if clean:
        own, rival = (number(rewards[i], "completed reward") for i in (seat, 1 - seat))
        outcome = "W" if own > rival else "L" if own < rival else "T"
    else:
        own = rival = outcome = None
    completed_at = timestamp(entry.get("completed_at"), "completed_at")
    if completed_at and manifest.get("as_of") and completed_at > timestamp(manifest["as_of"], "as_of"):
        raise ValueError("completed_at is later than snapshot as_of")
    rating = entry.get("opponent_rating_before")
    if rating is not None:
        rating = number(rating, "opponent_rating_before")
    metadata_evidence = entry.get("metadata_evidence")
    if metadata_evidence is not None and not isinstance(metadata_evidence, str):
        raise ValueError("metadata_evidence must be a string")
    if (completed_at is not None or rating is not None) and not metadata_evidence:
        raise ValueError("supplied completion time/rating needs metadata_evidence")
    names = replay.get("info", {}).get("TeamNames", [])
    opponent = names[1 - seat] if isinstance(names, list) and len(names) == 2 else None
    if opponent is not None and not isinstance(opponent, str):
        raise ValueError("opponent name must be a string")
    return dict(submission_id=submission, episode_id=episode, own_seat=seat,
                classification=kind, statuses=statuses, frame_count=len(steps),
                expected_frames=expected, decision_rounds=max(0, len(steps) - 1),
                outcome=outcome, own_cash=own, rival_cash=rival,
                margin=own - rival if clean else None, opponent_name=opponent,
                completed_at=completed_at, opponent_rating_before=rating,
                runtime_failures=[{"seat":p, "status":s} for p,s in sorted(observed_failures)],
                metadata_evidence=[metadata_evidence] if metadata_evidence else [], sources=[source])


def deduplicate(records: list[dict]) -> tuple[list[dict], list[dict], int]:
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for row in records:
        groups[tuple(row[k] for k in ("submission_id", "episode_id", "own_seat"))].append(row)
    unique, conflicts, duplicate_count = [], [], 0
    seats: dict[tuple, set] = defaultdict(set)
    for key in groups:
        seats[key[:2]].add(key[2])
    comparable = ("classification", "statuses", "frame_count", "outcome", "own_cash", "rival_cash")
    for key, rows in sorted(groups.items()):
        if len(seats[key[:2]]) != 1:
            conflicts.append({"identity":list(key), "reason":"multiple own-seat bindings for one hosted episode",
                              "records":rows})
            continue
        # A later terminal snapshot can supersede an ACTIVE partial snapshot.
        terminal = [r for r in rows if r["classification"] != "incomplete"]
        candidates = terminal or [r for r in rows if r["frame_count"] == max(x["frame_count"] for x in rows)]
        signatures = {json.dumps([r[k] for k in comparable], sort_keys=True) for r in candidates}
        differences = [k for k in ("completed_at", "opponent_rating_before", "opponent_name")
                       if len({r[k] for r in rows if r[k] is not None}) > 1]
        if len(signatures) != 1 or differences:
            conflicts.append({"identity": list(key), "reason": "contradictory snapshots or metadata",
                              "differing_metadata": differences, "records": rows})
            continue
        result = dict(candidates[0])
        for field in ("completed_at", "opponent_rating_before", "opponent_name"):
            result[field] = next((r[field] for r in rows if r[field] is not None), None)
        result["sources"] = [s for r in rows for s in r["sources"]]
        result["metadata_evidence"] = sorted({s for r in rows for s in r["metadata_evidence"]})
        result["superseded_partial_snapshots"] = len(rows) - len(candidates)
        result["duplicate_snapshots"] = len(rows) - 1
        duplicate_count += len(rows) - 1
        unique.append(result)
    return unique, conflicts, duplicate_count


def statistics(rows: list[dict]) -> dict:
    counts = Counter(row["outcome"] for row in rows)
    n = len(rows)
    return dict(n=n, wins=counts["W"], ties=counts["T"], losses=counts["L"],
                win_rate=counts["W"] / n if n else None,
                result_score_rate=(counts["W"] + counts["T"] / 2) / n if n else None,
                mean_margin=sum(r["margin"] for r in rows) / n if n else None)


def analyze(manifest_path: Path) -> dict:
    manifest = load_json(manifest_path)
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise ValueError("manifest schema_version must be 1")
    integer(manifest.get("submission_id"), "submission_id", 1)
    if not isinstance(manifest.get("identity_evidence"), str) or not manifest["identity_evidence"].strip():
        raise ValueError("identity_evidence must describe external submission/seat binding")
    entries = manifest.get("entries")
    if not isinstance(entries, list) or not entries:
        raise ValueError("entries must be a nonempty list")
    as_of = timestamp(manifest.get("as_of"), "as_of")
    declared = manifest.get("coverage_complete", False)
    if type(declared) is not bool:
        raise ValueError("coverage_complete must be boolean")
    if declared and (not as_of or not manifest.get("coverage_evidence")):
        raise ValueError("complete coverage declaration needs as_of and coverage_evidence")
    records, rejected = [], []
    for index, entry in enumerate(entries):
        try:
            if not isinstance(entry, dict) or not isinstance(entry.get("replay"), str):
                raise ValueError("each entry needs a replay path")
            path = (manifest_path.parent / entry["replay"]).resolve()
            source = {"manifest_entry":index, "path":entry["replay"], "sha256":sha256(path)}
            records.append(normalize(load_json(path), entry, manifest, source))
        except (OSError, ValueError, TypeError, KeyError, OverflowError) as exc:
            rejected.append({"manifest_entry":index, "error":str(exc)})
    rows, conflicts, duplicates = deduplicate(records)
    clean = [r for r in rows if r["classification"] == "completed"]
    missing_times = sum(r["completed_at"] is None for r in clean)
    dated = sorted((r for r in clean if r["completed_at"]), key=lambda r:r["completed_at"], reverse=True)
    windows = {}
    for size in (20, 50):
        chosen = dated[:size]
        # Same-time boundary cohorts cannot be ordered by episode ID or filename.
        if chosen:
            cutoff = chosen[-1]["completed_at"]
            chosen = [r for r in dated if r["completed_at"] >= cutoff]
        reasons = []
        if not declared: reasons.append("history coverage is not declared complete")
        if rejected: reasons.append("one or more inputs were rejected")
        if conflicts: reasons.append("episode snapshots conflict")
        if missing_times: reasons.append("completed episodes lack completion timestamps")
        if len(dated) < size: reasons.append(f"fewer than {size} dated completed episodes")
        if len(chosen) > size: reasons.append("timestamp tie straddles the window boundary")
        windows[str(size)] = {"requested_completed_games":size, "supported":not reasons,
                             "unsupported_reasons":reasons,
                             "scope":"supplied dated normal completions; coverage is a manifest declaration",
                             "statistics":statistics(chosen) if chosen else None,
                             "episode_ids":[r["episode_id"] for r in chosen]}
    by_opponent, by_band = defaultdict(list), defaultdict(list)
    for row in clean:
        by_opponent[row["opponent_name"] or "unknown"].append(row)
        rating = row["opponent_rating_before"]
        band = "unknown" if rating is None else "below_2000" if rating < 2000 else "2000_to_below_2500" if rating < 2500 else "2500_and_above"
        by_band[band].append(row)
    return dict(schema_version=1, submission_id=manifest["submission_id"], as_of=as_of,
                manifest_sha256=sha256(manifest_path), identity_evidence=manifest["identity_evidence"],
                coverage_complete_declared=declared, coverage_evidence=manifest.get("coverage_evidence"),
                input_count=len(entries), unique_episode_seats=len(rows), duplicate_snapshots=duplicates,
                classifications=dict(Counter(r["classification"] for r in rows)),
                rejected_inputs=rejected, conflicts=conflicts, records=rows,
                available_completed=statistics(clean), missing_completion_times=missing_times,
                missing_opponent_ratings=sum(r["opponent_rating_before"] is None for r in clean),
                by_opponent_name={k:statistics(v) for k,v in sorted(by_opponent.items())},
                by_supplied_rating_band={k:statistics(v) for k,v in sorted(by_band.items())},
                latest_normal_completion_windows=windows,
                warnings=["Selected uploads are not a random or exhaustive hosted-history sample.",
                          "Latest windows count normal completions only; official forfeit outcomes are not inferred.",
                          "Runtime failures are separate, not silently counted as strategy losses or wins.",
                          "Episode IDs, replay UUIDs and upload timestamps do not establish completion order.",
                          "Rating bands are descriptive cutoffs, not a strength estimate or rating calibration."])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = analyze(args.manifest)
        input_paths = {args.manifest.resolve()}
        input_paths.update((args.manifest.parent / entry["replay"]).resolve()
                           for entry in load_json(args.manifest)["entries"]
                           if isinstance(entry, dict) and isinstance(entry.get("replay"), str))
        if args.output.resolve() in input_paths or (args.output.exists() and any(
                p.exists() and args.output.samefile(p) for p in input_paths)):
            raise ValueError("output must not overwrite an input file")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    except (OSError, ValueError, TypeError) as exc:
        print(f"hosted-recency: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"output":str(args.output), "completed":report["available_completed"]["n"],
                      "rejected":len(report["rejected_inputs"]), "conflicts":len(report["conflicts"])}))
    return 1 if report["rejected_inputs"] or report["conflicts"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
