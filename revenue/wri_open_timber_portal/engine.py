from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any, Mapping
from urllib.parse import urlparse

INPUT_SCHEMA = "wri-open-timber-proposal/v1"
REPORT_SCHEMA = "wri-open-timber-proposal-report/v2"
VERIFY_SCHEMA = "wri-open-timber-proposal-verification/v2"
EVIDENCE_SCHEMA = "wri-open-timber-repo-evidence/v1"
EVIDENCE_BINDING_ID = "wri-fti-api-dc9f33b1-v1"
EVIDENCE_REGISTRY_SHA256 = "4dbbcad844eb7a63902952ab78780d16cac4f8ad46d43bd60a6f9c7b6331dcd2"

_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+-]{0,159}$")
_UTC_TEXT = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_REQUIRED_WORKSTREAMS = {
    "reference_and_runtime_updates",
    "performance_and_security",
    "surface_fixes",
    "maintenance_and_bugs",
    "forward_improvement_list",
}
_BLOCKING_UNKNOWN_CATEGORIES = {
    "submission_route",
    "deadline_time_and_timezone",
    "mandatory_qualifications",
    "required_forms_and_representations",
    "evaluation_method",
    "pricing_instructions",
    "role_title",
}
_ALLOWED_AUTHORITIES = {"OFFICIAL_BUYER_PAGE", "BUYER_OWNED_PUBLIC_REPO", "SECONDARY_PROCUREMENT_MIRROR"}
_ALLOWED_ACCESS = {"RETRIEVED", "UNRETRIEVED_403"}
_ALLOWED_EVIDENCE = {"VERIFIED", "UNVERIFIED", "UNKNOWN"}
_ALLOWED_PRICING = {"OWNER_DECISION_REQUIRED", "PROPOSED_NOT_SUBMITTED"}
_AUTHORITY_KEYS = (
    "contact_authorized",
    "submission_authorized",
    "signature_authorized",
    "personnel_commitment_authorized",
    "contract_acceptance_claimed",
    "deployment_authorized",
    "award_claimed",
    "payment_claimed",
    "revenue_recognition_authorized",
)


class ContractError(ValueError):
    pass


def canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ContractError(f"non-canonical value: {exc}") from exc


def digest(value: Any) -> str:
    return sha256(canonical_json(value)).hexdigest()


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ContractError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def load_json_strict(raw: bytes, label: str = "input") -> dict[str, Any]:
    if not isinstance(raw, (bytes, bytearray)) or len(raw) > 2_000_000:
        raise ContractError(f"{label}: bounded bytes required")
    try:
        value = json.loads(
            bytes(raw).decode("utf-8", "strict"),
            object_pairs_hook=_pairs,
            parse_constant=lambda token: (_ for _ in ()).throw(
                ContractError(f"{label}: non-finite number {token}")
            ),
            parse_float=lambda token: (_ for _ in ()).throw(
                ContractError(f"{label}: floating-point numbers forbidden")
            ),
        )
    except ContractError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise ContractError(f"{label}: invalid JSON/UTF-8") from exc
    if type(value) is not dict:
        raise ContractError(f"{label}: top level must be object")
    return value


def _plain(value: Any, where: str) -> Any:
    if value is None or type(value) in {str, int, bool}:
        return value
    if type(value) is list:
        return [_plain(item, f"{where}[]") for item in value]
    if type(value) is dict:
        clean: dict[str, Any] = {}
        for key, item in value.items():
            if type(key) is not str:
                raise ContractError(f"{where}: string object keys required")
            clean[key] = _plain(item, f"{where}.{key}")
        return clean
    raise ContractError(f"{where}: plain JSON builtins required")


def _keys(value: Any, expected: set[str], where: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise ContractError(f"{where}: object required")
    if set(value) != expected:
        raise ContractError(
            f"{where}: keys mismatch missing={sorted(expected-set(value))} "
            f"extra={sorted(set(value)-expected)}"
        )
    return value


def _text(value: Any, where: str, limit: int = 3000) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > limit
        or any(ord(ch) < 32 and ch != "\t" for ch in value)
    ):
        raise ContractError(f"{where}: safe non-empty trimmed text required")
    return value


