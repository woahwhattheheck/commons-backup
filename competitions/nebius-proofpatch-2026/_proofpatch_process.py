"""Run the retained ratio repair and verifier replay in fresh child processes.

This is the fixed local demonstration for Commons #16339, operation
proofpatch-real-process-kiln73-20260919. It is not a general execution sandbox.
"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile

import _proofpatch_core as core


EXECUTOR_ID = "proofpatch-fixed-ratio-process-v1"
REPORT_SCHEMA = "proofpatch.real-process/v1"

# The operator demonstration is product source, copied beside the retained calc
# generation. It emits observations directly; no unittest runner is involved.
RATIO_DEMO = '''import json
import runpy
import sys

ratio = runpy.run_path("calc.py")["ratio"]
phase = sys.argv[1]
operands = [(5, 2, 2.5)]
if phase == "regression":
    operands += [(0, 2, 0.0), (-5, 2, -2.5), (6, 2, 3.0), (2, 5, 0.4)]
observations = []
for numerator, denominator, expected in operands:
    actual = ratio(numerator, denominator)
    observations.append({"numerator": numerator, "denominator": denominator,
                         "actual": repr(actual), "expected": repr(expected),
                         "matches": actual == expected})
ok = all(row["matches"] for row in observations)
print(json.dumps({"phase": phase, "observations": observations, "ok": ok},
                 sort_keys=True, separators=(",", ":")))
sys.exit(0 if ok else 1)
'''


def _parts():
    baseline_files = {"calc.py": core.BASE_CALC, "ratio_demo.py": RATIO_DEMO}
    patched_files = {**baseline_files, "calc.py": core.PATCHED_CALC}
    task = core.validate_task({
        "schema": core.TASK_SCHEMA,
        "task_id": "real-process-ratio-floor-division",
        "issue_ref": "commons:16339",
        "allowed_paths": ["calc.py"],
        "reproduction": {"argv": ["python", "-B", "ratio_demo.py", "reproduction"], "timeout_s": 10},
        "regression": {"argv": ["python", "-B", "ratio_demo.py", "regression"], "timeout_s": 10},
    })
    return task, baseline_files, patched_files


def _read_root(root):
    """Account for every root entry, including hidden and non-regular entries."""
    files = {}
    with os.scandir(root) as entries:
        for entry in sorted(entries, key=lambda item: item.name):
            if not stat.S_ISREG(entry.stat(follow_symlinks=False).st_mode):
                raise core.ProofError("unexpected non-regular demonstration entry: " + entry.name)
            files[entry.name] = Path(entry.path).read_bytes().decode("utf-8")
    return files


def _same_root(root, expected):
    actual = _read_root(root)
    if actual != expected:
        raise core.ProofError("demonstration root changed outside the captured ratio repair")
    return actual


class FixedRatioProcessExecutor:
    """Materialize known source for every run; never consult an outcome map."""

    def __init__(self):
        self.task, self.baseline_files, self.patched_files = _parts()
        self.baseline = core.snapshot_from_files(self.baseline_files)
        self.patched = core.snapshot_from_files(self.patched_files)
        self.runs = []
        self.patch_applications = 0
        self.observed_files = {}

    def run(self, command, repo_digest):
        command = core.validate_command(core.freeze_plain_json(command))
        known_command = command == self.task["reproduction"] or command == self.task["regression"]
        if not known_command:
            raise core.ProofError("command does not describe this fixed ratio demonstration")
        if repo_digest == self.baseline["digest"]:
            expected = self.baseline_files
            generation = "baseline"
        elif repo_digest == self.patched["digest"]:
            expected = self.patched_files
            generation = "patched"
        else:
            raise core.ProofError("repository digest does not describe the retained ratio source")

        with tempfile.TemporaryDirectory(prefix="proofpatch-ratio-") as directory:
            root = Path(directory)
            for name, content in self.baseline_files.items():
                with (root / name).open("xb") as handle:
                    handle.write(content.encode("utf-8"))
            self.observed_files["baseline"] = _same_root(root, self.baseline_files)
            if generation == "patched":
                (root / "calc.py").write_bytes(core.PATCHED_CALC.encode("utf-8"))
                self.patch_applications += 1
            before_files = _same_root(root, expected)
            self.observed_files[generation] = before_files
            before = core.snapshot_from_files(before_files)

            # Resolve the logical python command to this running interpreter.
            # No shell, inherited environment, input stream, or extra open FDs.
            argv = [sys.executable, *command["argv"][1:]]
            raw_stdout, raw_stderr = b"", b""
            timed_out, launch_error, returncode = False, None, None
            try:
                process = subprocess.Popen(
                    argv, cwd=root, env={}, stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, close_fds=True,
                )
                try:
                    raw_stdout, raw_stderr = process.communicate(timeout=command["timeout_s"])
                except subprocess.TimeoutExpired:
                    timed_out = True
                    process.kill()
                    raw_stdout, raw_stderr = process.communicate()
                returncode = process.returncode
            except OSError as exc:
                launch_error = str(exc)

            run = {
                "sequence": len(self.runs), "generation": generation,
                "command": command, "actual_argv": argv, "returncode": returncode,
                "timed_out": timed_out, "launch_error": launch_error,
                "stdout_base64": base64.b64encode(raw_stdout).decode("ascii"),
                "stderr_base64": base64.b64encode(raw_stderr).decode("ascii"),
                "repo_before": before, "repo_after": None, "result": None,
            }
            self.runs.append(run)
            stdout = raw_stdout.decode("utf-8")
            stderr = raw_stderr.decode("utf-8")
            # Preserve the native returncode separately; bundle result codes
            # use the existing portable 0..255 schema, including signal exits.
            code = 127 if returncode is None else returncode
            if code < 0:
                code = 128 - code
            result = core.validate_result({
                "exit_code": min(code, 255), "stdout": stdout, "stderr": stderr,
                "timed_out": timed_out,
            })
            run["result"] = result
            after_files = _read_root(root)
            run["repo_after"] = core.snapshot_from_files(after_files)
            if after_files != before_files:
                raise core.ProofError("child process changed the demonstration root")
            if launch_error:
                raise core.ProofError("child process launch failed: " + launch_error)
            if timed_out:
                raise core.ProofError("child process timed out")
            if generation == "baseline":
                diagnostic = {
                    "phase": "reproduction", "ok": False,
                    "observations": [{"numerator": 5, "denominator": 2,
                                      "actual": "2", "expected": "2.5", "matches": False}],
                }
                if returncode != 1 or stderr or json.loads(stdout) != diagnostic:
                    raise core.ProofError("baseline did not reproduce the retained ratio defect")
            elif returncode != 0:
                raise core.ProofError("patched ratio execution failed")
            return result


def _report(executor, bundle, verification, error):
    return {
        "schema": REPORT_SCHEMA,
        "operation": "proofpatch-real-process-kiln73-20260919",
        "execution_kind": "LOCAL_FIXED_RATIO_PROCESSES",
        "ok": error is None, "error": error,
        "process_count": len(executor.runs),
        "patch_applications": executor.patch_applications,
        "file_snapshots": executor.observed_files,
        "process_runs": executor.runs,
        "bundle": bundle, "verification": verification,
    }


def run_rehearsal():
    """Execute four phases, then replay all four in new processes and roots."""
    executor = FixedRatioProcessExecutor()
    bundle = None
    try:
        task, baseline, patched = executor.task, executor.baseline, executor.patched
        patch = core.make_patch(baseline, patched, [
            {"path": "calc.py", "before": core.BASE_CALC, "after": core.PATCHED_CALC},
        ])
        phases = [
            ("REPRODUCTION", task["reproduction"], baseline),
            ("FOCUSED_TEST", task["reproduction"], patched),
            ("REGRESSION_TEST", task["regression"], patched),
            ("REPLAY_TEST", task["reproduction"], patched),
        ]
        receipts, previous = [], "0" * 64
        for sequence, (phase, command, snapshot) in enumerate(phases):
            result = executor.run(command, snapshot["digest"])
            receipt = core.make_receipt(
                sequence, phase, core.task_digest(task), command, result,
                snapshot["digest"], snapshot["digest"], previous,
            )
            receipts.append(receipt)
            previous = receipt["entry_digest"]
        bundle = core.build_bundle(task, baseline, patched, patch, receipts)
        verification = core.verify_with_executor(bundle, executor, EXECUTOR_ID)
        return _report(executor, bundle, verification, None)
    except (OSError, UnicodeError, json.JSONDecodeError, core.ProofError) as exc:
        return _report(executor, bundle, None, str(exc))


def verify_rehearsal(value):
    """Replay a saved bundle using only the local, fixed ratio executor."""
    executor = FixedRatioProcessExecutor()
    bundle = value
    try:
        if type(value) is dict and value.get("schema") == REPORT_SCHEMA:
            bundle = value.get("bundle")
        verification = core.verify_with_executor(bundle, executor, EXECUTOR_ID)
        return _report(executor, bundle, verification, None)
    except (OSError, UnicodeError, json.JSONDecodeError, core.ProofError) as exc:
        return _report(executor, bundle, None, str(exc))
