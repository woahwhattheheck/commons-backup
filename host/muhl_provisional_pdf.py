#!/usr/bin/env python3
"""host/muhl_provisional_pdf.py — collapse PROVISIONAL_SESSION.md to PDF. Dies.

Host = surface ∨ die. No titan write. No dc inject. No 337. No --go.

  python host/muhl_provisional_pdf.py
"""
from __future__ import annotations

import html
import os
import subprocess
import sys

MD = os.path.normpath(r"C:\Users\lucys\Desktop\MUHL_GO\PROVISIONAL_SESSION.md")
PDF = os.path.normpath(r"C:\Users\lucys\Desktop\MUHL_GO\PROVISIONAL_SESSION.pdf")
HTM = os.path.normpath(r"C:\Users\lucys\Desktop\MUHL_GO\PROVISIONAL_SESSION.print.html")

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass


def _md_to_html(text):
    lines = text.replace("\r\n", "\n").split("\n")
    out = [
        "<!DOCTYPE html><html><head><meta charset='utf-8'>",
        "<title>PROVISIONAL SESSION</title>",
        "<style>body{font-family:Calibri,Arial,sans-serif;font-size:11pt;margin:24px;color:#111}",
        "h1{font-size:18pt}h2{font-size:14pt}h3{font-size:12pt}",
        "pre,code{font-family:Consolas,monospace;font-size:9pt}",
        "table{border-collapse:collapse}td,th{border:1px solid #333;padding:4px 8px}",
        "</style></head><body>",
    ]
    in_pre = False
    in_table = False
    for line in lines:
        if line.startswith("```"):
            if in_pre:
                out.append("</pre>")
                in_pre = False
            else:
                out.append("<pre>")
                in_pre = True
            continue
        if in_pre:
            out.append(html.escape(line))
            continue
        if line.startswith("|") and "---" not in line:
            cells = [c.strip() for c in line.strip("|").split("|")]
            tag = "th" if not in_table else "td"
            if not in_table:
                out.append("<table>")
                in_table = True
            out.append("<tr>" + "".join("<%s>%s</%s>" % (tag, html.escape(c), tag) for c in cells) + "</tr>")
            continue
        if in_table:
            if line.startswith("|"):
                continue
            out.append("</table>")
            in_table = False
        if line.startswith("# "):
            out.append("<h1>%s</h1>" % html.escape(line[2:]))
        elif line.startswith("## "):
            out.append("<h2>%s</h2>" % html.escape(line[3:]))
        elif line.startswith("### "):
            out.append("<h3>%s</h3>" % html.escape(line[4:]))
        elif line.strip() == "":
            out.append("<p></p>")
        else:
            out.append("<p>%s</p>" % html.escape(line))
    if in_pre:
        out.append("</pre>")
    if in_table:
        out.append("</table>")
    out.append("</body></html>")
    return "\n".join(out)


def main():
    if not os.path.isfile(MD):
        print("NEED_BRYCE — missing %s" % MD)
        print("  (button dies)")
        return 1
    text = open(MD, "r", encoding="utf-8", errors="replace").read()
    open(HTM, "w", encoding="utf-8").write(_md_to_html(text))
    edge = os.path.normpath(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
    if not os.path.isfile(edge):
        edge = os.path.normpath(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe")
    if not os.path.isfile(edge):
        print("NEED_BRYCE — Edge missing")
        print("  html %s" % HTM)
        print("  (button dies)")
        return 1
    if os.path.isfile(PDF):
        try:
            os.remove(PDF)
        except OSError:
            pass
    cmd = [
        edge,
        "--headless",
        "--disable-gpu",
        "--no-pdf-header-footer",
        "--print-to-pdf=" + PDF,
        "file:///" + HTM.replace("\\", "/"),
    ]
    completed = subprocess.run(cmd, check=False)
    if completed.returncode != 0 or not os.path.isfile(PDF):
        print("NEED_BRYCE — pdf fail rc=%s exists=%s" % (completed.returncode, os.path.isfile(PDF)))
        print("  (button dies)")
        return 1
    n = os.path.getsize(PDF)
    mtime = os.path.getmtime(PDF)
    print("PROVISIONAL PDF")
    print("  path  %s" % PDF)
    print("  bytes %s" % n)
    print("  mtime %s" % mtime)
    print("  (button dies)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
