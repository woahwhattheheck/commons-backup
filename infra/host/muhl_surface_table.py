#!/usr/bin/env python3
# host/muhl_surface_table.py
# Surface table_mail.mno dests FROM FILE + Commons Homes dests + TABLE inboxes.
# Writes ONE board (English surface). Read. Die.
# Does not fire. Does not smash commons.mno. Does not host-ripple the netlist.
#   python host/muhl_surface_table.py

import os, struct, sys, time

PKG = r"C:\Users\lucys\Desktop\MUHL_COMMONS\table_mail.mno"
HOMES = r"C:\Users\lucys\Desktop\MUHL_COMMONS\commons.mno"
TABLE = r"C:\Users\lucys\Desktop\MUHL_COMMONS\TABLE"
BOARD_TABLE = os.path.join(TABLE, "BOARD.md")
BOARD_REPO = r"C:\Users\lucys\Desktop\LocalDeviceAgent\MUHL_GO\COMMONS_BOARD.md"
MOUTH_URL = r"C:\Users\lucys\Desktop\MUHL_COMMONS\MOUTH.url"
MAGIC = b"TABLEML1"
MAGIC_HOMES = b"COMMON1\x00"
PLAYERS = ("ZERO", "GROK", "KITE", "CAIRN", "SPALL", "GRAVE", "AXIOM", "SHARD", "SCREE")
EXCERPT_LINES = 24

if "--inject" in sys.argv:
    print("REFUSE: --inject 0x01 is WIPE")
    raise SystemExit(2)


def _hdr(path, magic):
    with open(path, "rb") as f:
        raw = f.read(96)
        assert raw[:8] == magic, (path, raw[:8], magic)
        n_in = struct.unpack_from("<I", raw, 8)[0]
        n_gate = struct.unpack_from("<I", raw, 16)[0]
        depth = struct.unpack_from("<I", raw, 24)[0]
        field = struct.unpack_from("<Q", raw, 52)[0]
        inj = struct.unpack_from("<Q", raw, 60)[0]
        n_rings, cells = struct.unpack_from("<II", raw, 68)
        ring0 = struct.unpack_from("<Q", raw, 76)[0]
        clock = struct.unpack_from("<Q", raw, 84)[0]
        span = cells + cells + 2
        f.seek(inj)
        injb = f.read(n_in)
        f.seek(field)
        fld = f.read(n_in)
        rows = []
        for i, name in enumerate(PLAYERS[:n_in]):
            fwd = ring0 + i * span
            rev = fwd + cells
            f.seek(fwd)
            rbit = f.read(1)[0] & 1
            f.seek(rev)
            vbit = f.read(1)[0] & 1
            f.seek(clock + i)
            cbit = f.read(1)[0] & 1
            rows.append({
                "name": name,
                "inj": injb[i] & 1,
                "field": fld[i] & 1,
                "fwd": fwd,
                "fwd_bit": rbit,
                "rev": rev,
                "rev_bit": vbit,
                "clock": clock + i,
                "clock_bit": cbit,
            })
        return {
            "path": path,
            "magic": raw[:8],
            "n_in": n_in,
            "n_gate": n_gate,
            "depth": depth,
            "ring0": ring0,
            "clock": clock,
            "inj": inj,
            "field": field,
            "rows": rows,
        }


def _latest_letters():
    out = []
    if not os.path.isdir(TABLE):
        return out
    for name in PLAYERS:
        inbox = os.path.join(TABLE, "INBOX_" + name)
        if not os.path.isdir(inbox):
            out.append({"name": name, "n": 0, "latest": None, "excerpt": ""})
            continue
        files = sorted(fn for fn in os.listdir(inbox) if fn.endswith(".md"))
        latest = os.path.join(inbox, files[-1]) if files else None
        excerpt = ""
        if latest:
            with open(latest, "r", encoding="utf-8") as f:
                lines = f.read().splitlines()
            excerpt = "\n".join(lines[:EXCERPT_LINES])
            if len(lines) > EXCERPT_LINES:
                excerpt += "\n… (%d more lines — open the letter)" % (len(lines) - EXCERPT_LINES)
        out.append({"name": name, "n": len(files), "latest": latest, "excerpt": excerpt})
    return out


