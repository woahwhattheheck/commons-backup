#!/usr/bin/env python3
"""Classify tracked Commons paths and emit deterministic coordination facts."""

from __future__ import annotations

import argparse
import ast
from bisect import bisect_left
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Iterable, Sequence


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "architecture" / "path-manifest.json"


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def manifest_digest(manifest: dict) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(manifest).encode("utf-8")).hexdigest()


def _glob_regex(pattern: str) -> re.Pattern[str]:
    """Compile a small, path-segment-aware glob language.

    `*` stays within one segment. `**` crosses directories. `**/` also matches
    the empty prefix so one rule can observe root and nested files.
    """

    out = ["^"]
    index = 0
    while index < len(pattern):
        char = pattern[index]
        if char == "*":
            if index + 1 < len(pattern) and pattern[index + 1] == "*":
                index += 2
                if index < len(pattern) and pattern[index] == "/":
                    out.append("(?:.*/)?")
                    index += 1
                else:
                    out.append(".*")
                continue
            out.append("[^/]*")
        elif char == "?":
            out.append("[^/]")
        else:
            out.append(re.escape(char))
        index += 1
    # Git permits newlines within filenames. Wildcards include them, while a
    # literal pattern must not also match a name with an extra final newline.
    out.append(r"\Z")
    return re.compile("".join(out), re.DOTALL)


def load_manifest(path: Path = DEFAULT_MANIFEST) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        manifest = json.load(handle)
    if manifest.get("schema") != "commons-path-manifest-v1":
        raise ValueError("unsupported path manifest schema")
    if manifest.get("participation_effect") != "NONE":
        raise ValueError("path manifest must stay descriptive")
    if manifest.get("evaluation") != "FIRST_MATCH":
        raise ValueError("path manifest evaluation must be FIRST_MATCH")
    class_names = set(manifest.get("classes", {}))
    seen = set()
    for rule in list(manifest.get("rules", [])) + [manifest.get("fallback", {})]:
        rule_id = rule.get("id")
        if not rule_id or rule_id in seen:
            raise ValueError("path manifest rule ids must be unique and nonempty")
        seen.add(rule_id)
        if rule.get("classification") not in class_names:
            raise ValueError("unknown classification on rule %s" % rule_id)
        if not isinstance(rule.get("patterns"), list) or not rule["patterns"]:
            raise ValueError("rule %s has no patterns" % rule_id)
        for pattern in rule["patterns"]:
            _glob_regex(pattern)
    return manifest


def _normalized(path: str) -> str:
    # These are Git paths, already separated with '/'. A backslash is a
    # filename character, not an alternate directory separator.
    value = str(path)
    while value.startswith("./"):
        value = value[2:]
    if not value or value.startswith("/") or ".." in value.split("/"):
        raise ValueError("path is not repository-relative: %r" % path)
    return value


class PathClassifier:
    def __init__(self, manifest: dict):
        self.manifest = manifest
        self.rules = []
        for rule in manifest["rules"]:
            self.rules.append((rule, [_glob_regex(item) for item in rule["patterns"]]))
        fallback = manifest["fallback"]
        self.fallback = (fallback, [_glob_regex(item) for item in fallback["patterns"]])

    def classify(self, path: str) -> dict:
        value = _normalized(path)
        for rule, patterns in self.rules:
            if any(pattern.match(value) for pattern in patterns):
                return self._result(value, rule)
        return self._result(value, self.fallback[0])

    @staticmethod
    def _result(path: str, rule: dict) -> dict:
        return {
            "path": path,
            "rule_id": rule["id"],
            "classification": rule["classification"],
            "subsystem": rule["subsystem"],
            "producer": rule["producer"],
            "tests": list(rule["tests"]),
            "flags": list(rule["flags"]),
        }


