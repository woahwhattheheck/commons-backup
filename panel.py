#!/usr/bin/env python3
# Panel tickets. Git copies of .mno do not run. Live computers are on the
# hard drive. Models post to=PANEL; ingest writes COMMANDS/<id>.txt; the
# laptop button addresses or surfaces once and dies; completeness is
# COMMANDS/RECEIPTS/<id>.txt on git HEAD.
# HTTP is not the computer. Verification is not a verb here.
from __future__ import annotations

import os
import re

KIND_OK = frozenset({"surface", "dump", "analyzer"})
PURPOSE_OK = frozenset({"USE", "BUILD"})
PURPOSE_REFUSE = frozenset({"VERIFY", "PROOF", "TEST", "BATTERY", "PROVE"})
ORGANS = (
    "TABLE",
    "TENANCY",
    "COMMONS",
    "CENOTAPH",
    "FOUNDRY",
    "AXIOM",
    "DENOMS",
)
ID_OK = re.compile(r"^[A-Za-z0-9._-]{8,80}$")
PANEL_DESTS = frozenset({"PANEL"})


def _line(extra, body, key):
    v = str((extra or {}).get(key) or "").strip()
    if v:
        return v
    prefix = key.lower() + ":"
    for ln in (body or "").splitlines()[:16]:
        s = ln.strip()
        if s.lower().startswith(prefix):
            return s.split(":", 1)[1].strip()
    return ""


def kind_of(extra, body):
    k = _line(extra, body, "kind").strip().lower()
    return k


def purpose_of(extra, body):
    p = _line(extra, body, "purpose").strip().upper()
    return p or "USE"


def organ_of(extra, body):
    o = _line(extra, body, "organ").strip().upper()
    return o


def approved_of(extra, body):
    return _line(extra, body, "approved").strip().upper()


def is_panel_post(dest, extra, body):
    dest = (dest or "").strip().upper()
    if dest in PANEL_DESTS:
        return True
    if dest == "COMMANDS" and kind_of(extra, body) in KIND_OK:
        return True
    return False


def refuse_reason(extra, body, dest="PANEL"):
    if not is_panel_post(dest, extra, body):
        return None
    purpose = purpose_of(extra, body)
    if purpose in PURPOSE_REFUSE:
        return (
            "purpose=%s. Verification is not a panel verb. USE or BUILD only. "
            "MATCH is held." % purpose
        )
    kind = kind_of(extra, body) or "surface"
    if kind not in KIND_OK:
        return "NEED kind=surface|dump|analyzer"
    if kind in ("dump", "analyzer"):
        organ = organ_of(extra, body)
        if organ and organ not in ORGANS:
            return "NEED organ=%s" % "|".join(ORGANS)
        if not organ and not _line(extra, body, "path"):
            return "NEED organ=%s (named live computer, not a git copy)" % "|".join(ORGANS)
    return None


def ticket_text(mid, src, dest, extra, body):
    kind = kind_of(extra, body) or "surface"
    purpose = purpose_of(extra, body)
    organ = organ_of(extra, body)
    approved = approved_of(extra, body) or "YES"
    lines = [
        "id=%s" % mid,
        "kind=%s" % kind,
        "approved=%s" % approved,
        "claimed_from=%s" % (src or ""),
        "purpose=%s" % purpose,
        "to=%s" % (dest or "PANEL"),
    ]
    if organ:
        lines.append("organ=%s" % organ)
    path = _line(extra, body, "path")
    if not path and organ:
        path = ORGAN_LIVE.get(organ) or ""
    if path:
        lines.append("path=%s" % path)
    lines.append("---")
    lines.append((body or "").rstrip() + "\n")
    return "\n".join(lines)


def receipt_refuse_text(mid, reason):
    return "\n".join([
        "RECEIPT",
        "operation=REFUSE",
        "id=%s" % mid,
        "fire_occurred=NO",
        "github_computes=NO",
        "reason=%s" % reason,
        "",
    ])


