# Additive top-30 opponent intake

The September 12, 2026 18:22:49 UTC official leaderboard snapshot and the earlier
09:54 UTC public-submission snapshot identify 41 distinct submission targets:
30 current, 30 previous, with 11 newly added versions. The full download contains
three recent completed public games per target: 123 opponent fixtures from 105
distinct 720-state episodes. Versions are keyed by submission ID, not team name.
The latest three completed games are selected without filtering for wins.

Direct public opponent executable download was unavailable (official endpoint
returned HTTP 403). These additions are **recorded-action opponents**, which do
not react to a changed farm or market. Existing executable policies, synthetic
profiles, old recorded opponents and mirror remain part of the original gauntlet.
Keep their original provenance. This intake does not imply 41 independently
available adaptive executables or establish a Kaggle rating.

V4 source and improvements remain preserved. V3.1 is a comparison control.
**V5 Kaggle submission is on hold until Bryce explicitly releases it.**

## Install and extend the existing gauntlet

Extract the shared corpus archive. It contains `manifest.json`, official source
metadata and `replays/`. Keep the existing gauntlet output and source directories.

```bash
python -B corpus.py --corpus /path/to/corpus --out /path/to/new-runtime \
  --legacy-registry /path/to/existing-gauntlet-registry.json
```

The legacy registry must have an `opponents` array with unique `id` fields.
`extended-gauntlet.json` retains all legacy rows, fields and order, and appends
the new fixtures. Colliding IDs raise an error; nothing is overwritten. A legacy
registry that already owns the reserved `additive_intake` field is rejected
rather than silently overwritten.

The materializer now hard-pins this corpus closure to 41 unique submission IDs
and 123 fixtures (three per submission), authenticates every replay digest, and
stamps every generated trace with `provenance=public_recorded_actions`,
`adaptive=false`, and `executable=false`. When `--legacy-registry` is supplied it
also emits `GAUNTLET-UNION-RECEIPT.json`, binding the legacy file SHA256 and source
manifest SHA256 while re-checking the exact legacy prefix and untouched top-level
fields. A receipt PASS establishes additive/provenance closure only; recorded
traces remain non-responsive diagnostic opponents.

Re-run materialization on each VM because entry paths are local to that VM.

The preserved published old-family table records 30 ranked slots plus mirror;
rank17's name and actual VM entry were absent from that published table. That
metadata is retained, with the real runtime-manifest export assigned to the
existing owner. The published family table is not a replacement runtime manifest.

## Execute a bounded native shard

```bash
python -B run.py --kg-root /path/to/revenue/kaggriculture \
  --engine-dir /path/to/pinned-engine \
  --index /path/to/new-runtime/recorded-opponents.json \
  --candidate /path/to/exact-candidate.tar.gz --candidate-sha256 SHA256 \
  --output /path/to/new-result-directory --group all --shard 0 --shards 4
```

The default uses each fixture's original seed and opponent seat. `--both-seats`
adds a labeled synthetic seat-swapped stress case. `--limit 2` is a small import
screen. Run the same shard for exact V4, exact V3.1 and a repaired candidate;
compare matching submission/episode/seat rows. Retain the original gauntlet
jobs alongside these additions. Numerical receipts belong in `#sim-data`.

The launcher uses the existing Commons evaluator, pack adapter and pinned engine;
each game gets fresh persistent policy processes. It contains no submission API.
Eight focused importer tests cover replay offset/seat identity, legacy and mirror
preservation, collision rejection, reserved-field safety, explicit non-executable
provenance, and receipt mutation/count closure. Materialization checks every real
fixture.
