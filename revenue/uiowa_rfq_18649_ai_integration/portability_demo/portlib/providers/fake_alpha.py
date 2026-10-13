"""FICTIONAL provider ALPHA -- capability class: hosted-inference-api.

Entirely invented for UIOWA-080. Not a model of, or a stand-in for, any real
commercial product. Its only job is to have a wire shape and an error taxonomy
that are DIFFERENT from provider BETA's, so that the swap demonstration is
actually doing work rather than swapping two identical things.

ALPHA's (invented) wire contract:
    request  : {"input": <str>, "labels": [<str>, ...]}
    response : {"label": <str>, "score": <float 0..1>, "explain": <str>}
    errors   : AlphaTimeout, AlphaRefused
"""

from portlib.port import (
    Classification,
    ClassificationPort,
    Document,
    ProviderContractViolation,
    ProviderTimeout,
    ProviderUnavailable,
)


# --- the "SDK" side of the wall: shapes and exceptions that must never escape ---

class AlphaTimeout(Exception):
    pass


class AlphaRefused(Exception):
    pass


_ALPHA_RULES = (
    ("declin", "billing", 0.93),
    ("deposit", "billing", 0.88),
    ("invoice", "billing", 0.90),
    ("badge", "access", 0.91),
    ("password", "access", 0.86),
    ("locked out", "access", 0.94),
    ("leak", "facilities", 0.89),
    ("thermostat", "facilities", 0.84),
    ("elevator", "facilities", 0.92),
)


class _AlphaWireClient:
    """Stands in for a vendor SDK. Deterministic, offline, no network."""

    def __init__(self, fail_mode=None):
        self.fail_mode = fail_mode
        self.calls = 0

    def infer(self, payload: dict) -> dict:
        self.calls += 1
        if self.fail_mode == "timeout":
            raise AlphaTimeout("alpha: deadline exceeded")
        if self.fail_mode == "refused":
            raise AlphaRefused("alpha: endpoint refused connection")
        if self.fail_mode == "garbage":
            return {"label": "sentiment_positive", "score": 4.7, "explain": ""}
        text = payload["input"].lower()
        for needle, label, score in _ALPHA_RULES:
            if needle in text:
                return {"label": label, "score": score,
                        "explain": f"alpha matched token {needle!r}"}
        return {"label": "other", "score": 0.55, "explain": "alpha found no strong signal"}


# ------------------------------- the adapter: the ONLY place the wire shape lives

class AlphaClassificationAdapter(ClassificationPort):
    capability_class = "hosted-inference-api"

    def __init__(self, policy, fail_mode=None):
        self._client = _AlphaWireClient(fail_mode=fail_mode)
        self._policy = policy

    def classify(self, document: Document) -> Classification:
        try:
            raw = self._client.infer({"input": document.text,
                                      "labels": list(self._policy.categories)})
        except AlphaTimeout as exc:
            # Vendor exception translated at the wall. Callers never see AlphaTimeout.
            raise ProviderTimeout(f"alpha did not answer in budget: {exc}") from exc
        except AlphaRefused as exc:
            raise ProviderUnavailable(f"alpha unreachable: {exc}", retry_after_s=30) from exc

        label = raw.get("label")
        score = raw.get("score")
        if label not in self._policy.categories:
            raise ProviderContractViolation(
                f"alpha returned label {label!r}, outside the institution taxonomy")
        if not isinstance(score, (int, float)) or not (0.0 <= float(score) <= 1.0):
            raise ProviderContractViolation(f"alpha returned unnormalizable score {score!r}")

        return Classification(
            doc_id=document.doc_id,
            category=label,
            confidence=float(score),
            rationale=raw.get("explain") or "alpha returned no explanation",
            capability_class=self.capability_class,
        )

    def health(self) -> dict:
        return {"reachable": self._client.fail_mode not in ("timeout", "refused"),
                "capability_class": self.capability_class,
                "calls": self._client.calls}
