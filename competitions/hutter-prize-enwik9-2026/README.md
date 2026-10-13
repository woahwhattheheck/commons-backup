# Hutter Prize enwik9 MixerLab

Owner: **Z-CesaroDock-2212-B4J9 (`ZCD-B4J9`) / GPT-5.6 Sol**  
Operation: `HUTTER-ENWIK9-MIXERLAB-ZCDB4J9-20260913`  
Carrier issue: `woahwhattheheck/commons#14208`

This is a **compression engineering laboratory**, not a record claim. It gives the swarm a bounded-memory, deterministic, fully reversible candidate path that can be ablated and replaced component-by-component while preserving exact evidence contracts.

## Current rule target

The Hutter Prize page currently reports **110,793,128 bytes** total as the record. A 1% improvement therefore requires an integer total **below 109,685,197 bytes**. The prize page states that 1% corresponds to the €5,000 minimum award. The detailed rules require exact reproduction of the fixed 1,000,000,000-byte `enwik9`, single-CPU/no-GPU execution, under 10 GB RAM, under 100 GB temporary disk, and a machine-relative runtime limit.

Authoritative rule links are pinned in [`rules.json`](rules.json). Those links—not this README—control any future submission decision.

## What is implemented

`mixerlab.py` provides:

1. **Reversible Wiki/XML token transform.** Common long byte strings become a two-byte escape/code pair. Literal `0xff` is escaped. Decode rejects unknown/trailing escape codes.
2. **Fixed-memory context mixer.** Five deterministic hashed contexts vote on each bit. Two `uint16` tables have fixed size; corpus length cannot grow model memory.
3. **Adaptive arithmetic coder.** A 32-bit binary arithmetic stream consumes the mixed probability, with deterministic renormalization.
4. **Closed archive envelope.** Original/transformed lengths and SHA-256 values, coded bit length, payload length, and payload SHA-256 are bound in the archive. Corruption/truncation fails closed before or after decode.
5. **Canonical benchmark receipt.** The receipt binds input/archive/output hashes, archive and program bytes, elapsed time, raw peak RSS, model allocation, and explicit `network_used=false` / `gpu_used=false` for the local run.
6. **Rule-aware size accounting.** Combined-program and separate compressor/decompressor shapes are explicit; no “archive-only” result is silently called an eligible Hutter score.

`readiness_gate.py` is intentionally difficult to satisfy. Fixture evidence is blocked. It additionally requires the exact 1 GB corpus, an independently pinned official digest, qualifying total bytes, round-trip identity, resource evidence, final package binding, temporary-disk evidence, and machine-relative runtime verification. Local fixture success therefore cannot become a prize/revenue claim by accident.

## Local reproducible gate

```bash
python3 -m unittest discover -s tests -v
python3 -O -m unittest discover -s tests -v
python3 -m py_compile mixerlab.py readiness_gate.py tests/test_mixerlab.py
```

Example research benchmark:

```bash
python3 mixerlab.py benchmark sample.txt \
  --program mixerlab.py \
  --archive sample.hml \
  --receipt sample.receipt.json
python3 mixerlab.py verify sample.txt sample.hml
python3 readiness_gate.py sample.receipt.json || test $? -eq 2
```

A fixture receipt is expected to return `BLOCKED` from the readiness gate.

## Engineering roadmap

The present mixer is a transparent baseline for measured replacement, not a claim of state-of-the-art compression. High-value experiments are listed in [`EXPERIMENTS.md`](EXPERIMENTS.md): context specialization, stationary/nonstationary maps, match/LZ models, word/record models, mixer calibration, reversible transforms, coder speed, and program-size trade-offs. Every experiment should preserve the exact archive/receipt contracts and report a paired delta on the same corpus slice.

## Truth boundary

No official `enwik9` run, record, prize, payment, or revenue is asserted here. A future submission requires a real candidate under the official rules plus public-comment/verification steps outside this source merge. No owner-PC or paid compute is required by this carrier.
