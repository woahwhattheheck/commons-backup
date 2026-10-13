#!/usr/bin/env python3
"""UIOWA-029 -- prioritization method and horizon organization.

Run:
    python3 method.py --render          # writes 29-prioritization-method.md
    python3 method.py --check           # validate the backlog, exit 1 on a violation
    python3 method.py --print

Python 3 standard library only. No network. No clock. Deterministic.

**This lane does not contain a scoring model.** The weighting of quality,
security and delivery against complexity is already implemented in
`../uiowa_rfq_18649_prioritization/` (UIOWA-084) with its own weight
profiles, its own sensitivity sweep, and its own `0` versus `UNKNOWN` rule.
Building a second one would give the engagement two methods that disagree.
This lane binds to that one and adds the part it does not do: organizing
ranked recommendations into the RFQ's 0-90, 90-180 and 180+ day horizons.

Two quantities are deliberately kept apart, and conflating them is the error
this method exists to prevent:

  complexity   -- UIOWA-084's 1..5 band. An input to RANKING. It says how
                  hard something is relative to other items.
  effort range -- low/high days. An input to SCHEDULING. It says how much
                  calendar a horizon has to absorb.

A high-complexity item is not automatically a long one, and a cheap item is
not automatically a quick win. The horizon rules below use effort; the
ranking uses complexity; neither substitutes for the other.

Every rule has an id, is stated in the generated method document, and is
checked by `--check`. The tool PROPOSES a horizon from the rules and compares
it against the horizon the backlog declares. It never overwrites a declared
horizon: a disagreement is reported for a person to settle.
"""

import argparse
import json
import math
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
UNKNOWN = "UNKNOWN"

HORIZONS = ("0-90", "90-180", "180+")
HORIZON_ORDER = {"0-90": 0, "90-180": 1, "180+": 2}
NEEDS_ESTIMATE = "NEEDS_ESTIMATE"
UNASSIGNED = "UNASSIGNED"
INVALID_HORIZON = "INVALID_HORIZON"

# Parameters, stated rather than buried. Change them in backlog.json and
# re-run to see the effect.
DEFAULT_PARAMETERS = {
    "quick_win_max_effort_days": 10,
    "high_effort_min_effort_days": 60,
}

RULES = {
    "H1": ("An item whose effort is UNKNOWN may not be proposed for 0-90. "
           "A window cannot be committed to work nobody has sized. It is "
           "proposed as NEEDS_ESTIMATE, which is not a horizon."),
    "H2": ("A prerequisite may not sit in a later horizon than the item that "
           "needs it."),
    "H3": ("A quick win is an item with effort at or under the quick-win "
           "threshold, at least one assessed non-zero effect, and no "
           "prerequisites. It is proposed for 0-90."),
    "H4": ("An item with prerequisites is proposed no earlier than the "
           "horizon of its latest prerequisite."),
    "H5": ("An item whose lower effort bound reaches the high-effort "
           "threshold is proposed for 180+ unless the backlog declares "
           "otherwise with a stated reason."),
    "H6": ("Effort is a range. A point estimate is permitted but is flagged, "
           "because a single number states a certainty the estimator may not "
           "have."),
    "H7": ("A declared horizon is never overwritten. Where the proposal and "
           "the declaration differ, both are shown and the difference is "
           "reported."),
}

VIOLATION_CODES = (
    "PREREQUISITE_AFTER_DEPENDENT",
    "UNKNOWN_EFFORT_DECLARED_IN_FIRST_HORIZON",
    "DANGLING_PREREQUISITE",
    "DUPLICATE_RECOMMENDATION_ID",
    "UNKNOWN_HORIZON_VALUE",
    "EFFORT_RANGE_REVERSED",
    "HIGH_EFFORT_MOVED_EARLIER_WITHOUT_REASON",
    "PREREQUISITE_CYCLE",
)


class MethodError(ValueError):
    pass


