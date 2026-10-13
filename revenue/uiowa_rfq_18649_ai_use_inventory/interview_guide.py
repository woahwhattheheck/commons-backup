#!/usr/bin/env python3
"""UIOWA-071 -- the discovery instrument: what an interviewer actually asks.

Run:
    python3 interview_guide.py --guide
    python3 interview_guide.py --probes fixtures/synthetic_ai_use.json

The work order's completion condition is the design constraint here:
"interview questions seek concrete examples and leave unsupported University
adoption claims unfilled."  Two rules follow from it and both are enforced
by test_inventory.py rather than left as good intentions:

  * Every question asks for something that exists -- an instance, an
    artifact, a count, a named system.  No question invites a self-rating,
    a maturity score, or a comparison against another institution, because
    an answer to one of those cannot be checked and cannot be left blank
    honestly.
  * Every question is explicitly answerable with "I don't know".  The
    recording rule is printed on the instrument: an unknown answer is
    written UNKNOWN and stays UNKNOWN.  It is not estimated, and it is not
    rounded to zero.
"""

import argparse
import json
import sys

if __package__:
    from . import schema
else:  # Preserve direct-script execution.
    import schema

# What a question is allowed to go after.
ALLOWED_SEEKS = (
    "concrete_instance",
    "artifact_locator",
    "enumeration",
    "named_system",
    "limitation_instance",
    "comparison_basis",
    "scope_boundary",
)

# What a question may never go after.  A question of these kinds produces an
# answer nobody can verify and nobody can leave blank without looking evasive,
# which is how unsupported adoption claims get manufactured in the first place.
BANNED_SEEKS = (
    "self_rating",
    "maturity_score",
    "peer_comparison",
    "individual_performance",
)

RECORDING_RULE = (
    "If you do not know, say so and we write UNKNOWN. An UNKNOWN answer is a "
    "normal result and is reported as UNKNOWN -- it is never estimated, and it "
    "is never recorded as zero or as 'no'."
)

SCOPE_NOTE = (
    "This inventory records what a team does with a tool. It does not record "
    "who is good at it. Answers are attributed to a role and a team, never to "
    "a named individual, and nothing here feeds an individual evaluation."
)


def _q(qid, field, text, seeks, covers=()):
    assert seeks in ALLOWED_SEEKS, seeks
    return {
        "id": qid,
        "field": field,
        "text": text,
        "seeks": seeks,
        "accepts_unknown": True,
        "covers_gaps": list(covers),
    }


# The baseline walk-through: one pass per AI use a team names.  Every field
# the work order enumerates has at least one question here; test_inventory
# asserts that against the order text so the instrument cannot quietly lose
# a field.
BASE_QUESTIONS = [
    _q("Q-TASK-01", "task",
       "Name one thing you used an AI tool for in the last two weeks. What was the task, start to finish?",
       "concrete_instance"),
    _q("Q-TASK-02", "function",
       "Was that development, documentation, testing, support, or analysis work? If it spans two, say which parts.",
       "scope_boundary"),
    _q("Q-USERS-01", "users",
       "Which roles on the team do this? Roughly how many people hold those roles?",
       "enumeration", ("UNKNOWN_USER_COUNT",)),
    _q("Q-INPUT-01", "inputs",
       "What goes in? Name the actual material -- a ticket, a log, a code file, a policy document.",
       "concrete_instance"),
    _q("Q-INPUT-02", "inputs",
       "Does any of that input contain student, health, financial, or otherwise restricted data?",
       "scope_boundary"),
    _q("Q-OUTPUT-01", "outputs",
       "What comes out, and where does it end up? Can you point me at one that exists right now?",
       "artifact_locator", ("NO_EVIDENCE_LOCATOR", "NO_CONCRETE_EXAMPLE")),
    _q("Q-INTEG-01", "integrations",
       "Does this run inside a system you already use, or do you open it separately? Name the system.",
       "named_system", ("UNKNOWN_INTEGRATION",)),
    _q("Q-FREQ-01", "frequency",
       "How many times was this used in the last full week?",
       "enumeration", ("UNKNOWN_FREQUENCY",)),
    _q("Q-BEN-01", "observed_benefits",
       "What is better than before? Describe the last specific time you saw that difference.",
       "concrete_instance", ("UNSUPPORTED_BENEFIT",)),
    _q("Q-BEN-02", "observed_benefits",
       "What did that same work take before this tool, and where could someone see that comparison?",
       "comparison_basis", ("UNSUPPORTED_BENEFIT",)),
    _q("Q-LIMIT-01", "known_limitations",
       "Tell me about the most recent time the output was wrong or unusable. What happened next?",
       "limitation_instance", ("NO_LIMITATIONS_CAPTURED",)),
    _q("Q-LIMIT-02", "known_limitations",
       "Is there work you deliberately do not use it for? What made you draw that line?",
       "scope_boundary", ("NO_LIMITATIONS_CAPTURED",)),
    _q("Q-STATUS-01", "declared_status",
       "Is this part of how the work runs now, something a few people are trying, or something not started yet?",
       "scope_boundary"),
    _q("Q-STATUS-02", "evidence_refs",
       "Where is the record of it -- a repository, a ticket queue, a shared folder? A locator is enough.",
       "artifact_locator", ("NO_EVIDENCE_LOCATOR", "NO_CONCRETE_EXAMPLE", "STATUS_EVIDENCE_MISMATCH")),
]

