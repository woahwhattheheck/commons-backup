# Hive006 authenticated Twilio webhook edge

`twilio_webhook.py` is the public-provider authentication boundary for the existing Voice Support Desk. It does **not** replace `desk.py` or `merchant_auth.py`: a request must first pass Twilio request-signature validation and then still pass the landed per-order support-code gate before order-specific data or return actions are reachable.

## Boundary

- The process binds to loopback only. Put it behind an HTTPS reverse proxy/TLS terminator; do not expose the Python listener directly.
- Supply the Twilio Auth Token only through a runtime environment variable (`TWILIO_AUTH_TOKEN` by default). The token is not accepted on the command line, written to SQLite, included in source bundles, or logged.
- Configure `--public-origin` to the exact HTTPS origin Twilio is configured to call, such as `https://support.example.com`. The proxy must preserve the raw request path and query string. The edge deliberately does **not** trust `Host`, `Forwarded`, or `X-Forwarded-*` to construct the signature URL.
- Only `application/x-www-form-urlencoded` `POST /voice` and `POST /dial-result` are accepted. Every received form field is passed to Twilio's validator. Duplicate form names are rejected rather than collapsed into ambiguous application input.
- Missing or invalid `X-Twilio-Signature` returns HTTP 403 before per-request `MerchantGate` dispatch or request-driven `Store` access. Process startup constructs `MerchantGate` / `Store` and may initialize the SQLite schema before listening, so this boundary does not claim zero startup database access. A correctly signed provider request still has to complete the order-reference + support-code flow from `merchant_auth.py`.
- Twilio's form-webhook signature does not add an application timestamp. Provider retries are therefore handled by the already-landed immutable call-turn / dial-result replay rules instead of inventing a timestamp field Twilio does not send.

Twilio's current security documentation recommends its SDK request validator because webhook parameter sets can evolve. This edge therefore pins `twilio==9.11.0` in `requirements-webhook.txt` and calls `twilio.request_validator.RequestValidator`; it does not carry a local HMAC implementation.

## Install and run

```bash
python -m pip install -r requirements-webhook.txt
export TWILIO_AUTH_TOKEN='...runtime secret...'
python merchant_auth.py --db voice-support.sqlite3 access merchant-access.csv
python twilio_webhook.py --db voice-support.sqlite3 serve \
  --bind 127.0.0.1 --port 8098 \
  --public-origin https://support.example.com
```

Configure the provider's Voice webhook as an HTTPS POST to `https://support.example.com/voice`. The desk-generated TwiML uses the relative `/voice?turn=N` and `/dial-result` callbacks, so the same configured public origin remains the signature source of truth.

The reverse proxy must preserve the original path and query bytes. If the public URL changes (scheme, host, path, query, or provider configuration), update `--public-origin` / proxy routing together and rerun signature acceptance. Do not “fix” validation failures by trusting forwarded host headers.

## Acceptance

`test_twilio_webhook.py` exercises missing/invalid signatures with a zero-dispatch assertion, exact configured public URL + raw query binding, all-form-field forwarding, query tamper rejection, duplicate-field fail-closure, authenticated dial dispatch, loopback/public-origin constraints, Twilio's published form-signature vector through the official SDK, and a signed end-to-end flow through the real `MerchantGate` proving provider authentication does not bypass the per-order support code.

The hosted workflow also runs the original desk and merchant-auth suites on the exact pull-request head. This remains a local/synthetic integration until a merchant supplies a real Twilio account/configuration and performs authorized end-to-end calls; no live telephone/provider acceptance is claimed here.

## Source packaging

`python twilio_webhook.py bundle voice-support-source.zip` creates a source-only bundle containing the desk, merchant gate, authenticated edge, docs/tests/examples, and pinned webhook dependency. It never packages the SQLite database, Auth Token, ambient logs, or customer data.
