# Project retained native Gmail message bodies

`host/connected_gmail_messages.cjs` provides a bounded view of full MIME responses already returned by the connected Gmail readers. It exports the pure function `projectGmailMessages(response, options?)`. It makes no provider calls and does not change the retained response.

Use it when a full message envelope contains many transport headers, duplicate HTML, or attachments around the useful body. Keep the original request and response beside the projection so omitted content remains available.

## Load and consume a retained response

In Node, use `require('./host/connected_gmail_messages.cjs')` from the repository root. In code mode, load the source once and pass the original native response:

```js
const source = await tools.mcp__codex_apps__github_fetch_file({
  repository_full_name: "woahwhattheheck/commons",
  path: "host/connected_gmail_messages.cjs",
  ref: "main"
});
if (source.isError || source.structuredContent?.encoding !== "utf-8") {
  throw new Error("Readable native source is required");
}
const box = { exports: {} };
new Function("module", "exports", source.structuredContent.content)(box, box.exports);

// This key holds an earlier authorized full-MIME read, saved before printing.
const retained = load("mail-full-response");
if (!retained) throw new Error("Retain the original full message response first");
const view = box.exports.projectGmailMessages(retained, {
  maxMessages: 10,
  maxBodyChars: 6000,
  maxTotalBodyChars: 18000
});
store("mail-body-view", view);

// Display selected plain text and metadata for selected HTML.
// The complete native response and complete projection remain retained.
const display = {
  display_format: "gmail-plain-body-display-v1",
  message_count: view.message_count,
  omitted_messages: view.omitted.messages,
  messages: view.messages.map(message => ({
    id: message.id,
    thread_id: message.thread_id,
    source_index: message.source_index,
    source_path: message.source_path,
    subject: message.subject,
    from: message.from,
    date: message.date,
    projection_omitted_header_chars: message.omitted.header_chars,
    projection_omitted_body_chars: message.omitted.body_chars,
    projection_omitted_body_parts: message.omitted.body_parts,
    bodies: message.bodies.map(body => ({
      mime_type: body.mime_type,
      source_path: body.source_path,
      original_chars: body.original_chars,
      projected_chars: body.text.length,
      projection_omitted_chars: body.omitted_chars,
      projection_truncated: body.truncated,
      display_status: body.mime_type === "text/plain" ? "included" : "withheld_html",
      display_omitted_chars: body.mime_type === "text/plain" ? 0 : body.text.length,
      text: body.mime_type === "text/plain" ? body.text : undefined
    })),
    unavailable_bodies: message.unavailable_bodies.map(body => ({
      mime_type: body.mime_type,
      source_path: body.source_path,
      reason: body.reason
    }))
  }))
};
store("mail-body-display", display);
text(display);
```

Save a native read result with `store("mail-full-response", response)` before emitting a projection.

The example keeps the complete projection under `mail-body-view` and stores a separate reading display under `mail-body-display`. Only selected `text/plain` bodies are displayed as text. For selected `text/html`, the display includes its MIME type, exact source path and character counts with `display_status: "withheld_html"`; the HTML string, including its tag attributes, is not emitted. No HTML rendering, tag stripping, entity decoding or conversion is performed. An available HTML-only body is therefore explicitly withheld in this display, not represented as an empty or unavailable body.

`original_chars`, `projection_omitted_chars` and `projection_truncated` describe the existing projector's source and clipping. `projected_chars` is the selected string's returned length; `display_omitted_chars` counts only that returned string withheld by this additional display step. These counts remain separate, so projector clipping is not reported as display coverage. The helper's complete MIME omission counts, limits and selection record remain in `mail-body-view`. Sparse source indices and body paths retain their original positions; the display does not inspect an omitted message or an unused HTML alternative. Explicit output fields also keep transport headers and unrelated envelope fields out of this reading display.

