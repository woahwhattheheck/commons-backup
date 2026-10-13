# Merchant order authorization edge

This is the order-specific authorization layer for the Hive006 Voice Support Desk. It closes the desk's original “order reference alone” authorization gap without changing the proven local desk state machine.

## What it protects

`merchant_auth.py` requires an 8–12 digit merchant-provisioned support code before it delegates a call into `desk.Store.turn()`. A guessed order reference by itself cannot read order status/ETA or create a return. Unknown and real order references receive the same pre-verification prompt. Wrong, blank, cross-order, or unknown-order verification ends with a generic response and never opens a desk call or return.

Support codes are stored only as salted PBKDF2-HMAC-SHA256 verifiers with 200,000 iterations in companion SQLite tables. Plain support codes are not written to the desk order table, snapshots, exports, audit rows, or call-turn payloads. Merchant-gate turn persistence stores only request hashes and responses, preserving exact retry behavior without retaining the supplied code.

## Provision

First import the normal order CSV with the existing desk, then provision the companion access CSV against those order references:

```sh
cd revenue/hive/voice-support-desk
python3 desk.py --db /your/workspace/voice-support.sqlite3 import orders.csv
python3 merchant_auth.py --db /your/workspace/voice-support.sqlite3 access merchant-access.csv
```

The access CSV is exact two-column UTF-8 data:

```csv
order_ref,support_code
1001,31415926
1002,27182818
```

The checked-in example values are fictional. Real merchants should generate random per-order codes and deliver them through their existing order-confirmation/customer channel. Do not reuse the example values or a global shop PIN. Re-importing a reference rotates its verifier. Access import rejects unknown orders and validates the entire file before any verifier row is changed.

## Run behind the trusted relay

```sh
python3 merchant_auth.py --db /your/workspace/voice-support.sqlite3 serve --bind 127.0.0.1 --port 8097
```

The merchant edge deliberately accepts loopback binds only. An existing voice-service relay should authenticate the provider request and forward only `/voice` and `/dial-result` to this local edge. The edge itself does **not** validate Twilio signatures or trusted proxy headers. That is the separate Hive006 reviewer blocker (2), and this module must not be exposed directly to the internet or represented as solving provider authenticity.

The original `desk.py serve` remains the local simulator/operator service and must not be substituted as the public customer webhook. Its `/voice` route does not include this verifier gate.

The gate supports the existing team handoff before or after verification. After successful verification, it maps the public call ID to a deterministic internal desk call ID and translates external turn numbers into the existing desk turn sequence. Return eligibility, policy rechecks, unique-return semantics, staff handoff behavior, and the desk's immutable retry records stay in the original implementation.

## Package and test

```sh
python3 merchant_auth.py bundle voice-support-desk-merchant.zip
python3 -B -m unittest -v test_desk.py test_merchant_auth.py
```

The merchant bundle contains the original five-file desk plus this module, its focused tests, this guide, and the fictional access CSV. It does not include the SQLite database or real verifier data.

Focused acceptance covers: identical known/unknown pre-verification responses; wrong/blank/cross-order no-disclosure/no-return; exact verification followed by real status and confirmed-return paths; process-restart replay; verifier exclusion from desk snapshots/exports; atomic access import; and loopback-only bind enforcement.

## Remaining live-connection boundary

This closes only order-specific caller authorization. A real public telephone installation still requires the merchant's trusted edge to validate provider authenticity/signatures and public URL/proxy rules before forwarding. No live call, merchant data, provider configuration, payment, storefront change, or customer deployment is performed by this package.
