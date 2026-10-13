# Private receiver adapter — operator handoff

`host/chargeback_defense_receiver.py` is a deployment-neutral, no-account-auth
HTTP ingress adapter around the landed chargeback-defense ingest path
(`host/chargeback_defense.py`). It turns the CLI-only private signed-event
ledger into a composable private-backend service boundary without configuring
a provider, deploying anything, or moving money.

## What it does

* Accepts `POST /ingest` with the exact raw body bytes and forwards the exact
  `Stripe-Signature` header to the core's own `verify()` / `normalize()` —
  the same provenance check and minimization the `ingest` CLI performs.
* Enforces a bounded request size (default 8 MiB, the core's `MAX_BODY`) and
  explicit method / content-type / path handling.
* Maps signature, stale-timestamp, malformed-input, duplicate, durable-write,
  and internal failures to deterministic HTTP outcomes (see the module
  docstring's status table).
* Returns `200 recorded` / `200 duplicate` only after the core reports a
  durable outcome: atomic `BEGIN IMMEDIATE` write, exact-byte replay is
  idempotent with no second effect, same event ID with different bytes is a
  `409` with the original row preserved.
* Logs and returns public-safe operational metadata only: schema version,
  status, event ID, record kind, counts, HTTP status, byte sizes, timestamps.
  Raw bodies, secrets, customer fields, account identifiers, and private
  filesystem paths never appear in logs, responses, or receipts.

## What it does not do

No login, no provider configuration, no Stripe reauthentication, no live
signing secret handling beyond the operator-supplied runtime value, no real
event ingestion, no provider/customer contact, no charge/capture/refund, no
dispute submission, no pricing change, and no acceptance / revenue / cash
claim of any kind. The adapter performs no account authentication of its own;
it is meant to sit behind the operator's private network boundary.

`host/stripe_event_bridge.py` is intentionally not imported (it requires
unrelated commerce dependencies). Signature semantics are composed from
`host/chargeback_defense.py`, which documents their equivalence.

## Running it (private backend only)

```bash
# 1. Choose a private directory OUTSIDE every Git checkout and public root.
export CHARGEBACK_DB=/private/ops/chargeback/ledger.sqlite
export STRIPE_WEBHOOK_SECRET='<endpoint secret from the Stripe dashboard>'

# 2. Initialize the ledger once (no server, no secret needed for --init).
python3 host/chargeback_defense_receiver.py --init

# 3. Serve on the private interface (default 127.0.0.1, ephemeral port).
python3 host/chargeback_defense_receiver.py --bind 127.0.0.1 --port 8443
```

A `--secret-file` (mode-600 file in a mode-700 private directory) may replace
`--secret-env`. The process sets umask 077. Any WSGI server can serve
`create_app(config)` instead of the bundled stdlib server.

For missing, invalid, or oversized `Content-Length`, the bundled HTTP/1.1
listener returns its existing `411` / `400` / `413` JSON response with
`Connection: close`. Reconnect before sending the next request. The rejected
body stays outside the next request parser, following the HTTP persistence
requirement in [RFC 9112 §9.3](https://www.rfc-editor.org/rfc/rfc9112.html#section-9.3).

## Verifying without a provider

```bash
python3 host/chargeback_defense_receiver.py --loopback-proof
```

Spins up a real HTTP listener on 127.0.0.1 with an ephemeral port, signs an
explicitly synthetic event with an explicitly synthetic HMAC secret, delivers
it, replays it, and exercises the rejection paths. Zero external calls.

Focused tests (run both):

```bash
cd host && python3 test_chargeback_defense_receiver.py
cd host && python3 -O test_chargeback_defense_receiver.py
```

## Remaining operator dependencies (not part of this build)

Owner/operator selection of the private backend and storage, Stripe
reauthentication, endpoint-secret creation, deployment behind the private
network boundary, and observation of one real signed event. This adapter
proves the ingress surface with synthetic events only; it performs none of
those steps.
