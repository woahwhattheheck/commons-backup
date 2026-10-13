#!/usr/bin/env python3
# host/muhl_lang_u16_fit.py
# Routing button: encode AGENT LANG verb codes with SPM dest FROM FILE,
# report which ids fit the published 16-bit A mouth, then die.
# Does not invent dest. Does not write titan. Does not fire.
#   python host/muhl_lang_u16_fit.py
# Never --inject 0x01.

from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import muhl_address_agent as addr

if "--inject" in sys.argv:
    print("REFUSE: --inject 0x01 is WIPE")
    raise SystemExit(2)

# AgentLanguage.kt VERB_TO_CODE values (this tree).
CODES = (
    "cl", "st", "cr", "fd", "rv", "pk", "zm", "zo", "np", "pp",
    "sc", "sw", "xy", "am", "tg", "tn", "tq", "lp", "dw", "sk",
    "en", "sd", "rp", "ad", "oa", "bk", "hm", "ra", "nf", "qs",
    "sp", "se", "cp", "ps", "rc", "ct", "oc", "gt", "at", "ar",
    "sn", "sv", "cd", "wt", "ak", "dn", "do", "hp", "dl", "sm",
    "sa", "nv", "wb", "bt", "dg",
)
SAMPLES = ("cl5", "st5:hi", "bk", "hm", "oa", "ak", "cl")
U16 = 65535


def main():
    path = addr.installed_litert()
    if not os.path.isfile(path):
        print("NEED — AGENT .litertlm")
        return 1
    vocab, pieces, maxtok = addr.load_vocab(path)
    fit = over = 0
    over_rows = []
    for c in CODES:
        ids = addr.encode(c, vocab, maxtok, add_bos=True)
        hi = [i for i in ids if i > U16]
        if hi:
            over += 1
            over_rows.append((c, ids, hi))
        else:
            fit += 1
    n_over_v = sum(1 for i in range(len(pieces)) if i > U16)
    print("AGENT SPM dest FROM FILE pieces=%d" % len(pieces))
    print("LANG codes n=%d FIT_u16=%d OVER_u16=%d" % (len(CODES), fit, over))
    print("vocab_ids>u16 %d/%d frac=%.4f" % (n_over_v, len(pieces), n_over_v / len(pieces)))
    print("OVER codes", [(c, ids) for c, ids, _ in over_rows])
    print("---samples---")
    for s in SAMPLES:
        ids = addr.encode(s, vocab, maxtok, add_bos=True)
        print("sample", s, "ids", ids, "over", [i for i in ids if i > U16])
    print("GAP — pin mouth A is u16. Digit pieces (cl5) overflow even when bare cl fits.")
    print("NO WRITE")
    print("NO FIRE")
    print("DIE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
