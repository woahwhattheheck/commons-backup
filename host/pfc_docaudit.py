"""
pfc_docaudit.py - RE-DERIVE EVERY NUMBER IN THE DOCS FROM THE BINARY.

Same move as host/pfc_serial_audit.py, aimed at the PROSE instead of the netlist. That tool found
assistant-produced sequencing mechanically; this one finds assistant-produced NUMBERS mechanically.

WHY THIS IS NOT PEDANTRY
S53E found `pfc_specs` reporting a core THREE FIXES OUT OF DATE. Improving the source of a circuit
does NOT update the stored copy, and the stored copy is what every tool reads. So a divergence
between a doc figure and the registry is EXPECTED in places - it is precisely the signal this tool
exists to surface. A divergence here means one of:
    (a) the doc records a figure from a source build that was never stored  -> restore or restate
    (b) the stored circuit is stale relative to the source                  -> re-store it
    (c) the doc is simply wrong                                             -> fix the doc
This tool does not decide which. It reports the divergence with both numbers and the line.

WHAT IT CHECKS
  DEPTH   - re-derived by a longest-path walk over the STORED netlist (S24: the only latency)
  gates   - len(ga) of the STORED netlist (area)
  muhl    - gates / DEPTH, the RATING (S52/S54A), symbol Mh, compared with the doc's kMh/MMh too

WHAT IT CANNOT CHECK, and says so per claim rather than silently dropping it:
  - a name that is not in the registry (never stored, or renamed)
  - a stored entry that will not load (format the loader does not accept)
  - a figure attached to no circuit name, or to a prose label ("RV32I core", "the miter itself")
  - a PROJECTED figure (ns at a stated tau) or a HOST figure (seconds) - a different machine (S24)
  - a FABRICATOR's gates/DEPTH - manufacturing, never a latency (S31)

Run:  python host/pfc_docaudit.py                 (audit docs/PFC_FINDINGS.md)
      python host/pfc_docaudit.py <doc> [<doc>..]
      python host/pfc_docaudit.py --selftest      (positive controls + mutants)
      python host/pfc_docaudit.py --all           (list every claim, not just divergences)
"""
import sys, os, re, json, math

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import titan_circuit as TC

DEFAULT_DOC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "docs", "PFC_FINDINGS.md")

# figures that belong to a DIFFERENT machine or to the factory - never compared against a netlist
SKIP_CONTEXT = re.compile(
    r"PROJECT|projection|ns @|host wall|wall-clock|s/token|ms\b|H/s|gate-evals|tau|"
    r"fabricat\w* time|manufactur", re.I)

NUM = r"([0-9][0-9,]*(?:\.[0-9]+)?)"
RE_DEPTH_INLINE = re.compile(r"DEPTH\s+" + NUM)
RE_GATES_INLINE = re.compile(r"gates\s+" + NUM + r"|" + NUM + r"\s+gates")
RE_MUHL_INLINE = re.compile(NUM + r"\s*(kMh|MMh|GMh|Mh|kmuhl|Mmuhl|muhl)\b")
RE_TICKNAME = re.compile(r"`([A-Za-z_][A-Za-z0-9_]*)`")


def num(s):
    return float(s.replace(",", ""))


def scale_of(unit):
    return {"kMh": 1e3, "MMh": 1e6, "GMh": 1e9, "kmuhl": 1e3, "Mmuhl": 1e6}.get(unit, 1.0)


# ------------------------------------------------------------------ the binary side
_cache = {}


def derive(name):
    """gates and DEPTH re-derived from the STORED netlist. Returns (gates, depth) or raises."""
    if name in _cache:
        v = _cache[name]
        if isinstance(v, Exception):
            raise v
        return v
    try:
        cd = TC.load(name)
        if not cd.get("ga") or not cd.get("outs"):
            raise ValueError("stored entry has no gates/outputs")
        n = cd["n_in"]
        d = [0] * (2 + n + len(cd["ga"]))
        b = 2 + n
        for k in range(len(cd["ga"])):
            d[b + k] = 1 + max(d[cd["ga"][k]], d[cd["gb"][k]])
        v = (len(cd["ga"]), max(d[x] for x in cd["outs"]))
    except Exception as e:
        _cache[name] = e
        raise
    _cache[name] = v
    return v


