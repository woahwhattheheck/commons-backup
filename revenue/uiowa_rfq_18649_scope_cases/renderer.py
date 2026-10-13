"""Load, validate, and render UIOWA-139 disposition packets."""

from __future__ import annotations

import json
import os

try:
    from .canonical import (
        AUTHORITY,
        BASELINE,
        EXHIBIT_BLOB,
        EXHIBIT_PATH,
        SCHEMA,
        SECTION_2_TRIGGERS,
    )
    from .dispositions import (
        REQUIRED_CASE_FIELDS,
        CaseError,
        classify,
        clause_records,
    )
except ImportError:
    from canonical import (
        AUTHORITY,
        BASELINE,
        EXHIBIT_BLOB,
        EXHIBIT_PATH,
        SCHEMA,
        SECTION_2_TRIGGERS,
    )
    from dispositions import (
        REQUIRED_CASE_FIELDS,
        CaseError,
        classify,
        clause_records,
    )

MAX_FILE_BYTES = 200_000
PHASES = {"kickoff", "draft", "final"}
EFFORT_LABEL = "HYPOTHETICAL / NOT ACCEPTED"


def load_case(path):
    st = os.stat(path)
    if st.st_size > MAX_FILE_BYTES:
        raise CaseError("case %r exceeds %d bytes" % (path, MAX_FILE_BYTES))
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise CaseError("case must be a JSON object")
    validate_case(data)
    return data


def validate_case(data):
    if data.get("schema") != SCHEMA:
        raise CaseError("unsupported schema %r" % (data.get("schema"),))
    for field in REQUIRED_CASE_FIELDS:
        if field not in data:
            raise CaseError("case missing required field %r" % field)
    req = data["request"]
    art = data["artifact"]
    effort = data["effort"]
    if not isinstance(req, dict) or not req.get("class") or not req.get("exact_edit"):
        raise CaseError("request must include class and exact_edit")
    if not isinstance(art, dict):
        raise CaseError("artifact must be an object")
    for key in ("phase", "id", "before", "after"):
        if key not in art:
            raise CaseError("artifact missing %r" % key)
    if art["phase"] not in PHASES:
        raise CaseError("artifact.phase %r is not kickoff/draft/final" % art["phase"])
    expected = classify(req["class"])
    if data["disposition"] != expected["code"]:
        raise CaseError(
            "case disposition %r does not match request class %r (expected %r)"
            % (data["disposition"], req["class"], expected["code"])
        )
    if data["payment_effect"] != "NONE_SECTION_2_UNCHANGED":
        raise CaseError("packets must not rewrite Section 2 payment effect")
    if data.get("commercial_triggers_preserved") is not True:
        raise CaseError("commercial_triggers_preserved must be true")
    if not isinstance(data["source_clauses"], list) or not data["source_clauses"]:
        raise CaseError("source_clauses must be a non-empty list")
    clause_records(data["source_clauses"])
    if not isinstance(effort, dict):
        raise CaseError("effort must be an object")
    if effort.get("label") != EFFORT_LABEL:
        raise CaseError("effort.label must be %r" % EFFORT_LABEL)
    if expected["new_scope"] is False and effort.get("usd_incremental") not in (0, None):
        raise CaseError("non-scope dispositions cannot invent an incremental fee")
    if data["disposition"] == "EVIDENCE_DEPENDENCY_HOLD":
        if art.get("after_state") == "supported" and art.get("before_state") != "supported":
            raise CaseError("unknown/new evidence must not be promoted to supported")
    if data["disposition"] == "PRIME_JUDGMENT_NOT_DEFECT":
        if art.get("technical_conclusion_changed"):
            raise CaseError("judgment packets must not silently rewrite a supported conclusion")
    if data.get("product_vendor_recommendation"):
        raise CaseError("packets must not emit a product/vendor recommendation")
    return expected


def load_cases_dir(path):
    names = sorted(
        n for n in os.listdir(path) if n.endswith(".json") and not n.startswith(".")
    )
    if len(names) != 6:
        raise CaseError("expected six case files, found %d" % len(names))
    cases = []
    seen = set()
    for name in names:
        case = load_case(os.path.join(path, name))
        if case["id"] in seen:
            raise CaseError("duplicate case id %r" % case["id"])
        seen.add(case["id"])
        cases.append(case)
    required = {
        "CASE-01",
        "CASE-02",
        "CASE-03",
        "CASE-04",
        "CASE-05",
        "CASE-06",
    }
    if seen != required:
        raise CaseError("case ids %r do not match %r" % (sorted(seen), sorted(required)))
    return cases


def enrich(case):
    spec = classify(case["request"]["class"])
    return {
        "schema": SCHEMA,
        "exhibit": {"path": EXHIBIT_PATH, "blob": EXHIBIT_BLOB},
        "baseline": dict(BASELINE),
        "section_2_triggers": [dict(x) for x in SECTION_2_TRIGGERS],
        "authority": dict(AUTHORITY),
        "disposition_spec": spec,
        "clauses": clause_records(case["source_clauses"]),
        "case": case,
        "notes": [
            "$%d is TJLabs subcontract workshare, not the prime all-inclusive bid fee."
            % BASELINE["workshare_base_usd"],
            "Artifact cure is not a payment trigger rewrite (Section 2).",
            "Unknown evidence is never promoted to a supported state.",
            "Technical disagreement is not automatically a defect.",
            "New work is proposed, not silently added.",
            "Effort figures are HYPOTHETICAL / NOT ACCEPTED.",
            "This packet is not an invoice, acceptance, submission, or schedule.",
        ],
    }


