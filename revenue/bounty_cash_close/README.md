# Bounty Cash Close Board

Issue: #13975  
Original product/source owner: `Z-LaplaceHarbor-913948-X7K4` (`ZLH-X7K4`)  
Stale recovery/finalization: `Z-TantalumWharf-2026-B4K9` (`ZTW-B4K9`)

This package closes the gap between **engineering work that happened** and **cash that actually settled**. It compiles source-bound bounty identity, advertised-value evidence, and an append-only receipt chain into one conservative close state plus one bounded next action.

The board is intentionally skeptical. A merged PR is not money. A sent payout email is not money. A payment link is not money. A sponsor saying “paid” is strong payout evidence but still does not become `SETTLED` until an independent processor, wallet, bank, or ledger observation follows it.

## Authority ceiling

Every artifact keeps all of these false:

- `external_contact_authorized`
- `submission_authorized`
- `invoice_or_payment_mutation_authorized`
- `revenue_recognition_authorized`

The code has no network/provider integration. It never submits bounty work, contacts maintainers, asks for compensation, creates invoices, changes payment rails, moves cash, or recognizes revenue. Actions such as `ASK_COMPENSATION` are owner-review recommendations only.

## Input model

Input schema: `bounty-cash-close-input/v1`.

Each bounty has a canonical SHA-256 identity over:

- sponsor/program ref;
- bounty ref;
- claimant ref;
- source revision;
- exact work fingerprint SHA-256.

Advertised value is either:

- `FIXED`: positive integer minor units + uppercase three-letter currency + source/evidence binding; or
- `UNPRICED`: explicit source/evidence binding.

No value is inferred from a merged PR, issue title, local expectation, or payout request.

## Receipt chain

Every observation is content-addressed. Its receipt SHA-256 covers:

- stable event ID and kind;
- canonical whole-second UTC observation time;
- provider class and provider ref;
- opaque external ref;
- evidence digest;
- previous receipt digest.

The compiler reconstructs the chain independent of input ordering and rejects forks, missing parents, disconnected chains, duplicate semantic milestones, non-monotonic time, changed receipt bytes, unsafe types, and invalid provider authority.

Important semantics:

- `SUBMISSION_ATTEMPT_FAILED` never means delivered.
- `SUBMISSION_DELIVERED` is required before `TECHNICAL_ACCEPTED`.
- `TECHNICAL_ACCEPTED` is not payment.
- `PAYOUT_ACKNOWLEDGED` must be sponsor-observed and is not settlement.
- `SETTLEMENT_OBSERVED` must occur later and come from `PROCESSOR`, `WALLET`, `BANK`, or `LEDGER`.
- `PAYMENT_LINK_CREATED` never settles anything.

## Bounded close actions

The board emits exactly one of:

- `SUBMIT`
- `UNBLOCK_EXTERNAL_GATE`
- `ASK_COMPENSATION`
- `FOLLOW_UP_COMPENSATION`
- `RECONCILE_SETTLEMENT`
- `WAIT_DNR`
- `CLOSE_SETTLED`

Policy supplies review and compensation follow-up windows. Each lane permits at most one recorded follow-up. Once that follow-up exists, the board returns `WAIT_DNR` rather than generating an outreach loop.

Those windows and the one-follow-up limit apply both before and after a
delivered receipt exists. A `GATE_CLEARED` observation after a failed send
clears that transport blocker; without a delivered receipt the next action is
still the send lane, never a claim that delivery happened. A later blocked
hold or failed attempt reopens the blocker, while an already-used follow-up
stays spent.

## CLI

Production `compile` owns current process UTC; callers do not supply an `--as-of` value.

```bash
python -m revenue.bounty_cash_close compile input.json --output-dir /tmp/bounty-close
python -m revenue.bounty_cash_close verify input.json --output-dir /tmp/bounty-close
```

Outputs are create-exclusive:

- `board.json`
- `board.md`
- `receipt.json`

Input JSON uses bounded retained-descriptor regular-file reads, refuses final-component symlinks where the platform exposes `O_NOFOLLOW`, rejects duplicate keys and non-finite constants, and fingerprints mode/device/inode/size/mtime/ctime before and after the read.

`verify` proves historical bundle integrity by recompiling from the exact normalized input and the receipt's bound evaluation instant. It does not convert a historical recommendation into current send/payment authority.

## Validation

```bash
python -m py_compile revenue/bounty_cash_close/*.py test_bounty_cash_close.py
python -m unittest -v test_bounty_cash_close
python -O -m unittest -v test_bounty_cash_close
```

The hostile suite covers failed GitHub-style transport, delivered fallback, merge-vs-payment separation, sponsor-paid-vs-settlement separation, independent rail settlement, payment-link non-authority, bounded gate/compensation follow-up, chain tamper/forks/reordering, canonical identity dedupe, malformed types/times/provider classes, output tamper, duplicate JSON keys, symlink ingress, and create-exclusive output refusal.
