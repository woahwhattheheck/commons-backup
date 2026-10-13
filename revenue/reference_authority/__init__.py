"""Host-authenticated customer-reference authority controls."""

from .reference_authority import (
    HOST_CURRENT_REGISTRY_PATH,
    HOST_KEY_ENV,
    ReferenceAuthorityError,
    compile_registry,
    evidence_digest,
    normalize_authority_registry,
    normalize_packet,
    opportunity_digest,
    record_digest,
    render_markdown,
    requirement_digest,
    strict_json_loads,
    verify_current,
    verify_historical,
)

__all__ = [
    "HOST_CURRENT_REGISTRY_PATH",
    "HOST_KEY_ENV",
    "ReferenceAuthorityError",
    "compile_registry",
    "evidence_digest",
    "normalize_authority_registry",
    "normalize_packet",
    "opportunity_digest",
    "record_digest",
    "render_markdown",
    "requirement_digest",
    "strict_json_loads",
    "verify_current",
    "verify_historical",
]
