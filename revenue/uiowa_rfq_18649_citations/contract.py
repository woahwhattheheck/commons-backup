"""Small, explicit input contract. References are identities, never title guesses."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any

SCHEMA = "uiowa.citation-packet.v1"
TRACE_SCHEMA = "uiowa.citation-trace.v1"
LABEL = "SYNTHETIC_DRAFT_NON_AUTHORITATIVE"
ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}\Z")
SHA = re.compile(r"[0-9a-f]{64}\Z")
GROUPS = {"ESS", "RIS", "IAM"}
DIMENSIONS = {"software", "security", "deployment", "ai_readiness"}
MAX_INPUT = 8 * 1024 * 1024


class CitationError(ValueError):
    pass


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2,
                       allow_nan=False) + "\n").encode("utf-8")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_json(path: Path) -> dict:
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise CitationError(f"Duplicate JSON key: {key}")
            out[key] = value
        return out
    def constant(token):
        raise CitationError(f"Non-finite JSON token: {token}")
    data = path.read_bytes()
    if len(data) > MAX_INPUT:
        raise CitationError("Input exceeds 8 MiB")
    return json.loads(data.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)


def text(value, where: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 20000:
        raise CitationError(f"{where}: expected nonempty text of at most 20000 characters")
    return value


def identifier(value, where: str) -> str:
    if not isinstance(value, str) or ID.fullmatch(value) is None:
        raise CitationError(f"{where}: invalid identifier")
    return value


def sha(value, where: str) -> str:
    if not isinstance(value, str) or SHA.fullmatch(value) is None:
        raise CitationError(f"{where}: invalid lowercase SHA-256")
    return value


def rows(value, where: str) -> list:
    if not isinstance(value, list) or len(value) > 10000:
        raise CitationError(f"{where}: expected bounded array")
    return value


def unique(items: list, key: str, where: str) -> dict:
    found = {}
    for item in items:
        name = identifier(item[key], f"{where}.{key}")
        if name in found:
            raise CitationError(f"{where}: duplicate {key} {name}")
        found[name] = item
    return found


def relative_path(value: str) -> PurePosixPath:
    text(value, "source.path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "\\" in value or ":" in value:
        raise CitationError("Source location must be a relative bundle path")
    if not path.parts or path.as_posix() != value or any(ord(c) < 32 for c in value):
        raise CitationError("Source location must be a canonical relative bundle path")
    return path


def validate_packet(packet: dict) -> None:
    if not isinstance(packet, dict) or packet.get("schema") != SCHEMA:
        raise CitationError("Unsupported citation packet schema")
    if packet.get("label") != LABEL:
        raise CitationError("This preparation kit requires an explicit synthetic-draft label")
    sha(packet["compiler_receipt_sha256"], "compiler_receipt_sha256")
    identifier(packet["generation"], "generation")
    for source in rows(packet["sources"], "sources"):
        for key in ("source_id", "version"):
            identifier(source[key], "source." + key)
        sha(source["sha256"], "source.sha256")
        text(source["title"], "source.title")
        relative_path(source["path"])
        for alias in rows(source.get("aliases", []), "source.aliases"):
            relative_path(alias)
        if source.get("superseded_by") is not None:
            identifier(source["superseded_by"], "source.superseded_by")
    findings = unique(rows(packet["findings"], "findings"), "finding_id", "findings")
    recommendations = unique(rows(packet["recommendations"], "recommendations"),
                             "recommendation_id", "recommendations")
    for finding in findings.values():
        if finding["kind"] not in {"strength", "gap", "open_question"}:
            raise CitationError("Unknown finding kind")
        if finding["group"] not in GROUPS or finding["dimension"] not in DIMENSIONS:
            raise CitationError("Unknown finding scope")
        text(finding["statement"], "finding.statement")
        text(finding["limits"], "finding.limits")
        refs = rows(finding["evidence_refs"], "finding.evidence_refs")
        if not refs:
            raise CitationError("Every finding needs a source reference, even when unresolved")
        for ref in refs:
            for key in ("source_id", "version", "segment_id"):
                identifier(ref[key], "reference." + key)
            sha(ref["sha256"], "reference.sha256")
            text(ref["locator"], "reference.locator")
            text(ref["quote"], "reference.quote")
    for rec in recommendations.values():
        for key in ("action", "rationale", "owner_role", "effort", "outcome_measure"):
            text(rec[key], "recommendation." + key)
        if rec["phase"] not in {"0-90 days", "90-180 days", "180+ days"}:
            raise CitationError("Unsupported relative roadmap phase")
        links = rows(rec["finding_ids"], "recommendation.finding_ids")
        if not links or len(set(links)) != len(links) or not set(links) <= findings.keys():
            raise CitationError("Recommendation has missing or duplicate finding references")
    for key, index in (("finding_ids", findings), ("recommendation_ids", recommendations)):
        links = rows(packet["executive_summary"][key], "executive_summary." + key)
        if len(links) != len(set(links)) or not set(links) <= index.keys():
            raise CitationError("Executive summary has missing or duplicate references")