def tracked_files(root: Path = ROOT) -> list[str]:
    # An explicit report root must not inherit another Git command's index or
    # repository selectors (for example when launched from a hook).
    env = os.environ.copy()
    for name in (
        "GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE",
        "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_SHALLOW_FILE", "GIT_GRAFT_FILE", "GIT_NAMESPACE", "GIT_PREFIX",
        "GIT_IMPLICIT_WORK_TREE",
    ):
        env.pop(name, None)
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        check=False,
        capture_output=True,
        env=env,
    )
    if result.returncode:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(detail or "git ls-files failed")
    return sorted(
        item.decode("utf-8", errors="surrogateescape")
        for item in result.stdout.split(b"\0")
        if item
    )


def literal_sequence(source_path: Path, symbol: str) -> list[str]:
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    for node in tree.body:
        names = []
        value = None
        if isinstance(node, ast.Assign):
            names = [item.id for item in node.targets if isinstance(item, ast.Name)]
            value = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names = [node.target.id]
            value = node.value
        if symbol not in names or value is None:
            continue
        resolved = ast.literal_eval(value)
        if not isinstance(resolved, (list, tuple)) or not all(isinstance(item, str) for item in resolved):
            raise ValueError("%s:%s is not a literal string sequence" % (source_path, symbol))
        return list(resolved)
    raise ValueError("%s does not define %s" % (source_path, symbol))


def _generator_inventory(root: Path, manifest: dict, classifier: PathClassifier, paths: set[str]) -> list[dict]:
    out = []
    # Only the first tracked descendant is needed to classify a directory.
    # Sort once, then seek to each prefix instead of scanning the whole tree
    # for every declared generator target.
    ordered_paths = sorted(paths)
    for contract in manifest.get("generator_contracts", []):
        declared = literal_sequence(root / contract["source"], contract["symbol"])
        rows = []
        missing = []
        unmapped = []
        for item in declared:
            prefix = item.rstrip("/") + "/"
            position = bisect_left(ordered_paths, prefix)
            descendant = (ordered_paths[position]
                          if position < len(ordered_paths)
                          and ordered_paths[position].startswith(prefix) else None)
            if item in paths:
                tracked = True
                target_kind = "TRACKED_FILE"
                classification_path = item
            elif descendant is not None:
                tracked = True
                target_kind = "TRACKED_DIRECTORY"
                classification_path = descendant
            else:
                tracked = False
                target_kind = "MISSING_PATH"
                # Classify a missing literal as declared. Appending a made-up
                # descendant changes the path type (for example panel.json)
                # and can create a false UNMAPPED diagnostic.
                classification_path = item
            row = classifier.classify(classification_path)
            target = {
                "path": item,
                "tracked": tracked,
                "target_kind": target_kind,
                "classification_path": classification_path,
                "classification": row["classification"],
                "rule_id": row["rule_id"],
            }
            rows.append(target)
            if not tracked:
                missing.append(item)
            if row["classification"] == "UNMAPPED":
                unmapped.append(item)
        out.append(
            {
                "id": contract["id"],
                "source": contract["source"],
                "symbol": contract["symbol"],
                "producer": contract["producer"],
                "path_semantics": contract.get("path_semantics", "UNSPECIFIED"),
                "tests": list(contract["tests"]),
                "declared_count": len(declared),
                "classification_counts": dict(sorted(Counter(row["classification"] for row in rows).items())),
                "missing_tracked_targets": sorted(missing),
                "unmapped_count": len(unmapped),
                "unmapped_targets": sorted(unmapped),
                "targets": rows,
            }
        )
    return out


