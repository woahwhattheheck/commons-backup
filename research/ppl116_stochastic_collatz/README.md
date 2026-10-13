# Stopped stochastic Collatz absorption

Exact rational first-hit/first-exit probabilities and expected stopped times for a finite odd domain under independent fair choices of odd(3n−1) and odd(3n+1).

| File | Contents |
| --- | --- |
| [finite_absorption.cjs](finite_absorption.cjs) | Bounded constructor and saved query API |
| [FINITE_ABSORPTION_API.md](FINITE_ABSORPTION_API.md) | Source conventions, finite proof, equations, API and complete scope |
| [odd139_absorption.json](odd139_absorption.json) | Full graph/SCC/path/matrix/solution record and all 12 reader outputs |

The one actual domain contains the **70 odd states 1 through 139**. It has 140 signed coin transitions, 32 strongly connected components and no closed class except 1. Its 23 distinct first-exit destinations are retained individually. A terminal event is reachable within four moves from every state, giving a conditional stopping probability of at least 1/16 in each four-move block.

The exact probability of hitting 1 before exit from start 27 is **243731074/280829761**. Its remaining mass **37098687/280829761** exits the domain. Expected stopped time is **2225556383/280829761** moves. All 70 solution rows and 1725 exact zero equation residuals are retained.

Exit is not failure in the original infinite process: an exited path may later return and hit 1. The saved probabilities therefore give qualified eventual-hit lower/upper enclosures and allow explicitly supplied boundary values. Expected stopped time is not the unknown time to actual absorption after leaving the domain.

The [primary Althöfer page](https://althofer.de/collatz-prizes.html), updated September 21, 2026, supplies the fair independent-sign model and conjecture. The API does not settle that conjecture, transfer a result from the separate mixed/game variants, or contact the sponsor. Standard finite absorbing-chain equations retain Grinstead–Snell attribution in the guide.

The source was frozen at `4661428b7c467422f6c1fe7e5bc73e0fb69ae485`. Complete source and constructor/reader packets were banked in Git before prose. The fresh saved reader performs structural checks and new mixture/boundary arithmetic, with zero transition/SCC reconstruction, elimination or residual replay. Its loader does not independently authenticate the saved mathematical results.

Only scalar 70 is reused from released #31507; no earlier word, NFA or deterministic Althöfer computation was repeated. Other input/error branches were source-inspected only. This is a bounded exact computational capability, with no asymptotic, novelty or prize claim.
