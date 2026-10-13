"""Fail-closed xTech|Search 10 qualification/readiness packet compiler.

The result is evidence organization for owner review. It never claims that the Army
has determined eligibility and never authorizes submission or consumes an entity's
one-submission slot.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
import hashlib
import json
import os
import stat
import re
from typing import Any, Iterable

INPUT_VERSION = "xtech.search10.qualification.input/v1"
SOURCES_VERSION = "xtech.search10.official-sources/v1"
REPORT_VERSION = "xtech.search10.qualification.report/v1"
UTC_FMT = "%Y-%m-%dT%H:%M:%SZ"
MAX_FILE_BYTES = 1_000_000
MAX_ROWS = 128
SAFE_INT = (1 << 53) - 1
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,191}$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
FACT_STATES = {"UNKNOWN", "CONFIRMED_TRUE", "CONFIRMED_FALSE"}
SUPPORT_OVERLAP = {"NONE", "POTENTIALLY_SAME", "SUBSTANTIALLY_SAME"}
SUPPORT_STATUS = {"FUNDED", "CURRENT", "PENDING_AWARD", "CLOSED_UNFUNDED"}
REQUIRED_FACTS = {
    "forProfitUSConcern",
    "independent",
    "sbirSmallBusinessRequirementsMet",
    "majorityQualifyingOwnershipControl",
    "employeeCountWithAffiliatesAtMost500",
    "oneSubmissionSlotAvailable",
}
EXPECTED_SOURCE_FACTSET_SHA256 = "6cc553ba8bfe05df1d85d42dd38506c01b3f4ce3e14e98d88ebcfc409fed91b3"
EXPECTED_SOURCE_RETRIEVED_AT = "2026-09-14T04:35:00Z"
EXPECTED_SOURCE_URLS = {
    "xtech-search10-competition": "https://xtech.army.mil/competition/xtechsearch10/",
    "army-sbir-search10-topic": "https://armysbir.army.mil/topics/xtechsearch-10-competition/",
    "xtech-search10-rfi": "https://xtech.army.mil/wp-content/uploads/2026/09/xTechSearch-10-Competition-RFI_Final-1.pdf",
}


class ContractError(ValueError):
    def __init__(self, code: str, detail: str = ""):
        self.code = code
        self.detail = detail
        super().__init__(code if not detail else f"{code}:{detail}")


def _pairs_no_duplicates(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ContractError("JSON_DUPLICATE_KEY", key)
        out[key] = value
    return out


def parse_json_strict(raw: str | bytes) -> Any:
    if isinstance(raw, bytes):
        try:
            raw = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ContractError("JSON_NOT_UTF8") from exc
    def reject(value: str) -> None:
        raise ContractError("JSON_NONFINITE", value)
    try:
        return json.loads(raw, object_pairs_hook=_pairs_no_duplicates, parse_constant=reject)
    except ContractError:
        raise
    except json.JSONDecodeError as exc:
        raise ContractError("JSON_INVALID", str(exc)) from exc


def canonical_json(value: Any) -> str:
    def check(node: Any, path: str = "$") -> Any:
        if node is None or isinstance(node, (str, bool)):
            return node
        if isinstance(node, int) and not isinstance(node, bool):
            if abs(node) > SAFE_INT:
                raise ContractError("UNSAFE_INTEGER", path)
            return node
        if isinstance(node, list):
            if len(node) > MAX_ROWS:
                raise ContractError("ARRAY_TOO_LARGE", path)
            return [check(item, f"{path}[]") for item in node]
        if type(node) is dict:
            return {str(key): check(item, f"{path}.{key}") for key, item in node.items()}
        raise ContractError("NON_JSON_VALUE", f"{path}:{type(node).__name__}")
    return json.dumps(check(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _exact(value: Any, keys: set[str], path: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise ContractError("EXPECTED_OBJECT", path)
    got = set(value)
    if got != keys:
        raise ContractError("OBJECT_SHAPE", f"{path}:missing={sorted(keys-got)},extra={sorted(got-keys)}")
    return value


def _text(value: Any, path: str, *, max_len: int = 192) -> str:
    if not isinstance(value, str) or not (1 <= len(value) <= max_len) or ID_RE.fullmatch(value) is None:
        raise ContractError("INVALID_TEXT", path)
    return value


def _utc(value: Any, path: str) -> datetime:
    if not isinstance(value, str):
        raise ContractError("INVALID_UTC", path)
    try:
        parsed = datetime.strptime(value, UTC_FMT).replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise ContractError("INVALID_UTC", path) from exc
    if parsed.strftime(UTC_FMT) != value:
        raise ContractError("NONCANONICAL_UTC", path)
    return parsed


def _utc_string(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).strftime(UTC_FMT)


def read_regular_json(path: str) -> Any:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise ContractError("INPUT_OPEN_FAILED", type(exc).__name__) from exc
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_FILE_BYTES:
            raise ContractError("INPUT_NOT_BOUNDED_REGULAR_FILE")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(fd, min(65536, MAX_FILE_BYTES + 1 - total))
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_FILE_BYTES:
                raise ContractError("INPUT_TOO_LARGE")
            chunks.append(chunk)
        after = os.fstat(fd)
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            raise ContractError("INPUT_GENERATION_CHANGED")
        try:
            visible = os.stat(path, follow_symlinks=False)
        except OSError as exc:
            raise ContractError("INPUT_PATH_CHANGED", type(exc).__name__) from exc
        if (visible.st_dev, visible.st_ino) != (after.st_dev, after.st_ino):
            raise ContractError("INPUT_PATH_REBOUND")
        return parse_json_strict(b"".join(chunks))
    finally:
        os.close(fd)


def _validate_sources(value: Any, now: datetime) -> dict[str, Any]:
    src = _exact(value, {"version", "retrievedAt", "sources", "facts"}, "sources")
    if src["version"] != SOURCES_VERSION:
        raise ContractError("SOURCE_VERSION_INVALID")
    if src["retrievedAt"] != EXPECTED_SOURCE_RETRIEVED_AT:
        raise ContractError("SOURCE_GENERATION_UNPINNED")
    retrieved = _utc(src["retrievedAt"], "sources.retrievedAt")
    if retrieved > now + timedelta(minutes=5):
        raise ContractError("SOURCE_FROM_FUTURE")
    if now - retrieved > timedelta(days=30):
        raise ContractError("SOURCE_TOO_OLD")
    sources = src["sources"]
    if not isinstance(sources, list) or len(sources) != len(EXPECTED_SOURCE_URLS):
        raise ContractError("SOURCES_INCOMPLETE")
    seen: set[str] = set()
    for idx, raw in enumerate(sources):
        row = _exact(raw, {"sourceId", "url", "authority", "retrievedAt"}, f"sources.sources[{idx}]")
        sid = _text(row["sourceId"], f"sources.sources[{idx}].sourceId")
        if sid in seen:
            raise ContractError("SOURCE_ID_DUPLICATE", sid)
        seen.add(sid)
        if sid not in EXPECTED_SOURCE_URLS or row["url"] != EXPECTED_SOURCE_URLS[sid]:
            raise ContractError("SOURCE_ID_URL_UNPINNED", sid)
        if row["retrievedAt"] != EXPECTED_SOURCE_RETRIEVED_AT:
            raise ContractError("SOURCE_ROW_GENERATION_UNPINNED", sid)
        if row["authority"] != "OFFICIAL_ARMY":
            raise ContractError("SOURCE_AUTHORITY_INVALID", sid)
        if not isinstance(row["url"], str) or not row["url"].startswith("https://"):
            raise ContractError("SOURCE_URL_INVALID", sid)
        row_retrieved = _utc(row["retrievedAt"], f"sources.sources[{idx}].retrievedAt")
        if row_retrieved > now + timedelta(minutes=5):
            raise ContractError("SOURCE_ROW_FROM_FUTURE", sid)
        if now - row_retrieved > timedelta(days=30):
            raise ContractError("SOURCE_ROW_TOO_OLD", sid)
    if seen != set(EXPECTED_SOURCE_URLS):
        raise ContractError("SOURCES_INCOMPLETE")
    facts = _exact(
        src["facts"],
        {"deadlineUtc", "whitePaperPages", "mandatoryTemplate", "rubricWeights", "semiFinalists", "semiFinalistPrizeUsd", "finalists", "finalistPrizeUsd", "finalsPrizesUsd", "phaseIUpperUsd", "employeeCeiling", "entityType", "similarFederalSupportRule", "oneSubmissionPerEligibleEntity"},
        "sources.facts",
    )
    if facts["deadlineUtc"] != "2026-10-19T21:00:00Z":
        raise ContractError("DEADLINE_FACT_MISMATCH")
    integer_expectations = {
        "whitePaperPages": 3,
        "semiFinalists": 50,
        "semiFinalistPrizeUsd": 5000,
        "finalists": 20,
        "finalistPrizeUsd": 20000,
        "phaseIUpperUsd": 300000,
        "employeeCeiling": 500,
    }
    for key, expected in integer_expectations.items():
        if isinstance(facts[key], bool) or facts[key] != expected:
            raise ContractError("SOURCE_FACT_MISMATCH", key)
    if facts["mandatoryTemplate"] is not True:
        raise ContractError("SOURCE_FACT_MISMATCH", "mandatoryTemplate")
    if facts["rubricWeights"] != {"introduction": 5, "armyBenefits": 25, "technicalApproach": 40, "commercialPotential": 25, "proposalQuality": 5}:
        raise ContractError("SOURCE_FACT_MISMATCH", "rubricWeights")
    if facts["finalsPrizesUsd"] != [200000, 100000, 50000]:
        raise ContractError("SOURCE_FACT_MISMATCH", "finalsPrizesUsd")
    if facts["entityType"] != "SMALL_INDEPENDENT_US_FOR_PROFIT":
        raise ContractError("SOURCE_FACT_MISMATCH", "entityType")
    if facts["oneSubmissionPerEligibleEntity"] is not True:
        raise ContractError("SOURCE_FACT_MISMATCH", "oneSubmissionPerEligibleEntity")
    if facts["similarFederalSupportRule"] != "NO_SUBSTANTIALLY_SAME_FUNDED_CURRENT_OR_PENDING_FEDERAL_PROPOSAL":
        raise ContractError("SOURCE_FACT_MISMATCH", "similarFederalSupportRule")
    if sha256_json(src["facts"]) != EXPECTED_SOURCE_FACTSET_SHA256:
        raise ContractError("SOURCE_FACTSET_HASH_MISMATCH")
    return src


def _validate_fact(raw: Any, path: str, now: datetime) -> tuple[str, bool]:
    fact = _exact(raw, {"state", "evidenceRef", "observedAt"}, path)
    if fact["state"] not in FACT_STATES:
        raise ContractError("FACT_STATE_INVALID", path)
    if fact["evidenceRef"] is not None:
        _text(fact["evidenceRef"], f"{path}.evidenceRef")
    observed = None if fact["observedAt"] is None else _utc(fact["observedAt"], f"{path}.observedAt")
    if fact["state"] == "UNKNOWN":
        if fact["evidenceRef"] is not None or observed is not None:
            raise ContractError("UNKNOWN_FACT_HAS_EVIDENCE", path)
        return "UNKNOWN", False
    if fact["evidenceRef"] is None or observed is None:
        raise ContractError("CONFIRMED_FACT_MISSING_EVIDENCE", path)
    fresh = observed <= now and now - observed <= timedelta(days=90)
    return fact["state"], fresh


def compile_packet(document: Any, sources: Any, *, as_of: datetime | None = None) -> dict[str, Any]:
    current = as_of or datetime.now(timezone.utc).replace(microsecond=0)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ContractError("AS_OF_MUST_BE_TIMEZONE_AWARE")
    current = current.astimezone(timezone.utc).replace(microsecond=0)
    validated_sources = _validate_sources(sources, current)
    doc = _exact(document, {"version", "entityRef", "entityFacts", "federalSupportCensus", "federalSupport", "commercialEvidence"}, "input")
    if doc["version"] != INPUT_VERSION:
        raise ContractError("INPUT_VERSION_INVALID")
    _text(doc["entityRef"], "input.entityRef")
    facts = _exact(doc["entityFacts"], REQUIRED_FACTS, "input.entityFacts")

    blockers: list[str] = []
    for name in sorted(REQUIRED_FACTS):
        state, fresh = _validate_fact(facts[name], f"input.entityFacts.{name}", current)
        if state == "CONFIRMED_FALSE":
            blockers.append(f"ENTITY_FACT_FALSE:{name}")
        elif state == "UNKNOWN" or not fresh:
            blockers.append(f"ENTITY_FACT_UNPROVEN_OR_STALE:{name}")

    census_state, census_fresh = _validate_fact(doc["federalSupportCensus"], "input.federalSupportCensus", current)
    if census_state != "CONFIRMED_TRUE" or not census_fresh:
        blockers.append("FEDERAL_SUPPORT_CENSUS_UNPROVEN_OR_STALE")

    support = doc["federalSupport"]
    if not isinstance(support, list) or len(support) > MAX_ROWS:
        raise ContractError("FEDERAL_SUPPORT_INVALID")
    seen_support: set[str] = set()
    normalized_support: list[dict[str, Any]] = []
    for idx, raw in enumerate(support):
        row = _exact(raw, {"recordId", "agencyRef", "status", "technologyOverlap", "evidenceRef", "observedAt"}, f"input.federalSupport[{idx}]")
        rid = _text(row["recordId"], f"input.federalSupport[{idx}].recordId")
        if rid in seen_support:
            raise ContractError("SUPPORT_RECORD_DUPLICATE", rid)
        seen_support.add(rid)
        _text(row["agencyRef"], f"input.federalSupport[{idx}].agencyRef")
        if row["status"] not in SUPPORT_STATUS:
            raise ContractError("SUPPORT_STATUS_INVALID", rid)
        if row["technologyOverlap"] not in SUPPORT_OVERLAP:
            raise ContractError("SUPPORT_OVERLAP_INVALID", rid)
        _text(row["evidenceRef"], f"input.federalSupport[{idx}].evidenceRef")
        observed = _utc(row["observedAt"], f"input.federalSupport[{idx}].observedAt")
        if observed > current or current - observed > timedelta(days=90):
            blockers.append(f"FEDERAL_SUPPORT_EVIDENCE_STALE:{rid}")
        if row["technologyOverlap"] == "SUBSTANTIALLY_SAME" and row["status"] in {"FUNDED", "CURRENT", "PENDING_AWARD"}:
            blockers.append(f"SUBSTANTIALLY_SAME_FEDERAL_SUPPORT:{rid}")
        elif row["technologyOverlap"] == "POTENTIALLY_SAME":
            blockers.append(f"FEDERAL_SUPPORT_REVIEW_REQUIRED:{rid}")
        normalized_support.append(row)

    commercial = doc["commercialEvidence"]
    if not isinstance(commercial, list) or len(commercial) > MAX_ROWS:
        raise ContractError("COMMERCIAL_EVIDENCE_INVALID")
    commercial_refs: set[str] = set()
    normalized_commercial: list[dict[str, Any]] = []
    for idx, raw in enumerate(commercial):
        row = _exact(raw, {"evidenceId", "kind", "claim", "evidenceRef", "observedAt"}, f"input.commercialEvidence[{idx}]")
        eid = _text(row["evidenceId"], f"input.commercialEvidence[{idx}].evidenceId")
        if eid in commercial_refs:
            raise ContractError("COMMERCIAL_EVIDENCE_DUPLICATE", eid)
        commercial_refs.add(eid)
        if row["kind"] not in {"PRODUCT_PROOF", "CUSTOMER_INTEREST", "PAID_TRACTION", "MARKET_RESEARCH"}:
            raise ContractError("COMMERCIAL_KIND_INVALID", eid)
        if not isinstance(row["claim"], str) or not (1 <= len(row["claim"]) <= 400):
            raise ContractError("COMMERCIAL_CLAIM_INVALID", eid)
        _text(row["evidenceRef"], f"input.commercialEvidence[{idx}].evidenceRef")
        _utc(row["observedAt"], f"input.commercialEvidence[{idx}].observedAt")
        normalized_commercial.append(row)

    if any(item.startswith("SUBSTANTIALLY_SAME_FEDERAL_SUPPORT") for item in blockers):
        state = "BLOCKED_FEDERAL_SUPPORT_COLLISION"
    elif any(item.startswith("FEDERAL_SUPPORT_REVIEW_REQUIRED") or item.startswith("FEDERAL_SUPPORT_EVIDENCE_STALE") for item in blockers):
        state = "BLOCKED_FEDERAL_SUPPORT_REVIEW"
    elif "FEDERAL_SUPPORT_CENSUS_UNPROVEN_OR_STALE" in blockers:
        state = "BLOCKED_FEDERAL_SUPPORT_CENSUS"
    elif blockers:
        state = "BLOCKED_OWNER_ENTITY_FACTS"
    else:
        state = "EVIDENCE_PACKET_COMPLETE_OWNER_REVIEW"

    core = {
        "version": REPORT_VERSION,
        "mode": "HISTORICAL_INTEGRITY_ONLY" if as_of is not None else "CURRENT_PROCESS_UTC",
        "evaluatedAt": _utc_string(current),
        "officialFactSetSha256": sha256_json(validated_sources["facts"]),
        "inputSha256": sha256_json({
            "version": doc["version"],
            "entityRef": doc["entityRef"],
            "entityFacts": doc["entityFacts"],
            "federalSupportCensus": doc["federalSupportCensus"],
            "federalSupport": sorted(normalized_support, key=lambda row: row["recordId"]),
            "commercialEvidence": sorted(normalized_commercial, key=lambda row: row["evidenceId"]),
        }),
        "state": state,
        "blockers": sorted(set(blockers)),
        "commercialEvidenceCount": len(commercial),
        "authority": {
            "armyEligibilityDetermined": False,
            "submissionAuthorized": False,
            "entitySlotConsumed": False,
            "termsAccepted": False,
            "armyContactAuthorized": False,
            "awardClaimed": False,
            "paymentClaimed": False,
            "revenueClaimed": False,
        },
    }
    return {**core, "receiptSha256": sha256_json(core)}
