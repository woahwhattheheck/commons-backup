"""Verified offline Git repository portability primitives."""

from .portability import (
    INVENTORY_SCHEMA,
    PLAN_SCHEMA,
    SNAPSHOT_SCHEMA,
    PortabilityError,
    ValidationError,
    VerificationError,
    canonical_json,
    compile_migration_plan,
    create_snapshot,
    loads_strict,
    verify_snapshot,
    write_migration_plan,
)

__all__ = [
    "INVENTORY_SCHEMA",
    "PLAN_SCHEMA",
    "SNAPSHOT_SCHEMA",
    "PortabilityError",
    "ValidationError",
    "VerificationError",
    "canonical_json",
    "compile_migration_plan",
    "create_snapshot",
    "loads_strict",
    "verify_snapshot",
    "write_migration_plan",
]
