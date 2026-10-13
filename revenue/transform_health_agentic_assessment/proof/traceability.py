#!/usr/bin/env python3
"""Deterministic evidence-traceability compiler for a draft legislative assessment.

This is a buyer-neutral synthetic proof for the existing Transform Health pursuit
carrier. A retrieval/agent layer may propose evidence candidates, but only exact,
source-bound verbatim spans can enter the draft assessment.
"""

from __future__ import annotations
import hashlib
import json
from typing import Any

SCHEMA_SOURCE = "tjlabs.transform_health.source_bundle.v1"
SCHEMA_ASSESSMENT = "tjlabs.transform_health.draft_assessment.v1"
LANGUAGES = {"en", "fr", "es"}
MAX_QUOTE_CHARS = 4000


class TraceabilityError(ValueError):
    pass


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _plain_str(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TraceabilityError(f"{field} must be a nonempty string")
    return value


def _plain_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TraceabilityError(f"{field} must be an integer")
    return value


def _plain_bool(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise TraceabilityError(f"{field} must be boolean")
    return value


def _prepare(source: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    if not isinstance(source, dict) or source.get("schema") != SCHEMA_SOURCE:
        raise TraceabilityError("source schema mismatch")

    framework = source.get("framework")
    documents = source.get("documents")
    candidates = source.get("candidates")
    if not isinstance(framework, list) or not framework:
        raise TraceabilityError("framework must be a nonempty list")
    if not isinstance(documents, list) or not documents:
        raise TraceabilityError("documents must be a nonempty list")
    if not isinstance(candidates, list):
        raise TraceabilityError("candidates must be a list")

    elements: dict[str, Any] = {}
    for idx, item in enumerate(framework):
        if not isinstance(item, dict):
            raise TraceabilityError(f"framework[{idx}] must be an object")
        element_id = _plain_str(item.get("id"), f"framework[{idx}].id")
        label = _plain_str(item.get("label"), f"framework[{idx}].label")
        if element_id in elements:
            raise TraceabilityError(f"duplicate framework id: {element_id}")
        elements[element_id] = {"id": element_id, "label": label}

    docs: dict[str, Any] = {}
    doc_receipts: list[dict[str, Any]] = []
    for idx, doc in enumerate(documents):
        if not isinstance(doc, dict):
            raise TraceabilityError(f"documents[{idx}] must be an object")
        doc_id = _plain_str(doc.get("id"), f"documents[{idx}].id")
        if doc_id in docs:
            raise TraceabilityError(f"duplicate document id: {doc_id}")
        language = _plain_str(doc.get("language"), f"documents[{idx}].language")
        if language not in LANGUAGES:
            raise TraceabilityError(f"unsupported language for {doc_id}: {language}")
        machine_readable = _plain_bool(doc.get("machine_readable"), f"documents[{idx}].machine_readable")
        pages = doc.get("pages")
        if not isinstance(pages, list) or not pages:
            raise TraceabilityError(f"documents[{idx}].pages must be a nonempty list")
        page_map: dict[int, dict[str, Any]] = {}
        normalized_pages: list[dict[str, Any]] = []
        for pidx, page in enumerate(pages):
            if not isinstance(page, dict):
                raise TraceabilityError(f"{doc_id}.pages[{pidx}] must be an object")
            number = _plain_int(page.get("number"), f"{doc_id}.pages[{pidx}].number")
            if number <= 0 or number in page_map:
                raise TraceabilityError(f"{doc_id} has invalid/duplicate page number {number}")
            text = page.get("text")
            if not isinstance(text, str):
                raise TraceabilityError(f"{doc_id}.page[{number}].text must be a string")
            if not machine_readable and text:
                raise TraceabilityError(f"{doc_id} is non-machine-readable but contains extracted text")
            normalized = {"number": number, "text": text}
            normalized["sha256"] = _sha({"number": number, "text": text})
            page_map[number] = normalized
            normalized_pages.append(normalized)
        normalized_pages.sort(key=lambda p: p["number"])
        digest_payload = {
            "id": doc_id,
            "language": language,
            "machine_readable": machine_readable,
            "pages": [{"number": p["number"], "text": p["text"]} for p in normalized_pages],
        }
        doc_sha = _sha(digest_payload)
        docs[doc_id] = {**digest_payload, "sha256": doc_sha, "page_map": page_map}
        doc_receipts.append(
            {
                "document_id": doc_id,
                "language": language,
                "machine_readable": machine_readable,
                "document_sha256": doc_sha,
                "status": "READY" if machine_readable else "OCR_REQUIRED",
            }
        )

    return elements, docs, doc_receipts


def compile_assessment(source: dict[str, Any]) -> dict[str, Any]:
    elements, docs, document_receipts = _prepare(source)
    candidates = source["candidates"]
    evidence_by_element: dict[str, list[dict[str, Any]]] = {key: [] for key in elements}
    seen_candidate_keys: set[tuple[Any, ...]] = set()

    for idx, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            raise TraceabilityError(f"candidates[{idx}] must be an object")
        element_id = _plain_str(candidate.get("element_id"), f"candidates[{idx}].element_id")
        doc_id = _plain_str(candidate.get("document_id"), f"candidates[{idx}].document_id")
        if element_id not in elements:
            raise TraceabilityError(f"unknown framework element: {element_id}")
        if doc_id not in docs:
            raise TraceabilityError(f"unknown document: {doc_id}")
        doc = docs[doc_id]
        if not doc["machine_readable"]:
            raise TraceabilityError(f"candidate cites OCR_REQUIRED document: {doc_id}")
        page_number = _plain_int(candidate.get("page"), f"candidates[{idx}].page")
        if page_number not in doc["page_map"]:
            raise TraceabilityError(f"unknown page {page_number} in {doc_id}")
        page = doc["page_map"][page_number]

        start = _plain_int(candidate.get("start"), f"candidates[{idx}].start")
        end = _plain_int(candidate.get("end"), f"candidates[{idx}].end")
        quote = _plain_str(candidate.get("quote"), f"candidates[{idx}].quote")
        if start < 0 or end <= start or end > len(page["text"]):
            raise TraceabilityError(f"invalid offsets in candidate {idx}")
        if len(quote) > MAX_QUOTE_CHARS:
            raise TraceabilityError(f"candidate {idx} quote exceeds maximum length")
        if page["text"][start:end] != quote:
            raise TraceabilityError(f"candidate {idx} is not an exact verbatim source span")
        if candidate.get("page_sha256") != page["sha256"]:
            raise TraceabilityError(f"candidate {idx} page digest mismatch")
        if candidate.get("document_sha256") != doc["sha256"]:
            raise TraceabilityError(f"candidate {idx} document digest mismatch")

        key = (element_id, doc_id, page_number, start, end, quote)
        if key in seen_candidate_keys:
            raise TraceabilityError(f"duplicate evidence candidate at index {idx}")
        seen_candidate_keys.add(key)
        evidence_id = _sha(
            {
                "element_id": element_id,
                "document_id": doc_id,
                "document_sha256": doc["sha256"],
                "page": page_number,
                "page_sha256": page["sha256"],
                "start": start,
                "end": end,
                "quote": quote,
            }
        )
        evidence_by_element[element_id].append(
            {
                "evidence_id": evidence_id,
                "document_id": doc_id,
                "document_sha256": doc["sha256"],
                "language": doc["language"],
                "page": page_number,
                "page_sha256": page["sha256"],
                "start": start,
                "end": end,
                "quote": quote,
                "verbatim": True,
            }
        )

    corpus_complete = all(item["machine_readable"] for item in document_receipts)
    step2: list[dict[str, Any]] = []
    step3: list[dict[str, Any]] = []
    for element_id in sorted(elements):
        evidence = sorted(
            evidence_by_element[element_id],
            key=lambda e: (e["document_id"], e["page"], e["start"], e["end"], e["evidence_id"]),
        )
        step2.append({"element_id": element_id, "label": elements[element_id]["label"], "evidence": evidence})
        if evidence:
            status = "IDENTIFIED_DRAFT"
        elif corpus_complete:
            status = "NOT_IDENTIFIED_DRAFT"
        else:
            status = "HOLD_INCOMPLETE_CORPUS"
        step3.append(
            {
                "element_id": element_id,
                "status": status,
                "evidence_count": len(evidence),
                "evidence_ids": [item["evidence_id"] for item in evidence],
            }
        )

    assessment: dict[str, Any] = {
        "schema": SCHEMA_ASSESSMENT,
        "state": "DRAFT_HUMAN_REVIEW_REQUIRED",
        "corpus_complete": corpus_complete,
        "document_receipts": sorted(document_receipts, key=lambda d: d["document_id"]),
        "step2": step2,
        "step3": step3,
        "authority": {
            "legal_interpretation_authorized": False,
            "legal_findings_authorized": False,
            "human_review_required": True,
            "publication_authorized": False,
            "generated_legislative_text_allowed": False,
        },
    }
    assessment["receipt_sha256"] = _sha(assessment)
    return assessment


def verify_assessment(source: dict[str, Any], assessment: dict[str, Any]) -> bool:
    if not isinstance(assessment, dict):
        return False
    try:
        expected = compile_assessment(source)
    except TraceabilityError:
        return False
    return _canonical(expected) == _canonical(assessment)
