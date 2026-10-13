# Canonical outbound opportunity/reply seam authority

## Decision

`revenue/outbound_connector_lease/` defines the canonical **opportunity/reply
identity** for external outbound work. It is not, by itself, the sole production
mutex for an organization, and its Git branch is not durable authority until the
repository host independently proves rollback-resistant ref rules.

The connector seam identity is:

```text
outbound-connector-lease/v1/<sha256(canonical seam JSON)>
```

An exact successful GitHub create can become the decisive atomic event for that
seam only after active host rules for the exact branch are independently read and
shown to block deletion, update, and non-fast-forward mutation without a fleet or
GitHub-App bypass. A pre-existing ref, any transport error, ambiguous create,
missing rule evidence, evaluate-only rule, or bypassable rule is `HOLD`.

Current offline admission is therefore deliberately:

```text
identity_state=CANONICAL_OPPORTUNITY_SEAM_IDENTITY_VALID
state=HOLD_REF_ROLLBACK_PROTECTION_UNVERIFIED
ref_rollback_protection_required=true
ref_rollback_protection_verified=false
branch_create_authority=false
production_mutex_complete=false
external_send_authorized=false
```

This layer also does not claim to serialize every simultaneous opportunity at one
organization and does not prove that a caller-supplied domain is the
organization's one authoritative identity.

## What this fixes

Commons also contains `revenue/outbound_mutex/`, merged by #14266. Its reference
CAS machinery hashes caller-authored free-form `opportunity + channel +
destination`. Two workers can therefore describe one commercial situation
differently and obtain different legacy lease paths.

Example of the forbidden split:

```text
SigNoz / $2,500 survival proof
signoz agent reliability pilot
```

for the same route/destination. The closed connector schema removes price,
recipient, route, subject and draft from one opportunity/reply identity, so those
labels cannot mint parallel canonical opportunity seams.

A `revenue/outbound_mutex` document — active, released, sent or otherwise — never
satisfies the canonical opportunity/reply seam prerequisite. Historical legacy
records remain conservative evidence; they are not send clearance.

## Ref rollback defect and containment

A branch is mutable state unless GitHub mechanically says otherwise. A writer can
create a non-default ref, delete it, and create the same ref again. Both creates
can succeed. Branch absence then cannot distinguish “never acquired” from
“acquired, deleted, and rolled back.”

Source documentation and receipts must not call such a ref permanent one-touch
state. `authority.py` validates only identity and always withholds ref authority.
The checked-in ruleset candidate is non-authoritative configuration material; it
cannot prove that an administrator installed an active, applicable, bypass-free
ruleset.

Before interpreting branch create success, the executor must retain independent
host evidence for the exact candidate ref. Missing, disabled, evaluate-only,
ambiguous, or bypassable protection means
`HOLD_REF_ROLLBACK_PROTECTION_UNVERIFIED`.

Pre-protection v1 absence is permanently ambiguous without another monotonic
witness. A reviewed cutover should use a protected new prefix/generation or an
independently retained append-only record. No worker may mint v2 merely to evade
an existing v1 seam.

## Explicit limits

The connector key compiler performs syntactic normalization, not semantic
organization resolution. These are deliberately different connector seams:

- one buyer scope with `cold` versus an `external` opportunity;
- one buyer scope with external opportunity A versus external opportunity B;
- `example.com` versus `www.example.com` as caller-supplied buyer scopes;
- two syntactically valid authority domains chosen for the same real source.

Therefore even protected exact branch-create success does **not** prove
organization-wide mutual exclusion. `authority.py` makes the current ceiling
mechanical with:

```text
organization_scope_authority_required=true
organization_wide_mutex_required=true
ref_rollback_protection_required=true
ref_rollback_protection_verified=false
branch_create_authority=false
production_mutex_complete=false
external_send_authorized=false
```

This repair does not invent a replacement organization-wide lock, self-attest
repository rules, or bless an unmerged/SOURCE-RED carrier as authority.

## Required composition and lock order

When production policy requires both organization-wide pile-on prevention and an
opportunity/reply seam, acquire them in one order only:

1. **Authoritative organization scope first.** Resolve the buyer to retained,
   current organization identity evidence. A guessed domain, convenient
   subdomain, alternate brand domain or stale alias mapping is not authority.
2. **Organization-wide atomic mutex second.** Use the current landed and
   independently validated organization-level pressure/lease authority. If none
   is available for a path that requires one, `HOLD`; do not substitute the
   connector seam or any SOURCE-RED/unmerged carrier.
3. **Host ref protection third.** Read the rules currently applicable to the
   exact candidate branch. Require active no-bypass deletion and update/non-fast-
   forward protection and retain that provider generation. Otherwise HOLD.
4. **Canonical opportunity/reply branch fourth.** Compile the closed connector
   identity and atomically create exactly its protected GitHub branch.
5. **Provider readback next.** Re-read authoritative provider history immediately
   before mutation. Any relevant change means stop and re-evaluate.
6. Apply every independent owner/content/legal/route/cooldown/payment gate, then
   perform at most one provider mutation.
7. Persist the canonical provider outcome immediately. Ambiguous provider outcome
   means reconcile; never retry blindly.

Never acquire these layers in reverse order to race another worker. If a later
prerequisite fails after an organization-wide lease was acquired, follow that
authority's own release/expiry contract; do not improvise a new unlock or mint a
variant identity.

## Mechanical admission

`revenue/outbound_connector_lease/authority.py` accepts only exact compiled output
from `key.py`, recomputes branch/digest, rejects extra identity fields, and
explicitly rejects the #14266 legacy lease shape.

A successful identity parse means only:

```text
CANONICAL_OPPORTUNITY_SEAM_IDENTITY_VALID
```

The CLI exits 2 and the operational state remains:

```text
HOLD_REF_ROLLBACK_PROTECTION_UNVERIFIED
```

until an independently reviewed provider-bound path proves the host rule state.
Caller-supplied rules JSON cannot upgrade itself. Identity validation explicitly
does not certify ref immutability, organization identity, organization-wide
exclusivity, production readiness, or external-send authority.
