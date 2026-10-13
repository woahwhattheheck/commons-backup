#!/usr/bin/env python3
"""UIOWA-108 -- classify a contractor transition into the three states the
work order names, and render the handoff report.

Run:
    python3 transition.py --input fixtures/contractor_transition.json --outdir out
    python3 transition.py --input fixtures/contractor_transition.json --print

Python 3 standard library only. No network. Deterministic.

The order: *"The example distinguishes completed access changes, unresolved
ownership, and missing evidence."*  Those are three different operational
situations with three different next actions, and a careless handoff report
collapses all three into one green checkmark:

  COMPLETED            -- a dated change record with an evidence locator says
                          the change happened.
  UNRESOLVED_OWNERSHIP -- the departing contractor still owns it and no
                          successor is recorded. A live gap with a
                          name-shaped hole in it.
  NO_EVIDENCE          -- we have no record either way. This includes the
                          case that matters most in practice: a successor has
                          been *named* but nothing shows the handoff actually
                          happened. A plan is not evidence.

None of the three is scored, ranked, weighted, or rolled into a percentage,
and the transition cannot be reported closed while any item sits outside
COMPLETED.
"""

import argparse
import csv
import io
import json
import os
import sys

import scenario

STATES = ("COMPLETED", "UNRESOLVED_OWNERSHIP", "NO_EVIDENCE")

STATE_MEANING = {
    "COMPLETED": "a dated change record with an evidence locator confirms it happened",
    "UNRESOLVED_OWNERSHIP": "still owned by the departing contractor, no successor recorded",
    "NO_EVIDENCE": "no record establishes either outcome",
}

NEXT_ACTION = {
    "COMPLETED": "None. Retain the evidence locator for the closeout record.",
    "UNRESOLVED_OWNERSHIP": "Name an accountable owner before the contractor's last day. This is a live gap, not a paperwork gap.",
    "NO_EVIDENCE": "Ask for the change record or the system export that would settle it. Do not record an outcome without one.",
}


def _owned_items(index, departing_ref):
    """Every application, service identity and runbook the departing person
    owns. These are the transition items."""
    items = []
    for rid, (kind, record) in sorted(index.items()):
        if kind not in ("applications", "service_identities", "runbooks"):
            continue
        if record.get("owner_ref") != departing_ref:
            continue
        items.append((rid, kind, record))
    return items


def _changes_for(packet, target_ref, subject_ref):
    """Retain every matching change occurrence, including duplicate IDs.

    The lookup index deliberately has one entry per ID. It cannot be used as
    the relationship census: a later duplicate may name another target or
    subject. Its ID is already invalid, and each matching occurrence must
    carry that diagnostic into its own item's completion decision. Keep
    unique IDs in their original deterministic sort order for clean reports.
    """
    out = []
    for record in sorted(packet.get("access_changes", []),
                         key=lambda row: row.get("id") or "<missing id>"):
        if record.get("target_ref") != target_ref:
            continue
        if subject_ref and record.get("subject_ref") != subject_ref:
            continue
        out.append(record)
    return out


