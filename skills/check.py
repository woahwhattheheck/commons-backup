#!/usr/bin/env python3
"""Receipt for the worker packs. One job per skill. Spec: agentskills.io."""
from __future__ import annotations

import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS = os.path.join(ROOT, ".agents", "skills")
MANIFEST = os.path.join(ROOT, "skills.json")
MANUAL = os.path.join(ROOT, "skills", "MANUAL.md")
NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def frontmatter(text: str) -> dict:
    if not text.startswith("---\n"):
        raise ValueError("missing YAML frontmatter")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise ValueError("unclosed YAML frontmatter")
    block = text[4:end]
    data = {}
    key = None
    for line in block.splitlines():
        if line.startswith("  ") and key == "description":
            data[key] = (data.get(key, "") + " " + line.strip()).strip()
            continue
        if line.startswith("  ") and key == "metadata":
            continue
        m = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if not m:
            continue
        key, val = m.group(1), m.group(2).strip()
        if val == ">" or val == "|":
            data[key] = ""
            continue
        data[key] = val.strip("\"'")
    return data


def main() -> int:
    with open(MANIFEST, encoding="utf-8") as f:
        manifest = json.load(f)
    rows = manifest["skills"]
    manual = open(MANUAL, encoding="utf-8").read()
    failed = []
    seen = set()
    for row in rows:
        sid = row["id"]
        seen.add(sid)
        path = os.path.join(SKILLS, sid, "SKILL.md")
        if not os.path.isfile(path):
            failed.append("%s: missing %s" % (sid, path))
            continue
        meta = frontmatter(open(path, encoding="utf-8").read())
        if meta.get("name") != sid:
            failed.append("%s: name %r != directory" % (sid, meta.get("name")))
        desc = meta.get("description") or ""
        if not (1 <= len(desc) <= 1024):
            failed.append("%s: description length %d" % (sid, len(desc)))
        if not NAME_RE.match(sid):
            failed.append("%s: bad name" % sid)
        token = row.get("token") or ""
        if token:
            tpath = os.path.join(ROOT, token)
            if not os.path.isfile(tpath):
                failed.append("%s: missing token %s" % (sid, token))
        if sid not in manual:
            failed.append("%s: not named in skills/MANUAL.md" % sid)
    dirs = {
        name
        for name in os.listdir(SKILLS)
        if os.path.isdir(os.path.join(SKILLS, name))
    }
    extra = dirs - seen
    if extra:
        failed.append("skill dirs not in skills.json: %s" % sorted(extra))
    missing = seen - dirs
    if missing:
        failed.append("manifest ids without dirs: %s" % sorted(missing))
    if failed:
        print("FAIL")
        for line in failed:
            print(" ", line)
        return 1
    print("PASS %d skills" % len(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
