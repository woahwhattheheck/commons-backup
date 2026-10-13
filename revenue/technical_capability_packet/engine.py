from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from itertools import combinations
import json
import re
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlparse

SCHEMA = "technical-capability-request/v1"
REPORT_SCHEMA = "technical-capability-packet/v1"
VERIFY_SCHEMA = "technical-capability-verification/v1"
_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_ALLOWED_KINDS = {"PUBLIC_REPO", "PUBLIC_DEMO", "PUBLIC_REPORT", "PUBLIC_DOC", "BUYER_PROVIDED"}
_ALLOWED_SCOPES = {"PUBLIC_REUSABLE", "BUYER_BOUND"}
_MAX_ASSETS = 20
_MAX_REQUIREMENTS = 64


class ContractError(ValueError):
    pass


@dataclass(frozen=True)
class Asset:
    asset_id: str
    generation: int
    kind: str
    uri: str
    digest: str
    observed_at: datetime
    expires_at: datetime
    claims: frozenset[str]
    limitations: tuple[str, ...]
    scope: str
    buyer_id: str | None
    opportunity_id: str | None


@dataclass(frozen=True)
class Requirement:
    requirement_id: str
    title: str
    required_claims: frozenset[str]
    mandatory: bool


def _canonical(value: Any) -> bytes:
    try:
        text = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ContractError(f"non-canonical value: {exc}") from exc
    return text.encode("utf-8")


def _digest(value: Any) -> str:
    return sha256(_canonical(value)).hexdigest()


def load_json_strict(raw: bytes) -> Any:
    if len(raw) > 2_000_000:
        raise ContractError("input too large")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ContractError("input must be UTF-8") from exc

    def hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in pairs:
            if key in out:
                raise ContractError(f"duplicate JSON key: {key}")
            out[key] = value
        return out

    try:
        return json.loads(text, object_pairs_hook=hook, parse_constant=lambda x: (_ for _ in ()).throw(ContractError(f"non-finite JSON number: {x}")))
    except json.JSONDecodeError as exc:
        raise ContractError(f"invalid JSON: {exc.msg}") from exc


def _exact_keys(obj: Mapping[str, Any], keys: set[str], where: str) -> None:
    if set(obj) != keys:
        missing = sorted(keys - set(obj))
        extra = sorted(set(obj) - keys)
        raise ContractError(f"{where} schema mismatch missing={missing} extra={extra}")


def _token(value: Any, where: str) -> str:
    if not isinstance(value, str) or not _TOKEN.fullmatch(value):
        raise ContractError(f"{where} must be a canonical token")
    return value


def _text(value: Any, where: str, *, max_len: int = 1000) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip() or len(value) > max_len or any(ord(ch) < 32 and ch not in "\t" for ch in value):
        raise ContractError(f"{where} must be non-empty trimmed text")
    return value


def _positive_int(value: Any, where: str, *, maximum: int = 10**12) -> int:
    if type(value) is not int or not 1 <= value <= maximum:
        raise ContractError(f"{where} must be an exact positive integer")
    return value


def _nonnegative_int(value: Any, where: str, *, maximum: int = 10**12) -> int:
    if type(value) is not int or not 0 <= value <= maximum:
        raise ContractError(f"{where} must be an exact non-negative integer")
    return value


def _utc(value: Any, where: str) -> datetime:
    if not isinstance(value, str) or not _UTC.fullmatch(value):
        raise ContractError(f"{where} must be canonical UTC seconds (YYYY-MM-DDTHH:MM:SSZ)")
    try:
        dt = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise ContractError(f"{where} is not a real timestamp") from exc
    return dt


def _trusted_time(dt: datetime, where: str) -> datetime:
    if not isinstance(dt, datetime) or dt.tzinfo is None or dt.utcoffset() is None:
        raise ContractError(f"{where} must be timezone-aware")
    try:
        return dt.astimezone(timezone.utc).replace(microsecond=0)
    except (OverflowError, ValueError) as exc:
        raise ContractError(f"{where} is invalid") from exc


def _utc_text(dt: datetime) -> str:
    return _trusted_time(dt, "timestamp").strftime("%Y-%m-%dT%H:%M:%SZ")


