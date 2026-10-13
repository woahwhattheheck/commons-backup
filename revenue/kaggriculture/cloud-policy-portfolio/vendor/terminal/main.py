"""Intact Arlene plus final-day routing. Native file-agent entry point."""
import hashlib
import importlib.util
from pathlib import Path
import sys

PARENT_SHA256 = '1dc166ae2bf0c56a44fac4482f469b8812968c4cb32459cb9860f5077897a7d4'
_parent = None
_overlay = None


def agent(observation, configuration=None):
    global _parent, _overlay
    if _parent is None:
        # Kaggle executes raw Python with an empty globals dict; __file__ is not
        # supplied. Its build_agent sets this documented local-file path instead.
        raw = (configuration or {}).get('__raw_path__') or globals().get('__file__')
        if not raw:
            raise ValueError('The file-agent loader must supply __raw_path__')
        here = Path(raw).resolve().parent
        path = here / 'arlene.py'
        if not path.is_file():
            path = here.parent / 'cloud-frontier-policy/next-panel/vendor/arlene.py'
        if hashlib.sha256(path.read_bytes()).hexdigest() != PARENT_SHA256:
            raise ValueError('Arlene source does not match the reviewed pin')
        spec = importlib.util.spec_from_file_location('t05_intact_arlene', path)
        parent = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(parent)
        spec = importlib.util.spec_from_file_location('t05_terminal', here / 'terminal.py')
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        _parent, _overlay = parent, module.Planner().act
    parent_action = _parent.agent(observation)
    state = _parent._A
    step = int(observation.get('step', 0))
    final = int((configuration or {}).get('episodeSteps', 720)) - 2
    # The active route was selected by Arlene using past public observations.
    future = state.R[state.cur][step:final + 1] if state is not None else None
    return _overlay(observation, parent_action, configuration, own_future_actions=future)
