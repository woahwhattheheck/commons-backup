# Retain JSON through bounded execution commands

`connected_exec_json_journal.cjs` exports `createExecJsonJournal(execCommand, options)` and `ExecJsonJournalError`. It writes caller-supplied JSON snapshots to an isolated local directory through the supplied, already-authorized execution binding. It makes no provider call or credential lookup and never resumes or retries an external effect.

The actual Git tree readback from one Commons publication serialized to 487,268 characters. Embedding that complete response in one execution command exceeded the execution server's argument limit, stopping publication before any GitHub write. This helper splits JSON into bounded commands and installs the final journal atomically.

## Use in code mode

Load the complete source with the connected GitHub file reader and evaluate it as a CommonJS module. Pass the existing `tools.exec_command` function and an absolute cloud scratch directory dedicated to this operation:

```js
const journal = box.exports.createExecJsonJournal(tools.exec_command, {
  directory: '/workspace/scratch/my-operation/journal'
});
await journal.write('call-001-intent', {binding, args});
const response = await tools[binding](args);
store('call-001-response', response);
await journal.write('call-001-response', response);
return response;
```

The caller owns authorization, operation identity, provider dispatch and custody of original response objects. An intent write must complete before that caller dispatches its provider operation. If response retention fails after a provider call, preserve the actual response in memory and reconcile the provider effect before deciding any further action. This helper never interprets the journal as permission or replays a provider call.

Use fresh unique snapshot names, including for progress. A final file already present or a pending directory from an interrupted write causes an explicit failure; neither is overwritten or silently treated as successful. Reconcile these local artifacts rather than calling `write` again with that name. A concurrently active name in the same factory is rejected before dispatch. Separate operations should use separate directories.

## Local prerequisites and bounds

The supplied execution binding must accept `{cmd, shell, login, max_output_tokens, yield_time_ms}` and return a completed `{exit_code: 0}`. The local runtime needs Bash and Python3 with their standard libraries. A returned process session is incomplete; the error retains its execution result for caller recovery instead of starting another process.

| Option | Default | Bound |
|---|---|---|
| `directory` | required | Absolute path other than `/`, no NUL, at most4096 UTF-8 bytes. |
| `max_command_bytes` |48000 |8192–60000 actual UTF-8 bytes of every complete command. |
| `chunk_chars` |16000 |1–24000 JSON UTF-16 code units before adaptive command fitting. |
| `concurrency` |4 |1–8 independent chunk commands. Preparation/assembly stay sequential. |
| `max_serialized_chars` |8388608 |1–67108864 JSON UTF-16 code units. |

Only these options are accepted. Names are plain basenames of1–120 characters, beginning with an ASCII letter or digit, followed by ASCII letters/digits/dot/underscore/hyphen. JSON-unsupported values, circular values and size violations fail before local commands. The writer retains JSON serialization semantics, not non-JSON object identity or descriptors.

Each Python program is placed in a quoted heredoc. Structured values are encoded as a Python JSON expression inside that program; they are never interpolated as shell syntax. The command byte bound includes paths, syntax and all escaping. Oversized chunks shrink until the complete command fits, and boundaries avoid splitting surrogate pairs.

## Completion and interruption

The writer creates an exclusive `.<name>.pending` directory, writes numbered parts there, validates the reconstructed JSON, flushes/fsyncs the assembled file and atomically replaces `<name>.json`. Chunks are awaited in bounded groups, with every outcome inspected before the next group. Successful cleanup removes the parts and pending directory; cleanup failures do not turn an already installed final file into an uncertain provider effect.

Success reports `status: written`, `stage: complete`, the exact local path, JSON character/file-byte sizes, chunk count, execution-command count and largest complete command byte size. This is local file completion, not provider completion or a power-loss durability guarantee.

Failures throw `ExecJsonJournalError` with the stage, path, pending directory and observed command counts. The underlying cause retains an incomplete/error execution result when available. Pending files remain for concrete recovery; no automatic cleanup, overwrite, resume or effect retry occurs.

## Actual activation

The helper consumes the already-retained real 487,268-character Git tree response from the earlier failed journal write. The final JSON is compared with that original retained response. The same helper then records its own source publication's requests, raw responses and progress; no earlier provider read or write is replayed to activate it.

The actual large-response activation wrote 31 chunks in 33 local commands. The largest complete command was 24,704 UTF-8 bytes; final file size was487,269 bytes, including the trailing newline. It matched the original saved response byte-for-byte, and the retained in-memory input stayed unchanged.
