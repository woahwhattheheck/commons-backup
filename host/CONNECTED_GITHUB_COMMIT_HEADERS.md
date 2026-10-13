# Inspect retained commit headers

[connected_github_commit_headers.cjs](connected_github_commit_headers.cjs)
provides a bounded view of the actual native `github_fetch_commit` or approved
token commit-read CallToolResult. It reads the observed envelope, preserves exact original
source paths and makes no tool, network or filesystem call.

```javascript
const {projectGitHubCommitHeaders} =
  require('./host/connected_github_commit_headers.cjs');
const overview = projectGitHubCommitHeaders(retainedResponse, {
  expected_commit_sha: requestedCommitSha,
  source_indices: [0, 2],
  max_files: 2,
  max_message_chars: 0
});
```

Load the dependency-free CommonJS module normally or use its complete
identified source with the existing in-memory module loader. Keep the complete
original response separately. The function does not mutate it or the options.

## Envelope paths

| Representation | Commit/file root | Message path | Actor fields |
| --- | --- | --- | --- |
| Native `github_fetch_commit` | `structuredContent.commit` | `structuredContent.commit.message` | Root `author`/`committer` login and ID. |
| Token `GET /repos/{owner}/{repo}/commits/{sha}` | `structuredContent.data` | `structuredContent.data.commit.message` | Root `author`/`committer` login and ID. |

The token envelope must have a boolean `ok`, integer HTTP `status` and object
`data`. A failed or non-2xx status returns `PROVIDER_ERROR`, with the observed
status, before inspecting its data. Successful data must contain an object
`commit`, a complete lowercase SHA, its nested string message and a files array.
The token view preserves only the present literal root `url` and `html_url`
headers. It does not derive repository names or timestamps, substitute the
nested Git author/committer names or emails for account identities, or include
tree, parent, verification, stats or file-patch bodies. Missing root account
actors stay missing; null actors remain null. Every returned path addresses
the original envelope rather than a normalized intermediate object.

## Retained metadata

The identified commit object must have a complete lowercase 40-character
`sha`, the native or nested token string message and a `files` array. An optional
`expected_commit_sha` compares that actual returned identity with the caller's
requested identity; a mismatch returns `IDENTITY_MISMATCH`.

The view returns the literal SHA and present native
`repository_full_name`, `url`, `html_url`, `display_url`
and `created_at` fields. These optional fields must be strings or null.
They are not normalized or derived. `metadata_source_paths` points to each
original field under `["structuredContent", "commit"]`.

Present author and committer objects contribute only their observed
`login` and `id`, with exact source paths. Null actors and nullable fields
remain null. IDs retain the original safe nonnegative integer or decimal
string representation. Names, email addresses, avatars and all other actor
fields are omitted. This retained metadata is not a current credential or
publication-actor preflight.

A message is returned only as a literal bounded prefix. Its original and
returned character counts, source path, half-open returned range and
truncation state are explicit. The default zero budget withholds all message
text; display-title aliases are omitted as well. Prefix boundaries avoid
splitting a surrogate pair. Message ranges
refer to UTF-16 code units in the original identified message string.

Each selected file preserves its original row index, literal `filename`
and exact row/filename source paths. Retained file rows must be objects with
a string filename. A present patch must be a string or null. The view records
patch presence, source path and character count; it never returns patch text.
Missing patch fields stay missing. A null patch has a null character count.

The commit diff, file patches, comments and email fields are always omitted.
Coverage records the native commit diff's presence and character count, and
whether a comments field was present. It does not inspect or claim completeness
for comments. Top-level display/diff aliases are not substituted for the
identified native commit object's fields.

## Options and coverage

| Option | Default | Allowed range or meaning |
| --- | --- | --- |
| `start_index` | 0 | Contiguous starting file row; mutually exclusive with `source_indices`. |
| `source_indices` | absent | Distinct increasing nonnegative original file indices. |
| `max_files` | 8 | 0–100 selected file headers; must accommodate explicit indices. |
| `max_message_chars` | 0 | 0–100,000 UTF-16 code units in the literal message prefix. |
| `max_header_chars` | 4,096 | 128–16,384 code units per returned string header or filename. |
| `max_input_files` | 10,000 | 1–100,000 retained file rows to inspect. |
| `expected_commit_sha` | absent | Optional exact complete lowercase commit SHA. |

All supported commit/actor header fields and all filenames/patch field shapes
are inspected before selection. Diff, patch and message bodies are already
strings; their full contents are not copied into the bounded view.
Other provider fields remain solely in the original envelope.

Coverage always describes `retained_response_only`, with
`snapshot: false` and `provider_file_completeness: "not_inferred"`.
It records retained/returned/omitted file counts, original selected indices,
half-open omitted index ranges and the next contiguous index when available.
`all_retained_file_headers_included` refers only to this returned envelope,
not GitHub's complete changed-file collection or source-tree contents.

A valid retained empty file array still returns `PROJECTED`. Provider error
envelopes return `PROVIDER_ERROR`. Unsupported envelope shapes return
`UNSUPPORTED_REPRESENTATION`; excessive header or file counts return
`INPUT_LIMIT`. The issue contains a code and relevant original source path
when available. These states are not empty commit results. Invalid options
or file selections throw. No response state causes a retry or another read.

## Actual activation

The implementation consumed the fresh native response for source commit
`c692a6ebb06b63cb1b0253be7ab4549c75da01b2`. That envelope retained three file
rows and 17,176 diff characters. The view selected original file rows 0 and 2,
preserved their exact metadata/source paths and withheld the message, diff,
patches, comments and emails. The original envelope and options stayed unchanged.
The projection itself made no provider call.

The additive token activation used actual native and approved token responses
for immutable source commit `ad3c37076332215317ab0f8c7dec9cbd38d73153`.
The previous helper projected native headers but refused the token envelope.
The updated helper projects both with file rows 0 and 2 selected, zero message
budget, literal SHA/account IDs and exact original row/message paths. The native
output stays byte-equivalent to the previous projection. Both complete input
envelopes and the shared options remain unchanged; no read or retry is caused
by either projection.