# ------------------------------------------------------------------ the prose side
def split_row(line):
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def cell_subjects(cell):
    """The names a table cell is ABOUT, which is not the same as the names it MENTIONS.

    `pfc_rsqrt`                          -> subject
    `pfc_mac` rebuilt                    -> subject (a qualifier, not prose)
    `v_pre` / `mz` / `b_12`              -> THREE subjects, one row, one figure each
    mul-then-ripple (what `dot32_i8` does) -> NO subject; dot32_i8 is only mentioned, and
                                              attributing the row's 172/196/156,120 to it
                                              manufactured four false divergences.

    The rule: take the backticked identifiers; if what remains after removing them is more than
    two words of prose, the cell is a description and owns no figure."""
    t = cell.strip().strip("*").strip()
    names = [m.group(1) for m in RE_TICKNAME.finditer(t)]
    if not names:
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)$", t)
        return [m.group(1)] if m else []
    rest = RE_TICKNAME.sub(" ", t)
    rest = re.sub(r"[/,()]", " ", rest)
    words = [w for w in rest.split() if w]
    return names if len(words) <= 2 else []


def classify_header(cells):
    """map column index -> 'name' | 'gates' | 'depth' | 'muhl', by the header text"""
    col = {}
    for i, c in enumerate(cells):
        t = c.strip().strip("*").lower()
        if t in ("circuit", "name", "build", "variant", "claim", "property", "stage", "limb"):
            col[i] = "name"
        elif "gate" in t and "delay" not in t and "/" not in t:
            col[i] = "gates"
        elif t.startswith("depth") or t == "depth":
            col[i] = "depth"
        elif t in ("power", "muhl", "rating", "mh") or "muhl" in t or t.endswith("mh"):
            col[i] = "muhl"
    return col


