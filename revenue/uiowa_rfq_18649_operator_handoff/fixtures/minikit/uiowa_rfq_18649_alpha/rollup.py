"""Fixture component that works. FICTION."""


def rollup(rows):
    """Sum supplied counts. An absent count stays absent; it never becomes 0."""
    total = 0
    unknown = 0
    for r in rows:
        v = r.get("count")
        if v is None:
            unknown += 1
        else:
            total += int(v)
    return {"total": total, "unknown_inputs": unknown}
