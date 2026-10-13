from . import engine as _engine
from .strict_json import canonical_json, digest, parse_strict_json

# Install the hardened parser/canonical graph before importing the authority
# layer. Historical/test helpers intentionally remain injectable; the public
# CURRENT surface is wrapped by current_runtime after authority is loaded.
_engine.parse_strict_json = parse_strict_json
_engine.canonical_json = canonical_json
_engine.digest = digest

from .authority import AuthorityError, authority_subject
from .current_runtime import (
    compile_current,
    render_current_markdown,
    verify_current_authority,
)
from .engine import (
    DealEconomicsError,
    compile_report as compile_arithmetic_report,
    render_markdown as render_arithmetic_markdown,
    verify_historical as verify_arithmetic_historical,
)

__all__ = [
    "AuthorityError",
    "DealEconomicsError",
    "authority_subject",
    "canonical_json",
    "compile_arithmetic_report",
    "compile_current",
    "digest",
    "parse_strict_json",
    "render_arithmetic_markdown",
    "render_current_markdown",
    "verify_arithmetic_historical",
    "verify_current_authority",
]