def _validate_document(doc):
    """Validate shapes before arithmetic; missing information stays missing."""
    if not isinstance(doc, dict):
        raise MethodError("backlog must be a JSON object")
    parameters = doc.get("parameters")
    if parameters is not None and not isinstance(parameters, dict):
        raise MethodError("parameters must be an object or null")

    def number(value, where):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise MethodError("%s must be a finite non-negative number" % where)
        if value < 0 or (isinstance(value, float) and not math.isfinite(value)):
            raise MethodError("%s must be a finite non-negative number" % where)

    for key in DEFAULT_PARAMETERS:
        if key in (parameters or {}):
            number(parameters[key], "parameters." + key)
    records = doc.get("recommendations")
    if not isinstance(records, list) or not records:
        raise MethodError("recommendations must be a non-empty list")
    for index, rec in enumerate(records):
        where = "recommendations[%d]" % index
        if not isinstance(rec, dict):
            raise MethodError("%s must be an object" % where)
        rid = rec.get("recommendation_id")
        if not isinstance(rid, str) or not rid.strip():
            raise MethodError("%s needs a non-empty recommendation_id" % where)
        for key in ("effort_days_low", "effort_days_high"):
            if rec.get(key) is not None:
                number(rec[key], where + "." + key)
        prereqs = rec.get("prerequisites")
        if prereqs is not None and (not isinstance(prereqs, list) or any(
                not isinstance(value, str) or not value.strip() for value in prereqs)):
            raise MethodError("%s.prerequisites must be a list of non-empty ids or null" % where)
        for key in ("declared_horizon", "declared_horizon_reason"):
            if rec.get(key) is not None and not isinstance(rec[key], str):
                raise MethodError("%s.%s must be text or null" % (where, key))
        effects = rec.get("effects")
        if effects is not None and not isinstance(effects, dict):
            raise MethodError("%s.effects must be an object or null" % where)
        for key, value in (effects or {}).items():
            if not isinstance(key, str) or not key:
                raise MethodError("%s.effects keys must be non-empty text" % where)
            if value is not None:
                number(value, where + ".effects." + key)


def _effort(rec):
    lo, hi = rec.get("effort_days_low"), rec.get("effort_days_high")
    if lo is None or hi is None:
        return None, None
    return lo, hi


def _assessed_effects(rec):
    """Effects that were actually assessed. A null is UNKNOWN, not zero --
    the same distinction UIOWA-084's data dictionary makes."""
    effects = rec.get("effects") or {}
    return dict((k, v) for k, v in effects.items() if v is not None)


