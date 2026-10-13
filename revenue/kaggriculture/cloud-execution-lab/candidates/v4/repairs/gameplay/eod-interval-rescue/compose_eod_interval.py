# SPDX-License-Identifier: Apache-2.0
"""Compose this proof into the existing EOD helper; never run a V4 materializer.

Usage: python compose_eod_interval.py donor_9ad40924.py /tmp/r04_eod_capacity_rescue.py
The output must not exist. No repository ref, key, config or archive is edited.
A later EOD successor requires an explicit semantic rebase; drift is rejected.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
from pathlib import Path

DONOR_BLOB = "9ad4092453e2332b0914f90ca89791b18f2229c2"
SOLVER_BLOB = "02edb332c9a9aef8093243587e3f9e0ed9208860"
OLD_CALL = "    discarded = _discarded_products(inventories, capacity - shed_total, r04.PRODUCTS)"
NEW_CALL = '''    discarded = certified_rescue_vector(
        inventories, shed, capacity=capacity,
        order_slots=h3c.STANDARD_CONFIG["maxMarketOrdersPerTurn"] - len(market))'''


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def compose(donor: bytes, solver: bytes) -> bytes:
    """Pure, exact-source one-callsite composition; no candidate code executes."""
    if git_blob(donor) != DONOR_BLOB or git_blob(solver) != SOLVER_BLOB:
        raise ValueError("EOD donor/solver byte drift; review and rebase explicitly")
    source, proof = donor.decode("utf-8"), solver.decode("utf-8")
    if source.count(OLD_CALL) != 1:
        raise ValueError("EOD vector-selection anchor must occur exactly once")
    proof_ast = ast.parse(proof)
    # The pinned proof is self-contained after its docstring/future import.
    start = next(node.lineno for node in proof_ast.body if isinstance(node, ast.Assign))
    body = "\n".join(proof.splitlines()[start-1:]) + "\n"
    source = source.replace(OLD_CALL, NEW_CALL)
    source = source.replace(
        "exactly the unmodified path. Partial vector rescue is deliberately forbidden.",
        "exactly the unmodified path. The interval extension below additionally admits\n"
        "partial vectors only when their added admission is order-invariant and exact.")
    source = source.replace(
        '"""Append the bounded, whole loss vector or preserve exact parent identity."""',
        '"""Append a certified whole/partial rescue or preserve exact parent identity."""')
    source = source.replace(
        "    # A partial vector can change which later product the drop admits. Require\n"
        "    # coverage and executable raw slots for the WHOLE vector before any edit.",
        "    # The interval proof already requires exact replenishment of every sold\n"
        "    # product. Retain the incumbent stock, slot and price checks as well.")
    output = (source + "\n\n# BEGIN existing-key EOD interval proof; no new wrapper or key.\n" + body).encode("utf-8")
    compile(output, "<composed-existing-eod-helper>", "exec")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("donor", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    donor = args.donor.read_bytes()
    solver = Path(__file__).with_name("eod_interval.py").read_bytes()
    output = compose(donor, solver)
    # Exclusive creation prevents overwriting either source or an active helper.
    with args.output.open("xb") as stream:
        stream.write(output)
    print("output_git_blob=" + git_blob(output))


if __name__ == "__main__":
    main()
