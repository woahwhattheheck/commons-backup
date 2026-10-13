#!/usr/bin/env python3
"""UIOWA-042 -- interview prompts for the traceability chain.

Run:
    python3 prompts.py --guide
    python3 prompts.py --for fixtures/project_delivery.json

The work order asks for "explicit follow-up questions rather than invented
conclusions". So every prompt here asks for something that exists -- a
record, a locator, a date, a role -- and every prompt is explicitly
answerable with "I don't know", which is recorded as UNKNOWN rather than
estimated.

No prompt asks anyone to rate delivery quality or to judge another team.
This instrument records how work is traced, not how well anyone performed.
"""

import argparse
import json
import sys

ALLOWED_SEEKS = ("record_locator", "role", "date", "concrete_instance",
                 "scope_boundary", "enumeration")

BANNED_SEEKS = ("self_rating", "quality_score", "peer_comparison",
                "individual_performance")

RECORDING_RULE = (
    "If you do not know, say so and we write UNKNOWN. An UNKNOWN answer is a "
    "normal result. It is never estimated and never recorded as 'no'."
)

SCOPE_NOTE = (
    "This records how delivered work is traced back to what was asked for. It "
    "does not rate delivery quality and does not evaluate any individual. "
    "Acceptance is attributed to a role, never to a named person."
)


def _q(qid, stage, text, seeks, covers=()):
    assert seeks in ALLOWED_SEEKS, seeks
    return {"id": qid, "stage": stage, "text": text, "seeks": seeks,
            "accepts_unknown": True, "covers_states": list(covers)}


CHAIN_QUESTIONS = [
    _q("Q-REQ-01", "request",
       "Take one change your team delivered recently. Where was the original request written down?",
       "record_locator"),
    _q("Q-REQ-02", "request",
       "Who asked for it? Give me the role, not the person.",
       "role"),
    _q("Q-AC-01", "acceptance_criteria",
       "What would have had to be true for that request to count as done? Was that written anywhere before the work started?",
       "record_locator"),
    _q("Q-AC-02", "acceptance_criteria",
       "Did what was being asked for change while the work was in flight? What changed, and when?",
       "concrete_instance", ("ACCEPTED_AGAINST_SUPERSEDED_REVISION",)),
    _q("Q-IMP-01", "implementation",
       "Where is the record of the change itself -- a commit, a ticket, a release note?",
       "record_locator", ("NOT_IMPLEMENTED",)),
    _q("Q-TST-01", "test",
       "How was it checked? Point me at the test, or at the suite that covers it.",
       "record_locator", ("UNTESTED",)),
    _q("Q-TST-02", "test",
       "Was anything still failing or unrun when it went out? What happened about it?",
       "concrete_instance", ("TEST_NOT_PASSING",)),
    _q("Q-ACC-01", "user_acceptance",
       "Who agreed the delivered work met the need? Which role, and on what date?",
       "role", ("INCOMPLETE_ACCEPTANCE",)),
    _q("Q-ACC-02", "user_acceptance",
       "Where is that agreement recorded? A message, a sign-off, a meeting note -- a locator is enough.",
       "record_locator", ("INCOMPLETE_ACCEPTANCE",)),
    _q("Q-STYLE-01", "delivery_style",
       "Is this typical of a small maintenance change, a larger project, or neither? Does the trail differ between them?",
       "scope_boundary"),
    _q("Q-STYLE-02", "delivery_style",
       "For a small change, is acceptance recorded at all, or is it handled in conversation?",
       "scope_boundary"),
]

