#!/usr/bin/env python3
"""LotLens — lot-impact investigation over existing exports (Build Order 2, 2026-09-04).

A read-only traceability engine. Import the CSV family described in
IMPORT_SPEC.md (supplier lots, splits, batches, consumption, rework, packages,
shipments), keep every identifier inside its namespace, keep every source
row, and answer "this lot has a problem; what else could it affect?" with an
evidence path for every affected item.

Three kinds of statement, never blended:
  KNOWN_AFFECTED        a documented path of rows connects the start to the item
  POTENTIALLY_AFFECTED  reachable only through an edge that an investigator asked
                        the engine to assume, and the assumption is named on the edge
  UNRESOLVED            a reference the records cannot resolve, or a stage with no
                        downstream record at all. Absence of a path is not proof of
                        no impact; the report says so per item.

Contradictions (a lot consumed beyond its quantity, a shipment claiming two
packages, a unit mismatch) are preserved as facts with every row that produced
them. Investigator annotations live in their own append-only file with
revisions; they never alter observations. The engine chooses nothing about the
investigation: it imports, inspects, traverses, filters, annotates and exports.
Stdlib only.
"""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import io
import json
import os
import re
import shutil
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

SCHEMA = "commons-lotlens/v1"
KINDS = ("lot", "batch", "package", "shipment")
RELATIONS = ("split", "consumed", "rework", "packed", "shipped")
STATUS_KNOWN = "KNOWN_AFFECTED"
STATUS_POTENTIAL = "POTENTIALLY_AFFECTED"
STATUS_UNRESOLVED = "UNRESOLVED"

# One import family. Each file is optional; unknown columns are kept in the raw row.
FILES = {
    "lots.csv": ("namespace", "lot_id"),
    "splits.csv": ("namespace", "lot_id", "child_lot_id"),
    "batches.csv": ("namespace", "batch_id"),
    "consumption.csv": ("namespace", "batch_id", "input_namespace", "input_kind", "input_id"),
    "rework.csv": ("namespace", "rework_id", "from_batch_id", "into_batch_id"),
    "packages.csv": ("namespace", "package_id"),
    "shipments.csv": ("namespace", "shipment_id", "package_id"),
}

NodeKey = tuple[str, str, str]  # (namespace, kind, id)


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def key_str(key: NodeKey) -> str:
    return "/".join(key)


def parse_key(text: str) -> NodeKey:
    parts = text.split("/")
    if len(parts) != 3 or parts[1] not in KINDS or not parts[0] or not parts[2]:
        raise ValueError("node keys look like namespace/kind/id with kind in " + ", ".join(KINDS))
    return (parts[0], parts[1], parts[2])


def _num(value: Any) -> float | None:
    try:
        text = str(value).strip().replace(",", "")
        return float(text) if text else None
    except ValueError:
        return None


def _date(value: Any) -> str:
    return str(value or "").strip()[:10]


@dataclass
class Source:
    version: str
    file: str
    line: int

    def as_dict(self) -> dict[str, Any]:
        return {"version": self.version, "file": self.file, "line": self.line}


@dataclass
class Node:
    key: NodeKey
    attrs: dict[str, Any] = field(default_factory=dict)
    sources: list[Source] = field(default_factory=list)

    @property
    def namespace(self) -> str:
        return self.key[0]

    @property
    def kind(self) -> str:
        return self.key[1]

    @property
    def id(self) -> str:
        return self.key[2]

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": key_str(self.key),
            "namespace": self.namespace,
            "kind": self.kind,
            "id": self.id,
            "attrs": dict(self.attrs),
            "sources": [s.as_dict() for s in self.sources],
        }


@dataclass
class Edge:
    src: NodeKey
    dst: NodeKey
    relation: str
    status: str = "known"  # known | potential
    assumption: str | None = None
    quantity: float | None = None
    unit: str = ""
    sources: list[Source] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "from": key_str(self.src),
            "to": key_str(self.dst),
            "relation": self.relation,
            "status": self.status,
            "assumption": self.assumption,
            "quantity": self.quantity,
            "unit": self.unit,
            "sources": [s.as_dict() for s in self.sources],
        }


