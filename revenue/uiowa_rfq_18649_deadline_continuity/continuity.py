#!/usr/bin/env python3
"""UIOWA-107 -- research-deadline continuity: options, verdicts, and the
evidence that would settle them.

Run:
    python3 continuity.py --input fixtures/ris_deadline_scenario.json --outdir out
    python3 continuity.py --input fixtures/ris_deadline_scenario.json --print

Python 3 standard library only. No network. Deterministic.

The work order asks for "practical preparation choices AND the evidence needed
to distinguish them". The tempting build is: compute an exposure number per
option, print the winner. That is false certainty dressed as analysis, and it
is worse than useless on a scenario whose central input nobody has asked for
yet.

So this tool is built to refuse a conclusion it cannot support:

  * Each option's in-window exposure is an INTERVAL, summed from explicit
    assumptions (see intervals.py).
  * An option's verdict is FITS / AT_RISK / NOT_DETERMINED -- and
    NOT_DETERMINED whenever the intervals overlap or a bound is missing.
  * Two options are compared only when one's range ends before the other's
    begins. Otherwise the pair is NOT_SEPARABLE and says so.
  * For every unseparated pair it then does the useful thing: works out which
    assumption, if resolved, would separate them, and emits that as a
    concrete evidence request. When no single assumption would do it, it says
    that too.

There is no `recommended` field anywhere in the output, by design. The tool
narrows the question and names what to go find out; a person decides.
"""

import argparse
import csv
import json
import os
import sys

from intervals import Assumption, AssumptionError, Interval

VERDICTS = ("FITS", "AT_RISK", "NOT_DETERMINED")

VERDICT_MEANING = {
    "FITS": "the worst case still sits inside the capacity available in the window",
    "AT_RISK": "even the best case exceeds the capacity available in the window",
    "NOT_DETERMINED": "the ranges overlap or a bound is missing; not answerable yet",
}


class ScenarioError(ValueError):
    pass


class Option(object):
    __slots__ = ("id", "label", "description", "exposure_terms", "capacity_terms", "not_modelled")

    def __init__(self, record):
        self.id = record.get("id")
        self.label = record.get("label")
        self.description = record.get("description", "")
        self.exposure_terms = record.get("exposure_terms") or []
        self.capacity_terms = record.get("capacity_terms") or []
        self.not_modelled = record.get("not_modelled") or []
        if not self.id or not self.label:
            raise ScenarioError("an option needs an id and a label")
        if not self.exposure_terms:
            raise ScenarioError("%s: an option with no exposure terms models nothing" % self.id)
        if not self.capacity_terms:
            raise ScenarioError("%s: an option must say which capacity it draws on" % self.id)


def _sum_terms(terms, assumptions, pins=None):
    """Sum a list of {assumption_ref, multiplier} over the assumption set.

    `pins` maps assumption id -> Interval, used by the sensitivity walk to ask
    "what if this one were resolved to here?". A pin of None means the end
    could not be pinned, and the whole sum is unanswerable -- which is
    reported, not silently skipped.
    """
    total = Interval(0, 0)
    for term in terms:
        ref = term.get("assumption_ref")
        if ref not in assumptions:
            raise ScenarioError("term references unknown assumption %r" % ref)
        if pins and ref in pins:
            pinned = pins[ref]
            if pinned is None:
                return None
            base = pinned
        else:
            base = assumptions[ref].interval()
        total = total + base.scaled(term.get("multiplier", 1))
    return total


def verdict_for(exposure, capacity):
    if exposure is None or capacity is None:
        return "NOT_DETERMINED"
    if exposure.strictly_below(capacity):
        return "FITS"
    if capacity.strictly_below(exposure):
        return "AT_RISK"
    return "NOT_DETERMINED"


def unbounded_inputs(terms, assumptions):
    """Which assumptions in this term list have no upper bound. These are the
    reason a verdict comes out NOT_DETERMINED, and naming them is the single
    most actionable line in the report."""
    out = []
    for term in terms:
        a = assumptions[term["assumption_ref"]]
        if not a.interval().bounded:
            out.append(a.id)
    return sorted(set(out))


