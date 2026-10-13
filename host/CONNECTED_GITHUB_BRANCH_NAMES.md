# Connected GitHub branch names

`projectGitHubBranchNames(response, options?)` is a pure reader for an unchanged native `mcp__codex_apps__github_search_branches` MCP response: `structuredContent.branches[]` contains objects with a nonempty string `branch`. It performs no provider reads or writes. REST, token, and JSON-text fallback representations are unsupported.

```js
const {projectGitHubBranchNames} = require("./connected_github_branch_names.cjs");
const result = projectGitHubBranchNames(retainedNativeBranchSearch, {
  source_indices: [0, 2], max_branches: 2, max_total_name_chars: 128
});
```

The caller retains the original envelope privately; this example requires at least three rows.

| Option | Default | Accepted values |
| --- | --- | --- |
| `start_index` | `0` | Safe integer, 0–`Number.MAX_SAFE_INTEGER`; cannot exceed retained count |
| `max_branches` | `10` | Integer, 0–100 |
| `max_name_chars` | `4096` | Integer, 1–16384 |
| `max_total_name_chars` | `4096` | Integer, 0–1000000 |
| `max_input_branches` | `10000` | Integer, 1–100000 |
| `source_indices` | Absent | Increasing, distinct, nonnegative safe integers within retained rows; length ≤ `max_branches` |

Without `source_indices`, selection starts at `start_index` and takes up to `max_branches`. Sparse selection accepts `[]` and cannot accompany an explicit `start_index`. All supplied rows are validated before selection, including omitted rows.

Names are copied whole. Character limits count JavaScript UTF-16 code units. `max_name_chars` applies to every supplied name; `max_total_name_chars` applies to the selected sum. Exceeding either budget refuses the result; names are never clipped or partially returned.

On `PROJECTED`, `branches[]` preserves provider order and contains `branch`, `branch_chars`, original `source_index`, row `source_path`, and `branch_source_path`. Paths are arrays: `["structuredContent", "branches", index]` and the same path plus `"branch"`. `source.representation` is `native_branch_search`.

`coverage` reports retained/returned/omitted counts, selected indices, returned name characters, and omitted index ranges `[start, end)` over this retained page. `all_retained_names_included` concerns only supplied rows. Contiguous `next_index` is a local selection offset, or null at the retained end; sparse selection always returns null. It is not a provider cursor.

`provider_cursor` describes only an observed `cursor`: `present`, path `["structuredContent", "cursor"]`, type `absent`/`null`/`string`, and `retained_chars` for strings, including empty strings. `value_withheld` is true; the actual opaque value is never copied. Absent or null cursors do not establish pagination or completeness. Forwarding a cursor requires the caller's retained original response.

Invalid options throw `TypeError` or `RangeError`; out-of-page selection also throws `RangeError`. Refusals return no names (`branches: []`) and an `issue.code`:

- `UNSUPPORTED_REPRESENTATION`: `EXPECTED_CALL_TOOL_RESULT`, `EXPECTED_NATIVE_BRANCH_SEARCH`, `INVALID_BRANCH_NAME`, `INVALID_CURSOR`.
- `PROVIDER_ERROR`: `PROVIDER_ERROR_ENVELOPE`, `PROVIDER_ERROR_PAYLOAD`.
- `INPUT_LIMIT`: `BRANCHES_LIMIT`, `NAME_CHAR_LIMIT`, `SELECTED_NAME_CHAR_BUDGET`.

No SHA, protection, default-branch status, repository binding, snapshot, or branch-state inference is made. Ref resolution is not performed; other fields remain withheld.
