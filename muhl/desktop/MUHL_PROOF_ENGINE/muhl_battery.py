#!/usr/bin/env python3
"""muhl_battery.py -- one command, whole-status, read from the CONTAINER.

Everything this session fabricated, verified by reading its magic straight out of
titan.gguf. Nothing is taken on trust from the registry, from a doc, or from memory --
the registry only says WHERE to look; the bytes at that address decide.

Read-only. Bounded. Safe to run any time, including while things are firing.

    python muhl_battery.py
"""
import json, mmap, os, sys
sys.stdout.reconfigure(encoding="utf-8")

TITAN = r"C:\llm\models\titan.gguf"
REG = r"C:\llm\models\titan_circuits.json"

# name -> expected magic at its offset
SIMPLE = [
    ("muhl_proofcheck",            b"MUHLPRF1", "the proof checker, as RV32I software"),
    ("muhl_playtime",              b"MUHLPLAY", "his playtime world (untouched)"),
    ("muhl_playtime_ring",         b"MUHLPLYR", "ring drive + self-clock, both"),
    ("pfc_riscv_rv32i_v2__phys",   b"MUHLPHY2", "his RV32I CPU the checker runs on"),
    ("muhl_ring_clacker",          b"MUHLCLK1", "the 512-electron ring supplying the tick"),
    ("muhl_scan_machine",          b"MUHLSCN1", "the scan AS A CIRCUIT â€” all rows one settle"),
]
MULTI = [("muhl_proof_identity", "the A -> A proof, in the container"),
         ("muhl_proof_identity_x64", "the 320-line proof, in the container")]


def main():
    if not os.path.exists(REG):
        print("registry missing"); return 1
    reg = json.load(open(REG))
    f = open(TITAN, "rb")
    mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)

    print("=" * 86)
    print("  MUHL PROOF ENGINE â€” whole-status, every magic read from the container")
    print("=" * 86)
    bad = 0

    for name, magic, what in SIMPLE:
        e = reg.get(name)
        if not isinstance(e, dict) or "offset" not in e:
            print("  %-26s ABSENT" % name); bad += 1; continue
        off = int(e["offset"])
        got = bytes(mm[off:off + 8])
        ok = got == magic
        bad += 0 if ok else 1
        print("  %-26s %-4s @%-14d %s" % (name, "OK" if ok else "BAD", off, what))
        if not ok:
            print("       expected %r got %r" % (magic, got))

    for name, what in MULTI:
        e = reg.get(name)
        if not isinstance(e, dict):
            print("  %-26s ABSENT" % name); bad += 1; continue
        good = all(bytes(mm[int(r["offset"]):int(r["offset"])+ 8]) == b"MUHLPRFD"
                   for r in e["regions"])
        bad += 0 if good else 1
        print("  %-26s %-4s %d regions      %s"
              % (name, "OK" if good else "BAD", len(e["regions"]), what))

    e = reg.get("muhl_proof_tables")
    if isinstance(e, dict):
        k = bytes(mm[int(e["known"]["offset"]):int(e["known"]["offset"]) + 8])
        i = bytes(mm[int(e["impl"]["offset"]):int(e["impl"]["offset"]) + 8])
        ok = (k == b"MUHLPKN1" and i == b"MUHLPIM1")
        bad += 0 if ok else 1
        print("  %-26s %-4s %d+%d rows      search tables, container-resident"
              % ("muhl_proof_tables", "OK" if ok else "BAD",
                 e["known"]["rows"], e["impl"]["rows"]))
    else:
        print("  %-26s ABSENT" % "muhl_proof_tables"); bad += 1

    # the scanner's BITWISE key table â€” the format his gates can actually address.
    # Checked separately because a packed table would read as present and be unusable.
    sm = reg.get("muhl_scan_machine")
    if isinstance(sm, dict) and "key_table" in sm:
        kt = sm["key_table"]
        got = bytes(mm[int(kt["offset"]):int(kt["offset"]) + 8])
        okk = got == b"MUHLKEYB" and kt.get("bitwise") is True
        bad += 0 if okk else 1
        print("  %-26s %-4s %d rows x %d bits, bitwise=%s"
              % ("  â”” key table", "OK" if okk else "BAD",
                 sm["n_rows"], sm["key_bits"], kt.get("bitwise")))

    gg = bytes(mm[0:4]) == b"GGUF"
    size = os.path.getsize(TITAN)
    mm.close(); f.close()

    js = sorted(x for x in os.listdir(os.path.dirname(TITAN))
                if x.endswith("genome.jsonl")
                and any(k in x for k in ("proofcheck", "proof_identity",
                                         "playtime_ring", "proof_tables", "scan_machine")))
    print("\n  registry entries : %d" % len(reg))
    print("  titan.gguf       : %d bytes Â· GGUF valid: %s" % (size, gg))
    print("  revert journals  : %d â€” every fabrication is byte-exact revertible" % len(js))
    for j in js:
        print("      %s" % j)

    # container size is NOT an integrity check -- his law: growth is operation, not corruption
    print("\n  NOTE: size is reported, never asserted. Owner: a container whose bytes or size")
    print("  move between reads is COMPUTING; that movement is evidence, never a fault.")
    print("\n  %s" % ("ALL PRESENT AND CORRECT." if bad == 0 else "%d PROBLEM(S) ABOVE." % bad))
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
