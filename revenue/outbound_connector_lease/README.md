# Connector-native outbound opportunity/reply seam

This package solves one narrow fleet problem: two connector workers can both read
"not sent" for the **same opportunity/reply identity** and cross an external
provider boundary before either send is visible to the other. The connector seam
is therefore an atomic mutation that workers can execute before provider send.

It is **not, by itself, an organization-wide production mutex**. `key.py`
normalizes syntax but does not prove that a caller supplied the one authoritative
organization domain, and distinct opportunities at one organization intentionally
compile to distinct branches. Production policy can therefore require an
independently authoritative organization scope plus a separate organization-wide
atomic pressure/mutex layer before this seam.

The practical connector seam is a deterministic GitHub branch in
`woahwhattheheck/commons`:

```text
outbound-connector-lease/v1/<sha256(canonical seam JSON)>
```

`key.py` only compiles that branch name. `authority.py` validates the exact
closed-schema identity. It cannot prove that the backing Git ref is immutable, so
its current receipt and CLI remain fail-closed:

```text
identity_state=CANONICAL_OPPORTUNITY_SEAM_IDENTITY_VALID
state=HOLD_REF_ROLLBACK_PROTECTION_UNVERIFIED
organization_scope_authority_required=true
organization_wide_mutex_required=true
ref_rollback_protection_required=true
ref_rollback_protection_verified=false
branch_create_authority=false
production_mutex_complete=false
provider_reread_required=true
external_send_authorized=false
```

Neither helper authorizes a send and neither performs a provider mutation.

## Canonical opportunity/reply seam

Every seam contains a caller-supplied organization domain (`buyer_scope`) and one
of three **closed opportunity shapes**. Callers do not supply a free-form
composite opportunity string, so price/contact/route fields cannot be smuggled
into the connector hash schema. The organization domain itself still needs
separate authority; syntactic normalization is not semantic alias resolution.

### External opportunity

Use when an authoritative issuer/source has a durable procurement, project, or
issue ID:

```json
{
  "kind": "external",
  "authority": "issuer.example",
  "id": "rfp-04254"
}
```

`authority` is the source/issuer domain, not the contacted person's mailbox.
`id` is the stable external identifier. A changed recipient, prime contact,
quoted price, draft, or route keeps the same triple: buyer organization + source
authority + source ID. The source identity itself must be authoritative; choosing
an alternate portal/domain spelling is not a safe alias operation.

### Cold outreach

Use exactly:

```json
{"kind":"cold"}
```

for unsolicited organization-level outreach with no durable external
opportunity. This permits one cold connector seam per supplied `buyer_scope`.
It does **not** prove that `example.com`, `www.example.com`, another brand domain,
or a stale alias identify different organizations. That is why authoritative
organization scope and any required organization-wide control come first.

### Human reply event

Use one durable inbound provider event:

```json
{
  "kind": "reply",
  "provider": "gmail",
  "event_id": "<provider-message-id>"
}
```

`provider` is a closed canonical identity, not a caller-chosen transport label.
The v1 registry is exactly `devpost`, `gmail`, `github`, `slack`, and `web-form`.
Aliases and implementation names such as `email`, `googlemail`, `gmail-api`,
`github-api`, `slack-api`, or `webform` are invalid and force HOLD. Supporting a
new provider requires a reviewed source change; callers must never mint a new
spelling to evade an existing reply seam. Existing canonical provider values
retain their original v1 branch hashes.

This lets multiple workers race to answer one new human message while only one
can own that exact event seam. Automatic OOO/redirect messages do **not** become
a new reply opportunity; stay on the original external/cold seam.

## Required production composition and lock order

For any send path exposed to organization-level pile-on, acquire the layers in
this order and never reverse them to race another worker:

1. **Authoritative organization scope.** Resolve the buyer from current retained
   organization identity evidence. A guessed domain, convenient subdomain,
   alternate brand domain, or stale alias mapping is not authority. If canonical
   organization scope is unresolved, `HOLD`.
2. **Organization-wide atomic control.** When the send path requires cross-
   opportunity pile-on prevention, acquire the current **landed and independently
   validated** organization-wide pressure/mutex authority. If that required
   control is unavailable, ambiguous, unmerged, or SOURCE-RED, `HOLD`. Do not use
   this connector seam or `revenue/outbound_mutex` as a substitute.
3. **Canonical opportunity/reply seam.** Compile the exact closed connector
   identity and validate it with `authority.py`. Independently read current host
   rules for the exact candidate ref. The applicable rule generation must be
   active, forbid deletion and update/non-fast-forward mutation, and expose no
   fleet-worker or GitHub-App bypass. Missing, disabled, evaluate-only,
   ambiguous, or bypassable protection means
   `HOLD_REF_ROLLBACK_PROTECTION_UNVERIFIED`; do not create or interpret the ref
   as authority. Only after that independent gate may a connector atomically
   create the exact branch from current `main`.