def build_report(
    root: Path,
    manifest: dict,
    paths: Iterable[str] | None = None,
    include_rows: bool = False,
) -> dict:
    classifier = PathClassifier(manifest)
    selected = sorted(set(paths if paths is not None else tracked_files(root)))
    rows = [classifier.classify(path) for path in selected]
    unmapped = [row["path"] for row in rows if row["classification"] == "UNMAPPED"]
    root_tests = [path for path in selected if "/" not in path and re.match(r"^test_[^/]*\.(?:py|js)\Z", path)]
    nested_tests = [path for path in selected if "/" in path and re.search(r"(?:^|/)test[^/]*\.(?:py|js)\Z", path)]
    generator_contracts = _generator_inventory(root, manifest, classifier, set(selected))
    generator_unmapped_targets = [
        {"contract_id": item["id"], "path": path}
        for item in generator_contracts
        for path in item["unmapped_targets"]
    ]
    report = {
        "schema": "commons-path-report-v1",
        "manifest_digest": manifest_digest(manifest),
        "participation_effect": "NONE",
        "tracked_files": len(rows),
        "classification_counts": dict(sorted(Counter(row["classification"] for row in rows).items())),
        "subsystem_counts": dict(sorted(Counter(row["subsystem"] for row in rows).items())),
        "unmapped_count": len(unmapped),
        "unmapped_paths": unmapped,
        "tests": {
            "root_count": len(root_tests),
            "nested_count": len(nested_tests),
            "root": root_tests,
            "nested": nested_tests,
        },
        "generator_contracts": generator_contracts,
        "generator_unmapped_count": len(generator_unmapped_targets),
        "generator_unmapped_targets": generator_unmapped_targets,
    }
    if include_rows:
        report["paths"] = rows
    return report


def markdown_summary(report: dict) -> str:
    counts = " · ".join("%s %s" % (name, count) for name, count in report["classification_counts"].items())
    lines = [
        "## Commons path manifest",
        "",
        "- Tracked files: **%d**" % report["tracked_files"],
        "- Unmapped, visibly reported: **%d**" % report["unmapped_count"],
        "- Mixed staging/generator targets unmapped: **%d**" % report["generator_unmapped_count"],
        "- Tests discovered: **%d root + %d nested**"
        % (report["tests"]["root_count"], report["tests"]["nested_count"]),
        "- Classes: %s" % (counts or "none"),
        "- Manifest: `%s`" % report["manifest_digest"],
    ]
    for item in report["generator_contracts"]:
        lines.append(
            "- Mixed staging/generator contract `%s:%s`: **%d targets**, **%d missing tracked**, **%d unmapped**"
            % (
                item["source"],
                item["symbol"],
                item["declared_count"],
                len(item["missing_tracked_targets"]),
                item["unmapped_count"],
            )
        )
        if item["missing_tracked_targets"]:
            lines.append("  - Missing tracked: %s" % ", ".join("`%s`" % path for path in item["missing_tracked_targets"]))
        if item["unmapped_targets"]:
            lines.append("  - Unmapped declarations: %s" % ", ".join("`%s`" % path for path in item["unmapped_targets"]))
    if report["unmapped_paths"]:
        lines.extend(["", "First unmapped paths:", ""])
        lines.extend("- `%s`" % path for path in report["unmapped_paths"][:25])
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--summary", type=Path, help="append Markdown diagnostics to this file")
    parser.add_argument("--include-rows", action="store_true")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    manifest_path = (args.manifest or root / "architecture" / "path-manifest.json").resolve()
    try:
        manifest = load_manifest(manifest_path)
        report = build_report(root, manifest, include_rows=args.include_rows)
    except (OSError, RuntimeError, ValueError, SyntaxError, json.JSONDecodeError) as exc:
        print("PATH MANIFEST: ERROR — %s" % exc, file=sys.stderr)
        return 2
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered, encoding="utf-8")
    if args.summary:
        with args.summary.open("a", encoding="utf-8") as handle:
            handle.write(markdown_summary(report))
    print("PATH MANIFEST: OBSERVED %d tracked files; %d visibly unmapped" % (report["tracked_files"], report["unmapped_count"]))
    print("PATH MANIFEST: %d mixed staging/generator targets visibly unmapped" % report["generator_unmapped_count"])
    print("PATH MANIFEST: %d root tests; %d nested tests" % (report["tests"]["root_count"], report["tests"]["nested_count"]))
    print("PATH MANIFEST: %s" % report["manifest_digest"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
