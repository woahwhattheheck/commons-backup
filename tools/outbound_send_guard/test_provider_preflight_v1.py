from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("provider_preflight_v1.py")
spec = importlib.util.spec_from_file_location("provider_preflight_v1", MODULE_PATH)
guard = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = guard
spec.loader.exec_module(guard)

NOW = "2026-09-16T14:30:00Z"


def h(ch: str) -> str:
    return ch * 64


def base_snapshot() -> dict:
    return {
        "schema_version": "outbound-provider-preflight-snapshot/v1",
        "as_of_utc": NOW,
        "ledger_complete": True,
        "request": {
            "schema_version": "outbound-provider-preflight-request/v1",
            "publication_key": h("a"),
            "candidate_sha256": h("b"),
            "intent_sha256": h("c"),
            "buyer_scope_sha256": h("d"),
            "recipient_fingerprint": h("e"),
            "route_kind": "EMAIL",
            "operation_id": "OP-ACME-20260916",
            "prepared_at": "2026-09-16T14:20:00Z",
        },
        "send_receipts": [],
        "dnr_receipts": [],
        "source_observations": [h("f"), h("1")],
    }


def base_authority(snapshot: dict | None = None) -> dict:
    s = snapshot if snapshot is not None else base_snapshot()
    return {
        "schema_version": "outbound-provider-preflight-retained-authority/v1",
        "observed_at_utc": s["as_of_utc"],
        "ledger_complete": s["ledger_complete"],
        "send_receipts": deepcopy(s["send_receipts"]),
        "dnr_receipts": deepcopy(s["dnr_receipts"]),
    }


def compile(snapshot: dict, authority: dict | None = None, now_utc: str = NOW):
    if authority is None:
        authority = base_authority(snapshot)
    return guard.compile_report(snapshot, authority, now_utc=now_utc)


def send_receipt(**updates) -> dict:
    row = {
        "provider": "GMAIL",
        "provider_message_id": "gmail:msg-001",
        "sent_at": "2026-09-16T14:25:00Z",
        "publication_key": h("a"),
        "candidate_sha256": h("b"),
        "intent_sha256": h("c"),
        "buyer_scope_sha256": h("d"),
        "recipient_fingerprint": h("e"),
        "route_kind": "EMAIL",
        "operation_id": "OP-ACME-20260916",
    }
    row.update(updates)
    return row


def dnr_receipt(**updates) -> dict:
    row = {
        "provider_ref": "slack:dnr:001",
        "observed_at": "2026-09-16T14:22:00Z",
        "buyer_scope_sha256": h("d"),
        "recipient_fingerprint": h("e"),
        "route_kind": "EMAIL",
        "reason_code": "HARD_NEGATIVE",
    }
    row.update(updates)
    return row


