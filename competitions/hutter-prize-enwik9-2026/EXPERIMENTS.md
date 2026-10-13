# MixerLab experiment queue

The objective is not to decorate the baseline; it is to lower **accounted total bytes** while staying inside Hutter execution limits. Every experiment should use paired measurements on identical input bytes and keep round-trip verification mandatory.

## Priority A — model quality per byte of program

1. **Match model:** fixed-size rolling hash from 4–8 recent bytes to prior position + bounded match length. Feed match-bit probabilities into the mixer without unbounded dictionaries.
2. **Stationary maps:** split sparse XML punctuation contexts from natural-language contexts so a single collided count table is not forced to model both regimes.
3. **Word model:** rolling lowercase word hash, word-position bit, and previous-word hash. Measure English prose gain versus source-size cost.
4. **Record/XML state:** derive a tiny parser state from `<page>`, `<title>`, `<text>`, revision metadata, and entity syntax. It must be recoverable solely from decoded history.
5. **Mixer calibration:** replace integer probability averaging with fixed-point logit weights trained online; bound all weights and specify saturation/renormalization.

## Priority B — transforms

6. **Dictionary selection by measured net gain:** current static token transform is transparent but not optimized. Rank candidate tokens by `(raw_bytes - escaped_bytes) * count - source_cost` on `enwik8`; freeze a dictionary before evaluating `enwik9`.
7. **Case/punctuation transforms:** test reversible word-case separation and punctuation streams. Reject any transform whose inverse needs side information not counted in the archive.
8. **Numeric/date fields:** test reversible delta transforms for repeated revision IDs/timestamps only if parser state is unambiguous.

## Priority C — coder and runtime

9. **Range coder:** compare a byte-oriented carry-safe range coder with the current bit arithmetic implementation; measure archive delta and throughput.
10. **Table layout:** benchmark 2^16 through 2^20 slots for compression/RSS/speed Pareto frontier.
11. **Block parallelism is out by default:** official rules are single CPU; any threading experiment must remain disabled in the candidate path unless rules explicitly permit it.

## Required receipt for every claimed improvement

Record: input SHA-256 + bytes, baseline archive/program/total, candidate archive/program/total, exact round-trip hash, elapsed time, peak RSS, table sizes, transform flags, source commit/blob hashes, and whether the corpus is fixture/enwik8/enwik9. Never compare different byte slices.
