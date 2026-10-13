"""LARK deferred milk continuation, Apache-2.0, appended to Arlene v14.

One policy edit: reconsider the inherited milk-glut continuation at its first
actual route divergence, using that turn's observation. The original threshold,
route tapes, feasibility guards, sale logic and persistent Agent are unchanged.
"""
_DEFERRED_PARENT = agent
_DEFERRED_ROUTES = routes()
_DEFERRED_MAIN = _DEFERRED_ROUTES[MAIN]
_DEFERRED_GLUT = _DEFERRED_ROUTES[MILK_GLUT]
_DEFERRED_STEP = next(i for i, (a, b) in enumerate(zip(_DEFERRED_MAIN, _DEFERRED_GLUT)) if a != b)
assert _DEFERRED_STEP == 577, 'Pinned Arlene v14 route prefix changed'
DECISIONS = tuple((_DEFERRED_STEP, feature, threshold, target) if target == MILK_GLUT
                  else (step, feature, threshold, target)
                  for step, feature, threshold, target in DECISIONS)


def lark_deferred_milk_entrypoint(observation):
    return _DEFERRED_PARENT(observation)
