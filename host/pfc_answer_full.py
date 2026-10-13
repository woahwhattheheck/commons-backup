#!/usr/bin/env python3
"""host/pfc_answer_full.py — prefabricate the FULL-ANSWER write-out for the Bitcoin Muhlnickel (owner 07-19).

The owner's fix: "instead of it writing one or zero there, prefabricate the capacity and — a logical extension of that —
have it write the FULL answer." Today the win path emits a single bit (`win = hash < target`) and a 4-byte nonce only on a
win. This adds:
  1) `full_answer` — a widened answer register ([status:1][en2/group:4][nonce:4] = 9 bytes) with CAPACITY for the whole
     submittable answer, prefabricated reversibly (the genome journals every overwritten byte range -> byte-exact revert).
  2) `answer_writeout` — a gate circuit that is the logical extension of the 1-bit win: given the pfc's (nonce, group, win)
     it emits the FULL answer bits [nonce:32 | group:32 | status:1]. Byte-exact-verified before storing.

Fabrication ONLY — the White Box circuit tool. No executor, no runtime here. The pfc deposits the full answer when the
signal runs it; the autopilot reads that answer from the safezone and submits it.

  python host/pfc_answer_full.py          # fabricate full_answer + answer_writeout (reversible, verified)
  python host/pfc_answer_full.py revert    # restore titan.gguf byte-exact
"""
import json, os, random, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as TC

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
GENOME = "C:/llm/models/titan_pfc_answer_genome.jsonl"
FULL_ANSWER_BYTES = 9                                    # [status:1][en2/group:4 LE][nonce:4 LE]


def build_answer_writeout():
    """logical extension of the 1-bit win: (nonce:32, group:32, win:1) -> full answer bits [nonce:32 | group:32 | status:1].
    The write-out that formats the Muhlnickel's real result for the safezone — status carries the win, nonce+group pass through."""
    c = TC.Circuit(65)
    nonce = c.IN[0:32]; group = c.IN[32:64]; win = c.IN[64]
    status = c.or_(win, c.C0)                             # status bit = win (buffered through a gate)
    return c, list(nonce) + list(group) + [status]


def _verify(c, outs):
    cd = {"n_in": c.n_in, "n_wire": c.n_wire(), "ga": c.ga, "gb": c.gb, "outs": outs}
    random.seed(7)
    for _ in range(600):
        n = random.getrandbits(32); g = random.getrandbits(32); w = random.getrandbits(1)
        inb = [(n >> i) & 1 for i in range(32)] + [(g >> i) & 1 for i in range(32)] + [w]
        got = TC.ripple(cd, inb)
        want = [(n >> i) & 1 for i in range(32)] + [(g >> i) & 1 for i in range(32)] + [w]
        if got != want:
            return False, (n, g, w)
    return True, None


def backup_and_write(off, blob):
    with open(TITAN, "rb") as f:
        f.seek(off); original = f.read(len(blob))
    with open(GENOME, "a") as g:
        g.write(json.dumps({"off": off, "orig": original.hex()}) + "\n")
    with open(TITAN, "r+b") as f:
        f.seek(off); f.write(blob)


def revert():
    if not os.path.exists(GENOME):
        print("no answer genome — nothing to revert."); return 0
    lines = [json.loads(l) for l in open(GENOME) if l.strip()]
    for e in reversed(lines):
        with open(TITAN, "r+b") as f:
            f.seek(int(e["off"])); f.write(bytes.fromhex(e["orig"]))
    os.remove(GENOME)
    reg = json.load(open(REG))
    for k in ("full_answer", "answer_writeout"): reg.pop(k, None)
    json.dump(reg, open(REG, "w"), indent=1)
    print(f"reverted {len(lines)} edits — titan.gguf restored byte-exact; full_answer/answer_writeout removed.")
    return 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "revert":
        return revert()
    reg = json.load(open(REG))
    if "full_answer" in reg and "answer_writeout" in reg:
        print("full-answer write-out already fabricated. revert first to redo."); return 0
    if "win_cmp" not in reg:
        print("win_cmp absent — fabricate the mining Muhlnickel first (sdc_fab_big.py)."); return 1

    # 1) prefabricate the widened answer register (capacity for the full submittable answer)
    print("prefabricating full_answer register (9 bytes: status + en2/group + nonce) …", flush=True)
    aoff, atn = TC._alloc(FULL_ANSWER_BYTES, reg)
    backup_and_write(aoff, b"\x00" * FULL_ANSWER_BYTES)
    reg["full_answer"] = {"tensor": atn, "offset": aoff, "len": FULL_ANSWER_BYTES,
                          "layout": "status:1|en2:4LE|nonce:4LE"}
    json.dump(reg, open(REG, "w"), indent=1)

    # 2) fabricate the full-answer write-out circuit (logical extension of the 1-bit win), verified byte-exact
    print("fabricating answer_writeout (the full-answer write-out, logical extension of win) as gates …", flush=True)
    c, outs = build_answer_writeout()
    ok, bad = _verify(c, outs)
    if not ok:
        print(f"  MISMATCH {bad} — storing nothing (no cheating)."); return 1
    print(f"  byte-exact over 600 cases ({len(c.ga)} gates): full answer = nonce | group | status", flush=True)
    blob = TC.serialize(c, outs)
    reg = json.load(open(REG)); coff, ctn = TC._alloc(len(blob), reg)
    backup_and_write(coff, blob)
    reg["answer_writeout"] = {"tensor": ctn, "offset": coff, "len": len(blob), "n_in": c.n_in, "n_out": len(outs),
                              "n_gate": len(c.ga)}
    json.dump(reg, open(REG, "w"), indent=1)

    with open(TITAN, "rb") as f: gg = f.read(4) == b"GGUF"
    print(f"\nFABRICATED (reversible): full_answer @ {aoff} ({FULL_ANSWER_BYTES} B) + answer_writeout @ {coff} "
          f"({len(c.ga)} gates). titan GGUF-valid: {gg}.", flush=True)
    print("revert byte-exact:  python host/pfc_answer_full.py revert", flush=True)
    print("=> the safezone answer is now the FULL answer (nonce+group+status); the autopilot reads + submits it.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
