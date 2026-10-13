#!/usr/bin/env python3
"""Deterministic evidence-only acceptance engine for Exeter CA RFP 2026-06.

Production semantics are closure-bound at import time. Exported compatibility constants are
informational only and may be rebound/mutated without widening acceptance semantics.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

INPUT_SCHEMA = "tjlabs.exeter_finance_acceptance/v2"
REPORT_SCHEMA = "tjlabs.exeter_finance_acceptance.report/v2"
AUTHORITY = "EVIDENCE_ONLY_NO_BUYER_OR_PRODUCTION_ACCEPTANCE"
MAX_INPUT_BYTES = 1_048_576
MAX_STRING = 512
MAX_ROWS = 10_000
MAX_SOURCE_AGE_SECONDS = 172_800
TOP_KEYS = {
    "schema", "as_of_utc", "source_pin", "generation", "crosswalks",
    "control_totals", "subledgers", "bank_reconciliation",
    "required_interfaces", "interfaces", "uat", "cutover",
}
CROSSWALK_KEYS = ("accounts", "vendors", "customers", "employees")
SUBLEDGER_KEYS = ("ap", "ar", "payroll", "utility", "cashiering")
REQUIRED_UAT = (
    "GL_FUND_ACCOUNTING", "AP", "AR", "PAYROLL", "CASHIERING",
    "BANK_RECONCILIATION", "UTILITY_BILLING", "FINANCIAL_REPORTING",
    "INTEGRATIONS", "DATA_CONVERSION",
)


class PacketError(ValueError):
    def __init__(self, code: str, path: str, detail: str = "") -> None:
        super().__init__(f"{code}:{path}:{detail}")
        self.code = code
        self.path = path
        self.detail = detail


def _build_api():
    input_schema = "tjlabs.exeter_finance_acceptance/v2"
    report_schema = "tjlabs.exeter_finance_acceptance.report/v2"
    authority = "EVIDENCE_ONLY_NO_BUYER_OR_PRODUCTION_ACCEPTANCE"
    max_input_bytes = 1_048_576
    max_string = 512
    max_rows = 10_000
    max_source_age_seconds = 172_800
    top_keys = frozenset({
        "schema", "as_of_utc", "source_pin", "generation", "crosswalks",
        "control_totals", "subledgers", "bank_reconciliation",
        "required_interfaces", "interfaces", "uat", "cutover",
    })
    crosswalk_keys = ("accounts", "vendors", "customers", "employees")
    subledger_keys = ("ap", "ar", "payroll", "utility", "cashiering")
    required_uat = (
        "GL_FUND_ACCOUNTING", "AP", "AR", "PAYROLL", "CASHIERING",
        "BANK_RECONCILIATION", "UTILITY_BILLING", "FINANCIAL_REPORTING",
        "INTEGRATIONS", "DATA_CONVERSION",
    )
    authority_bits = {
        "buyer_acceptance_authorized": False,
        "production_posting_authorized": False,
        "bank_action_authorized": False,
        "payment_authorized": False,
        "revenue_recognized": False,
    }
    qa_states = frozenset({
        "RECHECK_NOT_YET_DUE",
        "POSTED_AND_RETAINED",
        "NO_QA_ADDENDA_REQUIRED_CONFIRMED",
        "OFFICIAL_PAGE_RECHECKED_NO_POSTING",
    })

    error_cls = PacketError
    json_dumps = json.dumps
    json_loads = json.loads
    sha256_fn = hashlib.sha256
    re_fullmatch = re.fullmatch
    dt_fromiso = datetime.fromisoformat
    path_cls = Path

    def canonical(v: Any) -> str:
        return json_dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    def sha256_text(v: str) -> str:
        return sha256_fn(v.encode("utf-8")).hexdigest()

    def exact_dict(v: Any, keys: Iterable[str], path: str) -> dict[str, Any]:
        if type(v) is not dict:
            raise error_cls("TYPE_OBJECT_REQUIRED", path)
        expected = set(keys)
        actual = set(v)
        if actual != expected:
            raise error_cls(
                "OBJECT_KEYS_INVALID", path,
                f"missing={','.join(sorted(expected-actual))};extra={','.join(sorted(actual-expected))}",
            )
        return v

    def string(v: Any, path: str) -> str:
        if type(v) is not str:
            raise error_cls("TYPE_STRING_REQUIRED", path)
        if not v or len(v) > max_string:
            raise error_cls("STRING_BOUNDS_INVALID", path)
        if "\x00" in v:
            raise error_cls("STRING_NUL_FORBIDDEN", path)
        return v

    def digest(v: Any, path: str, allow_none: bool = False) -> str | None:
        if allow_none and v is None:
            return None
        s = string(v, path)
        if re_fullmatch(r"[0-9a-f]{64}", s) is None:
            raise error_cls("SHA256_INVALID", path)
        return s

    def integer(v: Any, path: str, minimum: int | None = None) -> int:
        if type(v) is not int:
            raise error_cls("TYPE_INTEGER_REQUIRED", path)
        if minimum is not None and v < minimum:
            raise error_cls("INTEGER_RANGE_INVALID", path)
        return v

    def boolean(v: Any, path: str) -> bool:
        if type(v) is not bool:
            raise error_cls("TYPE_BOOLEAN_REQUIRED", path)
        return v

    def array(v: Any, path: str, nonempty: bool = False) -> list[Any]:
        if type(v) is not list:
            raise error_cls("TYPE_ARRAY_REQUIRED", path)
        if len(v) > max_rows or (nonempty and not v):
            raise error_cls("ARRAY_BOUNDS_INVALID", path)
        return v

    def utc(v: Any, path: str):
        s = string(v, path)
        if not s.endswith("Z"):
            raise error_cls("UTC_TIMESTAMP_INVALID", path)
        try:
            dt = dt_fromiso(s[:-1] + "+00:00")
        except ValueError as exc:
            raise error_cls("UTC_TIMESTAMP_INVALID", path) from exc
        if dt.tzinfo is None or dt.utcoffset().total_seconds() != 0:
            raise error_cls("UTC_TIMESTAMP_INVALID", path)
        return dt

    def unique(rows: list[dict[str, Any]], path: str, key: str = "id") -> None:
        seen: set[str] = set()
        for i, row in enumerate(rows):
            ident = string(row[key], f"{path}[{i}].{key}")
            if ident in seen:
                raise error_cls("DUPLICATE_ID", f"{path}[{i}].{key}", ident)
            seen.add(ident)

    def exception(code: str, path: str, detail: str) -> dict[str, str]:
        ident = {"code": code, "path": path, "detail": detail}
        return {"id": sha256_text(canonical(ident))[:20], **ident}

    def validate(packet: Any) -> dict[str, Any]:
        b = exact_dict(packet, top_keys, "$")
        if b["schema"] != input_schema:
            raise error_cls("SCHEMA_INVALID", "$.schema")
        as_of = utc(b["as_of_utc"], "$.as_of_utc")

        source = exact_dict(
            b["source_pin"],
            (
                "ledger_sha256", "procurement_index_sha256", "rfp_sha256",
                "qa_addenda_sha256", "observed_at_utc", "qa_recheck_due_at_utc",
                "qa_addenda_state",
            ),
            "$.source_pin",
        )
        digest(source["ledger_sha256"], "$.source_pin.ledger_sha256")
        digest(source["procurement_index_sha256"], "$.source_pin.procurement_index_sha256")
        digest(source["rfp_sha256"], "$.source_pin.rfp_sha256")
        digest(source["qa_addenda_sha256"], "$.source_pin.qa_addenda_sha256", True)
        observed = utc(source["observed_at_utc"], "$.source_pin.observed_at_utc")
        utc(source["qa_recheck_due_at_utc"], "$.source_pin.qa_recheck_due_at_utc")
        qa_state = string(source["qa_addenda_state"], "$.source_pin.qa_addenda_state")
        if qa_state not in qa_states:
            raise error_cls("QA_ADDENDA_STATE_INVALID", "$.source_pin.qa_addenda_state")
        if observed > as_of:
            raise error_cls("SOURCE_OBSERVED_IN_FUTURE", "$.source_pin.observed_at_utc")

        g = exact_dict(b["generation"], ("source_sha256", "target_sha256"), "$.generation")
        digest(g["source_sha256"], "$.generation.source_sha256")
        digest(g["target_sha256"], "$.generation.target_sha256")

        cw = exact_dict(b["crosswalks"], crosswalk_keys, "$.crosswalks")
        for category in crosswalk_keys:
            rows = array(cw[category], f"$.crosswalks.{category}", True)
            seen: set[str] = set()
            for i, value in enumerate(rows):
                row = exact_dict(value, ("source_id", "target_id"), f"$.crosswalks.{category}[{i}]")
                source_id = string(row["source_id"], f"$.crosswalks.{category}[{i}].source_id")
                string(row["target_id"], f"$.crosswalks.{category}[{i}].target_id")
                if source_id in seen:
                    raise error_cls("DUPLICATE_SOURCE_ID", f"$.crosswalks.{category}[{i}].source_id", source_id)
                seen.add(source_id)

        controls = array(b["control_totals"], "$.control_totals", True)
        normalized_controls = []
        for i, value in enumerate(controls):
            row = exact_dict(
                value,
                ("id", "source_cents", "target_cents", "approved_delta_cents", "adjustment_sha256"),
                f"$.control_totals[{i}]",
            )
            string(row["id"], f"$.control_totals[{i}].id")
            integer(row["source_cents"], f"$.control_totals[{i}].source_cents")
            integer(row["target_cents"], f"$.control_totals[{i}].target_cents")
            integer(row["approved_delta_cents"], f"$.control_totals[{i}].approved_delta_cents")
            digest(row["adjustment_sha256"], f"$.control_totals[{i}].adjustment_sha256", True)
            normalized_controls.append(row)
        unique(normalized_controls, "$.control_totals")

        sl = exact_dict(b["subledgers"], subledger_keys, "$.subledgers")
        ledger_keys = (
            "control_id", "source_count", "target_count", "approved_count_delta",
            "source_cents", "target_cents", "approved_amount_delta_cents",
            "adjustment_sha256", "exceptions",
        )
        control_ids: set[str] = set()
        for name in subledger_keys:
            row = exact_dict(sl[name], ledger_keys, f"$.subledgers.{name}")
            control_id = string(row["control_id"], f"$.subledgers.{name}.control_id")
            if control_id in control_ids:
                raise error_cls("SUBLEDGER_CONTROL_ID_REUSED", f"$.subledgers.{name}.control_id", control_id)
            control_ids.add(control_id)
            integer(row["source_count"], f"$.subledgers.{name}.source_count", 0)
            integer(row["target_count"], f"$.subledgers.{name}.target_count", 0)
            integer(row["approved_count_delta"], f"$.subledgers.{name}.approved_count_delta")
            integer(row["source_cents"], f"$.subledgers.{name}.source_cents")
            integer(row["target_cents"], f"$.subledgers.{name}.target_cents")
            integer(row["approved_amount_delta_cents"], f"$.subledgers.{name}.approved_amount_delta_cents")
            digest(row["adjustment_sha256"], f"$.subledgers.{name}.adjustment_sha256", True)
            excs = array(row["exceptions"], f"$.subledgers.{name}.exceptions")
            seen: set[str] = set()
            for i, v in enumerate(excs):
                ident = string(v, f"$.subledgers.{name}.exceptions[{i}]")
                if ident in seen:
                    raise error_cls("DUPLICATE_EXCEPTION_ID", f"$.subledgers.{name}.exceptions[{i}]", ident)
                seen.add(ident)

        bank = exact_dict(
            b["bank_reconciliation"],
            (
                "statement_ending_cents", "statement_additions_cents", "statement_deductions_cents",
                "book_ending_cents", "book_additions_cents", "book_deductions_cents", "reconciled_cents",
            ),
            "$.bank_reconciliation",
        )
        for key in ("statement_ending_cents", "book_ending_cents", "reconciled_cents"):
            integer(bank[key], f"$.bank_reconciliation.{key}")
        for key in ("statement_additions_cents", "statement_deductions_cents", "book_additions_cents", "book_deductions_cents"):
            integer(bank[key], f"$.bank_reconciliation.{key}", 0)

        required = array(b["required_interfaces"], "$.required_interfaces", True)
        seen: set[str] = set()
        for i, v in enumerate(required):
            ident = string(v, f"$.required_interfaces[{i}]")
            if ident in seen:
                raise error_cls("DUPLICATE_REQUIRED_INTERFACE", f"$.required_interfaces[{i}]", ident)
            seen.add(ident)

        interfaces = array(b["interfaces"], "$.interfaces")
        normalized_interfaces = []
        for i, v in enumerate(interfaces):
            row = exact_dict(v, ("id", "source", "target", "manifest_sha256", "status"), f"$.interfaces[{i}]")
            for key in ("id", "source", "target", "status"):
                string(row[key], f"$.interfaces[{i}].{key}")
            digest(row["manifest_sha256"], f"$.interfaces[{i}].manifest_sha256")
            normalized_interfaces.append(row)
        unique(normalized_interfaces, "$.interfaces")

        uat = array(b["uat"], "$.uat")
        normalized_uat = []
        for i, v in enumerate(uat):
            row = exact_dict(v, ("id", "mandatory", "status", "evidence_sha256"), f"$.uat[{i}]")
            string(row["id"], f"$.uat[{i}].id")
            boolean(row["mandatory"], f"$.uat[{i}].mandatory")
            string(row["status"], f"$.uat[{i}].status")
            digest(row["evidence_sha256"], f"$.uat[{i}].evidence_sha256")
            normalized_uat.append(row)
        unique(normalized_uat, "$.uat")

        cut = exact_dict(
            b["cutover"],
            ("source_freeze_sha256", "rollback_receipt_sha256", "replay_receipt_sha256", "unresolved_exceptions"),
            "$.cutover",
        )
        for key in ("source_freeze_sha256", "rollback_receipt_sha256", "replay_receipt_sha256"):
            digest(cut[key], f"$.cutover.{key}")
        seen = set()
        for i, v in enumerate(array(cut["unresolved_exceptions"], "$.cutover.unresolved_exceptions")):
            ident = string(v, f"$.cutover.unresolved_exceptions[{i}]")
            if ident in seen:
                raise error_cls("DUPLICATE_EXCEPTION_ID", f"$.cutover.unresolved_exceptions[{i}]", ident)
            seen.add(ident)
        return b

    def evaluate_impl(packet: Any) -> dict[str, Any]:
        b = validate(packet)
        failures: list[dict[str, str]] = []

        as_of = utc(b["as_of_utc"], "$.as_of_utc")
        source = b["source_pin"]
        observed = utc(source["observed_at_utc"], "$.source_pin.observed_at_utc")
        qa_recheck_due = utc(source["qa_recheck_due_at_utc"], "$.source_pin.qa_recheck_due_at_utc")
        age_seconds = int((as_of - observed).total_seconds())
        if age_seconds > max_source_age_seconds:
            failures.append(exception("SOURCE_PIN_STALE", "$.source_pin.observed_at_utc", str(age_seconds)))
        state = source["qa_addenda_state"]
        qa_digest = source["qa_addenda_sha256"]
        if state == "POSTED_AND_RETAINED":
            if qa_digest is None:
                failures.append(exception("QA_ADDENDA_DIGEST_MISSING", "$.source_pin.qa_addenda_sha256", state))
        elif state == "NO_QA_ADDENDA_REQUIRED_CONFIRMED":
            if qa_digest is None:
                failures.append(exception("QA_NO_ADDENDA_CONFIRMATION_MISSING", "$.source_pin.qa_addenda_sha256", state))
        elif state == "RECHECK_NOT_YET_DUE":
            if as_of >= qa_recheck_due:
                failures.append(exception("QA_RECHECK_REQUIRED", "$.source_pin.qa_addenda_state", state))
        elif state == "OFFICIAL_PAGE_RECHECKED_NO_POSTING":
            failures.append(exception("QA_PUBLICATION_UNRESOLVED", "$.source_pin.qa_addenda_state", state))

        controls = {row["id"]: row for row in b["control_totals"]}
        for i, row in enumerate(b["control_totals"]):
            control_delta = row["target_cents"] - row["source_cents"]
            approved_delta = row["approved_delta_cents"]
            if control_delta != approved_delta:
                failures.append(exception("CONTROL_TOTAL_DELTA_MISMATCH", f"$.control_totals[{i}]", row["id"]))
            if approved_delta != 0 and row["adjustment_sha256"] is None:
                failures.append(exception("CONTROL_ADJUSTMENT_EVIDENCE_MISSING", f"$.control_totals[{i}]", row["id"]))
            if approved_delta == 0 and row["adjustment_sha256"] is not None:
                failures.append(exception("CONTROL_UNNEEDED_ADJUSTMENT_EVIDENCE", f"$.control_totals[{i}]", row["id"]))

        for name in subledger_keys:
            row = b["subledgers"][name]
            count_delta = row["target_count"] - row["source_count"]
            amount_delta = row["target_cents"] - row["source_cents"]
            if count_delta != row["approved_count_delta"]:
                failures.append(exception("SUBLEDGER_COUNT_DELTA_MISMATCH", f"$.subledgers.{name}", name))
            if amount_delta != row["approved_amount_delta_cents"]:
                failures.append(exception("SUBLEDGER_AMOUNT_DELTA_MISMATCH", f"$.subledgers.{name}", name))
            approved = row["approved_count_delta"] != 0 or row["approved_amount_delta_cents"] != 0
            if approved and row["adjustment_sha256"] is None:
                failures.append(exception("ADJUSTMENT_EVIDENCE_MISSING", f"$.subledgers.{name}", name))
            if not approved and row["adjustment_sha256"] is not None:
                failures.append(exception("UNNEEDED_ADJUSTMENT_EVIDENCE", f"$.subledgers.{name}", name))
            for exc in row["exceptions"]:
                failures.append(exception("SUBLEDGER_EXCEPTION_OPEN", f"$.subledgers.{name}.exceptions", exc))
            control = controls.get(row["control_id"])
            if control is None:
                failures.append(exception("SUBLEDGER_CONTROL_MISSING", f"$.subledgers.{name}.control_id", row["control_id"]))
            else:
                if control["source_cents"] != row["source_cents"]:
                    failures.append(exception("SUBLEDGER_SOURCE_GL_MISMATCH", f"$.subledgers.{name}", row["control_id"]))
                if control["target_cents"] != row["target_cents"]:
                    failures.append(exception("SUBLEDGER_TARGET_GL_MISMATCH", f"$.subledgers.{name}", row["control_id"]))
                if control["approved_delta_cents"] != row["approved_amount_delta_cents"]:
                    failures.append(exception("SUBLEDGER_GL_APPROVED_DELTA_MISMATCH", f"$.subledgers.{name}", row["control_id"]))
                if control["adjustment_sha256"] != row["adjustment_sha256"]:
                    failures.append(exception("SUBLEDGER_GL_ADJUSTMENT_EVIDENCE_MISMATCH", f"$.subledgers.{name}", row["control_id"]))

        bank = b["bank_reconciliation"]
        statement = bank["statement_ending_cents"] + bank["statement_additions_cents"] - bank["statement_deductions_cents"]
        book = bank["book_ending_cents"] + bank["book_additions_cents"] - bank["book_deductions_cents"]
        rec = bank["reconciled_cents"]
        if statement != rec:
            failures.append(exception("BANK_STATEMENT_RECON_MISMATCH", "$.bank_reconciliation", str(statement)))
        if book != rec:
            failures.append(exception("BANK_BOOK_RECON_MISMATCH", "$.bank_reconciliation", str(book)))

        by_interface = {row["id"]: row for row in b["interfaces"]}
        for required_id in b["required_interfaces"]:
            row = by_interface.get(required_id)
            if row is None:
                failures.append(exception("REQUIRED_INTERFACE_MISSING", "$.interfaces", required_id))
            elif row["status"] != "verified":
                failures.append(exception("INTERFACE_NOT_VERIFIED", f"$.interfaces[{required_id}]", row["status"]))

        by_uat = {row["id"]: row for row in b["uat"]}
        for required_id in required_uat:
            row = by_uat.get(required_id)
            if row is None:
                failures.append(exception("REQUIRED_UAT_MISSING", "$.uat", required_id))
                continue
            if row["mandatory"] is not True:
                failures.append(exception("REQUIRED_UAT_NOT_MANDATORY", f"$.uat[{required_id}]", required_id))
            if row["status"] != "pass":
                failures.append(exception("MANDATORY_UAT_NOT_PASS", f"$.uat[{required_id}]", row["status"]))
        for row in b["uat"]:
            if row["mandatory"] and row["status"] != "pass" and row["id"] not in required_uat:
                failures.append(exception("MANDATORY_UAT_NOT_PASS", f"$.uat[{row['id']}]", row["status"]))

        for exc in b["cutover"]["unresolved_exceptions"]:
            failures.append(exception("CUTOVER_EXCEPTION_OPEN", "$.cutover.unresolved_exceptions", exc))

        failures.sort(key=lambda x: (x["code"], x["path"], x["detail"], x["id"]))
        ready = not failures
        return {
            "schema": report_schema,
            "authority": authority,
            **authority_bits,
            "packet_sha256": sha256_text(canonical(b)),
            "status": "READY" if ready else "HOLD",
            "ready": ready,
            "exception_count": len(failures),
            "exceptions": failures,
        }

    evaluate_generation = evaluate_impl

    def verify_report_impl(report: Any, packet: Any) -> bool:
        if type(report) is not dict:
            return False
        try:
            expected = evaluate_generation(packet)
        except error_cls:
            return False
        return canonical(report) == canonical(expected)

    def strict_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in pairs:
            if key in out:
                raise error_cls("DUPLICATE_JSON_KEY", "$", key)
            out[key] = value
        return out

    def load_packet_impl(path: str | os.PathLike[str]) -> dict[str, Any]:
        try:
            raw = path_cls(path).read_bytes()
        except OSError as exc:
            raise error_cls("INPUT_UNREADABLE", "$", type(exc).__name__) from exc
        if len(raw) > max_input_bytes:
            raise error_cls("INPUT_TOO_LARGE", "$", str(len(raw)))
        try:
            text = raw.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise error_cls("INPUT_UTF8_INVALID", "$") from exc
        try:
            value = json_loads(
                text,
                object_pairs_hook=strict_pairs,
                parse_constant=lambda _: (_ for _ in ()).throw(error_cls("NONFINITE_JSON_NUMBER", "$")),
            )
        except error_cls:
            raise
        except (json.JSONDecodeError, RecursionError, ValueError) as exc:
            raise error_cls("INPUT_JSON_INVALID", "$") from exc
        if type(value) is not dict:
            raise error_cls("TYPE_OBJECT_REQUIRED", "$")
        return value

    def error_receipt(error: PacketError) -> str:
        return canonical({
            "schema": "tjlabs.exeter_finance_acceptance.error/v2",
            "authority": authority, "code": error.code, "path": error.path,
        })

    load_generation = load_packet_impl

    def main_impl(argv: list[str] | None = None) -> int:
        args = sys.argv[1:] if argv is None else argv
        if len(args) == 1:
            try:
                report = evaluate_generation(load_generation(args[0]))
            except error_cls as error:
                sys.stderr.write(error_receipt(error) + "\n")
                return 64
            sys.stdout.write(canonical(report) + "\n")
            return 0 if report["ready"] else 2
        if len(args) == 3 and args[0] == "--verify":
            try:
                report_obj = load_generation(args[1])
                packet_obj = load_generation(args[2])
            except error_cls as error:
                sys.stderr.write(error_receipt(error) + "\n")
                return 64
            ok = verify_report_impl(report_obj, packet_obj)
            sys.stdout.write(canonical({
                "schema": "tjlabs.exeter_finance_acceptance.verify/v1", "valid": ok
            }) + "\n")
            return 0 if ok else 3
        sys.stderr.write(canonical({
            "schema": "tjlabs.exeter_finance_acceptance.error/v2",
            "authority": authority, "code": "USAGE", "path": "$",
        }) + "\n")
        return 64

    return evaluate_generation, verify_report_impl, load_generation, main_impl


evaluate, verify_report, load_packet, main = _build_api()

if __name__ == "__main__":
    raise SystemExit(main())
