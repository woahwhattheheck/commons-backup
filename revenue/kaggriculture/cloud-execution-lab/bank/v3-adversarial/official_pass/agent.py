"""Apache-2.0 official kaggriculture pass_agent. Path wrapper only; strategy unchanged.
Source: Kaggle/kaggle-environments commit 28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c
"""
import sys
from pathlib import Path
_ENG = Path("/tmp/v25/engine")
if str(_ENG) not in sys.path:
    sys.path.insert(0, str(_ENG))
import kaggriculture as _eng  # noqa: E402

def agent(obs, config=None):
    return _eng.pass_agent(obs)