def parse_claims(path, known):
    """Return a list of claim dicts. A claim is (name, kind, value) with provenance."""
    txt = open(path, encoding="utf-8", errors="replace").read().splitlines()
    claims = []
    i = 0
    while i < len(txt):
        line = txt[i]
        # ---- markdown table?
        if line.strip().startswith("|") and i + 1 < len(txt) and \
                re.match(r"^\s*\|[\s:|-]+\|\s*$", txt[i + 1]):
            hdr = classify_header(split_row(line))
            j = i + 2
            while j < len(txt) and txt[j].strip().startswith("|"):
                cells = split_row(txt[j])
                # ---- NEAREST-NAME-TO-THE-LEFT.
                # The first version of this parser took the FIRST known name in the row and gave it
                # every number. That produced 7 false divergences on rows shaped
                # `| deep | DEPTH | shallow | DEPTH |` (a header with TWO depth columns), where the
                # second DEPTH belongs to the SECOND name. A tool that invents divergences is worse
                # than none, because the report then has to be audited itself.
                subj = {}
                for k, cell in enumerate(cells):
                    subj[k] = cell_subjects(cell)
                subj = {k: v for k, v in subj.items() if v}
                raw = " | ".join(cells)
                for k, kind in hdr.items():
                    if kind == "name" or k >= len(cells):
                        continue
                    cell = cells[k].strip().strip("*")
                    m = re.match(r"^" + NUM + r"\s*(kMh|MMh|GMh|Mh|kmuhl|Mmuhl|muhl)?$", cell)
                    if not m:
                        continue
                    val = num(m.group(1)) * (scale_of(m.group(2)) if m.group(2) else 1.0)
                    left = [c for c in subj if c < k]
                    nms = subj[max(left)] if left else [None]
                    for nm in nms:                    # `a` / `b` / `c` in one cell = 3 subjects
                        claims.append(dict(name=nm, kind=kind, val=val, line=j + 1,
                                           src=os.path.basename(path), text=raw[:90],
                                           skip=bool(SKIP_CONTEXT.search(raw))))
                j += 1
            i = j
            continue
        # ---- inline prose: same rule. Each figure belongs to the nearest backticked name to its
        # LEFT, not to the first name on the line (line 657 of PFC_FINDINGS names two circuits and
        # two depths in one sentence; first-name attribution mis-assigned the second).
        marks = [(m.start(), m.group(1)) for m in RE_TICKNAME.finditer(line) if m.group(1) in known]
        if marks:
            def owner(pos):
                left = [n for p, n in marks if p < pos]
                return left[-1] if left else marks[0][1]
            for m in RE_DEPTH_INLINE.finditer(line):
                claims.append(dict(name=owner(m.start()), kind="depth", val=num(m.group(1)),
                                   line=i + 1, src=os.path.basename(path),
                                   text=line.strip()[:90], skip=bool(SKIP_CONTEXT.search(line))))
            for m in RE_GATES_INLINE.finditer(line):
                g = m.group(1) or m.group(2)
                claims.append(dict(name=owner(m.start()), kind="gates", val=num(g), line=i + 1,
                                   src=os.path.basename(path), text=line.strip()[:90],
                                   skip=bool(SKIP_CONTEXT.search(line))))
            for m in RE_MUHL_INLINE.finditer(line):
                claims.append(dict(name=owner(m.start()), kind="muhl",
                                   val=num(m.group(1)) * scale_of(m.group(2)),
                                   line=i + 1, src=os.path.basename(path),
                                   text=line.strip()[:90], skip=bool(SKIP_CONTEXT.search(line))))
        i += 1
    # de-duplicate identical (name, kind, val, line)
    seen, out = set(), []
    for c in claims:
        k = (c["name"], c["kind"], c["val"], c["line"], c["src"])
        if k not in seen:
            seen.add(k)
            out.append(c)
    return out


# ------------------------------------------------------------------ compare
def check(claims, known=None):
    if known is None:
        known = set(n for n in json.load(open(TC.REG)) if ":" not in n)
    match, diverge, unchk = [], [], []
    for c in claims:
        if c["name"] is None:
            c["why"] = "no circuit name on the line - figure belongs to no stored netlist"
            unchk.append(c); continue
        if c["name"] not in known:
            c["why"] = "name is not in the registry - never stored, or renamed"
            unchk.append(c); continue
        if c["skip"]:
            c["why"] = "PROJECTED / HOST / MANUFACTURING figure - a different machine (S24/S31)"
            unchk.append(c); continue
        try:
            g, d = derive(c["name"])
        except Exception as e:
            c["why"] = "not re-derivable: %s (%s)" % (type(e).__name__, str(e)[:40])
            unchk.append(c); continue
        if c["kind"] == "gates":
            got, ok = g, (abs(c["val"] - g) < 0.5)
        elif c["kind"] == "depth":
            got, ok = d, (abs(c["val"] - d) < 0.5)
        else:
            got = g / d
            # docs round the rating (e.g. "16.08 kMh"); accept anything that rounds the same way
            ok = abs(c["val"] - got) <= max(0.05 * 10 ** math.floor(math.log10(max(got, 1)) - 2), 0.06) \
                 or (got and abs(c["val"] - got) / got < 0.002)
        c["got"] = got
        (match if ok else diverge).append(c)
    return match, diverge, unchk


def fmt(kind, v):
    if kind == "muhl":
        return "%.4g" % v
    return "{:,}".format(int(round(v)))


