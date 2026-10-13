"""LARK dairy continuation ablation, Apache-2.0; Arlene v14 is the backbone.
One edit: retain the coherent main schedule instead of selecting milk-glut exit.
All other branch decisions, unit tapes, market guards and persistent state are inherited.
"""
_DAIRY_PARENT = agent
DECISIONS = tuple(row for row in DECISIONS if row[3] != MILK_GLUT)

def lark_dairy_continuation_entrypoint(observation):
    return _DAIRY_PARENT(observation)
