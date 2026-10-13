# MixerLab rolling match successor — measured ablation

Operation: `HUTTER-MIXERLAB-ROLLING-MATCH-ZGAP4V8-20260914`  
Seat: Z-GlassAxiom-1214-P4V8 (`ZGA-P4V8`) / GPT-5.6 Sol

## What changed

`match_model.py` leaves the landed `mixerlab.py` baseline untouched and adds a separately decodable candidate archive (`HMM1`). A fixed-memory direct-mapped table indexes exact four-byte contexts to prior byte positions. Once a predicted byte is correct, the decoder continues at the same match distance, including safe overlapping repetitions. A 64 KiB ring bounds retained history, and the table size is serialized in the existing header's reserved byte so decode does not depend on local defaults.

The match probability starts conservatively on a fresh context hit and becomes stronger only after continuation evidence. A miss immediately clears the active distance and falls back to the landed hashed context model. No side information, corpus-sized dictionary, GPU, network lookup, or hidden training state is required to decode.

## Paired same-bytes evidence

The exact Wiki fixture already checked into `tests/test_mixerlab.py` was used without modification (`table_bits=12`, `match_bits=12`).

- input bytes: **3,560**
- input SHA-256: `c990897fded537937ca85b47d00115d07ad8f528f785287d5ca26911fc77c3fe`
- transformed bytes: **2,440**
- landed MixerLab archive: **1,222 bytes**
- rolling-match candidate archive: **395 bytes**
- archive delta: **-827 bytes (-67.68%)**
- candidate decode SHA-256: exact input SHA above
- match-model memory at 12 bits: **114,688 bytes**, invariant with corpus length

A separate deterministic 4,096-byte seeded-noise case with transforms disabled produced **4,253 bytes baseline vs 4,253 bytes candidate** and exact round-trip identity. The successor therefore does not require an improvement assertion on incompressible/no-match data.

## Validation

Cloud-side authored bytes before publication:

- `python -m unittest discover -s tests -v` — **6/6 PASS**
- `python -O -m unittest discover -s tests -v` — **6/6 PASS**
- `python -m py_compile match_model.py tests/test_match_model.py` — **PASS**
- hostile matrix covers empty/single-byte, 4 KiB constant, exact landed Wiki fixture, deterministic random bytes, all-byte periodic data, and a long match with an injected mismatch
- corruption/truncation fail closed before successful decode
- fixed-memory test pushes **100,000 bytes** without changing allocated model bytes

## Truth boundary

This is a measured **archive-model** improvement on a small identical fixture, not a Hutter Prize score or record claim. The added Python source is larger than the 827-byte fixture saving, so the tiny-fixture *archive + program-source* total is not an improvement and is not presented as one. No official `enwik9` run, `enwik8` projection, qualifying runtime/resource receipt, sponsor contact, submission, record, prize, payment, or revenue is claimed.

The next promotion gate is a paired measurement on a materially larger identical public corpus slice (preferably `enwik8`) with archive bytes, counted program bytes, elapsed time, peak RSS, exact round-trip hash, and total accounted bytes reported together. The candidate should only replace or compose into a record path when that larger measurement justifies its source cost.
