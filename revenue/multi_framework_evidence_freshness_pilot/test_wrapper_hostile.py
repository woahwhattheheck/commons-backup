from __future__ import annotations

import copy
import hashlib
import json
import unittest

from revenue.multi_framework_evidence_freshness.golden import build_golden_input

from .wrapper import (
    MAX_EVIDENCE_OBJECTS,
    DiagnosticError,
    compile_diagnostic,
    render_buyer_page,
    verify_diagnostic,
)


def _one() -> dict:
    raw = build_golden_input()
    raw["evidence"] = [copy.deepcopy(raw["evidence"][0])]
    return raw


def _reseal(envelope: dict) -> dict:
    payload = json.dumps(envelope["diagnostic"], ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    envelope["diagnostic_sha256"] = hashlib.sha256(payload).hexdigest()
    return envelope


class WrapperHostileTests(unittest.TestCase):
    def test_rejects_non_object_root(self) -> None:
        with self.assertRaisesRegex(DiagnosticError, "root:object_required"):
            compile_diagnostic([])

    def test_rejects_non_list_evidence(self) -> None:
        raw = _one()
        raw["evidence"] = {"evidence_id": "x"}
        with self.assertRaisesRegex(DiagnosticError, "evidence:list_required"):
            compile_diagnostic(raw)

    def test_rejects_over_500(self) -> None:
        raw = _one()
        template = raw["evidence"][0]
        raw["evidence"] = []
        for i in range(MAX_EVIDENCE_OBJECTS + 1):
            row = copy.deepcopy(template)
            row["evidence_id"] = f"OVER-{i:03d}"
            raw["evidence"].append(row)
        with self.assertRaisesRegex(DiagnosticError, "evidence:max_500"):
            compile_diagnostic(raw)

    def test_digest_tamper_rejected(self) -> None:
        envelope = compile_diagnostic(_one())
        envelope["diagnostic_sha256"] = "0" * 64
        with self.assertRaisesRegex(DiagnosticError, "diagnostic_digest_mismatch"):
            verify_diagnostic(envelope)

    def test_authority_escalation_rejected(self) -> None:
        envelope = compile_diagnostic(_one())
        envelope["diagnostic"]["authority"]["audit_opinion"] = True
        with self.assertRaisesRegex(DiagnosticError, "authority_escalation"):
            verify_diagnostic(_reseal(envelope))

    def test_price_status_tamper_rejected(self) -> None:
        envelope = compile_diagnostic(_one())
        envelope["diagnostic"]["offer"]["status"] = "ACCEPTED"
        with self.assertRaisesRegex(DiagnosticError, "price_status"):
            verify_diagnostic(_reseal(envelope))

    def test_missing_engine_packet_rejected(self) -> None:
        envelope = compile_diagnostic(_one())
        del envelope["engine_packet"]
        with self.assertRaisesRegex(DiagnosticError, "engine_packet_missing"):
            verify_diagnostic(envelope)

    def test_receipt_binding_mismatch_rejected(self) -> None:
        envelope = compile_diagnostic(_one())
        envelope["diagnostic"]["binding"]["engine_receipt_sha256"] = "a" * 64
        with self.assertRaisesRegex(DiagnosticError, "receipt_binding"):
            verify_diagnostic(_reseal(envelope))

    def test_render_requires_diagnostic(self) -> None:
        with self.assertRaisesRegex(DiagnosticError, "envelope:diagnostic_required"):
            render_buyer_page({})


if __name__ == "__main__":
    unittest.main()
