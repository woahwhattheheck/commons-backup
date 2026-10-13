"""Disposition taxonomy. Not an automatic acceptance or payment engine."""

from __future__ import annotations

try:
    from .canonical import AUTHORITY, CLAUSES, SECTION_2_TRIGGERS
except ImportError:
    from canonical import AUTHORITY, CLAUSES, SECTION_2_TRIGGERS

DISPOSITIONS = {
    "ARTIFACT_CURE_IN_SCOPE": {
        "kind": "cure",
        "new_scope": False,
        "defect": True,
        "payment_effect": "NONE_SECTION_2_UNCHANGED",
        "summary": "Genuine TJLabs artifact nonconformance is cured in-scope at $0 incremental.",
    },
    "PRIME_JUDGMENT_NOT_DEFECT": {
        "kind": "judgment",
        "new_scope": False,
        "defect": False,
        "payment_effect": "NONE_SECTION_2_UNCHANGED",
        "summary": "Technical disagreement or wording preference is not an artifact defect.",
    },
    "EVIDENCE_DEPENDENCY_HOLD": {
        "kind": "evidence",
        "new_scope": False,
        "defect": False,
        "payment_effect": "NONE_SECTION_2_UNCHANGED",
        "summary": "New or unknown evidence is registered; cells stay HOLD until compiled. Unknown is not promoted.",
    },
    "PROPOSED_NEW_SCOPE": {
        "kind": "scope",
        "new_scope": True,
        "defect": False,
        "payment_effect": "NONE_SECTION_2_UNCHANGED",
        "summary": "Material new work is proposed, not silently added to the $24,000 base.",
    },
    "VENDOR_RECOMMENDATION_REFUSED": {
        "kind": "exclusion",
        "new_scope": False,
        "defect": False,
        "payment_effect": "NONE_SECTION_2_UNCHANGED",
        "summary": "Specific product/vendor recommendation is a controlling RFQ exclusion, not change-control.",
    },
}

REQUEST_CLASS_TO_DISPOSITION = {
    "broken_citation": "ARTIFACT_CURE_IN_SCOPE",
    "disputed_supported_conclusion": "PRIME_JUDGMENT_NOT_DEFECT",
    "newly_supplied_evidence": "EVIDENCE_DEPENDENCY_HOLD",
    "wording_preference": "PRIME_JUDGMENT_NOT_DEFECT",
    "extra_stakeholder_group": "PROPOSED_NEW_SCOPE",
    "new_deliverable": "PROPOSED_NEW_SCOPE",
    "product_vendor_recommendation": "VENDOR_RECOMMENDATION_REFUSED",
}

REQUIRED_CASE_FIELDS = (
    "schema",
    "id",
    "title",
    "request",
    "artifact",
    "source_clauses",
    "disposition",
    "rationale",
    "effort",
    "commercial_triggers_preserved",
    "payment_effect",
)


def classify(request_class):
    if request_class not in REQUEST_CLASS_TO_DISPOSITION:
        raise CaseError("unknown request class %r" % request_class)
    code = REQUEST_CLASS_TO_DISPOSITION[request_class]
    spec = dict(DISPOSITIONS[code])
    spec["code"] = code
    spec["authority"] = dict(AUTHORITY)
    spec["section_2"] = [dict(x) for x in SECTION_2_TRIGGERS]
    return spec


def clause_records(keys):
    out = []
    for key in keys:
        if key not in CLAUSES:
            raise CaseError("unknown clause key %r" % key)
        rec = dict(CLAUSES[key])
        rec["key"] = key
        out.append(rec)
    return out


class CaseError(Exception):
    """Packet cannot be rendered without inventing a required field."""
