#!/usr/bin/env python3
"""Regression tests for the UIOWA-132 commercial-facts checker.

Run normally and with real python -O. Required checks do not use assert.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from canonical import CANONICAL
from checker import (
    DocumentFacts,
    FactsError,
    check_bundle,
    check_document,
    load_bundle,
    loads_strict,
    parse_document,
    render_facts_markdown,
)
from repair import repair_document, repair_text
import cli

FIXTURES = ROOT / "fixtures"


def _codes(result) -> set[str]:
    return set(result["finding_codes"])


class CanonicalTests(unittest.TestCase):
    def test_pinned_commercial_facts(self) -> None:
        if CANONICAL["rfq_id"] != "18649":
            raise AssertionError("rfq_id")
        if CANONICAL["currency"] != "USD":
            raise AssertionError("currency")
        if CANONICAL["deadline_date"] != "2026-09-22":
            raise AssertionError("deadline")
        if CANONICAL["deadline_timezone"] != "America/Chicago":
            raise AssertionError("timezone")
        if CANONICAL["base_amount_usd"] != 24000:
            raise AssertionError("base")
        if CANONICAL["option_amount_usd"] != 4000:
            raise AssertionError("option")
        if CANONICAL["option_included_in_base"] is not False:
            raise AssertionError("option not in base")
        if CANONICAL["milestone_split"] != (40, 40, 20):
            raise AssertionError("split")
        if CANONICAL["milestone_amounts_usd"] != (9600, 9600, 4800):
            raise AssertionError("milestone amounts")
        if CANONICAL["kickoff_assumption"] != "after_award_no_travel":
            raise AssertionError("kickoff")
        if CANONICAL["travel_treatment"] != "excluded_from_base":
            raise AssertionError("travel")
        if CANONICAL["roles"]["principal"] != "prime":
            raise AssertionError("prime")
        if CANONICAL["roles"]["specialist"] != "subcontract":
            raise AssertionError("subcontract")
        if any(CANONICAL["authority"].values()):
            raise AssertionError("authority ceiling must stay false")


class FixtureTests(unittest.TestCase):
    def test_consistent_bundle_has_no_findings(self) -> None:
        result = check_bundle(load_bundle(FIXTURES / "consistent"))
        if result["consistent"] is not True:
            raise AssertionError(result["findings"])
        if result["findings"]:
            raise AssertionError(result["findings"])
        table = render_facts_markdown(result)
        if "No cross-document commercial mismatches." not in table:
            raise AssertionError(table)
        if "Buyer contact" not in table:
            raise AssertionError("authority ceiling missing from table")

    def test_stale_september_22_detected(self) -> None:
        result = check_bundle(load_bundle(FIXTURES / "stale_september_22"))
        if "STALE_SEPTEMBER_22" not in _codes(result):
            raise AssertionError(result["findings"])
        if result["consistent"] is not False:
            raise AssertionError("stale bundle marked consistent")

    def test_amount_mismatch_detected(self) -> None:
        result = check_bundle(load_bundle(FIXTURES / "amount_mismatch"))
        if "AMOUNT_MISMATCH" not in _codes(result):
            raise AssertionError(result["findings"])

    def test_delivery_vs_acceptance_detected(self) -> None:
        result = check_bundle(load_bundle(FIXTURES / "delivery_vs_acceptance"))
        if "DELIVERY_VS_ACCEPTANCE_TRIGGER" not in _codes(result):
            raise AssertionError(result["findings"])

    def test_facts_table_names_all_five_documents(self) -> None:
        result = check_bundle(load_bundle(FIXTURES / "consistent"))
        names = [row["document"] for row in result["facts_table"]]
        if names != [
            "proposal",
            "fee_schedule",
            "staffing",
            "scope_exhibit",
            "option_sheet",
        ]:
            raise AssertionError(names)


class RepairTests(unittest.TestCase):
    def test_repair_stale_deadline(self) -> None:
        bundle = load_bundle(FIXTURES / "stale_september_22")
        repaired, remaining = repair_document(bundle["proposal"])
        if "2025" in repaired:
            raise AssertionError(repaired)
        if any(f.code == "STALE_SEPTEMBER_22" for f in remaining):
            raise AssertionError(remaining)

    def test_repair_amount_mismatch(self) -> None:
        bundle = load_bundle(FIXTURES / "amount_mismatch")
        repaired, remaining = repair_document(bundle["fee_schedule"])
        if "$25,000" in repaired or "25000" in repaired.replace(",", ""):
            if "base_amount_usd: 24000" not in repaired:
                raise AssertionError(repaired)
        if any(f.code == "AMOUNT_MISMATCH" for f in remaining):
            raise AssertionError(remaining)

    def test_repair_delivery_trigger(self) -> None:
        bundle = load_bundle(FIXTURES / "delivery_vs_acceptance")
        repaired, remaining = repair_document(bundle["fee_schedule"])
        if "upon delivery" in repaired.casefold():
            raise AssertionError(repaired)
        if "upon acceptance" not in repaired.casefold():
            raise AssertionError(repaired)
        if any(f.code == "DELIVERY_VS_ACCEPTANCE_TRIGGER" for f in remaining):
            raise AssertionError(remaining)

    def test_repair_does_not_collapse_prime_and_subcontract(self) -> None:
        text = (
            "The principal is the prime. The specialist is a subcontract "
            "resource and must not be rewritten as the prime.\n"
            "deadline: 2025-09-22\n"
            "base_amount_usd: 25000\n"
            "final_trigger: delivery\n"
            "The final milestone is payable upon delivery.\n"
        )
        repaired = repair_text(text)
        if "prime" not in repaired.casefold():
            raise RuntimeError("repair collapsed prime identity")
        if "subcontract" not in repaired.casefold():
            raise RuntimeError("repair collapsed subcontract identity")
        if "subcontract as prime" in repaired.casefold():
            raise AssertionError(repaired)
        findings = check_document(DocumentFacts("proposal", repaired))
        codes = {f.code for f in findings}
        if "STALE_SEPTEMBER_22" in codes:
            raise AssertionError(findings)
        if "AMOUNT_MISMATCH" in codes:
            raise AssertionError(findings)
        if "DELIVERY_VS_ACCEPTANCE_TRIGGER" in codes:
            raise AssertionError(findings)


class IngressTests(unittest.TestCase):
    def test_missing_document_is_a_hard_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "proposal.md").write_text("x", encoding="utf-8")
            try:
                load_bundle(root)
            except FactsError as exc:
                if "missing regular file" not in str(exc):
                    raise AssertionError(exc)
            else:
                raise AssertionError("missing file was accepted")

    def test_unexpected_document_is_a_hard_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in (
                "proposal",
                "fee_schedule",
                "staffing",
                "scope_exhibit",
                "option_sheet",
            ):
                (root / f"{name}.md").write_text("ok", encoding="utf-8")
            (root / "invoice.md").write_text("no", encoding="utf-8")
            try:
                load_bundle(root)
            except FactsError as exc:
                if "unexpected documents" not in str(exc):
                    raise AssertionError(exc)
            else:
                raise AssertionError("extra document was accepted")

    def test_symlink_document_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "real.md"
            target.write_text("ok", encoding="utf-8")
            for name in (
                "proposal",
                "fee_schedule",
                "staffing",
                "scope_exhibit",
                "option_sheet",
            ):
                os.symlink(target, root / f"{name}.md")
            try:
                load_bundle(root)
            except FactsError as exc:
                if "missing regular file" not in str(exc):
                    raise AssertionError(exc)
            else:
                raise AssertionError("symlink bundle was accepted")

    def test_duplicate_json_keys_are_refused(self) -> None:
        try:
            loads_strict('{"a": 1, "a": 2}')
        except FactsError:
            return
        raise AssertionError("duplicate JSON keys accepted")

    def test_nonfinite_json_is_refused(self) -> None:
        try:
            loads_strict('{"n": NaN}')
        except FactsError:
            return
        raise AssertionError("NaN accepted")

    def test_parse_rejects_non_strings(self) -> None:
        try:
            parse_document(1, "x")  # type: ignore[arg-type]
        except FactsError:
            return
        raise AssertionError("non-string name accepted")


class RoleTests(unittest.TestCase):
    def test_role_collapse_is_detected_and_not_treated_as_repair_success(self) -> None:
        text = (
            "deadline: 2026-09-22 15:00 America/Chicago\n"
            "currency: USD\n"
            "base_amount_usd: 24000\n"
            "option_amount_usd: 4000\n"
            "milestone_split: 40/40/20\n"
            "principal_role: prime\n"
            "specialist_role: subcontract\n"
            "final_trigger: acceptance\n"
            "The subcontractor is billed as the prime.\n"
        )
        findings = check_document(DocumentFacts("staffing", text))
        if not any(f.code == "ROLE_COLLAPSE" for f in findings):
            raise AssertionError(findings)
        repaired = repair_text(text)
        if "subcontract" not in repaired.casefold():
            raise RuntimeError("repair collapsed subcontract identity")
        if "prime" not in repaired.casefold():
            raise RuntimeError("repair collapsed prime identity")


class CliTests(unittest.TestCase):
    def test_cli_consistent_exit_zero(self) -> None:
        code = cli.main([str(FIXTURES / "consistent")])
        if code != 0:
            raise AssertionError(code)

    def test_cli_inconsistent_exit_one_and_writes_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            code = cli.main(
                [
                    str(FIXTURES / "amount_mismatch"),
                    "--json-out",
                    str(out / "facts.json"),
                    "--md-out",
                    str(out / "facts.md"),
                    "--repair-out",
                    str(out / "repaired"),
                ]
            )
            if code != 1:
                raise AssertionError(code)
            payload = json.loads((out / "facts.json").read_text(encoding="utf-8"))
            if "AMOUNT_MISMATCH" not in payload["finding_codes"]:
                raise AssertionError(payload)
            repaired = (out / "repaired" / "proposal.md").read_text(encoding="utf-8")
            if "subcontract" not in repaired.casefold():
                raise AssertionError(repaired)
            if "prime" not in repaired.casefold():
                raise AssertionError(repaired)

    def test_cli_missing_bundle_exit_two(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            code = cli.main([tmp])
            if code != 2:
                raise AssertionError(code)


if __name__ == "__main__":
    unittest.main()
