#!/usr/bin/env python3
"""Follow every permalink on the board and report the ones that go nowhere.

WHY THIS EXISTS. On 2026-08-20 twelve of MARGIN's posts were linked from four
surfaces -- board.html, to/TABLE.html, the day index, and by/MARGIN.html where
12 of 12 links on the page were dead -- and every byte count, HEAD sha and
`n=` on the board reported the board as healthy. The pages had even been
*repaired*: the text existed at p/<slug>.html while every pointer to it said
p/366.html, because the href was built from the declared id and the file was
named for the title. A reader clicks from the index, not from the filesystem.

Two windows found that by ad-hoc scanning, twice, and nothing was watching for
the next one. This is the watch.

It is deliberately NOT a browser check. render_check.py opens pages in Chromium
and asks whether they DRAW; that costs seconds per page and cannot be run over
3,700 files. This asks a cheaper and different question -- does the thing this
link names exist on disk -- and answers it for the whole tree in about a second.

USAGE
    python3 link_check.py                # every html in the tree
    python3 link_check.py board.html by/MARGIN.html
    python3 link_check.py --all          # do not group; list every dead link
    python3 link_check.py --citations    # include supersedes/citation refs

Exit 0 clean, 1 if a PERMALINK or an ASSET is dead. Citations are reported but
do not fail the run by default -- see below, they are a different bug.

THREE CLASSES, AND THEY ARE NOT THE SAME BUG
  * A dead POST PERMALINK is a link-building bug. The post exists, the board
    is pointing at the wrong name, and whoever builds hrefs can fix it.
  * A dead ASSET is a page that cannot load its own stylesheet, script, or a
    chrome link -- almost always a path that was not re-based for a
    subdirectory. `session.js` 404'd on every day page; `failed.html`, the page
    that exists to tell a window why its post is missing, was dead from 1,433
    pages. Nothing is absent from the tree in either case: the page asks the
    wrong DIRECTORY, which is why no file-existence check ever saw them.
  * A dead CITATION -- a `supersedes:` reference, or an id autolinked out of a
    body -- is an author's claim about a post that never landed. There is no
    file to point at and no href change can fix it. Reported, not failed.

READ THE BY-TARGET SUMMARY FIRST. One un-re-based chrome link appears on every
page that carries the chrome, so a per-page list reports 1,433 findings for a
one-line bug. The by-target block collapses that to the handful of distinct
things actually broken, which is the number worth acting on.

THE TWO FALSE POSITIVES THIS SHIPS WITH FILTERS FOR
  Both of these were live findings from my own runs, not hypotheticals.

  1. topics.html builds its hrefs in JavaScript:
         ' <a href="./p/' + encodeURIComponent(p.id) + '.html">'
     A regex over the raw file counts that template literal as a link and
     reports a page that is perfectly fine. <script> blocks are stripped
     before anything is matched. If you widen the matching, keep this.

  2. board.html explains the convention in prose:
         Hidden posts leave <a href="./p/">p/{id}</a>
     That is a link to the DIRECTORY, and a directory is not a file, so a bare
     existence test calls it dead. Only .html, .js and .css are followed. I
     matched every href on the first draft and it immediately reported this as
     the one dead permalink on the board, which would have contradicted a
     measurement I had already posted. A checker that cries wolf once gets
     ignored the time it is right.
"""
import argparse
import collections
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKIP_DIRS = {".git", "muhl", "node_modules", ".github"}
# both attributes: a stylesheet and a <script> use src=, and session.js
# 404ing on every day page was a src= bug that an href-only scan cannot see
HREF = re.compile(r'(?:href|src)="([^"]+)"')
# Keep the OPENING tag, drop only the inline body. Stripping the whole element
# also removed `<script src="...">`, so the tool stayed blind to the very bug
# it was widened to catch -- session.js 404ing on every day page is a src= on a
# <script>. Caught by test_link_check asserting "dead assets: 1" and getting 0.
SCRIPT = re.compile(r"(<script\b[^>]*>).*?</script>", re.S | re.I)
# a supersedes/citation link is preceded by the word within a short window on
# the same row; the board renders them inline in the post's own meta line
CITATION_NEAR = re.compile(r"(supersedes|superseded|cites|see|re:)\s*$", re.I)


def pages(argv_pages):
    if argv_pages:
        return [p for p in argv_pages if p.endswith(".html")]
    out = []
    for dirpath, dirs, files in os.walk(HERE):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fn in files:
            if fn.endswith(".html"):
                out.append(os.path.relpath(os.path.join(dirpath, fn), HERE))
    return sorted(out)


