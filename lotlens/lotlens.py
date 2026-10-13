#!/usr/bin/env python3
"""LotLens command line: import, inspect, traverse, annotate, export. Every command prints JSON.

    python lotlens/lotlens.py --workspace WS import lotlens/fixtures/synthetic_pilot --label pilot
    python lotlens/lotlens.py --workspace WS imports
    python lotlens/lotlens.py --workspace WS summary
    python lotlens/lotlens.py --workspace WS find LOT-WATER-01
    python lotlens/lotlens.py --workspace WS inspect sup-acme/lot/LOT-CITRIC-01
    python lotlens/lotlens.py --workspace WS impact sup-acme/lot/LOT-CITRIC-01 [--backward] [--assume NAME] [--out r.json] [--md r.md]
    python lotlens/lotlens.py --workspace WS facts [--kind contradiction]
    python lotlens/lotlens.py --workspace WS annotate pilot-plant/batch/BATCH-P3 "text" [--by NAME] [--supersedes ID]
    python lotlens/lotlens.py --workspace WS annotations [TARGET]
    python lotlens/lotlens.py --workspace WS compare V1 V2
    python lotlens/lotlens.py --workspace WS --versions V1 impact pilot-plant/package/PKG-P4-1   (ask the older import)
    python lotlens/lotlens.py assumptions

There is no command that runs an investigation for you. Each command performs its
stated mechanic and returns what it saw; the next question is the investigator's.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import engine  # noqa: E402


def _out(value, indent: int = 2) -> None:
    sys.stdout.write(json.dumps(value, indent=indent, ensure_ascii=False, sort_keys=False) + "\n")


def cmd_import(ws: engine.Workspace, args) -> dict:
    return ws.import_dir(args.source, label=args.label or "")


def cmd_imports(ws: engine.Workspace, args) -> dict:
    return {"workspace": str(ws.root), "imports": ws.imports()}


def cmd_summary(ws: engine.Workspace, args) -> dict:
    graph = ws.graph(args.versions)
    return {"workspace": str(ws.root), **graph.summary()}


def cmd_find(ws: engine.Workspace, args) -> dict:
    graph = ws.graph(args.versions)
    matches = graph.find(args.id)
    return {"id": args.id, "matches": [n.as_dict() for n in matches], "note": "same id in different namespaces stays different"}


def cmd_inspect(ws: engine.Workspace, args) -> dict:
    graph = ws.graph(args.versions)
    key = engine.parse_key(args.key)
    node = graph.nodes.get(key)
    if node is None:
        return {"key": args.key, "found": False}
    out_edges = [e.as_dict() for e in graph.edges if e.src == key]
    in_edges = [e.as_dict() for e in graph.edges if e.dst == key]
    rows = {}
    for s in node.sources:
        rows[f"{s.file}:{s.line}"] = graph.rows.get(f"{s.version}:{s.file}:{s.line}")
    return {
        "key": args.key,
        "found": True,
        "node": node.as_dict(),
        "source_rows": rows,
        "upstream": in_edges,
        "downstream": out_edges,
        "facts": graph.facts_for([key]),
        "annotations": ws.annotations(args.key),
    }


def cmd_impact(ws: engine.Workspace, args) -> dict:
    graph = ws.graph(args.versions)
    key = engine.parse_key(args.key)
    impact = graph.impact(key, "backward" if args.backward else "forward", args.assume or [])
    report = engine.build_report(ws, graph, impact)
    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    if args.md:
        Path(args.md).write_text(engine.render_markdown(report), encoding="utf-8", newline="\n")
    if args.brief:
        return {
            "query": impact["query"],
            "counts": impact.get("counts"),
            "affected": [
                {
                    "key": a["key"],
                    "status": a["status"],
                    "hops": a["hops"],
                    "detail": engine.node_detail(a["kind"], a["attrs"]),
                    "path": engine.path_summary(a["path"]),
                }
                for a in impact.get("affected", [])
            ],
            "content_sha256": report["content_sha256"],
            "written": {"json": args.out, "markdown": args.md},
        }
    if args.paths == "summary":
        shown = json.loads(json.dumps(report))
        for a in shown["impact"].get("affected", []):
            a["path"] = engine.path_summary(a["path"])
            a["detail"] = engine.node_detail(a["kind"], a["attrs"])
        return shown
    return report


def cmd_facts(ws: engine.Workspace, args) -> dict:
    graph = ws.graph(args.versions)
    facts = graph.facts if not args.kind else [f for f in graph.facts if f["kind"] == args.kind]
    return {"count": len(facts), "facts": facts}


def cmd_annotate(ws: engine.Workspace, args) -> dict:
    engine.parse_key(args.target)
    return ws.annotate(args.target, args.text, investigator=args.by or "", supersedes=args.supersedes)


def cmd_annotations(ws: engine.Workspace, args) -> dict:
    return {"target": args.target, "annotations": ws.annotations(args.target)}


def cmd_compare(ws: engine.Workspace, args) -> dict:
    return ws.compare(args.a, args.b)


def cmd_assumptions(ws, args) -> dict:
    return {name: {"description": spec["description"], "default": "off"} for name, spec in sorted(engine.ASSUMPTIONS.items())}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--workspace", "-w", default=".lotlens", help="workspace directory (created on first import)")
    parser.add_argument("--versions", action="append", default=None, metavar="VERSION",
                        help="import version to load; repeat the flag or comma-separate for several (default: the latest). "
                             "Takes one value, so it can sit before the command: --versions V1 impact ...")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("import"); p.add_argument("source"); p.add_argument("--label", default="")
    sub.add_parser("imports")
    sub.add_parser("summary")
    p = sub.add_parser("find"); p.add_argument("id")
    p = sub.add_parser("inspect"); p.add_argument("key")
    p = sub.add_parser("impact"); p.add_argument("key"); p.add_argument("--backward", action="store_true")
    p.add_argument("--assume", nargs="*", default=[]); p.add_argument("--out"); p.add_argument("--md"); p.add_argument("--brief", action="store_true")
    p.add_argument("--paths", default="full", help="full (edge objects) or summary (one 'from -> to (file:line)' line per hop) in the printed report; files written with --out keep the full form")
    p = sub.add_parser("facts"); p.add_argument("--kind")
    p = sub.add_parser("annotate"); p.add_argument("target"); p.add_argument("text"); p.add_argument("--by"); p.add_argument("--supersedes")
    p = sub.add_parser("annotations"); p.add_argument("target", nargs="?")
    p = sub.add_parser("compare"); p.add_argument("a"); p.add_argument("b")
    sub.add_parser("assumptions")
    return parser


COMMANDS = {
    "import": cmd_import, "imports": cmd_imports, "summary": cmd_summary, "find": cmd_find, "inspect": cmd_inspect,
    "impact": cmd_impact, "facts": cmd_facts, "annotate": cmd_annotate, "annotations": cmd_annotations,
    "compare": cmd_compare, "assumptions": cmd_assumptions,
}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.versions is not None:
        args.versions = [v.strip() for chunk in args.versions for v in chunk.split(",") if v.strip()] or None
    ws = engine.Workspace(args.workspace) if args.command != "assumptions" else None
    try:
        _out(COMMANDS[args.command](ws, args))
    except (ValueError, KeyError, FileNotFoundError) as exc:
        _out({"ok": False, "error": type(exc).__name__, "message": str(exc)})
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
