# Results

Every number below was produced by `bash scripts/run_full.sh` (16 workers,
here `WORKERS=16`) on 2026-10-15, and every certificate it wrote is re-verified
by `oplab verify`. Raw output: `runs/full_run.log` (regenerate with
`WORKERS=16 bash scripts/run_full.sh`, about 20 minutes).

The searches are seed-determined but **time-bounded**: a re-run on a different
machine reaches a slightly different local optimum, which is why the committed
certificates — not the numbers you obtain locally — are the record, and why CI
checks the certificates rather than trying to reproduce the searches.

**Summary of what is actually new here.** One exhaustive negative result
(`R(5,5) >= 43` has no circulant witness), several exact reconstructions of
classical configurations, and a set of honestly measured failures that give the
next run something to beat. No record was broken.

---

## 1. Exact classical constructions (reproducible from integer arithmetic)

| certificate | claim | value recomputed by the verifier |
|---|---|---|
| `certs/sphere/a2_kissing.json` | `tau(2) >= 6` | 6 points, `max_dot = 0.5` |
| `certs/sphere/icosahedron_kissing.json` | `tau(3) >= 12` | 12 points, `max_dot = 1/sqrt(5) = 0.4472136` |
| `certs/sphere/d4_kissing.json` | `tau(4) >= 24` | 24 points, `max_dot = 0.5` |
| `certs/sphere/d5_kissing.json` | `tau(5) >= 40` | 40 points, `max_dot = 0.5` |
| `certs/sphere/e6_kissing.json` | `tau(6) >= 72` | 72 points, `max_dot = 0.5` |
| `certs/sphere/e7_kissing.json` | `tau(7) >= 126` | 126 points, `max_dot = 0.5` |
| `certs/sphere/e8_kissing.json` | `tau(8) >= 240` | 240 points, `max_dot = 0.5` |
| `certs/unitdist/diamond.json` | plane chromatic number `>= 3` | 4 vertices, 5 edges, chromatic number 3 |
| `certs/unitdist/moser.json` | plane chromatic number `>= 4` | 7 vertices, 11 edges, chromatic number 4 (4-critical) |
| `certs/unitdist/hexagon.json` | plane chromatic number `>= 2` | 6 vertices, 6 edges, chromatic number 2 |

The root systems are generated from integer vectors (`D_d`, the 240 roots of
`E8`, and `E7`/`E6` as orthogonal complements inside it, projected onto their own
span so that they live in exactly 7 and 6 dimensions). The test suite checks the
integer certificates directly on the unscaled integer vectors — every squared
norm and every pairwise dot product is verified in exact integer arithmetic
(`test_root_systems_are_exact_integer_arithmetic`), so "all pairwise dot products
`<= 1/2`" holds with no floating-point slack at all.

`tau(8) = 240` is one of the three proved cases in this table (with 2, 3, 4); the
others are lower bounds only, and dimension 6's upper bound was improved to 77 in
2024.

## 2. The exhaustive result: no circulant witness for `R(5,5) >= 43`

`ramsey.circulant_search` enumerates **every** translation-invariant
(circulant) 2-colouring of `K_n` — `2^21` of them for `n = 42` and `n = 43` — and
tests, via translation invariance, only the cliques through vertex 0.

| sweep | family size | tested | witnesses | wall time (16 workers) |
|---|---|---|---|---|
| `K5`, `k=3` (validation) | 4 | 4 | 2 — **the 5-cycle**, `R(3,3) > 5` | < 0.1 s |
| `K6`, `k=3` (validation) | 8 | 8 | 0 | < 0.1 s |
| `K17`, `k=4` (validation) | 256 | 256 | 2 — **Paley(17)**, `R(4,4) > 17` | < 0.1 s |
| `K18`, `k=4` (validation) | 512 | 512 | 0 | < 0.1 s |
| **`K42`, `k=5`** | 2 097 152 | 2 097 152 | **0** | 8.6 s |
| **`K43`, `k=5`** | 2 097 152 | 2 097 152 | **0** | 7.9 s |

Reading:

* The two positive rows are *known* facts that the code rediscovers without being
  told about them (the 5-cycle colouring and the quadratic-residue colouring of
  `Z_17`), and the two matching negative rows `n = 6` and `n = 18` agree with
  `R(3,3) = 6` and `R(4,4) = 18`. That is the validation of the method.
* The `K42` row means: **the 1989 witness for `R(5,5) >= 43` cannot be circulant.**
  Every one of the 2 097 152 translation-invariant colourings of `K42` contains a
  monochromatic `K5`, so any construction raising the lower bound to 44 must be
  non-circulant. This is a finite, fully enumerated statement, and
  `oplab verify certs --deep` re-runs the whole sweep from scratch in CI.
* The `K43` row is a consistency check: it says the same for the target of the
  open question, which is what one expects while `R(5,5) <= 46`.

## 3. Tammes problem on `S^2`, `N = 15..23` — measured gaps

45 seconds per size, 16 independent searches per size (one process each), all 9
sizes in ~7 minutes. Reference values are Sloane's tabulated best-known minimal
angles (putatively optimal; optimality is proved only for `N <= 14` and `N = 24`).

| `N` | best found (deg) | published best known | gap |
|---|---|---|---|
| 15 | 53.5841005 | 53.6578501 | −0.07375 |
| 16 | 52.1891593 | 52.2443957 | −0.05524 |
| 17 | 51.0576594 | 51.0903285 | −0.03267 |
| 18 | 49.4918106 | 49.5566548 | −0.06484 |
| 19 | 47.6148359 | 47.6919141 | −0.07708 |
| 20 | 47.4048122 | 47.4310362 | −0.02622 |
| 21 | 45.5221516 | 45.6132231 | −0.09107 |
| 22 | 44.6753882 | 44.7401612 | −0.06477 |
| 23 | 43.5831237 | 43.7099642 | −0.12684 |

No published value was matched or beaten. The gaps (0.03°–0.13°) are the honest
starting point: the same optimiser is within a hundredth of a degree of every
record in under a minute per size, so closing the gap is a question of compute
and of a better ending routine, not of a different algorithm. Each run also
writes a verified `tammes` certificate, so any future improvement is one file
swap away.

## 4. Kissing numbers: attempts to add one point

Each attempt starts from random configurations and 16 workers × 60 s, and asks
for `N` unit vectors in `R^d` with all pairwise dot products `<= 0.5`. The
classical values are `40 / 72 / 126`; nothing here improves them.

| target | best `max_dot` found | outcome | spread over 16 workers |
|---|---|---|---|
| `d=5`, `N=41` | **0.516632968710** | no bound | 0.5166 – 0.5229 |
| `d=6`, `N=73` | 0.544016735222 | no bound | — |
| `d=7`, `N=127` | 0.571137848140 | no bound | — |

The dimension-5 case is the interesting one: two workers with different seeds
converged to the *same* value `0.516632968710`, and all 16 stayed inside
`0.5166–0.5229`. A configuration of 41 points would need `max_dot = 0.5`
exactly, i.e. about 1.9 degrees better on the closest pair than anything reached
here. The attempt is recorded as a `spherical_search` certificate whose
`establishes_bound: false` flag is itself verified, so the file cannot be
mistaken for a result.

## 5. Ramsey tabu baselines

Heuristic edge-flip tabu search, one process, 150 s per target, minimising the
exact monochromatic-`K5` count (`K42` starts at ≈1880 cliques on a random
colouring).

| target | best mono-`K5` count | flips | target value |
|---|---|---|---|
| `K42` | 100 | 30 234 | 0 (would give `R(5,5) >= 43`) |
| `K43` | 138 | 25 659 | 0 (would give `R(5,5) >= 44`) |

This is far from competitive: published constructions come from specialised
searches, and the number of known `(5,5;42)` colourings is in the hundreds after
decades of work. The value of these two certificates is that they are *measured
baselines with reproducible seeds* for a heuristic (≈250 flips/s in pure Python,
≈37 000 exact delta evaluations/s), and that the exact counter they use is
cross-checked against brute force in the test suite.

## 6. Unit-distance graph search

Random growth by unit-circle intersections, exact chromatic number computed on
every 8th surviving sample (≈8 000–12 000 exact colouring computations per run):

| seed graph | budget | vertices | samples | best exact chromatic number | recorded witness |
|---|---|---|---|---|---|
| single unit edge | 45 s | 11 | 66 629 | **3** | 11 vertices, 18 edges |
| Moser spindle | 60 s | 12 | 94 148 | **4** | 12 vertices, 18 edges |

Both numbers are exact (`unitdist.chromatic_number`, branch and bound with DSATUR
ordering, cross-checked against an independent backtracking reference on random
graphs and on every edge-deletion of the Moser spindle). The difference between
the two rows is the point: unseeded growth keeps producing 3-colourable
configurations, and only a seed that already contains the 4-chromatic spindle
carries that property forward. Four is the ceiling of anything this harness can
reach — the smallest known 5-chromatic unit-distance graph has 509 vertices — so
the honest summary is "random growth is hopeless for this target, and here is the
measurement that shows it".

## 7. Verification status

