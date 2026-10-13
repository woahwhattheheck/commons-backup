# TITAN V3 paired-ledger custody gate

`titan_paired_ledger_gate.py` is the fail-closed front door for any V1/V2/V3
headline produced by `titan_regression_gate.py compare`.

## The two predecessor failures it closes

The incumbent comparator correctly keys rows by engine, environment seed,
opponent artifact, and candidate seat, but those keys alone do not prove which
candidate bytes produced a row.

1. A caller can copy completed rows from archive A into a ledger whose top-level
   `archive_sha256` names archive B. The incumbent comparator sees two archive
   labels and can report `COMPARABLE`; the rows themselves never attest B.
2. A caller can supply only seat 0 for every seed. If both ledgers omit seat 1 in
   the same way, the schedules are identical and can be reported `COMPARABLE`.
   That is exact intersection, but it is not a paired-seat panel.

The new gate requires every row to bind the candidate archive and requires the
exact seat set `{0, 1}` for every `engine × seed × opponent` matchup before it
calls the incumbent comparator.

## Ledger contract

```json
{
  "schema": "titan-paired-regression-ledger/v2",
  "archive_sha256": "<candidate archive; lowercase 64-hex>",
  "engine_sha256": "<pinned engine; lowercase 64-hex>",
  "games": 4,
  "schedule_sha256": "<digest of canonical schedule rows>",
  "rows": [
    {
      "candidate_archive_sha256": "<must equal top-level archive_sha256>",
      "environment_seed": 101,
      "opponent_sha256": "<opponent artifact; lowercase 64-hex>",
      "seat": 0,
      "margin": 1200,
      "status": "DONE"
    },
    {
      "candidate_archive_sha256": "<same candidate archive>",
      "environment_seed": 101,
      "opponent_sha256": "<same opponent artifact>",
      "seat": 1,
      "margin": -300,
      "status": "DONE"
    }
  ]
}
```

Additional hard boundaries:

- `games` must equal the exact row count;
- `schedule_sha256` must equal the canonical schedule digest;
- SHA-256 fields must be lowercase 64-hex values;
- seat must be exactly `0` or `1`;
- duplicate cells, incomplete/failed rows, booleans, NaN, and infinities fail;
- when margin and both terminal scores are supplied, they must agree exactly to
  floating-point tolerance;
- a row-level engine override cannot escape the ledger-level engine pin;
- left and right must use the identical complete schedule; there is no partial
  panel mode.

## Run

From `revenue/kaggriculture/cloud-execution-lab`:

```bash
python -B titan_paired_ledger_gate.py \
  --left v1-ledger.json \
  --right v3-ledger.json \
  --report-json v1-v3-paired-report.json

python -B -m unittest -v test_titan_paired_ledger_gate.py
```

A successful report retains the incumbent exact-cell delta output and adds:

- an explicit per-row candidate-custody certificate;
- schedule digest, cell count, matchup-pair count, and required seats;
- delta summaries by seat and by opponent artifact × seat.

Exit `0` means comparable. Exit `3` means both ledgers were valid but named the
same archive or different schedules. Exit `4` means ledger custody, lifecycle,
score evidence, or pair topology was malformed.

This tool is a measurement gate only. It does not run a game, mutate policy,
change canonical pointers, estimate leaderboard score, or authorize promotion.
