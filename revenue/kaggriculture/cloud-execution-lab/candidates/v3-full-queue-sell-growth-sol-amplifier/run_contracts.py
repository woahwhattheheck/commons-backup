# SPDX-License-Identifier: Apache-2.0
"""Run the SOL-AMPLIFIER contracts with path-bound module custody.

The original workflow invoked unittest after adding the canonical lab root to
``sys.path``.  The integration class then inserted that root at index zero and
``import candidate`` resolved the lab's unrelated compatibility entrypoint,
not this candidate.  Preload every lane module from its exact file before test
discovery; later imports are therefore identity-bound through ``sys.modules``.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
DEFAULT_TESTS = (
    "test_full_queue_sell_growth.py",
    "test_action_bound_panel.py",
)


def load_exact(name: str, path: Path):
    source = path.resolve(strict=True)
    if source.parent != HERE:
        raise RuntimeError(f"contract module escaped candidate directory: {source}")
    spec = importlib.util.spec_from_file_location(name, source)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {source}")
    module = importlib.util.module_from_spec(spec)
    prior = sys.modules.get(name)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        if prior is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = prior
        raise
    return module


def main(argv: list[str] | None = None) -> int:
    values = list(sys.argv[1:] if argv is None else argv) or list(DEFAULT_TESTS)
    expected = set(DEFAULT_TESTS)
    if set(values) != expected or len(values) != len(expected):
        raise ValueError(f"expected each contract suite exactly once: {DEFAULT_TESTS}")

    root = str(HERE)
    while root in sys.path:
        sys.path.remove(root)
    sys.path.insert(0, root)

    # Bind names imported by the tests before their setUpClass mutates sys.path.
    load_exact("growth_patch", HERE / "growth_patch.py")
    load_exact("audit_change", HERE / "audit_change.py")
    load_exact("run_panel", HERE / "run_panel.py")
    load_exact("candidate", HERE / "candidate.py")

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for filename in values:
        module_name = Path(filename).stem
        module = load_exact(module_name, HERE / filename)
        suite.addTests(loader.loadTestsFromModule(module))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
