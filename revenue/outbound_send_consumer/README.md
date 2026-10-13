# One-shot outbound provider consumer

Issue: `woahwhattheheck/commons#14049`.

This package is the terminal mutation primitive for one externally visible outbound event. It does **not** decide whether outreach is allowed and never creates a reusable send-authority bearer. A trusted host must already have independently derived the provider request bytes, canonical organization/buyer identity, canonical commercial opportunity, exact triggering event generation, repository anchor, and live private authority generation.

## Exclusion seam

The atomic reservation seam is exactly:

`repo + buyer_scope + opportunity_scope + event_kind + event_key`

It intentionally excludes recipient/route aliases, message draft, price, claimant/worker, and claim ID. Two workers with different drafts, prices, or contacts at the same organization/opportunity/event therefore race on the **same** immutable Git ref. Initial outreach uses a host-derived `event_kind=initial` + canonical first-contact event key; replies/follow-ups use their own exact newer event generations. A genuinely newer human/provider event is a new seam.

## Call contract

`consume_once()` requires two independently supplied objects:

* caller `intent_raw` describing the attempted mutation; and
* trusted `host_raw` derived by the provider host from the actual request/state.

The objects must match on all provider-relevant identity/request fields. A live `authority_probe()` returns the host-retained 64-hex authority-generation digest. The consumer probes before reservation and **again after winning, immediately before the provider callback**. A copied public receipt cannot substitute for that private live probe.

The consumer creates a content-addressed annotated tag carrying a cryptographic invocation nonce and atomically creates one deterministic reservation ref. Ambiguous create is reconciled by exactly one readback. Only an exact-self winner may reach the callback. The callback receives a content-addressed idempotency key and must return built-in `None` on known completion; arbitrary return values are neither serialized nor `repr()`'d and force `OUTCOME_UNKNOWN`.

A second immutable ref retains one of `SENT`, `REJECTED`, `OUTCOME_UNKNOWN`, or `HELD_AUTHORITY`. Provider exception/timeout, ambiguous reservation, or outcome-persistence uncertainty becomes `RECONCILE_REQUIRED`; the same event seam is never automatically retried. A suppressed loser always has `external_send_completed=false`; if it can verify a prior retained `SENT`, it may separately report `prior_send_observed=true`.

## Authority ceiling

Source/tests only. The package performs no Gmail, Slack, Discord, customer, payment, accounting, or other external-provider mutation by itself. `external_send_authorized` remains false in every receipt: authority must remain private to the host and is consumed only inside the winning invocation.

`#14269` is the separate integration carrier that must compose organization-pressure, organization-wide lease, prospect/opportunity authority, action-specific slot, this one-shot consumer, and adapter coverage before the live duplicate-outreach incident is mechanically closed.
