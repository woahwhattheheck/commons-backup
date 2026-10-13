#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
from typing import Any
from managed_common import ManagedClippingError, _sha256, load_project, verify_source
from managed_adapters import normalize_cedar_keeps, normalize_kestrel_segments
from managed_project import create_project, edit_moment
from managed_render import export_handoff, render_project

def project_summary(project_path: Path) -> dict[str, Any]:
    project = load_project(project_path)
    source = verify_source(project)
    rendered = sum(1 for m in project["moments"] if m.get("renders"))
    selection = project.get("selection") or {}
    return {
        "schema": project["schema"],
        "project": str(project_path),
        "source": str(source),
        "source_sha256": project["source"]["sha256"],
        "edit_revision": project["edit_revision"],
        "moment_count": len(project["moments"]),
        "rendered_moments": rendered,
        "synthetic_demo": project["synthetic_demo"],
        "selection_mode": selection.get("mode", "unspecified"),
        "distinct_moments": bool(selection.get("distinct", False)),
        "transcript_refs": sum(len(m.get("transcript_refs") or []) for m in project["moments"]),
    }


def _read_json(path: str | None) -> Any | None:
    if path is None:
        return None
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if value is None:
        raise ManagedClippingError(f"{path}: input JSON cannot be null; supply a document or list")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("init", help="create an editable clipping project")
    p.add_argument("source", type=Path)
    p.add_argument("project", type=Path)
    p.add_argument("--transcript-json")
    p.add_argument("--cedar-keeps-json")
    p.add_argument("--moments", type=int, default=20)
    p.add_argument("--synthetic-demo", action="store_true")

    p = sub.add_parser("edit", help="edit one clip; creates a new project revision")
    p.add_argument("project", type=Path)
    p.add_argument("clip_id")
    p.add_argument("--start-ms", type=int)
    p.add_argument("--end-ms", type=int)
    p.add_argument("--caption")
    p.add_argument("--hook")
    p.add_argument("--crop", help="normalized x,y,w,h")

    p = sub.add_parser("render", help="render all or selected clips")
    p.add_argument("project", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("--clip", action="append", default=[])

    p = sub.add_parser("handoff", help="export latest renders + editable metadata")
    p.add_argument("project", type=Path)
    p.add_argument("destination", type=Path)

    p = sub.add_parser("summary", help="verify source synchronization and summarize project")
    p.add_argument("project", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "init":
            result = create_project(
                args.source,
                args.project,
                transcript_document=_read_json(args.transcript_json),
                cedar_keeps=_read_json(args.cedar_keeps_json),
                moment_count=args.moments,
                synthetic_demo=args.synthetic_demo,
            )
            print(json.dumps({"project": str(args.project), "moments": len(result["moments"]), "revision": result["edit_revision"]}, sort_keys=True))
        elif args.command == "edit":
            result = edit_moment(
                args.project, args.clip_id, start_ms=args.start_ms, end_ms=args.end_ms,
                caption=args.caption, hook=args.hook, crop=args.crop,
            )
            print(json.dumps({"project": str(args.project), "clip_id": args.clip_id, "revision": result["edit_revision"]}, sort_keys=True))
        elif args.command == "render":
            result = render_project(args.project, args.output, args.clip or None)
            print(json.dumps({"rendered": len(result), "clips": [r["clip_id"] for r in result]}, sort_keys=True))
        elif args.command == "handoff":
            print(json.dumps(export_handoff(args.project, args.destination), sort_keys=True))
        elif args.command == "summary":
            print(json.dumps(project_summary(args.project), sort_keys=True))
        return 0
    except (ManagedClippingError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"managed-clipping: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