def _token(value: Any, where: str) -> str:
    value = _text(value, where, 160)
    if not _TOKEN.fullmatch(value):
        raise ContractError(f"{where}: canonical token required")
    return value


def _https(value: Any, where: str) -> str:
    value = _text(value, where, 2048)
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password or parsed.fragment:
        raise ContractError(f"{where}: https URL without credentials/fragment required")
    return value


def _bool(value: Any, where: str) -> bool:
    if type(value) is not bool:
        raise ContractError(f"{where}: boolean required")
    return value


def _int(value: Any, where: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum or value > 10**12:
        raise ContractError(f"{where}: bounded exact integer required")
    return value


def _utc(value: Any, where: str, _strptime=datetime.strptime, _utc_tz=timezone.utc) -> datetime:
    value = _text(value, where, 20)
    if not _UTC_TEXT.fullmatch(value):
        raise ContractError(f"{where}: RFC3339 UTC seconds required")
    try:
        return _strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=_utc_tz)
    except ValueError as exc:
        raise ContractError(f"{where}: invalid timestamp") from exc


def _utc_text(value: datetime, _datetime_cls=datetime, _utc_tz=timezone.utc) -> str:
    if not isinstance(value, _datetime_cls) or value.tzinfo is None or value.utcoffset() is None:
        raise ContractError("process clock must be timezone-aware")
    return value.astimezone(_utc_tz).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _make_clock(now=datetime.now, utc_tz=timezone.utc):
    def current() -> datetime:
        return now(utc_tz).replace(microsecond=0)
    return current


_PROCESS_UTC_NOW = _make_clock()


def _texts(value: Any, where: str, *, allow_empty: bool = False, limit: int = 64) -> list[str]:
    if type(value) is not list or len(value) > limit or (not value and not allow_empty):
        raise ContractError(f"{where}: bounded list required")
    out = [_text(item, f"{where}[]") for item in value]
    if len(out) != len(set(out)):
        raise ContractError(f"{where}: duplicates forbidden")
    return out


def _tokens(value: Any, where: str, *, allow_empty: bool = False) -> list[str]:
    if type(value) is not list or (not value and not allow_empty):
        raise ContractError(f"{where}: list required")
    out = [_token(item, f"{where}[]") for item in value]
    if len(out) != len(set(out)):
        raise ContractError(f"{where}: duplicates forbidden")
    return out


def _load_repo_evidence_registry() -> tuple[str, dict[str, Any]]:
    raw = Path(__file__).with_name("repo_evidence.json").read_bytes()
    parsed = load_json_strict(raw, "repo_evidence.json")
    if digest(parsed) != EVIDENCE_REGISTRY_SHA256:
        raise ContractError("repo evidence registry canonical root mismatch")
    parsed = _keys(parsed, {"schema", "evidence"}, "repo_evidence.json")
    if parsed["schema"] != EVIDENCE_SCHEMA or type(parsed["evidence"]) is not list:
        raise ContractError("repo_evidence.json: unsupported schema")
    matches = [row for row in parsed["evidence"] if type(row) is dict and row.get("binding_id") == EVIDENCE_BINDING_ID]
    if len(matches) != 1:
        raise ContractError("repo evidence binding missing or duplicated")
    binding = _plain(matches[0], "repo_evidence.binding")
    binding = _keys(
        binding,
        {"binding_id", "repository", "repository_url", "commit_sha", "commit_url", "files", "baseline"},
        "repo_evidence.binding",
    )
    if binding["repository"] != "wri/fti_api":
        raise ContractError("repo evidence repository mismatch")
    if binding["repository_url"] != "https://github.com/wri/fti_api":
        raise ContractError("repo evidence URL mismatch")
    if not re.fullmatch(r"[0-9a-f]{40}", _text(binding["commit_sha"], "repo_evidence.commit_sha", 40)):
        raise ContractError("repo evidence commit SHA invalid")
    _https(binding["commit_url"], "repo_evidence.commit_url")
    if type(binding["files"]) is not list or len(binding["files"]) < 2:
        raise ContractError("repo evidence files missing")
    for index, row in enumerate(binding["files"]):
        row = _keys(row, {"path", "git_blob_sha", "url"}, f"repo_evidence.files[{index}]")
        _text(row["path"], f"repo_evidence.files[{index}].path", 256)
        if not re.fullmatch(r"[0-9a-f]{40}", _text(row["git_blob_sha"], "blob", 40)):
            raise ContractError("repo evidence blob SHA invalid")
        _https(row["url"], f"repo_evidence.files[{index}].url")
    baseline = _keys(
        binding["baseline"],
        {
            "repo_url", "application", "runtime", "database", "spatial_extension", "queue",
            "hosting", "provisioning", "deployment", "test_command", "parallel_test_command",
            "repo_source_id",
        },
        "repo_evidence.baseline",
    )
    _https(baseline["repo_url"], "repo_evidence.baseline.repo_url")
    for key, value in baseline.items():
        if key != "repo_url":
            _text(value, f"repo_evidence.baseline.{key}", 500)
    return EVIDENCE_REGISTRY_SHA256, binding


