from .probe import exact_equal, row_key
from .validation_probe import ValidationError, require_fields, require_rows


def index_rows(rows, key_fields, compare_fields, side):
    indexed = {}
    for ordinal, row in enumerate(require_rows(rows), 1):
        for field in key_fields + compare_fields:
            if field not in row:
                raise ValidationError(f"{side} row {ordinal} is missing field {field!r}")
        key = row_key(row, key_fields)
        if any(type(value) not in (str, int) for value in key):
            raise ValidationError(f"{side} row {ordinal} keys must be strings or integers")
        # Keep typed identity explicit; Python otherwise aliases True and 1.
        identity = tuple((type(value).__name__, value) for value in key)
        if identity in indexed:
            previous = indexed[identity][2]
            raise ValidationError(f"{side} rows {previous} and {ordinal} have the same key; no rows were discarded")
        indexed[identity] = (key, row, ordinal)
    return indexed

def compare_rows(legacy_rows, target_rows, key_fields, compare_fields):
    require_fields(key_fields, "key_fields", 4)
    require_fields(compare_fields, "compare_fields", 32)
    legacy = index_rows(legacy_rows, key_fields, compare_fields, "legacy")
    target = index_rows(target_rows, key_fields, compare_fields, "target")
    findings = []
    for identity in sorted(set(legacy) | set(target), key=repr):
        left_entry = legacy.get(identity)
        right_entry = target.get(identity)
        key = (left_entry or right_entry)[0]
        if left_entry is None:
            findings.append(("EXTRA_TARGET_ROW", key, None))
            continue
        if right_entry is None:
            findings.append(("MISSING_TARGET_ROW", key, None))
            continue
        left, right = left_entry[1], right_entry[1]
        for field in compare_fields:
            if not exact_equal(left[field], right[field]):
                findings.append(("VALUE_DRIFT", key, field))
    return findings