MIME selection is not redaction or sender authentication. Apply the recipe only to the messages already selected for the current task. Plain text can itself contain sensitive values; this recipe only controls which selected representation is displayed. If HTML content is needed for the task, use the retained source path deliberately rather than silently substituting a different body representation.

The observed-consumption measurements below describe the existing projector. They are not measurements of this added display recipe; the new example has been reviewed against the current projector's fields without executing another mailbox-body projection.

The module accepts these actual native full-MIME shapes:

| Reader | Required response shape |
| --- | --- |
| `gmail_read_email` with full format | `response.structuredContent` contains `id`, `thread_id`, and `payload`. |
| `gmail_batch_read_email` | `response.structuredContent.responses[]` contains those full message objects directly. |
| `gmail_read_email_thread` | `response.structuredContent` contains the native thread `id` and `messages[]` of those full message objects. Each message must identify that same `thread_id`. |
| `gmail_batch_read_email_threads` | A nonempty `response.structuredContent.responses[]` contains native thread objects, each with `id` and full-MIME `messages[]`. Every message must identify its enclosing thread's `id`. |

A nonempty collection containing only native thread envelopes uses
`source_shape: "batch_threads"`. An empty `responses[]` retains the existing
`source_shape: "batch"`; a mixed collection of thread and direct-message
envelopes is rejected explicitly.

A payload contains `mime_type`, optional MIME `parts`, headers as `{name, value}` entries, and decoded text in `body.content`. Raw, metadata-only, search, error, and unrelated response shapes are unsupported. The projector does not substitute a search snippet or decode `base64_url_content`.

## Reading the view

The result contains `format`, `source_shape`, the original `message_count`, selected `messages`, aggregate `omitted` counts, and the effective `limits`. Existing single-message, direct-message batch, and single-thread outputs remain unchanged. A native thread uses `source_shape: "thread"` and adds `thread: {id, source_path}`, copying the exact observed thread ID from `$.structuredContent.id`. A native thread batch adds `thread_count`, `threads`, and `thread_message_range_end: "exclusive"`, as described below; its `message_count` is the total retained messages across the supplied threads.

Each selected message retains its `id` and `thread_id`, plus literal Subject, From, and Date header values, clipped to the header limit. Header values are message data, not an authentication assertion. Each available body has:

- `mime_type`: `text/plain` or `text/html`.
- `text`: literal decoded content, with only explicit length clipping.
- `source_path`: the exact path to the original `body.content`.
- `original_chars`, `omitted_chars`, and `truncated`.

For example, a batch path such as
`$.structuredContent.responses[0].payload.parts[0].body.content`
refers to that field in the retained native response. A single-message path starts at
`$.structuredContent.payload`; a thread message uses
`$.structuredContent.messages[index].payload`; a batch-thread message uses
`$.structuredContent.responses[threadIndex].messages[messageIndex].payload`.
Read a needed omitted field from the retained response; another Gmail call is unnecessary when the content is already present.

## Consume a retained native thread

Pass the complete retained `gmail_read_email_thread` response directly to the
same API. Its `messages[]` are kept distinct and in provider order; they are
not flattened into another message or inferred from the thread snippet.

```js
const threadView = box.exports.projectGmailMessages(retainedThreadResponse, {
  source_indices: selectedThreadMessageIndices,
  maxMessages: selectedThreadMessageIndices.length,
  maxBodyChars: 0,
  maxTotalBodyChars: 0,
  include_native_metadata: true
});
store("mail-thread-view", threadView);
```

Choose source indices from that already retained array. Sparse message paths,
body paths and optional native-metadata paths keep their original
`$.structuredContent.messages[index]` positions. Existing MIME selection,
clipping, unavailable-body reports and omission counts apply independently to
each selected message. All retained message envelopes are validated, including
omitted ones; raw or metadata-only thread messages are not accepted as full MIME.