```
81/81 certificates verified   (oplab verify certs)
174/174 claims re-proved in Lean 4   (cd lean && lake build)
```

* `certs/*.json` is mirrored, claim by claim, into `lean/Oplab/Certs.lean` by
  `scripts/gen_lean_certs.py`: 174 theorems over 81 certificates, 140 of them
  kernel-checked by `decide` and 34 (the two `2^21` circulant sweeps, the two
  `K42`/`K43` tabu counts, the `3^12` lower-bound colouring search of the
  Moser drawing, the `K29`/`K44`/`K54` multicolour witness counts, the
  clique-group recomputations that are too large for the kernel, and the
  group-table checks of the four `certs/cayley` rows: that each stored table is a
  group, and that the class and clique-group counts its encoding size is computed
  from are recomputed from it) by
  `native_decide`. The Lean layer has no Mathlib and
  no floating point: coordinates from JSON become exact integers scaled by
  `10^18`, and the geometric claims become integer inequalities with an explicit
  `1e-9` rounding allowance. See [`lean/README.md`](lean/README.md) for the table
  of statements and for what it deliberately does not claim.

* Every certificate is sha256-pinned and every claim is recomputed from the
  payload; tampering is detected by the test suite
  (`tests/test_verify.py::test_tampered_payload_is_detected`).
* The contract earned its keep during development: the independent
  backtracking reference exposed an over-reporting exact-colouring solver (the
  branch-and-bound pruned at `best - 1` and reused a fresh colour without
  recording it in the neighbours' saturation sets, so it could return the greedy
  upper bound instead of the true chromatic number), and re-verifying caught a
  certificate whose recorded edge set came from a looser distance tolerance than
  the verifier's. Both are fixed, both are now covered by tests, and the
  certificates that depended on them were regenerated — which is exactly the
  workflow the repository is supposed to enforce.
* The Lean companion settles the smallest Ramsey case with no solver at all:
  `ramsey_R33_exhaustive : cleanMasks 6 3 (2^15) = []` proves `R(3,3) <= 6` by
  exhaustion over all 32768 colourings of `K6`, and the clean `K5` witnesses in
  `certs/sat/k5_k3_sym*.json` and `certs/circulant/k5_k3.json` give
  `R(3,3) > 5`; together `R(3,3) = 6`.
* CI runs the test suite on Python 3.10 and 3.13, re-verifies all certificates,
  re-runs the exhaustive circulant sweeps from scratch
  (`oplab verify certs/circulant --deep`), and builds the Lean layer after
  checking that the generated file is up to date with `certs/`.
* `runs/full_run.log` is the raw, timestamped output of the run quoted above.

## 8. Multicolour Ramsey frontier: the general engines, measured

The multicolour lower bounds are the softest part of the Ramsey table —
`R(3,3,3,3) >= 51` has stood since 1973, `R(4,4,4) >= 128` since 1982 — so this
is where a record would be cheapest. `scripts/hunt_records.py` runs the engines
of `multicolour.py` against that frontier: **300 s per job, 16 jobs on 12 cores
(2026-10-15)**, every count re-derived exactly by the verifier, raw log in
`runs/hunt_driver.log`, machine-readable rows in `runs/hunt_2026-10-15.jsonl`.

| target | engine | seeds | best mono-clique count | steps per run | witness? |
|---|---|---|---|---|---|
| `K50`, `(3,3,3,3)` — **validation**: the published 1973 witness exists | matrix | 4 | 147 (147, 151, 156, 158) | ≈1.4 M | **no** |
| `K51`, `(3,3,3,3)` — the record attempt (`R(3,3,3,3) >= 52`) | matrix | 8 | 140 | ≈1.36 M | no |
| `K162`, `(3,3,3,3,3)` — the record attempt (`R(3,3,3,3,3) >= 163`) | bits | 3 | 17 303 | ≈2.0 M | no |
| `K29`, `(3,3,4)` — **validation**: `R(3,3,4) = 30` is a theorem | general | 1 | 130 | 252 053 | **no** |

Reading:

* The two validation rows are the point of the table. `K50` *has* a clean
  4-colouring (Chung 1973) and `K29` *has* a clean `(3,3,4)`-colouring
  (Kreher–Li–Radziszowski 1988), yet 300 s of tabu search lands 130–158
  monochromatic cliques away from a witness. A search that cannot find known
  solutions cannot be trusted to report a negative, which is why nothing in this
  section is a bound.
* The engines are fast in the only sense that is measurable here — 1.4 M exact
  neighbourhood evaluations in 300 s (matrix) and 2.0 M moves in 300 s
  (bit-parallel) — and still nowhere near the published constructions, which come
  from algebraic and recursive methods rather than local search.
* Two bugs were fixed before these numbers were produced, both found by the tests
  rather than by the results: a perturbation that could write a colour index out
  of range (it crashed most jobs), and a reporting mix-up between the current and
  the incumbent objective. Re-running after the fix changed nothing qualitative,
  which is the honest outcome for a heuristic that is simply the wrong tool.

## 9. The circulant sub-family, decided

A *circulant* colouring of `K_n` assigns one colour to each difference class of
`Z_n`, so it is described by `n/2` choices instead of `C(n,2)`. Inside that
sub-family the question "is there a witness?" is an exact CNF — one variable per
(class, colour), one clause per (colour, clique class set) — with a few hundred
variables and a few thousand clauses, so CaDiCaL or Kissat answers it in
seconds (`oplab mc-circulant`). The encoding is not assumed to be right: the test
suite enumerates **every** class assignment on five small instances and checks
that the clause set is satisfiable exactly when the expansion is clean.

| instance | status | witness | encoding | time | stored DRAT trace |
|---|---|---|---|---|---|
| `K5`, `(3,3)` | `sat` | yes — the 5-cycle | 2 classes, 6 clauses | < 0.1 s | — |
| `K6`, `(3,3)` | **obstructed** | none possible: `3 ∣ 6` | 3 classes, 12 clauses | arithmetic | — |
| `K17`, `(4,4)` | `sat` | yes — Paley(17) | 8 classes, 152 clauses | < 0.1 s | — |
| `K18`, `(4,4)` | `unsat` | — agrees with `R(4,4) = 18` | 9 classes, 186 clauses | < 0.1 s | **26 steps**, replay < 0.1 s |
| `K29`, `(3,3,4)` | `sat` | yes — a verified witness | 14 classes, 623 clauses | < 0.1 s | — |
| `K30`, `(3,3,4)` | `unsat` | — agrees with `R(3,3,4) = 30` | 15 classes, 680 clauses | < 0.1 s | **1 179 steps**, replay 0.04 s |
| `K35`, `(4,6)` | `unsat` | — | 17 classes, 12 908 clauses | 0.05 s | **505 steps**, replay 0.8 s |
| `K36`, `(4,6)` | `unsat` | — no circulant witness for `R(4,6) >= 37` | 18 classes, 16 830 clauses | 0.06 s | **260 steps**, replay 0.6 s |
| `K42`, `(5,5)` | `unsat` | — agrees with the exhaustive `2^21` sweep of §2 | 21 classes, 18 164 clauses | 0.64 s | **8 288 steps**, replay 4.1 s |
| `K43`, `(5,5)` | `unsat` | — agrees with the exhaustive `2^21` sweep of §2 | 21 classes, 20 916 clauses | 0.66 s | **24 749 steps**, replay 8.0 s |
| `K44`, `(3,3,5)` | `sat` | yes — a verified witness | 22 classes, 11 641 clauses | 0.04 s | — |
| `K45`, `(3,3,5)` | `unsat` | — no circulant witness for `R(3,3,5) >= 46` | 22 classes, 13 173 clauses | 0.20 s | **36 496 steps**, replay 13.0 s |
| `K50`, `(3,3,3,3)` | `unsat` | — no circulant witness at the published size | 25 classes, 1 003 clauses | 6.7 s | **642 728 steps**, replay 694 s (`drat-trim`: 6.4 s) |
| `K51`, `(3,3,3,3)` | **obstructed** | none possible: `3 ∣ 51`, class 17 | 25 classes, 1 043 clauses | arithmetic | — |
| `K54`, `(3,4,4)` | `sat` | yes — a verified witness | 27 classes, 6 399 clauses | 0.37 s | — |
| `K55`, `(3,4,4)` | `unsat` | — no circulant witness for `R(3,4,4) >= 56` | 27 classes, 6 813 clauses | 1.3 s | **173 165 steps**, replay 80 s (`drat-trim`: 0.9 s) |
| `K96`, `(3,3,3,4)` | `unknown` | — none claimed: budget spent | 48 classes, 20 345 clauses | 120 s | — |
| `K97`, `(3,3,3,4)` | `unknown` — **refuted by cube-and-conquer (§9b)**, which is a run artifact and not a stored row | — none claimed: budget spent | 48 classes, 21 016 clauses | 120 s | — |
| `K127`, `(4,4,4)` | `unknown` | — none claimed: budget spent | 63 classes, 124 866 clauses | 120 s | — |
| `K128`, `(4,4,4)` | `unknown` | — none claimed: budget spent | 64 classes, 127 813 clauses | 300 s | — |
| `K161`, `(3,3,3,3,3)` | `unknown` | — none claimed: budget spent | 80 classes, 11 680 clauses | 300 s | — |
| `K162`, `(3,3,3,3,3)` | **obstructed** | none possible: `3 ∣ 162`, class 54 | 81 classes, 11 826 clauses | arithmetic | — |
| `K537`, `(3,3,3,3,3,3)` | **obstructed** | none possible: `3 ∣ 537`, class 179 | 268 classes, 148 474 clauses | arithmetic | — |
| `K538`, `(3,3,3,3,3,3)` | `unknown` | — none claimed: budget spent | 269 classes, 149 024 clauses | 300 s | — |

