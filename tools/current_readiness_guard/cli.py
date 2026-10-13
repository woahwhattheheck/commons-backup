from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from .guard import Finding, PolicyError, load_policy, scan_paths

DEFAULT_POLICY = Path(__file__).with_name("policy.json")


def _policy(path: Path):
    try:
        return load_policy(path.read_bytes())
    except OSError as exc:
        raise PolicyError(f"cannot read policy: {exc}") from exc


def _emit(findings: list[Finding], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps([finding.to_dict() for finding in findings], sort_keys=True, separators=(",", ":")))
        return
    for finding in findings:
        suffix = f" [{finding.function}]" if finding.function else ""
        print(f"{finding.path}:{finding.line}:{finding.col}: {finding.rule} {finding.message}{suffix}")
    print(f"current-readiness-guard: {len(findings)} finding(s)" if findings else "current-readiness-guard: PASS")


def _changed(base: str, head: str) -> list[str]:
    for revision in (base, head):
        if not revision or revision.startswith("-") or any(character.isspace() for character in revision):
            raise PolicyError("git revisions must be nonempty tokens")
    try:
        process = subprocess.run(
            ["git", "diff", "--name-only", "--diff-filter=ACMRT", f"{base}...{head}", "--", "revenue"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            text=True,
            encoding="utf-8",
        )
    except OSError as exc:
        raise PolicyError(f"git diff failed: {exc}") from exc
    if process.returncode != 0:
        raise PolicyError(f"git diff failed: {process.stderr.strip() or process.returncode}")
    return sorted({line.strip() for line in process.stdout.splitlines() if line.strip().endswith(".py")})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prevent caller-minted current readiness in changed revenue Python")
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--json", action="store_true", dest="as_json")
    subparsers = parser.add_subparsers(dest="command", required=True)
    scan = subparsers.add_parser("scan")
    scan.add_argument("paths", nargs="+")
    subparsers.add_parser("all", help="advisory full-repository revenue Python audit")
    changed = subparsers.add_parser("changed")
    changed.add_argument("--base", required=True)
    changed.add_argument("--head", required=True)
    args = parser.parse_args(argv)
    try:
        exemptions = _policy(args.policy)
        if args.command == "scan":
            paths = args.paths
        elif args.command == "changed":
            paths = _changed(args.base, args.head)
        else:
            paths = [path.relative_to(Path.cwd()).as_posix() for path in sorted(Path.cwd().glob("revenue/**/*.py"))]
        findings = scan_paths(paths, root=Path.cwd(), exemptions=exemptions)
    except PolicyError as exc:
        print(f"current-readiness-guard policy/error: {exc}", file=sys.stderr)
        return 2
    _emit(findings, as_json=args.as_json)
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
