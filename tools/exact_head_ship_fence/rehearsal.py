"""Exercise the existing CLI on fictional snapshots; never collect provider data."""
from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

from .demo import snapshot

PACKAGE = Path(__file__).resolve().parent
ROOT = PACKAGE.parents[1]
SOURCE_FILES = (
    "__init__.py", "__main__.py", "_core.src", "fence.py",
    "cli.py", "demo.py", "rehearsal.py",
)


@dataclass(frozen=True)
class Case:
    name: str
    explanation: str
    packet: dict[str, Any]
    verdict: str | None
    action: str | None


def catalog() -> list[Case]:
    """Fixed teaching cases, all derived from the original fresh synthetic demo."""
    base = snapshot()
    cases: list[Case] = []

    def add(name: str, explanation: str, verdict: str | None, action: str | None,
            packet: dict[str, Any]) -> None:
        cases.append(Case(name, explanation, packet, verdict, action))

    ready = "READY_TO_MERGE_EVIDENCE"
    recensus = "MERGE_AFTER_LIVE_RECENSUS"
    add("01-ready", "All declared requirements agree in this fictional packet; no provider was contacted.", ready, recensus, deepcopy(base))
    for name, status, conclusion, explanation in (
        ("02-queued", "QUEUED", "NONE", "A required job has not finished. This is unknown, not a failed test or a pass."),
        ("04-cancelled", "COMPLETED", "CANCELLED", "Cancellation supplies no successful execution result."),
        ("05-failed", "COMPLETED", "FAILURE", "The retained required job failed; the next action is repair, not merely waiting."),
        ("06-skipped", "COMPLETED", "SKIPPED", "The packet policy does not permit a skipped required check."),
    ):
        packet = deepcopy(base)
        packet["checks"][0].update(status=status, conclusion=conclusion)
        failed = conclusion == "FAILURE"
        add(name, explanation, "HOLD_CI_RED" if failed else "HOLD_CI_UNKNOWN", "REPAIR_CI" if failed else "WAIT_FOR_CI", packet)
    packet = deepcopy(base); packet["checks"] = []
    add("03-missing", "A required check is absent; omission cannot stand in for success.", "HOLD_CI_UNKNOWN", "WAIT_FOR_CI", packet)
    packet = deepcopy(base)
    packet["checks"][0]["conclusion"] = "SKIPPED"
    packet["check_policy"][0]["allow_skipped"] = True
    add("07-explicit-skip-policy", "Only the supplied policy permits this skip. The tool does not authenticate who approved that policy.", ready, recensus, packet)
    packet = deepcopy(base); packet["reviews"][0]["head_sha"] = "9" * 40
    add("08-old-review", "A PASS names an older head and does not satisfy the current-head review requirement.", "HOLD_REVIEW_STALE", "REREVIEW_EXACT_HEAD", packet)
    packet = deepcopy(base)
    packet["review_policy"] = {"required": False, "min_passes": 0}
    packet["reviews"][0]["verdict"] = "STOP"
    add("09-optional-policy-stop", "Making positive reviews optional does not erase a STOP on the current head.", "HOLD_REVIEW_STALE", "REREVIEW_EXACT_HEAD", packet)
    packet = deepcopy(base)
    packet["topology"].update(candidate_paths_known=False, candidate_paths=[])
    add("10-unknown-paths", "Unknown changed paths are not an explicitly empty changed-path set.", "HOLD_TOPOLOGY_UNKNOWN", "REFRESH_TOPOLOGY", packet)
    packet = deepcopy(base)
    packet["current_pr_head"] = "9" * 40
    packet["checks"][0]["head_sha"] = packet["reviews"][0]["head_sha"] = "9" * 40
    add("11-head-moved", "The current head differs from the head the operator expected, despite checks naming the new head.", "HOLD_HEAD_MOVED", "REFRESH_EVIDENCE", packet)
    moved = deepcopy(base)
    moved["current_base_head"] = "4" * 40
    moved["topology"]["base_delta_paths"] = [{"path": "docs/unrelated.md", "blob_sha": None}]
    add("12-main-moved", "Disjoint path lists alone do not show that the current base was rejoined.", "HOLD_BASE_MOVED", "REJOIN_CURRENT_MAIN", deepcopy(moved))
    moved["topology"].update(evaluated_base_sha="4" * 40, rejoin_proven=True, rejoin_head_sha=moved["current_pr_head"])
    add("13-disjoint-rejoin", "The supplied packet now binds the disjoint rejoin to this exact head/base. This is still only retained evidence.", ready, recensus, deepcopy(moved))
    moved["topology"]["base_delta_paths"] = deepcopy(moved["topology"]["candidate_paths"])
    add("14-overlap-rejoin", "V1 refuses to infer a semantic conflict resolution from overlapping paths, even with a claimed rejoin.", "HOLD_BASE_MOVED", "REJOIN_CURRENT_MAIN", moved)
    packet = deepcopy(base); packet["snapshot_complete"] = False
    add("15-incomplete", "A declared partial census cannot become complete because its visible checks happen to pass.", "HOLD_INCOMPLETE_EVIDENCE", "REFRESH_EVIDENCE", packet)
    packet = deepcopy(base)
    packet.update(check_policy=[], checks=[], review_policy={"required": False, "min_passes": 0}, reviews=[])
    add("16-empty-policy", "Zero required checks can satisfy an empty supplied policy. READY is not proof that any test or independent review occurred.", ready, recensus, packet)
    packet = deepcopy(base)
    packet["check_policy"][0]["required"] = False
    packet["checks"][0]["conclusion"] = "FAILURE"
    add("17-optional-failure", "A failed optional check remains in the input but does not block this policy. Inspect the policy, not only the verdict.", ready, recensus, packet)
    packet = deepcopy(base); packet["checks"][0]["head_sha"] = "9" * 40
    add("18-other-head-check", "A check from another head is invalid input, not a successful observation for this head.", None, None, packet)
    packet = deepcopy(base); packet["checks"][0].update(status="QUEUED", conclusion="SUCCESS")
    add("19-impossible-check", "QUEUED plus SUCCESS is an impossible state/conclusion pair and produces no report bundle.", None, None, packet)
    packet = deepcopy(base)
    old = (datetime.now(timezone.utc) - timedelta(hours=2)).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
    packet["observed_at"] = packet["checks"][0]["observed_at"] = packet["reviews"][0]["observed_at"] = old
    add("20-stale-observation", "A two-hour-old fictional observation exceeds the one-hour lifetime. Do not refresh timestamps on real evidence to make it pass.", None, None, packet)
    return sorted(cases, key=lambda case: case.name)


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def source_inventory() -> dict[str, dict[str, Any]]:
    result = {}
    for name in SOURCE_FILES:
        data = (PACKAGE / name).read_bytes()
        result[name] = {"sha256": digest(data), "bytes": len(data)}
    return result


