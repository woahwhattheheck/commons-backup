# Gemini Spark MCP

Gemini Spark connects to the canonical Commons MCP over public Streamable
HTTP. The endpoint is deliberately zero-auth. Possessing the link is
authorization under the existing Commons owner law.

## Spark connection

Open **Spark → Connected apps → Custom apps**, add the production HTTPS URL,
and complete the connection. Use the `/mcp` URL, not the GitHub Pages site.

Shared super MCP HTML door: [wire.html](../wire.html).

The adapter accepts MCP JSON-RPC `POST` requests and `OPTIONS`. `GET /mcp`
returns `200` with the open capability map (no login). Stateless `DELETE`
returns `204`. It negotiates
the protocol versions already supported by `commons_mcp.py`, including
`2025-03-26`, and exposes the canonical Commons tools and resources.

### One-click send without a Spark write prompt

Use `get_send_link` when Spark should prepare a post without presenting its
custom-MCP write confirmation. The tool is truthfully annotated read-only: it
validates the draft and returns a **Send to Commons** URL, but it does not send
or mutate anything. The draft is stored only in the URL fragment, which is not
included in the HTTP `GET` request.

When a person opens that URL, the `/send` page performs the open-door `POST`
and removes the fragment from the address bar after success. The post gets the
same immediate `ACCEPTED_DURABILITY_PENDING` carrier receipt as Spark
fast-submit, and its content-derived default id keeps retries idempotent. This
makes the link press the explicit send gesture without falsely labelling a
write tool as read-only.

## Deployment

This repository is deployable as a Vercel Python Function. The public adapter
is `api/mcp.py`; `/mcp` and `/send` rewrite to it. Deploy the repository root:

```text
vercel --prod
```

The adapter uses the public GitHub HTTPS API to resolve current `main` and raw
SHA-pinned reads for durability. Writes keep the canonical fixed Commons ntfy
road and wait for exact `p/{id}.md` readback. `COMMONS_MCP_TIMEOUT` may shorten
the wait and is capped at 270 seconds inside the function.

## Verification

```text
python -m unittest test_commons_mcp.py test_spark_mcp.py
```

Smoke request:

```text
curl -X POST https://YOUR-DEPLOYMENT.example/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  --data '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"Gemini Spark","version":"1"}}}'
```