STATE_PROBES = {
    "ACCEPTED_AGAINST_SUPERSEDED_REVISION": [
        _q("P-REV-01", "acceptance_criteria",
           "This was accepted before the requirement changed. Was the change taken back to whoever accepted it?",
           "concrete_instance", ("ACCEPTED_AGAINST_SUPERSEDED_REVISION",)),
        _q("P-REV-02", "user_acceptance",
           "Is there a later record of anyone accepting the changed version?",
           "record_locator", ("ACCEPTED_AGAINST_SUPERSEDED_REVISION",)),
    ],
    "INCOMPLETE_ACCEPTANCE": [
        _q("P-ACC-01", "user_acceptance",
           "The tests pass, but nothing shows anyone agreed this was the need. Who would that have been?",
           "role", ("INCOMPLETE_ACCEPTANCE",)),
        _q("P-ACC-02", "user_acceptance",
           "Would a record of that agreement exist anywhere -- a mail, a ticket comment, a meeting note?",
           "record_locator", ("INCOMPLETE_ACCEPTANCE",)),
    ],
    "TEST_NOT_PASSING": [
        _q("P-TST-01", "test",
           "What does this failing or unrun test cover, and what was decided about it before delivery?",
           "concrete_instance", ("TEST_NOT_PASSING",)),
    ],
    "UNTESTED": [
        _q("P-UNT-01", "test",
           "How was this checked? If an existing suite covers it, where is it?",
           "record_locator", ("UNTESTED",)),
    ],
    "NOT_IMPLEMENTED": [
        _q("P-IMP-01", "implementation",
           "Was this dropped, deferred, or delivered under a different record? UNKNOWN is fine.",
           "scope_boundary", ("NOT_IMPLEMENTED",)),
    ],
    "BROKEN_LINK": [
        _q("P-LNK-01", "request",
           "This points at a record I cannot find. Where does it live?",
           "record_locator", ("BROKEN_LINK",)),
    ],
}


def all_questions():
    out = list(CHAIN_QUESTIONS)
    for probes in STATE_PROBES.values():
        out.extend(probes)
    return out


def probes_for(results):
    """Deterministic, de-duplicated probes for a set of criterion results."""
    seen, out = set(), []
    for r in results:
        for q in STATE_PROBES.get(r["state"], []):
            if q["id"] in seen:
                continue
            seen.add(q["id"])
            out.append({"id": q["id"], "criterion_id": r["criterion_id"],
                        "state": r["state"], "text": q["text"]})
    return out


def render_guide():
    lines = []
    lines.append("# Requirements-to-acceptance interview prompts (UIOWA-042)")
    lines.append("")
    lines.append("**Recording rule.** %s" % RECORDING_RULE)
    lines.append("")
    lines.append("**Scope.** %s" % SCOPE_NOTE)
    lines.append("")
    lines.append("## Walk the chain once per delivered change")
    lines.append("")
    lines.append("| # | Stage | Question | Seeks |")
    lines.append("| --- | --- | --- | --- |")
    for q in CHAIN_QUESTIONS:
        lines.append("| %s | %s | %s | %s |" % (q["id"], q["stage"], q["text"], q["seeks"]))
    lines.append("")
    lines.append("## Probes fired by what the records show")
    lines.append("")
    for state in sorted(STATE_PROBES):
        lines.append("### %s" % state)
        lines.append("")
        for q in STATE_PROBES[state]:
            lines.append("- **%s** (%s) — %s" % (q["id"], q["seeks"], q["text"]))
        lines.append("")
    lines.append("## What this instrument does not ask")
    lines.append("")
    lines.append("- How good the delivery was on a scale. An unverifiable rating cannot be")
    lines.append("  left blank honestly, so it is not asked.")
    lines.append("- How this team compares to another. No such data is collected.")
    lines.append("- Anything that identifies an individual. Acceptance is recorded by role.")
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    p = argparse.ArgumentParser(description="Traceability interview prompts.")
    p.add_argument("--guide", action="store_true")
    p.add_argument("--for", dest="for_path")
    args = p.parse_args(argv)

    if args.for_path:
        import trace as trace_mod
        try:
            example = trace_mod.Example(trace_mod.load(args.for_path))
        except (ValueError, trace_mod.TraceError) as exc:
            sys.stderr.write("error: %s\n" % exc)
            return 2
        json.dump(probes_for(example.results), sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    sys.stdout.write(render_guide())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
