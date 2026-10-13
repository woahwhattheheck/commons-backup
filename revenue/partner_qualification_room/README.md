# Partner Qualification Room

A local, buyer-neutral evidence engine for deciding whether a potential teaming or subcontracting partner is ready for **human review** against public-sector opportunity requirements.

This is deliberately a qualification *room*. Runtime surfaces are local/offline only; authority fields for outreach, quoting, submission, provider mutation, and payment remain false.

## What it does

- turns capability, experience, geography, insurance, certification, registration, and authority requirements into a deterministic matrix;
- requires every evidence item to point at an explicit source reference;
- distinguishes `confirmed`, `claimed`, `unknown`, and `contradicted` evidence—only `confirmed` can satisfy a requirement;
- treats expired evidence as stale and future-dated observations as unusable;
- fails closed on duplicate IDs, malformed dates, unknown requirement links, missing sources, and unsupported categories;
- yields `READY_FOR_HUMAN_REVIEW`, `QUALIFICATION_GAPS`, or `DISQUALIFYING_CONTRADICTION`;
- evaluates a room of partners without inventing a winner or numerical score;
- emits stable SHA-256 packet and room digests; reordered input arrays produce the same result;
- exports a Markdown requirement matrix plus evidence ledger with source references;
- provides a standard-library-only JSON/Markdown CLI for local/offline use.

## Non-authority boundary

`READY_FOR_HUMAN_REVIEW` is a review state only. Every packet hard-codes `eligibility_asserted=false`, `outreach_authorized=false`, `quote_authorized=false`, `bid_submission_authorized=false`, `provider_mutation_authorized=false`, and `payment_authorized=false`. A human with the relevant legal/commercial authority decides any next action.

## Evidence states

| State | Can satisfy? | Meaning |
|---|---:|---|
| `confirmed` | yes | source-linked evidence supports the requirement and is current as of evaluation |
| `claimed` | no | claim-only evidence remains unverified |
| `unknown` | no | available evidence leaves the requirement unverified |
| `contradicted` | no | source-linked evidence conflicts with the requirement; a required contradiction blocks readiness |

## Run the example

From this directory:

```bash
python qualification.py example.json --format json
python qualification.py example.json --format markdown
```

The example intentionally leaves insurance as `claimed`; claim-only evidence leaves the requirement unverified.

## Input shape

The root JSON object must contain:

- `as_of`: ISO date (`YYYY-MM-DD`);
- `opportunity`: object with `id` and non-empty `requirements`;
- exactly one of `partner` or `partners`.

Each requirement has an `id`, supported `category`, `description`, and boolean `must_have`. Each evidence item has an `id`, `requirement_id`, evidence `state`, `source.ref`, `observed_on`, optional `expires_on`, and optional `note`.

## Validation

```bash
python -m py_compile qualification.py test_qualification.py
python -m unittest -v test_qualification.py
```

The implementation uses only the Python standard library and performs no network I/O.
