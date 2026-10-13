#!/usr/bin/env python3
"""Execute exactly four sequential cold portfolio arms on A04 and A14.

The workflow is manually dispatched. This script never builds or downloads.
The frozen comparator supplies exact native-scientific six-decimal ranking.
"""
import argparse
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import shutil
import signal
import subprocess
import sys
import time

try:
    import resource
except ImportError:
    resource = None

FROZEN = "6feb9c0566b8f203c5d1a2ffdfbf1cb6d11be055"
PINS = {
    "sources/candidate/main.cpp": "758977095f8f34263bbcd9ed043ac4ab7943f04f65fae530c78ee64787c34f8f",
    "supervisor.py": "182371658e82f9037716e90ea8cd115622d089d02512916c7a7bf3b39fca1c63",
    "compare_checker.py": "a402a0166b1e52c95dd181e15b8a124504ac78ddea7e815944c754569b323cb8",
}
ORDER = (("setA-04", ("baseline", "new")), ("setA-14", ("new", "baseline")))


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_record(path):
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": sha(path)}


def write_json(path, value):
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, default=str) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def utc():
    return datetime.now(timezone.utc).isoformat()


def read_optional(path):
    try:
        return Path(path).read_text().strip()
    except OSError:
        return None


def limits():
    return {"platform": platform.platform(), "python": sys.version,
            "logical_cpus": os.cpu_count(),
            "affinity": sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else None,
            "cpu_max": read_optional("/sys/fs/cgroup/cpu.max"),
            "memory_max": read_optional("/sys/fs/cgroup/memory.max"),
            "cpu_stat": read_optional("/sys/fs/cgroup/cpu.stat"),
            "memory_events": read_optional("/sys/fs/cgroup/memory.events"),
            "cgroup_memory_peak": read_optional("/sys/fs/cgroup/memory.peak"),
            "host_meminfo": read_optional("/proc/meminfo"),
            "scope": "observed shared runner cgroup; not dedicated per-arm CPU or RAM"}


def tree_sample(namespace_pid):
    """Resolve our direct child's host PID, then include descendants across sessions."""
    own = dict(line.split(":", 1) for line in Path("/proc/self/status").read_text().splitlines())
    parent = int(own["Pid"])
    processes = {}
    for path in Path("/proc").iterdir():
        if not path.name.isdecimal():
            continue
        try:
            fields = dict(line.split(":", 1) for line in (path / "status").read_text().splitlines())
            processes[int(fields["Pid"])] = (int(fields["PPid"]),
                int(fields.get("NSpid", fields["Pid"]).split()[-1]),
                int(fields.get("VmRSS", "0").split()[0]))
        except (OSError, ValueError, KeyError):
            continue
    roots = [pid for pid, row in processes.items() if row[0] == parent and row[1] == namespace_pid]
    if len(roots) != 1:
        return {"rss_kib": None, "pids": [], "root_resolved": False}
    pending, seen = list(roots), set()
    while pending:
        pid = pending.pop()
        if pid in seen:
            continue
        seen.add(pid)
        pending.extend(child for child, row in processes.items() if row[0] == pid)
    tokens = {}
    for pid in seen:
        try:
            tokens[pid] = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19]
        except (OSError, IndexError):
            pass
    return {"rss_kib": sum(processes[pid][2] for pid in seen),
            "pids": sorted(seen), "tokens": tokens, "root_resolved": True}


def still_alive(pid, start_token):
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        return fields[19] == start_token and fields[0] not in ("Z", "X")
    except (OSError, IndexError):
        return False


