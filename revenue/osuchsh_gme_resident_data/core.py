"""Public compatibility surface for the OSU-CHS resident-data prototype."""

from .codec import (
    ALLOWED_FIELDS,
    DIRECT_IDENTIFIERS,
    ROLE_VIEW_FIELDS,
    ROLE_WRITE_FIELDS,
    AuditError,
    ConflictError,
    DataError,
    PermissionDenied,
    StaleWriteError,
    canonical_bytes,
    digest,
    strict_json_loads,
    validate_record,
)
from .migration import MigrationPlan, compile_migration
from .store import ResidentStore

__all__ = [
    "ALLOWED_FIELDS",
    "DIRECT_IDENTIFIERS",
    "ROLE_VIEW_FIELDS",
    "ROLE_WRITE_FIELDS",
    "AuditError",
    "ConflictError",
    "DataError",
    "MigrationPlan",
    "PermissionDenied",
    "ResidentStore",
    "StaleWriteError",
    "canonical_bytes",
    "compile_migration",
    "digest",
    "strict_json_loads",
    "validate_record",
]
