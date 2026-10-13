from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import re
from typing import Any, Mapping
from urllib.parse import urlparse

SCHEMA = "proof-to-paid-work-input/v1"
PRIVATE_SCHEMA = "proof-to-paid-work-private/v1"
PUBLIC_SCHEMA = "proof-to-paid-work-public/v1"
RECEIPT_SCHEMA = "proof-to-paid-work-receipt/v1"

_ALLOWED_WORK_STATES = {"OPEN", "DELIVERED", "MERGED", "ACCEPTED", "REJECTED"}
_ALLOWED_SETTLEMENT_STATES = {"UNKNOWN", "UNPAID", "SETTLED"}
_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_CURRENCY_RE = re.compile(r"^[A-Z0-9]{2,8}$")
_SAFE_LABEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 .,&()'/_+-]{0,79}$")
_FORBIDDEN_PUBLIC_KEYS = {
    "sponsor_label", "task_url", "work_url", "provider_evidence_refs",
    "acceptance_evidence_refs", "private_evidence_refs", "settled_at",
    "amount_minor", "currency", "work_id",
}

SERVICE_MENU = (
    {
        "service_id": "EVIDENCE_RECON_DIAGNOSTIC",
        "name": "Evidence Reconciliation Diagnostic",
        "reference_price_usd_minor": 500000,
        "reference_duration_business_days": 5,
        "commercial_state": "PROPOSED_NOT_ACCEPTED",
        "acceptance": (
            "owner-supplied bounded evidence ingested",
            "deterministic exception packet delivered",
            "receipt and rerun instructions reproduce the packet",
        ),
        "exclusions": (
            "staffing", "platform replacement", "customer/provider mutation",
            "legal/accounting/compliance opinion",
        ),
    },
    {
        "service_id": "INTEGRATION_ACCEPTANCE_SPRINT",
        "name": "Integration & Acceptance Sprint",
        "reference_price_usd_minor": 1500000,
        "reference_duration_business_days": 10,
        "commercial_state": "PROPOSED_NOT_ACCEPTED",
        "acceptance": (
            "agreed interface/input fixture passes",
            "named failure cases fail closed",
            "handoff includes deterministic test and evidence receipts",
        ),
        "exclusions": (
            "staffing", "platform replacement", "production credentials during qualification",
            "buyer signatory authority",
        ),
    },
    {
        "service_id": "DETERMINISTIC_REPAIR_SPRINT",
        "name": "Deterministic Repair Sprint",
        "reference_price_usd_minor": 1000000,
        "reference_duration_business_days": 10,
        "commercial_state": "PROPOSED_NOT_ACCEPTED",
        "acceptance": (
            "predecessor bug has a reproducible failing fixture",
            "repair makes that fixture pass without weakening retained guards",
            "source/test receipt binds the delivered revision",
        ),
        "exclusions": (
            "staff augmentation", "open-ended maintenance", "unbounded production access",
            "outcome or savings guarantee",
        ),
    },
)

PUBLIC_CASE_STUDY_TEMPLATE = """# Bounded paid-work delivery pattern

This is a **template**, not a claim about a named customer, sponsor, payment, or outcome.

1. Start from an explicitly priced task or fixed-fee workshare.
2. Bind the exact task source, advertised amount/currency, and acceptance mechanism.
3. Deliver a bounded implementation, repair, integration, or QA artifact with reproducible tests.
4. Bind maintainer/buyer acceptance or merge separately from the work artifact.
5. If payment remains due, request the **advertised amount in the advertised currency** and link the accepted/merged work.
6. Record settlement evidence separately. Do not convert a non-USD award to USD without separately authoritative conversion evidence.

Every arrow is an evidence boundary. A task listing is not acceptance; a merge is not settlement; a settlement is not customer endorsement or recognized revenue.
"""


class KitError(ValueError):
    pass


