from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

from .contracts import Corpus
from .core import (
    SCHEMA_T2_OUTPUT, SCHEMA_T2_QUERIES, ContractError, _array, _exact_keys, _identifier,
    _int, _object, _string, normalized_tokens, semantic_sha256,
)

def _study_documents(corpus: Corpus) -> dict[str, tuple[str, ...]]:
    vars_by_study: dict[str, list[str]] = {s.study_id: [] for s in corpus.studies}
    for v in corpus.variables:
        vars_by_study[v.study_id].append(v.text)
    docs: dict[str, tuple[str, ...]] = {}
    for s in corpus.studies:
        text = " ".join([s.title, s.description, *sorted(vars_by_study[s.study_id])])
        docs[s.study_id] = normalized_tokens(text)
    return docs


def _lexical_rank(query: str, corpus: Corpus) -> list[dict[str, Any]]:
    q_tokens = normalized_tokens(_string(query, "query", max_len=8192))
    q_unique = tuple(sorted(set(q_tokens)))
    docs = _study_documents(corpus)
    n = len(docs)
    df: dict[str, int] = {term: sum(1 for tokens in docs.values() if term in set(tokens)) for term in q_unique}
    rows: list[dict[str, Any]] = []
    for sid, tokens in docs.items():
        counts: dict[str, int] = {}
        for tok in tokens:
            if tok in df:
                counts[tok] = counts.get(tok, 0) + 1
        score = 0
        matched: list[dict[str, int | str]] = []
        for term in q_unique:
            tf = counts.get(term, 0)
            if not tf:
                continue
            rarity = 1000 + (1000 * max(0, n - df[term])) // max(1, df[term])
            saturation = (2000 * tf) // (tf + 1)
            contribution = rarity * saturation
            score += contribution
            matched.append({"term": term, "tf": tf, "df": df[term], "contribution": contribution})
        coverage = len(matched)
        score += coverage * coverage * 1_000_000
        rows.append({"study_id": sid, "score": score, "matched_terms": matched, "matched_term_count": coverage})
    rows.sort(key=lambda r: (-r["score"], -r["matched_term_count"], r["study_id"]))
    return rows


def track2_rank(corpus: Corpus, query_obj: Any, *, top_k: int = 10) -> dict[str, Any]:
    _int(top_k, "top_k", minimum=1, maximum=1000)
    root = _object(query_obj, "track2 input")
    _exact_keys(root, {"schema", "queries"}, "track2 input")
    if root["schema"] != SCHEMA_T2_QUERIES:
        raise ContractError("unsupported track2 input schema")
    rows = _array(root["queries"], "track2 queries")
    seen: set[str] = set()
    output: list[dict[str, Any]] = []
    for i, item in enumerate(rows):
        row = _object(item, f"track2.queries[{i}]")
        _exact_keys(row, {"query_id", "text"}, f"track2.queries[{i}]")
        qid = _identifier(row["query_id"], f"track2.queries[{i}].query_id")
        if qid in seen:
            raise ContractError(f"duplicate query_id: {qid}")
        seen.add(qid)
        ranked = _lexical_rank(_string(row["text"], f"track2.queries[{i}].text", max_len=8192), corpus)[:top_k]
        output.append({"query_id": qid, "ranked_studies": ranked})
    output.sort(key=lambda x: x["query_id"])
    payload = {"schema": SCHEMA_T2_OUTPUT, "corpus_sha256": corpus.digest, "policy": {"top_k": top_k}, "results": output}
    payload["output_sha256"] = semantic_sha256(payload)
    return payload


def _dcg(rels: Sequence[int]) -> float:
    total = 0.0
    for rank, rel in enumerate(rels, start=1):
        _int(rel, "relevance", minimum=0, maximum=4)
        total += (2**rel - 1) / math.log2(rank + 1)
    return total


def evaluate_track2(rankings: Mapping[str, Sequence[str]], relevance: Mapping[str, Mapping[str, int]], *, k: int = 10) -> dict[str, Any]:
    _int(k, "k", minimum=1, maximum=1000)
    if set(rankings) != set(relevance):
        raise ContractError("track2 ranking/relevance query sets differ")
    per_query: list[dict[str, Any]] = []
    ndcgs: list[float] = []
    for qid in sorted(rankings):
        ranked = list(rankings[qid])[:k]
        if len(set(ranked)) != len(ranked):
            raise ContractError(f"duplicate ranked study for query {qid}")
        rel_map = relevance[qid]
        for sid, rel in rel_map.items():
            _identifier(sid, f"relevance[{qid}] study")
            _int(rel, f"relevance[{qid}][{sid}]", minimum=0, maximum=4)
        actual_rels = [rel_map.get(sid, 0) for sid in ranked]
        ideal_rels = sorted(rel_map.values(), reverse=True)[:k]
        dcg = _dcg(actual_rels)
        idcg = _dcg(ideal_rels)
        ndcg = dcg / idcg if idcg else 0.0
        ndcgs.append(ndcg)
        per_query.append({
            "query_id": qid,
            "cg": sum(actual_rels),
            "dcg_scaled_1e9": int(round(dcg * 1_000_000_000)),
            "idcg_scaled_1e9": int(round(idcg * 1_000_000_000)),
            "ndcg_scaled_1e9": int(round(ndcg * 1_000_000_000)),
        })
    mean = sum(ndcgs) / len(ndcgs) if ndcgs else 0.0
    return {"k": k, "queries": per_query, "mean_ndcg_scaled_1e9": int(round(mean * 1_000_000_000)), "scale": 1_000_000_000}