def classify_item(record, changes, dangling_refs, invalid_refs=None):
    """Return (state, reasons, evidence_refs)."""
    reasons = []
    evidence = []
    invalid_refs = set(invalid_refs or ())

    if (record.get("id") or "<missing id>") in dangling_refs:
        # A broken reference cannot be evidence of anything. Refusing to let
        # it read as completed is the whole point: a handoff report that says
        # "done" about a record pointing at nothing is worse than silence.
        reasons.append("record carries a broken reference; no outcome can be established from it")
        return "NO_EVIDENCE", reasons, evidence

    if ((record.get("id") or "<missing id>") in invalid_refs
            or any((c.get("id") or "<missing id>") in invalid_refs for c in changes)):
        reasons.append("record or a related change carries an integrity issue; no outcome can be established from it")
        return "NO_EVIDENCE", reasons, evidence

    completed = [
        c for c in changes
        if c.get("status") == "COMPLETED"
        and c.get("action") in scenario.ACCESS_ACTIONS
        and isinstance(c.get("evidence_ref"), str)
        and c["evidence_ref"].strip()
        and scenario.valid_completion_date(c.get("completed_at"))
    ]
    # MERIDIAN-Q7's semantic review distinguishes a completed action from a
    # complete handoff. Retain supported action locators while ownership or a
    # separately declared action remains open; never infer supersession.
    for c in completed:
        evidence.append(c["evidence_ref"])
        reasons.append("%s recorded %s on %s" % (c["id"], c["action"], c["completed_at"]))

    incomplete = []
    claimed_complete = [c for c in changes if c.get("status") == "COMPLETED"]
    for c in claimed_complete:
        if c in completed:
            continue
        # Status alone is somebody typing a word into a field.
        locator = c.get("evidence_ref")
        if not isinstance(locator, str) or not locator.strip():
            incomplete.append("%s is marked COMPLETED but carries no evidence locator" % c.get("id", "UNKNOWN"))
        if not scenario.valid_completion_date(c.get("completed_at")):
            incomplete.append("%s is marked COMPLETED but carries no valid completion date" % c.get("id", "UNKNOWN"))
        if c.get("action") not in scenario.ACCESS_ACTIONS:
            incomplete.append("%s has no recognized completion action" % c.get("id", "UNKNOWN"))
    for c in changes:
        if c.get("status") != "COMPLETED":
            incomplete.append("%s is %s, not complete" % (c.get("id", "UNKNOWN"), c.get("status", "UNKNOWN")))

    successor = record.get("successor_ref")
    if not successor or successor == record.get("owner_ref"):
        reasons.append("still owned by the departing contractor and no successor is recorded"
                       if not successor else "the departing contractor is also the named successor")
        reasons.extend(incomplete)
        return "UNRESOLVED_OWNERSHIP", reasons, evidence

    if completed and not incomplete:
        return "COMPLETED", reasons, evidence

    if claimed_complete:
        reasons.extend(incomplete)
        return "NO_EVIDENCE", reasons, evidence

    # A successor is named. That is a plan, not a handoff.
    reasons.append(
        "successor %s is named but no completed change record shows the handoff occurred; "
        "a named successor is a plan, not evidence" % successor
    )
    reasons.extend(incomplete)
    return "NO_EVIDENCE", reasons, evidence


class TransitionReport(object):
    def __init__(self, packet, issues, index):
        self.packet = packet
        self.issues = issues
        self.index = index
        self.departing_ref = packet.get("transition", {}).get("departing_ref")
        self.dangling_refs = set(
            i.record_id for i in issues if i.code == "DANGLING_REFERENCE"
        )
        self.invalid_refs = set(i.record_id for i in issues)
        # A valid-looking item cannot borrow authority from an invalid owner,
        # successor, application, or change. Propagate diagnostics to all
        # referring records; cycles terminate because this set only grows.
        changed = True
        while changed:
            changed = False
            for rid, (_kind, record) in sorted(index.items()):
                if rid in self.invalid_refs:
                    continue
                if any(isinstance(record.get(field), str) and record[field] in self.invalid_refs
                       for field in scenario.REFERENCE_KINDS):
                    self.invalid_refs.add(rid)
                    changed = True
        self.items = self._build_items()

    def _build_items(self):
        items = []
        for rid, kind, record in _owned_items(self.index, self.departing_ref):
            changes = _changes_for(self.packet, rid, self.departing_ref)
            state, reasons, evidence = classify_item(record, changes, self.dangling_refs, self.invalid_refs)
            items.append(
                {
                    "item_id": rid,
                    "kind": kind,
                    "label": record.get("name") or record.get("title") or record.get("account_name") or rid,
                    "service": record.get("service", "UNKNOWN"),
                    "owner_ref": record.get("owner_ref"),
                    "successor_ref": record.get("successor_ref"),
                    "state": state,
                    "reasons": reasons,
                    "evidence_refs": evidence,
                    "next_action": NEXT_ACTION[state],
                }
            )
        return items

    def counts(self):
        out = dict((s, 0) for s in STATES)
        for item in self.items:
            out[item["state"]] += 1
        return out

    def transition_closed(self):
        """Fail-closed. The transition is closed only when every item is
        COMPLETED. There is no threshold and no percentage -- one unresolved
        service identity is a contractor who still has a way in."""
        return not self.issues and bool(self.items) and all(i["state"] == "COMPLETED" for i in self.items)

    def open_items(self):
        return [i for i in self.items if i["state"] != "COMPLETED"]

    def as_dict(self):
        return {
            "meta": {
                "work_order": "UIOWA-108",
                "solicitation_id": "18649",
                "authority": scenario.AUTHORITY,
                "synthetic": True,
                "prohibited_interpretation": [
                    "University of Iowa finding",
                    "statement of current University access practice",
                    "compliance or certification conclusion",
                    "employee performance assessment",
                ],
                "packet_id": self.packet.get("packet_id", "UNKNOWN"),
                "departing_ref": self.departing_ref,
            },
            "counts": self.counts(),
            "transition_closed": self.transition_closed(),
            "items": self.items,
            "issues": [i.as_dict() for i in self.issues],
        }