def run_process(command, folder, label, env, guard_seconds):
    record = {"command": command, "started_utc": utc(), "limits_before": limits(),
              "guard": {"term_after_seconds": guard_seconds, "kill_after_term_seconds": 10},
              "sample_period_seconds": 0.5, "sampled_peak_tree_rss_kib": None,
              "rss_scope": "reachable process tree VmRSS; sampled, excludes page cache, not a hard bound",
              "samples": 0, "unresolved_root_samples": 0}
    guarded = ["timeout", "--signal=TERM", "--kill-after=10s", str(guard_seconds) + "s", *command]
    record["guarded_command"] = guarded
    before = resource.getrusage(resource.RUSAGE_CHILDREN) if resource else None
    started = time.monotonic()
    process, observed = None, {}
    with (folder / (label + ".stdout")).open("xb") as stdout, (folder / (label + ".stderr")).open("xb") as stderr:
        try:
            process = subprocess.Popen(guarded, env=env, stdout=stdout, stderr=stderr,
                                       stdin=subprocess.DEVNULL, start_new_session=True)
            while process.poll() is None:
                sample = tree_sample(process.pid)
                observed.update(sample.get("tokens", {}))
                record["samples"] += 1
                if sample["root_resolved"]:
                    record["sampled_peak_tree_rss_kib"] = max(record["sampled_peak_tree_rss_kib"] or 0, sample["rss_kib"])
                else:
                    record["unresolved_root_samples"] += 1
                time.sleep(0.5)
            record["returncode"] = process.wait()
        except BaseException as error:
            record["exception"] = {"type": type(error).__name__, "message": str(error)}
            if process is not None and process.poll() is None:
                process.kill()
                process.wait()
            raise
        finally:
            # A wrapper's exit is not proof that its separately grouped solvers
            # exited. Retained start tokens prevent signaling a reused PID.
            leftovers = [pid for pid, token in observed.items() if still_alive(pid, token)]
            record["unexpected_descendants_after_exit"] = leftovers
            for pid in leftovers:
                try:
                    if still_alive(pid, observed[pid]):
                        os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            cleanup_deadline = time.monotonic() + 1
            remaining = list(leftovers)
            while remaining and time.monotonic() < cleanup_deadline:
                time.sleep(0.05)
                remaining = [pid for pid in remaining if still_alive(pid, observed[pid])]
            record["descendants_remaining_after_cleanup"] = remaining
            record.update(finished_utc=utc(), wall_seconds=time.monotonic() - started,
                          limits_after=limits())
            if before is not None:
                after = resource.getrusage(resource.RUSAGE_CHILDREN)
                record["waited_child_cpu_seconds"] = {"user": after.ru_utime - before.ru_utime,
                                                       "system": after.ru_stime - before.ru_stime}
            for stream_name in ("stdout", "stderr"):
                path = folder / (label + "." + stream_name)
                record[stream_name] = file_record(path)
            write_json(folder / (label + ".process.json"), record)
            if remaining:
                raise RuntimeError("Prior invocation still has live descendants; refusing the next arm")
    return record


def arm_environment(context, folder, candidate, new):
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(("FLEET_", "SEDGE_", "CLOUD_", "PORTFOLIO_"))}
    controls = {"PORTFOLIO_SECONDS": "585", "PORTFOLIO_CANDIDATE": str(candidate),
                "PORTFOLIO_SEDGE": str(context / "bin/sedge"),
                "PORTFOLIO_FLORA": str(context / "bin/flora"),
                "PORTFOLIO_CHECKER": str(context / "bin/checker"),
                "PORTFOLIO_ARTIFACTS": str(folder / "artifacts"),
                "PORTFOLIO_RECEIPT": str(folder / "portfolio.json"),
                "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1",
                "MKL_NUM_THREADS": "1", "NUMEXPR_NUM_THREADS": "1",
                "PYTHONDONTWRITEBYTECODE": "1"}
    if new:
        controls["FLEET_POLISH_AFTER_EXHAUSTION"] = "1"
    env.update(controls)
    return env, controls


