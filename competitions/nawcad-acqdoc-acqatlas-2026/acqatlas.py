#!/usr/bin/env python3
"""AcqAtlas: deterministic offline procurement-document clustering and vehicle recommendation.

Standard-library-only baseline designed for reproducible IL4-style offline execution.
It intentionally makes no external API/model calls and is deterministic for identical bytes.
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
import hashlib
import html
import json
import math
from pathlib import Path
import re
import resource
import statistics
import time
from collections import Counter, defaultdict
from typing import Iterable, Sequence

SCHEMA = "acqatlas-analysis-v1"
TOKEN_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9_-]{1,}|\d+(?:\.\d+)?")
STOP = frozenset({
    "a","an","and","are","as","at","be","by","for","from","has","have","in","is","it","of","on","or",
    "that","the","this","to","will","with","shall","must","may","including","include","includes","provide",
    "provided","services","service","support","contractor","government","requirement","requirements","work",
})

@dataclass(frozen=True)
class Document:
    doc_id: str
    title: str
    text: str
    vehicle: str | None = None
    acceptable_vehicles: tuple[str, ...] = ()

    @classmethod
    def from_mapping(cls, row: dict) -> "Document":
        doc_id = str(row.get("doc_id", "")).strip()
        title = str(row.get("title", "")).strip()
        text = str(row.get("text", "")).strip()
        if not doc_id:
            raise ValueError("document missing doc_id")
        if not text:
            raise ValueError(f"document {doc_id!r} missing text")
        vehicle_raw = row.get("vehicle")
        vehicle = str(vehicle_raw).strip() if vehicle_raw not in (None, "") else None
        acceptable = row.get("acceptable_vehicles", ())
        if isinstance(acceptable, str):
            acceptable = [x.strip() for x in acceptable.split("|") if x.strip()]
        acceptable_tuple = tuple(sorted({str(x).strip() for x in acceptable if str(x).strip()}))
        return cls(doc_id=doc_id, title=title, text=text, vehicle=vehicle, acceptable_vehicles=acceptable_tuple)


def canonical_json_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def document_manifest(docs: Sequence[Document]) -> list[dict]:
    """Canonical, order-independent manifest used to bind benchmark evidence."""
    return [
        {
            "doc_id": d.doc_id,
            "title_sha256": sha256_hex(d.title.encode("utf-8")),
            "text_sha256": sha256_hex(d.text.encode("utf-8")),
            "vehicle": d.vehicle,
            "acceptable_vehicles": list(d.acceptable_vehicles),
        }
        for d in sorted(docs, key=lambda item: item.doc_id)
    ]


def document_manifest_sha256(docs: Sequence[Document]) -> str:
    return sha256_hex(canonical_json_bytes(document_manifest(docs)))


def tokenize(text: str) -> list[str]:
    out: list[str] = []
    for raw in TOKEN_RE.findall(text.lower()):
        token = "<num>" if raw[0].isdigit() else raw.replace("_", "-")
        if token not in STOP and len(token) > 1:
            out.append(token)
    return out


def features(text: str) -> list[str]:
    toks = tokenize(text)
    feats = list(toks)
    # Bigrams capture requirement phrases such as "flight line" and "zero trust".
    feats.extend(f"{a}::{b}" for a, b in zip(toks, toks[1:]))
    return feats


def sparse_tfidf(docs: Sequence[Document]) -> tuple[dict[str, dict[str, float]], dict[str, float]]:
    if not docs:
        raise ValueError("at least one document required")
    term_counts: dict[str, Counter[str]] = {}
    df: Counter[str] = Counter()
    for doc in docs:
        counts = Counter(features(doc.title + "\n" + doc.text))
        term_counts[doc.doc_id] = counts
        df.update(counts.keys())
    n = len(docs)
    idf = {term: math.log((1 + n) / (1 + freq)) + 1.0 for term, freq in sorted(df.items())}
    vectors: dict[str, dict[str, float]] = {}
    for doc in docs:
        weighted: dict[str, float] = {}
        for term, count in term_counts[doc.doc_id].items():
            weighted[term] = (1.0 + math.log(count)) * idf[term]
        norm = math.sqrt(sum(v * v for v in weighted.values())) or 1.0
        vectors[doc.doc_id] = {term: value / norm for term, value in sorted(weighted.items())}
    return vectors, idf


def cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(value * b.get(term, 0.0) for term, value in a.items())


def weighted_jaccard(a: Counter[str], b: Counter[str]) -> float:
    keys = set(a) | set(b)
    if not keys:
        return 0.0
    numer = sum(min(a.get(k, 0), b.get(k, 0)) for k in keys)
    denom = sum(max(a.get(k, 0), b.get(k, 0)) for k in keys)
    return numer / denom if denom else 0.0


def pair_similarity(a: Document, b: Document, vectors: dict[str, dict[str, float]], token_counts: dict[str, Counter[str]]) -> float:
    lexical = cosine(vectors[a.doc_id], vectors[b.doc_id])
    overlap = weighted_jaccard(token_counts[a.doc_id], token_counts[b.doc_id])
    return (0.82 * lexical) + (0.18 * overlap)


class UnionFind:
    def __init__(self, ids: Iterable[str]) -> None:
        self.parent = {x: x for x in ids}

    def find(self, x: str) -> str:
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[x] != x:
            nxt = self.parent[x]
            self.parent[x] = root
            x = nxt
        return root

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        # Canonical root makes output independent of incidental iteration order.
        lo, hi = sorted((ra, rb))
        self.parent[hi] = lo


def build_similarity(docs: Sequence[Document]) -> tuple[dict[str, dict[str, float]], dict[tuple[str, str], float], dict[str, Counter[str]]]:
    vectors, _idf = sparse_tfidf(docs)
    token_counts = {d.doc_id: Counter(tokenize(d.title + "\n" + d.text)) for d in docs}
    sim: dict[tuple[str, str], float] = {}
    ordered = sorted(docs, key=lambda d: d.doc_id)
    for i, a in enumerate(ordered):
        for b in ordered[i + 1:]:
            sim[(a.doc_id, b.doc_id)] = pair_similarity(a, b, vectors, token_counts)
    return vectors, sim, token_counts


def lookup_similarity(a: str, b: str, sim: dict[tuple[str, str], float]) -> float:
    if a == b:
        return 1.0
    return sim.get(tuple(sorted((a, b))), 0.0)


def cluster_documents(docs: Sequence[Document], sim: dict[tuple[str, str], float], *, threshold: float = 0.18) -> list[dict]:
    uf = UnionFind(d.doc_id for d in docs)
    for (a, b), score in sorted(sim.items()):
        if score >= threshold:
            uf.union(a, b)
    groups: defaultdict[str, list[Document]] = defaultdict(list)
    for doc in sorted(docs, key=lambda d: d.doc_id):
        groups[uf.find(doc.doc_id)].append(doc)
    result: list[dict] = []
    for cluster_idx, (_root, members) in enumerate(sorted(groups.items(), key=lambda kv: min(d.doc_id for d in kv[1])), start=1):
        ids = [d.doc_id for d in members]
        pair_scores = [lookup_similarity(a, b, sim) for i, a in enumerate(ids) for b in ids[i + 1:]]
        terms = Counter()
        vehicles = Counter()
        for d in members:
            terms.update(tokenize(d.title + "\n" + d.text))
            if d.vehicle:
                vehicles[d.vehicle] += 1
        result.append({
            "cluster_id": f"C{cluster_idx:03d}",
            "members": ids,
            "size": len(ids),
            "cohesion_mean": round(statistics.fmean(pair_scores), 6) if pair_scores else 1.0,
            "top_terms": [t for t, _ in sorted(terms.items(), key=lambda kv: (-kv[1], kv[0]))[:12]],
            "vehicle_distribution": dict(sorted(vehicles.items())),
        })
    return result


def recommend_for(doc: Document, docs: Sequence[Document], vectors: dict[str, dict[str, float]], token_counts: dict[str, Counter[str]], *, top_k: int = 5, exclude_self: bool = True) -> list[dict]:
    neighbors: list[tuple[float, str, str]] = []
    for other in docs:
        if exclude_self and other.doc_id == doc.doc_id:
            continue
        if not other.vehicle:
            continue
        score = pair_similarity(doc, other, vectors, token_counts)
        if score > 0:
            neighbors.append((score, other.doc_id, other.vehicle))
    neighbors.sort(key=lambda x: (-x[0], x[1], x[2]))
    # Aggregate diverse evidence rather than allowing one copied document to dominate.
    by_vehicle: defaultdict[str, list[tuple[float, str]]] = defaultdict(list)
    for score, doc_id, vehicle in neighbors[:40]:
        by_vehicle[vehicle].append((score, doc_id))
    ranked: list[dict] = []
    for vehicle, evidence in by_vehicle.items():
        evidence = sorted(evidence, key=lambda x: (-x[0], x[1]))
        # Diminishing returns from duplicate neighbors; first three carry most weight.
        agg = sum((score * score) / (1.0 + 0.35 * idx) for idx, (score, _id) in enumerate(evidence[:8]))
        ranked.append({
            "vehicle": vehicle,
            "score": round(agg, 8),
            "evidence": [{"doc_id": did, "similarity": round(score, 6)} for score, did in evidence[:5]],
        })
    ranked.sort(key=lambda r: (-r["score"], r["vehicle"]))
    return ranked[:top_k]


def validate_leave_one_out(docs: Sequence[Document], *, top_k: int = 5) -> dict:
    labeled = [d for d in docs if d.vehicle]
    if len(labeled) < 2:
        raise ValueError("validation requires at least two labeled documents")
    hits1 = hitsk = 0
    rows = []
    for target in sorted(labeled, key=lambda d: d.doc_id):
        train_docs = [d for d in docs if d.doc_id != target.doc_id]
        # Query must be projected in the same feature space. Refit including target only
        # for IDF calculation, while excluding its label from recommendation evidence.
        vectors, _ = sparse_tfidf(docs)
        token_counts = {d.doc_id: Counter(tokenize(d.title + "\n" + d.text)) for d in docs}
        recs = recommend_for(target, train_docs, vectors, token_counts, top_k=top_k, exclude_self=False)
        predicted = [r["vehicle"] for r in recs]
        acceptable = set(target.acceptable_vehicles or ((target.vehicle,) if target.vehicle else ()))
        top1 = bool(predicted and predicted[0] in acceptable)
        topk_hit = any(p in acceptable for p in predicted)
        hits1 += int(top1)
        hitsk += int(topk_hit)
        rows.append({"doc_id": target.doc_id, "actual": target.vehicle, "acceptable": sorted(acceptable), "predicted": predicted, "top1_hit": top1, f"top{top_k}_hit": topk_hit})
    return {
        "labeled_documents": len(labeled),
        "top1_accuracy": round(hits1 / len(labeled), 6),
        f"top{top_k}_recall": round(hitsk / len(labeled), 6),
        "rows": rows,
    }


def analyze(docs: Sequence[Document], *, cluster_threshold: float = 0.18, top_k: int = 5) -> dict:
    ids = [d.doc_id for d in docs]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate doc_id")
    vectors, sim, token_counts = build_similarity(docs)
    clusters = cluster_documents(docs, sim, threshold=cluster_threshold)
    recommendations = {}
    for doc in sorted(docs, key=lambda d: d.doc_id):
        recommendations[doc.doc_id] = recommend_for(doc, docs, vectors, token_counts, top_k=top_k)
    body = {
        "schema": SCHEMA,
        "document_count": len(docs),
        "cluster_threshold": cluster_threshold,
        "clusters": clusters,
        "recommendations": recommendations,
    }
    body["analysis_sha256"] = sha256_hex(canonical_json_bytes(body))
    return body


def verify_analysis(result: dict) -> None:
    clone = dict(result)
    claimed = clone.pop("analysis_sha256", None)
    if not isinstance(claimed, str) or len(claimed) != 64:
        raise ValueError("analysis missing analysis_sha256")
    if clone.get("schema") != SCHEMA:
        raise ValueError("unsupported analysis schema")
    if claimed != sha256_hex(canonical_json_bytes(clone)):
        raise ValueError("analysis SHA-256 mismatch")


def load_documents(path: Path) -> list[Document]:
    suffix = path.suffix.lower()
    rows: list[dict] = []
    if suffix in {".jsonl", ".ndjson"}:
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON on line {lineno}: {exc.msg}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"line {lineno} must be an object")
            rows.append(value)
    elif suffix == ".json":
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, list):
            raise ValueError("JSON input must be an array")
        rows = value
    elif suffix == ".csv":
        with path.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
    else:
        raise ValueError("input must be .jsonl, .ndjson, .json, or .csv")
    docs = [Document.from_mapping(row) for row in rows]
    ids = [d.doc_id for d in docs]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate doc_id")
    return docs


def render_html(result: dict, docs: Sequence[Document]) -> str:
    by_id = {d.doc_id: d for d in docs}
    parts = ["<!doctype html><meta charset='utf-8'><title>AcqAtlas Analysis</title>",
             "<style>body{font-family:system-ui;max-width:1100px;margin:2rem auto;padding:0 1rem}table{border-collapse:collapse;width:100%}td,th{border:1px solid #bbb;padding:.4rem;text-align:left}code{word-break:break-all}.muted{opacity:.65}</style>",
             "<h1>AcqAtlas analysis</h1>",
             f"<p class='muted'>Deterministic analysis SHA-256: <code>{html.escape(result['analysis_sha256'])}</code></p>",
             "<h2>Clusters</h2><table><tr><th>Cluster</th><th>Members</th><th>Cohesion</th><th>Top terms</th></tr>"]
    for cluster in result["clusters"]:
        labels = [by_id[x].title or x for x in cluster["members"]]
        parts.append("<tr><td>%s</td><td>%s</td><td>%.4f</td><td>%s</td></tr>" % (
            html.escape(cluster["cluster_id"]), html.escape(" | ".join(labels)), cluster["cohesion_mean"], html.escape(", ".join(cluster["top_terms"]))))
    parts.append("</table><h2>Top vehicle recommendations</h2><table><tr><th>Document</th><th>Top candidates</th></tr>")
    for doc_id in sorted(result["recommendations"]):
        recs = result["recommendations"][doc_id]
        text = " | ".join(f"{r['vehicle']} ({r['score']:.4f})" for r in recs)
        parts.append(f"<tr><td>{html.escape(by_id[doc_id].title or doc_id)}</td><td>{html.escape(text)}</td></tr>")
    parts.append("</table>")
    return "\n".join(parts) + "\n"


def benchmark(docs: Sequence[Document], *, repeats: int = 3, cluster_threshold: float = 0.18) -> dict:
    if repeats < 2:
        raise ValueError("repeats must be >=2 to demonstrate repeatability")
    started = time.perf_counter()
    hashes = []
    elapsed = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        result = analyze(docs, cluster_threshold=cluster_threshold)
        elapsed.append(time.perf_counter() - t0)
        hashes.append(result["analysis_sha256"])
    total = time.perf_counter() - started
    rss_raw = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    receipt = {
        "schema": "acqatlas-benchmark-v2",
        "document_count": len(docs),
        "document_manifest_sha256": document_manifest_sha256(docs),
        "engine_source_sha256": sha256_hex(Path(__file__).read_bytes()),
        "cluster_threshold": cluster_threshold,
        "repeats": repeats,
        "analysis_hashes": hashes,
        "deterministic": len(set(hashes)) == 1,
        "elapsed_seconds_each": [round(x, 6) for x in elapsed],
        "elapsed_seconds_total": round(total, 6),
        "peak_rss_raw": rss_raw,
        "peak_rss_bytes_linux_interpretation": rss_raw * 1024,
        "network_calls": 0,
        "llm_tokens": 0,
    }
    receipt["receipt_sha256"] = sha256_hex(canonical_json_bytes(receipt))
    return receipt


def verify_benchmark_receipt(receipt: dict) -> None:
    clone = dict(receipt)
    claimed = clone.pop("receipt_sha256", None)
    if not isinstance(claimed, str) or len(claimed) != 64:
        raise ValueError("benchmark receipt missing receipt_sha256")
    if clone.get("schema") != "acqatlas-benchmark-v2":
        raise ValueError("unsupported benchmark receipt schema")
    if claimed != sha256_hex(canonical_json_bytes(clone)):
        raise ValueError("benchmark receipt SHA-256 mismatch")
    hashes = clone.get("analysis_hashes")
    if not isinstance(hashes, list) or len(hashes) < 2 or len(set(hashes)) != 1:
        raise ValueError("benchmark receipt does not prove deterministic repeated analysis")
    if clone.get("deterministic") is not True:
        raise ValueError("benchmark deterministic flag is false")
    for key in ("document_manifest_sha256", "engine_source_sha256"):
        value = clone.get(key)
        if not isinstance(value, str) or len(value) != 64:
            raise ValueError(f"benchmark receipt missing valid {key}")


def write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)


def cli(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    pa = sub.add_parser("analyze")
    pa.add_argument("input", type=Path)
    pa.add_argument("--output", type=Path)
    pa.add_argument("--html", type=Path)
    pa.add_argument("--threshold", type=float, default=0.18)
    pa.add_argument("--top-k", type=int, default=5)
    pv = sub.add_parser("validate")
    pv.add_argument("input", type=Path)
    pv.add_argument("--top-k", type=int, default=5)
    pb = sub.add_parser("benchmark")
    pb.add_argument("input", type=Path)
    pb.add_argument("--repeats", type=int, default=3)
    pb.add_argument("--output", type=Path)
    pverify = sub.add_parser("verify-analysis")
    pverify.add_argument("analysis", type=Path)
    pverify_bench = sub.add_parser("verify-benchmark")
    pverify_bench.add_argument("receipt", type=Path)
    args = parser.parse_args(argv)

    if args.cmd == "verify-benchmark":
        value = json.loads(args.receipt.read_text(encoding="utf-8"))
        verify_benchmark_receipt(value)
        print(json.dumps({"ok": True, "receipt_sha256": value["receipt_sha256"]}, sort_keys=True))
        return 0
    if args.cmd == "verify-analysis":
        value = json.loads(args.analysis.read_text(encoding="utf-8"))
        verify_analysis(value)
        print(json.dumps({"ok": True, "analysis_sha256": value["analysis_sha256"]}, sort_keys=True))
        return 0
    docs = load_documents(args.input)
    if args.cmd == "analyze":
        value = analyze(docs, cluster_threshold=args.threshold, top_k=args.top_k)
        rendered = canonical_json_bytes(value)
        if args.output:
            write_atomic(args.output, rendered)
        if args.html:
            write_atomic(args.html, render_html(value, docs).encode("utf-8"))
        print(rendered.decode("utf-8"), end="")
        return 0
    if args.cmd == "validate":
        print(canonical_json_bytes(validate_leave_one_out(docs, top_k=args.top_k)).decode("utf-8"), end="")
        return 0
    if args.cmd == "benchmark":
        value = benchmark(docs, repeats=args.repeats)
        rendered = canonical_json_bytes(value)
        if args.output:
            write_atomic(args.output, rendered)
        print(rendered.decode("utf-8"), end="")
        return 0
    raise RuntimeError("unreachable")


if __name__ == "__main__":
    raise SystemExit(cli())
