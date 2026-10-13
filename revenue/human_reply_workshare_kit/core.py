from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Mapping

SCHEMA = "human-reply-paid-workshare/v1"
COMMERCIAL_STATE = "PROPOSED_NOT_ACCEPTED"

_PACKS: dict[str, dict[str, Any]] = {
    "DATA_MIGRATION_ACCEPTANCE": {
        "name": "Data Migration + Integration Acceptance Workshare",
        "fee_min_minor": 1_800_000,
        "fee_reference_minor": 3_000_000,
        "fee_max_minor": 4_500_000,
        "duration_min": 10,
        "duration_reference": 15,
        "duration_max": 25,
        "summary": (
            "Bounded legacy-to-target migration reconciliation, interface replay/idempotency, "
            "UAT/cutover evidence, and exception closure."
        ),
        "deliverables": (
            "source-to-target field/count/value reconciliation matrix",
            "interface replay/idempotency evidence for agreed fixtures and failure cases",
            "exception ledger with owner/disposition and retained evidence references",
            "UAT/cutover acceptance pack with rerun instructions and immutable source/test receipt",
        ),
        "acceptance": (
            "agreed source/target fixtures reconcile within the written tolerance or remain explicit HOLD exceptions",
            "named duplicate/replay/failure cases are demonstrated fail-closed",
            "buyer or prime can rerun the supplied acceptance checks from the documented inputs",
            "final exception ledger contains no silently dropped rows, interfaces, or unresolved ownership",
        ),
        "exclusions": (
            "prime/vendor product replacement",
            "production cutover authority or buyer signatory authority",
            "open-ended data cleansing or indefinite managed services",
            "credential harvesting, unsupervised production mutation, or unsupported compliance certification",
        ),
        "intake_gates": (
            "written source/target boundary and authoritative owner for each system",
            "representative buyer-supplied export/schema plus explicit row/interface bounds",
            "named acceptance owner and agreed exception/tolerance policy",
            "non-production fixture path first; production credentials are not required for qualification",
        ),
        "retained_authority": (
            "prime/vendor architecture and product commitments",
            "buyer security, privacy, legal, compliance, and production-access decisions",
            "buyer acceptance, signature, payment, award, and cutover authority",
        ),
    },
    "RESPONSIBLE_AI_EVALUATION": {
        "name": "Responsible-AI / LLM Evaluation + Governance Evidence Workshare",
        "fee_min_minor": 1_500_000,
        "fee_reference_minor": 2_400_000,
        "fee_max_minor": 4_000_000,
        "duration_min": 10,
        "duration_reference": 15,
        "duration_max": 20,
        "summary": (
            "Bounded model/system evaluation, role-based acceptance testing, governance-evidence mapping, "
            "and deterministic evidence-pack delivery."
        ),
        "deliverables": (
            "frozen evaluation matrix binding roles, scenarios, expected behavior, and evidence sources",
            "deterministic evaluation harness or replay procedure for agreed model/system surfaces",
            "failure/exception ledger covering safety, reliability, traceability, and governance gaps",
            "acceptance/governance evidence pack with source/test receipts and rerun instructions",
        ),
        "acceptance": (
            "all agreed scenarios execute or remain explicit HOLD with reproducible failure evidence",
            "reported findings bind to frozen inputs/model or system revision and evaluator version",
            "governance mappings cite supplied requirements without claiming certification or legal sufficiency",
            "buyer or prime can rerun the agreed evaluation procedure and reproduce the evidence packet",
        ),
        "exclusions": (
            "model/vendor replacement or open-ended prompt engineering",
            "legal, regulatory, medical, security, or compliance certification",
            "guarantees of model safety, accuracy, ROI, approval, or procurement outcome",
            "production credential custody or autonomous deployment authority",
        ),
        "intake_gates": (
            "written evaluation boundary, system/model revision, roles, and success/failure semantics",
            "buyer-supplied policy/requirement sources or an explicit statement that none are authoritative",
            "representative non-sensitive fixtures or approved synthetic test data",
            "named acceptance/governance owner and change-control rule for source/model drift",
        ),
        "retained_authority": (
            "buyer/prime model choice, policy interpretation, risk acceptance, and production deployment",
            "buyer legal/compliance/privacy/security decisions",
            "buyer acceptance, signature, payment, award, and public claims",
        ),
    },
    "FINANCIAL_EVIDENCE_RECONCILIATION": {
        "name": "Operational / Financial Evidence Reconciliation Workshare",
        "fee_min_minor": 650_000,
        "fee_reference_minor": 1_250_000,
        "fee_max_minor": 2_500_000,
        "duration_min": 5,
        "duration_reference": 10,
        "duration_max": 15,
        "summary": (
            "Read-only reconciliation of a bounded closed period using buyer-retained operational, "
            "invoice/settlement, approval, and credit evidence."
        ),
        "deliverables": (
            "canonical evidence manifest and normalization/reconciliation rules",
            "deterministic variance/exception ledger with duplicate, missing, orphan, timing, and mismatch classes",
            "owner-review packet binding each material exception to retained source evidence",
            "rerun script/procedure plus close receipt for the bounded period",
        ),
        "acceptance": (
            "all in-scope retained rows are accounted for exactly once or remain explicit HOLD exceptions",
            "totals and classifications reproduce from the frozen buyer-supplied inputs",
            "no exception is represented as fraud, savings, recovery, or accounting conclusion without buyer authority",
            "buyer or prime can rerun the reconciliation and reproduce the owner-review packet",
        ),
        "exclusions": (
            "payment initiation, accounting/ERP mutation, dispute filing, or provider/carrier contact",
            "audit opinion, tax/legal/accounting advice, fraud finding, or savings/recovery guarantee",
            "open-ended bookkeeping, collections, or managed AP/AR services",
            "production credentials during qualification",
        ),
        "intake_gates": (
            "one named legal entity, one closed period, one currency, and explicit evidence-source boundary",
            "buyer-supplied retained exports plus owner mapping for rate/contract/approval authority",
            "written materiality/tolerance rules or explicit zero-tolerance default",
            "named owner for exception disposition and acceptance",
        ),
        "retained_authority": (
            "buyer/provider contract interpretation and accounting policy",
            "buyer approval, dispute, posting, payment, recovery, and write-off actions",
            "buyer acceptance, signature, payment, award, and revenue recognition",
        ),
    },
}