def checker_report(path, comparator, precision):
    if precision == 6:
        return comparator.load_result(path)
    raw = json.loads(path.read_bytes(), parse_float=Decimal)
    if not isinstance(raw, dict) or type(raw.get("valid")) is not bool:
        raise ValueError("Expected checker validity boolean")
    record = {"valid": raw["valid"], "sha256": sha(path), "total_cost": raw.get("total_cost")}
    if not raw["valid"]:
        return record
    rows = raw.get("saturations")
    if not isinstance(rows, list) or not rows:
        raise ValueError("Empty checker vector")
    keys, vector = set(), []
    for row in rows:
        value = Decimal(row["sat"])
        if not value.is_finite() or value < 0:
            raise ValueError("Invalid checker saturation")
        key = (row["t"], str(row["from"]), str(row["to"]))
        if key in keys:
            raise ValueError("Duplicate checker coordinate")
        keys.add(key)
        vector.append(value)
    record.update(keys=keys, vector=sorted(vector, reverse=True))
    return record


def event_readout(folder):
    events, malformed = [], []
    for path in sorted((folder / "artifacts").rglob("*.log")):
        for number, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
            if line.startswith("FLEET_POLISH "):
                try:
                    events.append({"log": str(path.relative_to(folder)), "line": number,
                                   "event": json.loads(line[len("FLEET_POLISH "):])})
                except json.JSONDecodeError:
                    malformed.append({"log": str(path.relative_to(folder)), "line": number, "text": line})
    return {"events": events, "malformed_events": malformed,
            "inference": "missing phase events do not establish phase execution or fallback"}


