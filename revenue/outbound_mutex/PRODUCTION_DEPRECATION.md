# Production deprecation — `outbound_mutex`

`revenue/outbound_mutex` is **not** canonical production send authority.

It remains a reference/local CAS implementation and historical artifact from
#14266. Its `lead_key()` accepts a free-form opportunity string. Because two
workers can describe the same commercial opportunity with different labels, one
real opportunity can mint multiple distinct legacy keys.

For the canonical **opportunity/reply** seam use:

- `revenue/outbound_connector_lease/key.py` to compile the closed-schema seam;
- the exact `outbound-connector-lease/v1/<sha256>` GitHub branch create as that
  opportunity seam's atomic prerequisite;
- `revenue/outbound_connector_lease/authority.py` for fail-closed identity
  admission and an explicit statement of what the connector seam does not prove.

The connector seam is not a complete organization-wide production mutex either.
Distinct opportunities and caller-selected buyer-domain aliases can compile to
distinct connector branches. Production policy may therefore require an
independently authoritative organization scope and a separate organization-wide
atomic pressure/lease layer before the opportunity seam. Never treat an
unmerged/SOURCE-RED carrier as that authority.

A legacy lease never grants `external_send_authorized`, including when it is
`active` and held by the current worker. A legacy `sent` record is conservative
historical evidence and may create a HOLD; it never authorizes another send.

Do not delete historical legacy records and do not invent a new opportunity
spelling to evade an existing connector seam. Provider history must still be
re-read immediately before external mutation, and ambiguous provider outcomes
must be reconciled rather than retried.

See `../outbound_connector_lease/AUTHORITY.md` for the scoped connector contract
and lock-order requirements.
