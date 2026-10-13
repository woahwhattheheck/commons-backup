from __future__ import annotations

from typing import Any, Mapping, Sequence

from .contracts import Concept, Corpus
from .core import (
    ONT_NONE, SCHEMA_T1_OUTPUT, SCHEMA_T1_QUERIES, ContractError, _array, _exact_keys,
    _identifier, _int, _object, _string, normalized_tokens, semantic_sha256,
)

def _overlap_score(variable_tokens: tuple[str, ...], phrase: tuple[str, ...]) -> tuple[int, int, int]:
    """Integer, transparent lexical score: exact phrase > token coverage > compactness."""
    if not variable_tokens or not phrase:
        return (0, 0, 0)
    vset = set(variable_tokens)
    pset = set(phrase)
    common = len(vset & pset)
    union = len(vset | pset)
    coverage_bp = (common * 10_000) // max(1, len(pset))
    jaccard_bp = (common * 10_000) // max(1, union)
    joined_v = " ".join(variable_tokens)
    joined_p = " ".join(phrase)
    exact_phrase = 1 if joined_p in joined_v else 0
    return (exact_phrase, coverage_bp, jaccard_bp)


def rank_concepts(text: str, concepts: Sequence[Concept], *, top_k: int = 5) -> list[dict[str, Any]]:
    _string(text, "track1.variable_text", max_len=8192)
    _int(top_k, "top_k", minimum=1, maximum=100)
    tokens = normalized_tokens(text)
    rows: list[dict[str, Any]] = []
    for concept in concepts:
        best = max((_overlap_score(tokens, phrase) for phrase in concept.phrases), default=(0, 0, 0))
        rows.append({
            "concept_id": concept.concept_id,
            "exact_phrase": best[0],
            "coverage_bp": best[1],
            "jaccard_bp": best[2],
        })
    rows.sort(key=lambda r: (-r["exact_phrase"], -r["coverage_bp"], -r["jaccard_bp"], r["concept_id"]))
    return rows[:top_k]


def track1_predict(corpus: Corpus, query_obj: Any, *, abstain_coverage_bp: int = 5000, top_k: int = 5) -> dict[str, Any]:
    _int(abstain_coverage_bp, "abstain_coverage_bp", minimum=0, maximum=10_000)
    root = _object(query_obj, "track1 input")
    _exact_keys(root, {"schema", "variables"}, "track1 input")
    if root["schema"] != SCHEMA_T1_QUERIES:
        raise ContractError("unsupported track1 input schema")
    rows = _array(root["variables"], "track1 variables")
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for i, item in enumerate(rows):
        row = _object(item, f"track1.variables[{i}]")
        _exact_keys(row, {"query_variable_id", "text"}, f"track1.variables[{i}]")
        qid = _identifier(row["query_variable_id"], f"track1.variables[{i}].query_variable_id")
        if qid in seen:
            raise ContractError(f"duplicate query_variable_id: {qid}")
        seen.add(qid)
        text = _string(row["text"], f"track1.variables[{i}].text", max_len=8192)
        ranked = rank_concepts(text, corpus.concepts, top_k=top_k)
        chosen = ONT_NONE
        if ranked and ranked[0]["coverage_bp"] >= abstain_coverage_bp:
            chosen = ranked[0]["concept_id"]
        out.append({"query_variable_id": qid, "predicted_concept_id": chosen, "candidates": ranked})
    out.sort(key=lambda x: x["query_variable_id"])
    payload = {
        "schema": SCHEMA_T1_OUTPUT,
        "corpus_sha256": corpus.digest,
        "policy": {"abstain_coverage_bp": abstain_coverage_bp, "top_k": top_k},
        "predictions": out,
    }
    payload["output_sha256"] = semantic_sha256(payload)
    return payload


def _fraction(num: int, den: int) -> dict[str, int]:
    return {"numerator": num, "denominator": den}


def evaluate_track1(predictions: Mapping[str, str], gold: Mapping[str, str]) -> dict[str, Any]:
    if set(predictions) != set(gold):
        raise ContractError("track1 prediction/gold key sets differ")
    classes = sorted(set(predictions.values()) | set(gold.values()))
    if not classes:
        raise ContractError("track1 evaluation requires at least one item")
    per_class: list[dict[str, Any]] = []
    macro_f1_num = 0
    macro_scale = 1_000_000
    for cid in classes:
        tp = sum(1 for k in gold if gold[k] == cid and predictions[k] == cid)
        fp = sum(1 for k in gold if gold[k] != cid and predictions[k] == cid)
        fn = sum(1 for k in gold if gold[k] == cid and predictions[k] != cid)
        p_den = tp + fp
        r_den = tp + fn
        f_den = 2 * tp + fp + fn
        f_scaled = (2 * tp * macro_scale) // f_den if f_den else 0
        macro_f1_num += f_scaled
        per_class.append({
            "concept_id": cid,
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "precision": _fraction(tp, p_den),
            "recall": _fraction(tp, r_den),
            "f1": _fraction(2 * tp, f_den),
        })
    return {
        "classes": per_class,
        "macro_f1_scaled_1e6": macro_f1_num // len(classes),
        "macro_f1_scale": macro_scale,
        "includes_ont_none": ONT_NONE in classes,
    }

