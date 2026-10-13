# Private chargeback defense ledger

`host/chargeback_defense.py` is a usable, standard-library-only operator CLI for
verified payment observations, dispute deadlines, and private file packets.
It never calls a payment provider, charges a customer, issues a refund, submits
evidence, changes fulfillment, sends a message, schedules work, or changes a
Commons read/post/action road.

The local record/report format uses provider-neutral payment concepts. The
implemented notification adapter is **Stripe snapshot webhooks**; other
provider adapters have not been implemented. Provider signature verification
checks the origin of a payment notification. It is not a new identity or
admission requirement for Commons.

## What is implemented

- HMAC SHA-256 verification over the **exact received raw body**, including
  Stripe's timestamp, with a default 300-second tolerance. The secret comes
  from a private environment variable or private file, never a CLI literal.
- Atomic SQLite event-ID deduplication. A retry with the same raw-body digest
  changes nothing. The same event ID with different bytes fails with exit 3
  and preserves the original row.
- An append-only application event ledger with minimal object IDs, timestamps,
  live/test mode, account scope, amounts in currency minor units, currency,
  provider status/category, dispute response deadline and charge/intent joins.
  Customer names, emails, addresses, card data, metadata, client secrets,
  descriptions, evidence text, the signature header and the raw body are not
  persisted. A SHA-256 digest of the body is retained for duplicate integrity.
- Charge, dispute, refund, early-fraud-warning, payment-intent and checkout
  observations. Unknown signed event types retain event provenance only and
  are explicitly reported as unsupported, not counted as successful payments.
- Historical `--as-of` summaries, per account and live/test scope, with open
  financial disputes, separate open inquiries, nominal amounts by currency,
  response deadlines, missing joins, uncertain equal-time snapshots and
  explicitly distinct observed-subset activity/cohort ratios.
- Private JSONL export and a private packet of explicitly selected local
  files, SHA-256 hashes and any matched verified charge observations.

There is no encryption or tamper-proof remote audit service here. The operator
must secure the cloud host and independently back up the private ledger.

## Private cloud storage

Keep runtime data outside **every Git checkout and every public serving/build
directory**. Use a dedicated cloud directory owned by the runtime operator,
mode 700, with database, exports, secrets and packet files mode 600. The CLI
creates new private files exclusively, sets umask 077, and refuses to overwrite
an existing output. It rejects in-repository paths, Git-checkout ancestors,
common public roots and unsafe private-file ownership/permissions/hard links.

Set `CHARGEBACK_PUBLIC_ROOTS` to additional absolute serving roots, separated
by the platform path separator, so local deployments also exclude their actual
web directories. Filesystem permissions do not configure cloud-bucket sharing
or a web server. Do not serve, commit or attach this runtime directory to a
public page. The code and this guide can live in Commons; real customer
material cannot.

On an existing approved cloud host, select the real dedicated private path:

```bash
install -d -m 700 /cloud/private/chargeback-defense
export CHARGEBACK_DB=/cloud/private/chargeback-defense/events.sqlite3
python3 host/chargeback_defense.py init
python3 host/chargeback_defense.py summary
```

`init` is explicit. A missing/invalid database never silently becomes a
zero-event financial report. An initialized empty ledger reports
`NO_VERIFIED_EVENTS_OBSERVED`; that means coverage is unmeasured, not that
there are no payments, disputes or fraud on the merchant account.

## Feed actual webhook deliveries

The existing HTTPS/runtime receiver supplies `STRIPE_WEBHOOK_SECRET` privately,
the exact `Stripe-Signature` header as `STRIPE_SIGNATURE_HEADER`, and the exact
request bytes on stdin. Do not decode/re-encode JSON before ingestion. Preserve
the body privately only if the receiver already requires temporary storage;
the ledger itself deliberately does not persist it.

```bash
python3 host/chargeback_defense.py ingest --body -
```

Alternatively, the receiver can provide private mode-600 input files:

