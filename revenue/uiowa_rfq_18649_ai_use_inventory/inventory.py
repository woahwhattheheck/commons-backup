#!/usr/bin/env python3
"""UIOWA-071 -- the deterministic AI-use inventory classifier and gap report.

Run:
    python3 inventory.py --input fixtures/synthetic_ai_use.json --outdir out
    python3 inventory.py --input fixtures/synthetic_ai_use.json --print

Python 3 standard library only.  No network at runtime.  No model calls.
The same input always produces the same output.

The classifier answers one question the work order asks for: is this
*active use*, an *informal experiment*, or *planned use*?  It answers from
what the record can show, not from what the record asserts, and it records
its reason every time those two differ.
"""

import argparse
import csv
import json
import os
import sys

if __package__:
    from . import schema
    from .schema import UNKNOWN
else:  # Preserve direct-script and lane-local unittest entry points.
    import schema
    from schema import UNKNOWN


# ---------------------------------------------------------------------------
# classification
# ---------------------------------------------------------------------------

def _has_concrete_example(rec):
    """A concrete example is an evidence locator, a benefit with an example
    behind it, or a named output.  Absent all three, an assertion of use is
    just an assertion."""
    if rec["evidence_refs"]:
        return True
    if rec["benefits_with_example"] > 0:
        return True
    if rec["outputs"]:
        return True
    return False


def classify(rec):
    """Return (classification, reasons, demoted).

    Two rules carry the order's intent:

    1. A claim of use with no concrete example of any kind never becomes
       active use.  It goes to UNSUPPORTED_CLAIM and is counted there, in
       the open, so the number of unbacked adoption claims is a visible
       figure in the baseline rather than an invisible contributor to it.

    2. The classifier demotes but never promotes.  A record declared PLANNED
       that arrives carrying evidence is *not* silently reclassified as
       active -- the two readings are both preserved and a follow-up is
       issued, the same way the methodology handles conflicting sources.
    """
    reasons = []
    declared = rec["declared_status"]
    has_example = _has_concrete_example(rec)
    recurring = rec["frequency"] in schema.RECURRING_FREQUENCY

    if declared == UNKNOWN:
        # Nothing was claimed.  This is different from an unbacked claim and
        # is kept in its own bucket so the two never blur together.
        if not has_example and rec["task"] == UNKNOWN:
            reasons.append("no declared status and no substantive content captured")
            return UNKNOWN, reasons, False
        reasons.append("declared_status was not captured; cannot separate active from planned use")
        return UNKNOWN, reasons, False

    if declared == "PLANNED":
        if has_example:
            # Do not resolve this in the tool's favour in either direction.
            reasons.append(
                "declared PLANNED but the record carries a concrete example; "
                "both readings preserved for a human to reconcile"
            )
        if rec["observed_benefits"]:
            reasons.append(
                "benefits reported as observed for a use declared not-yet-started; "
                "these are projections until the use is running"
            )
        return "PLANNED_USE", reasons, False

    # declared ACTIVE or INFORMAL from here down.
    if not has_example:
        reasons.append(
            "use asserted (%s) with no evidence locator, no benefit example and no named output"
            % declared
        )
        return "UNSUPPORTED_CLAIM", reasons, declared == "ACTIVE"

    if declared == "INFORMAL":
        return "INFORMAL_EXPERIMENT", reasons, False

    # declared ACTIVE with at least one concrete example.
    missing = []
    if not recurring:
        missing.append("frequency is %s, not a recurring cadence" % rec["frequency"])
    if not rec["outputs"]:
        missing.append("no named output")
    if rec["integrations_state"] == "NONE_REPORTED":
        missing.append("explicitly not integrated into a workflow")

    if missing:
        reasons.extend(missing)
        reasons.append("recorded as an informal experiment rather than active use")
        return "INFORMAL_EXPERIMENT", reasons, True

    return "ACTIVE_USE", reasons, False


# ---------------------------------------------------------------------------
# gaps -- each one carries the question that closes it
# ---------------------------------------------------------------------------

