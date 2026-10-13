#!/usr/bin/env python3
"""Compare repeated CHI-Bench run packets with reliability-aware metrics.

Consumes exactly three prepared packet directories per group and uses only the
public packet contract: trials/*/*/result.json, verifier/reward.json, and
(optionally) agent/trajectory.jsonl.zst.
"""
from __future__ import annotations

import argparse
import itertools
import json
import shutil
import statistics
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class Trial:
    task: str
    reward: int
    cost_usd: float | None
    wall_s: float | None
    tool_calls: int | None


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read JSON {path}: {exc}") from exc


def reward_from(trial_dir: Path, result: dict[str, Any]) -> int:
    reward_path = trial_dir / "verifier" / "reward.json"
    if reward_path.exists():
        reward_doc = read_json(reward_path)
        value = reward_doc.get("reward") if isinstance(reward_doc, dict) else None
        if value in (0, 0.0, 1, 1.0):
            return int(value)
    verifier = result.get("verifier_result") or {}
    rewards = verifier.get("rewards") or {}
    value = rewards.get("reward")
    if value in (0, 0.0, 1, 1.0):
        return int(value)
    raise ValueError(f"missing binary reward in {trial_dir}")


def aggregate_agent_result(result: dict[str, Any], key: str) -> float | None:
    contexts: list[dict[str, Any]] = []
    if isinstance(result.get("agent_result"), dict):
        contexts.append(result["agent_result"])
    for step in result.get("step_results") or []:
        if isinstance(step, dict) and isinstance(step.get("agent_result"), dict):
            contexts.append(step["agent_result"])
    values = [ctx.get(key) for ctx in contexts if isinstance(ctx.get(key), (int, float))]
    return float(sum(values)) if values else None


def wall_seconds(result: dict[str, Any]) -> float | None:
    timing = result.get("agent_execution") or {}
    start, end = timing.get("started_at"), timing.get("finished_at")
    if not (isinstance(start, str) and isinstance(end, str)):
        return None
    try:
        a = datetime.fromisoformat(start.replace("Z", "+00:00"))
        b = datetime.fromisoformat(end.replace("Z", "+00:00"))
    except ValueError:
        return None
    return max(0.0, (b - a).total_seconds())


def iter_trajectory_lines(path: Path) -> Iterable[str]:
    try:
        import zstandard as zstd  # type: ignore
    except ImportError:
        zstd = None
    if zstd is not None:
        with path.open("rb") as raw:
            with zstd.ZstdDecompressor().stream_reader(raw) as reader:
                pending = b""
                while True:
                    chunk = reader.read(1024 * 1024)
                    if not chunk:
                        break
                    pending += chunk
                    *lines, pending = pending.split(b"\n")
                    for line in lines:
                        if line.strip():
                            yield line.decode("utf-8")
                if pending.strip():
                    yield pending.decode("utf-8")
        return
    zstdcat = shutil.which("zstdcat") or shutil.which("zstd")
    if not zstdcat:
        return
    cmd = [zstdcat, str(path)] if Path(zstdcat).name == "zstdcat" else [zstdcat, "-dc", str(path)]
    proc = subprocess.run(cmd, check=False, text=True, capture_output=True)
    if proc.returncode != 0:
        return
    yield from (line for line in proc.stdout.splitlines() if line.strip())


def count_tool_calls(path: Path) -> int | None:
    if not path.exists():
        return None
    total = 0
    seen = False
    for line in iter_trajectory_lines(path):
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        seen = True
        if isinstance(obj, dict):
            calls = obj.get("tool_calls")
            if isinstance(calls, list):
                total += len(calls)
            message = obj.get("message")
            if isinstance(message, dict) and isinstance(message.get("tool_calls"), list):
                total += len(message["tool_calls"])
    return total if seen else None