**All nine `unsat` rows are proof-carrying, and every trace is checked twice.**
The traces are stored in `certs/circulant_multicolour/proofs/` as **binary DRAT
under xz** (`name.bdrat.xz`: drat-trim's `-i` encoding, the same proof as the ASCII
text at about an eighth of the bytes — 132 B to 4.98 MB, 6.27 MB for the nine,
against 8.0 MB as gzipped text) and the certificate records the path, the sha256 of
the canonical text, the sha256 of the stored bytes, the container, the step counts,
the sizes and the replay cost.  [`oplab/drat.py`](../src/oplab/drat.py)
checks a trace against the encoding it rebuilds from `(n, sizes)`: RUP for every
addition, RAT when RUP fails, deletions honoured, accepted when the empty clause
is derived — no solver in the loop, and every addition RUP-checked against
**two watched literals per clause** rather than the whole formula.  A trace is
only stored after that replay has accepted it.  On this machine the nine replays
cost 0.0 s to 694 s: seven are cheap enough (under 14 s) that a plain
`oplab verify` re-runs them every time, and the two heaviest (`K50`: 694 s for
642 728 steps; `K55`: 80 s for 173 165) are re-checked by digest on every run and
replayed in full by `--deep` and by the `proofs` CI job.

Those two rows are stored at all because the Python replay stopped being the only
way to check them: `scripts/drat_trim_check.py` rebuilds each CNF from its
certificate and hands the pair to **`drat-trim`**, Marijn Heule's checker, which
verifies all nine traces in about 9 seconds — `K50` in 6.4 s, `K55` in 0.9 s —
and shares no code with `oplab.drat`, reading the stored binary container directly.
`make replay-bench` (`scripts/replay_bench.py`) is what times the two of them on the same
traces, which is how the envelope quoted with the long round below is a measurement rather
than an assumption.
That cross-check runs in CI (the `drat-trim` job, which builds the commit
`scripts/drat-trim.pin` names and hashes the source it compiled against the same
pin) and on demand, so an accepted trace has to convince two unrelated
implementations, and a bug in one of them cannot keep a bad proof looking good in
every later run — nor can a checker that quietly changed, because the script
refuses a verdict from any `drat-trim.c` but the pinned one.

**The store itself is pinned, not only each trace.**  Every check above is
internal: the certificate's digest matches its trace, today and tomorrow.  A
*consistent* replacement — re-solve, store a different trace, write a fresh
certificate with fresh digests — would pass them all while the artifact under
review was gone.  `certs/circulant_multicolour/MANIFEST.txt` is therefore checked
in (both digests, steps, container and size for each of the nine), and
`scripts/proof_manifest.py --check` compares manifest, certificates and the bytes
on disk three ways, failing by name on any drift; `--write` rewrites it, so
regenerating the store is a visible diff rather than a silent one.  Two
regenerations of all nine traces produced byte-identical files, so the manifest
survived both unchanged, which is the property the check is for.

**Six rows were still `unknown`, and three refinements of them were tried.**
The first two, below, decide none of them.  The third one — cutting the instance
into a decision tree instead of handing one engine a longer budget — is §9b, and it
decides `K97`.  The stored
budgets (120 s and 300 s of CaDiCaL) expired — and now say so: those six rows
record `budget_expired`, which is what distinguishes an exhausted budget from a
solver that died, a distinction the verifier enforces (the bundled Kissat wheel
dies with an access violation on this platform, and such a row is refused instead
of being filed as a bounded attempt).  A **30-minute round** then gave every one
of the six to CaDiCaL and to Glucose4, and the three cheapest to MapleChrono: 15
runs, 1800 s each, one core each — **15 `unknown`**, including `K96` and `K97` at
192 variables and `K161` at 400, the three where an answer looked reachable.  The
six rows are therefore settled as *open*, not as *undecided-but-easy*: at six to
fifteen times the stored budget, with three unrelated engines, none of them
produces a verdict.  The DIMACS hand-off (20 345 to 149 024 clauses) remains the documented
way to attack them with a stronger solver.  What *can* be
decided in milliseconds is the sub-family one step tighter than circulant: the
colourings invariant under multiplication by the units of `Z_n`, where the
instance collapses to one variable per orbit — 21 for `K128`, 15 for `K161`
(`scripts/orbit_probe.py`).  It is not vacuous (`K8` with sizes `(3,3,3)` is SAT
there, and the witness re-counts), and it is **empty at all six target sizes**, so
no structured candidate is hiding at them.

**And one of the six is now decided, by partitioning it.**  `K97` at `(3,3,3,4)` —
192 variables, 21 016 clauses, 4 096 leaves at depth 12 — is refuted in the
circulant family leaf by leaf in §9b, which also says what that is and is not worth:
the other five (`K96`, `K127`, `K128`, `K161`, `K538`) are still open here, and the
published witness this sub-family is measured against sits at `K96`.  That statement is about that
sub-family, and nothing else: the full circulant family and every published bound
are untouched by it.

**Where that restriction actually stops helping (measured).**  The full unit group
is *too* strong a restriction, so `scripts/orbit_probe.py --by-subgroup` sweeps
every distinct subgroup of it (5–16 per size), most restricted first, and the
answer changes with the size:

| instance | what the sweep decided | what is left |
|---|---|---|
| `K127` `(4,4,4)` | **SAT in 2 s** at the order-42 subgroup (3 orbits, 9 variables), witness re-counted: `R(4,4,4) > 127` | nothing below it |
| `K96` `(3,3,3,4)` | 14 of its 16 subgroups (56–144 variables): UNSAT | the two that are the full 192-variable instance |
| `K97` `(3,3,3,4)` | 10 of the 12, down to order 3 (4–96 variables): UNSAT | the two that are the full 192 |
| `K128` `(4,4,4)` | 10 of the 12 (21–144 variables): UNSAT | the two that are the full 192 |
| `K161` `(3,3,3,3,3)` | 12 of the 16 (15–170 variables): UNSAT, plus one order-2 family (235 variables) **UNSAT after 3774 s** | the three order-2 families and the full 400 |
| `K537` `(3,3,3,3,3,3)` | all 8, including the full 1608-variable instance: UNSAT — the arithmetic obstruction, since `3 | n` | nothing |
| `K538` `(3,3,3,3,3,3)` | 3 of the 6 (18–30 variables): UNSAT | order 4 (810) and the two that are the full 1614 |

The `K127` row is the useful one: the ordinary verifier re-counts the colouring,
but `127` is the published *witness* size (`R(4,4,4) >= 128`), so this reproduces
a known bound inside a restricted family — it is not a record, and it is the one
place where the restriction stops being empty.  What is left after the sweep is
never smaller than the full instance: for odd `n` the difference classes are
already quotiented by ±1, so the order-2 subgroup *is* the whole circulant family,
and `K96`/`K97` at 192 variables and `K161` at 400 are exactly the instances that
spent 30 minutes without a verdict above.  Those residual families (`K96` full,
`K97` full, `K161` full, `K538` order 4 and full) are the only undecided rows this
tool has left, and they are the ones handed a 3-hour budget.  One of them has since
fallen: `K161` at order 2 — 47 orbits, 235 variables, 11 505 clauses — is **UNSAT**
after 3774 s, so at `K161` every structured family below the full instance is now
refuted and only the 400-variable circulant instance itself is open.  The other
five were still running when this was written; the raw rows are in
`runs/invariant_sweep.json`, which is where a result has to land before it is
quoted here.  Two caveats, in the repository's own terms: the `sat` row is a
*witness*, re-counted by the ordinary verifier, but this `unsat` row is a solver
**verdict** with no stored DRAT trace and no certificate — the nine proof-carrying
`unsat` rows above are theorems, this one is not, and turning it into one means
re-running the reduced CNF with `--proof` (the reduced encoding is not exported by
the CLI yet, so the trace cannot be produced with the current commands).

**The second symmetry, and the one that was still there.**  The circulant encoding
had no colour-naming break at all, although colours with the same forbidden-clique
size are interchangeable: for `(3,3,3,4)` the three 3s can be relabelled (`3!`),
for five 3s `5!`, for six 3s `6!` — a factor 720 at `K537`/`K538`.  Requiring
equal-size colours to *first appear* in increasing order costs no colouring (any
colouring can be relabelled that way), and it is checked rather than asserted:
`orbit_probe.py --compare` runs both encodings on **every subgroup of a case** and
demands the same verdict, with every `sat` row re-counted clean.  On `K29`, `K44`,
`K51`, `K18` and the whole sweep above the two encodings agree family by family;
`K29`/`K44` remain SAT through *smaller* subgroups than the unit group (which is
UNSAT there), and `K18`/`K30`/`K51` remain UNSAT everywhere.  The break buys search
space, not a verdict: with it `K96`/`K97` (192 variables) and `K161` (400) still
have no verdict inside their budget.

