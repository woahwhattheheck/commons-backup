# PPL121: saved word-pair NFA catalogue

This finite consumer compares the inherited DFA minimum 4 for 0^212 1^2 versus 0^2 1^212 with a new complete three-state NFA catalogue. It finds 25,294 labelled epsilon-free initial-zero forward separators across 7,810 transition tables. Full two-state relation identities and a three-state witness establish NFA minimum 3 for this pair, hence the finite ratio 4/3 under the inherited DFA convention.

Read [NFA_PAIR212_API.md](NFA_PAIR212_API.md) for the exact model, matrix argument, epsilon/initial-set boundary, saved-data assembly, and conditional count/rank/select/trace API. The first reader retained 127 responses, 45 matching inverses, three exact traces, and 23 caches. Source/input and every expensive stage were natively checkpointed before the next stage.

This consumes saved #31368 and #31503 results without replaying their calculations. It is not a worst-case bound, priority claim, sponsor submission or current prize resolution.
