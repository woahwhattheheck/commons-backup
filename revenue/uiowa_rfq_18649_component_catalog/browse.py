#!/usr/bin/env python3
"""Search version-bound component commands without executing them."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATUSES = ("working", "static", "template", "incomplete")
NOTICE = (
    "Commands describe their recorded source revisions. Listing does not verify the current "
    "checkout or run a component. Sample evidence retains its stated basis; outputs are not University findings."
)


def read_catalog(path: Path) -> list[dict]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not isinstance(value.get("entries"), list):
        raise ValueError(f"{path.name}: catalog entries must be an array")
    snapshot = value.get("snapshot", {})
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("revision"), str):
        raise ValueError(f"{path.name}: snapshot revision is required")
    entries = []
    for entry in value["entries"]:
        if not isinstance(entry, dict):
            raise ValueError(f"{path.name}: each entry must be an object")
        for field in ("id", "title", "status", "work_order"):
            if not isinstance(entry.get(field), str) or not entry[field].strip():
                raise ValueError(f"{path.name}: nonempty {field} is required")
        if entry["status"] not in STATUSES:
            raise ValueError(f"{entry['id']}: unrecognized status")
        if entry["status"] == "working" and not isinstance(entry.get("command"), str):
            raise ValueError(f"{entry['id']}: working entry needs a command")
        entries.append({**entry, "revision": entry.get("revision", snapshot["revision"]),
                        "catalog": path.name})
    return entries


def search(paths: list[Path], query: str = "", status: str | None = None,
           exact_id: str | None = None) -> list[dict]:
    all_entries = []
    seen = set()
    for path in paths:
        for entry in read_catalog(path):
            if entry["id"] in seen:
                raise ValueError(f"duplicate component ID: {entry['id']}")
            seen.add(entry["id"])
            all_entries.append(entry)
    terms = query.casefold().split()
    selected = []
    for entry in all_entries:
        haystack = " ".join(str(entry.get(k, "")) for k in (
            "id", "title", "work_order", "supported_input", "produced_output", "command"
        )).casefold()
        if status and entry["status"] != status:
            continue
        if exact_id is not None and entry["id"] != exact_id:
            continue
        if all(term in haystack for term in terms):
            selected.append(entry)
    return sorted(selected, key=lambda e: (e["work_order"], e["id"]))


def render(entries: list[dict], format_name: str) -> str:
    if format_name == "json":
        return json.dumps({"schema": "uiowa.component-browser.v1", "notice": NOTICE,
                           "count": len(entries), "entries": entries}, indent=2, ensure_ascii=False) + "\n"
    lines = [f"{len(entries)} component(s)", NOTICE, ""]
    for e in entries:
        heading = f"{e['id']} | {e['work_order']} | {e['status']} | {e['title']}"
        lines.append(("## " if format_name == "markdown" else "") + heading)
        lines.append("Recorded revision: " + e["revision"])
        if e.get("supported_input"):
            lines.append("Input: " + str(e["supported_input"]))
        if e.get("produced_output"):
            lines.append("Output: " + str(e["produced_output"]))
        if e.get("prerequisites"):
            lines.append("Prerequisites: " + "; ".join(str(x) for x in e["prerequisites"]))
        if e.get("command"):
            lines.append("Working directory: " + str(e.get("command_cwd", ".")))
            # Indented code preserves arbitrary literal catalog text without shell evaluation.
            lines += ["", *["    " + line for line in e["command"].splitlines()], ""]
        else:
            lines.append("Command: none recorded for this " + e["status"] + " surface")
        for key in ("source", "readme"):
            item = e.get(key)
            if isinstance(item, dict) and item.get("path"):
                lines.append(f"{key.capitalize()}: {item['path']} (blob {item.get('blob_sha', 'UNRECORDED')})")
        sample = e.get("sample_result")
        if isinstance(sample, dict):
            lines.append(f"Sample basis: {sample.get('basis', 'UNRECORDED')}; {sample.get('summary', '')}")
        lines.append("")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", nargs="?", default="", help="all search words must match")
    parser.add_argument("--id", help="exact component ID")
    parser.add_argument("--status", choices=STATUSES)
    parser.add_argument("--format", choices=("text", "markdown", "json"), default="text")
    parser.add_argument("--catalog", type=Path, default=HERE / "component_catalog.json")
    parser.add_argument("--supplement", type=Path, default=HERE / "recovered_components.json")
    parser.add_argument("--base-only", action="store_true")
    args = parser.parse_args(argv)
    try:
        paths = [args.catalog] + ([] if args.base_only else [args.supplement])
        entries = search(paths, args.query, args.status, args.id)
        if args.id is not None and not entries:
            print(f"component not found under selected filters: {args.id}", file=sys.stderr)
            return 1
        print(render(entries, args.format), end="")
        return 0
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        print(f"component browser: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
