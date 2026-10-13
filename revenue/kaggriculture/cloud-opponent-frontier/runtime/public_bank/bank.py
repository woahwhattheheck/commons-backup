"""Portable, fresh-instance adapters for the pinned T07 public opponent bank."""
from __future__ import annotations

import argparse
import builtins
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
from typing import Callable


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Cannot load {path}")
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def make_agent(root: Path, identity: str) -> Callable:
    """Create one policy instance; call this anew for every actor/match."""
    root = Path(root).resolve()
    entry = json.loads((root / "BANK.json").read_text())["entries"][identity]
    source = root / entry["source"]
    source_bytes = source.read_bytes()
    if hashlib.sha256(source_bytes).hexdigest() != entry["source_sha256"]:
        raise ValueError("Opponent source differs from bank snapshot")
    official = module(root / "contract/official.py", "t07_bank_contract")
    original = official.contract()["get_last_callable"]
    mode = entry["assignment"]

    def inspected(raw, *args, **kwargs):
        # The official loader reads once during construction, then compiles
        # lazily. Compare its retained program BEFORE executing it. Its UTF-8
        # text reader performs universal-newline conversion; only mirror that
        # conversion here, keeping the manifest identity on the original bytes.
        expected = source_bytes.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
        if raw != expected:
            raise ValueError("Opponent loader source differs from bank snapshot")
        function = original(raw, *args, **kwargs)
        if mode != "not_applicable":
            observed = bool(function.__globals__.get("_HUNGARIAN"))
            if observed != (mode == "scipy"):
                raise RuntimeError("Observed assignment branch differs from bank entry")
        return function

    official.contract()["get_last_callable"] = inspected
    run = official.make_agent(source)
    first = True

    def agent(observation, configuration=None):
        nonlocal first
        if not first:
            return run(observation, configuration or {})
        # Only the optional-import environment differs. Vendored policy bytes
        # and the official last-callable / argument-slicing contract are intact.
        previous_import = builtins.__import__

        def optional_import(name, *args, **kwargs):
            if mode == "greedy" and name.split(".")[0] in ("numpy", "scipy"):
                raise ImportError("T07 explicit stdlib/greedy runtime")
            return previous_import(name, *args, **kwargs)

        try:
            if mode == "scipy":
                import numpy
                import scipy
                from scipy.optimize import linear_sum_assignment
                actual = {"numpy": numpy.__version__, "scipy": scipy.__version__}
                if actual != entry["dependencies"]:
                    raise RuntimeError(f"Dependency snapshot differs: {actual}")
                if not callable(linear_sum_assignment):
                    raise TypeError("SciPy assignment function is not callable")
            builtins.__import__ = optional_import
            action = run(observation, configuration or {})
        finally:
            builtins.__import__ = previous_import
        first = False
        return action

    return agent


def prepare(sources: Path, pack: Path, output: Path, include_scipy: bool = False) -> dict:
    """Copy real policy + license + loader closures, then generate adapters."""
    import intake
    manifest = intake.verify(sources)
    output.mkdir(parents=True, exist_ok=False)
    shutil.copytree(sources, output / "sources")
    contract = output / "contract"
    contract.mkdir()
    for name in ("official.py", "LICENSE", "LICENSE-MIT.txt", "LICENSE-CC-BY-4.0.txt"):
        shutil.copy2(pack / name, contract / name)
    shutil.copytree(pack / "upstream", contract / "upstream")
    shutil.copy2(Path(__file__), output / "bank.py")
    dependencies = {}
    if include_scipy:
        import numpy
        import scipy
        from scipy.optimize import linear_sum_assignment
        dependencies = {"numpy": numpy.__version__, "scipy": scipy.__version__}
        if not callable(linear_sum_assignment):
            raise TypeError("SciPy assignment function is not callable")
    entries = {}
    modes = [("lonespear-v18-greedy", "lonespear-v18", "greedy"),
             ("cok-v10", "cok-v10", "not_applicable")]
    if include_scipy:
        modes.append(("lonespear-v18-scipy", "lonespear-v18", "scipy"))
    for identity, name, mode in modes:
        source = manifest["opponents"][name]
        entry = f"sources/{name}/{source['entry']}"
        entries[identity] = {"source": entry, "source_sha256": sha256(output / entry),
                             "assignment": mode, "dependencies": dependencies if mode == "scipy" else {},
                             "repository": source["repository"], "commit": source["commit"]}
        adapter = f'''"""T07 {identity}: one instance per actor/match; no source edits."""
import importlib.util as _util
from pathlib import Path as _Path
_runner = None

def agent(observation, configuration=None):
    global _runner
    if _runner is None:
        root = _Path(agent.__code__.co_filename).resolve().parent
        spec = _util.spec_from_file_location('t07_public_bank', root / 'bank.py')
        bank = _util.module_from_spec(spec)
        spec.loader.exec_module(bank)
        _runner = bank.make_agent(root, {identity!r})
    return _runner(observation, configuration or {{}})
'''
        (output / f"{identity}.py").write_text(adapter, encoding="utf-8")
    result = {"schema": "titan.public-opponent-launch.v1", "entries": entries,
              "state": "one instance per actor/match; never share across actors or games",
              "timing": "cold first call includes loader and optional dependency imports",
              "source_policy_changes": False,
              "files": {str(p.relative_to(output)): sha256(p) for p in sorted(output.rglob('*'))
                        if p.is_file() and '__pycache__' not in p.parts}}
    (output / "BANK.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--pack", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--include-scipy", action="store_true")
    args = parser.parse_args()
    print(json.dumps(prepare(args.sources, args.pack, args.output, args.include_scipy), indent=2))


if __name__ == "__main__":
    main()
