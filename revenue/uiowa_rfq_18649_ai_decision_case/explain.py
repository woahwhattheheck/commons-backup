"""Render the decision as an explanation -- and then audit that explanation.

WHY THE AUDIT EXISTS.

Producing a persuasive narrative about an AI workflow is the easiest part of
this job and the least trustworthy. A fluent paragraph containing "roughly 40%
faster" reads exactly like a paragraph containing a measured number, and a
reader cannot tell them apart. The only durable defence is mechanical: every
line of the explanation that carries a quantity must cite a record ID, and
every cited ID must resolve to a record that is actually in the case.

So the renderer emits citations, and audit_explanation() re-reads its own
output and fails the run if any quantity is uncited (UNCITED_QUANTITY) or any
citation dangles (DANGLING_CITATION). The audit is run against the real
rendered text, not against the data structure that produced it, so a renderer
bug that drops a citation is caught rather than trusted away.

This is deliberately strict. It is cheaper to add a citation than to defend an
unsourced number in front of leadership.
"""
from __future__ import annotations

import re

from case import (BENEFICIAL, UNCERTAIN, UNDECIDABLE, UNFAVOURABLE, Decision)
from model import Case, is_known

_CITATION_RE = re.compile(r"\[([A-Z][A-Z0-9\-]*(?:\s*,\s*[A-Z][A-Z0-9\-]*)*)\]")
_DIGIT_RE = re.compile(r"\d")

VERDICT_SENTENCE = {
    BENEFICIAL: "the recorded assisted workflow uses less human effort than the "
                "manual baseline across the declared range; the capacity valuation is positive",
    UNFAVOURABLE: "the recorded assisted workflow uses MORE human effort than the "
                  "manual baseline across the declared range; the capacity valuation is negative",
    UNCERTAIN: "the net effect crosses zero inside the declared assumption range, "
               "so which approach is cheaper is not established",
    UNDECIDABLE: "the comparison cannot be made, because required effort was never recorded",
}


def cite(*ids: str) -> str:
    return "[" + ", ".join(ids) + "]"


def _n(value, digits: int = 1) -> str:
    if not is_known(value):
        return "UNKNOWN"
    return f"{float(value):,.{digits}f}"


def _doc_ids(case: Case, variant: str) -> list[str]:
    return [d.id for d in case.docs_for(variant)]


def _event_ids(case: Case, variant: str, kinds: tuple[str, ...]) -> list[str]:
    return sorted(e.id for d in case.docs_for(variant)
                  for e in d.events if e.kind in kinds)


def _qm_ids(case: Case, variant: str) -> list[str]:
    doc_ids = set(_doc_ids(case, variant))
    return sorted(q.id for q in case.quality if q.document_id in doc_ids)