def task_id(result: dict[str, Any], domain: str, trial_dir: Path) -> str:
    for key in ("task_name", "task_id", "task"):
        value = result.get(key)
        if isinstance(value, str) and value:
            return value
    return f"{domain}/{trial_dir.name}"


def load_packet(packet: Path) -> dict[str, Trial]:
    trials_root = packet / "trials"
    if not trials_root.is_dir():
        raise ValueError(f"packet has no trials/ directory: {packet}")
    out: dict[str, Trial] = {}
    for result_path in sorted(trials_root.glob("*/*/result.json")):
        trial_dir = result_path.parent
        domain = trial_dir.parent.name
        result = read_json(result_path)
        if not isinstance(result, dict):
            raise ValueError(f"result is not an object: {result_path}")
        key = task_id(result, domain, trial_dir)
        if key in out:
            raise ValueError(f"duplicate task identity {key!r} in {packet}")
        out[key] = Trial(
            task=key,
            reward=reward_from(trial_dir, result),
            cost_usd=aggregate_agent_result(result, "cost_usd"),
            wall_s=wall_seconds(result),
            tool_calls=count_tool_calls(trial_dir / "agent" / "trajectory.jsonl.zst"),
        )
    if not out:
        raise ValueError(f"no trial result.json files found under {trials_root}")
    return out


def mean_known(values: Iterable[float | int | None]) -> float | None:
    known = [float(v) for v in values if v is not None]
    return statistics.fmean(known) if known else None


def summarize_group(packets: list[Path]) -> tuple[dict[str, Any], dict[str, list[Trial]]]:
    if len(packets) != 3:
        raise ValueError("each group must contain exactly three packet directories")
    attempts = [load_packet(p) for p in packets]
    task_sets = [set(a) for a in attempts]
    if task_sets[1:] != task_sets[:-1]:
        common = set.intersection(*task_sets)
        union = set.union(*task_sets)
        missing = sorted(union - common)
        raise ValueError(f"attempt packets do not contain identical tasks; mismatched: {missing[:12]}")
    tasks = sorted(task_sets[0])
    by_task = {task: [attempt[task] for attempt in attempts] for task in tasks}
    rewards = [trial.reward for rows in by_task.values() for trial in rows]
    pass3_tasks = [task for task, rows in by_task.items() if all(r.reward == 1 for r in rows)]
    mixed_tasks = [task for task, rows in by_task.items() if 0 < sum(r.reward for r in rows) < 3]
    never_tasks = [task for task, rows in by_task.items() if sum(r.reward for r in rows) == 0]
    metrics = {
        "n_tasks": len(tasks),
        "n_trials": len(rewards),
        "empirical_pass_at_1": sum(rewards) / len(rewards),
        "pass_3": len(pass3_tasks) / len(tasks),
        "mixed_task_rate": len(mixed_tasks) / len(tasks),
        "never_pass_rate": len(never_tasks) / len(tasks),
        "mean_cost_usd": mean_known(t.cost_usd for rows in by_task.values() for t in rows),
        "mean_wall_s": mean_known(t.wall_s for rows in by_task.values() for t in rows),
        "mean_tool_calls": mean_known(t.tool_calls for rows in by_task.values() for t in rows),
        "pass_3_tasks": pass3_tasks,
        "mixed_tasks": mixed_tasks,
        "never_pass_tasks": never_tasks,
    }
    return metrics, by_task


def compare(base: dict[str, list[Trial]], cand: dict[str, list[Trial]]) -> dict[str, Any]:
    if set(base) != set(cand):
        raise ValueError("baseline and candidate groups do not cover identical tasks")
    improved, regressed, unchanged = [], [], []
    for task in sorted(base):
        b = tuple(t.reward for t in base[task])
        c = tuple(t.reward for t in cand[task])
        b_all, c_all = all(b), all(c)
        if c_all and not b_all:
            improved.append(task)
        elif b_all and not c_all:
            regressed.append(task)
        else:
            unchanged.append(task)
    return {
        "pass3_improved_tasks": improved,
        "pass3_regressed_tasks": regressed,
        "pass3_unchanged_tasks": unchanged,
    }


