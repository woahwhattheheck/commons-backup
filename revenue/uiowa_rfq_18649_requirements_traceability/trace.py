#!/usr/bin/env python3
"""UIOWA-042 -- requirements-to-acceptance traceability.

Run:
    python3 trace.py --input fixtures/project_delivery.json --outdir out
    python3 trace.py --input fixtures/maintenance_change.json --print

Python 3 standard library only. No network. No clock. Deterministic.

The chain is request -> acceptance criterion -> implementation -> test ->
user acceptance. The work order requires the examples to include a changed
requirement and incomplete acceptance evidence, "with explicit follow-up
questions rather than invented conclusions". Those two are the cases where a
traceability spreadsheet normally lies:

  * A requirement that CHANGED after acceptance was recorded. The row still
    shows a tick. What it actually records is that somebody accepted an
    earlier version of the requirement, and nobody has accepted this one.

  * Acceptance evidence that is INCOMPLETE -- an acceptance row with no
    locator behind it, or no acceptance row at all under a passing test. A
    passing test is evidence the code does what the test says. It is not
    evidence anybody agreed that was the need.

Neither is resolved here. Both produce an explicit follow-up question, and
the overall verdict stays NOT_ESTABLISHED until a person closes them.
"""

import argparse
import csv
import copy
import json
import os
import sys

UNKNOWN = "UNKNOWN"

SERVICES = ("ESS", "RIS", "IAM")
DELIVERY_STYLES = ("maintenance_change", "project")
TEST_RESULTS = ("PASS", "FAIL", "NOT_RUN")

STATES = (
    "TRACED",
    "ACCEPTED_AGAINST_SUPERSEDED_REVISION",
    "INCOMPLETE_ACCEPTANCE",
    "TEST_NOT_PASSING",
    "UNTESTED",
    "NOT_IMPLEMENTED",
    "BROKEN_LINK",
    "SUPERSEDED",
)

STATE_MEANING = {
    "TRACED": "every link resolves and acceptance is recorded against the current revision",
    "ACCEPTED_AGAINST_SUPERSEDED_REVISION": "acceptance exists, but against an earlier revision of this criterion",
    "INCOMPLETE_ACCEPTANCE": "nobody has recorded accepting this, or the acceptance has no evidence behind it",
    "TEST_NOT_PASSING": "a test exists but did not pass, or was never run",
    "UNTESTED": "implemented with no test and no declared regression coverage",
    "NOT_IMPLEMENTED": "no implementation record references this criterion",
    "BROKEN_LINK": "a record in the chain points at something that is not in this example",
    "SUPERSEDED": "this revision was replaced; its successor carries the requirement",
}

# TRACED closes a current criterion; a valid successor may retire an old one.
CLOSED_STATES = ("TRACED", "SUPERSEDED")

FOLLOW_UP = {
    "ACCEPTED_AGAINST_SUPERSEDED_REVISION":
        "The requirement changed after this was accepted. Ask who accepted revision {rev} "
        "and whether the change was reviewed with them; do not carry the earlier acceptance forward.",
    "INCOMPLETE_ACCEPTANCE":
        "Ask who agreed the delivered work met the need, when, and where that is recorded. "
        "A passing test is not a substitute for that record.",
    "TEST_NOT_PASSING":
        "Ask what the failing or unrun test covers, and what was done about it before delivery.",
    "UNTESTED":
        "Ask how this change was checked. If an existing regression suite covers it, record "
        "that locator rather than assuming it.",
    "NOT_IMPLEMENTED":
        "Ask whether this criterion was dropped, deferred, or delivered under another record. "
        "A criterion with no implementation is not evidence of anything either way.",
    "BROKEN_LINK":
        "Ask where the referenced record lives. Until it resolves, nothing downstream of it "
        "can be relied on.",
    "SUPERSEDED":
        "No action: the successor revision carries the requirement.",
    "TRACED":
        "No outstanding question for this criterion.",
}


class TraceError(ValueError):
    pass


def _index(records, key):
    out = {}
    for rec in records or []:
        if isinstance(rec, dict) and rec.get(key):
            out.setdefault(rec[key], []).append(rec)
    return out


def _known_text(value):
    return isinstance(value, str) and bool(value.strip()) and value.strip().upper() != UNKNOWN


def _revision(value):
    # bool is an int subclass; True is not evidence of revision 1.
    return type(value) is int and value > 0


