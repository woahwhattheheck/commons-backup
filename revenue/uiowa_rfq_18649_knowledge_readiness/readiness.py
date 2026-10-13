#!/usr/bin/env python3
"""Offline, evidence-linked knowledge readiness analysis. Python standard library only.

The analyzer checks supplied records, not institutional truth. Assertion meanings
and relevance judgments are analyst inputs; retrieval is measured, not simulated.
No network requests, model calls, access mutations, or institutional scoring.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

VERSION = "1.0"
GROUPS = {"ESS", "RIS", "IAM"}
STATUSES = {"active", "superseded", "archived"}
STOPWORDS = {"a", "an", "the", "is", "are", "what", "how", "for", "of", "to", "and", "in", "on", "do", "does"}


class DataError(ValueError):
    """An input contract or source-binding error."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise DataError(message)


def text(value: object, field: str) -> str:
    require(isinstance(value, str) and bool(value.strip()), f"{field}: nonempty text required")
    try:
        value.encode("utf-8")
    except UnicodeError as exc:
        raise DataError(f"{field}: valid Unicode text required") from exc
    return value


def iso_date(value: object, field: str) -> date:
    text(value, field)
    try:
        result = date.fromisoformat(value)
    except ValueError as exc:
        raise DataError(f"{field}: YYYY-MM-DD required") from exc
    require(result.isoformat() == value, f"{field}: YYYY-MM-DD required")
    return result


def integer(value: object, field: str, minimum: int = 0) -> int:
    require(type(value) is int and value >= minimum, f"{field}: integer >= {minimum} required")
    return value


def unique_pairs(pairs: list) -> dict:
    obj = {}
    for key, value in pairs:
        require(key not in obj, f"duplicate JSON key: {key}")
        obj[key] = value
    return obj


def reject_constant(value: str) -> None:
    raise DataError(f"non-finite JSON constant: {value}")


def finite_float(value: str) -> float:
    result = float(value)
    require(math.isfinite(result), f"non-finite JSON number: {value}")
    return result


def load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_pairs,
                          parse_constant=reject_constant, parse_float=finite_float)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DataError(f"cannot read JSON: {exc}") from exc