**The construction space, searched (measured).**  The note in `docs/targets.md` asks
for the next step to be a search over *constructions* rather than over colourings, and
that is now implemented: `oplab.cayley` colours the **inversion classes of a group of
order `n`**, so the colouring is translation invariant and one variable per (class,
colour) decides the family — the circulant encoding is the cyclic case, and the other
groups are constructions the circulant sweep cannot see.  The portfolio is complete for
the *abelian* groups (7 for `n = 96`, 15 for `128`) plus one entry per dihedral,
dicyclic and semidihedral family and per direct product with a small cyclic factor:
22 groups at `K96`, 26 at `K128`, 2 at `K538` (only `Z269 x Z2` and the non-abelian
`D269` exist there), 1 at `K97` and 1 at `K161` (prime and `7 * 23`, so nothing beyond
the cyclic group).  Every table is checked against the group axioms before it is
searched, which is what makes the hand-derived dihedral/dicyclic/semidihedral rules
usable.

| target | groups searched | verdicts (300 s per group, then 3 600 s for the leftovers) |
|---|---|---|
| `K96` `(3,3,3,4)` | 22 | **9 UNSAT**, 13 unknown, **no witness** |
| `K128` `(4,4,4)` | 26 | **24 UNSAT**, 2 unknown (`cyclic`, `D64`), **no witness** |
| `K97` `(3,3,3,4)` | 1 (cyclic) | unknown |
| `K538` `(3,3,3,3,3,3)` | 2 | unknown |
| `K161` `(3,3,3,3,3)` | 1 (cyclic) | unknown |

52 group-runs in 2 141 s at 300 s each, then **21 runs of one hour each on exactly the
groups that round left open** — and six of those 21 came back with a verdict, so 33
sub-families are decided empty and 19 are not, with **no witness anywhere** and no bound
moved: `R(4,4,4)` stays `>= 128`, `R(3,3,3,4)` stays `>= 97`.  The `K128` row is the
interesting one — 5 of its UNSAT groups fall in seconds (2.3 s to 6.2 s: the 381-variable
elementary-abelian `Z2^7`, `Z16xD4`, `Z16xDic2` and two abelian groups), the other 18 spend
the whole five-minute budget, and only `Z2 x D32` fell once the budget was an hour: the two
still open are the 192-variable *cyclic* instance and `D64`.  So the non-cyclic groups are
both easy to refute and empty here, and the group that matters at that size is the one that
was already hard.  At `K96` the hour bought five more refutations (`Z3xDic8`, `Z8xD6`,
`Z8xDic3`, `Z12xDic2`, `Z16xD3`) and thirteen groups are still open.  Raw rows:
`runs/cayley_sweep.json`, whose `rows` are the frontier and whose `superseded` list keeps
the 300 s rows the longer round replaced — the earlier attempt is part of what was
measured, and `scripts/sweep_merge.py` is what wrote both.

**Why the long round stored no traces, measured.**  The same plumbing that makes an
`unsat` row over a group a theorem (below) is available to that round and was left off on
purpose, and the reason is a size, not a doubt.  `scripts/replay_bench.py` times both
replayers on the twelve traces already committed — 901 607 steps — on the same CNFs and
the same traces, back to back.  Measured while this machine was carrying a 16-way solver
round, so both columns are slow and the *pairing* is what is comparable: the in-repo
`oplab.drat` took **4 181 s** (216 steps/s) and the pinned `drat-trim` **245 s** (3 679
steps/s), about **17× end to end**.  The gap is decisive where the trace is big — `K50`,
642 728 steps, 3 678 s against 90 s (**40.7×**); `K55`, 173 165 steps, 258 s against 32 s —
and *absent* where it is small, because a native run pays a fixed cost the Python one does
not: `K35` (505 steps) took 6.5 s in Python and 14.4 s natively, `K36` (260) 4.4 s against
12.4 s.  Idle, the same `K50` pair was measured as 693.7 s against 6.4 s when the store was
written, so the ratio moves with the load (17× to 100×) while the ordering never does.  Raw
rows: `runs/replay_bench.json`.  So the native replayer is the one to reach for when a
trace is too big to replay in Python.  But
the store is committed to git, and the traces are **7.7 bytes per step** (`K50`: 4.98 MB
for 642 728 steps, 6.27 MB for all nine).  A refutation that takes an hour produces on the
order of 10^7–10^8 steps — **hundreds of megabytes each** — so the binding constraint on
a long round is bytes rather than minutes: the clock moved by one to two orders of
magnitude, the repository did not move at all.  Making those rows theorems means keeping their traces outside the store and
citing their digests from the certificate, which is a change to the certificate kind, not
a longer run — until then the long round records verdicts and says so.

**And the witness hunt over the same groups, one hour each.**  A refutation is not the
prize at these sizes — a clean colouring would be, and it is `cayley.repair` that hunts
one (`--mode repair`), because CDCL is poor at *finding* a witness in a structured
instance even where one exists.  The three groups at `K128` were given an hour each of
local search, and it found **no witness in any of them**: three `unknown` rows with the
best violation count each reached, in `runs/cayley_long_k128_repair.json`.  Together with
the 24 refutations that is *no translation-invariant witness at the record size*, neither
found nor left unrefuted except for the cyclic group and `D64`, and `R(4,4,4) >= 128`
stays where it is.  Those repair rows are deliberately **not** merged into the sweep: they
report no decision, so `scripts/sweep_merge.py` refuses them (folding one in would replace
the frontier row with an attempt) and they stay in their own file, quoted here.  A repair
round over the thirteen open `K96` groups — the same experiment at the size where a
published witness *does* exist — found no witness either: thirteen `unknown` rows after an
hour each, in `runs/cayley_long_k96_repair.json`.  That is the measurement worth having:
the witness at `K96` is real, and a one-hour local search over the classes of any of these
thirteen groups does not reach it, so the published witness is not translation invariant
over them.

The rows above are verdicts from that sweep, and the plumbing that turns a verdict into
a theorem now exists for this encoding too: `cayley_solve` takes a proof path, the solver
writes its DRAT trace, `cayley.replay_proof` re-checks it against **that group's** CNF
before anything is stored (no solver in the loop), and the certificate kind
`cayley_multicolour` accepts `unsat` *only* with a trace it can replay — a bare verdict
is refused rather than stored, since the clauses are built from the group description
and a trace from another family does not fit.  Four rows exercise it and are committed:
`K18` over the dihedral `D9` (122 steps) and over the product `Z3xD3` (50), `K30` over
`D15` (14 039, 53 kB), and `K6` over `D3` as `obstructed` — the arithmetic decides that
one, so no solver run is claimed for it.  (A fifth row sits in the same store and is not
one of these: the `K96` witness the portfolio screen found, a `sat` row, which carries a
colouring instead of a trace.)  Three reasons for the choice of anchors: they
are the groups the sweep above already decided, they are cheap to reproduce
(`make cayley-anchors`, seconds), and they are rows the *circulant* store cannot hold,
because over `Z_n` those statements are different (and mostly open) ones.  Both stores
are pinned the same way — `proof_manifest.py --certs certs/cayley --check`, which `make
proof-store` runs alongside the circulant manifest — and all twelve traces are
cross-checked by the external `drat-trim`, which rebuilds each CNF from its certificate
(the group rows from the group description, not from `(n, sizes)`).

One caveat stays: the portfolio is a portfolio — it is not every group of order `n`,
only the families `cayley.groups_of_order` lists.  A proof-carrying `unsat` is therefore
a theorem about *one group*, and reading it as a statement about every construction of
that size would be reading it wrong.

**That caveat is now closed, and closing it changed an answer.**  The gap was the one
thing GAP was installed for: `make portfolio` exports *every* group of an order out of
the SmallGroups library as permutation generators
(`scripts/gap_export_smallgroups.g`, GAP 4.15.1 with the `smallgrp` package),
`scripts/portfolio_build.py` closes each one in Python and re-counts the invariants GAP
declared for it, and the checked lists are committed — **231** groups of order 96 and
**2 328** of order 128 (`data/smallgroups_96.json`, `data/smallgroups_128.json`, the
second recording its four export parts and their digests).  Nothing downstream trusts
GAP: `load_portfolio` closes every group again and re-counts `portfolio_signature` on
load, a disagreement is an error and not a warning, and a certificate's `id` is
provenance.  What is *quoted* rather than proved is the classification itself — at order
128 the invariant signature leaves 462 of its 1 050 classes holding more than one group,
and sharing a signature is necessary but not sufficient for being isomorphic, so "every
group of order 128" is the library's claim while each individual table, and every fact
the repository derives from it, is ours.

