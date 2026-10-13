# Prepare one task for native fallback execution

`host/connected_tool_request.py` translates a public search or URL-read task
into concrete native arguments for the connected tool router. It uses the
existing route facts and the tools actually discovered on the current carrier.
The router still retains account-plan, quota-domain and cooldown observations.

Keep the current tool-name array and generated request beside the private
runtime journal. Prepare a search with the existing task operation ID:

```sh
python host/connected_tool_request.py \
  --routes-file inventory/resources/connected_capability_observations.json \
  --tools-file /private/runtime/current-tool-names.json \
  < /private/runtime/task.json > /private/runtime/request.json
```

The search task supplies `operation_id`, `capability: "search"`, `query`, and
optional `objective` and `search_queries`. A URL task supplies
`capability: "url_read"`, one to five public `urls`, and an optional `objective`.
Parallel bindings additionally require the conversation's existing 32-character
or longer `session_id`; reuse it across turns and search/fetch calls. The helper
does not generate identities or turn a failed direct route into a new session.

Pass the generated request to the router's `dispatch` command, invoke the
returned native tool once, then `resume` with the full response. Follow
[CONNECTED_TOOL_ROUTER.md](CONNECTED_TOOL_ROUTER.md) for that execution loop.
Provider-adapter consumers can include their actual adapter tool names in the
same carrier list and use `run --provider-apis` where compatible.

The helper prepares small basic searches, with no automatic page extraction,
browser action or paid model choice. URL reads select each provider's read
method rather than reusing its search method. Multi-URL reads omit adapters
that only accept a single URL. Only exposed, schema-supported methods are
bound; newly connected unsupported methods stay visible in the catalog.

This prepares a request without making a provider call. Exit 0 returns a usable
binding map; exit 2 explains malformed input or a carrier with no compatible
schema-supported method. Preparing arguments does not establish a ready Free
route, an account balance or a completed provider operation. Direct tool access
remains available.
