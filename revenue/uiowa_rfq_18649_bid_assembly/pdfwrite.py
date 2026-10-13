"""Stdlib PDF writer recovered from OP5-TOPAZ bid_pack/pdfwrite.py.

Used here as an input writer for isolated UIOWA-136 bid_assembly.
TOPAZ retains original assembler/writer credit. Navigation (outline +
/Link) is implemented; this is not tagged PDF/UA.
"""

from __future__ import annotations

import re

PAGE_W = 612.0
PAGE_H = 792.0
MARGIN = 72.0

FONT_KEYS = {"H": "/Helvetica", "HB": "/Helvetica-Bold", "C": "/Courier"}
# Advance-width estimate per em. Courier is exact; Helvetica is an estimate that
# errs wide so wrapped text does not spill past the right margin.
FONT_ADV = {"H": 0.55, "HB": 0.58, "C": 0.60}


class PdfError(Exception):
    """Raised when the document cannot be rendered truthfully."""


# --------------------------------------------------------------------------
# encoding
# --------------------------------------------------------------------------

def encode_text(text):
    """Return (cp1252 bytes, [chars that could not be represented]).

    Never silently drops information: every unrepresentable character is
    returned to the caller so it can be raised as an issue.
    """
    lost = []
    out = bytearray()
    for ch in text:
        try:
            out.extend(ch.encode("cp1252"))
        except UnicodeEncodeError:
            lost.append(ch)
            out.extend(b"?")
    return bytes(out), lost


def _pdf_string(raw: bytes) -> bytes:
    esc = raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")
    esc = esc.replace(b"\r", b"\\r").replace(b"\n", b"\\n")
    return b"(" + esc + b")"


def wrap_width(font: str, size: float, avail: float) -> int:
    """How many characters of `font` at `size` fit in `avail` points."""
    per = FONT_ADV[font] * size
    return max(8, int(avail / per))


def text_width(font: str, size: float, text: str) -> float:
    return FONT_ADV[font] * size * len(text)


# --------------------------------------------------------------------------
# pagination
# --------------------------------------------------------------------------

_STYLE = {
    # kind    -> (font, size, leading, space_before)
    "title": ("HB", 20.0, 26.0, 0.0),
    "heading": ("HB", 15.0, 21.0, 10.0),
    "subheading": ("HB", 12.0, 17.0, 6.0),
    "body": ("H", 11.0, 15.0, 0.0),
    "mono": ("C", 8.5, 12.0, 0.0),
    "link": ("H", 11.0, 15.0, 0.0),
}


def paginate(blocks, page_w=PAGE_W, page_h=PAGE_H, margin=MARGIN):
    """Lay `blocks` out into pages.

    Each block is a dict with 'kind' in _STYLE plus 'pagebreak' / 'spacer'.
    Returns a list of pages; each page is a list of placed items with absolute
    coordinates. Headings are kept with the next line so a section title cannot
    be orphaned at the foot of a page.
    """
    avail = page_w - 2 * margin
    lines = []
    for blk in blocks:
        kind = blk.get("kind", "body")
        if kind == "pagebreak":
            lines.append({"break": True})
            continue
        if kind == "spacer":
            lines.append({"spacer": True, "height": float(blk.get("height", 12.0))})
            continue
        if kind not in _STYLE:
            raise PdfError("unknown block kind: %r" % (kind,))
        font, size, lead, space_before = _STYLE[kind]
        if space_before:
            lines.append({"spacer": True, "height": space_before})
        text = blk.get("text", "")
        width = wrap_width(font, size, avail)
        # Monospace blocks are TABLES. Collapsing their runs of spaces (which is
        # what a word wrapper does) silently destroys the column alignment the
        # index depends on -- the bug this branch exists to prevent.
        chunks = _wrap_fixed(text, width) if font == "C" else _wrap(text, width)
        for i, chunk in enumerate(chunks):
            lines.append({
                "font": font, "size": size, "height": lead, "text": chunk,
                # anchor/dest/title only ride on the first wrapped line
                "anchor": blk.get("anchor") if i == 0 else None,
                "dest": blk.get("dest") if i == 0 else None,
                "outline": blk.get("outline") if i == 0 else None,
                "keep": 2 if kind in ("heading", "subheading") and i == len(chunks) - 1 else 0,
            })

    pages = [[]]
    y = page_h - margin
    bottom = margin
    idx = 0
    while idx < len(lines):
        ln = lines[idx]
        if ln.get("break"):
            if pages[-1]:
                pages.append([])
                y = page_h - margin
            idx += 1
            continue
        if ln.get("spacer"):
            # a spacer never opens a page on its own
            if pages[-1]:
                y -= ln["height"]
            idx += 1
            continue
        need = ln["height"] * (1 + ln.get("keep", 0))
        if y - need < bottom and pages[-1]:
            pages.append([])
            y = page_h - margin
        y -= ln["height"]
        item = {
            "x": margin, "y": y, "font": ln["font"], "size": ln["size"],
            "text": ln["text"], "anchor": ln.get("anchor"), "dest": ln.get("dest"),
            "outline": ln.get("outline"),
            "width": text_width(ln["font"], ln["size"], ln["text"]),
        }
        pages[-1].append(item)
        idx += 1
    return pages