`message_count` counts the retained `messages[]` only. The native thread reader
returns at most its requested `max_messages`, in oldest-to-newest order within
that returned set; the projector neither supplies missing history nor declares
a total conversation count. Projection limits add further explicit omissions.
An empty native `messages[]` therefore means no messages in the supplied
collection, not that the conversation has no other messages. Thread identity
is native envelope data and does not establish sender authentication or current
mailbox state.

## Consume retained native thread batches

Pass the complete retained `gmail_batch_read_email_threads` response to the same
API. Messages stay separate in provider thread/message order. Selection uses
global zero-based message indices across that ordered set, while source paths
keep each message's original outer thread and inner message positions.

```js
const threadBatchView = box.exports.projectGmailMessages(retainedThreadBatchResponse, {
  source_indices: selectedGlobalMessageIndices,
  maxMessages: selectedGlobalMessageIndices.length,
  maxBodyChars: 0,
  maxTotalBodyChars: 0,
  include_native_metadata: true
});
store("mail-thread-batch-view", threadBatchView);
```

Choose `selectedGlobalMessageIndices` from the already retained batch. The
result's `threads[]` maps the supplied threads to the global message range:

| Field | Retained mapping |
| --- | --- |
| `thread_count` | Number of supplied native thread envelopes, including empty retained threads. |
| `threads[].source_index` | Original zero-based outer thread index. |
| `threads[].id` | Exact enclosing native thread ID. |
| `threads[].source_path` | `$.structuredContent.responses[threadIndex].id`. |
| `threads[].message_count` | Number of retained messages in that thread. |
| `threads[].message_index_range` | Half-open `[start, end)` global message indices; `thread_message_range_end` is `"exclusive"`. |

An empty retained thread has a zero-length `[start, start)` range. These ranges
and counts cover only the supplied set and do not declare a full conversation
or mailbox history.

Every selected batch-thread message carries `source_index` for its global
message position and `source_path` for
`$.structuredContent.responses[threadIndex].messages[messageIndex]`, whether or
not `source_indices` was supplied. It also carries `thread_source_index` and
`thread_message_index` for those original outer and inner positions. Body and
optional native-metadata paths use that same original message location; sparse
selection never renumbers them.

All outer thread and message envelopes are validated before selection,
including omitted threads and messages. A message's `thread_id` must equal its
original enclosing thread's `id`; mixed thread/direct-message collections and
unsupported message envelopes fail explicitly. Existing MIME selection,
unavailable-body reporting, budgets and sparse omission ranges apply to the
selected messages. No snippet replaces a body, and no missing conversation
history is inferred or fetched.


MIME selection follows these rules:

- Within `multipart/alternative`, choose a branch containing plain text when present; otherwise choose one containing HTML. Content availability is reported separately from that preference.
- HTML is labelled `text/html` and returned unchanged as data. The module neither renders HTML nor converts it to plain text.
- Within `multipart/related`, select the root identified by the Content-Type `start` parameter, or the first child when that parameter is absent. Other related parts are counted as omitted.
- Parts with filenames or attachment dispositions, forwarded `message/rfc822` and `message/global` parts, and unsupported non-text parts are omitted and counted.
- Selected text parts with an external `attachment_id` or without decoded `body.content` appear in `unavailable_bodies` with a reason and exact source path. The projector never fetches an attachment or substitutes a snippet.

## Limits and omissions

| Option | Default | Meaning |
| --- | ---: | --- |
| `maxMessages` | 10 | Maximum displayed messages. |
| `maxBodyChars` | 6,000 | Maximum displayed characters per selected body. |
| `maxTotalBodyChars` | 18,000 | Shared displayed body-character budget across messages. |
| `maxHeaderChars` | 300 | Maximum characters in each selected header value. |
| `maxBodiesPerMessage` | 8 | Combined available and unavailable selected-body positions per message. |

