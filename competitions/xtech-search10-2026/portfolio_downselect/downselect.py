"""Fail-closed xTech|Search 10 cross-asset evidence down-selector.

This module organizes owner evidence. It does not predict sponsor scores, determine
legal eligibility, reserve a submission slot, obtain the sponsor template, or
authorize registration/submission.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
from types import MappingProxyType
from typing import Any, Iterable

PORTFOLIO_VERSION = "xtech.search10.portfolio/v1"
REPORT_VERSION = "xtech.search10.downselect.report/v1"
MAX_FILE_BYTES = 1_000_000
MAX_CANDIDATES = 16
MAX_CLAIMS_PER_CRITERION = 32
MAX_JSON_NODES = 20_000
MAX_JSON_DEPTH = 48
SAFE_INT = (1 << 53) - 1
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,191}$")
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

CRITERIA_WEIGHTS = MappingProxyType(
    {
        "introduction": 5,
        "armyBenefits": 25,
        "technicalApproach": 40,
        "commercialPotential": 25,
        "proposalQuality": 5,
    }
)
CLAIM_STATES = frozenset({"EVIDENCED", "PROPOSED", "OWNER_REQUIRED", "FORBIDDEN"})
STRONG_TRACTION_KINDS = frozenset({
    "CUSTOMER_PAYMENT",
    "CUSTOMER_CONTRACT",
    "CUSTOMER_DEPLOYMENT",
    "EXTERNAL_ADOPTION",
})
SUPPORTING_TRACTION_KINDS = frozenset({
    "CUSTOMER_PILOT",
    "CUSTOMER_LOI",
})
EXTERNAL_TRACTION_KINDS = STRONG_TRACTION_KINDS | SUPPORTING_TRACTION_KINDS
INTERNAL_ONLY_TRACTION_KINDS = frozenset({
    "REPO_ACTIVITY",
    "GITHUB_STARS",
    "RELEASE_DOWNLOADS",
    "INTERNAL_DEMO",
    "INTERNAL_TESTS",
    "COMMIT_COUNT",
})
PRIORITY_AREAS = frozenset({
    "ALL_ARMS_MANEUVER",
    "C2_COUNTER_C2_NETWORKS",
    "FORMATION_BASED_LAYERED_PROTECTION",
    "ADAPTIVE_SUSTAINMENT",
    "CROSS_DOMAIN_FIRES",
    "OTHER_VALID_ARMY_NEED",
})
GLOBAL_FACT_STATES = frozenset({"UNKNOWN", "CONFIRMED_TRUE", "CONFIRMED_FALSE"})
SUPPORT_STATES = frozenset({"UNKNOWN", "CLEAR", "BLOCKED"})
SLOT_STATES = frozenset({"UNKNOWN", "AVAILABLE", "CONSUMED_OR_RESERVED"})
TEMPLATE_STATES = frozenset({"UNKNOWN", "BOUND", "MISMATCH"})
SOURCE_CURRENTNESS_STATES = frozenset({"UNKNOWN", "CURRENT", "STALE"})
OVERLAP_STATES = frozenset({"UNKNOWN", "NONE", "POTENTIALLY_SAME", "SUBSTANTIALLY_SAME"})
EXCLUSIVITY_STATES = frozenset({"UNKNOWN", "NOT_EXCLUSIVE", "EXCLUSIVE"})
EVIDENCE_CLASSES = frozenset({"REPO", "OWNER", "PROVIDER", "EXTERNAL_COUNTERPARTY"})

# Hard-coded from the current official competition announcement/RFI and kept
# separate from any candidate-controlled packet. Containers exposed in reports
# are freshly materialized so consumers cannot mutate later scoring policy.
OFFICIAL_POLICY_RETRIEVED_AT_UTC = "2026-09-17T20:00:00Z"
OFFICIAL_COMPETITION_URL = "https://xtech.army.mil/competition/xtechsearch10/"
OFFICIAL_RFI_URL = "https://xtech.army.mil/wp-content/uploads/2026/09/xTechSearch-10-Competition-RFI_Final-1.pdf"
OFFICIAL_DEADLINE_UTC = "2026-10-19T21:00:00Z"
OFFICIAL_WHITEPAPER_PAGES = 3
OFFICIAL_MANDATORY_TEMPLATE = True
OFFICIAL_ONE_SUBMISSION_PER_ENTITY = True
OFFICIAL_PRIORITY_AREAS = tuple(sorted(PRIORITY_AREAS - {"OTHER_VALID_ARMY_NEED"}))


def _official_constraint_snapshot() -> dict[str, Any]:
    return {
        "retrievedAtUtc": OFFICIAL_POLICY_RETRIEVED_AT_UTC,
        "sourceUrls": [OFFICIAL_COMPETITION_URL, OFFICIAL_RFI_URL],
        "deadlineUtc": OFFICIAL_DEADLINE_UTC,
        "oneSubmissionPerEligibleEntity": OFFICIAL_ONE_SUBMISSION_PER_ENTITY,
        "whitePaperPages": OFFICIAL_WHITEPAPER_PAGES,
        "mandatoryTemplate": OFFICIAL_MANDATORY_TEMPLATE,
        "weights": dict(CRITERIA_WEIGHTS),
        "priorityAreas": list(OFFICIAL_PRIORITY_AREAS),
    }


class ContractError(ValueError):
    def __init__(self, code: str, detail: str = ""):
        self.code = code
        self.detail = detail
        super().__init__(code if not detail else f"{code}:{detail}")


@dataclass(frozen=True)
class CandidateProjection:
    candidateId: str
    sourceIdentity: str
    readinessBasisPoints: int
    criterionBasisPoints: dict[str, int]
    hardBlockers: list[str]
    externalTractionEvidenceCount: int
    strongCommercialTractionEvidenceCount: int


def _pairs_no_duplicates(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ContractError("JSON_DUPLICATE_KEY", key)
        out[key] = value
    return out


def _reject_float(value: str) -> None:
    raise ContractError("JSON_FLOAT_FORBIDDEN", value)


def _parse_int(value: str) -> int:
    digits = value[1:] if value.startswith("-") else value
    if len(digits) > 16:
        raise ContractError("UNSAFE_INTEGER")
    number = int(value)
    if abs(number) > SAFE_INT:
        raise ContractError("UNSAFE_INTEGER")
    return number


def parse_json_strict(raw: bytes | str) -> Any:
    if isinstance(raw, bytes):
        if len(raw) > MAX_FILE_BYTES:
            raise ContractError("JSON_TOO_LARGE")
        try:
            text = raw.decode("utf-8", "strict")
        except UnicodeDecodeError as exc:
            raise ContractError("JSON_NOT_UTF8") from exc
    elif isinstance(raw, str):
        try:
            encoded = raw.encode("utf-8", "strict")
        except UnicodeEncodeError as exc:
            raise ContractError("JSON_NOT_UTF8") from exc
        if len(encoded) > MAX_FILE_BYTES:
            raise ContractError("JSON_TOO_LARGE")
        text = raw
    else:
        raise TypeError("parse_json_strict accepts bytes or str")
    try:
        value = json.loads(
            text,
            object_pairs_hook=_pairs_no_duplicates,
            parse_float=_reject_float,
            parse_int=_parse_int,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ContractError("JSON_NONFINITE", value)
            ),
        )
    except ContractError:
        raise
    except (json.JSONDecodeError, ValueError, RecursionError) as exc:
        raise ContractError("JSON_INVALID") from exc
    _bound_structure(value)
    return value


def _bound_structure(value: Any) -> None:
    stack: list[tuple[Any, int]] = [(value, 0)]
    nodes = 0
    while stack:
        node, depth = stack.pop()
        nodes += 1
        if nodes > MAX_JSON_NODES:
            raise ContractError("JSON_TOO_MANY_NODES")
        if depth > MAX_JSON_DEPTH:
            raise ContractError("JSON_TOO_DEEP")
        if isinstance(node, str):
            try:
                node.encode("utf-8", "strict")
            except UnicodeEncodeError as exc:
                raise ContractError("JSON_NOT_UTF8") from exc
        elif isinstance(node, list):
            stack.extend((item, depth + 1) for item in node)
        elif type(node) is dict:
            for key, item in node.items():
                if not isinstance(key, str):
                    raise ContractError("JSON_KEY_NOT_STRING")
                stack.append((key, depth + 1))
                stack.append((item, depth + 1))
        elif node is None or isinstance(node, (bool, int)):
            continue
        else:
            raise ContractError("JSON_TYPE_FORBIDDEN", type(node).__name__)


def canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        )
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise ContractError("NOT_CANONICALIZABLE") from exc


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def read_regular_json(path: str | os.PathLike[str]) -> Any:
    supplied = Path(path)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        before_lstat = supplied.lstat()
    except OSError as exc:
        raise ContractError("INPUT_STAT_FAILED", type(exc).__name__) from exc
    if stat.S_ISLNK(before_lstat.st_mode):
        raise ContractError("INPUT_SYMLINK_FORBIDDEN")
    if not stat.S_ISREG(before_lstat.st_mode):
        raise ContractError("INPUT_NOT_REGULAR")
    try:
        fd = os.open(supplied, flags)
    except OSError as exc:
        raise ContractError("INPUT_OPEN_FAILED", type(exc).__name__) from exc

    primary_error = False
    try:
        try:
            opened = os.fstat(fd)
        except OSError as exc:
            raise ContractError("INPUT_FSTAT_FAILED", type(exc).__name__) from exc
        if not stat.S_ISREG(opened.st_mode):
            raise ContractError("INPUT_NOT_REGULAR")
        if (opened.st_dev, opened.st_ino) != (before_lstat.st_dev, before_lstat.st_ino):
            raise ContractError("INPUT_GENERATION_CHANGED_BEFORE_READ")
        if opened.st_size > MAX_FILE_BYTES:
            raise ContractError("INPUT_TOO_LARGE")
        chunks: list[bytes] = []
        total = 0
        while True:
            try:
                chunk = os.read(fd, 65536)
            except OSError as exc:
                raise ContractError("INPUT_READ_FAILED", type(exc).__name__) from exc
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_FILE_BYTES:
                raise ContractError("INPUT_TOO_LARGE")
            chunks.append(chunk)
        try:
            after = os.fstat(fd)
        except OSError as exc:
            raise ContractError("INPUT_FSTAT_FAILED", type(exc).__name__) from exc
        if (
            (opened.st_dev, opened.st_ino) != (after.st_dev, after.st_ino)
            or opened.st_size != after.st_size
            or getattr(opened, "st_mtime_ns", int(opened.st_mtime * 1e9))
            != getattr(after, "st_mtime_ns", int(after.st_mtime * 1e9))
        ):
            raise ContractError("INPUT_CHANGED_DURING_READ")
        return parse_json_strict(b"".join(chunks))
    except BaseException:
        primary_error = True
        raise
    finally:
        try:
            os.close(fd)
        except OSError as exc:
            if not primary_error:
                raise ContractError("INPUT_CLOSE_FAILED", type(exc).__name__) from exc


def _exact(value: Any, keys: set[str], path: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise ContractError("EXPECTED_OBJECT", path)
    got = set(value)
    if got != keys:
        raise ContractError(
            "OBJECT_SHAPE",
            f"{path}:missing={sorted(keys-got)},extra={sorted(got-keys)}",
        )
    return value


def _id(value: Any, path: str) -> str:
    if not isinstance(value, str) or ID_RE.fullmatch(value) is None:
        raise ContractError("INVALID_ID", path)
    return value


def _evidence_ref(value: Any, path: str) -> str:
    if not isinstance(value, str) or not (1 <= len(value) <= 512):
        raise ContractError("INVALID_EVIDENCE_REF", path)
    if any(ord(ch) < 0x20 for ch in value):
        raise ContractError("INVALID_EVIDENCE_REF", path)
    return value


def _claim_text(value: Any, path: str) -> str:
    if not isinstance(value, str) or not (1 <= len(value) <= 1200):
        raise ContractError("INVALID_CLAIM_TEXT", path)
    if any(ord(ch) < 0x20 and ch not in {"\t"} for ch in value):
        raise ContractError("INVALID_CLAIM_TEXT", path)
    return value


def _repo_name(value: Any, path: str) -> str:
    text = _evidence_ref(value, path)
    if REPO_RE.fullmatch(text) is None:
        raise ContractError("INVALID_SOURCE_REPO", path)
    owner, name = text.split("/", 1)
    if owner in {".", ".."} or name in {".", ".."} or name.casefold().endswith(".git"):
        raise ContractError("INVALID_SOURCE_REPO", path)
    return f"{owner.casefold()}/{name.casefold()}"


def _repo_path(value: Any, path: str) -> str:
    text = _evidence_ref(value, path)
    if text.startswith("/") or "\\" in text:
        raise ContractError("INVALID_REPO_PATH", path)
    parts = text.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ContractError("INVALID_REPO_PATH", path)
    return text


def _evidence_registry(raw: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(raw, list) or len(raw) > MAX_JSON_NODES:
        raise ContractError("INVALID_EVIDENCE_REGISTRY")
    registry: dict[str, dict[str, Any]] = {}
    for index, value in enumerate(raw):
        path = f"$.evidenceRecords[{index}]"
        row = _exact(
            value,
            {
                "evidenceId",
                "binding",
                "sourceClass",
                "repo",
                "commit",
                "path",
                "locator",
                "sha256",
            },
            path,
        )
        evidence_id = _id(row["evidenceId"], path + ".evidenceId")
        if evidence_id in registry:
            raise ContractError("DUPLICATE_EVIDENCE_ID", evidence_id)
        binding = _evidence_ref(row["binding"], path + ".binding")
        source_class = row["sourceClass"]
        if source_class not in EVIDENCE_CLASSES:
            raise ContractError("INVALID_EVIDENCE_CLASS", evidence_id)
        normalized = dict(row)
        normalized["evidenceId"] = evidence_id
        normalized["binding"] = binding
        if source_class == "REPO":
            normalized["repo"] = _repo_name(row["repo"], path + ".repo")
            commit = row["commit"]
            if not isinstance(commit, str) or SHA40_RE.fullmatch(commit) is None:
                raise ContractError("INVALID_EVIDENCE_COMMIT", evidence_id)
            normalized["commit"] = commit
            normalized["path"] = _repo_path(row["path"], path + ".path")
            if row["locator"] is not None or row["sha256"] is not None:
                raise ContractError("REPO_EVIDENCE_VARIANT_MISMATCH", evidence_id)
        else:
            if row["repo"] is not None or row["commit"] is not None or row["path"] is not None:
                raise ContractError("ARTIFACT_EVIDENCE_VARIANT_MISMATCH", evidence_id)
            normalized["locator"] = _evidence_ref(row["locator"], path + ".locator")
            digest = row["sha256"]
            if not isinstance(digest, str) or SHA256_RE.fullmatch(digest) is None:
                raise ContractError("INVALID_EVIDENCE_SHA256", evidence_id)
            normalized["sha256"] = digest
        registry[evidence_id] = normalized

    external_artifacts: dict[str, str] = {}
    for row in registry.values():
        if row["sourceClass"] != "EXTERNAL_COUNTERPARTY":
            continue
        parts = row["binding"].split(":")
        candidate_id = parts[1] if len(parts) >= 3 and parts[0] == "candidate" else ""
        identity = row["sha256"]
        prior_candidate = external_artifacts.get(identity)
        if prior_candidate is not None and prior_candidate != candidate_id:
            raise ContractError("EXTERNAL_EVIDENCE_CANDIDATE_REPLAY", row["evidenceId"])
        external_artifacts[identity] = candidate_id
    return registry


def _consume_evidence(
    evidence_ref: Any,
    *,
    binding: str,
    allowed_classes: set[str],
    registry: dict[str, dict[str, Any]],
    used: set[str],
    candidate_source: dict[str, str] | None = None,
) -> dict[str, Any]:
    evidence_id = _id(evidence_ref, binding + ".evidenceRef")
    row = registry.get(evidence_id)
    if row is None:
        raise ContractError("EVIDENCE_REF_MISSING", evidence_id)
    if evidence_id in used:
        raise ContractError("EVIDENCE_RECORD_REUSED", evidence_id)
    if row["binding"] != binding:
        raise ContractError("EVIDENCE_BINDING_MISMATCH", evidence_id)
    if row["sourceClass"] not in allowed_classes:
        raise ContractError("EVIDENCE_CLASS_MISMATCH", evidence_id)
    if row["sourceClass"] == "REPO" and candidate_source is not None:
        if row["repo"] != candidate_source["repo"] or row["commit"] != candidate_source["commit"]:
            raise ContractError("EVIDENCE_CANDIDATE_GENERATION_MISMATCH", evidence_id)
        base_path = candidate_source["path"].rstrip("/")
        evidence_path = row["path"]
        if evidence_path != base_path and not evidence_path.startswith(base_path + "/"):
            raise ContractError("EVIDENCE_CANDIDATE_PATH_MISMATCH", evidence_id)
    used.add(evidence_id)
    return row


def _fact(
    value: Any,
    path: str,
    *,
    binding: str,
    allowed_classes: set[str],
    registry: dict[str, dict[str, Any]],
    used: set[str],
) -> tuple[str, str | None]:
    obj = _exact(value, {"state", "evidenceRef"}, path)
    state = obj["state"]
    if state not in GLOBAL_FACT_STATES:
        raise ContractError("INVALID_FACT_STATE", path)
    evidence = obj["evidenceRef"]
    if state == "UNKNOWN":
        if evidence is not None:
            raise ContractError("UNKNOWN_WITH_EVIDENCE", path)
    else:
        _consume_evidence(
            evidence,
            binding=binding,
            allowed_classes=allowed_classes,
            registry=registry,
            used=used,
        )
    return state, evidence


def _enum_fact(
    value: Any,
    path: str,
    allowed: set[str],
    *,
    ready: str,
    binding: str,
    allowed_classes: set[str],
    registry: dict[str, dict[str, Any]],
    used: set[str],
) -> tuple[str, str | None, bool]:
    obj = _exact(value, {"state", "evidenceRef"}, path)
    state = obj["state"]
    if state not in allowed:
        raise ContractError("INVALID_GATE_STATE", path)
    evidence = obj["evidenceRef"]
    if state == "UNKNOWN":
        if evidence is not None:
            raise ContractError("UNKNOWN_WITH_EVIDENCE", path)
    else:
        _consume_evidence(
            evidence,
            binding=binding,
            allowed_classes=allowed_classes,
            registry=registry,
            used=used,
        )
    return state, evidence, state == ready


def _criterion_projection(
    items: Any,
    path: str,
    *,
    candidate_id: str,
    candidate_source: dict[str, str],
    registry: dict[str, dict[str, Any]],
    used: set[str],
    seen_claim_ids: set[str],
) -> tuple[int, list[str]]:
    if not isinstance(items, list) or not items or len(items) > MAX_CLAIMS_PER_CRITERION:
        raise ContractError("INVALID_CLAIM_LIST", path)
    evidenced = 0
    blockers: list[str] = []
    for index, raw in enumerate(items):
        item_path = f"{path}[{index}]"
        item = _exact(raw, {"claimId", "text", "state", "evidenceRef"}, item_path)
        claim_id = _id(item["claimId"], item_path + ".claimId")
        _claim_text(item["text"], item_path + ".text")
        if claim_id in seen_claim_ids:
            raise ContractError("DUPLICATE_CLAIM_ID", claim_id)
        seen_claim_ids.add(claim_id)
        state = item["state"]
        if state not in CLAIM_STATES:
            raise ContractError("INVALID_CLAIM_STATE", item_path)
        evidence = item["evidenceRef"]
        if state == "EVIDENCED":
            _consume_evidence(
                evidence,
                binding=f"candidate:{candidate_id}:claim:{claim_id}",
                allowed_classes=EVIDENCE_CLASSES,
                registry=registry,
                used=used,
                candidate_source=candidate_source,
            )
            evidenced += 1
        else:
            if evidence is not None:
                raise ContractError("UNEVIDENCED_CLAIM_HAS_REF", item_path)
            blockers.append(f"claim:{claim_id}:{state}")
    return (evidenced * 10_000) // len(items), blockers


def _candidate(
    raw: Any,
    index: int,
    *,
    registry: dict[str, dict[str, Any]],
    used: set[str],
) -> CandidateProjection:
    path = f"$.candidates[{index}]"
    obj = _exact(
        raw,
        {
            "candidateId",
            "source",
            "priorityArea",
            "sourceCurrentness",
            "usamrdcExclusive",
            "federalSupportOverlap",
            "criteria",
            "demonstratedMetrics",
            "transitionPath",
            "traction",
        },
        path,
    )
    candidate_id = _id(obj["candidateId"], path + ".candidateId")
    source = _exact(obj["source"], {"repo", "commit", "path"}, path + ".source")
    repo = _repo_name(source["repo"], path + ".source.repo")
    commit = source["commit"]
    if not isinstance(commit, str) or SHA40_RE.fullmatch(commit) is None:
        raise ContractError("INVALID_SOURCE_COMMIT", candidate_id)
    source_path = _repo_path(source["path"], path + ".source.path")
    candidate_source = {"repo": repo, "commit": commit, "path": source_path}

    priority = obj["priorityArea"]
    if priority not in PRIORITY_AREAS:
        raise ContractError("INVALID_PRIORITY_AREA", candidate_id)

    source_currentness = _exact(
        obj["sourceCurrentness"],
        {"state", "evidenceRef"},
        path + ".sourceCurrentness",
    )
    source_currentness_state = source_currentness["state"]
    if source_currentness_state not in SOURCE_CURRENTNESS_STATES:
        raise ContractError("INVALID_SOURCE_CURRENTNESS", candidate_id)
    if source_currentness_state == "UNKNOWN":
        if source_currentness["evidenceRef"] is not None:
            raise ContractError("UNKNOWN_WITH_EVIDENCE", path + ".sourceCurrentness")
    else:
        _consume_evidence(
            source_currentness["evidenceRef"],
            binding=f"candidate:{candidate_id}:sourceCurrentness",
            allowed_classes={"OWNER"},
            registry=registry,
            used=used,
        )

    exclusivity = _exact(
        obj["usamrdcExclusive"], {"state", "evidenceRef"}, path + ".usamrdcExclusive"
    )
    exclusivity_state = exclusivity["state"]
    if exclusivity_state not in EXCLUSIVITY_STATES:
        raise ContractError("INVALID_USAMRDC_STATE", candidate_id)
    if exclusivity_state == "UNKNOWN":
        if exclusivity["evidenceRef"] is not None:
            raise ContractError("UNKNOWN_WITH_EVIDENCE", path + ".usamrdcExclusive")
    else:
        _consume_evidence(
            exclusivity["evidenceRef"],
            binding=f"candidate:{candidate_id}:usamrdcExclusive",
            allowed_classes={"OWNER"},
            registry=registry,
            used=used,
        )

    overlap_gate = _exact(
        obj["federalSupportOverlap"],
        {"state", "evidenceRef"},
        path + ".federalSupportOverlap",
    )
    overlap = overlap_gate["state"]
    if overlap not in OVERLAP_STATES:
        raise ContractError("INVALID_SUPPORT_OVERLAP", candidate_id)
    if overlap == "UNKNOWN":
        if overlap_gate["evidenceRef"] is not None:
            raise ContractError("UNKNOWN_WITH_EVIDENCE", path + ".federalSupportOverlap")
    else:
        _consume_evidence(
            overlap_gate["evidenceRef"],
            binding=f"candidate:{candidate_id}:federalSupportOverlap",
            allowed_classes={"OWNER"},
            registry=registry,
            used=used,
        )

    criteria = _exact(obj["criteria"], set(CRITERIA_WEIGHTS), path + ".criteria")
    criterion_bp: dict[str, int] = {}
    blockers: list[str] = []
    seen_claim_ids: set[str] = set()
    total_bp = 0
    for criterion, weight in CRITERIA_WEIGHTS.items():
        coverage_bp, claim_blockers = _criterion_projection(
            criteria[criterion],
            f"{path}.criteria.{criterion}",
            candidate_id=candidate_id,
            candidate_source=candidate_source,
            registry=registry,
            used=used,
            seen_claim_ids=seen_claim_ids,
        )
        weighted_bp = (coverage_bp * weight) // 100
        criterion_bp[criterion] = weighted_bp
        total_bp += weighted_bp
        blockers.extend(claim_blockers)

    for auxiliary_name in ("demonstratedMetrics", "transitionPath"):
        _, auxiliary_blockers = _criterion_projection(
            obj[auxiliary_name],
            f"{path}.{auxiliary_name}",
            candidate_id=candidate_id,
            candidate_source=candidate_source,
            registry=registry,
            used=used,
            seen_claim_ids=seen_claim_ids,
        )
        blockers.extend(auxiliary_blockers)

    traction = obj["traction"]
    if not isinstance(traction, list) or len(traction) > 32:
        raise ContractError("INVALID_TRACTION_LIST", candidate_id)
    external_count = 0
    strong_traction_count = 0
    traction_ids: set[str] = set()
    for tindex, raw_traction in enumerate(traction):
        tpath = f"{path}.traction[{tindex}]"
        row = _exact(raw_traction, {"evidenceId", "kind", "evidenceRef"}, tpath)
        evidence_id = _id(row["evidenceId"], tpath + ".evidenceId")
        if evidence_id in traction_ids:
            raise ContractError("DUPLICATE_TRACTION_ID", evidence_id)
        traction_ids.add(evidence_id)
        kind = row["kind"]
        if kind in INTERNAL_ONLY_TRACTION_KINDS:
            if row["evidenceRef"] is not None:
                raise ContractError("INTERNAL_TRACTION_HAS_EVIDENCE_REF", evidence_id)
            blockers.append(f"fake_traction:{evidence_id}:{kind}")
            continue
        if kind not in EXTERNAL_TRACTION_KINDS:
            raise ContractError("UNKNOWN_TRACTION_KIND", str(kind))
        _consume_evidence(
            row["evidenceRef"],
            binding=f"candidate:{candidate_id}:traction:{evidence_id}",
            allowed_classes={"EXTERNAL_COUNTERPARTY"},
            registry=registry,
            used=used,
        )
        external_count += 1
        if kind in STRONG_TRACTION_KINDS:
            strong_traction_count += 1

    if source_currentness_state != "CURRENT":
        blockers.append(f"source_generation:{source_currentness_state}")
    if external_count == 0:
        blockers.append("commercial_traction:missing_external_evidence")
    if strong_traction_count == 0:
        blockers.append("commercial_traction:missing_strong_external_evidence")
    if overlap != "NONE":
        blockers.append(f"federal_support_overlap:{overlap}")
    if exclusivity_state != "NOT_EXCLUSIVE":
        blockers.append(f"scope:USAMRDC_EXCLUSIVE:{exclusivity_state}")
    return CandidateProjection(
        candidateId=candidate_id,
        sourceIdentity=f"{repo}@{commit}:{source_path}",
        readinessBasisPoints=total_bp,
        criterionBasisPoints=criterion_bp,
        hardBlockers=sorted(set(blockers)),
        externalTractionEvidenceCount=external_count,
        strongCommercialTractionEvidenceCount=strong_traction_count,
    )


def compile_portfolio(packet: Any) -> dict[str, Any]:
    root = _exact(
        packet,
        {
            "version",
            "entityId",
            "globalGates",
            "evidenceRecords",
            "candidates",
        },
        "$",
    )
    if root["version"] != PORTFOLIO_VERSION:
        raise ContractError("UNSUPPORTED_VERSION")
    entity_id = _id(root["entityId"], "$.entityId")

    candidates_raw = root["candidates"]
    if (
        not isinstance(candidates_raw, list)
        or len(candidates_raw) < 2
        or len(candidates_raw) > MAX_CANDIDATES
    ):
        raise ContractError("CANDIDATE_COUNT")
    candidate_ids: list[str] = []
    for index, row in enumerate(candidates_raw):
        if type(row) is not dict:
            raise ContractError("EXPECTED_OBJECT", f"$.candidates[{index}]")
        candidate_id = _id(row.get("candidateId"), f"$.candidates[{index}].candidateId")
        if candidate_id in candidate_ids:
            raise ContractError("DUPLICATE_CANDIDATE_ID", candidate_id)
        candidate_ids.append(candidate_id)

    registry = _evidence_registry(root["evidenceRecords"])
    used_evidence: set[str] = set()
    gates = _exact(
        root["globalGates"],
        {
            "forProfitIndependentUsSmallBusiness",
            "ownershipControlEligible",
            "employeeCeilingMet",
            "sbirSmallBusinessRequirementsMet",
            "federalSupportCensus",
            "oneSubmissionSlot",
            "officialTemplate",
        },
        "$.globalGates",
    )

    global_blockers: list[str] = []
    for name in (
        "forProfitIndependentUsSmallBusiness",
        "ownershipControlEligible",
        "employeeCeilingMet",
        "sbirSmallBusinessRequirementsMet",
    ):
        state, _ = _fact(
            gates[name],
            f"$.globalGates.{name}",
            binding=f"global:{name}",
            allowed_classes={"OWNER"},
            registry=registry,
            used=used_evidence,
        )
        if state != "CONFIRMED_TRUE":
            global_blockers.append(f"global:{name}:{state}")

    support_state, _, support_ready = _enum_fact(
        gates["federalSupportCensus"],
        "$.globalGates.federalSupportCensus",
        SUPPORT_STATES,
        ready="CLEAR",
        binding="global:federalSupportCensus",
        allowed_classes={"OWNER"},
        registry=registry,
        used=used_evidence,
    )
    if not support_ready:
        global_blockers.append(f"global:federalSupportCensus:{support_state}")

    slot_state, _, slot_ready = _enum_fact(
        gates["oneSubmissionSlot"],
        "$.globalGates.oneSubmissionSlot",
        SLOT_STATES,
        ready="AVAILABLE",
        binding="global:oneSubmissionSlot",
        allowed_classes={"OWNER", "PROVIDER"},
        registry=registry,
        used=used_evidence,
    )
    if not slot_ready:
        global_blockers.append(f"global:oneSubmissionSlot:{slot_state}")

    template_state, _, template_ready = _enum_fact(
        gates["officialTemplate"],
        "$.globalGates.officialTemplate",
        TEMPLATE_STATES,
        ready="BOUND",
        binding="global:officialTemplate",
        allowed_classes={"PROVIDER"},
        registry=registry,
        used=used_evidence,
    )
    if not template_ready:
        global_blockers.append(f"global:officialTemplate:{template_state}")

    projections = [
        _candidate(row, i, registry=registry, used=used_evidence)
        for i, row in enumerate(candidates_raw)
    ]
    source_identities = [row.sourceIdentity for row in projections]
    if len(source_identities) != len(set(source_identities)):
        raise ContractError("CANDIDATE_SOURCE_REPLAY")
    unused = sorted(set(registry) - used_evidence)
    if unused:
        raise ContractError("UNUSED_EVIDENCE_RECORD", unused[0])

    viable = [row for row in projections if not row.hardBlockers]
    selected: str | None = None
    state = "HOLD"
    hold_reason = "GLOBAL_GATES"
    if global_blockers:
        pass
    elif not viable:
        hold_reason = "NO_CANDIDATE_PASSES_HARD_GATES"
    else:
        best = max(row.readinessBasisPoints for row in viable)
        leaders = [row for row in viable if row.readinessBasisPoints == best]
        if len(leaders) != 1:
            hold_reason = "TOP_READINESS_TIE"
        else:
            selected = leaders[0].candidateId
            state = "SELECTED"
            hold_reason = ""

    report = {
        "version": REPORT_VERSION,
        "inputPacketSha256": sha256_json(packet),
        "entityId": entity_id,
        "state": state,
        "selectedCandidateId": selected,
        "holdReason": hold_reason or None,
        "globalBlockers": sorted(global_blockers),
        "projections": [asdict(row) for row in sorted(projections, key=lambda row: row.candidateId)],
        "officialConstraintSnapshot": _official_constraint_snapshot(),
        "retainedEvidenceManifestSha256": sha256_json(
            [registry[key] for key in sorted(registry)]
        ),
        "evidenceTrustBoundary": (
            "retained references are structurally bound to one semantic use and "
            "carry immutable repo generation or artifact SHA-256; compiler does "
            "not independently authenticate the underlying external artifact"
        ),
        "officialConstraintPolicySha256": sha256_json(
            _official_constraint_snapshot()
        ),
        "readinessMetricMeaning": (
            "internal evidence-coverage basis points using published criterion weights; "
            "not an Army score, ranking, selection prediction, or outcome probability"
        ),
        "authority": {
            "armyEligibilityDetermined": False,
            "officialTemplateObtainedByCompiler": False,
            "registrationAuthorized": False,
            "submissionAuthorized": False,
            "entitySlotConsumed": False,
            "awardOrPrizeClaimed": False,
        },
    }
    report["receiptSha256"] = sha256_json(report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="xTech Search 10 evidence-only portfolio down-selector")
    parser.add_argument("packet")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = compile_portfolio(read_regular_json(args.packet))
    except ContractError as exc:
        print(json.dumps({"ok": False, "code": exc.code, "detail": exc.detail}, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(report, sort_keys=True, indent=2 if args.pretty else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
