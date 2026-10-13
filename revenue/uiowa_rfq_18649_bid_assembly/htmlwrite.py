"""Offline HTML pack with fragment navigation. Stdlib only."""

from __future__ import annotations

from xml.sax.saxutils import escape


def _aid(anchor):
    return escape(anchor or "")


def write_html(path, blocks, title="Document", notice=""):
    """Write a single-file HTML review draft.

    Anchors become id=; dests become href=#id only when that id exists.
    A destination that was never defined is left as visible plain text.
    """
    defined = set()
    for blk in blocks:
        if blk.get("anchor"):
            defined.add(blk["anchor"])

    parts = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        "<title>%s</title>" % escape(title),
        "<style>",
        "body{font-family:Georgia,serif;max-width:52rem;margin:2rem auto;padding:0 1rem;line-height:1.45}",
        "h1,h2,h3{font-family:Helvetica,Arial,sans-serif}",
        "pre,code,.mono{font-family:Consolas,Menlo,monospace;font-size:0.85rem;white-space:pre-wrap}",
        ".notice{border:1px solid #444;padding:0.75rem;margin:1rem 0;background:#f7f7f4}",
        "a{color:#123}",
        "</style>",
        "</head>",
        "<body>",
    ]
    if notice:
        parts.append('<p class="notice">%s</p>' % escape(notice))
    for blk in blocks:
        kind = blk.get("kind", "body")
        if kind == "pagebreak":
            parts.append("<hr>")
            continue
        if kind == "spacer":
            parts.append('<div style="height:%spx"></div>' % int(blk.get("height", 8)))
            continue
        text = escape(blk.get("text", ""))
        dest = blk.get("dest")
        if dest and dest in defined:
            inner = '<a href="#%s">%s</a>' % (_aid(dest), text)
        else:
            inner = text
        tag = {
            "title": "h1",
            "heading": "h2",
            "subheading": "h3",
            "mono": "pre",
            "body": "p",
            "link": "p",
        }.get(kind, "p")
        aid = blk.get("anchor")
        idattr = ' id="%s"' % _aid(aid) if aid else ""
        cls = ' class="mono"' if kind == "mono" else ""
        parts.append("<%s%s%s>%s</%s>" % (tag, idattr, cls, inner, tag))
    parts.append("</body></html>")
    html = "\n".join(parts) + "\n"
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(html)
    return html


def read_html_ids(text):
    import re
    return re.findall(r'\sid="([^"]+)"', text)


def read_html_hrefs(text):
    import re
    return re.findall(r'href="#([^"]+)"', text)