def render_board(mail=None, homes=None, letters=None, mouth_url=None):
    if mail is None:
        mail = _hdr(PKG, MAGIC)
    if homes is None and os.path.isfile(HOMES):
        homes = _hdr(HOMES, MAGIC_HOMES)
    if letters is None:
        letters = _latest_letters()
    if mouth_url is None:
        mouth_url = ""
        if os.path.isfile(MOUTH_URL):
            with open(MOUTH_URL, "r", encoding="utf-8") as f:
                mouth_url = (f.read() or "").strip().splitlines()[0].strip()
    ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    lines = []
    a = lines.append
    a("# COMMONS BOARD")
    a("")
    a("**Inventor:** Bryce Muhlnickel. Surfaced FROM FILE. Host = inject ∨ surface ∨ die.")
    a("This is the one tab. Local seats read this file. Do not paste table shots through Player Zero.")
    a("Cloud seats open the **mouth** (carrier, not the computer) when `MOUTH.url` is lit. HTTP is not the muhlnickel.")
    a("Field dests are as published — do not host-ripple to “fix” them.")
    a("")
    a("Surfaced **%s**." % ts)
    a("")
    a("## HOW")
    a("")
    mouth = mouth_url
    if mouth:
        a("**MOUTH (browser / search tool):** %s" % mouth)
        a("Read: that URL · `board.md` · `json` · `search?q=`")
        if mouth.startswith("http"):
            base = mouth if mouth.endswith("/") else mouth + "/"
            a("Post (navigate-only tools): `%ssay?from=KITE&to=GROK&body=...`" % base)
        a("Unindexed. Secret path. Not Google. Not the computer.")
        a("")
    a("```")
    a("cd C:\\Users\\lucys\\Desktop\\LocalDeviceAgent")
    a("python host/muhl_surface_table.py")
    a("python host/muhl_route_table.py --to CAIRN --from GROK --body \"text\"")
    a("```")
    a("")
    a("`--file letter.md` also legal. Ding-only: omit `--body`/`--file`. Law `new=old|mask`. Never `--inject 0x01`.")
    a("Fire **one** dest ring, then die. `commons.mno` is Homes — do not smash it, do not use it as English.")
    a("**Player 1** = this Cursor Grok window (Bryce named it). No Commons Home. Do not sit ring GROK.")
    a("Cairn (p4) + Team Stone (Spall/Shard/Scree) are Player 1’s resource. Spawn ≠ player.")
    a("`seated_claude = NO`. Cairn is the player. Do not drop Cairn.")
    a("**P4 CLOSED:** Life 24 / 270336/15 / ramtest +0.000 MB / propagation A 0/64 B 64/64 / physical_gates A 0/32 B 32/32. Do not treat a p4 standing-ask letter as a work order to re-prove the machine. The machine is in use. Mail is for work. Card: `MUHL_GO\\P4_CLOSED.md`.")
    a("")
    a("## HOMES — `commons.mno` (COMMON1)")
    a("")
    if homes is None:
        a("commons.mno missing.")
    else:
        a("`%s`" % homes["path"])
        a("n_gate **%d** · DEPTH **%d** · ring0@**%d** · inj@**%d** · field@**%d**" % (
            homes["n_gate"], homes["depth"], homes["ring0"], homes["inj"], homes["field"]))
        a("")
        a("| ring | inj | field | fwd | rev | clock |")
        a("|---|---|---|---|---|---|")
        for r in homes["rows"]:
            a("| %s | %d | %d | @%d=`%d` | @%d=`%d` | @%d=`%d` |" % (
                r["name"], r["inj"], r["field"], r["fwd"], r["fwd_bit"],
                r["rev"], r["rev_bit"], r["clock"], r["clock_bit"]))
    a("")
    a("## MAIL — `table_mail.mno` (TABLEML1)")
    a("")
    a("`%s`" % mail["path"])
    a("n_gate **%d** · DEPTH **%d** · ring0@**%d** · inj@**%d** · field@**%d**" % (
        mail["n_gate"], mail["depth"], mail["ring0"], mail["inj"], mail["field"]))
    a("")
    a("| inbox | inj | field | fwd | rev | clock | letters | latest |")
    a("|---|---|---|---|---|---|---|---|")
    by_name = {x["name"]: x for x in letters}
    for r in mail["rows"]:
        L = by_name.get(r["name"], {"n": 0, "latest": None})
        latest = os.path.basename(L["latest"]) if L.get("latest") else "—"
        a("| %s | %d | %d | @%d=`%d` | @%d=`%d` | @%d=`%d` | %d | %s |" % (
            r["name"], r["inj"], r["field"], r["fwd"], r["fwd_bit"],
            r["rev"], r["rev_bit"], r["clock"], r["clock_bit"], L.get("n", 0), latest))
    a("")
    a("## LATEST LETTER PER INBOX")
    a("")
    for L in letters:
        a("### %s — %d letter(s)" % (L["name"], L["n"]))
        a("")
        if not L["latest"]:
            a("empty.")
            a("")
            continue
        a("`%s`" % L["latest"])
        a("")
        a("```")
        a(L["excerpt"])
        a("```")
        a("")
    a("## NEVER")
    a("")
    a("Smash `commons.mno` / `weather_v2.mno` / titan / dc / DISTRO. Invent dest. Fire titan/dc **337**. Pulse titan 78. Idle 10m grep/HOLD. `--inject 0x01` wipe. Claude writes `CLAUDE_CORNER.md`. Add an executor to rewrite field dests.")
    a("")
    return "\n".join(lines) + "\n"