CSV_COLUMNS = ("item_id", "kind", "label", "service", "owner_ref", "successor_ref",
               "state", "evidence_refs", "reasons", "next_action")


def write_csv(report, path):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(CSV_COLUMNS)
        for item in report.items:
            writer.writerow([
                item["item_id"], item["kind"], item["label"], item["service"],
                item["owner_ref"] or "", item["successor_ref"] or "", item["state"],
                "; ".join(item["evidence_refs"]), "; ".join(item["reasons"]), item["next_action"],
            ])


def render_markdown(report):
    counts = report.counts()
    lines = []
    lines.append("# Contractor transition -- handoff evidence (UIOWA-108)")
    lines.append("")
    lines.append("**This scenario is fictional.** Every person, application, service identity,")
    lines.append("runbook and change record below was invented for rehearsal. It is not a")
    lines.append("University of Iowa finding and not a statement about University access")
    lines.append("practice. No real account data appears in it, and the packet is refused")
    lines.append("outright if any is found.")
    lines.append("")
    lines.append("Packet `%s`. Departing: `%s`." % (
        report.packet.get("packet_id", "UNKNOWN"), report.departing_ref))
    lines.append("")
    lines.append("## Where the transition stands")
    lines.append("")
    lines.append("| State | Items | What it means |")
    lines.append("| --- | ---: | --- |")
    for state in STATES:
        lines.append("| %s | %d | %s |" % (state, counts[state], STATE_MEANING[state]))
    lines.append("")
    if report.transition_closed():
        lines.append("**Transition closed.** Every item carries a completed change record")
        lines.append("with an evidence locator.")
    else:
        lines.append("**Transition NOT closed — %d item(s) remain open.**" % len(report.open_items()))
        if report.issues:
            lines.append("Closure also requires resolving %d packet issue(s); see Packet issues below." % len(report.issues))
        lines.append("")
        lines.append("There is no completion percentage here on purpose. One unresolved")
        lines.append("service identity is a contractor who still has a way in; averaging it")
        lines.append("against completed items would produce a reassuring number that")
        lines.append("describes nothing anybody can act on.")
    lines.append("")
    lines.append("## Items")
    lines.append("")
    for state in STATES:
        rows = [i for i in report.items if i["state"] == state]
        if not rows:
            continue
        lines.append("### %s" % state)
        lines.append("")
        for item in rows:
            lines.append("**%s** — %s (`%s`, %s)" % (item["item_id"], item["label"], item["kind"], item["service"]))
            lines.append("")
            for reason in item["reasons"]:
                lines.append("- %s" % reason)
            if item["evidence_refs"]:
                lines.append("- Evidence: %s" % "; ".join("`%s`" % e for e in item["evidence_refs"]))
            lines.append("- Next: %s" % item["next_action"])
            lines.append("")
    if report.issues:
        lines.append("## Packet issues")
        lines.append("")
        lines.append("| Class | Record | Code | Field | Detail |")
        lines.append("| --- | --- | --- | --- | --- |")
        for issue in report.issues:
            d = issue.as_dict()
            lines.append("| %s | %s | %s | %s | %s |" % (
                d["class"], d["record_id"], d["code"], d["field"], d["detail"]))
        lines.append("")
    lines.append("## Still UNKNOWN (University inputs not collected)")
    lines.append("")
    for item in (
        "the real joiner/mover/leaver process and who authorises each step",
        "whether service identities are inventoried anywhere authoritative",
        "how contractor end dates reach the access-management system, if they do",
        "what evidence the University can actually export for a completed revocation",
        "who owns a runbook when its author leaves",
    ):
        lines.append("- %s" % item)
    lines.append("")
    return "\n".join(lines)


