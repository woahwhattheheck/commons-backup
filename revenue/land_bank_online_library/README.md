# Land Bank T12-09-26 online legal-library readiness carrier

This isolated carrier supports a **teaming-first** response to Land and
Agricultural Development Bank of South Africa solicitation `T12-09-26`.

It is deliberately fail-closed. Public tender listings are useful discovery
evidence, but they do not become procurement authority. The carrier therefore
keeps `teaming_status=HOLD` until the buyer-authored tender bytes are retained
with a SHA-256 reference.

## Public discovery snapshot

Public listings captured on 2026-09-16 described:

- online legal-library implementation, licensing, maintenance and support for
  three years;
- close at `2026-10-08 11:00 SAST`;
- virtual briefing at `2026-09-17 11:00 SAST`, marked non-compulsory by the
  public listing;
- legal-content ingestion/versioning/metadata, secure user access, search,
  in-browser document access/comparison/citation/export, personalization,
  cloud hosting, availability/DR, security, training and handover;
- prime qualification signals including legal-library/platform track record,
  OEM/OSM or authorized-partner posture, and South African procurement
  returnables.

Those facts are **working discovery facts only** until the buyer-authored files
are retained and hashed.

Primary discovery listing:
`https://easytenders.co.za/tenders/t12-09-26-centurion-online-library-system`

Durable pursuit carrier:
`https://github.com/woahwhattheheck/commons/issues/14872`

## State separation

The compiler exposes three separate states:

- `TEAMING_PACKET_READY`: source bytes plus the bounded paid TJLabs workshare
  are ready. This can be true while prime qualification remains HOLD.
- `PRIME_RESPONSE_ASSEMBLY_READY`: source bytes, workshare and every modeled
  prime evidence gate are all present.
- `SUBMISSION_READY`: prime response is ready and four explicit submission
  authority flags are exactly `True`.

No state is inferred from company names, URLs, prose claims, truthy strings or
secondary tender summaries.

## Paid TJLabs seam

The only accepted commercial workshare state is
`PAID_SCOPE_TO_BE_AGREED`. The bounded deliverable set is:

1. content migration / metadata acceptance;
2. RBAC / entitlement acceptance;
3. search and retrieval regression;
4. integration data-contract QA;
5. security / DR evidence matrix;
6. training / handover acceptance;
7. requirements traceability pack.

This does not make TJLabs the legal-content supplier, OEM/OSM, South African
registered bidder, penetration-testing certifier, signatory, or submission
authority.

## Run

```bash
python -m unittest -v test_land_bank_online_library
python -O -m unittest -v test_land_bank_online_library
python -m revenue.land_bank_online_library.cli \
  revenue/land_bank_online_library/example_hold.json
```

Ordinary HOLD returns exit code `2`. Only `SUBMISSION_READY` returns `0`.