class Backlog(object):
    def __init__(self, doc):
        _validate_document(doc)
        self.doc = doc
        self.parameters = dict(DEFAULT_PARAMETERS)
        self.parameters.update(doc.get("parameters") or {})
        self.records = doc.get("recommendations") or []
        if not self.records:
            raise MethodError("a backlog with no recommendations organizes nothing")
        self.by_id = {}
        self.violations = []
        for rec in self.records:
            rid = rec.get("recommendation_id")
            if not rid:
                raise MethodError("every recommendation needs a recommendation_id")
            if rid in self.by_id:
                self._violate(rid, "DUPLICATE_RECOMMENDATION_ID",
                              "id already used by an earlier record")
            self.by_id[rid] = rec
        self.results = self._evaluate()

    def _violate(self, rid, code, detail):
        assert code in VIOLATION_CODES, code
        self.violations.append({"recommendation_id": rid, "code": code, "detail": detail})

    # -- prerequisites -----------------------------------------------------
    def _prereqs(self, rec):
        return [p for p in (rec.get("prerequisites") or [])]

    def _cycle_from(self, rid, seen=None):
        # Iterative DFS preserves input-order diagnostics without Python's
        # recursion ceiling or repeated traversal of shared acyclic subgraphs.
        path = list(seen or [])
        active = {value: index for index, value in enumerate(path)}
        done = set()
        stack = [(rid, False)]
        while stack:
            current, leaving = stack.pop()
            if leaving:
                active.pop(current)
                path.pop()
                done.add(current)
                continue
            if current in active:
                return path[active[current]:] + [current]
            if current in done or current not in self.by_id:
                continue
            active[current] = len(path)
            path.append(current)
            stack.append((current, True))
            stack.extend((value, False) for value in reversed(self._prereqs(self.by_id[current])))
        return None

    # -- proposal ----------------------------------------------------------
    def _propose(self, rec):
        """Return (proposed_horizon, reasons, flags) from the stated rules."""
        rid = rec["recommendation_id"]
        reasons, flags = [], []
        lo, hi = _effort(rec)

        prereqs = self._prereqs(rec)
        missing = [p for p in prereqs if p not in self.by_id]
        for p in missing:
            self._violate(rid, "DANGLING_PREREQUISITE",
                          "%r does not name a recommendation in this backlog" % p)

        if lo is None:
            reasons.append("H1: effort is UNKNOWN, so no horizon can be proposed")
            return NEEDS_ESTIMATE, reasons, flags

        if lo == hi:
            flags.append("POINT_ESTIMATE")
            reasons.append("H6: effort given as a single number rather than a range")

        base = "0-90"
        if lo >= self.parameters["high_effort_min_effort_days"]:
            base = "180+"
            reasons.append("H5: lower effort bound %s reaches the high-effort threshold %s"
                           % (lo, self.parameters["high_effort_min_effort_days"]))
        elif not prereqs and hi <= self.parameters["quick_win_max_effort_days"] \
                and any(v > 0 for v in _assessed_effects(rec).values()):
            flags.append("QUICK_WIN")
            reasons.append("H3: no prerequisites, effort at or under %s days, at least one "
                           "assessed non-zero effect"
                           % self.parameters["quick_win_max_effort_days"])
        else:
            base = "90-180"
            reasons.append("H3 not met: neither a quick win nor high effort")

        # H4 -- never earlier than the latest prerequisite.
        for p in prereqs:
            if p not in self.by_id:
                continue
            p_horizon = self._declared(self.by_id[p])
            if p_horizon in HORIZON_ORDER and HORIZON_ORDER[p_horizon] >= HORIZON_ORDER.get(base, 0):
                later = HORIZONS[min(HORIZON_ORDER[p_horizon] + 1, len(HORIZONS) - 1)]
                reasons.append("H4: prerequisite %s is in %s, so this is proposed no earlier "
                               "than %s" % (p, p_horizon, later))
                base = later
        return base, reasons, flags

    def _declared(self, rec):
        return rec.get("declared_horizon")

    def _evaluate(self):
        out = []
        for rec in self.records:
            rid = rec["recommendation_id"]
            declared = self._declared(rec)
            if declared is not None and declared not in HORIZONS:
                self._violate(rid, "UNKNOWN_HORIZON_VALUE",
                              "%r is not one of %s" % (declared, list(HORIZONS)))
            lo, hi = _effort(rec)
            if lo is not None and hi is not None and hi < lo:
                self._violate(rid, "EFFORT_RANGE_REVERSED",
                              "effort_days_high %s is below effort_days_low %s" % (hi, lo))

            cycle = self._cycle_from(rid)
            if cycle:
                self._violate(rid, "PREREQUISITE_CYCLE", " -> ".join(cycle))

            proposed, reasons, flags = self._propose(rec)

            # H1 as a violation of a declaration, not just of a proposal.
            if lo is None and declared == "0-90":
                self._violate(rid, "UNKNOWN_EFFORT_DECLARED_IN_FIRST_HORIZON",
                              "declared 0-90 with no effort estimate")

            # H2 over the declared horizons, which is what a reader acts on.
            if declared in HORIZON_ORDER:
                for p in self._prereqs(rec):
                    prereq = self.by_id.get(p)
                    if prereq is None:
                        continue
                    p_declared = self._declared(prereq)
                    if p_declared in HORIZON_ORDER and \
                            HORIZON_ORDER[p_declared] > HORIZON_ORDER[declared]:
                        self._violate(rid, "PREREQUISITE_AFTER_DEPENDENT",
                                      "%s is declared %s but its prerequisite %s is declared %s"
                                      % (rid, declared, p, p_declared))

            # H5 override must be justified.
            if lo is not None and lo >= self.parameters["high_effort_min_effort_days"] \
                    and declared in ("0-90", "90-180") \
                    and not (rec.get("declared_horizon_reason") or "").strip():
                self._violate(rid, "HIGH_EFFORT_MOVED_EARLIER_WITHOUT_REASON",
                              "declared %s against a lower effort bound of %s with no stated reason"
                              % (declared, lo))

            out.append({
                "recommendation_id": rid,
                "title": rec.get("title", UNKNOWN),
                "group": rec.get("group", UNKNOWN),
                "area": rec.get("area", UNKNOWN),
                "complexity": rec.get("complexity", UNKNOWN),
                "effort_days_low": rec.get("effort_days_low") if rec.get("effort_days_low") is not None else UNKNOWN,
                "effort_days_high": rec.get("effort_days_high") if rec.get("effort_days_high") is not None else UNKNOWN,
                "effects_assessed": _assessed_effects(rec),
                "effects_unknown": sorted(k for k, v in (rec.get("effects") or {}).items()
                                          if v is None),
                "prerequisites": self._prereqs(rec),
                "declared_horizon": declared or UNKNOWN,
                "declared_horizon_reason": rec.get("declared_horizon_reason") or "",
                "proposed_horizon": proposed,
                # An item nobody has placed and nobody has sized is not a
                # disagreement; both readings say the same thing.
                "agrees": (declared == proposed
                           or (declared is None and proposed == NEEDS_ESTIMATE)),
                "proposal_reasons": reasons,
                "flags": flags,
            })
        return out

    # -- views -------------------------------------------------------------
    def by_horizon(self):
        out = dict((h, []) for h in HORIZONS)
        out[NEEDS_ESTIMATE] = []
        out[UNASSIGNED] = []
        out[INVALID_HORIZON] = []
        for rec, r in zip(self.records, self.results):
            declared = self._declared(rec)
            if declared in HORIZONS:
                key = declared
            elif declared is not None:
                key = INVALID_HORIZON
            elif r["proposed_horizon"] == NEEDS_ESTIMATE:
                key = NEEDS_ESTIMATE
            else:
                key = UNASSIGNED
            out[key].append(r["recommendation_id"])
        return out

    def disagreements(self):
        return [r for r in self.results if not r["agrees"]]

    def quick_wins(self):
        return [r for r in self.results if "QUICK_WIN" in r["flags"]]

    def prerequisite_work(self):
        needed = set()
        for r in self.results:
            needed.update(r["prerequisites"])
        return [r for r in self.results if r["recommendation_id"] in needed]

    def as_dict(self):
        return {
            "meta": {
                "work_order": "UIOWA-029",
                "solicitation_id": "18649",
                "synthetic": True,
                "authority": "FICTIONAL_REHEARSAL_ONLY",
                "prohibited_interpretation": [
                    "University of Iowa finding",
                    "a commitment to a delivery date",
                    "compliance or certification conclusion",
                    "employee performance assessment",
                ],
                "backlog_id": self.doc.get("backlog_id", UNKNOWN),
                "parameters": self.parameters,
                "scoring_model": "not implemented here; see ../uiowa_rfq_18649_prioritization "
                                 "(UIOWA-084)",
            },
            "recommendations": self.results,
            "by_horizon": self.by_horizon(),
            "disagreements": [r["recommendation_id"] for r in self.disagreements()],
            "violations": self.violations,
        }


