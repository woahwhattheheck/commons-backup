#!/usr/bin/env python3
"""host/lda_android_ci.py — is LDA Android CI on current-main Actions?

Slack 1787635487.642039 (DEMON rolling utilization / stranded map):
LocalDeviceAgent has substantive Android source, but
lda/workflows/android.yml sits outside .github/workflows, so GitHub
Actions never ran it. Talk about Android CI without this leftover is
CLAIMED. A blind copy of the LDA file is NOT_LANDED on Commons: it
would fire on every board post and delete repo-wide artifacts.

This leftover measures the smallest current-main placement:
.github/workflows/lda-android.yml with working-directory lda, a path
filter, assembleDebug, and no global artifact wipe. A workflow file
is not a run URL. titan: NOT_WRITTEN. No auth.

  python3 host/lda_android_ci.py
  python3 host/lda_android_ci.py --root .
  python3 host/lda_android_ci.py --self-test
"""
from __future__ import annotations

import argparse
import json
import os
import sys


WORKFLOW = ".github/workflows/lda-android.yml"
STRANDED = "lda/workflows/android.yml"


def parse_workflow(text):
    """Pure parser so tests do not need the live tree or an Android SDK."""
    body = str(text or "")
    lower = body.lower()
    return {
        "measured": True,
        "has_lda_workdir": "working-directory: lda" in body,
        "has_assemble": "assembledebug" in lower,
        "has_jdk": "setup-java" in lower or "java-version" in lower or "jdk 17" in lower,
        "has_path_filter": "lda/" in body and "paths:" in body,
        "has_workflow_dispatch": "workflow_dispatch" in body,
        "wipes_repo_artifacts": (
            "listartifactsforrepo" in lower
            or "deleteartifact" in lower
            or "gha-remove-artifacts" in lower
        ),
        "titan": "NOT_WRITTEN",
    }


def classify(row):
    """Turn a measured workflow into a land-desk state."""
    row = row or {}
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "note": "lda-android workflow body not read. Absence was not stillness.",
        }
    if row.get("wipes_repo_artifacts"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "workflow would wipe repo-wide artifacts. The LDA-root copy is "
                "not Commons CI. Place a path-filtered lda-android leftover."
            ),
        }
    if (
        row.get("has_lda_workdir")
        and row.get("has_assemble")
        and row.get("has_jdk")
        and row.get("has_path_filter")
        and row.get("has_workflow_dispatch")
    ):
        return {
            "state": "INTEGRATED",
            "note": (
                "lda-android is a current-main Actions workflow: working-directory "
                "lda, path-filtered, assembleDebug, workflow_dispatch. A workflow "
                "file is not a run URL. Talk is not a land."
            ),
        }
    missing = [
        name
        for name, ok in (
            ("working-directory lda", row.get("has_lda_workdir")),
            ("assembleDebug", row.get("has_assemble")),
            ("JDK", row.get("has_jdk")),
            ("lda/ path filter", row.get("has_path_filter")),
            ("workflow_dispatch", row.get("has_workflow_dispatch")),
        )
        if not ok
    ]
    return {
        "state": "NOT_LANDED",
        "note": (
            "LDA Android CI is not a current-main Actions gate. Missing: %s. "
            "lda/workflows/android.yml outside .github/workflows is CLAIMED."
        )
        % (", ".join(missing) if missing else "workflow"),
    }


def measure_root(root):
    path = os.path.join(os.path.abspath(root), WORKFLOW)
    if not os.path.isfile(path):
        return {
            "measured": True,
            "has_lda_workdir": False,
            "has_assemble": False,
            "has_jdk": False,
            "has_path_filter": False,
            "has_workflow_dispatch": False,
            "wipes_repo_artifacts": False,
            "workflow": WORKFLOW,
            "stranded": STRANDED,
            "present": False,
            "titan": "NOT_WRITTEN",
        }
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        row = parse_workflow(handle.read())
    row["workflow"] = WORKFLOW
    row["stranded"] = STRANDED
    row["present"] = True
    return row


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Measure whether LDA Android CI is a current-main Actions gate"
    )
    parser.add_argument("--root", default=".")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run the stdlib fixtures and exit",
    )
    args = parser.parse_args(argv)
    if args.self_test:
        return 0 if _self_test() else 1
    row = measure_root(args.root)
    verdict = classify(row)
    payload = dict(row)
    payload.update(verdict)
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if row.get("measured") else 2


def _self_test():
    empty = classify({})
    assert empty["state"] == "UNMEASURED"
    missing = classify(parse_workflow("# battery only\npython3 test_land_desk.js\n"))
    assert missing["state"] == "NOT_LANDED"
    wipe = classify(
        parse_workflow(
            "\n".join(
                [
                    "working-directory: lda",
                    "assembleDebug",
                    "setup-java",
                    "paths:",
                    "  - lda/app/**",
                    "workflow_dispatch:",
                    "listArtifactsForRepo",
                ]
            )
        )
    )
    assert wipe["state"] == "NOT_LANDED"
    wired = classify(
        parse_workflow(
            "\n".join(
                [
                    "name: lda-android",
                    "on:",
                    "  workflow_dispatch:",
                    "  paths:",
                    "    - lda/app/**",
                    "jobs:",
                    "  validate:",
                    "    defaults:",
                    "      run:",
                    "        working-directory: lda",
                    "    steps:",
                    "      - uses: actions/setup-java@v4",
                    "      - run: gradle :app:assembleDebug --build-cache",
                ]
            )
        )
    )
    assert wired["state"] == "INTEGRATED"
    assert "assembleDebug" in wired["note"]
    return True


if __name__ == "__main__":
    sys.exit(main())
