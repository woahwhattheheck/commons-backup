"""UIOWA-132 cross-document commercial-facts checker for RFQ 18649."""

try:
    from .canonical import CANONICAL
    from .checker import (
        DocumentFacts,
        FactsError,
        Finding,
        check_bundle,
        check_document,
        load_bundle,
        render_facts_markdown,
    )
    from .repair import repair_document, repair_text
except ImportError:
    from canonical import CANONICAL
    from checker import (
        DocumentFacts,
        FactsError,
        Finding,
        check_bundle,
        check_document,
        load_bundle,
        render_facts_markdown,
    )
    from repair import repair_document, repair_text

__all__ = [
    "CANONICAL",
    "DocumentFacts",
    "FactsError",
    "Finding",
    "check_bundle",
    "check_document",
    "load_bundle",
    "render_facts_markdown",
    "repair_document",
    "repair_text",
]