# ---------------------------------------------------------------------------
# Assumptions: named, off by default, cited on every edge they create.
# ---------------------------------------------------------------------------


def _assume_unlinked_package_same_product_day(graph: "Graph") -> list[Edge]:
    """A package with no batch link may come from a batch of the same product,
    same namespace, produced on the day it was packed."""
    out: list[Edge] = []
    linked = {e.dst for e in graph.edges if e.relation == "packed"}
    batches_by_ns_product: dict[tuple[str, str], list[Node]] = defaultdict(list)
    for node in graph.nodes.values():
        if node.kind == "batch":
            batches_by_ns_product[(node.namespace, str(node.attrs.get("product", "")))].append(node)
    for node in graph.nodes.values():
        if node.kind != "package" or node.key in linked:
            continue
        product = str(node.attrs.get("product", ""))
        day = _date(node.attrs.get("packed_at"))
        for batch in sorted(batches_by_ns_product.get((node.namespace, product), []), key=lambda n: n.id):
            if day and _date(batch.attrs.get("produced_at")) == day:
                out.append(
                    Edge(
                        batch.key,
                        node.key,
                        "packed",
                        status="potential",
                        assumption="unlinked_package_same_product_day",
                        sources=list(batch.sources) + list(node.sources),
                    )
                )
    return out


ASSUMPTIONS: dict[str, dict[str, Any]] = {
    "unlinked_package_same_product_day": {
        "description": (
            "A package whose batch link is missing is treated as possibly packed from any batch in "
            "the same namespace with the same product produced on the packing day. Off unless asked."
        ),
        "fn": _assume_unlinked_package_same_product_day,
    },
}


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------


