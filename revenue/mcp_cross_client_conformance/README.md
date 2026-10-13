# MCP Cross-Client Conformance Kernel

Buyer-neutral internal delivery infrastructure for evaluating **frozen evidence** from multiple MCP clients against one explicit release manifest.

It is intentionally not an MCP client, proxy, gateway, production agent, or infrastructure operator. It performs no network I/O and cannot mutate an MCP server. Integrations must collect observations separately and pass only frozen evidence into this package.

## Problem boundary

A cross-client MCP release can appear healthy in one client while silently omitting a tool, negotiating a different protocol version, returning stale resource bytes, or failing discovery in another. An empty or unreachable listing is especially dangerous if interpreted as “zero capabilities” rather than an unverified measurement.

The kernel binds every observation to one server-build identifier, one fixture identifier and SHA-256, a declared supported-protocol set, an exact required client-profile set, an exact tool inventory, separately hashed canonical-JSON and raw-byte resources, and a zero-production-action authority ceiling. A server-build, fixture, or required-client binding failure is aggregate-fatal even when a hostile observation otherwise resolves to its expected `REJECT`, `HOLD`, or `UNVERIFIED` disposition.

It requires at least two clean runs per client and verifies deterministic replay. Exact duplicate observation IDs may collapse; the same ID with different bytes fails closed.

## Dispositions

- `PASS`: clean evidence exactly matches the manifest.
- `HOLD`: evidence is present but mismatches the frozen release contract.
- `REJECT`: protocol negotiation was explicitly unsupported or downgraded.
- `UNVERIFIED`: evidence could not be measured, for example an unreachable listing.

`UNVERIFIED` is never converted into an empty tool or resource set.

## Synthetic acceptance

`acceptance.py` creates a five-client, two-clean-run fixture plus hostile cases for unsupported protocol, silent downgrade, omitted tool, stale JSON schema hash, corrupted raw resource hash, and unreachable listing.

A PASS requires all ten clean runs to pass, both runs for each client to produce the same conformance signature, every hostile case to resolve to its manifest-declared fail-closed disposition, every observation to remain bound to the frozen server build/fixture/required-client universe, and production action count to remain zero.

```bash
python -m unittest revenue.mcp_cross_client_conformance.test_kernel -v
python -O -m unittest revenue.mcp_cross_client_conformance.test_kernel -v
python -m revenue.mcp_cross_client_conformance.acceptance
```

The acceptance CLI emits canonical JSON containing the manifest, frozen observations, deterministic report, and receipt verification flag.

## Authority ceiling

This package does **not** prove provider authenticity from hashes alone. The acquisition path that supplies server build identity, client identity, protocol transcript, tool listing, and resource bytes must be independently trusted and scoped.

The kernel does not log into or execute a live MCP client/server; use production credentials or customer data; authorize infrastructure mutation; alter gateway/RBAC/policy authority; certify security/compliance/interoperability/production readiness; contact a buyer; deploy code; accept a contract; or recognize revenue.

It is an evidence evaluator for a later integration boundary.