def _normalize_sources(value: Any) -> list[dict[str, Any]]:
    if type(value) is not list or not 2 <= len(value) <= 20:
        raise ContractError("sources: 2..20 rows required")
    out: list[dict[str, Any]] = []
    ids: set[str] = set()
    urls: set[str] = set()
    for index, raw in enumerate(value):
        row = _keys(
            raw,
            {"source_id", "authority", "url", "access_state", "observed_at", "fresh_until", "claims", "limitations"},
            f"sources[{index}]",
        )
        sid = _token(row["source_id"], "source_id")
        if sid in ids:
            raise ContractError("duplicate source_id")
        ids.add(sid)
        url = _https(row["url"], "source.url")
        if url in urls:
            raise ContractError("duplicate source URL")
        urls.add(url)
        authority = _token(row["authority"], "source.authority")
        if authority not in _ALLOWED_AUTHORITIES:
            raise ContractError("unsupported source authority")
        access = _token(row["access_state"], "source.access_state")
        if access not in _ALLOWED_ACCESS:
            raise ContractError("unsupported source access_state")
        claims = _tokens(row["claims"], "source.claims", allow_empty=True)
        limitations = _texts(row["limitations"], "source.limitations", limit=16)
        observed = _utc(row["observed_at"], "source.observed_at")
        fresh = _utc(row["fresh_until"], "source.fresh_until")
        if fresh < observed:
            raise ContractError("source freshness precedes observation")
        if access == "UNRETRIEVED_403" and claims:
            raise ContractError("unretrieved source cannot carry claims")
        out.append(
            {
                "source_id": sid,
                "authority": authority,
                "url": url,
                "access_state": access,
                "observed_at": _utc_text(observed),
                "fresh_until": _utc_text(fresh),
                "claims": sorted(claims),
                "limitations": limitations,
            }
        )
    return sorted(out, key=lambda row: row["source_id"])