def _unique_tokens(value: Any, where: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    if not isinstance(value, list) or (not value and not allow_empty):
        raise ContractError(f"{where} must be a {'possibly empty ' if allow_empty else 'non-empty '}list")
    result = tuple(_token(v, f"{where}[]") for v in value)
    if len(set(result)) != len(result):
        raise ContractError(f"{where} contains duplicates")
    return result


def _unique_texts(value: Any, where: str, *, allow_empty: bool = False, max_items: int = 64) -> tuple[str, ...]:
    if not isinstance(value, list) or (not value and not allow_empty) or len(value) > max_items:
        raise ContractError(f"{where} must be a bounded {'possibly empty ' if allow_empty else 'non-empty '}list")
    result = tuple(_text(v, f"{where}[]") for v in value)
    if len(set(result)) != len(result):
        raise ContractError(f"{where} contains duplicates")
    return result


def _https_uri(value: Any, where: str) -> str:
    value = _text(value, where, max_len=2048)
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password or parsed.fragment:
        raise ContractError(f"{where} must be an https URL without credentials or fragment")
    return value


def _parse_requirement(raw: Any) -> Requirement:
    if not isinstance(raw, dict):
        raise ContractError("requirement must be an object")
    _exact_keys(raw, {"requirement_id", "title", "required_claims", "mandatory"}, "requirement")
    if type(raw["mandatory"]) is not bool:
        raise ContractError("requirement.mandatory must be boolean")
    claims = frozenset(_unique_tokens(raw["required_claims"], "requirement.required_claims"))
    return Requirement(
        _token(raw["requirement_id"], "requirement.requirement_id"),
        _text(raw["title"], "requirement.title", max_len=240),
        claims,
        raw["mandatory"],
    )


def _parse_asset(raw: Any, buyer_id: str, opportunity_id: str) -> Asset:
    if not isinstance(raw, dict):
        raise ContractError("proof asset must be an object")
    keys = {"asset_id", "generation", "kind", "uri", "sha256", "observed_at", "expires_at", "claims", "limitations", "scope", "buyer_id", "opportunity_id"}
    _exact_keys(raw, keys, "proof_asset")
    kind = _token(raw["kind"], "proof_asset.kind")
    if kind not in _ALLOWED_KINDS:
        raise ContractError("unsupported proof_asset.kind")
    scope = _token(raw["scope"], "proof_asset.scope")
    if scope not in _ALLOWED_SCOPES:
        raise ContractError("unsupported proof_asset.scope")
    digest = raw["sha256"]
    if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
        raise ContractError("proof_asset.sha256 must be lowercase SHA-256")
    observed = _utc(raw["observed_at"], "proof_asset.observed_at")
    expires = _utc(raw["expires_at"], "proof_asset.expires_at")
    if expires <= observed:
        raise ContractError("proof_asset expires_at must be after observed_at")
    claims = frozenset(_unique_tokens(raw["claims"], "proof_asset.claims"))
    limitations = _unique_texts(raw["limitations"], "proof_asset.limitations", max_items=32)
    bound_buyer = raw["buyer_id"]
    bound_opp = raw["opportunity_id"]
    if scope == "PUBLIC_REUSABLE":
        if bound_buyer is not None or bound_opp is not None:
            raise ContractError("PUBLIC_REUSABLE proof cannot carry buyer/opportunity bindings")
    else:
        if _token(bound_buyer, "proof_asset.buyer_id") != buyer_id or _token(bound_opp, "proof_asset.opportunity_id") != opportunity_id:
            raise ContractError("BUYER_BOUND proof must bind this buyer and opportunity")
    return Asset(
        _token(raw["asset_id"], "proof_asset.asset_id"),
        _positive_int(raw["generation"], "proof_asset.generation", maximum=10**9),
        kind,
        _https_uri(raw["uri"], "proof_asset.uri"),
        digest,
        observed,
        expires,
        claims,
        limitations,
        scope,
        bound_buyer,
        bound_opp,
    )


def _normalize(packet: Any) -> dict[str, Any]:
    if not isinstance(packet, dict):
        raise ContractError("packet must be an object")
    _exact_keys(packet, {"schema", "buyer_id", "opportunity_id", "request", "known_unsupported_claims", "proof_assets", "next_step"}, "packet")
    if packet["schema"] != SCHEMA:
        raise ContractError("unsupported packet schema")
    buyer_id = _token(packet["buyer_id"], "buyer_id")
    opportunity_id = _token(packet["opportunity_id"], "opportunity_id")

    request = packet["request"]
    if not isinstance(request, dict):
        raise ContractError("request must be an object")
    _exact_keys(request, {"request_id", "generation", "observed_at", "expires_at", "requirements"}, "request")
    request_id = _token(request["request_id"], "request.request_id")
    generation = _positive_int(request["generation"], "request.generation", maximum=10**9)
    observed_at = _utc(request["observed_at"], "request.observed_at")
    expires_at = _utc(request["expires_at"], "request.expires_at")
    if expires_at <= observed_at:
        raise ContractError("request expires_at must be after observed_at")
    raw_requirements = request["requirements"]
    if not isinstance(raw_requirements, list) or not 1 <= len(raw_requirements) <= _MAX_REQUIREMENTS:
        raise ContractError("request.requirements must be a bounded non-empty list")
    requirements = tuple(_parse_requirement(x) for x in raw_requirements)
    if len({x.requirement_id for x in requirements}) != len(requirements):
        raise ContractError("duplicate requirement_id")
    if not any(x.mandatory for x in requirements):
        raise ContractError("request must contain at least one mandatory requirement")

    unsupported = frozenset(_unique_tokens(packet["known_unsupported_claims"], "known_unsupported_claims", allow_empty=True))

    raw_assets = packet["proof_assets"]
    if not isinstance(raw_assets, list) or not 1 <= len(raw_assets) <= _MAX_ASSETS:
        raise ContractError(f"proof_assets must contain 1..{_MAX_ASSETS} assets")
    assets = tuple(_parse_asset(x, buyer_id, opportunity_id) for x in raw_assets)
    if len({x.asset_id for x in assets}) != len(assets):
        raise ContractError("duplicate proof asset_id")
    if len({x.uri for x in assets}) != len(assets):
        raise ContractError("duplicate proof URI alias")
    if len({x.digest for x in assets}) != len(assets):
        raise ContractError("duplicate proof digest alias")
    all_asset_claims = frozenset().union(*(x.claims for x in assets))
    conflict = sorted(unsupported & all_asset_claims)
    if conflict:
        raise ContractError(f"proof contradicts known unsupported claims: {conflict}")

    next_step = packet["next_step"]
    if not isinstance(next_step, dict):
        raise ContractError("next_step must be an object")
    _exact_keys(next_step, {"offer_id", "amount_minor", "currency", "duration_days", "scope", "deliverables", "dependencies", "acceptance_criteria"}, "next_step")
    currency = _token(next_step["currency"], "next_step.currency")
    if not re.fullmatch(r"[A-Z]{3}", currency):
        raise ContractError("next_step.currency must be ISO-like three uppercase letters")
    normalized_next = {
        "offer_id": _token(next_step["offer_id"], "next_step.offer_id"),
        "amount_minor": _positive_int(next_step["amount_minor"], "next_step.amount_minor"),
        "currency": currency,
        "duration_days": _positive_int(next_step["duration_days"], "next_step.duration_days", maximum=3650),
        "scope": _text(next_step["scope"], "next_step.scope", max_len=2000),
        "deliverables": list(_unique_texts(next_step["deliverables"], "next_step.deliverables", max_items=32)),
        "dependencies": list(_unique_texts(next_step["dependencies"], "next_step.dependencies", allow_empty=True, max_items=32)),
        "acceptance_criteria": list(_unique_texts(next_step["acceptance_criteria"], "next_step.acceptance_criteria", max_items=32)),
    }

    return {
        "schema": SCHEMA,
        "buyer_id": buyer_id,
        "opportunity_id": opportunity_id,
        "request": {
            "request_id": request_id,
            "generation": generation,
            "observed_at": _utc_text(observed_at),
            "expires_at": _utc_text(expires_at),
            "requirements": [
                {"requirement_id": r.requirement_id, "title": r.title, "required_claims": sorted(r.required_claims), "mandatory": r.mandatory}
                for r in sorted(requirements, key=lambda r: r.requirement_id)
            ],
        },
        "known_unsupported_claims": sorted(unsupported),
        "proof_assets": [
            {
                "asset_id": a.asset_id,
                "generation": a.generation,
                "kind": a.kind,
                "uri": a.uri,
                "sha256": a.digest,
                "observed_at": _utc_text(a.observed_at),
                "expires_at": _utc_text(a.expires_at),
                "claims": sorted(a.claims),
                "limitations": list(a.limitations),
                "scope": a.scope,
                "buyer_id": a.buyer_id,
                "opportunity_id": a.opportunity_id,
            }
            for a in sorted(assets, key=lambda a: a.asset_id)
        ],
        "next_step": normalized_next,
    }


def _as_models(normalized: Mapping[str, Any]) -> tuple[tuple[Requirement, ...], tuple[Asset, ...]]:
    requirements = tuple(_parse_requirement(x) for x in normalized["request"]["requirements"])
    assets = tuple(_parse_asset(x, normalized["buyer_id"], normalized["opportunity_id"]) for x in normalized["proof_assets"])
    return requirements, assets


def _minimal_cover(assets: Sequence[Asset], target_claims: frozenset[str]) -> tuple[str, ...]:
    if not target_claims:
        return ()
    useful = sorted((a for a in assets if a.claims & target_claims), key=lambda a: a.asset_id)
    for size in range(1, len(useful) + 1):
        winners: list[tuple[str, ...]] = []
        for combo in combinations(useful, size):
            covered = frozenset().union(*(a.claims for a in combo))
            if target_claims <= covered:
                winners.append(tuple(a.asset_id for a in combo))
        if winners:
            return min(winners)
    return ()


def compile_packet(packet: Any, *, as_of: datetime) -> dict[str, Any]:
    normalized = _normalize(packet)
    now = _trusted_time(as_of, "as_of")
    now_text = _utc_text(now)
    request_observed = _utc(normalized["request"]["observed_at"], "request.observed_at")
    request_expires = _utc(normalized["request"]["expires_at"], "request.expires_at")
    if now < request_observed:
        raise ContractError("evaluation precedes request observation")
    requirements, assets = _as_models(normalized)
    unsupported = frozenset(normalized["known_unsupported_claims"])
    valid_assets = tuple(a for a in assets if a.observed_at <= now <= a.expires_at)
    valid_claims = frozenset().union(*(a.claims for a in valid_assets)) if valid_assets else frozenset()
    stale_claims = frozenset().union(*(a.claims for a in assets if a.expires_at < now)) if assets else frozenset()

    mappings: list[dict[str, Any]] = []
    proven_target: set[str] = set()
    for req in sorted(requirements, key=lambda r: r.requirement_id):
        if req.required_claims & unsupported:
            status = "UNSUPPORTED"
        else:
            covered = req.required_claims & valid_claims
            if covered == req.required_claims:
                status = "SUPPORTED"
            elif covered:
                status = "PARTIAL"
            else:
                status = "NEEDS_EVIDENCE"
            proven_target.update(covered)
        missing = sorted(req.required_claims - valid_claims - unsupported)
        stale_only = sorted((req.required_claims & stale_claims) - valid_claims)
        mappings.append({
            "requirement_id": req.requirement_id,
            "title": req.title,
            "mandatory": req.mandatory,
            "status": status,
            "required_claims": sorted(req.required_claims),
            "covered_claims": sorted(req.required_claims & valid_claims),
            "missing_claims": missing,
            "unsupported_claims": sorted(req.required_claims & unsupported),
            "stale_only_claims": stale_only,
        })

    selected_ids = _minimal_cover(valid_assets, frozenset(proven_target))
    selected = [a for a in valid_assets if a.asset_id in set(selected_ids)]
    request_live = now <= request_expires
    mandatory_complete = all(row["status"] == "SUPPORTED" for row in mappings if row["mandatory"])
    readiness = "READY_FOR_OWNER_SEND_REVIEW" if request_live and mandatory_complete else "HOLD_FOR_EVIDENCE"
    authority = {
        "outbound_authorized": False,
        "buyer_acceptance_claimed": False,
        "payment_claimed": False,
        "revenue_recognition_authorized": False,
        "proposal_status": "PROPOSED_NOT_ACCEPTED",
    }
    result_core = {
        "schema": REPORT_SCHEMA,
        "buyer_id": normalized["buyer_id"],
        "opportunity_id": normalized["opportunity_id"],
        "request_id": normalized["request"]["request_id"],
        "request_generation": normalized["request"]["generation"],
        "request_sha256": _digest({
            "buyer_id": normalized["buyer_id"],
            "opportunity_id": normalized["opportunity_id"],
            "request": normalized["request"],
        }),
        "request_live": request_live,
        "readiness": readiness,
        "requirements": mappings,
        "selected_proof": [
            {
                "asset_id": a.asset_id,
                "generation": a.generation,
                "kind": a.kind,
                "uri": a.uri,
                "sha256": a.digest,
                "claims": sorted(a.claims),
                "limitations": list(a.limitations),
            }
            for a in sorted(selected, key=lambda a: a.asset_id)
        ],
        "paid_next_step": {**normalized["next_step"], "status": "PROPOSED_NOT_ACCEPTED"},
        "authority": authority,
    }
    state_digest = _digest(result_core)
    report_without_receipt = {**result_core, "evaluated_at": now_text, "state_sha256": state_digest}
    return {**report_without_receipt, "receipt_sha256": _digest(report_without_receipt)}


def verify_report(packet: Any, report: Any, *, current_as_of: datetime) -> dict[str, Any]:
    if not isinstance(report, dict):
        raise ContractError("report must be an object")
    expected_keys = {"schema", "buyer_id", "opportunity_id", "request_id", "request_generation", "request_sha256", "request_live", "readiness", "requirements", "selected_proof", "paid_next_step", "authority", "evaluated_at", "state_sha256", "receipt_sha256"}
    _exact_keys(report, expected_keys, "report")
    if report["schema"] != REPORT_SCHEMA:
        raise ContractError("unsupported report schema")
    receipt = report["receipt_sha256"]
    if not isinstance(receipt, str) or not _SHA256.fullmatch(receipt):
        raise ContractError("invalid report receipt")
    historical_payload = {key: value for key, value in report.items() if key != "receipt_sha256"}
    historical_receipt_valid = _digest(historical_payload) == receipt
    current_now = _trusted_time(current_as_of, "current_as_of")
    evaluated_at = _utc(report["evaluated_at"], "report.evaluated_at")
    report_not_future = evaluated_at <= current_now
    historical = compile_packet(packet, as_of=evaluated_at)
    historical_exact = historical == report
    current = compile_packet(packet, as_of=current_now)
    current_same_state = current["state_sha256"] == report["state_sha256"]
    current_usable = current_same_state and current["readiness"] == "READY_FOR_OWNER_SEND_REVIEW" and current["request_live"]
    verdict = "CURRENT_VERIFIED" if historical_receipt_valid and historical_exact and report_not_future and current_usable else "STALE_OR_DRIFTED"
    payload = {
        "schema": VERIFY_SCHEMA,
        "verdict": verdict,
        "historical_receipt_valid": historical_receipt_valid,
        "historical_exact": historical_exact,
        "current_same_state": current_same_state,
        "current_readiness": current["readiness"],
        "current_request_live": current["request_live"],
        "report_receipt_sha256": receipt,
        "current_state_sha256": current["state_sha256"],
    }
    return {**payload, "receipt_sha256": _digest(payload)}


def render_markdown(report: Mapping[str, Any]) -> str:
    if report.get("schema") != REPORT_SCHEMA:
        raise ContractError("not a technical capability report")
    lines = [
        "# Technical Capability Packet",
        "",
        f"**Readiness:** `{report['readiness']}`  ",
        f"**Request:** `{report['request_id']}` generation `{report['request_generation']}`  ",
        f"**Evidence receipt:** `{report['receipt_sha256']}`",
        "",
        "## Requirement coverage",
        "",
    ]
    for row in report["requirements"]:
        lines.append(f"- **{row['status']}** — {row['title']} (`{row['requirement_id']}`)")
        if row["missing_claims"]:
            lines.append(f"  - Missing evidence: {', '.join(row['missing_claims'])}")
        if row["unsupported_claims"]:
            lines.append(f"  - Explicitly unsupported: {', '.join(row['unsupported_claims'])}")
        if row["stale_only_claims"]:
            lines.append(f"  - Stale-only evidence: {', '.join(row['stale_only_claims'])}")
    lines += ["", "## Selected proof", ""]
    for asset in report["selected_proof"]:
        lines.append(f"- [{asset['asset_id']}]({asset['uri']}) — {asset['kind']} — SHA-256 `{asset['sha256']}`")
        for limitation in asset["limitations"]:
            lines.append(f"  - Limitation: {limitation}")
    step = report["paid_next_step"]
    lines += [
        "",
        "## Proposed paid next step",
        "",
        f"**Status:** `{step['status']}` (proposal only; not buyer acceptance)  ",
        f"**Offer:** `{step['offer_id']}` — {step['amount_minor']} minor units {step['currency']} — {step['duration_days']} day(s)",
        "",
        step["scope"],
        "",
        "**Deliverables**",
    ]
    lines.extend(f"- {item}" for item in step["deliverables"])
    lines += ["", "**Dependencies**"]
    lines.extend(f"- {item}" for item in step["dependencies"])
    lines += ["", "**Acceptance criteria**"]
    lines.extend(f"- {item}" for item in step["acceptance_criteria"])
    lines += [
        "",
        "## Authority ceiling",
        "",
        "This packet does not authorize outbound contact, establish buyer acceptance, prove payment, or authorize revenue recognition.",
        "",
    ]
    return "\n".join(lines)