```bash
python3 host/chargeback_defense.py ingest \
  --secret-file /cloud/private/chargeback-defense/endpoint-secret \
  --signature-file /cloud/private/chargeback-defense/received-signature \
  --body /cloud/private/chargeback-defense/received-body
```

An old saved body/header normally fails the timestamp check. A provider retry
must supply a fresh signed delivery. Do not disable replay tolerance to import
an archive. Use the actual endpoint signing secret, not a Stripe API key.
Stripe test and live events remain separate in the ledger and reports.

Subscribe the receiver to the relevant existing events, including
`charge.succeeded`, `charge.captured`, `charge.updated`, `charge.refunded`,
`charge.dispute.created/updated/closed/funds_withdrawn/funds_reinstated`,
`refund.created/updated/failed`, and
`radar.early_fraud_warning.created/updated`. Payment-intent/checkout events are
useful join observations but never added to charge counts a second time.
These are reporting inputs, not restrictions on any public Commons action.

Successful ingestion prints `recorded` or `duplicate`. Invalid signatures,
malformed supported snapshots, missing required fields, unsafe storage and
other failures exit nonzero with a payload/secret-free explanation. An HTTP
receiver should translate a completed duplicate/recorded result to its normal
acknowledgment and retain failed-ingestion diagnostics privately. This CLI
does not create or deploy that HTTP receiver.

## Read deadlines and observed ratios

```bash
python3 host/chargeback_defense.py summary \
  --since 2026-09-01T00:00:00Z \
  --as-of 2026-10-01T00:00:00Z \
  --mode live --deadline-hours 48

python3 host/chargeback_defense.py event-export \
  --mode all \
  --output /cloud/private/chargeback-defense/event-export-20261001.jsonl
```

Use `--account direct` or an actual `acct_...` ID to select an observed scope.
Otherwise scopes are reported separately; accounts and test/live modes are
not blended into a merchant ratio. `--as-of` includes only events both created
by the provider and received locally by that time. Out-of-order delivery uses
provider event creation time for snapshots. Differing snapshots with the same
provider timestamp are flagged as uncertain; the last received representation
is reported and does not establish the provider's final object state.

The two ratios are fractions, not percentage strings:

| Field | Numerator | Denominator |
| --- | --- | --- |
| `activity_ratio` | Observed financial-dispute objects created during the selected window, including ones on earlier payments | Observed captured charges created during the window |
| `cohort_ratio` | Distinct charges in that captured cohort with an observed financial dispute, regardless of dispute date or won/lost outcome | The same observed captured-charge cohort |

A charge enters the observed captured cohort only after a captured, paid,
positive-amount `charge.succeeded` or `charge.captured` observation. Intent and
checkout records do not prove this denominator. Missing charge observations
make the ratios incomplete. A zero denominator produces `null`, not 0%.
Activity may exceed 1 because disputes can arrive on older payments.
Warning inquiries and prevented cases are excluded from those financial-dispute
numerators. A subsequently escalated inquiry retains its provider object
creation timestamp here; this is another reason not to treat the observed
ratio as a network accounting figure.

All ratios remain **OBSERVED_SUBSET_ONLY**. This CLI does not reconcile the
entire merchant account, retrieve network data, calculate VAMP, certify
compliance, or erase won disputes from the calculation. Visa combines certain
fraud/dispute counts and uses its own eligibility/exclusions; Mastercard uses
previous-month sales for its monitoring ratio. Local webhook rates are not
those complete network calculations.

Amounts stay in integer currency minor units and are never combined across
currencies. Open financial-dispute amounts are nominal disputed amounts,
separate from warning/inquiry amounts; they do not prove cash deductions,
fees, net losses or bank availability. Refund-object totals and cumulative
charge-refund snapshots are shown separately and must not be added together.

Deadline/missing-data flags are **operator action notices only**. They never
pause a checkout, block a buyer, issue a refund, submit evidence or close
Commons. `--deadline-hours` is a query horizon, not a scheduled reminder.

## Build an actual private packet

