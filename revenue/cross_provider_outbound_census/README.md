# Cross-Provider Outbound Census — host-authority v2

This gate prevents a provider-local clean result from being mistaken for a clean logical outbound opportunity. The motivating failure was a one-per-person GitHub bounty that appeared untouched on GitHub while an earlier submission already existed through the issue's official Gmail fallback.

The v2 design deliberately removes three facts from claimant control:

1. **current time** comes from the application host;
2. **the complete fallback/alias universe** comes from a retained host registry;
3. **provider history** comes from host-owned provider census adapters.

Claimant JSON contains only the canonical outbound lease seam plus the current intent. `aliases`, `snapshots`, and `trusted_now` are invalid extra fields. There is no authority-bearing command-line interface and no public clock override.

## Trust boundary

`TrustedCensusAuthority` is an application-host interface. The host must choose and instantiate the implementation outside claimant-controlled data and back it with retained registry state plus authoritative connector/provider reads. A caller that can execute arbitrary Python and replace the host authority object is inside the trusted application boundary; deployments that do not trust in-process code must place the authority adapter in a separate service/process or add a cryptographic receipt layer there.

The gate does not pretend a SHA-256 receipt authenticates its source. `source_receipt_sha256` fields bind host-retained provider/registry receipts; authenticity comes from the host authority boundary that supplied them.

## Candidate request

```json
{
  "schema": "commons-cross-provider-outbound-census/request-v2",
  "lease_input": {
    "schema": "outbound-connector-lease/v1",
    "buyer_scope": "example.org",
    "opportunity": {
      "kind": "external",
      "authority": "github.com",
      "id": "owner/repo/issues/16863"
    }
  },
  "intent": {
    "provider": "github",
    "route_sha256": "<sha256 route commitment>",
    "claimant_scope": "swarm-z",
    "claim_scope": "issue-16863",
    "requested_at": "2026-09-14T16:00:00Z"
  }
}
```

No route address, email address, Slack destination, subject, body, or buyer PII is required. Routes remain SHA-256 commitments.

## Required host authority

For each request the host performs three operations:

1. `current_utc()` obtains the host clock;
2. `alias_registry(lease_key)` reads a fresh snapshot of the independently retained fallback registry for the exact canonical lease seam;
3. `provider_census(...)` reads one provider-history generation for **every provider present in that retained registry**, covering the exact registered routes.

Registry snapshots bind the canonical lease seam, a generation ID, observation time, source-receipt commitment, and retained provider-route set. Provider snapshots bind the same seam, the exact registry generation, provider identity, provider generation, observation time, source receipt, route coverage, and concrete historical events. A provider snapshot captured against a different registry generation or lease seam is rejected.

## Fixed freshness / fail closed

Policy windows are constants, not request parameters: current intent 300 seconds; retained-registry snapshot 300 seconds; provider-history snapshot 300 seconds. A complete registry snapshot must be at or after the current intent. Each complete provider snapshot must be at or after both the intent and registry snapshot. Future or stale material HOLDs.

The following also HOLD:

- retained registry unavailable or ambiguous;
- intent route absent from the retained registry;
- missing, throttled, unavailable, or ambiguous provider census;
- incomplete or unknown route coverage;
- prior `PROVIDER_SENT`, `HUMAN_REPLY`, or `AUTO_REPLY` anywhere in the retained alias universe;
- `UNSUBSCRIBE` or `DNR` history;
- hard/soft bounce or provider rejection (route-repair HOLD, not buyer rejection);
- ambiguous provider effect.

Known events remain visible even when provider coverage is incomplete. A throttle cannot erase a known prior touch.

## Exact #16863 hostile

If the retained registry contains both GitHub and Gmail, a candidate cannot omit Gmail because the candidate does not control the registry. Missing Gmail history returns `HOLD`. A Gmail `PROVIDER_SENT` for the earlier email-fallback submission returns `HOLD / EXISTING_TOUCH_HISTORY` even when GitHub itself is clean.

## Authority ceiling

The strongest result is `CLEAR_FOR_DOWNSTREAM_GATES`. Every packet still states:

```json
{
  "external_send_authorized": false,
  "lease_authorized": false,
  "provider_mutation_authorized": false
}
```

The existing `outbound_connector_lease`, pressure/suppression gates, terminal send authority, provider-bound consumer, and post-send forensics remain mandatory.

`verify_census()` re-queries the host authority. A changed registry generation, changed provider generation/history, request drift, packet mutation, or expired `clear_until` fails closed and requires a new preflight.

## No historical authority replay

v1 exposed `--trusted-now` and accepted aliases/provider snapshots in ordinary JSON. That design is permanently superseded. v2 has no authority-bearing CLI and neither `compile_census()` nor `verify_census()` accepts a caller-selected clock. Historical replay belongs in separate analysis tooling and must never produce a current `CLEAR_FOR_DOWNSTREAM_GATES` packet.

## Tests

The focused hostile suite covers all three original SOURCE REDs plus provider failure semantics, route coverage, generation binding, packet tamper, expiry, determinism, strict JSON handling, normal Python, optimized Python, and pycompile.