_FORBIDDEN_SCOPE_ASSERTIONS = (
    re.compile(r"\bbuyer (?:has )?accepted\b", re.I),
    re.compile(r"\b(?:we|tjlabs) (?:have |has )?(?:been )?awarded\b", re.I),
    re.compile(r"\baward (?:is )?secured\b", re.I),
    re.compile(r"\b(?:already |were |was )?paid\b", re.I),
    re.compile(r"\bpayment (?:was |is )?received\b", re.I),
    re.compile(r"\bbooked revenue\b", re.I),
    re.compile(r"\brecognized revenue\b", re.I),
    re.compile(r"\bsigned contract\b", re.I),
    re.compile(r"\b(?:existing|current) customer\b", re.I),
    re.compile(r"\bguaranteed (?:savings|outcome|roi|acceptance|award)\b", re.I),
)
_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_SAFE_LABEL_RE = re.compile(r"^[^\x00\r\n]{1,160}$")


class WorkshareError(ValueError):
    pass


@dataclass(frozen=True)
class CompiledOffer:
    normalized: Mapping[str, Any]
    markdown: str
    receipt_sha256: str


def _reject_float(_: str) -> None:
    raise WorkshareError("floats are not allowed")


def _parse_int(token: str) -> int:
    if len(token.lstrip("-")) > 128:
        raise WorkshareError("integer token too long")
    return int(token)


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise WorkshareError(f"duplicate key: {key}")
        out[key] = value
    return out


def strict_json_loads(raw: str) -> Any:
    try:
        return json.loads(
            raw,
            object_pairs_hook=_pairs,
            parse_float=_reject_float,
            parse_int=_parse_int,
            parse_constant=_reject_float,
        )
    except WorkshareError:
        raise
    except (json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise WorkshareError(f"invalid JSON: {exc}") from None


def canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ) + "\n"
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise WorkshareError(f"cannot canonicalize: {exc}") from None


