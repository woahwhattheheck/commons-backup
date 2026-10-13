from .parity_probe import compare_rows

def demo_input():
    """The retained one-row demonstration, usable through the operator CLI."""
    return {
        "schema": "report-row-parity/v1",
        "key_fields": ["id"],
        "compare_fields": ["value"],
        "legacy_rows": [{"id": "A", "value": 1}],
        "target_rows": [{"id": "A", "value": 2}],
    }

def run_demo():
    data = demo_input()
    return compare_rows(data["legacy_rows"], data["target_rows"], data["key_fields"], data["compare_fields"])
