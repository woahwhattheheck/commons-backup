"""FICTIONAL provider BETA -- capability class: self-operated-model.

Invented for UIOWA-080. Deliberately shaped nothing like ALPHA: nested response
envelope, percentage confidence, upper-case category names, a different taxonomy
that has to be MAPPED, and an error carrying a retry hint. If the adapter did not
exist, every one of those differences would be a change in calling code.

BETA's (invented) wire contract:
    request  : {"document": {"body": <str>}, "taxonomy_version": <str>}
    response : {"result": {"category_name": <UPPER str>, "confidence_pct": <int 0..100>,
                           "notes": <str>}, "meta": {...}}
    errors   : BetaUnavailable(retry_after)
"""

from portlib.port import (
    Classification,
    ClassificationPort,
    Document,
    ProviderContractViolation,
    ProviderTimeout,
    ProviderUnavailable,
)


class BetaUnavailable(Exception):
    def __init__(self, message, retry_after):
        super().__init__(message)
        self.retry_after = retry_after


class BetaSlowLane(Exception):
    pass


# BETA uses its own category names. Mapping them is adapter work, not caller work.
_BETA_TO_DOMAIN = {
    "FINANCE_DISPUTE": "billing",
    "IDENTITY_ACCESS": "access",
    "BUILDING_OPS": "facilities",
    "UNSORTED": "other",
}

_BETA_RULES = (
    ("declin", "FINANCE_DISPUTE", 81),
    ("deposit", "FINANCE_DISPUTE", 79),
    ("invoice", "FINANCE_DISPUTE", 85),
    ("badge", "IDENTITY_ACCESS", 88),
    ("password", "IDENTITY_ACCESS", 90),
    ("locked out", "IDENTITY_ACCESS", 92),
    ("leak", "BUILDING_OPS", 87),
    ("thermostat", "BUILDING_OPS", 66),
    ("elevator", "BUILDING_OPS", 90),
)


class _BetaWireClient:
    def __init__(self, fail_mode=None):
        self.fail_mode = fail_mode
        self.calls = 0

    def submit(self, payload: dict) -> dict:
        self.calls += 1
        if self.fail_mode == "down":
            raise BetaUnavailable("beta: node pool draining", retry_after=120)
        if self.fail_mode == "slow":
            raise BetaSlowLane("beta: queue depth above admission threshold")
        if self.fail_mode == "garbage":
            return {"result": {"category_name": "PLEASE_RETRY", "confidence_pct": 55, "notes": ""}}
        text = payload["document"]["body"].lower()
        for needle, cat, pct in _BETA_RULES:
            if needle in text:
                return {"result": {"category_name": cat, "confidence_pct": pct,
                                   "notes": f"beta rule {needle!r}"},
                        "meta": {"taxonomy_version": payload.get("taxonomy_version")}}
        return {"result": {"category_name": "UNSORTED", "confidence_pct": 48,
                           "notes": "beta: below admission signal"},
                "meta": {"taxonomy_version": payload.get("taxonomy_version")}}


class BetaClassificationAdapter(ClassificationPort):
    capability_class = "self-operated-model"

    def __init__(self, policy, fail_mode=None):
        self._client = _BetaWireClient(fail_mode=fail_mode)
        self._policy = policy

    def classify(self, document: Document) -> Classification:
        try:
            raw = self._client.submit({"document": {"body": document.text},
                                       "taxonomy_version": "hri-2026.1"})
        except BetaSlowLane as exc:
            raise ProviderTimeout(f"beta over admission threshold: {exc}") from exc
        except BetaUnavailable as exc:
            raise ProviderUnavailable(f"beta unreachable: {exc}",
                                      retry_after_s=exc.retry_after) from exc

        result = raw.get("result") or {}
        beta_name = result.get("category_name")
        pct = result.get("confidence_pct")

        if beta_name not in _BETA_TO_DOMAIN:
            raise ProviderContractViolation(
                f"beta returned unmapped category {beta_name!r}; the taxonomy map "
                f"must be updated deliberately, not guessed at runtime")
        domain_category = _BETA_TO_DOMAIN[beta_name]
        if domain_category not in self._policy.categories:
            raise ProviderContractViolation(
                f"mapped category {domain_category!r} is outside the institution taxonomy")
        if not isinstance(pct, int) or not (0 <= pct <= 100):
            raise ProviderContractViolation(f"beta confidence_pct unusable: {pct!r}")

        return Classification(
            doc_id=document.doc_id,
            category=domain_category,
            confidence=round(pct / 100.0, 4),   # normalization happens HERE, once
            rationale=result.get("notes") or "beta returned no notes",
            capability_class=self.capability_class,
        )

    def health(self) -> dict:
        return {"reachable": self._client.fail_mode not in ("down", "slow"),
                "capability_class": self.capability_class,
                "calls": self._client.calls}
