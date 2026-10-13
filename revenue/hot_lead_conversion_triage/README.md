# Hot Lead Conversion Triage

`hot_lead_conversion_triage` converts an **owner-supplied, structured observation snapshot** into a deterministic hot-lead action queue without contacting a provider and without authorizing any external send.

It exists for a fleet failure mode that gets more expensive as concurrency rises: one agent sees a useful reply while another sees an older outbound state, or multiple agents treat an automated acknowledgement as human interest and independently publish follow-ups. The triage receipt answers only:

> Given this exact supplied snapshot, which threads look like unanswered human conversion events, which are already answered, and which must be held or blocked?

It deliberately does **not** answer whether a provider observation is authentic or whether a message may be sent. Those are separate authority questions.

## What it does

- prioritizes an unanswered `HUMAN_POSITIVE` reply ahead of `HUMAN_QUESTION`;
- suppresses all follow-up after any supplied `EXPLICIT_DNR`;
- treats `AUTOMATED_ACK` as HOLD rather than human interest;
- distinguishes a human reply that arrived **after** the latest outbound from one already answered by a newer outbound;
- blocks equal-timestamp reply/outbound ordering instead of guessing which happened first;
- blocks contradictory human meanings asserted at the same instant;
- blocks a supplied `DELIVERY_FAILURE` rather than recommending an immediate blind resend;
- binds an optional proposed follow-up by SHA-256 while omitting its raw text from the receipt;
- emits `external_send_authorized: false` at both receipt and item/queue boundaries;
- uses stable priorities and identity tie-breaks so two agents with the same snapshot get the same queue.

## What it does not do

- no Gmail/Slack/GitHub/provider reads;
- no sentiment or identity inference from raw message text;
- no proof that an event marked `HUMAN_POSITIVE` was actually written by a human;
- no Muse election or publication mutex;
- no email/message send;
- no payment, revenue, consent, or legal-status claim.

See [`AUTHORITY.md`](./AUTHORITY.md).

## Input

```json
{
  "schema_version": 1,
  "as_of": "2026-09-15T00:45:00Z",
  "threads": [
    {
      "prospect_id": "lead-42",
      "thread_id": "gmail-thread-abc",
      "last_outbound_at": "2026-09-15T00:30:00Z",
      "candidate_followup": "Thanks for the reply. Here is the scoped next step.",
      "observations": [
        {
          "event_id": "reply-1",
          "observed_at": "2026-09-15T00:41:00Z",
          "kind": "HUMAN_POSITIVE"
        }
      ]
    }
  ]
}
```

Allowed observation kinds:

| Kind | Triage meaning |
| --- | --- |
| `HUMAN_POSITIVE` | Unanswered reply is highest conversion priority. |
| `HUMAN_QUESTION` | Unanswered reply is actionable, behind positive. |
| `HUMAN_NEGATIVE` | Hold; no automatic follow-up recommendation. |
| `EXPLICIT_DNR` | Terminal suppression for the supplied thread snapshot. |
| `AUTOMATED_ACK` | Hold; never treated as human interest. |
| `DELIVERY_FAILURE` | Block blind repeat-send behavior. |
| `NO_REPLY` | Snapshot assertion only; not a human response. |

All timestamps must be UTC RFC3339 strings ending in `Z`. Observations later than `as_of` are rejected. Duplicate event IDs, duplicate thread identities, duplicate JSON keys, non-finite JSON values, unknown fields, and future observations fail closed.

## Run

From the repository root:

```bash
python -m revenue.hot_lead_conversion_triage snapshot.json
```

Or pipe JSON:

```bash
cat snapshot.json | python -m revenue.hot_lead_conversion_triage -
```

Success emits one compact JSON receipt. Structural input failure emits a compact error object with a `reason_code` and exits `2`.

## Receipt

A positive human reply after the latest outbound produces an `ACTIONABLE_INBOUND` item and an entry in `action_queue`, but still carries `external_send_authorized: false`.

The receipt also includes:

- `input_sha256`: SHA-256 of the exact canonicalized structured input;
- `candidate_followup_sha256`: SHA-256 of optional candidate text, never the raw candidate;
- deterministic `priority` and `reason_code`;
- an authority block requiring a separate current publication-election/authority receipt before any send.

`action_queue` is therefore a **work queue**, not a send queue.

## Decision order

For each thread:

1. contradictory same-instant human meanings → `BLOCKED`;
2. any supplied explicit DNR → `TERMINAL_DNR`;
3. unanswered human positive/question after latest outbound → `ACTIONABLE_INBOUND`;
4. unanswered human negative → `HOLD`;
5. current delivery failure → `BLOCKED`;
6. older human reply already followed by a newer outbound → `WAIT`;
7. automated acknowledgement only → `HOLD`;
8. prior outbound without human reply → `WAIT`;
9. no outbound/human reply → `COLD`.

An equal timestamp between the latest human reply and latest outbound is deliberately `BLOCKED` because ordering cannot be proven from second-level timestamps.

## Validation

```bash
python -m unittest revenue.hot_lead_conversion_triage.test_triage -v
python -O -m unittest revenue.hot_lead_conversion_triage.test_triage -v
```

The initial carrier validates 14 tests in normal mode and the same 14 with `-O`, including positive-vs-question priority, already-answered suppression, DNR permanence, contradictory observation blocking, auto-ack hold, delivery failure, digest-only candidate binding, duplicate event IDs, future timestamps, duplicate JSON keys, non-finite JSON, and deterministic ordering.

## Integration boundary

```text
provider / operator observation
        |
        v
owner-supplied structured snapshot
        |
        v
hot_lead_conversion_triage
        |
        +--> ranked conversion work (NO SEND AUTHORITY)
        |
        v
independent current publication election / authority receipt
        |
        v
provider connector send
```

A caller must not reinterpret `ACTIONABLE_INBOUND` as authorization. It means only that, **if the supplied observation is trusted**, the thread deserves human conversion attention before colder work.
