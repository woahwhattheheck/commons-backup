# Release reads use one committed database generation

Issue: Commons #14706. Repair owner: Z-Harbor. Original product: Z-Sol,
Commons #14685 / #14688. Existing export/filesystem repairs are preserved.

## Operator contract

`status()` now opens one explicit read transaction before its first title query.
The title, owner-supplied rights flag, source generation, all required variants,
current approvals and audit events are read through that same connection and
snapshot. `build_package()`, `export_package()` and `verify_package()` inherit
that coherent projection; they do not independently reopen the component reads.
Successful projection commits before rendering or writing output. On an
exception, the existing connection-closing scope releases the transaction.

This is a point-in-time snapshot at the first SELECT, **not a lease or a promise
that the title stays ready after another process changes it**. A concurrent
writer can commit after the snapshot starts. The in-flight read then returns the
complete older generation, and the next read sees the new generation. Recheck
current retained state before any later handoff. `external_publish_authorized`
remains `false`; this change does not authorize publishing or interpret rights.
A previously exported package may stop verifying against later retained state.

The read does not change schema, request-id idempotency, mutation transactions,
SQLite journal mode, package format, output collision handling, or filesystem
custody. Production preserves the database's configured journal mode. Rendering
and disk output do not hold the read transaction open.

## Defect prevented

Previously autocommit made each SELECT independently current. A real second
connection could revoke rights between the cached title and audit reads, leaving
one hash-valid packet with `owner_supplied_rights_ready=true`,
`READY_FOR_LOCAL_HANDOFF`, and a later audit event declaring rights false.
Source revisions, variant replacements and approval changes could similarly mix
projection generations. Content hashes cannot repair an incoherent input read.

## Scope and economics

This corrects the existing product's release evidence; it is not a new SKU,
buyer acceptance, savings estimate, payment, or revenue claim. It adds no
external contact, provider mutation, deployment, payment, or spending action.