def render(backlog):
    d = backlog.as_dict()
    L = []
    L.append("# 29 — Recommendation prioritization and horizon method")
    L.append("")
    L.append("Solicitation 18649, work order UIOWA-029.")
    L.append("")
    L.append("**The synthetic backlog below is fictional.** It is not a University of Iowa")
    L.append("finding and the horizons are not a commitment to any date.")
    L.append("")
    L.append("## What this method does not contain")
    L.append("")
    L.append("It contains **no scoring model**. Weighting quality, security and delivery")
    L.append("against complexity is implemented in `../uiowa_rfq_18649_prioritization/`")
    L.append("(UIOWA-084), with weight profiles, a sensitivity sweep and its own `0`-versus-")
    L.append("`UNKNOWN` rule. A second scoring model would give this engagement two methods")
    L.append("that disagree. This method binds to that one and adds horizon organization,")
    L.append("which it does not do.")
    L.append("")
    L.append("## Two quantities that must not be conflated")
    L.append("")
    L.append("| | What it is | What it feeds |")
    L.append("| --- | --- | --- |")
    L.append("| `complexity` | UIOWA-084's 1–5 band: how hard, relative to other items | **ranking** |")
    L.append("| effort range | low/high days | **scheduling** |")
    L.append("")
    L.append("A high-complexity item is not automatically a long one, and a cheap item is")
    L.append("not automatically a quick win. Substituting one for the other is the most")
    L.append("common way a prioritized list turns into an undeliverable plan.")
    L.append("")
    L.append("## The horizon rules")
    L.append("")
    L.append("| Rule | Statement |")
    L.append("| --- | --- |")
    for rid in sorted(RULES):
        L.append("| **%s** | %s |" % (rid, RULES[rid]))
    L.append("")
    L.append("Parameters, stated rather than buried: %s."
             % ", ".join("`%s = %s`" % (k, v) for k, v in sorted(d["meta"]["parameters"].items())))
    L.append("Change them in `backlog.json` and re-run.")
    L.append("")
    L.append("## The worked backlog")
    L.append("")
    L.append("| ID | Effort (d) | Complexity | Prereqs | Declared | Proposed | Agrees |")
    L.append("| --- | --- | ---: | --- | --- | --- | --- |")
    for r in d["recommendations"]:
        effort = ("%s–%s" % (r["effort_days_low"], r["effort_days_high"])
                  if (r["effort_days_low"], r["effort_days_high"]) != (UNKNOWN, UNKNOWN) else UNKNOWN)
        L.append("| `%s` | %s | %s | %s | %s | %s | %s |"
                 % (r["recommendation_id"], effort, r["complexity"],
                    ", ".join(r["prerequisites"]) or "—", r["declared_horizon"],
                    r["proposed_horizon"], "yes" if r["agrees"] else "**no**"))
    L.append("")
    L.append("### Organized by declared horizon")
    L.append("")
    for h in list(HORIZONS) + [NEEDS_ESTIMATE, UNASSIGNED, INVALID_HORIZON]:
        ids = d["by_horizon"][h]
        L.append("- **%s** — %s" % (h, ", ".join("`%s`" % i for i in ids) if ids else "none"))
    L.append("")
    L.append("`NEEDS_ESTIMATE` is not a horizon. It is where an item sits when nobody has")
    L.append("sized it, and it is reported separately so it cannot be mistaken for work")
    L.append("scheduled late. A partial range retains its supplied bound but still needs an estimate.")
    L.append("`UNASSIGNED` means sized work with no declared horizon; `INVALID_HORIZON`")
    L.append("means the declaration is outside the vocabulary. Neither means an unknown estimate.")
    L.append("Proposals inspect declared prerequisite horizons only, not other proposals.")
    L.append("They are per-item suggestions, not a jointly feasible transitive schedule.")
    L.append("")
    quick = backlog.quick_wins()
    prereq = backlog.prerequisite_work()
    L.append("### The three classes the order asks for")
    L.append("")
    L.append("- **Quick wins** (%d): %s" % (len(quick), ", ".join("`%s`" % r["recommendation_id"]
                                                                  for r in quick) or "none"))
    L.append("- **Prerequisite work** (%d, items other recommendations depend on): %s"
             % (len(prereq), ", ".join("`%s`" % r["recommendation_id"] for r in prereq) or "none"))
    high = [r for r in d["recommendations"]
            if r["effort_days_low"] != UNKNOWN and r["effort_days_high"] != UNKNOWN
            and r["effort_days_low"] >= d["meta"]["parameters"]["high_effort_min_effort_days"]]
    L.append("- **High effort** (%d): %s" % (len(high), ", ".join("`%s`" % r["recommendation_id"]
                                                                  for r in high) or "none"))
    L.append("")
    if d["disagreements"]:
        L.append("## Where the proposal and the declaration differ")
        L.append("")
        L.append("Rule H7: the declared horizon is never overwritten. Both readings are shown")
        L.append("and a person settles it.")
        L.append("")
        for r in backlog.disagreements():
            L.append("**`%s`** — declared `%s`, proposed `%s`"
                     % (r["recommendation_id"], r["declared_horizon"], r["proposed_horizon"]))
            L.append("")
            for reason in r["proposal_reasons"]:
                L.append("- %s" % reason)
            if r["declared_horizon_reason"]:
                L.append("- Declared reason: %s" % r["declared_horizon_reason"])
            L.append("")
    if d["violations"]:
        L.append("## Rule violations")
        L.append("")
        L.append("| Recommendation | Code | Detail |")
        L.append("| --- | --- | --- |")
        for v in d["violations"]:
            L.append("| `%s` | `%s` | %s |" % (v["recommendation_id"], v["code"], v["detail"]))
        L.append("")
    L.append("## Uncertainty")
    L.append("")
    L.append("Effort is a **range**, and an item nobody has sized carries no range at all")
    L.append("rather than a placeholder. A point estimate is permitted but flagged, because")
    L.append("a single number states a certainty the estimator may not have. An effect that")
    L.append("was not assessed is `UNKNOWN` and does not contribute — it is not a zero.")
    L.append("")
    L.append("## Still UNKNOWN")
    L.append("")
    for item in (
        "the real recommendation set — this backlog is fiction",
        "whether a horizon means start or completion; the rules above treat it as the "
        "window in which the work is done, and that has not been confirmed",
        "the University's actual capacity per horizon, so nothing here is checked against "
        "available effort",
        "which prerequisites the assessment team treats as binding rather than preferred",
        "whether the quick-win and high-effort thresholds are the right ones; they are "
        "parameters of this method, not findings",
    ):
        L.append("- %s" % item)
    L.append("")
    return "\n".join(L)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise MethodError("duplicate JSON key: %r" % key)
        result[key] = value
    return result


