# UIOWA-129 — evidence-preserving timestamp adapter

**Working offline component. All included records are synthetic. No University finding, recovery approval, engagement acceptance or personal scheduling is performed.**

The adapter resolves supplied instants before timeline tools subtract them. It never borrows the operator's local timezone, assigns a DST fold without evidence, or treats an unknown timestamp as zero. It includes a real integration rehearsal with the existing UIOWA-064 delivery calculator; that calculator already handles numeric offsets correctly. This component extends its input boundary rather than replacing its metric definitions.

Builder: ZZ-TESSERA-46 / GPT-6 Astra Pro. Work order: UIOWA-129. Durable work record: [Commons #16170](https://github.com/woahwhattheheck/commons/issues/16170).

## Run from the repository root

Python 3.12+ (executed here with Python 3.13.5) and an available IANA timezone database are required for named-zone inputs. `zoneinfo` uses the operating system database or the separately installed `tzdata` package; neither is silently downloaded. Numeric-offset timestamps need no timezone database. Missing timezone data produces an explicit unresolved diagnostic. This is the documented [Python zoneinfo data-source behavior](https://docs.python.org/3/library/zoneinfo.html#data-sources).

```sh
python revenue/uiowa_rfq_18649_timestamps/timestamp_adapter.py revenue/uiowa_rfq_18649_timestamps/fixtures/timeline_cases.json --output timeline-report.json
python -m unittest discover -s revenue/uiowa_rfq_18649_timestamps/tests -v
PYTHONOPTIMIZE=1 python -O -m unittest discover -s revenue/uiowa_rfq_18649_timestamps/tests -v
python revenue/uiowa_rfq_18649_timestamps/rehearse_delivery.py
```

The full suite includes the real sibling `revenue/uiowa_rfq_18649_delivery_metrics/` calculator and fixture. A component-only copy can run `test_timestamps.py`; the integration suite deliberately fails rather than skips when its published dependency is missing.

`timeline-report.json` contains 13 events and 8 interval requests. Three known intervals are 3,600 seconds and one is exactly zero. Five event timestamps and four requested intervals remain non-resolved: the fixture intentionally includes absent, ambiguous, nonexistent and contradictory evidence. This is a successful diagnostic demonstration, not eight successful measurements. Add `--require-resolved` for exit 1 whenever any event/interval is missing, unresolved or invalid. Malformed input or I/O failure returns 2; normal diagnostic generation returns 0. No source packet can be overwritten by the report path.

## Timestamp contract

Each event's `timestamp` is a string, null, or an object with `value` and optional `zone` and `fold`. Input shape is documented in [packet.schema.json](packet.schema.json). Event and interval IDs are unique within their own collections. Unknown interval references stay unresolved; duplicate IDs and duplicate JSON keys are rejected. Extra event/packet metadata is retained unchanged in the report.

```json
{
  "schema_version": 1,
  "synthetic": true,
  "events": [
    {"id": "release", "timestamp": {"value": "2026-11-01T01:30:00", "zone": "America/New_York", "fold": 0}},
    {"id": "verified", "timestamp": {"value": "2026-11-01T01:30:00", "zone": "America/New_York", "fold": 1}}
  ],
  "intervals": [{"id": "elapsed", "start": "release", "end": "verified"}]
}
```

These two identical-looking wall-clock values identify different instants. Output duration is 3,600 seconds. Removing either fold makes the corresponding timestamp ambiguous and suppresses the duration. A reported recovery event here is fictional: converting its time does not validate what its author claimed happened.

The accepted lexical profile is `YYYY-MM-DDTHH:MM:SS[.ffffff][Z|+HH:MM|-HH:MM]`; lowercase `t` and `z` are accepted. Date-only values, abbreviations such as CST, surrounding nonblank whitespace, bracket annotations, leap seconds and more than six fractional digits are rejected with reason codes. This is an intentionally bounded profile, not a claim to implement every ISO-8601/RFC-9557 form.

| Evidence | Result |
|---|---|
| Explicit numeric offset | Known UTC instant; original representation retained |
| Local time plus valid IANA zone, one real candidate | Resolved from supplied zone |
| Repeated local time, no fold/offset evidence | `ambiguous_local_time`; both candidates retained; no chosen instant |
| Local time inside a timezone gap | `nonexistent_local_time`; fold cannot repair it |
| Numeric offset contradicts the supplied IANA zone | `offset_zone_mismatch`; no accepted instant |
| Missing offset and missing zone | `missing_offset_or_zone`; no guessed timezone |
| Missing or unknown IANA data | `zone_unavailable`; no fallback to local time |
| Null/blank | `missing_timestamp`, distinct from zero elapsed time |
| End precedes start | `reversed_timeline`, signed discrepancy retained, positive duration not invented |

**`Z` and `-00:00` are known UTC instants, not unknown instants.** Their local offset is unspecified under [RFC 9557 section 2](https://www.rfc-editor.org/rfc/rfc9557.html#section-2). When a separate IANA zone is supplied, the adapter renders that known instant in the zone; it does not reinterpret the UTC clock fields as local. A numerical `+00:00` paired with a nonzero IANA local offset is instead a checked consistency claim.

The [PEP 495 fold specification](https://peps.python.org/pep-0495/) explains why attaching a timezone object is insufficient to validate a local time. The implementation enumerates both fold values and round-trips each through UTC. A candidate must recover both the local fields and fold before being accepted. Tests include a 30-minute Lord Howe transition and Apia's skipped civil day; there is no hardcoded one-hour-DST assumption.

## CSV bridge into existing components

```sh
python revenue/uiowa_rfq_18649_timestamps/csv_bridge.py revenue/uiowa_rfq_18649_timestamps/fixtures/delivery_dst.csv --output delivery-normalized.csv --audit delivery-time-audit.json
python revenue/uiowa_rfq_18649_delivery_metrics/calculator.py delivery-normalized.csv --window-start 2026-11-01T00:00:00Z --window-end 2026-11-02T00:00:00Z --service synthetic-dst
```

Choose new output/audit names for each run: existing outputs are refused to prevent accidental reuse of stale evidence. Source, normalized output and audit must be distinct. Successful output retains every input column and its order, including notes and explicit sidecars `<timestamp_field>_zone` and `<timestamp_field>_fold`. The audit retains original parsed rows and source-file SHA-256; JSON source strings remain unchanged. CSV lexical quoting/newline representation may change, so a CSV byte-identity claim is not made.

Default time fields are `commit_at,deployed_at,recovered_at`; `deployed_at` is required. Optional blank times remain blank with a missing diagnostic. **Any nonblank unresolved/invalid timestamp or missing required timestamp blocks the entire normalized CSV**, while the diagnostic audit is written. There is no silent row deletion or partial passing file. A ready conversion is not a statement that the source rows meet every downstream metric rule; the existing calculator still validates service scope, classifications and chronology.

Other lifecycle adapters can supply explicit mappings:

```sh
python revenue/uiowa_rfq_18649_timestamps/csv_bridge.py lifecycle.csv --fields joined,retired --required joined --id-field event_id --output lifecycle-normalized.csv --audit lifecycle-audit.json
```

Reusable APIs: `normalize(spec)`, `elapsed(start, end)`, `normalize_packet(packet)` and `convert_rows(rows, timestamp_fields=..., required_fields=..., id_field=...)`. Returned source structures are copied, not mutated. Use `duration_microseconds` for exact integer arithmetic; `duration_seconds` is a display convenience. Consumers must preserve JSON integer precision if handling historical/extreme dates. `interval_from_results` is a lower-level helper for this module's own normalized records, not a verifier of externally asserted normalization results.

## Real-component acceptance and provenance

[rehearse_delivery.py](rehearse_delivery.py) imports and executes the real sibling calculator using its actual source, then removes its private import name. It never writes to that component. [evidence/delivery_rehearsal.json](evidence/delivery_rehearsal.json) retains executed native results, not a handwritten reconstruction of their metric values.

The recorded dependency blobs are calculator `13d7a895f5785e9cc7e3a35fc10a851a468547ab` and fixture `8fac02fb9d947deed7df99d563ab05d949127793`. Both were matched byte-for-byte before execution. For pinned replay add `--expect-calculator-blob 13d7a895f5785e9cc7e3a35fc10a851a468547ab`; a changed source then fails explicitly. Without this option the rehearsal tests the current checkout and records its actual blobs, allowing compatible future component improvements.

Six executable checks establish: unchanged native metrics for the original eight deployments; unchanged metrics after representing those same instants in mixed offsets; the expected eight-row population; one-hour DST lead time; one-hour DST recovery; and suppression of a CSV when recovery's fold evidence is removed. The normal fixture retains 11h median/14.875h mean lead time, 4 deployments/week, and 3h median recovery. No metric definition or maturity scale was modified.

Named-zone results include a SHA-256 of the exact TZif bytes loaded for conversion. The hash is content provenance, not authentication. Replays require equivalent timezone data; timezone law/database changes can legitimately change a future local-time conversion. A process caches the loaded bytes, preventing a mid-run database update from mixing old resolver objects with new provenance hashes.

## Boundaries

No clock synchronization, source authenticity, causal ordering, actual service restoration or business-hours calculation is established. Elapsed arithmetic uses Python's UTC datetime model and does not account for leap seconds. This tool does not infer missing observations, procurement choices, individual performance, University practices, appointments or commitments. No network, shell command, model service or live system is called by the runtime. The test suite invokes local Python entry points in temporary directories only.
