from __future__ import annotations

import copy
import datetime as dt
import json
import os
import tempfile
import unittest
from pathlib import Path

from revenue.water4all_2026_swm import authority_registry, cli
from revenue.water4all_2026_swm.engine import (
    ReadinessError,
    canonical_bytes,
    compile_at,
    compile_current,
    compile_historical,
    render_owner_markdown,
    verify_bundle,
)
from revenue.water4all_2026_swm.common import seal_source, sha256_hex, strict_json_loads

UTC = dt.timezone.utc
T0 = dt.datetime(2026, 9, 14, 4, 0, 0, tzinfo=UTC)
HERE = Path(__file__).resolve().parent


def load_json(name):
    return json.loads((HERE / name).read_text(encoding="utf-8"))


def _install_test_authority(value):
    authority_registry.TEST_ONLY_OFFICIAL_SOURCE_GENERATIONS.clear()
    authority_registry.TEST_ONLY_OFFICIAL_SOURCE_GENERATIONS.update(
        {source["source_id"]: copy.deepcopy(source) for source in value["official_sources"]}
    )
    authority_registry.TEST_ONLY_TECHNICAL_EVIDENCE.clear()
    for evidence in value["technical_evidence"]:
        authority_registry.TEST_ONLY_TECHNICAL_EVIDENCE[evidence["evidence_id"]] = {
            "repo_full_name": evidence["repo_full_name"],
            "commit_sha": evidence["commit_sha"],
            "path": evidence["path"],
            "content_sha256": evidence["content_sha256"],
            "publicability": evidence["publicability"],
            "capability_tags": sorted(set(evidence["capability_tags"])),
        }


def base_valid():
    example = load_json("example_input.json")
    sources = copy.deepcopy(example["official_sources"])
    for source in sources:
        source["source_id"] = "test-" + source["source_id"]
        source["observed_at"] = "2026-09-14T03:40:00Z"
        source["preproposal_deadline_at"] = "2026-11-10T14:00:00Z"
        source.update(seal_source(source))

    members = []
    for partner_id, country, coordinator in [
        ("p1", "DE", True),
        ("p2", "ES", False),
        ("p3", "NL", False),
    ]:
        members.append(
            {
                "partner_id": partner_id,
                "organization_label": "Verified %s entity" % partner_id,
                "country_code": country,
                "role": "FUNDED_PARTNER",
                "eu_or_associated": True,
                "participating_fpo_country": True,
                "fpo_eligibility_verified": True,
                "undersubscribed_fpo": False,
                "legal_entity_verified": True,
                "pic_verified": True,
                "self_funding_commitment_verified": False,
                "coordinator": coordinator,
                "person_months_milli": 10000,
                "synthetic_placeholder": False,
                "water4all_partnership_beneficiary": False,
            }
        )
    evidence = [
        {
            "evidence_id": "ev1",
            "repo_full_name": "owner/repo",
            "commit_sha": "a" * 40,
            "path": "src/water.py",
            "content_sha256": "b" * 64,
            "observed_at": "2026-09-14T03:45:00Z",
            "verified": True,
            "publicability": "PUBLIC_DESCRIPTOR",
            "capability_tags": [
                "water_monitoring",
                "multimodal_data_integration",
                "uncertainty_quantification",
                "decision_support",
                "provenance_receipts",
            ],
        }
    ]
    value = {
        "schema": "water4all-2026-readiness-input/v1",
        "official_sources": sources,
        "consortium": {
            "members": members,
            "coordinator_pi_cross_proposal_evidence": {
                "pi_id": "pi-1",
                "evidence_id": "pi-cross-proposal-check-1",
                "participates_in_other_jtc_or_ecr_proposal": False,
                "verified": True,
            },
        },
        "applicant": {
            "applicant_id": "p1",
            "organization_label": "Verified p1 entity",
            "country_code": "DE",
            "intended_role": "FUNDED_PARTNER",
            "legal_entity_verified": True,
            "pic_verified": True,
            "paid_role_authority_verified": False,
            "subcontract_rule_verified": False,
            "synthetic_placeholder": False,
        },
        "concept": {
            "concept_title": "Verified monitoring concept",
            "topic_ids": [1],
            "status": "PROPOSED_NOT_ACCEPTED",
        },
        "technical_evidence": evidence,
        "partner_shortlist": copy.deepcopy(example["partner_shortlist"]),
        "commercial": {
            "status": "OWNER_APPROVED_INTERNAL",
            "paid_path": "OWNER_APPROVED_PARTICIPATION_PATH",
            "owner_approved_internal": True,
            "accepted_external": False,
            "price_quote_authorized": False,
            "self_funding_authorized": False,
            "consortium_commitment_authorized": False,
        },
    }
    _install_test_authority(value)
    return value


def compile_valid(value=None, mode="HISTORICAL", when=T0):
    payload = base_valid() if value is None else value
    if mode == "CURRENT":
        return compile_current(payload, payload)
    if mode != "HISTORICAL":
        raise ValueError("mode must be CURRENT or HISTORICAL")
    return compile_at(payload, when, "HISTORICAL")


def reason_codes(bundle):
    return {item["code"] for item in bundle["packet"]["decision"]["reasons"]}


def reseal(source):
    source.update(seal_source(source))
