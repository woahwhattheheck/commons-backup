# SPDX-License-Identifier: Apache-2.0
"""Classify whether a git event must run the L02 192-game development panel.

ADVANCE vs REJECT is unchanged. This helper only answers: did the event mutate
the executable L02 candidate, overlay, or panel runner? GitHub path filters
treat every file as changed on a new-branch push, so unrelated packets such as
the S02 admission-firewall bootstrap re-ran the known development REJECT
(mean own-cash delta -315.615, 80/96 cells negative) without touching L02
bytes. Unit tests still run; only the expensive official-engine matrix is gated.
Unknown bases fail closed and run the panel.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

CANDIDATE_DIR = (
    "revenue/kaggriculture/cloud-execution-lab/candidates/v3-l02-ledger-tranche"
)
EXECUTABLE_FILES = ("candidate.py", "ledger_tranche.py", "run_panel.py")
EXECUTABLE_PATHS = tuple(f"{CANDIDATE_DIR}/{name}" for name in EXECUTABLE_FILES)


def _posix(path: str) -> str:
    text = str(path).replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return text


def executable_l02_paths(changed_paths: Iterable[str]) -> list[str]:
    """Return the executable L02 paths present in a changed-path list."""
    hits: list[str] = []
    seen: set[str] = set()
    for raw in changed_paths:
        path = _posix(raw)
        if path in EXECUTABLE_PATHS or path in EXECUTABLE_FILES:
            key = path if path in EXECUTABLE_PATHS else f"{CANDIDATE_DIR}/{path}"
            if key not in seen:
                seen.add(key)
                hits.append(key)
    return hits


def panel_required(changed_paths: Iterable[str], *, event_name: str = "push",
                   force: bool = False, unknown_base: bool = False) -> bool:
    """True when the 192-game official-engine comparison must run."""
    if force or event_name == "workflow_dispatch" or unknown_base:
        return True
    return bool(executable_l02_paths(changed_paths))


def classify(changed_paths: Sequence[str], *, event_name: str = "push",
             head: str = "", base: str = "", force: bool = False,
             unknown_base: bool = False) -> dict[str, Any]:
    paths = [_posix(path) for path in changed_paths if str(path).strip()]
    hits = executable_l02_paths(paths)
    required = panel_required(
        paths, event_name=event_name, force=force, unknown_base=unknown_base)
    if event_name == "workflow_dispatch" or force:
        reason = "workflow_dispatch always runs the development panel"
    elif unknown_base:
        reason = "base commit unavailable; run panel fail-closed"
    elif required:
        reason = "executable L02 candidate, overlay, or panel runner changed"
    else:
        reason = "executable L02 bytes unchanged; skip 192-game panel"
    return {
        "schema": "titan.l02.panel-trigger.v1",
        "event_name": event_name,
        "head": head,
        "base": base,
        "unknown_base": unknown_base,
        "run_panel": required,
        "reason": reason,
        "changed_paths": paths,
        "executable_hits": hits,
        "scope": "gates the 192-game matrix only; ADVANCE vs REJECT is unchanged",
    }


def markdown(report: Mapping[str, Any]) -> str:
    decision = "RUN" if report.get("run_panel") else "SKIP"
    lines = [
        "# TITAN L02 panel trigger",
        "",
        f"Decision: **{decision}**",
        "",
        f"Reason: {report.get('reason')}",
        f"Event: `{report.get('event_name')}`",
        f"Head: `{report.get('head') or 'unspecified'}`",
        f"Base: `{report.get('base') or 'unspecified'}`",
        "",
        "Executable hits:",
    ]
    hits = list(report.get("executable_hits") or ())
    if hits:
        lines.extend(f"- `{path}`" for path in hits)
    else:
        lines.append("- (none)")
    lines.extend(["", "ADVANCE vs REJECT is unchanged."])
    if not report.get("run_panel"):
        lines.extend([
            "",
            "The 192-game official-engine comparison did not run because this "
            "event did not mutate `candidate.py`, `ledger_tranche.py`, or "
            "`run_panel.py`. Unit tests and the fail-closed REJECT contract "
            "remain in force for actual L02 candidate changes.",
        ])
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event", dest="event_name", default="push")
    parser.add_argument("--head", default="")
    parser.add_argument("--base", default="")
    parser.add_argument("--changed-file", action="append", default=[],
                        dest="changed_files")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--unknown-base", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--markdown", type=Path)
    args = parser.parse_args(argv)
    report = classify(
        args.changed_files, event_name=args.event_name, head=args.head,
        base=args.base, force=args.force, unknown_base=args.unknown_base)
    text = json.dumps(report, indent=2, sort_keys=True)
    print(text)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    if args.markdown is not None:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(markdown(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