def normalize(packet: Any) -> dict[str, Any]:
    packet = _plain(packet, "packet")
    packet = _keys(
        packet,
        {"schema", "opportunity", "sources", "controlling_unknowns", "technical_baseline", "workstreams", "company_evidence", "commercial"},
        "packet",
    )
    if packet["schema"] != INPUT_SCHEMA:
        raise ContractError("unsupported packet schema")

    opp = _keys(
        packet["opportunity"],
        {"buyer_id", "opportunity_id", "buyer_name", "project_name", "target_role", "issued_date_hint",
         "proposal_due_date_hint", "vendor_decision_date_hint", "anticipated_start_date_hint",
         "deliverables_due_date_hint"},
        "opportunity",
    )
    normalized_opp = {
        "buyer_id": _token(opp["buyer_id"], "opportunity.buyer_id"),
        "opportunity_id": _token(opp["opportunity_id"], "opportunity.opportunity_id"),
        "buyer_name": _text(opp["buyer_name"], "opportunity.buyer_name", 200),
        "project_name": _text(opp["project_name"], "opportunity.project_name", 300),
        "target_role": _text(opp["target_role"], "opportunity.target_role", 300),
        "issued_date_hint": _text(opp["issued_date_hint"], "opportunity.issued_date_hint", 32),
        "proposal_due_date_hint": _text(opp["proposal_due_date_hint"], "opportunity.proposal_due_date_hint", 32),
        "vendor_decision_date_hint": _text(opp["vendor_decision_date_hint"], "opportunity.vendor_decision_date_hint", 32),
        "anticipated_start_date_hint": _text(opp["anticipated_start_date_hint"], "opportunity.anticipated_start_date_hint", 32),
        "deliverables_due_date_hint": _text(opp["deliverables_due_date_hint"], "opportunity.deliverables_due_date_hint", 32),
    }

    sources = _normalize_sources(packet["sources"])

    unknowns = packet["controlling_unknowns"]
    if type(unknowns) is not list or not unknowns:
        raise ContractError("controlling_unknowns required")
    normalized_unknowns: list[dict[str, Any]] = []
    categories: set[str] = set()
    for index, raw in enumerate(unknowns):
        row = _keys(raw, {"category", "blocking", "description", "resolution_evidence"}, f"unknowns[{index}]")
        category = _token(row["category"], "unknown.category")
        if category in categories:
            raise ContractError("duplicate controlling unknown")
        categories.add(category)
        blocking = _bool(row["blocking"], "unknown.blocking")
        resolution = row["resolution_evidence"]
        if resolution is not None:
            _text(resolution, "unknown.resolution_evidence", 2000)
            raise ContractError("candidate cannot self-resolve controlling procurement facts")
        normalized_unknowns.append(
            {
                "category": category,
                "blocking": blocking,
                "description": _text(row["description"], "unknown.description", 2000),
                "resolution_evidence": None,
            }
        )
    missing = _BLOCKING_UNKNOWN_CATEGORIES - categories
    if missing:
        raise ContractError(f"required controlling unknown categories omitted: {sorted(missing)}")
    for row in normalized_unknowns:
        if row["category"] in _BLOCKING_UNKNOWN_CATEGORIES and not row["blocking"]:
            raise ContractError(f"{row['category']} must remain blocking")

    registry_sha, binding = _load_repo_evidence_registry()
    baseline = _plain(packet["technical_baseline"], "technical_baseline")
    expected_baseline = deepcopy(binding["baseline"])
    if baseline != expected_baseline:
        raise ContractError(
            "technical_baseline does not match repo-pinned WRI evidence; "
            "candidate-authored technical facts cannot become readiness"
        )
    source_by_id = {row["source_id"]: row for row in sources}
    repo_sid = expected_baseline["repo_source_id"]
    if repo_sid not in source_by_id:
        raise ContractError("informational repo source row missing")
    if source_by_id[repo_sid]["url"] != binding["repository_url"]:
        raise ContractError("informational repo URL disagrees with retained evidence")
    repo_evidence = {
        "binding_id": binding["binding_id"],
        "registry_sha256": registry_sha,
        "repository": binding["repository"],
        "repository_url": binding["repository_url"],
        "commit_sha": binding["commit_sha"],
        "commit_url": binding["commit_url"],
        "files": deepcopy(binding["files"]),
    }

    workstreams = packet["workstreams"]
    if type(workstreams) is not list or len(workstreams) < len(_REQUIRED_WORKSTREAMS):
        raise ContractError("workstreams incomplete")
    normalized_workstreams: list[dict[str, Any]] = []
    buckets: set[str] = set()
    ids: set[str] = set()
    for index, raw in enumerate(workstreams):
        row = _keys(
            raw,
            {"workstream_id", "bucket", "objective", "activities", "acceptance_evidence", "assumptions"},
            f"workstreams[{index}]",
        )
        wid = _token(row["workstream_id"], "workstream_id")
        bucket = _token(row["bucket"], "workstream.bucket")
        if wid in ids or bucket in buckets:
            raise ContractError("duplicate workstream identity/bucket")
        ids.add(wid)
        buckets.add(bucket)
        normalized_workstreams.append(
            {
                "workstream_id": wid,
                "bucket": bucket,
                "objective": _text(row["objective"], "workstream.objective", 1500),
                "activities": _texts(row["activities"], "workstream.activities", limit=16),
                "acceptance_evidence": _texts(row["acceptance_evidence"], "workstream.acceptance_evidence", limit=16),
                "assumptions": _texts(row["assumptions"], "workstream.assumptions", allow_empty=True, limit=16),
            }
        )
    missing_ws = _REQUIRED_WORKSTREAMS - buckets
    if missing_ws:
        raise ContractError(f"missing published work buckets: {sorted(missing_ws)}")

    evidence = packet["company_evidence"]
    if type(evidence) is not dict or not evidence:
        raise ContractError("company_evidence required")
    normalized_evidence: dict[str, str] = {}
    for key, value in evidence.items():
        key = _token(key, "company_evidence key")
        value = _token(value, f"company_evidence.{key}")
        if value not in _ALLOWED_EVIDENCE:
            raise ContractError(f"unsupported company evidence state: {key}")
        normalized_evidence[key] = value
    for key in ("ruby_rails_delivery", "legal_vendor_eligibility", "relevant_past_performance", "named_staffing"):
        if key not in normalized_evidence:
            raise ContractError(f"missing company evidence gate: {key}")

    commercial = _keys(
        packet["commercial"],
        {"currency", "amount_minor", "pricing_status", "pricing_basis", "offer_status", "assumptions"},
        "commercial",
    )
    currency = _token(commercial["currency"], "commercial.currency")
    if not re.fullmatch(r"[A-Z]{3}", currency):
        raise ContractError("currency must be three uppercase letters")
    amount = commercial["amount_minor"]
    if amount is not None:
        amount = _int(amount, "commercial.amount_minor", 1)
    pricing_status = _token(commercial["pricing_status"], "commercial.pricing_status")
    if pricing_status not in _ALLOWED_PRICING:
        raise ContractError("unsupported pricing status")
    if pricing_status == "OWNER_DECISION_REQUIRED" and amount is not None:
        raise ContractError("owner-decision pricing cannot include amount")
    if pricing_status == "PROPOSED_NOT_SUBMITTED" and amount is None:
        raise ContractError("proposed pricing requires amount")
    if commercial["offer_status"] != "NOT_SUBMITTED":
        raise ContractError("offer status must remain NOT_SUBMITTED")
    normalized_commercial = {
        "currency": currency,
        "amount_minor": amount,
        "pricing_status": pricing_status,
        "pricing_basis": _text(commercial["pricing_basis"], "commercial.pricing_basis", 2000),
        "offer_status": "NOT_SUBMITTED",
        "assumptions": _texts(commercial["assumptions"], "commercial.assumptions", allow_empty=True, limit=32),
    }

    return {
        "schema": INPUT_SCHEMA,
        "opportunity": normalized_opp,
        "sources": sources,
        "controlling_unknowns": sorted(normalized_unknowns, key=lambda row: row["category"]),
        "technical_baseline": expected_baseline,
        "repo_evidence": repo_evidence,
        "workstreams": sorted(normalized_workstreams, key=lambda row: row["bucket"]),
        "company_evidence": dict(sorted(normalized_evidence.items())),
        "commercial": normalized_commercial,
    }


