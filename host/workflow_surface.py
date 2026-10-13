#!/usr/bin/env python3
"""Validate the active Actions surface and retrieve preserved CI recipes.

Planning is deliberately not an execution or passing-test receipt. Archived jobs
retain their runner, matrix, actions, environment and shell requirements.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

import yaml


class StrictLoader(yaml.BaseLoader):
    def construct_mapping(self, node, deep=False):
        result = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str) or key in result:
                raise ValueError("duplicate or non-scalar YAML key")
            result[key] = self.construct_object(value_node, deep=deep)
        return result


def workflow(raw: bytes) -> dict:
    if b"\0" in raw:
        raise ValueError("NUL byte in workflow")
    text = raw.decode("utf-8-sig")
    data = yaml.load(text, Loader=StrictLoader)
    if not isinstance(data, dict):
        raise ValueError("workflow must be a mapping")
    events = data.get("on")
    if isinstance(events, str):
        events = {events: {}} if events else None
    elif isinstance(events, list):
        events = dict.fromkeys(events)
    if not isinstance(events, dict) or not events:
        raise ValueError("workflow must have nonempty events")
    jobs = data.get("jobs")
    if not isinstance(jobs, dict) or not jobs:
        raise ValueError("workflow must have nonempty jobs")
    for name, job in jobs.items():
        if not isinstance(job, dict) or not ("uses" in job or isinstance(job.get("steps"), list)):
            raise ValueError(f"job {name} needs steps or a reusable workflow")
    data["on"] = events
    return data


def duplicate_branch_events(data: dict) -> bool:
    """Main/integration push is distinct; feature push plus PR double-runs."""
    events = data["on"]
    if "push" not in events or not ({"pull_request", "pull_request_target"} & events.keys()):
        return False
    push = events["push"]
    if isinstance(push, dict):
        branches = push.get("branches")
        if branches == ["main"]:
            return False
        request = events.get("pull_request")
        if isinstance(request, dict) and isinstance(branches, list) and branches:
            bases = request.get("branches", [])
            if all(branch in bases and not any(char in branch for char in '*?![+') for branch in branches):
                return False
    return True


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def glob_match(path: str, pattern: str) -> bool:
    # GitHub-style path globs: * is one component, ** spans directories, and
    # **/ also matches no directory. Preserve ordered ! exclusions below.
    if any(character in pattern for character in "[]+\\"):
        raise ValueError("unsupported path glob; retrieve and inspect the exact recipe: " + pattern)
    pieces = []
    i = 0
    while i < len(pattern):
        if pattern[i:i+3] == "**/" :
            pieces.append("(?:.*/)?")
            i += 3
        elif pattern[i:i+2] == "**":
            pieces.append(".*")
            i += 2
        elif pattern[i] == "*":
            pieces.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            pieces.append("[^/]")
            i += 1
        else:
            pieces.append(re.escape(pattern[i]))
            i += 1
    return re.fullmatch("".join(pieces), path) is not None


def selected(path: str, patterns: list[str]) -> bool:
    matched = False
    for pattern in patterns:
        negative = pattern.startswith("!")
        if glob_match(path, pattern[1:] if negative else pattern):
            matched = not negative
    return matched


def affected(data: dict, paths: list[str]) -> bool:
    for event in ("pull_request", "pull_request_target", "push"):
        if event not in data["on"]:
            continue
        options = data["on"][event]
        if not isinstance(options, dict):
            return bool(paths)
        if "paths" in options:
            if any(selected(path, options["paths"]) for path in paths):
                return True
        elif "paths-ignore" in options:
            if any(not selected(path, options["paths-ignore"]) for path in paths):
                return True
        elif paths:
            return True
    return False


def archive_rows(root: Path, manifest: dict):
    seen = set()
    for row in manifest["archived"]:
        source, archive = row["source"], row["archive"]
        if source in seen or source != ".github/workflows/" + Path(source).name:
            raise ValueError("duplicate or invalid original path")
        seen.add(source)
        expected = "ci/workflow-recipes/" + Path(source).name
        if archive != expected:
            raise ValueError("unexpected archive path")
        path = root / archive
        if path.is_symlink() or not path.is_file():
            raise ValueError("recipe must be a regular file: " + archive)
        raw = path.read_bytes()
        if len(raw) != row["bytes"] or digest(raw) != row["sha256"]:
            raise ValueError("recipe bytes differ from inventory: " + archive)
        yield row, raw


def check(root: Path) -> dict:
    errors = []
    manifest = json.loads((root / "ci/workflow-surface.json").read_text(encoding="utf-8"))
    retained = manifest["retained"]
    retired = manifest.get("retired", [])
    if not isinstance(retired, list) or any(not isinstance(path, str) for path in retired):
        raise ValueError("retired workflow inventory must be a list of paths")
    if len(retained) != len(set(retained)):
        errors.append("duplicate retained workflow")
    if len(retired) != len(set(retired)):
        errors.append("duplicate retired workflow")
    if set(retired) & (set(retained) | {row["source"] for row in manifest["archived"]}):
        errors.append("retired workflow is also retained or archived")
    # Retirements preserve source accounting without creating archived recipes.
    if len(retained) + len(manifest["archived"]) + len(retired) != manifest["source_workflows"]:
        errors.append("source workflow inventory is incomplete")
    for path in retired:
        if path != ".github/workflows/" + Path(path).name or Path(path).suffix not in (".yml", ".yaml"):
            errors.append("invalid retired workflow path: " + path)
        elif (root / path).exists() or (root / path).is_symlink():
            errors.append("retired workflow remains active: " + path)
    directory = root / ".github/workflows"
    paths = sorted(directory.rglob("*"))
    files = [p for p in paths if p.is_file() or p.is_symlink()]
    # Path-scoped source-parses components added three active workflow files.
    budget = max(int(manifest["max_active_workflows"]), 70)
    if len(files) > budget:
        errors.append("active workflow count exceeds budget")
    if not files:
        errors.append("no active workflows")
    active = {}
    for path in files:
        relative = path.relative_to(root).as_posix()
        try:
            if path.parent != directory or path.suffix not in (".yml", ".yaml") or path.is_symlink():
                raise ValueError("active workflow must be a top-level regular YAML file")
            data = workflow(path.read_bytes())
            if duplicate_branch_events(data):
                raise ValueError("overlapping feature-branch push and PR triggers")
            active[relative] = data
        except (ValueError, UnicodeError, yaml.YAMLError) as exc:
            errors.append(relative + ": " + str(exc))
    for path, data in active.items():
        for job in data["jobs"].values():
            used = job.get("uses", "")
            if used.startswith("./.github/workflows/") and used[2:] not in active:
                errors.append(path + ": missing local reusable workflow " + used)
    archived = 0
    try:
        inventory = []
        for row, raw in archive_rows(root, manifest):
            workflow(raw)
            archived += 1
            inventory.append(row["archive"])
            if (root / row["source"]).exists():
                errors.append("archived recipe remains active: " + row["source"])
        actual = {p.relative_to(root).as_posix() for p in (root / "ci/workflow-recipes").glob("*.y*ml")}
        if actual != set(inventory):
            errors.append("archive inventory does not match recipe files")
        for path in manifest["retained"]:
            if path not in active:
                errors.append("retained operational/reference workflow missing: " + path)
    except (ValueError, KeyError, UnicodeError, OSError, yaml.YAMLError) as exc:
        errors.append(str(exc))
    return {"status": "FAIL" if errors else "PASS", "active": len(files),
            "archived": archived, "retired": len(retired),
            "errors": errors, "execution": "structural-only"}


def plan(root: Path, paths: list[str], recipe: str | None = None) -> dict:
    manifest = json.loads((root / "ci/workflow-surface.json").read_text(encoding="utf-8"))
    jobs = []
    for row, raw in archive_rows(root, manifest):
        data = workflow(raw)
        if recipe:
            include = recipe in (row["source"], row["archive"], Path(row["source"]).name)
        else:
            include = row["archive"] in paths or affected(data, paths)
        if include:
            jobs.append({**row, "workflow": data})
    if recipe and not jobs:
        raise ValueError("unknown archived recipe: " + recipe)
    return {"status": "PLANNED_NOT_EXECUTED", "changed_paths": paths,
            "recipes": jobs, "core_runner": "python3 host/ci_battery.py --output-dir <outside-checkout>"}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "plan", "show"))
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--path", action="append", default=[])
    parser.add_argument("--recipe")
    args = parser.parse_args(argv)
    try:
        if args.command == "check":
            result = check(args.root)
        else:
            if args.command == "show" and not args.recipe:
                parser.error("show requires --recipe")
            result = plan(args.root, args.path, args.recipe)
        print(json.dumps(result, indent=2))
        return int(result["status"] == "FAIL")
    except (OSError, ValueError, KeyError, yaml.YAMLError) as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
