#!/usr/bin/env python3
"""Discriminate a simultaneous exchange from ordinary one-demand search."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def clear_output_cell(path):
    """Remove one deterministic output cell without following stale symlinks."""
    try:
        Path(path).unlink()
    except FileNotFoundError:
        return
    except IsADirectoryError as exc:
        raise RuntimeError(f"Output cell is a directory: {path}") from exc


def captured_bytes(value):
    """Return TimeoutExpired streams as exact bytes for durable evidence."""
    if value is None:
        return b""
    if isinstance(value, bytes):
        return value
    return str(value).encode("utf-8")


def captured_text(value):
    return captured_bytes(value).decode("utf-8", errors="replace")


def timeout_receipt(path, stage, timeout, stdout, stderr):
    stdout_bytes, stderr_bytes = captured_bytes(stdout), captured_bytes(stderr)
    record = {
        "status": "timeout",
        "stage": stage,
        "timeout_seconds": timeout,
        "stdout_sha256": hashlib.sha256(stdout_bytes).hexdigest(),
        "stderr_sha256": hashlib.sha256(stderr_bytes).hexdigest(),
        "stdout_bytes": len(stdout_bytes),
        "stderr_bytes": len(stderr_bytes),
    }
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--solver", type=Path, required=True)
    parser.add_argument("--checker", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    args.output.mkdir(parents=True, exist_ok=True)
    args.output = args.output.resolve()
    args.solver = args.solver.resolve()
    args.checker = args.checker.resolve()
    summary = args.output / "summary.json"
    clear_output_cell(summary)
    reports = []

    def execute(case, joint, suffix, *, resume=None, rounds=128):
        network = root / "joint-net.json"
        traffic = root / (case + "-tm.json")
        scenario = root / (case + "-scenario.json")
        output = args.output / (suffix + ".json")
        stats = args.output / (suffix + "-stats.json")
        log = args.output / (suffix + ".log")
        checker_report = args.output / (suffix + "-checker.json")
        checker_log = args.output / (suffix + "-checker.log")
        timeout_report = args.output / (suffix + "-timeout.json")
        resume_path = Path(resume).resolve() if resume else None
        temporary_resume = None
        if resume_path == output.resolve():
            descriptor, name = tempfile.mkstemp(
                prefix="." + suffix + ".resume-", suffix=".json", dir=args.output)
            os.close(descriptor)
            temporary_resume = Path(name)
            try:
                shutil.copyfile(resume_path, temporary_resume)
            except Exception:
                clear_output_cell(temporary_resume)
                raise
            resume_path = temporary_resume
        for path in (output, stats, log, checker_report, checker_log, timeout_report):
            clear_output_cell(path)
        environment = os.environ.copy()
        for name in ("CLOUD_INITIAL_SOLUTION", "FLEET_WAYPOINT_LIMIT"):
            environment.pop(name, None)
        environment.update(SEDGE_SECONDS="40", SEDGE_MAX_ROUNDS=str(rounds),
                           SEDGE_STATS=str(stats), FLEET_DIRECTED="1", FLEET_JOINT=str(joint))
        if resume_path:
            environment["CLOUD_INITIAL_SOLUTION"] = str(resume_path)
        command = [str(args.solver), str(network), str(traffic), str(scenario), str(output)]
        try:
            try:
                run = subprocess.run(command, env=environment, capture_output=True, text=True, timeout=60)
            except subprocess.TimeoutExpired as exc:
                stdout, stderr = captured_bytes(exc.stdout), captured_bytes(exc.stderr)
                log.write_bytes(stdout + stderr)
                timeout_receipt(timeout_report, "solver", exc.timeout, stdout, stderr)
                raise
        finally:
            if temporary_resume is not None:
                clear_output_cell(temporary_resume)
        log.write_text(run.stdout + run.stderr, encoding="utf-8")
        if run.returncode:
            raise RuntimeError(f"Solver failed ({run.returncode}): {run.stderr}")
        missing = [str(path) for path in (output, stats) if not path.is_file()]
        if missing:
            raise RuntimeError(
                "Solver exited 0 without creating current output cells: " + ", ".join(missing))
        command = [str(args.checker), "--net", str(network), "--tm", str(traffic),
                   "--scenario", str(scenario), "--srpaths", str(output), "--max-decimal-places", "6"]
        try:
            checked = subprocess.run(command, capture_output=True, text=True, timeout=30)
        except subprocess.TimeoutExpired as exc:
            stdout, stderr = captured_bytes(exc.stdout), captured_bytes(exc.stderr)
            checker_report.write_bytes(stdout)
            checker_log.write_bytes(stderr)
            timeout_receipt(timeout_report, "checker", exc.timeout, stdout, stderr)
            raise
        checker_report.write_text(checked.stdout, encoding="utf-8")
        checker_log.write_text(checked.stderr, encoding="utf-8")
        if checked.returncode:
            raise RuntimeError(f"Checker failed ({checked.returncode}): {checked.stderr}")
        result = json.loads(checked.stdout)
        assert result["valid"] is True, result
        vector = sorted((x["sat"] for x in result["saturations"]), reverse=True)
        measured = json.loads(stats.read_text(encoding="utf-8"))
        return output, vector, measured, result

    for case, first_rank in (("joint", 1), ("joint-budget", 3)):
        resume = root / "joint-budget-incumbent.json" if case == "joint-budget" else None
        old_path, old, negative, old_checked = execute(case, 0, case + "-disabled", resume=resume)
        new_path, new, positive, new_checked = execute(case, 1, case + "-enabled", resume=resume)
        assert negative["accepted"] == 0, "Negative control has an improving one-demand move"
        assert positive["joint_accepted"] > 0, "Exchange neighborhood was not exercised"
        assert new < old, "Exchange did not improve the official six-decimal objective"
        rank = next(i + 1 for i, pair in enumerate(zip(old, new)) if pair[0] != pair[1])
        assert rank == first_rank, (case, rank, old, new)
        if case == "joint":
            assert old[0] == 10 and new[0] == 9, (old, new)
        else:
            assert old[0] == new[0] == 10
            assert negative["budget_used"] == positive["budget_used"] == [0, 3]
            assert old_checked["total_cost"] == new_checked["total_cost"] == 3
        repeat_path, repeated, repeat_stats, _ = execute(case, 1, case + "-repeat", resume=resume)
        assert repeated == new and repeat_path.read_bytes() == new_path.read_bytes()
        assert repeat_stats["joint_accepted"] == positive["joint_accepted"]
        same_path = args.output / (case + " resume in place.json")
        shutil.copyfile(new_path, same_path)
        resumed_path, resumed, resumed_stats, _ = execute(
            case, 1, case + " resume in place", resume=same_path, rounds=0)
        assert resumed_path == same_path and resumed == new and resumed_stats["resumed"]
        reports.append({"case": case, "first_improved_rank": rank,
                        "before_mlu": old[0], "after_mlu": new[0],
                        "joint_accepted": positive["joint_accepted"],
                        "cost_before": old_checked["total_cost"], "cost_after": new_checked["total_cost"],
                        "negative_control": "pass", "same_path_resume": "pass",
                        "fixed_round_repeatability": "pass", "checker_valid": True,
                        "before_sha256": digest(old_path), "after_sha256": digest(new_path)})
    report = {"solver_sha256": digest(args.solver), "source_sha256": digest(root / "main.cpp"),
              "checker_sha256": digest(args.checker), "cases": reports,
              "fixture_sha256": {p.name: digest(p) for p in sorted(root.glob("joint*.json"))}}
    summary.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