def _validate(payload):
    """Validate transport shape, not whether supplied evidence is true."""
    if not isinstance(payload, dict):
        raise TraceError("example must be a JSON object")
    for section, id_key in (("requests", "request_id"), ("criteria", "criterion_id"),
                            ("implementations", "impl_id"), ("tests", "test_id"),
                            ("acceptances", "acceptance_id")):
        records = payload.get(section, [])
        if not isinstance(records, list):
            raise TraceError("%s must be an array" % section)
        seen = set()
        for i, record in enumerate(records):
            location = "%s[%d]" % (section, i)
            if not isinstance(record, dict):
                raise TraceError("%s must be an object" % location)
            value = record.get(id_key)
            if not _known_text(value) or value != value.strip():
                raise TraceError("%s.%s must be a nonblank, unpadded ID" % (location, id_key))
            if value in seen:
                raise TraceError("%s repeats %s %r" % (location, id_key, value))
            seen.add(value)
            for key in ("request_id", "criterion_id", "superseded_by", "text", "ref",
                        "covered_by_regression_ref", "evidence_ref", "accepted_by_role",
                        "accepted_at", "result"):
                if key in record and record[key] is not None and not isinstance(record[key], str):
                    raise TraceError("%s.%s must be text or null" % (location, key))


class Example(object):
    def __init__(self, payload):
        _validate(payload)
        payload = copy.deepcopy(payload)
        self.payload = payload
        self.example_id = payload.get("example_id") or UNKNOWN
        self.style = payload.get("delivery_style")
        if self.style not in DELIVERY_STYLES:
            raise TraceError("delivery_style must be one of %s, got %r"
                             % (list(DELIVERY_STYLES), self.style))
        self.requests = payload.get("requests") or []
        self.criteria = payload.get("criteria") or []
        if not self.criteria:
            raise TraceError("an example with no acceptance criteria traces nothing")
        self.request_ids = set(r.get("request_id") for r in self.requests)
        self.criterion_ids = set(c.get("criterion_id") for c in self.criteria)
        self.impl_by_criterion = _index(payload.get("implementations"), "criterion_id")
        self.tests_by_criterion = _index(payload.get("tests"), "criterion_id")
        self.acc_by_criterion = _index(payload.get("acceptances"), "criterion_id")
        self.criteria_by_id = {c["criterion_id"]: c for c in self.criteria}
        self.results = [self._evaluate(c) for c in self.criteria]

    # -- link integrity ----------------------------------------------------
    def dangling_links(self):
        out = []
        for c in self.criteria:
            if c.get("request_id") not in self.request_ids:
                out.append({"record": c.get("criterion_id"), "field": "request_id",
                            "ref": c.get("request_id")})
            sup = c.get("superseded_by")
            if sup and sup not in self.criterion_ids:
                out.append({"record": c.get("criterion_id"), "field": "superseded_by", "ref": sup})
        for section, key, idfield in (("implementations", "criterion_id", "impl_id"),
                                      ("tests", "criterion_id", "test_id"),
                                      ("acceptances", "criterion_id", "acceptance_id")):
            for rec in self.payload.get(section) or []:
                if rec.get(key) not in self.criterion_ids:
                    out.append({"record": rec.get(idfield), "field": key, "ref": rec.get(key)})
        return out

    def _has_broken_link(self, criterion):
        cid = criterion.get("criterion_id")
        for d in self.dangling_links():
            if d["field"] in ("request_id", "superseded_by") and d["record"] == cid:
                return d
            if d["field"] == "criterion_id" and d["ref"] == cid:
                return d
        return None

    # -- the chain ---------------------------------------------------------
    def _evaluate(self, criterion):
        cid = criterion.get("criterion_id")
        revision = criterion.get("revision", UNKNOWN)
        detail = []

        broken = self._has_broken_link(criterion)
        if broken:
            detail.append("%s.%s points at %r, which is not in this example"
                          % (broken["record"], broken["field"], broken["ref"]))
            return self._result(criterion, "BROKEN_LINK", detail)

        if not _revision(revision):
            detail.append("criterion revision is unknown or not a positive integer; ask for its exact revision")
            return self._result(criterion, "BROKEN_LINK", detail)

        if criterion.get("superseded_by"):
            seen = {cid}
            node = criterion
            while node.get("superseded_by"):
                successor = node["superseded_by"]
                next_node = self.criteria_by_id.get(successor)
                if successor in seen or next_node is None:
                    detail.append("successor lineage is cyclic or incomplete at %s" % successor)
                    return self._result(criterion, "BROKEN_LINK", detail)
                if next_node.get("request_id") != criterion.get("request_id"):
                    detail.append("successor %s belongs to another request; reconcile the change record" % successor)
                    return self._result(criterion, "BROKEN_LINK", detail)
                if not _revision(next_node.get("revision")):
                    detail.append("successor %s has no explicit valid revision" % successor)
                    return self._result(criterion, "BROKEN_LINK", detail)
                seen.add(successor)
                node = next_node
            detail.append("replaced by %s" % criterion["superseded_by"])
            return self._result(criterion, "SUPERSEDED", detail)

        impls = self.impl_by_criterion.get(cid, [])
        if not impls:
            return self._result(criterion, "NOT_IMPLEMENTED", detail)
        if any(not _known_text(i.get("ref")) for i in impls):
            detail.append("implementation record has no evidence locator; ask for the change record")
            return self._result(criterion, "BROKEN_LINK", detail)
        detail.append("implemented by %s" % ", ".join(i.get("impl_id", UNKNOWN) for i in impls))

        tests = self.tests_by_criterion.get(cid, [])
        coverage = (criterion.get("covered_by_regression_ref") or "").strip()
        if not tests:
            if _known_text(coverage) and self.style == "maintenance_change":
                # Allowed, but only because the record SAYS so. The tool never
                # assumes a maintenance change is covered by something
                # existing; the locator has to be there.
                detail.append("no dedicated test; declared covered by %s" % coverage)
            else:
                return self._result(criterion, "UNTESTED", detail)
        else:
            if any(not _known_text(t.get("ref")) for t in tests):
                detail.append("test record has no evidence locator; ask for the test result record")
                return self._result(criterion, "BROKEN_LINK", detail)
            results = [t.get("result") for t in tests]
            if any(r != "PASS" for r in results):
                detail.append("test results: %s" % ", ".join(str(r) for r in results))
                return self._result(criterion, "TEST_NOT_PASSING", detail)
            detail.append("tests passing: %s" % ", ".join(t.get("test_id", UNKNOWN) for t in tests))

        accs = self.acc_by_criterion.get(cid, [])
        if not accs:
            detail.append("no user acceptance record")
            return self._result(criterion, "INCOMPLETE_ACCEPTANCE", detail)

        with_evidence = [a for a in accs if _known_text(a.get("evidence_ref"))]
        if not with_evidence:
            detail.append("acceptance recorded by %s with no evidence locator"
                          % ", ".join((a.get("accepted_by_role") or UNKNOWN) for a in accs))
            return self._result(criterion, "INCOMPLETE_ACCEPTANCE", detail)

        if any(not _revision(a.get("criterion_revision")) for a in with_evidence):
            detail.append("acceptance revision is unknown or not a positive integer; ask which version was accepted")
            return self._result(criterion, "INCOMPLETE_ACCEPTANCE", detail)
        if any(a["criterion_revision"] > revision for a in with_evidence):
            detail.append("acceptance points to a future revision; reconcile the criterion and acceptance records")
            return self._result(criterion, "BROKEN_LINK", detail)
        current = [a for a in with_evidence if a["criterion_revision"] == revision]
        if not current:
            accepted_revs = sorted(set(a["criterion_revision"] for a in with_evidence))
            detail.append("accepted against revision %s; this criterion is at revision %s"
                          % (", ".join(str(r) for r in accepted_revs), revision))
            return self._result(criterion, "ACCEPTED_AGAINST_SUPERSEDED_REVISION", detail,
                                rev=revision)

        if any(not _known_text(a.get(field)) for a in current
               for field in ("accepted_by_role", "accepted_at")):
            detail.append("current acceptance has an unknown role or date; ask who accepted it and when")
            return self._result(criterion, "INCOMPLETE_ACCEPTANCE", detail)
        detail.append("accepted by %s on %s"
                      % (current[0].get("accepted_by_role", UNKNOWN),
                         current[0].get("accepted_at", UNKNOWN)))
        return self._result(criterion, "TRACED", detail)

    def _result(self, criterion, state, detail, rev=None):
        return {
            "criterion_id": criterion.get("criterion_id", UNKNOWN),
            "request_id": criterion.get("request_id", UNKNOWN),
            "text": criterion.get("text", UNKNOWN),
            "revision": criterion.get("revision", UNKNOWN),
            "state": state,
            "detail": detail,
            "follow_up": FOLLOW_UP[state].format(rev=rev if rev is not None else "?"),
            "closed": state in CLOSED_STATES,
        }

    # -- verdict -----------------------------------------------------------
    def counts(self):
        out = dict((s, 0) for s in STATES)
        for r in self.results:
            out[r["state"]] += 1
        return out

    def open_criteria(self):
        return [r for r in self.results if not r["closed"]]

    def verdict(self):
        """There is no percentage here. Either every current criterion traces
        to a recorded acceptance of the current revision, or the question is
        still open and the open rows say why."""
        current = [r for r in self.results if r["state"] != "SUPERSEDED"]
        if not current or self.dangling_links():
            return "NOT_ESTABLISHED"
        return "EVIDENCED" if all(r["state"] == "TRACED" for r in current) else "NOT_ESTABLISHED"

    def as_dict(self):
        return {
            "meta": {
                "work_order": "UIOWA-042",
                "solicitation_id": "18649",
                "synthetic": True,
                "authority": "FICTIONAL_REHEARSAL_ONLY",
                "prohibited_interpretation": [
                    "University of Iowa finding",
                    "statement of current University delivery practice",
                    "compliance or certification conclusion",
                    "employee performance assessment",
                ],
                "example_id": self.example_id,
                "delivery_style": self.style,
            },
            "verdict": self.verdict(),
            "verdict_meaning": (
                "every current criterion traces to a recorded acceptance of the current revision"
                if self.verdict() == "EVIDENCED" else
                ("unresolved record references remain; see the broken references"
                 if self.dangling_links() else
                 "at least one criterion has an open question; see the follow-ups")),
            "counts": self.counts(),
            "open_criteria": len(self.open_criteria()),
            "criteria": self.results,
            "dangling_links": self.dangling_links(),
        }