class Analysis(object):
    def __init__(self, scenario):
        self.scenario = scenario
        self.assumptions = {}
        for record in scenario.get("assumptions", []):
            a = Assumption(record)
            if a.id in self.assumptions:
                raise ScenarioError("duplicate assumption id %r" % a.id)
            self.assumptions[a.id] = a
        self.options = [Option(r) for r in scenario.get("options", [])]
        ids = [o.id for o in self.options]
        if len(ids) != len(set(ids)):
            raise ScenarioError("duplicate option id in scenario")
        if not self.options:
            raise ScenarioError("a scenario with no options cannot be analysed")
        self.results = self._evaluate()

    def _evaluate(self):
        out = []
        for option in self.options:
            exposure = _sum_terms(option.exposure_terms, self.assumptions)
            capacity = _sum_terms(option.capacity_terms, self.assumptions)
            v = verdict_for(exposure, capacity)
            blocking = []
            if v == "NOT_DETERMINED":
                blocking = sorted(set(
                    unbounded_inputs(option.exposure_terms, self.assumptions)
                    + unbounded_inputs(option.capacity_terms, self.assumptions)
                ))
            out.append(
                {
                    "option_id": option.id,
                    "label": option.label,
                    "description": option.description,
                    "exposure": exposure.as_dict(),
                    "capacity": capacity.as_dict(),
                    "verdict": v,
                    "verdict_meaning": VERDICT_MEANING[v],
                    "unbounded_inputs": blocking,
                    "not_modelled": list(option.not_modelled),
                }
            )
        return out

    # -- pairwise comparison -------------------------------------------------
    def _exposure(self, option, pins=None):
        return _sum_terms(option.exposure_terms, self.assumptions, pins)

    def comparisons(self):
        """Every ordered pair, with a separability judgement and -- when not
        separable -- the evidence that would separate it."""
        out = []
        for i, a in enumerate(self.options):
            for b in self.options[i + 1:]:
                ea, eb = self._exposure(a), self._exposure(b)
                if ea.strictly_below(eb):
                    out.append(self._separated(a, b, ea, eb, a.id))
                elif eb.strictly_below(ea):
                    out.append(self._separated(a, b, ea, eb, b.id))
                else:
                    out.append(self._unseparated(a, b, ea, eb))
        return out

    def _separated(self, a, b, ea, eb, lower_id):
        return {
            "pair": [a.id, b.id],
            "status": "SEPARATED",
            "lower_in_window_exposure": lower_id,
            "detail": "%s ends before %s begins, so the comparison holds across the whole range"
                      % (lower_id, b.id if lower_id == a.id else a.id),
            "exposures": {a.id: ea.as_dict(), b.id: eb.as_dict()},
            "discriminating_assumptions": [],
            "bound_required": [],
            "evidence_requests": [],
        }

    def _unseparated(self, a, b, ea, eb):
        """Sensitivity walk: pin each assumption to each end and re-ask."""
        discriminating = []
        bound_required = []
        for aid, assumption in sorted(self.assumptions.items()):
            for end in ("low", "high"):
                pinned = assumption.pinned(end)
                if pinned is None:
                    # The UNKNOWN upper bound. It cannot be probed, and that
                    # is the finding: this input must be bounded before any
                    # comparison involving it can close.
                    if aid not in bound_required and self._feeds(aid, a, b):
                        bound_required.append(aid)
                    continue
                pins = {aid: pinned}
                pa, pb = self._exposure(a, pins), self._exposure(b, pins)
                if pa is None or pb is None:
                    continue
                if pa.strictly_below(pb) or pb.strictly_below(pa):
                    if aid not in discriminating:
                        discriminating.append(aid)
                    break

        requests = []

        # Two options can have identical in-window exposure and differ only in
        # the capacity they draw on -- OPT-A vs OPT-D is exactly that shape.
        # Comparing exposure alone would report "not separable" and say
        # nothing useful, when the real difference is a capacity input nobody
        # has confirmed. Name it.
        capacity_delta = self._capacity_difference(a, b)
        if ea == eb and capacity_delta:
            for aid in capacity_delta:
                assumption = self.assumptions[aid]
                requests.append({
                    "assumption_ref": aid,
                    "ask": "Confirm: %s" % assumption.statement,
                    "why": "%s and %s have identical in-window exposure; they differ only in "
                           "capacity, and this %s input is the whole difference"
                           % (a.id, b.id, assumption.basis),
                })

        for aid in bound_required:
            requests.append({
                "assumption_ref": aid,
                "ask": "Obtain any upper bound for: %s" % self.assumptions[aid].statement,
                "why": "with no upper bound on this input, %s and %s cannot be compared at all"
                       % (a.id, b.id),
            })
        for aid in discriminating:
            requests.append({
                "assumption_ref": aid,
                "ask": "Resolve: %s" % self.assumptions[aid].statement,
                "why": "pinning this input separates %s from %s; it is the input the choice turns on"
                       % (a.id, b.id),
            })
        if not requests:
            requests.append({
                "assumption_ref": None,
                "ask": "No single assumption separates these two options.",
                "why": "they remain comparable only on grounds this model does not carry; "
                       "do not manufacture a preference from the numbers",
            })
        return {
            "pair": [a.id, b.id],
            "status": "NOT_SEPARABLE",
            "lower_in_window_exposure": None,
            "detail": "the exposure ranges overlap; neither option is lower across the whole range",
            "exposures": {a.id: ea.as_dict(), b.id: eb.as_dict()},
            "discriminating_assumptions": discriminating,
            "bound_required": bound_required,
            "evidence_requests": requests,
        }

    def _capacity_difference(self, a, b):
        """Capacity assumptions present for one option and not the other."""
        ca = set(t["assumption_ref"] for t in a.capacity_terms)
        cb = set(t["assumption_ref"] for t in b.capacity_terms)
        return sorted(ca ^ cb)

    def _feeds(self, assumption_id, *options):
        for option in options:
            for term in option.exposure_terms + option.capacity_terms:
                if term.get("assumption_ref") == assumption_id:
                    return True
        return False

    def unresolved_assumptions(self):
        return sorted(a.id for a in self.assumptions.values() if not a.resolved)

    def as_dict(self):
        return {
            "meta": {
                "work_order": "UIOWA-107",
                "solicitation_id": "18649",
                "synthetic": True,
                "authority": "FICTIONAL_REHEARSAL_ONLY",
                "prohibited_interpretation": [
                    "University of Iowa finding",
                    "statement of current University capacity or schedule",
                    "a commitment, appointment, or scheduled date",
                    "employee performance assessment",
                ],
                "scenario_id": self.scenario.get("scenario_id", "UNKNOWN"),
                "service": self.scenario.get("service", "UNKNOWN"),
                "unit": self.scenario.get("unit_of_measure", "hours"),
            },
            "deadline": self.scenario.get("deadline", {}),
            "assumptions": [self.assumptions[k].as_dict() for k in sorted(self.assumptions)],
            "unresolved_assumptions": self.unresolved_assumptions(),
            "options": self.results,
            "comparisons": self.comparisons(),
        }