# Follow-up probes, fired only when a captured record is thin in a specific
# way.  These are the questions that stop a claim becoming a fact.
PROBE_QUESTIONS = {
    "NO_CONCRETE_EXAMPLE": [
        _q("P-EX-01", "evidence_refs",
           "You described this as in use. Walk me through the single most recent time, and tell me what it produced.",
           "concrete_instance", ("NO_CONCRETE_EXAMPLE",)),
        _q("P-EX-02", "outputs",
           "Is there anything still on disk or in a queue from that use that I could record a locator for?",
           "artifact_locator", ("NO_CONCRETE_EXAMPLE",)),
    ],
    "UNSUPPORTED_BENEFIT": [
        _q("P-BEN-01", "observed_benefits",
           "You mentioned a saving. What task was it, and how long did that task take the last time it was done both ways?",
           "comparison_basis", ("UNSUPPORTED_BENEFIT",)),
    ],
    "UNKNOWN_FREQUENCY": [
        _q("P-FREQ-01", "frequency",
           "Take last week specifically -- was it every day, a few times, once, or not at all? UNKNOWN is fine.",
           "enumeration", ("UNKNOWN_FREQUENCY",)),
    ],
    "UNKNOWN_INTEGRATION": [
        _q("P-INT-01", "integrations",
           "When you use it, do you switch to another application first? If so, which one?",
           "named_system", ("UNKNOWN_INTEGRATION",)),
    ],
    "NO_LIMITATIONS_CAPTURED": [
        _q("P-LIM-01", "known_limitations",
           "Has anyone had to redo work because of an output from this? Describe that case.",
           "limitation_instance", ("NO_LIMITATIONS_CAPTURED",)),
    ],
    "UNKNOWN_USER_COUNT": [
        _q("P-USR-01", "users",
           "Which roles, and about how many people in each? A range is fine; UNKNOWN is fine.",
           "enumeration", ("UNKNOWN_USER_COUNT",)),
    ],
    "STATUS_EVIDENCE_MISMATCH": [
        _q("P-MIS-01", "declared_status",
           "The record says this has not started, but there is output from it. Which is it, and what changed?",
           "scope_boundary", ("STATUS_EVIDENCE_MISMATCH",)),
    ],
    "NO_EVIDENCE_LOCATOR": [
        _q("P-LOC-01", "evidence_refs",
           "Where would I look to see this for myself? A folder, a board, a repository -- a pointer is enough.",
           "artifact_locator", ("NO_EVIDENCE_LOCATOR",)),
    ],
}


def all_questions():
    out = list(BASE_QUESTIONS)
    for probes in PROBE_QUESTIONS.values():
        out.extend(probes)
    return out


def probes_for(entry):
    """Return the follow-up questions a classified entry's gaps require.

    Deterministic and de-duplicated: the same entry always yields the same
    probe list in the same order.
    """
    seen = set()
    out = []
    for gap in entry.get("gaps", []):
        for q in PROBE_QUESTIONS.get(gap["gap"], []):
            if q["id"] in seen:
                continue
            seen.add(q["id"])
            out.append(q)
    return out


def render_guide():
    lines = []
    lines.append("# AI-use discovery instrument (UIOWA-071)")
    lines.append("")
    lines.append("**Recording rule.** %s" % RECORDING_RULE)
    lines.append("")
    lines.append("**Scope.** %s" % SCOPE_NOTE)
    lines.append("")
    lines.append("**Ask once per named AI use, not once per person.** If a team names")
    lines.append("three uses, that is three passes through this list.")
    lines.append("")
    lines.append("## Baseline walk-through")
    lines.append("")
    lines.append("| # | Field | Question | Seeks |")
    lines.append("| --- | --- | --- | --- |")
    for q in BASE_QUESTIONS:
        lines.append("| %s | %s | %s | %s |" % (q["id"], q["field"], q["text"], q["seeks"]))
    lines.append("")
    lines.append("## Follow-up probes")
    lines.append("")
    lines.append("Fired by the inventory when a record is thin in a specific way. Each")
    lines.append("is the question that turns an assertion into something checkable, or")
    lines.append("leaves it visibly unfilled.")
    lines.append("")
    for gap in sorted(PROBE_QUESTIONS):
        lines.append("### %s" % gap)
        lines.append("")
        for q in PROBE_QUESTIONS[gap]:
            lines.append("- **%s** (%s) -- %s" % (q["id"], q["seeks"], q["text"]))
        lines.append("")
    lines.append("## What this instrument deliberately does not ask")
    lines.append("")
    lines.append("- How mature the unit's AI practice is on a scale. An unverifiable")
    lines.append("  self-rating cannot be left blank honestly, so it is not asked.")
    lines.append("- How the unit compares to peer institutions. No peer data was")
    lines.append("  collected, and a comparison built on an impression is not evidence.")
    lines.append("- How well any individual uses a tool. Rows are keyed to a task and a")
    lines.append("  team; the schema carries no field that identifies a person.")
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="AI-use discovery instrument.")
    parser.add_argument("--guide", action="store_true", help="print the interview guide")
    parser.add_argument("--probes", help="print the probes a classified collection requires")
    args = parser.parse_args(argv)

    if args.probes:
        if __package__:
            from . import inventory
        else:
            import inventory
        try:
            records, label = inventory.load(args.probes)
        except ValueError as exc:
            sys.stderr.write("error: %s\n" % exc)
            return 2
        inv = inventory.build(records, source_label=label)
        payload = []
        for e in inv.entries:
            probes = probes_for(e)
            if probes:
                payload.append(
                    {
                        "entry_id": e["entry_id"],
                        "classification": e["classification"],
                        "probes": [{"id": p["id"], "text": p["text"]} for p in probes],
                    }
                )
        json.dump(payload, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    sys.stdout.write(render_guide())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