GAP_FOLLOW_UPS = {
    "NO_CONCRETE_EXAMPLE": "Ask for one specific instance from the last 30 days, with the artifact or ticket it produced.",
    "UNSUPPORTED_BENEFIT": "Ask what the work looked like before, what it looks like now, and where that comparison can be seen.",
    "UNKNOWN_FREQUENCY": "Ask how many times this was used in the last full week; record UNKNOWN if unsure rather than estimating.",
    "UNKNOWN_INTEGRATION": "Ask whether this runs inside an existing system or is opened separately, and name the system.",
    "NO_LIMITATIONS_CAPTURED": "Ask for the most recent case where the output was wrong or unusable and what happened next.",
    "UNKNOWN_USER_COUNT": "Ask which roles use this and roughly how many people hold that role; team-level only.",
    "STATUS_EVIDENCE_MISMATCH": "Reconcile the declared status against the evidence with the team before it enters a finding.",
    "NO_EVIDENCE_LOCATOR": "Ask where the output is stored so a locator can be recorded.",
}


def find_gaps(rec, classification, reasons):
    """Return a list of gap dicts.  A gap is a preparation item, never a
    score and never a deduction."""
    gaps = []

    def add(kind, detail):
        gaps.append(
            {
                "entry_id": rec["entry_id"],
                "group": rec["group"],
                "function": rec["function"],
                "gap": kind,
                "detail": detail,
                "follow_up": GAP_FOLLOW_UPS[kind],
            }
        )

    if classification == "UNSUPPORTED_CLAIM":
        add("NO_CONCRETE_EXAMPLE", "use is asserted but nothing demonstrates it")
    if rec["benefits_unsupported"]:
        add(
            "UNSUPPORTED_BENEFIT",
            "%d benefit claim(s) with no example behind them" % rec["benefits_unsupported"],
        )
    if rec["frequency"] == UNKNOWN:
        add("UNKNOWN_FREQUENCY", "frequency was not captured; not recorded as zero use")
    if rec["integrations_state"] == UNKNOWN:
        add("UNKNOWN_INTEGRATION", "integration was not captured; not recorded as standalone")
    if rec["known_limitations_state"] != "REPORTED":
        add("NO_LIMITATIONS_CAPTURED", "no known limitation recorded for this use")
    if rec["user_count"] == UNKNOWN:
        add("UNKNOWN_USER_COUNT", "user count was not captured; not recorded as zero users")
    if not rec["evidence_refs"]:
        add("NO_EVIDENCE_LOCATOR", "no source locator recorded for this use")
    for reason in reasons:
        if "both readings preserved" in reason:
            add("STATUS_EVIDENCE_MISMATCH", reason)
    return gaps


# ---------------------------------------------------------------------------
# the inventory
# ---------------------------------------------------------------------------

class Inventory(object):
    def __init__(self, entries, issues, meta):
        self.entries = entries          # list of classified row dicts
        self.issues = issues            # list of ValidationIssue dicts
        self.meta = meta

    # -- counts -------------------------------------------------------------
    def counts(self):
        """Five buckets reported separately.  They sum to the record total;
        test_inventory asserts it, because a bucket that silently absorbs a
        record is how an adoption number gets inflated."""
        out = dict((c, 0) for c in schema.CLASSIFICATIONS)
        for e in self.entries:
            out[e["classification"]] += 1
        return out

    def coverage(self):
        """Which (group, function) cells have any entry at all.

        A cell with no entry is NO_ENTRY_CAPTURED.  It is never a zero and
        never a low score: nobody was asked, so nothing is known."""
        cells = []
        for group in schema.GROUPS:
            for function in schema.FUNCTIONS:
                rows = [
                    e for e in self.entries
                    if e["group"] == group and e["function"] == function
                ]
                if not rows:
                    state = "NO_ENTRY_CAPTURED"
                else:
                    kinds = set(r["classification"] for r in rows)
                    if "ACTIVE_USE" in kinds:
                        state = "ACTIVE_USE_PRESENT"
                    elif "INFORMAL_EXPERIMENT" in kinds:
                        state = "INFORMAL_ONLY"
                    elif "PLANNED_USE" in kinds:
                        state = "PLANNED_ONLY"
                    elif kinds == {"UNSUPPORTED_CLAIM"}:
                        state = "CLAIMED_UNSUPPORTED"
                    else:
                        state = UNKNOWN
                cells.append(
                    {
                        "group": group,
                        "function": function,
                        "area": schema.AREA,
                        "entries": len(rows),
                        "state": state,
                    }
                )
        return cells

    def unmapped(self):
        """Entries that cannot be placed in the coverage grid because their
        group or function is outside the vocabulary.

        coverage() + unmapped() is exhaustive and disjoint over the whole
        collection -- test_inventory asserts the two add up to the record
        count, so a malformed row can never quietly leave the report.
        """
        out = []
        for e in self.entries:
            if e["group"] not in schema.GROUPS or e["function"] not in schema.FUNCTIONS:
                out.append(
                    {
                        "entry_id": e["entry_id"],
                        "group_as_given": e.get("group_as_given", UNKNOWN),
                        "function_as_given": e.get("function_as_given", UNKNOWN),
                        "classification": e["classification"],
                        "reason": "group or function is outside the vocabulary; not placed in the grid",
                    }
                )
        return out

    def gaps(self):
        out = []
        for e in self.entries:
            out.extend(e["gaps"])
        return out

    # -- serialisation ------------------------------------------------------
    def as_dict(self):
        return {
            "meta": self.meta,
            "counts": self.counts(),
            "coverage": self.coverage(),
            "unmapped": self.unmapped(),
            "entries": self.entries,
            "gaps": self.gaps(),
            "validation_issues": self.issues,
        }


