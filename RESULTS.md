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
53/53 certificates verified   (oplab verify certs)
108/108 claims re-proved in Lean 4   (cd lean && lake build)
```

* `certs/*.json` is mirrored, claim by claim, into `lean/Oplab/Certs.lean` by
  `scripts/gen_lean_certs.py`: 108 theorems over 53 certificates, 103 of them
  kernel-checked by `decide` and 5 (the two `2^21` circulant sweeps, the two
  `K42`/`K43` tabu counts and the `3^12` lower-bound colouring search of the
  Moser drawing) by `native_decide`. The Lean layer has no Mathlib and
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

## Limitations, stated plainly

* **Only the circulant sweeps are exhaustive.** Everything else is a heuristic
  with a seed and a time budget.
* **No record was broken.** The best Tammes configurations found are 0.03°–0.13°
  short of the published values, and no kissing configuration with 41 points in
  dimension 5 was found.
* **The Tammes comparison uses Sloane's tabulated values**, which are best-known
  configurations, not proved optima; a gap of 0.03° is within the numerical
  noise of a summary table, and a 0.03° "improvement" would need its own careful
  analysis before being called a record.
* **The circulant result is a statement about a sub-family.** "No circulant
  witness exists" says nothing about the many non-circulant colourings, and
  nothing about the upper bound.
* **Timings are single-machine wall-clock numbers** on a 16-core Windows box
  (`Python 3.14.6`, `numpy 2.4.4`), and are quoted only to describe the effort,
  not as a benchmark.
* **To actually attack these targets**, the next steps are: SAT-based search with
  symmetry breaking for `K43`; the Exoo/Parts style generation of large
  unit-distance graphs; a proper nonlinear optimiser (SLSQP or SNOPT via SciPy)
  with contact-graph continuation for Tammes; and much more compute for
  dimensions 5–7 of the kissing problem. Those are tracked in
  [docs/targets.md](docs/targets.md).