The screen over all 231 groups of order 96 — 20 s each, 519 s of wall clock, run with
`--keep-going` so that a witness does not stop the round
(`runs/cayley_full_k96.json`) — gives 15 `unsat`, 213 `unknown` and **three witnesses**.
`SmallGroup(96,87)`, `SmallGroup(96,147)` and `SmallGroup(96,230)` each carry a
translation-invariant colouring of `K96` with nothing monochromatic in colours
`(3,3,3,4)`: 252, 260 and 316 variables, decided in 21.3 s, 21.3 s and 13.1 s, each
re-counted by `multicolour.verify_colouring` (`monochromatic_cliques = [0,0,0,0]`).  So
`R(3,3,3,4) > 96` *is* realised inside the invariant construction space — and the round
above, nine refutations and thirteen opens out of twenty-two groups with an hour of
repair on each open one, was a fact about its portfolio.  None of the three shares an
invariant signature with any named group, so they are not near-misses of the groups that
were searched: the witness lives in groups the named families never contained.  No
published bound moves — `R(3,3,3,4) >= 97`, and 96 is the size below it — but "no
translation-invariant witness at `K96`" is false of the complete portfolio, and that is
the kind of sentence this repository exists to be wrong about out loud.

One of the three carries a certificate as well
(`certs/cayley/k96_3x3x3x4_SmallGroup_96_87.json`, verified like every other row); the
other two stay verified rows in the round's JSON.  The reason is a cost, not a doubt:
a certificate's Lean theorem counts `C(96,4) = 3.3 M` subsets with `native_decide`, and
three of those is a measurable addition to `lake build` for one more instance of the
same statement.  One is enough to exercise the path end to end, and the round's JSON
keeps the other two colourings in full.

The same screen over the other half of the portfolio came back empty, which is the half
of a result that is easiest to leave unsaid: all **2 328** groups of order 128, 20 s each
on 16 workers, **893 s** of wall clock (`runs/cayley_full_k128.json`) — **2 314 `unsat`,
14 `unknown`, no witness**.  Nothing new is proved and the finding is a negative one about
a portfolio, but two numbers in it are the reason the round was run.  First, the screen
is cheap because the instances are: the median group was *refuted* in 3.5 s — the
slowest refutation 22.7 s, and 71 of the 2 314 spending the whole 20 s — so the 2 314
refutations cost 11 163 s of solver time in 893 s of wall clock.  Order 128 does not
need an hour per group; it needs an hour for fourteen of them.  Second, the widening
that *falsified* the K96 sentence leaves the K128 one standing.  The 26 named groups map
into the portfolio by invariant signature — 25 onto one id each, `Z2xDic16` onto four
that share one — and 22 of the 26 are refuted inside 20 s.  The four that are not are
the cyclic group, `Z64xZ2`, `D64` and `Z2xD32`: the three the 300 s round left open,
plus the one that round needed all 300 s for.  Over the whole portfolio the 14 still
open are
`SmallGroup(128,{1, 45, 89, 93, 100, 102, 134, 151, 157, 159, 160, 161, 444, 991})`,
which contains the cyclic group (id 1) and `D64` (161) — the two the long round could not
decide in an hour — and `Z2xD32` (991), which it decided only at the hour.  A screen is
not a hunt, and this one names the fourteen groups the next hour should go to.

**One theorem did come out of it.**  The `3 | n` obstruction no longer needs the group
to be cyclic: Cauchy's theorem gives an element `g` of order 3 in *any* group of order
`n` with `3 | n`, so `{e, g, g²}` has all three of its differences in the single class
`{g, g⁻¹}` and its `n/3` translates are monochromatic in whatever colour that class
carries.  No translation-invariant colouring of any group of order `n` avoids
a monochromatic triangle there — `K162`, `K537` and every other all-triangle instance
divisible by 3 are unreachable from *any* group, not just from `Z_n`.  The verifier
re-derives that argument arithmetically (`cayley_multicolour`, status `obstructed`) with
no solver in the loop.

The checkers are not taken on faith either.  `K6` in this same encoding is
refuted by a trace *and* by Lean's exhaustive proof of `R(3,3) = 6`; the tampering
tests include a solver-free instance (`(1 ∨ ¬2)` is not RUP and its `(2)` is not
RAT) where both rules must fail, and a trace whose certificate's digest was
forged, which only the external checker refuses.  The tests have also caught two
real bugs in the checker: the first version accepted the empty clause without a
RUP check (RAT cannot apply to it, so any trace pasting `0` at the top looked
valid), and the watched-literal version dropped the entries a conflict left
unexamined in a watch list — `K18`'s trace then came back "neither RUP nor RAT",
which is exactly what that trace is for.

Four things are worth stating plainly:

1. **The validations are exact.** `R(3,3,4) = 30` is a theorem (Codish et al.,
   2016): the encoding finds a witness at 29 and proves none exists at 30.
   `R(4,4) = 18` likewise. The 5-cycle and the Paley graph are rediscovered
   without being told about them. Those five rows are the evidence that a
   `sat`/`unsat` pair from this encoding means what it says.
2. **No decided instance is a record.** The five `sat` rows are circulant
   witnesses at published *witness* sizes, and every `unsat` row says the
   circulant family has nothing at that size — which at three published witness
   sizes (`K35`, `K42`, `K50`, the witnesses for `R(4,6) >= 36`, `R(5,5) >= 43`
   and `R(3,3,3,3) >= 51`) means those published witnesses are not circulant
   colourings. For the multicolour frontier that is a *negative about a
   sub-family*: it moves no published bound. The statement is deliberately limited
   to the 18 decided rows — the six `unknown` verdicts record a spent budget, not
   evidence of absence — and two of those six (`K96`, `K127`) sit at the published
   witness sizes of `R(3,3,3,4)` and `R(4,4,4)`, where the published witnesses
   come from algebraic and recursive constructions, so whether a circulant witness
   exists there is left open.
3. **At `3 ∣ n` the all-triangle instances are obstructed by arithmetic, not by
   search.**  If every colour forbids a triangle and `3 ∣ n`, the difference
   class `n/3` is a real class and the three edges of `{0, n/3, 2n/3}` all lie in
   it; the colour class `n/3` receives is then monochromatic on `n/3` triangles.
   So **no** circulant colouring of `K_n` is clean — for any number of colours —
   and `K6`, `K51`, `K162`, `K537` are all settled without a solver. This is the
   only *proved* negative in the repository that is not an exhaustive sweep: the
   Lean layer checks `diffClass n 0 (n/3) = n/3 ∧ …` per instance with
   `decide`.
4. **Five instances are undecided and stay undecided here.** `K96`,
   `K127`/`K128`, `K161` and `K538` returned `unknown` when the encoding reached
   20 000–149 000 clauses and the 120 s/300 s budget ran out. They are not one
   budget step away either: a 30-minute round gave each of them to CaDiCaL and to
   Glucose4, and the three with the fewest clauses (`K161`: 11 680 over 400
   variables; `K96`: 20 345; `K97`: 21 016) to MapleChrono as well — 15 runs of
   1800 s, one core each, **15 `unknown`**, every one of them recording
   `budget_expired` rather than leaving the reason to be inferred. They are stored
   as certificates with `status: unknown`, the verifier re-derives their encoding
   size and nothing else, and no table in this repository counts them as a
   negative. Deciding them needs more than this budget, and more than one more
   engine: the DIMACS hand-off is what makes that possible —
   `oplab mc-circulant --n 96 --sizes 3,3,3,4 --dimacs-only --dimacs
   dimacs/k96_3x3x3x4.cnf`, which `scripts/run_full.sh` does for all six, and which
   the 30-minute round above consumed without a verdict.  A sixth instance, `K97`,
   was on this list until it was decided without a longer budget — by partitioning
   it, §9b — and the form that decision takes (verdicts, not a proof) is the reason
   it is a run artifact rather than a row in this store.

## 9b. `K97` at `(3,3,3,4)`: a partition, and the leaves refuted one by one

One of the rows above — the one no longer budget decided — is now refuted *inside
the circulant family*, by cutting the instance into a complete decision tree and
refuting every leaf.  The `unknown` row above is left where it is, because what came
out is a different kind of claim.

`march_cu` (pinned in [`docs/tools.pin`](docs/tools.pin)) cut the 21 016-clause
instance at depth 12 in **17.8 s** into **4 096 cubes**, and the trie test on that
list — every internal node branching on one variable, both ways — says it is a
**complete decision tree**: 4 096 leaves, all of them at depth 12, is exactly
`2^12`.  Kissat 4.0.4, the binary built from upstream, then refuted the leaves, one
process per leaf and ten at a time:

| pass | leaves | budget per leaf | result | leaf time | wall clock |
|---|---|---|---|---|---|
| 1 | 4 096 | 60 s | **4 000 refuted** (median 3.5 s, 3 997 of them inside the minute); 96 with no verdict, each one a budget that expired | 41 483 s | 4 783 s |
| 2 | those 96 | 900 s | **96 refuted** (median 70 s, longest 186 s) | 7 285 s | 818 s |