def run_arm(args, comparator, case, name):
    folder = args.output / case / name
    folder.mkdir(parents=True)  # Exclusive: no reuse of output or diagnostics.
    (folder / "artifacts").mkdir()
    inputs = [args.official_root / "setA" / (case + suffix + ".json") for suffix in ("-net", "-tm", "-scenario")]
    candidate = args.new_candidate if name == "new" else args.context / "bin/candidate"
    env, controls = arm_environment(args.context, folder, candidate, name == "new")
    output = folder / "solution.json"
    row = {"case": case, "arm": name, "controls": controls, "cold_start": True,
           "input_files": [file_record(path) for path in inputs], "candidate_binary": file_record(candidate)}
    row["process"] = run_process([sys.executable, "-B", str(args.context / "supervisor.py"),
                                  *map(str, inputs), str(output)], folder, "portfolio", env, 590)
    receipt = folder / "portfolio.json"
    if receipt.is_file():
        try:
            row["portfolio_receipt"] = json.loads(receipt.read_bytes())
        except (ValueError, OSError) as error:
            row["receipt_error"] = str(error)
    row["phase_readout"] = event_readout(folder)
    reports = {}
    row["checks"] = {}
    if output.is_file():
        row["solution"] = file_record(output)
        for precision in (6, 12):
            label = "checker-" + str(precision)
            command = [str(args.context / "bin/checker"), "--net", str(inputs[0]), "--tm", str(inputs[1]),
                       "--scenario", str(inputs[2]), "--srpaths", str(output), "--max-decimal-places", str(precision)]
            process = run_process(command, folder, label, env, 110)
            item = {"process": process}
            try:
                reports[precision] = checker_report(folder / (label + ".stdout"), comparator, precision)
                report = reports[precision]
                item.update(valid=report["valid"], load_count=len(report.get("vector", [])),
                            total_cost_diagnostic=report.get("total_cost"))
            except (ValueError, TypeError, KeyError, ArithmeticError, OSError) as error:
                item.update(valid=None, parse_error=str(error))
            row["checks"][str(precision)] = item
    valid = all(p in reports and reports[p]["valid"] and row["checks"][str(p)]["process"]["returncode"] == 0 for p in (6, 12))
    row["precisions_agree_on_keys_and_cost"] = bool(valid and reports[6]["keys"] == reports[12]["keys"] and reports[6].get("total_cost") == reports[12].get("total_cost"))
    saved = row.get("portfolio_receipt", {})
    row["receipt_matches_solution"] = bool(output.is_file() and saved.get("validated") is True and saved.get("solution_sha256") == row["solution"]["sha256"])
    row["complete"] = bool(row["process"]["returncode"] == 0 and not row["process"]["unexpected_descendants_after_exit"] and saved.get("status") == "complete" and row["precisions_agree_on_keys_and_cost"] and row["receipt_matches_solution"])
    row["selected_lane"] = saved.get("selected_lane")
    row["zero_change_baseline_selected"] = saved.get("selected_lane") == "zero_change_baseline"
    write_json(folder / "result.json", row)
    return row, reports.get(6)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("context", "official-root", "new-candidate", "new-source", "integration-receipt", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--expected-new-sha256", required=True)
    parser.add_argument("--operation-id", required=True)
    parser.add_argument("--integration-ref", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{7,79}", args.operation_id):
        parser.error("operation-id must be 8-80 filename-safe ASCII characters")
    if not re.fullmatch(r"[0-9a-f]{40}", args.integration_ref):
        parser.error("integration-ref must be an immutable 40-character commit SHA")
    if sys.platform != "linux" or shutil.which("timeout") is None:
        parser.error("Requires native Linux and GNU timeout")
    for name in ("context", "official_root", "new_candidate", "new_source", "integration_receipt"):
        setattr(args, name, getattr(args, name).resolve(strict=True))
    args.output = args.output.resolve()
    if args.output.exists():
        parser.error("Output must be fresh; existing trials are never rerun or replaced")
    for relative, expected in PINS.items():
        if sha(args.context / relative) != expected:
            parser.error("Frozen context identity mismatch: " + relative)
    if sha(args.new_source) != args.expected_new_sha256 or args.expected_new_sha256 == PINS["sources/candidate/main.cpp"]:
        parser.error("Integrated source identity mismatch or unchanged source")
    for case, _ in ORDER:
        for suffix in ("-net", "-tm", "-scenario"):
            (args.official_root / "setA" / (case + suffix + ".json")).resolve(strict=True)
    args.output.mkdir(parents=True)
    spec = importlib.util.spec_from_file_location("frozen_compare", args.context / "compare_checker.py")
    comparator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(comparator)
    source_files = [file_record(path) for path in sorted(args.context.rglob("*")) if path.is_file()]
    summary = {"schema": "roadef.after-exhaustion.cold-pairs.v1", "started_utc": utc(),
               "operation_id": args.operation_id, "integration_ref": args.integration_ref,
               "github_run": {key: os.environ.get(key) for key in
                              ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "GITHUB_SHA", "GITHUB_REF", "GITHUB_WORKFLOW_REF")},
               "frozen_commit": FROZEN, "comparison": "complete descending official Decimal vector; no rounding or cost tiebreak",
               "order": ORDER, "limits": limits(), "context_files": source_files,
               "new_source": file_record(args.new_source), "new_binary": file_record(args.new_candidate),
               "integration_receipt": json.loads(args.integration_receipt.read_bytes()),
               "integration_receipt_file": file_record(args.integration_receipt),
               "harness": file_record(Path(__file__).resolve()), "arms": [], "pairs": [], "status": "running"}
    write_json(args.output / "summary.json", summary)
    for case, order in ORDER:
        case_rows, reports = {}, {}
        for name in order:
            row, report = run_arm(args, comparator, case, name)
            case_rows[name], reports[name] = row, report
            summary["arms"].append(row)
            write_json(args.output / "summary.json", summary)
        pair = {"case": case, "order": order, "both_arms_complete": all(row["complete"] for row in case_rows.values())}
        if all(reports.values()):
            try:
                pair["saved_output_comparison_new_vs_baseline"] = comparator.compare(reports["new"], reports["baseline"])
            except (ValueError, KeyError, TypeError) as error:
                pair["comparison_error"] = str(error)
        else:
            pair["comparison_error"] = "Missing readable official six-decimal report; no winner inferred"
        summary["pairs"].append(pair)
        write_json(args.output / "summary.json", summary)
    summary.update(finished_utc=utc(), status="complete" if all(row["complete"] for row in summary["arms"]) else "incomplete")
    write_json(args.output / "summary.json", summary)
    print(json.dumps({key: summary[key] for key in ("status", "pairs")}, indent=2))
    return 0 if summary["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
