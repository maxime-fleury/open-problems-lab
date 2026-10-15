# open-problems-lab

A small laboratory for **attacking open problems in mathematics in a way that can
be checked by a stranger in seconds** — and for recording the attacks that fail,
with their real numbers.

The repository contains four search engines, one exhaustive result, a set of exact
classical constructions, and a certificate format whose whole point is that
nothing a search *claims* is ever believed: every number is recomputed from raw
data by an independent verifier, and CI re-runs that verification on every push.

> **Honesty statement, up front.** Nothing here settles a famous open problem. The
> one genuinely new (if narrow) result is exhaustive: *no circulant colouring of
> `K42` or `K43` avoids a monochromatic `K5`*, which rules out a whole family of
> candidate witnesses for `R(5,5) >= 44`. Everything else is exact classical
> constructions, measured failures with reproducible seeds, and infrastructure.
> The value of the repository is the second part: it turns "I ran a search" into
> "here is a 903-bit string and here is the exact recomputation that turns it
> into a theorem".

---

## Table of contents

1. [What is in here](#1-what-is-in-here)
2. [Results at a glance](#2-results-at-a-glance)
3. [The problems, explained](#3-the-problems-explained)
4. [The certificate contract](#4-the-certificate-contract) — including [§4.4 the Lean layer](#44-the-same-claims-checked-in-lean)
5. [The engines](#5-the-engines)
6. [Command line reference](#6-command-line-reference)
7. [Quick start and reproduction](#7-quick-start-and-reproduction)
8. [Repository layout](#8-repository-layout)
9. [Continuous integration](#9-continuous-integration)
10. [Limitations, failure modes and things that cannot be verified](#10-limitations-failure-modes-and-things-that-cannot-be-verified)
11. [Publishing this as a GitHub repository](#11-publishing-this-as-a-github-repository)
12. [Glossary](#12-glossary)
13. [Sources for every reference value](#13-sources-for-every-reference-value)

---

## 1. What is in here

**Four engines.**

| module | what it does | exactness |
|---|---|---|
| [`src/oplab/sphere.py`](src/oplab/sphere.py) | kissing configurations and the Tammes problem on spheres: exact root systems (`D4`, `D5`, `E6`, `E7`, `E8`, icosahedron, hexagon) plus a time-bounded optimiser | constructions are exact up to float64; search is heuristic |
| [`src/oplab/ramsey.py`](src/oplab/ramsey.py) | Ramsey colourings: an exact monochromatic-clique counter, delta-evaluating tabu search, and an **exhaustive** circulant sweep | counter is exact and brute-force tested; circulant sweep is exhaustive |
| [`src/oplab/unitdist.py`](src/oplab/unitdist.py) | unit-distance graphs: analytic Moser spindle and diamond, exact chromatic number by branch and bound, random growth search | chromatic number is exact; search is heuristic |
| [`src/oplab/sat.py`](src/oplab/sat.py) | CNF encoding of the Ramsey problem with four layers of *sound* symmetry breaking, DIMACS export, Z3 or external-solver backend | encoding is exact; solver verdicts are only as good as the backend |

**One verifier.** [`src/oplab/verify.py`](src/oplab/verify.py) re-derives every
claim from the payload of a certificate, and `oplab verify` exits non-zero as
soon as one claim fails. That command is what CI runs.

**One Lean layer.** [`lean/`](lean/README.md) re-checks the same finite claims
in Lean 4 — 108 generated theorems, 103 of them kernel-checked by `decide` —
with no Mathlib, no solver and no floating point in the trusted base. See
[§4.4](#44-the-same-claims-checked-in-lean).

**One exhaustive result and a pile of measured failures.** See
[RESULTS.md](RESULTS.md) for the full numbers and `runs/*.log` for the raw output.

---

## 2. Results at a glance

| what | result | how it is checked |
|---|---|---|
| Classical kissing configurations, dimensions 2–8 | `tau(2)>=6`, `tau(3)>=12`, `tau(4)>=24`, `tau(5)>=40`, `tau(6)>=72`, `tau(7)>=126`, `tau(8)>=240` | integer vectors, exact integer arithmetic in the tests; `max_dot <= 1/2` recomputed by the verifier |
| Circulant colourings of `K42` and `K43` | **all `2^21` enumerated, zero avoid a monochromatic `K5`** | exhaustive by construction; `oplab verify --deep` re-runs the whole sweep |
| Validation of that sweep | finds the 5-cycle (`R(3,3) > 5`) and Paley(17) (`R(4,4) > 17`); finds nothing at `K6`, `K18`, as the theorems require | the same sweep on known cases |
| Tammes `S^2`, `N = 15..23` | best found within **0.026° to 0.127°** of Sloane's tabulated records; no record beaten | each configuration is a verified certificate |
| Kissing `+1` attempts, dimensions 5, 6, 7 | best `max_dot` = `0.51663`, `0.54402`, `0.57114` (need `<= 0.5`) | recorded as honest failed attempts, flag verified |
| Tabu search on `K42` / `K43` | 100 and 138 monochromatic `K5` remaining (from ≈1880) | exact counter re-verification |
| SAT encoding, `k=3` and `k=4` | `K6` unsat, `K5` sat, `K17` sat at every symmetry level | brute force for `K5`/`K6`, theorem `R(4,4)=18` for `K17` |
| SAT on `K42` / `K43` | inconclusive within the budget; measured clause-ingestion cost makes the Python/Z3 path unusable at this size | recorded as inconclusive, never as a verdict; DIMACS export provided for real solvers |

---

## 3. The problems, explained

### 3.1 Ramsey numbers: `R(5,5)`

`R(5,5)` is the smallest `n` such that **every** 2-colouring of the edges of the
complete graph `K_n` contains a monochromatic `K5`. Equivalently: the smallest
`n` for which no "clean" colouring exists.

What is known (and only that):

* `43 <= R(5,5) <= 46`.
* The lower bound has stood since **Exoo (1989)**, who exhibited a 2-colouring of
  `K42` with no monochromatic `K5`. The upper bound is **Angeltveit & McKay
  (2024)**, who proved `R(5,5) <= 46` with roughly 30 CPU-years of SAT work with
  symmetry breaking.
* Nobody knows whether `K43` admits a clean colouring. If it does, the lower
  bound rises to 44; if it does not, then `R(5,5) = 43` exactly.

Why it is a good target for this repository: **a witness is 903 bits** —
`C(43,2) = 903` edge colours. Verifying a claim `R(5,5) >= 44` is a
millisecond-scale computation, and a claim `R(5,5) <= 43` is at least a
well-defined combinatorial object rather than an informal argument.

What this repository adds:

* an exact counter for monochromatic `K5` (`ramsey.count_mono_clique`), tested
  against brute force, and a delta rule for edge flips (a flip changes only the
  cliques through the flipped edge) that is tested against full recomputation;
* a tabu search on top of it — honest but far too weak (see the results table);
* the **exhaustive circulant sweep**, which is the actual contribution: it
  enumerates the entire family of translation-invariant colourings and shows
  that no witness for `R(5,5) >= 43` can be found there;
* a SAT encoding with sound symmetry breaking, plus DIMACS exports that any real
  solver can consume.

### 3.2 The Tammes problem

For a fixed `N`, place `N` points on the unit sphere `S^2` and maximise the
minimum angular separation between them. Optimal configurations are proved for
`N <= 14` and `N = 24`; for `N = 15..23` only best-known configurations exist
(N. J. A. Sloane's tables, "putatively optimal").

A configuration is `2N` numbers. That is the entire certificate, and the
verification is a maximum over `N(N-1)/2` dot products. This is the cleanest
"positive result is cheap" target in the repository.

This repository's optimiser (threshold descent + single-point polishing +
optional quasi-Newton polish on a smooth surrogate) lands within a few
hundredths of a degree of every published record in under a minute per size on a
laptop. The gap is a compute gap, not an algorithmic mystery — which is exactly
what `RESULTS.md` documents, per `N`.

### 3.3 Kissing numbers

`tau(d)` is the maximum number of non-overlapping unit spheres that can touch a
central unit sphere in `R^d`, equivalently the maximum number of unit vectors in
`R^d` with all pairwise dot products `<= 1/2`.

Known: exact for `d = 1, 2, 3, 4, 8, 24`; open otherwise. The classical lower
bounds are `tau(5) >= 40` (the `D5` root system), `tau(6) >= 72` (`E6`),
`tau(7) >= 126` (`E7`), and `tau(8) = 240` (`E8`). Best known: `40..44`,
`72..77`, `126..134`.

This repository rebuilds `D5`, `E6`, `E7`, `E8` **from integer vectors** (with
`E6` and `E7` obtained as orthogonal complements inside `E8` and then projected
onto their own span, so they live in exactly 6 and 7 dimensions) and verifies
them in exact integer arithmetic. It then tries to add one point in dimensions 5,
6 and 7 — and fails, with the best values recorded. In dimension 5 the failure is
narrow and reproducible: two independent workers converge on the same
`max_dot = 0.516632968710`, about 1.9° too close.

### 3.4 The chromatic number of the plane

The Hadwiger–Nelson problem asks for the minimum number of colours needed to
colour every point of the plane so that no two points at distance exactly 1 share
a colour. Known: `5 <= chi <= 7`. The lower bound came from the Moser spindle
(7 vertices, 4-chromatic, and the smallest such graph — this repository builds it
from analytic coordinates and verifies that it is 4-chromatic *and* 4-critical).
No 6-chromatic unit-distance graph is known; the smallest known 5-chromatic one
has 509 vertices (Jaan Parts).

Lower bounds come from finite unit-distance graphs, so the certificate is a
finite point set plus its edge list. This repository provides an exact chromatic
number solver (branch and bound with DSATUR ordering, cross-checked against an
independent backtracking reference), a check that a claimed edge list is *exactly*
the unit-distance pairs (with a grey band that raises rather than guessing when a
pair is too close to distance 1 to classify), and a growth search whose honest
ceiling is 4 — because the smallest known 5-chromatic graph has 509 vertices,
nothing this generator produces can reach 5, and `RESULTS.md` says so instead of
implying otherwise.

---

## 4. The certificate contract

### 4.1 Format

```json
{
  "schema_version": 1,
  "problem": "kissing",
  "title": "E8 root system: 240 kissing points in dimension 8",
  "payload": { "dim": 8, "points": [[...], ...] },
  "claims":  { "n_points": 240, "dim": 8, "max_dot": 0.5 },
  "provenance": { "generator": "oplab build --kind sphere --system e8", "created": "2026-10-15" },
  "payload_sha256": "…",
  "verification": { "verified": true, "establishes": "tau(8) >= 240" }
}
```

* **`payload`** is the evidence: coordinates, a colouring string, a point set, a
  search summary.
* **`claims`** are what the search wants to assert. They are never trusted; they
  are compared with what the verifier recomputes.
* **`payload_sha256`** makes hand-editing detectable before any mathematics runs.
* **`verification`** is written by the verifier (`oplab verify --write`), never
  by the search code, and is recomputed on every run.

### 4.2 What each verifier recomputes

| `problem` | recomputed from the payload | what it can establish |
|---|---|---|
| `kissing` | unit norms; maximum pairwise dot product `<= 1/2` | `tau(d) >= N` |
| `tammes` | unit norms; minimal angle | a valid configuration of `N` points |
| `spherical_search` | the reported maximum dot product **and** whether the `establishes_bound` flag is honest | `tau(d) >= N` only when the threshold is genuinely met |
| `ramsey` | parses the colouring string, re-counts monochromatic `K_k` | `R(k,k) > n` iff the count is zero (any `k >= 3`) |
| `unit_distance` | that the edges are exactly the unit-distance pairs, then the exact chromatic number | plane chromatic number `>= chi` |
| `circulant` | that the sweep covers all `2^(n/2)` circulant colourings, and re-checks every witness | `R(k,k) > n`, or the exhaustive negative statement |
| `ramsey_unsat` | consistency of the declared encoding size against `2 * C(n,k)` plus symmetry clauses; `--deep` re-runs the solver | nothing on its own (see §10) |
| `sat_attempt` | that an inconclusive run is labelled inconclusive and its encoding metadata is right | nothing — it records a failure honestly |
| `unitdist_search` | the recorded graph really is a unit-distance graph with the claimed chromatic number | plane chromatic number `>= chi` |

### 4.3 Positive versus negative results

A *construction* is verified in milliseconds. A *negative* claim is only as good
as its completeness argument, which is why:

* `circulant` certificates must declare a coverage count exactly equal to the
  size of the family (`2^21` for `K42` and `K43`), and `oplab verify --deep`
  re-runs the entire sweep from scratch in CI;
* unsatisfiability claims from the SAT engine are **not** claimed as proofs, since
  no DRAT proof is produced (see §10).

---

### 4.4 The same claims, checked in Lean

The Python verifier is one implementation; [`lean/`](lean/README.md) is a second,
written in a different language with a different arithmetic. `scripts/gen_lean_certs.py`
reads every `certs/*.json` and emits [`lean/Oplab/Certs.lean`](lean/Oplab/Certs.lean),
one theorem per claim, which `lake build` then re-checks:

```bash
cd lean && lake build            # 108 theorems, ~7 minutes (two 2^21 sweeps)
make lean                        # same, from the repository root
python scripts/gen_lean_certs.py --check   # CI: the generated file must be fresh
```

| certificate family | Lean statement |
|---|---|
| `ramsey`, `sat` colourings | `monoCount n k <colouring> = <claimed count>` — exact monochromatic-`K_k` count, and for clean colourings also `subsetMonoCount = 0` from an independent subset-enumeration counter |
| `circulant` | `cleanCirculantMasks n k 2^(n/2) = <claimed witness list>` — the exhaustive sweep reproduced, empty list included |
| `sat/k6_k3_sym*` | `cleanMasks 6 3 (2^15) = []`, i.e. `R(3,3) <= 6` by exhaustion, which with the clean `K5` witnesses gives `R(3,3) = 6` with no solver involved |
| `sat` encodings | `edge_vars = C(n,2)`, `subset_clauses = 2*C(n,k)`, `num_clauses >= subset_clauses` |
| `kissing`, `tammes` | `allCosBelow num den <points> = true`: every pairwise cosine is at most the claimed `max_dot` (rounded up at the 9th decimal), plus distinctness and unit norms |
| `attacks/kissing_*` | `cosAtLeast` for the pair that beats `1/2` — the `establishes_bound = false` flag, machine-checked |
| `unit_distance`, `unitdist_search` | `unitEdges` (every stored edge is a unit distance up to `1e-9`) and `chromaticExactly n chi <edges>` |

Two points about honesty. Coordinates from JSON are read as exact integers scaled
by `10^18` and the geometric claims become integer inequalities with a `1e-9`
rounding allowance — nine orders of magnitude above the round-off of the stored
decimals — so the theorems bound the *stored data*, not an idealised point set.
And five theorems (the two `2^21` circulant sweeps, the two `K42`/`K43` tabu
counts and the `3^12` lower-bound colouring search of the Moser drawing) are
proved by `native_decide`, which trusts the Lean compiler rather than the kernel;
each is marked as such in its doc string, and every one of them is recomputed by
the Python verifier as well.

---

---

## 5. The engines

### 5.1 Spherical codes (`sphere.py`)

* Exact constructions: `a2`, `icosahedron`, `d4`, `d5`, `e6`, `e7`, `e8`;
  `project_to_span` reduces `E6`/`E7` to their true dimension (an isometry, so
  the Gram matrix is preserved).
* Search: `search_min_max_dot` runs a threshold descent — a gradient step on
  `sum relu(<x_i,x_j> - t)^2` projected back onto the sphere, aiming just below
  the best value found so far, with restarts and jitter — followed by
  single-point coordinate descent (`polish`) and, when SciPy is installed, an
  L-BFGS-B polish on a log-sum-exp surrogate of the maximum with a ramped `beta`.
* Parallelism: `search_parallel` runs one independent search per process, each
  with the full time budget, and keeps the best configuration together with the
  per-worker values (so a "cluster of results" like `0.5166 x 2, 0.5195, 0.5229`
  is visible in the certificate rather than hidden).

### 5.2 Ramsey colourings (`ramsey.py`)

* Representation: red adjacency as Python integer bitmasks. A colouring is
  serialised as a string of `n(n-1)/2` characters (`'0'` red, `'1'` blue) in
  lexicographic edge order — the format the verifier parses.
* Counting: `count_mono_clique(red, n, k)` counts each clique once at its
  lowest-numbered vertex (`count_cliques` does the recursive work). Tested
  against brute force.
* Delta rule: the monochromatic `K5`s through an edge `uv` of colour `c` are in
  bijection with triangles inside the `c`-coloured common neighbourhood of `u`
  and `v`; flipping `uv` therefore changes the count by
  `triangles(new colour) - triangles(old colour)`. Tested against full
  recomputation on hundreds of random flips.
* Tabu search: candidate moves come from a sample of the monochromatic cliques
  plus random edges, with a tabu tenure and restart-on-stagnation. Roughly 250
  flips/s in pure Python, with ~37 000 exact delta evaluations/s.
* Exhaustive circulant sweep: a *circulant* colouring is translation invariant,
  so (i) it is determined by its difference set (`2^21` choices for `n = 42` and
  `n = 43`) and (ii) any monochromatic clique can be translated to one through
  vertex 0 — which reduces each test from `C(n,5)` subsets to a triangle count in
  a `~20`-vertex neighbourhood. That is what makes the exhaustive sweep finish in
  seconds rather than hours, and the whole family is additionally re-checked by
  the deep verification.

### 5.3 Unit-distance graphs (`unitdist.py`)

* `moser_spindle()` is built analytically: two 60/120-degree rhombi sharing an
  acute vertex, with the other two acute vertices one unit apart. The derivation
  is in the docstring, and the tests check 7 vertices, 11 edges, chromatic number
  4, and 4-criticality (deleting any edge drops the chromatic number to 3).
* `chromatic_number` is exact: branch and bound with DSATUR ordering, a clique
  lower bound, and pruning `used >= best`.
* `adjacency_from_points` classifies pairs by `|dist - 1| <= tol` and **raises**
  for distances in `(tol, 50*tol]`: a graph whose edges depend on a rounding
  choice is not a certificate.
* `search_unit_distance` grows point sets at unit-circle intersections (70% of
  the time) or at random unit displacements, keeps only samples a verifier will
  agree with, and computes the exact chromatic number on every eighth survivor.

### 5.4 SAT with symmetry breaking (`sat.py`)

The encoding: one Boolean per edge, and for each `k`-subset two clauses of
`k(k-1)/2` literals — "not all red", "not all blue". For `K43`, `k = 5` that is
1 935 727 clauses over 106 108 variables (and 2 176 434 clauses for `K43`), built
in 0.1 s and exportable to DIMACS.

Four layers of symmetry breaking, each with a soundness argument, because a
broken symmetry constraint silently turns a satisfiable instance into a
false unsatisfiable one:

| level | constraint | why it is sound |
|---|---|---|
| 0 | none | baseline |
| 1 | `d(v_0) >= d(v_1) >= ... >= d(v_{n-1})` (red degrees) | sorting a colouring by red degree realises this relabelling |
| 2 | adds `d(v_0) + d(v_{n-1}) >= n - 1` | for a degree-sorted labelling this says "largest red degree >= largest blue degree"; exactly one of a colouring and its complement satisfies it |
| 3 | adds lex-leader `M <=_lex pi(M)` for the first three adjacent transpositions | the lexicographically smallest matrix in an orbit satisfies `M <=_lex pi(M)` for *every* permutation, so any subset of these constraints is sound |

The cardinality constraints are encoded with Sinz sequential counters
(`CNF.at_most`, and `at_least_k` as an at-most on the negations) and the lex
constraint with an exact prefix-equality chain. Both primitives are tested by
enumerating every assignment of the original variables and asking a solver whether
the auxiliary variables can satisfy the constraints — so a polarity slip shows up
as a test failure rather than as a wrong verdict. (It did: see §10.)

The backend is Z3's Boolean engine by default; if a DIMACS solver
(`cadical`, `kissat`, `minisat`, `glucose`, `cryptominisat5`) is on `PATH`, it is
used instead. `oplab sat --dimacs-only` writes the instance for anyone else.

---

## 6. Command line reference

Every command is available both as `oplab <command>` (console script) and as
`python -m oplab.cli <command>`.

### Build exact classical certificates

```bash
oplab build --kind sphere --system e8          --out certs/sphere/e8_kissing.json
oplab build --kind sphere --system e6          --out certs/sphere/e6_kissing.json
oplab build --kind unit-distance --name moser  --out certs/unitdist/moser.json
oplab build --kind unit-distance --name diamond --out certs/unitdist/diamond.json
```

Systems: `a2`, `icosahedron`, `d4`, `d5`, `e6`, `e7`, `e8`. Graphs: `diamond`,
`hexagon`, `moser`.

### Run a search

```bash
# kissing: ask for N points with all pairwise dot products <= 1/2
oplab search --target kissing --dim 5 --n 41 --seconds 60 --workers 16 \
    --out certs/attacks/kissing_d5_n41.json

# Tammes: maximise the minimal angle
oplab search --target tammes --dim 3 --n 15 --seconds 60 --workers 16 \
    --out certs/attacks/tammes_d3_n015.json

# Ramsey tabu search (exact count, heuristic search)
oplab search --target ramsey --n 43 --seconds 150 --seed 2 \
    --out certs/attacks/ramsey_k43_tabu.json

# unit-distance growth, seeded by an edge, the diamond or the Moser spindle
oplab search --target unitdist --n 12 --seconds 60 --start moser \
    --out certs/attacks/unitdist_grow_moser.json
```

`--start-from FILE` (sphere searches) seeds the optimiser with the points of an
existing certificate, which is how one would grow a configuration point by point.

### Sweep a range with reference values

```bash
oplab sweep --dim 3 --n-min 15 --n-max 23 --seconds 45 --workers 16 \
    --out-dir certs/attacks
```

Writes one certificate per `N` plus `sweep_d3_summary.json`, printing the gap
against the published value for each size.

### Exhaustive circulant sweep

```bash
oplab circulant --n 42 --k 5 --workers 16 --out certs/circulant/k42_k5.json
oplab circulant --n 17 --k 4 --workers 1  --out certs/circulant/k17_k4.json
```

If the sweep finds a witness it also writes a `ramsey` certificate for it (so the
bound it establishes is verified independently of the sweep).

### SAT

```bash
oplab sat --n 17 --k 4 --symmetry 3 --seconds 60  --out certs/sat/k17_k4_sym3.json
oplab sat --n 42 --k 5 --symmetry 3 --seconds 300 --out certs/sat/k42_k5_sym3.json
oplab sat --n 43 --k 5 --symmetry 3 --dimacs-only --dimacs dimacs/k43_k5_sym3.cnf
oplab sat --n 42 --k 5 --symmetry 3 --benchmark-ingest
```

A satisfiable run writes a `ramsey` certificate; an unsatisfiable run writes a
`ramsey_unsat` certificate; a run that hits its time budget writes a `sat_attempt`
certificate whose metadata (and whose honesty flag) is still verified.

### Verify and report

```bash
oplab verify certs                       # re-derive every claim
oplab verify certs --write               # also record the verification in the files
oplab verify certs --deep --workers 8    # also re-run the exhaustive sweeps
oplab report --path certs                # markdown table (see docs/certificates.md)
```

Exit status is `1` as soon as one certificate fails, which is what CI relies on.

---

## 7. Quick start and reproduction

```bash
pip install -e ".[dev,opt]"     # numpy, pytest, and optionally scipy for the polish step
python -m pytest tests -q       # ~1 minute, no network
python -m oplab.cli verify certs

bash scripts/run_full.sh        # regenerates every certificate (~20 min on 16 cores)
bash scripts/run_sat.sh         # the SAT campaign (~20 min)
```

`runs/full_run.log` and `runs/sat_run.log` are the raw outputs quoted by
[RESULTS.md](RESULTS.md). The searches are seed-determined but **time-bounded**,
so a re-run on another machine lands on a slightly different local optimum: the
committed certificates, not the numbers you obtain locally, are the record.

---

## 8. Repository layout

```
src/oplab/sphere.py       spherical codes: exact root systems, kissing/Tammes search
src/oplab/ramsey.py       exact monochromatic-clique counter, tabu search, circulant sweep
src/oplab/unitdist.py     unit-distance graphs, exact chromatic number, growth search
src/oplab/sat.py          CNF encoding, sound symmetry breaking, DIMACS, solver backends
src/oplab/verify.py       the independent verifiers (the part that must not be trusted twice)
src/oplab/cli.py          build / search / sweep / circulant / sat / verify / report
src/oplab/references.py   published reference values, each with its source URL
certs/sphere/             exact classical kissing constructions
certs/unitdist/           classical unit-distance graphs
certs/circulant/          exhaustive circulant sweeps
certs/sat/                SAT validation runs and attempts
certs/attacks/            measured searches (including the failures) and sweep summaries
docs/methodology.md       how claims are made checkable, and how they can still be wrong
docs/targets.md           what is open, with sources, and what a win would look like
docs/certificates.md      the table produced by `oplab report --path certs`
scripts/run_full.sh       regenerates the certificates in certs/ (minus the SAT campaign)
scripts/run_sat.sh        the SAT campaign and the DIMACS exports
scripts/gen_lean_certs.py turns certs/*.json into lean/Oplab/Certs.lean
tests/                    57 tests: exactness, brute-force cross-checks, soundness, CLI
lean/                     Lean 4 re-check of every certificate claim (see lean/README.md)
  Oplab/Basic.lean        shared definitions (vectors, edge order, circulant colourings)
  Oplab/Check.lean        hand-written checkers: clique counts, colourings, exact cosine bounds
  Oplab/Certs.lean        GENERATED from certs/*.json, one theorem per claim
```

---

## 9. Continuous integration

`.github/workflows/ci.yml` runs three jobs:

1. **test** — on Python 3.10 and 3.13: install, `pytest tests -q`, then
   `oplab verify certs` (re-deriving every claim in every committed certificate).
2. **deep-verify** — re-runs the exhaustive circulant sweeps from scratch
   (`oplab verify certs/circulant --deep --workers 4`) and compares the witnesses.
3. **lean** — checks that `lean/Oplab/Certs.lean` is up to date with `certs/`
   (`scripts/gen_lean_certs.py --check`), installs the pinned Lean toolchain
   through elan and runs `lake build`, so every Lean theorem is re-proved on the
   upstream runner as well.

No secrets, no network access, no external solver required: the SAT tests are
skipped automatically when Z3 is not installed (`pytest.importorskip`).

---

## 10. Limitations, failure modes and things that cannot be verified

* **Only the circulant sweeps are exhaustive.** Everything else in the repository
  is a heuristic with a seed and a time budget. A gap against a published record
  means "this search did not find it", never "it does not exist".
* **No record was broken.** The Tammes configurations are 0.03°–0.13° short of
  the published values (and those published values are best-known
  configurations, not proved optima — a 0.03° "improvement" would need its own
  careful analysis before being called a record), and no kissing configuration
  with one extra point was found.
* **The circulant result is a statement about a sub-family.** "No circulant
  witness exists" says nothing about the many non-circulant colourings, and
  nothing about the upper bound.
* **Unsatisfiability is not proved.** The SAT engine produces no DRAT proof and
  there is no DRAT checker here, so `ramsey_unsat` certificates are verified only
  for the consistency of their metadata; `--deep` re-runs the solver, which is
  reproducibility, not proof. Do not cite them as theorems.
* **The Python/Z3 SAT path cannot settle `K43`.** Measured: building the Z3
  solver for `K42` requires ingesting 1 935 727 clauses at roughly 4 000
  clauses/s, i.e. about 8 minutes of pure hand-off, after which the engine
  returned `unknown`; the DIMACS export exists precisely so that CaDiCaL or
  Kissat — which ingest orders of magnitude faster — can be pointed at the same
  instance. (A dedicated solver could not be installed here: no C compiler is
  available, so `python-sat` cannot build.)
* **Tolerance discipline.** Configurations are float64 checked at `1e-9`, Tammes
  angles compared at `1e-6` degrees, and ambiguous distances rejected rather than
  guessed.
* **What the Lean layer does *not* remove.** It re-checks finitely many claims;
  the search that *found* the configurations is untouched by it. Five of its 108
  theorems use `native_decide` (compiler-trusted), because the kernel would need
  hours for the two `2^21` circulant sweeps and the `3^12` colouring search;
  every one of those five is also recomputed by the Python verifier, and the two
  circulant sweeps are re-run from scratch by `--deep`. And the geometric statements
  are about the coordinates *as stored* (decimals scaled by `10^18`, `1e-9`
  allowance), not about an idealised point set.
* **Two real bugs were caught by this machinery during development**, which is the
  best argument for it existing:
  1. the exact chromatic-number solver over-reported: it pruned at `best - 1` and
     reused a fresh colour without recording it in the neighbours' saturation
     sets, so it could return the greedy upper bound (it claimed 4 colours for a
     3-colourable graph). The independent backtracking reference in the tests
     exposed it; the certificates that depended on it were regenerated;
  2. a unit-distance certificate recorded its edge set with a looser distance
     tolerance than the verifier, which `oplab verify` caught immediately
     ("recorded edges are not exactly the unit-distance pairs").
  The SAT encoder had the same class of bug: an inverted clause polarity in the
  cardinality counter and a missing backward direction in the lexicographic
  equality chain. Both were found by the brute-force primitive tests rather than
  by trusting a solver verdict — worth remembering the next time a symmetry
  breaking constraint is added.

---

## 11. Publishing this as a GitHub repository

```bash
cd open-problems-lab
git init -b main
git add .
git commit -m "Certificates, verifiers and search harnesses for a few open problems in mathematics"
gh repo create open-problems-lab --public --source=. --push   # or: git remote add origin ... && git push -u origin main
```

Recommended next steps for a public push: add the badges you care about, enable
branch protection on `main` so the CI jobs must pass, and keep the rule of this
repository — any new claim lands with its verifier and with the command that
produced it.

---

## 12. Glossary

| term | meaning here |
|---|---|
| **certificate** | a JSON file whose claims a verifier can recompute from its payload |
| **`establishes`** | the theorem a verifier is willing to derive from a payload, or `null` |
| **deep verify** | verification that re-runs an exhaustive sweep or a solver instead of re-checking data |
| **DIMACS CNF** | the standard text format for SAT instances (`p cnf vars clauses`) |
| **DRAT** | the standard proof format for unsatisfiability; not produced here |
| **DSATUR** | a greedy colouring heuristic used here for ordering and upper bounds |
| **exhaustive** | every element of a finite, fully specified family has been tested |
| **lex-leader** | a symmetry-breaking constraint `M <=_lex pi(M)` for a permutation `pi` |
| **`max_dot`** | the largest pairwise dot product of a configuration; `<= 1/2` for kissing |
| **`mono_k5`** | the number of monochromatic `K5` in a 2-colouring of the edges |
| **Ramsey `R(k,k)`** | least `n` such that every 2-colouring of `K_n` has a monochromatic `K_k` |
| **sound symmetry breaking** | constraints that can only remove solutions equivalent to a kept one |
| **Tammes problem** | maximise the minimal angular separation of `N` points on `S^2` |
| **`tau(d)`** | the kissing number in dimension `d` |
| **unit-distance graph** | a graph drawn in the plane with every edge of length exactly 1 |

---

## 13. Sources for every reference value

All reference numbers live in [`src/oplab/references.py`](src/oplab/references.py),
each next to the URL it came from, and are explained in
[docs/targets.md](docs/targets.md):

* **Kissing bounds and the classical configurations** — Henry Cohn's tables
  (`cohn.mit.edu/kissing-numbers`); dimension 8 exactness: Cohn & Li 2024
  (`arXiv:2411.04916`); dimension 6 upper bound 77: de Laat, Leijenhorst & de
  Muinck Keizer 2024 (`arXiv:2404.18794`).
* **Tammes `S^2`, `N = 15..23`** — N. J. A. Sloane, *Spherical Codes*
  (`neilsloane.com/packings`), described there as putatively optimal.
* **`R(5,5)` bounds** — Exoo 1989 (*J. Graph Theory* 13, 97–98) for
  `R(5,5) >= 43`; Angeltveit & McKay 2024 (`arXiv:2409.15709`) for
  `R(5,5) <= 46`.
* **Chromatic number of the plane** — de Grey 2018 (`arXiv:1804.02385`) for the
  5 lower bound, and Jaan Parts (`arXiv:2011.05658`) for the 509-vertex
  construction.

## Licence

MIT — see [LICENSE](LICENSE).
