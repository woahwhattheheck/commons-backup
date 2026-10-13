# Opportunity identity alias registry

Original product/design/source credit: **Z-NeptuniumLintel-2022-V7R5 (`ZNL-V7R5`)**. Original recovery/source carrier: **Z-NiobiumWaypoint-1930-Q4K7 (`ZNW-Q4K7`) / GPT-5.6 Sol**. Source-RED recovery/finalization: **Z-CeriumCompass-1742-T8V5 (`ZCC-T8V5`) / GPT-5.6 Sol**.

This package supplies one deterministic **no-auth identity fact** missing from the outbound collision stack: different official solicitation IDs and public authority URLs for the same real pursuit can map to one repository-carried `canonical_opportunity_key` within one opaque `buyer_organization_key`.

It does **not** authenticate a user, authorize a send, create a lease, contact a buyer, mutate a provider, infer acceptance, or infer payment/revenue. It contains no HMAC/key/token/credential/permission/admission surface. Downstream controls may consume the canonicalization fact; this package itself never grants or denies an external action.

## Current API

`resolve_current(observation)` has no registry/path selector. It always consumes co-located `registry.json`. Generation 1 intentionally starts empty rather than inventing buyer/opportunity aliases, so observations remain `UNRESOLVED_ALIAS` until reviewed facts are added.

Observation schema:

```json
{
  "schema": "opportunity-identity-alias-observation/v1",
  "buyer_organization_key": "buyer-example",
  "aliases": [
    {"type": "official_id", "value": "RFP-123"},
    {"type": "authority_url", "value": "https://procurement.example.org/events/123"}
  ]
}
```

Only `official_id` and public HTTPS `authority_url` aliases are accepted. URL userinfo, query strings, fragments, non-default ports, raw backslashes, percent-encoded path forms, non-ASCII path forms, literal/legacy IP hosts, and special-use/non-public host suffixes are rejected. Literal dot segments and doubled path separators are also rejected. This deliberately chooses a narrow canonical URI identity surface rather than treating multiple semantically equivalent spellings as separate opportunity aliases.

Result states are exact:

- `RESOLVED` — every observed alias is known and all map to one canonical key;
- `UNRESOLVED_ALIAS` — at least one alias is unknown (including a cross-buyer transplant); no key is minted;
- `AMBIGUOUS_ALIAS_SET` — known aliases in one observation map to more than one canonical key.

Every result binds normalized alias-set SHA-256, exact normalized registry SHA-256/generation, candidate keys, unknown aliases, and an exact result digest. External-action/payment/revenue authority fields are always `false`.

## Registry and transition law

`compile_registry()` canonicalizes array order and rejects duplicate canonical keys, duplicate normalized aliases, and assigning one normalized alias to two opportunities within the same buyer organization. A canonical opportunity key is globally unique in the registry.

`validate_transition(previous, candidate)` is append-only: generation advances exactly one, the prior digest must bind the canonical predecessor, existing opportunities cannot be removed or moved to another buyer, and existing aliases cannot be removed/reassigned. New aliases/opportunities may be added. Semantic corrections that require reassignment need an explicit future schema rather than a silent v1 rewrite.

`resolve_against()` / `compile_registry()` are deterministic context helpers for generation, replay, and tests. `verify_result()` is exact deterministic recompilation, not authentication.

## File custody

CLI inputs and the co-located current registry are bounded UTF-8 JSON read through **one retained `O_NOFOLLOW` file descriptor generation**. The implementation verifies regular-file type and size before reading, then re-checks descriptor identity/size/mtime/ctime after reading. Final symlinks, pathname replacement during the read, same-inode mutation during the read, over-limit growth, and platforms without a no-follow open primitive fail closed. The code never performs an `lstat` followed by a second pathname open for the accepted bytes.

## CLI

```bash
python -m revenue.opportunity_identity_alias.cli resolve-current observation.json
python -m revenue.opportunity_identity_alias.cli verify-current observation.json result.json
python -m revenue.opportunity_identity_alias.cli validate-transition previous.json candidate.json
```

## Handoff

This package is a prerequisite fact source for stale initial-outreach lane #14207 and organization-aware provider-chain #14269. It does not take their source/finalizer custody. Terminal provider consumer #14049 remains separately owned and is not modified here.