def _invalid_constant(value):
    raise MethodError("non-finite JSON number: %s" % value)


def load(name):
    with open(os.path.join(HERE, name), "r", encoding="utf-8") as fh:
        return json.load(fh, object_pairs_hook=_unique_object,
                         parse_constant=_invalid_constant)


def _write_report(path, text, input_path):
    """Replace a report atomically, never a source alias; retain prior output on failure."""
    path, input_path = os.path.abspath(path), os.path.abspath(input_path)
    if path == input_path or (os.path.exists(path) and os.path.samefile(path, input_path)):
        raise MethodError("report path aliases the input backlog")
    parent = os.path.dirname(path)
    os.makedirs(parent, exist_ok=True)
    descriptor, staging = tempfile.mkstemp(prefix=".uiowa029-", dir=parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(staging, path)
    finally:
        if os.path.exists(staging):
            os.unlink(staging)


def main(argv=None):
    p = argparse.ArgumentParser(description="Prioritization method and horizon organization.")
    p.add_argument("--render", action="store_true")
    p.add_argument("--check", action="store_true")
    p.add_argument("--print", dest="do_print", action="store_true")
    p.add_argument("--outdir")
    p.add_argument("--input", help="edited synthetic backlog; relative to the working directory")
    p.add_argument("--json", action="store_true", help="print machine-readable results to stdout")
    args = p.parse_args(argv)
    if args.json and (args.render or args.do_print or args.outdir):
        p.error("--json cannot be combined with --render, --print or --outdir")

    try:
        input_path = os.path.abspath(args.input) if args.input else os.path.join(HERE, "backlog.json")
        backlog = Backlog(load(input_path))
    except (MethodError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        sys.stderr.write("error: %s\n" % exc)
        return 2

    if args.check and not (args.render or args.do_print or args.outdir or args.json):
        for v in backlog.violations:
            sys.stderr.write("VIOLATION %s %s: %s\n"
                             % (v["recommendation_id"], v["code"], v["detail"]))
        sys.stderr.write("items=%d violations=%d disagreements=%d\n"
                         % (len(backlog.results), len(backlog.violations),
                            len(backlog.disagreements())))
        return 1 if backlog.violations else 0

    try:
        text = render(backlog)
        payload = json.dumps(backlog.as_dict(), indent=2, sort_keys=True, allow_nan=False)
        if args.render:
            # With an edited input, keep the committed named example untouched.
            target = (os.path.join(args.outdir, "29-prioritization-method.md")
                      if args.input and args.outdir else os.path.join(HERE, "29-prioritization-method.md"))
            if args.input and not args.outdir:
                raise MethodError("--render with --input requires --outdir; use --print for stdout")
            _write_report(target, text, input_path)
            sys.stdout.write("wrote 29-prioritization-method.md\n")
        if args.outdir:
            _write_report(os.path.join(args.outdir, "horizons.json"), payload, input_path)
            sys.stdout.write("wrote horizons.json to %s\n" % args.outdir)
        if args.json:
            sys.stdout.write(payload + "\n")
        elif args.do_print or not (args.render or args.outdir):
            sys.stdout.write(text)
    except (MethodError, OSError, UnicodeError, ValueError) as exc:
        sys.stderr.write("error: %s\n" % exc)
        return 2

    sys.stderr.write("items=%d quick_wins=%d prerequisite_work=%d violations=%d disagreements=%d\n"
                     % (len(backlog.results), len(backlog.quick_wins()),
                        len(backlog.prerequisite_work()), len(backlog.violations),
                        len(backlog.disagreements())))
    return 1 if backlog.violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