# The original ten columns keep their order and criterion-level meaning.
# Packet diagnostics repeat on each row; an orphan is not a fake criterion.
SHEET_COLUMNS = ("example_id", "delivery_style", "request_id", "criterion_id", "revision",
                 "state", "closed", "detail", "follow_up", "text",
                 "packet_verdict", "packet_open_criteria", "packet_dangling_link_count",
                 "packet_dangling_links", "packet_follow_up")


def write_sheet(examples, path):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(SHEET_COLUMNS)
        for ex in examples:
            dangling = ex.dangling_links()
            packet_fields = [ex.verdict(), len(ex.open_criteria()), len(dangling),
                             json.dumps(dangling, ensure_ascii=False, sort_keys=True),
                             ("Resolve the listed record references before closing this packet."
                              if dangling else
                              ("Review the open criterion follow-ups."
                               if ex.open_criteria() else "No open packet question."))]
            for r in ex.results:
                w.writerow([ex.example_id, ex.style, r["request_id"], r["criterion_id"],
                            r["revision"], r["state"], r["closed"], "; ".join(r["detail"]),
                            r["follow_up"], r["text"]] + packet_fields)


def render_markdown(examples):
    lines = []
    lines.append("# Requirements-to-acceptance traceability (UIOWA-042)")
    lines.append("")
    lines.append("**These examples are fictional.** Every request, criterion, implementation,")
    lines.append("test and acceptance record below was invented for rehearsal. Not a")
    lines.append("University of Iowa finding and not a statement about University delivery")
    lines.append("practice. No individual is named.")
    lines.append("")
    lines.append("The chain: request → acceptance criterion → implementation → test → user")
    lines.append("acceptance. A criterion closes only when every link resolves **and** the")
    lines.append("acceptance is recorded against the criterion's current revision.")
    lines.append("")
    for ex in examples:
        d = ex.as_dict()
        lines.append("## %s — %s" % (ex.example_id, ex.style))
        lines.append("")
        lines.append("**Verdict: `%s`** — %s" % (d["verdict"], d["verdict_meaning"]))
        lines.append("")
        lines.append("| State | Criteria | Meaning |")
        lines.append("| --- | ---: | --- |")
        for state in STATES:
            if d["counts"][state]:
                lines.append("| %s | %d | %s |" % (state, d["counts"][state], STATE_MEANING[state]))
        lines.append("")
        lines.append("| Criterion | Rev | State | What the records show |")
        lines.append("| --- | ---: | --- | --- |")
        for r in d["criteria"]:
            lines.append("| `%s` | %s | %s | %s |"
                         % (r["criterion_id"], r["revision"], r["state"], "; ".join(r["detail"]) or "—"))
        lines.append("")
        open_rows = [r for r in d["criteria"] if not r["closed"]]
        if open_rows:
            lines.append("### Follow-up questions")
            lines.append("")
            lines.append("These are questions, not conclusions. Nothing below is resolved by")
            lines.append("this tool.")
            lines.append("")
            for r in open_rows:
                lines.append("- **`%s`** (%s) — %s" % (r["criterion_id"], r["state"], r["follow_up"]))
            lines.append("")
        if d["dangling_links"]:
            lines.append("### Broken references")
            lines.append("")
            for dl in d["dangling_links"]:
                lines.append("- `%s`.`%s` → `%s` (not in this example)"
                             % (dl["record"], dl["field"], dl["ref"]))
            lines.append("")
    lines.append("## Still UNKNOWN (University inputs not collected)")
    lines.append("")
    for item in (
        "where business requests are recorded, and whether acceptance criteria live with them",
        "who is empowered to accept delivered work, by role",
        "whether acceptance is recorded at all for maintenance changes",
        "what happens to a recorded acceptance when the requirement later changes",
        "whether regression coverage is asserted anywhere a locator could be read from",
    ):
        lines.append("- %s" % item)
    lines.append("")
    return "\n".join(lines)


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise TraceError("duplicate JSON key %r" % key)
        result[key] = value
    return result


