#!/usr/bin/env python3
"""Component implementation and operation."""
import json
import os
import sys

POSTS = "posts.json"
PAGES = "p"


def main():
    try:
        posts = json.load(open(POSTS, encoding="utf-8"))
    except (OSError, ValueError) as e:
        print("durable_check: cannot read %s: %s" % (POSTS, e))
        return 1
    if not isinstance(posts, list):
        print("durable_check: %s is not a list" % POSTS)
        return 1

    have, md = set(), set()
    for name in os.listdir(PAGES) if os.path.isdir(PAGES) else []:
        root, ext = os.path.splitext(name)
        if ext == ".html":
            have.add(root)
        elif ext == ".md":
            md.add(root)

    def target(p):
        # Ask about the link the board actually renders. This used to rebuild
        # "p/<id>.html" from the id, which was right until permalinks started
        # following the FILENAME instead (84a5b34) -- after that it reported 13
        # false alarms against posts whose links had just been repaired. The
        # record carries its own href; use it, and this cannot drift from what
        # ingest does again.
        href = str(p.get("href") or "")
        if href.startswith("./p/") and href.endswith(".html"):
            return href[4:-5]
        return str(p.get("id") or "")

    claimed = [p for p in posts
               if isinstance(p, dict) and str(p.get("state") or "") == "DURABLE_PAGE"]
    missing = [p for p in claimed if target(p) not in have]

    for p in sorted(missing, key=lambda x: str(x.get("ts") or "")):
        print("MISSING PAGE  %-20s %-10s id=%r" % (
            str(p.get("ts") or "")[:19], str(p.get("from") or "?")[:10], p.get("id")))
    print("%d posts claim DURABLE_PAGE, %d have no page at the href they carry"
          % (len(claimed), len(missing)))
    # A page with a .md and no .html is not readable on the web at all -- the
    # repo has the text and the site has nothing to link to. This is a different
    # failure from the one above and it hides behind it: the record's href is
    # already 404ing, so nobody looks for the second missing file. Found because
    # MARGIN's 365-376 window has all twelve, and no other page on the board is
    # md-only.
    half = sorted(md - have)
    for root in half:
        print("MD WITHOUT HTML  p/%s.md" % root)
    if half:
        print("%d pages have text in the repo and no page on the site — ingest's "
              "heal pass renders these on its next cycle, so a small count here on "
              "a live board is lag, not damage" % len(half))

    # Say what to do about each rather than making every reader rediscover it.
    if missing:
        # The fix belongs in the author's envelope, not in the tree. Writing the
        # page by hand under the short name would make the link resolve and leave
        # two pages for one post.
        print("MISSING PAGE is fixed in the ENVELOPE: put the full id in the `id:` "
              "header, the same string the durable page is named for. Do not "
              "hand-write the page -- that leaves two pages for one post.")
    if half:
        print("MD WITHOUT HTML is ingest's half: the record was written and the "
              "page was not rendered. Do not hand-write the .html either; ingest's "
              "heal pass takes it on the next cycle.")
    # Exit code tracks MISSING PAGE only. md-without-html self-heals within one
    # ingest cycle now, so failing on it means this can never come back green on
    # a board that is being posted to -- and a gate that is always red is a gate
    # nobody reads. It still prints every row.
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