def _authority() -> dict[str, bool]:
    return {key: False for key in _AUTHORITY_KEYS}


def _compile_at(packet: Any, evaluated_at: datetime) -> dict[str, Any]:
    normalized = normalize(packet)
    now_text = _utc_text(evaluated_at)
    now = _utc(now_text, "evaluated_at")
    current_source_ids = [
        row["source_id"]
        for row in normalized["sources"]
        if _utc(row["observed_at"], "source.observed_at") <= now <= _utc(row["fresh_until"], "source.fresh_until")
    ]
    stale_source_ids = [
        row["source_id"]
        for row in normalized["sources"]
        if now > _utc(row["fresh_until"], "source.fresh_until")
    ]
    blocking_unknowns = [
        row["category"] for row in normalized["controlling_unknowns"]
        if row["blocking"] and row["resolution_evidence"] is None
    ]
    company_gaps = sorted(
        key for key, state in normalized["company_evidence"].items() if state != "VERIFIED"
    )
    buckets = {row["bucket"] for row in normalized["workstreams"]}
    technical_ready = buckets >= _REQUIRED_WORKSTREAMS
    if not technical_ready:
        raise ContractError("required technical workstreams missing")
    core = {
        "schema": REPORT_SCHEMA,
        "buyer_id": normalized["opportunity"]["buyer_id"],
        "opportunity_id": normalized["opportunity"]["opportunity_id"],
        "project_name": normalized["opportunity"]["project_name"],
        "target_role": normalized["opportunity"]["target_role"],
        "technical_readiness": "TECHNICALLY_READY_SOURCE_BOUND",
        "submission_readiness": "HOLD_CONTROLLING_SOURCE",
        "blocking_unknowns": blocking_unknowns,
        "company_evidence_gaps": company_gaps,
        "current_source_ids": current_source_ids,
        "stale_source_ids": stale_source_ids,
        "source_metadata_advisory": True,
        "technical_baseline": normalized["technical_baseline"],
        "repo_evidence": normalized["repo_evidence"],
        "workstreams": normalized["workstreams"],
        "commercial": normalized["commercial"],
        "authority": _authority(),
        "external_submission_authorized": False,
        "source_manifest_sha256": digest(normalized["sources"]),
        "input_sha256": digest(normalized),
        "semantic_boundary": (
            "Technical readiness means only that the preserved delivery workstreams align with a baseline "
            "exactly pinned to reviewed WRI Git commit/blob evidence. Candidate source labels, claims, and "
            "timestamps are advisory and cannot create technical or submission authority."
        ),
    }
    state_sha = digest(core)
    historical = {**core, "evaluated_at": now_text, "state_sha256": state_sha}
    return {**historical, "receipt_sha256": digest(historical)}