Limit options must be supported nonnegative safe integers; zero is allowed. The optional `source_indices` array is described below. Character counts and limits use JavaScript UTF-16 code units. Clipping preserves a surrogate pair at the boundary. These are limits on displayed fields and entry counts, not an exact serialized-JSON byte ceiling.

Per-message `omitted` reports excluded message-header entries, clipped selected-header characters, clipped or capped selected-body characters, capped body positions, and counts of excluded attachment, forwarded-message, alternative, related, and unsupported parts. Alternative and related counts refer to excluded branches or children at the selection point, not every descendant. `body_chars` does not include unused alternative HTML or other excluded nonselected branches. Header-character counts do not sum discarded transport-header values.

Top-level `omitted.messages` counts messages excluded by `maxMessages` or an explicit `source_indices` selection. Its character and body-position counts sum the displayed messages only; it does not inspect or estimate the bodies of excluded messages. Raw/search/error message envelopes are rejected even when they fall beyond the message-display limit.

Malformed or unsupported input raises a `TypeError` with `code` and `source_path`. Selected MIME traversals also reject cycles, depth beyond 32, or more than 4,096 visited parts per message. No uncertain shape is turned into a successful empty message.

## Select disjoint retained messages

Pass optional `source_indices` to select messages by their original positions in the retained response. For `batch_threads`, these are global indices across messages in provider thread/message order, not outer thread indices or per-thread message indices. Omit the property to preserve the existing first-`maxMessages` behavior and the shape's normal location metadata.

```js
const selected = box.exports.projectGmailMessages(retained, {
  source_indices: [1, 2, 4, 7],
  maxMessages: 4,
  maxBodyChars: 45000,
  maxTotalBodyChars: 60000
});
store("mail-selected-body-view", selected);
```

The array must be dense and strictly increasing, with zero-based safe integers inside the retained response's message range. Its length must not exceed `maxMessages`; `[]` is valid and selects no messages. Explicit `null` or `undefined`, missing array entries, duplicates, descending or noninteger indices, and out-of-range indices raise `INVALID_OPTIONS` with the offending `source_path`. No indices are silently sorted, deduplicated, dropped or capped.

For existing single-message, direct-message batch, and single-thread shapes, only this mode adds `source_index` and `source_path` pointing to the original selected envelope. For `batch_threads`, those fields and the original thread/message indices are always present. Existing body paths retain their original positions, including `responses[threadIndex].messages[messageIndex]` for thread batches. The effective `limits.source_indices` and top-level `selection.source_indices` are copies of the selection; the input options remain unchanged.

The added `selection.omitted_source_index_ranges` lists every omitted message range using half-open `[start, end)` bounds, with `range_end: "exclusive"`. For the ten-message selection above, these are `[[0,1],[3,4],[5,7],[8,10]]`, and `omitted.messages` is `6`. An empty selection omits every input message.

All message envelopes are validated before selection, including omitted ones. MIME traversal runs only for selected messages; header/body omission counts and display budgets cover only those messages. No omitted body is fetched, decoded, traversed or estimated, and no provider call is added. Existing MIME selection, HTML-as-data handling, unavailable bodies and structural limits are unchanged.

## Observed consumption

The initial implementation was consumed in code mode against one retained native batch containing two actual full-MIME messages. Each message had 40 message headers, one 877-character plain body, and an HTML alternative.

| Observation | Result |
| --- | ---: |
| Original complete response, serialized with `JSON.stringify` | 28,681 characters |
| Default projection, serialized the same way | 3,410 characters |
| Reduction in displayed serialized characters | 25,271 / 88.1% |
| Plain-text bodies retained completely | 2 of 2 |
| Original body text equals each resolved source path | 2 of 2 |
| Original response unchanged after projection | Yes |
| Additional Gmail calls for this consumption | 0 |

Both messages reported 37 omitted message-header entries and one unused alternative branch, with no selected-body truncation. This observation covers that actual batch and the code-mode module load. It is not a token, latency, quota, attachment-fetch, or general MIME-corpus benchmark. The original mail content, message identifiers, and transport headers are not part of this repository receipt.

