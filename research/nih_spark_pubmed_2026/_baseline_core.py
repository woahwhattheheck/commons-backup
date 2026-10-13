from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from typing import Any, Mapping

SCHEMA_CORPUS = "nih.spark.pubmed.corpus/v1"
SCHEMA_CASES = "nih.spark.pubmed.cases/v1"
SCHEMA_ANSWER = "nih.spark.pubmed.exploratory-answer/v1"
SCHEMA_RECEIPT = "nih.spark.pubmed.run-receipt/v1"

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class ContractError(ValueError):
    pass


def _reject_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ContractError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def load_json_strict_bytes(data: bytes) -> Any:
    if len(data) > 16 * 1024 * 1024:
        raise ContractError("input exceeds 16 MiB")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ContractError("input must be UTF-8") from exc
    try:
        return json.loads(
            text,
            object_pairs_hook=_reject_pairs,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ContractError(f"non-finite JSON number: {value}")
            ),
        )
    except json.JSONDecodeError as exc:
        raise ContractError(f"invalid JSON: {exc.msg}") from exc


def canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ContractError("value is not canonical-JSON serializable") from exc


def semantic_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _object(value: Any, where: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise ContractError(f"{where} must be an object")
    return value


def _array(value: Any, where: str, *, minimum: int = 0, maximum: int = 100_000) -> list[Any]:
    if type(value) is not list:
        raise ContractError(f"{where} must be an array")
    if not minimum <= len(value) <= maximum:
        raise ContractError(f"{where} length outside range")
    return value


def _string(value: Any, where: str, *, minimum: int = 1, maximum: int = 20_000) -> str:
    if type(value) is not str:
        raise ContractError(f"{where} must be a string")
    if not minimum <= len(value) <= maximum:
        raise ContractError(f"{where} length outside range")
    if _CONTROL_RE.search(value):
        raise ContractError(f"{where} contains control characters")
    return value


def _identifier(value: Any, where: str) -> str:
    value = _string(value, where, maximum=128)
    if not _ID_RE.fullmatch(value):
        raise ContractError(f"{where} must be a safe identifier")
    return value


def _sha(value: Any, where: str) -> str:
    value = _string(value, where, minimum=64, maximum=64)
    if not _SHA_RE.fullmatch(value):
        raise ContractError(f"{where} must be lowercase SHA-256")
    return value


def _int(value: Any, where: str, *, minimum: int = 0, maximum: int = 10_000) -> int:
    if type(value) is not int:
        raise ContractError(f"{where} must be an integer (bool/float rejected)")
    if not minimum <= value <= maximum:
        raise ContractError(f"{where} outside range")
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], where: str) -> None:
    actual = set(value)
    if actual != expected:
        raise ContractError(
            f"{where} keys mismatch: missing={sorted(expected-actual)} extra={sorted(actual-expected)}"
        )


def _tokens(text: str) -> tuple[str, ...]:
    return tuple(token.lower() for token in _TOKEN_RE.findall(text))


