"""Finite deterministic property exercise and bounded batch smoke run.

These generated inputs are synthetic, never customer/payables execution proof.
Run from this directory with Python 3.10+; no dependencies or network required.
"""
from copy import deepcopy
import json
import platform
import random
import sys
import time

import batch_reconcile as m
from test_batch_reconcile import AS_OF, invoice, snapshot


def main() -> int:
    rng = random.Random(20260917)
    start = time.perf_counter()
    for index in range(250):
        p = snapshot()
        capacity = rng.randint(2, 50)
        price = rng.randint(1, 100)
        p["purchase_orders"][0].update(quantity_milliunits=capacity*1000, unit_price_minor=price)
        p["receipts"][0]["quantity_milliunits"] = capacity*1000
        quantities = [rng.randint(1, 8) for _ in range(rng.randint(1, 8))]
        p["invoices"] = [invoice(f"I-{n}",q*1000,price=price) for n,q in enumerate(quantities)]
        expected = "REVIEW_CLEAR" if sum(quantities) <= capacity else "HOLD_REVIEW"
        report = m.compile_review(p,as_of=AS_OF)
        if report["state"] != expected:
            raise RuntimeError(f"scenario {index}: capacity oracle disagreement")
        shuffled = deepcopy(p); rng.shuffle(shuffled["invoices"])
        if m.canonical(report) != m.canonical(m.compile_review(shuffled,as_of=AS_OF)):
            raise RuntimeError(f"scenario {index}: order dependence")
        if any(report["authority"].values()):
            raise RuntimeError(f"scenario {index}: authority widened")
    scenarios_seconds = time.perf_counter()-start
    p = snapshot()
    p["purchase_orders"][0]["quantity_milliunits"] = 1_000_000
    p["receipts"][0]["quantity_milliunits"] = 1_000_000
    p["invoices"] = [invoice(f"L-{n:04d}",1000) for n in range(1000)]
    started = time.perf_counter(); report = m.compile_review(p,as_of=AS_OF)
    large_seconds = time.perf_counter()-started
    if report["state"] != "REVIEW_CLEAR" or len(report["invoices"]) != 1000:
        raise RuntimeError("1000-invoice smoke run failed")
    if not m.verify_report(p,report):
        raise RuntimeError("1000-invoice report verification failed")
    print(json.dumps({"evidence_class":"SYNTHETIC_LOCAL_EXECUTION", "python":platform.python_version(),
                      "optimize":sys.flags.optimize,"seed":20260917,"scenario_count":250,
                      "permutation_checks":250,"scenario_seconds":round(scenarios_seconds,6),
                      "smoke_invoice_count":1000,"smoke_input_bytes":len(m.canonical(p)),
                      "smoke_elapsed_seconds":round(large_seconds,6),"smoke_receipt_sha256":report["receipt_sha256"],
                      "result":"PASS"},indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