def render_markdown(enriched):
    case = enriched["case"]
    art = case["artifact"]
    effort = case["effort"]
    req = case["request"]
    usd = effort.get("usd_incremental")
    usd_s = "HOLD" if usd is None else "$" + "{:,}".format(usd)
    lines = [
        "# %s — %s" % (case["id"], case["title"]),
        "",
        "Disposition: **%s**." % case["disposition"],
        "Request class: `%s`." % req["class"],
        "Phase: **%s** / artifact `%s`." % (art["phase"], art["id"]),
        "Payment effect: **%s**." % case["payment_effect"],
        "Exhibit blob: `%s`." % enriched["exhibit"]["blob"],
        "",
        "## Request",
        "",
        req.get("summary", ""),
        "",
        "Exact example edit:",
        "",
        "```",
        req["exact_edit"].rstrip(),
        "```",
        "",
        "## Before",
        "",
        "```",
        art["before"].rstrip(),
        "```",
        "",
        "## After",
        "",
        "```",
        art["after"].rstrip(),
        "```",
        "",
        "## Rationale",
        "",
        case["rationale"],
        "",
        "## Source clauses",
        "",
    ]
    for cl in enriched["clauses"]:
        lines.append("- **§%s** `%s` — %s" % (cl["section"], cl["key"], cl["rule"]))
    hours = effort.get("hours_hypothetical")
    lines += [
        "",
        "## Effort (labeled hypothetical)",
        "",
        "- Class: `%s`" % effort.get("class"),
        "- Hours (hypothetical): %s" % hours,
        "- Incremental USD: %s" % usd_s,
        "- Label: **%s**" % effort.get("label"),
        "",
        "## Section 2 triggers (unchanged)",
        "",
        "| Milestone | Share | Amount | Trigger | Acceptance-triggered |",
        "|---|---:|---:|---|---|",
    ]
    for t in enriched["section_2_triggers"]:
        lines.append(
            "| %s | %s%% | $%s | %s | %s |"
            % (
                t["milestone"],
                t["share_pct"],
                "{:,}".format(t["amount_usd"]),
                t["trigger"],
                t["acceptance_triggered"],
            )
        )
    lines += ["", "## Notes", ""]
    for n in enriched["notes"]:
        lines.append("- %s" % n)
    return "\n".join(lines) + "\n"


def render_decision_aid():
    lines = [
        "# Clause-linked decision aid (not an automatic engine)",
        "",
        "Use this to distinguish ordinary artifact cure from judgment, evidence",
        "dependencies, and new work. It does not accept, reject, invoice, or",
        "expand the $24,000 workshare.",
        "",
        "| Request class | Disposition | Governing clauses | Incremental fee |",
        "|---|---|---|---|",
        "| broken citation / missing source trace | ARTIFACT_CURE_IN_SCOPE | S5_2_1_TRACE, S7_CURE_NOT_SCOPE, S2_TRIGGERS | $0 |",
        "| disputed supported conclusion | PRIME_JUDGMENT_NOT_DEFECT | S5_3_DISAGREEMENT, S9_PRIME_JUDGMENT | $0 |",
        "| newly supplied evidence | EVIDENCE_DEPENDENCY_HOLD | S5_2_3_NO_PROMOTE, S3_NO_FABRICATE, S5_2_6_COMMENTS | $0 until compiled; unknown not promoted |",
        "| wording preference | PRIME_JUDGMENT_NOT_DEFECT | S5_2_6_COMMENTS, S9_PRIME_JUDGMENT | $0 |",
        "| extra stakeholder / AIS group | PROPOSED_NEW_SCOPE | S7_CHANGE_CONTROL | hypothetical; not silently added |",
        "| new deliverable | PROPOSED_NEW_SCOPE | S7_CHANGE_CONTROL, S9_PRIME_JUDGMENT | hypothetical; not silently added |",
        "| product/vendor recommendation | VENDOR_RECOMMENDATION_REFUSED | S4_5_VENDOR, S7_VENDOR_NOT_CHANGE | refused |",
        "",
        "## Section 2 reminder",
        "",
        "- Kickoff payment trigger = written authorization (not minimum-input).",
        "- Draft payment trigger = delivery (not acceptance/cure).",
        "- Final payment trigger = acceptance of the final package.",
        "",
        "Pinned exhibit: `%s` blob `%s`." % (EXHIBIT_PATH, EXHIBIT_BLOB),
        "",
    ]
    return "\n".join(lines)


def bundle(cases):
    enriched = [enrich(c) for c in cases]
    return {
        "schema": SCHEMA,
        "exhibit": {"path": EXHIBIT_PATH, "blob": EXHIBIT_BLOB},
        "baseline": dict(BASELINE),
        "section_2_triggers": [dict(x) for x in SECTION_2_TRIGGERS],
        "authority": dict(AUTHORITY),
        "decision_aid": {
            "automatic_engine": False,
            "auto_accept": False,
            "auto_scope_expand": False,
        },
        "cases": enriched,
    }
