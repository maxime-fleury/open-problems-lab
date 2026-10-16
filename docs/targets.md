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
magnitude faster.  Unsatisfiability claims from *this* engine carry no DRAT proof
and are not claimed as theorems — the multicolour circulant rows, which do carry
them, are a different encoding and a different module (`oplab.drat`, §4c).

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

## 4c. The multicolour frontier: the softest part of the Ramsey table

**Status.** One forbidden clique size per colour, arbitrary `k`. The published
lower bounds and their ages:

| number | bounds | lower-bound witness | age |
|---|---|---|---|
| `R(3,3,3,3)` | `51 .. 62` | `K50` | Chung, 1973 |
| `R(3,3,5)` | `45 .. 57` | `K44` | Kreher, Li & Radziszowski, 1988 |
| `R(3,4,4)` | `55 .. 77` | `K54` | Kreher, Li & Radziszowski, 1988 |
| `R(3,3,3,4)` | `97 .. 149` | `K96` | Exoo, c. 2005 |
| `R(4,4,4)` | `128 .. 229` | `K127` | Hill & Irving, 1982 |
| `R(3,3,3,3,3)` | `162 .. 307` | `K161` | Exoo, 1994 |
| `R(4,6)` | `36 .. 40` | `K35` | Exoo, 2012 |
| `R(3,3,3,3,3,3)` | `538 .. 1838` | `K537` | Fredricksen & Sweet, 2000 |

**Win condition.** One colouring of `K_{n+1}` with no monochromatic forbidden
clique, i.e. `C(n+1, 2)` digits — for example a clean 4-colouring of `K51` would
raise `R(3,3,3,3) >= 51` to `>= 52`, a bound that has not moved in 53 years.

**What this repo adds, and what it measured.**  Two things, neither of which is
a record:

* `multicolour.tabu_search` attacks the frontier directly and *fails*, including
  on the two instances whose witnesses are published (`K50`, `K29`): 300 s per
  target, 140–17 560 monochromatic cliques left, in `RESULTS.md` §8.  The engines
  are published as the honest baselines they are.
* `scripts/orbit_probe.py` decides **restricted** colourings with two independent
  symmetry breaks, and measures where each one stops helping.  Neither break decides
  `K96`, `K97`, `K128` or `K538`, and no published bound moved.
  * *multiplicative*: colourings constant on the orbits of a subgroup of the unit
    group of `Z_n`.  The whole unit group is 21 variables for `K128` and 15 for
    `K161` against the 192 and 400 of the full circulant encoding, decided in
    milliseconds — and `K8` with sizes `(3,3,3)` is SAT there with a witness the
    ordinary verifier re-counts, so it is neither vacuous nor broken.  `--by-subgroup`
    sweeps *every* distinct subgroup (6–16 of them), most restricted first, and the
    full unit group is strictly too strong: at `K127` `(4,4,4)` the order-42 subgroup
    is SAT in 2 s with a clean witness (`R(4,4,4) > 127`, which is the published
    witness size, not a record), while at `K96` 14 of the 16 subgroups (56–144
    variables), at `K97` 10 of the 12 (4–96), at `K128` 10 of the 12 (21–144) and at
    `K161` 12 of the 16 (15–170) are UNSAT, and `K537` is UNSAT in all eight of its
    subgroups — the full 1608-variable instance included, by the arithmetic
    obstruction.  The residual families are the
    full 192- and 400-variable instances again: for odd `n` the difference classes
    are already quotiented by ±1, so the order-2 subgroup *is* the whole circulant
    family.  Where a residual family is still genuine it is handed a 3-hour budget,
    and one has fallen: `K161` at order 2 (47 orbits, 235 variables) is **UNSAT after
    3774 s**, so at `K161` only the full 400-variable instance is still open.  That is
    a statement about those sub-families only.
  * *colour-naming*: colours with the same forbidden clique size are
    interchangeable, so requiring equal-size colours to *first appear* in increasing
    order costs no colouring — a factor `3!`, `5!`, `6!` off the search space of
    `(3,3,3,4)`, five 3s and six 3s.  It is validated rather than asserted:
    `--compare` runs the plain and the broken encoding on every subgroup of a case
    and demands the same verdict, and the broken one may only ever report a witness
    the ordinary verifier re-counts.  `K29` and `K44` stay SAT with clean witnesses
    (`R(3,3,4) > 29`, `R(3,3,5) > 44` — reached through *smaller* subgroups than the
    unit group, which is UNSAT there), and `K18`, `K30`, `K51` stay UNSAT in every
    family, so the break never manufactures a verdict.
