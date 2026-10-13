#!/usr/bin/env python3
"""host/muhl_post_render.py — SURFACE codebook only. bytes → (glyph, text_or_empty, hex).

THINKING = bits / collisions / mouths / 1-maps / electrons. Always.
WORDS = optional ASCII decode on the SURFACE of the answer space so Bryce can read mail.
Host puts bits into words for HIM only. Not Titan's inner alphabet. Not thinking.
Not GPT/Fable/json tabs. Not instruments. Not the compute path. Not pfc_harness English-thought.
Popcount / RAW still valid. Model never paraphrases. titan_thinks_in_ascii = NO.
No titan write. No numpy. Not a process.
"""
from __future__ import annotations

WORKING_LO = 128 - 32
WORKING_HI = 128 + 32
_ASCII_WS = frozenset((0x09, 0x0A, 0x0D))


def popcount(blob):
    n = 0
    for b in blob:
        n += bin(b).count("1")
    return n


def _printable_runs(blob, min_len=4):
    """ANY printable run length>=4. Bits spell words. Not all-or-nothing. Not thinking."""
    runs = []
    cur = []
    for b in blob:
        if (0x20 <= b <= 0x7E) or b in _ASCII_WS:
            cur.append(b)
        else:
            if len(cur) >= min_len:
                runs.append(bytes(cur).decode("ascii"))
            cur = []
    if len(cur) >= min_len:
        runs.append(bytes(cur).decode("ascii"))
    return runs


def render(blob):
    """bytes → (glyph, text_or_empty, hex). Surface mail only. Not thinking. No paraphrase."""
    blob = bytes(blob)
    hx = blob.hex()
    n = popcount(blob)
    if n == 0:
        return ("YES", "", hx)
    if n == 256:
        return ("NO", "", hx)
    if WORKING_LO <= n <= WORKING_HI:
        return ("WORKING", "", hx)
    runs = _printable_runs(blob)
    if runs:
        return ("WORDS", " ".join(runs), hx)
    return ("RAW", "", hx)
