"""Stdlib OOXML writer recovered from OP5-TOPAZ bid_pack/docxwrite.py.

Used here as an input writer for isolated UIOWA-136 bid_assembly.
TOPAZ retains original assembler credit. This copy pins zip timestamps
so repeated builds of identical blocks are byte-identical.
"""

from __future__ import annotations

import re
import zipfile
from xml.sax.saxutils import escape, quoteattr

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
</Types>"""

_ROOT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
</Relationships>"""

_DOC_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"""


def _styles_xml():
    out = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
           '<w:styles xmlns:w="%s">' % W,
           '<w:style w:type="paragraph" w:default="1" w:styleId="Normal">'
           '<w:name w:val="Normal"/><w:rPr><w:sz w:val="22"/></w:rPr></w:style>']
    for lvl, sz in ((1, 32), (2, 26), (3, 24)):
        out.append(
            '<w:style w:type="paragraph" w:styleId="Heading%d">'
            '<w:name w:val="heading %d"/><w:basedOn w:val="Normal"/>'
            '<w:pPr><w:outlineLvl w:val="%d"/></w:pPr>'
            '<w:rPr><w:b/><w:sz w:val="%d"/></w:rPr></w:style>' % (lvl, lvl, lvl - 1, sz))
    out.append('<w:style w:type="character" w:styleId="Hyperlink">'
               '<w:name w:val="Hyperlink"/><w:rPr><w:u w:val="single"/></w:rPr></w:style>')
    out.append('</w:styles>')
    return "".join(out)


def _core_xml(title, author):
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<cp:coreProperties '
        'xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/">'
        '<dc:title>%s</dc:title><dc:creator>%s</dc:creator>'
        '</cp:coreProperties>' % (escape(title), escape(author)))


def _safe_anchor(anchor):
    """Word bookmark names: letters/digits/underscore, <=40 chars, no leading digit."""
    a = re.sub(r"[^0-9A-Za-z_]", "_", anchor)
    if not a or a[0].isdigit():
        a = "b_" + a
    return a[:40]


def write_docx(path, blocks, title="Document", author="", lang="en-US"):
    """Write a .docx from the same block list the PDF path uses.

    Returns the set of anchors that were actually bookmarked, so the caller can
    tell which internal links will land. A link whose anchor was never defined
    is written as plain text, never as a hyperlink that goes nowhere.
    """
    defined = set()
    for blk in blocks:
        if blk.get("anchor"):
            defined.add(_safe_anchor(blk["anchor"]))

    body, bid = [], 1
    for blk in blocks:
        kind = blk.get("kind", "body")
        if kind in ("pagebreak", "spacer"):
            if kind == "pagebreak":
                body.append('<w:p><w:r><w:br w:type="page"/></w:r></w:p>')
            continue
        style = {"title": "Heading1", "heading": "Heading1",
                 "subheading": "Heading2", "body": "Normal",
                 "mono": "Normal", "link": "Normal"}.get(kind, "Normal")
        mono = '<w:rFonts w:ascii="Courier New" w:hAnsi="Courier New"/><w:sz w:val="16"/>' \
            if kind == "mono" else ""
        rpr = '<w:rPr>%s<w:lang w:val=%s/></w:rPr>' % (mono, quoteattr(lang))
        text = escape(blk.get("text", ""))
        inner = ""
        if blk.get("anchor"):
            a = _safe_anchor(blk["anchor"])
            inner += '<w:bookmarkStart w:id="%d" w:name=%s/>' % (bid, quoteattr(a))
        run = '<w:r>%s<w:t xml:space="preserve">%s</w:t></w:r>' % (rpr, text)
        dest = blk.get("dest")
        if dest and _safe_anchor(dest) in defined:
            run = ('<w:hyperlink w:anchor=%s><w:r><w:rPr>%s<w:rStyle w:val="Hyperlink"/>'
                   '</w:rPr><w:t xml:space="preserve">%s</w:t></w:r></w:hyperlink>'
                   % (quoteattr(_safe_anchor(dest)), mono, text))
        inner += run
        if blk.get("anchor"):
            inner += '<w:bookmarkEnd w:id="%d"/>' % bid
            bid += 1
        body.append('<w:p><w:pPr><w:pStyle w:val="%s"/></w:pPr>%s</w:p>' % (style, inner))

    doc = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           '<w:document xmlns:w="%s" xmlns:r="%s"><w:body>%s'
           '<w:sectPr><w:pgSz w:w="12240" w:h="15840"/></w:sectPr>'
           '</w:body></w:document>' % (W, R, "".join(body)))

    def _put(z, name, data):
        info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        z.writestr(info, data)

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        _put(z, "[Content_Types].xml", _CONTENT_TYPES)
        _put(z, "_rels/.rels", _ROOT_RELS)
        _put(z, "docProps/core.xml", _core_xml(title, author))
        _put(z, "word/_rels/document.xml.rels", _DOC_RELS)
        _put(z, "word/styles.xml", _styles_xml())
        _put(z, "word/document.xml", doc)
    return defined


def read_docx_text(path):
    """Reopen the package and return the visible paragraph text, in order."""
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8")
    out = []
    for para in re.findall(r"<w:p>.*?</w:p>", xml, re.S):
        runs = re.findall(r"<w:t[^>]*>(.*?)</w:t>", para, re.S)
        out.append("".join(runs).replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">"))
    return out


def read_docx_nav(path):
    """Return (bookmark names, internal hyperlink anchors) from the written bytes."""
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8")
    marks = set(re.findall(r'<w:bookmarkStart [^>]*w:name="([^"]+)"', xml))
    links = re.findall(r'<w:hyperlink w:anchor="([^"]+)"', xml)
    return marks, links
