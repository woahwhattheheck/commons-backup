# Warranty & RMA Operations Desk

A local-first post-sale workflow for small manufacturers, repair businesses, and e-commerce operators.

The desk turns a customer defect report into one merchant-controlled case lifecycle:

`SUBMITTED -> NEEDS_INFO / APPROVED_RMA / DENIED -> RECEIVED -> INSPECTED -> RESOLUTION_APPROVED -> CLOSED`

It deliberately does **not** decide legal warranty coverage, diagnose product safety, contact customers, buy labels, call carriers/storefronts/payment providers, issue refunds, or claim external completion. Consequential actions are explicit operator decisions. External return/resolution handoffs are represented as `NOT_SENT` / `external_authority=false` until a separate authorized integration performs them.

## Customer workflow

1. Pick a merchant-authored product/policy.
2. Submit purchase reference/date, serial when required, issue description, and optional evidence metadata.
3. Save the one-time status capability returned on case creation. Only its SHA-256 is stored.
4. Read a public-safe timeline for that case only.
5. If the merchant requests information, add a bounded supplement with replay protection.

An intake idempotency key is bound to normalized content. Exact retries reuse the case; changed retries fail closed. A second active case for the same product serial is rejected.

## Operator workflow

The operator bearer is separate from customer capabilities.

The operator can:

- create products and merchant-authored policy revisions;
- inspect complete case/evidence/audit state;
- request more information, approve an RMA, or deny;
- record receipt only against the exact case RMA;
- record an inspection only after receipt;
- choose `REPAIR`, `REPLACEMENT`, `REFUND`, or `RETURN_AS_IS` only after inspection;
- close only after a resolution handoff exists and the merchant supplies a completion reference;
- export a deterministic canonical case packet.

Every mutation requires an idempotency key. Consequential operations also bind the current case revision; operator decisions additionally bind the exact policy revision frozen onto the case. A later catalog policy cannot silently relabel an older case.

`completion_ref` means **merchant-observed workflow completion only**. Export and close receipts explicitly keep provider verification and all external authority false.

## Run

Python 3.11+; stdlib only.

```bash
python app.py serve \
  --db ./warranty-rma.sqlite3 \
  --operator-token 'replace-with-a-long-random-local-capability'
```

The server refuses non-loopback bind targets. The hardened entry boundary also requires the HTTP `Host` header to name loopback exactly and requires `application/json` for POST bodies that can reach JSON parsing. Open the printed local URL. The browser UI has customer intake/status and operator catalog/case workflows.

For a synthetic end-to-end case:

```bash
python app.py demo --db ./demo.sqlite3
```

Expected shape:

```json
{
  "demo": "synthetic",
  "external_actions_performed": 0,
  "final_status": "CLOSED",
  "resolution": "REPLACEMENT"
}
```

Export an existing case without overwriting an existing path:

```bash
python app.py export --db ./warranty-rma.sqlite3 --case-id RMA-... --out ./case.json
```

Export publication is create-exclusive and fail-closed. The entry boundary drains legal positive short writes, fsyncs, verifies the retained regular single-link inode and exact size, reads the visible pathname back byte-for-byte, then re-checks pathname identity and single-link state after readback. If any publication check fails, the command fails nonzero.

Failure cleanup intentionally does **not** unlink the output pathname. Portable `lstat(path)` followed by `unlink(path)` has a replacement race that could delete foreign data. A failed create-exclusive artifact may therefore remain for operator inspection/removal; a later export to the same path will continue to refuse overwrite until an operator handles that artifact. Foreign replacement paths and hardlink aliases are never deleted by failure cleanup.

## Security / privacy boundaries

- SQLite state is local; no external network client exists in the Python product.
- Customer status is capability-based and case-scoped; operator notes never appear in the customer timeline.
- Operator bearer and customer status capabilities are cryptographically compared by SHA-256 digest; plaintext status capabilities are not persisted.
- JSON parsing rejects duplicate keys and non-finite values.
- HTTP JSON bodies are bounded and transfer encoding is rejected.
- Loopback HTTP requests require an exact loopback `Host`; mutation bodies that can reach JSON parsing require `application/json`.
- Evidence stores metadata + SHA-256 only; this product does not upload customer files to an external service.
- Browser rendering uses DOM text nodes rather than dynamic `innerHTML`.
- HTTP responses use `no-store`, `nosniff`, no-referrer, and a local-only CSP.
- The current product is a local operations desk, not a hosted multi-tenant service or legal/compliance system.

If deployed beyond loopback later, add an explicit deployment/auth/TLS/tenant-isolation layer rather than treating this local bearer boundary as Internet-ready.

## Tests