class Graph:
    def __init__(self) -> None:
        self.nodes: dict[NodeKey, Node] = {}
        self.edges: list[Edge] = []
        self.facts: list[dict[str, Any]] = []
        self.rows: dict[str, dict[str, Any]] = {}  # "version:file:line" -> raw row
        self.versions: list[str] = []

    # ---- construction --------------------------------------------------
    def _node(self, key: NodeKey, source: Source | None = None, **attrs: Any) -> Node:
        node = self.nodes.get(key)
        if node is None:
            node = Node(key)
            self.nodes[key] = node
        for name, value in attrs.items():
            if value not in (None, ""):
                node.attrs.setdefault(name, value)
        if source is not None and source.as_dict() not in [s.as_dict() for s in node.sources]:
            node.sources.append(source)
        return node

    def _edge(self, src: NodeKey, dst: NodeKey, relation: str, source: Source, quantity: Any = None, unit: str = "") -> Edge:
        for existing in self.edges:
            if existing.src == src and existing.dst == dst and existing.relation == relation and existing.status == "known":
                if source.as_dict() not in [s.as_dict() for s in existing.sources]:
                    existing.sources.append(source)
                if existing.quantity is not None and _num(quantity) is not None and existing.quantity != _num(quantity):
                    self.fact("contradiction", "duplicate_link_different_quantity", [src, dst], existing.sources,
                              detail={"quantities": [existing.quantity, _num(quantity)], "relation": relation})
                return existing
        edge = Edge(src, dst, relation, quantity=_num(quantity), unit=str(unit or ""), sources=[source])
        self.edges.append(edge)
        return edge

    def fact(self, kind: str, code: str, keys: Iterable[NodeKey], sources: Iterable[Source], detail: dict[str, Any] | None = None) -> None:
        self.facts.append(
            {
                "kind": kind,
                "code": code,
                "nodes": [key_str(k) for k in keys],
                "sources": [s.as_dict() for s in sources],
                "detail": detail or {},
            }
        )

    def has_node(self, key: NodeKey) -> bool:
        return key in self.nodes

    def find(self, ident: str) -> list[Node]:
        return [n for k, n in sorted(self.nodes.items()) if n.id == ident]

    # ---- analysis ------------------------------------------------------
    def finalize(self) -> None:
        """Derive contradictions and coverage gaps from the loaded rows."""
        # over-consumption of a lot
        consumed: dict[NodeKey, list[Edge]] = defaultdict(list)
        for edge in self.edges:
            if edge.relation in ("consumed", "split") and edge.src[1] == "lot":
                consumed[edge.src].append(edge)
        for key, edges in consumed.items():
            node = self.nodes.get(key)
            if node is None:
                continue
            have = _num(node.attrs.get("quantity"))
            unit = str(node.attrs.get("unit", "")).strip().lower()
            for edge in edges:
                if edge.unit and unit and edge.unit.strip().lower() != unit:
                    self.fact("contradiction", "unit_mismatch", [key, edge.dst], edge.sources,
                              detail={"lot_unit": unit, "row_unit": edge.unit})
            total = sum(e.quantity for e in edges if e.quantity is not None and (not unit or not e.unit or e.unit.strip().lower() == unit))
            if have is not None and total > have + 1e-9:
                srcs = [s for e in edges for s in e.sources] + list(node.sources)
                self.fact("contradiction", "over_consumption", [key] + [e.dst for e in edges], srcs,
                          detail={"lot_quantity": have, "consumed_total": total, "unit": unit})
        # multi-link: a shipment naming more than one package, a package naming more than one batch
        by_dst: dict[tuple[NodeKey, str], list[Edge]] = defaultdict(list)
        for edge in self.edges:
            if edge.relation in ("shipped", "packed") and edge.status == "known":
                by_dst[(edge.dst, edge.relation)].append(edge)
        for (dst, relation), edges in by_dst.items():
            if len({e.src for e in edges}) > 1:
                self.fact("contradiction", f"multiple_{relation}_links", [dst] + [e.src for e in edges],
                          [s for e in edges for s in e.sources], detail={"relation": relation, "count": len(edges)})
        # coverage gaps: stages with no downstream record at all
        outgoing = defaultdict(int)
        for edge in self.edges:
            if edge.status == "known":
                outgoing[edge.src] += 1
        for key, node in self.nodes.items():
            if node.kind == "batch" and not any(e.src == key and e.relation in ("packed", "consumed", "rework") for e in self.edges):
                self.fact("coverage_gap", "batch_without_package_or_consumer", [key], node.sources)
            if node.kind == "package" and not any(e.src == key and e.relation == "shipped" for e in self.edges):
                self.fact("coverage_gap", "package_without_shipment", [key], node.sources)
        # cycles among batches (rework loops)
        for cycle in self.cycles():
            self.fact("cycle", "batch_cycle", cycle, [], detail={"length": len(cycle)})

    def cycles(self) -> list[list[NodeKey]]:
        adj: dict[NodeKey, list[NodeKey]] = defaultdict(list)
        for edge in self.edges:
            if edge.status == "known" and edge.src[1] == "batch" and edge.dst[1] == "batch":
                adj[edge.src].append(edge.dst)
        found: list[list[NodeKey]] = []
        seen_cycles: set[tuple[NodeKey, ...]] = set()
        color: dict[NodeKey, int] = {}
        stack: list[NodeKey] = []

        def visit(node: NodeKey) -> None:
            color[node] = 1
            stack.append(node)
            for nxt in sorted(adj.get(node, [])):
                if color.get(nxt, 0) == 1:
                    cycle = stack[stack.index(nxt):]
                    canon = tuple(sorted(cycle))
                    if canon not in seen_cycles:
                        seen_cycles.add(canon)
                        found.append(list(cycle))
                elif color.get(nxt, 0) == 0:
                    visit(nxt)
            stack.pop()
            color[node] = 2

        for node in sorted(adj):
            if color.get(node, 0) == 0:
                visit(node)
        return found

    def facts_for(self, keys: Iterable[NodeKey]) -> list[dict[str, Any]]:
        wanted = {key_str(k) for k in keys}
        return [f for f in self.facts if any(n in wanted for n in f["nodes"])]

    def impact(self, start: NodeKey, direction: str = "forward", assumptions: Iterable[str] = ()) -> dict[str, Any]:
        if direction not in ("forward", "backward"):
            raise ValueError("direction is forward or backward")
        if start not in self.nodes:
            return {
                "schema": SCHEMA,
                "query": {"start": key_str(start), "direction": direction, "assumptions": sorted(assumptions)},
                "start_found": False,
                "affected": [],
                "unresolved": [{"code": "start_not_in_records", "node": key_str(start)}],
                "coverage_gaps": [],
                "contradictions": [],
                "cycles": [],
                "note": "the start node is not in the imported records; check the namespace and kind with find",
            }
        chosen = sorted(set(assumptions))
        unknown = [a for a in chosen if a not in ASSUMPTIONS]
        if unknown:
            raise ValueError("no such assumption: " + ", ".join(unknown) + "; known: " + ", ".join(sorted(ASSUMPTIONS)))
        extra: list[Edge] = []
        for name in chosen:
            extra.extend(ASSUMPTIONS[name]["fn"](self))
        all_edges = list(self.edges) + extra

        def neighbours(edges: list[Edge]) -> dict[NodeKey, list[Edge]]:
            table: dict[NodeKey, list[Edge]] = defaultdict(list)
            for e in edges:
                if direction == "forward":
                    table[e.src].append(e)
                else:
                    table[e.dst].append(e)
            return table

        def other(e: Edge) -> NodeKey:
            return e.dst if direction == "forward" else e.src

        def bfs(edges: list[Edge]) -> dict[NodeKey, list[Edge]]:
            table = neighbours(edges)
            paths: dict[NodeKey, list[Edge]] = {start: []}
            queue = deque([start])
            while queue:
                cur = queue.popleft()
                for e in sorted(table.get(cur, []), key=lambda x: (key_str(other(x)), x.relation, x.status)):
                    nxt = other(e)
                    if nxt not in paths:
                        paths[nxt] = paths[cur] + [e]
                        queue.append(nxt)
            return paths

        known_paths = bfs([e for e in all_edges if e.status == "known"])
        all_paths = bfs(all_edges)
        affected: list[dict[str, Any]] = []
        for key in sorted(all_paths):
            if key == start:
                continue
            status = STATUS_KNOWN if key in known_paths else STATUS_POTENTIAL
            path = known_paths.get(key) or all_paths[key]
            node = self.nodes[key]
            affected.append(
                {
                    "key": key_str(key),
                    "namespace": key[0],
                    "kind": key[1],
                    "id": key[2],
                    "status": status,
                    "hops": len(path),
                    "attrs": dict(node.attrs),
                    "path": [e.as_dict() for e in path],
                    "assumptions_on_path": sorted({e.assumption for e in path if e.assumption}),
                }
            )
        reached = {start} | set(all_paths)
        facts = self.facts_for(reached)
        unresolved = [f for f in facts if f["kind"] == "unresolved"]
        gaps = [f for f in facts if f["kind"] == "coverage_gap"]
        contradictions = [f for f in facts if f["kind"] == "contradiction"]
        cycles = [f for f in facts if f["kind"] == "cycle"]
        return {
            "schema": SCHEMA,
            "query": {"start": key_str(start), "direction": direction, "assumptions": chosen},
            "start_found": True,
            "start": self.nodes[start].as_dict(),
            "affected": affected,
            "counts": {
                STATUS_KNOWN: sum(1 for a in affected if a["status"] == STATUS_KNOWN),
                STATUS_POTENTIAL: sum(1 for a in affected if a["status"] == STATUS_POTENTIAL),
                "unresolved": len(unresolved),
                "coverage_gaps": len(gaps),
                "contradictions": len(contradictions),
            },
            "unresolved": unresolved,
            "coverage_gaps": gaps,
            "contradictions": contradictions,
            "cycles": cycles,
            "note": (
                "KNOWN_AFFECTED has a documented row path; POTENTIALLY_AFFECTED needs the named assumption; "
                "a coverage gap means the records stop there, not that nothing happened after it."
            ),
        }

    def summary(self) -> dict[str, Any]:
        by_kind: dict[str, int] = defaultdict(int)
        for node in self.nodes.values():
            by_kind[node.kind] += 1
        by_rel: dict[str, int] = defaultdict(int)
        for edge in self.edges:
            by_rel[edge.relation] += 1
        by_fact: dict[str, int] = defaultdict(int)
        for f in self.facts:
            by_fact[f["kind"] + ":" + f["code"]] += 1
        return {
            "versions": list(self.versions),
            "nodes": dict(sorted(by_kind.items())),
            "edges": dict(sorted(by_rel.items())),
            "facts": dict(sorted(by_fact.items())),
            "namespaces": sorted({n.namespace for n in self.nodes.values()}),
        }