def _fmt(interval_dict):
    high = interval_dict["high"]
    return "%g–%s" % (interval_dict["low"], "%g" % high if high is not None else "UNBOUNDED")


def write_csv(analysis, path):
    cols = ("option_id", "label", "exposure_low", "exposure_high", "capacity_low",
            "capacity_high", "verdict", "unbounded_inputs", "not_modelled")
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for r in analysis.results:
            w.writerow([
                r["option_id"], r["label"], r["exposure"]["low"],
                "" if r["exposure"]["high"] is None else r["exposure"]["high"],
                r["capacity"]["low"],
                "" if r["capacity"]["high"] is None else r["capacity"]["high"],
                r["verdict"], "; ".join(r["unbounded_inputs"]), "; ".join(r["not_modelled"]),
            ])


def write_evidence_csv(analysis, path):
    cols = ("pair", "status", "assumption_ref", "ask", "why")
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for c in analysis.comparisons():
            for r in c["evidence_requests"]:
                w.writerow([" vs ".join(c["pair"]), c["status"],
                            r["assumption_ref"] or "", r["ask"], r["why"]])


def render_markdown(analysis):
    d = analysis.as_dict()
    lines = []
    lines.append("# Research-deadline continuity (UIOWA-107)")
    lines.append("")
    lines.append("**This scenario is fictional.** The deadline, the shared identity service,")
    lines.append("the application change and every number below were invented for rehearsal.")
    lines.append("It is not a University of Iowa finding, not a statement about University")
    lines.append("capacity, and not a commitment to any date.")
    lines.append("")
    dl = d["deadline"]
    lines.append("Scenario `%s` — service %s. Deadline: **%s** (%s)." % (
        d["meta"]["scenario_id"], d["meta"]["service"],
        dl.get("label", "UNKNOWN"), dl.get("date_basis", "relative to kickoff")))
    lines.append("")
    lines.append("## Assumptions, stated in the open")
    lines.append("")
    lines.append("| ID | Basis | Range (%s) | Statement | Stated by |" % d["meta"]["unit"])
    lines.append("| --- | --- | --- | --- | --- |")
    for a in d["assumptions"]:
        rng = "—" if not a["resolved"] else ("%g–%g" % (a["low"], a["high"]))
        lines.append("| %s | %s | %s | %s | %s |" % (
            a["id"], a["basis"], rng, a["statement"], a["stated_by"] or "UNKNOWN"))
    lines.append("")
    if d["unresolved_assumptions"]:
        lines.append("**%d assumption(s) are UNKNOWN: %s.** They carry no numbers. An UNKNOWN"
                     % (len(d["unresolved_assumptions"]), ", ".join(d["unresolved_assumptions"])))
        lines.append("input is not given a default or a midpoint — it propagates as an")
        lines.append("unbounded range, and any conclusion resting on it comes out")
        lines.append("`NOT_DETERMINED`. That is the honest answer.")
        lines.append("")
    lines.append("## Preparation options")
    lines.append("")
    lines.append("| Option | In-window exposure | Capacity | Verdict |")
    lines.append("| --- | --- | --- | --- |")
    for r in d["options"]:
        lines.append("| **%s** %s | %s | %s | `%s` |" % (
            r["option_id"], r["label"], _fmt(r["exposure"]), _fmt(r["capacity"]), r["verdict"]))
    lines.append("")
    for r in d["options"]:
        lines.append("### %s — %s" % (r["option_id"], r["label"]))
        lines.append("")
        if r["description"]:
            lines.append(r["description"])
            lines.append("")
        lines.append("- Verdict `%s` — %s" % (r["verdict"], r["verdict_meaning"]))
        if r["unbounded_inputs"]:
            lines.append("- Unanswerable because these inputs have no upper bound: %s"
                         % ", ".join("`%s`" % u for u in r["unbounded_inputs"]))
        for nm in r["not_modelled"]:
            lines.append("- **Not modelled here:** %s" % nm)
        lines.append("")
    lines.append("## Can the options be told apart?")
    lines.append("")
    for c in d["comparisons"]:
        lines.append("### %s" % " vs ".join(c["pair"]))
        lines.append("")
        lines.append("- `%s` — %s" % (c["status"], c["detail"]))
        if c["lower_in_window_exposure"]:
            lines.append("- Lower **in-window exposure**: `%s`. That is a statement about hours"
                         % c["lower_in_window_exposure"])
            lines.append("  inside the reporting window only — it is not a recommendation, and it")
            lines.append("  does not price anything listed under *Not modelled*.")
        for r in c["evidence_requests"]:
            lines.append("- **Evidence needed:** %s" % r["ask"])
            lines.append("  - Why: %s" % r["why"])
        lines.append("")
    lines.append("## What this tool does not do")
    lines.append("")
    lines.append("- It never marks an option recommended. It narrows the question and names")
    lines.append("  what to go find out; a person decides.")
    lines.append("- It does not rank teams, units or people. The comparison is between")
    lines.append("  preparation options.")
    lines.append("- It runs no load test and reads no live system. Availability is a stated")
    lines.append("  scenario assumption, never an appointment or a commitment.")
    lines.append("")
    lines.append("## Still UNKNOWN (University inputs not collected)")
    lines.append("")
    for item in self_unknowns():
        lines.append("- %s" % item)
    lines.append("")
    return "\n".join(lines)