def render(case: Case, decision: Decision) -> str:
    L: list[str] = []
    L.append(f"# AI decision case — {case.workflow}")
    L.append("")
    L.append("**SYNTHETIC.** Every document, measurement, effort record and cost "
             "assumption below is invented for demonstration. Nothing here is a "
             "University of Iowa finding, measurement or price.")
    L.append("")
    L.append("## Verdict")
    L.append("")
    L.append(f"**{decision.verdict}** — {VERDICT_SENTENCE[decision.verdict]}. "
             + cite(case.case_id))
    L.append("")
    for reason in decision.reasons:
        L.append(f"- {reason} " + cite(case.case_id))
    L.append("")

    if decision.verdict == UNDECIDABLE:
        L.append("## What would make this decidable")
        L.append("")
        L.append("The missing records named above are the entire blocker. They are "
                 "not estimated, not averaged from the documents that were recorded, "
                 "and not treated as zero effort — an unrecorded checking step is "
                 "the most likely place for the cost to hide. " + cite(case.case_id))
        L.append("")
        L.append("## Still UNKNOWN")
        L.append("")
        L.append("Net value, net effort and the generation speed-up are all UNKNOWN "
                 "for this case. No figure is offered. " + cite(case.case_id))
        L.append("")
        return "\n".join(L)

    base, asst = decision.baseline, decision.assisted
    gen_ids = _event_ids(case, "BASELINE", ("AUTHOR",)) + _event_ids(case, "ASSISTED", ("GENERATE",))

    L.append("## What the headline says")
    L.append("")
    L.append(f"Producing a first draft took a mean of {_n(asst.mean_component('generation'))} "
             f"minutes with assistance against {_n(base.mean_component('generation'))} minutes "
             f"authored manually — a {_n(decision.headline_ratio, 2)}x speed-up **on the "
             f"drafting step alone**. " + cite(*gen_ids))
    L.append("")
    L.append("That figure is true and it is not the basis for a decision. It measures "
             "the one step that got cheaper. " + cite(case.case_id))
    L.append("")

    L.append("## What delivery actually costs")
    L.append("")
    L.append("| | manual baseline | with assistance |")
    L.append("|---|---|---|")
    both = _doc_ids(case, "BASELINE") + _doc_ids(case, "ASSISTED")
    L.append(f"| mean minutes before acceptance | {_n(base.mean_component('pre_accept'))} | "
             f"{_n(asst.mean_component('pre_accept'))} | " + cite(*both))
    L.append(f"| mean minutes after acceptance | {_n(base.mean_component('post_accept'))} | "
             f"{_n(asst.mean_component('post_accept'))} | " + cite(*both))
    L.append(f"| mean minutes per delivered document | {_n(base.mean_total())} | "
             f"{_n(asst.mean_total())} | " + cite(*both))
    L.append(f"| observed range across documents | {_n(base.min_total())}–{_n(base.max_total())} | "
             f"{_n(asst.min_total())}–{_n(asst.max_total())} | " + cite(*both))
    L.append("")

    net_low, net_mid, net_high = decision.net_minutes_per_doc
    # Report the range in the SAME direction as the sentence. A signed range
    # printed under a sentence that already said "costs an extra" reads as a
    # saving to anyone skimming, which is the wrong way for a number to be
    # misread in a leadership paper.
    if net_mid > 0:
        L.append(f"Per delivered document, assistance saves {_n(net_mid)} minutes at "
                 f"the midpoint, with an observed range of {_n(net_low)} to "
                 f"{_n(net_high)} minutes saved. The range is the spread actually "
                 f"seen across the recorded documents, not an assumed tolerance. "
                 + cite(*both))
    else:
        L.append(f"Per delivered document, assistance costs an extra "
                 f"{_n(abs(net_mid))} minutes at the midpoint, with an observed range "
                 f"of {_n(abs(net_high))} to {_n(abs(net_low))} minutes extra. The "
                 f"range is the spread actually seen across the recorded documents, "
                 f"not an assumed tolerance. " + cite(*both))
    L.append("")

    post_delta = asst.mean_component("post_accept") - base.mean_component("post_accept")
    if post_delta > 0:
        rework_ids = _event_ids(case, "ASSISTED", ("REWORK_AFTER_ACCEPT", "MAINTENANCE_EDIT"))
        L.append("## Where the difference comes from")
        L.append("")
        L.append(f"Work arriving **after** the document was accepted adds "
                 f"{_n(post_delta)} minutes per document relative to the manual baseline. "
                 f"This is the cost the drafting-speed headline cannot see. "
                 + cite(*rework_ids))
        L.append("")

    L.append("## Quality")
    L.append("")
    aq, bq = decision.assisted_quality, decision.baseline_quality
    L.append(f"Assisted drafts scored {_n(aq.mean_completeness, 3)} mean completeness "
             f"against {_n(bq.mean_completeness, 3)} for manual drafts, over "
             f"{aq.documents_measured} and {bq.documents_measured} measured documents. "
             + cite(*(_qm_ids(case, "ASSISTED") + _qm_ids(case, "BASELINE"))))
    L.append("")
    if decision.quality_risk:
        L.append(f"**Quality risk:** {aq.fabricated_references_total} fabricated "
                 f"references survived review into accepted documents "
                 f"({', '.join(aq.documents_with_fabrications)}). This is reported "
                 f"separately from the cost result and is never averaged into it — a "
                 f"cheaper document that is wrong is not a better outcome. "
                 + cite(*_qm_ids(case, "ASSISTED")))
        L.append("")

    L.append("## Modeled capacity value and the assumptions behind it")
    L.append("")
    lo, hi = decision.net_money_over_horizon
    asm = sorted(case.assumptions.values(), key=lambda a: a.name)
    L.append(f"Over the declared horizon the modeled capacity value lies between {_n(lo, 0)} and "
             f"{_n(hi, 0)} currency units. " + cite(*(both + [a.id for a in asm])))
    L.append(f"At nominal assumptions, the signed capacity change is "
             f"{_n(decision.nominal_capacity_hours, 2)} hours, valued at "
             f"{_n(decision.nominal_capacity_value, 2)} currency units. "
             + cite(*(both + [a.id for a in asm])))
    L.append("")
    L.append("Cash cost, cash savings and realized opportunity value are UNKNOWN. "
             "This model has no integration, platform, metered-service or cash-conversion "
             "inputs. A positive capacity valuation is not cash savings or a full "
             "investment recommendation. " + cite(case.case_id))
    L.append("")
    L.append("| assumption | value | declared range | basis |")
    L.append("|---|---|---|---|")
    for a in asm:
        L.append(f"| {a.name} | {_n(a.value, 2)} {a.unit} | {_n(a.low, 2)}–{_n(a.high, 2)} | "
                 f"{a.basis} | " + cite(a.id))
    L.append("")
    L.append("These are stated assumptions, not measurements. Replacing any of them "
             "re-runs the case and re-renders this explanation. " + cite(*[a.id for a in asm]))
    L.append("")
    return "\n".join(L)


# --------------------------------------------------------------------------
# the audit
# --------------------------------------------------------------------------

def audit_explanation(text: str, case: Case) -> list[str]:
    """Return a list of problems. Empty list means every quantity is sourced."""
    known = case.record_ids()
    problems: list[str] = []
    in_fence = False

    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence or not stripped or stripped.startswith("#"):
            continue
        # markdown table separator row: no content to source
        if set(stripped) <= set("|-: "):
            continue

        cited: list[str] = []
        for match in _CITATION_RE.finditer(line):
            cited.extend(i.strip() for i in match.group(1).split(","))

        for ref in cited:
            if ref not in known:
                problems.append(
                    f"DANGLING_CITATION line {lineno}: {ref!r} is cited but is not a "
                    "record in this case")

        # Strip the citations before looking for numbers, or the IDs themselves
        # (which contain digits) would count as the quantity they are sourcing.
        body = _CITATION_RE.sub("", line)
        if _DIGIT_RE.search(body) and not cited:
            problems.append(
                f"UNCITED_QUANTITY line {lineno}: this line states a quantity with no "
                f"record citation -- {stripped[:80]!r}")

    return problems
