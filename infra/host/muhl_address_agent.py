#!/usr/bin/env python3
# host/muhl_address_agent.py
# Address a prompt using AGENT's tokenizer dest FROM FILE, then die.
# Does not fire the receiver. Does not use llama BPE. Does not convert.
#   python host/muhl_address_agent.py "hello"
# Never --inject 0x01.

from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import muhl_dump_litertlm as dump

if "--inject" in sys.argv:
    print("REFUSE: --inject 0x01 is WIPE")
    raise SystemExit(2)

REG = r"C:\llm\models\titan_circuits.json"
LITERT = r"C:\Users\lucys\Desktop\MUHL_GEMMA_E4B\gemma-4-E4B-it.litertlm"
SPM_BEGIN = 32768
SPM_SIZE = 4689013


def installed_litert():
    if os.path.isfile(REG):
        import json
        inst = json.load(open(REG, encoding="utf-8")).get("pfc_installed_model") or {}
        p = inst.get("model_path") or inst.get("model_path") or ""
        if p and os.path.isfile(p):
            return p
    return LITERT
MARK = "\u2581"
BOS, EOS, UNK = 2, 1, 3


def load_vocab(path):
    with open(path, "rb") as f:
        f.seek(SPM_BEGIN)
        blob = f.read(SPM_SIZE)
    i = 0
    end = len(blob)
    vocab = {}
    pieces = []
    n = 0
    while i < end:
        tag = blob[i]
        i += 1
        fid = tag >> 3
        wt = tag & 7
        if fid == 1 and wt == 2:
            nlen, i = dump.read_varint(blob, i, end)
            inner_end = i + nlen
            piece = None
            j = i
            while j < inner_end:
                t2 = blob[j]
                j += 1
                f2 = t2 >> 3
                w2 = t2 & 7
                if f2 == 1 and w2 == 2:
                    slen, j = dump.read_varint(blob, j, inner_end)
                    piece = blob[j : j + slen].decode("utf-8", "replace")
                    j += slen
                else:
                    j = dump.skip_field(blob, j, w2, inner_end)
            if piece is None:
                print("REFUSE — piece %d missing string" % n)
                raise SystemExit(2)
            vocab[piece] = n
            pieces.append(piece)
            n += 1
            i = inner_end
            continue
        break
    if n != 262144:
        print("REFUSE — expected 262144 pieces, got %d" % n)
        raise SystemExit(2)
    maxtok = max(len(p) for p in pieces)
    return vocab, pieces, maxtok


def encode(text, vocab, maxtok, add_bos=True):
    ids = [BOS] if add_bos else []
    s = MARK + (text or "").replace(" ", MARK)
    i = 0
    while i < len(s):
        hit = None
        L = min(maxtok, len(s) - i)
        while L > 0:
            j = vocab.get(s[i : i + L])
            if j is not None:
                hit = j
                i += L
                break
            L -= 1
        if hit is None:
            for b in s[i].encode("utf-8"):
                k = vocab.get("<0x%02X>" % b)
                ids.append(k if k is not None else UNK)
            i += 1
        else:
            ids.append(hit)
    return ids


def main():
    path = installed_litert()
    if not os.path.isfile(path):
        print("NEED — AGENT .litertlm")
        return 1
    prompt = "hello"
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if args:
        prompt = args[0]
    vocab, pieces, maxtok = load_vocab(path)
    ids = encode(prompt, vocab, maxtok, add_bos=True)
    print("AGENT tokenizer dest FROM FILE spm@%d size=%d pieces=%d" % (SPM_BEGIN, SPM_SIZE, len(pieces)))
    print("prompt %r" % prompt)
    print("ids %s" % ids)
    print("pieces %s" % [pieces[i] if 0 <= i < len(pieces) else "?" for i in ids])
    if prompt == "hello" and ids == [BOS, vocab[MARK + "hello"]]:
        print("CANARY MATCH bos=%d ▁hello=%d" % (BOS, vocab[MARK + "hello"]))
    print("NO FIRE")
    print("DIE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
