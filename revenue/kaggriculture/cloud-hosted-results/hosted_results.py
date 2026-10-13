#!/usr/bin/env python3
"""Offline, coverage-aware results and log summaries for Kaggriculture replays.

No network, provider writes, agent imports, simulations, or policy changes.
Source files remain untouched. A selected replay sample is never a recent-N window.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import statistics
import sys
import tempfile
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

MAX_FILE = 96 * 1024 * 1024
MAX_ARCHIVE = 512 * 1024 * 1024
LOG_NAME = re.compile(r"^(\d+)-(\d+)(?:\(\d+\))?\.json$")
COVERAGE_KINDS = {"selected_development", "contiguous_completed_suffix", "complete_submission_history"}


class InputError(ValueError):
    """Malformed, conflicting or unsupported evidence."""


def finite_number(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


def parse_time(value: Any) -> datetime:
    if not isinstance(value, str):
        raise InputError("completed_at/as_of must be an explicit timezone-aware ISO timestamp")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise InputError("invalid ISO timestamp") from exc
    if result.tzinfo is None:
        raise InputError("naive timestamps are not accepted")
    return result.astimezone(timezone.utc)


def identity(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise InputError(f"{label} must be a nonnegative integer")
    return value


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * p
    lo, hi = math.floor(position), math.ceil(position)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (position - lo)


def describe(values: list[float]) -> dict[str, Any]:
    return {"n": len(values), "mean": statistics.mean(values) if values else None,
            "median": statistics.median(values) if values else None,
            "p99": percentile(values, .99), "max": max(values) if values else None}


def read_json(data: bytes, label: str) -> Any:
    if len(data) > MAX_FILE:
        raise InputError(f"JSON file too large: {label}")
    try:
        return json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InputError(f"invalid JSON: {label}") from exc


def read_sources(paths: list[Path]) -> tuple[list[tuple[str, bytes]], list[dict[str, Any]], dict[int, dict[str, Any]]]:
    """Read JSON or ZIP without extracting paths; verify any supplied source manifest."""
    documents: list[tuple[str, bytes]] = []
    sources: list[dict[str, Any]] = []
    bindings: dict[int, dict[str, Any]] = {}
    for path in paths:
        if not path.is_file():
            raise InputError(f"not a file: {path}")
        if path.stat().st_size > MAX_ARCHIVE:
            raise InputError(f"input too large: {path.name}")
        raw = path.read_bytes()
        source = {"name": path.name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
        if path.suffix.lower() != ".zip":
            documents.append((path.name, raw))
            sources.append(source)
            continue
        try:
            with zipfile.ZipFile(path) as archive:
                infos = archive.infolist()
                if sum(i.file_size for i in infos) > MAX_ARCHIVE:
                    raise InputError("archive expanded size exceeds limit")
                names = [i.filename for i in infos]
                if len(names) != len(set(names)):
                    raise InputError("duplicate ZIP member names")
                blobs: dict[str, bytes] = {}
                for info in infos:
                    name = PurePosixPath(info.filename)
                    if name.is_absolute() or ".." in name.parts or "\\" in info.filename:
                        raise InputError("unsafe ZIP member name")
                    if ((info.external_attr >> 16) & 0o170000) == 0o120000:
                        raise InputError("ZIP symlinks are not supported")
                    if info.is_dir():
                        continue
                    if info.file_size > MAX_FILE:
                        raise InputError("archive member exceeds file limit")
                    if info.filename.endswith(".json"):
                        blobs[info.filename] = archive.read(info)
                manifests = [name for name in blobs if PurePosixPath(name).name == "MANIFEST.json"]
                if len(manifests) > 1:
                    raise InputError("multiple bundle manifests are ambiguous")
                verified = []
                if manifests:
                    manifest = read_json(blobs[manifests[0]], manifests[0])
                    if not isinstance(manifest, dict) or not isinstance(manifest.get("files"), list):
                        raise InputError("unsupported bundle manifest")
                    listed: set[str] = set()
                    for item in manifest["files"]:
                        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
                            raise InputError("invalid manifest file entry")
                        matches = [name for name in blobs if name == item["name"] or name == "originals/" + item["name"]]
                        if len(matches) != 1 or matches[0] in listed:
                            raise InputError("missing or duplicated manifest member")
                        name = matches[0]
                        listed.add(name)
                        data = blobs[name]
                        if item.get("bytes") != len(data) or item.get("sha256") != hashlib.sha256(data).hexdigest():
                            raise InputError("manifest byte/hash mismatch: " + name)
                        verified.append(name)
                    unlisted = set(blobs) - set(manifests) - listed
                    if unlisted:
                        raise InputError("unmanifested JSON members: " + ", ".join(sorted(unlisted)))
                    submission = manifest.get("hosted_submission")
                    if submission is not None:
                        submission = identity(submission, "hosted_submission")
                        for name in listed:
                            # Binding comes from the owner's manifest, not from the replay itself.
                            match = re.fullmatch(r"(\d+)(?:\(\d+\))?\.json", PurePosixPath(name).name)
                            if match:
                                eid = int(match[1])
                                binding = {"submission_id": submission, "archive_sha256": manifest.get("archive"),
                                           "binding_source": "owner_bundle_manifest"}
                                if eid in bindings and bindings[eid] != binding:
                                    raise InputError("conflicting submission/archive bindings")
                                bindings[eid] = binding
                for name, data in blobs.items():
                    if name not in manifests:
                        documents.append((path.name + "::" + name, data))
                source["verified_manifest_members"] = sorted(verified)
        except zipfile.BadZipFile as exc:
            raise InputError("invalid ZIP: " + path.name) from exc
        sources.append(source)
    return documents, sources, bindings


def replay_record(data: Any, agent_name: str) -> dict[str, Any]:
    if not isinstance(data, dict) or not isinstance(data.get("info"), dict):
        raise InputError("expected a native replay object with info")
    info = data["info"]
    eid = identity(info.get("EpisodeId"), "EpisodeId")
    agents = info.get("Agents")
    if not isinstance(agents, list) or len(agents) != 2 or any(not isinstance(a, dict) for a in agents):
        raise InputError(f"episode {eid}: expected exactly two agent records")
    matches = [i for i, agent in enumerate(agents) if agent.get("Name") == agent_name]
    if len(matches) != 1:
        raise InputError(f"episode {eid}: own agent name must match exactly one seat")
    own = matches[0]
    statuses, rewards, steps = data.get("statuses"), data.get("rewards"), data.get("steps")
    if not isinstance(statuses, list) or len(statuses) != 2 or any(not isinstance(s, str) for s in statuses):
        raise InputError(f"episode {eid}: invalid statuses")
    if not isinstance(rewards, list) or len(rewards) != 2 or not isinstance(steps, list) or not steps:
        raise InputError(f"episode {eid}: invalid rewards or steps")
    configured = data.get("configuration", {}).get("episodeSteps")
    expected = configured if isinstance(configured, int) and not isinstance(configured, bool) else None
    issues = []
    if expected is None or expected < 1:
        issues.append("invalid_expected_horizon")
    elif len(steps) > expected or (statuses == ["DONE", "DONE"] and len(steps) != expected):
        issues.append("state_count_not_expected_horizon")
    for seat in (0, 1):
        final = steps[-1]
        if not isinstance(final, list) or len(final) != 2 or not isinstance(final[seat], dict):
            raise InputError(f"episode {eid}: malformed terminal state")
        if final[seat].get("status") != statuses[seat]:
            issues.append(f"seat_{seat}_terminal_status_mismatch")
    observed_statuses = Counter()
    for step in steps:
        if not isinstance(step, list) or len(step) != 2 or not isinstance(step[own], dict):
            raise InputError(f"episode {eid}: malformed state")
        observed_statuses[str(step[own].get("status", "MISSING"))] += 1
    own_reward, other_reward = rewards[own], rewards[1-own]
    scored = finite_number(own_reward) and finite_number(other_reward)
    complete = all(s in {"DONE", "ERROR", "INVALID", "TIMEOUT"} for s in statuses)
    clean_done = statuses == ["DONE", "DONE"] and not issues
    outcome = ("WIN" if own_reward > other_reward else "LOSS" if own_reward < other_reward else "TIE") if scored and complete else "UNKNOWN"
    final_money = steps[-1][own].get("observation", {}).get("farms", [])
    if len(final_money) == 2 and finite_number(own_reward):
        own_cash = final_money[own].get("money")
        if finite_number(own_cash) and not math.isclose(own_cash, own_reward, rel_tol=0, abs_tol=1e-9):
            issues.append("terminal_money_reward_mismatch")
            clean_done = False
    fault_statuses = {"ERROR", "INVALID", "TIMEOUT"}
    return {"episode_id": eid, "own_seat": own, "opponent_name": agents[1-own].get("Name"),
            "own_reward": own_reward if finite_number(own_reward) else None,
            "opponent_reward": other_reward if finite_number(other_reward) else None,
            "margin": own_reward-other_reward if scored else None, "outcome": outcome,
            "statuses": statuses, "terminal_observed": complete, "clean_done": clean_done,
            "own_runtime_fault_status_observed": any(s.upper() in fault_statuses for s in observed_statuses),
            "own_observed_status_counts": dict(observed_statuses), "recorded_states": len(steps), "horizon_complete": len(steps) == expected,
            "expected_states": expected, "action_rounds": max(0, len(steps)-1),
            "act_timeout_s": data.get("configuration", {}).get("actTimeout"),
            "integrity_issues": issues, "completed_at": None, "opponent_rating_pre": None}


def summarize_log(rows: Any, expected_rounds: int, limit_s: Any) -> dict[str, Any]:
    if not isinstance(rows, list):
        raise InputError("own log must be an array of per-round arrays")
    durations: list[float] = []
    nonempty_stdout = nonempty_stderr = invalid_duration = record_count = 0
    round_counts = []
    for round_rows in rows:
        if not isinstance(round_rows, list) or any(not isinstance(r, dict) for r in round_rows):
            raise InputError("malformed per-round log array")
        round_counts.append(len(round_rows))
        for row in round_rows:
            record_count += 1
            duration = row.get("duration")
            if finite_number(duration) and duration >= 0:
                durations.append(float(duration))
            else:
                invalid_duration += 1
            nonempty_stdout += bool(row.get("stdout"))
            nonempty_stderr += bool(row.get("stderr"))
    return {"present": True, "rounds": len(rows), "records": record_count,
            "exactly_one_record_each_round": bool(rows) and all(n == 1 for n in round_counts),
            "matches_replay_action_rounds": len(rows) == expected_rounds,
            "duration_s": describe(durations), "invalid_duration_records": invalid_duration,
            "duration_above_configured_timeout": sum(d > limit_s for d in durations) if finite_number(limit_s) else None,
            "nonempty_stdout_records": nonempty_stdout, "nonempty_stderr_records": nonempty_stderr,
            "duration_semantics": "provider_log_duration; not independently measured CPU or wall time"}


def summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(r["outcome"] for r in records)
    ratings = [r["opponent_rating_pre"] for r in records if finite_number(r.get("opponent_rating_pre"))]
    margins = [r["margin"] for r in records if finite_number(r.get("margin"))]
    n = len(records)
    resolved = sum(counts[k] for k in ("WIN", "LOSS", "TIE"))
    return {"episodes": n, "wins": counts["WIN"], "ties": counts["TIE"], "losses": counts["LOSS"],
            "unknown_outcomes": counts["UNKNOWN"], "resolved_outcomes": resolved,
            "wins_per_episode": counts["WIN"]/n if n else None,
            "resolved_outcome_win_rate": counts["WIN"]/resolved if resolved else None,
            "opponent_rating_pre": describe(ratings), "cash_margin": describe(margins),
            "runtime_fault_status_episodes": sum(r["own_runtime_fault_status_observed"] for r in records),
            "own_logs_present": sum(r.get("own_log", {}).get("present", False) for r in records)}


def apply_history(records: list[dict[str, Any]], metadata: Any, submission_id: int | None) -> dict[str, Any]:
    default = {"kind": "selected_development", "as_of": None, "source": None,
               "statement": "Available selected replays only; not a complete or recent hosted history."}
    if metadata is None:
        return default
    if not isinstance(metadata, dict) or metadata.get("kind") not in COVERAGE_KINDS:
        raise InputError("invalid history metadata kind")
    source = metadata.get("source")
    if not isinstance(source, str) or not source.strip():
        raise InputError("history metadata requires its exact source reference")
    mid = identity(metadata.get("submission_id"), "metadata submission_id")
    if submission_id is not None and mid != submission_id:
        raise InputError("history metadata submission mismatch")
    stamp = parse_time(metadata.get("as_of"))
    rows = metadata.get("episodes")
    if not isinstance(rows, list):
        raise InputError("history metadata requires episodes")
    by_id = {}
    for row in rows:
        if not isinstance(row, dict):
            raise InputError("invalid episode metadata")
        eid = identity(row.get("episode_id"), "metadata episode_id")
        if eid in by_id:
            raise InputError("duplicate metadata episode_id")
        by_id[eid] = row
    if set(by_id) != {r["episode_id"] for r in records}:
        raise InputError("metadata episode IDs must equal the deduplicated input replay IDs")
    for record in records:
        if record.get("submission_id") not in (None, mid):
            raise InputError("manifest/metadata submission mismatch")
        row = by_id[record["episode_id"]]
        if row.get("own_seat") != record["own_seat"]:
            raise InputError("history metadata must bind the actual own seat")
        if not isinstance(row.get("own_seat"), int) or isinstance(row.get("own_seat"), bool):
            raise InputError("history own_seat must be an integer")
        rating = row.get("opponent_rating_pre")
        if rating is not None and not finite_number(rating):
            raise InputError("opponent_rating_pre must be finite or null")
        completed_at = row.get("completed_at")
        if completed_at is not None:
            completed = parse_time(completed_at)
            if completed > stamp:
                raise InputError("episode completion is later than history as_of")
            record["completed_at"] = completed.isoformat()
        record["opponent_rating_pre"] = rating
        record["submission_id"] = mid
        record["history_metadata_source"] = source
    return {"kind": metadata["kind"], "as_of": stamp.isoformat(), "source": source,
            "statement": "Coverage is asserted by supplied history metadata, not inferred from replay IDs or file dates."}


def rolling(records: list[dict[str, Any]], coverage: dict[str, Any], n: int) -> dict[str, Any]:
    reason = None
    if coverage["kind"] == "selected_development":
        reason = "selected_replays_are_not_a_contiguous_recent_history"
    elif any(r["completed_at"] is None for r in records):
        reason = "missing_authoritative_completion_timestamps"
    elif any(not r["terminal_observed"] or r["integrity_issues"] for r in records):
        reason = "nonterminal_or_inconsistent_replay_records"
    elif len({r.get("submission_id") for r in records}) != 1 or records[0].get("submission_id") is None:
        reason = "missing_or_mixed_submission_identity"
    elif len(records) < n:
        reason = "insufficient_episodes"
    if reason:
        return {"requested": n, "available": len(records), "computed": False, "reason": reason}
    ordered = sorted(records, key=lambda r: (parse_time(r["completed_at"]), r["episode_id"]))
    # Do not break an ambiguous timestamp tie at the window boundary using an ID proxy.
    if len(ordered) > n and ordered[-n-1]["completed_at"] == ordered[-n]["completed_at"]:
        return {"requested": n, "available": len(records), "computed": False,
                "reason": "completion_timestamp_tie_crosses_window_boundary"}
    chosen = ordered[-n:]
    return {"requested": n, "computed": True, "episode_ids": [r["episode_id"] for r in chosen],
            "oldest_completed_at": chosen[0]["completed_at"], "newest_completed_at": chosen[-1]["completed_at"],
            "summary": summary(chosen)}


def analyze(paths: list[Path], agent_name: str, submission_id: int | None = None,
            history: Any = None) -> dict[str, Any]:
    documents, sources, bindings = read_sources(paths)
    records: dict[int, dict[str, Any]] = {}
    replay_hashes: dict[int, str] = {}
    logs: dict[tuple[int, int], tuple[str, Any, str]] = {}
    duplicate_replays = duplicate_logs = 0
    for label, raw in documents:
        data = read_json(raw, label)
        digest = hashlib.sha256(raw).hexdigest()
        if isinstance(data, list):
            match = LOG_NAME.fullmatch(PurePosixPath(label.split("::")[-1]).name)
            if not match:
                raise InputError("cannot bind log filename to episode and seat: " + label)
            key = (int(match[1]), int(match[2]))
            if key in logs:
                if logs[key][0] != digest:
                    raise InputError("conflicting logs for same episode/seat")
                duplicate_logs += 1
            else:
                logs[key] = (digest, data, label)
            continue
        record = replay_record(data, agent_name)
        eid = record["episode_id"]
        if eid in records:
            if replay_hashes[eid] != digest:
                raise InputError("conflicting replay bytes for same EpisodeId")
            duplicate_replays += 1
            continue
        record.update(bindings.get(eid, {}))
        record.update({"source": label, "sha256": digest})
        records[eid], replay_hashes[eid] = record, digest
    if not records:
        raise InputError("no replay records supplied")
    ordered = [records[eid] for eid in sorted(records)]
    for record in ordered:
        key = (record["episode_id"], record["own_seat"])
        if key in logs:
            digest, rows, label = logs[key]
            record["own_log"] = summarize_log(rows, record["action_rounds"], record["act_timeout_s"])
            record["own_log"].update({"source": label, "sha256": digest})
        else:
            record["own_log"] = {"present": False, "reason": "exact_episode_and_own_seat_log_not_supplied"}
    coverage = apply_history(ordered, history, submission_id)
    if submission_id is not None and any(r.get("submission_id") != submission_id for r in ordered):
        raise InputError("requested submission is not bound for every replay by manifest or supplied history")
    warnings = []
    if coverage["kind"] == "selected_development":
        warnings.append("Selected-development outcome totals are not a hosted win rate or a recent-20/50 trend.")
    if any(r["completed_at"] is None for r in ordered):
        warnings.append("Completion timestamps absent; EpisodeId and file upload time are not used as dates.")
    if any(r["opponent_rating_pre"] is None for r in ordered):
        warnings.append("Pre-game opponent ratings absent for some/all episodes; opposition-strength trend is unmeasured.")
    if any(not r["own_log"]["present"] for r in ordered):
        warnings.append("Own-log coverage is partial; missing logs are not counted as error-free calls.")
    return {"schema_version": 1, "agent_name": agent_name, "submission_id": submission_id,
            "coverage": coverage, "sources": sources, "duplicates": {"replays": duplicate_replays, "logs": duplicate_logs},
            "unmatched_log_keys": [list(k) for k in sorted(logs) if k not in {(r["episode_id"], r["own_seat"]) for r in ordered}],
            "sample_summary": summary(ordered), "recent_20": rolling(ordered, coverage, 20),
            "recent_50": rolling(ordered, coverage, 50), "warnings": warnings, "episodes": ordered,
            "actions_performed": {"new_simulations": 0, "provider_writes": 0, "runtime_changes": 0}}


def markdown(report: dict[str, Any]) -> str:
    s = report["sample_summary"]
    lines = ["# TITAN hosted-results handoff", "", "## Coverage", "",
             report["coverage"]["statement"], "",
             f"Available inputs: {s['episodes']} distinct episodes; {s['wins']} wins, {s['ties']} ties, {s['losses']} losses, {s['unknown_outcomes']} unresolved outcomes.", "",
             "**These are selected development inputs, not a recent hosted win-rate claim.**" if report["coverage"]["kind"] == "selected_development" else "History coverage source: " + report["coverage"]["source"], ""]
    for key in ("recent_20", "recent_50"):
        window = report[key]
        lines.append(f"{key}: " + (json.dumps(window["summary"], sort_keys=True) if window["computed"] else "not computed — " + window["reason"]) + ".")
    lines += ["", "## Per-episode readback", "", "| Episode | Own seat | Outcome | Own cash | Rival cash | Margin | Own log |", "|---|---:|---|---:|---:|---:|---|"]
    for r in report["episodes"]:
        log = r["own_log"]
        log_text = f"{log['rounds']} rounds; max {log['duration_s']['max']:.6f}s" if log["present"] and log["duration_s"]["max"] is not None else "Not supplied"
        lines.append(f"| {r['episode_id']} | {r['own_seat']} | {r['outcome']} | {r['own_reward']} | {r['opponent_reward']} | {r['margin']} | {log_text} |")
    lines += ["", "## Runtime observations", "",
              f"{s['runtime_fault_status_episodes']} episodes contain an own-agent ERROR, INVALID or TIMEOUT status. Own logs are supplied for {s['own_logs_present']}/{s['episodes']} episodes.",
              "Provider log durations are not independent CPU measurements. Empty stderr and DONE statuses do not prove every action was economically or semantically correct.", "", "## Remaining data requirements", ""]
    lines.extend("- " + warning for warning in report["warnings"])
    lines += ["", "Supply a source-referenced contiguous hosted history with exact episode IDs, own seats, completion timestamps, and pre-game opponent ratings to compute the requested recent windows and opposition trend.", "",
              "This offline analysis does not run games, modify the canonical policy, or perform provider or submission actions. Publication status is recorded separately by the publishing workflow.", ""]
    return "\n".join(lines)


def atomic_write(path: Path, text: str) -> None:
    """Write a private output without modifying a hard-linked original in place."""
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix="." + path.name + ".", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--agent-name", required=True)
    parser.add_argument("--submission-id", type=int)
    parser.add_argument("--history-metadata", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--markdown", type=Path)
    args = parser.parse_args()
    try:
        protected = {path.resolve() for path in args.inputs}
        if args.history_metadata:
            protected.add(args.history_metadata.resolve())
        destinations = [args.output] + ([args.markdown] if args.markdown else [])
        resolved = [path.resolve() for path in destinations]
        if len(set(resolved)) != len(resolved) or any(path in protected for path in resolved):
            raise InputError("outputs must be distinct from every input and from each other")
        if args.submission_id is not None:
            identity(args.submission_id, "submission_id")
        history = read_json(args.history_metadata.read_bytes(), str(args.history_metadata)) if args.history_metadata else None
        report = analyze(args.inputs, args.agent_name, args.submission_id, history)
        atomic_write(args.output, json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n")
        if args.markdown:
            atomic_write(args.markdown, markdown(report))
    except (InputError, OSError, TypeError, KeyError) as exc:
        print(f"input error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"episodes": report["sample_summary"]["episodes"], "recent_20_computed": report["recent_20"]["computed"],
                      "recent_50_computed": report["recent_50"]["computed"], "report": str(args.output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