def parse_group(text: str) -> tuple[str, list[Path]]:
    if "=" not in text:
        raise argparse.ArgumentTypeError("group must be NAME=packet1,packet2,packet3")
    name, raw = text.split("=", 1)
    paths = [Path(p).expanduser().resolve() for p in raw.split(",") if p]
    if not name or len(paths) != 3:
        raise argparse.ArgumentTypeError("group must be NAME=packet1,packet2,packet3")
    return name, paths


def self_test() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        groups: dict[str, list[Path]] = {"base": [], "cand": []}
        matrices = {
            "base": [[1, 1, 0], [1, 0, 0], [1, 1, 1]],
            "cand": [[1, 1, 1], [1, 1, 0], [1, 1, 1]],
        }
        for group, rows in matrices.items():
            for attempt in range(3):
                packet = root / f"{group}-{attempt}"
                groups[group].append(packet)
                for idx, task in enumerate(("a", "b", "c")):
                    trial = packet / "trials" / "pa" / task
                    (trial / "verifier").mkdir(parents=True)
                    (trial / "verifier" / "reward.json").write_text(json.dumps({"reward": rows[idx][attempt]}))
                    (trial / "result.json").write_text(json.dumps({"task_name": task, "agent_result": {"cost_usd": 1 + attempt}}))
        bm, bt = summarize_group(groups["base"])
        cm, ct = summarize_group(groups["cand"])
        delta = compare(bt, ct)
        assert round(bm["empirical_pass_at_1"], 6) == round(6 / 9, 6)
        assert bm["pass_3"] == 1 / 3
        assert cm["pass_3"] == 2 / 3
        assert delta["pass3_improved_tasks"] == ["a"]
        assert delta["pass3_regressed_tasks"] == []
    print("self-test: PASS")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--group", action="append", type=parse_group, default=[], help="NAME=packet1,packet2,packet3; repeat for A/B")
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        self_test()
        return 0
    if not args.group:
        parser.error("at least one --group is required")

    report: dict[str, Any] = {"groups": {}, "comparisons": []}
    detail: dict[str, dict[str, list[Trial]]] = {}
    for name, paths in args.group:
        if name in report["groups"]:
            parser.error(f"duplicate group name: {name}")
        metrics, tasks = summarize_group(paths)
        report["groups"][name] = {"packets": [str(p) for p in paths], **metrics}
        detail[name] = tasks

    names = list(detail)
    for base_name, cand_name in itertools.combinations(names, 2):
        base_metrics = report["groups"][base_name]
        cand_metrics = report["groups"][cand_name]
        task_delta = compare(detail[base_name], detail[cand_name])
        report["comparisons"].append({
            "baseline": base_name,
            "candidate": cand_name,
            "delta": {
                "empirical_pass_at_1": cand_metrics["empirical_pass_at_1"] - base_metrics["empirical_pass_at_1"],
                "pass_3": cand_metrics["pass_3"] - base_metrics["pass_3"],
                "mean_cost_usd": (cand_metrics["mean_cost_usd"] - base_metrics["mean_cost_usd"]) if cand_metrics["mean_cost_usd"] is not None and base_metrics["mean_cost_usd"] is not None else None,
                "mean_wall_s": (cand_metrics["mean_wall_s"] - base_metrics["mean_wall_s"]) if cand_metrics["mean_wall_s"] is not None and base_metrics["mean_wall_s"] is not None else None,
                "mean_tool_calls": (cand_metrics["mean_tool_calls"] - base_metrics["mean_tool_calls"]) if cand_metrics["mean_tool_calls"] is not None and base_metrics["mean_tool_calls"] is not None else None,
            },
            **task_delta,
        })

    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.json_out:
        args.json_out.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