def compile_proposal(packet: Any) -> dict[str, Any]:
    """Compile current posture using process-owned UTC. No caller clock is accepted."""
    return _compile_at(packet, _PROCESS_UTC_NOW())


def verify_report(packet: Any, report: Any) -> dict[str, Any]:
    report = _plain(report, "report")
    expected = {
        "schema", "buyer_id", "opportunity_id", "project_name", "target_role",
        "technical_readiness", "submission_readiness", "blocking_unknowns",
        "company_evidence_gaps", "current_source_ids", "stale_source_ids",
        "source_metadata_advisory", "technical_baseline", "repo_evidence", "workstreams",
        "commercial", "authority", "external_submission_authorized",
        "source_manifest_sha256", "input_sha256", "semantic_boundary", "evaluated_at",
        "state_sha256", "receipt_sha256",
    }
    report = _keys(report, expected, "report")
    if report["schema"] != REPORT_SCHEMA:
        raise ContractError("unsupported report schema")
    receipt = _text(report["receipt_sha256"], "report.receipt_sha256", 64)
    if not re.fullmatch(r"[0-9a-f]{64}", receipt):
        raise ContractError("invalid report receipt")
    payload = {key: value for key, value in report.items() if key != "receipt_sha256"}
    receipt_valid = digest(payload) == receipt
    evaluated = _utc(report["evaluated_at"], "report.evaluated_at")
    historical = _compile_at(packet, evaluated)
    historical_exact = historical == report
    current = compile_proposal(packet)
    current_same_state = current["state_sha256"] == report["state_sha256"]
    verdict = (
        "CURRENT_SOURCE_BOUND_TECHNICAL_CARRIER_VERIFIED"
        if receipt_valid and historical_exact and current_same_state
        else "STALE_OR_DRIFTED"
    )
    core = {
        "schema": VERIFY_SCHEMA,
        "verdict": verdict,
        "historical_receipt_valid": receipt_valid,
        "historical_exact": historical_exact,
        "current_same_state": current_same_state,
        "current_submission_readiness": current["submission_readiness"],
        "external_submission_authorized": False,
        "report_receipt_sha256": receipt,
        "current_state_sha256": current["state_sha256"],
    }
    return {**core, "receipt_sha256": digest(core)}


