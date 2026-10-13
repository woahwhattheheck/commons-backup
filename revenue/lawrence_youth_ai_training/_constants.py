from __future__ import annotations

import re
from pathlib import Path

SOURCE_SCHEMA = "lawrence-youth-ai-rfp-source-contract/v1"
SNAPSHOT_SCHEMA = "lawrence-youth-ai-qualification-snapshot/v2"
RECEIPT_SCHEMA = "lawrence-youth-ai-qualification-receipt/v2"
AUTHORITY_ENVELOPE_SCHEMA = "lawrence-youth-ai-semantic-authority-envelope/v1"
AUTHORITY_KEY_SCHEMA = "lawrence-youth-ai-semantic-authority-key/v1"

PRIME_READY = "PRIME_READY"
COLLABORATIVE_READY = "COLLABORATIVE_READY"
HOLD = "HOLD"
NO_BID = "NO_BID"
AUTHORITY = "INTERNAL_QUALIFICATION_EVIDENCE_ONLY"

EXPECTED_SOURCE_CONTRACT_SHA256 = "9f9176b1747389c2c5a982e3fe459f6db2465b0244099fc8e625239236d7116e"
SOURCE_MAX_AGE_SECONDS = 24 * 60 * 60
RECEIPT_MAX_AGE_SECONDS = 60 * 60
SEMANTIC_AUTHORITY_MAX_AGE_SECONDS = 24 * 60 * 60
MAX_JSON_BYTES = 1_048_576
MAX_ITEMS = 128
MAX_STRING_BYTES = 2048

GOOD_STANDING_DOCUMENT = "certificate_good_standing"
AUDIT_DOCUMENT = "audit_assurance_certification"
_SEMANTIC_DOCUMENTS = frozenset({GOOD_STANDING_DOCUMENT, AUDIT_DOCUMENT})

HOST_AUTHORITY_ROOT = Path("/etc/commons/lawrence-youth-ai-training")
HOST_AUTHORITY_KEY_PATH = HOST_AUTHORITY_ROOT / "authority-key.json"
HOST_AUTHORITY_ENVELOPE_PATH = HOST_AUTHORITY_ROOT / "semantic-authority.json"

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_HEX_KEY = re.compile(r"^[0-9a-f]{64,256}$")
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_EXPLICIT_TZ = re.compile(r"(?:Z|[+-][0-9]{2}:[0-9]{2})$")

_AUTHORITY_FALSE_FIELDS = (
    "proposal_submission_authorized",
    "external_contact_authorized",
    "pricing_authorized",
    "certification_signature_authorized",
    "participant_data_authorized",
    "employer_commitment_inferred",
    "contract_awarded_inferred",
    "payment_received_inferred",
    "revenue_recognized_inferred",
)


class QualificationInputError(ValueError):
    """Malformed qualification evidence."""


class SemanticAuthorityUnavailable(RuntimeError):
    """The fixed production semantic-authority root is absent or unsafe."""
