# Outbound mutex — legacy/reference CAS

> **Production deprecation:** this package does not provide canonical production
> send authority. Its free-form opportunity key can split one real commercial
> opportunity across aliases. For the canonical closed-schema opportunity/reply
> seam use `revenue/outbound_connector_lease/`; see
> `PRODUCTION_DEPRECATION.md` and
> `../outbound_connector_lease/AUTHORITY.md`. A connector opportunity seam is
> itself not proof of organization-wide mutual exclusion or send authorization.

A duplicate outbound message can destroy a hot lead. This package remains useful
as a reference/local compare-and-swap implementation for one exact **legacy** key.
It must not be used to claim that two independently authored legacy keys describe
different real opportunities.

## Legacy invariant

For one exact legacy key, a writer may model exclusive ownership only while it
owns the current durable lease and the provider snapshot remains unchanged. That
model is not sufficient for a production external mutation.

The legacy lock path is deterministic:

`coordination/outbound/leases/<sha256>.json`

The digest is derived from normalized `opportunity + channel + destination`. The
free-form `opportunity` component is the production defect: semantic aliases can
produce different hashes. The public lease stores only a destination hash; it
never stores the raw email address.

## Historical/reference GitHub CAS protocol

The following describes this package's CAS mechanics for tests, incident analysis
and historical records. It is **not** the current production send protocol.

1. Compute the legacy deterministic key/path with `lease.py key`.
2. Re-read the provider and record a provider snapshot identifier.
3. Initial claim uses create-if-absent for that exact legacy path.
4. Fetch the just-landed lease and verify state/holder/expiry.
5. Re-read the provider and run legacy preflight.
6. A reference caller may model one mutation for that exact key.
7. Replace the lease with `state=sent` using exact-current blob CAS; `sent` is
   terminal for that legacy key.

None of these steps proves that another worker did not mint a different legacy
key for the same real organization/opportunity. Production workers must use the
scoped connector opportunity/reply seam plus every separately required
organization-wide and provider gate.

### Takeover / release

An active legacy lease can be considered for takeover only after expiration. A
released legacy lease can be considered immediately. **Before either takeover,
freshly re-read the provider and require its fingerprint to equal the snapshot
retained by the lease being replaced.** If provider state changed, takeover fails
closed for reconciliation/manual review; the changed generation must never be
adopted as a new automatic-send baseline. This preserves the landed
crash-after-send protection where a prior holder could have sent successfully and
crashed before persisting `state=sent`.

If provider state is unchanged, fetch the current lease file and update using its
exact blob SHA; two contenders using the same prior SHA cannot both win. A `sent`
legacy lease can never be released or taken over.

For GitHub connector seats, the reference primitives are:

- `fetch_file` current legacy lease
- `create_file` initial legacy claim
- `update_file(... sha=<exact current blob SHA>)` release, takeover, or sent receipt

Always fetch again after a successful write. Do not convert that readback into
production send clearance.

## Provider snapshot

The provider snapshot is a non-secret version marker that changes if relevant
provider state changes. For Gmail, use a stable combination that changes when the
thread changes (for example thread/message/history identity from the provider
read). The lease stores only its SHA-256 fingerprint.

A provider change after claim, release, or expiry is not permission to “send
fast” or to establish a replacement baseline. It is a mandatory stop: another
agent or the prospect may have acted, or a prior send may have succeeded before
its durable receipt was written.

## CLI

```bash
python revenue/outbound_mutex/lease.py key \
  --opportunity "Acme / $199 diagnostic" \
  --channel email \
  --destination buyer@example.com

python revenue/outbound_mutex/lease.py claim \
  --opportunity "Acme / $199 diagnostic" \
  --channel email \
  --destination buyer@example.com \
  --holder Z-Forge \
  --provider-snapshot 'thread:abc/history:123'
```

The `claim` command emits canonical JSON for one legacy key. It does not send
mail, claim the remote lease by itself, or establish production authority.
`takeover` likewise requires a freshly read provider snapshot and exits non-zero
if it differs from the lease's retained snapshot.

## Tests

```bash
cd revenue/outbound_mutex
python -m unittest -v test_lease.py
```

The suite includes changed-provider crash-after-send hostiles for both expired
and released legacy leases, plus simultaneous initial claimants and takeover CAS
contenders for one exact legacy key. Exactly one may win each unchanged-provider
race. These tests do not prove semantic identity across free-form opportunity
aliases.
