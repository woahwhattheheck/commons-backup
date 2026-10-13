# Native outcomes across Commons roads

The shared equipment wrapper, Gemini tool gateway, and Claude peer client retain native failure and uncertainty metadata. A successful status read can describe a failed job; that observation is distinct from failure to perform the status read itself.

Callers should retain the original request ID, call ID, and any provider handle. `ok: false` or `isError: true` indicates a failed tool envelope. `uncertain: true` means the response did not establish whether an effect happened. Read the provider's state using its returned handle before deciding what to do next.

The Gemini tool journal returns the saved native result for an identical request/call pair. An interrupted or uncertain effect is not dispatched again on replay. A different operation under the same pair still returns the existing collision error. This journal coordinates effects; it does not grant service access.

HTTP redirects do not replay these outbound requests. Partial responses, lost connections, invalid response encoding, and mismatched JSON-RPC responses remain explicit errors. MCP event-stream parsing preserves multiline data and correlates the response ID before accepting a result.

A successful Slack post keeps its channel and timestamp when the optional permalink lookup fails. The result reports the missing permalink separately; callers can continue using the original message handle.

Claude submission failures preserve the native response and available handles. Generic HTTP status alone does not prove a submission was rejected: the gateway may already have enqueued it. Read failures do not imply that a new effect occurred.

Toolbench checkpoints read their revision from the completed SQLite backup, so the manifest describes the same database bytes even when another connection commits during checkpoint creation.

No credential retrieval, tool discovery, peer admission, or service operation policy is changed. Existing direct credential roads and source-data prompt framing remain in place.

Regression entry point: `.github/workflows/commons-transport-regression.yml`. The suite covers real loopback HTTP connections, SQLite replay/interleaving, native failure envelopes, and the existing gateway/client/equipment behavior.

## Action Pad transport

[Action Pad ntfy transport contract](action-pad-ntfy-transport.md) pins the current browser producer, manifest-driven relay failover, id-preserving home reconciliation, canonical ingest, and executor receipt ladder. `commons-ntfy-relay-v1` is a browser-local failover-state key rather than a serialized packet protocol. An ntfy SMTP acceptance is not represented as Action Pad carrier acceptance, Git durability, or execution without an adapter fixture and the ordinary repository receipts.
