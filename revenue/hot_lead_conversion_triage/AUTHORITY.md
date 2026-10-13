# Authority boundary

## Purpose

This package is a deterministic **triage** boundary. It orders owner-supplied lead/thread observations so a large concurrent fleet can focus on unanswered human conversion events without confusing automated acknowledgements, already-answered threads, or DNRs for new publication opportunities.

## Source authority

The input is caller/owner supplied.

Therefore:

- `HUMAN_POSITIVE` does **not** prove that a provider message exists;
- `HUMAN_POSITIVE` does **not** prove the sender was human;
- `EXPLICIT_DNR` is treated conservatively as terminal when supplied, but the package does not independently fetch or authenticate the underlying message;
- `last_outbound_at` does **not** prove a provider accepted or delivered a send;
- `candidate_followup` is only digest-bound data.

The receipt binds and reasons over the exact structured snapshot. It does not elevate caller-authored classification into provider truth.

## Publication authority

This package cannot authorize publication.

Every receipt has:

```json
{
  "authority": {
    "scope": "triage_only",
    "external_send_authorized": false,
    "muse_election_claimed": false,
    "publication_authority_required": true
  }
}
```

Every item and every actionable queue entry also carries:

```json
{
  "external_send_authorized": false
}
```

This redundancy is deliberate. A consumer that strips the top-level authority block still cannot honestly read a queue row as a send permit.

A current independent publication-election/authority receipt (for example, the workspace's Muse selection mechanism plus whatever connector-specific authority gate is current) remains required before any external send.

## Consent and DNR

The package never infers consent. It uses fail-closed operational meanings:

- any supplied `EXPLICIT_DNR` suppresses the thread;
- supplied `HUMAN_NEGATIVE` is HOLD, not permission for persuasion;
- `AUTOMATED_ACK` is HOLD, not interest;
- an equal timestamp between reply and outbound is BLOCKED because order is ambiguous;
- contradictory same-instant human labels are BLOCKED.

No state here revokes a DNR. If the organization later supports authenticated DNR revocation, that needs a separate explicit authority design; it must not be inferred from a later positive label.

## Candidate text

Optional `candidate_followup` is accepted only so downstream systems can bind an election/publication receipt to exact proposed bytes. The triage receipt contains only its SHA-256 digest, never the raw text.

The digest:

- does not approve wording;
- does not prove recipient identity;
- does not authorize a connector;
- does not authorize payment or contractual terms;
- does not claim a Muse win.

## Non-authorities

The package does not:

- contact Gmail, Slack, GitHub, or another provider;
- mutate a provider;
- create or renew a distributed lock;
- settle a publication race;
- verify human identity;
- verify email ownership;
- verify message delivery;
- recognize revenue;
- verify payment;
- claim sponsor/prospect consent;
- create legal obligations.

It is safe to run in parallel because it has no external side effects. Publication remains separately serialized.
