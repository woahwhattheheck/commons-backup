#!/usr/bin/env python3
"""host/pfc_ask.py — WHICH DOC GOVERNS WHAT I AM ABOUT TO DO. Run this BEFORE acting.

PFC_FINDINGS S0 already mandates this move for CIRCUITS:
    "BEFORE BUILDING ANYTHING: grep -rln 'def <thing>' host/*.py | python host/pfc_index.py <thing>.
     126 circuits and FOUR forward-pass paths already exist."
That rule exists because sessions kept rebuilding circuits that already existed. The identical
failure happens one layer up with ANSWERS: the governing passage is written down, is obvious in
hindsight, and is invisible in foresight across ~29,000 lines. pfc_index.py closes it for circuits.
This closes it for answers.

It is not grep. It RANKS BY AUTHORITY, because on this corpus the authoritative line and the merely
matching line look identical to a keyword search:
  - owner-verbatim quotes, HARD RULE, RULE ZERO, banners (a star), stop-signs               weight 10
  - imperatives (NEVER / ALWAYS / MUST / do not / forbidden / purged / stale)               weight  6
  - numbered spec sections (S3.4, S40E, S56D...) and measured verdicts                      weight  4
  - plain prose mentioning the term                                                         weight  1
Later corrections outrank earlier ones (FINALREADME: "prefer this one - the corpus was iterated
over months and the early parts lag"), so PURGED/STALE markers demote a passage to the floor.

  python host/pfc_ask.py "read the answer"       # governing passages, ranked, with citations
  python host/pfc_ask.py "clock" --all           # include the quarantined corpus
  python host/pfc_ask.py --topics                # the recurring questions this corpus answers
"""
import io, os, re, sys
sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# THE OWNER'S DOCS ONLY. host/*.py is excluded on purpose: my own files restate his rules, carry the
# same authority markers, and would rank ABOVE the source. A lookup that returns my paraphrase instead
# of his passage entrenches the failure it exists to fix.
DOCS = [os.path.join(ROOT, "docs"), ROOT]

AUTHORITY = [
    (10, re.compile(r"HARD RULE|RULE ZERO|owner[,:]|\(owner|verbatim|★|⛔|CANONICAL|"
                    r"AUTHORITATIVE|READ THIS FIRST|non-negotiable", re.I)),
    (6,  re.compile(r"\bNEVER\b|\bALWAYS\b|\bMUST\b|\bdo not\b|\bdon't\b|forbidden|banned|"
                    r"\bonly\b|\bno\b\s+\w+ing", re.I)),
    (4,  re.compile(r"§\s?\d|MEASURED|byte-exact|proven|demonstrated|\bfixed\b", re.I)),
]
DEMOTE = re.compile(r"PURGED|STALE|superseded|retracted|quarantined", re.I)

TOPICS = {
    "read the answer":      "how the answer register is read, and with what",
    "clock":                "what drives the machine; self-clock vs host-clocking",
    "width":                "does going wide cost latency (it does not)",
    "fold":                 "the winner-only fold, coverage, lane count",
    "fabrication":          "when fabrication may happen, and when it may not",
    "depth":                "DEPTH as the machine's only latency; attribution before optimising",
    "host":                 "what the host is allowed to do at runtime",
    "instrument":           "which observation tools exist and may be used",
    "guarantee":            "proving coverage before firing",
    "crutch":               "which shapes are the crutch and why",
    "units":                "DEPTH / gates / muhl / host wall-clock, never mixed",
    "wire-buffer":          "the per-lane gate buffer and why it collapses the count",
}


def paragraphs(path):
    try: txt = io.open(path, encoding="utf-8", errors="replace").read()
    except Exception: return
    line_no, buf, start = 1, [], 1
    for raw in txt.splitlines():
        if raw.strip():
            if not buf: start = line_no
            buf.append(raw)
        else:
            if buf: yield start, "\n".join(buf)
            buf = []
        line_no += 1
    if buf: yield start, "\n".join(buf)


def score(para, terms):
    low = para.lower()
    present = [t for t in terms if t in low]
    if len(present) < max(1, len(terms) - 1):     # require nearly ALL terms, not any
        return 0
    # coverage, not raw count: a long list mentioning a word 20x is not more governing than a
    # two-line rule that states it once.
    s = 4 * len(present)
    for w, rx in AUTHORITY:
        if rx.search(para): s += w
    if DEMOTE.search(para): s = 1          # a corrected passage must never outrank its correction
    # normalise by length: the tight statement outranks the essay that happens to contain the words
    n = len(para)
    if n > 2500: s = int(s * 0.25)
    elif n > 1200: s = int(s * 0.5)
    elif n < 400: s += 3
    return s


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if "--topics" in sys.argv or not args:
        print("pfc_ask — run BEFORE acting. The recurring questions this corpus already answers:\n")
        for k, v in TOPICS.items():
            print(f"  {k:20s} {v}")
        print('\n  python host/pfc_ask.py "read the answer"')
        return 0
    q = " ".join(args).lower()
    terms = [t for t in re.split(r"\W+", q) if len(t) > 2]
    if not terms:
        print("give me a topic."); return 1

    found = []
    for d in DOCS:
        if not os.path.isdir(d): continue
        for fn in sorted(os.listdir(d)):
            if not fn.endswith(".md"): continue
            p = os.path.join(d, fn)
            if "archive_misdescribed" in p and "--all" not in sys.argv: continue
            for ln, para in paragraphs(p):
                sc = score(para, terms)
                if sc > 0: found.append((sc, os.path.relpath(p, ROOT), ln, para))
    found.sort(key=lambda r: -r[0])
    if not found:
        print(f"nothing governs '{q}'. That means it is genuinely NOT YET WRITTEN — "
              f"ask, do not presume (FINALREADME S8).")
        return 1

    print(f"GOVERNING PASSAGES for '{q}' — ranked by authority, {len(found)} match(es)\n")
    for sc, path, ln, para in found[:6]:
        body = "\n".join("     " + l for l in para.splitlines()[:9])
        print(f"  [{sc:3d}] {path}:{ln}")
        print(body)
        if len(para.splitlines()) > 9: print("     ...")
        print()
    print("  Quote the passage in the action it justifies. If the top hit is PURGED/STALE it was")
    print("  demoted to score 1 — read the correction that replaced it, never the original.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
