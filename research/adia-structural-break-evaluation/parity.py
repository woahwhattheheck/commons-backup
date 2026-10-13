"""Exercise the exact pinned upstream score() body on locally built frames.

Requires pandas/scikit-learn. The real scorer algorithm is extracted unchanged;
only file loading, log context, and the return-value wrapper are supplied locally.
This does not claim full Crunch runner / participant data / leaderboard parity.
The upstream source is not vendored; fetch the documented public pinned blob.
"""
from __future__ import annotations

import argparse
import ast
from contextlib import nullcontext
import hashlib
import json
from pathlib import Path
import random
from types import SimpleNamespace

from evaluation import SCORER, Trace, digest, ts_auc


def load_score(path: Path):
    source = path.read_bytes()
    blob = hashlib.sha1(b"blob " + str(len(source)).encode() + b"\0" + source).hexdigest()
    if blob != SCORER["git_blob"]:
        raise ValueError(f"upstream source does not match pinned Git blob: {blob}")
    tree = ast.parse(source)
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "score"]
    if len(nodes) != 1:
        raise ValueError("expected one upstream score function")
    module = ast.Module(body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0), nodes[0]], type_ignores=[])
    ast.fix_missing_locations(module)
    from sklearn.metrics import roc_auc_score
    namespace = {"roc_auc_score": roc_auc_score, "ParticipantVisibleError": ValueError,
                 "ScoredMetric": lambda score, details: score,
                 "tracer": SimpleNamespace(log=lambda *a, **k: nullcontext())}
    exec(compile(module, str(path), "exec"), namespace)
    return namespace


def upstream_value(namespace: dict, traces: list[Trace]) -> float:
    import pandas as pd
    indices, scores, labels = [], [], []
    for case, trace in enumerate(traces):
        for t, value in enumerate(trace.scores):
            indices.append((case, 1000 + t))
            scores.append(value)
            labels.append(trace.label(t))
    index = pd.MultiIndex.from_tuples(indices, names=["id", "time"])
    prediction = pd.DataFrame({"prediction": scores}, index=index)
    truth = pd.DataFrame({"target": labels}, index=index)
    namespace["_load_prediction"] = lambda path: prediction
    namespace["_load_y_test"] = lambda path: truth
    metric = SimpleNamespace(name="ts-auc", id="metric")
    return namespace["score"]("unused", "unused", [(None, [metric])])["metric"]


def check(path: Path, panels: int = 128) -> dict:
    if type(panels) is not int or not 1 <= panels <= 10000:
        raise ValueError("panels must be an integer in [1,10000]")
    import pandas as pd
    import sklearn
    namespace = load_score(path)
    largest_error = 0.0
    for panel in range(panels):
        rng = random.Random(87100 + panel)
        traces = []
        for i in range(2 + panel % 29):
            n = rng.randrange(1, 32)
            tau = None if i % 3 == 0 else rng.randrange(n)
            scores = tuple(rng.choice((0.0, 0.1, 0.5, 0.9, 1.0)) for _ in range(n))
            traces.append(Trace(str(i), i, "parity", digest([panel, i]), tau, scores))
        actual = ts_auc(traces)["ts_auc"]
        expected = upstream_value(namespace, traces)
        error = abs(actual - expected)
        largest_error = max(largest_error, error)
        if error > 1e-12:
            raise ValueError(f"parity failed at panel {panel}: {actual} != {expected}")
    return {"result": "PASS", "panels": panels, "maximum_absolute_error": largest_error,
            "source": dict(SCORER), "evidence_class": "EXTRACTED_PUBLIC_SCORER_FUNCTION_LOCAL_FRAMES",
            "full_crunch_runner_executed": False, "pandas": pd.__version__, "sklearn": sklearn.__version__}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scorer_source", type=Path)
    args = parser.parse_args()
    print(json.dumps(check(args.scorer_source), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
