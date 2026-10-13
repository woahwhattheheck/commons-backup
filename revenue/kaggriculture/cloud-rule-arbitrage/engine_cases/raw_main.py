# SPDX-License-Identifier: Apache-2.0
"""Official file-loader entrypoint delegating to the unchanged measured policy."""
_FUNCTION = None


def agent(observation, configuration=None):
    global _FUNCTION
    if _FUNCTION is None:
        import importlib.util
        from pathlib import Path
        config = configuration or {}
        raw_path = globals().get('__file__') or config.get('__raw_path__')
        if not raw_path:
            raise RuntimeError('File loader must supply __file__ or __raw_path__')
        directory = Path(raw_path).resolve().parent
        policy = directory / 't11_policy.py'
        if not policy.is_file():
            policy = directory / 'main.py'
        spec = importlib.util.spec_from_file_location('t11_measured_policy', policy)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _FUNCTION = module.agent
    return _FUNCTION(observation, configuration)
