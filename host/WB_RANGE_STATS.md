# Range index runtime statistics

Use `index --stats PATH` to write a separate JSON report for one indexing
invocation. The model index schema and the usual JSON summary on stdout stay
the same.

```sh
python host/wb_range.py index "$MODEL_URL" --work-dir wb-range-out --stats cold.json
python host/wb_range.py index "$MODEL_URL" --work-dir wb-range-out --stats warm.json
```

Use a new work directory for a cold-cache run. Reusing that directory measures
the cache actually used by the second invocation. Each selected report path is
written for that invocation, so use different paths to retain both reports.

| Field | Meaning |
| --- | --- |
| `schema_version` | `commons-wb-range-stats/v1` |
| `operation` | `index` |
| `status` | `INDEXED`, or `FAILED` if indexing or writing the index failed |
| `http_scope` | `range_requests_only`; excludes the Hugging Face file-list request |
| `elapsed_seconds` | Monotonic time from starting index construction through writing the index, or reaching an error; excludes interpreter startup and writing the stats report |
| `files_indexed` | Source files parsed and added successfully during this invocation |
| `read_calls` | Calls to `RangeReader.read` that passed its range bounds checks, including cache hits; direct remote-size probes are counted in HTTP counters instead |
| `cache_hits` | Reads satisfied by a cached chunk after length and SHA-256 validation |
| `cache_body_bytes_read` | Bytes read from cached chunk files, including an invalid cached chunk encountered before refetching |
| `http_requests_attempted` | Actual attempts to open range requests, including attempts that fail |
| `http_requests_succeeded` | Range responses accepted after the strict HTTP status, range, encoding, and body-length checks |
| `http_body_bytes_read` | Response body bytes returned by `read`, plus partial body bytes exposed by a read error; includes bodies rejected after reading |
| `error` | Present on a failed invocation; exception type and message |

Counters start at zero for each invocation and aggregate across its indexed
files. They do not derive from the number of entries in a cache manifest. A
reported zero HTTP request count means no range request was attempted during
that invocation.

`http_body_bytes_read` is an application read count. It does not measure HTTP
headers, TLS overhead, socket prefetch, or total traffic on the wire. Hub file
discovery contributes to elapsed time but not to range request or body-byte
counts. These statistics describe header indexing, not model inference speed.

If indexing fails, the CLI writes the counters collected so far with
`status: "FAILED"`, provided the stats path is writable, and preserves the
original failure. The stats path must differ from the model index output path.
Omit `--stats` to retain the existing CLI output behavior without a report.

## Cache checkpoints during indexing

Index construction publishes the cache manifest after every 64 fetched ranges
and at each successfully parsed file boundary. It also attempts to publish
pending ranges if parsing fails; a publication failure preserves the original
parser or transport error. Successful completion leaves every fetched range
in the manifest. Individual `RangeReader` callers retain immediate publication
by default.

The complete manifest is written atomically at each checkpoint. Abrupt process
termination can leave up to one group of 64 recently fetched ranges outside the
last published manifest, so a later invocation may fetch those ranges again.
This bounded checkpoint interval avoids encoding the entire growing manifest
after every header read. It does not change requested ranges, cached chunk
contents, the model index, or runtime counter definitions.
