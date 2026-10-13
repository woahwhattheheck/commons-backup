from __future__ import annotations

import re

INPUT_SCHEMA = "bidder-qualification-vault/entity-bound/v2"
OUTPUT_SCHEMA = "bidder-qualification-vault/entity-bound-candidate-manifest/v2"

# These are candidate/integrity states over caller-supplied bytes. They are
# deliberately not current operational authority.
STATES = {
    "CANDIDATE_VERIFIED",
    "EXPIRED",
    "SUPERSEDED",
    "MISSING",
    "HOLD_PRIVATE_REVIEW",
    "CONFLICT",
}
CATEGORIES = {
    "LEGAL_ENTITY",
    "REGISTRATION",
    "W9",
    "FINANCIAL_STATEMENT",
    "INSURANCE_COI",
    "STAFF_CV",
    "STAFF_AVAILABILITY",
    "REFERENCE_PERFORMANCE",
    "REFERENCE_PERMISSION",
    "REFERENCE_CONTACTABILITY",
    "CERTIFICATION",
    "SIGNATURE_AUTHORITY",
    "COMMERCIAL_APPROVAL",
    "OTHER",
}
SOURCE_CLASSES = {"OWNER_CONTROLLED", "ISSUER_CONTROLLED", "THIRD_PARTY_PUBLIC", "SELF_ASSERTED"}
VERIFICATION_STATES = {"VERIFIED", "PENDING_PRIVATE_REVIEW", "SELF_ASSERTED"}
VERIFIER_CLASSES = {"HUMAN_OWNER", "ISSUER", "THIRD_PARTY_VERIFIER", "NONE"}
REUSE_SCOPES = {"GLOBAL", "OPPORTUNITY_ONLY"}
PUBLICABILITY = {"PUBLIC_METADATA", "PRIVATE_REVIEW"}
STAGES = {"SUBMISSION", "AWARD"}
FINANCIAL_CLASSES = {"AUDITED", "REVIEWED", "COMPILED", "OTHER"}

ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

INPUT_KEYS = {"schema", "generation_id", "entity_id", "as_of", "evidence", "requirements"}
EVIDENCE_KEYS = {
    "id", "category", "entity_id", "subject_id", "source_class", "issuer", "descriptor",
    "content_sha256", "captured_at", "issued_at", "expires_at", "verification_state",
    "verifier_class", "reuse_scope", "opportunity_ids", "stages", "publicability",
    "supersedes", "revoked_at", "metadata",
}
REQ_KEYS = {"id", "category", "stage", "subject_id", "opportunity_id", "required_financial_class"}
