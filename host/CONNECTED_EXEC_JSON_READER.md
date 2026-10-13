# Recover a complete cloud JSON journal through bounded reads

`connected_exec_json_reader.cjs` exports
`createExecJsonReader(execCommand, sha256Utf8, options)` and
`ExecJsonReaderError`. It restores one saved JSON file through an existing
authorized cloud execution binding, verifies complete reconstructed bytes and
returns both exact decoded text and the parsed value. It performs no file
write, provider operation, credential lookup, retry or implicit resume.

Use it after runtime state loss or when one terminal response would be too
large to restore a retained envelope. This is a reader for saved data; reading
an intent or acknowledgement does not dispatch or authorize its provider effect.

## Use in connected code mode

Load the complete reader source and the existing
[SHA256 helper](connected_sha256.cjs) through the ordinary identified CommonJS
loader, then inject their actual exports and the existing cloud execution tool:

```javascript
const reader = readerModule.createExecJsonReader(
  tools.exec_command,
  sha256Module.sha256Utf8,
  {directory: '/workspace/scratch/my-operation/journal'}
);
const recovered = await reader.read('call-001-response');
store('recovered-response', recovered.value);
text({
  path: recovered.source.path,
  bytes: recovered.source.file_bytes,
  sha256Verified: recovered.source.complete_sha256_verified
});
```

The named file is `<directory>/<name>.json`. The caller supplies its existing
operation directory and known snapshot name. Keep the complete result privately:
`json_text` and `value` contain the saved content. Print metadata separately.
The input is not copied into command text; local commands only identify the
known file, expected identity and requested byte range.

The [JSON journal writer](CONNECTED_EXEC_JSON_JOURNAL.md) is a compatible
producer. The reader also accepts complete ordinary UTF-8 JSON files,
including indentation or a trailing newline. It does not normalize those bytes,
strip a BOM, replace malformed UTF-8 or treat an empty file as an empty result.

## Identity and exact reconstruction

The initial read opens a regular file, checks its byte bound, hashes its complete
contents with Python SHA256 and compares descriptor metadata before and after.
The observed device, inode and nanosecond modification time are retained as
decimal strings to avoid JavaScript integer precision loss; file size is a
bounded safe integer.

Each chunk reopens that same path, requires the observed identity to match,
reads the exact requested byte range and checks identity and byte count again.
Bounded base64 output is decoded into the correct byte offset. Every outcome
in each concurrent group is awaited and inspected before another group starts.

The complete byte buffer is decoded as strict UTF-8. The supplied existing
`sha256Utf8` function returns `{bytes, sha256}`; both must match the original
observed file before JSON parsing. Invalid UTF-8, a changed file, incomplete
terminal output, wrong chunk range/count, digest mismatch or invalid JSON
stops the read. No partial value is presented as recovered data.

This binds recovery to the observed local file and complete content digest.
It does not independently certify a provider acknowledgement, current branch,
account identity or provider outcome. Reconcile those effects through their
existing canonical read paths before any next mutation.

## Execution and bounds

The supplied execution binding must accept
`{cmd, shell, login, max_output_tokens, yield_time_ms}` and return a completed
`{exit_code: 0, output: string}` without a process session. Bash and Python3
standard libraries are required in the cloud runtime. Each program is placed
in a quoted heredoc; values are Python JSON expressions rather than shell
interpolation. Complete command size includes paths, escaping and syntax.

| Option | Default | Bound |
| --- | --- | --- |
| `directory` | required | Absolute path other than `/`, no NUL, at most 4,096 UTF-8 bytes. |
| `max_file_bytes` | 8,388,608 | 1–67,108,864 bytes in the complete observed file. |
| `chunk_bytes` | 4,096 | 1,024–8,192 bytes per chunk. |
| `concurrency` | 4 | 1–8 independent read commands. |
| `max_command_bytes` | 48,000 | 8,192–60,000 UTF-8 bytes per complete command. |

Names are plain basenames of 1–120 characters, beginning with an ASCII letter
or digit, followed by letters, digits, dot, underscore or hyphen. Unsupported
options and invalid bounds fail before execution. Large files require an
explicitly sufficient byte bound. Terminal output token budgets account for
base64 expansion; a transport that still truncates output produces an explicit
failure rather than silent recovery.

Success returns `status: "read"`, exact file path/identity/byte count/SHA256,
`complete_sha256_verified: true`, command/chunk counts, largest command byte
size, complete `json_text` and parsed `value`. JSON parsing retains standard
JSON semantics, not JavaScript descriptors or unsupported non-JSON values.

Failures throw `ExecJsonReaderError` with observed stage, file identity,
received byte counts and command counts. The underlying cause retains a
returned incomplete/error execution result when available. Preserve those
details privately. There is no automatic retry, alternate file or provider replay.

## Actual recovery

The real reader consumes the existing TinyFish recovery effect journal:
196,136 bytes, with a previously acknowledged observations blob and retained
provider readbacks. The recovered text/value match the original saved journal;
source identity and complete SHA256 are verified. Recovery used 48 chunks in
49 completed local commands; the largest command was 998 UTF-8 bytes. The
saved boundary is historical and is not current provider-state truth. No
provider read or write is replayed. The existing journal writer then retains this reader's own source
publication requests, raw responses and progress through an injected operation
recorder callback using unique snapshot names.