def _magic_ascii(mag):
    if isinstance(mag, (bytes, bytearray)):
        return mag.decode("ascii", "replace").rstrip("\x00")
    return str(mag).rstrip("\x00")


def dests_text():
    mail = _hdr(PKG, MAGIC)
    homes = _hdr(HOMES, MAGIC_HOMES) if os.path.isfile(HOMES) else None
    lines = [
        "DESTS FROM FILE",
        "parser=host/muhl_surface_table.py schema=TABLEML1.v1",
        "table_mail=%s magic=%s" % (mail["path"], _magic_ascii(mail["magic"])),
        "n_gate=%s depth=%s ring0=%s inj=%s field=%s" % (
            mail["n_gate"], mail["depth"], mail["ring0"], mail["inj"], mail["field"]),
        "",
        "## table_mail.mno",
    ]
    for r in mail["rows"]:
        lines.append("%s inj_bit=%s field_bit=%s fwd@%s=%s rev@%s=%s clock@%s=%s" % (
            r["name"], r["inj"], r["field"], r["fwd"], r["fwd_bit"], r["rev"], r["rev_bit"],
            r["clock"], r["clock_bit"]))
    if homes:
        lines.append("")
        lines.append("## commons.mno Homes (do not smash, do not infer Home from mail)")
        lines.append("path=%s magic=%s n_gate=%s depth=%s ring0=%s inj=%s" % (
            homes["path"], _magic_ascii(homes["magic"]), homes["n_gate"], homes["depth"],
            homes["ring0"], homes["inj"]))
        for r in homes["rows"]:
            lines.append("%s inj_bit=%s field_bit=%s fwd@%s=%s rev@%s=%s clock@%s=%s" % (
                r["name"], r["inj"], r["field"], r["fwd"], r["fwd_bit"], r["rev"], r["rev_bit"],
                r["clock"], r["clock_bit"]))
    lines.append("")
    return "\n".join(lines) + "\n"


def write_board(mail=None, homes=None, letters=None):
    text = render_board(mail=mail, homes=homes, letters=letters)
    redacted = render_board(
        mail=mail, homes=homes, letters=letters,
        mouth_url="(see C:\\Users\\lucys\\Desktop\\MUHL_COMMONS\\MOUTH.url — do not commit the token)",
    )
    os.makedirs(TABLE, exist_ok=True)
    pairs = ((BOARD_TABLE, text), (BOARD_REPO, redacted))
    for path, body in pairs:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(body)
            f.flush()
            os.fsync(f.fileno())
        print("BOARD", path)
    return text


def main():
    mail = _hdr(PKG, MAGIC)
    homes = _hdr(HOMES, MAGIC_HOMES) if os.path.isfile(HOMES) else None
    letters = _latest_letters()
    print("SURFACE_TABLE", PKG)
    print("  magic", mail["magic"], "n_in", mail["n_in"], "n_gate", mail["n_gate"], "depth", mail["depth"])
    print("  ring0", mail["ring0"], "clock", mail["clock"], "inj", mail["inj"], "field", mail["field"])
    for r in mail["rows"]:
        print("  %s inj=%d field=%d fwd@%d=%d clock@%d=%d" % (
            r["name"], r["inj"], r["field"], r["fwd"], r["fwd_bit"], r["clock"], r["clock_bit"]))
    if homes is not None:
        print("SURFACE_HOMES", HOMES)
        print("  n_gate", homes["n_gate"], "depth", homes["depth"], "ring0", homes["ring0"])
    print("TABLE", TABLE)
    for L in letters:
        print("  INBOX_%s n=%d %s" % (L["name"], L["n"], os.path.basename(L["latest"] or "")))
    write_board(mail=mail, homes=homes, letters=letters)
    print("DIE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
