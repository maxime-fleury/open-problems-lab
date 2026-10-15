# Targets: what is actually open, and what would count as a win

Status of each target, checked against the literature. Every entry names the
artifact that would certify a win, because a problem whose solution cannot be
checked in seconds is a bad fit for this repository.

## 1. `R(5,5)` — the flagship negative result of this repo

**Status.** `43 <= R(5,5) <= 46`. The upper bound is Angeltveit & McKay (2024,
`arXiv:2409.15709`, roughly 30 CPU-years of SAT). The lower bound has stood
since Exoo (1989, *J. Graph Theory* 13, 97–98), who gave a 2-colouring of `K42`
with no monochromatic `K5`. Nothing is known about which colourings work best:
the searches are heuristic.

**Win condition.** A single colouring of `K43` with no monochromatic `K5` raises
the lower bound to 44, i.e. `R(5,5) >= 44`. The artifact is 903 bits.

**What this repo adds.** An exact delta-evaluating monochromatic-`K5` counter
(`ramsey.count_mono_k5`, cross-checked against brute force in the test suite),
a tabu baseline, a SAT encoding with four sound symmetry-breaking layers, and an
**exhaustive** sweep of the circulant family (`ramsey.circulant_search`): all
`2^21` circulant colourings of `K42` and `K43` were enumerated, and none avoids a
monochromatic `K5`. So the 1989 lower bound cannot be witnessed by a circulant
colouring, and any witness for `R(5,5) >= 44` must be non-circulant. The method is
validated against C5 and Paley(17), and against the matching negative cases
`K6` and `K18` (for `k = 3` and `k = 4`).

**The SAT route, and its measured wall.** `oplab.sat` encodes "no monochromatic
`K_k`" as 2 clauses per `k`-subset — 1 935 727 clauses over 106 108 variables for
`K42`, 2 176 434 for `K43` — and layers degree ordering, a colour-swap break and
lex-leader constraints on top, each with a soundness argument and a test that a
*satisfiable* instance stays satisfiable.  The wall is not the encoding but the
hand-off: Z3's Python API ingests clauses at roughly 4 000/s, so loading `K42`
costs about 8 minutes before any reasoning starts, and the engine then returns
`unknown`.  The deliverable is therefore the encoding plus a DIMACS export
(`oplab sat --dimacs-only`), meant for CaDiCaL/Kissat, which ingest orders of
magnitude faster.  Unsatisfiability claims carry no DRAT proof and are not
claimed as theorems.

## 2. Tammes problem on `S^2`, `N = 15..23`

**Status.** Optimal configurations are proved for `N <= 14` and `N = 24`; for
`N = 15..23` only best-known configurations exist, tabulated by N. J. A. Sloane
(*Spherical Codes*, `neilsloane.com/packings/`) and reproduced by Henry Cohn's
tables. The published values are quoted in `oplab/references.py`.

**Win condition.** Any configuration of `N` points on `S^2` whose minimal angle
strictly exceeds the tabulated value. The artifact is `2N` floats.

**What this repo adds.** A measured baseline: the same search reaches within a
few hundredths of a degree of the published records on a laptop within a minute
per size (see `RESULTS.md`), and every configuration it writes is a verified
certificate. Closing the remaining gap is a matter of compute, which is a
different thing from being stuck.

## 3. Kissing numbers in dimensions 5, 6, 7

**Status.** `40 <= tau(5) <= 44`, `72 <= tau(6) <= 77`, `126 <= tau(7) <= 134`.
The lower bounds come from the `D5`, `E6`, `E7` root systems (this repository
reconstructs all three *exactly*, in integer arithmetic, and verifies them in
CI). The only proved dimensions are 1, 2, 3, 4, 8 and 24; dimension 6's upper
bound was improved to 77 in 2024 (`arXiv:2404.18794`).

**Win condition.** An explicit configuration of `41` (resp. `73`, `127`) unit
vectors with all pairwise dot products `<= 1/2`. The artifact is `41 x 5` floats.

**What this repo adds.** Honest failed attempts with the best values found
(`max_dot` around `0.52 / 0.54 / 0.57` in 60 seconds on 16 cores), which is the
right baseline to beat: the gap is real but small in dimension 5.

## 4. Chromatic number of the plane

**Status.** `5 <= chi <= 7`. The Moser spindle (7 vertices, this repo builds it
from analytic coordinates and verifies it is 4-chromatic and 4-critical) gives
the 4 lower bound; the smallest known 5-chromatic unit-distance graph has 509
vertices (Jaan Parts). **No 6-chromatic unit-distance graph is known.**

**Win condition.** A unit-distance graph requiring 6 colours, or a 6-colouring
of the plane. A finite witness is a finite list of points plus its edge set.

**What this repo adds.** An exact chromatic-number solver (branch and bound with
DSATUR ordering, validated against a backtracking reference in the test suite),
verification that a claimed edge set is *exactly* the unit-distance pairs, and a
random-growth search whose honest ceiling is 4 — the smallest known 5-chromatic
graph is 509 vertices, so this harness cannot reach 5 by construction. Scaling
this target means implementing the Exoo/Parts style de Grey graph families.

## 4b. `R(k,k)` for small `k`: the validation ladder

The same engines are run on cases whose answers are known, which is how the
machinery is kept honest:

| instance | truth | how it is known |
|---|---|---|
| `K5`, `k=3` | satisfiable | brute force (12 clean colourings) |
| `K6`, `k=3` | unsatisfiable | brute force, and `R(3,3) = 6` |
| `K17`, `k=4` | satisfiable | `R(4,4) = 18` |
| `K18`, `k=4` | unsatisfiable | `R(4,4) = 18` (proved 1955/1995) |

Every layer of symmetry breaking is re-checked against the two satisfiable rows
(a bad layer would return `unsat`: the test suite fails, CI fails).

## 5. Deliberately out of scope

* **Erdős problems** (~630 open). The bottleneck is verification of long Lean
  proofs, not search, so a certificate format based on 903 bits and 240 points
  does not help. The right harness is an LLM + Lean loop, which is a different
  repository.
* **Navier–Stokes, turbulence closure, high-Tc mechanism, the quantum sign
  problem.** No finite certificate exists that a CI job could re-check in
  seconds, which is exactly the property this repository optimises for.
  `TARGETS` in `docs/targets.md` is a deliberate list of problems in the
  "one verifiable artifact" regime.
* **Hadamard order 2004.** The next missing order after 668 fell in August 2026.
  The verifier would be trivial (`H H^T = n I`, integer arithmetic), but no
  search strategy here is competitive with the published constructions; a
  certificate for a known order would add nothing.

## Reference values used by the code

All in `src/oplab/references.py`, each with its source URL:

| quantity | values | source |
|---|---|---|
| kissing bounds | `d=5: 40..44`, `d=6: 72..77`, `d=7: 126..134`, `d=8: 240` exact | Cohn, *Kissing numbers*; Cohn & Li 2024 |
| Tammes `S^2`, `N=15..23` | minimal angle in degrees, 7 decimals | Sloane, *Spherical Codes* |
| `R(5,5)` | `43 <= R(5,5) <= 46` | Exoo 1989; Angeltveit & McKay 2024 |
| plane chromatic number | `5 <= chi <= 7`; smallest known 5-chromatic graph: 509 vertices | de Grey 2018; Parts |