## Include exact native labels and date metadata

Pass `include_native_metadata: true` when intake needs the native `label_ids` or `internal_date` fields. The boolean is optional. Omitting it or passing `false` preserves the existing output shape and limits; explicit `null`, `undefined`, or any nonboolean value raises `INVALID_OPTIONS`.

```js
const metadataView = box.exports.projectGmailMessages(retained, {
  source_indices: [0],
  maxMessages: 1,
  maxBodyChars: 0,
  maxTotalBodyChars: 0,
  include_native_metadata: true
});
store("mail-native-metadata-view", metadataView);
text(metadataView.messages.map(message => ({
  source_index: message.source_index,
  native_metadata: message.native_metadata
})));
```

Each selected message gains `native_metadata.label_ids` and `native_metadata.internal_date`. Both fields contain a `status` and an exact `source_path`, such as `$.structuredContent.responses[0].label_ids`. The original index survives sparse selection. A single-message source path starts at `$.structuredContent`; a native thread uses `$.structuredContent.messages[index]` for the original message position; a native thread batch uses `$.structuredContent.responses[threadIndex].messages[messageIndex]` before the metadata field name.

| Status | Meaning | `value` |
| --- | --- | --- |
| `included` | The complete native value has a supported shape and fits every bound. | Exact string array or exact string. |
| `missing` | The native envelope has no own property with this field name. | Absent. |
| `invalid` | A present value has an unsupported type, or its label array contains a hole or a nonstring entry. | Absent. |
| `limit_exceeded` | The native field exceeds a fixed metadata bound. | Absent. |

`label_ids` must be a dense array of strings. An empty array, empty strings, original order, and duplicate strings are preserved. The returned array is a copy. `internal_date` must be a string; it is copied exactly, including an empty string. Present `null` and `undefined` values are invalid. The reader does not parse a date, convert a number, validate a label's meaning, normalize text, or derive mailbox state from message headers.

The enabled view reports these fixed bounds in `limits.native_metadata` and records `limits.include_native_metadata: true`:

| Bound | Value |
| --- | ---: |
| `max_label_ids` | 100 |
| `max_label_id_chars` | 256 per label ID |
| `max_internal_date_chars` | 64 |

Character bounds use UTF-16 code units. The label count is checked before its entries. Every admitted entry must fit; no partial array or clipped label/date string is emitted. A field's unavailable status does not suppress its sibling metadata or an otherwise valid MIME projection. The bounds are reader constants, not new caller options.

These fields describe the retained native read. Consumers should check `status === "included"` before reading `value`; missing, invalid, or limited metadata is not evidence that a label is absent. The Date header remains a separate message field. Native labels and dates do not establish current mailbox state, sender authentication, or permission to change or send mail.

Metadata projection runs only for selected messages. Existing full-envelope validation, MIME selection and omission counting remain unchanged. Setting body display budgets to zero hides body text while retaining the existing selected-MIME traversal and counts. Excluded message bodies remain untraversed.

### Observed native metadata consumption

The extension was consumed once on source index `0` of an actual retained two-message native batch, with zero body-display budgets. It returned three complete label IDs (31 characters total) and the 13-character native date string. Both source paths resolved to the original fields; the label array was copied, and the selected envelope and options were unchanged.

The previously retained header/body projection for that selected message matched every existing field after removing the new metadata and the already-supported sparse-selection location fields. The other message remained omitted at `[[1,2]]`, and no body text was displayed. This consumption made zero additional Gmail calls and did not rerun the previous reader. No actual mail content, headers, identifiers, label values, or date values are published in this receipt.

Missing, invalid, limit-exceeded, disabled-option, and single-message metadata branches were reviewed in source; the actual input exercised the complete native batch fields. This observation is not a general MIME, timestamp, or label corpus benchmark.