def _constant(value):
    raise TraceError("non-finite JSON number %s" % value)


def load(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh, object_pairs_hook=_object, parse_constant=_constant)
    except json.JSONDecodeError as exc:
        raise ValueError("%s is not valid JSON: line %d column %d: %s"
                         % (path, exc.lineno, exc.colno, exc.msg))
    except OSError as exc:
        raise ValueError("cannot read %s: %s" % (path, exc.strerror))


def _same_file(left, right):
    """Detect stable path, symlink and hardlink aliases before any output write.

    This is a preflight, not a lock or a concurrent-filesystem guarantee.
    """
    if os.path.normcase(os.path.realpath(left)) == os.path.normcase(os.path.realpath(right)):
        return True
    try:
        return os.path.samefile(left, right)
    except FileNotFoundError:
        return False


def _output_paths(inputs, outdir):
    paths = [os.path.join(outdir, name) for name in
             ("traceability_sheet.csv", "traceability.json", "traceability_report.md")]
    for index, target in enumerate(paths):
        for source in inputs:
            if _same_file(source, target):
                raise TraceError("output %s aliases input %s; choose a separate output directory"
                                 % (target, source))
        for previous in paths[:index]:
            if _same_file(previous, target):
                raise TraceError("output files alias each other: %s and %s" % (previous, target))
    return paths


