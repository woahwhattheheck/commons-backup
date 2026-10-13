#!/usr/bin/env python3
"""Component implementation and operation."""
import html
import re
import sys

SRC = "DIRECTIVES.md"
OUT = "todo.html"

# "### 7. Profile pictures, player-selected, with a default"
HEAD = re.compile(r"^###\s+(\d+)\.\s+(.+?)\s*$")
# Status may start a line or sit inline after "**Asked:** ... ·". Both shapes are in
# the file today and neither is wrong, so match the marker anywhere.
STATUS = re.compile(r"\*\*Status:\*\*\s*(.+)")
SECTION = re.compile(r"^##\s+(.+?)\s*$")
FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})([^\n]*)$")

# The word that decides the colour. status_word() chooses the earliest bounded token,
# so OPEN wins in "OPEN. Not LANDED" and NOT BUILT is never read as BUILT.
WORDS = ["NOT BUILT", "LANDED", "BUILT", "MEASURED", "PARTIAL", "SPLIT", "HALF",
         "OPEN", "SPEC'D", "CLOSED", "DONE"]


def status_word(status):
    """Return the first status token, not a later negated token.

    A status such as ``OPEN. Not LANDED.`` must stay OPEN. The old fixed-order
    substring scan found LANDED later in that sentence and painted an unfinished
    directive green.
    """
    up = status.upper()
    hits = []
    for word in WORDS:
        match = re.search(r"(?<![A-Z])%s(?![A-Z])" % re.escape(word), up)
        if match:
            hits.append((match.start(), -len(word), word))
    return min(hits)[2] if hits else "OPEN"


def parse(text):
    rows, section, cur = [], "", None
    fence = None
    for line in text.split("\n"):
        # Markdown examples are not directives. A closer uses the same marker,
        # at least the opening length, and no info string (CommonMark 4.5).
        marker = FENCE.match(line)
        if fence is not None:
            if (marker and marker.group(1)[0] == fence[0]
                    and len(marker.group(1)) >= len(fence)
                    and not marker.group(2).strip(" \t\r")):
                fence = None
            continue
        if marker and not (marker.group(1)[0] == "`" and "`" in marker.group(2)):
            fence = marker.group(1)
            if cur is not None and cur["status"]:
                cur["done"] = True
            continue
        m = SECTION.match(line)
        if m:
            section = m.group(1).split("(")[0].strip()
            cur = None
            continue
        m = HEAD.match(line)
        if m:
            cur = {"n": int(m.group(1)), "title": m.group(2),
                   "status": "", "word": "OPEN", "section": section}
            rows.append(cur)
            continue
        if cur is None:
            continue
        if cur.get("done"):
            continue
        if cur["status"]:
            # A status sentence can wrap. Keep pulling continuation lines until a blank
            # line or the next bolded field, or item 11 truncates at "published titles, byte".
            if line.strip() and not line.startswith(("**", ">", "#", "-")):
                cur["status"] += " " + line.strip()
                continue
            cur["done"] = True
            continue
        m = STATUS.search(line)
        if m:
            cur["status"] = m.group(1).strip()
    for r in rows:
        s = re.sub(r"\s+", " ", r["status"]).strip()
        # one sentence of it -- the rest is receipts, which belong in the file
        s = re.split(r"(?<=[a-z0-9`)])\.\s", s)[0].strip().rstrip(".")
        up = s.upper()
        r["word"] = status_word(s)
        # do not print "BUILT BUILT 2026-08-19 -- ..."; the badge already says the word
        if up.startswith(r["word"]):
            s = s[len(r["word"]):].lstrip(" .,:\u2014-")
        r["status"] = s
        r.pop("done", None)
    return rows


def strip_md(s):
    s = re.sub(r"`([^`]*)`", r"\1", s)
    s = re.sub(r"\*\*([^*]*)\*\*", r"\1", s)
    return s


def render(rows):
    out = []
    for r in rows:
        cls = r["word"].lower().replace(" ", "-").replace("'", "")
        out.append(
            '<tr><td>%d</td><td>%s</td><td><b class="s-%s">%s</b> %s</td><td>%s</td></tr>'
            % (r["n"], html.escape(strip_md(r["title"])), cls, html.escape(r["word"]),
               html.escape(strip_md(r["status"])[:200]), html.escape(r["section"])))
    return "\n".join(out)


def project(page, directives):
    rows = parse(directives)
    if not rows:
        raise ValueError("parsed 0 directives -- refusing to write an empty todo")
    if '<tbody id="rows">' not in page:
        raise ValueError('todo.html has no <tbody id="rows"> to fill')
    new, replacements = re.subn(r'(<tbody id="rows">).*?(</tbody>)',
                                lambda m: m.group(1) + "\n" + render(rows) + "\n" + m.group(2),
                                page, count=1, flags=re.S)
    if replacements != 1:
        raise ValueError("todo.html has no closing </tbody> for rows")
    return new, rows


def main():
    page = open(OUT, encoding="utf-8").read()
    try:
        new, rows = project(page, open(SRC, encoding="utf-8").read())
    except ValueError as exc:
        print("todo_gen: %s" % exc, file=sys.stderr)
        return 1
    open(OUT, "w", encoding="utf-8").write(new)
    print("todo_gen: %d directives baked into %s" % (len(rows), OUT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
