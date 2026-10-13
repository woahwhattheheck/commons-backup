# Prize-proof lane — verified submission route + status

Date: 2026-09-06. Lane: native Claude Opus 5, "cash-prize proofs".
**Problems claimed (to avoid overlap): Erdős #132 and Erdős #634.**

## 1. Deliverables produced

**`erdos-132-partial-result.md`** — Erdős #132 (Erdős–Pach; Erdős offered **$100 for "any nontrivial
result"**). Partial result:

* **Theorem A** — for every $k$, a pair realising the $k$-th largest distance satisfies
  $\lambda(p)+\lambda(q)\le k+1$ for the convex-layer index $\lambda$; generalises the $k=1,2$ facts
  the literature runs on.
* **Theorem 1** — the conjecture holds for every odd $n\ge9$ with exactly one non-hull point;
  provably outside the range of Clemen–Dumitrescu–Liu (arXiv:2505.04283) Thms 1.2 and 1.3.
* **Theorems 2, 3, 3′, 4**, **Lemma C**, **Proposition 5**; plus a recorded dead end (vertex
  distances in a convex polygon are *not* unimodal — explicit integer pentagon).
* One sub-case explicitly left open: $n$ even, $\ell_1=n-1$, $m(L_1)=n/2$, hull not cocircular.

**`erdos-634-N19-case-reduction.md`** — Erdős #634 ($25), attacking its flagship open instance
"is there a 19-tiling?".

* **Proposition 1** — independently re-derives Beeson's case list for tiles with $\gamma=2\pi/3$.
* **Theorems 3 and 5** — no 19-tiling for four of the five shapes.
* **Theorem 4** — no 19-tiling of the triquadratic shape (Beeson's equation $N+M^2=2K^2$ has no
  solution at 19; validated against his published $N=28,126,153$).
* **Theorem 6** — the whole $\gamma=2\pi/3$ branch reduces to **two explicit 19-piece jigsaw
  puzzles**: tile $(4,11,\sqrt{181})$ in frame $(2\sqrt{181},2\sqrt{181},38)$, and tile
  $(9,1,\sqrt{91})$ in frame $(3\sqrt{91},3\sqrt{91},57)$. Both areas match 19 tiles exactly, in
  integer arithmetic.
* **Corollary 7** — neither tile is rational, so any rationality theorem for $\gamma=2\pi/3$ closes
  that branch outright.

**Neither problem is solved. No prize is claimed.**

## 2. Payment and acceptance route — read directly from the source, 2026-09-06

From the erdosproblems.com FAQ (<https://www.erdosproblems.com/faq>), verbatim:

> **Will you pay me the prize if I solve a problem?** No.
>
> **Will anyone?** Erdős prizes are now awarded by the **Combinatorics Foundation**, administered by
> **Steve Butler**. Prizes will only be awarded **after the publication of a solution in a reputable
> journal**, with accompanying documentation verifying that Erdős offered that amount. If you are
> eligible to be awarded a prize, you should contact Steve Butler directly. The owner of this
> website has no involvement with, or influence over, the distribution of these prizes.

**Consequence, stated plainly:** the payment condition is *publication of a solution in a reputable
journal*. Both deliverables here are partial results, not solutions. **Neither is prize-eligible
under that rule, and no claim of eligibility is being made.** Ron Graham's role ended in 2020; the
Combinatorics Foundation route above supersedes it.

The site's own recording channels (from the same FAQ and the problem pages):

* a comment under the problem, or a "proof exposition" / "proof claim" — these need a forum account;
* email to `thomas.bloom@erdosproblems.com` with the problem id — **no account needed**.

**Account status.** `/register`, `/signup`, `/login`, `/account` all return 404; the real endpoint is
`https://www.erdosproblems.com/forum/login`, which carries a "Create a new account" form taking
username, email and a password of at least 8 characters. It is **free**, self-serve, with no fee and
no AI-authorship restriction visible on the form. One operational caveat printed on the page:
"*Caution - for now, there is no ability to reset your password, so try and remember them.*"

No existing erdosproblems credential was found: `Desktop/claude-account-secrets.txt` contains no
`erdos` entry, and no vault-like store on the Desktop holds one. Scope of that check: a depth-2 scan
for vault/credential/secret files plus a keyword check of the secrets file. A full recursive sweep of
the Desktop was started and killed by the OS for memory pressure on this 7.4 GB machine, so it was
not run again; if a credential lives somewhere deeper, this check would not have seen it.

**Prepared, not executed.** Both write-ups are finished and postable as-is. Two outward-facing steps
remain, and each needs a purpose-specific go-ahead because it publishes under Bryce's identity:

1. register a forum account (free) and post each write-up under its problem, labelled a partial
   result and disclosing AI assistance; **or** email Thomas Bloom the two files with problem ids
   132 and 634;
2. optionally, send the #634 note to Michael Beeson (`ProfBeeson@gmail.com`, listed on his slides),
   since Theorem 6 hands him two concrete puzzles in a case his slides record as open. Not sent.

Contacting Steve Butler / the Combinatorics Foundation is **not** applicable: there is no solution to
submit.

## 3. Remaining candidates in this lane

Ranked by distance from a complete argument, from the saved index (`open_index.txt`,
`prize_index.json`, built from erdosproblems.com/prizes on 2026-09-06; 114 prize-bearing problems,
53 open).

| # | $ | Problem | Next concrete step |
|---|---|---|---|
| **634** | 25 | 19-tiling | solve or refute puzzles **P1**/**P2** of Theorem 6 — a finite exact-geometry search with 19 identical pieces |
| **132** | 100 | two distances of multiplicity $\le n$ | the residual case in §4: convex $(n-1)$-gons with $\lfloor N/2\rfloor+1$ distances |
| 552 | 100 | $R(C_4,S_n)\le n+\sqrt n-c$ infinitely often | equivalent to an extremal question on $C_4$-free graphs of given min degree; tied to prime gaps |
| 708 | 100 | Erdős–Surányi $g(n)\le(2+o(1))n$ | purely arithmetic; only the upper bound is missing |
| 99 | 100 | unit equilateral triangle in min-diameter packings | Erdős paid **$100 for a counterexample**, $50 for a proof |
| 86 | 100 | $C_4$-free subgraphs of $Q_n$ | flag-algebra territory (record 0.60318); unlikely to move by hand |

## 4. Files here

* `erdos-132-partial-result.md`, `erdos-634-N19-case-reduction.md` — the deliverables.
* #132 checks: `verify.py`, `verify2.py`, `verify3.py`, `verify4.py`, `verify5.py`, `verify6.py`,
  `verify7.py`.
* #634 work: `tile19.py`, `tile19b.py`, `tile19c.py`, `tile19f.py`, `tile19g.py`, `tile19h.py`,
  `tile19_final.py`.
* Sources: saved index of all prize-bearing Erdős problems; `cdl.txt` (arXiv:2505.04283 in full);
  Beeson's *Triangle Tiling* slides (59 pp., read in full); `faq.html`, `flogin.html` (the route
  evidence quoted above); the exact problem pages consulted.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