def _wrap(text, width):
    if not text:
        return [""]
    words = text.split()
    if not words:
        return [""]
    out, cur = [], ""
    for w in words:
        while len(w) > width:            # a single unbreakable token (a long URL,
            if cur:                      # a long locator) still has to be shown
                out.append(cur)
                cur = ""
            out.append(w[:width])
            w = w[width:]
        cand = w if not cur else cur + " " + w
        if len(cand) <= width:
            cur = cand
        else:
            out.append(cur)
            cur = w
    if cur:
        out.append(cur)
    return out


def _wrap_fixed(text, width):
    """Wrap without touching whitespace, so monospace columns stay columns.

    Breaks at the last space in the back third of the line when there is one,
    otherwise hard-slices. Leading indentation is preserved on continuation
    lines so a wrapped table row still reads as part of its row.
    """
    if len(text) <= width:
        return [text]
    indent = " " * (len(text) - len(text.lstrip(" ")) + 2)
    out, rest, first = [], text, True
    while rest:
        limit = width if first else max(8, width - len(indent))
        if len(rest) <= limit:
            out.append(rest if first else indent + rest)
            break
        cut = rest.rfind(" ", int(limit * 0.6), limit)
        if cut <= 0:
            cut = limit
        out.append(rest[:cut] if first else indent + rest[:cut])
        rest = rest[cut:].lstrip(" ")
        first = False
    return out


def anchor_pages(pages):
    """anchor id -> (0-based page index, y of the anchor)."""
    found = {}
    for pi, page in enumerate(pages):
        for item in page:
            if item.get("anchor") and item["anchor"] not in found:
                found[item["anchor"]] = (pi, item["y"])
    return found


# --------------------------------------------------------------------------
# writing
# --------------------------------------------------------------------------

