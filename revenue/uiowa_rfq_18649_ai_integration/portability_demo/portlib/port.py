"""The port: domain-shaped types and one interface the calling code depends on.

Portability is usually asserted ("we'll put an abstraction layer in front of it")
and never demonstrated. This file is the demonstration. The rule it encodes:

    The port is shaped like the ORGANIZATION'S problem, not like any provider's API.

If the interface were shaped like a vendor wire format -- prompt strings in, raw
JSON out -- then swapping providers would change every caller, and the abstraction
would be decorative. Here the caller asks for a Classification of a Document. How
that is obtained (hosted capability, self-operated model, rules engine, a person)
is entirely behind the port.

Nothing in this module names or imports any provider.
"""

from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------- domain types

@dataclass(frozen=True)
class Document:
    """An inbound item the institution needs categorized. Domain vocabulary only."""
    doc_id: str
    text: str
    source: str = "intake"


@dataclass(frozen=True)
class Classification:
    """The domain answer. Note what is NOT here: no token counts, no model id,
    no vendor response envelope. Those are adapter-internal concerns."""
    doc_id: str
    category: str
    confidence: float          # normalized 0.0-1.0 by the adapter, always
    rationale: str
    capability_class: str      # e.g. "hosted-inference-api", "self-operated-model"
    degraded: bool = False     # True when produced by the fallback path, not the AI


@dataclass(frozen=True)
class RoutingDecision:
    """What the calling workflow actually does with a Classification."""
    doc_id: str
    queue: str
    reason: str
    needs_human_review: bool
    degraded: bool = False


@dataclass(frozen=True)
class RoutingPolicy:
    """Institution policy, not provider config. Owned by the workflow team."""
    categories: tuple = ("billing", "access", "facilities", "other")
    confidence_floor: float = 0.70
    human_review_queue: str = "queue.human_review"
    # Which categories always get a person in the loop regardless of confidence.
    always_review: tuple = ("billing",)


# ------------------------------------------------------- port-level exceptions

class ProviderError(Exception):
    """Base class. Callers catch THESE, never a vendor SDK's exception type.

    Error-taxonomy coupling is one of the most expensive and least noticed
    portability costs: if `except SomeVendorTimeout:` appears in workflow code,
    every one of those call sites changes on a swap.
    """


class ProviderTimeout(ProviderError):
    """The capability did not answer inside the caller's latency budget."""


class ProviderUnavailable(ProviderError):
    """The capability could not be reached at all."""
    def __init__(self, message, retry_after_s=None):
        super().__init__(message)
        self.retry_after_s = retry_after_s


class ProviderContractViolation(ProviderError):
    """The adapter got something it cannot honestly map to the domain type.

    Deliberately NOT swallowed into a low-confidence guess. An unmappable answer
    is missing evidence, and missing evidence is not a score.
    """


# ----------------------------------------------------------------- the port

class ClassificationPort:
    """The single interface the calling code is allowed to depend on."""

    capability_class = "abstract"

    def classify(self, document: Document) -> Classification:
        raise NotImplementedError

    def health(self) -> dict:
        """Coarse reachability signal. Shape is domain-defined, not vendor-defined."""
        raise NotImplementedError


# ------------------------------------------------- contract conformance check

REQUIRED_PORT_METHODS = ("classify", "health")


def check_conformance(port, policy: RoutingPolicy, probe: Optional[Document] = None) -> dict:
    """Run any candidate implementation against the same contract.

    This is what makes a swap an engineering decision rather than a leap: the
    replacement must pass the identical checks before it is wired in.
    """
    probe = probe or Document(doc_id="probe-0", text="card declined on my deposit", source="conformance")
    findings = []
    ok = True

    for name in REQUIRED_PORT_METHODS:
        if not callable(getattr(port, name, None)):
            findings.append(f"missing required port method: {name}()")
            ok = False
    if not ok:
        return {"conformant": False, "findings": findings}

    try:
        result = port.classify(probe)
    except ProviderError as exc:
        return {"conformant": False,
                "findings": [f"probe raised a port-level error (acceptable at runtime, "
                             f"not acceptable during conformance): {type(exc).__name__}"]}

    if not isinstance(result, Classification):
        findings.append(f"classify() returned {type(result).__name__}, not Classification")
        ok = False
    else:
        if result.doc_id != probe.doc_id:
            findings.append("classify() did not preserve doc_id")
            ok = False
        if not isinstance(result.confidence, float) or not (0.0 <= result.confidence <= 1.0):
            findings.append(f"confidence not normalized to 0.0-1.0: {result.confidence!r}")
            ok = False
        if result.category not in policy.categories:
            findings.append(f"category {result.category!r} is outside the institution's "
                            f"taxonomy {policy.categories}")
            ok = False
        if not result.rationale:
            findings.append("empty rationale: reviewers cannot audit an unexplained routing")
            ok = False

    health = port.health()
    if not isinstance(health, dict) or "reachable" not in health:
        findings.append("health() must return a dict containing 'reachable'")
        ok = False

    return {"conformant": ok, "findings": findings}