CSV_COLUMNS = (
    "entry_id",
    "proposed_evidence_id",
    "group",
    "group_as_given",
    "area",
    "function",
    "function_as_given",
    "quarantined",
    "task",
    "declared_status",
    "classification",
    "demoted",
    "frequency",
    "user_roles",
    "user_count",
    "inputs",
    "outputs",
    "integrations",
    "integrations_state",
    "benefits_with_example",
    "benefits_unsupported",
    "known_limitations",
    "evidence_refs",
    "captured_at",
    "respondent_role",
    "classification_reasons",
)


def build(records, source_label="unlabelled"):
    """Classify a list of raw record dicts into an Inventory."""
    issues = []
    seen = {}
    entries = []
    for index, raw in enumerate(records, start=1):
        record_issues = schema.validate_record(raw)
        eid = raw.get("entry_id") if isinstance(raw, dict) else None
        if eid:
            if eid in seen:
                record_issues.append(
                    schema.ValidationIssue(
                        eid, "DUPLICATE_ENTRY_ID", "entry_id",
                        "also used by record #%d; both rows preserved" % seen[eid],
                    )
                )
            else:
                seen[eid] = index
        issues.extend(i.as_dict() for i in record_issues)

        if not isinstance(raw, dict):
            # Keep the position visible instead of dropping it silently.
            entries.append(
                {
                    "entry_id": "RECORD_%03d" % index,
                    "group": UNKNOWN,
                    "group_as_given": UNKNOWN,
                    "area": schema.AREA,
                    "function": UNKNOWN,
                    "function_as_given": UNKNOWN,
                    "quarantined": False,
                    "task": UNKNOWN,
                    "declared_status": UNKNOWN,
                    "classification": UNKNOWN,
                    "demoted": False,
                    "classification_reasons": ["record is not an object and could not be read"],
                    "gaps": [],
                    "validation_codes": ["BAD_TYPE"],
                    "proposed_evidence_id": UNKNOWN,
                    "frequency": UNKNOWN,
                    "user_roles": [],
                    "user_count": UNKNOWN,
                    "inputs": [],
                    "outputs": [],
                    "integrations": [],
                    "integrations_state": UNKNOWN,
                    "benefits_with_example": 0,
                    "benefits_unsupported": 0,
                    "observed_benefits": [],
                    "known_limitations": [],
                    "known_limitations_state": UNKNOWN,
                    "evidence_refs": [],
                    "captured_at": UNKNOWN,
                    "respondent_role": UNKNOWN,
                    "notes": "",
                }
            )
            continue

        rec = schema.normalize_record(raw)
        codes = set(i.code for i in record_issues)
        if "INDIVIDUAL_IDENTIFIER_PRESENT" in codes:
            # Do not classify it.  Letting this row into a usage bucket would
            # mean an individual identifier was accepted into the baseline.
            # normalize_record copies only known fields, so the identifier's
            # value is already absent from `rec`; the row is held open until
            # it is resubmitted keyed to a role.
            classification = UNKNOWN
            reasons = [
                "quarantined: record carried an individual identifier; "
                "resubmit keyed to a role and a team"
            ]
            demoted = False
            rec["quarantined"] = True
        else:
            rec["quarantined"] = False
            classification, reasons, demoted = classify(rec)
        rec["classification"] = classification
        rec["classification_reasons"] = reasons
        rec["demoted"] = demoted
        rec["validation_codes"] = sorted(set(i.code for i in record_issues))
        rec["proposed_evidence_id"] = schema.proposed_evidence_id(rec["group"], index)
        rec["gaps"] = find_gaps(rec, classification, reasons)
        entries.append(rec)

    meta = {
        "lane": "uiowa_rfq_18649_ai_use_inventory",
        "work_order": "UIOWA-071",
        "solicitation_id": "18649",
        "content": "SYNTHETIC -- fictional records built for rehearsal. No University input collected.",
        "source_label": source_label,
        "record_count": len(entries),
    }
    return Inventory(entries, issues, meta)


