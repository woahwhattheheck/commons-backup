# Deploy transport source-binding preflight

This tool answers one narrow question **before** a hosting mutation: does the declared provider action surface have a machine-readable path that can carry the exact immutable source generation we intend to deploy?

It exists because “create a project” or “deploy a site/current project” is not the same thing as binding the intended repository bytes. A provider connector can be perfectly capable of creating infrastructure while still being unable to prove which source generation it will publish.

## Outcomes

- `READY_SOURCE_BOUND_PATH` — at least one declared action can bind an immutable repository commit, artifact digest, file-bundle digest, source-generation ID, or an existing project whose retained planning binding exactly matches the request.
- `HOLD_SOURCE_UNBOUND` — the actions may create/deploy infrastructure, but none can mechanically bind the requested source generation.
- `HOLD_AMBIGUOUS_CAPABILITY` — the action manifest is semantically unknown, contradictory, or names a different provider.

The report always keeps `provider_authenticated`, `project_create_authorized`, `deploy_authorized`, `public_url_proven`, `competition_submission_authorized`, and `payment_or_revenue_proven` exact built-in `false`. Those report bits are constructed source-literally by the compiler rather than copied from the public compatibility descriptor, so ordinary rebinding or in-place mutation of that module global cannot widen compile/verify authority. Verification compares canonical JSON bytes, so JSON `false` cannot be substituted by integer `0`. This is a deterministic planning compiler, not provider authentication or deployment authority.

## Source identity rules

A mutable branch name is never sufficient. Repository binding requires `repo` plus a lowercase 40-hex immutable `commit_sha`. A request naming a repository `subdir` requires a transport action that explicitly declares `repo_commit_subdir`; plain `repo_commit` cannot silently ignore it. Artifact and file-bundle paths use lowercase SHA-256. Requests carrying more than one independent immutable identity family fail closed instead of letting a transport bind only a subset. A project-ID deploy path is READY only when a separate retained project-binding record matches provider, project, and the complete immutable source identity. Free-form prose, URLs in descriptions, project names, and site IDs do not become source bindings by implication.

The request, capability manifest, optional project binding, and compiled report use strict canonical JSON. Raw input is capped at 256,000 bytes and structurally depth-fenced before CPython's recursive decoder; decoded/direct JSON work is then iteratively bounded to 64 levels and 50,000 nodes before recursive canonical serialization. Duplicate keys, floats/nonfinite numbers, unsafe integers, excessive depth/work, lone surrogates, unknown schema fields, unsafe paths, noncanonical repository URLs, and receipt tampering fail closed as stable domain errors. `verify` recompiles the entire report from the inputs and requires canonical byte identity.

## Current-provider fixtures

`fixtures/netlify_current.json` models the connector surface observed on 2026-09-17: create-by-name/team plus deploy-existing-site. Without an exact retained project/source binding, the fixture returns `HOLD_SOURCE_UNBOUND`.

`fixtures/vercel_current.json` models deploy-current-project. With no exact project/source binding, it also returns `HOLD_SOURCE_UNBOUND`.

These fixtures are **caller-retained planning evidence**, not authenticated provider facts. Re-census the real provider before any mutation. Callers that require a freshness bound can add `manifest_policy.evaluation_epoch` + `max_age_seconds` to the request and `captured_at_epoch` to the manifest; missing, future, or stale capture then returns `HOLD_AMBIGUOUS_CAPABILITY`. The timestamps remain caller-retained planning evidence, not provider authentication.

## CLI

```text
python tools/deploy_transport_preflight/preflight.py compile \
  --request request.json --manifest manifest.json [--binding project-binding.json] \
  --out report.json

python tools/deploy_transport_preflight/preflight.py verify \
  --request request.json --manifest manifest.json [--binding project-binding.json] \
  --report report.json
```

`compile` creates the report exclusively and refuses to overwrite an existing path.

## Proof

```text
python -m unittest tools.deploy_transport_preflight.test_preflight
python -O -m unittest tools.deploy_transport_preflight.test_preflight
python -m py_compile tools/deploy_transport_preflight/preflight.py tools/deploy_transport_preflight/test_preflight.py
```

The hostile suite covers the two current unbound provider shapes, positive immutable repo/artifact/bundle paths, exact existing-project matching, cross-provider/project/source transplant, branch-only input, unknown/contradictory action semantics, strict JSON hazards including raw/direct excessive nesting, canonical repository URLs, mutable/rebound authority-descriptor attacks, bool/int authority aliasing, report tamper, typed CLI depth failure without traceback, CLI compile/verify, and create-exclusive output.
