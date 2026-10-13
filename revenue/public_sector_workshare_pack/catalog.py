"""Static commercial and technical catalog for the workshare pack."""
from __future__ import annotations

from typing import Any

MANIFEST_SCHEMA = "commons.public-sector-workshare-manifest/v1"
PACKET_SCHEMA = "commons.public-sector-workshare-packet/v1"
MAX_SOURCE_AGE_SECONDS = 7 * 24 * 60 * 60
EXPECTED_COMMERCIAL_STATE = "PROPOSED_NOT_ACCEPTED"
OUTBOUND_STATE = "NOT_AUTHORIZED_TO_SEND"

ALLOWED_AUTHORITIES = {"OFFICIAL_BUYER", "OFFICIAL_PORTAL", "SECONDARY_PUBLIC", "INTERNAL_SCOUT"}
ALLOWED_DEADLINE_AUTHORITIES = set(ALLOWED_AUTHORITIES)
ALLOWED_TARGET_BASIS = {
    "PRIOR_QUALIFIED_MATERIALLY_SIMILAR",
    "PRIOR_RELATED_AWARDEE",
    "PUBLICLY_RELEVANT_VENDOR",
    "ROLE_ARCHETYPE_ONLY",
}
ALLOWED_MODULES = {
    "MIGRATION_EVIDENCE",
    "INTEGRATION_CONFORMANCE",
    "UAT_ACCEPTANCE_EVIDENCE",
    "CUTOVER_REPLAY",
}

MODULE_CATALOG: dict[str, dict[str, Any]] = {
    "MIGRATION_EVIDENCE": {
        "title": "Legacy/data migration evidence",
        "inputs": [
            "source inventory plus immutable extract/file/table digests",
            "source row/object counts and declared business-key rules",
            "target load/export evidence with matching generation identity",
        ],
        "outputs": [
            "deterministic source-to-target reconciliation matrix",
            "exception/ambiguity ledger with exact evidence commitments",
            "repeatable migration receipt suitable for prime/buyer UAT evidence",
        ],
        "acceptance": [
            "every in-scope source object is accounted for exactly once",
            "changed same-identity bytes or duplicate business keys fail closed",
            "counts/digests reconcile or exceptions remain explicitly HOLD",
        ],
        "exclusions": [
            "source-system access or extraction authority",
            "business-record cleanup/deletion decisions",
            "production cutover or buyer acceptance authority",
        ],
    },
    "INTEGRATION_CONFORMANCE": {
        "title": "Interface/integration conformance",
        "inputs": [
            "versioned interface contract or mapping supplied by the prime/buyer",
            "synthetic or approved test payloads with source digests",
            "adapter/test execution evidence from an authorized environment",
        ],
        "outputs": [
            "contract-to-test traceability matrix",
            "deterministic pass/hold evidence by interface and version",
            "replayable failure corpus and regression receipt",
        ],
        "acceptance": [
            "no undocumented field/version coercion is promoted to PASS",
            "retry/idempotency and changed-replay cases are exercised",
            "unsupported or stale contract generations stay HOLD",
        ],
        "exclusions": [
            "live credential custody",
            "external system mutation",
            "solution-architecture/OEM certification claims",
        ],
    },
    "UAT_ACCEPTANCE_EVIDENCE": {
        "title": "UAT/acceptance evidence harness",
        "inputs": [
            "prime/buyer-authored acceptance criteria and requirement IDs",
            "approved synthetic/deidentified scenarios or buyer-provided fixtures",
            "test execution outputs tied to exact build/config generations",
        ],
        "outputs": [
            "requirement-to-scenario acceptance matrix",
            "defect/evidence gap queue without silent pass inflation",
            "content-addressed UAT evidence pack and verifier receipt",
        ],
        "acceptance": [
            "every claimed result binds exact requirement, fixture, build, and run evidence",
            "missing/contradictory evidence remains HOLD",
            "owner/buyer sign-off is represented separately from technical proof",
        ],
        "exclusions": [
            "buyer sign-off or contract acceptance",
            "production deployment authority",
            "fabricated public-sector past performance",
        ],
    },
    "CUTOVER_REPLAY": {
        "title": "Cutover/replay evidence",
        "inputs": [
            "prime-authored cutover plan and rollback checkpoints",
            "pre/post migration or integration evidence generations",
            "authorized rehearsal/replay outputs",
        ],
        "outputs": [
            "step/checkpoint evidence ledger",
            "rehearsal/replay determinism and rollback-readiness report",
            "unresolved exception queue for prime/buyer disposition",
        ],
        "acceptance": [
            "every irreversible step remains externally owner-authorized",
            "rehearsal evidence cannot masquerade as production completion",
            "state drift or missing checkpoints fail closed",
        ],
        "exclusions": [
            "go-live command authority",
            "rollback execution authority",
            "production operations ownership",
        ],
    },
}

COMMERCIAL_SHAPES: tuple[dict[str, Any], ...] = (
    {
        "shape_id": "PAID_FIXED_FEE_PILOT_2_4_WEEK",
        "commercial_state": EXPECTED_COMMERCIAL_STATE,
        "duration_business_days_min": 10,
        "duration_business_days_max": 20,
        "fee_state": "OWNER_INPUT_REQUIRED",
        "payment_path_state": "REQUIRED_BEFORE_AUTHORIZED_OUTBOUND",
        "positioning": "bounded paid workshare pilot with exact inputs, outputs, acceptance tests, and exclusions",
    },
    {
        "shape_id": "PAID_IMPLEMENTATION_WORKSHARE",
        "commercial_state": EXPECTED_COMMERCIAL_STATE,
        "duration_state": "PRIME_SCHEDULE_INPUT_REQUIRED",
        "fee_state": "OWNER_INPUT_REQUIRED",
        "payment_path_state": "REQUIRED_BEFORE_AUTHORIZED_OUTBOUND",
        "positioning": "larger paid subcontract/workshare after prime fit, scope, commercial, and authority gates close",
    },
)