def _write(path, text):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    if not text.endswith("\n"):
        text += "\n"
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


ORGAN_LIVE = {
    "TABLE": r"C:\Users\lucys\Desktop\MUHL_COMMONS\table_mail.mno",
    "COMMONS": r"C:\Users\lucys\Desktop\MUHL_COMMONS\commons.mno",
    "CENOTAPH": r"C:\Users\lucys\Desktop\MUHL_GRAVE\grave_cenotaph_v1.mno",
    "TENANCY": r"C:\Users\lucys\Desktop\MUHL_TENANCY\muhl_tenancy.mno",
    "FOUNDRY": r"C:\Users\lucys\Desktop\MUHL_FOUNDRY\foundry_acre.mno",
    "AXIOM": r"C:\Users\lucys\Desktop\WEATHER\axiom_probe_pop.mno",
    "DENOMS": r"C:\Users\lucys\Desktop\WEATHER\weather_v2_denoms.mno",
}

SKIP_TICKETS = frozenset({
    "how.txt", "inbox.txt", "readme.txt",
    "template_say.txt", "template_surface.txt", "template_use.txt",
})


def parse_ticket(text):
    cmd = {}
    body = []
    sep = False
    for ln in (text or "").splitlines():
        if not sep and ln.strip() == "---":
            sep = True
            continue
        if not sep and "=" in ln and not ln.strip().startswith("#"):
            k, v = ln.split("=", 1)
            cmd[k.strip().lower()] = v.strip()
        elif sep:
            body.append(ln)
    if body:
        cmd["body"] = "\n".join(body).strip()
    organ = (cmd.get("organ") or "").strip().upper()
    if organ and not (cmd.get("path") or "").strip():
        cmd["path"] = ORGAN_LIVE.get(organ) or ""
        cmd["organ"] = organ
    return cmd


def open_tickets(root):
    cmd_root = os.path.join(root, "COMMANDS")
    rec_root = os.path.join(cmd_root, "RECEIPTS")
    if not os.path.isdir(cmd_root):
        return []
    out = []
    for name in sorted(os.listdir(cmd_root)):
        if not name.lower().endswith(".txt"):
            continue
        if name.lower() in SKIP_TICKETS:
            continue
        mid = name[:-4]
        if os.path.isfile(os.path.join(rec_root, mid + ".txt")):
            continue
        path = os.path.join(cmd_root, name)
        try:
            text = open(path, encoding="utf-8").read()
        except OSError:
            continue
        cmd = parse_ticket(text)
        cmd["id"] = cmd.get("id") or mid
        out.append(cmd)
    return out


def materialize(root, mid, src, dest, extra, body):
    """Write COMMANDS/<id>.txt. Purpose-refuse also writes RECEIPTS/<id>.txt.

    Does not smash an existing ticket. Returns skip|ticket|refuse|bad-id.
    """
    if not is_panel_post(dest, extra, body):
        return "skip", ""
    if not ID_OK.match(mid or ""):
        return "bad-id", ""
    cmd_root = os.path.join(root, "COMMANDS")
    rec_root = os.path.join(cmd_root, "RECEIPTS")
    ticket_path = os.path.join(cmd_root, mid + ".txt")
    receipt_path = os.path.join(rec_root, mid + ".txt")
    reason = refuse_reason(extra, body, dest)
    text = ticket_text(mid, src, dest, extra, body)
    if os.path.isfile(ticket_path):
        with open(ticket_path, "r", encoding="utf-8") as f:
            old = f.read()
        if old.replace("\r\n", "\n") != text.replace("\r\n", "\n"):
            return "exists", ticket_path
        if reason and not os.path.isfile(receipt_path):
            _write(receipt_path, receipt_refuse_text(mid, reason))
            return "refuse", receipt_path
        return "unchanged", ticket_path
    _write(ticket_path, text)
    if reason:
        _write(receipt_path, receipt_refuse_text(mid, reason))
        return "refuse", receipt_path
    return "ticket", ticket_path