# ---------------------------------------------------------------------------
# Loading rows into a graph
# ---------------------------------------------------------------------------


def _read_csv(text: str) -> list[dict[str, str]]:
    reader = csv.DictReader(io.StringIO(text))
    rows = []
    for row in reader:
        rows.append({(k or "").strip(): (v or "").strip() for k, v in row.items() if k is not None})
    return rows


def load_rows(graph: Graph, version: str, name: str, text: str) -> int:
    """Load one export file's rows into the graph. Returns the row count."""
    if name not in FILES:
        return 0
    rows = _read_csv(text)
    for index, row in enumerate(rows, start=2):  # line 1 is the header
        src = Source(version, name, index)
        graph.rows[f"{version}:{name}:{index}"] = dict(row)
        ns = row.get("namespace", "")
        if name == "lots.csv":
            graph._node((ns, "lot", row["lot_id"]), src, supplier=row.get("supplier"), material=row.get("material"),
                        quantity=_num(row.get("quantity")), unit=row.get("unit"), received_at=row.get("received_at"))
        elif name == "batches.csv":
            graph._node((ns, "batch", row["batch_id"]), src, product=row.get("product"), formula_id=row.get("formula_id"),
                        formula_version=row.get("formula_version"), produced_at=row.get("produced_at"),
                        quantity=_num(row.get("quantity")), unit=row.get("unit"))
        elif name == "packages.csv":
            pkg = graph._node((ns, "package", row["package_id"]), src, product=row.get("product"),
                              quantity=_num(row.get("quantity")), unit=row.get("unit"), packed_at=row.get("packed_at"))
            batch_id = row.get("batch_id", "")
            if batch_id:
                bkey = (ns, "batch", batch_id)
                if graph.has_node(bkey):
                    graph._edge(bkey, pkg.key, "packed", src, row.get("quantity"), row.get("unit", ""))
                else:
                    graph.fact("unresolved", "package_batch_not_in_records", [pkg.key], [src], detail={"batch_ref": key_str(bkey)})
            else:
                graph.fact("unresolved", "package_without_batch_link", [pkg.key], [src])
        elif name == "shipments.csv":
            shp = graph._node((ns, "shipment", row["shipment_id"]), src, customer=row.get("customer"),
                              quantity=_num(row.get("quantity")), unit=row.get("unit"), shipped_at=row.get("shipped_at"))
            pkey = (ns, "package", row.get("package_id", ""))
            if graph.has_node(pkey):
                graph._edge(pkey, shp.key, "shipped", src, row.get("quantity"), row.get("unit", ""))
            else:
                graph.fact("unresolved", "shipment_package_not_in_records", [shp.key], [src], detail={"package_ref": key_str(pkey)})
        elif name == "splits.csv":
            parent = (ns, "lot", row["lot_id"])
            child = (ns, "lot", row["child_lot_id"])
            if not graph.has_node(parent):
                graph.fact("unresolved", "split_parent_not_in_records", [child], [src], detail={"lot_ref": key_str(parent)})
                continue
            if not graph.has_node(child):
                graph.fact("unresolved", "split_child_not_in_records", [parent], [src], detail={"lot_ref": key_str(child)})
                continue
            graph._edge(parent, child, "split", src, row.get("quantity"), row.get("unit", ""))
        elif name == "consumption.csv":
            bkey = (ns, "batch", row["batch_id"])
            ikind = row.get("input_kind", "lot").strip().lower() or "lot"
            ikey = (row.get("input_namespace", ns) or ns, ikind if ikind in KINDS else "lot", row["input_id"])
            if not graph.has_node(bkey):
                graph.fact("unresolved", "consumption_batch_not_in_records", [ikey], [src], detail={"batch_ref": key_str(bkey)})
                continue
            if not graph.has_node(ikey):
                graph.fact("unresolved", "consumed_input_not_in_records", [bkey], [src], detail={"input_ref": key_str(ikey)})
                continue
            graph._edge(ikey, bkey, "consumed", src, row.get("quantity"), row.get("unit", ""))
        elif name == "rework.csv":
            a = (ns, "batch", row["from_batch_id"])
            b = (ns, "batch", row["into_batch_id"])
            missing = [k for k in (a, b) if not graph.has_node(k)]
            if missing:
                graph.fact("unresolved", "rework_batch_not_in_records", [k for k in (a, b) if graph.has_node(k)], [src],
                           detail={"missing": [key_str(k) for k in missing], "rework_id": row.get("rework_id")})
                continue
            graph._edge(a, b, "rework", src, row.get("quantity"), row.get("unit", ""))
    return len(rows)


