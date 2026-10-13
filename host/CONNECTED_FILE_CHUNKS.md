# Connected file-chunk consumer

`host/connected_file_chunks.cjs` consumes the existing `host/file_chunk_export.py` protocol through native `exec_command` and `write_stdin` bindings. It replaces the repeated caller code that starts a guarded export, sends each `NEXT <offset>`, joins its parts, and waits for successful process closure.

The immediate consumer was the [Douglas public-source publication](https://github.com/woahwhattheheck/commons/pull/30981): its private runner transferred four retained files through 21 parts. This module extracts that conversation while leaving the command, local source selection, execution admission and GitHub publication with the caller.

## Interface

The CommonJS module exports `collectFileChunks(bindings, request, options)` and `FileChunkError`. It uses standard JavaScript only: no filesystem, network client, Node package, credential lookup, shell builder or JavaScript cryptography dependency.

```js
const box = { exports: {} };
new Function('module', 'exports', consumerSource)(box, box.exports);

const result = await box.exports.collectFileChunks(tools, {
  command: alreadyAuthorizedGuardedExporterCommand,
  file: absoluteSourcePath,
  expected_bytes: sourceBytes,
  expected_sha256: sourceSha256,
  expected_git_blob_sha1: sourceGitBlob,
  max_bytes: 8 * 1024 * 1024
}, {
  onProgress: progress => store('file-export-progress', progress),
  onResponse: (response, meta) =>
    store('file-export-response-' + meta.call, response)
});

if (result.status !== 'complete') {
  // Preserve the command's actual exit and startup output.
  store('file-export-not-complete', result);
} else {
  // Supply result.base64 to the already-authorized GitHub publisher.
  // Compare the provider's actual blob SHA with result.manifest.git_blob_sha1.
}
```

`consumerSource` is the exact source loaded from the repository. A Node caller can use `require('./connected_file_chunks.cjs')` instead.

The command is supplied verbatim. Keep its existing immediate admission guard, quoting, absolute paths and time limits. The helper calls it with `login:false` and `tty:true`; an optional `workdir` is forwarded. A typical underlying command runs the pinned Python exporter with `--chunk-bytes 12288 --wait-seconds 45` and the caller's file budget and source pins. Small chunks keep individual native responses easy to retain.

A caller that has already started its own exporter can supply `start_result` instead of `command`. Supply exactly one. Adopting a result never starts or repeats the command; the supplied session must belong to that one authorized exporter and may be interrupted by this helper if its conversation fails.

`file` is required and must match the manifest's exact path string. The three `expected_*` fields are optional independent pins. Their presence is reported in `source_pins_matched`; omitting a pin does not create an independent identity check.

## What is validated

The consumer accepts one manifest of schema `commons.file_chunk_export/v1`. It checks the requested path, byte budget, chunk size, exact part count and any supplied pins. It then sends one NEXT request for each expected offset. An empty native read can collect a delayed response; it never repeats a NEXT after an ambiguous send.

Every part must retain the manifest's path, byte count and reported digests, have the exact next index and contiguous range, and contain canonical base64 of the exact stated byte length. Interior parts cannot introduce padding. The complete record must cover every byte and part, and the native command must finish with exit 0. Empty files can complete directly from their manifest.

A successful result includes:

- `status: 'complete'`, the original `manifest` and `completion`, and `exit_code: 0`;
- joined `base64` and compact per-part range/hash metadata;
- the supplied-pin coverage, validation description and compact progress;
- bounded startup output preceding the protocol, such as a caller's admission record.

The Python producer computes source and transferred-byte hashes. This JavaScript module validates those reported identities and the transport structure; it does not independently hash decoded content. Its result labels this as `content_hashes: 'reported_by_exporter'`. For GitHub publication, compare the actual create-blob result with the expected Git blob before using it. Do not treat reported SHA-256 text alone as a separate JavaScript content-hash calculation.

Keep `base64` and raw `onResponse` records in private orchestration storage. Progress omits file content. The module makes no GitHub or Slack writes, and it does not print responses.

The example `store()` callbacks retain data in the current runtime; they do
not establish cross-isolate custody after replacement. For a handoff that needs
durable bytes, follow [Retain complete bytes across a session handoff](CONNECTED_GITHUB_PUBLISH.md#retain-complete-bytes-across-a-session-handoff):
preserve the exact authorized command and required file bytes in an existing
carrier appropriate to their visibility, with immutable identities and complete
readback. Progress, producer-reported hashes and a scratch path are insufficient
when the original bytes are unavailable. Retention does not start or restart an
export; preserve the actual transfer and process-closure outcome.

## Bounds and failures

| Request field | Default | Meaning |
| --- | ---: | --- |
| `max_bytes` | 33,554,432 | Maximum admitted full-file bytes |
| `max_parts` | 4,096 | Maximum manifest parts |
| `timeout_ms` | 120,000 | Cooperative deadline checked between native calls |
| `max_polls` | 64 | Total empty reads while awaiting records or process exit |
| `max_response_chars` | 1,048,576 | Maximum characters in one returned native output |
| `max_line_chars` | 900,000 | Maximum complete or pending protocol line |
| `max_preamble_chars` | 8,192 | Maximum non-protocol startup text |
| `max_output_tokens` | 300,000 | Native response token request; provider caps still apply |
| `yield_time_ms` | 1,000 | Native wait, configurable from 250 to 1,000 ms |

The line buffer handles records split across native responses. Native output truncation, malformed records, changed pins, gaps, unsolicited parts, incomplete transfers and nonzero exporter exits never produce a complete result. The cooperative deadline does not cancel an in-flight tool call; retain the caller's underlying execution limits.

A nonzero command exit before any manifest returns `status: 'exited_before_manifest'` with its actual exit and startup output. This preserves a caller's capacity hold without claiming an export occurred. A producer error record or failure after the protocol begins throws `FileChunkError` with a compact `progress` snapshot.

On failure, the helper makes a bounded best effort to interrupt only its known exporter terminal: one Ctrl-C and at most two empty closure reads. Cleanup reports whether an exit was actually observed; it never claims an unobserved closure or controls other processes. There is no restart, automatic command retry, resumptive NEXT replay, source deletion or admission-limit change.

Use a separate call for each file. Checkpoint completed files in the caller, and continue with the next unfinished file after any genuine hold. The original native responses remain available through the optional callback for an exact private receipt.
