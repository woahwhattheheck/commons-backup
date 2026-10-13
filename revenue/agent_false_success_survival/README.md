# Agent False-Success Survival Proof

A dependency-free, offline diagnostic for a specific agent failure mode: transport-level success is reported while the response is actually an HTML/login/error page, malformed JSON, a JSON-RPC error, an MCP tool error, or another payload that cannot safely authorize semantic success.

The proof consumes captured exchanges; it performs **no live probing** and accepts **no credentials or HTTP headers**. Raw bodies remain in the input bundle. The emitted receipt contains content digests, bounded semantic facts, and deterministic policy decisions.

## Decision contract

A complete matrix requires nine declared families: `HTTP_200_HTML`, `HTTP_200_LOGIN_HTML`, `HTTP_200_MISLABELED_HTML`, `HTTP_NON_2XX`, `JSON_RPC_ERROR`, `MCP_TOOL_ERROR`, `MCP_WRAPPED_HTML`, `MALFORMED_JSON`, and `VALID_CONTROL`.

`SURVIVED` means only that every supplied captured client disposition matched this fixed policy over the complete matrix. It is **not** a production, security, vendor, SLA, or compliance certification.

The recovery policy fails closed on the source-review defects found in the predecessor PR:

- JSON-RPC responses are bound to an explicit expected request/response ID. SSE may contain notifications, but cross-ID, missing, or duplicate correlated terminal responses are rejected.
- Accepted MCP tool content is intentionally narrow: a non-empty list of exact `{type:"text", text:<Unicode scalar string>}` blocks. Unknown/image/audio/resource blocks do not mint a valid control; extend the policy first if those variants need proof coverage.
- HTML document roots are detected even after benign text prefixes inside MCP text content; structural login-page markers are also rejected without treating ordinary prose about HTML as an error page.
- Lone UTF-16 surrogates are rejected before canonical receipt generation, and residual canonicalization failures become structured proof errors.
- CLI reads bind the retained inode/generation across `lstat -> open(O_NOFOLLOW) -> fstat/read/fstat -> lstat`, including mode, link count, size, nanosecond mtime, and nanosecond ctime; same-size in-place mutation and path rebinding fail closed.
- `source_sha256` and `client_event_sha256` are explicitly **caller-provided, unverified commitments**, not authenticated evidence roots. Reusing one commitment for contradictory semantic generations is rejected. Independently authenticated provenance requires a separate retained-artifact/root layer.

## Schema v2

Every case includes `expected_jsonrpc_id` in addition to status, media type, bounded base64 body, observed client disposition, and the two caller commitments. Boolean IDs are forbidden; IDs are bounded non-negative integers or safe strings. This v2 bump is intentional because the predecessor v1 never landed and lacked correlation authority.

## CLI

```bash
python -m revenue.agent_false_success_survival demo revenue/agent_false_success_survival/fixtures/synthetic_capture.json
python -m revenue.agent_false_success_survival compile capture.json --out proof.json
python -m revenue.agent_false_success_survival verify capture.json proof.json
```

`compile` is create-exclusive: it refuses to overwrite or follow an existing output. `verify` recomputes the entire proof from the original capture bundle instead of trusting receipt flags.

## Fixed commercial shape

**Same-Day Agent Survival Proof — $2,500 fixed scope — `PROPOSED_NOT_ACCEPTED`.**

Inputs: a bounded captured matrix from the client/system under test, client build/version, expected JSON-RPC correlation IDs, and caller-provided source/client-event commitments. Deliverables: deterministic proof JSON, case-by-case false-success findings, replayable acceptance checks, and a concise remediation map keyed to transport/media-type/JSON-RPC/MCP/correlation boundaries.

Exclusions: live production probing, credentials, customer-data extraction, penetration testing, provider/account mutation, code deployment, or guarantees about uncaptured routes. Remediation/implementation work is separately scoped. No issue, PR, email, silence, or technical finding constitutes buyer acceptance; payment/cash/revenue remain literal provider facts only.

## SigNoz target overlay

`targets/signoz.json` is internal research/positioning metadata only and permanently carries `external_send_authorized=false`. It maps public first-party evidence to the diagnostic hypothesis. Before any contact, re-read live Slack ownership and mailbox/provider history, acquire the fleet's single-writer Muse selection for the exact target/thread, and make at most the selected bounded outbound action.

## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)