def digest(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def fact_key(assertion: dict) -> str:
    # Array encoding prevents delimiter collisions in user-supplied fields.
    return json.dumps([assertion["scope"], assertion["key"]], ensure_ascii=False)


def locator(doc: dict, assertion: dict | None = None) -> str:
    suffix = "" if assertion is None else f"#L{assertion['start_line']}-L{assertion['end_line']}"
    return f"{doc['id']}@{doc['revision']}:{doc['sha256']}{suffix}"


def validate(packet: object) -> None:
    require(isinstance(packet, dict), "packet: object required")
    require(packet.get("schema_version") == VERSION, "unsupported schema_version")
    require(type(packet.get("synthetic")) is bool, "synthetic: explicit boolean required")
    text(packet.get("snapshot_id"), "snapshot_id")
    iso_date(packet.get("as_of"), "as_of")
    docs = packet.get("documents")
    queries = packet.get("queries")
    require(isinstance(docs, list), "documents: array required")
    require(isinstance(queries, list), "queries: array required")
    doc_ids = set()
    for doc in docs:
        require(isinstance(doc, dict), "document: object required")
        for field in ("id", "title", "revision", "content", "sha256"):
            text(doc.get(field), f"document.{field}")
        require(doc["id"] not in doc_ids, f"duplicate document id: {doc['id']}")
        doc_ids.add(doc["id"])
        require(isinstance(doc.get("group"), str) and doc["group"] in GROUPS, f"{doc['id']}: group must be ESS/RIS/IAM")
        require(isinstance(doc.get("status"), str) and doc["status"] in STATUSES, f"{doc['id']}: invalid status")
        require(digest(doc["content"]) == doc["sha256"], f"{doc['id']}: content digest mismatch")
        for field in ("reviewed_on", "captured_on"):
            require(field in doc, f"{doc['id']}: missing {field}; use null for unknown")
            if doc[field] is not None:
                iso_date(doc[field], field)
        require("review_interval_days" in doc, "missing review_interval_days")
        if doc["review_interval_days"] is not None:
            integer(doc["review_interval_days"], "review_interval_days", 1)
        for field in ("owner", "source_locator", "access_semantics"):
            require(field in doc, f"{doc['id']}: missing {field}; use null for unknown")
            if doc[field] is not None:
                text(doc[field], field)
        assertions = doc.get("assertions")
        require(isinstance(assertions, list), f"{doc['id']}: assertions array required")
        lines = doc["content"].splitlines()
        for item in assertions:
            require(isinstance(item, dict), "assertion: object required")
            for field in ("scope", "key", "value", "quote"):
                text(item.get(field), f"assertion.{field}")
            first = integer(item.get("start_line"), "start_line", 1)
            last = integer(item.get("end_line"), "end_line", first)
            require(last <= len(lines), f"{doc['id']}: assertion locator outside source")
            require("\n".join(lines[first - 1:last]) == item["quote"],
                    f"{doc['id']}: assertion quote does not match source lines")
    query_ids = set()
    for query in queries:
        require(isinstance(query, dict), "query: object required")
        for field in ("id", "question"):
            text(query.get(field), f"query.{field}")
        require(query["id"] not in query_ids, f"duplicate query id: {query['id']}")
        query_ids.add(query["id"])
        require(isinstance(query.get("group"), str) and query["group"] in GROUPS, "query.group must be ESS/RIS/IAM")
        integer(query.get("top_k"), "top_k", 1)
        needs = query.get("required_facts")
        require(isinstance(needs, list) and bool(needs), "required_facts: nonempty array required")
        keys = []
        for item in needs:
            require(isinstance(item, dict), "required fact: object required")
            for field in ("scope", "key"):
                text(item.get(field), f"required_fact.{field}")
            keys.append(fact_key(item))
        require(len(set(keys)) == len(keys), "duplicate required fact")
        relevant = query.get("relevant_document_ids")
        require(relevant is None or isinstance(relevant, list), "relevance must be array or null")
        if relevant is not None:
            require(all(isinstance(item, str) for item in relevant), "relevance IDs must be text")
            require(len(relevant) == len(set(relevant)), "duplicate relevance ID")
            for doc_id in relevant:
                require(doc_id in doc_ids, f"unknown relevance document: {doc_id}")
                doc = next(d for d in docs if d["id"] == doc_id)
                require(doc["group"] == query["group"] and doc["status"] == "active",
                        f"{doc_id}: relevance judgment outside query's active group corpus")


def tokens(value: str) -> list[str]:
    return [t for t in re.findall(r"[^\W_]+", unicodedata.normalize("NFKC", value).casefold())
            if t not in STOPWORDS]


def retrieve(documents: list[dict], query: dict) -> list[dict]:
    """Lexical TF-IDF cosine baseline over active documents in the query's group.

    Group is an analytical partition, not an authorization decision. Recorded
    access_semantics does not change the retrieval result or any real permission.
    """
    corpus = [d for d in documents if d["status"] == "active" and d["group"] == query["group"]]
    if not corpus:
        return []
    terms = [Counter(tokens(d["title"] + "\n" + d["content"])) for d in corpus]
    df = Counter(t for bag in terms for t in bag)
    idf = {t: math.log((1 + len(corpus)) / (1 + freq)) + 1 for t, freq in df.items()}
    qbag = Counter(tokens(query["question"]))
    qvec = {t: (1 + math.log(n)) * idf[t] for t, n in qbag.items() if t in idf}
    qnorm = math.sqrt(sum(v * v for v in qvec.values()))
    if not qnorm:
        return []
    ranked = []
    for doc, bag in zip(corpus, terms):
        vec = {t: (1 + math.log(n)) * idf[t] for t, n in bag.items()}
        denominator = qnorm * math.sqrt(sum(v * v for v in vec.values()))
        if not denominator:
            continue
        score = sum(v * vec.get(t, 0) for t, v in qvec.items()) / denominator
        if score > 0:
            ranked.append({"document_id": doc["id"], "score": score})
    ranked.sort(key=lambda item: (-item["score"], item["document_id"]))
    return [{**item, "score": round(item["score"], 8)} for item in ranked[:query["top_k"]]]


def source_health(doc: dict, as_of: date) -> dict:
    issues = []
    if doc["status"] != "active":
        issues.append("not_active")
    for field in ("owner", "source_locator", "access_semantics"):
        if doc[field] is None:
            issues.append(f"unknown_{field}")
    captured = iso_date(doc["captured_on"], "captured_on") if doc["captured_on"] else None
    reviewed = iso_date(doc["reviewed_on"], "reviewed_on") if doc["reviewed_on"] else None
    if captured is None:
        issues.append("unknown_capture_date")
    elif captured > as_of:
        issues.append("future_capture_date")
    if reviewed is None or doc["review_interval_days"] is None:
        freshness = "unknown"
    elif reviewed > as_of:
        freshness = "future_review_date"
    elif captured is not None and reviewed > captured:
        freshness = "review_after_capture"
    elif (as_of - reviewed).days > doc["review_interval_days"]:
        freshness = "stale"
    else:
        freshness = "current_within_declared_interval"
    if freshness != "current_within_declared_interval":
        issues.append("unknown_freshness" if freshness == "unknown" else freshness)
    if not doc["assertions"]:
        issues.append("no_structured_assertions")
    return {"document_id": doc["id"], "group": doc["group"], "status": doc["status"],
            "locator": locator(doc), "freshness": freshness, "issues": issues,
            "owner": doc["owner"], "access_semantics": doc["access_semantics"]}


def classify_support(candidates: list[tuple[dict, dict]], health: dict) -> dict:
    # Preserve conflicting active claims even when one is stale; dates do not
    # establish which claim is authoritative. Explicit supersession is input.
    values = sorted({a["value"] for _, a in candidates})
    refs = [{"value": a["value"], "locator": locator(d, a), "quote": a["quote"],
             "source_issues": health[d["id"]]["issues"]} for d, a in candidates]
    if len(values) > 1:
        state = "conflicting"
    elif not values:
        state = "missing"
    elif any(not health[d["id"]]["issues"] for d, _ in candidates):
        state = "supported_by_current_record"
    else:
        state = "support_needs_preparation"
    return {"state": state, "values": values, "sources": refs}


def metric(numerator: int, denominator: int) -> dict:
    return {"numerator": numerator, "denominator": denominator,
            "value": numerator / denominator if denominator else None}


def assess(packet: dict) -> dict:
    validate(packet)
    docs = packet["documents"]
    health = {d["id"]: source_health(d, iso_date(packet["as_of"], "as_of")) for d in docs}
    active_facts = defaultdict(list)
    for doc in docs:
        if doc["status"] == "active":
            for assertion in doc["assertions"]:
                active_facts[(doc["group"], fact_key(assertion))].append((doc, assertion))
    conflicts = []
    for (group, key), candidates in sorted(active_facts.items()):
        support = classify_support(candidates, health)
        if support["state"] == "conflicting":
            conflicts.append({"group": group, "fact": json.loads(key), **support})
    queries = []
    for query in packet["queries"]:
        retrieved = retrieve(docs, query)
        retrieved_ids = {item["document_id"] for item in retrieved}
        facts = []
        for need in query["required_facts"]:
            candidates = active_facts[(query["group"], fact_key(need))]
            local = [(d, a) for d, a in candidates if d["id"] in retrieved_ids]
            full_support = classify_support(candidates, health)
            retrieved_support = classify_support(local, health)
            # A contradictory source outside top-k still limits answer support.
            state = "conflicting" if full_support["state"] == "conflicting" else retrieved_support["state"]
            if state == "missing" and full_support["state"] != "missing":
                state = "retrieval_gap"
            facts.append({**need, "state": state, "corpus_support": full_support,
                          "retrieved_support": retrieved_support})
        states = Counter(item["state"] for item in facts)
        if states["conflicting"]:
            answer_state = "contradictory_sources_require_resolution"
        elif states["supported_by_current_record"] == len(facts):
            answer_state = "complete_source_support_not_answer_validation"
        else:
            answer_state = "incomplete_source_support"
        gold = query.get("relevant_document_ids")
        hits = len(retrieved_ids.intersection(gold)) if gold is not None else None
        metrics = {"judgment_status": "unknown" if gold is None else "analyst_supplied",
                   "precision": metric(hits, len(retrieved_ids)) if gold is not None else None,
                   "recall": metric(hits, len(gold)) if gold is not None else None}
        queries.append({"query_id": query["id"], "question": query["question"], "group": query["group"],
                        "top_k": query["top_k"], "retrieved": retrieved, "retrieval_metrics": metrics,
                        "answer_support": answer_state, "required_facts": facts,
                        "supported_facts": metric(states["supported_by_current_record"], len(facts))})
    backlog = []
    for doc in docs:
        if doc["status"] != "active":
            continue
        for problem in health[doc["id"]]["issues"]:
            if problem == "not_active":
                continue
            backlog.append({"kind": "source_preparation", "subject": doc["id"], "problem": problem,
                            "owner": doc["owner"], "evidence": [locator(doc)],
                            "next_step": "Confirm with the source steward and capture revised, dated evidence; do not silently fill the field."})
    for conflict in conflicts:
        backlog.append({"kind": "contradiction_resolution", "subject": conflict["group"] + ":" + repr(conflict["fact"]),
                        "problem": "conflicting_active_assertions", "owner": None,
                        "evidence": [s["locator"] for s in conflict["sources"]],
                        "next_step": "Ask the accountable subject steward to reconcile scope and effective period; record explicit correction or supersession."})
    for query in queries:
        for fact in query["required_facts"]:
            if fact["state"] in {"missing", "retrieval_gap"}:
                backlog.append({"kind": "knowledge_gap" if fact["state"] == "missing" else "retrieval_improvement",
                                "subject": query["query_id"] + ":" + fact_key(fact), "problem": fact["state"],
                                "owner": None, "evidence": [s["locator"] for s in fact["corpus_support"]["sources"]],
                                "next_step": "Collect the missing source" if fact["state"] == "missing" else "Inspect vocabulary, chunk boundaries and indexing; rerun this exact query."})
    return {"schema_version": VERSION, "snapshot_id": packet["snapshot_id"], "synthetic": packet["synthetic"],
            "as_of": packet["as_of"], "analysis_kind": "offline_record_and_retrieval_assessment",
            "source_count": len(docs), "active_source_count": sum(d["status"] == "active" for d in docs),
            "sources": list(health.values()), "conflicts": conflicts, "queries": queries, "preparation_backlog": backlog,
            "limitations": ["Not University findings, a maturity score, an authorization decision, or a compliance verdict.",
                            "Freshness uses analyst-declared intervals, not proof the content is true or effective today.",
                            "Assertion meanings and relevance judgments are analyst inputs; quote binding does not validate interpretation.",
                            "Exact assertion values are compared only within a declared group/scope/key; unstated semantic contradictions are not detected.",
                            "Measured TF-IDF retrieval and source support are not model-answer quality or evidence of AI benefit.",
                            "A supplied locator or content hash does not establish authenticity, reachability, or current access authorization."]}


def cell(value: object) -> str:
    return str(value if value is not None else "UNKNOWN").replace("|", "\\|").replace("\n", "<br>")


def render(report: dict) -> str:
    label = "SYNTHETIC REHEARSAL" if report["synthetic"] else "SUPPLIED RECORDS — NOT VERIFIED FINDINGS"
    lines = [f"# Knowledge readiness — {report['snapshot_id']}", "", label, "", f"As of: {report['as_of']}", "",
             f"Sources: {report['source_count']}; active: {report['active_source_count']}; active fact conflicts: {len(report['conflicts'])}.", "",
             "## Query rehearsal", "", "| Query | Group | Current supported facts | Source-support outcome |", "|---|---|---|---|"]
    for query in report["queries"]:
        m = query["supported_facts"]
        lines.append(f"| {cell(query['query_id'])} | {query['group']} | {m['numerator']}/{m['denominator']} | {query['answer_support']} |")
    for query in report["queries"]:
        lines += ["", f"### {cell(query['query_id'])}: {cell(query['question'])}", ""]
        for name in ("precision", "recall"):
            m = query["retrieval_metrics"][name]
            shown = "UNKNOWN: relevance judgments unavailable" if m is None else f"{m['numerator']}/{m['denominator']} = {m['value'] if m['value'] is not None else 'UNDEFINED'}"
            lines.append(f"{name.capitalize()} over up to {query['top_k']} unique active-group documents: {shown}.")
        for fact in query["required_facts"]:
            lines += ["", f"**{cell(fact['scope'])} / {cell(fact['key'])}: {fact['state']}**"]
            for source in fact["corpus_support"]["sources"]:
                lines.append(f"- `{source['locator']}` — {cell(source['value'])}; issues: {cell(', '.join(source['source_issues']) or 'none observed')}. Quote: {cell(source['quote'])}")
    lines += ["", "## Preparation backlog", "", "| Subject | Problem | Owner | Next step |", "|---|---|---|---|"]
    for item in report["preparation_backlog"]:
        lines.append("| " + " | ".join(cell(item[k]) for k in ("subject", "problem", "owner", "next_step")) + " |")
    lines += ["", "## Interpretation limits", ""] + [f"- {item}" for item in report["limitations"]]
    return "\n".join(lines) + "\n"


def csv_text(value: object) -> str:
    """Spreadsheet-display encoding; exact values remain in report.json."""
    value = "UNKNOWN" if value is None else str(value)
    if value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n")):
        return "'" + value
    return value


def write_outputs(report: dict, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    (output / "report.md").write_text(render(report), encoding="utf-8")
    with (output / "preparation.csv").open("w", encoding="utf-8", newline="") as handle:
        fields = ("kind", "subject", "problem", "owner", "evidence", "next_step")
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for item in report["preparation_backlog"]:
            encoded = {**item, "evidence": json.dumps(item["evidence"], ensure_ascii=False)}
            writer.writerow({key: csv_text(value) for key, value in encoded.items()})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packet", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        report = assess(load(args.packet))
        write_outputs(report, args.out)
    except (DataError, OSError) as exc:
        print(f"INPUT/OUTPUT ERROR: {exc}", file=sys.stderr)
        return 2
    print(f"{report['snapshot_id']}: {report['source_count']} sources, {len(report['queries'])} queries, {len(report['conflicts'])} conflicts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
