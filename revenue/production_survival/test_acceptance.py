from __future__ import annotations

import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest

import acceptance


class AcceptanceCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.private = self.root / "private"
        self.public = self.root / "public"
        self.private.mkdir()
        self.public.mkdir()
        self.buyer_ref = "buyer_" + "a" * 32
        self.intent_path = self.public / "intent.json"
        self.terms_path = self.public / "terms-issued.json"
        self.acceptance_path = self.public / "acceptance.json"
        self._write_bytes("reply.txt", b"Interested in the fixed proof.\n")
        self._write_json(
            "intent-meta.json",
            {
                "buyer_ref": self.buyer_ref,
                "message_ref": "opaque:intentmsg001",
                "received_at": "2026-08-26T13:00:00Z",
                "classification": "POSITIVE",
                "operator_attestation": acceptance.INTENT_ATTESTATION,
            },
        )
        self.terms = {
            "buyer_ref": self.buyer_ref,
            "offer_id": acceptance.OFFER_ID,
            "currency": "USD",
            "fixed_amount": 2500,
            "given": "a public synthetic intake and a clean state directory",
            "when": "the local worker is intentionally crashed after its file-backed effect",
            "then": "one static receipt records recovery and a single deduplicated effect",
            "environment": "public Python 3.12 fixture with no private inputs",
            "terms_sent_at": "2026-08-26T14:00:00Z",
            "window_start": "2026-08-27T09:00:00-04:00",
            "window_end": "2026-08-27T17:00:00-04:00",
            "timezone": "America/New_York",
            "refund_choice": "REFUND_IF_MISSED",
            "proof_claims": acceptance.PROOF_CLAIMS,
            "exclusions": acceptance.EXCLUSIONS,
            "contract_nonce": "nonce_" + "b" * 32,
        }
        self._write_json("terms.json", self.terms)
        self._write_json(
            "terms-meta.json",
            {
                "buyer_ref": self.buyer_ref,
                "message_ref": "opaque:termsmsg001",
                "sent_at": "2026-08-26T14:00:00Z",
                "classification": "TERMS_ISSUED",
                "operator_attestation": acceptance.TERMS_ATTESTATION,
            },
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _write_bytes(self, relative: str, data: bytes) -> None:
        (self.private / relative).write_bytes(data)

    def _write_json(self, relative: str, value: object) -> None:
        (self.private / relative).write_text(
            json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
            newline="\n",
        )

    def _run(self, *args: str) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = acceptance.main(list(args))
        return code, stdout.getvalue(), stderr.getvalue()

    def _record_intent(self) -> dict[str, object]:
        code, _, error = self._run(
            "record-intent",
            "--evidence-root",
            str(self.private.resolve()),
            "--reply",
            "reply.txt",
            "--metadata",
            "intent-meta.json",
            "--out",
            str(self.intent_path.resolve()),
        )
        self.assertEqual(0, code, error)
        return json.loads(self.intent_path.read_text(encoding="utf-8"))

    def _issue_terms(self) -> dict[str, object]:
        self._record_intent()
        code, _, error = self._run(
            "issue-terms",
            "--evidence-root",
            str(self.private.resolve()),
            "--intent-receipt",
            str(self.intent_path.resolve()),
            "--terms",
            "terms.json",
            "--metadata",
            "terms-meta.json",
            "--out",
            str(self.terms_path.resolve()),
        )
        self.assertEqual(0, code, error)
        return json.loads(self.terms_path.read_text(encoding="utf-8"))

    def _record_acceptance(self, token: bytes | None = None) -> dict[str, object]:
        terms_receipt = self._issue_terms()
        if token is None:
            lineage = terms_receipt["lineage"]
            token = (
                f"ACCEPT {lineage['contract_id']} {lineage['contract_sha256']} "
                f"{terms_receipt['terms']['contract_nonce']}\n"
            ).encode("ascii")
        self._write_bytes("acceptance.txt", token)
        self._write_json(
            "acceptance-meta.json",
            {
                "buyer_ref": self.buyer_ref,
                "message_ref": "opaque:acceptmsg001",
                "in_reply_to": "opaque:termsmsg001",
                "received_at": "2026-08-26T15:00:00Z",
                "classification": "WRITTEN_ACCEPTANCE",
                "operator_attestation": acceptance.ACCEPTANCE_ATTESTATION,
            },
        )
        code, _, error = self._run(
            "record-acceptance",
            "--evidence-root",
            str(self.private.resolve()),
            "--terms-receipt",
            str(self.terms_path.resolve()),
            "--written-acceptance",
            "acceptance.txt",
            "--metadata",
            "acceptance-meta.json",
            "--out",
            str(self.acceptance_path.resolve()),
        )
        self.assertEqual(0, code, error)
        return json.loads(self.acceptance_path.read_text(encoding="utf-8"))

    def test_happy_chain_reduce_and_private_replay_gate(self) -> None:
        accepted = self._record_acceptance()
        code, output, error = self._run(
            "reduce",
            "--intent-receipt",
            str(self.intent_path.resolve()),
            "--terms-receipt",
            str(self.terms_path.resolve()),
            "--acceptance-receipt",
            str(self.acceptance_path.resolve()),
        )
        self.assertEqual(0, code, error)
        state = json.loads(output)
        self.assertEqual("ACCEPTED_OWNER_REPORTED", state["state"])
        self.assertEqual(0, state["collected_cash_usd"])
        code, output, error = self._run(
            "invoice-gate",
            "--evidence-root",
            str(self.private.resolve()),
            "--intent-receipt",
            str(self.intent_path.resolve()),
            "--terms-receipt",
            str(self.terms_path.resolve()),
            "--acceptance-receipt",
            str(self.acceptance_path.resolve()),
            "--reply",
            "reply.txt",
            "--terms",
            "terms.json",
            "--written-acceptance",
            "acceptance.txt",
        )
        self.assertEqual(0, code, error)
        gated = json.loads(output)
        self.assertEqual("READY_FOR_OWNER_HOSTED_INVOICE", gated["status"])
        self.assertEqual("NOT_LANDED", gated["invoice_state"])
        self.assertEqual("OWNER_REPORTED", accepted["facts"]["legal_acceptance"])

    def test_positive_reply_never_claims_acceptance_or_money(self) -> None:
        intent = self._record_intent()
        self.assertEqual("PURCHASE_INTENT", intent["facts"]["buyer_signal"])
        self.assertEqual("NOT_LANDED", intent["facts"]["legal_acceptance"])
        self.assertEqual(0, intent["facts"]["collected_cash_usd"])
        for key in (
            "invoice_state",
            "authorization_state",
            "settlement_state",
            "payout_state",
            "bank_available_state",
        ):
            self.assertEqual("NOT_LANDED", intent["facts"][key])

    def test_vague_acceptance_is_rejected_without_output(self) -> None:
        self._issue_terms()
        self._write_bytes("acceptance.txt", b"Looks good to me.\n")
        self._write_json(
            "acceptance-meta.json",
            {
                "buyer_ref": self.buyer_ref,
                "message_ref": "opaque:acceptmsg001",
                "in_reply_to": "opaque:termsmsg001",
                "received_at": "2026-08-26T15:00:00Z",
                "classification": "WRITTEN_ACCEPTANCE",
                "operator_attestation": acceptance.ACCEPTANCE_ATTESTATION,
            },
        )
        code, _, error = self._run(
            "record-acceptance",
            "--evidence-root",
            str(self.private.resolve()),
            "--terms-receipt",
            str(self.terms_path.resolve()),
            "--written-acceptance",
            "acceptance.txt",
            "--metadata",
            "acceptance-meta.json",
            "--out",
            str(self.acceptance_path.resolve()),
        )
        self.assertEqual(2, code)
        self.assertIn("exact ASCII contract token", error)
        self.assertFalse(self.acceptance_path.exists())

    def test_wrong_thread_and_reply_before_terms_fail(self) -> None:
        terms_receipt = self._issue_terms()
        token = (
            f"ACCEPT {terms_receipt['lineage']['contract_id']} "
            f"{terms_receipt['lineage']['contract_sha256']} {self.terms['contract_nonce']}\n"
        ).encode("ascii")
        self._write_bytes("acceptance.txt", token)
        for in_reply_to, received_at in (
            ("opaque:wrongthread1", "2026-08-26T15:00:00Z"),
            ("opaque:termsmsg001", "2026-08-26T13:59:59Z"),
        ):
            self._write_json(
                "acceptance-meta.json",
                {
                    "buyer_ref": self.buyer_ref,
                    "message_ref": "opaque:acceptmsg001",
                    "in_reply_to": in_reply_to,
                    "received_at": received_at,
                    "classification": "WRITTEN_ACCEPTANCE",
                    "operator_attestation": acceptance.ACCEPTANCE_ATTESTATION,
                },
            )
            code, _, _ = self._run(
                "record-acceptance",
                "--evidence-root",
                str(self.private.resolve()),
                "--terms-receipt",
                str(self.terms_path.resolve()),
                "--written-acceptance",
                "acceptance.txt",
                "--metadata",
                "acceptance-meta.json",
                "--out",
                str(self.acceptance_path.resolve()),
            )
            self.assertEqual(2, code)

    def test_terms_price_claims_exclusions_and_pii_fail_closed(self) -> None:
        for key, value in (
            ("fixed_amount", 2499),
            ("proof_claims", ["hosted runner"]),
            ("exclusions", []),
            ("environment", "send results to buyer@example.com"),
        ):
            changed = dict(self.terms)
            changed[key] = value
            self._write_json("terms.json", changed)
            self._record_intent()
            code, _, _ = self._run(
                "issue-terms",
                "--evidence-root",
                str(self.private.resolve()),
                "--intent-receipt",
                str(self.intent_path.resolve()),
                "--terms",
                "terms.json",
                "--metadata",
                "terms-meta.json",
                "--out",
                str(self.terms_path.resolve()),
            )
            self.assertEqual(2, code, key)
            self.assertFalse(self.terms_path.exists())

    def test_append_only_replay_is_identical_and_conflict_fails(self) -> None:
        self._record_intent()
        first = self.intent_path.read_bytes()
        self._record_intent()
        self.assertEqual(first, self.intent_path.read_bytes())
        self._write_bytes("reply.txt", b"different private evidence\n")
        code, _, error = self._run(
            "record-intent",
            "--evidence-root",
            str(self.private.resolve()),
            "--reply",
            "reply.txt",
            "--metadata",
            "intent-meta.json",
            "--out",
            str(self.intent_path.resolve()),
        )
        self.assertEqual(2, code)
        self.assertIn("different bytes", error)
        self.assertEqual(first, self.intent_path.read_bytes())

    def test_tampered_lineage_fails_reducer(self) -> None:
        self._record_acceptance()
        value = json.loads(self.terms_path.read_text(encoding="utf-8"))
        value["lineage"]["prior_receipt_sha256"] = "0" * 64
        self.terms_path.write_bytes(acceptance.canonical_bytes(value))
        code, _, _ = self._run(
            "reduce",
            "--intent-receipt",
            str(self.intent_path.resolve()),
            "--terms-receipt",
            str(self.terms_path.resolve()),
            "--acceptance-receipt",
            str(self.acceptance_path.resolve()),
        )
        self.assertEqual(2, code)

    def test_private_path_traversal_and_relative_root_fail(self) -> None:
        code, _, _ = self._run(
            "record-intent",
            "--evidence-root",
            "private",
            "--reply",
            "reply.txt",
            "--metadata",
            "intent-meta.json",
            "--out",
            str(self.intent_path.resolve()),
        )
        self.assertEqual(2, code)
        code, _, _ = self._run(
            "record-intent",
            "--evidence-root",
            str(self.private.resolve()),
            "--reply",
            "../reply.txt",
            "--metadata",
            "intent-meta.json",
            "--out",
            str(self.intent_path.resolve()),
        )
        self.assertEqual(2, code)

    def test_public_receipts_do_not_leak_private_content_or_paths(self) -> None:
        self._record_acceptance()
        public = b"".join(path.read_bytes() for path in self.public.iterdir())
        for forbidden in (
            b"buyer@example.com",
            b"Interested in the fixed proof",
            str(self.private).encode(),
            b"reply.txt",
            b"acceptance.txt",
        ):
            self.assertNotIn(forbidden, public)
        self.assertIn(hashlib.sha256((self.private / "reply.txt").read_bytes()).hexdigest().encode(), public)

    def test_schema_is_closed_at_every_object_boundary(self) -> None:
        schema = json.loads((Path(__file__).with_name("acceptance.schema.json")).read_text(encoding="utf-8"))
        self.assertFalse(schema["additionalProperties"])
        self.assertFalse(schema["properties"]["source"]["additionalProperties"])
        terms_object = schema["properties"]["terms"]["oneOf"][1]
        self.assertFalse(terms_object["additionalProperties"])
        self.assertFalse(schema["properties"]["lineage"]["additionalProperties"])
        self.assertFalse(schema["properties"]["facts"]["additionalProperties"])


if __name__ == "__main__":
    unittest.main()