Pass 1's refutations are cheap and the 96 that outlived the minute are the hard
leaves, which is what a partition is for: 41 483 s of leaf time inside 4 783 s of
wall clock, a 8.7× speed-up on ten workers.  Most of the survivors fell just past
the minute they were given — pass 2's median is 70 s — so the second budget did not
have to be fourteen times the first: the leaves it inherited were the ones *near*
the boundary, not a different order of difficulty.  Neither report may
claim the refutation on its own: pass 1's cube list closes but has 96 holes in it,
and pass 2's list is a fragment.  The step that may claim it is `--combine`, and it
*checks* rather than adds up: it re-reads the reports, re-runs the cover test, and
refuses the claim unless the cover's leaves are exactly the cubes the passes decided
and every one of them was refuted (a leaf no pass decided, a cube that is not a leaf,
and two passes returning *different verdicts* for one leaf are each their own
refusal — a budget that ran out is not a disagreement, it is what pass 2 is for).
It accepts here:

```
runs/cube_k97_cnc.json   refuted-cover   4 096/4 096 leaves, cover complete at depth 12, 2 passes
```

**What it says, and what it does not.**  It says no *circulant* colouring of `K97`
avoids a monochromatic triangle in each of the three triangle-colours and a
monochromatic `K4` in the fourth.  It does not touch `K96`, the size the published
bound is measured at (`R(3,3,3,4) >= 97` is a colouring of `K96`, whose circulant
question this repository still records as open), and it moves no published bound in
either direction.  It is also a refutation resting on 4 096 solver **verdicts** rather than
on a proof: the nine `unsat` rows of §9 are proof-carrying and this is not one of
them, which is why it lives in `runs/` — where the report, the cover it was worked
on and the second pass's rows all are — instead of in `certs/`.  Turning it into a
theorem is the step §9 already sets out for the long rounds: refute the same leaves
with an engine that writes a DRAT trace, replay each one against that leaf's CNF,
and the cover check is what makes the collection a statement about the instance.
The two rounds above are the size of that job rather than an argument against it:
given a leaf whose refutation took 186 s, the trace is the thing that costs the
bytes, and the store's own measurement is 7.7 bytes per step.

For scale, the same binary given the whole `K96` instance — the neighbour, 20 345
clauses, 192 variables — spent **768 s** and returned `unknown`
(`runs/rerun_kissat/k96_3x3x3x4.json`, as did `K97`, `K127`, `K128`, `K161` and
`K538` in the same round).  The partition did in 93 minutes of wall clock what a
768 s single run could not, which is the measurement this section exists for.

## 9c. Block-Cayley colourings: the family the published witnesses live in

The circulant rows above are empty at every target size (§9b decides one more of
them), so no amount of them can move a published bound: the bounds are not
circulant.  The next family out is the one the published witnesses are actually
described in — Chung's four-colouring of `K50` is a **three-block block-Cayley
colouring over a group of order 16, extended by two vertices**, and the SAT results
that have moved multicolour lower bounds since 2015 (Rowley 2022; Wesley 2025) all
impose a structure of that kind and let a solver fill it in.

`oplab.blocks` is that family: `b` blocks carrying an abelian group of order `m`,
plus `e` free extra vertices, one variable per (class, colour), one clause per
(colour, clique class set).  At `b = 1` it is the circulant family, class for class
(checked, not assumed), so it sits around the two families already swept rather than
beside them.  The encoding is checked the same way: the classes partition the
`C(n, 2)` edges on eight shapes, the clause set is satisfied by exactly those
assignments whose expansion is clean on five instances small enough to exhaust, and
the colour break — one class fixed to colour 0, `4! = 24` fewer searches — is proved
not to cost a colouring when the forbidden sizes are equal, and refused for `(4, 6)`.

**The family is the right one, and that is measured.**  Three blocks of `Z_2^4` plus
two extras, the published witness's shape, is **SAT at `K50` in 527 s** (760
variables, 14 871 clauses) and the colouring re-counts clean: `R(3,3,3,3) > 50`
reproduced inside the family.  That is what makes the one-vertex extension a
question worth asking, and it validates the decode as much as the family.  The group
matters, not only the block order: the same three blocks of order 16 taken cyclically
(`Z_16`, 676 variables, 14 556 clauses) is still `unknown` at 900 s, while the
elementary-abelian shape was decided.

**The obstruction comes back per block.**  `n = 51` escapes the circulant `n/3`
argument because a block of `Z_17` has no difference 17 — but inside a block it
returns: if `3 | m`, Cauchy gives an element `d` of order 3, and `{x, x+d, x+2d}` has
all three differences in the class of `d`, so that block carries a monochromatic
triangle whichever colour the class gets.  Three shapes are refuted by that argument
in **under a second of wall clock, with no solver opened**, and `block_obstruction`
now says so before the engine is started.

**What the `K51` ladder measured.**  Every shape whose blocks avoid a factor of three:

| shape | variables | clauses | verdict | time |
|---|---|---|---|---|
| 3 blocks of `Z_17` | 300 | 5 234 | `unknown` | 900 s |
| 3 blocks of `Z_2^4` + 3 extras | 960 | 20 121 | `unknown` | 900 s |
| 3 blocks of `Z_16` + 3 extras | 876 | 19 806 | `unknown` | 900 s |
| 6 blocks of `Z_8` + 3 extras | 1 164 | 24 754 | `unknown` | 900 s |
| 17 blocks of `Z_3` | 1 700 | 30 788 | **obstructed** | arithmetic |
| 3 blocks of `Z_15` + 6 extras | 1 404 | 32 634 | **obstructed** | arithmetic |
| 4 blocks of `Z_12` + 3 extras | 972 | 21 482 | **obstructed** | arithmetic |
| 3 blocks of `Z_17`, one hour | 300 | 5 234 | `unknown` | 3 600 s |
| 3 blocks of `Z_2^4` + 3 extras, one hour | 960 | 20 121 | `unknown` | 3 600 s |
| `K51` general, `symmetry=2`, one hour | 193 950 | 470 222 | `unknown` | 3 060 s |

No witness, and no refutation either: four shapes are open after fifteen minutes of
Kissat each.  Buying two of them an hour instead — the purest shape (3 blocks of
`Z_17`, 300 variables) and the largest (3 blocks of `Z_2^4` plus 3 extras, 960) —
returned `unknown` again at **3 600 s**: four times the budget, the same non-verdict.
And the general instance, not the family, was given its own hour: `K51` as a whole,
193 950 variables and 470 222 clauses with the `symmetry=2` break, ran 3 060 s and
came back `unknown` too.  More time is not the lever; a partition or a better
encoding is.

And the one-vertex extension of the witness we do have is **dead**:
with the `K50` colouring fixed, "colour the 50 edges to one new vertex" is a
200-variable, 1 575-clause CSP, and it is UNSAT in **0.19 s**.  That is a fact about
that colouring and not about `K51` — a clean `K51` would appear as an *extendable*
clean `K50`, and there are astronomically many of those to draw from.

So `R(3,3,3,3)` stays in `[51, 62]` and `K51` stays open.  What this section adds is
the machinery to attack it in the family the record is written in, the measurement
that the family contains the record size, one arithmetic obstruction that prunes the
ladder, and one hard negative.  It is not a bound, and the tables say so.

## 9d. A GPU search for a witness: the ceiling, measured

The `K51` rows above are `unknown` because the engine is CDCL, and CDCL is sequential:
one lineage of decisions, no GPU port worth the name, and a bottleneck that is the
shape of the search tree rather than arithmetic.  Finding a *witness* is the other
kind of computation — count, for many skeletons at once, how many forbidden cliques
are monochromatic — and that one is arithmetic a card does well.  `oplab.gputabu` is
that search, so the claim resting on it can be measured instead of guessed.

**The kernel is fast, and the fast part is not the hard part.**  Counting the
monochromatic cliques of 4 096 colourings at once runs 24–35× faster than vectorised
numpy on this machine (46→1 130 k evaluations/s at `K51` 3×`Z_17`, 10→200 k/s on the
whole of `K51`), and both paths were checked against each other on shared skeletons
rather than trusted (`docs/methodology.md`).  The walk built on it is TABUCOL over a
population of 4 096 skeletons, each with its own tabu list, at **0.34–0.69 million
flips per second**.

**It is a search, and the report says so.**  A run that stops with violations left is
`best-effort` with a count; it never says `unsat`, because a heuristic has no way to
know.  A run that reaches zero is expanded and handed to `verify_colouring` — and a
run that claims zero and fails that check is `sat-invalid`, a bug in the module and
not a result.  The incremental counter is itself checked: the walk recounts from
scratch every 2 000 steps and reports the disagreements in `recount_drift`, which is
**0 in every run below**.  That check earned its keep — it caught a delta taken from a
tabu move that was never applied, and a gather one element past the end of a row on
the padded class sets of `Z_17` (in characteristic two a triangle cannot be isoceles,
so the elementary-abelian instances never exercised that path).

**The calibration is the part that matters.**  Before any `K51` run means anything,
the same walk was pointed at instances whose answer is known:

| instance | status of the instance | best found | time |
|---|---|---|---|
| `K5` (3,3) | has a clean colouring (`R(3,3) = 6`) | **0**, witness verified | 0.1 s |
| `K29` (3,3,3,3) | has one (circulant, §3) | **0**, witness verified | 1.3 s |
| `K44` (3,3,3,3) general | has one (circulant) | 68 | 45 s |
| `K50` 3×`Z_2^4`+2, the family | **SAT, decided by Kissat in 527 s** (§9c) | **2** | 600 s |

