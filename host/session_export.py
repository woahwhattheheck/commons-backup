#!/usr/bin/env python3
"""Describe work still held by a Git session, without fetching or writing.

Dirty paths and commits absent from all observed remote refs need checkpointing.
A clean, remotely preserved branch ahead of main is a merge candidate. Comparisons
use local remote-tracking refs, not a claim about the current provider head. Missing
refs or incomplete history remain unknown instead of becoming a clean bill.
Submodule work is included even when local Git settings hide it from ordinary
status. The dirty inventory names the containing submodule path.

  python3 host/session_export.py --root /path/to/clone
  python3 host/session_export.py --main-ref origin/master --max-items 50
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

try:
    from host.git_source_capsules import _git_env
except ModuleNotFoundError:
    from git_source_capsules import _git_env


def classify(row):
    """Keep known local work visible even when a comparison is unavailable."""
    row = row or {}
    dirty = row.get("dirty") or 0
    unpushed = row.get("unpushed") or 0
    if dirty > 0 or unpushed > 0:
        return {
            "state": "NOT_LANDED",
            "note": "%s dirty path(s), %s commit(s) absent from observed remote refs. "
                    "Checkpoint these bytes, then merge the intended work to main."
                    % (row.get("dirty") if row.get("dirty") is not None else "unknown",
                       row.get("unpushed") if row.get("unpushed") is not None else "unknown"),
        }
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "note": "Session comparison is incomplete; inspect errors before treating work as preserved.",
        }
    if (row.get("ahead_of_main") or 0) > 0:
        return {
            "state": "CANDIDATE",
            "note": "This branch is preserved by observed remote refs but has %s commit(s) "
                    "not reachable from the observed main ref. Merge is still outstanding."
                    % row["ahead_of_main"],
        }
    return {
        "state": "INTEGRATED",
        "note": "No session-only bytes found against the observed refs. Provider freshness is not measured.",
    }


def measure_from_git_text(status_text, rev_list_text, ahead_text="0"):
    """Compatibility parser for already measured line-oriented Git output."""
    try:
        ahead = int(str(ahead_text).strip())
        if ahead < 0:
            raise ValueError
    except (TypeError, ValueError):
        return {"measured": False, "error": "invalid main-ahead count", "titan": "NOT_WRITTEN"}
    return {
        "measured": True,
        "dirty": sum(bool(line.strip()) for line in str(status_text or "").splitlines()),
        "unpushed": sum(bool(line.strip()) for line in str(rev_list_text or "").splitlines()),
        "ahead_of_main": ahead,
        "titan": "NOT_WRITTEN",
    }


def _run(root, args):
    env = _git_env()
    env["GIT_TERMINAL_PROMPT"] = "0"
    try:
        proc = subprocess.run(
            args, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            check=False,
            timeout=30, env=env,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return 2, "", str(error)
    # Universal-newline decoding would change CR bytes inside NUL-delimited
    # filenames. Decode bytes directly so the inventory remains literal.
    return (proc.returncode, proc.stdout.decode("utf-8", "surrogateescape"),
            proc.stderr.decode("utf-8", "surrogateescape"))


def _dirty_paths(status_text):
    fields = iter(status_text.split("\0"))
    paths = []
    for field in fields:
        if not field:
            continue
        if len(field) < 4 or field[2] != " ":
            raise ValueError("malformed Git status record")
        row = {"status": field[:2], "path": field[3:]}
        if "R" in field[:2] or "C" in field[:2]:
            original = next(fields, "")
            if not original:
                raise ValueError("missing original path for Git rename/copy")
            row["original_path"] = original
        paths.append(row)
    return paths


def measure_clone(root, main_ref="origin/main", max_items=200):
    root = os.path.abspath(root)
    row = {
        "measured": False, "root": root, "titan": "NOT_WRITTEN",
        "comparison_scope": "local_remote_tracking_refs", "provider_freshness_measured": False,
        "main_ref": main_ref, "dirty": None, "unpushed": None, "ahead_of_main": None,
        "dirty_paths": [], "unpushed_commits": [], "main_ahead_commits": [], "errors": [],
    }

    def git(*args):
        return _run(root, ["git", *args])

    def required(label, *args, strip=True):
        code, out, err = git(*args)
        if code:
            row["errors"].append(label + ": " + (err.strip() or "Git exited %s" % code))
            return None
        return out.strip() if strip else out.removesuffix("\n")

    top = required("repository", "rev-parse", "--show-toplevel", strip=False)
    if top is None:
        row["error"] = "; ".join(row["errors"])
        return row
    root = row["root"] = top
    code, status, error = git("status", "--porcelain=v1", "-z", "--untracked-files=all", "--ignore-submodules=none")
    if code:
        row["errors"].append("status: " + (error.strip() or "Git status failed"))
    else:
        try:
            paths = _dirty_paths(status)
            row["dirty"] = len(paths)
            row["dirty_paths"] = paths[:max_items]
            row["dirty_paths_truncated"] = len(paths) > max_items
        except ValueError as error:
            row["errors"].append("status: " + str(error))
    row["head_sha"] = required("HEAD", "rev-parse", "--verify", "HEAD^{commit}")
    if row["head_sha"] is None:
        row["error"] = "; ".join(row["errors"])
        return row
    row["main_sha"] = required("main ref", "rev-parse", "--verify", "--end-of-options", main_ref + "^{commit}")
    shallow = required("history", "rev-parse", "--is-shallow-repository")
    row["shallow"] = None if shallow is None else shallow == "true"
    code, branch, _ = git("symbolic-ref", "--quiet", "--short", "HEAD")
    row["branch"] = branch.strip() if code == 0 else None
    code, upstream, _ = git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}")
    row["upstream"] = upstream.strip() if code == 0 else None
    remote_refs = required("remote refs", "for-each-ref", "--format=%(refname)", "refs/remotes/")
    row["remote_ref_count"] = len(remote_refs.splitlines()) if remote_refs else 0

    def commits(label, output_key, count_key, *revisions):
        count = required(label, "rev-list", "--count", *revisions, "--")
        listing = required(label + " inventory", "rev-list", "--max-count=%s" % max_items, *revisions, "--")
        if count is not None and listing is not None:
            try:
                row[count_key] = int(count)
            except ValueError:
                row["errors"].append(label + ": invalid Git count")
                return
            row[output_key] = listing.splitlines() if listing else []
            row[output_key + "_truncated"] = row[count_key] > len(row[output_key])

    if row["main_sha"]:
        commits("main comparison", "main_ahead_commits", "ahead_of_main", row["main_sha"] + ".." + row["head_sha"])
    if remote_refs:
        commits("remote comparison", "unpushed_commits", "unpushed", row["head_sha"], "--not", "--remotes")
    elif remote_refs is not None:
        row["errors"].append("remote comparison: no observed remote refs; publication state is unknown")
    if row["upstream"]:
        value = required("upstream comparison", "rev-list", "--count", "@{upstream}..HEAD", "--")
        if value is not None:
            row["ahead_of_upstream"] = int(value)
    # A shared shallow boundary is excluded from the difference, so work on a
    # normal depth-one checkout can still be classified. A boundary included in
    # the difference might conceal common ancestry and cannot give an exact count.
    if row["shallow"] and any((row.get(key) or 0) > 0 for key in ("ahead_of_main", "unpushed")):
        shallow_path = required("shallow boundary", "rev-parse", "--git-path", "shallow")
        try:
            with open(os.path.join(root, shallow_path or ""), encoding="ascii") as handle:
                boundaries = handle.read().splitlines()
        except (OSError, UnicodeError) as error:
            boundaries = []
            row["errors"].append("shallow boundary: " + str(error))
        uncertain = set()
        for boundary in boundaries:
            code, _, error = git("merge-base", "--is-ancestor", boundary, row["head_sha"])
            if code == 1:
                continue
            if code:
                row["errors"].append("shallow reachability: " + error.strip())
                continue
            if row.get("ahead_of_main"):
                code, _, error = git("merge-base", "--is-ancestor", boundary, row["main_sha"])
                if code == 1:
                    uncertain.add("ahead_of_main")
                elif code:
                    row["errors"].append("shallow main reachability: " + error.strip())
            if row.get("unpushed"):
                containing = required("shallow remote reachability", "for-each-ref", "--format=%(refname)", "--contains=" + boundary, "refs/remotes/")
                if containing == "":
                    uncertain.add("unpushed")
        for key in sorted(uncertain):
            row["observed_" + key] = row[key]
            row[key] = None
            row["errors"].append("history: " + key + " crosses an unmatched shallow boundary; deepen to resolve")
    row["measured"] = not row["errors"]
    if row["errors"]:
        row["error"] = "; ".join(row["errors"])
    return row


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="clone or worktree to measure")
    parser.add_argument("--main-ref", default="origin/main", help="locally observed canonical branch")
    parser.add_argument("--max-items", type=int, default=200, help="maximum paths/commit IDs per inventory; counts stay exact")
    args = parser.parse_args(argv)
    if args.max_items < 1:
        parser.error("--max-items must be positive")
    row = measure_clone(args.root, args.main_ref, args.max_items)
    payload = {**row, **classify(row)}
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if row.get("measured") else 2


if __name__ == "__main__":
    sys.exit(main())
