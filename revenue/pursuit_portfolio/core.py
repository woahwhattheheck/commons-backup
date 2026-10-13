"""Public pursuit-portfolio API.

The v1 implementation lived here.  v2 moved the authority-bound engine and
its descriptor-custody publication logic into ``core_v2`` so old vulnerable
code cannot remain callable through the public module.
"""
from .core_v2 import *  # noqa: F401,F403