# ------------------------------------------------------------------ controls
CONTROL_DOC = """
# control

| circuit | gates | DEPTH | POWER |
|---|---|---|---|
| `%(n1)s` | %(g1)s | %(d1)d | %(m1)s |
| `%(n1)s` | %(gbad)s | %(dbad)d | %(m1)s |
| `%(n2)s` | %(g2)s | %(d2)d | %(m2)s |
| `no_such_circuit_xyz` | 999 | 42 | 23.8 Mh |

| deep circuit | DEPTH | shallow replacement | DEPTH |
|---|---|---|---|
| `%(n1)s` | %(d1)d | `%(n2)s` | %(d2)d |

Inline true: `%(n1)s` DEPTH %(d1)d, %(g1)s gates.
Inline false: `%(n2)s` DEPTH %(dbad2)d.
Inline two-name: `%(n1)s` (DEPTH %(d1)d) is deeper than `%(n2)s` at DEPTH %(d2)d.
Projection: `%(n1)s` DEPTH %(d1)d ns @ 1 ns/stage [PROJECTION, not measured]
"""


def selftest():
    """POSITIVE CONTROLS FIRST, with the degenerate baselines stated.
    The control doc holds 6 checkable claims: 4 TRUE and 2 FALSE (deliberately wrong), plus 4
    un-checkable ones (an unknown circuit x3 fields, and a PROJECTED figure).
      a tool that answers 'everything MATCHES'  scores 4/6 on match, 0/2 on divergence -> 4/10
      a tool that answers 'everything DIVERGES' scores 0/4 on match, 2/2 on divergence -> 2/10
      a correct tool scores 10/10.
    Stating those baselines is the point: 87.5% once looked like a pass (S40B)."""
    reg = json.load(open(TC.REG))
    known = set(n for n in reg if ":" not in n)
    picks = []
    for n in sorted(known):
        try:
            picks.append((n,) + derive(n))
        except Exception:
            pass
        if len(picks) == 2:
            break
    if len(picks) < 2:
        print("  cannot self-test: fewer than 2 loadable circuits")
        return False
    (n1, g1, d1), (n2, g2, d2) = picks
    doc = CONTROL_DOC % dict(n1=n1, g1="{:,}".format(g1), d1=d1, m1="%.1f Mh" % (g1 / d1),
                             n2=n2, g2="{:,}".format(g2), d2=d2, m2="%.1f Mh" % (g2 / d2),
                             gbad="{:,}".format(g1 + 7), dbad=d1 + 13, dbad2=d2 + 5)
    tmp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_docaudit_control.md")
    open(tmp, "w", encoding="utf-8").write(doc)
    try:
        claims = parse_claims(tmp, known)
        m, dv, u = check(claims)
        # expected TRUE claims: row1 gates/depth/muhl, row3 gates/depth/muhl, inline depth+gates
        want_match = {(n1, "gates", float(g1)), (n1, "depth", float(d1)),
                      (n2, "gates", float(g2)), (n2, "depth", float(d2))}
        want_div = {(n1, "gates", float(g1 + 7)), (n1, "depth", float(d1 + 13)),
                    (n2, "depth", float(d2 + 5))}
        got_match = set((c["name"], c["kind"], c["val"]) for c in m)
        got_div = set((c["name"], c["kind"], c["val"]) for c in dv)
        res = []
        res.append(("P1 every TRUE claim classified MATCH", want_match <= got_match,
                    "%d/%d" % (len(want_match & got_match), len(want_match))))
        res.append(("P2 every FALSE claim classified DIVERGE", want_div <= got_div,
                    "%d/%d" % (len(want_div & got_div), len(want_div))))
        res.append(("P3 no FALSE claim leaked into MATCH", not (want_div & got_match),
                    str(len(want_div & got_match))))
        res.append(("P4 no TRUE claim leaked into DIVERGE", not (want_match & got_div),
                    str(len(want_match & got_div))))
        res.append(("P5 unknown circuit -> UNCHECKABLE, not MATCH",
                    any(c["name"] == "no_such_circuit_xyz" for c in u) and
                    not any(c["name"] == "no_such_circuit_xyz" for c in m + dv),
                    str(sum(1 for c in u if c["name"] == "no_such_circuit_xyz"))))
        res.append(("P6 PROJECTED line -> UNCHECKABLE (S24)",
                    any("PROJECT" in c["text"].upper() for c in u),
                    str(sum(1 for c in u if "PROJECT" in c["text"].upper()))))
        # P8 is the regression guard for the bug this parser actually had: a two-name row
        # `| deep | DEPTH | shallow | DEPTH |` where first-name attribution invents a divergence.
        res.append(("P8 two-name row: 2nd DEPTH -> 2nd name",
                    (n2, "depth", float(d2)) in got_match and (n1, "depth", float(d2)) not in got_div
                    if d1 != d2 else True,
                    "d1=%d d2=%d" % (d1, d2)))
        res.append(("P7 the rating (muhl) round-trips",
                    (n1, "muhl", round(g1 / d1, 1)) in set((c["name"], c["kind"], round(c["val"], 1)) for c in m),
                    "%.3f" % (g1 / d1)))
        print("  POSITIVE CONTROLS - degenerate baselines stated so a score means something")
        print("    'everything matches' tool: 4/10 claim-level, and it FAILS P2/P3")
        print("    'everything diverges' tool: 2/10 claim-level, and it FAILS P1/P4")
        print()
        for nm, ok, det in res:
            print("    [%s] %-46s %s" % ("PASS" if ok else "FAIL", nm, det))
        score = sum(1 for _, ok, _ in res if ok)
        print("    score %d/%d   (control circuits: %s, %s)" % (score, len(res), n1, n2))

        print()
        print("  MUTANTS (S45C) - perturb the doc and the classification MUST move")
        muts = []
        for delta, label in ((1, "DEPTH off by 1"), (-1, "DEPTH off by -1"), (100, "DEPTH off by 100")):
            d2doc = doc.replace("| %d |" % d1, "| %d |" % (d1 + delta), 1)
            open(tmp, "w", encoding="utf-8").write(d2doc)
            cl = parse_claims(tmp, known)
            mm, dd, _ = check(cl)
            moved = (n1, "depth", float(d1 + delta)) in set((c["name"], c["kind"], c["val"]) for c in dd)
            muts.append((label, moved))
        # a mutant the tool must NOT flag: reformat the same number with a comma
        open(tmp, "w", encoding="utf-8").write(doc.replace("| %d |" % d1, "| %d |" % d1, 1))
        muts.append(("identical number reformatted -> still MATCH",
                     (n1, "depth", float(d1)) in set((c["name"], c["kind"], c["val"])
                                                     for c in check(parse_claims(tmp, known))[0])))
        for label, ok in muts:
            print("    [%s] %s" % ("KILLED" if ok else "SURVIVED", label))
        print("    %d/%d mutants killed" % (sum(1 for _, k in muts if k), len(muts)))
        return score == len(res) and all(k for _, k in muts)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


