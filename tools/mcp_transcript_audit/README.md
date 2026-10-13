# MCP 2025-11-25 transcript audit

A dependency-free, offline integrity/audit tool for captured Model Context Protocol JSON-RPC sessions. It is deliberately separate from Commons' endpoint-oriented `host/mcp_conformance.py`: this package never opens an endpoint or executes a tool. It verifies the bytes of a capture you already possess.

The auditor is hard-pinned to MCP `2025-11-25` (the CLI has no protocol-version override). The lifecycle checks follow that official lifecycle: initialization is the first interaction, the client sends `initialize`, the server answers with its negotiated protocol version and capabilities, and the client sends `notifications/initialized` before normal operations. Reference: <https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle>.

## Capture format

The capture is JSONL. Each non-empty line contains exactly two fields:

```json
{"direction":"client_to_server","payload_base64":"eyJqc29ucnBjIjoiMi4wIiwiaWQiOjEsIm1ldGhvZCI6ImluaXRpYWxpemUiLCJwYXJhbXMiOnsiLi4uIjoiLi4uIn19"}
```

`payload_base64` is the exact JSON-RPC wire body bytes. Base64 keeps the capture unambiguous even when payloads contain arbitrary Unicode or whitespace. The auditor binds both the exact capture-line bytes and decoded payload bytes by SHA-256.

Directions are `client_to_server` and `server_to_client`.

## What is proved

A PASS receipt proves, for the supplied capture bytes:

- strict UTF-8/JSON parsing with duplicate-key and NaN/Infinity rejection;
- JSON-RPC 2.0 request/notification/response envelope shape;
- string or integer request IDs (bool/null/non-integral/non-finite values are rejected), with exact integral numeric-value correlation and no ID reuse;
- response correlation to the opposite direction with no orphan, duplicate, or unresolved response/request;
- `initialize` as the first interaction;
- required initialize fields and exact `2025-11-25` request/negotiated version;
- client `notifications/initialized` after the successful initialize response and before ordinary operations;
- schema-valid server `notifications/message` logging exceptions before initialization (required level + data);
- bounded JSON nesting and capture/event/line limits that fail closed on hostile input;
- CLI file ingestion is bounded before allocation (8 MiB capture, 32 MiB receipt), requires regular files, opens with `O_NONBLOCK` where the platform exposes it so FIFOs cannot hang before the regular-file check, and uses no-follow/close-on-exec opens where supported;
- deterministic source, line, payload, and receipt hashes.

The durable receipt intentionally omits request parameters, response results, error data, and raw request IDs. It retains method names, counts, line numbers, typed-ID hashes, and content hashes needed to audit correlation without copying business payloads.

This does **not** prove endpoint identity, HTTP headers/session IDs, tool semantics, tool authorization, external side effects, or business correctness. Those require separate evidence.

## CLI

From the Commons repository root:

```bash
python -m tools.mcp_transcript_audit.cli audit \
  tools/mcp_transcript_audit/example_session.jsonl \
  --output /tmp/mcp-audit.json

python -m tools.mcp_transcript_audit.cli verify \
  tools/mcp_transcript_audit/example_session.jsonl \
  /tmp/mcp-audit.json
```

Audit exits `0` for PASS and `3` for HOLD. Verification exits `0` only for an exact recomputation match. Oversized/non-regular input paths (including named pipes on POSIX with `O_NONBLOCK`) are rejected as input errors before content allocation. Input symlinks are not followed on platforms with `O_NOFOLLOW`. Output files are create-exclusive and non-overwriting; existing destinations are not replaced.

## Library

```python
from tools.mcp_transcript_audit import audit_transcript, verify_receipt

source = open("capture.jsonl", "rb").read()
receipt = audit_transcript(source)
```

No network access, account, token, cloud service, or third-party package is required.
