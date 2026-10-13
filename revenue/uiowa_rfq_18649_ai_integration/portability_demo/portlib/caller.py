"""CALLING CODE. This is the file whose invariance IS the portability claim.

Everything the institution's workflow actually does lives here: apply the routing
policy, decide what a person has to look at, and decide what happens when the AI
capability is slow, unreachable, or answers something unusable.

Constraints this file holds, and which test_ai_integration.py enforces mechanically:

  1. It imports ONLY from portlib.port. No provider module, class, wire field name,
     error type, or capability brand appears anywhere in this source.
  2. Its sha256 is recorded on every run of demo_swap.py. Swapping the provider
     produces the SAME hash, because nothing here changes. That is the difference
     between a portability claim and a portability demonstration.
  3. The degraded path never invents an answer. When the capability fails, the item
     goes to a person with the failure class named. An unavailable service produces
     UNKNOWN-equivalent handling, not a default category.
"""

import hashlib
import pathlib

from portlib.port import (
    Document,
    ProviderContractViolation,
    ProviderError,
    ProviderTimeout,
    ProviderUnavailable,
    RoutingDecision,
    RoutingPolicy,
)


def route_document(port, document: Document, policy: RoutingPolicy) -> RoutingDecision:
    """Route one item. The only thing this knows about the capability is the port."""
    try:
        result = port.classify(document)
    except ProviderTimeout as exc:
        return RoutingDecision(
            doc_id=document.doc_id,
            queue=policy.human_review_queue,
            reason=f"capability did not answer in budget ({exc}); routed to a person "
                   f"rather than guessed",
            needs_human_review=True,
            degraded=True,
        )
    except ProviderUnavailable as exc:
        retry = getattr(exc, "retry_after_s", None)
        hint = f"; capability suggested retry after {retry}s" if retry else ""
        return RoutingDecision(
            doc_id=document.doc_id,
            queue=policy.human_review_queue,
            reason=f"capability unreachable ({exc}){hint}; routed to a person rather "
                   f"than guessed",
            needs_human_review=True,
            degraded=True,
        )
    except ProviderContractViolation as exc:
        return RoutingDecision(
            doc_id=document.doc_id,
            queue=policy.human_review_queue,
            reason=f"capability answered outside the agreed contract ({exc}); an "
                   f"unmappable answer is missing evidence, not a low score",
            needs_human_review=True,
            degraded=True,
        )
    except ProviderError as exc:  # future port-level error classes still land safely
        return RoutingDecision(
            doc_id=document.doc_id,
            queue=policy.human_review_queue,
            reason=f"unclassified capability failure ({type(exc).__name__}: {exc})",
            needs_human_review=True,
            degraded=True,
        )

    if result.category in policy.always_review:
        return RoutingDecision(
            doc_id=document.doc_id,
            queue=policy.human_review_queue,
            reason=f"category {result.category!r} is always reviewed by policy "
                   f"(confidence {result.confidence:.2f}: {result.rationale})",
            needs_human_review=True,
        )

    if result.confidence < policy.confidence_floor:
        return RoutingDecision(
            doc_id=document.doc_id,
            queue=policy.human_review_queue,
            reason=f"confidence {result.confidence:.2f} below floor "
                   f"{policy.confidence_floor:.2f}; suggested {result.category!r}",
            needs_human_review=True,
        )

    return RoutingDecision(
        doc_id=document.doc_id,
        queue=f"queue.{result.category}",
        reason=f"confidence {result.confidence:.2f} at or above floor "
               f"{policy.confidence_floor:.2f}: {result.rationale}",
        needs_human_review=False,
    )


def route_documents(port, documents, policy: RoutingPolicy):
    return [route_document(port, doc, policy) for doc in documents]


def summarize_run(decisions):
    """Operational summary. Counts are facts about THIS run, not a quality score."""
    return {
        "items": len(decisions),
        "auto_routed": sum(1 for d in decisions if not d.needs_human_review),
        "to_human_review": sum(1 for d in decisions if d.needs_human_review),
        "degraded": sum(1 for d in decisions if d.degraded),
        "queues": sorted({d.queue for d in decisions}),
    }


def caller_source_sha256() -> str:
    """Hash of THIS file. Recorded on both sides of a provider swap."""
    return hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest()