def load_corpus(value: Any) -> dict[str, Any]:
    root = _object(value, "corpus")
    _exact_keys(root, {"schema", "documents"}, "corpus")
    if root["schema"] != SCHEMA_CORPUS:
        raise ContractError("unsupported corpus schema")
    documents = []
    seen_documents: set[str] = set()
    for index, raw_document in enumerate(_array(root["documents"], "documents", minimum=1, maximum=100_000)):
        document = _object(raw_document, f"documents[{index}]")
        _exact_keys(
            document,
            {"document_id", "version", "license", "provenance", "title", "text_sha256", "passages"},
            f"documents[{index}]",
        )
        document_id = _identifier(document["document_id"], f"documents[{index}].document_id")
        if document_id in seen_documents:
            raise ContractError(f"duplicate document_id: {document_id}")
        seen_documents.add(document_id)
        passages = []
        seen_passages: set[str] = set()
        for pindex, raw_passage in enumerate(_array(document["passages"], f"{document_id}.passages", minimum=1, maximum=10_000)):
            passage = _object(raw_passage, f"{document_id}.passages[{pindex}]")
            _exact_keys(passage, {"passage_id", "text"}, f"{document_id}.passages[{pindex}]")
            passage_id = _identifier(passage["passage_id"], f"{document_id}.passage_id")
            if passage_id in seen_passages:
                raise ContractError(f"duplicate passage_id in {document_id}: {passage_id}")
            seen_passages.add(passage_id)
            passages.append(
                {
                    "passage_id": passage_id,
                    "text": _string(passage["text"], f"{document_id}.{passage_id}.text", maximum=100_000),
                }
            )
        passages.sort(key=lambda row: row["passage_id"])
        joined = "\n".join(row["text"] for row in passages)
        supplied_digest = _sha(document["text_sha256"], f"{document_id}.text_sha256")
        actual_digest = text_sha256(joined)
        if supplied_digest != actual_digest:
            raise ContractError(f"text digest mismatch for {document_id}")
        documents.append(
            {
                "document_id": document_id,
                "version": _identifier(document["version"], f"{document_id}.version"),
                "license": _string(document["license"], f"{document_id}.license", maximum=512),
                "provenance": _string(document["provenance"], f"{document_id}.provenance", maximum=2048),
                "title": _string(document["title"], f"{document_id}.title", maximum=1024),
                "text_sha256": supplied_digest,
                "passages": passages,
            }
        )
    documents.sort(key=lambda row: row["document_id"])
    return {"schema": SCHEMA_CORPUS, "documents": documents}


def corpus_digest(corpus: Any) -> str:
    return semantic_sha256(load_corpus(corpus))


def _passage_rows(corpus: Any) -> list[dict[str, Any]]:
    normalized = load_corpus(corpus)
    rows = []
    for document in normalized["documents"]:
        for passage in document["passages"]:
            rows.append(
                {
                    "document_id": document["document_id"],
                    "passage_id": passage["passage_id"],
                    "text": passage["text"],
                    "tokens": _tokens(document["title"] + " " + passage["text"]),
                }
            )
    return rows


def bm25_retrieve(corpus: Any, query: str, *, top_k: int = 5) -> list[dict[str, Any]]:
    query = _string(query, "query", maximum=4096)
    top_k = _int(top_k, "top_k", minimum=1, maximum=100)
    terms = tuple(dict.fromkeys(_tokens(query)))
    if not terms:
        return []
    rows = _passage_rows(corpus)
    n = len(rows)
    avgdl = sum(len(row["tokens"]) for row in rows) / n
    dfs = {
        term: sum(1 for row in rows if term in set(row["tokens"]))
        for term in terms
    }
    scored = []
    k1 = 1.2
    b = 0.75
    for row in rows:
        counts = Counter(row["tokens"])
        dl = len(row["tokens"])
        score = 0.0
        for term in terms:
            tf = counts.get(term, 0)
            if not tf:
                continue
            df = dfs[term]
            idf = math.log(1.0 + (n - df + 0.5) / (df + 0.5))
            denom = tf + k1 * (1.0 - b + b * dl / avgdl)
            score += idf * (tf * (k1 + 1.0)) / denom
        if score > 0:
            scored.append(
                {
                    "document_id": row["document_id"],
                    "passage_id": row["passage_id"],
                    "score": round(score, 12),
                }
            )
    scored.sort(key=lambda row: (-row["score"], row["document_id"], row["passage_id"]))
    return scored[:top_k]


def _citation_index(corpus: Any) -> set[tuple[str, str]]:
    return {
        (row["document_id"], row["passage_id"])
        for row in _passage_rows(corpus)
    }


