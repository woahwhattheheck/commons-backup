# Bounded public HTTP source capture

`public_http_capture.py` captures a caller's explicit list of observed HTTP(S) URLs into a new private directory. It keeps each response's status, selected headers, body identity, timing and completeness in `acquisition.json`. The manifest is checkpointed before each request and after its completed or failed capture, so a later transport failure does not discard the earlier source records.

This is the reusable acquisition step used before a source reader or business application. It does not crawl links, parse documents, decide whether a solicitation is current, or publish captured bodies.

## Run

Prepare a small UTF-8 JSON file using the actual URLs already found in the source task:

```json
{
  "operation_id": "COUNTY-ADDENDUM-CAPTURE",
  "sources": [
    {
      "id": "official-board",
      "url": "https://example.org/observed-board",
      "filename": "board.html",
      "accept": "text/html,application/xhtml+xml"
    },
    {
      "id": "posted-addendum",
      "url": "https://example.org/observed-addendum.pdf",
      "filename": "addendum.pdf",
      "accept": "application/pdf"
    }
  ]
}
```

The example URLs above are placeholders, not a discovery or request plan. Replace them with the independently observed targets. Then run:

```sh
python3 -B host/public_http_capture.py \
  --sources /absolute/path/request.json \
  --out /absolute/path/new-capture \
  --max-source-bytes 8388608 \
  --max-total-bytes 8388608 \
  --io-timeout 20
```

The output directory must not already exist. The command creates `raw/` and `acquisition.json` there, prints a compact JSON summary to stdout, and leaves source bodies on disk. The directory is created with mode 0700 and body/manifest files with mode 0600, subject to the platform's filesystem semantics. It does not modify the input specification.

An interrupted or partial capture is retained. Inspect its manifest and body files before selecting any genuinely missing requests for a separate new capture directory. The command has no automatic retry, resume, overwrite or scheduling mode.

## Request contract

The top-level object accepts only `operation_id` and `sources`. There must be 1–32 sources. A source accepts `id`, `url`, and optional `filename` / `accept`. IDs and filenames must be unique simple basenames, start with an ASCII letter or digit, and contain at most 128 letters, digits, dots, underscores or hyphens. The default filename is the ID followed by `.body`; the default Accept header is `*/*`.

The entire JSON file is limited to 128 KiB and read through one descriptor. It must resolve to a regular file and remain unchanged during that read. URLs must be HTTP(S), include a host, contain no whitespace, URL userinfo or fragment, and fit 8,192 characters. An Accept value must be one header line of at most 512 characters. All entries and limits are validated before the output directory is created or a request is attempted.

The request method is always GET. The command configures no origin-authentication handler or cookie jar. It requests identity content encoding and leaves Python's normal proxy environment and HTTPS certificate verification behavior in place. It does not disable a proxy, install a global opener, supply credentials, or change network access.

Redirects are not followed. A redirect response's status, Location header and available body are captured at the observed URL. A caller can then interpret that response in its own source task. A login redirect is not permission to log in or discover a hidden route.