def self_unknowns():
    return (
        "the real research-administration reporting calendar and its true cutoff",
        "whether the shared identity service publishes a change-freeze window at all",
        "who is empowered to defer a scheduled application change, and on what notice",
        "actual analyst capacity in the reporting window, as opposed to roster headcount",
        "whether temporary capacity is fundable at all in that period",
    )


def load(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as exc:
        raise ValueError("%s is not valid JSON: line %d column %d: %s" % (path, exc.lineno, exc.colno, exc.msg))
    except OSError as exc:
        raise ValueError("cannot read %s: %s" % (path, exc.strerror))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Analyse a deadline-continuity scenario.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--outdir")
    parser.add_argument("--print", dest="do_print", action="store_true")
    args = parser.parse_args(argv)

    try:
        scenario = load(args.input)
    except ValueError as exc:
        sys.stderr.write("error: %s\n" % exc)
        return 2

    try:
        analysis = Analysis(scenario)
    except (ScenarioError, AssumptionError) as exc:
        sys.stderr.write("error: %s\n" % exc)
        return 2

    if args.outdir:
        os.makedirs(args.outdir, exist_ok=True)
        write_csv(analysis, os.path.join(args.outdir, "continuity_options.csv"))
        write_evidence_csv(analysis, os.path.join(args.outdir, "evidence_requests.csv"))
        with open(os.path.join(args.outdir, "continuity_analysis.json"), "w", encoding="utf-8") as fh:
            json.dump(analysis.as_dict(), fh, indent=2, sort_keys=True)
        with open(os.path.join(args.outdir, "continuity_report.md"), "w", encoding="utf-8") as fh:
            fh.write(render_markdown(analysis))
        sys.stdout.write("wrote 4 files to %s\n" % args.outdir)

    if args.do_print or not args.outdir:
        sys.stdout.write(render_markdown(analysis))

    comparisons = analysis.comparisons()
    undetermined = len([r for r in analysis.results if r["verdict"] == "NOT_DETERMINED"])
    unseparated = len([c for c in comparisons if c["status"] == "NOT_SEPARABLE"])
    sys.stderr.write(
        "options=%d undetermined=%d pairs=%d unseparated=%d unresolved_assumptions=%d\n"
        % (len(analysis.results), undetermined, len(comparisons), unseparated,
           len(analysis.unresolved_assumptions()))
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
