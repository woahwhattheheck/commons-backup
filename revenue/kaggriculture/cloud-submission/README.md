# TITAN direct-file submission transport

Operation: `titan-kaggriculture-frontier-20260907-01`.

The designated 57,711-byte archive at Commons commit `cf88ace1ba45a170fb8ba09986b5f7cb1413381b` has SHA256 `79b407d699b5fd39e7b396de8b6fc79b2bc2fb99f427f7e2e7ecd25fbc71fb0b`. Kaggle accepted submission **56074364** at 2026-09-07 10:01:29 UTC after a successful HTTP 200 archive upload. Provider readback found exactly one matching operation, 57,711 bytes, and three submissions remaining (two used today). Validation is COMPLETE with no reported error. Self-play validation episode 106416828 completed with 61,777 cash for both seats. No competitive episode was present in the 10:03:13 UTC readback. No further submission writes are needed. The earlier DISPATCH_STARTED journal is historical and preserved; subsequent provider reconciliation found no submission before the successful narrowed transport.

The separate public associated source notebook was created at https://www.kaggle.com/code/tokenjunkielabs/titan-kaggriculture-frontier-source (kernel 133417557, version 1). Kaggle normalized the requested slug from the title. Use the returned URL for readback, not the originally requested slug. The outgoing notebook in disclosure/frontier-source.ipynb has SHA256 `de300270cf596de7cf8029c55edd76436c91a60a6ae25db57697abcbfe4a73b1`. It contains the reviewed concise attribution, upstream notebook URLs, pinned source/archive links, exact source and original LICENSE/NOTICE. The existing farm-manager v2 notebook was not modified. No GPU or paid compute was requested.

`transport.py` verifies the exact designated archive, reads live quota and owner submissions, and records dispatch before the official client call. It records uncertain outcomes and requires provider reconciliation rather than blind retries. This is a local duplicate guard, not server idempotency. Every newly authorized immutable payload requires a fresh explicit `--operation-id`; provider readback must contain both that operation ID and the exact `sha256:<digest>` marker before it counts as the same submission. An optional description supports the exact authorized description while requiring the stable operation ID.

`narrow_archive_upload.py` remains a historical recovery helper pinned to the old 57,711-byte `79b407d...` payload. It must not be used for a later archive.

`readback.py` uses ordinary official Kaggle APIs. Credentials stay in the caller's configured runtime; never put them into source, arguments, receipts, or notebook cells. `disclosure.py` builds source disclosure without executing the candidate. Four focused transport/disclosure tests passed at the preparation checkpoint; these do not prove competition acceptance. No LARK games or validation were rerun.

Direct file submission does not require a notebook commit. The public notebook is separately associated code disclosure. Rules observations were supplied by root's live September 7 reading; current quota must always come from provider readback.

Actual provider receipts are under receipts/. Source publication and submission creation succeeded; validation and first hosted matches are monitored separately. The official SDK omits default PENDING status from to_dict output.

`narrow_archive_upload.py` sends only the exact designated archive to the exact provider-returned HTTPS storage URL using a new unauthenticated session. It disables netrc, cookies, redirects, and retries. The managed runtime proxy and CA bundle are applied explicitly while TLS verification remains enabled. A direct connection failed before creation, then a proxy attempt failed certificate verification before creation; their receipts are retained. Signed URLs and account credentials are never written to receipts. The successful receipt records the destination URL hash, payload hash, HTTP status, and absence of Authorization headers.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
