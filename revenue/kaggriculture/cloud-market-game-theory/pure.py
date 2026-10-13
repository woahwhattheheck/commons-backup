# SPDX-License-Identifier: Apache-2.0
"""Same complete-plan family with T12's pure acceptance condition."""
_INSTANCE=None


def agent(observation,configuration=None):
    global _INSTANCE
    if _INSTANCE is None or observation.get('step')==0:
        import sys
        from pathlib import Path
        source=globals().get('__file__') or (configuration or {}).get('__raw_path__')
        sys.path.insert(0,str(Path(source).resolve().parent))
        from runtime import MarketGameTheory
        _INSTANCE=MarketGameTheory('pure')
    return _INSTANCE.act(observation,configuration)