def verify_exploratory_answer(corpus: Any, value: Any) -> dict[str, Any]:
    normalized_corpus = load_corpus(corpus)
    valid_citations = _citation_index(normalized_corpus)
    root = _object(value, "answer")
    _exact_keys(
        root,
        {"schema", "query_id", "answerability", "claims", "contradiction_groups", "follow_up_actions"},
        "answer",
    )
    if root["schema"] != SCHEMA_ANSWER:
        raise ContractError("unsupported answer schema")
    query_id = _identifier(root["query_id"], "query_id")
    answerability = root["answerability"]
    if answerability not in {"ANSWERED", "UNANSWERABLE"}:
        raise ContractError("invalid answerability")
    claims = []
    claim_ids: set[str] = set()
    citation_docs_by_claim: dict[str, set[str]] = {}
    for index, raw_claim in enumerate(_array(root["claims"], "claims", maximum=1_000)):
        claim = _object(raw_claim, f"claims[{index}]")
        _exact_keys(claim, {"claim_id", "text", "citations"}, f"claims[{index}]")
        claim_id = _identifier(claim["claim_id"], f"claims[{index}].claim_id")
        if claim_id in claim_ids:
            raise ContractError(f"duplicate claim_id: {claim_id}")
        claim_ids.add(claim_id)
        citations = []
        seen_citations: set[tuple[str, str]] = set()
        for cindex, raw_citation in enumerate(
            _array(claim["citations"], f"{claim_id}.citations", minimum=1, maximum=100)
        ):
            citation = _object(raw_citation, f"{claim_id}.citations[{cindex}]")
            _exact_keys(citation, {"document_id", "passage_id"}, f"{claim_id}.citations[{cindex}]")
            pair = (
                _identifier(citation["document_id"], "citation.document_id"),
                _identifier(citation["passage_id"], "citation.passage_id"),
            )
            if pair not in valid_citations:
                raise ContractError(f"unknown citation: {pair[0]}#{pair[1]}")
            if pair in seen_citations:
                raise ContractError(f"duplicate citation in {claim_id}: {pair[0]}#{pair[1]}")
            seen_citations.add(pair)
            citations.append({"document_id": pair[0], "passage_id": pair[1]})
        citations.sort(key=lambda row: (row["document_id"], row["passage_id"]))
        citation_docs_by_claim[claim_id] = {row["document_id"] for row in citations}
        claims.append(
            {
                "claim_id": claim_id,
                "text": _string(claim["text"], f"{claim_id}.text", maximum=10_000),
                "citations": citations,
            }
        )
    claims.sort(key=lambda row: row["claim_id"])
    if answerability == "ANSWERED" and not claims:
        raise ContractError("ANSWERED output requires at least one claim")
    if answerability == "UNANSWERABLE" and claims:
        raise ContractError("UNANSWERABLE output must contain zero claims")

    contradiction_groups = []
    grouped_claims: set[str] = set()
    for index, raw_group in enumerate(_array(root["contradiction_groups"], "contradiction_groups", maximum=1_000)):
        group = _object(raw_group, f"contradiction_groups[{index}]")
        _exact_keys(group, {"group_id", "claim_ids"}, f"contradiction_groups[{index}]")
        group_id = _identifier(group["group_id"], f"contradiction_groups[{index}].group_id")
        members = [
            _identifier(member, f"{group_id}.claim_ids")
            for member in _array(group["claim_ids"], f"{group_id}.claim_ids", minimum=2, maximum=100)
        ]
        if len(set(members)) != len(members):
            raise ContractError(f"duplicate claim in contradiction group {group_id}")
        unknown = sorted(set(members) - claim_ids)
        if unknown:
            raise ContractError(f"unknown contradiction claim(s): {unknown}")
        if grouped_claims.intersection(members):
            raise ContractError("a claim may belong to only one contradiction group")
        grouped_claims.update(members)
        cited_docs = set().union(*(citation_docs_by_claim[member] for member in members))
        if len(cited_docs) < 2:
            raise ContractError("contradiction group must preserve evidence from at least two documents")
        contradiction_groups.append({"group_id": group_id, "claim_ids": sorted(members)})
    contradiction_groups.sort(key=lambda row: row["group_id"])
    if answerability == "UNANSWERABLE" and contradiction_groups:
        raise ContractError("UNANSWERABLE output must contain zero contradiction groups")

    actions = [
        _string(action, "follow_up_action", maximum=512)
        for action in _array(root["follow_up_actions"], "follow_up_actions", minimum=3, maximum=5)
    ]
    if len(set(actions)) != len(actions):
        raise ContractError("follow-up actions must be unique")
    return {
        "schema": SCHEMA_ANSWER,
        "query_id": query_id,
        "answerability": answerability,
        "claims": claims,
        "contradiction_groups": contradiction_groups,
        "follow_up_actions": actions,
    }


