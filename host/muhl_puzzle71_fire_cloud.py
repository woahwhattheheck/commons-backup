#!/usr/bin/env python3
"""host/muhl_puzzle71_fire_cloud.py — derived scan-based CI fire helper.

Not the live-run instrument. Exact owner-PC bytes live at
host/muhl_puzzle71_fire_add.py (Fable blob 72e8544056c248b56975317887f39494798ff731).
Companion to host/muhl_puzzle71_organs_cloud.py.

Default --dry: bounded read of cell 0 fwd+rev every ring, write nothing.
--surface: same bounded read, labeled SURFACE.
--go: journal, new=old|0x01 cell 0 fwd+rev every ring, reread, die.

Never titan. Never --inject (wipe). Never commons.mno / dc.

  python3 host/muhl_puzzle71_fire_cloud.py --dry --reg PATH --dest PATH
  python3 host/muhl_puzzle71_fire_cloud.py --surface --reg PATH --dest PATH
  python3 host/muhl_puzzle71_fire_cloud.py --go --reg PATH --dest PATH
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

try:
    import pfc_paths as PFCP

    PFC_ROOT = PFCP.ROOT
except (ImportError, AttributeError):
    PFC_ROOT = os.environ.get("PFC_ROOT", "C:/llm").replace("\\", "/").rstrip("/")

try:
    from muhl_puzzle71_organs_cloud import DEFAULT_DEST, DEFAULT_REG, refuse_dest
except ImportError:
    DEFAULT_DEST = PFC_ROOT + "/models/muhl_puzzle71.mno"
    DEFAULT_REG = PFC_ROOT + "/models/muhl_puzzle71.circuits.json"

    def refuse_dest(path):
        base = os.path.basename(os.path.normpath(path)).lower()
        if base in ("titan.gguf", "muhlnickel_dc.mno", "dc.mno", "commons.mno"):
            return "REFUSE dest %s" % base
        return None

DEFAULT_JOURNAL = PFC_ROOT + "/models/muhl_puzzle71_fire_add_genome.jsonl"
MASK = 0x01

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fail(msg):
    print("FAIL CLOSED: %s" % msg)
    return 1


def _arg_value(argv, flag, default=None):
    if flag in argv:
        i = argv.index(flag)
        if i + 1 >= len(argv):
            return None, "%s needs a value" % flag
        return argv[i + 1], None
    return default, None


def _read_byte(path, off):
    with open(path, "rb") as f:
        f.seek(off)
        got = f.read(1)
    if len(got) != 1:
        raise IOError("short read @%s" % off)
    return got[0]


def _write_byte(path, off, val):
    with open(path, "r+b") as f:
        f.seek(off)
        f.write(bytes((val,)))
        f.flush()
        os.fsync(f.fileno())


def _journal(journal_path, row):
    parent = os.path.dirname(journal_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(journal_path, "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(row, ensure_ascii=True) + "\n")
        f.flush()
        os.fsync(f.fileno())


def load_rings(reg_path):
    if not os.path.isfile(reg_path):
        return None, "registry missing: %s" % reg_path
    with open(reg_path, encoding="utf-8") as f:
        reg = json.load(f)
    rings = reg.get("rings")
    if not isinstance(rings, list) or not rings:
        return None, "registry has no rings"
    out = []
    for i, ring in enumerate(rings):
        if not isinstance(ring, dict):
            return None, "ring %s not an object" % i
        try:
            fwd = int(ring["fwd"])
            rev = int(ring["rev"])
        except (KeyError, TypeError, ValueError):
            return None, "ring %s missing fwd/rev" % i
        if fwd < 0 or rev < 0:
            return None, "ring %s negative offset" % i
        out.append({"name": ring.get("name") or "nring2_puz%02d" % i, "fwd": fwd, "rev": rev})
    return out, None


def surface(dest, rings, label):
    print("PUZZLE71 FIRE", label)
    print("  dest", dest)
    print("  law new=old|0x01 both senses cell 0")
    rows = []
    for ring in rings:
        fo = _read_byte(dest, ring["fwd"])
        ro = _read_byte(dest, ring["rev"])
        print("  %s fwd@%s %s  rev@%s %s" % (ring["name"], ring["fwd"], fo, ring["rev"], ro))
        rows.append((ring, fo, ro))
    return rows


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--inject" in argv:
        print("REFUSE: --inject 0x01 is WIPE. Law is new=old|0x01.")
        return 2
    dest, err = _arg_value(argv, "--dest", DEFAULT_DEST)
    if err:
        return _fail(err)
    refuse = refuse_dest(dest)
    if refuse:
        print(refuse)
        return 2
    reg_path, err = _arg_value(argv, "--reg", DEFAULT_REG)
    if err:
        return _fail(err)
    journal_path, err = _arg_value(argv, "--journal", DEFAULT_JOURNAL)
    if err:
        return _fail(err)
    if "--go" not in argv and "--dry" not in argv and "--surface" not in argv:
        print("NEED --dry or --surface or --go")
        return 1
    if not os.path.isfile(dest):
        return _fail("dest missing: %s" % dest)
    rings, err = load_rings(reg_path)
    if err:
        return _fail(err)
    label = "GO" if "--go" in argv else ("SURFACE" if "--surface" in argv else "DRY")
    rows = surface(dest, rings, label)
    if "--go" not in argv:
        print("NO WRITE." if label != "SURFACE" else "SURFACE only.")
        print("DIE")
        return 0
    fired = []
    for ring, fo, ro in rows:
        fn = fo | MASK
        rn = ro | MASK
        if fn < fo or rn < ro:
            return _fail("ones would fall")
        _journal(
            journal_path,
            {
                "ts": _now(),
                "name": ring["name"],
                "fwd_off": ring["fwd"],
                "rev_off": ring["rev"],
                "old_fwd": fo,
                "old_rev": ro,
                "new_fwd": fn,
                "new_rev": rn,
                "law": "new=old|0x01",
            },
        )
        _write_byte(dest, ring["fwd"], fn)
        _write_byte(dest, ring["rev"], rn)
        af = _read_byte(dest, ring["fwd"])
        ar = _read_byte(dest, ring["rev"])
        if af != fn or ar != rn:
            return _fail("reread mismatch %s" % ring["name"])
        fired.append((ring["name"], ring["fwd"], fo, fn, ring["rev"], ro, rn))
    print("JOURNAL", journal_path)
    for name, fa, fo, fn, ra, ro, rn in fired:
        print("  %s fwd@%s %s->%s  rev@%s %s->%s" % (name, fa, fo, fn, ra, ro, rn))
    print("DIE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