def _expect_map(value: Any, where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise WorkshareError(f"{where} must be an object")
    return value


def _exact_keys(obj: Mapping[str, Any], expected: set[str], where: str) -> None:
    actual = set(obj)
    if actual != expected:
        raise WorkshareError(
            f"{where} keys mismatch; missing={sorted(expected - actual)} extra={sorted(actual - expected)}"
        )


def _plain_str(value: Any, where: str, *, max_len: int) -> str:
    if not isinstance(value, str) or not value or len(value) > max_len:
        raise WorkshareError(f"{where} must be a non-empty string <= {max_len}")
    if "\x00" in value or "\r" in value or "\n" in value:
        raise WorkshareError(f"{where} must be one line")
    try:
        value.encode("utf-8", "strict")
    except UnicodeEncodeError:
        raise WorkshareError(f"{where} must be Unicode scalar text") from None
    return value


def _token(value: Any, where: str) -> str:
    value = _plain_str(value, where, max_len=128)
    if not _TOKEN_RE.fullmatch(value):
        raise WorkshareError(f"{where} has invalid token characters")
    return value


def _label(value: Any, where: str) -> str:
    value = _plain_str(value, where, max_len=160)
    if not _SAFE_LABEL_RE.fullmatch(value):
        raise WorkshareError(f"{where} has unsafe label characters")
    value = value.strip()
    if not value:
        raise WorkshareError(f"{where} must not be blank")
    return value


def _int(value: Any, where: str, *, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise WorkshareError(f"{where} must be an integer")
    if value < low or value > high:
        raise WorkshareError(f"{where} out of range [{low}, {high}]")
    return value


def _list_of_lines(value: Any, where: str, *, minimum: int = 1, maximum: int = 8) -> list[str]:
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise WorkshareError(f"{where} must be an array of {minimum}..{maximum} one-line strings")
    out: list[str] = []
    for i, item in enumerate(value):
        text = _plain_str(item, f"{where}[{i}]", max_len=240).strip()
        if not text:
            raise WorkshareError(f"{where}[{i}] must not be blank")
        if text in out:
            raise WorkshareError(f"{where} contains duplicate item")
        out.append(text)
    return out


def _scope_text(value: Any) -> str:
    text = _plain_str(value, "scope.one_line", max_len=320).strip()
    if not text:
        raise WorkshareError("scope.one_line must not be blank")
    for pattern in _FORBIDDEN_SCOPE_ASSERTIONS:
        if pattern.search(text):
            raise WorkshareError("scope.one_line contains unsupported commercial/outcome assertion")
    return text


def _evidence_state(value: Any) -> dict[str, bool]:
    value = _expect_map(value, "evidence_state")
    keys = {
        "buyer_accepted",
        "customer_relationship",
        "contract_signed",
        "invoice_issued",
        "payment_settled",
        "booked_revenue",
        "recognized_revenue",
    }
    _exact_keys(value, keys, "evidence_state")
    out: dict[str, bool] = {}
    for key in sorted(keys):
        item = value[key]
        if not isinstance(item, bool):
            raise WorkshareError(f"evidence_state.{key} must be boolean")
        if item:
            raise WorkshareError(
                f"evidence_state.{key}=true is outside this qualification/proposal compiler; "
                "bind accepted/paid state in a separate evidence-backed workflow"
            )
        out[key] = False
    return out


def _money_text(amount_minor: int) -> str:
    whole, frac = divmod(amount_minor, 100)
    return f"${whole:,}.{frac:02d} USD"


def pack_catalog() -> dict[str, dict[str, Any]]:
    return json.loads(json.dumps(_PACKS))


def normalize_offer(raw: Mapping[str, Any]) -> dict[str, Any]:
    raw = _expect_map(raw, "root")
    _exact_keys(
        raw,
        {
            "schema",
            "offer_id",
            "pack_id",
            "counterparty_label",
            "opportunity_label",
            "commercial_state",
            "offer",
            "scope",
            "evidence_state",
        },
        "root",
    )
    if raw["schema"] != SCHEMA:
        raise WorkshareError(f"schema must be {SCHEMA}")
    pack_id = _token(raw["pack_id"], "pack_id")
    if pack_id not in _PACKS:
        raise WorkshareError(f"unknown pack_id: {pack_id}")
    if raw["commercial_state"] != COMMERCIAL_STATE:
        raise WorkshareError(f"commercial_state must be {COMMERCIAL_STATE}")

    pack = _PACKS[pack_id]
    offer = _expect_map(raw["offer"], "offer")
    _exact_keys(
        offer,
        {"amount_minor", "currency", "decimals", "duration_business_days"},
        "offer",
    )
    amount_minor = _int(
        offer["amount_minor"],
        "offer.amount_minor",
        low=int(pack["fee_min_minor"]),
        high=int(pack["fee_max_minor"]),
    )
    if offer["currency"] != "USD":
        raise WorkshareError("offer.currency must be USD")
    if offer["decimals"] != 2:
        raise WorkshareError("offer.decimals must be 2")
    duration = _int(
        offer["duration_business_days"],
        "offer.duration_business_days",
        low=int(pack["duration_min"]),
        high=int(pack["duration_max"]),
    )

    scope = _expect_map(raw["scope"], "scope")
    _exact_keys(scope, {"one_line", "input_bounds"}, "scope")
    normalized = {
        "schema": SCHEMA,
        "offer_id": _token(raw["offer_id"], "offer_id"),
        "pack_id": pack_id,
        "counterparty_label": _label(raw["counterparty_label"], "counterparty_label"),
        "opportunity_label": _label(raw["opportunity_label"], "opportunity_label"),
        "commercial_state": COMMERCIAL_STATE,
        "offer": {
            "amount_minor": amount_minor,
            "currency": "USD",
            "decimals": 2,
            "duration_business_days": duration,
        },
        "scope": {
            "one_line": _scope_text(scope["one_line"]),
            "input_bounds": _list_of_lines(scope["input_bounds"], "scope.input_bounds"),
        },
        "evidence_state": _evidence_state(raw["evidence_state"]),
    }
    return normalized


def _milestones(duration: int) -> tuple[tuple[str, int, str], ...]:
    intake_day = max(1, min(3, (duration + 4) // 5))
    draft_day = max(intake_day + 1, (duration * 2 + 2) // 3)
    if draft_day >= duration:
        draft_day = duration - 1
    return (
        (
            "Boundary + acceptance lock",
            intake_day,
            "written scope, authoritative inputs/owners, and acceptance semantics frozen",
        ),
        (
            "Deterministic draft evidence pack",
            draft_day,
            "agreed fixtures replayed; exceptions emitted fail-closed with owner/evidence binding",
        ),
        (
            "Final acceptance handoff",
            duration,
            "rerun instructions, final exception ledger, and source/test receipt delivered",
        ),
    )


def render_offer_markdown(normalized: Mapping[str, Any]) -> str:
    pack = _PACKS[str(normalized["pack_id"])]
    offer = normalized["offer"]
    duration = int(offer["duration_business_days"])
    lines = [
        f"# {pack['name']}",
        "",
        f"**{COMMERCIAL_STATE} — qualification/workshare proposal only; no acceptance, contract, invoice, payment, or revenue is asserted.**",
        "",
        f"- Counterparty: {normalized['counterparty_label']}",
        f"- Opportunity: {normalized['opportunity_label']}",
        f"- Proposed fixed fee: {_money_text(int(offer['amount_minor']))}",
        f"- Target delivery: {duration} business days after complete, accepted intake",
        f"- Offer ID: `{normalized['offer_id']}`",
        "",
        "## Bounded scope",
        f"{pack['summary']} Specific boundary: {normalized['scope']['one_line']}",
        "",
        "Input bounds:",
    ]
    lines.extend(f"- {item}" for item in normalized["scope"]["input_bounds"])
    lines += ["", "## Deliverables"]
    lines.extend(f"- {item}" for item in pack["deliverables"])
    lines += ["", "## Acceptance"]
    lines.extend(f"- {item}" for item in pack["acceptance"])
    lines += ["", "## Milestones"]
    for name, day, gate in _milestones(duration):
        lines.append(f"- **Day {day}: {name}.** {gate}.")
    lines += ["", "## Intake + security gates"]
    lines.extend(f"- {item}" for item in pack["intake_gates"])
    lines += ["", "## Authority retained by buyer / prime"]
    lines.extend(f"- {item}" for item in pack["retained_authority"])
    lines += ["", "## Explicit exclusions"]
    lines.extend(f"- {item}" for item in pack["exclusions"])
    lines += [
        "",
        "## Commercial truth boundary",
        f"- State is `{COMMERCIAL_STATE}` until a separately evidenced acceptance event exists.",
        "- This artifact does not prove a customer relationship, signed contract, issued invoice, settlement, booked revenue, or recognized revenue.",
        "- Any scope, price, deadline, source, currency, or acceptance change requires a new offer revision; do not silently roll old terms forward.",
        "",
        "## Next step",
        "If this workshare is useful, name the delivery/acceptance owner and confirm the bounded intake. No commitment is assumed from routing, interest, or silence.",
        "",
    ]
    return "\n".join(lines)


def compile_offer(raw: Mapping[str, Any]) -> CompiledOffer:
    normalized = normalize_offer(raw)
    encoded = canonical_json(normalized).encode("utf-8")
    receipt = hashlib.sha256(encoded).hexdigest()
    return CompiledOffer(
        normalized=normalized,
        markdown=render_offer_markdown(normalized),
        receipt_sha256=receipt,
    )


def render_receipt_json(compiled: CompiledOffer) -> str:
    return canonical_json(
        {
            "schema": "human-reply-paid-workshare-receipt/v1",
            "offer_id": compiled.normalized["offer_id"],
            "pack_id": compiled.normalized["pack_id"],
            "commercial_state": COMMERCIAL_STATE,
            "normalized_sha256": compiled.receipt_sha256,
        }
    )
