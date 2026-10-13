# External opportunity intake freshness + expiry ledger

A deterministic, read-only compiler for retained evidence about external bounties, offers, competitions, paid discovery, and partnership opportunities.

`READY_FOR_INTERNAL_ROUTING` means **internal routing only**. Every emitted record hard-codes false authority for external contact/application/acceptance, Muse election/consume, competition entry, contracts, provider/account mutation, spend, funds movement, and cash/revenue recognition.

## Input contract

The compiler accepts strict JSON only. It rejects duplicate keys, floats/nonfinite numbers, bool-as-int aliases, unsafe integers, lone surrogates/control-shaped identifiers, unknown fields, cross-opportunity evidence transplants, impossible chronology, duplicate semantic actions, and malformed source generations.

Top-level fields:

- `opportunity_id`, `opportunity_class`, `active_source_generation`
- retained descriptive evidence: `title`, `counterparty`, `scope`, `opportunity_url`
- `sources`: immutable refs/digests, generations, observed/published UTC, optional externally stated deadline, explicit supersession
- `compensation`: fixed minor units, non-fixed retained terms, or explicit `UNKNOWN`
- `acceptance_route`: retained route evidence or `null`
- owner `policy`: permitted classes, max source age, candidate holder ID
- `custody`, `actions`, and DNR/relationship `blockers`

States are exactly those in Commons issue #15708. An external deadline is valid through its exact timestamp and expires immediately after it. Without a deadline, `policy.max_source_age_seconds` bounds freshness. Future evidence always fails closed. A historical replay can verify integrity but can never emit current `READY_FOR_INTERNAL_ROUTING`.

## CLI

```bash
python -m revenue.external_opportunity_intake.cli compile-current input.json out-dir
python -m revenue.external_opportunity_intake.cli compile-historical input.json replay-dir --at 2026-09-19T20:00:00Z
python -m revenue.external_opportunity_intake.cli verify out-dir/record.json
```

Output directories are create-exclusive. A bundle contains canonical `record.json`, deterministic `routing.md`, and `manifest.json` with byte hashes plus the semantic receipt.

## Proof

```bash
python -m revenue.external_opportunity_intake.selftest
python -O -m revenue.external_opportunity_intake.selftest
python -m py_compile revenue/external_opportunity_intake/*.py
```

The dedicated GitHub Actions workflow runs the same proof commands for changes to this package.
