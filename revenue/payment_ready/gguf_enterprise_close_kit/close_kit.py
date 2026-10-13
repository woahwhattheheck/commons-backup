from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

AUTHORITY_SCHEMA = "tjlabs.gguf-12k-authority/v2"
INTAKE_SCHEMA = "tjlabs.gguf-12k-intake/v2"
EVIDENCE_SCHEMA = "tjlabs.gguf-12k-delivery-evidence/v2"
ACCEPTANCE_SCHEMA = "tjlabs.gguf-12k-acceptance/v2"
CLOSE_PACKET_SCHEMA = "tjlabs.gguf-12k-close-packet/v2"

OFFER_ID = "gguf-diagnostic-10d-12k"
PUBLIC_PRODUCT_NAME = "White Box diagnostic"
CURRENCY = "USD"
FIXED_AMOUNT_USD = 12000
TERM_CALENDAR_DAYS = 10
M1_AMOUNT_USD = 6000
M2_AMOUNT_USD = 6000
M1_DUE = "before customer file exchange; after NDA and SOW signing"
M2_DUE = "on AT1-AT6 acceptance"
ACCEPTANCE_RULE = "rollback evidence, not metric lift"
ACCEPTANCE_IDS = ("AT1", "AT2", "AT3", "AT4", "AT5", "AT6")
PUBLIC_SURFACE = "diagnostic.html"
CANONICAL_PACK = "revenue/payment_ready/pack.json"
CANONICAL_RECOVERY = "revenue/payment_ready/recovery.json"
RECOVERY_RECEIPT_SCHEMA = "revenue-recovery/v1"
SAFE_EVIDENCE_NONE = "NONE"
SYNTHETIC_MODE = "SYNTHETIC_REHEARSAL"
PRODUCTION_MODE = "PRODUCTION"

AUTHORITY_FALSE = {
    "buyer_contact_authorized": False,
    "private_file_transfer_authorized": False,
    "nda_signed": False,
    "sow_signed": False,
    "m1_payment_received": False,
    "customer_acceptance_recorded": False,
    "invoice_authorized": False,
    "payment_mutation_authorized": False,
    "revenue_recognized": False,
}

SHA_RE = re.compile(r"^[0-9a-f]{64}$")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}$")
SENSITIVE_KEY_ALLOWLIST = {
    "raw_model_public_allowed",
}
SENSITIVE_KEY_PARTS = {
    "password", "passwd", "secret_value", "credential_value", "private_key",
    "api_key", "auth_token", "access_token", "routing_number", "account_number",
    "card_number", "cvv", "tax_id", "model_bytes", "gguf_bytes", "raw_model",
    "signed_document_bytes",
}


class ContractError(ValueError):
    pass