def load(path):
    """Read a fixture file.  A malformed file produces a clean diagnostic,
    not a traceback -- an operator running this at a desk should get a
    sentence, not a stack."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        raise ValueError("%s is not valid JSON: line %d column %d: %s" % (path, exc.lineno, exc.colno, exc.msg))
    except OSError as exc:
        raise ValueError("cannot read %s: %s" % (path, exc.strerror))
    if isinstance(data, dict):
        records = data.get("entries")
        label = data.get("collection_id", os.path.basename(path))
    else:
        records = data
        label = os.path.basename(path)
    if not isinstance(records, list):
        raise ValueError("%s: expected a list of entries, or an object with an 'entries' list" % path)
    return records, label


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------

def _join(value):
    if isinstance(value, list):
        return "; ".join(str(v) for v in value)
    return "" if value is None else str(value)


def write_csv(inv, path):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(CSV_COLUMNS)
        for e in inv.entries:
            writer.writerow([_join(e.get(col, "")) for col in CSV_COLUMNS])


def write_gaps_csv(inv, path):
    cols = ("entry_id", "group", "function", "gap", "detail", "follow_up")
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(cols)
        for g in inv.gaps():
            writer.writerow([g[c] for c in cols])


def render_markdown(inv):
    counts = inv.counts()
    lines = []
    lines.append("# AI-use inventory -- synthetic baseline (UIOWA-071)")
    lines.append("")
    lines.append("**All records below are fictional.** They were written to rehearse the")
    lines.append("discovery instrument. No University input has been collected; every")
    lines.append("University figure in this document is therefore absent, not zero.")
    lines.append("")
    lines.append("Source collection: `%s` -- %d records." % (inv.meta["source_label"], inv.meta["record_count"]))
    lines.append("")
    lines.append("## How the records classified")
    lines.append("")
    lines.append("| Classification | Records | Reading |")
    lines.append("| --- | ---: | --- |")
    readings = {
        "ACTIVE_USE": "running work, with a concrete example behind it",
        "INFORMAL_EXPERIMENT": "real use, but not yet an operated workflow",
        "PLANNED_USE": "intended; nothing observed yet",
        "UNSUPPORTED_CLAIM": "use asserted, nothing demonstrates it -- left unfilled on purpose",
        UNKNOWN: "not enough captured to classify",
    }
    for key in schema.CLASSIFICATIONS:
        lines.append("| %s | %d | %s |" % (key, counts[key], readings[key]))
    lines.append("")
    lines.append("These five are reported separately and are never combined into an")
    lines.append("adoption percentage. `UNSUPPORTED_CLAIM` in particular is a count of")
    lines.append("claims that did not survive a request for an example; folding it into")
    lines.append("active use is the exact error this instrument exists to prevent.")
    lines.append("")
    lines.append("## Coverage by group and function")
    lines.append("")
    lines.append("| Group | Function | Entries | State |")
    lines.append("| --- | --- | ---: | --- |")
    for cell in inv.coverage():
        lines.append(
            "| %s | %s | %d | %s |" % (cell["group"], cell["function"], cell["entries"], cell["state"])
        )
    lines.append("")
    lines.append("`NO_ENTRY_CAPTURED` means nobody in that group was asked about that")
    lines.append("function. It is not a finding of no AI use.")
    lines.append("")
    unmapped = inv.unmapped()
    if unmapped:
        lines.append("### Entries not placed in the grid")
        lines.append("")
        lines.append("| Entry | Group as given | Function as given | Classification |")
        lines.append("| --- | --- | --- | --- |")
        for u in unmapped:
            lines.append("| %s | %s | %s | %s |" % (
                u["entry_id"], u["group_as_given"], u["function_as_given"], u["classification"]))
        lines.append("")
        lines.append("These rows are listed rather than dropped. The grid plus this table")
        lines.append("accounts for every record in the collection.")
        lines.append("")
    lines.append("## Entries")
    lines.append("")
    for e in inv.entries:
        lines.append("### %s -- %s / %s" % (e["entry_id"], e["group"], e["function"]))
        lines.append("")
        lines.append("- **Task:** %s" % e["task"])
        lines.append("- **Declared:** %s -> **classified:** %s%s" % (
            e["declared_status"], e["classification"], "  *(demoted)*" if e.get("demoted") else ""))
        lines.append("- **Frequency:** %s | **Users:** %s (%s)" % (
            e["frequency"], _join(e["user_roles"]) or UNKNOWN, e["user_count"]))
        lines.append("- **Inputs:** %s" % (_join(e["inputs"]) or UNKNOWN))
        lines.append("- **Outputs:** %s" % (_join(e["outputs"]) or UNKNOWN))
        lines.append("- **Integrations:** %s (%s)" % (_join(e["integrations"]) or "-", e["integrations_state"]))
        lines.append("- **Benefits:** %d with an example, %d unsupported" % (
            e["benefits_with_example"], e["benefits_unsupported"]))
        lines.append("- **Known limitations:** %s" % (_join(e["known_limitations"]) or "NONE CAPTURED"))
        lines.append("- **Evidence locators:** %s" % (_join(e["evidence_refs"]) or "NONE"))
        if e["classification_reasons"]:
            lines.append("- **Why:** %s" % "; ".join(e["classification_reasons"]))
        if e["gaps"]:
            lines.append("- **Preparation work:**")
            for g in e["gaps"]:
                lines.append("    - `%s` -- %s" % (g["gap"], g["follow_up"]))
        lines.append("")
    if inv.issues:
        lines.append("## Validation issues")
        lines.append("")
        lines.append("| Entry | Code | Field | Detail |")
        lines.append("| --- | --- | --- | --- |")
        for i in inv.issues:
            lines.append("| %s | %s | %s | %s |" % (i["entry_id"], i["code"], i["field"], i["detail"]))
        lines.append("")
    lines.append("## Still UNKNOWN (University inputs not collected)")
    lines.append("")
    for item in (
        "which units actually use AI tooling today, and under what approval",
        "whether any use touches student or restricted data, and under which access semantics",
        "existing license, contract or procurement coverage for any tool named",
        "whether informal experiments are known to the unit's leadership",
        "the real headcount behind any role named in an entry",
    ):
        lines.append("- %s" % item)
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(description="Classify an AI-use inventory collection.")
    parser.add_argument("--input", required=True, help="path to a JSON collection")
    parser.add_argument("--outdir", help="write CSV/JSON/Markdown here")
    parser.add_argument("--print", dest="do_print", action="store_true", help="print the Markdown report")
    args = parser.parse_args(argv)

    try:
        records, label = load(args.input)
    except ValueError as exc:
        sys.stderr.write("error: %s\n" % exc)
        return 2

    inv = build(records, source_label=label)

    if args.outdir:
        os.makedirs(args.outdir, exist_ok=True)
        write_csv(inv, os.path.join(args.outdir, "ai_use_inventory.csv"))
        write_gaps_csv(inv, os.path.join(args.outdir, "ai_use_gaps.csv"))
        with open(os.path.join(args.outdir, "ai_use_inventory.json"), "w", encoding="utf-8") as fh:
            json.dump(inv.as_dict(), fh, indent=2, sort_keys=True)
        with open(os.path.join(args.outdir, "ai_use_inventory.md"), "w", encoding="utf-8") as fh:
            fh.write(render_markdown(inv))
        sys.stdout.write("wrote 4 files to %s\n" % args.outdir)

    if args.do_print or not args.outdir:
        sys.stdout.write(render_markdown(inv))

    counts = inv.counts()
    sys.stderr.write(
        "records=%d active=%d informal=%d planned=%d unsupported=%d unknown=%d gaps=%d\n"
        % (
            inv.meta["record_count"], counts["ACTIVE_USE"], counts["INFORMAL_EXPERIMENT"],
            counts["PLANNED_USE"], counts["UNSUPPORTED_CLAIM"], counts[UNKNOWN], len(inv.gaps()),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
