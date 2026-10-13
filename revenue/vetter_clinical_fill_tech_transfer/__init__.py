"""Current-candidate cross-site clinical fill tech-transfer evidence gate.

`compile_transfer` creates a non-authoritative process-time candidate.
`verify_report_current` and `render_markdown` independently cross the fresh
process-time gate that can emit CURRENT_OWNER_REVIEW authority. Deterministic
explicit-time replay is intentionally not re-exported here; use the explicit
`historical` test/replay namespace when historical authority is required.
"""

from .engine import (
    TransferError,
    compile_transfer,
    render_markdown,
    verify_report_current,
)

__all__ = [
    "TransferError",
    "compile_transfer",
    "render_markdown",
    "verify_report_current",
]