def write_new(path: Path, data: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(data)


def native_command(command: str, source: Path, output: Path) -> dict[str, Any]:
    flags = ["-" + "O" * sys.flags.optimize] if sys.flags.optimize else []
    argv = [sys.executable, *flags, "-m", "tools.exact_head_ship_fence", command, str(source), str(output)]
    completed = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, timeout=30, check=False)
    return {"argv": argv, "returncode": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr}


def render_readout(rows: list[dict[str, Any]], observed_at: str, optimize: int) -> str:
    lines = [
        "# Exact-head ship fence: worked operator rehearsal", "",
        "**Every repository, commit, job and review in this rehearsal is fictional.**",
        "The existing CLI was executed; GitHub was not contacted. These results do not authorize a merge.", "",
        f"Observation anchor: `{observed_at}`. Python optimization level: `{optimize}`.", "",
        "A compile exit of 0 means a report was written, including HOLD reports. A verify exit of 0 means",
        "the report agrees with its captured input and is current under the supplied policy. Neither means permission to merge.", "",
        "| Case | Actual verdict | Next action | Required checks | Compile / verify exit |",
        "|---|---|---|---:|---|",
    ]
    for row in rows:
        report = row["report"]
        if report is None:
            lines.append(f"| {row['name']} | INPUT_REJECTED | Correct or recollect input | — | {row['compile']['returncode']} / not run |")
        else:
            lines.append(f"| {row['name']} | {report['verdict']} | {report['next_action']} | {report['summary']['required_check_count']} | {row['compile']['returncode']} / {row['verify']['returncode']} |")
    lines.extend(["", "## Read the distinctions, not just the color", ""])
    for row in rows:
        lines.extend([f"### {row['name']}", row["explanation"], ""])
        if row["report"] is not None:
            lines.extend(["Actual reason codes: " + ", ".join(f"`{item}`" for item in row["report"]["reason_codes"]), ""])
        else:
            lines.extend(["Actual diagnostic:", "```text", row["compile"]["stderr"].strip(), "```", ""])
    lines.extend([
        "## Reuse", "",
        "Run `python -m tools.exact_head_ship_fence.rehearsal NEW_DIRECTORY` to generate a fresh fictional run;",
        "use `python -O -m tools.exact_head_ship_fence.rehearsal ANOTHER_NEW_DIRECTORY` for optimized execution.",
        "Do not reuse an output directory. Failures retain partial work but do not create COMPLETE.json.",
        "Saved inputs expire under their one-hour policy; later verification may correctly reject them.", "",
        "RUN.json retains the actual input, JSON/Markdown output and subprocess records for every case.",
        "COMPLETE.json binds that capture, this readout and the individual case files by SHA-256.",
        "Its source inventory records file bytes observed before/after execution, not a provider or sandbox attestation.", "",
        "The original compiler, CLI and review history remain credited to #15731's contributors;",
        "ZZ-KESTREL-D4M8 adds the input-order correction, regression completion and this operator rehearsal.", "",
    ])
    return "\n".join(lines)


