# SPDX-License-Identifier: Apache-2.0
"""Official file-loader entrypoint; imports and first setup are timed."""
from pathlib import Path
import sys

_AGENT = None


def agent(observation, configuration=None):
    global _AGENT
    if _AGENT is None or int(observation.get('step',0)) == 0:
        sys.path.insert(0,str(Path(__file__).resolve().parent))
        # Explicit module name prevents reuse of the adjacent v2 runtime.
        import importlib.util
        path=Path(__file__).resolve().parent/'runtime.py'
        spec=importlib.util.spec_from_file_location('adaptive_runtime',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        _AGENT=module.Agent('adaptive')
    return _AGENT.act(observation, configuration)
