# Bounded local file export

`host/file_chunk_export.py` carries one existing local file into a connected-tool orchestration session without placing the whole file in one terminal response. It reuses the explicit `NEXT` protocol used for the retained VCTC, Exeter and Family Eldercare source transfers. The command reads the file through one retained descriptor, emits bounded base64 parts on request, and finishes with the SHA-256 and Git blob identity of the bytes it transferred.

This fills the outbound local-file step beside `connected_github_source.py` (inbound source materialization) and `connected_github_publish.cjs` (provider publication). Git repositories, import manifests, archives and source-acquisition clients keep their existing formats.

## Run

Python 3.10+ and a Unix-like cloud runtime are sufficient. There are no third-party dependencies.

```bash
python3 -B host/file_chunk_export.py /path/to/retained-file \
  --max-bytes 8388608 \
  --chunk-bytes 450000 \
  --wait-seconds 45
```

The process first prints one JSON manifest. Send `NEXT 0` on standard input to receive the first part. For each subsequent part, send `NEXT <next_offset>` using the offset in the prior response. The shorter `NEXT` command also requests the next part, matching the existing transfer scripts. One request is followed by one part; wait for that response before requesting another part. After the last part, the process prints a completion record and exits 0.

The request deadline covers the complete line, including a partial line received through a pipe; receiving a byte does not reset it.

Optional `--expect-sha256` and `--expect-git-blob` bind the input to a known lowercase digest before any manifest or content is emitted. Both digests are recomputed from the opened file.

| Setting | Default | Behavior |
|---|---:|---|
| `--max-bytes` | 33,554,432 | Full-file size budget; explicit nonnegative integer |
| `--chunk-bytes` | 450,000 | Raw bytes per part; multiple of 3 from 3 through 524,286 |
| `--wait-seconds` | 45 | Wait for each request; greater than 0 and at most 60 seconds |

The 450,000-byte default produces at most 600,000 base64 characters per part. Even the maximum chunk stays below 700,000 base64 characters. Each JSON event has a separate 900,000-byte serialization limit, leaving space below the observed 1 MiB tool-response ceiling. The last response may contain both its part and the small completion record.

Interior raw chunks are multiples of three. Their base64 strings can therefore be concatenated in order, with any padding occurring only in the final part. A decoder may also decode each part independently.

## Records and completion

All records use `schema: "commons.file_chunk_export/v1"`.

- `manifest`: file path, exact byte count, SHA-256, Git SHA-1 blob identity, chunk size, part count, budget and first requested offset.
- `source-part`: zero-based part index, start/end byte offsets, repeated whole-file identities, chunk SHA-256, base64 content and next offset.
- `complete`: exact transferred byte count, part count and final whole-file identities.

The Git identity hashes `b"blob " + str(len(data)).encode("ascii") + b"\0" + data`, matching GitHub's Git blob object. These content identities describe the supplied bytes; they do not authenticate their origin.

An empty regular file produces a manifest and completion immediately, with zero parts. For a nonempty file, the consumer must retain contiguous parts, receive the completion record and observe exit 0 before treating the transfer as complete. A manifest or a partial series of parts is incomplete work.

Failures produce a structured `error` record on stderr and exit 2. Codes include `FILE_TOO_LARGE`, `NOT_REGULAR_FILE`, `SHA256_MISMATCH`, `GIT_BLOB_MISMATCH`, `SOURCE_CHANGED`, `INVALID_NEXT`, `NEXT_TIMEOUT` and `INCOMPLETE_EXPORT`. Invalid CLI syntax uses argparse's ordinary exit 2. Failed or incomplete transfers never emit a successful completion record.

## Connected-tool use

Start the existing command in a terminal session so its standard input remains available:

```javascript
const started = await tools.exec_command({
  cmd: "python3 -B host/file_chunk_export.py /path/to/retained-file --max-bytes 8388608",
  login: false,
  tty: true,
  yield_time_ms: 1000,
  max_output_tokens: 10000
});
// Parse the small manifest from started.output and retain started.session_id.
// The command disables terminal input echo and restores it when it exits.
```

Use a properly shell-quoted path when building a command from variable input. Apply the existing lane's capacity decision to the actual invocation; this exporter does not schedule work or alter resource limits.

For each requested offset, make one call and parse its JSON lines into private orchestration storage:

```javascript
const step = await tools.write_stdin({
  session_id,
  chars: "NEXT " + nextOffset + "\n",
  yield_time_ms: 1000,
  max_output_tokens: 300000
});
```

The existing transfer road used these settings for 450,000-byte raw parts. Increasing the output-token budget does not remove the tool's separate response-byte ceiling. Do not print the returned base64 into the conversation.

Before appending a part, check its schema, index, contiguous `start`/`end`, total size and repeated file identities against the manifest. Check `base64.length === 4 * Math.ceil((end - start) / 3)` and the returned next offset. Keep the original event if an operation's outcome is uncertain; inspect the session's new output before sending another request.

After complete/exit 0, concatenate the part strings in order. The existing GitHub publication helper accepts that value as a file's `content` with `encoding: "base64"`, together with its normal path and expected prior blob. Compare the created blob identity with the transfer manifest, then retain ordinary branch/PR/main readback. A direct `github_create_blob` call is also available when a caller already owns the tree/commit work. The exporter itself performs no provider operation and writes no output file.

The terminal-side process holds only bounded read and encoding buffers. A GitHub create-blob request still requires the assembled base64 content in the caller's orchestration memory.

## Source lifetime

The command opens an existing regular file, hashes it in bounded reads, rewinds the same descriptor and reads each requested part. A symlink to a regular file is supported. Namespace changes do not redirect the retained descriptor to another file.

Size, device/inode and modification/change timestamps are checked during the initial hash and around each part. The transmitted bytes are hashed again and must match the initial identities before completion. An observed in-place source change fails the transfer. The command never changes source files, copies them into another workspace, truncates them or removes them.

Keep the source stable while exporting. A failed transfer can be restarted from the existing file after resolving the reported condition; it does not resume from a different descriptor or silently reuse an earlier identity.