def write_pdf(pages, title="Document", lang="en-US", author=""):
    """Serialize laid-out `pages` to PDF bytes.

    Returns (bytes, lost_characters). A destination that does not exist in the
    document produces NO annotation -- a link that goes nowhere is worse than no
    link, and the absence is reported by the caller's issue list instead.
    """
    lost_all = []
    anchors = anchor_pages(pages)
    outline_items = []
    for pi, page in enumerate(pages):
        for item in page:
            if item.get("outline"):
                outline_items.append((item["outline"], pi, item["y"]))

    n_catalog, n_pages_obj, n_fh, n_fhb, n_fc, n_outlines, n_info = 1, 2, 3, 4, 5, 6, 7
    next_num = 8
    outline_nums = []
    for _ in outline_items:
        outline_nums.append(next_num)
        next_num += 1

    page_nums, content_nums, annot_nums = [], [], []
    for page in pages:
        page_nums.append(next_num); next_num += 1
        content_nums.append(next_num); next_num += 1
        nums = []
        for item in page:
            if item.get("dest") and item["dest"] in anchors:
                nums.append(next_num); next_num += 1
        annot_nums.append(nums)

    objs = {}

    kids = b" ".join(b"%d 0 R" % n for n in page_nums)
    objs[n_pages_obj] = b"<< /Type /Pages /Kids [ " + kids + b" ] /Count %d >>" % len(pages)
    cat = (b"<< /Type /Catalog /Pages %d 0 R /Lang " % n_pages_obj
           + _pdf_string(encode_text(lang)[0]))
    if outline_items:
        cat += b" /Outlines %d 0 R /PageMode /UseOutlines" % n_outlines
    objs[n_catalog] = cat + b" >>"
    for num, base in ((n_fh, "H"), (n_fhb, "HB"), (n_fc, "C")):
        objs[num] = (b"<< /Type /Font /Subtype /Type1 /BaseFont "
                     + FONT_KEYS[base].encode("ascii")
                     + b" /Encoding /WinAnsiEncoding >>")

    tb, tlost = encode_text(title)
    ab, alost = encode_text(author)
    lost_all.extend(tlost); lost_all.extend(alost)
    objs[n_info] = b"<< /Title " + _pdf_string(tb) + b" /Author " + _pdf_string(ab) + b" >>"

    if outline_items:
        objs[n_outlines] = (b"<< /Type /Outlines /First %d 0 R /Last %d 0 R /Count %d >>"
                            % (outline_nums[0], outline_nums[-1], len(outline_items)))
        for i, (otitle, pi, oy) in enumerate(outline_items):
            ob, olost = encode_text(otitle)
            lost_all.extend(olost)
            body = (b"<< /Title " + _pdf_string(ob)
                    + b" /Parent %d 0 R /Dest [ %d 0 R /XYZ 0 %.1f 0 ]"
                    % (n_outlines, page_nums[pi], oy + 14.0))
            if i > 0:
                body += b" /Prev %d 0 R" % outline_nums[i - 1]
            if i < len(outline_items) - 1:
                body += b" /Next %d 0 R" % outline_nums[i + 1]
            objs[outline_nums[i]] = body + b" >>"
    else:
        objs[n_outlines] = b"<< /Type /Outlines /Count 0 >>"

    for pi, page in enumerate(pages):
        stream = bytearray()
        ai = 0
        for item in page:
            raw, lost = encode_text(item["text"])
            lost_all.extend(lost)
            fk = {"H": b"/FH", "HB": b"/FHB", "C": b"/FC"}[item["font"]]
            stream += (b"BT " + fk + b" %.1f Tf %.1f %.1f Td " % (item["size"], item["x"], item["y"])
                       + _pdf_string(raw) + b" Tj ET\n")
            dest = item.get("dest")
            if dest and dest in anchors:
                dpi, dy = anchors[dest]
                num = annot_nums[pi][ai]; ai += 1
                objs[num] = (b"<< /Type /Annot /Subtype /Link /Border [ 0 0 0 ]"
                             b" /Rect [ %.1f %.1f %.1f %.1f ]"
                             b" /Dest [ %d 0 R /XYZ 0 %.1f 0 ] >>"
                             % (item["x"], item["y"] - 2.0, item["x"] + item["width"],
                                item["y"] + item["size"], page_nums[dpi], dy + 14.0))
        data = bytes(stream)
        objs[content_nums[pi]] = (b"<< /Length %d >>\nstream\n" % len(data)) + data + b"\nendstream"
        pobj = (b"<< /Type /Page /Parent %d 0 R /MediaBox [ 0 0 %.0f %.0f ]"
                b" /Resources << /Font << /FH %d 0 R /FHB %d 0 R /FC %d 0 R >> >>"
                b" /Contents %d 0 R"
                % (n_pages_obj, PAGE_W, PAGE_H, n_fh, n_fhb, n_fc, content_nums[pi]))
        if annot_nums[pi]:
            arr = b" ".join(b"%d 0 R" % n for n in annot_nums[pi])
            pobj += b" /Annots [ " + arr + b" ]"
        objs[page_nums[pi]] = pobj + b" >>"

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = {}
    for num in sorted(objs):
        offsets[num] = len(out)
        out += b"%d 0 obj\n" % num + objs[num] + b"\nendobj\n"
    xref_at = len(out)
    top = max(objs) + 1
    out += b"xref\n0 %d\n" % top
    out += b"0000000000 65535 f \n"
    for num in range(1, top):
        out += b"%010d 00000 n \n" % offsets.get(num, 0)
    out += (b"trailer\n<< /Size %d /Root %d 0 R /Info %d 0 R >>\nstartxref\n%d\n%%%%EOF\n"
            % (top, n_catalog, n_info, xref_at))
    return bytes(out), lost_all