def main(argv=None):
    p = argparse.ArgumentParser(description="Requirements-to-acceptance traceability.")
    p.add_argument("--input", required=True, nargs="+")
    p.add_argument("--outdir")
    p.add_argument("--print", dest="do_print", action="store_true")
    args = p.parse_args(argv)

    examples = []
    for path in args.input:
        try:
            examples.append(Example(load(path)))
        except (ValueError, TraceError) as exc:
            sys.stderr.write("error: %s\n" % exc)
            return 2

    if args.outdir:
        try:
            # Resolve every collision before creating a directory or replacing any report.
            sheet_path, json_path, markdown_path = _output_paths(args.input, args.outdir)
            os.makedirs(args.outdir, exist_ok=True)
            write_sheet(examples, sheet_path)
            with open(json_path, "w", encoding="utf-8") as fh:
                json.dump([e.as_dict() for e in examples], fh, indent=2, sort_keys=True)
            with open(markdown_path, "w", encoding="utf-8") as fh:
                fh.write(render_markdown(examples))
        except (OSError, ValueError) as exc:
            sys.stderr.write("error: cannot publish reports: %s\n" % exc)
            return 2
        sys.stdout.write("wrote 3 files to %s\n" % args.outdir)

    if args.do_print or not args.outdir:
        sys.stdout.write(render_markdown(examples))

    total_open = sum(len(e.open_criteria()) for e in examples)
    sys.stderr.write("examples=%d criteria=%d open=%d verdicts=%s\n"
                     % (len(examples), sum(len(e.results) for e in examples), total_open,
                        ",".join(e.verdict() for e in examples)))
    return 0 if all(e.verdict() == "EVIDENCED" for e in examples) else 1


if __name__ == "__main__":
    raise SystemExit(main())
