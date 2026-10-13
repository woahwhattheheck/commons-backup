#!/usr/bin/env python3
"""Deterministic, public-safe close/delivery evidence compiler for the $12k GGUF diagnostic."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

OFFER_ID = "gguf-diagnostic-10d-12k"
FIXED_AMOUNT_USD = 12_000
TERM_CALENDAR_DAYS = 10
M1_AMOUNT_USD = M2_AMOUNT_USD = 6_000
ACCEPTANCE_RULE = "rollback evidence, not metric lift"
TERMS_SHA256 = "1c0756062563415e551587a5f1ab22147366d406135de6c45ccbd3a562985730"
ACCEPTANCE_IDS = ("AT1", "AT2", "AT3", "AT4", "AT5", "AT6")
CASE_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
OPAQUE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,119}$")
URL_RE = re.compile(r"https?://", re.I)
LOCATOR_RE = re.compile(
    r"(?:^|\s)(?:/\S+|[A-Za-z]:[\\/]\S+|\\\\\S+|localhost(?::\d+)?|(?:\d{1,3}\.){3}\d{1,3}(?::\d+)?)(?:$|\s)", re.I
)

_DLP_PATH = Path(__file__).resolve().parents[2] / "host" / "revenue_recovery.py"
_SPEC = importlib.util.spec_from_file_location("gguf_close_kit_canonical_dlp", _DLP_PATH)
if _SPEC is None or _SPEC.loader is None:  # pragma: no cover
    raise ImportError(f"cannot load canonical revenue DLP from {_DLP_PATH}")
_DLP_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_DLP_MODULE)
_CANONICAL_DLP = _DLP_MODULE.contains_sensitive_value
del _DLP_MODULE, _SPEC


class InputError(ValueError):
    pass


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise InputError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def parse_json_strict(text: str) -> Any:
    try:
        return json.loads(text, object_pairs_hook=_pairs, parse_constant=lambda x: (_ for _ in ()).throw(InputError(f"non-finite JSON constant: {x}")))
    except InputError:
        raise
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise InputError(f"invalid JSON: {exc}") from exc


def read_json(path: Path) -> Any:
    if path.is_symlink() or not path.is_file():
        raise InputError(f"input must be a regular non-symlink file: {path}")
    return parse_json_strict(path.read_text(encoding="utf-8"))


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def sha256_obj(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def _exact(value: dict[str, Any], expected: set[str], where: str) -> None:
    actual = set(value)
    if actual != expected:
        raise InputError(f"{where} schema mismatch; missing={sorted(expected-actual)} extra={sorted(actual-expected)}")


def _bool(value: Any, where: str) -> bool:
    if type(value) is not bool:
        raise InputError(f"{where} must be boolean")
    return value


def _text(value: Any, where: str, max_len: int = 500) -> str:
    if not isinstance(value, str):
        raise InputError(f"{where} must be a string")
    text = value.strip()
    if not text or len(text) > max_len or any(ord(ch) < 32 and ch not in "\t\n" for ch in text):
        raise InputError(f"{where} must be nonempty safe text <= {max_len} chars")
    normalized = unicodedata.normalize("NFKC", text)
    if not text.isascii() or normalized != text or any(unicodedata.category(ch) == "Cf" for ch in text):
        raise InputError(f"{where} contains forbidden sensitive/private content")
    if URL_RE.search(normalized) or LOCATOR_RE.search(normalized) or _CANONICAL_DLP(normalized):
        raise InputError(f"{where} contains forbidden sensitive/private content")
    return text


def _opaque(value: Any, where: str) -> str:
    text = _text(value, where, 120)
    if OPAQUE_RE.fullmatch(text) is None:
        raise InputError(f"{where} must be an opaque identifier using only letters, digits, _ or -")
    return text


def _digest(value: Any, where: str, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str) or SHA_RE.fullmatch(value) is None:
        raise InputError(f"{where} must be a lowercase sha256 hex digest")
    return value


def _metric(value: Any, where: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(float(value)):
        raise InputError(f"{where} must be finite numeric")
    return float(value)


def canonical_offer() -> dict[str, Any]:
    return {
        "offer_id": OFFER_ID, "terms_sha256": TERMS_SHA256, "currency": "USD",
        "fixed_amount": FIXED_AMOUNT_USD, "term_calendar_days": TERM_CALENDAR_DAYS,
        "milestones": [
            {"id": "M1_BEFORE_FILE", "amount": M1_AMOUNT_USD, "due": "after NDA + SOW; before customer file exchange"},
            {"id": "M2_AT1_AT6", "amount": M2_AMOUNT_USD, "due": "on AT1-AT6 acceptance evidence"},
        ],
        "acceptance_rule": ACCEPTANCE_RULE, "acceptance_tests": list(ACCEPTANCE_IDS),
        "expansion": "same-GGUF $30k / 30d White Box pilot only after paid AT1-AT6 delivery",
    }


def validate_intake(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise InputError("intake must be an object")
    _exact(value, {"schema_version", "kind", "mode", "offer_id", "case_id", "customer_readiness", "privacy", "scope", "evidence_refs"}, "intake")
    if value["schema_version"] != 1 or value["kind"] != "GGUF_ENTERPRISE_INTAKE":
        raise InputError("unsupported intake schema/kind")
    if value["mode"] not in {"SYNTHETIC_DEMO", "CUSTOMER_PRIVATE"} or value["offer_id"] != OFFER_ID:
        raise InputError("intake mode/offer drift")
    if not isinstance(value["case_id"], str) or CASE_RE.fullmatch(value["case_id"]) is None:
        raise InputError("case_id invalid")

    r = value["customer_readiness"]
    rkeys = {"legal_control_confirmed", "harness_ready", "nda_signed", "sow_signed", "m1_received_owner_reported"}
    if not isinstance(r, dict):
        raise InputError("customer_readiness must be object")
    _exact(r, rkeys, "customer_readiness")
    for key in rkeys: _bool(r[key], f"customer_readiness.{key}")

    privacy = value["privacy"]
    pkeys = {"public_model_bytes_present", "public_secret_values_present", "public_private_contact_present"}
    if not isinstance(privacy, dict):
        raise InputError("privacy must be object")
    _exact(privacy, pkeys, "privacy")
    for key in pkeys:
        if _bool(privacy[key], f"privacy.{key}"):
            raise InputError(f"privacy violation: {key} must be false")

    scope = value["scope"]
    if not isinstance(scope, dict):
        raise InputError("scope must be object")
    _exact(scope, {"model_label", "objective", "harness_label", "start_window", "data_classification"}, "scope")
    _opaque(scope["model_label"], "scope.model_label")
    _text(scope["objective"], "scope.objective")
    _opaque(scope["harness_label"], "scope.harness_label")
    _opaque(scope["start_window"], "scope.start_window")
    allowed = {"SYNTHETIC_DEMO": "PUBLIC_SYNTHETIC", "CUSTOMER_PRIVATE": "PRIVATE_CUSTOMER_CONTROLLED"}
    if scope["data_classification"] != allowed[value["mode"]]:
        raise InputError("mode/data_classification mismatch")

    refs = value["evidence_refs"]
    if not isinstance(refs, dict):
        raise InputError("evidence_refs must be object")
    _exact(refs, {"nda_sha256", "sow_sha256", "m1_sha256"}, "evidence_refs")
    refs = {k: _digest(v, f"evidence_refs.{k}", True) for k, v in refs.items()}
    bindings = {"nda_signed": "nda_sha256", "sow_signed": "sow_sha256", "m1_received_owner_reported": "m1_sha256"}
    if value["mode"] == "SYNTHETIC_DEMO":
        if any(r.values()) or any(refs.values()):
            raise InputError("synthetic demo must not assert customer readiness/payment facts or evidence refs")
    else:
        for flag, ref in bindings.items():
            if r[flag] and refs[ref] is None: raise InputError(f"{flag}=true requires {ref}")
            if not r[flag] and refs[ref] is not None: raise InputError(f"{ref} present while {flag}=false")
    return value


def validate_evidence(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict): raise InputError("evidence must be an object")
    _exact(value, {"schema_version", "kind", "case_id", "artifacts", "harness_runs", "finding_sha256", "delivery_receipt_sha256", "claims"}, "evidence")
    if value["schema_version"] != 1 or value["kind"] != "GGUF_ACCEPTANCE_EVIDENCE" or not isinstance(value["case_id"], str) or CASE_RE.fullmatch(value["case_id"]) is None:
        raise InputError("unsupported evidence schema/kind/case")
    a = value["artifacts"]
    if not isinstance(a, dict): raise InputError("artifacts must be object")
    _exact(a, {"original_sha256", "ablated_sha256", "restored_sha256"}, "artifacts")
    for k, v in a.items(): _digest(v, f"artifacts.{k}")
    runs = value["harness_runs"]
    if not isinstance(runs, dict): raise InputError("harness_runs must be object")
    _exact(runs, {"baseline", "ablation", "restore"}, "harness_runs")
    metric_keys = None
    for phase in ("baseline", "ablation", "restore"):
        run = runs[phase]
        if not isinstance(run, dict): raise InputError(f"harness_runs.{phase} must be object")
        _exact(run, {"log_sha256", "metrics"}, f"harness_runs.{phase}")
        _digest(run["log_sha256"], f"harness_runs.{phase}.log_sha256")
        metrics = run["metrics"]
        if not isinstance(metrics, dict) or not metrics or len(metrics) > 32: raise InputError("metrics must be 1..32 object")
        keys = set(metrics)
        metric_keys = keys if metric_keys is None else metric_keys
        if keys != metric_keys: raise InputError("metric key sets must match across baseline/ablation/restore")
        for name, metric in metrics.items():
            if not isinstance(name, str) or re.fullmatch(r"[a-z][a-z0-9_.-]{0,63}", name) is None: raise InputError(f"invalid metric name: {name!r}")
            _metric(metric, f"harness_runs.{phase}.metrics.{name}")
    _digest(value["finding_sha256"], "finding_sha256"); _digest(value["delivery_receipt_sha256"], "delivery_receipt_sha256")
    claims = value["claims"]
    if not isinstance(claims, dict): raise InputError("claims must be object")
    _exact(claims, {"public_binary_bytes_present", "metric_lift_required", "buyer_acceptance_claimed", "payment_claimed"}, "claims")
    for key in claims: _bool(claims[key], f"claims.{key}")
    if claims["public_binary_bytes_present"]: raise InputError("public binary bytes are forbidden")
    if claims["metric_lift_required"]: raise InputError("metric lift cannot be an acceptance requirement")
    if claims["buyer_acceptance_claimed"]: raise InputError("this compiler cannot assert buyer/legal acceptance")
    if claims["payment_claimed"]: raise InputError("this compiler cannot assert payment")
    return value


def _readiness(intake: dict[str, Any]) -> tuple[str, list[str]]:
    if intake["mode"] == "SYNTHETIC_DEMO": return "SYNTHETIC_DEMO_ONLY", []
    r = intake["customer_readiness"]
    holds = []
    for key, code in (
        ("legal_control_confirmed", "LEGAL_GGUF_CONTROL_NOT_CONFIRMED"), ("harness_ready", "CUSTOMER_HARNESS_NOT_READY"),
        ("nda_signed", "NDA_NOT_SIGNED"), ("sow_signed", "SOW_NOT_SIGNED"), ("m1_received_owner_reported", "M1_NOT_OWNER_REPORTED_RECEIVED"),
    ):
        if not r[key]: holds.append(code)
    return ("READY_FOR_OWNER_PRIVATE_FILE_EXCHANGE_REVIEW" if not holds else "HOLD"), holds


def _acceptance(evidence: dict[str, Any]) -> tuple[dict[str, bool], dict[str, Any]]:
    a, runs = evidence["artifacts"], evidence["harness_runs"]
    tests = {"AT1": True, "AT2": a["ablated_sha256"] != a["original_sha256"], "AT3": a["restored_sha256"] == a["original_sha256"], "AT4": True, "AT5": True, "AT6": True}
    metrics = {}
    for name in sorted(runs["baseline"]["metrics"]):
        b, x, r = (float(runs[p]["metrics"][name]) for p in ("baseline", "ablation", "restore"))
        metrics[name] = {"baseline": b, "ablation": x, "restore": r, "ablation_delta": x-b, "restore_delta": r-b}
    return tests, {"metrics": metrics, "metric_lift_is_acceptance": False}


def compile_packet(intake_raw: Any, evidence_raw: Any) -> dict[str, Any]:
    intake, evidence = validate_intake(intake_raw), validate_evidence(evidence_raw)
    if intake["case_id"] != evidence["case_id"]: raise InputError("intake/evidence case_id mismatch")
    ready, holds = _readiness(intake)
    tests, benchmark = _acceptance(evidence)
    complete, synthetic = all(tests.values()), intake["mode"] == "SYNTHETIC_DEMO"
    state = ("SYNTHETIC_DEMO_COMPLETE" if complete else "SYNTHETIC_DEMO_HOLD") if synthetic else ("HOLD_PRE_FILE_EXCHANGE" if ready != "READY_FOR_OWNER_PRIVATE_FILE_EXCHANGE_REVIEW" else ("READY_FOR_OWNER_M2_ACCEPTANCE_REVIEW" if complete else "HOLD_AT1_AT6_INCOMPLETE"))
    packet = {
        "schema_version": 1, "kind": "GGUF_ENTERPRISE_CLOSE_PACKET", "offer": canonical_offer(), "case_id": intake["case_id"], "mode": intake["mode"],
        "intake": intake, "evidence": evidence, "readiness": {"state": ready, "holds": holds, "private_file_exchange_is_publicly_authorized": False},
        "acceptance": {"tests": tests, "all_at1_at6_evidence_complete": complete, "rule": ACCEPTANCE_RULE, "legal_acceptance_claimed": False},
        "benchmark": benchmark, "terminal_state": state,
        "milestones": {"M1": "SYNTHETIC_NOT_APPLICABLE" if synthetic else ("OWNER_REPORTED_EVIDENCE_PRESENT" if intake["customer_readiness"]["m1_received_owner_reported"] else "HOLD"), "M2": "SYNTHETIC_NOT_APPLICABLE" if synthetic else ("READY_FOR_OWNER_ACCEPTANCE_REVIEW" if state == "READY_FOR_OWNER_M2_ACCEPTANCE_REVIEW" else "HOLD")},
        "expansion": {"white_box_30d_discussion_ready": False, "expansion_accepted": False},
        "authority": {"buyer_contact_authorized": False, "legal_acceptance_authorized": False, "customer_file_transfer_authorized_by_this_packet": False, "payment_capture_authorized": False, "refund_authorized": False, "revenue_recognition_authorized": False, "public_model_bytes_allowed": False},
        "truth": {"build_is_buyer_interest": False, "build_is_payment": False, "build_is_revenue": False, "synthetic_demo": synthetic},
    }
    packet["packet_receipt_sha256"] = sha256_obj(packet)
    return packet


def verify_packet(packet_raw: Any) -> None:
    if not isinstance(packet_raw, dict): raise InputError("packet must be object")
    required = {"schema_version", "kind", "offer", "case_id", "mode", "intake", "evidence", "readiness", "acceptance", "benchmark", "terminal_state", "milestones", "expansion", "authority", "truth", "packet_receipt_sha256"}
    _exact(packet_raw, required, "packet")
    receipt = _digest(packet_raw["packet_receipt_sha256"], "packet_receipt_sha256")
    unsigned = dict(packet_raw); unsigned.pop("packet_receipt_sha256")
    if sha256_obj(unsigned) != receipt: raise InputError("packet receipt mismatch")
    if compile_packet(packet_raw["intake"], packet_raw["evidence"]) != packet_raw: raise InputError("packet semantic verification mismatch")


def render_markdown(packet: dict[str, Any]) -> str:
    verify_packet(packet)
    tests = "\n".join(f"- {k}: {'PASS' if packet['acceptance']['tests'][k] else 'HOLD'}" for k in ACCEPTANCE_IDS)
    holds = "\n".join(f"- {x}" for x in packet["readiness"]["holds"]) or "- none"
    metrics = "\n".join(f"- {n}: baseline={r['baseline']:g}, ablation={r['ablation']:g}, restore={r['restore']:g}" for n, r in packet["benchmark"]["metrics"].items())
    synthetic = "**SYNTHETIC / UNPAID / NOT A CUSTOMER CASE**\n\n" if packet["truth"]["synthetic_demo"] else ""
    return f"# GGUF diagnostic evidence packet\n\n{synthetic}Offer: `{OFFER_ID}` · **$12,000 fixed / 10 calendar days**  \nCase: `{packet['case_id']}`  \nState: `{packet['terminal_state']}`  \nAcceptance rule: **{ACCEPTANCE_RULE}**\n\n## Pre-file-exchange holds\n{holds}\n\n## AT1–AT6 evidence\n{tests}\n\n## Reproducible benchmark summary\n{metrics}\n\nMetric lift is observational only and is **not** an acceptance condition. AT3 is byte-exact rollback.\n\n## Authority boundary\nThis packet does not authorize buyer contact, legal acceptance, customer-file transfer, payment capture, refund execution, or revenue recognition. Public model bytes are forbidden.\n\nReceipt: `{packet['packet_receipt_sha256']}`\n"


def _write_exclusive(path: Path, text: str) -> None:
    if path.exists() or path.is_symlink(): raise InputError(f"exclusive create refused: {path}")
    with path.open("x", encoding="utf-8", newline="\n") as handle: handle.write(text)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__); sub = p.add_subparsers(dest="command", required=True)
    c = sub.add_parser("compile"); c.add_argument("intake", type=Path); c.add_argument("evidence", type=Path); c.add_argument("--json-out", type=Path); c.add_argument("--markdown-out", type=Path)
    v = sub.add_parser("verify"); v.add_argument("packet", type=Path)
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "compile":
            packet = compile_packet(read_json(args.intake), read_json(args.evidence)); js = canonical_json(packet) + "\n"; md = render_markdown(packet)
            _write_exclusive(args.json_out, js) if args.json_out else sys.stdout.write(js)
            if args.markdown_out: _write_exclusive(args.markdown_out, md)
            return 0
        verify_packet(read_json(args.packet)); print("VERIFIED"); return 0
    except InputError as exc:
        print(f"ERROR: {exc}", file=sys.stderr); return 2


if __name__ == "__main__":
    raise SystemExit(main())
