"""Connector-native capability-chain prospect contact custody v2.

This module is an offline planner/verifier.  It never calls GitHub or a provider.
The authority event is create-exclusive deterministic branch creation performed
by a connector executor, then exact readback compiled here.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import unicodedata
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Mapping

SCHEMA = "prospect-contact-custody/v2"
CLAIM_PLAN_SCHEMA = "prospect-contact-custody-claim-plan/v2"
CLAIM_INTENT_SCHEMA = "prospect-contact-custody-claim-intent/v2"
CLAIM_RECEIPT_SCHEMA = "prospect-contact-custody-claim-receipt/v2"
TERMINAL_PLAN_SCHEMA = "prospect-contact-custody-terminal-plan/v2"
TERMINAL_INTENT_SCHEMA = "prospect-contact-custody-terminal-intent/v2"
TERMINAL_RECEIPT_SCHEMA = "prospect-contact-custody-terminal-receipt/v2"
REVEAL_PLAN_SCHEMA = "prospect-contact-custody-release-reveal-plan/v2"
REVEAL_INTENT_SCHEMA = "prospect-contact-custody-release-reveal-intent/v2"
REVEAL_RECEIPT_SCHEMA = "prospect-contact-custody-release-reveal-receipt/v2"
CONTACTED_PLAN_SCHEMA = "prospect-contact-custody-contacted-plan/v2"
CONTACTED_INTENT_SCHEMA = "prospect-contact-custody-contacted-intent/v2"
CONTACTED_RECEIPT_SCHEMA = "prospect-contact-custody-contacted-receipt/v2"

CLAIM_BRANCH_PREFIX = "prospect-contact-v2/claim/"
TERMINAL_BRANCH_PREFIX = "prospect-contact-v2/terminal/"
REVEAL_BRANCH_PREFIX = "prospect-contact-v2/reveal/"
CONTACTED_BRANCH_PREFIX = "prospect-contact-v2/contacted/"
METADATA_PREFIX = ".tjlabs/prospect-contact-v2/"
ZERO64 = "0" * 64
CAPABILITY_BYTES = 32
MAX_TEXT = 500

HEX40_RE = re.compile(r"^[0-9a-f]{40}$")
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,159}$")
PHONE_RE = re.compile(r"^\+[1-9][0-9]{7,14}$")
CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
_AMOUNT_RE = re.compile(
    r"(?:[$€£]\s*(?P<lead>[0-9][0-9,]*(?:\.[0-9]{1,2})?)|"
    r"(?P<trail>[0-9][0-9,]*(?:\.[0-9]{1,2})?)\s*(?:usd|eur|gbp|rtc)\b)",
    re.IGNORECASE,
)
_NEGATIVE_COMP_RE = re.compile(
    r"(?:\b(?:unpaid|gratis|volunteer|free)\b|\bpro\s+bono\b|"
    r"\b(?:no|not|without|zero)\s+(?:pay|paid|payment|fee|compensation|bounty|prize|invoice|commission|retainer)\b)",
    re.IGNORECASE,
)
_SIGNAL_PHRASES = (
    "paid", "payment", "bounty", "prize", "invoice", "fee", "commission",
    "award", "purchase order", "retainer", "contract", "subcontract", "bid",
    "pilot", "discovery",
)


class CustodyError(ValueError):
    pass


def _canon(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise CustodyError("value is not canonical JSON") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canon(value)).hexdigest()


def _text_digest(value: str) -> str:
    if type(value) is not str:
        raise CustodyError("text required")
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _token(value: Any, field: str) -> str:
    if type(value) is not str:
        raise CustodyError(f"{field} must be text")
    value = unicodedata.normalize("NFKC", value.strip())
    if not TOKEN_RE.fullmatch(value):
        raise CustodyError(f"{field} invalid")
    return value


def _sha40(value: Any, field: str) -> str:
    if type(value) is not str or not HEX40_RE.fullmatch(value):
        raise CustodyError(f"{field} must be lowercase git SHA-1")
    return value


def _sha64(value: Any, field: str) -> str:
    if type(value) is not str or not HEX64_RE.fullmatch(value):
        raise CustodyError(f"{field} must be lowercase SHA-256")
    return value


def _capability(value: Any) -> str:
    return _sha64(value, "capability")


def capability_commitment(capability: str) -> str:
    return hashlib.sha256(bytes.fromhex(_capability(capability))).hexdigest()


def _authority_flags() -> dict[str, bool]:
    return {
        "external_send_authorized": False,
        "provider_send_completed": False,
        "payment_or_revenue_inferred": False,
    }


def _check_authority_flags(raw: Mapping[str, Any]) -> None:
    for key, expected in _authority_flags().items():
        if raw.get(key) is not expected:
            raise CustodyError(f"{key} must remain false")


def _expected_sealed_fields(raw: Mapping[str, Any], seal_field: str) -> set[str]:
    schema = raw.get("schema")
    state = raw.get("state")
    flags = {"external_send_authorized", "provider_send_completed", "payment_or_revenue_inferred"}
    common_claim = {"generation", "key_sha256", "claim_seam_sha256", "claimant", "operation_id", "claim_capability_sha256"}
    if schema == CLAIM_PLAN_SCHEMA:
        fields = common_claim | {"schema", "target_kind", "target_hint", "prior_release_reveal_receipt_sha256", "anchor_sha", "preflight_sha256", "branch_name", "metadata_path", "metadata_sha256", "metadata_json", "plan_sha256"}
    elif schema == CLAIM_INTENT_SCHEMA:
        fields = common_claim | {"schema", "anchor_sha", "branch_name", "metadata_path", "metadata_sha256", "plan_sha256", "claim_commit_sha", "intent_sha256"}
    elif schema == CLAIM_RECEIPT_SCHEMA:
        fields = common_claim | {"schema", "state", "target_kind", "target_hint", "prior_release_reveal_receipt_sha256", "anchor_sha", "preflight_sha256", "branch_name", "metadata_path", "metadata_sha256", "metadata_json", "claim_commit_sha", "plan_sha256", "intent_sha256", "receipt_sha256"}
    elif schema == TERMINAL_PLAN_SCHEMA and state == "RELEASED_UNSENT":
        fields = {"schema", "state", "generation", "key_sha256", "claim_seam_sha256", "claim_commit_sha", "claim_receipt_sha256", "claim_receipt", "claim_capability_sha256", "release_reason_sha256", "holder_proof_hmac_sha256", "terminal_branch_name", "metadata_path", "metadata_sha256", "metadata_json", "plan_sha256"}
    elif schema == TERMINAL_PLAN_SCHEMA and state == "DISPATCHED_OUTCOME_UNKNOWN":
        fields = {"schema", "state", "generation", "key_sha256", "claim_seam_sha256", "claim_commit_sha", "claim_receipt_sha256", "claim_receipt", "claim_capability_sha256", "message_sha256", "channel", "compensation_path_sha256", "compensation_category", "holder_proof_hmac_sha256", "terminal_branch_name", "metadata_path", "metadata_sha256", "metadata_json", "plan_sha256"}
    elif schema == TERMINAL_INTENT_SCHEMA and state in {"RELEASED_UNSENT", "DISPATCHED_OUTCOME_UNKNOWN"}:
        fields = {"schema", "state", "generation", "key_sha256", "claim_seam_sha256", "claim_commit_sha", "claim_receipt_sha256", "claim_receipt", "claim_capability_sha256", "terminal_branch_name", "metadata_path", "metadata_sha256", "plan_sha256", "terminal_commit_sha", "intent_sha256"}
    elif schema == TERMINAL_RECEIPT_SCHEMA and state == "RELEASED_UNSENT":
        fields = {"schema", "state", "generation", "key_sha256", "claim_seam_sha256", "claim_commit_sha", "claim_receipt_sha256", "claim_receipt", "claim_capability_sha256", "release_reason_sha256", "holder_proof_hmac_sha256", "terminal_branch_name", "metadata_path", "metadata_sha256", "metadata_json", "terminal_commit_sha", "plan_sha256", "intent_sha256", "receipt_sha256"}
    elif schema == TERMINAL_RECEIPT_SCHEMA and state == "DISPATCHED_OUTCOME_UNKNOWN":
        fields = {"schema", "state", "generation", "key_sha256", "claim_seam_sha256", "claim_commit_sha", "claim_receipt_sha256", "claim_receipt", "claim_capability_sha256", "message_sha256", "channel", "compensation_path_sha256", "compensation_category", "holder_proof_hmac_sha256", "terminal_branch_name", "metadata_path", "metadata_sha256", "metadata_json", "terminal_commit_sha", "plan_sha256", "intent_sha256", "receipt_sha256"}
    elif schema == REVEAL_PLAN_SCHEMA:
        fields = {"schema", "state", "generation", "key_sha256", "claim_seam_sha256", "claim_commit_sha", "terminal_commit_sha", "terminal_receipt_sha256", "terminal_receipt", "claim_capability_sha256", "retired_capability", "reveal_branch_name", "metadata_path", "metadata_sha256", "metadata_json", "plan_sha256"}
    elif schema == REVEAL_INTENT_SCHEMA:
        fields = {"schema", "state", "generation", "key_sha256", "claim_seam_sha256", "terminal_commit_sha", "terminal_receipt_sha256", "reveal_branch_name", "metadata_path", "metadata_sha256", "plan_sha256", "reveal_commit_sha", "intent_sha256"}
    elif schema == REVEAL_RECEIPT_SCHEMA:
        fields = {"schema", "state", "generation", "key_sha256", "claim_seam_sha256", "claim_commit_sha", "terminal_commit_sha", "terminal_receipt_sha256", "terminal_receipt", "claim_capability_sha256", "retired_capability", "reveal_branch_name", "metadata_path", "metadata_sha256", "metadata_json", "reveal_commit_sha", "plan_sha256", "intent_sha256", "receipt_sha256"}
    elif schema == CONTACTED_PLAN_SCHEMA:
        fields = {"schema", "state", "generation", "key_sha256", "claim_seam_sha256", "claim_commit_sha", "terminal_commit_sha", "terminal_receipt_sha256", "claim_capability_sha256", "provider_receipt_sha256", "contacted_branch_name", "metadata_path", "metadata_sha256", "metadata_json", "plan_sha256"}
    elif schema == CONTACTED_INTENT_SCHEMA:
        fields = {"schema", "state", "generation", "key_sha256", "claim_seam_sha256", "terminal_commit_sha", "terminal_receipt_sha256", "contacted_branch_name", "metadata_path", "metadata_sha256", "plan_sha256", "contacted_commit_sha", "intent_sha256"}
    elif schema == CONTACTED_RECEIPT_SCHEMA:
        fields = {"schema", "state", "generation", "key_sha256", "claim_seam_sha256", "claim_commit_sha", "claim_capability_sha256", "terminal_commit_sha", "terminal_receipt_sha256", "provider_receipt_sha256", "contacted_branch_name", "metadata_path", "metadata_sha256", "metadata_json", "contacted_commit_sha", "plan_sha256", "intent_sha256", "receipt_sha256"}
    else:
        raise CustodyError("unsupported sealed object schema/state")
    fields |= flags
    if seal_field not in fields:
        raise CustodyError("sealed object uses unexpected seal field")
    return fields


def _normalize_domain(raw: str) -> str:
    value = unicodedata.normalize("NFKC", raw.strip()).rstrip(".").casefold()
    if not value or CONTROL_RE.search(value) or any(ch.isspace() for ch in value):
        raise CustodyError("invalid domain")
    try:
        domain = value.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise CustodyError("invalid domain") from exc
    labels = domain.split(".")
    if len(domain) > 253 or len(labels) < 2:
        raise CustodyError("domain must be qualified")
    if any(not x or len(x) > 63 or x[0] == "-" or x[-1] == "-" or not re.fullmatch(r"[a-z0-9-]+", x) for x in labels):
        raise CustodyError("invalid domain labels")
    return domain


def normalize_target(kind: str, raw: str) -> dict[str, str]:
    kind = _token(kind, "kind").casefold()
    if type(raw) is not str:
        raise CustodyError("target must be text")
    value = unicodedata.normalize("NFKC", raw.strip())
    if kind == "email":
        if CONTROL_RE.search(value) or any(ch.isspace() for ch in value) or value.count("@") != 1:
            raise CustodyError("invalid email")
        local, domain = value.rsplit("@", 1)
        local = local.casefold()
        if not local or len(local) > 64:
            raise CustodyError("invalid email local part")
        domain = _normalize_domain(domain)
        canonical = f"{local}@{domain}"
        hint = f"{local[:1]}…@{domain}"
    elif kind == "domain":
        canonical = _normalize_domain(value)
        hint = f"{canonical[:1]}…{canonical[-1:]}"
    elif kind == "phone":
        canonical = re.sub(r"[\s().-]", "", value)
        if not PHONE_RE.fullmatch(canonical):
            raise CustodyError("phone must be E.164")
        hint = canonical[:2] + "…" + canonical[-2:]
    else:
        raise CustodyError("kind must be email, domain, or phone")
    key = hashlib.sha256(b"prospect-contact-custody/v2\0" + kind.encode() + b"\0" + canonical.encode()).hexdigest()
    return {"kind": kind, "key_sha256": key, "target_hint": hint}


def _compensation_category(text: str) -> tuple[str, str]:
    if type(text) is not str:
        raise CustodyError("compensation_path must be text")
    raw = unicodedata.normalize("NFKC", text.strip())
    norm = raw.casefold()
    if not norm or len(norm) > MAX_TEXT or CONTROL_RE.search(norm):
        raise CustodyError("compensation_path invalid")
    if _NEGATIVE_COMP_RE.search(norm):
        raise CustodyError("negative/free compensation language")
    saw_zero = False
    for match in _AMOUNT_RE.finditer(norm):
        value = (match.group("lead") or match.group("trail") or "").replace(",", "")
        try:
            amount = Decimal(value)
        except InvalidOperation:
            continue
        if amount > 0:
            return "priced_service", hashlib.sha256(raw.encode()).hexdigest()
        if amount == 0:
            saw_zero = True
    if saw_zero:
        raise CustodyError("zero-value compensation path")
    tokens = re.findall(r"[a-z0-9]+", norm)
    for phrase in _SIGNAL_PHRASES:
        words = phrase.split()
        if any(tokens[i:i+len(words)] == words for i in range(0, len(tokens)-len(words)+1)):
            if phrase in {"bounty", "prize"}:
                category = "bounty_or_prize"
            elif phrase in {"contract", "subcontract", "bid", "award"}:
                category = "bid_or_contract"
            elif phrase in {"invoice", "fee", "commission", "retainer"}:
                category = "fee_or_invoice"
            else:
                category = "paid_path"
            return category, hashlib.sha256(raw.encode()).hexdigest()
    raise CustodyError("concrete paid/award path required")


def _claim_seam(key_sha256: str, prior_release_reveal_receipt_sha256: str) -> str:
    return _digest({
        "schema": SCHEMA,
        "key_sha256": _sha64(key_sha256, "key_sha256"),
        "prior_release_reveal_receipt_sha256": _sha64(prior_release_reveal_receipt_sha256, "prior_release_reveal_receipt_sha256"),
    })


def claim_branch(key_sha256: str, prior_release_reveal_receipt_sha256: str = ZERO64) -> str:
    return CLAIM_BRANCH_PREFIX + _claim_seam(key_sha256, prior_release_reveal_receipt_sha256)


def terminal_branch(claim_seam_sha256: str) -> str:
    return TERMINAL_BRANCH_PREFIX + _sha64(claim_seam_sha256, "claim_seam_sha256")


def reveal_branch(claim_seam_sha256: str) -> str:
    return REVEAL_BRANCH_PREFIX + _sha64(claim_seam_sha256, "claim_seam_sha256")


def contacted_branch(claim_seam_sha256: str) -> str:
    return CONTACTED_BRANCH_PREFIX + _sha64(claim_seam_sha256, "claim_seam_sha256")


def _metadata_path(claim_seam_sha256: str, kind: str) -> str:
    if kind not in {"claim", "terminal", "reveal", "contacted"}:
        raise CustodyError("metadata kind invalid")
    return f"{METADATA_PREFIX}{_sha64(claim_seam_sha256, 'claim_seam_sha256')}/{kind}.json"


def _seal(doc: dict[str, Any], field: str) -> dict[str, Any]:
    out = dict(doc)
    out[field] = _digest(out)
    return out


def _verify_seal(raw: Mapping[str, Any], field: str) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise CustodyError("object required")
    expected = _expected_sealed_fields(raw, field)
    actual = set(raw)
    if actual != expected:
        raise CustodyError(f"sealed object keys mismatch; missing={sorted(expected-actual)} extra={sorted(actual-expected)}")
    doc = dict(raw)
    seal = _sha64(doc.pop(field, None), field)
    if _digest(doc) != seal:
        raise CustodyError(f"{field} mismatch")
    _check_authority_flags(doc)
    return dict(raw)


def _canonical_json_text(doc: Mapping[str, Any]) -> str:
    return _canon(doc).decode("utf-8") + "\n"


def _verify_live_metadata(expected_text: str, live_text: str) -> None:
    if type(live_text) is not str or live_text != expected_text:
        raise CustodyError("live metadata mismatch")


def _prior_release_context(
    target_key: str,
    prior_release_reveal_receipt: Mapping[str, Any] | None,
    *,
    live_prior_claim_branch_sha: str | None,
    live_prior_claim_parent_sha: str | None,
    live_prior_claim_metadata_json: str | None,
    live_prior_terminal_branch_sha: str | None,
    live_prior_terminal_parent_sha: str | None,
    live_prior_terminal_metadata_json: str | None,
    live_prior_reveal_branch_sha: str | None,
    live_prior_reveal_parent_sha: str | None,
    live_prior_reveal_metadata_json: str | None,
) -> tuple[int, str]:
    live_values = (
        live_prior_claim_branch_sha, live_prior_claim_parent_sha, live_prior_claim_metadata_json,
        live_prior_terminal_branch_sha, live_prior_terminal_parent_sha, live_prior_terminal_metadata_json,
        live_prior_reveal_branch_sha, live_prior_reveal_parent_sha, live_prior_reveal_metadata_json,
    )
    if prior_release_reveal_receipt is None:
        if any(x is not None for x in live_values):
            raise CustodyError("prior release live readback provided without reveal receipt")
        return 1, ZERO64

    reveal = verify_release_reveal_receipt(prior_release_reveal_receipt)
    release = verify_terminal_receipt(reveal["terminal_receipt"])
    if release["state"] != "RELEASED_UNSENT":
        raise CustodyError("only RELEASED_UNSENT may reopen contact")
    if reveal["key_sha256"] != target_key:
        raise CustodyError("prior release contact mismatch")
    if any(x is None for x in live_values):
        raise CustodyError("fresh prior claim + terminal + reveal readback required")

    verify_claim_readback(
        release["claim_receipt"],
        live_branch_sha=live_prior_claim_branch_sha,
        live_parent_sha=live_prior_claim_parent_sha,
        live_metadata_json=live_prior_claim_metadata_json,
    )
    if _sha40(live_prior_terminal_branch_sha, "live prior terminal branch sha") != release["terminal_commit_sha"]:
        raise CustodyError("prior release terminal branch moved")
    if _sha40(live_prior_terminal_parent_sha, "live prior terminal parent sha") != release["claim_commit_sha"]:
        raise CustodyError("prior release terminal parent mismatch")
    _verify_live_metadata(release["metadata_json"], live_prior_terminal_metadata_json)

    if _sha40(live_prior_reveal_branch_sha, "live prior reveal branch sha") != reveal["reveal_commit_sha"]:
        raise CustodyError("prior release reveal branch moved")
    if _sha40(live_prior_reveal_parent_sha, "live prior reveal parent sha") != release["terminal_commit_sha"]:
        raise CustodyError("prior release reveal parent mismatch")
    _verify_live_metadata(reveal["metadata_json"], live_prior_reveal_metadata_json)

    retired = _capability(reveal["retired_capability"])
    if capability_commitment(retired) != reveal["claim_capability_sha256"]:
        raise CustodyError("prior release retired capability mismatch")
    return int(reveal["generation"]) + 1, reveal["receipt_sha256"]


def prepare_claim(
    kind: str,
    raw_target: str,
    *,
    claimant: str,
    operation_id: str,
    anchor_sha: str,
    preflight_sha256: str,
    retain_capability: Callable[[str], None],
    prior_release_reveal_receipt: Mapping[str, Any] | None = None,
    live_prior_claim_branch_sha: str | None = None,
    live_prior_claim_parent_sha: str | None = None,
    live_prior_claim_metadata_json: str | None = None,
    live_prior_terminal_branch_sha: str | None = None,
    live_prior_terminal_parent_sha: str | None = None,
    live_prior_terminal_metadata_json: str | None = None,
    live_prior_reveal_branch_sha: str | None = None,
    live_prior_reveal_parent_sha: str | None = None,
    live_prior_reveal_metadata_json: str | None = None,
) -> dict[str, Any]:
    target = normalize_target(kind, raw_target)
    claimant = _token(claimant, "claimant")
    operation_id = _token(operation_id, "operation_id")
    anchor_sha = _sha40(anchor_sha, "anchor_sha")
    preflight_sha256 = _sha64(preflight_sha256, "preflight_sha256")
    if not callable(retain_capability):
        raise CustodyError("retain_capability callback required")
    generation, prior_digest = _prior_release_context(
        target["key_sha256"], prior_release_reveal_receipt,
        live_prior_claim_branch_sha=live_prior_claim_branch_sha,
        live_prior_claim_parent_sha=live_prior_claim_parent_sha,
        live_prior_claim_metadata_json=live_prior_claim_metadata_json,
        live_prior_terminal_branch_sha=live_prior_terminal_branch_sha,
        live_prior_terminal_parent_sha=live_prior_terminal_parent_sha,
        live_prior_terminal_metadata_json=live_prior_terminal_metadata_json,
        live_prior_reveal_branch_sha=live_prior_reveal_branch_sha,
        live_prior_reveal_parent_sha=live_prior_reveal_parent_sha,
        live_prior_reveal_metadata_json=live_prior_reveal_metadata_json,
    )
    capability = secrets.token_hex(CAPABILITY_BYTES)
    try:
        retain_capability(capability)
    except Exception as exc:
        raise CustodyError("capability retention failed before any authority mutation") from exc
    commitment = capability_commitment(capability)
    seam = _claim_seam(target["key_sha256"], prior_digest)
    metadata = {
        "schema": SCHEMA,
        "record_type": "CLAIM",
        "generation": generation,
        "key_sha256": target["key_sha256"],
        "target_kind": target["kind"],
        "target_hint": target["target_hint"],
        "claim_seam_sha256": seam,
        "prior_release_reveal_receipt_sha256": prior_digest,
        "claimant": claimant,
        "operation_id": operation_id,
        "anchor_sha": anchor_sha,
        "preflight_sha256": preflight_sha256,
        "claim_capability_sha256": commitment,
        **_authority_flags(),
    }
    metadata_json = _canonical_json_text(metadata)
    plan = {
        "schema": CLAIM_PLAN_SCHEMA,
        "generation": generation,
        "key_sha256": target["key_sha256"],
        "target_kind": target["kind"],
        "target_hint": target["target_hint"],
        "claim_seam_sha256": seam,
        "prior_release_reveal_receipt_sha256": prior_digest,
        "claimant": claimant,
        "operation_id": operation_id,
        "anchor_sha": anchor_sha,
        "preflight_sha256": preflight_sha256,
        "claim_capability_sha256": commitment,
        "branch_name": claim_branch(target["key_sha256"], prior_digest),
        "metadata_path": _metadata_path(seam, "claim"),
        "metadata_sha256": _text_digest(metadata_json),
        "metadata_json": metadata_json,
        **_authority_flags(),
    }
    return _seal(plan, "plan_sha256")


def verify_claim_plan(raw: Mapping[str, Any]) -> dict[str, Any]:
    plan = _verify_seal(raw, "plan_sha256")
    if plan.get("schema") != CLAIM_PLAN_SCHEMA:
        raise CustodyError("claim plan schema mismatch")
    seam = _claim_seam(plan["key_sha256"], plan["prior_release_reveal_receipt_sha256"])
    if plan.get("claim_seam_sha256") != seam:
        raise CustodyError("claim seam mismatch")
    if plan.get("branch_name") != CLAIM_BRANCH_PREFIX + seam:
        raise CustodyError("claim branch mismatch")
    if plan.get("metadata_path") != _metadata_path(seam, "claim"):
        raise CustodyError("claim metadata path mismatch")
    expected_metadata = {
        "schema": SCHEMA,
        "record_type": "CLAIM",
        "generation": plan["generation"],
        "key_sha256": plan["key_sha256"],
        "target_kind": plan["target_kind"],
        "target_hint": plan["target_hint"],
        "claim_seam_sha256": seam,
        "prior_release_reveal_receipt_sha256": plan["prior_release_reveal_receipt_sha256"],
        "claimant": plan["claimant"],
        "operation_id": plan["operation_id"],
        "anchor_sha": _sha40(plan["anchor_sha"], "anchor_sha"),
        "preflight_sha256": _sha64(plan["preflight_sha256"], "preflight_sha256"),
        "claim_capability_sha256": _sha64(plan["claim_capability_sha256"], "claim_capability_sha256"),
        **_authority_flags(),
    }
    expected_text = _canonical_json_text(expected_metadata)
    if plan.get("metadata_json") != expected_text or plan.get("metadata_sha256") != _text_digest(expected_text):
        raise CustodyError("claim metadata binding mismatch")
    if type(plan.get("generation")) is not int or plan["generation"] < 1:
        raise CustodyError("claim generation invalid")
    _token(plan["claimant"], "claimant")
    _token(plan["operation_id"], "operation_id")
    return plan


def bind_claim_commit(plan_raw: Mapping[str, Any], claim_commit_sha: str) -> dict[str, Any]:
    plan = verify_claim_plan(plan_raw)
    commit = _sha40(claim_commit_sha, "claim_commit_sha")
    intent = {
        "schema": CLAIM_INTENT_SCHEMA,
        "plan_sha256": plan["plan_sha256"],
        "key_sha256": plan["key_sha256"],
        "claim_seam_sha256": plan["claim_seam_sha256"],
        "generation": plan["generation"],
        "branch_name": plan["branch_name"],
        "metadata_path": plan["metadata_path"],
        "metadata_sha256": plan["metadata_sha256"],
        "claim_capability_sha256": plan["claim_capability_sha256"],
        "claimant": plan["claimant"],
        "operation_id": plan["operation_id"],
        "anchor_sha": plan["anchor_sha"],
        "claim_commit_sha": commit,
        **_authority_flags(),
    }
    return _seal(intent, "intent_sha256")


def verify_claim_intent(raw: Mapping[str, Any]) -> dict[str, Any]:
    intent = _verify_seal(raw, "intent_sha256")
    if intent.get("schema") != CLAIM_INTENT_SCHEMA:
        raise CustodyError("claim intent schema mismatch")
    for field in ("key_sha256", "claim_seam_sha256", "metadata_sha256", "claim_capability_sha256", "plan_sha256"):
        _sha64(intent[field], field)
    _sha40(intent["anchor_sha"], "anchor_sha")
    _sha40(intent["claim_commit_sha"], "claim_commit_sha")
    if intent.get("branch_name") != CLAIM_BRANCH_PREFIX + intent["claim_seam_sha256"]:
        raise CustodyError("claim intent branch mismatch")
    return intent


def claim_receipt_from_readback(
    plan_raw: Mapping[str, Any],
    intent_raw: Mapping[str, Any],
    *,
    live_branch_sha: str,
    live_parent_sha: str,
    live_metadata_json: str,
) -> dict[str, Any]:
    plan = verify_claim_plan(plan_raw)
    intent = verify_claim_intent(intent_raw)
    if intent["plan_sha256"] != plan["plan_sha256"]:
        raise CustodyError("claim plan/intent mismatch")
    if _sha40(live_branch_sha, "live_branch_sha") != intent["claim_commit_sha"]:
        raise CustodyError("claim branch head mismatch")
    if _sha40(live_parent_sha, "live_parent_sha") != plan["anchor_sha"]:
        raise CustodyError("claim commit parent mismatch")
    _verify_live_metadata(plan["metadata_json"], live_metadata_json)
    receipt = {
        "schema": CLAIM_RECEIPT_SCHEMA,
        "state": "CLAIM_HELD",
        "generation": plan["generation"],
        "key_sha256": plan["key_sha256"],
        "target_kind": plan["target_kind"],
        "target_hint": plan["target_hint"],
        "claim_seam_sha256": plan["claim_seam_sha256"],
        "prior_release_reveal_receipt_sha256": plan["prior_release_reveal_receipt_sha256"],
        "claimant": plan["claimant"],
        "operation_id": plan["operation_id"],
        "anchor_sha": plan["anchor_sha"],
        "preflight_sha256": plan["preflight_sha256"],
        "claim_capability_sha256": plan["claim_capability_sha256"],
        "branch_name": plan["branch_name"],
        "metadata_path": plan["metadata_path"],
        "metadata_sha256": plan["metadata_sha256"],
        "metadata_json": plan["metadata_json"],
        "claim_commit_sha": intent["claim_commit_sha"],
        "plan_sha256": plan["plan_sha256"],
        "intent_sha256": intent["intent_sha256"],
        **_authority_flags(),
    }
    return _seal(receipt, "receipt_sha256")


def verify_claim_receipt(raw: Mapping[str, Any]) -> dict[str, Any]:
    receipt = _verify_seal(raw, "receipt_sha256")
    if receipt.get("schema") != CLAIM_RECEIPT_SCHEMA or receipt.get("state") != "CLAIM_HELD":
        raise CustodyError("claim receipt schema/state mismatch")
    seam = _claim_seam(receipt["key_sha256"], receipt["prior_release_reveal_receipt_sha256"])
    if receipt.get("claim_seam_sha256") != seam or receipt.get("branch_name") != CLAIM_BRANCH_PREFIX + seam:
        raise CustodyError("claim receipt seam mismatch")
    _sha40(receipt["claim_commit_sha"], "claim_commit_sha")
    _sha40(receipt["anchor_sha"], "anchor_sha")
    for field in ("claim_capability_sha256","metadata_sha256","plan_sha256","intent_sha256","preflight_sha256"):
        _sha64(receipt[field], field)
    if receipt.get("metadata_path") != _metadata_path(seam, "claim"):
        raise CustodyError("claim receipt metadata path mismatch")
    expected_metadata = {
        "schema": SCHEMA,
        "record_type": "CLAIM",
        "generation": receipt["generation"],
        "key_sha256": receipt["key_sha256"],
        "target_kind": receipt["target_kind"],
        "target_hint": receipt["target_hint"],
        "claim_seam_sha256": seam,
        "prior_release_reveal_receipt_sha256": receipt["prior_release_reveal_receipt_sha256"],
        "claimant": receipt["claimant"],
        "operation_id": receipt["operation_id"],
        "anchor_sha": receipt["anchor_sha"],
        "preflight_sha256": receipt["preflight_sha256"],
        "claim_capability_sha256": receipt["claim_capability_sha256"],
        **_authority_flags(),
    }
    expected_text = _canonical_json_text(expected_metadata)
    if receipt.get("metadata_json") != expected_text or receipt.get("metadata_sha256") != _text_digest(expected_text):
        raise CustodyError("claim receipt metadata binding mismatch")
    return receipt


def verify_claim_readback(
    receipt_raw: Mapping[str, Any],
    *,
    live_branch_sha: str,
    live_parent_sha: str,
    live_metadata_json: str,
) -> bool:
    receipt = verify_claim_receipt(receipt_raw)
    if _sha40(live_branch_sha, "live_branch_sha") != receipt["claim_commit_sha"]:
        raise CustodyError("live claim branch moved")
    if _sha40(live_parent_sha, "live_parent_sha") != receipt["anchor_sha"]:
        raise CustodyError("live claim parent mismatch")
    _verify_live_metadata(receipt["metadata_json"], live_metadata_json)
    return True


def verify_claim_possession(
    receipt_raw: Mapping[str, Any],
    *,
    capability: str,
    live_branch_sha: str,
    live_parent_sha: str,
    live_metadata_json: str,
) -> bool:
    receipt = verify_claim_receipt(receipt_raw)
    verify_claim_readback(
        receipt,
        live_branch_sha=live_branch_sha,
        live_parent_sha=live_parent_sha,
        live_metadata_json=live_metadata_json,
    )
    cap = _capability(capability)
    if capability_commitment(cap) != receipt["claim_capability_sha256"]:
        raise CustodyError("private capability does not match claim commitment")
    return True


def _terminal_material_base(claim: Mapping[str, Any], state: str) -> dict[str, Any]:
    if state not in {"RELEASED_UNSENT", "DISPATCHED_OUTCOME_UNKNOWN"}:
        raise CustodyError("terminal state invalid")
    return {
        "schema": SCHEMA,
        "record_type": "TERMINAL",
        "state": state,
        "generation": claim["generation"],
        "key_sha256": claim["key_sha256"],
        "claim_seam_sha256": claim["claim_seam_sha256"],
        "claim_commit_sha": claim["claim_commit_sha"],
        "claim_receipt_sha256": claim["receipt_sha256"],
        "claim_capability_sha256": claim["claim_capability_sha256"],
        "claimant": claim["claimant"],
        "operation_id": claim["operation_id"],
        **_authority_flags(),
    }


def _holder_proof(capability: str, material: Mapping[str, Any]) -> str:
    return hmac.new(bytes.fromhex(_capability(capability)), _canon(material), hashlib.sha256).hexdigest()


def prepare_release_terminal(
    claim_receipt_raw: Mapping[str, Any],
    *,
    capability: str,
    live_claim_branch_sha: str,
    live_claim_parent_sha: str,
    live_claim_metadata_json: str,
    reason: str,
) -> dict[str, Any]:
    claim = verify_claim_receipt(claim_receipt_raw)
    cap = _capability(capability)
    verify_claim_possession(
        claim,
        capability=cap,
        live_branch_sha=live_claim_branch_sha,
        live_parent_sha=live_claim_parent_sha,
        live_metadata_json=live_claim_metadata_json,
    )
    if type(reason) is not str:
        raise CustodyError("release reason must be text")
    reason = unicodedata.normalize("NFKC", reason.strip())
    if not reason or len(reason) > MAX_TEXT or CONTROL_RE.search(reason):
        raise CustodyError("release reason invalid")
    reason_sha = hashlib.sha256(reason.encode()).hexdigest()
    proof_material = {
        "state": "RELEASED_UNSENT",
        "claim_receipt_sha256": claim["receipt_sha256"],
        "release_reason_sha256": reason_sha,
    }
    proof = _holder_proof(cap, proof_material)
    metadata = _terminal_material_base(claim, "RELEASED_UNSENT")
    metadata.update({
        "release_reason_sha256": reason_sha,
        "holder_proof_hmac_sha256": proof,
    })
    metadata_json = _canonical_json_text(metadata)
    plan = {
        "schema": TERMINAL_PLAN_SCHEMA,
        "state": "RELEASED_UNSENT",
        "generation": claim["generation"],
        "key_sha256": claim["key_sha256"],
        "claim_seam_sha256": claim["claim_seam_sha256"],
        "claim_commit_sha": claim["claim_commit_sha"],
        "claim_receipt_sha256": claim["receipt_sha256"],
        "claim_receipt": claim,
        "claim_capability_sha256": claim["claim_capability_sha256"],
        "terminal_branch_name": terminal_branch(claim["claim_seam_sha256"]),
        "metadata_path": _metadata_path(claim["claim_seam_sha256"], "terminal"),
        "metadata_sha256": _text_digest(metadata_json),
        "metadata_json": metadata_json,
        "release_reason_sha256": reason_sha,
        "holder_proof_hmac_sha256": proof,
        **_authority_flags(),
    }
    return _seal(plan, "plan_sha256")


def _dispatch_proof(capability: str, material: Mapping[str, Any]) -> str:
    return _holder_proof(capability, material)


def prepare_dispatch_terminal(
    claim_receipt_raw: Mapping[str, Any],
    *,
    capability: str,
    live_claim_branch_sha: str,
    live_claim_parent_sha: str,
    live_claim_metadata_json: str,
    message_sha256: str,
    channel: str,
    compensation_path: str,
) -> dict[str, Any]:
    claim = verify_claim_receipt(claim_receipt_raw)
    cap = _capability(capability)
    verify_claim_possession(
        claim,
        capability=cap,
        live_branch_sha=live_claim_branch_sha,
        live_parent_sha=live_claim_parent_sha,
        live_metadata_json=live_claim_metadata_json,
    )
    message_sha256 = _sha64(message_sha256, "message_sha256")
    channel = _token(channel, "channel").casefold()
    category, compensation_sha = _compensation_category(compensation_path)
    proof_material = {
        "state": "DISPATCHED_OUTCOME_UNKNOWN",
        "claim_receipt_sha256": claim["receipt_sha256"],
        "message_sha256": message_sha256,
        "channel": channel,
        "compensation_path_sha256": compensation_sha,
        "compensation_category": category,
    }
    proof = _dispatch_proof(cap, proof_material)
    metadata = _terminal_material_base(claim, "DISPATCHED_OUTCOME_UNKNOWN")
    metadata.update({**proof_material,
        "holder_proof_hmac_sha256": proof,
    })
    # state/claim fields duplicated by proof_material are identical; canonical map remains unambiguous.
    metadata_json = _canonical_json_text(metadata)
    plan = {
        "schema": TERMINAL_PLAN_SCHEMA,
        "state": "DISPATCHED_OUTCOME_UNKNOWN",
        "generation": claim["generation"],
        "key_sha256": claim["key_sha256"],
        "claim_seam_sha256": claim["claim_seam_sha256"],
        "claim_commit_sha": claim["claim_commit_sha"],
        "claim_receipt_sha256": claim["receipt_sha256"],
        "claim_receipt": claim,
        "claim_capability_sha256": claim["claim_capability_sha256"],
        "terminal_branch_name": terminal_branch(claim["claim_seam_sha256"]),
        "metadata_path": _metadata_path(claim["claim_seam_sha256"], "terminal"),
        "metadata_sha256": _text_digest(metadata_json),
        "metadata_json": metadata_json,
        "message_sha256": message_sha256,
        "channel": channel,
        "compensation_path_sha256": compensation_sha,
        "compensation_category": category,
        "holder_proof_hmac_sha256": proof,
        **_authority_flags(),
    }
    return _seal(plan, "plan_sha256")


def verify_terminal_plan(raw: Mapping[str, Any]) -> dict[str, Any]:
    plan = _verify_seal(raw, "plan_sha256")
    if plan.get("schema") != TERMINAL_PLAN_SCHEMA:
        raise CustodyError("terminal plan schema mismatch")
    state = plan.get("state")
    if state not in {"RELEASED_UNSENT", "DISPATCHED_OUTCOME_UNKNOWN"}:
        raise CustodyError("terminal plan state invalid")
    seam = _sha64(plan["claim_seam_sha256"], "claim_seam_sha256")
    if plan.get("terminal_branch_name") != terminal_branch(seam):
        raise CustodyError("terminal branch mismatch")
    if plan.get("metadata_path") != _metadata_path(seam, "terminal"):
        raise CustodyError("terminal metadata path mismatch")
    if plan.get("metadata_sha256") != _text_digest(plan["metadata_json"]):
        raise CustodyError("terminal metadata digest mismatch")
    _sha40(plan["claim_commit_sha"], "claim_commit_sha")
    for field in ("key_sha256","claim_receipt_sha256","claim_capability_sha256"):
        _sha64(plan[field], field)
    claim = verify_claim_receipt(plan.get("claim_receipt"))
    if claim["receipt_sha256"] != plan["claim_receipt_sha256"] or claim["claim_commit_sha"] != plan["claim_commit_sha"] or claim["claim_seam_sha256"] != plan["claim_seam_sha256"] or claim["claim_capability_sha256"] != plan["claim_capability_sha256"]:
        raise CustodyError("terminal plan claim receipt mismatch")
    expected_metadata = _terminal_material_base(claim, state)
    if state == "RELEASED_UNSENT":
        reason_sha = _sha64(plan.get("release_reason_sha256"), "release_reason_sha256")
        proof = _sha64(plan.get("holder_proof_hmac_sha256"), "holder_proof_hmac_sha256")
        expected_metadata.update({"release_reason_sha256": reason_sha, "holder_proof_hmac_sha256": proof})
        if "retired_capability" in plan or "retired_capability" in plan.get("metadata_json", ""):
            raise CustodyError("release terminal must not disclose active capability")
    else:
        message_sha = _sha64(plan.get("message_sha256"), "message_sha256")
        compensation_sha = _sha64(plan.get("compensation_path_sha256"), "compensation_path_sha256")
        proof = _sha64(plan.get("holder_proof_hmac_sha256"), "holder_proof_hmac_sha256")
        channel = _token(plan.get("channel"), "channel").casefold()
        category = plan.get("compensation_category")
        if category not in {"priced_service","bounty_or_prize","bid_or_contract","fee_or_invoice","paid_path"}:
            raise CustodyError("compensation category invalid")
        proof_material = {
            "state": "DISPATCHED_OUTCOME_UNKNOWN",
            "claim_receipt_sha256": claim["receipt_sha256"],
            "message_sha256": message_sha,
            "channel": channel,
            "compensation_path_sha256": compensation_sha,
            "compensation_category": category,
        }
        expected_metadata.update({**proof_material, "holder_proof_hmac_sha256": proof})
        if "retired_capability" in plan:
            raise CustodyError("dispatch must not disclose capability")
    expected_text = _canonical_json_text(expected_metadata)
    if plan.get("metadata_json") != expected_text or plan.get("metadata_sha256") != _text_digest(expected_text):
        raise CustodyError("terminal metadata binding mismatch")
    return plan


def bind_terminal_commit(plan_raw: Mapping[str, Any], terminal_commit_sha: str) -> dict[str, Any]:
    plan = verify_terminal_plan(plan_raw)
    commit = _sha40(terminal_commit_sha, "terminal_commit_sha")
    intent = {
        "schema": TERMINAL_INTENT_SCHEMA,
        "state": plan["state"],
        "generation": plan["generation"],
        "key_sha256": plan["key_sha256"],
        "claim_seam_sha256": plan["claim_seam_sha256"],
        "claim_commit_sha": plan["claim_commit_sha"],
        "claim_receipt_sha256": plan["claim_receipt_sha256"],
        "claim_receipt": plan["claim_receipt"],
        "claim_capability_sha256": plan["claim_capability_sha256"],
        "terminal_branch_name": plan["terminal_branch_name"],
        "metadata_path": plan["metadata_path"],
        "metadata_sha256": plan["metadata_sha256"],
        "plan_sha256": plan["plan_sha256"],
        "terminal_commit_sha": commit,
        **_authority_flags(),
    }
    return _seal(intent, "intent_sha256")


def verify_terminal_intent(raw: Mapping[str, Any]) -> dict[str, Any]:
    intent = _verify_seal(raw, "intent_sha256")
    if intent.get("schema") != TERMINAL_INTENT_SCHEMA:
        raise CustodyError("terminal intent schema mismatch")
    if intent.get("state") not in {"RELEASED_UNSENT","DISPATCHED_OUTCOME_UNKNOWN"}:
        raise CustodyError("terminal intent state invalid")
    if intent.get("terminal_branch_name") != terminal_branch(intent["claim_seam_sha256"]):
        raise CustodyError("terminal intent branch mismatch")
    _sha40(intent["claim_commit_sha"], "claim_commit_sha")
    _sha40(intent["terminal_commit_sha"], "terminal_commit_sha")
    return intent


def terminal_receipt_from_readback(
    plan_raw: Mapping[str, Any],
    intent_raw: Mapping[str, Any],
    *,
    live_branch_sha: str,
    live_parent_sha: str,
    live_metadata_json: str,
) -> dict[str, Any]:
    plan = verify_terminal_plan(plan_raw)
    intent = verify_terminal_intent(intent_raw)
    if intent["plan_sha256"] != plan["plan_sha256"] or intent["state"] != plan["state"]:
        raise CustodyError("terminal plan/intent mismatch")
    if _sha40(live_branch_sha, "live_branch_sha") != intent["terminal_commit_sha"]:
        raise CustodyError("terminal branch head mismatch")
    if _sha40(live_parent_sha, "live_parent_sha") != plan["claim_commit_sha"]:
        raise CustodyError("terminal parent must be exact claim commit")
    _verify_live_metadata(plan["metadata_json"], live_metadata_json)
    receipt = {
        "schema": TERMINAL_RECEIPT_SCHEMA,
        "state": plan["state"],
        "generation": plan["generation"],
        "key_sha256": plan["key_sha256"],
        "claim_seam_sha256": plan["claim_seam_sha256"],
        "claim_commit_sha": plan["claim_commit_sha"],
        "claim_receipt_sha256": plan["claim_receipt_sha256"],
        "claim_receipt": plan["claim_receipt"],
        "claim_capability_sha256": plan["claim_capability_sha256"],
        "terminal_branch_name": plan["terminal_branch_name"],
        "metadata_path": plan["metadata_path"],
        "metadata_sha256": plan["metadata_sha256"],
        "metadata_json": plan["metadata_json"],
        "terminal_commit_sha": intent["terminal_commit_sha"],
        "plan_sha256": plan["plan_sha256"],
        "intent_sha256": intent["intent_sha256"],
        **_authority_flags(),
    }
    if plan["state"] == "RELEASED_UNSENT":
        receipt["release_reason_sha256"] = plan["release_reason_sha256"]
        receipt["holder_proof_hmac_sha256"] = plan["holder_proof_hmac_sha256"]
    else:
        for field in ("message_sha256","channel","compensation_path_sha256","compensation_category","holder_proof_hmac_sha256"):
            receipt[field] = plan[field]
    return _seal(receipt, "receipt_sha256")


def verify_terminal_receipt(raw: Mapping[str, Any]) -> dict[str, Any]:
    receipt = _verify_seal(raw, "receipt_sha256")
    if receipt.get("schema") != TERMINAL_RECEIPT_SCHEMA:
        raise CustodyError("terminal receipt schema mismatch")
    state = receipt.get("state")
    if state not in {"RELEASED_UNSENT","DISPATCHED_OUTCOME_UNKNOWN"}:
        raise CustodyError("terminal receipt state invalid")
    if receipt.get("terminal_branch_name") != terminal_branch(receipt["claim_seam_sha256"]):
        raise CustodyError("terminal receipt branch mismatch")
    if receipt.get("metadata_path") != _metadata_path(receipt["claim_seam_sha256"], "terminal"):
        raise CustodyError("terminal receipt metadata path mismatch")
    if receipt.get("metadata_sha256") != _text_digest(receipt["metadata_json"]):
        raise CustodyError("terminal receipt metadata digest mismatch")
    _sha40(receipt["claim_commit_sha"], "claim_commit_sha")
    _sha40(receipt["terminal_commit_sha"], "terminal_commit_sha")
    claim = verify_claim_receipt(receipt.get("claim_receipt"))
    if claim["receipt_sha256"] != receipt["claim_receipt_sha256"] or claim["claim_commit_sha"] != receipt["claim_commit_sha"] or claim["claim_seam_sha256"] != receipt["claim_seam_sha256"] or claim["claim_capability_sha256"] != receipt["claim_capability_sha256"]:
        raise CustodyError("terminal receipt claim binding mismatch")
    expected_metadata = _terminal_material_base(claim, state)
    if state == "RELEASED_UNSENT":
        reason_sha = _sha64(receipt.get("release_reason_sha256"), "release_reason_sha256")
        proof = _sha64(receipt.get("holder_proof_hmac_sha256"), "holder_proof_hmac_sha256")
        expected_metadata.update({"release_reason_sha256": reason_sha, "holder_proof_hmac_sha256": proof})
        if "retired_capability" in receipt or "retired_capability" in receipt.get("metadata_json", ""):
            raise CustodyError("release terminal receipt must not disclose capability")
    else:
        message_sha = _sha64(receipt["message_sha256"], "message_sha256")
        compensation_sha = _sha64(receipt["compensation_path_sha256"], "compensation_path_sha256")
        proof = _sha64(receipt["holder_proof_hmac_sha256"], "holder_proof_hmac_sha256")
        channel = _token(receipt["channel"], "channel").casefold()
        category = receipt["compensation_category"]
        if category not in {"priced_service","bounty_or_prize","bid_or_contract","fee_or_invoice","paid_path"}:
            raise CustodyError("compensation category invalid")
        proof_material = {
            "state": "DISPATCHED_OUTCOME_UNKNOWN",
            "claim_receipt_sha256": claim["receipt_sha256"],
            "message_sha256": message_sha,
            "channel": channel,
            "compensation_path_sha256": compensation_sha,
            "compensation_category": category,
        }
        expected_metadata.update({**proof_material, "holder_proof_hmac_sha256": proof})
    expected_text = _canonical_json_text(expected_metadata)
    if receipt.get("metadata_json") != expected_text or receipt.get("metadata_sha256") != _text_digest(expected_text):
        raise CustodyError("terminal receipt metadata binding mismatch")
    return receipt



def _verify_release_holder_proof(release_receipt: Mapping[str, Any], capability: str) -> None:
    receipt = verify_terminal_receipt(release_receipt)
    if receipt["state"] != "RELEASED_UNSENT":
        raise CustodyError("release terminal receipt required")
    cap = _capability(capability)
    if capability_commitment(cap) != receipt["claim_capability_sha256"]:
        raise CustodyError("release capability mismatch")
    material = {
        "state": "RELEASED_UNSENT",
        "claim_receipt_sha256": receipt["claim_receipt_sha256"],
        "release_reason_sha256": receipt["release_reason_sha256"],
    }
    expected = _holder_proof(cap, material)
    if not hmac.compare_digest(expected, receipt["holder_proof_hmac_sha256"]):
        raise CustodyError("release holder proof mismatch")


def prepare_release_reveal(
    release_receipt_raw: Mapping[str, Any],
    *, capability: str,
    live_claim_branch_sha: str,
    live_claim_parent_sha: str,
    live_claim_metadata_json: str,
    live_terminal_branch_sha: str,
    live_terminal_parent_sha: str,
    live_terminal_metadata_json: str,
) -> dict[str, Any]:
    release = verify_terminal_receipt(release_receipt_raw)
    if release["state"] != "RELEASED_UNSENT":
        raise CustodyError("release terminal receipt required")
    verify_claim_readback(
        release["claim_receipt"],
        live_branch_sha=live_claim_branch_sha,
        live_parent_sha=live_claim_parent_sha,
        live_metadata_json=live_claim_metadata_json,
    )
    if _sha40(live_terminal_branch_sha, "live_terminal_branch_sha") != release["terminal_commit_sha"]:
        raise CustodyError("live release terminal branch moved")
    if _sha40(live_terminal_parent_sha, "live_terminal_parent_sha") != release["claim_commit_sha"]:
        raise CustodyError("live release terminal parent mismatch")
    _verify_live_metadata(release["metadata_json"], live_terminal_metadata_json)
    cap = _capability(capability)
    _verify_release_holder_proof(release, cap)
    metadata = {
        "schema": SCHEMA,
        "record_type": "RELEASE_CAPABILITY_REVEAL",
        "state": "RELEASED_UNSENT",
        "generation": release["generation"],
        "key_sha256": release["key_sha256"],
        "claim_seam_sha256": release["claim_seam_sha256"],
        "claim_commit_sha": release["claim_commit_sha"],
        "terminal_commit_sha": release["terminal_commit_sha"],
        "terminal_receipt_sha256": release["receipt_sha256"],
        "claim_capability_sha256": release["claim_capability_sha256"],
        # Safe to disclose only now: RELEASED_UNSENT is already the live terminal state.
        "retired_capability": cap,
        **_authority_flags(),
    }
    metadata_json = _canonical_json_text(metadata)
    plan = {
        "schema": REVEAL_PLAN_SCHEMA,
        "state": "RELEASED_UNSENT",
        "generation": release["generation"],
        "key_sha256": release["key_sha256"],
        "claim_seam_sha256": release["claim_seam_sha256"],
        "claim_commit_sha": release["claim_commit_sha"],
        "terminal_commit_sha": release["terminal_commit_sha"],
        "terminal_receipt_sha256": release["receipt_sha256"],
        "terminal_receipt": release,
        "claim_capability_sha256": release["claim_capability_sha256"],
        "retired_capability": cap,
        "reveal_branch_name": reveal_branch(release["claim_seam_sha256"]),
        "metadata_path": _metadata_path(release["claim_seam_sha256"], "reveal"),
        "metadata_sha256": _text_digest(metadata_json),
        "metadata_json": metadata_json,
        **_authority_flags(),
    }
    return _seal(plan, "plan_sha256")


def verify_release_reveal_plan(raw: Mapping[str, Any]) -> dict[str, Any]:
    plan = _verify_seal(raw, "plan_sha256")
    if plan.get("schema") != REVEAL_PLAN_SCHEMA or plan.get("state") != "RELEASED_UNSENT":
        raise CustodyError("release reveal plan schema/state mismatch")
    release = verify_terminal_receipt(plan.get("terminal_receipt"))
    if release["state"] != "RELEASED_UNSENT":
        raise CustodyError("release reveal must bind released terminal")
    if release["receipt_sha256"] != plan.get("terminal_receipt_sha256") or release["terminal_commit_sha"] != plan.get("terminal_commit_sha"):
        raise CustodyError("release reveal terminal binding mismatch")
    if release["claim_seam_sha256"] != plan.get("claim_seam_sha256") or release["claim_capability_sha256"] != plan.get("claim_capability_sha256"):
        raise CustodyError("release reveal claim binding mismatch")
    cap = _capability(plan.get("retired_capability"))
    _verify_release_holder_proof(release, cap)
    if plan.get("reveal_branch_name") != reveal_branch(plan["claim_seam_sha256"]):
        raise CustodyError("release reveal branch mismatch")
    if plan.get("metadata_path") != _metadata_path(plan["claim_seam_sha256"], "reveal"):
        raise CustodyError("release reveal metadata path mismatch")
    expected_metadata = {
        "schema": SCHEMA,
        "record_type": "RELEASE_CAPABILITY_REVEAL",
        "state": "RELEASED_UNSENT",
        "generation": release["generation"],
        "key_sha256": release["key_sha256"],
        "claim_seam_sha256": release["claim_seam_sha256"],
        "claim_commit_sha": release["claim_commit_sha"],
        "terminal_commit_sha": release["terminal_commit_sha"],
        "terminal_receipt_sha256": release["receipt_sha256"],
        "claim_capability_sha256": release["claim_capability_sha256"],
        "retired_capability": cap,
        **_authority_flags(),
    }
    expected_text = _canonical_json_text(expected_metadata)
    if plan.get("metadata_json") != expected_text or plan.get("metadata_sha256") != _text_digest(expected_text):
        raise CustodyError("release reveal metadata binding mismatch")
    return plan


def bind_release_reveal_commit(plan_raw: Mapping[str, Any], reveal_commit_sha: str) -> dict[str, Any]:
    plan = verify_release_reveal_plan(plan_raw)
    intent = {
        "schema": REVEAL_INTENT_SCHEMA,
        "state": "RELEASED_UNSENT",
        "generation": plan["generation"],
        "key_sha256": plan["key_sha256"],
        "claim_seam_sha256": plan["claim_seam_sha256"],
        "terminal_commit_sha": plan["terminal_commit_sha"],
        "terminal_receipt_sha256": plan["terminal_receipt_sha256"],
        "reveal_branch_name": plan["reveal_branch_name"],
        "metadata_path": plan["metadata_path"],
        "metadata_sha256": plan["metadata_sha256"],
        "plan_sha256": plan["plan_sha256"],
        "reveal_commit_sha": _sha40(reveal_commit_sha, "reveal_commit_sha"),
        **_authority_flags(),
    }
    return _seal(intent, "intent_sha256")


def verify_release_reveal_intent(raw: Mapping[str, Any]) -> dict[str, Any]:
    intent = _verify_seal(raw, "intent_sha256")
    if intent.get("schema") != REVEAL_INTENT_SCHEMA or intent.get("state") != "RELEASED_UNSENT":
        raise CustodyError("release reveal intent schema/state mismatch")
    if intent.get("reveal_branch_name") != reveal_branch(intent["claim_seam_sha256"]):
        raise CustodyError("release reveal intent branch mismatch")
    _sha40(intent["terminal_commit_sha"], "terminal_commit_sha")
    _sha40(intent["reveal_commit_sha"], "reveal_commit_sha")
    return intent


def release_reveal_receipt_from_readback(
    plan_raw: Mapping[str, Any], intent_raw: Mapping[str, Any], *,
    live_branch_sha: str, live_parent_sha: str, live_metadata_json: str,
) -> dict[str, Any]:
    plan = verify_release_reveal_plan(plan_raw)
    intent = verify_release_reveal_intent(intent_raw)
    if intent["plan_sha256"] != plan["plan_sha256"]:
        raise CustodyError("release reveal plan/intent mismatch")
    if _sha40(live_branch_sha, "live_branch_sha") != intent["reveal_commit_sha"]:
        raise CustodyError("release reveal branch head mismatch")
    if _sha40(live_parent_sha, "live_parent_sha") != plan["terminal_commit_sha"]:
        raise CustodyError("release reveal parent mismatch")
    _verify_live_metadata(plan["metadata_json"], live_metadata_json)
    receipt = {
        "schema": REVEAL_RECEIPT_SCHEMA,
        "state": "RELEASED_UNSENT",
        "generation": plan["generation"],
        "key_sha256": plan["key_sha256"],
        "claim_seam_sha256": plan["claim_seam_sha256"],
        "claim_commit_sha": plan["claim_commit_sha"],
        "terminal_commit_sha": plan["terminal_commit_sha"],
        "terminal_receipt_sha256": plan["terminal_receipt_sha256"],
        "terminal_receipt": plan["terminal_receipt"],
        "claim_capability_sha256": plan["claim_capability_sha256"],
        "retired_capability": plan["retired_capability"],
        "reveal_branch_name": plan["reveal_branch_name"],
        "metadata_path": plan["metadata_path"],
        "metadata_sha256": plan["metadata_sha256"],
        "metadata_json": plan["metadata_json"],
        "reveal_commit_sha": intent["reveal_commit_sha"],
        "plan_sha256": plan["plan_sha256"],
        "intent_sha256": intent["intent_sha256"],
        **_authority_flags(),
    }
    return _seal(receipt, "receipt_sha256")


def verify_release_reveal_receipt(raw: Mapping[str, Any]) -> dict[str, Any]:
    receipt = _verify_seal(raw, "receipt_sha256")
    if receipt.get("schema") != REVEAL_RECEIPT_SCHEMA or receipt.get("state") != "RELEASED_UNSENT":
        raise CustodyError("release reveal receipt schema/state mismatch")
    release = verify_terminal_receipt(receipt.get("terminal_receipt"))
    if release["state"] != "RELEASED_UNSENT" or release["receipt_sha256"] != receipt.get("terminal_receipt_sha256"):
        raise CustodyError("release reveal receipt terminal mismatch")
    cap = _capability(receipt.get("retired_capability"))
    _verify_release_holder_proof(release, cap)
    if receipt.get("claim_capability_sha256") != release["claim_capability_sha256"] or receipt.get("claim_seam_sha256") != release["claim_seam_sha256"]:
        raise CustodyError("release reveal receipt claim mismatch")
    if receipt.get("reveal_branch_name") != reveal_branch(receipt["claim_seam_sha256"]):
        raise CustodyError("release reveal receipt branch mismatch")
    _sha40(receipt["reveal_commit_sha"], "reveal_commit_sha")
    if receipt.get("metadata_path") != _metadata_path(receipt["claim_seam_sha256"], "reveal"):
        raise CustodyError("release reveal receipt metadata path mismatch")
    expected_metadata = {
        "schema": SCHEMA,
        "record_type": "RELEASE_CAPABILITY_REVEAL",
        "state": "RELEASED_UNSENT",
        "generation": release["generation"],
        "key_sha256": release["key_sha256"],
        "claim_seam_sha256": release["claim_seam_sha256"],
        "claim_commit_sha": release["claim_commit_sha"],
        "terminal_commit_sha": release["terminal_commit_sha"],
        "terminal_receipt_sha256": release["receipt_sha256"],
        "claim_capability_sha256": release["claim_capability_sha256"],
        "retired_capability": cap,
        **_authority_flags(),
    }
    expected_text = _canonical_json_text(expected_metadata)
    if receipt.get("metadata_json") != expected_text or receipt.get("metadata_sha256") != _text_digest(expected_text):
        raise CustodyError("release reveal receipt metadata binding mismatch")
    return receipt

def verify_dispatch_possession(
    terminal_receipt_raw: Mapping[str, Any], *, capability: str,
    live_claim_branch_sha: str, live_claim_parent_sha: str,
    live_claim_metadata_json: str,
    live_terminal_branch_sha: str, live_terminal_parent_sha: str,
    live_terminal_metadata_json: str,
) -> bool:
    receipt = verify_terminal_receipt(terminal_receipt_raw)
    if receipt["state"] != "DISPATCHED_OUTCOME_UNKNOWN":
        raise CustodyError("dispatch receipt required")
    verify_claim_readback(
        receipt["claim_receipt"],
        live_branch_sha=live_claim_branch_sha,
        live_parent_sha=live_claim_parent_sha,
        live_metadata_json=live_claim_metadata_json,
    )
    cap = _capability(capability)
    if capability_commitment(cap) != receipt["claim_capability_sha256"]:
        raise CustodyError("dispatch capability mismatch")
    if _sha40(live_terminal_branch_sha, "live_terminal_branch_sha") != receipt["terminal_commit_sha"]:
        raise CustodyError("live terminal branch moved")
    if _sha40(live_terminal_parent_sha, "live_terminal_parent_sha") != receipt["claim_commit_sha"]:
        raise CustodyError("live terminal parent mismatch")
    _verify_live_metadata(receipt["metadata_json"], live_terminal_metadata_json)
    material = {
        "state": "DISPATCHED_OUTCOME_UNKNOWN",
        "claim_receipt_sha256": receipt["claim_receipt_sha256"],
        "message_sha256": receipt["message_sha256"],
        "channel": receipt["channel"],
        "compensation_path_sha256": receipt["compensation_path_sha256"],
        "compensation_category": receipt["compensation_category"],
    }
    if not hmac.compare_digest(_dispatch_proof(cap, material), receipt["holder_proof_hmac_sha256"]):
        raise CustodyError("dispatch holder proof mismatch")
    return True


def prepare_contacted(
    dispatch_receipt_raw: Mapping[str, Any],
    *, capability: str,
    live_claim_branch_sha: str,
    live_claim_parent_sha: str,
    live_claim_metadata_json: str,
    live_terminal_branch_sha: str,
    live_terminal_parent_sha: str,
    live_terminal_metadata_json: str,
    provider_receipt: str,
) -> dict[str, Any]:
    dispatch = verify_terminal_receipt(dispatch_receipt_raw)
    verify_dispatch_possession(
        dispatch,
        capability=capability,
        live_claim_branch_sha=live_claim_branch_sha,
        live_claim_parent_sha=live_claim_parent_sha,
        live_claim_metadata_json=live_claim_metadata_json,
        live_terminal_branch_sha=live_terminal_branch_sha,
        live_terminal_parent_sha=live_terminal_parent_sha,
        live_terminal_metadata_json=live_terminal_metadata_json,
    )
    if type(provider_receipt) is not str:
        raise CustodyError("provider_receipt must be text")
    provider_receipt = unicodedata.normalize("NFKC", provider_receipt.strip())
    if not provider_receipt or len(provider_receipt) > 1000 or CONTROL_RE.search(provider_receipt):
        raise CustodyError("provider_receipt invalid")
    provider_digest = hashlib.sha256(provider_receipt.encode()).hexdigest()
    metadata = {
        "schema": SCHEMA,
        "record_type": "CONTACTED",
        "state": "CONTACTED",
        "generation": dispatch["generation"],
        "key_sha256": dispatch["key_sha256"],
        "claim_seam_sha256": dispatch["claim_seam_sha256"],
        "claim_commit_sha": dispatch["claim_commit_sha"],
        "terminal_commit_sha": dispatch["terminal_commit_sha"],
        "terminal_receipt_sha256": dispatch["receipt_sha256"],
        "claim_capability_sha256": dispatch["claim_capability_sha256"],
        "provider_receipt_sha256": provider_digest,
        **_authority_flags(),
    }
    metadata_json = _canonical_json_text(metadata)
    plan = {
        "schema": CONTACTED_PLAN_SCHEMA,
        "state": "CONTACTED",
        "generation": dispatch["generation"],
        "key_sha256": dispatch["key_sha256"],
        "claim_seam_sha256": dispatch["claim_seam_sha256"],
        "claim_commit_sha": dispatch["claim_commit_sha"],
        "terminal_commit_sha": dispatch["terminal_commit_sha"],
        "terminal_receipt_sha256": dispatch["receipt_sha256"],
        "claim_capability_sha256": dispatch["claim_capability_sha256"],
        "provider_receipt_sha256": provider_digest,
        "contacted_branch_name": contacted_branch(dispatch["claim_seam_sha256"]),
        "metadata_path": _metadata_path(dispatch["claim_seam_sha256"], "contacted"),
        "metadata_sha256": _text_digest(metadata_json),
        "metadata_json": metadata_json,
        **_authority_flags(),
    }
    return _seal(plan, "plan_sha256")


def verify_contacted_plan(raw: Mapping[str, Any]) -> dict[str, Any]:
    plan = _verify_seal(raw, "plan_sha256")
    if plan.get("schema") != CONTACTED_PLAN_SCHEMA or plan.get("state") != "CONTACTED":
        raise CustodyError("contacted plan schema/state mismatch")
    if plan.get("contacted_branch_name") != contacted_branch(plan["claim_seam_sha256"]):
        raise CustodyError("contacted branch mismatch")
    if plan.get("metadata_path") != _metadata_path(plan["claim_seam_sha256"], "contacted"):
        raise CustodyError("contacted metadata path mismatch")
    for field in ("terminal_receipt_sha256","claim_capability_sha256","provider_receipt_sha256"):
        _sha64(plan[field], field)
    _sha40(plan["claim_commit_sha"], "claim_commit_sha")
    _sha40(plan["terminal_commit_sha"], "terminal_commit_sha")
    expected_metadata = {
        "schema": SCHEMA,
        "record_type": "CONTACTED",
        "state": "CONTACTED",
        "generation": plan["generation"],
        "key_sha256": plan["key_sha256"],
        "claim_seam_sha256": plan["claim_seam_sha256"],
        "claim_commit_sha": plan["claim_commit_sha"],
        "terminal_commit_sha": plan["terminal_commit_sha"],
        "terminal_receipt_sha256": plan["terminal_receipt_sha256"],
        "claim_capability_sha256": plan["claim_capability_sha256"],
        "provider_receipt_sha256": plan["provider_receipt_sha256"],
        **_authority_flags(),
    }
    expected_text = _canonical_json_text(expected_metadata)
    if plan.get("metadata_json") != expected_text or plan.get("metadata_sha256") != _text_digest(expected_text):
        raise CustodyError("contacted metadata binding mismatch")
    return plan


def bind_contacted_commit(plan_raw: Mapping[str, Any], contacted_commit_sha: str) -> dict[str, Any]:
    plan = verify_contacted_plan(plan_raw)
    intent = {
        "schema": CONTACTED_INTENT_SCHEMA,
        "state": "CONTACTED",
        "generation": plan["generation"],
        "key_sha256": plan["key_sha256"],
        "claim_seam_sha256": plan["claim_seam_sha256"],
        "terminal_commit_sha": plan["terminal_commit_sha"],
        "terminal_receipt_sha256": plan["terminal_receipt_sha256"],
        "contacted_branch_name": plan["contacted_branch_name"],
        "metadata_path": plan["metadata_path"],
        "metadata_sha256": plan["metadata_sha256"],
        "plan_sha256": plan["plan_sha256"],
        "contacted_commit_sha": _sha40(contacted_commit_sha, "contacted_commit_sha"),
        **_authority_flags(),
    }
    return _seal(intent, "intent_sha256")


def contacted_receipt_from_readback(
    plan_raw: Mapping[str, Any], intent_raw: Mapping[str, Any], *,
    live_branch_sha: str, live_parent_sha: str, live_metadata_json: str,
) -> dict[str, Any]:
    plan = verify_contacted_plan(plan_raw)
    intent = _verify_seal(intent_raw, "intent_sha256")
    if intent.get("schema") != CONTACTED_INTENT_SCHEMA or intent.get("plan_sha256") != plan["plan_sha256"]:
        raise CustodyError("contacted intent mismatch")
    if _sha40(live_branch_sha, "live_branch_sha") != intent["contacted_commit_sha"]:
        raise CustodyError("contacted branch head mismatch")
    if _sha40(live_parent_sha, "live_parent_sha") != plan["terminal_commit_sha"]:
        raise CustodyError("contacted parent mismatch")
    _verify_live_metadata(plan["metadata_json"], live_metadata_json)
    receipt = {
        "schema": CONTACTED_RECEIPT_SCHEMA,
        "state": "CONTACTED",
        "generation": plan["generation"],
        "key_sha256": plan["key_sha256"],
        "claim_seam_sha256": plan["claim_seam_sha256"],
        "claim_commit_sha": plan["claim_commit_sha"],
        "claim_capability_sha256": plan["claim_capability_sha256"],
        "terminal_commit_sha": plan["terminal_commit_sha"],
        "terminal_receipt_sha256": plan["terminal_receipt_sha256"],
        "provider_receipt_sha256": plan["provider_receipt_sha256"],
        "contacted_branch_name": plan["contacted_branch_name"],
        "metadata_path": plan["metadata_path"],
        "metadata_sha256": plan["metadata_sha256"],
        "metadata_json": plan["metadata_json"],
        "contacted_commit_sha": intent["contacted_commit_sha"],
        "plan_sha256": plan["plan_sha256"],
        "intent_sha256": intent["intent_sha256"],
        **_authority_flags(),
    }
    return _seal(receipt, "receipt_sha256")


def verify_contacted_receipt(raw: Mapping[str, Any]) -> dict[str, Any]:
    receipt = _verify_seal(raw, "receipt_sha256")
    if receipt.get("schema") != CONTACTED_RECEIPT_SCHEMA or receipt.get("state") != "CONTACTED":
        raise CustodyError("contacted receipt schema/state mismatch")
    if receipt.get("contacted_branch_name") != contacted_branch(receipt["claim_seam_sha256"]):
        raise CustodyError("contacted receipt branch mismatch")
    _sha40(receipt["terminal_commit_sha"], "terminal_commit_sha")
    _sha40(receipt["contacted_commit_sha"], "contacted_commit_sha")
    _sha64(receipt["provider_receipt_sha256"], "provider_receipt_sha256")
    expected_metadata = {
        "schema": SCHEMA,
        "record_type": "CONTACTED",
        "state": "CONTACTED",
        "generation": receipt["generation"],
        "key_sha256": receipt["key_sha256"],
        "claim_seam_sha256": receipt["claim_seam_sha256"],
        "claim_commit_sha": receipt.get("claim_commit_sha"),
        "terminal_commit_sha": receipt["terminal_commit_sha"],
        "terminal_receipt_sha256": receipt["terminal_receipt_sha256"],
        "claim_capability_sha256": receipt.get("claim_capability_sha256"),
        "provider_receipt_sha256": receipt["provider_receipt_sha256"],
        **_authority_flags(),
    }
    _sha40(expected_metadata["claim_commit_sha"], "claim_commit_sha")
    _sha64(expected_metadata["claim_capability_sha256"], "claim_capability_sha256")
    expected_text = _canonical_json_text(expected_metadata)
    if receipt.get("metadata_json") != expected_text or receipt.get("metadata_sha256") != _text_digest(expected_text):
        raise CustodyError("contacted receipt metadata binding mismatch")
    return receipt