* `oplab.cayley` attacks the **construction space** instead of the colouring space,
  which is the "next step" the note above asked for: a Cayley colouring assigns a
  colour per *inversion class* of a group of order `n`, so the colouring is
  translation invariant and one variable per (class, colour) decides the family — the
  circulant encoding is the special case where the group is cyclic, and the published
  witnesses could plausibly live in one of the other groups.  Measured, not hoped for:
  * the portfolio is complete for the **abelian** groups (7 for `n = 96`, 15 for
    `128`), plus one entry per dihedral, dicyclic and semidihedral family and per
    direct product of those with a small cyclic factor: 22 groups at `K96`, 26 at
    `K128`, and 2 at `K538` (`Z269 x Z2` and `D269`, since `538 = 2 * 269`).  It is not
    every group of order `n` — `cayley.groups_of_order` lists exactly what is in it.
  * every table is checked against the group axioms before it is searched
    (`cayley.verify_group`: identity, inverses, associativity over every triple), which
    is what makes the hand-derived dihedral, dicyclic and semidihedral rules safe to
    use instead of plausible-looking.
  * **`K128` `(4,4,4)`: 24 of the 26 groups are UNSAT** — 5 of them in seconds (2.3 s
    to 6.2 s), 18 inside the 5-minute budget, and `Z2 x D32` only when the budget went
    to an hour — so the two still open are the *cyclic* group and `D64`.  No
    translation-invariant witness exists at the record size, so `R(4,4,4) >= 128`
    stays where it is.
  * **`K96` `(3,3,3,4)`: 9 of the 22 groups UNSAT, 13 unknown, no witness.**  Four
    fell in the 5-minute round and five more — `Z3xDic8`, `Z8xD6`, `Z8xDic3`,
    `Z12xDic2`, `Z16xD3` — when the thirteen that round left open were given an hour
    each.  Those thirteen were then given an hour each of the *repair* search — the
    engine that hunts witnesses instead of refutations — and it found none either
    (`runs/cayley_long_k96_repair.json`): the published `K96`
    witness is not translation invariant over any of them, over that portfolio.
  * **A later round supersedes rows instead of editing them away.**
    `scripts/sweep_merge.py` puts the longer round in `runs/cayley_sweep.json` as the
    frontier and keeps the 300 s rows it replaced under `superseded`, so "300 s told
    nothing, 3600 s decided it" is both readable and a visible diff; `make
    cayley-long` is the command that produced it.  Those rows are still *verdicts*:
    the long round ran with no `--proof-dir` on purpose, because a trace from a
    refutation that took an hour is hundreds of megabytes — see the replay envelope
    in `RESULTS.md`.
  * **`K97`, `K161` and `K538`**: one group each in practice (the order is prime or
    `7 * 23` / `2 * 269` with no non-abelian group of that order except `D269`), and
    none of them is decided — for prime `n` there is nothing here that the circulant
    sweep did not already try, which is why the target sizes that *are* prime gain
    nothing from this layer.
  * the one thing this layer decides **without a solver** is stronger than the
    repository's old obstruction: `3 | n` kills translation-invariant colourings of
    **every** group of order `n`, not just the cyclic one.  Cauchy's theorem gives an
    element `g` of order 3, so `{e, g, g²}` has all three of its differences in the
    single class `{g, g⁻¹}`, and its `n/3` translates are monochromatic in whatever
    colour that class carries.  `K162`, `K537` and every all-triangle instance
    divisible by 3 are therefore unreachable from *any* group.
  * the `unsat` rows now have the same standing as the circulant ones: the encoding
    takes a proof path, `cayley.replay_proof` re-checks the emitted trace against that
    group's own CNF before anything is stored (no solver in the loop), and
    `cayley_multicolour` accepts an `unsat` row **only** with a trace it can replay —
    a bare verdict is refused rather than stored, because the clauses depend on the
    group description and a trace from another family has neither the right variables
    nor the right clauses.  The three rows in `certs/cayley/` (`D9` and `Z3xD3` at
    `K18`, `D15` at `K30`) are that path, exercised; `K6` over `D3` is stored as
    `obstructed` instead, because the arithmetic decides it and a solver run would say
    less.  `sat` (a witness the ordinary verifier re-counts) is unchanged, and every
    row is only written after `verify_certificate` has accepted it.
  * `oplab cayley --n N --sizes … --group NAME` is the one-group-at-a-time interface
    (`--list` prints the portfolio), `scripts/cayley_hunt.py --proof-dir/--cnf-dir`
    records traces for a whole sweep, and `scripts/drat_trim_check.py` rebuilds the
    CNF from the *certificate* — the circulant encoding or the group's, whichever
    family it declares — so the external checker judges the group traces too.
* `multicolour.circulant_solve` decides the *circulant* sub-family exactly: one
  variable per (difference class, colour), one clause per (colour, clique class
  set), a few hundred variables, seconds of CaDiCaL.  **18 of the 24 instances
  run are decided** — 5 `sat`, 9 `unsat`, 4 obstructed by arithmetic — and not
  one of them moves a bound: every `sat` row is a witness at a published
  *witness* size (`K5`, `K17`, `K29`, `K44`, `K54`), and every `unsat` row says
  the circulant family has nothing at that size, which at the published witness
  sizes `K35` (`R(4,6) >= 36`), `K42` (`R(5,5) >= 43`) and `K50`
  (`R(3,3,3,3) >= 51`) means those published witnesses are not circulant.  The
  six instances the budget did not settle (`K96`, `K97`, `K127`, `K128`, `K161`,
  `K538`) are stored as `unknown` with no claim at all, and their rows now record
  that the solver's budget expired rather than leaving it to be assumed.  A
  **30-minute round** on 12 cores went further: CaDiCaL and Glucose4 were given
  each of the six, and MapleChrono the three cheapest, 1800 s per run — 15 runs,
  15 `unknown`, so these six are open rather than merely under-budgeted.
* The `unsat` rows are *proof-carrying*, which is what makes them theorems rather
  than verdicts: all nine store the solver's DRAT trace next to the certificate,
  and `oplab.drat` (400 lines, RUP/RAT/deletions, no solver, two watched literals
  per clause) replays it against the encoding rebuilt from `(n, sizes)`.  Every
  stored trace is then checked again by the external `drat-trim`
  (`scripts/drat_trim_check.py`, CI job `drat-trim`, at the commit and source hash
  pinned in `scripts/drat-trim.pin`) — all nine in about nine seconds — so the two
  heaviest (`K50`: 642 728 steps, 694 s in Python and 6.4 s in C; `K55`: 173 165
  steps) are cross-checked on every CI run even though a plain `verify` only
  digests them.  The traces are stored as binary DRAT under xz (6.27 MB for the
  nine) and pinned a second time, as *files*, by
  `certs/circulant_multicolour/MANIFEST.txt`: a trace that is edited, dropped or
  regenerated with a matching certificate fails `make proof-store` until the
  manifest is deliberately rewritten.  The method agrees with
  the exhaustive `2^21` sweep of §1 on `K42`/`K43`, in 0.6 s each instead of an
  enumeration, which is the validation of the new method.
* For `3 | n` and an all-triangle instance (`3,3`, `3,3,3,3`, `3^5`, `3^6`) there
  is a **proof**, not a verdict: the class `n/3` forces a monochromatic triangle
  in whatever colour it takes, so `K6`, `K51`, `K162` and `K537` are unreachable
  from the circulant side for any number of colours.  The obstruction is checked
  arithmetically by `oplab verify` and by `decide` in Lean.

**Next step for a real attempt** (not implemented here): the published witnesses
come from algebraic and recursive constructions; a plausible route is to search
over those constructions (product/circular lift families with a small parameter
space) rather than over colourings — `oplab.cayley` is the first layer of that, and
its `unsat` rows are already proof-carrying, so what is missing is a wider family
of constructions rather than a way to certify one.  The cheap part is also wired:
the six instances the bundled solver leaves `unknown` (`K96`, `K97`, `K127`,
`K128`, `K161`, `K538`) are exported to DIMACS by `oplab mc-circulant
--dimacs-only` and by `scripts/run_full.sh`, and `oplab cayley --dimacs-only`
does the same for any group of the order, so a real solver can be pointed at them
without touching Python.

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
* **Hadamard matrices.** Order 2004 is *not* a gap: 2003 is prime and
  `= 3 (mod 4)`, so Paley I has produced a matrix of order 2004 for a century,
  and the August 2026 result closed every order below 2000 that was still open.
  The smallest unknown order is above 2000 and no authoritative table is
  reproduced here. The verifier would be trivial (`H H^T = n I`, integer
  arithmetic), but no search strategy here is competitive with the published
  constructions; a certificate for a known order would add nothing.

## Reference values used by the code

All in `src/oplab/references.py`, each with its source URL:

| quantity | values | source |
|---|---|---|
| kissing bounds | `d=5: 40..44`, `d=6: 72..77`, `d=7: 126..134`, `d=8: 240` exact | Cohn, *Kissing numbers*; Cohn & Li 2024 |
| Tammes `S^2`, `N=15..23` | minimal angle in degrees, 7 decimals | Sloane, *Spherical Codes* |
| `R(5,5)` | `43 <= R(5,5) <= 46` | Exoo 1989; Angeltveit & McKay 2024 |
| multicolour Ramsey | `R(3,3,3,3) in 51..62`, `R(3,3,5) in 45..57`, `R(3,4,4) in 55..77`, `R(4,6) in 36..40`, `R(3,3,3,3,3) in 162..307` | Radziszowski, *Small Ramsey Numbers*, rev. 18 (2026) |
| plane chromatic number | `5 <= chi <= 7`; smallest known 5-chromatic graph: 509 vertices | de Grey 2018; Parts |
