# Connected GitHub tree entries

`projectGitHubTreeEntries(response, options?)` projects one retained MCP response without IO, ref resolution, subtree traversal, or file-body decoding.

| Input | Exact payload boundary | Representation / decoding |
| --- | --- | --- |
| Native `mcp__codex_apps__github_fetch` JSON text | `structuredContent.content`, a string | `native_fetch_json_text`; `JSON.parse` |
| Successful `mcp__codex_apps__github_token_connection_github_read` HTTP envelope | `structuredContent.data`, an object; own `status`, `ok`, `data`; integer status 200–299 and `ok: true` | `token_http_tree`; no decoding |

Both require a decoded object with lowercase 40-character `sha`, array `tree`, and boolean `truncated`. Direct REST, text-block, and nested fallbacks are unsupported. JSON text plus a complete HTTP envelope is ambiguous and refused.

```js
const {projectGitHubTreeEntries} = require("./connected_github_tree_entries.cjs");
const view = projectGitHubTreeEntries(retainedTreeEnvelope, {
  source_indices: [0, 2], max_entries: 2, max_total_metadata_chars: 1024
});
```

Requires at least three retained entries.

| Option | Default | Safe-integer bounds |
| --- | ---: | --- |
| `start_index` | 0 | 0–`Number.MAX_SAFE_INTEGER`; ≤ retained count |
| `max_entries` | 10 | 0–100 |
| `max_path_chars` | 4096 | 1–16384 |
| `max_url_chars` | 4096 | 1–16384 |
| `max_total_metadata_chars` | 4096 | 40–1000000 |
| `max_input_chars` | 2000000 | 0–10000000; native JSON string only |
| `max_input_entries` | 10000 | 1–100000 |
| `source_indices` | absent | Increasing, distinct, nonnegative safe integers within retained entries; length ≤ `max_entries` |

Contiguous selection starts at `start_index` and takes up to `max_entries`. Sparse selection accepts `[]` and excludes an explicit `start_index`. Every supplied entry and URL is validated before selection, including omitted rows.

Entries require nonempty string `path`, literal type `blob`/`tree`/`commit`, mode `040000`/`100644`/`100755`/`120000`/`160000`, and lowercase 40-character SHA. Optional `size` must be a nonnegative safe integer; it is copied only when observed. Optional URLs preserve absent/null/string states.

Character bounds count UTF-16 code units. Metadata budget first reserves 40 units for the observed top-level SHA plus each selected entry's whole path, mode, type, and SHA; insufficiency refuses the result. URLs are copied whole in top-level, selected-entry order or omitted with decoded path/count/reason. Later shorter URLs may fit. Nothing is clipped. Numbers, booleans, nulls, keys, and annotation paths consume no metadata-string budget.

`PROJECTED` returns top-level `sha`/`truncated` and ordered `entries[]` with original `source_index` and `decoded_source_path: ["tree", index]`. Decoded paths are separate from `source.envelope_payload_path`, not properties through encoded JSON. Top-level SHA/truncation paths are `["sha"]`/`["truncated"]`.

`coverage` records counts, literal retained type counts, selected indices, omitted ranges `[start, end)`, metadata units and optional-field omissions. `next_index` is a local contiguous offset, null at retained end or for sparse selection. Inclusion flags cover supplied rows only.

Invalid options and out-of-page selection throw `TypeError`/`RangeError`. Malformed, ambiguous, provider-error, or input-limit responses return `entries: []`, an `issue.code`, and status `UNSUPPORTED_REPRESENTATION`, `PROVIDER_ERROR`, or `INPUT_LIMIT`.

Literal SHA/truncation does not verify Git objects, commits, snapshots, repository binding, recursion, or completeness. Representation labels describe admitted shapes and do not authenticate a binding or response origin. Other fields remain withheld.