# --------------------------------------------------------------------------
# reading back (used by the tests to open what was actually written)
# --------------------------------------------------------------------------

_OBJ_RE = re.compile(rb"(\d+) 0 obj\n(.*?)\nendobj\n", re.S)


def _objects(data: bytes):
    return {int(m.group(1)): m.group(2) for m in _OBJ_RE.finditer(data)}


def _page_object_numbers(objs):
    for num, body in objs.items():
        if b"/Type /Pages" in body:
            kids = re.search(rb"/Kids \[ (.*?) \]", body, re.S)
            if kids:
                return [int(x) for x in re.findall(rb"(\d+) 0 R", kids.group(1))]
    return []


def read_pdf_pages(data: bytes):
    """Return the visible text of each page, in page order, as a list of str."""
    objs = _objects(data)
    out = []
    for pnum in _page_object_numbers(objs):
        body = objs[pnum]
        cm = re.search(rb"/Contents (\d+) 0 R", body)
        text = ""
        if cm:
            stream = objs.get(int(cm.group(1)), b"")
            sm = re.search(rb"stream\n(.*)\nendstream", stream, re.S)
            if sm:
                parts = []
                for lit in re.findall(rb"\(((?:[^()\\]|\\.)*)\) Tj", sm.group(1)):
                    lit = (lit.replace(b"\\(", b"(").replace(b"\\)", b")")
                              .replace(b"\\\\", b"\\"))
                    parts.append(lit.decode("cp1252", "replace"))
                text = "\n".join(parts)
        out.append(text)
    return out


def read_pdf_outline(data: bytes):
    """Return [(title, 0-based page index)] by walking the real outline chain."""
    objs = _objects(data)
    pages = _page_object_numbers(objs)
    root = None
    for num, body in objs.items():
        if b"/Type /Outlines" in body:
            root = body
            break
    if root is None:
        return []
    first = re.search(rb"/First (\d+) 0 R", root)
    if not first:
        return []
    out, cur, seen = [], int(first.group(1)), set()
    while cur and cur not in seen:
        seen.add(cur)
        body = objs.get(cur, b"")
        t = re.search(rb"/Title \(((?:[^()\\]|\\.)*)\)", body)
        d = re.search(rb"/Dest \[ (\d+) 0 R", body)
        if t and d:
            title = (t.group(1).replace(b"\\(", b"(").replace(b"\\)", b")")
                     .replace(b"\\\\", b"\\")).decode("cp1252", "replace")
            pnum = int(d.group(1))
            out.append((title, pages.index(pnum) if pnum in pages else -1))
        nxt = re.search(rb"/Next (\d+) 0 R", body)
        cur = int(nxt.group(1)) if nxt else None
    return out


def read_pdf_links(data: bytes):
    """Return [(source page index, destination page index)] for every /Link."""
    objs = _objects(data)
    pages = _page_object_numbers(objs)
    out = []
    for pi, pnum in enumerate(pages):
        am = re.search(rb"/Annots \[ (.*?) \]", objs[pnum], re.S)
        if not am:
            continue
        for anum in re.findall(rb"(\d+) 0 R", am.group(1)):
            body = objs.get(int(anum), b"")
            d = re.search(rb"/Dest \[ (\d+) 0 R", body)
            if d:
                dn = int(d.group(1))
                out.append((pi, pages.index(dn) if dn in pages else -1))
    return out
