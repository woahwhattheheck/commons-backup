# Revenue underwriter

`underwriter.py` is a deterministic, offline decision gate for funded work that has
already passed discovery. It exists because an advertised reward is not evidence
that a task is still open, pays out in practice, or is worth competing for.

The tool intentionally keeps four concepts separate:

1. **advertised amount** — what the listing says is available;
2. **canonical freshness** — whether the authoritative work item is actionable now;
3. **realized payout evidence** — dated, source-bound observations of money actually awarded;
4. **planning range** — a conservative allocation range used to rank worker time.

The planning range is **not** a probability, forecast, invoice, booking, acceptance,
or payment claim. The tool has no network code and never contacts a sponsor, claims
a bounty, submits work, spends money, or mutates a payment provider.

## Input

See `schema.input.json` and `examples/repeated-payer.json`. Required evidence is:

- one canonical candidate URL, currency, and advertised amount;
- one native `tools/funded_work_freshness` receipt; its SHA-256 is recomputed and its
  canonical URL, amount, currency, state, and competition counts are bound to the candidate;
- one or more payout-history snapshots with source URL/class, timestamp, paid total,
  award/completion counts, and open pool.

For repeated snapshots from the same source, paid/award/completion totals must be
monotonic. Simultaneous observations of a single normalized source URL must agree on
source class, paid amount, award/completion counts, and open pool. Distinct
marketplace or sponsor URLs have independent histories, even if sampled at the
same instant. This avoids false multi-platform conflicts while detecting
contradictory statements from the same source. Currency must match across all evidence. Evidence
older than the configured history window fails closed.

## Decision rules

Hard failures produce `reject`: non-actionable/closed canonical work, stale/future
evidence, contradictory payout histories, currency mismatches, or a zero-paid pool
with at least the configured competition count (default 3).

Otherwise the tool assigns an explicit **planning multiplier band** from realized
payout history and divides it by `1 + visible_claims + active_competing_prs`. That
denominator is an equal-share planning assumption, not an inferred win probability.
A candidate is `pursue` only when the conservative lower planning bound meets
`--min-pursue-cash` (default 100); other viable candidates are `watch`.

When multiple evidence sources mirror the same sponsor ledger, the receipt preserves
the latest observation from each source and uses maxima instead of summing totals, so
mirrored payout pages cannot double-count historical money.

## Usage

```bash
python3 underwriter.py examples/repeated-payer.json \
  --observed-at 2026-09-13T07:30:00Z
```

Exit codes: `0` pursue, `3` watch, `4` reject, `2` invalid input/runtime error.

To replay exactly, preserve the input packet and `--observed-at`. Receipts contain a
canonical input SHA-256 plus a receipt SHA-256.

## Tests

```bash
python3 -B -m unittest discover -v
python3 -O -B -m unittest discover -v
python3 -m py_compile underwriter.py tests/test_underwriter.py
```

All code uses the Python standard library only.
