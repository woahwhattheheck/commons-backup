# Saving reports without replacing their source catalog

The UIOWA-047 assessor checks its destination, stages a complete report beside it,
flushes the staged file, checks the destination again, then replaces only the
distinct report path. A normal replacement of an existing ordinary report remains
supported. Assessment and rendering behavior are separate from file delivery.

The original repair and historical execution are retained in
[issue #16408](https://github.com/woahwhattheheck/commons/issues/16408); its runtime
integration is [PR #19246](https://github.com/woahwhattheheck/commons/pull/19246).
The original kit is [PR #16122](https://github.com/woahwhattheheck/commons/pull/16122).

## Choose the intended destination

From this component directory, print the fictional demonstration or deliberately
save a distinct report:

```sh
python3 test_data_assessor.py fixtures/catalog.synthetic.json
python3 test_data_assessor.py fixtures/catalog.synthetic.json --format json --output report.json
```

The second command intentionally replaces an existing ordinary `report.json`.
Choose a new filename when the prior report must be kept. The CSV importer's
separate `--output` always requires a new file; see [CSV intake](CSV_INTAKE.md).

The assessor refuses an output that is the input path, a resolved source alias or
a hard link to the source. It also refuses all output symbolic links, including
links to distinct reports and dangling links. Choose an ordinary output path
instead. A missing parent directory or non-regular destination produces a delivery
error rather than a successful report save.

Expected output failures return a readable diagnostic and exit 2. Encoding or
staging failures do not truncate the previous report. Exit 0 means the report was
generated and delivered, not that every assessment check was evidenced.

## Filesystem and operational limits

This is one-file staged replacement, not a multi-file transaction, backup system
or power-loss durability guarantee. The directory itself is not fsynced. Keep
independent backups when prior reports must remain versioned; successful
replacement intentionally replaces the selected previous report.

Replacing a distinct hard-linked report replaces only the selected directory
entry, leaving its other names on their previous bytes. Existing permission mode
bits are copied, not ownership, access-control lists or extended attributes.
New reports inherit the temporary file's restricted mode on POSIX systems.

Use a caller-controlled ordinary directory and do not concurrently change path
bindings while saving. The second alias check is not an adversarial filesystem-
race guarantee. Staging cleanup is attempted on pre-replacement failures, but an
operating-system refusal to remove a staging file cannot be guaranteed away.
Keyboard interruption propagates after cleanup instead of becoming CLI exit 2.

Only fictional input is used by the demonstration. No live-system access,
University records, external contact, scheduling or paid runner is required.
