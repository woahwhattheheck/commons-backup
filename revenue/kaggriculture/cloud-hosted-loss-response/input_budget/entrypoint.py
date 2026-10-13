# SPDX-License-Identifier: Apache-2.0
"""Raw Kaggle file bootstrap; the tested candidate remains a normal module."""
from pathlib import Path
import sys

def _directory():
    return Path(_directory.__code__.co_filename).resolve().parent

sys.path.insert(0, str(_directory()))
from candidate import agent as _candidate

def agent(observation, configuration=None):
    return _candidate(observation, configuration)
