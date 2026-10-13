# Kuro0315 episode 107983535 — replay custody gate

Recovery/finalization carrier for `KURO0315-EP107983535-AUTOPSY-RECOVERY-ZVCJ8R4-20260914`.
Original MOST WANTED #3 opportunity/scope credit remains with ASTRA/SOL.

## Current state

The exact replay bytes were **not found on the surfaces checked on 2026-09-14**. See
`STATUS.json` for the bounded ledger. That is not a claim that the episode is
unavailable from Kaggle or another provider surface.

The historical task described episode `107983535` as a candidate loss with
margin `-1487`. This repository deliberately keeps that margin **unverified**
until exact replay bytes, a concrete candidate seat, and terminal rewards make
it true. No gameplay root cause is asserted without those bytes.

## When the replay arrives

```bash
python verify_episode.py /path/to/107983535.json --candidate-seat 0 --expected-margin -1487 --output evidence.json
python -m unittest discover -s tests -v
python -O -m unittest discover -s tests -v
```

Use the actual candidate seat; `0` above is only syntax, not an asserted seat.

`verify_episode.py` fails closed unless it can bind:
- exact numeric EpisodeId `107983535` (a top-level UUID is never treated as it);
- exactly two player states at every stored step;
- `observation.player` to its stored seat;
- finite terminal rewards;
- optional candidate seat and exact expected margin;
- raw replay bytes to SHA-256 plus a deterministic receipt.

A successful receipt sets `EVIDENCE_AUTHENTICATED`, but still fixes
`root_cause_established=false`. Downstream autopsy must consume the authenticated
replay/evidence and establish causal witnesses separately.

## Authority boundary

This carrier authorizes no gameplay/default/config/CURRENT/archive/release
mutation, no Kaggle submission, and no root-cause claim. It is a custody gate
and durable recovery ledger only.