class ProviderPreflightTests(unittest.TestCase):
    def test_clear_for_muse_preflight(self):
        report = compile(base_snapshot())
        self.assertEqual(report["payload"]["result"], "CLEAR_FOR_MUSE_PREFLIGHT")
        self.assertTrue(report["payload"]["operationallyCurrent"])
        self.assertFalse(report["payload"]["authorities"]["externalSendAuthorized"])
        self.assertTrue(report["payload"]["requiresCanonicalMuseElectionV2"])
        self.assertTrue(guard.verify_report(base_snapshot(), base_authority(), report, now_utc=NOW)["valid"])

    def test_exact_intent_send_holds(self):
        s = base_snapshot(); s["send_receipts"] = [send_receipt()]
        r = compile(s)["payload"]
        self.assertEqual(r["result"], "HOLD_EXACT_INTENT_ALREADY_SENT")
        self.assertEqual(r["evidence"]["providerMessageId"], "gmail:msg-001")

    def test_same_publication_different_candidate_holds(self):
        s = base_snapshot(); s["send_receipts"] = [send_receipt(candidate_sha256=h("9"), intent_sha256=h("8"), operation_id="OP-OTHER")]
        self.assertEqual(compile(s)["payload"]["result"], "HOLD_PUBLICATION_ALREADY_SENT")

    def test_unrelated_publication_does_not_hold(self):
        s = base_snapshot(); s["send_receipts"] = [send_receipt(publication_key=h("9"), candidate_sha256=h("9"), intent_sha256=h("8"), buyer_scope_sha256=h("7"), recipient_fingerprint=h("6"), operation_id="OP-OTHER")]
        self.assertEqual(compile(s)["payload"]["result"], "CLEAR_FOR_MUSE_PREFLIGHT")

    def test_matching_dnr_holds(self):
        s = base_snapshot(); s["dnr_receipts"] = [dnr_receipt()]
        r = compile(s)["payload"]
        self.assertEqual(r["result"], "HOLD_AFTER_DNR")
        self.assertEqual(r["evidence"]["providerRef"], "slack:dnr:001")

    def test_dnr_stronger_than_exact_send(self):
        s = base_snapshot(); s["dnr_receipts"] = [dnr_receipt()]; s["send_receipts"] = [send_receipt()]
        self.assertEqual(compile(s)["payload"]["result"], "HOLD_AFTER_DNR")

    def test_dnr_other_recipient_does_not_hold(self):
        s = base_snapshot(); s["dnr_receipts"] = [dnr_receipt(recipient_fingerprint=h("9"))]
        self.assertEqual(compile(s)["payload"]["result"], "CLEAR_FOR_MUSE_PREFLIGHT")

    def test_dnr_other_buyer_does_not_hold(self):
        s = base_snapshot(); s["dnr_receipts"] = [dnr_receipt(buyer_scope_sha256=h("9"))]
        self.assertEqual(compile(s)["payload"]["result"], "CLEAR_FOR_MUSE_PREFLIGHT")

    def test_dnr_other_route_does_not_hold(self):
        s = base_snapshot(); s["dnr_receipts"] = [dnr_receipt(route_kind="DIRECT_MESSAGE")]
        self.assertEqual(compile(s)["payload"]["result"], "CLEAR_FOR_MUSE_PREFLIGHT")

    def test_incomplete_ledger_holds(self):
        s = base_snapshot(); s["ledger_complete"] = False
        self.assertEqual(compile(s)["payload"]["result"], "HOLD_LEDGER_INCOMPLETE")

    def test_prepared_after_as_of_holds(self):
        s = base_snapshot(); s["request"]["prepared_at"] = "2026-09-16T14:31:00Z"
        self.assertEqual(compile(s)["payload"]["result"], "HOLD_EVIDENCE_ORDERING")

    def test_future_send_holds(self):
        s = base_snapshot(); s["send_receipts"] = [send_receipt(sent_at="2026-09-16T14:31:00Z")]
        self.assertEqual(compile(s)["payload"]["result"], "HOLD_EVIDENCE_ORDERING")

    def test_future_dnr_holds(self):
        s = base_snapshot(); s["dnr_receipts"] = [dnr_receipt(observed_at="2026-09-16T14:31:00Z")]
        self.assertEqual(compile(s)["payload"]["result"], "HOLD_EVIDENCE_ORDERING")

    def test_candidate_publication_rebound_holds_source_conflict(self):
        s = base_snapshot(); s["send_receipts"] = [send_receipt(publication_key=h("9"))]
        self.assertEqual(compile(s)["payload"]["result"], "HOLD_SOURCE_CONFLICT")

    def test_candidate_intent_rebound_holds_source_conflict(self):
        s = base_snapshot(); s["send_receipts"] = [send_receipt(intent_sha256=h("9"))]
        self.assertEqual(compile(s)["payload"]["result"], "HOLD_SOURCE_CONFLICT")

    def test_candidate_operation_rebound_holds_source_conflict(self):
        s = base_snapshot(); s["send_receipts"] = [send_receipt(operation_id="OP-OTHER")]
        self.assertEqual(compile(s)["payload"]["result"], "HOLD_SOURCE_CONFLICT")

    def test_candidate_route_rebound_holds_source_conflict(self):
        s = base_snapshot(); s["send_receipts"] = [send_receipt(route_kind="DIRECT_MESSAGE")]
        self.assertEqual(compile(s)["payload"]["result"], "HOLD_SOURCE_CONFLICT")

    def test_duplicate_provider_message_id_rejected(self):
        s = base_snapshot(); s["send_receipts"] = [send_receipt(), send_receipt()]
        with self.assertRaises(guard.PreflightError) as ctx: compile(s)
        self.assertEqual(ctx.exception.code, "DUPLICATE_PROVIDER_MESSAGE_ID")

    def test_same_message_id_different_provider_allowed(self):
        s = base_snapshot(); s["send_receipts"] = [send_receipt(), send_receipt(provider="SLACK")]
        self.assertEqual(compile(s)["payload"]["result"], "HOLD_EXACT_INTENT_ALREADY_SENT")

    def test_duplicate_dnr_ref_rejected(self):
        s = base_snapshot(); s["dnr_receipts"] = [dnr_receipt(), dnr_receipt()]
        with self.assertRaises(guard.PreflightError) as ctx: compile(s)
        self.assertEqual(ctx.exception.code, "DUPLICATE_DNR_PROVIDER_REF")

    def test_duplicate_source_observation_rejected(self):
        s = base_snapshot(); s["source_observations"].append(s["source_observations"][0])
        with self.assertRaises(guard.PreflightError): compile(s)

    def test_empty_source_observation_rejected(self):
        s = base_snapshot(); s["source_observations"] = []
        with self.assertRaises(guard.PreflightError): compile(s)

    def test_unknown_root_field_rejected(self):
        s = base_snapshot(); s["extra"] = 1
        with self.assertRaises(guard.PreflightError): compile(s)

    def test_unknown_send_field_rejected(self):
        s = base_snapshot(); row = send_receipt(); row["extra"] = "x"; s["send_receipts"] = [row]
        with self.assertRaises(guard.PreflightError): compile(s)

    def test_unsupported_route_rejected(self):
        s = base_snapshot(); s["request"]["route_kind"] = "FAX"
        with self.assertRaises(guard.PreflightError) as ctx: compile(s)
        self.assertEqual(ctx.exception.code, "ROUTE_KIND_INVALID")

    def test_unsupported_provider_rejected(self):
        s = base_snapshot(); s["send_receipts"] = [send_receipt(provider="SMTP")]
        with self.assertRaises(guard.PreflightError) as ctx: compile(s)
        self.assertEqual(ctx.exception.code, "PROVIDER_INVALID")

    def test_bool_ledger_required(self):
        s = base_snapshot(); s["ledger_complete"] = 1
        with self.assertRaises(guard.PreflightError) as ctx: compile(s)
        self.assertEqual(ctx.exception.code, "LEDGER_COMPLETE_BOOL_REQUIRED")

    def test_invalid_hash_rejected(self):
        s = base_snapshot(); s["request"]["publication_key"] = "abc"
        with self.assertRaises(guard.PreflightError): compile(s)

    def test_invalid_utc_rejected(self):
        s = base_snapshot(); s["as_of_utc"] = "2026-99-99T00:00:00Z"
        with self.assertRaises(guard.PreflightError): compile(s)

    def test_duplicate_json_key_rejected(self):
        with self.assertRaises(guard.PreflightError) as ctx: guard.strict_json_loads('{"x":1,"x":2}')
        self.assertEqual(ctx.exception.code, "DUPLICATE_JSON_KEY")

    def test_float_rejected(self):
        with self.assertRaises(guard.PreflightError) as ctx: guard.strict_json_loads('{"x":1.5}')
        self.assertEqual(ctx.exception.code, "FLOAT_NOT_ALLOWED")

    def test_nonfinite_rejected(self):
        with self.assertRaises(guard.PreflightError) as ctx: guard.strict_json_loads('{"x":NaN}')
        self.assertEqual(ctx.exception.code, "NONFINITE_NUMBER")

    def test_oversized_int_rejected_without_traceback(self):
        huge = "1" + ("0" * 80)
        with self.assertRaises(guard.PreflightError) as ctx:
            guard.strict_json_loads('{"x":' + huge + "}")
        self.assertEqual(ctx.exception.code, "INT_OUT_OF_RANGE")

    def test_max_safe_int_accepted(self):
        self.assertEqual(guard.strict_json_loads('{"x":9007199254740991}')["x"], 9007199254740991)

    def test_report_tamper_rejected(self):
        s = base_snapshot(); report = compile(s); report["payload"]["result"] = "HOLD_AFTER_DNR"
        self.assertFalse(guard.verify_report(s, base_authority(s), report, now_utc=NOW)["valid"])

    def test_resealed_report_tamper_rejected(self):
        s = base_snapshot(); report = compile(s); report["payload"]["result"] = "HOLD_AFTER_DNR"; report["receiptSha256"] = guard.sha256_text(guard.canonical_json(report["payload"]))
        self.assertFalse(guard.verify_report(s, base_authority(s), report, now_utc=NOW)["valid"])

    def test_source_mutation_breaks_verification(self):
        s = base_snapshot(); report = compile(s); s["source_observations"][0] = h("9")
        self.assertFalse(guard.verify_report(s, base_authority(), report, now_utc=NOW)["valid"])

    def test_input_order_deterministic(self):
        s = base_snapshot(); s["send_receipts"] = [send_receipt(provider_message_id="gmail:z", sent_at="2026-09-16T14:26:00Z"), send_receipt(provider_message_id="gmail:a", candidate_sha256=h("9"), intent_sha256=h("8"), operation_id="OP-OTHER", sent_at="2026-09-16T14:21:00Z")]
        s["send_receipts"][0]["candidate_sha256"] = h("7"); s["send_receipts"][0]["intent_sha256"] = h("6"); s["send_receipts"][0]["operation_id"] = "OP-OTHER-2"
        r1 = compile(s); s["send_receipts"].reverse(); r2 = compile(s)
        self.assertEqual(r1, r2)

    def test_public_authority_mutation_cannot_authorize(self):
        original = deepcopy(guard.AUTHORITY_FALSE)
        try:
            for k in guard.AUTHORITY_FALSE: guard.AUTHORITY_FALSE[k] = True
            report = compile(base_snapshot())
            self.assertTrue(all(v is False for v in report["payload"]["authorities"].values()))
        finally:
            guard.AUTHORITY_FALSE.clear(); guard.AUTHORITY_FALSE.update(original)

    def test_public_authority_rebind_cannot_authorize(self):
        original = guard.AUTHORITY_FALSE
        try:
            guard.AUTHORITY_FALSE = {"externalSendAuthorized": True}
            report = compile(base_snapshot())
            self.assertTrue(all(v is False for v in report["payload"]["authorities"].values()))
        finally: guard.AUTHORITY_FALSE = original

    def test_clear_is_not_send_authority(self):
        p = compile(base_snapshot())["payload"]
        self.assertEqual(p["result"], "CLEAR_FOR_MUSE_PREFLIGHT")
        self.assertTrue(p["requiresFreshProviderPreflight"])
        self.assertTrue(p["requiresCanonicalMuseElectionV2"])
        self.assertTrue(p["operationallyCurrent"])
        self.assertFalse(p["authorities"]["externalSendAuthorized"])
        self.assertFalse(p["authorities"]["providerMutationAuthorized"])

    def test_deleted_stopping_row_cannot_clear_against_retained_authority(self):
        retained = base_snapshot()
        retained["dnr_receipts"] = [dnr_receipt()]
        retained["send_receipts"] = [send_receipt()]
        authority = base_authority(retained)
        candidate = base_snapshot()
        candidate["ledger_complete"] = True
        candidate["source_observations"] = [h("9"), h("8")]
        r = compile(candidate, authority)["payload"]
        self.assertEqual(r["result"], "HOLD_RETAINED_AUTHORITY_MISMATCH")
        self.assertNotEqual(r["result"], "CLEAR_FOR_MUSE_PREFLIGHT")

    def test_stale_retained_authority_is_not_current(self):
        s = base_snapshot()
        authority = base_authority(s)
        authority["observed_at_utc"] = "2026-09-16T13:00:00Z"
        r = compile(s, authority, now_utc=NOW)["payload"]
        self.assertEqual(r["result"], "HOLD_NOT_CURRENT")
        self.assertFalse(r["operationallyCurrent"])

    def _write_current_pair(self, src: Path, auth: Path) -> None:
        now = datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
        snapshot = base_snapshot(); snapshot["as_of_utc"] = now; snapshot["request"]["prepared_at"] = now
        authority = base_authority(snapshot); authority["observed_at_utc"] = now
        src.write_text(json.dumps(snapshot), encoding="utf-8")
        auth.write_text(json.dumps(authority), encoding="utf-8")

    def test_cli_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td); src = td / "snapshot.json"; auth = td / "authority.json"; out = td / "report.json"
            stdout = ""
            for _ in range(6):
                if out.exists():
                    out.unlink()
                self._write_current_pair(src, auth)
                p = subprocess.run([sys.executable, str(MODULE_PATH), "compile", str(src), str(auth), str(out)], capture_output=True, text=True, check=False)
                stdout = p.stdout.strip()
                if p.returncode == 0 and stdout == "CLEAR_FOR_MUSE_PREFLIGHT":
                    break
            self.assertEqual(stdout, "CLEAR_FOR_MUSE_PREFLIGHT")
            v = subprocess.run([sys.executable, str(MODULE_PATH), "verify", str(src), str(auth), str(out)], capture_output=True, text=True, check=False)
            self.assertEqual(v.returncode, 0, v.stderr); self.assertEqual(v.stdout.strip(), "VERIFIED")

    def test_cli_roundtrip_optimized(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td); src = td / "snapshot.json"; auth = td / "authority.json"; out = td / "report.json"
            stdout = ""
            for _ in range(6):
                if out.exists():
                    out.unlink()
                self._write_current_pair(src, auth)
                p = subprocess.run([sys.executable, "-O", str(MODULE_PATH), "compile", str(src), str(auth), str(out)], capture_output=True, text=True, check=False)
                stdout = p.stdout.strip()
                if p.returncode == 0 and stdout == "CLEAR_FOR_MUSE_PREFLIGHT":
                    break
            self.assertEqual(stdout, "CLEAR_FOR_MUSE_PREFLIGHT")
            self.assertEqual(p.stderr, "")

    def test_cli_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td); src = td / "snapshot.json"; auth = td / "authority.json"; out = td / "report.json"
            src.write_text(json.dumps(base_snapshot()), encoding="utf-8")
            auth.write_text(json.dumps(base_authority()), encoding="utf-8")
            out.write_text("occupied", encoding="utf-8")
            p = subprocess.run([sys.executable, str(MODULE_PATH), "compile", str(src), str(auth), str(out)], capture_output=True, text=True, check=False)
            self.assertEqual(p.returncode, 2); self.assertIn("OUTPUT_EXISTS", p.stderr)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink unavailable")
    def test_cli_refuses_input_symlink(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td); real = td / "real.json"; link = td / "link.json"; auth = td / "authority.json"; out = td / "report.json"
            real.write_text(json.dumps(base_snapshot()), encoding="utf-8"); os.symlink(real, link)
            auth.write_text(json.dumps(base_authority()), encoding="utf-8")
            p = subprocess.run([sys.executable, str(MODULE_PATH), "compile", str(link), str(auth), str(out)], capture_output=True, text=True, check=False)
            self.assertEqual(p.returncode, 2); self.assertIn("INPUT_OPEN_FAILED", p.stderr)

    def test_cli_fifo_rejected_without_hang(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            fifo = td / "snapshot.fifo"
            auth = td / "authority.json"
            out = td / "report.json"
            os.mkfifo(fifo)
            auth.write_text(json.dumps(base_authority()), encoding="utf-8")
            p = subprocess.run(
                [sys.executable, str(MODULE_PATH), "compile", str(fifo), str(auth), str(out)],
                capture_output=True, text=True, check=False, timeout=3,
            )
            self.assertEqual(p.returncode, 2)
            self.assertIn("INPUT_NOT_REGULAR_FILE", p.stderr)
            self.assertNotIn("Traceback", p.stderr)

    def test_cli_fifo_rejected_optimized(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            fifo = td / "snapshot.fifo"
            auth = td / "authority.json"
            out = td / "report.json"
            os.mkfifo(fifo)
            auth.write_text(json.dumps(base_authority()), encoding="utf-8")
            p = subprocess.run(
                [sys.executable, "-O", str(MODULE_PATH), "compile", str(fifo), str(auth), str(out)],
                capture_output=True, text=True, check=False, timeout=3,
            )
            self.assertEqual(p.returncode, 2)
            self.assertIn("INPUT_NOT_REGULAR_FILE", p.stderr)
            self.assertNotIn("Traceback", p.stderr)

    def test_cli_oversized_int_no_traceback(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            src = td / "snapshot.json"
            auth = td / "authority.json"
            out = td / "report.json"
            src.write_text('{"x":' + ("1" * 5000) + "}", encoding="utf-8")
            auth.write_text(json.dumps(base_authority()), encoding="utf-8")
            p = subprocess.run(
                [sys.executable, str(MODULE_PATH), "compile", str(src), str(auth), str(out)],
                capture_output=True, text=True, check=False, timeout=3,
            )
            self.assertEqual(p.returncode, 2)
            self.assertTrue("INT_OUT_OF_RANGE" in p.stderr or "INVALID_JSON" in p.stderr)
            self.assertNotIn("Traceback", p.stderr)

    def test_cli_oversized_int_optimized_no_traceback(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            src = td / "snapshot.json"
            auth = td / "authority.json"
            out = td / "report.json"
            src.write_text('{"x":' + ("1" * 5000) + "}", encoding="utf-8")
            auth.write_text(json.dumps(base_authority()), encoding="utf-8")
            p = subprocess.run(
                [sys.executable, "-O", str(MODULE_PATH), "compile", str(src), str(auth), str(out)],
                capture_output=True, text=True, check=False, timeout=3,
            )
            self.assertEqual(p.returncode, 2)
            self.assertTrue("INT_OUT_OF_RANGE" in p.stderr or "INVALID_JSON" in p.stderr)
            self.assertNotIn("Traceback", p.stderr)


if __name__ == "__main__":
    unittest.main()
