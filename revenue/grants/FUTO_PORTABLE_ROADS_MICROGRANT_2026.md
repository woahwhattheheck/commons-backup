# FUTO microgrant application — Commons Portable Roads Bundle

Status: application packet for **new future work**; not an award and not booked revenue.

Sponsor: [FUTO Grants](https://futo.tech/grants)  
Published microgrant range: **$1,000–$5,000 one-time**  
Requested amount: **$5,000**  
Project: [Commons](https://github.com/woahwhattheheck/commons)  
License: Apache-2.0

## One-sentence proposal

Build **Portable Roads Bundle v1**, an open, vendor-neutral way to export an agent workflow's tool/resource schemas and nonsecret transport metadata from Commons, verify the bundle completely offline, and import it into generic MCP/HTTP action roads so a user can move working automation between runtimes without rewriting it around a proprietary agent SDK or persisting credentials.

## Why this belongs in Commons

Commons already provides a public, link-addressable action surface whose core model is intentionally not a closed roster, login wall, or single model-provider runtime. The next missing portability layer is a durable, documented representation of the *roads themselves*: what tools/resources exist, how their schemas are shaped, what transport family they use, and what nonsecret configuration is required to rebind them somewhere else.

Today a useful agent workflow can still become de facto captive to one harness because its tool catalog and connection metadata are represented in provider-specific configuration. Portable Roads Bundle makes that configuration inspectable, movable and testable outside the original harness.

This proposal is for work that does **not** exist yet. It does not seek retroactive reimbursement for the current Commons codebase.

## Deliverable

A small Apache-2.0 reference implementation and specification with four parts:

1. **`roadpack-v1` manifest format**
   - Tool and resource names, descriptions and input/output schemas.
   - Transport family and endpoint metadata needed to rebind a road.
   - Capability/provenance fields so a consumer can explain where a road came from.
   - Authentication represented only as symbolic requirements (for example `env:SLACK_TOKEN`), never credential values, cookies, authorization headers or encrypted secret blobs.
   - Stable canonical serialization for deterministic diffing and review.

2. **CLI reference implementation**
   - `roadpack export` — emit a bundle from supported Commons/MCP metadata.
   - `roadpack verify` — validate schema, provenance and secret-safety without network access.
   - `roadpack import` — bind a valid bundle to a supported local/reference road.
   - Human-readable diagnostics for unsupported capabilities rather than silent coercion.

3. **Two provider-independent reference transports**
   - MCP Streamable HTTP tool/resource catalog binding.
   - Plain HTTP/JSON action binding for services that do not expose MCP.
   - Neither adapter depends on an OpenAI, Anthropic, Google or other model-vendor SDK.

4. **Offline interoperability fixture + migration guide**
   - Synthetic fixture service with at least 25 tools/resources and representative nested schemas.
   - Round-trip tests proving names, descriptions and schemas survive export → verify → import.
   - Secret-safety tests proving credential values/authorization headers cannot enter a valid bundle.
   - A documented migration walkthrough showing the same fixture bundle bound through both reference transports.

## Acceptance criteria

The milestone is complete when all of the following are true on a clean checkout:

- A fixture catalog containing **at least 25 tools/resources** exports to a `roadpack-v1` bundle and imports with no loss of tool/resource name, description or declared JSON schema.
- `roadpack verify` succeeds with networking disabled for a valid bundle and returns a nonzero result for malformed schema/provenance.
- Secret-safety regression tests reject literal authorization headers, cookies, bearer tokens and credential values while allowing symbolic secret requirements.
- The same fixture is exercised through both MCP Streamable HTTP and plain HTTP/JSON reference bindings without any model-provider SDK.
- Documentation includes format specification, threat model, migration walkthrough, extension rules and a versioning policy.
- The implementation and documentation are merged into the public Apache-2.0 Commons repository.

## Scope boundaries

This microgrant would **not** fund a hosted SaaS, model usage, proprietary connector licenses, customer data ingestion, credential brokerage, or a rewrite of Commons. It would fund the narrow portability layer above. The test corpus is synthetic and the verifier is designed to work without external services.

The format also does not attempt to standardize arbitrary agent prompts or hidden model state. It covers explicit action/resource interfaces and the minimum nonsecret metadata required to move them.

## Four-week work plan

**Week 1 — specification + secret model**  
Freeze `roadpack-v1` fields, canonical serialization, symbolic secret references, schema validation and threat model.

**Week 2 — export/verify CLI + fixtures**  
Implement exporter/verifier, 25+ tool/resource synthetic service and deterministic round-trip/negative tests.

**Week 3 — import + two reference transports**  
Implement MCP Streamable HTTP and plain HTTP/JSON bindings with explicit unsupported-capability diagnostics.

**Week 4 — interoperability hardening + release**  
Run clean-checkout acceptance suite, write migration/extension/versioning docs, publish a tagged release and example bundle.

## Funding use

Requested: **$5,000 one-time microgrant** for the four-week milestone above. The grant supports implementation, interoperability fixtures/tests, documentation and release work. No paid cloud/model dependency is required for the deliverable.

## Why FUTO

FUTO describes its grants as supporting technology that gives users control over their computing and challenges concentrated platform control. Portable Roads Bundle targets a narrow but practical form of lock-in: an automation can be nominally built from open protocols while its usable tool configuration remains trapped inside one agent vendor's harness. This project makes that configuration inspectable, exportable and runnable through provider-independent roads.

A user should be able to change the model or runtime that reasons over their tools without rebuilding the tools themselves or handing a new vendor a serialized credential cache. The artifact is intentionally small, source-available under the project's existing Apache-2.0 license, and useful without a Commons-hosted service.

## Public references

- Commons repository: https://github.com/woahwhattheheck/commons
- Commons public door: https://woahwhattheheck.github.io/commons/
- License: https://github.com/woahwhattheheck/commons/blob/main/LICENSE
- FUTO grants: https://futo.tech/grants
