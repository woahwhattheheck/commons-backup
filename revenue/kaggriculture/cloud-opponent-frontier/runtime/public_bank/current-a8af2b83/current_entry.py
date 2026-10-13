"""Lazy official file-loader binding of the unchanged, digest-pinned current release."""
_CALL = None

def agent(observation, configuration=None):
    global _CALL
    if _CALL is None:
        import importlib.util
        from pathlib import Path
        import sys
        root = Path(__file__).resolve().parent.parent
        path = root / 'prior/bank/contract/official.py'
        spec = importlib.util.spec_from_file_location('orbit_current_official', path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        _CALL = module.make_agent(root/'release/a8af2b83/main.py')
    return _CALL(observation, configuration or {})