LOAD_ORDER = ("lots.csv", "batches.csv", "splits.csv", "consumption.csv", "rework.csv", "packages.csv", "shipments.csv")


# ---------------------------------------------------------------------------
# Workspace: imports registry, copied source files, annotations
# ---------------------------------------------------------------------------


class Workspace:
    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.imports_dir = self.root / "imports"
        self.registry_path = self.root / "imports.json"
        self.annotations_path = self.root / "annotations.jsonl"
        self.root.mkdir(parents=True, exist_ok=True)
        self.imports_dir.mkdir(parents=True, exist_ok=True)

    # ---- imports -------------------------------------------------------
    def imports(self) -> list[dict[str, Any]]:
        if not self.registry_path.is_file():
            return []
        return json.loads(self.registry_path.read_text(encoding="utf-8"))

    def _save_imports(self, items: list[dict[str, Any]]) -> None:
        self.registry_path.write_text(json.dumps(items, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")

    def import_dir(self, source: Path | str, label: str = "") -> dict[str, Any]:
        source = Path(source)
        files: list[dict[str, Any]] = []
        for name in sorted(FILES):
            path = source / name
            if path.is_file():
                data = path.read_bytes()
                files.append({"name": name, "sha256": sha256_bytes(data), "bytes": len(data)})
        if not files:
            raise ValueError(f"no import files found in {source}; expected some of: {', '.join(sorted(FILES))}")
        version = sha256_bytes("\n".join(f"{f['name']}:{f['sha256']}" for f in files).encode("utf-8"))[:16]
        items = self.imports()
        existing = next((i for i in items if i["version"] == version), None)
        if existing is not None:
            existing.setdefault("seen", []).append(utc_now())
            self._save_imports(items)
            return {"version": version, "new": False, "files": files, "label": existing.get("label", "")}
        target = self.imports_dir / version
        target.mkdir(parents=True, exist_ok=True)
        rows = {}
        for f in files:
            shutil.copyfile(source / f["name"], target / f["name"])
            rows[f["name"]] = max(0, len(_read_csv((source / f["name"]).read_text(encoding="utf-8-sig"))))
        record = {
            "version": version,
            "label": label,
            "imported_at": utc_now(),
            "source_dir": str(source),
            "files": files,
            "rows": rows,
            "seen": [],
        }
        items.append(record)
        self._save_imports(items)
        return {"version": version, "new": True, "files": files, "label": label, "rows": rows}

    def _file_text(self, version: str, name: str) -> str | None:
        path = self.imports_dir / version / name
        if not path.is_file():
            return None
        return path.read_text(encoding="utf-8-sig")

    def graph(self, versions: list[str] | None = None) -> Graph:
        items = self.imports()
        if not items:
            raise ValueError("workspace has no imports yet")
        if versions is None:
            versions = [items[-1]["version"]]  # latest import; ask for more explicitly
        graph = Graph()
        graph.versions = list(versions)
        for version in versions:
            for name in LOAD_ORDER:
                text = self._file_text(version, name)
                if text is not None:
                    load_rows(graph, version, name, text)
        graph.finalize()
        return graph

    def compare(self, version_a: str, version_b: str) -> dict[str, Any]:
        def rows_of(version: str) -> dict[str, set[str]]:
            out: dict[str, set[str]] = {}
            for name in sorted(FILES):
                text = self._file_text(version, name)
                out[name] = set() if text is None else {json.dumps(r, sort_keys=True) for r in _read_csv(text)}
            return out

        a, b = rows_of(version_a), rows_of(version_b)
        result = {"a": version_a, "b": version_b, "files": {}}
        for name in sorted(FILES):
            only_a = sorted(a[name] - b[name])
            only_b = sorted(b[name] - a[name])
            if only_a or only_b or a[name] or b[name]:
                result["files"][name] = {
                    "only_in_a": [json.loads(r) for r in only_a],
                    "only_in_b": [json.loads(r) for r in only_b],
                    "same": len(a[name] & b[name]),
                }
        return result

    # ---- annotations ---------------------------------------------------
    def annotate(self, target: str, text: str, investigator: str = "", supersedes: str | None = None) -> dict[str, Any]:
        if not str(text).strip():
            raise ValueError("annotation text is empty")
        existing = self.annotations()
        if supersedes and not any(a["id"] == supersedes for a in existing):
            raise ValueError(f"cannot supersede unknown annotation {supersedes}")
        revision = 1 + sum(1 for a in existing if a["target"] == target)
        record = {
            "id": sha256_bytes(f"{target}|{revision}|{text}|{utc_now()}".encode("utf-8"))[:12],
            "target": target,
            "revision": revision,
            "text": str(text),
            "investigator": str(investigator or ""),
            "supersedes": supersedes,
            "at": utc_now(),
        }
        with self.annotations_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
        return record

    def annotations(self, target: str | None = None) -> list[dict[str, Any]]:
        if not self.annotations_path.is_file():
            return []
        out = []
        for line in self.annotations_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                if target is None or rec["target"] == target:
                    out.append(rec)
        superseded = {a["supersedes"] for a in out if a.get("supersedes")}
        for a in out:
            a["current"] = a["id"] not in superseded
        return out


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def node_detail(kind: str, attrs: dict[str, Any]) -> str:
    """The one attribute a reader wants next to the id: what a lot is, what a batch or
    package holds, who a shipment went to. Display only; the attrs stay in the report."""
    if kind == "lot":
        return " ".join(str(v) for v in (attrs.get("material"), attrs.get("supplier")) if v)
    if kind in ("batch", "package"):
        return str(attrs.get("product") or "")
    if kind == "shipment":
        return str(attrs.get("customer") or "")
    return ""


def path_summary(path: list[dict[str, Any]]) -> list[str]:
    """One line per hop: from -relation-> to (file:line@version); `*` marks an edge that exists only
    under a named assumption; an edge with no source row prints `no row`. Same form as the viewer."""
    out = []
    for e in path:
        rows = ", ".join(f"{s['file']}:{s['line']}@{str(s['version'])[:8]}" for s in e.get("sources", []))
        flag = "*" if e.get("status") == "potential" else ""
        out.append(f"{e['from']} -{e['relation']}{flag}-> {e['to']} ({rows or 'no row'})")
    return out


def build_report(workspace: Workspace, graph: Graph, impact: dict[str, Any]) -> dict[str, Any]:
    keys = [impact["query"]["start"]] + [a["key"] for a in impact.get("affected", [])]
    notes = [a for a in workspace.annotations() if a["target"] in set(keys)]
    report = {
        "schema": SCHEMA + "/report",
        "generated_at": utc_now(),
        "imports": [{k: v for k, v in i.items() if k in ("version", "label", "imported_at", "files", "rows")} for i in workspace.imports() if i["version"] in graph.versions],
        "impact": impact,
        "annotations": notes,
    }
    # The hash covers the answer and the bytes it came from (schema, import version/label/files/rows,
    # impact, annotations), not the clocks: two workspaces that import the same export at different
    # times and ask the same question get the same content_sha256.
    hashed = {k: v for k, v in report.items() if k != "generated_at"}
    hashed["imports"] = [{k: v for k, v in i.items() if k != "imported_at"} for i in report["imports"]]
    canonical = json.dumps(hashed, sort_keys=True, ensure_ascii=False)
    report["content_sha256"] = sha256_bytes(canonical.encode("utf-8"))
    return report


def render_markdown(report: dict[str, Any]) -> str:
    imp = report["impact"]
    q = imp["query"]
    lines = [
        f"# LotLens impact report — {q['start']} ({q['direction']})",
        "",
        f"Generated {report['generated_at']} · content sha256 `{report['content_sha256']}`",
        f"Imports: " + ", ".join(f"`{i['version']}`" + (f" ({i['label']})" if i.get("label") else "") for i in report["imports"]),
        f"Assumptions in force: " + (", ".join(q["assumptions"]) if q["assumptions"] else "none"),
        "",
    ]
    if not imp.get("start_found"):
        lines.append("The start node is not in the imported records.")
        return "\n".join(lines) + "\n"
    counts = imp["counts"]
    lines.append(
        f"{counts[STATUS_KNOWN]} known affected · {counts[STATUS_POTENTIAL]} potentially affected · "
        f"{counts['unresolved']} unresolved · {counts['coverage_gaps']} coverage gaps · {counts['contradictions']} contradictions"
    )
    lines += ["", "| status | item | kind | what | hops | via | evidence |", "| --- | --- | --- | --- | --- | --- | --- |"]
    for a in imp["affected"]:
        via = " → ".join(f"{e['relation']}{'*' if e['status'] == 'potential' else ''}" for e in a["path"])
        ev = "; ".join(f"{s['file']}:{s['line']}" for e in a["path"] for s in e["sources"])
        lines.append(f"| {a['status']} | `{a['key']}` | {a['kind']} | {node_detail(a['kind'], a.get('attrs', {}))} | {a['hops']} | {via} | {ev} |")
    lines.append("")
    lines.append("`*` marks an edge that exists only under a named assumption.")
    for title, items in (("Unresolved", imp["unresolved"]), ("Coverage gaps", imp["coverage_gaps"]), ("Contradictions", imp["contradictions"]), ("Cycles", imp["cycles"])):
        lines += ["", f"## {title}", ""]
        if not items:
            lines.append("none recorded")
        for f in items:
            srcs = "; ".join(f"{s['file']}:{s['line']}" for s in f["sources"]) or "no row"
            lines.append(f"- `{f['code']}` on {', '.join('`' + n + '`' for n in f['nodes'])} — {json.dumps(f['detail'], sort_keys=True)} — {srcs}")
    lines += ["", "## Investigator annotations", ""]
    if not report["annotations"]:
        lines.append("none")
    for a in report["annotations"]:
        flag = "current" if a.get("current") else "superseded"
        lines.append(f"- `{a['target']}` r{a['revision']} ({flag}, {a['investigator'] or 'unsigned'}, {a['at']}): {a['text']}")
    lines += ["", imp["note"], ""]
    return "\n".join(lines)