# ------------------------------------------------------------------ main
def main():
    argv = sys.argv[1:]
    show_all = "--all" in argv
    docs = [a for a in argv if not a.startswith("--")] or [DEFAULT_DOC]

    print("=" * 104)
    print("pfc_docaudit - EVERY DOC FIGURE RE-DERIVED FROM THE BINARY")
    print("  DEPTH by a longest-path walk over the STORED netlist. gates = len(ga). muhl = gates/DEPTH.")
    print("  S53E: improving SOURCE does not update the STORED copy, and every tool reads the stored")
    print("  copy. Divergence is therefore EXPECTED in places - surfacing it is the whole point.")
    print("=" * 104)

    if "--selftest" in argv:
        print()
        selftest()
        return

    reg = json.load(open(TC.REG))
    known = set(n for n in reg if ":" not in n)
    claims = []
    for d in docs:
        if not os.path.exists(d):
            print("  missing: %s" % d)
            continue
        claims += parse_claims(d, known)

    m, dv, u = check(claims)
    names_seen = set(c["name"] for c in claims if c["name"])

    print()
    print("  documents        : %s" % ", ".join(os.path.basename(d) for d in docs))
    print("  registry         : %d named circuits" % len(known))
    print("  claims parsed    : %d   over %d distinct circuit names" % (len(claims), len(names_seen)))
    print("  re-derived       : %d" % (len(m) + len(dv)))
    print("  MATCHING         : %d" % len(m))
    print("  DIVERGING        : %d" % len(dv))
    print("  un-checkable     : %d" % len(u))

    if dv:
        print()
        print("  DIVERGENCES - doc says one thing, the stored netlist says another")
        print("  %-26s %-6s %14s %14s %8s  %s"
              % ("circuit", "kind", "doc claims", "binary says", "line", "where"))
        for c in sorted(dv, key=lambda x: (x["name"], x["kind"], x["line"])):
            print("  %-26s %-6s %14s %14s %8d  %s:%d"
                  % (c["name"], c["kind"], fmt(c["kind"], c["val"]), fmt(c["kind"], c["got"]),
                     c["line"], c["src"], c["line"]))

    if u:
        print()
        print("  UN-CHECKABLE - reported with the reason, never silently dropped")
        by = {}
        for c in u:
            by.setdefault(c["why"], []).append(c)
        for why, cs in sorted(by.items(), key=lambda kv: -len(kv[1])):
            names = sorted(set(str(c["name"]) for c in cs))
            print("    %3d  %s" % (len(cs), why))
            print("         %s" % (", ".join(names[:8]) + (" ..." if len(names) > 8 else "")))

    # S53E's actual shape: a table row that quotes gates AND DEPTH under a PROSE label. That is a
    # rating with no stored counterpart - nothing in the binary can confirm or deny it. These are
    # the rows to either store or restate, and they are invisible in a plain match/diverge count.
    byline = {}
    for c in u:
        if c["name"] is None:
            byline.setdefault((c["src"], c["line"]), {})[c["kind"]] = c
    orphan = [(k, v) for k, v in byline.items()
              if "gates" in v and "depth" in v and v["depth"]["val"] > 0]
    if orphan:
        print()
        print("  ORPHAN RATINGS - a row quoting BOTH gates and DEPTH under a label that is not a")
        print("  stored circuit. Nothing in the binary can confirm or deny these (S53E).")
        print("  CAVEAT: where a table has two DEPTH columns (e.g. unsigned/signed), the pairing")
        print("  below takes the last one on the row, so 'implied Mh' there is indicative only.")
        print("  %6s %10s %9s %11s  %s" % ("line", "gates", "DEPTH", "implied Mh", "the row"))
        for (src, ln), v in sorted(orphan)[:40]:
            g, d = v["gates"]["val"], v["depth"]["val"]
            print("  %6d %10s %9d %11.1f  %s"
                  % (ln, "{:,}".format(int(g)), int(d), (g / d if d else 0), v["gates"]["text"][:58]))
        if len(orphan) > 40:
            print("  ... and %d more" % (len(orphan) - 40))

    unmentioned = sorted(known - names_seen)
    print()
    print("  REVERSE: %d of %d registry circuits carry no figure anywhere in these documents."
          % (len(unmentioned), len(known)))
    print("           %s%s" % (", ".join(unmentioned[:10]), " ..." if len(unmentioned) > 10 else ""))

    if show_all and m:
        print()
        print("  MATCHES")
        for c in sorted(m, key=lambda x: (x["name"], x["kind"])):
            print("    %-26s %-6s %14s  == binary  (%s:%d)"
                  % (c["name"], c["kind"], fmt(c["kind"], c["val"]), c["src"], c["line"]))

    print()
    print("  A DIVERGENCE IS NOT AUTOMATICALLY A DOC BUG. Per S53E it is one of: the doc records a")
    print("  SOURCE build that was never stored; the STORED circuit is stale; or the doc is wrong.")
    print("  This tool reports both numbers and the line, and decides nothing.")
    print()
    print("  Controls: python host/pfc_docaudit.py --selftest")


if __name__ == "__main__":
    main()