That last row is the whole story.  On an instance where a witness provably exists, in
the family the witness lives in, with ten minutes and 264 million flips, the walk
gets to two monochromatic cliques and stops.  A searcher that cannot close the
smaller, known-satisfiable instance has earned no claim about the larger one.

**What the twenty minutes per shape actually measured.**  Four shapes, 4 096 walks
each, `pick-every 8`, seed 11:

| shape | classes | class sets | best | steps | flips | rate | drift |
|---|---|---|---|---|---|---|---|
| 3 blocks of `Z_17` | 75 | 4 708 | **3** | 201 038 | 823 451 648 | 686 k/s | 0 |
| 3 blocks of `Z_2^4` + 3 | 240 | 18 440 | **3** | 104 281 | 427 134 976 | 356 k/s | 0 |
| 3 blocks of `Z_16` + 3 | 219 | 18 272 | **3** | 100 423 | 411 332 608 | 343 k/s | 0 |
| 6 blocks of `Z_8` + 3 | 291 | 22 716 | **6** | 114 286 | 468 115 456 | 390 k/s | 0 |

**The population was not the lever either.**  On 3×`Z_17` at a fixed 120 s, 4 096
walks got 17 897 steps each and 16 384 got 5 230 — both ended at 3 — while the
aggregate rate moved only from 611 k to 714 k flips/s.  Four times the skeletons,
three and a half times less depth each, the same answer: what this walk needs is
*per-walk* progress, and the card buys multiplicity, not progress.  A million walks
does not fit in the first place: the counts are `S x k` bytes per walk, 18.4 KiB on
this shape, so 17.5 GiB for the *smallest* of the four against 15 GiB on the card —
and four times that on the six-block shape.

**2.13 billion flips, eighty minutes, no witness** — and no `sat-invalid` either, so
the counting is sound; the runs simply ended where they ended.  The reported figure is
the smallest value in each run's 30-second history, so it is a record and not a
snapshot.  For the record the numbers are *not* an argument that these families are
empty: `K50` is the proof that a plateau in this walk says nothing about existence.
What the section establishes is narrower and worth having — the GPU is the right tool
for the witness side and the wrong tool for the decision side, the machinery now
exists and is tested, and on this platform it is **not** sufficient for `K51`.

```bash
python scripts/gpu_tabu.py 51:3,3,3,3 --blocks 3 --group 17 --seconds 1200 \
    --walks 4096 --pick-every 8
```

## 9e. A guided annealing, and the gate it fails

The batched walk of §9d was never short of steps: 264 million class moves, and it still
stopped two cliques away from a witness that exists.  That leaves two readings — the
instance is beyond local search in this encoding, or the walk was tuned badly — and only
a second, differently steered search can tell them apart.  `oplab.anneal` is that second
search: penalty weights (guided local search) so a set that stays violated keeps getting
expensive, Metropolis acceptance with a cooling-and-reheating schedule, Kempe chains so a
whole cluster can be recoloured in one step, and the same recount discipline (every
2 000 steps, against a full recount, reported in `recount_drift`).

**The gate was written before the target, and it held.**  The campaign rule was that
this search may not speak about `K51` until it has rediscovered the *known* `K50`
witness, in the family where that witness lives, from a random start — the same
instance, the same encoding, no seeded hint.  `scripts/anneal_hunt.py` enforces it as
code: any spec other than the calibration refuses to run without a stored pass.

Four seeds, 120 s each, on `K50` 3×`Z_2^4`+2 (190 classes, 13 540 class sets):

| seed | steps | steps/s | best | Kempe swaps | drift |
|---|---|---|---|---|---|
| 0 | 441 451 | 3 679 | **3** | 2 175 | 0 |
| 1 | 447 092 | 3 726 | **3** | 2 250 | 0 |
| 2 | 447 734 | 3 731 | **3** | 2 270 | 0 |
| 3 | 454 881 | 3 791 | **2** | 2 239 | 0 |

Every run is at three by its **second** ten-second report (six at the first) and never
moves again: the walk reaches the plateau almost immediately and then spends two minutes
failing to leave it.  Four hundred and forty thousand class moves per seed, and the
answer stays two or three cliques away from a colouring that Kissat produced in 527 s.

**What the tuning did and did not buy.**  Measured on the same instance, seed 0,
twenty-second runs of `oplab.anneal` directly — the flags are the CLI's, and the CLI
refuses them without a passed gate, which is the gate doing its job: always-move
with weights leaves **2**; the same rule with Kempe chains at `0.005` leaves **3**; the
Metropolis rule at `T = 0.35` leaves **6**, because at that temperature most steps are
refusals and the walk freezes — which is why `reject=False` is the shipped default and
the cooling schedule is kept as an option the report records; Kempe at `0.05` leaves
**15**, where swaps drown the fine moves.  The spread between the first two is one or
two cliques out of 13 540 sets — **noise, not a finding**: the honest statement is that
chains do not rescue this instance, not that they help.  None of the four configurations
reaches zero, and the two-minute runs do not either.

**It is not broken; it is calibrated, and it fails.**  The same code finds what exists
elsewhere: `K8` 2×`Z_4` at `(3,3,3)` in two steps, `K29` general in 1 543 steps, both
with witnesses the ordinary verifier accepts — and on `K17` `(3,3,3)`, where
`R(3,3,3) = 17` says there is nothing to find, it ends one clique short and reports
`best-effort`, which is exactly what a search may say.  What it cannot do is close
`K50`.

So the two readings are now one: two independent searches, one buying multiplicity
(GPU tabu, 4 096 walks) and one buying steering (weights, chains, 4.4 × 10⁵ steps per
seed), both stall at two or three on the same instance where a witness is known to
exist.  **The plateau is a property of `K50` in this encoding, not of one walk's luck** —
and a plateau that survives two methods and four seeds is not evidence about `K51`
either, in the direction of absence or of existence.

**No `K51` run was made with this tool**, because the gate refused.  That is the point
of having one: §9d spent eighty minutes on four shapes with a search that had never
found a witness it knew to exist.  The question for `K51` is now explicitly a question
about *method*, not about budget — more walks, more steps and more seeds have all been
measured to buy nothing on the calibration instance.

```bash
python scripts/anneal_hunt.py --gate --seconds 120 --seed 0   # writes runs/anneal/gate_k50.json
python scripts/anneal_hunt.py 51:3,3,3,3 --blocks 3 --group 17 --seconds 900
# -> refused with exit code 2 while the gate file does not record a verified K50 witness
```

## 9f. The repair move: exact inside a neighbourhood, and still not enough

§9e leaves a question a plateau cannot answer on its own: is the last two or three
cliques a **local** trap that a coordinated move would escape, or is it a wall?  A
third move settles it, and it is the strongest one available — hand the neighbourhood to
a CDCL engine and let it find the recolouring exactly.

`oplab.anneal.repair` frees the classes of the violated sets plus a random sample of the
classes they touch, freezes everything else, and builds the instance's own clause for
every set that a free class appears in.  The construction is exact inside the
neighbourhood, and that has a consequence worth stating: **no satisfying assignment can
create a violation**, because every set touched by a free class is in the sub-CNF and
every set with no free class is untouched.  So the repair can only lower the count, and
the tests pin that rather than assume it.

**It works where a repair exists.**  On `K8` at `(3,3,3)` a perturbed witness is fixed in
0.02–0.06 s at neighbourhoods of 24 to 128 classes (4 monochromatic cliques → 0), which
is the positive control the suite runs.  On `K50` the same code, starting from the
*stored* witness perturbed to 4 cliques, repairs it at every cap from 24 to 128 in under
0.07 s.

**It does nothing on the plateau.**  The walk of §9e, with `repair_cap = 120` and a 5 s
budget per attempt:

| run | steps | repairs | solved | best |
|---|---|---|---|---|
| annealing, no repair | 441 451 | — | — | 3 |
| annealing + repair | 244 040 | 1 207 | **0** | 3 |

Not one of the 1 207 sub-instances was satisfiable.  The reason is measurable and it is
not the encoding: the violated sets at this plateau have a **one-hop neighbourhood of 159
of the 190 classes**, so "free the classes around them" and "free the instance" are the
same request at any cap above 159 — and below it the engine returns UNSAT, not a timeout
(0 timeouts in the run; §9g explains why that field could not have been non-zero, and
repeats the run on a budget that can actually fire: 1 100 repairs, 0 solved, 0 timeouts).  The last three cliques are therefore not a local trap: there
is no recolouring of 120 of the 190 classes that removes them without creating others.
The search that would succeed on that neighbourhood is the full 527 s CDCL run, which is
where this started.

The step budget says the same thing from the other side: 1 207 repairs cost 45 % of the
steps (441 k → 244 k) and bought nothing, so the move is not merely useless here — it is
expensive, and the default is off (`repair_cap = 0`).