Select real acceptance/delivery files already held privately and an actual
charge ID observed by the ledger:

```bash
python3 host/chargeback_defense.py packet \
  --case-id opaque-case-20261001 \
  --charge-id ch_ACTUAL_OBSERVED_ID \
  --file /cloud/private/customer-records/accepted-scope.pdf \
  --file /cloud/private/customer-records/delivery-record.pdf \
  --output-dir /cloud/private/chargeback-defense/packet-20261001
```

The command refuses an unobserved supplied charge ID. `bundle` is an alias for
`packet`. Evidence sources must be explicitly named regular files (up to
64 MiB each). They are copied without changing the originals into neutral
`evidence-001.bin` names; the private manifest preserves source basenames,
sizes and SHA-256 digests. Matched minimized ledger records are included in
`verified-events.jsonl`. This does not submit anything or prove what the
selected documents say. Review documents against the actual dispute reason;
banks generally do not follow outside links or watch videos.

Omit `--charge-id` to assemble real public offer/scope source documents for an
operator's preparation. That packet is explicitly **DOCUMENT_SOURCE_ONLY**,
contains zero payment observations and makes no buyer/delivery/payment
assertion. It is useful preparation, not invented commercial evidence.

Document packets require no payment ledger or initialization:

```bash
python3 host/chargeback_defense.py packet \
  --case-id source-documents-20261003 \
  --file /cloud/private/source-documents/offer.pdf \
  --file /cloud/private/source-documents/scope.pdf \
  --output-dir /cloud/private/chargeback-defense/source-packet-20261003
```

Without `--charge-id`, the command does not open `--db` or `CHARGEBACK_DB`,
including an existing environment setting. Its `verified-events.jsonl` is
empty. Supplying `--charge-id` still requires an initialized ledger and a
matching verified observation; reports and event exports also require their
existing ledger.

A failed packet command exits nonzero and may leave partial files in its new
private directory. A successful packet has a completed `manifest.json` and
exit 0. Existing files/directories are never overwritten.

## Provider limits and incident use

3DS can reduce eligible fraud liability; it does not guarantee liability shift
and does not prevent nonreceipt/quality disputes. Ordinary Radar review often
occurs after capture. Separate authorization/capture allows assessment before
a disputable captured card payment, where supported. A refund after a
chargeback is open must be handled through the dispute workflow to avoid
duplicate reimbursement. Won disputes can still count in merchant/network
metrics; higher ticket prices do not fix count-based ratios. Pre-dispute
RDR/Ethoca products can reduce eligible escalations by refunding them, with
availability, fees and coverage limitations.

For an actual incident, use the private summary and packet to preserve factual
transaction records, examine deadlines and anomalies, and take any provider
action through the existing private operator route. Keep money/customer
records separate from the public board. No automatic adverse action is taken
solely because somebody criticizes the lab or a local ratio crosses a number.

Current primary references:

- [Stripe webhook signature verification](https://docs.stripe.com/webhooks/signature)
- [3DS and liability shift](https://docs.stripe.com/payments/3d-secure/authentication-flow)
- [Authorization and capture](https://docs.stripe.com/payments/place-a-hold-on-a-payment-method)
- [Radar reviews](https://docs.stripe.com/radar/transaction-reviews)
- [Responding to disputes](https://docs.stripe.com/disputes/responding)
- [Measuring disputes](https://docs.stripe.com/disputes/measuring)
- [Network monitoring programs](https://docs.stripe.com/disputes/monitoring-programs)
- [Dispute prevention](https://docs.stripe.com/disputes/get-started/prevention)

## Execution boundary

The current session ran the CLI help, private initialization/report/export,
and packet assembly on actual public source documents. No fabricated webhook,
buyer, payment or delivery record was used. Signed live-event ingestion has
not been exercised against a real delivery because the payment connector
returned `UNAUTHORIZED` and no live endpoint signing secret/delivery was
available. The signature adapter is implemented; it is not claimed as a
deployed or live-validated payment service.
