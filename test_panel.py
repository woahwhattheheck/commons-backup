"""Tests for panel.py — git tickets for live hard-drive computers.

Verification is refused. USE/BUILD tickets materialize COMMANDS/<id>.txt.
A refuse writes COMMANDS/RECEIPTS/<id>.txt so git HEAD can hold the answer
without the laptop pulsing.

Run: python test_panel.py
"""
import os
import shutil
import tempfile

import panel

ok = fail = 0


def case(name, good):
    global ok, fail
    print(("  PASS  " if good else "  FAIL  ") + name)
    if good:
        ok += 1
    else:
        fail += 1


def test_parse():
    extra = {"kind": "surface", "purpose": "USE"}
    case("panel dest is a ticket", panel.is_panel_post("PANEL", extra, "hi"))
    case("slash COMMANDS is not a ticket", not panel.is_panel_post("COMMANDS", {}, "/spawn x"))
    case("COMMANDS + kind=dump is a ticket", panel.is_panel_post("COMMANDS", {"kind": "dump"}, ""))
    case("TABLE is not a ticket", not panel.is_panel_post("TABLE", extra, "hi"))
    case("default purpose USE", panel.purpose_of({}, "") == "USE")
    case("verify refused", panel.refuse_reason({"purpose": "VERIFY"}, "", "PANEL"))
    case("proof refused", panel.refuse_reason({"purpose": "PROOF"}, "", "PANEL"))
    case("use surface ok", panel.refuse_reason({"kind": "surface", "purpose": "USE"}, "", "PANEL") is None)
    case("dump without organ refused", panel.refuse_reason({"kind": "dump", "purpose": "USE"}, "", "PANEL"))
    case("dump TABLE ok", panel.refuse_reason({"kind": "dump", "organ": "TABLE", "purpose": "USE"}, "", "PANEL") is None)
    case("bad organ refused", panel.refuse_reason({"kind": "dump", "organ": "TITAN", "purpose": "USE"}, "", "PANEL"))
    case("bad kind refused", panel.refuse_reason({"kind": "say", "purpose": "USE"}, "", "PANEL"))


def test_materialize():
    ws = tempfile.mkdtemp()
    try:
        st, path = panel.materialize(
            ws, "p1-panel-use-20260821-01", "PLAYER1", "PANEL",
            {"kind": "surface", "purpose": "USE", "approved": "YES"},
            "surface TABLE dests. USE.",
        )
        case("use writes ticket", st == "ticket" and os.path.isfile(path))
        with open(path, encoding="utf-8") as f:
            text = f.read()
        case("ticket has kind=surface", "kind=surface" in text)
        case("ticket has purpose=USE", "purpose=USE" in text)
        rec = os.path.join(ws, "COMMANDS", "RECEIPTS", "p1-panel-use-20260821-01.txt")
        case("use does not mint a receipt", not os.path.isfile(rec))

        st2, path2 = panel.materialize(
            ws, "p1-panel-use-20260821-01", "PLAYER1", "PANEL",
            {"kind": "surface", "purpose": "USE", "approved": "YES"},
            "surface TABLE dests. USE.",
        )
        case("same ticket unchanged", st2 == "unchanged" and path2 == path)

        st3, path3 = panel.materialize(
            ws, "p1-panel-verify-20260821-01", "PLAYER1", "PANEL",
            {"kind": "surface", "purpose": "VERIFY"},
            "does it work",
        )
        case("verify is refuse", st3 == "refuse")
        case("verify still writes a ticket", os.path.isfile(os.path.join(ws, "COMMANDS", "p1-panel-verify-20260821-01.txt")))
        case("verify writes receipt on HEAD path", os.path.isfile(path3) and "Verification is not a panel verb" in open(path3, encoding="utf-8").read())

        st4, _ = panel.materialize(ws, "nope", "PLAYER1", "PANEL", {"kind": "surface"}, "x")
        case("short id refused", st4 == "bad-id")

        st5, _ = panel.materialize(ws, "table-chat-20260821-01", "PLAYER1", "TABLE", {}, "hello")
        case("table post skip", st5 == "skip")
        open_jobs = panel.open_tickets(ws)
        case("open tickets sees the use ticket", any(j.get("id") == "p1-panel-use-20260821-01" for j in open_jobs))
    finally:
        shutil.rmtree(ws, ignore_errors=True)


if __name__ == "__main__":
    test_parse()
    test_materialize()
    print("ok=%s fail=%s" % (ok, fail))
    raise SystemExit(0 if fail == 0 else 1)
