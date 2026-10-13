"""Deterministic relationship graph over an existing citation-resolver trace.

This is a presentation/inspection layer only. It never upgrades citation
resolution into source authenticity, verified findings, or recommendation
approval. The complete input trace is retained inside every graph artifact.
"""
from __future__ import annotations

import copy
import html
import json
from collections import Counter, defaultdict
from typing import Any, Iterable

GRAPH_SCHEMA = "uiowa.source-relationship-graph.v1"


class GraphError(ValueError):
    pass


def _text(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value:
        raise GraphError(f"{where}: non-empty text required")
    return value


def _id(prefix: str, raw: str) -> str:
    return f"{prefix}:{raw}"


def _source_key(citation: dict[str, Any]) -> tuple[str, str, str]:
    return (
        _text(citation.get("source_id"), "citation.source_id"),
        _text(citation.get("version"), "citation.version"),
        _text(citation.get("sha256"), "citation.sha256"),
    )


def build_graph(
    trace: dict[str, Any],
    contradictions: Iterable[tuple[str, str]] = (),
) -> dict[str, Any]:
    """Build a lossless graph projection from a citation-resolver trace."""
    if not isinstance(trace, dict) or not isinstance(trace.get("findings"), list):
        raise GraphError("trace.findings must be an array")
    if not isinstance(trace.get("recommendations"), list):
        raise GraphError("trace.recommendations must be an array")

    nodes: dict[str, dict[str, Any]] = {}
    edges: dict[tuple[str, str, str], dict[str, Any]] = {}
    findings: dict[str, dict[str, Any]] = {}
    citation_to_source: defaultdict[tuple[str, str, str], list[str]] = defaultdict(list)

    def add_node(node: dict[str, Any]) -> None:
        node_id = _text(node.get("id"), "node.id")
        existing = nodes.get(node_id)
        if existing is not None and existing != node:
            raise GraphError(f"conflicting node identity: {node_id}")
        nodes[node_id] = node

    def add_edge(source: str, target: str, relation: str, **extra: Any) -> None:
        if source not in nodes or target not in nodes:
            raise GraphError(f"edge endpoint missing: {source} -> {target}")
        key = (source, target, relation)
        row = {"source": source, "target": target, "relation": relation, **extra}
        existing = edges.get(key)
        if existing is not None and existing != row:
            raise GraphError(f"conflicting edge identity: {key}")
        edges[key] = row

    for finding in trace["findings"]:
        if not isinstance(finding, dict):
            raise GraphError("finding must be object")
        fid = _text(finding.get("finding_id"), "finding.finding_id")
        if fid in findings:
            raise GraphError(f"duplicate finding id: {fid}")
        findings[fid] = finding
        finding_id = _id("finding", fid)
        add_node({
            "id": finding_id,
            "kind": "finding",
            "finding_id": fid,
            "finding_kind": finding.get("kind"),
            "group": finding.get("group"),
            "dimension": finding.get("dimension"),
            "trace_status": finding.get("trace_status"),
            "label": finding.get("statement") or fid,
            "statement": finding.get("statement"),
            "limits": finding.get("limits"),
        })

        citations = finding.get("citations")
        if not isinstance(citations, list) or not citations:
            raise GraphError(f"finding {fid} has no citation rows")
        seen_cids: set[str] = set()
        for ordinal, citation in enumerate(citations, 1):
            if not isinstance(citation, dict):
                raise GraphError("citation must be object")
            cid = _text(citation.get("citation_id") or f"{fid}-C{ordinal}", "citation.citation_id")
            if cid in seen_cids:
                raise GraphError(f"duplicate citation id inside {fid}: {cid}")
            seen_cids.add(cid)
            observation_id = _id("observation", cid)
            source_key = _source_key(citation)
            source_node_id = _id("source", "|".join(source_key))
            diagnostics = list(citation.get("diagnostics") or [])
            citation_payload = citation.get("citation") if isinstance(citation.get("citation"), dict) else None
            label = (citation_payload or {}).get("quote") or citation.get("requested_quote") or cid

            add_node({
                "id": observation_id,
                "kind": "observation",
                "citation_id": cid,
                "label": label,
                "resolved": citation.get("resolved") is True,
                "bound_to_compiler_source": citation.get("bound_to_compiler_source") is True,
                "source_id": source_key[0],
                "version": source_key[1],
                "sha256": source_key[2],
                "requested_locator": citation.get("requested_locator"),
                "requested_quote": citation.get("requested_quote"),
                "diagnostics": diagnostics,
                "citation": copy.deepcopy(citation_payload),
            })
            add_edge(
                finding_id,
                observation_id,
                "supported_by" if citation.get("resolved") else "requests_evidence",
            )

            if source_node_id not in nodes:
                add_node({
                    "id": source_node_id,
                    "kind": "source",
                    "source_id": source_key[0],
                    "version": source_key[1],
                    "sha256": source_key[2],
                    "label": f"{source_key[0]} · {source_key[1]}",
                    "resolved_by_any": False,
                    "source_paths": [],
                    "locators": [],
                })
            src = nodes[source_node_id]
            if citation.get("resolved") is True:
                src["resolved_by_any"] = True
            if citation_payload:
                path = citation_payload.get("source_path")
                locator = citation_payload.get("locator")
                if path and path not in src["source_paths"]:
                    src["source_paths"].append(path)
                if locator and locator not in src["locators"]:
                    src["locators"].append(locator)
            citation_to_source[source_key].append(observation_id)
            add_edge(
                observation_id,
                source_node_id,
                "resolves_to" if citation.get("resolved") else "requests_source",
                diagnostics=diagnostics,
            )

    recommendation_ids: set[str] = set()
    for rec in trace["recommendations"]:
        if not isinstance(rec, dict):
            raise GraphError("recommendation must be object")
        rid = _text(rec.get("recommendation_id"), "recommendation.recommendation_id")
        if rid in recommendation_ids:
            raise GraphError(f"duplicate recommendation id: {rid}")
        recommendation_ids.add(rid)
        rec_node_id = _id("recommendation", rid)
        add_node({
            "id": rec_node_id,
            "kind": "recommendation",
            "recommendation_id": rid,
            "label": rec.get("action") or rid,
            "action": rec.get("action"),
            "rationale": rec.get("rationale"),
            "phase": rec.get("phase"),
            "owner_role": rec.get("owner_role"),
            "effort": rec.get("effort"),
            "outcome_measure": rec.get("outcome_measure"),
        })
        links = rec.get("finding_ids")
        if not isinstance(links, list) or not links:
            raise GraphError(f"recommendation {rid} has no finding links")
        for fid in links:
            if fid not in findings:
                raise GraphError(f"recommendation {rid} references unknown finding {fid}")
            add_edge(rec_node_id, _id("finding", fid), "addresses")

    contradiction_pairs: set[tuple[str, str]] = set()
    for left, right in contradictions:
        left = _text(left, "contradiction.left")
        right = _text(right, "contradiction.right")
        if left == right:
            raise GraphError("self-contradiction edge is invalid")
        if left not in findings or right not in findings:
            raise GraphError(f"contradiction references unknown finding: {left}, {right}")
        pair = tuple(sorted((left, right)))
        if pair in contradiction_pairs:
            continue
        contradiction_pairs.add(pair)
        add_edge(_id("finding", pair[0]), _id("finding", pair[1]), "contradicts", bidirectional=True)

    for node in nodes.values():
        if node["kind"] == "source":
            node["source_paths"].sort()
            node["locators"].sort()

    shared_sources = sum(1 for refs in citation_to_source.values() if len(refs) > 1)
    unresolved = sum(
        1 for n in nodes.values()
        if n["kind"] == "observation" and not n["resolved"]
    )
    counts = Counter(n["kind"] for n in nodes.values())
    counts.update({
        "edges": len(edges),
        "shared_sources": shared_sources,
        "unresolved_observations": unresolved,
        "contradictions": len(contradiction_pairs),
    })
    return {
        "schema": GRAPH_SCHEMA,
        "label": trace.get("label"),
        "counts": dict(sorted(counts.items())),
        "nodes": sorted(nodes.values(), key=lambda n: n["id"]),
        "edges": sorted(edges.values(), key=lambda e: (e["source"], e["target"], e["relation"])),
        "trace": copy.deepcopy(trace),
        "limits": (
            "This graph is a lossless navigation projection of a citation trace. "
            "A resolved edge proves only the resolver's byte/locator correspondence; "
            "it does not establish source authenticity, verified findings, maturity, "
            "recommendation approval, or completeness of the evidence universe."
        ),
    }


def render_html(graph: dict[str, Any]) -> str:
    """Return a single-file, offline graph with a clickable inspector."""
    if not isinstance(graph, dict) or graph.get("schema") != GRAPH_SCHEMA:
        raise GraphError("source relationship graph required")
    payload = json.dumps(graph, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    payload = payload.replace("</", "<\\/")
    title = "UIOWA-104 · Finding-to-source relationship graph"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<style>
:root{{font-family:ui-sans-serif,system-ui,-apple-system,Segoe UI,sans-serif;color:#17202a;background:#f5f7fa}}
body{{margin:0}} header{{padding:20px 24px;background:white;border-bottom:1px solid #d9e0e7}} h1{{font-size:20px;margin:0 0 6px}}
main{{display:grid;grid-template-columns:minmax(0,2fr) minmax(280px,1fr);gap:16px;padding:16px}} .panel{{background:white;border:1px solid #d9e0e7;border-radius:10px;overflow:hidden}}
#graph{{width:100%;height:700px;display:block}} .edge{{stroke:#9ba8b4;stroke-width:1.5}} .edge.contradicts{{stroke:#9c3b3b;stroke-dasharray:6 4}} .edge.requests_source,.edge.requests_evidence{{stroke:#b06b00;stroke-dasharray:4 3}}
.node rect{{stroke:#607080;stroke-width:1;rx:7}} .node text{{font-size:11px;pointer-events:none}} .recommendation rect{{fill:#edf6ff}} .finding rect{{fill:#f4efff}} .observation rect{{fill:#fff8e5}} .source rect{{fill:#edf9f1}} .node.unresolved rect{{stroke:#b06b00;stroke-width:2}}
#details{{padding:16px;white-space:pre-wrap;overflow:auto;max-height:668px;font:12px/1.45 ui-monospace,SFMono-Regular,Consolas,monospace}} .legend{{display:flex;gap:14px;flex-wrap:wrap;font-size:12px;color:#53606d}}
footer{{padding:0 16px 20px;color:#53606d;font-size:12px}} @media(max-width:900px){{main{{grid-template-columns:1fr}} #graph{{height:760px}}}}
</style></head><body>
<header><h1>{html.escape(title)}</h1><div class="legend">recommendation → finding → observation/citation → exact source identity</div></header>
<main><section class="panel"><svg id="graph" role="img" aria-label="Relationship graph"></svg></section><aside class="panel"><div id="details">Select a node or edge. The full resolver trace remains embedded in this file.</div></aside></main>
<footer>{html.escape(graph.get("limits") or "")}</footer>
<script type="application/json" id="graph-data">{payload}</script>
<script>
(()=>{{
const data=JSON.parse(document.getElementById("graph-data").textContent); const svg=document.getElementById("graph"); const details=document.getElementById("details");
const ns="http://www.w3.org/2000/svg"; const order={{recommendation:0,finding:1,observation:2,source:3}}, xs=[70,350,640,930]; const groups=[[],[],[],[]];
data.nodes.forEach(n=>groups[order[n.kind]].push(n)); groups.forEach(g=>g.sort((a,b)=>a.id.localeCompare(b.id))); const pos=new Map();
groups.forEach((g,layer)=>g.forEach((n,i)=>pos.set(n.id,[xs[layer],55+i*Math.max(62,610/Math.max(1,g.length))])));
function el(name,attrs={{}}){{const x=document.createElementNS(ns,name); Object.entries(attrs).forEach(([k,v])=>x.setAttribute(k,String(v))); return x}}
function show(obj){{details.textContent=JSON.stringify(obj,null,2)}}
data.edges.forEach(e=>{{const a=pos.get(e.source),b=pos.get(e.target); if(!a||!b)return; const line=el("line",{{x1:a[0]+120,y1:a[1]+18,x2:b[0],y2:b[1]+18,class:"edge "+e.relation,tabindex:0}}); line.addEventListener("click",()=>show(e)); svg.appendChild(line)}});
data.nodes.forEach(n=>{{const [x,y]=pos.get(n.id); const g=el("g",{{class:"node "+n.kind+(n.kind==="observation"&&!n.resolved?" unresolved":""),tabindex:0,role:"button"}}); const rect=el("rect",{{x,y,width:220,height:38}}); const text=el("text",{{x:x+8,y:y+23}}); const label=String(n.label||n.id); text.textContent=label.length>31?label.slice(0,30)+"…":label; g.append(rect,text); g.addEventListener("click",()=>show(n)); svg.appendChild(g)}});
svg.setAttribute("viewBox","0 0 1180 700");
}})();
</script></body></html>"""