def _pairs_no_dupes(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ContractError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def strict_loads(text: str) -> Any:
    return json.loads(
        text,
        object_pairs_hook=_pairs_no_dupes,
        parse_constant=lambda token: (_ for _ in ()).throw(
            ContractError(f"non-finite number: {token}")
        ),
    )


def strict_load(path: str | Path) -> Any:
    return strict_loads(Path(path).read_text(encoding="utf-8"))


def canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")


def canonical_compact_json(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _dict(value: Any, where: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise ContractError(f"{where}: object required")
    return value


def _list(value: Any, where: str, *, min_items: int = 0, max_items: int = 1000) -> list[Any]:
    if type(value) is not list or not (min_items <= len(value) <= max_items):
        raise ContractError(f"{where}: list length in [{min_items}, {max_items}] required")
    return value


def _exact_keys(value: Any, keys: set[str], where: str) -> dict[str, Any]:
    obj = _dict(value, where)
    if set(obj) != keys:
        raise ContractError(
            f"{where}: key mismatch missing={sorted(keys - set(obj))} extra={sorted(set(obj) - keys)}"
        )
    return obj


def _text(value: Any, where: str, *, max_len: int = 2000) -> str:
    if type(value) is not str or not value or len(value) > max_len:
        raise ContractError(f"{where}: bounded non-empty string required")
    if any(ord(ch) < 32 and ch not in "\t\n" for ch in value):
        raise ContractError(f"{where}: control characters forbidden")
    return value


def _ident(value: Any, where: str) -> str:
    text = _text(value, where, max_len=96)
    if not ID_RE.fullmatch(text):
        raise ContractError(f"{where}: safe identifier required")
    return text


def _bool(value: Any, where: str) -> bool:
    if type(value) is not bool:
        raise ContractError(f"{where}: bool required")
    return value


def _int(value: Any, where: str, lo: int = 0, hi: int = 2**63 - 1) -> int:
    if type(value) is not int or not (lo <= value <= hi):
        raise ContractError(f"{where}: integer in [{lo}, {hi}] required")
    return value


def _sha(value: Any, where: str, *, allow_none: bool = False) -> str:
    if allow_none and value == SAFE_EVIDENCE_NONE:
        return value
    text = _text(value, where, max_len=64)
    if not SHA_RE.fullmatch(text):
        raise ContractError(f"{where}: lowercase SHA-256 required")
    return text


def _https(value: Any, where: str) -> str:
    text = _text(value, where, max_len=500)
    parsed = urlparse(text)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ContractError(f"{where}: public HTTPS URL required")
    if parsed.query or parsed.fragment:
        raise ContractError(f"{where}: query/fragment forbidden")
    return text


def _assert_no_sensitive_keys(value: Any, where: str = "document") -> None:
    if type(value) is dict:
        for key, child in value.items():
            lowered = str(key).lower()
            if lowered not in SENSITIVE_KEY_ALLOWLIST and any(part in lowered for part in SENSITIVE_KEY_PARTS):
                raise ContractError(f"{where}.{key}: sensitive/raw field name forbidden")
            _assert_no_sensitive_keys(child, f"{where}.{key}")
    elif type(value) is list:
        for index, child in enumerate(value):
            _assert_no_sensitive_keys(child, f"{where}[{index}]")


def _add_receipt(packet: dict[str, Any]) -> dict[str, Any]:
    out = dict(packet)
    out["receipt_sha256"] = sha256_hex(canonical_json(packet))
    return out


def _terms_record(pack: dict[str, Any]) -> dict[str, Any]:
    offer = _dict(pack.get("offer"), "pack.offer")
    tests = _list(pack.get("acceptance_tests"), "pack.acceptance_tests", min_items=6, max_items=6)
    milestones = _list(offer.get("milestones"), "pack.offer.milestones", min_items=2, max_items=2)
    return {
        "acceptance_rule": offer.get("acceptance_rule"),
        "acceptance_tests": [_dict(row, "pack.acceptance_tests[]").get("id") for row in tests],
        "currency": offer.get("currency"),
        "fixed_amount": offer.get("fixed_amount"),
        "milestones": [
            {
                "amount": _dict(row, "pack.offer.milestones[]").get("amount"),
                "due": _dict(row, "pack.offer.milestones[]").get("due"),
                "id": _dict(row, "pack.offer.milestones[]").get("id"),
            }
            for row in milestones
        ],
        "offer_id": offer.get("offer_id"),
        "term_calendar_days": offer.get("term_calendar_days"),
    }


def _stage_state(recovery: dict[str, Any], stage_name: str) -> str:
    matches = [
        _dict(row, "recovery.stages[]")
        for row in _list(recovery.get("stages"), "recovery.stages", min_items=1, max_items=32)
        if _dict(row, "recovery.stages[]").get("stage") == stage_name
    ]
    if len(matches) != 1:
        raise ContractError(f"recovery.stages: exactly one {stage_name} stage required")
    return _text(matches[0].get("state"), f"recovery.stages.{stage_name}.state", max_len=64)


def _authority_packet(
    pack: Any,
    recovery: Any,
    *,
    pack_text: str | None = None,
    recovery_text: str | None = None,
) -> dict[str, Any]:
    p = _dict(pack, "pack")
    r = _dict(recovery, "recovery")
    offer = _dict(p.get("offer"), "pack.offer")
    rec_offer = _dict(r.get("offer"), "recovery.offer")

    if offer.get("offer_id") != OFFER_ID or rec_offer.get("offer_id") != OFFER_ID:
        raise ContractError("canonical offer id drift")
    if offer.get("public_product_name") != PUBLIC_PRODUCT_NAME:
        raise ContractError("canonical public product name drift")
    if offer.get("currency") != CURRENCY or rec_offer.get("currency") != CURRENCY:
        raise ContractError("canonical currency drift")
    if offer.get("fixed_amount") != FIXED_AMOUNT_USD or rec_offer.get("fixed_amount") != FIXED_AMOUNT_USD:
        raise ContractError("canonical fixed amount drift")
    if offer.get("term_calendar_days") != TERM_CALENDAR_DAYS or rec_offer.get("term_calendar_days") != TERM_CALENDAR_DAYS:
        raise ContractError("canonical term drift")
    if offer.get("acceptance_rule") != ACCEPTANCE_RULE or rec_offer.get("acceptance_rule") != ACCEPTANCE_RULE:
        raise ContractError("canonical acceptance rule drift")
    if offer.get("payment_collection") != "NOT_PROVIDED_ON_THIS_PAGE":
        raise ContractError("canonical payment-collection boundary drift")

    milestones = _list(offer.get("milestones"), "pack.offer.milestones", min_items=2, max_items=2)
    m1 = _dict(milestones[0], "pack.offer.milestones[0]")
    m2 = _dict(milestones[1], "pack.offer.milestones[1]")
    if (m1.get("id"), m1.get("amount"), m1.get("due")) != (
        "M1_BEFORE_FILE", M1_AMOUNT_USD, M1_DUE
    ):
        raise ContractError("canonical M1 drift")
    if (m2.get("id"), m2.get("amount"), m2.get("due")) != (
        "M2_AT1_AT6", M2_AMOUNT_USD, M2_DUE
    ):
        raise ContractError("canonical M2 drift")

    rec_milestones = _list(rec_offer.get("milestones"), "recovery.offer.milestones", min_items=2, max_items=2)
    rec_m1 = _dict(rec_milestones[0], "recovery.offer.milestones[0]")
    rec_m2 = _dict(rec_milestones[1], "recovery.offer.milestones[1]")
    if (rec_m1.get("id"), rec_m1.get("amount"), rec_m1.get("due")) != (
        "M1_BEFORE_FILE", M1_AMOUNT_USD, M1_DUE
    ):
        raise ContractError("canonical recovery M1 drift")
    if (rec_m2.get("id"), rec_m2.get("amount")) != ("M2_AT1_AT6", M2_AMOUNT_USD):
        raise ContractError("canonical recovery M2 drift")

    pack_tests = tuple(
        _dict(row, "pack.acceptance_tests[]").get("id")
        for row in _list(p.get("acceptance_tests"), "pack.acceptance_tests", min_items=6, max_items=6)
    )
    recovery_tests = tuple(
        _list(rec_offer.get("acceptance_tests"), "recovery.offer.acceptance_tests", min_items=6, max_items=6)
    )
    if pack_tests != ACCEPTANCE_IDS or recovery_tests != ACCEPTANCE_IDS:
        raise ContractError("canonical AT1-AT6 set/order drift")

    if rec_offer.get("source") != CANONICAL_PACK:
        raise ContractError("canonical recovery source path drift")
    terms_sha = sha256_hex(canonical_compact_json(_terms_record(p)))
    if rec_offer.get("terms_sha256") != terms_sha:
        raise ContractError("canonical recovery terms digest drift")

    pack_source_sha = None
    recovery_text_sha = None
    if pack_text is not None:
        pack_source_sha = sha256_hex(pack_text.encode("utf-8"))
        if rec_offer.get("source_sha256") != pack_source_sha:
            raise ContractError("canonical recovery exact source digest drift")
    if recovery_text is not None:
        recovery_text_sha = sha256_hex(recovery_text.encode("utf-8"))

    public = _dict(r.get("public_surface"), "recovery.public_surface")
    if public.get("path") != PUBLIC_SURFACE:
        raise ContractError("canonical public surface drift")
    for field in ("no_login", "no_auth", "no_gate"):
        if public.get(field) is not True:
            raise ContractError(f"canonical public surface {field} drift")

    processor = _dict(r.get("processor_handoff"), "recovery.processor_handoff")
    if processor.get("values_never_enter_commons") is not True:
        raise ContractError("processor private-values boundary drift")
    if processor.get("recommended_provider") != "Stripe":
        raise ContractError("processor recommendation drift")

    contract = _dict(r.get("receipt_contract"), "recovery.receipt_contract")
    required_contract = {
        "schema": "revenue/payment_ready/receipt.schema.json",
        "instrument": "host/revenue_recovery.py",
        "artifact_digest_verified_against_exact_bytes": True,
        "private_artifact_bytes_require_disjoint_external_evidence_root": True,
        "predecessor_source_digest_verified_against_exact_bytes": True,
        "runtime_deterministic_replay_is_transition_authority": True,
        "schema_binds_later_stage_state_and_facts": True,
        "nda_sow_m1_evidence_distinct": True,
        "real_world_nda_sow_m1_order_is_owner_reported": True,
    }
    for key, expected in required_contract.items():
        if contract.get(key) != expected:
            raise ContractError(f"canonical recovery receipt contract drift: {key}")

    truth = _dict(r.get("truth"), "recovery.truth")
    collected_cash = _int(truth.get("collected_cash_usd"), "recovery.truth.collected_cash_usd", 0)
    if rec_offer.get("collected_cash_usd") != collected_cash:
        raise ContractError("canonical recovery cash disagreement")
    if rec_offer.get("demand") != truth.get("demand"):
        raise ContractError("canonical recovery demand disagreement")

    packet = {
        "schema": AUTHORITY_SCHEMA,
        "offer_id": OFFER_ID,
        "public_product_name": PUBLIC_PRODUCT_NAME,
        "currency": CURRENCY,
        "fixed_amount_usd": FIXED_AMOUNT_USD,
        "term_calendar_days": TERM_CALENDAR_DAYS,
        "m1_amount_usd": M1_AMOUNT_USD,
        "m1_due": M1_DUE,
        "m2_amount_usd": M2_AMOUNT_USD,
        "m2_due": M2_DUE,
        "acceptance_rule": ACCEPTANCE_RULE,
        "acceptance_ids": list(ACCEPTANCE_IDS),
        "public_surface": PUBLIC_SURFACE,
        "public_surface_kind": "PURCHASE_INTENT_ONLY",
        "payment_collection_on_public_surface": False,
        "canonical_demand": _text(rec_offer.get("demand"), "recovery.offer.demand", max_len=64),
        "canonical_buyer_truth": _text(truth.get("buyer"), "recovery.truth.buyer", max_len=64),
        "canonical_legal_acceptance": _text(truth.get("legal_acceptance"), "recovery.truth.legal_acceptance", max_len=64),
        "canonical_delivery": _text(truth.get("delivery"), "recovery.truth.delivery", max_len=64),
        "canonical_cash_state": _text(rec_offer.get("cash_state"), "recovery.offer.cash_state", max_len=64),
        "canonical_collected_cash_usd": collected_cash,
        "canonical_purchase_intent_stage": _stage_state(r, "PURCHASE_INTENT"),
        "canonical_acceptance_stage": _stage_state(r, "ACCEPTANCE"),
        "canonical_delivery_stage": _stage_state(r, "DELIVERY"),
        "canonical_offer_source_sha256": _sha(rec_offer.get("source_sha256"), "recovery.offer.source_sha256"),
        "canonical_terms_sha256": _sha(rec_offer.get("terms_sha256"), "recovery.offer.terms_sha256"),
        "pack_text_sha256": pack_source_sha or SAFE_EVIDENCE_NONE,
        "recovery_text_sha256": recovery_text_sha or SAFE_EVIDENCE_NONE,
        **AUTHORITY_FALSE,
    }
    return _add_receipt(packet)


def load_authority(repo_root: str | Path) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    try:
        pack_text = (root / CANONICAL_PACK).read_text(encoding="utf-8")
        recovery_text = (root / CANONICAL_RECOVERY).read_text(encoding="utf-8")
    except OSError as exc:
        raise ContractError("canonical authority files unavailable") from exc
    return _authority_packet(
        strict_loads(pack_text), strict_loads(recovery_text),
        pack_text=pack_text, recovery_text=recovery_text,
    )


def validate_authority_docs(pack: Any, recovery: Any) -> dict[str, Any]:
    """Review helper only. Production compilation always calls load_authority(repo_root)."""
    return _authority_packet(pack, recovery)


def validate_intake(document: Any) -> dict[str, Any]:
    _assert_no_sensitive_keys(document)
    row = _exact_keys(
        document,
        {"schema", "mode", "engagement_id", "customer_reference", "gguf", "harness", "scope", "security", "recovery_authority"},
        "intake",
    )
    if row["schema"] != INTAKE_SCHEMA:
        raise ContractError("intake.schema: unsupported")
    mode = _text(row["mode"], "intake.mode", max_len=32)
    if mode not in {SYNTHETIC_MODE, PRODUCTION_MODE}:
        raise ContractError("intake.mode: unsupported")
    engagement_id = _ident(row["engagement_id"], "intake.engagement_id")
    customer_reference = _ident(row["customer_reference"], "intake.customer_reference")

    gguf = _exact_keys(row["gguf"], {"sha256", "size_bytes", "control_attested"}, "intake.gguf")
    gguf_sha = _sha(gguf["sha256"], "intake.gguf.sha256")
    gguf_size = _int(gguf["size_bytes"], "intake.gguf.size_bytes", 1)
    control = _bool(gguf["control_attested"], "intake.gguf.control_attested")

    harness = _exact_keys(
        row["harness"],
        {"name", "version", "reproducible_command_sha256", "eval_suite_sha256", "ready"},
        "intake.harness",
    )
    harness_name = _text(harness["name"], "intake.harness.name", max_len=120)
    harness_version = _text(harness["version"], "intake.harness.version", max_len=80)
    command_sha = _sha(harness["reproducible_command_sha256"], "intake.harness.reproducible_command_sha256")
    eval_sha = _sha(harness["eval_suite_sha256"], "intake.harness.eval_suite_sha256")
    harness_ready = _bool(harness["ready"], "intake.harness.ready")

    scope = _exact_keys(row["scope"], {"objective", "bounded_intervention", "metric_lift_guaranteed"}, "intake.scope")
    objective = _text(scope["objective"], "intake.scope.objective", max_len=1000)
    bounded_intervention = _bool(scope["bounded_intervention"], "intake.scope.bounded_intervention")
    if _bool(scope["metric_lift_guaranteed"], "intake.scope.metric_lift_guaranteed"):
        raise ContractError("intake.scope.metric_lift_guaranteed: canonical offer never guarantees metric lift")

    security = _exact_keys(
        row["security"],
        {"data_classification", "transfer_channel", "retention_days", "raw_model_public_allowed", "credentials_required", "public_contact_url"},
        "intake.security",
    )
    if security["data_classification"] != "CONFIDENTIAL_CUSTOMER_CONTROLLED":
        raise ContractError("intake.security.data_classification: unsupported")
    if security["transfer_channel"] != "OWNER_PRIVATE_EXTERNAL":
        raise ContractError("intake.security.transfer_channel: must remain owner-private external")
    retention_days = _int(security["retention_days"], "intake.security.retention_days", 0, 30)
    if _bool(security["raw_model_public_allowed"], "intake.security.raw_model_public_allowed"):
        raise ContractError("intake.security.raw_model_public_allowed: must remain false")
    if _bool(security["credentials_required"], "intake.security.credentials_required"):
        raise ContractError("intake.security.credentials_required: this carrier accepts no credentials")
    public_contact_url = _https(security["public_contact_url"], "intake.security.public_contact_url")

    recovery = _exact_keys(
        row["recovery_authority"],
        {"receipt_schema_version", "acceptance_receipt_sha256", "offer_source_sha256", "terms_sha256"},
        "intake.recovery_authority",
    )
    if recovery["receipt_schema_version"] != RECOVERY_RECEIPT_SCHEMA:
        raise ContractError("intake.recovery_authority.receipt_schema_version: unsupported")
    acceptance_receipt = _sha(recovery["acceptance_receipt_sha256"], "intake.recovery_authority.acceptance_receipt_sha256", allow_none=True)
    offer_source_sha = _sha(recovery["offer_source_sha256"], "intake.recovery_authority.offer_source_sha256", allow_none=True)
    terms_sha = _sha(recovery["terms_sha256"], "intake.recovery_authority.terms_sha256", allow_none=True)

    holds: list[str] = []
    if not control:
        holds.append("HOLD_GGUF_CONTROL")
    if not harness_ready:
        holds.append("HOLD_HARNESS_NOT_READY")
    if not bounded_intervention:
        holds.append("HOLD_UNBOUNDED_SCOPE")
    if mode == PRODUCTION_MODE:
        holds.append("HOLD_RECOVERY_REPLAY_REQUIRED")

    packet = {
        "schema": INTAKE_SCHEMA,
        "mode": mode,
        "engagement_id": engagement_id,
        "customer_reference": customer_reference,
        "gguf_sha256": gguf_sha,
        "gguf_size_bytes": gguf_size,
        "harness_name": harness_name,
        "harness_version": harness_version,
        "harness_command_sha256": command_sha,
        "eval_suite_sha256": eval_sha,
        "objective": objective,
        "retention_days": retention_days,
        "public_contact_url": public_contact_url,
        "recovery_receipt_shape_present": acceptance_receipt != SAFE_EVIDENCE_NONE,
        "recovery_source_generation_present": offer_source_sha != SAFE_EVIDENCE_NONE and terms_sha != SAFE_EVIDENCE_NONE,
        "recovery_runtime_replay_verified": False,
        "qualification_state": "SYNTHETIC_EVIDENCE_SHAPE_ONLY" if mode == SYNTHETIC_MODE and not holds else "HOLD",
        "holds": holds,
        **AUTHORITY_FALSE,
    }
    return _add_receipt(packet)


def _validated_run(raw: Any, *, where: str, expected_kind: str, expected_input_sha: str, intake_result: dict[str, Any]) -> dict[str, Any]:
    run = _exact_keys(
        raw,
        {"run_kind", "input_artifact_sha256", "harness_command_sha256", "eval_suite_sha256", "outcome_summary_sha256", "receipt_sha256"},
        where,
    )
    payload = {
        "run_kind": _text(run["run_kind"], f"{where}.run_kind", max_len=32),
        "input_artifact_sha256": _sha(run["input_artifact_sha256"], f"{where}.input_artifact_sha256"),
        "harness_command_sha256": _sha(run["harness_command_sha256"], f"{where}.harness_command_sha256"),
        "eval_suite_sha256": _sha(run["eval_suite_sha256"], f"{where}.eval_suite_sha256"),
        "outcome_summary_sha256": _sha(run["outcome_summary_sha256"], f"{where}.outcome_summary_sha256"),
    }
    receipt = _sha(run["receipt_sha256"], f"{where}.receipt_sha256")
    if payload["run_kind"] != expected_kind:
        raise ContractError(f"{where}.run_kind: expected {expected_kind}")
    if payload["input_artifact_sha256"] != expected_input_sha:
        raise ContractError(f"{where}: input artifact binding mismatch")
    if payload["harness_command_sha256"] != intake_result["harness_command_sha256"]:
        raise ContractError(f"{where}: harness command generation mismatch")
    if payload["eval_suite_sha256"] != intake_result["eval_suite_sha256"]:
        raise ContractError(f"{where}: eval suite generation mismatch")
    expected_receipt = sha256_hex(canonical_json(payload))
    if receipt != expected_receipt:
        raise ContractError(f"{where}.receipt_sha256: semantic receipt mismatch")
    return {**payload, "receipt_sha256": receipt}


def evaluate_acceptance(intake: Any, evidence: Any) -> dict[str, Any]:
    intake_result = validate_intake(intake)
    _assert_no_sensitive_keys(evidence)
    row = _exact_keys(
        evidence,
        {"schema", "mode", "engagement_id", "artifacts", "harness_runs", "finding", "delivery_receipt", "payment_reference_sha256"},
        "evidence",
    )
    if row["schema"] != EVIDENCE_SCHEMA:
        raise ContractError("evidence.schema: unsupported")
    if row["mode"] != intake_result["mode"]:
        raise ContractError("evidence.mode: intake mismatch")
    engagement_id = _ident(row["engagement_id"], "evidence.engagement_id")
    if engagement_id != intake_result["engagement_id"]:
        raise ContractError("evidence.engagement_id: intake mismatch")

    artifacts = _exact_keys(row["artifacts"], {"original", "ablated", "restored"}, "evidence.artifacts")
    parsed: dict[str, tuple[str, int]] = {}
    for name in ("original", "ablated", "restored"):
        artifact = _exact_keys(artifacts[name], {"sha256", "size_bytes"}, f"evidence.artifacts.{name}")
        parsed[name] = (
            _sha(artifact["sha256"], f"evidence.artifacts.{name}.sha256"),
            _int(artifact["size_bytes"], f"evidence.artifacts.{name}.size_bytes", 1),
        )
    original_sha, original_size = parsed["original"]
    ablated_sha, _ = parsed["ablated"]
    restored_sha, restored_size = parsed["restored"]

    runs = _exact_keys(row["harness_runs"], {"baseline", "ablation", "restore"}, "evidence.harness_runs")
    baseline = _validated_run(runs["baseline"], where="evidence.harness_runs.baseline", expected_kind="BASELINE", expected_input_sha=original_sha, intake_result=intake_result)
    ablation = _validated_run(runs["ablation"], where="evidence.harness_runs.ablation", expected_kind="ABLATION", expected_input_sha=ablated_sha, intake_result=intake_result)
    restore = _validated_run(runs["restore"], where="evidence.harness_runs.restore", expected_kind="RESTORE", expected_input_sha=restored_sha, intake_result=intake_result)
    run_receipts = [baseline["receipt_sha256"], ablation["receipt_sha256"], restore["receipt_sha256"]]

    finding = _exact_keys(row["finding"], {"report_sha256", "statement", "limitations"}, "evidence.finding")
    report_sha = _sha(finding["report_sha256"], "evidence.finding.report_sha256")
    statement = _text(finding["statement"], "evidence.finding.statement", max_len=1200)
    limitations = [
        _text(value, f"evidence.finding.limitations[{index}]", max_len=500)
        for index, value in enumerate(_list(finding["limitations"], "evidence.finding.limitations", min_items=1, max_items=20))
    ]

    delivery = _exact_keys(row["delivery_receipt"], {"manifest", "receipt_sha256"}, "evidence.delivery_receipt")
    manifest = _exact_keys(
        delivery["manifest"],
        {"engagement_id", "original_sha256", "ablated_sha256", "restored_sha256", "baseline_run_receipt_sha256", "ablation_run_receipt_sha256", "restore_run_receipt_sha256", "report_sha256"},
        "evidence.delivery_receipt.manifest",
    )
    normalized_manifest = {
        "engagement_id": _ident(manifest["engagement_id"], "evidence.delivery_receipt.manifest.engagement_id"),
        "original_sha256": _sha(manifest["original_sha256"], "evidence.delivery_receipt.manifest.original_sha256"),
        "ablated_sha256": _sha(manifest["ablated_sha256"], "evidence.delivery_receipt.manifest.ablated_sha256"),
        "restored_sha256": _sha(manifest["restored_sha256"], "evidence.delivery_receipt.manifest.restored_sha256"),
        "baseline_run_receipt_sha256": _sha(manifest["baseline_run_receipt_sha256"], "evidence.delivery_receipt.manifest.baseline_run_receipt_sha256"),
        "ablation_run_receipt_sha256": _sha(manifest["ablation_run_receipt_sha256"], "evidence.delivery_receipt.manifest.ablation_run_receipt_sha256"),
        "restore_run_receipt_sha256": _sha(manifest["restore_run_receipt_sha256"], "evidence.delivery_receipt.manifest.restore_run_receipt_sha256"),
        "report_sha256": _sha(manifest["report_sha256"], "evidence.delivery_receipt.manifest.report_sha256"),
    }
    expected_manifest = {
        "engagement_id": engagement_id,
        "original_sha256": original_sha,
        "ablated_sha256": ablated_sha,
        "restored_sha256": restored_sha,
        "baseline_run_receipt_sha256": baseline["receipt_sha256"],
        "ablation_run_receipt_sha256": ablation["receipt_sha256"],
        "restore_run_receipt_sha256": restore["receipt_sha256"],
        "report_sha256": report_sha,
    }
    if normalized_manifest != expected_manifest:
        raise ContractError("evidence.delivery_receipt.manifest: semantic binding mismatch")
    delivery_receipt_sha = _sha(delivery["receipt_sha256"], "evidence.delivery_receipt.receipt_sha256")
    if delivery_receipt_sha != sha256_hex(canonical_json(normalized_manifest)):
        raise ContractError("evidence.delivery_receipt.receipt_sha256: semantic receipt mismatch")

    payment_reference = _sha(row["payment_reference_sha256"], "evidence.payment_reference_sha256", allow_none=True)
    tests = {
        "AT1": original_sha == intake_result["gguf_sha256"] and original_size == intake_result["gguf_size_bytes"],
        "AT2": ablated_sha != original_sha,
        "AT3": restored_sha == original_sha and restored_size == original_size,
        "AT4": len(set(run_receipts)) == 3,
        "AT5": bool(statement.strip()) and bool(limitations),
        "AT6": True,
    }
    failed = [test_id for test_id in ACCEPTANCE_IDS if not tests[test_id]]
    if intake_result["mode"] == SYNTHETIC_MODE:
        verdict = "SYNTHETIC_AT1_AT6_COMPLETE_NON_PRODUCTION" if not failed else "SYNTHETIC_HOLD_ACCEPTANCE_EVIDENCE"
    else:
        verdict = "HOLD_RECOVERY_REPLAY_REQUIRED"

    return _add_receipt({
        "schema": ACCEPTANCE_SCHEMA,
        "mode": intake_result["mode"],
        "engagement_id": engagement_id,
        "acceptance_rule": ACCEPTANCE_RULE,
        "tests": tests,
        "failed_tests": failed,
        "verdict": verdict,
        "payment_reference_present": payment_reference != SAFE_EVIDENCE_NONE,
        "payment_reference_proves_acceptance": False,
        "delivery_receipt_sha256": delivery_receipt_sha,
        "finding_report_sha256": report_sha,
        **AUTHORITY_FALSE,
    })


def _canonical_blocker(authority: dict[str, Any]) -> str | None:
    if authority["canonical_purchase_intent_stage"] == "NEEDS_BUYER":
        return "HOLD_CANONICAL_NEEDS_BUYER"
    if authority["canonical_acceptance_stage"] == "NEEDS_BUYER":
        return "HOLD_CANONICAL_NEEDS_ACCEPTANCE"
    if authority["canonical_delivery_stage"] in {"NEEDS_ACCEPTANCE", "NEEDS_BUYER"}:
        return "HOLD_CANONICAL_NEEDS_DELIVERY"
    if authority["canonical_legal_acceptance"] != "OWNER_REPORTED":
        return "HOLD_CANONICAL_LEGAL_ACCEPTANCE"
    if authority["canonical_delivery"] != "OWNER_REPORTED":
        return "HOLD_CANONICAL_DELIVERY"
    return None


def compile_close_packet(repo_root: str | Path, intake: Any, evidence: Any | None = None) -> dict[str, Any]:
    """Compile from current canonical repo authority. Caller authority packets are not accepted."""
    auth = load_authority(repo_root)
    intake_result = validate_intake(intake)
    acceptance = evaluate_acceptance(intake, evidence) if evidence is not None else None
    canonical_blocker = _canonical_blocker(auth)

    if intake_result["mode"] == SYNTHETIC_MODE:
        state = (
            "SYNTHETIC_EVIDENCE_COMPLETE_NON_PRODUCTION"
            if acceptance and acceptance["verdict"] == "SYNTHETIC_AT1_AT6_COMPLETE_NON_PRODUCTION"
            else "SYNTHETIC_HOLD"
        )
    elif canonical_blocker is not None:
        state = canonical_blocker
    else:
        state = "HOLD_RECOVERY_REPLAY_REQUIRED"

    return _add_receipt({
        "schema": CLOSE_PACKET_SCHEMA,
        "offer_id": OFFER_ID,
        "authority_receipt_sha256": auth["receipt_sha256"],
        "canonical_offer_source_sha256": auth["canonical_offer_source_sha256"],
        "canonical_terms_sha256": auth["canonical_terms_sha256"],
        "intake_receipt_sha256": intake_result["receipt_sha256"],
        "acceptance_receipt_sha256": acceptance["receipt_sha256"] if acceptance else SAFE_EVIDENCE_NONE,
        "state": state,
        "canonical_blocker": canonical_blocker or SAFE_EVIDENCE_NONE,
        "recovery_runtime_replay_required_for_production": True,
        "customer_acceptance_required": True,
        "customer_acceptance_is_external_event": True,
        "public_purchase_intent_is_not_payment": True,
        "payment_reference_is_not_acceptance": True,
        "metric_lift_is_not_acceptance": True,
        "rollback_evidence_is_required": True,
        "synthetic_mode_is_never_production_ready": True,
        "expansion_path": "same-GGUF $30k / 30d pilot only after real AT1-AT6 acceptance; license only after paid delivery",
        **AUTHORITY_FALSE,
    })


def verify_close_packet(packet: Any, repo_root: str | Path, intake: Any, evidence: Any | None = None) -> bool:
    if type(packet) is not dict:
        return False
    try:
        expected = compile_close_packet(repo_root, intake, evidence)
    except (ContractError, KeyError, TypeError, ValueError, OSError):
        return False
    return canonical_json(packet) == canonical_json(expected)