These behaviors use the standard-library [URL opener and redirect handler](https://docs.python.org/3/library/urllib.request.html). Python exposes an [HTTPError as a readable response](https://docs.python.org/3/library/urllib.error.html), which lets the command retain a complete error body without treating it as a successful source document.

## Bounds and completeness

| Limit | Default and behavior |
| --- | --- |
| Source entries | At most 32, sequential |
| Per-source body | 8,388,608 bytes; configurable positive integer |
| Aggregate body | 8,388,608 bytes across all attempted responses; configurable positive integer |
| Body read chunk | At most 65,536 bytes, and never above the remaining body budget |
| Blocking I/O timeout | 20 seconds; configurable finite value greater than zero and at most 120 |
| Retained headers | Ten named headers; first four values per name, up to 2,048 characters each, with truncation counts recorded |

The aggregate counter includes bytes returned by a body read even if a later file write fails. `totals.retained_body_bytes` separately counts the files whose exact identities were obtained. HTTP error and redirect bodies consume the same budgets as successful responses.

If a usable Content-Length exceeds the remaining per-source or aggregate budget, the command retains the response metadata and closes it before reading a body. For transferred bodies, a declared HTTP framing length or a response-end observation establishes completeness. Bodyless HTTP statuses are treated as zero-length responses. A premature end before the declared length is incomplete.

For a response without a usable length, reaching the exact budget before observing its end is partial. The command does not perform an extra one-byte body read beyond the budget merely to decide whether the document would have fit. A later source is recorded as `NOT_REQUESTED_BUDGET` when earlier reads have consumed the aggregate budget.

HTTP framing is handled by Python's [HTTPResponse](https://docs.python.org/3/library/http.client.html); hashes cover the body bytes delivered by that reader and retained on disk, not wire headers or chunk framing. The command does not decompress an unexpected Content-Encoding. The header remains available for a downstream reader's admission decision.

The I/O timeout is **not a total wall-clock deadline**. Python applies it to blocking operations; name resolution, multiple reads and multiple sources do not become one wall-clock budget. Use the caller's existing process deadline and worker admission rules when those are required. The command does not alter or introduce those rules.

## Manifest and exit status

A source record contains its requested URL and Accept header, planned body file, request-attempt flag, status and response URL when available, selected headers, effective declared body length, read byte count, completion basis, elapsed time and UTC observations. A retained file receives its relative path, actual byte count, SHA-256 and Git blob SHA-1. The command also hashes the bytes returned by the HTTP reader; a complete capture requires that digest to match the retained file. A partial write can legitimately have fewer retained bytes than returned bytes.

A readable HTTP error is not a transport exception. In particular, a complete 302 or 404 body can have `state: COMPLETE` and `body_complete: true` while `http_success: false`. This reports capture completeness. It does not assert that the requested evidence was available, authoritative, acceptable to a downstream reader, or ready for any business action.

| Source state | Meaning |
| --- | --- |
| `COMPLETE` | The response body ended within its budget and its retained file identity was obtained |
| `PARTIAL` | A body file was created, but a read, write, size or identity problem prevented complete capture |
| `FAILED` | No body file was created, such as a transport error or declared-size refusal |
| `NOT_REQUESTED_BUDGET` | Earlier responses consumed the aggregate body budget |
| `PENDING` / `IN_PROGRESS` | Checkpoint state; the capture has not recorded a completed attempt for this entry |

Each checkpoint is written completely, flushed and atomically replaced within the new capture directory. A checkpoint write failure stops the command; the previous manifest and any body files remain available. Abrupt process termination can leave an in-progress record and a body file without a completed identity. The command makes no claim that such a file is complete.

| Exit | Meaning |
| --- | --- |
| 0 | Every requested HTTP body was captured completely; inspect each HTTP status separately |
| 3 | One or more captures are incomplete, failed or unrequested because of the aggregate budget; a final manifest and compact JSON summary are available |
| 2 | Invalid CLI usage or request contract; no GET is attempted |
| 1 | A local input/output or checkpoint failure; inspect the diagnostic and any prior checkpoint |
| 130 | Keyboard interruption; inspect the retained checkpoint |

Normal capture results go to stdout as JSON. Incomplete capture and fatal diagnostics go to stderr. The summary gives the manifest path, totals and each source's status/state/body identity without printing captured body content.

## Python use and composition

```python
from public_http_capture import capture_sources

manifest = capture_sources(
    request_spec,
    "/absolute/path/new-capture",
    max_source_bytes=8 * 1024 * 1024,
    max_total_bytes=8 * 1024 * 1024,
    io_timeout=20,
)
```

The Python API takes the same parsed specification. Expected per-source acquisition failures are manifest data; invalid specifications and local checkpoint failures raise. It uses only the standard library.

A source reader should consume the observed status and complete body identity under its own existing contract. For example, a PDF reader can require the expected status and PDF signature; that decision is outside this capture layer. A procurement packet can preserve a board timeout while binding separately captured controlling documents without inventing a board hash.

For an authorized later transfer, use [file_chunk_export.py](FILE_CHUNK_EXPORT.md) and the [connected file-chunk consumer](CONNECTED_FILE_CHUNKS.md) on the retained files. This command does not repeat their transport logic or publish raw sources. Body retention and publication permissions remain with the source task.

Captures are sequential observations at recorded times, not an atomic snapshot of a website. The manifest does not prove that other pages or amendments are absent. It records only the explicit requests that the caller supplied.