def load(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as exc:
        raise ValueError("%s is not valid JSON: line %d column %d: %s" % (path, exc.lineno, exc.colno, exc.msg))
    except OSError as exc:
        raise ValueError("cannot read %s: %s" % (path, exc.strerror))


def build(packet):
    issues, index = scenario.validate_packet(packet)
    return TransitionReport(packet, issues, index), issues


def _artifact_payloads(report):
    """Render once before touching output paths; preserve the original bytes."""
    text = io.StringIO(newline="")
    writer = csv.writer(text)
    writer.writerow(CSV_COLUMNS)
    for item in report.items:
        writer.writerow([
            item["item_id"], item["kind"], item["label"], item["service"],
            item["owner_ref"] or "", item["successor_ref"] or "", item["state"],
            "; ".join(item["evidence_refs"]), "; ".join(item["reasons"]), item["next_action"],
        ])
    return {
        "transition_items.csv": text.getvalue().encode("utf-8"),
        "transition_report.json": json.dumps(report.as_dict(), indent=2, sort_keys=True).encode("utf-8"),
        "transition_report.md": render_markdown(report).encode("utf-8"),
    }


def publish_artifacts(report, outdir):
    """Create a complete new artifact set without replacing existing entries.

    Empty existing directories and unrelated files are supported. Each target
    is reserved with O_EXCL, including after the preflight. Thus a source alias,
    prior report, or entry created concurrently is never opened for writing.
    Ordinary write failures remove only this call's still-identical files.
    This is not an atomic directory swap: readers must wait for CLI success
    (0 for closed, 1 for open) before consuming the three-file bundle.
    """
    payloads = _artifact_payloads(report)
    os.makedirs(outdir, exist_ok=True)
    paths = [(os.path.join(outdir, name), data) for name, data in payloads.items()]
    # Diagnose all pre-existing names before reserving any output. lexists
    # also sees dangling symlinks; existence of the referent is irrelevant.
    for path, _data in paths:
        if os.path.lexists(path):
            raise FileExistsError("output already exists: %s; choose a fresh destination" % path)
    reserved = []
    try:
        for path, data in paths:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o666)
            entry = {"path": path, "fd": fd, "identity": None, "data": data}
            reserved.append(entry)
            info = os.fstat(fd)
            entry["identity"] = (info.st_dev, info.st_ino)
        for entry in reserved:
            remaining = memoryview(entry["data"])
            while remaining:
                written = os.write(entry["fd"], remaining)
                if written <= 0:
                    raise OSError("output write made no progress: %s" % entry["path"])
                remaining = remaining[written:]
            os.fsync(entry["fd"])
        for entry in reserved:
            fd, entry["fd"] = entry["fd"], None
            os.close(fd)
    except BaseException as exc:
        # Close before unlink for Windows. Preserve a name replaced by another
        # writer instead of deleting an entry that this call did not create.
        cleanup_errors = []
        for entry in reversed(reserved):
            if entry["fd"] is not None:
                try:
                    os.close(entry["fd"])
                except OSError as error:
                    cleanup_errors.append(str(error))
                entry["fd"] = None
            try:
                current = os.stat(entry["path"], follow_symlinks=False)
                if entry["identity"] == (current.st_dev, current.st_ino):
                    os.unlink(entry["path"])
                else:
                    cleanup_errors.append("output identity changed; retained %s" % entry["path"])
            except FileNotFoundError:
                pass
            except OSError as error:
                cleanup_errors.append(str(error))
        if cleanup_errors and isinstance(exc, Exception):
            raise OSError("%s; cleanup incomplete: %s" % (exc, "; ".join(cleanup_errors))) from exc
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description="Classify a contractor-transition packet.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--outdir")
    parser.add_argument("--print", dest="do_print", action="store_true")
    args = parser.parse_args(argv)

    try:
        packet = load(args.input)
        report, issues = build(packet)
    except ValueError as exc:
        sys.stderr.write("error: %s\n" % exc)
        return 2

    if not scenario.is_deliverable(issues):
        unsafe = [i.as_dict() for i in issues if i.is_safety]
        sys.stderr.write(
            "REFUSED: the packet contains %d item(s) that could be mistaken for real "
            "account data. Nothing was rendered.\n" % len(unsafe)
        )
        for u in unsafe:
            sys.stderr.write("  %s %s.%s -- %s\n" % (u["code"], u["record_id"], u["field"], u["detail"]))
        return 3

    if args.outdir:
        try:
            publish_artifacts(report, args.outdir)
        except (OSError, ValueError) as exc:
            sys.stderr.write("error: cannot publish output: %s\n" % exc)
            return 2
        sys.stdout.write("wrote 3 files to %s\n" % args.outdir)

    if args.do_print or not args.outdir:
        sys.stdout.write(render_markdown(report))

    counts = report.counts()
    sys.stderr.write(
        "items=%d completed=%d unresolved=%d no_evidence=%d closed=%s issues=%d\n"
        % (len(report.items), counts["COMPLETED"], counts["UNRESOLVED_OWNERSHIP"],
           counts["NO_EVIDENCE"], report.transition_closed(), len(issues))
    )
    return 0 if report.transition_closed() else 1


if __name__ == "__main__":
    raise SystemExit(main())
