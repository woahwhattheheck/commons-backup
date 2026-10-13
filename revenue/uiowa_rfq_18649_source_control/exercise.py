#!/usr/bin/env python3
"""Exercise two fictional workflows in new, disposable Git repositories."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from assess import collect, write_report


class Workflow:
    def __init__(self, path: Path):
        self.path = path
        path.mkdir()
        self.commands = []
        self.tick = 0
        self.env = {**{k: v for k, v in os.environ.items() if not k.startswith("GIT_")},
                    "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
                    "GIT_AUTHOR_NAME": "Fictional Workflow Operator",
                    "GIT_AUTHOR_EMAIL": "workflow@example.invalid",
                    "GIT_COMMITTER_NAME": "Fictional Workflow Operator",
                    "GIT_COMMITTER_EMAIL": "workflow@example.invalid",
                    "GIT_TERMINAL_PROMPT": "0"}
        self.run("init", "--initial-branch=main")
        self.run("config", "core.hooksPath", str(path / "unused-hooks"))
        self.run("config", "commit.gpgsign", "false")
        self.run("config", "tag.gpgsign", "false")

    def run(self, *args: str, expected: int = 0) -> str:
        self.tick += 1
        # A declared fictional timeline, not measured elapsed development time.
        stamp = f"2026-01-01T12:{self.tick // 60:02d}:{self.tick % 60:02d}+00:00"
        env = {**self.env, "GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp}
        proc = subprocess.run(["git", "-C", str(self.path), *args], env=env,
                              capture_output=True, text=True, timeout=30)
        self.commands.append({"argv": ["git", *args], "exit_code": proc.returncode,
                              "stdout": proc.stdout, "stderr": proc.stderr})
        if proc.returncode != expected:
            raise ValueError(f"{self.path.name}: git {' '.join(args)} exited {proc.returncode}: {proc.stderr}")
        return proc.stdout.strip()

    def commit(self, text: str, message: str) -> str:
        (self.path / "service.txt").write_text(text, encoding="utf-8")
        self.run("add", "service.txt")
        self.run("commit", "-m", message)
        return self.run("rev-parse", "HEAD")

    def export(self, target: Path, evidence: dict) -> None:
        report = collect(self.path)
        report["fictional_workflow"] = True
        report["timestamp_basis"] = "scripted fictional timeline; not elapsed engineering time"
        report["demonstration"] = evidence
        write_report(report, target)
        (target / "commands.json").write_text(json.dumps(self.commands, indent=2) + "\n", encoding="utf-8")


def exercise(out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=False)
    short = Workflow(out / "short-lived-repo")
    short.commit("mode=baseline\n", "SC-101 establish baseline")
    short.run("switch", "-c", "change/response")
    short.commit("mode=responsive\n", "SC-102 improve response")
    short.run("switch", "main")
    short.commit("mode=compatible\n", "SC-103 retain compatibility")
    short.run("merge", "--no-ff", "change/response", "-m", "SC-104 integrate response", expected=1)
    unresolved = short.run("diff", "--name-only", "--diff-filter=U")
    if unresolved != "service.txt":
        raise ValueError("demonstration did not produce the expected service conflict")
    resolved = short.commit("mode=responsive-compatible\n", "SC-104 resolve behavior with both requirements")
    parent_count = len(short.run("rev-list", "--parents", "-n", "1", resolved).split()) - 1
    if parent_count != 2:
        raise ValueError("resolved integration does not retain both parent histories")
    bad = short.commit("mode=broken\n", "SC-105 recorded unsuccessful change")
    short.run("revert", "--no-edit", bad)
    recovered = (short.path / "service.txt").read_text(encoding="utf-8") == "mode=responsive-compatible\n"
    if not recovered:
        raise ValueError("revert did not recover the prior service content")
    short.export(out / "short-lived", {"branch_pattern": "short-lived change branch",
        "conflict_observed": True, "conflict_path": unresolved, "resolution_commit": resolved,
        "revert_target": bad, "recovered_content": recovered,
        "unresolved_gap": "Independent offsite restore and administrative continuity were not exercised."})

    release = Workflow(out / "release-repo")
    release.commit("mode=baseline\n", "SC-201 establish baseline")
    release.run("switch", "-c", "release/1")
    release.commit("mode=stable\n", "SC-202 stabilize release")
    release.run("switch", "main")
    (release.path / "roadmap.txt").write_text("Next release remains on main.\n", encoding="utf-8")
    release.run("add", "roadmap.txt")
    release.run("commit", "-m", "SC-203 continue next release")
    release.run("switch", "release/1")
    fix = release.commit("mode=stable-fixed\n", "SC-204 repair release behavior")
    release.run("tag", "release-1.0")
    release.run("switch", "main")
    release.run("merge", "--no-ff", "release/1", "-m", "SC-205 reintegrate released fix")
    integration = release.run("rev-parse", "HEAD")
    # Recover an earlier release into a new directory, never rewrite any ref.
    archive = out / "release-service.txt"
    archive.write_text(release.run("show", "release-1.0:service.txt") + "\n", encoding="utf-8")
    recovered = archive.read_text(encoding="utf-8") == "mode=stable-fixed\n"
    if not recovered:
        raise ValueError("tag content did not match the release fix")
    release.export(out / "release-branch", {"branch_pattern": "release branch plus continuing main",
        "conflict_observed": False, "released_fix_commit": fix, "reintegrated_at": integration,
        "recovery_ref": "release-1.0", "recovered_content": recovered,
        "unresolved_gap": "Independent offsite restore and administrative continuity were not exercised."})
    return {"output": str(out), "workflows_exercised": 2,
            "conflict_resolution": "observed", "local_content_recovery": "observed in both workflows",
            "offsite_restore": "UNKNOWN", "university_findings": False}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path, help="new disposable working directory")
    args = parser.parse_args(argv)
    try:
        print(json.dumps(exercise(args.out.resolve())))
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"source-control exercise: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