def load_cases(value: Any) -> dict[str, Any]:
    root = _object(value, "cases")
    _exact_keys(root, {"schema", "cases"}, "cases")
    if root["schema"] != SCHEMA_CASES:
        raise ContractError("unsupported cases schema")
    cases = []
    seen: set[str] = set()
    for index, raw_case in enumerate(_array(root["cases"], "cases", minimum=1, maximum=10_000)):
        case = _object(raw_case, f"cases[{index}]")
        _exact_keys(
            case,
            {"query_id", "query", "expected_document_ids", "expected_answerability", "expected_contradiction_document_sets"},
            f"cases[{index}]",
        )
        query_id = _identifier(case["query_id"], f"cases[{index}].query_id")
        if query_id in seen:
            raise ContractError(f"duplicate query_id: {query_id}")
        seen.add(query_id)
        expected_document_ids = sorted(
            {
                _identifier(value, f"{query_id}.expected_document_ids")
                for value in _array(case["expected_document_ids"], f"{query_id}.expected_document_ids", maximum=100)
            }
        )
        contradiction_sets = []
        for cindex, raw_group in enumerate(
            _array(case["expected_contradiction_document_sets"], f"{query_id}.expected_contradiction_document_sets", maximum=100)
        ):
            group = sorted(
                {
                    _identifier(value, f"{query_id}.contradiction[{cindex}]")
                    for value in _array(raw_group, f"{query_id}.contradiction[{cindex}]", minimum=2, maximum=20)
                }
            )
            if len(group) < 2:
                raise ContractError("expected contradiction set needs at least two distinct documents")
            contradiction_sets.append(group)
        contradiction_sets.sort()
        answerability = case["expected_answerability"]
        if answerability not in {"ANSWERED", "UNANSWERABLE"}:
            raise ContractError("invalid expected_answerability")
        cases.append(
            {
                "query_id": query_id,
                "query": _string(case["query"], f"{query_id}.query", maximum=4096),
                "expected_document_ids": expected_document_ids,
                "expected_answerability": answerability,
                "expected_contradiction_document_sets": contradiction_sets,
            }
        )
    cases.sort(key=lambda row: row["query_id"])
    return {"schema": SCHEMA_CASES, "cases": cases}


