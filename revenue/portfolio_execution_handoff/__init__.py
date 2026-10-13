"""Source-bound owner handoff manifests for selected revenue opportunities."""
from .handoff import (
    HandoffError,
    SCHEMA,
    RECEIPT_SCHEMA,
    compile_handoff,
    render_markdown,
    verify_receipt,
)
__all__ = ["HandoffError","SCHEMA","RECEIPT_SCHEMA","compile_handoff","render_markdown","verify_receipt"]