@dataclass(frozen=True)
class CompiledKit:
    private: Mapping[str, Any]
    public: Mapping[str, Any]
    receipt_sha256: str


def _reject_float(_: str) -> None:
    raise KitError("floats are not allowed")


def _parse_int(token: str) -> int:
    if len(token.lstrip("-")) > 128:
        raise KitError("integer token too long")
    return int(token)


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise KitError(f"duplicate key: {key}")
        out[key] = value
    return out


def strict_json_loads(raw: str) -> Any:
    try:
        return json.loads(raw, object_pairs_hook=_pairs, parse_float=_reject_float,
                          parse_int=_parse_int, parse_constant=_reject_float)
    except KitError:
        raise
    except (json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise KitError(f"invalid JSON: {exc}") from None


def canonical_json(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                          allow_nan=False) + "\n"
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise KitError(f"cannot canonicalize: {exc}") from None


def _expect_map(value: Any, where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise KitError(f"{where} must be an object")
    return value


def _exact_keys(obj: Mapping[str, Any], expected: set[str], where: str) -> None:
    actual = set(obj)
    if actual != expected:
        raise KitError(f"{where} keys mismatch; missing={sorted(expected-actual)} extra={sorted(actual-expected)}")


def _plain_str(value: Any, where: str, *, max_len: int = 512) -> str:
    if not isinstance(value, str) or not value or len(value) > max_len:
        raise KitError(f"{where} must be a non-empty string <= {max_len}")
    if "\x00" in value or "\r" in value or "\n" in value:
        raise KitError(f"{where} must be one line")
    try:
        value.encode("utf-8", "strict")
    except UnicodeEncodeError:
        raise KitError(f"{where} must be Unicode scalar text") from None
    return value


def _token(value: Any, where: str) -> str:
    value = _plain_str(value, where, max_len=128)
    if not _TOKEN_RE.fullmatch(value):
        raise KitError(f"{where} has invalid token characters")
    return value


def _label(value: Any, where: str) -> str:
    value = _plain_str(value, where, max_len=80)
    if not _SAFE_LABEL_RE.fullmatch(value):
        raise KitError(f"{where} has unsafe label characters")
    return value


def _https_url(value: Any, where: str) -> str:
    value = _plain_str(value, where, max_len=512)
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise KitError(f"{where} must be an https URL without credentials")
    if parsed.fragment:
        raise KitError(f"{where} must not contain a fragment")
    return value


def _int(value: Any, where: str, *, low: int = 0, high: int = 10**18) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise KitError(f"{where} must be an integer")
    if value < low or value > high:
        raise KitError(f"{where} out of range")
    return value


def _currency(value: Any, where: str) -> str:
    value = _plain_str(value, where, max_len=8)
    if not _CURRENCY_RE.fullmatch(value):
        raise KitError(f"{where} must be 2-8 uppercase letters/digits")
    return value


def _timestamp(value: Any, where: str) -> str:
    value = _plain_str(value, where, max_len=64)
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        raise KitError(f"{where} must be ISO-8601") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise KitError(f"{where} must include a timezone")
    return value


def _refs(value: Any, where: str) -> list[str]:
    if not isinstance(value, list) or len(value) > 32:
        raise KitError(f"{where} must be an array of <=32 refs")
    out: list[str] = []
    for i, ref in enumerate(value):
        ref = _plain_str(ref, f"{where}[{i}]", max_len=256)
        if ref in out:
            raise KitError(f"{where} contains duplicate ref")
        out.append(ref)
    return out


def _money(obj: Any, where: str) -> dict[str, Any]:
    obj = _expect_map(obj, where)
    _exact_keys(obj, {"amount_minor", "currency", "decimals"}, where)
    return {
        "amount_minor": _int(obj["amount_minor"], f"{where}.amount_minor", low=1),
        "currency": _currency(obj["currency"], f"{where}.currency"),
        "decimals": _int(obj["decimals"], f"{where}.decimals", low=0, high=8),
    }


def _display_money(money: Mapping[str, Any]) -> str:
    amount, decimals, currency = int(money["amount_minor"]), int(money["decimals"]), str(money["currency"])
    if decimals == 0:
        numeric = str(amount)
    else:
        whole, frac = divmod(amount, 10 ** decimals)
        numeric = f"{whole}.{frac:0{decimals}d}"
    return f"${numeric} USD" if currency == "USD" else f"{numeric} {currency}"


def _settlement(obj: Any) -> dict[str, Any]:
    obj = _expect_map(obj, "settlement")
    _exact_keys(obj, {"state", "amount", "settled_at", "provider_evidence_refs"}, "settlement")
    state = _plain_str(obj["state"], "settlement.state", max_len=16)
    if state not in _ALLOWED_SETTLEMENT_STATES:
        raise KitError("settlement.state invalid")
    refs = _refs(obj["provider_evidence_refs"], "settlement.provider_evidence_refs")
    amount, settled_at = obj["amount"], obj["settled_at"]
    if state == "SETTLED":
        if not refs:
            raise KitError("SETTLED assertion requires provider evidence refs")
        amount = _money(amount, "settlement.amount")
        settled_at = _timestamp(settled_at, "settlement.settled_at")
    else:
        if amount is not None or settled_at is not None or refs:
            raise KitError(f"{state} settlement must not carry settlement evidence")
        amount, settled_at = None, None
    return {"state": state, "amount": amount, "settled_at": settled_at,
            "provider_evidence_refs": refs}


def normalize_input(raw: Mapping[str, Any]) -> dict[str, Any]:
    raw = _expect_map(raw, "root")
    _exact_keys(raw, {"schema", "work_id", "sponsor_label", "task", "work", "settlement",
                      "private_evidence_refs"}, "root")
    if raw["schema"] != SCHEMA:
        raise KitError(f"schema must be {SCHEMA}")
    task, work = _expect_map(raw["task"], "task"), _expect_map(raw["work"], "work")
    _exact_keys(task, {"public_url", "advertised_award"}, "task")
    _exact_keys(work, {"public_url", "state", "acceptance_evidence_refs"}, "work")
    work_state = _plain_str(work["state"], "work.state", max_len=16)
    if work_state not in _ALLOWED_WORK_STATES:
        raise KitError("work.state invalid")
    acceptance_refs = _refs(work["acceptance_evidence_refs"], "work.acceptance_evidence_refs")
    if work_state == "ACCEPTED" and not acceptance_refs:
        raise KitError("ACCEPTED requires acceptance evidence refs")
    if work_state in {"OPEN", "DELIVERED"} and acceptance_refs:
        raise KitError(f"{work_state} must not carry acceptance evidence refs")
    advertised, settlement = _money(task["advertised_award"], "task.advertised_award"), _settlement(raw["settlement"])
    if settlement["state"] == "SETTLED":
        settled_money = settlement["amount"]
        if settled_money["currency"] != advertised["currency"] or settled_money["decimals"] != advertised["decimals"]:
            raise KitError("v1 refuses settlement currency/decimal conversion; bind native award only")
    return {
        "schema": SCHEMA,
        "work_id": _token(raw["work_id"], "work_id"),
        "sponsor_label": _label(raw["sponsor_label"], "sponsor_label"),
        "task": {"public_url": _https_url(task["public_url"], "task.public_url"), "advertised_award": advertised},
        "work": {"public_url": _https_url(work["public_url"], "work.public_url"), "state": work_state,
                 "acceptance_evidence_refs": acceptance_refs},
        "settlement": settlement,
        "private_evidence_refs": _refs(raw["private_evidence_refs"], "private_evidence_refs"),
    }


def _payment_request(record: Mapping[str, Any]) -> dict[str, Any]:
    if record["settlement"]["state"] == "SETTLED":
        return {"state": "HOLD_ALREADY_SETTLED", "markdown": None}
    if record["work"]["state"] not in {"MERGED", "ACCEPTED"}:
        return {"state": "HOLD_WORK_NOT_ACCEPTED_OR_MERGED", "markdown": None}
    amount, work_url, work_id = _display_money(record["task"]["advertised_award"]), record["work"]["public_url"], record["work_id"]
    markdown = (f"Payment request for {work_id}\n\nThe work is merged/accepted here: {work_url}\n\n"
                f"Please send the advertised {amount} award for this work.\n")
    if any(p in markdown.lower() for p in ("am i eligible", "eligibility", "do i qualify", "can i be paid")):
        raise KitError("payment request must not fish for eligibility")
    return {"state": "REQUEST_READY_INTERNAL_DRAFT", "markdown": markdown}


def _private_case_study(record: Mapping[str, Any]) -> str:
    award, settlement = _display_money(record["task"]["advertised_award"]), record["settlement"]
    if settlement["state"] == "SETTLED":
        settlement_line = (f"- Settlement assertion: ASSERTED_SETTLED at {_display_money(settlement['amount'])}; "
                           "provider refs retained privately; this compiler does not independently authenticate them.")
    elif settlement["state"] == "UNPAID":
        settlement_line = "- Settlement assertion: ASSERTED_UNPAID."
    else:
        settlement_line = "- Settlement assertion: UNKNOWN."
    return (
        "# Internal paid-work case-study draft\n\n**PRIVATE / INPUT-ASSERTION ONLY / NOT PUBLICATION AUTHORITY**\n\n"
        f"- Work ID: {record['work_id']}\n- Sponsor label: {record['sponsor_label']}\n- Advertised award: {award}\n"
        f"- Task: {record['task']['public_url']}\n- Delivered work: {record['work']['public_url']}\n"
        f"- Work state assertion: {record['work']['state']}\n{settlement_line}\n\n"
        "Pattern: explicit priced task -> bounded work -> independently evidenced merge/acceptance -> direct request "
        "for the advertised native-currency amount if still due -> separate settlement evidence.\n\n"
        "Do not infer endorsement, savings, customer outcome, booked/recognized revenue, or USD value for a non-USD award from this draft.\n"
    )


def _public_projection() -> dict[str, Any]:
    services = [{"service_id": x["service_id"], "name": x["name"],
                 "reference_price_usd_minor": x["reference_price_usd_minor"],
                 "reference_duration_business_days": x["reference_duration_business_days"],
                 "commercial_state": x["commercial_state"], "acceptance": list(x["acceptance"]),
                 "exclusions": list(x["exclusions"])} for x in SERVICE_MENU]
    return {
        "schema": PUBLIC_SCHEMA, "state": "GENERIC_TEMPLATE_ONLY",
        "real_engagement_claims_authorized": False, "payment_claim_authorized": False,
        "cash_claim_authorized": False, "revenue_claim_authorized": False,
        "token_to_usd_conversion_authorized": False,
        "case_study_template": PUBLIC_CASE_STUDY_TEMPLATE, "service_menu": services,
        "advertised_bounty_request_template": (
            "Link the accepted/merged work and directly request the advertised amount in the advertised currency. "
            "Do not ask whether you are eligible."
        ),
        "verified_paid_proof_dependency": (
            "Any future real public payment claim requires a separately authoritative publication-safe result "
            "from revenue/verified_paid_proof or its successor."
        ),
    }


def _assert_public_safe(public: Mapping[str, Any]) -> None:
    serialized, obj = canonical_json(public), json.loads(canonical_json(public))
    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key in _FORBIDDEN_PUBLIC_KEYS:
                    raise KitError(f"public projection leaked forbidden key: {key}")
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
    walk(obj)
    if "https://" in serialized or re.search(r"\b[0-9a-f]{64}\b", serialized):
        raise KitError("public projection contains a real locator/digest")
    for flag in ("real_engagement_claims_authorized", "payment_claim_authorized", "cash_claim_authorized",
                 "revenue_claim_authorized", "token_to_usd_conversion_authorized"):
        if obj.get(flag) is not False:
            raise KitError(f"{flag} must remain false")


def compile_kit(raw: Mapping[str, Any]) -> CompiledKit:
    record = normalize_input(raw)
    settlement = record["settlement"]
    financial_truth = {
        "settlement_state": "ASSERTED_SETTLED" if settlement["state"] == "SETTLED" else "ASSERTED_UNPAID" if settlement["state"] == "UNPAID" else "UNKNOWN",
        "provider_settlement_independently_verified_by_this_compiler": False,
        "cash_usd_minor": None, "booked_revenue": False, "recognized_revenue": False, "usd_conversion": None,
    }
    if settlement["state"] == "SETTLED" and settlement["amount"]["currency"] != "USD":
        financial_truth["native_currency_only"] = _display_money(settlement["amount"])
        financial_truth["conversion_state"] = "NO_USD_CONVERSION"
    private = {
        "schema": PRIVATE_SCHEMA, "authority_state": "INPUT_ASSERTION_ONLY", "normalized_record": record,
        "financial_truth": financial_truth, "case_study_markdown": _private_case_study(record),
        "payment_request": _payment_request(record), "outbound_authorized": False,
        "payment_provider_mutation_authorized": False, "publication_authorized": False,
    }
    public = _public_projection()
    _assert_public_safe(public)
    envelope = {"schema": RECEIPT_SCHEMA, "private": private, "public": public}
    receipt = hashlib.sha256(canonical_json(envelope).encode("utf-8")).hexdigest()
    return CompiledKit(private=private, public=public, receipt_sha256=receipt)


def render_private_json(compiled: CompiledKit) -> str:
    return canonical_json({"schema": PRIVATE_SCHEMA, "private": compiled.private, "receipt_sha256": compiled.receipt_sha256})


def render_public_json(compiled: CompiledKit) -> str:
    _assert_public_safe(compiled.public)
    return canonical_json(compiled.public)


def render_public_markdown(compiled: CompiledKit) -> str:
    _assert_public_safe(compiled.public)
    lines = ["# Proof-to-Paid Work Kit", "", "**GENERIC TEMPLATE ONLY — no named engagement/payment/revenue claim is authorized.**", "", PUBLIC_CASE_STUDY_TEMPLATE.rstrip(), "", "## Fixed-fee service menu", ""]
    for item in compiled.public["service_menu"]:
        price = _display_money({"amount_minor": item["reference_price_usd_minor"], "currency": "USD", "decimals": 2})
        lines += [f"### {item['name']}", f"- Reference: {price} / {item['reference_duration_business_days']} business days",
                  f"- Commercial state: {item['commercial_state']}", "- Acceptance:",
                  *[f"  - {x}" for x in item["acceptance"]], "- Exclusions:",
                  *[f"  - {x}" for x in item["exclusions"]], ""]
    lines += ["## Advertised-bounty payment request", "", "After independently establishing that work is merged/accepted and remains unpaid:", "",
              "> The work is merged/accepted here: <work URL>", ">", "> Please send the advertised <amount> <currency> award for this work.", "",
              "Do not ask whether you are eligible. Do not convert a non-USD award to USD without separately authoritative conversion evidence.", ""]
    return "\n".join(lines)


def validate_no_real_claims(public_text: str) -> None:
    if not isinstance(public_text, str):
        raise KitError("public text must be a string")
    dangerous = ("we were paid", "we received payment", "cash received", "recognized revenue", "booked revenue",
                 "customer approved", "buyer accepted", "converted to usd", "worth $")
    hit = [phrase for phrase in dangerous if phrase in public_text.lower()]
    if hit:
        raise KitError(f"unsupported real-world commercial claim(s): {hit}")
