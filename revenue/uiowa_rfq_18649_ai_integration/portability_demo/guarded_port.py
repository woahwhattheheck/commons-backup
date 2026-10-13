"""Validate every toy classification before the unchanged caller can route it."""
from __future__ import annotations

import math

from portlib.port import (
    Classification, ClassificationPort, Document, ProviderContractViolation,
    ProviderError, RoutingPolicy,
)


def _text(value: object) -> bool:
    return type(value) is str and bool(value.strip())


class GuardedPort(ClassificationPort):
    """Domain validation, not a sandbox for an untrusted in-process adapter."""

    def __init__(self, adapter: ClassificationPort, policy: RoutingPolicy):
        if type(policy) is not RoutingPolicy:
            raise ValueError("expected RoutingPolicy")
        if (type(policy.categories) is not tuple or not policy.categories
                or not all(_text(v) for v in policy.categories)
                or len(set(policy.categories)) != len(policy.categories)
                or type(policy.always_review) is not tuple
                or not all(_text(v) for v in policy.always_review)
                or not set(policy.always_review).issubset(policy.categories)
                or not _text(policy.human_review_queue)
                or type(policy.confidence_floor) is not float
                or not math.isfinite(policy.confidence_floor)
                or not 0.0 <= policy.confidence_floor <= 1.0):
            raise ValueError("invalid routing policy")
        if (not callable(getattr(adapter, "classify", None))
                or not callable(getattr(adapter, "health", None))
                or not _text(getattr(adapter, "capability_class", None))):
            raise ValueError("adapter must implement the classification port")
        self._adapter = adapter
        self._policy = policy
        self.capability_class = adapter.capability_class

    def classify(self, document: Document) -> Classification:
        if (type(document) is not Document or not _text(document.doc_id)
                or not _text(document.text) or not _text(document.source)):
            raise ValueError("expected a document with nonblank domain fields")
        try:
            result = self._adapter.classify(document)
        except ProviderError:
            raise
        except Exception as exc:
            # Keep provider-specific errors and payloads out of routing evidence.
            raise ProviderContractViolation("adapter raised a non-port error") from exc
        if (type(result) is not Classification
                or type(result.doc_id) is not str or result.doc_id != document.doc_id
                or type(result.category) is not str
                or result.category not in self._policy.categories
                or type(result.confidence) is not float
                or not math.isfinite(result.confidence)
                or not 0.0 <= result.confidence <= 1.0
                or not _text(result.rationale)
                or type(result.capability_class) is not str
                or result.capability_class != self.capability_class
                or type(result.degraded) is not bool):
            raise ProviderContractViolation("invalid classification response")
        # The preserved caller ignores Classification.degraded on its success path.
        if result.degraded:
            raise ProviderContractViolation("degraded classification requires a person")
        return result

    def health(self) -> dict:
        try:
            result = self._adapter.health()
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderContractViolation("adapter health raised a non-port error") from exc
        if (type(result) is not dict or type(result.get("reachable")) is not bool
                or result.get("capability_class") != self.capability_class):
            raise ProviderContractViolation("invalid health response")
        return {"reachable": result["reachable"], "capability_class": self.capability_class}
