#!/usr/bin/env python3
"""Component implementation and operation."""

from __future__ import annotations

import argparse
import importlib.util
import io
import json
import subprocess
import sys
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "ground/MERGE_ON_PR.json"
SPRINT = ROOT / "host/sprint_integration.py"
SPRINT_POLICY = ROOT / "ground/SPRINT_INTEGRATION.json"
PR7915 = ROOT / "host/pr7915_closed_unmerged.py"
REFUSE = ("--send", "--apply", "--go", "--autopilot", "--reopen", "--merge", "--worktree")


def load_catalog(path: Path | None = None) -> dict[str, Any]:
    return json.loads((path or CATALOG).read_text(encoding="utf-8"))


def load_pr7915():
    spec = importlib.util.spec_from_file_location("pr7915_closed_unmerged", PR7915)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def leftover_sprint_self_test() -> dict[str, Any]:
    proc = subprocess.run(
        [sys.executable, str(SPRINT), "--self-test"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return {
        "rc": proc.returncode,
        "ok": proc.returncode == 0,
        "stdout": proc.stdout.strip(),
    }


def leftover_pr7915_fixture_match() -> dict[str, Any]:
    probe = load_pr7915()
    body = json.dumps(
        {
            "state": "closed",
            "merged": False,
            "merged_at": None,
            "closed_at": "2026-09-02T19:44:19Z",
            "title": "Point unique-pack at leftover Harborline map pin-lift",
            "number": 7915,
            "head": {
                "ref": "cursor/harborline-map-pin-lift-pointer-ae54",
                "sha": "fa046ce059009f0ddece9d91eaa5d60a1f281f39",
            },
        }
    ).encode("utf-8")
    return probe.classify(200, body)


def leftover_pr7915_reopen_refused() -> dict[str, Any]:
    probe = load_pr7915()
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = probe.main(["--reopen"])
    payload = json.loads(buf.getvalue())
    payload["rc"] = rc
    return payload


def refuse_payload(flag: str) -> dict[str, Any]:
    return {
        "kind": "MERGE_ON_PR",
        "id": "cursor-merge-on-pr-20260902-01",
        "gate": False,
        "refused": flag,
        "verdict": "FINDER-FAILED",
        "sent": 0,
        "cash": 0,
        "reopened": False,
        "merged_7915": False,
        "worktree_added": False,
        "note": (
            f"{flag} REFUSED. Merge-default leftover does not reopen #7915, "
            "does not merge #7915, and does not add a worktree."
        ),
    }


def measure() -> dict[str, Any]:
    catalog = load_catalog()
    policy = json.loads(SPRINT_POLICY.read_text(encoding="utf-8"))
    sprint = leftover_sprint_self_test()
    pr_match = leftover_pr7915_fixture_match()
    reopen = leftover_pr7915_reopen_refused()
    stacked = bool(catalog["stacked_worktrees"])
    merge_default = bool(catalog["merge_default"]) and policy.get("default") == "MERGE"
    pr_ok = (
        pr_match.get("state") == "MATCH"
        and pr_match.get("merged") is False
        and reopen.get("state") == "REFUSED"
        and reopen.get("reopened") is False
        and reopen.get("rc") == 2
    )
    ok = sprint["ok"] and pr_ok and merge_default and not stacked
    return {
        "kind": "MERGE_ON_PR",
        "id": catalog["id"],
        "item": 6,
        "gate": False,
        "login": False,
        "merge_default": merge_default,
        "stacked_worktrees": stacked,
        "busy_main_is_stop": catalog["busy_main_is_stop"],
        "stale_base_is_stop": catalog["stale_base_is_stop"],
        "unrelated_checks_is_stop": catalog["unrelated_checks_is_stop"],
        "parallel_branches_are_collisions": catalog["parallel_branches_are_collisions"],
        "ride_sprint_integration": True,
        "remint_sprint_integration": False,
        "sprint_self_test_ok": sprint["ok"],
        "sprint_default": policy.get("default"),
        "not_stopping": policy.get("not_stopping"),
        "pr7915_owner_said_merges": catalog["pr7915"]["owner_said_merges"],
        "pr7915_this_seat_reopen": False,
        "pr7915_this_seat_merge": False,
        "pr7915_leftover_state": pr_match.get("state"),
        "pr7915_merged": pr_match.get("merged"),
        "pr7915_closed_at": pr_match.get("closed_at"),
        "pr7915_reopen_refused": reopen.get("state") == "REFUSED",
        "do_not_steal": catalog["do_not_steal"],
        "invented_stripe_urls": False,
        "sends": 0,
        "cash_usd": 0,
        "checkout": "FINDER-FAILED",
        "verdict": "RENDER" if ok else "FINDER-FAILED",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--json", action="store_true")
    args, unknown = parser.parse_known_args(argv)
    for flag in unknown:
        if flag in REFUSE:
            print(json.dumps(refuse_payload(flag), sort_keys=True))
            return 2
        if flag.startswith("-"):
            print(
                json.dumps(
                    {
                        "kind": "MERGE_ON_PR",
                        "verdict": "FINDER-FAILED",
                        "sent": 0,
                        "unknown": flag,
                        "note": f"{flag} FINDER-FAILED, never silent 0.",
                    },
                    sort_keys=True,
                )
            )
            return 1
    packet = measure()
    print(json.dumps(packet, indent=2, sort_keys=True))
    return 0 if packet["verdict"] == "RENDER" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