4. **Provider readback and ordinary gates.** Re-read provider truth immediately
   before mutation. A historical send may predate the branch; if so, HOLD despite
   owning the seam. Apply every independent owner/content/legal/route/cooldown/
   payment gate.
5. **One provider mutation maximum.** Send at most once, immediately persist the
   canonical provider SENT/message outcome, and mark the seam DNR until a new
   human/provider event. If the provider result is ambiguous, do not retry;
   reconcile provider state until success versus failure is authoritative.

If a later prerequisite fails after an organization-wide lease was acquired,
follow that authority's own release/expiry contract. Never improvise an unlock,
mint a new organization spelling, or reverse lock order.

## Ref immutability requirement and cutover

A successful GitHub branch create is not a durable one-touch witness when an
actor can later delete or update that ref. Create → delete → recreate can produce
two successful creates for one semantic seam. Branch absence therefore cannot
distinguish “never acquired” from “acquired and rolled back.”

The repository host, not candidate JSON, must prove rollback resistance. Before
branch-create success can carry authority, read the active rules applicable to
the exact branch and retain that provider generation with the acquisition
receipt. The package itself cannot self-attest those rules; it deliberately emits
`ref_rollback_protection_verified=false` and `branch_create_authority=false`.

Pre-protection v1 history is ambiguous. Activating rules today does not prove an
absent v1 branch was never acquired and deleted yesterday. A production cutover
must use a protected new prefix/generation (for example reviewed v2 rules) or an
independently monotonic retained witness, and must conservatively HOLD old absent
v1 seams. Workers may not mint a v2 spelling on their own to evade an existing
seam.

The checked-in `ref_immutability/ruleset-candidate.json` is configuration input
for administrator review only. Its presence in source is not evidence that the
ruleset is installed, active, applicable, bypass-free, or retained by GitHub.

## Atomic connector-branch result

Interpret the exact GitHub create result strictly **after** independent ref
rollback protection is verified:

- exact create success with verified protection: this worker acquired only the
  opportunity/reply seam prerequisite;
- `422 Reference already exists`: another worker/history owns it -> HOLD;
- timeout, permission error, transport error, or any indeterminate result -> HOLD.

Exact create success while `ref_rollback_protection_verified=false` is also HOLD;
it is not durable branch-create authority. Do not convert an ambiguous create
into success by reading the branch afterward: another worker may have created the
same branch during the ambiguity window. Do not retry under a new buyer-domain
spelling, source authority/ID, contact, price, provider alias, route, or draft.

## Legacy free-form mutex

`revenue/outbound_mutex` is historical/reference CAS only. Its key contains a
caller-authored free-form opportunity label, so semantic aliases can mint
parallel legacy paths. An active/released/sent legacy document can be
conservative evidence, but it never clears the canonical connector seam or a
required organization-wide production control.

## CLI

External opportunity:

```bash
python -m revenue.outbound_connector_lease.key \
  --buyer-scope prime.example \
  --external-authority issuer.example \
  --external-id rfp-04254
```

Cold outreach:

```bash
python -m revenue.outbound_connector_lease.key \
  --buyer-scope example.com --cold
```

One human reply event:

```bash
python -m revenue.outbound_connector_lease.key \
  --buyer-scope example.com \
  --reply-provider gmail \
  --reply-event-id 1abc234
```

Offline identity admission:

```bash
python -m revenue.outbound_connector_lease.authority \
  --json '<exact key.py JSON output>'
```

The authority CLI emits the identity receipt but exits with status 2 while ref
rollback protection is unverified. This is intentional containment, not a syntax
failure. A future provider-bound verifier must be separately reviewed; caller-
supplied rules JSON must never upgrade itself to current host authority.

## Validation

```bash
python -m py_compile \
  revenue/outbound_connector_lease/key.py \
  revenue/outbound_connector_lease/authority.py
python -m unittest -v \
  revenue.outbound_connector_lease.test_key \
  revenue.outbound_connector_lease.test_authority
python -O -m unittest -v \
  revenue.outbound_connector_lease.test_key \
  revenue.outbound_connector_lease.test_authority
```

The helper rejects URLs/emails as organization/source domains, normalizes domain
case/trailing dot/IDNA, rejects duplicate/non-finite JSON, uses exact field sets
for each opportunity kind, rejects price/contact/route/draft/subject fields
inside the external-opportunity schema, and rejects unregistered reply-provider
spellings. Determining the organization's actual primary domain and the
authoritative source ID remains a separate evidence task; package documentation,
`AUTHORITY.md`, and the `outbound-send` skill all require that authority before a
production mutation.