def render_markdown(report: Mapping[str, Any]) -> str:
    if report.get("schema") != REPORT_SCHEMA:
        raise ContractError("not a WRI OTP v2 report")
    baseline = report["technical_baseline"]
    evidence = report["repo_evidence"]
    commercial = report["commercial"]
    lines = [
        "# World Resources Institute — Open Timber Portal technical proposal carrier",
        "",
        f"**Target surface:** {report['target_role']}  ",
        f"**Technical readiness:** `{report['technical_readiness']}`  ",
        f"**Submission readiness:** `{report['submission_readiness']}`  ",
        f"**External submission authorized:** `{str(report['external_submission_authorized']).lower()}`  ",
        f"**Receipt:** `{report['receipt_sha256']}`",
        "",
        "## Repo-pinned technical evidence",
        "",
        f"- Repository: {evidence['repository_url']}",
        f"- Immutable commit: `{evidence['commit_sha']}`",
        f"- Evidence registry SHA-256: `{evidence['registry_sha256']}`",
    ]
    for row in evidence["files"]:
        lines.append(f"- `{row['path']}` Git blob: `{row['git_blob_sha']}`")
    lines += [
        "",
        "Candidate source labels/claims/timestamps are advisory only; they do not establish the technical baseline.",
        "",
        "## Source-bound technical baseline",
        "",
        f"- Application: {baseline['application']}",
        f"- Runtime: {baseline['runtime']}",
        f"- Data: {baseline['database']} + {baseline['spatial_extension']}",
        f"- Background processing: {baseline['queue']}",
        f"- Hosting: {baseline['hosting']}",
        f"- Provisioning: {baseline['provisioning']}",
        f"- Deployment: {baseline['deployment']}",
        f"- Test path: `{baseline['test_command']}` / `{baseline['parallel_test_command']}`",
        "",
        "## Six-month delivery plan",
        "",
    ]
    for ws in report["workstreams"]:
        lines += [
            f"### {ws['workstream_id']} — {ws['bucket']}",
            ws["objective"],
            "",
            "**Activities**",
            *[f"- {item}" for item in ws["activities"]],
            "",
            "**Acceptance evidence**",
            *[f"- {item}" for item in ws["acceptance_evidence"]],
            "",
        ]
    lines += [
        "## Commercial posture",
        "",
        f"- Status: `{commercial['pricing_status']}` / `{commercial['offer_status']}`",
        f"- Currency: {commercial['currency']}",
        f"- Amount (minor units): {commercial['amount_minor'] if commercial['amount_minor'] is not None else 'UNSET'}",
        f"- Basis: {commercial['pricing_basis']}",
        "",
        "## Blocking procurement facts",
        "",
        *[f"- `{item}`" for item in report["blocking_unknowns"]],
        "",
        "## Company evidence still required",
        "",
        *[f"- `{item}`" for item in report["company_evidence_gaps"]],
        "",
        "## Authority ceiling",
        "",
        "This carrier does not authorize WRI contact or Workday mutation/submission, commit personnel or fees, sign or accept a contract, deploy into WRI infrastructure, claim an award/payment, or recognize revenue.",
        "",
    ]
    return "\n".join(lines)
