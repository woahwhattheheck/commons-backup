#!/usr/bin/env python3
"""Coalesce a busy main branch into one bounded verification range.

Scheduled batches inspect source and descriptive path inventory without eagerly
importing production entrypoints or starting a replacement test-suite runner.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shlex
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import main_velocity


DATA_PREFIXES = ("p/", "by/", "to/", "d/", "chunks/", "excerpts/", "projection/")
DATA_FILES = {"board.md", "posts.json", "recent.json", "pulse.json", "fresh.md", "export.txt"}
VERIFICATION_PREFIXES = ("p/", "conflicts/", "memory/", ".github/workflows/")
VERIFICATION_FILES = {
    "board.js", "carrier.js", "court.js", "session.js", "commons.css", "index.html",
    "hub_pages.py", "board_ingest.py", "memory_board.py", "capability_declaration.py",
    "commons_mcp.py", "action_executor.py", "action_land.py", "device_action_state.py",
}

VERIFIER_PROVENANCE = {
    "open-door": {
        "scope": "FROZEN_RANGE",
        "paths": ("open_door_guard.py", "test_open_door_guard.py"),
    },
    "muhlnickel": {
        "scope": "FROZEN_RANGE",
        "paths": ("muhlnickel_spec_guard.py", "test_muhlnickel_spec_guard.py"),
    },
    "source-parses": {
        "scope": "FROZEN_HEAD",
        "paths": ("source_parses.py",),
    },
    "path-manifest": {
        "scope": "FROZEN_HEAD",
        "paths": (
            "architecture/path-manifest.json",
            "architecture/path-manifest.schema.json",
            "host/path_manifest.py",
        ),
    },
}


def git(*args: str, check: bool = True) -> str:
    result = subprocess.run(["git", *args], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if check and result.returncode:
        raise RuntimeError("git %s: %s" % (" ".join(args), result.stderr.strip()))
    return result.stdout.strip()


def resolve_range(head: str, base: str | None, lookback_minutes: int) -> tuple[str, str, int]:
    frozen_head = git("rev-parse", f"{head}^{{commit}}")
    if base:
        frozen_base = git("rev-parse", f"{base}^{{commit}}")
    else:
        # Commit timestamps need not follow parent order. Do not mistake an
        # older-dated tip for an empty window, or replay its previous merge.
        commits = git(
            "rev-list", "--reverse", "--topo-order",
            f"--since-as-filter={lookback_minutes} minutes ago", frozen_head,
        ).splitlines()
        if not commits:
            return frozen_head, frozen_head, 0
        oldest = commits[0]
        parent = git("rev-parse", f"{oldest}^", check=False)
        frozen_base = parent or oldest
    count = int(git("rev-list", "--count", f"{frozen_base}..{frozen_head}") or "0")
    return frozen_base, frozen_head, count


def changed_paths(base: str, head: str) -> list[str]:
    return sorted(set(git("diff", "--name-only", base, head).splitlines()))


def verification_paths(paths: list[str]) -> list[str]:
    return [
        path
        for path in paths
        if path in VERIFICATION_FILES
        or path.startswith(VERIFICATION_PREFIXES)
        or path.startswith("test_")
    ]


def plan(paths: list[str], *, audit_unchanged: bool = False) -> list[tuple[str, list[str]]]:
    """Batch changed content once; an explicit base can also audit unchanged HEAD."""
    if not paths and not audit_unchanged:
        return []
    # Importing these modules would execute their top-level code, not merely
    # inspect source. The syntax pass below already catches unreadable source;
    # this scheduler must not invoke product entrypoints as an import sweep.
    commands = [
        ("open-door", [sys.executable, "open_door_guard.py", "--diff", "{base}", "{head}"]),
        ("muhlnickel", [sys.executable, "muhlnickel_spec_guard.py", "--base", "{base}", "--worktree"]),
    ]
    only_projection_data = bool(paths) and all(p in DATA_FILES or p.startswith(DATA_PREFIXES) for p in paths)
    source_changed = any(path.endswith((".py", ".js")) for path in paths)
    if source_changed:
        commands.append(("source-parses", [sys.executable, "source_parses.py"]))
    if not only_projection_data:
        # Run the descriptive inventory itself, not its historical unittest
        # wrapper. Unknown/unmapped paths stay observations, not admission gates.
        commands.append(("path-manifest", [sys.executable, "host/path_manifest.py"]))
    return commands


def verifier_candidate_paths(name: str, paths: list[str]) -> list[str]:
    """Return range paths capable of producing a verifier finding."""
    if name == "source-parses":
        return sorted(path for path in paths if path.endswith((".py", ".js")))
    return sorted(set(paths).intersection(VERIFIER_PROVENANCE[name]["paths"]))


def finding_provenance(
    name: str,
    exit_code: int,
    base: str,
    head: str,
    paths: list[str],
) -> dict:
    """Bind one verifier result to evidence from its frozen range.

    Diff-aware verifiers directly inspect ``base..head``. Snapshot verifiers run
    on the frozen head; they may be attached to the range only when one of their
    named inputs changed. A failing snapshot without that evidence remains an
    unattributed head finding instead of becoming a regression on an unrelated
    candidate.
    """
    config = VERIFIER_PROVENANCE[name]
    verifier_paths = list(config["paths"])
    candidate_paths = verifier_candidate_paths(name, paths)
    scope = config["scope"]
    if exit_code == 0:
        attribution = "PASS"
    elif scope == "FROZEN_RANGE" or candidate_paths:
        attribution = "DIRECT_RANGE"
    else:
        attribution = "NO_DIRECT_RANGE_PROVENANCE"
    return {
        "base": base,
        "head": head,
        "range": f"{base}..{head}",
        "scope": scope,
        "attribution": attribution,
        "verifier_paths": verifier_paths,
        "candidate_paths": candidate_paths,
    }


def run_batch(
    base: str, head: str, paths: list[str], *, audit_unchanged: bool = False,
) -> tuple[list[dict], bool]:
    results = []
    ok = True
    for name, template in plan(paths, audit_unchanged=audit_unchanged):
        command = [part.format(base=base, head=head) for part in template]
        proc = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        results.append({
            "name": name,
            "command": shlex.join(command),
            "exit_code": proc.returncode,
            "output_tail": proc.stdout[-4000:],
            "provenance": finding_provenance(name, proc.returncode, base, head, paths),
        })
        ok = ok and proc.returncode == 0
    return results, ok


def build_receipt(head: str, base: str | None, lookback_minutes: int, execute: bool) -> dict:
    frozen_base, frozen_head, commit_count = resolve_range(head, base, lookback_minutes)
    paths = changed_paths(frozen_base, frozen_head)
    # --base is an explicit audit request, including --base HEAD. Automatic
    # samples with no content changes keep their receipt without running checks.
    audit_unchanged = base is not None
    tasks = [name for name, _ in plan(paths, audit_unchanged=audit_unchanged)]
    results, ok = (
        run_batch(frozen_base, frozen_head, paths, audit_unchanged=audit_unchanged)
        if execute and tasks else ([], True)
    )
    verification = verification_paths(paths)
    findings = [result for result in results if result["exit_code"] != 0]
    return {
        "schema": "commons.main-range.v1",
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "base": frozen_base,
        "head": frozen_head,
        "commit_count": commit_count,
        "changed_path_count": len(paths),
        "verification_paths": verification,
        "observations": {
            "verification_path_touches": len(verification),
            "record_guard": "OBSERVED" if verification else "CLEAR",
            "finding_count": len(findings),
            "direct_range_findings": sum(
                result["provenance"]["attribution"] == "DIRECT_RANGE"
                for result in findings
            ),
            "unattributed_head_findings": sum(
                result["provenance"]["attribution"] == "NO_DIRECT_RANGE_PROVENANCE"
                for result in findings
            ),
        },
        "tasks": tasks,
        "results": results,
        "status": "PLANNED" if tasks and not execute else "PASS" if ok else "FINDINGS",
        "execution_state": "IDLE" if not tasks else "EXECUTED" if execute else "PLANNED",
        "main_movement_policy": "freeze_then_next_range",
        "velocity": main_velocity.measure(frozen_head),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--base")
    parser.add_argument("--lookback-minutes", type=int, default=30)
    parser.add_argument("--receipt")
    parser.add_argument("--plan", action="store_true", help="resolve and print without running verifiers")
    args = parser.parse_args(argv)
    receipt = build_receipt(args.head, args.base, args.lookback_minutes, not args.plan)
    text = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if args.receipt:
        with open(args.receipt, "w", encoding="utf-8") as fh:
            fh.write(text)
    print(text, end="")
    # Findings are reported in one receipt without amplifying notifications;
    # this descriptive batch does not mint a separate publication gate.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
