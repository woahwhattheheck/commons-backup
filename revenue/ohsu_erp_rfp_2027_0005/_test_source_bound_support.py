from __future__ import annotations

import copy
import datetime as dt
import json
import pathlib
import subprocess
import sys
import unittest

from revenue.ohsu_erp_rfp_2027_0005 import source_bound as s

ROOT = pathlib.Path(__file__).resolve().parent
A = "1" * 64
B = "2" * 64
C = "3" * 64


def facts(*, route="TEAMING", commitment=False, all_satisfied=False, partner_gates=()):
    partner_gates = set(partner_gates)
    rows = []
    for rid in s.REQUIREMENT_IDS:
        if all_satisfied:
            partner = rid in partner_gates
            rows.append({
                "requirement_id": rid,
                "state": "SATISFIED",
                "basis": "NAMED_COMMITTED_TEAM_PARTNER" if partner else "RESPONDENT",
                "entity_ref": "prime.example" if partner else s.RESPONDENT_REF,
                "evidence_sha256": B if partner else A,
            })
        else:
            rows.append({
                "requirement_id": rid, "state": "UNKNOWN", "basis": "NONE",
                "entity_ref": None, "evidence_sha256": None,
            })
    return {
        "schema": s.SCHEMA_FACTS,
        "route": route,
        "source_binding": {
            "controlling_pack_sha256": s.CONTROLLING_PACK_SHA256,
            "supplier_qa_sha256": s.SUPPLIER_QA_SHA256,
            "professional_services_contract_sha256": s.PROFESSIONAL_SERVICES_CONTRACT_SHA256,
        },
        "requirements": rows,
        "teaming_commitment": (
            {"status": "CONFIRMED", "partner_ref": "prime.example", "evidence_sha256": C}
            if commitment else
            {"status": "UNCONFIRMED", "partner_ref": None, "evidence_sha256": None}
        ),
        "intent_receipt": None,
        "owner_reviewed": True,
    }


class SourceBoundTestCase(unittest.TestCase):
    def before_intent(self):
        return dt.datetime(2026, 9, 15, 12, 0, tzinfo=dt.timezone.utc)

    def at_intent(self):
        return dt.datetime(2026, 9, 17, 0, 0, tzinfo=dt.timezone.utc)


__all__ = [
    "copy", "dt", "json", "pathlib", "subprocess", "sys", "unittest",
    "s", "ROOT", "A", "B", "C", "facts", "SourceBoundTestCase",
]
