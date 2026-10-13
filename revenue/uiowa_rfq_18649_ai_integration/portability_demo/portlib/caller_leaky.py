"""NEGATIVE CONTROL -- deliberately non-portable calling code. Do not copy.

This file exists so the portability scanner has something real to catch, and so the
worked example demonstrates a gap as well as a strength. It is the shape most
integrations actually have on the first pass: the provider is imported directly into
workflow code, the vendor wire fields are read inline, and the vendor exception type
is caught by name.

Every line marked LEAK is a line that must be edited when the provider is replaced.
There are four leaks in ~20 lines of logic. That ratio is the portability problem.
"""

from portlib.providers.fake_alpha import AlphaTimeout, _AlphaWireClient  # LEAK 1 + 3


def route_document_leaky(policy, document, fail_mode=None):
    client = _AlphaWireClient(fail_mode=fail_mode)                        # LEAK 1
    try:
        raw = client.infer({"input": document.text,
                            "labels": list(policy.categories)})           # LEAK 2: wire request shape
    except AlphaTimeout:                                                  # LEAK 3: vendor error taxonomy
        return {"doc_id": document.doc_id, "queue": policy.human_review_queue,
                "reason": "timeout"}
    label = raw["label"]                                                  # LEAK 4: wire response shape
    score = raw["score"]                                                  # LEAK 4
    if score < policy.confidence_floor:
        return {"doc_id": document.doc_id, "queue": policy.human_review_queue,
                "reason": f"low score {score}"}
    return {"doc_id": document.doc_id, "queue": f"queue.{label}", "reason": "ok"}
