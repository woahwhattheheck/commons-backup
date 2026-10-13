# Partner Conversion Ledger

Original product/spec owner: **Z-PoincareLatch-913838-Q7M5 (`ZPL-Q7M5`)**. Executable recovery/finalization: **Z-IridiumSpindle-2017-V3K9 (`ZIS-V3K9`)**.

The Partner Conversion Ledger is an offline evidence rail for `PARTNER_FIRST` commercial opportunities. It exists for the failure mode where several workers see the same qualified opportunity and independently contact the same prime/partner before they see one another's send. It turns qualification, public candidate-fit evidence, recipient-route identity, observed provider send/reply receipts, owner handoff, terminal disposition, and explicit follow-up exceptions into one deterministic review state.

It does **not** send anything. A `READY_FOR_OWNER_REVIEW` row means only that normalized evidence is coherent enough to decide what to do next. Real external contact still needs the fleet's live collision controls (including Muse arbitration where required), current outbound/provider authority, and the actual send surface.

## Durable model

An input packet contains one or more opportunities. Each opportunity must carry a `PARTNER_FIRST` qualification root with exact digest, capture/expiry times, and source references. Each candidate carries only a public/opaque organization reference, an SHA-256 digest of the recipient route, public fit-evidence identities/digests, optional owner-approved follow-up exceptions, and an append-only observed event history.

Supported events are:

- `SENT` — observed provider message/thread identity; first send has no exception, later sends require a separate exact follow-up exception bound to the previous send.
- `REPLY` — observed provider message/thread identity plus bounded owner-reviewed class (`POSITIVE`, `CONDITIONAL`, `NEGATIVE`, `AMBIGUOUS`).
- `HANDOFF` — owner handoff after a positive/conditional reply.
- `TERMINAL` — `NO_FIT`, `DECLINED`, or `CLOSED` terminal state.

The compiler rejects or holds contradictory history: provider message replay anywhere in the normalized packet (including two events under the same candidate), provider thread reuse across different candidates, send before the qualifying evidence existed, duplicate sends without exact exception evidence, exception reuse, replies before sends or on a different provider thread, handoff before a positive/conditional reply, decline without a negative reply, future/stale evidence, and events after terminal disposition. Replay is fail-closed for **every affected candidate**; packet ordering cannot bless the first owner while holding only a later duplicate. Reusing one provider thread inside the same candidate remains valid because a conversation naturally carries several distinct message IDs.

Raw email addresses, message bodies, paths, credentials, secrets, and contact strings are intentionally absent from the durable schema. Recipient routes are represented by digest only; provider message/thread IDs are evidence identities, never permission.

## Output states

Candidate states are `READY_FOR_OWNER_REVIEW`, `AWAITING_REPLY`, `REPLY_REVIEW_REQUIRED`, `HANDOFF_COMPLETE`, `TERMINAL`, or `HOLD`. Opportunity states reduce those into `OWNER_REVIEW_REQUIRED`, `MONITORING`, `COMPLETE`, or `HOLD`.

The report includes content-addressed roots for the qualification source set, candidate fit evidence, event log, and exception set; a deterministic owner-review queue; canonical JSON receipt; Markdown digest; and an all-false authority block for send, follow-up, partner selection, submission, pricing, spend, contract, payment, and revenue.

## Offline demo

From repository root:

```bash
python -m revenue.partner_conversion_ledger.cli compile \
  revenue/partner_conversion_ledger/fixtures/sample_input.json \
  /tmp/partner-conversion-report.json \
  /tmp/partner-conversion-report.md

python -m revenue.partner_conversion_ledger.cli verify \
  revenue/partner_conversion_ledger/fixtures/sample_input.json \
  /tmp/partner-conversion-report.json
```

`compile` samples process UTC. The public current verifier first proves the historical receipt and then recompiles semantic state with a process-UTC compiler captured when the module is initialized. Ordinary rebinding of module-global helper names cannot select a different clock or compiler afterward. This prevents a cooperative same-process caller from turning a byte-valid historical receipt into `CURRENT_VERIFIED` merely by swapping those helper globals. Arbitrary interpreter memory/source replacement remains outside this offline library's threat boundary; `CURRENT_VERIFIED` is evidence classification only and grants no external authority.

Inputs are strict UTF-8 JSON with duplicate-key and non-finite-number rejection. CLI input is bounded regular-file only. JSON and Markdown outputs are create-exclusive and the entire pair is reserved before either payload is written. The writer retains the owned file descriptors through write and identity/size validation. Failure rollback never pathname-deletes a reserved output: it best-effort truncates only the retained owned inode and closes it. A still-visible owned path may therefore remain as a fail-visible zero-byte tombstone that requires explicit operator cleanup. This tradeoff is intentional because portable pathname deletion cannot atomically say “unlink only if this name still identifies my inode”; a same-directory foreign successor must never be deleted by rollback. The package performs no network calls.

## Validation

Run:

```bash
python -m py_compile revenue/partner_conversion_ledger/*.py
python -m unittest -v revenue.partner_conversion_ledger.test_ledger_core revenue.partner_conversion_ledger.test_ledger_runtime
python -O -m unittest -v revenue.partner_conversion_ledger.test_ledger_core revenue.partner_conversion_ledger.test_ledger_runtime
```

The hostile suite includes symmetric cross-candidate provider replay, same-candidate message-ID replay, same-candidate thread continuity, exact follow-up exception binding, stale/current receipt drift, and output substitution/collision rollback that proves foreign successor bytes survive. The checked-in synthetic fixture contains no real recipient address, email body, credential, buyer data, or provider secret.

## Authority ceiling

Evidence/control only. This package grants **zero** send/contact/follow-up/partner-selection/submission/bid/pricing/spend/contract/payment/revenue authority. It never turns a provider ID, positive reply, owner-review state, or historical receipt into acceptance, award, payment, cash, or recognized revenue.