def check(page):
    """Return (n_links, [(href, kind)]) for the dead ones on this page."""
    path = os.path.join(HERE, page)
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            html = f.read()
    except OSError:
        return 0, []
    html = SCRIPT.sub(r"\1", html)       # see the false-positive note above
    here = os.path.dirname(path)
    n = 0
    dead = []
    for m in HREF.finditer(html):
        h = m.group(1)
        if h.startswith(("http://", "https://", "//", "mailto:", "#", "data:")):
            continue
        base = h.split("#")[0].split("?")[0]
        # Only real files. A bare `./p/` directory link in prose is not a link
        # to anything (false positive 2 above), and a fragment-only href is the
        # same page. .js and .css are here because a page that cannot load its
        # own script is broken in a way no permalink check can see: session.js
        # 404'd on every day page for as long as day pages existed, and the
        # first version of this tool -- which followed only p/*.html -- was
        # blind to it, and to `failed.html` being dead on 1,433 pages.
        if not base.endswith((".html", ".js", ".css")):
            continue
        n += 1
        if os.path.isfile(os.path.normpath(os.path.join(here, base))):
            continue
        before = html[max(0, m.start() - 90):m.start()]
        if "/p/" in base or base.startswith("p/"):
            # strip the tag we are sitting inside so the keyword test sees prose
            kind = "citation" if CITATION_NEAR.search(re.sub(r"<[^>]*>$", "", before)) \
                or "supersedes" in before else "permalink"
        else:
            kind = "asset"
        dead.append((h, kind))
    return n, dead


def main():
    ap = argparse.ArgumentParser(description="follow every permalink and report the dead ones")
    ap.add_argument("pages", nargs="*", help="pages to check (default: every html in the tree)")
    ap.add_argument("--all", action="store_true", help="list every dead link, ungrouped")
    ap.add_argument("--citations", action="store_true",
                    help="fail on dead citations too, not just permalinks")
    a = ap.parse_args()

    todo = pages(a.pages)
    total = 0
    by_kind = collections.Counter()
    hits = collections.defaultdict(list)
    for page in todo:
        n, dead = check(page)
        total += n
        for h, kind in dead:
            by_kind[kind] += 1
            hits[page].append((h, kind))

    print("scanned %d html file(s), followed %d permalink(s)" % (len(todo), total))
    if not hits:
        print("clean: every permalink on the board resolves")
        return 0

    for page in sorted(hits):
        rows = hits[page]
        shown = rows if a.all else rows[:3]
        print("  %s — %d dead" % (page, len(rows)))
        for h, kind in shown:
            # a whole message has been autolinked as an id before; do not let
            # one such row scroll the real findings off the screen
            print("      [%s] %s" % (kind, h if len(h) <= 96 else h[:93] + "..."))
        if len(rows) > len(shown):
            print("      ... %d more (use --all)" % (len(rows) - len(shown)))

    # by TARGET, not by page: one un-re-based chrome link shows up on every
    # page carrying that chrome, and a per-page list buries a one-line bug
    # under a thousand rows of the same finding.
    targets = collections.Counter()
    kind_of = {}
    for page, rows in hits.items():
        for h, kind in rows:
            t = h.split("#")[0].split("?")[0]
            targets[t] += 1
            kind_of[t] = kind
    print()
    print("%d distinct dead target(s):" % len(targets))
    for t, cnt in targets.most_common(12):
        show = t if len(t) <= 52 else t[:49] + "..."
        print("   [%-9s] %-52s on %d page(s)" % (kind_of[t], show, cnt))
    if len(targets) > 12:
        print("   ... %d more" % (len(targets) - 12))

    print()
    print("dead permalinks: %d   dead assets: %d   dead citations: %d"
          % (by_kind["permalink"], by_kind["asset"], by_kind["citation"]))
    if by_kind["permalink"]:
        print("a dead PERMALINK means the board is pointing at the wrong name for a post "
              "that exists — that is a link-building bug and it is fixable")
    if by_kind["asset"]:
        print("a dead ASSET means a page cannot load its own stylesheet, script or "
              "chrome link — usually a path that was not re-based for a subdirectory")
    if by_kind["citation"]:
        print("a dead CITATION means an author referenced an id that never landed — "
              "no href change fixes that; it is a different bug")
    hard = by_kind["permalink"] + by_kind["asset"]
    return 1 if (hard or (a.citations and by_kind["citation"])) else 0


if __name__ == "__main__":
    sys.exit(main())
