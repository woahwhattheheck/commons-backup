"""Fail-closed teaming readiness compiler for Land Bank T12-09-26.

This module records evidence supplied by a qualified prime candidate and keeps
buyer/prime/submission authority mechanically separate from a bounded TJLabs
paid technical workshare. It does not certify procurement eligibility.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any, Iterable, Mapping, Sequence

SCHEMA = "tjlabs.land_bank_online_library_readiness.v1"
SOLICITATION = "T12-09-26"
BUYER = "Land and Agricultural Development Bank of South Africa"
CLOSING = "2026-10-08T11:00:00+02:00"

REQUIRED_PRIME_EVIDENCE = (
    "legal_library_platform_rights",
    "oem_osm_or_authorized_partner",
    "enterprise_reference_evidence",
    "cloud_hosting_capability",
    "uptime_and_disaster_recovery_capability",
    "security_and_encryption_capability",
    "independent_penetration_testing_capability",
    "south_africa_csd_registration",
    "sars_tax_compliance",
    "bbbee_evidence",
    "fica_kyc_evidence",
)

WORKSHARE_DELIVERABLES = (
    "content_migration_metadata_acceptance",
    "rbac_entitlement_acceptance",
    "search_retrieval_regression",
    "integration_data_contract_qa",
    "security_dr_evidence_matrix",
    "training_handover_acceptance",
    "requirements_traceability_pack",
)


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def _nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _unique_strings(values: Iterable[object]) -> list[str]:
    return sorted({v.strip() for v in values if isinstance(v, str) and v.strip()})


def _authority_accepted(authority_root: object) -> bool:
    return authority_root is True


@dataclass(frozen=True)
class EvidenceRef:
    label: str
    locator: str
    sha256_hex: str = ""
    note: str = ""

    def valid(self, *, require_hash: bool = False) -> bool:
        if not (_nonempty(self.label) and _nonempty(self.locator) and isinstance(self.note, str)):
            return False
        if require_hash:
            return (
                isinstance(self.sha256_hex, str)
                and len(self.sha256_hex) == 64
                and all(c in "0123456789abcdef" for c in self.sha256_hex)
            )
        return isinstance(self.sha256_hex, str)

    def as_dict(self) -> dict[str, str]:
        if not self.valid():
            raise ValueError("invalid evidence reference")
        return {
            "label": self.label.strip(),
            "locator": self.locator.strip(),
            "sha256": self.sha256_hex.strip(),
            "note": self.note.strip(),
        }


@dataclass(frozen=True)
class SourceCustody:
    authoritative_tender_ref: EvidenceRef | None
    annexure_refs: tuple[EvidenceRef, ...] = ()
    secondary_listing_refs: tuple[EvidenceRef, ...] = ()

    def result(self) -> dict[str, Any]:
        blockers: list[str] = []
        authoritative = self.authoritative_tender_ref
        if not isinstance(authoritative, EvidenceRef) or not authoritative.valid(require_hash=True):
            blockers.append("authoritative_tender_bytes_not_retained")
            authoritative_dict = None
        else:
            authoritative_dict = authoritative.as_dict()

        annexures = [
            ref.as_dict()
            for ref in self.annexure_refs
            if isinstance(ref, EvidenceRef) and ref.valid(require_hash=True)
        ]
        secondary = [
            ref.as_dict()
            for ref in self.secondary_listing_refs
            if isinstance(ref, EvidenceRef) and ref.valid()
        ]
        return {
            "status": "SOURCE_BYTES_READY" if not blockers else "HOLD",
            "blockers": blockers,
            "authoritative_tender_ref": authoritative_dict,
            "annexure_refs": annexures,
            "secondary_listing_refs": secondary,
            "secondary_sources_are_authority": False,
        }


@dataclass(frozen=True)
class PrimeCandidate:
    legal_name: str
    evidence: Mapping[str, EvidenceRef | None]

    def result(self, authority_root: object = False) -> dict[str, Any]:
        blockers: list[str] = []
        if not _authority_accepted(authority_root):
            blockers.append("authority_root_not_accepted")
        if not _nonempty(self.legal_name):
            blockers.append("missing_legal_name")

        rows: dict[str, dict[str, str] | None] = {}
        for key in REQUIRED_PRIME_EVIDENCE:
            ref = self.evidence.get(key)
            if not isinstance(ref, EvidenceRef) or not ref.valid():
                blockers.append(f"missing_prime_evidence:{key}")
                rows[key] = None
            else:
                rows[key] = ref.as_dict()

        unknown = sorted(set(self.evidence) - set(REQUIRED_PRIME_EVIDENCE))
        if unknown:
            blockers.append("unknown_prime_evidence_keys")

        return {
            "status": "PRIME_EVIDENCE_READY" if not blockers else "HOLD",
            "blockers": sorted(blockers),
            "legal_name": self.legal_name.strip() if isinstance(self.legal_name, str) else "",
            "evidence": rows,
            "unknown_evidence_keys": unknown,
        }


@dataclass(frozen=True)
class PaidWorkshare:
    owner: str
    deliverables: tuple[str, ...]
    acceptance_criteria: tuple[str, ...]
    exclusions: tuple[str, ...]
    commercial_state: str = "PAID_SCOPE_TO_BE_AGREED"

    def result(self, authority_root: object = False) -> dict[str, Any]:
        blockers: list[str] = []
        if not _authority_accepted(authority_root):
            blockers.append("authority_root_not_accepted")
        owner = self.owner.strip() if isinstance(self.owner, str) else ""
        if not owner:
            blockers.append("missing_workshare_owner")

        deliverables = _unique_strings(self.deliverables)
        unknown = sorted(set(deliverables) - set(WORKSHARE_DELIVERABLES))
        missing = sorted(set(WORKSHARE_DELIVERABLES) - set(deliverables))
        if missing:
            blockers.append("missing_workshare_deliverables")
        if unknown:
            blockers.append("unknown_workshare_deliverables")

        acceptance = _unique_strings(self.acceptance_criteria)
        exclusions = _unique_strings(self.exclusions)
        if not acceptance:
            blockers.append("missing_acceptance_criteria")
        if not exclusions:
            blockers.append("missing_exclusions")
        if self.commercial_state != "PAID_SCOPE_TO_BE_AGREED":
            blockers.append("unsupported_commercial_state")

        return {
            "status": "WORKSHARE_READY" if not blockers else "HOLD",
            "blockers": sorted(set(blockers)),
            "owner": owner,
            "deliverables": deliverables,
            "missing_deliverables": missing,
            "unknown_deliverables": unknown,
            "acceptance_criteria": acceptance,
            "exclusions": exclusions,
            "commercial_state": self.commercial_state,
        }


@dataclass(frozen=True)
class SubmissionAuthority:
    buyer_submission_instructions_verified: bool = False
    authorized_signatory_confirmed: bool = False
    prime_approved_submission: bool = False
    physical_delivery_authorized: bool = False

    def result(self, authority_root: object = False) -> dict[str, Any]:
        checks = {
            "buyer_submission_instructions_verified": self.buyer_submission_instructions_verified is True,
            "authorized_signatory_confirmed": self.authorized_signatory_confirmed is True,
            "prime_approved_submission": self.prime_approved_submission is True,
            "physical_delivery_authorized": self.physical_delivery_authorized is True,
        }
        blockers = [f"{key}:not_confirmed" for key, ok in checks.items() if not ok]
        if not _authority_accepted(authority_root):
            blockers.append("authority_root_not_accepted")
        return {
            "status": "SUBMISSION_AUTHORITY_READY" if not blockers else "HOLD",
            "blockers": blockers,
            "checks": checks,
        }


def compile_readiness(
    *,
    source_custody: SourceCustody,
    prime: PrimeCandidate,
    workshare: PaidWorkshare,
    submission_authority: SubmissionAuthority | None = None,
    authority_root: object = False,
) -> dict[str, Any]:
    if not _authority_accepted(authority_root):
        teaming_blockers_pre = ["authority_root"]
    else:
        teaming_blockers_pre = []
    source = source_custody.result()
    prime_result = prime.result(authority_root)
    workshare_result = workshare.result(authority_root)
    submission = (submission_authority or SubmissionAuthority()).result(authority_root)

    teaming_blockers: list[str] = list(teaming_blockers_pre)
    if source["status"] != "SOURCE_BYTES_READY":
        teaming_blockers.append("source_custody")
    if workshare_result["status"] != "WORKSHARE_READY":
        teaming_blockers.append("paid_workshare")

    prime_blockers = list(teaming_blockers)
    if prime_result["status"] != "PRIME_EVIDENCE_READY":
        prime_blockers.append("prime_qualification")

    teaming_status = "TEAMING_PACKET_READY" if not teaming_blockers else "HOLD"
    response_status = "PRIME_RESPONSE_ASSEMBLY_READY" if not prime_blockers else "HOLD"
    submission_status = (
        "SUBMISSION_READY"
        if response_status == "PRIME_RESPONSE_ASSEMBLY_READY"
        and submission["status"] == "SUBMISSION_AUTHORITY_READY"
        else "HOLD"
    )

    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "opportunity": {
            "buyer": BUYER,
            "solicitation": SOLICITATION,
            "closing": CLOSING,
        },
        "source_custody": source,
        "prime": prime_result,
        "paid_workshare": workshare_result,
        "teaming_status": teaming_status,
        "teaming_blockers": sorted(teaming_blockers),
        "response_status": response_status,
        "response_blockers": sorted(prime_blockers),
        "submission_authority": submission,
        "submission_status": submission_status,
        "claims_boundary": (
            "Evidence carrier only. It does not establish bidder eligibility, OEM/OSM "
            "or reseller status, CSD/tax/B-BBEE/FICA compliance, content rights, "
            "partnership, buyer contact, briefing attendance, submission, signature, "
            "award, invoice, payment, cash, or booked revenue."
        ),
    }
    payload["receipt_sha256"] = sha256(_canonical(payload)).hexdigest()
    return payload


def render_markdown(pack: Mapping[str, Any]) -> str:
    lines = [
        "# Land Bank T12-09-26 readiness pack",
        "",
        f"- Teaming packet: **{pack['teaming_status']}**",
        f"- Prime response: **{pack['response_status']}**",
        f"- Submission: **{pack['submission_status']}**",
        f"- Source custody: **{pack['source_custody']['status']}**",
        f"- Prime evidence: **{pack['prime']['status']}**",
        f"- Paid workshare: **{pack['paid_workshare']['status']}**",
        f"- Receipt SHA-256: `{pack['receipt_sha256']}`",
        "",
        "## Teaming blockers",
    ]
    lines.extend([f"- `{x}`" for x in pack["teaming_blockers"]] or ["- none"])
    lines.extend(["", "## Prime response blockers"])
    lines.extend([f"- `{x}`" for x in pack["response_blockers"]] or ["- none"])
    lines.extend(["", "## Submission blockers"])
    lines.extend(
        [f"- `{x}`" for x in pack["submission_authority"]["blockers"]] or ["- none"]
    )
    lines.extend(["", "## Claims boundary", str(pack["claims_boundary"]), ""])
    return "\n".join(lines)