**One bug, caught by measuring rather than by reading.**  The first version had the
clause polarity backwards — it encoded "every class of this set keeps the forbidden
colour", which the engine satisfied by keeping the violations.  Nothing crashed: the
repair reported `solved` 364 times and the count never moved, which is exactly how a
wrong constraint announces itself when the count is recounted after every move.  The
fixed version is what the tables above measure.

```bash
python scripts/anneal_hunt.py --gate --seconds 120 --repair-cap 120 \
    --repair-seconds 5 --gate-file runs/anneal/gate_repair_k50.json \
    --out runs/anneal/repair_k50.json
```

## 9g. Blanking instead of recolouring: the plateau dissolves, and the state is dead

§9f closes the neighbourhood route: at the plateau, freeing 120 of the 190 classes is not
enough, and the neighbourhood that *would* be enough is the instance.  So the next thing
to change is not the neighbourhood but the **encoding** — and the smallest change that
loosens the last classes is to stop insisting that they have a colour at all.

`oplab.anneal.partial` searches partial colourings.  A class may be left **blank**, a
blank class is masked out of every set it belongs to (so a set is never monochromatic
through it), and the objective is one scalar, `violations + blank_weight × blanks`,
minimised by min-conflicts: a violated set is attacked by recolouring one of its classes
**or by blanking it**, whichever is cheaper, and when no violation is left the walk tries
to refill a random blank class, accepting the refill when it is free or by chance
`exp(-cost)`.  Every `attempt_every` steps at zero violations, the blank classes go to
`repair` exactly — `free` now takes an explicit set, which is what a caller who already
knows which classes have to move has to hand in.

**It dissolves the plateau in under a second.**  `K50`, 3×`Z_2^4`+2 (190 classes,
13 540 class sets), seed 0, one re-insertion attempt per 20 000 steps; the second row is
the gate run stored as `runs/anneal/partial_k50_gate.json`:

| walk | seconds | steps | steps/s | violations | blanks | re-insertions | SAT |
|---|---|---|---|---|---|---|---|
| §9e annealing + repair | 120 | 223 k | 1 858 | **3** | — | 1 100 | 0 |
| partial colourings | 240 | 2 868 159 | 11 951 | **0** | **5** | 131 | **0** |

Zero violations at every ten-second report from `t = 20 s` to `t = 230 s`, at **5 blanks** —
2.6 % of the instance — where the annealing of §9e never got below two cliques in two
minutes.  The single blip is at `t = 160 s` (3 violations, 4 blanks) and it clears on the
next report: the walk leaves the state and comes back, which is the churn the refill rule
is for.  It stopped at `best-effort` with 2 violations because the clock ran out mid-cycle;
that is the state it was in, not a plateau.  The dissolution works, and it is not a matter
of tuning: at `blank_weight` 0.25, 0.5, 0.75 and 1.5 (90 s each) the walk lands at 5–8
blanks every time and never more, because it only blanks a class when no recolouring of it
is as cheap.

**And every dissolved state is dead.**  All 131 re-insertions were unsatisfiable — 121 of
them at exactly 5 blanks — and the engine was never the reason: 0 timeouts at a 5 s
budget, answers in 0.02–0.05 s, all on `maplechrono`.  Growing the blank set from one such
state — 5 blanks, zero violations, seed 0, `scripts/partial_support.py` — shows how far
the support is:

| blanks | answer | time |
|---|---|---|
| 5 → 149 | UNSAT | 0.00–0.11 s |
| 157 | UNSAT | 1.84 s |
| 165 | timeout (6 s) | — |

The same measurement from the **stored witness** says what a healthy state looks like:
blanking 2, 4, 8, 16, 32, 64, 96 or 128 of its classes and re-inserting them takes at most
0.05 s.  So a witness survives the loss of 128 of 190 classes (67 %), and the walk's
near-complete state does not survive the loss of 157 (83 %) — and at 165 the sub-instance
is as hard as the full 527 s search it came from.

The reading is not "blanking fails".  Blanking is a strictly better **detector** than a
solver: it reaches zero violations almost immediately and hands over a state that is five
classes short of complete, which is exactly the shape the plateau had.  What it also shows
is that the obstruction is not carried by a few classes — the last five are unpinnable
*for every colouring of the other 185*, so "find the recolouring of the last few" has no
answer to find, and "free more of the instance" costs the whole search.  This is the
precise sense in which §9e and §9f were not local traps: they were complete partial
colourings minus five classes, and no completion exists.  The dead state
is the measurement: it says the plateau is not a coverage problem.

**A budget that was never enforced.**  Found while measuring this, and it matters for
§9f: `Cadical195.interrupt` raises `NotImplementedError` *from the timer thread*, so
`solve_limited` there runs to completion and a "bounded" repair was not bounded at all —
one given 2 s ran for 86 s.  §9f's `repairs_timeout = 0` was therefore a guarantee of the
code path rather than a measurement: the counter could not have been non-zero.  The
bounded path now picks an engine whose interrupt works (`maplechrono`, `glucose4`,
`minisat22`; CaDiCaL stays the choice when nothing has to be stopped), every repair
reports `engine` and `budget_enforced`, and §9f's run was repeated on a real budget:
1 100 repairs, **0 solved, 0 timeouts**, 3 violations, 223 k steps — the same conclusion,
now resting on a timer that can fire.  The suite pins it by handing a pigeonhole formula
to a 0.3 s call and demanding the timeout arrives.

```bash
python scripts/anneal_hunt.py --gate --partial --seconds 240 \
    --gate-file runs/anneal/gate_partial_k50.json \
    --out runs/anneal/partial_k50_gate.json
python scripts/partial_support.py 50:3,3,3,3 --blocks 3 --group 2,2,2,2 --extras 2 \
    --seconds 12 --step 8 --repair-seconds 6 --out runs/anneal/partial_k50_support.json
python scripts/anneal_hunt.py 51:3,3,3,3 --blocks 3 --group 17 --partial --seconds 900
```

The gate applies here too, and for the same reason: `partial` can claim a witness, so it
may not speak about `K51` until it has rediscovered the known `K50` one.  It had not.

## Limitations, stated plainly

* **Only the circulant sweeps are exhaustive.** Everything else is a heuristic
  with a seed and a time budget — including the GPU tabu search of §9d and the guided
  annealing of §9e, both of which search for witnesses and never refute anything: their
  `best-effort` rows are statements about the walk, and their own calibration instance
  (`K50`, where a witness exists) ends at two or three monochromatic cliques.  The
  annealing has not passed its gate, so it has said nothing at all about `K51`; that is
  a limitation of the tool, and §9e reports it as one.  The repair move of §9f is exact
  inside its neighbourhood but that neighbourhood is a choice, and on the `K50` plateau
  every choice up to 120 of 190 classes is unsatisfiable — so "not locally repairable"
  is a statement about that state, not about the family.
* **No record was broken.** The best Tammes configurations found are 0.03°–0.13°
  short of the published values, and no kissing configuration with 41 points in
  dimension 5 was found.
* **The Tammes comparison uses Sloane's tabulated values**, which are best-known
  configurations, not proved optima; a gap of 0.03° is within the numerical
  noise of a summary table, and a 0.03° "improvement" would need its own careful
  analysis before being called a record.
* **The circulant result is a statement about a sub-family.** "No circulant
  witness exists" says nothing about the many non-circulant colourings, and
  nothing about the upper bound. That cuts both ways: the multicolour lower
  bounds were *not* moved, and a `sat` verdict inside the family would have been
  a genuine record (none of the target sizes produced one).
* **`unsat` from the circulant CNF is a theorem, and it is checked by two
  checkers.**  All nine `unsat` rows in §9 carry a DRAT trace that `oplab.drat`
  replays, and every stored trace is cross-checked by the external `drat-trim`
  (`scripts/drat_trim_check.py`, CI job `drat-trim`); the `ramsey_unsat  certificates still have no trace at all.  Where a trace exists, the row rests on
  a ~400-line checker *and* on a checker that shares no code with it, plus the
  encoding rather than on CaDiCaL — still a claim about the circulant sub-family
  only, and still one whose trusted base is two programs rather than none.  The
  `sat` rows are witnesses re-counted by the verifier *and* by Lean.  One `unsat`
  verdict in this repository is deliberately not in that class: the `K97`
  refutation of §9b, which is a solver verdict per leaf of a checked cover and no
  trace at all, and is reported as a measured negative about the sub-family.
* **The multicolour heuristic was beaten by the encoding.** 300 s of tabu search
  could not find the *published* witnesses at `K50` and `K29`, while the
  circulant decision found clean witnesses at `K29` and `K44` in milliseconds.
  That is a statement about which sub-problems are worth encoding, not about
  which colourings exist.
* **Timings are single-machine wall-clock numbers** on a 16-core Windows box
  (`Python 3.14.6`, `numpy 2.4.4`), and are quoted only to describe the effort,
  not as a benchmark.
* **To actually attack these targets**, the next steps are: SAT-based search with
  symmetry breaking for `K43`; the Exoo/Parts style generation of large
  unit-distance graphs; a proper nonlinear optimiser (SLSQP or SNOPT via SciPy)
  with contact-graph continuation for Tammes; and much more compute for
  dimensions 5–7 of the kissing problem. Those are tracked in
  [docs/targets.md](docs/targets.md).