def evaluate_bundle(
    corpus: Any,
    cases: Any,
    retrievals: Mapping[str, list[dict[str, Any]]],
    answers: Mapping[str, Any],
) -> dict[str, Any]:
    normalized_corpus = load_corpus(corpus)
    normalized_cases = load_cases(cases)
    valid_docs = {document["document_id"] for document in normalized_corpus["documents"]}
    valid_pairs = _citation_index(normalized_corpus)
    expected_query_ids = {case["query_id"] for case in normalized_cases["cases"]}
    if set(retrievals) != expected_query_ids:
        raise ContractError("retrieval query_id set differs from benchmark cases")
    if set(answers) != expected_query_ids:
        raise ContractError("answer query_id set differs from benchmark cases")
    rr_total = 0.0
    rr_count = 0
    hit_count = 0
    answerability_hits = 0
    contradiction_expected = 0
    contradiction_covered = 0
    verified_answers: dict[str, Any] = {}
    for case in normalized_cases["cases"]:
        query_id = case["query_id"]
        referenced_docs = set(case["expected_document_ids"])
        for expected_group in case["expected_contradiction_document_sets"]:
            referenced_docs.update(expected_group)
        unknown_expected = referenced_docs - valid_docs
        if unknown_expected:
            raise ContractError(
                f"benchmark case {query_id} references unknown expected document(s): {sorted(unknown_expected)}"
            )
        rows = retrievals[query_id]
        if type(rows) is not list:
            raise ContractError("retrieval rows must be arrays")
        seen_pairs: set[tuple[str, str]] = set()
        ranked_docs = []
        for row in rows:
            row = _object(row, f"retrievals[{query_id}]")
            _exact_keys(row, {"document_id", "passage_id", "score"}, f"retrievals[{query_id}]")
            document_id = _identifier(row["document_id"], "retrieval.document_id")
            passage_id = _identifier(row["passage_id"], "retrieval.passage_id")
            pair = (document_id, passage_id)
            if pair not in valid_pairs:
                raise ContractError(
                    f"retrieval references unknown document/passage pair {document_id}/{passage_id}"
                )
            if type(row["score"]) not in {int, float} or isinstance(row["score"], bool) or not math.isfinite(row["score"]):
                raise ContractError("retrieval score must be finite numeric")
            if pair in seen_pairs:
                raise ContractError("duplicate retrieval pair")
            seen_pairs.add(pair)
            ranked_docs.append(document_id)
        expected = set(case["expected_document_ids"])
        if expected:
            rr_count += 1
            rank = next((index + 1 for index, doc in enumerate(ranked_docs) if doc in expected), None)
            if rank is not None:
                rr_total += 1.0 / rank
                hit_count += 1
        answer = verify_exploratory_answer(normalized_corpus, answers[query_id])
        if answer["query_id"] != query_id:
            raise ContractError("answer query_id mismatch")
        verified_answers[query_id] = answer
        if answer["answerability"] == case["expected_answerability"]:
            answerability_hits += 1

        claim_docs = {
            claim["claim_id"]: {citation["document_id"] for citation in claim["citations"]}
            for claim in answer["claims"]
        }
        for expected_group in case["expected_contradiction_document_sets"]:
            contradiction_expected += 1
            needed = set(expected_group)
            for group in answer["contradiction_groups"]:
                observed = set().union(*(claim_docs[claim_id] for claim_id in group["claim_ids"]))
                if needed.issubset(observed):
                    contradiction_covered += 1
                    break

    case_count = len(normalized_cases["cases"])
    return {
        "schema": "nih.spark.pubmed.evaluation/v1",
        "case_count": case_count,
        "retrieval_hit_at_k": round(hit_count / rr_count, 12) if rr_count else 1.0,
        "retrieval_mrr": round(rr_total / rr_count, 12) if rr_count else 1.0,
        "answerability_accuracy": round(answerability_hits / case_count, 12),
        "citation_contract_validity": 1.0,
        "follow_up_contract_validity": 1.0,
        "contradiction_coverage": (
            round(contradiction_covered / contradiction_expected, 12)
            if contradiction_expected
            else 1.0
        ),
        "corpus_sha256": semantic_sha256(normalized_corpus),
        "cases_sha256": semantic_sha256(normalized_cases),
        "answers_sha256": semantic_sha256(verified_answers),
    }


def build_run_receipt(
    *,
    corpus: Any,
    cases: Any,
    retrievals: Mapping[str, Any],
    answers: Mapping[str, Any],
    evaluation: Any,
    source_version: str,
) -> dict[str, Any]:
    source_version = _identifier(source_version, "source_version")
    normalized_corpus = load_corpus(corpus)
    normalized_cases = load_cases(cases)
    expected_evaluation = evaluate_bundle(
        normalized_corpus,
        normalized_cases,
        retrievals,
        answers,
    )
    if evaluation != expected_evaluation:
        raise ContractError("evaluation differs from deterministic recomputation")
    payload = {
        "schema": SCHEMA_RECEIPT,
        "corpus_sha256": semantic_sha256(normalized_corpus),
        "cases_sha256": semantic_sha256(normalized_cases),
        "retrievals_sha256": semantic_sha256(dict(sorted(retrievals.items()))),
        "answers_sha256": semantic_sha256(dict(sorted(answers.items()))),
        "evaluation_sha256": semantic_sha256(evaluation),
        "source_version": source_version,
        "official_corpus_used": False,
        "nih_registration_claimed": False,
        "official_score_claimed": False,
        "submission_claimed": False,
        "award_or_payment_claimed": False,
    }
    payload["receipt_sha256"] = semantic_sha256(payload)
    return payload


def verify_run_receipt(receipt: Any, **kwargs: Any) -> bool:
    return type(receipt) is dict and receipt == build_run_receipt(**kwargs)