```bash
python -m py_compile app.py app_core.py test_app.py test_ui_contract.py test_boundary_hardening.py
python -m unittest -v
python -O -m unittest -v
```

The original focused suite attacks duplicate/changed retries, active duplicate serials, cross-case capability use, private-note leakage, stale case/policy decisions, impossible transition order, duplicate/cross-case receipt identities, reopen, concurrency, operator authentication, strict JSON/type handling, local HTTP authorization, and external-network primitives.

The recovery boundary suite additionally attacks positive short writes, zero write progress, overwrite refusal, pathname replacement before/during readback, hardlink creation during readback, hostile `Host`, cross-origin-simple `text/plain` JSON mutation, and ordinary loopback `application/json` compatibility. Failure-path tests trap `os.unlink` so a hidden pathname-deletion regression fails the suite.

## Native browser handoff

A 2026-10-03 native Chromium 153.0.8010.0 session used the existing `app_core.py` demo product, purchase, issue and evidence values through the actual catalog/intake/operator forms and the loopback Python server. No fetch, storage, crypto or clock adapter was injected. Evidence stayed metadata only: the existing demo filename and synthetic SHA-256, with the UI's `application/octet-stream` type; no image was uploaded or invented.

The native intake initially returned 201, then rejected an unchanged retry with `409 IDEMPOTENCY_CONFLICT`: the form retained its intake key but generated a fresh evidence ID. The UI now derives intake evidence identity from that same retained request key. The corrected form returned 201 then 200 for identical request content and one existing case/evidence/event. Changing the filename under the same key still returned 409; restoring it returned 200 again. The server's normalized-content binding is unchanged, as is independent evidence identity for supplements. Retain the first creation response's one-time status capability as instructed; repeat responses do not reissue it, and page reload does not preserve the unsent form/request key.

The same native case then followed the existing demo's merchant-recorded approve RMA → receive → inspect → replacement resolution → close workflow, reaching revision six with six events and one evidence item. Customer status retained its public timeline while excluding all operator notes. Return and resolution handoffs remained `NOT_SENT` with `external_authority=false`; closure retained `provider_verified=false`, and all seven export authority flags remained false. These are fictional local records, not actual receipt, inspection, replacement or customer/provider actions.

The existing create-exclusive CLI exported the canonical case packet, and its content receipt was independently recomputed. Page reload and a real server stop/restart preserved exact operator case, customer status and export bytes. Populated operator detail initially overflowed a 390-pixel viewport to 693 pixels because of unbroken evidence metadata. Shrinkable grid children and wrapping within cards now keep that page at 390 pixels; desktop/mobile screenshots were inspected. No page errors or external requests occurred. The deliberate changed-content request produced the expected HTTP 409/browser resource warning; the final layout/restart continuation was clean.

Only `index.html` and this README changed for the intake/layout handoff (#30845). The original product and recovery/publication-boundary contributions remain intact; `app.py`, `app_core.py` and existing tests were unchanged. No suite was rerun or expanded, no dependency installed, and temporary browser/server processes were closed. Native operator acceptance does not extend the external-action or commercial boundaries above.

## Equal-timestamp event order

The native case above recorded all six sequential actions within one timestamp second. The previous customer/operator reads broke timestamp ties with random event IDs, displaying resolution before submission despite the retained insertion sequence. Event reads now keep timestamps as the primary order and use the existing SQLite event insertion order for equal timestamps. The customer timeline, operator audit and canonical export therefore agree with the actual recorded sequence. No event, timestamp, case revision or policy was rewritten; no schema migration was introduced.

The same retained database was reopened through the real browser/server after this repair. Both views showed submission → approval → receipt → inspection → resolution → closure, with every original event field and every other case/status field unchanged. Native HTTP replays of the retained intake, approval and closure returned their existing results without adding events or changing any stored row. Existing CLI export and its recomputed receipt reflected only the corrected event-array order; a real server restart preserved the new bytes exactly. The saved earlier export remains its original historical artifact and was not overwritten. All seven external authority flags, both `NOT_SENT` handoffs and false provider verification remain unchanged.

This is a tie-breaking correction for the existing append-only event table. It does not reinterpret clock regressions or promise chronology for externally reconstructed databases. It changes only `app_core.py` and this README; prior UI, authentication and create-exclusive publication repairs are preserved. The retained rows and native workflows supplied acceptance evidence without new tests, fixture data, dependencies or external actions.

## Commercial posture

Initial internal offer hypothesis: **$499 setup + $99/month** for one bounded brand/workspace. This repository does not create a subscription, charge a customer, promise SLA/compliance, or recognize revenue. External pricing/customer deployment remains a separate commercial action.
