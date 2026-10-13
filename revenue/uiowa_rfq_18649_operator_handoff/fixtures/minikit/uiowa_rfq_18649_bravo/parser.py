"""Fixture component that is broken. FICTION."""


def parse_pair(text):
    # Deliberate defect: a value containing '=' is truncated. The fixture's own
    # test catches it, so the verifier must refuse to call bravo WORKING.
    k, _, v = text.partition("=")
    return k.strip(), v.strip().split("=")[0]