def run(output: Path) -> dict[str, Any]:
    output = output.absolute()
    before = source_inventory()
    output.mkdir(mode=0o700)
    rows: list[dict[str, Any]] = []
    retained: list[Path] = []
    cases = catalog()
    for case in cases:
        directory = output / case.name
        directory.mkdir(mode=0o700)
        source, bundle = directory / "snapshot.json", directory / "bundle"
        original = json_bytes(case.packet)
        write_new(source, original)
        retained.append(source)
        compiled = native_command("compile", source, bundle)
        row: dict[str, Any] = {"name": case.name, "explanation": case.explanation, "snapshot": case.packet,
                               "snapshot_file_sha256": digest(original), "compile": compiled, "verify": None,
                               "report": None, "markdown": None}
        expected_code = 0 if case.verdict is not None else 2
        if compiled["returncode"] != expected_code:
            raise RuntimeError(f"{case.name}: unexpected compile outcome {compiled['returncode']}: {compiled['stderr']}")
        if case.verdict is None:
            if bundle.exists() or "Traceback" in compiled["stderr"]:
                raise RuntimeError(f"{case.name}: invalid input did not fail cleanly")
        else:
            report_path, markdown_path = bundle / "report.json", bundle / "report.md"
            report = json.loads(report_path.read_bytes())
            if (report["verdict"], report["next_action"]) != (case.verdict, case.action):
                raise RuntimeError(f"{case.name}: actual verdict differs from the teaching case")
            if not report["authority"] or any(value is not False for value in report["authority"].values()):
                raise RuntimeError(f"{case.name}: authority ceiling mismatch")
            verified = native_command("verify", source, bundle)
            if verified["returncode"] != 0 or verified["stdout"].strip() != "VERIFIED":
                raise RuntimeError(f"{case.name}: native verification failed: {verified['stderr']}")
            row.update(report=report, markdown=markdown_path.read_text(encoding="utf-8"), verify=verified)
            retained.extend((report_path, markdown_path))
        if source.read_bytes() != original:
            raise RuntimeError(f"{case.name}: source input changed")
        rows.append(row)
    if source_inventory() != before:
        raise RuntimeError("source files changed during rehearsal")
    capture = {"schema_version": 1, "synthetic": True, "provider_calls": 0, "python": sys.version,
               "optimization": sys.flags.optimize, "source_file_inventory": before, "case_count": len(rows), "cases": rows}
    capture_path, readout_path = output / "RUN.json", output / "REHEARSAL.md"
    write_new(capture_path, json_bytes(capture))
    write_new(readout_path, render_readout(rows, cases[0].packet["observed_at"], sys.flags.optimize).encode("utf-8"))
    retained.extend((capture_path, readout_path))
    manifest = {path.relative_to(output).as_posix(): digest(path.read_bytes()) for path in retained}
    complete = {"schema_version": 1, "synthetic": True, "complete": True, "case_count": len(rows),
                "source_file_inventory": before, "files": manifest}
    write_new(output / "COMPLETE.json", json_bytes(complete))
    return complete


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="new output directory; its parent must exist")
    args = parser.parse_args(argv)
    try:
        complete = run(args.output)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"SYNTHETIC REHEARSAL COMPLETE: {complete['case_count']} cases; no provider calls")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
