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

**Five engines and one proof checker.**

| module | what it does | exactness |
|---|---|---|
| [`src/oplab/sphere.py`](src/oplab/sphere.py) | kissing configurations and the Tammes problem on spheres: exact root systems (`D4`, `D5`, `E6`, `E7`, `E8`, icosahedron, hexagon) plus a time-bounded optimiser | constructions are exact up to float64; search is heuristic |
| [`src/oplab/ramsey.py`](src/oplab/ramsey.py) | Ramsey colourings: an exact monochromatic-clique counter, delta-evaluating tabu search, and an **exhaustive** circulant sweep | counter is exact and brute-force tested; circulant sweep is exhaustive |
| [`src/oplab/unitdist.py`](src/oplab/unitdist.py) | unit-distance graphs: analytic Moser spindle and diamond, exact chromatic number by branch and bound, random growth search | chromatic number is exact; search is heuristic |
| [`src/oplab/multicolour.py`](src/oplab/multicolour.py) | multicolour Ramsey: exact per-colour clique counts, delta-evaluating tabu search, a CDCL encoding with a proved-sound colour break, and the **decidable** circulant sub-family | counts are exact and brute-force tested; the circulant encoding is proved equivalent to cleanliness on small instances (exhaustively, in the tests) |
| [`src/oplab/sat.py`](src/oplab/sat.py) | CNF encoding of the Ramsey problem with four layers of *sound* symmetry breaking, DIMACS export, Z3 or external-solver backend | encoding is exact; solver verdicts are only as good as the backend |
| [`src/oplab/drat.py`](src/oplab/drat.py) | a DRAT proof checker (RUP, RAT, deletions) and DIMACS/proof I/O — the trusted base behind every proved `unsat` row | checks a trace against a CNF with no solver involved; about 400 lines, validated on cases whose truth is known independently *and* cross-checked by the external `drat-trim` |

**One verifier.** [`src/oplab/verify.py`](src/oplab/verify.py) re-derives every
claim from the payload of a certificate, and `oplab verify` exits non-zero as
soon as one claim fails. That command is what CI runs.

**One Lean layer.** [`lean/`](lean/README.md) re-checks the same finite claims
in Lean 4 — 174 generated theorems, 140 of them kernel-checked by `decide` —
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
| Multicolour tabu search, `K50`–`K162` | no witness anywhere: the best colourings still carry 140–17 560 monochromatic cliques, **including at `K50` and `K29`, where witnesses are published and known to exist** | 300 s per target, exact counts re-derived by the verifier; raw log in `runs/hunt_driver.log`, machine-readable rows in `runs/hunt_2026-10-15.jsonl` |
| Translation-invariant colourings over *groups* of order `n` | 52 group-runs at the four undecided sizes in 5-minute rounds, then **one hour each on the 21 groups those rounds left open: 33 decided empty, 19 without a verdict, no witness and no bound moved**; `K128` `(4,4,4)` is the sharp case — 24 of its 26 groups are empty, and only the cyclic group and `D64` survive an hour each.  A 20 s screen over the **complete** portfolios (all 231 groups of order 96 and all 2 328 of order 128) then **refutes 2 329 of the 2 559, leaves 227 open, and finds three `K96` witnesses** — `R(3,3,3,4) > 96` inside the invariant space, in groups no named family contains — **and no `K128` witness** | every table checked against the group axioms before it is searched; the five stored rows carry the group as data, a DRAT trace for each `unsat` (replayed by [`drat.py`](src/oplab/drat.py), cross-checked by `drat-trim`) and a Lean theorem that the table *is* a group with the class structure its encoding size comes from; the long round's rows are verdicts, and `runs/cayley_sweep.json` keeps the 5-minute rows they replaced under `superseded`, while the two screens are counts keyed to the portfolio by digest (`runs/cayley_full_k96.json`, `runs/cayley_full_k128.json`) |
| Circulant sub-family of the multicolour frontier | 18 of the 24 instances decided in seconds, per instance: witnesses found (and verified) for `K29`, `K44`, `K54`, `K17`, `K5`; **no** circulant witness for `K18`, `K30`, `K35`, `K36`, `K42`, `K43`, `K45`, `K50`, `K55`; at `3 ∣ n` the all-triangle instances (`K6`, `K51`, `K162`, `K537`) are **obstructed by arithmetic**, no search involved; the other five (`K96`, `K127`, `K128`, `K161`, `K538`) returned `unknown` with the budget spent and are recorded as no claim, and `K97` — one of them until it was partitioned instead of given a longer budget — is **refuted by cube-and-conquer** (§9b), as a run artifact and not as a stored row | witnesses re-counted by the Python verifier *and* by the Lean kernel; the obstruction is `diffClass n 0 (n/3) = n/3 ∧ …` proved per instance by `decide`; **all nine `unsat` rows carry a DRAT trace, replayed by [`drat.py`](src/oplab/drat.py) and cross-checked by `drat-trim`** |

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

### 3.5 Multicolour Ramsey numbers: where a record is actually reachable

`R(3,3,3,3) >= 51` (Chung, 1973), `R(3,4,4) >= 55` and `R(3,3,5) >= 45`
(Kreher–Li–Radziszowski, 1988), `R(3,3,3,3,3) >= 162` (Exoo, 1994),
`R(4,4,4) >= 128` (Hill–Irving, 1982), `R(4,6) >= 36` (Exoo, 2012).  These
lower bounds are decades old, the gaps to the upper bounds are wide, and the
witness is always *one colouring of one graph* — so a colouring of `K_{n+1}` with
no monochromatic forbidden clique would move the published number by one.

This repository attacks that frontier on two fronts, and neither of them claims
a record:

* **Heuristically**, with the delta-evaluating tabu engines of
  [`multicolour.py`](src/oplab/multicolour.py) — measured to *fail*, including on
  instances whose witness is published (`K50`, `K29`).  The numbers are in
  [RESULTS.md](RESULTS.md) §8, with the raw log in `runs/hunt_driver.log` and the
  machine-readable rows in `runs/hunt_2026-10-15.jsonl`.
* **Exactly, inside the circulant sub-family**, where the question
  "is there a translation-invariant witness?" becomes one Boolean variable per
  difference class and colour, one clause per forbidden clique — a few hundred
  variables — and a CDCL solver answers it in seconds
  (`oplab mc-circulant --n 45 --sizes 3,3,5`).
* **Exactly, over every group of the order**, which is the same encoding with the
  difference classes of an arbitrary group in place of `Z_n`: the hand-written
  families of `oplab cayley` grew into the *complete* portfolio — all 231 groups of
  order 96 and all 2 328 of order 128, exported out of the GAP SmallGroups library
  as permutation generators (`make portfolio`, `data/smallgroups_96.json`,
  `data/smallgroups_128.json`) and rebuilt and re-counted here before anything is
  searched.  That widening changed a conclusion.  Over the 22 named groups of order
  96 the answer had been *nine refuted, thirteen open, no witness*; over the 231
  there are **three witnesses** — `SmallGroup(96,87)`, `SmallGroup(96,147)` and
  `SmallGroup(96,230)` carry a translation-invariant colouring of `K96` with
  nothing monochromatic in colours `(3,3,3,4)` — so `R(3,3,3,4) > 96` is realised
  *inside* the invariant construction space at that size, and the earlier sentence
  was true of one portfolio and false of the space
  (`runs/cayley_full_k96.json`; one of the three is stored as a
  [`cayley_multicolour`](certs/cayley) certificate as well).  The same widening
  over the 2 328 groups of order 128 changed nothing, which is the other half of
  the point: a 20 s screen refutes **2 314** of them and leaves **14** open, with no
  witness anywhere, so the named round's *two still open after an hour* survives as
  a statement about the whole library and those 14 become the shortlist
  (`runs/cayley_full_k128.json`).

Two things make the second front worth publishing even when it says no:

1. a `sat` verdict is a *witness*, re-counted exactly, so it is a real bound
   (`R(3,3,4) > 29` and `R(3,4,4) > 54` are recovered this way, matching the
   published values, and `K5`/`K17` recover the 5-cycle and the Paley graph);
2. when `3` divides `n` and every colour forbids a triangle, **no** circulant
   colouring can be clean at all: the class `n/3` is a real difference class and
   the three edges of `{0, n/3, 2n/3}` all lie in it, so whichever colour that
   class receives, that colour has `n/3` monochromatic triangles.  This is
   arithmetic, it is verified per instance by the Lean layer
   (`diffClass n 0 (n/3) = n/3 ∧ …`), and it needs no solver — which is exactly
   why the target sizes `51`, `96`, `162`, `537` cannot be reached from the
   circulant side, and why the honest form of that statement is the obstruction
   rather than a search result.

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
| `circulant_multicolour` | for `sat`: re-expands the stored string, checks it is constant on every difference class and re-counts every forbidden clique; for `obstructed`: re-derives the `3 ∣ n` arithmetic of the class `n/3` with no solver; for `unsat`: the encoding size **and the recorded DRAT trace** (digest always, replay from scratch when the row is cheap, always under `--deep`); for `unknown`: the encoding size, recomputed from the cliques | `R(s_1,…,s_k) > n` (a witness), the arithmetic obstruction, or *no circulant colouring of `K_n` is clean* (proof-carrying) |
| `cayley_multicolour` | **everything**: the group table is rebuilt from the description — a family's parameters, or the permutation generators of a group imported from the SmallGroups library, closed here (automatic associativity, checked order and re-derived invariants) — and checked against the stored table and the group axioms (identity, inverses, associativity); then the inversion classes, the encoding size and the per-class assignment are recomputed, expanded to all `C(n,2)` edges and re-counted by the exact clique counter; `obstructed` re-derives the `3 ∣ n` argument from the element of order 3 **found in the table** (Cauchy says there is one; which element it is depends on how the group was written down) and the declared triangle has to be the one the arithmetic finds; `unsat` requires the recorded DRAT trace and replays it against **this group's** encoding, rebuilt from the description (digest always, replay from scratch when the row is cheap, always under `--deep`) | `R(s_1,…,s_k) > n` (a witness over that group), the arithmetic obstruction, or *no translation-invariant colouring over that group is clean* (proof-carrying); an `unsat` row without a trace is refused, so this kind stores no bare verdicts |
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
  that engine produces no DRAT proof (see §10);
* unsatisfiability inside the circulant sub-family **is** proof-carrying: all
  nine `unsat` rows store the CaDiCaL trace next to the certificate, and
  [`oplab/drat.py`](src/oplab/drat.py) replays it against the encoding it rebuilt
  from `(n, sizes)` — no solver in the loop. A trace is only stored after that
  replay has accepted it, and the certificate records the digest of the canonical
  text, the sha256 of the stored bytes, the container and how long the replay took.
  The same plumbing carries the `cayley_multicolour` rows: three `unsat` ones in
  [`certs/cayley/`](certs/cayley) store a trace that is replayed against the
  encoding of *their* group (rebuilt from the group description, not from
  `(n, sizes)`, because the clauses are a different CNF) — which is also why a
  trace cannot be moved between the two families, or between two groups.
  Every stored trace is then cross-checked by the external `drat-trim`
  (`scripts/drat_trim_check.py`, CI job `drat-trim`, at the commit
  `scripts/drat-trim.pin` names), so the proofs do not rest on this repository's
  own checker alone — and which checker that second opinion comes from is itself
  pinned and checked, not assumed.

---

### 4.4 The same claims, checked in Lean

The Python verifier is one implementation; [`lean/`](lean/README.md) is a second,
written in a different language with a different arithmetic. `scripts/gen_lean_certs.py`
reads every `certs/*.json` and emits [`lean/Oplab/Certs.lean`](lean/Oplab/Certs.lean),
one theorem per claim, which `lake build` then re-checks:

```bash
cd lean && lake build            # 174 theorems, ~10 minutes (two 2^21 sweeps)
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
| `circulant_multicolour` witnesses | `multiMonoCount n [sizes] <colouring> = [0, …, 0]` — one exact count per colour, by the bitmask recursion, and on the cheap instances also by the naive subset enumeration (`multiSubsetMonoCount`) |
| `circulant_multicolour` obstruction | `diffClass n 0 (n/3) = n/3 ∧ diffClass n (n/3) (2n/3) = n/3 ∧ diffClass n 0 (2n/3) = n/3` |
| `circulant_multicolour` encodings | `n/2 * k` variables, and the clause count as `n/2 * (1 + k(k-1)/2)` plus one clause per (colour, clique class set); a second theorem recomputes those class-set counts from the cliques themselves with `cliqueClassGroups`, so the encoding size is a computation rather than a claim |
| `cayley_multicolour` groups | `isCayleyGroup <table> <inverse> = true`: the stored multiplication table really is a group — two-sided identity, inverses, associativity over all `n³` triples — as data, not as a description |
| `cayley_multicolour` class structure | `(cayleyClasses <table> <inverse>).length = k` and `(cayleyCliqueClassGroups <table> <inverse> s).length = <count>`: the class count and the clique-group counts the encoding size is built from, **recomputed** from the table's differences |
| `cayley_multicolour` encodings | `<classes> * k` variables and the clause count as a sum over the (colour, clique class set) groups — kernel arithmetic whose inputs the two theorems above recompute |
| `cayley_multicolour` obstruction | `hasOrderThree <table> = true`: the group really has an element of order 3, whose class then forces a monochromatic triangle in every colour |

Two points about honesty. Coordinates from JSON are read as exact integers scaled
by `10^18` and the geometric claims become integer inequalities with a `1e-9`
rounding allowance — nine orders of magnitude above the round-off of the stored
decimals — so the theorems bound the *stored data*, not an idealised point set.
And 34 theorems (the two `2^21` circulant sweeps, the two `K42`/`K43` tabu
counts, the `3^12` lower-bound colouring search of the Moser drawing, the three
multicolour witness counts, the clique-group recomputations and the group-table
checks of the `cayley_multicolour` rows) are proved by `native_decide`, which
trusts the Lean compiler rather than the kernel (the kernel would need hours for
the sweeps, and it cannot unfold the sorting inside `cliqueClassGroups` at all);
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

### 5.5 Multicolour instances (`multicolour.py`)

`R(s_1, …, s_k)` with one forbidden clique size per colour, so `k` is no longer
fixed at 2 and the engine no longer needs one accumulator per colour pair.

* **Exact verification.** `mono_clique_counts` re-counts the monochromatic
  forbidden cliques of each colour from the stored colouring; it is
  brute-force-tested against subset enumeration, and every search result is
  reported only after it agrees.
* **Two tabu engines.** A matrix engine that evaluates the whole one-edge
  neighbourhood exactly through `A_c @ A_c` (with rank-2 updates), and a
  bit-parallel engine that runs an order of magnitude more moves per second on
  all-triangle instances.  Both are *measured failures* on the frontier: see
  [RESULTS.md](RESULTS.md) §8.
* **CDCL with a sound colour break.** `MulticolourInstance` adds the
  restricted-growth condition on the edges out of vertex 0 — a colour may only be
  used once the next lower one has appeared — with an explicit auxiliary per
  (position, colour) whose definitional clauses make the break *exact* rather
  than merely implied.  The test suite proves the equivalence exhaustively on
  small instances, and separately that every valid colouring has a symmetric copy
  satisfying both this break and the vertex-degree break.
* **The circulant sub-family.** `CirculantInstance` gives one variable per
  (difference class, colour) and one clause per (colour, clique class set): the
  models are exactly the clean translation-invariant colourings, a claim checked
  by exhausting every class assignment on five small instances.  `circulant_solve`
  drives CaDiCaL or Kissat over it and reports `sat` (with a verified witness),
  `unsat`, or `obstructed` — the last being the `3 | n` arithmetic obstruction,
  which is decided without a solver.
* **The group sub-family (`cayley.py`).** A Cayley colouring assigns a colour per
  *inversion class* of a group of order `n`, so it is translation invariant and the
  circulant encoding is the cyclic case.  Every group the module can build
  (`groups_of_order`: all abelian ones, plus dihedral, dicyclic, semidihedral and
  products with a small cyclic factor) is checked against the group axioms before it
  is searched, and `cayley_solve` takes a `--proof` path: the solver writes its DRAT
  trace, `replay_proof` re-checks it against that group's encoding with no solver in
  the loop, and only then is a certificate written — so `unsat` leaves the pipeline
  as a theorem about one group rather than a verdict.

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

### Decide the circulant sub-family of a multicolour instance

```bash
oplab mc-circulant --n 45 --sizes 3,3,5 --proof certs/circulant_multicolour/proofs/k45_3x3x5.bdrat.xz \
    --out certs/circulant_multicolour/k45_3x3x5.json
oplab mc-circulant --n 51 --sizes 3,3,3,3 --out certs/circulant_multicolour/k51_3x3x3x3.json
oplab mc-circulant --n 96 --sizes 3,3,3,4 --dimacs-only --dimacs dimacs/k96_3x3x3x4.cnf
```

`--proof PATH` writes the DRAT trace of an unsatisfiable run and replays it once
before the certificate is written; the certificate then records the trace's path,
its two digests, the step counts and the replay cost.  The name picks the
container: `.bdrat.xz` is binary DRAT (`drat-trim`'s `-i` format) under xz, which
is what the stored traces are — the same proof as the ASCII text at an eighth of
the bytes — while `.drat`, `.drat.gz` and `.bdrat` are the other three
combinations.  The recorded sha256 is always the sha256 of the canonical *text*,
so re-encoding or re-compressing a trace changes no digest.

### Decide the translation-invariant colourings of one group

```bash
oplab cayley --n 18 --list                     # the portfolio of order 18, by name
oplab cayley --n 18 --sizes 4,4 --group D9 \
    --proof certs/cayley/proofs/k18_4x4_D9.bdrat.xz --out certs/cayley/k18_4x4_D9.json
oplab cayley --n 6 --sizes 3,3 --group D3 --out certs/cayley/k6_3x3_D3.json   # obstructed
oplab cayley --n 128 --sizes 4,4,4 --group D64 --dimacs-only --dimacs dimacs/k128_d64.cnf
oplab cayley --n 96 --sizes 3,3,3,4 --portfolio data/smallgroups_96.json \
    --group SmallGroup(96,87) --out certs/cayley/k96_3x3x3x4_SmallGroup_96_87.json
```

The group is named rather than described, so a certificate can be reproduced from
its command line.  `--proof` is the same contract as `mc-circulant --proof`, on a
different encoding: the trace is replayed against the group's own CNF before the
certificate is written, and `unsat` without a trace is refused by the verifier
rather than stored.  `--dimacs-only`/`--dimacs` export the reduced CNF for a
full-strength solver, `make cayley` sweeps the portfolio of named families at the
sizes that are still open, and `--portfolio` picks a group out of an exported
library instead — all 231 groups of order 96, all 2 328 of order 128 — which is
how `make cayley-full` screens the complete list.

### Check a proof

```bash
oplab solvers                                  # which bundled engines actually answer
oplab drat --cert certs/circulant_multicolour/k30_3x3x4.json   # rebuilds the CNF from (n, sizes)
oplab drat --cert certs/cayley/k30_3x3x4_D15.json              # or from the group description
oplab drat --cnf dimacs/k96_3x3x3x4.cnf --proof k96.drat       # or check an explicit pair
```

No solver is started: the checker verifies RUP and RAT steps and deletions against
the CNF and accepts the trace when it derives the empty clause.

`sat` writes a witness that the verifier re-counts and re-expands; `obstructed`
records the arithmetic fact that `3 | n` forces a monochromatic triangle in every
circulant colouring; `unsat` and `unknown` record the encoding and the solver's
verdict (never a theorem — see §10).  `--dimacs-only` (or `--dimacs PATH`
alongside a solve) is the hand-off for the six instances whose encodings
(20 345–149 024 clauses) exceeded the bundled solver's budget: CaDiCaL and Kissat
ingest them from the file where the in-process path does not, and
[`scripts/cube_conquer.py`](scripts/cube_conquer.py) partitions one of those files
into leaves and refutes them in parallel — writing the export itself unless
`--dimacs` names an existing one, and refusing an export whose header is not the
encoding of the instance it was asked to solve.  That is how `K97` at `(3,3,3,4)`
stopped being an `unknown`: 4 096 leaves at depth 12, refuted in two passes
([RESULTS.md](RESULTS.md) §9b).

### Verify and report

```bash
oplab verify certs                       # re-derive every claim (and replay the cheap DRAT traces)
oplab verify certs --write               # also record the verification in the files
oplab verify certs --deep --workers 8    # also re-run the exhaustive sweeps, every trace and every solver
oplab drat --cert certs/circulant_multicolour/k45_3x3x5.json   # replay one stored trace
oplab report --path certs                # markdown table (see docs/certificates.md)
```

Exit status is `1` as soon as one certificate fails, which is what CI relies on.

---

## 7. Quick start and reproduction

```bash
pip install -e ".[dev,opt]"     # numpy, pytest, and optionally scipy for the polish step
python -m pytest tests -q       # ~2 minutes, no network
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
src/oplab/multicolour.py  multicolour counts, tabu engines, CDCL, circulant sub-family decision
src/oplab/verify.py       the independent verifiers (the part that must not be trusted twice)
src/oplab/cli.py          build / search / sweep / circulant / mc-circulant / cayley / sat / verify / report
src/oplab/references.py   published reference values, each with its source URL
certs/sphere/             exact classical kissing constructions
certs/unitdist/           classical unit-distance graphs
certs/circulant/          exhaustive circulant sweeps
certs/circulant_multicolour/  decisions (witness / obstruction / proof-carrying verdict) for the multicolour frontier
certs/cayley/             the same, over *groups* of order n: one row per non-cyclic group, with its traces
certs/sat/                SAT validation runs and attempts
certs/attacks/            measured searches (including the failures) and sweep summaries
docs/methodology.md       how claims are made checkable, and how they can still be wrong
docs/targets.md           what is open, with sources, and what a win would look like
docs/certificates.md      the table produced by `oplab report --path certs`
scripts/run_full.sh       regenerates the certificates in certs/ (minus the SAT campaign and the
                  multicolour tabu hunt, which is scripts/hunt_records.py)
scripts/run_sat.sh        the SAT campaign and the DIMACS exports
scripts/gen_lean_certs.py turns certs/*.json into lean/Oplab/Certs.lean
scripts/proof_manifest.py checks (--check) and rewrites (--write) the pinned list of stored
                  traces of one store (--certs DIR); one manifest per store,
                  certs/circulant_multicolour/MANIFEST.txt and certs/cayley/MANIFEST.txt
scripts/drat-trim.pin     the external checker: commit *and* the sha256 of drat-trim.c
scripts/drat_trim_check.py  cross-checks every stored trace with that checker, rebuilding the CNF
scripts/orbit_probe.py    decides restricted sub-families with two symmetry breaks and measures
                  where each stops helping: the multiplier subgroup (--by-subgroup,
                  21 variables for K128 instead of 192) and the colour-naming order
                  (--canonical, checked against the plain encoding by --compare).
                  No published bound moves; the residual families are the full instances
src/oplab/cayley.py       colourings that are translation invariant over *any* group of order n —
                  the construction space, with the circulant family as the cyclic case
scripts/cayley_hunt.py    searches every group it can build for a witness (CDCL, or a
                  min-conflicts repair with exact incremental counts) and stores what it
                  finds as a `cayley_multicolour` certificate, only after `verify` accepts it;
                  --proof-dir/--cnf-dir also record the DRAT trace of every group the solver
                  decides, replayed before it is stored, and export the reduced CNF.
                  --portfolio swaps the named families for an exported complete list, and
                  --keep-going screens all of it instead of stopping at the first witness;
                  --summary writes such a screen as counts plus one row per group, naming the
                  portfolio by sha256 instead of repeating its generator lists (a `sat` row is
                  kept whole: a colouring is the artifact, the group does not contain it).
                  runs/cayley_full_k96.json is what that round found in 519 s and
                  runs/cayley_full_k128.json what the order-128 one found in 893 s
data/smallgroups_96.json   every group of order 96, from the GAP SmallGroups library:
                  permutation generators plus the invariants GAP computed for them, which
                  `load_portfolio` re-counts from the rebuilt table on every load — the id is
                  provenance, the group is the table (231 groups, 0.32 MB)
data/smallgroups_128.json  the same for all 2 328 groups of order 128 (1050 invariant-signature
                  classes, 462 of them holding more than one group — a signature is necessary
                  and not sufficient for non-isomorphism, and the file says so; 5.61 MB)
scripts/gap_export_smallgroups.g  the GAP program that writes those two files' input:
                  one JSON object per group, `order`/`out` in, `first_id`/`last_id` to split a
                  long export over several processes.  Nothing downstream trusts it
scripts/portfolio_build.py  turns that stream into the two data files: every group closed and
                  re-counted in Python, the parts made to tile the ids exactly once, and a
                  disagreement refused rather than written
scripts/sweep_merge.py    folds a later round of those runs into runs/cayley_sweep.json
                  (the frontier takes the new row, `superseded` keeps the one it replaced,
                  and a repair row is refused because it reports no decision); make cayley-long
                  is the one-hour round over the groups the 5-minute round left open
scripts/replay_bench.py   times both replayers — the in-repo `oplab.drat` and the pinned
                  external `drat-trim` — on every stored trace, so the envelope of what can
                  be replayed before storing is measured rather than assumed (make replay-bench)
tests/                    133 test functions (171 cases): exactness, brute-force cross-checks,
                          soundness of every symmetry break, exhaustive encoder equivalence, CLI,
                          proof-store and checker-pin guards, and the proof plumbing (a trace
                          that is replayed against the encoding its certificate declares,
                          refused when it was produced for another group or family)
lean/                     Lean 4 re-check of every certificate claim (see lean/README.md)
  Oplab/Basic.lean        shared definitions (vectors, edge order, circulant colourings)
  Oplab/Check.lean        hand-written checkers: clique counts, colourings, exact cosine bounds
  Oplab/Certs.lean        GENERATED from certs/*.json, one theorem per claim
```

---

## 9. Continuous integration

`.github/workflows/ci.yml` runs five jobs:

1. **test** — on Python 3.10 and 3.13: install, `pytest tests -q`, then
   `python scripts/proof_manifest.py --check` (the stored traces must still be the
   ones `certs/circulant_multicolour/MANIFEST.txt` pins), then
   `oplab verify certs` (re-deriving every claim in every committed certificate,
   including a replay of every DRAT trace whose recorded cost is under 45 s).
2. **deep-verify** — re-runs the exhaustive circulant sweeps from scratch
   (`oplab verify certs/circulant --deep --workers 4`) and compares the witnesses.
3. **proofs** — replays every stored DRAT trace against the encoding rebuilt from
   the certificate
   (`oplab verify certs/circulant_multicolour --deep --workers 4`), which also
   re-runs each of those solvers; nine traces, about 12 minutes of checking, most
   of it the 642 728-step `K50` trace (694 s here).
4. **drat-trim** — builds [drat-trim](https://github.com/marijnheule/drat-trim)
   at the commit `scripts/drat-trim.pin` names, cross-checks all nine stored traces
   with it (`python scripts/drat_trim_check.py --source /tmp/drat-trim/drat-trim.c
   --require-pin`), rebuilding each CNF from its certificate; about 10 seconds, and
   the only job that does not use this repository's own checker.  The `--source`
   hash is compared against the same pin, so a checker that changed behind the
   pin, a disagreement about a trace, or a pin file with no checker to match it
   each fail the build.
5. **lean** — checks that `lean/Oplab/Certs.lean` is up to date with `certs/`
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
* **Unsatisfiability is proved only where a trace is stored.** `ramsey_unsat`
  certificates (the 2-colour SAT engine) carry no DRAT proof at all, so they are
  verified only for the consistency of their metadata; `--deep` re-runs the
  solver, which is reproducibility, not proof. Do not cite those as theorems.
  The circulant-multicolour `unsat` rows are different — see the next bullet —
  but even there the theorem is relative to the checker, not to a Lean proof.
* **The Python/Z3 SAT path cannot settle `K43`.** Measured: building the Z3
  solver for `K42` requires ingesting 1 935 727 clauses at roughly 4 000
  clauses/s, i.e. about 8 minutes of pure hand-off, after which the engine
  returned `unknown`; the DIMACS export exists so that CaDiCaL or Kissat — which
  ingest orders of magnitude faster — can be pointed at the same instance.
* **The CDCL route is available and was measured.** `python-sat` ships CaDiCaL
  (1.03–3.00) and Kissat (4.04) as *binary wheels*, so no C compiler is needed;
  `multicolour.solve` and `multicolour.circulant_solve` drive them directly.  What
  they do with it is in [RESULTS.md](RESULTS.md): they decide the circulant
  sub-family in seconds and they did **not** decide the 2-colour `K43` instance
  or the multicolour `3 * C(n,2)`-clause instances within 50 minutes — a
  measured negative, not an excuse.
* **The bundled Kissat wheel is broken on Windows, and was replaced by the real
  engine.** `kissat404` dies with an access violation on a two-clause instance
  (`[[1], [-1]]`, `[[1, 2], [-1]]`) and answers `sat` *with a model that satisfies
  nothing* on a four-clause contradiction — a wrong verdict, not just a crash.  A
  binary built from upstream (rel-4.0.4, pinned in `docs/tools.pin`) is driven
  instead, and the name now reports `ok` with `backing binary`:

  ```
  engine       status     seconds  backing  detail
  kissat404    ok           0.859  binary   sat=True unsat=True
  ```

  `oplab.tools` finds it (`OPLAB_KISSAT`, `PATH`, or `~/kissat/build/kissat`
  under WSL) and `solver_backing` keeps the two implementations apart, so no row
  can quietly attribute a verdict to the wrong engine.
* **A partition decides what a single run could not.** `scripts/cube_conquer.py`
  cuts an instance with `march_cu`, checks that the leaf list is a *complete
  decision tree*, refutes the leaves in parallel with a per-leaf budget, and
  decodes and re-counts any witness before believing it.  `--combine` then reads
  several passes back as the one claim they add up to — refusing it unless the
  cover's leaves are exactly the cubes they decided, each one refuted — so a second
  pass over the undecided leaves is a checked conclusion rather than a pair of
  reports.  Measured: **`K97` at `(3,3,3,4)`, 4 096 leaves at depth 12, refuted in
  two passes** (4 000 in 80 minutes at 60 s per leaf, the other 96 at 900 s), after
  a 768 s single run of the same engine had nothing to say about it — so that instance
  is now decided inside the circulant family, as verdicts rather than as a proof
  ([RESULTS.md](RESULTS.md) §9b).  `march_cu` also refutes instances outright while
  cubing, and that verdict (with its model) is reported as what it is.
* **The family the record is written in is now searchable.**  `oplab.blocks` encodes
  block-Cayley colourings — `b` blocks carrying an abelian group, plus free extra
  vertices — checked against its own expansion by exhaustion and equal to the
  circulant family at `b = 1`.  Three blocks of `Z_2^4` plus two extras reproduce the
  published witness size (`R(3,3,3,3) > 50`, SAT in 527 s), a block whose order is
  divisible by 3 is refuted by arithmetic with no solver at all, and the `K51`
  shapes whose blocks avoid a factor of three are undecided: [RESULTS.md](RESULTS.md)
  §9c.  No bound moves.
* **A GPU search for witnesses, with its ceiling measured.**  `oplab.gputabu` runs
  batched tabu over the same instances: 24–35× the counting throughput of vectorised
  numpy and thousands of skeletons in flight.  It is a search and says so — `K5` and
  `K29` come back with verified witnesses in seconds, `K50` inside the family stalls at
  2 monochromatic cliques where Kissat found one in 527 s, and no `best-effort` row is
  ever a refutation.  CDCL gains nothing from the card, and the section measures why.
* **A gated second search, and the gate it fails.**  `oplab.anneal` steers instead of
  multiplying: penalty weights, Metropolis acceptance and Kempe chains, on a CPU, with
  the same recount discipline.  `scripts/anneal_hunt.py` refuses any target until the
  search has rediscovered the *known* `K50` witness from a random start — and it has
  not: four seeds, 440 k class moves each, still 2–3 cliques away.  Two independent
  methods plateauing on a known-satisfiable instance is the useful result, and no `K51`
  run was made: [RESULTS.md](RESULTS.md) §9e.
* **The multicolour frontier was not moved.** 300 s per target on 12 cores left
  140–17 560 monochromatic cliques in the best colourings found, and the general
  engines failed even on `K50` and `K29`, where published witnesses exist.  The
  circulant sub-family, which is decidable, has no witness at any of the target
  sizes (and is arithmetically obstructed at the all-triangle sizes divisible by
  three) — so nothing here raises or lowers any published Ramsey bound.
* **`unsat` inside the circulant sub-family is proof-carrying, and checked
  twice.**  All nine `unsat` rows store a DRAT trace that
  [`drat.py`](src/oplab/drat.py) replays from scratch: `K18` (26 steps, 0.0 s),
  `K30` (1 179, 0.04 s), `K35` (505, 0.8 s), `K36` (260, 0.6 s), `K42` (8 288,
  4.1 s), `K43` (24 749, 8.0 s), `K45` (36 496, 13.0 s) and then the two heavy
  ones — `K55` (173 165, 80 s) and `K50` (642 728 steps, 29.9 MB of text, 12.7 MB
  as binary DRAT, 4.98 MB stored, 694 s).  The traces are stored as binary DRAT
  under xz (`proofs/*.bdrat.xz`, 6.27 MB for the nine, down from 8.0 MB of gzipped
  text) and the digest is over the canonical *text*, so re-encoding or
  re-compressing one changes no recorded digest.  The seven cheap replays run in
  every `oplab verify`; the two heavy ones
  are re-checked by digest there and replayed in full by `--deep` and by the CI
  `proofs` job.  Because a checker that writes a trace and re-reads it proves
  nothing by itself, every stored trace is *also* given to the external
  `drat-trim` — all nine in about 9 seconds, `K50` in 6.4 s — by
  [`scripts/drat_trim_check.py`](scripts/drat_trim_check.py), which rebuilds each
  CNF from its certificate and hands over the stored container unchanged (CI job
  `drat-trim`, at the commit and source hash in `scripts/drat-trim.pin`).  The
  trusted base is therefore two independent checkers plus the encoding rather than
  CaDiCaL,
  and the Python one is validated on cases whose truth does not depend on it
  (`R(3,3) = 6` is proved by exhaustion in Lean, the tampering tests include a
  solver-free instance where both RUP and RAT must fail, and a forged certificate
  whose digest was rewritten, which only `drat-trim` refuses).
* **The one fully proof-free negative is the `3 | n` obstruction.**  It is
  arithmetic, needs no solver and no checker, and is checked by `decide` in Lean.
* **Tolerance discipline.** Configurations are float64 checked at `1e-9`, Tammes
  angles compared at `1e-6` degrees, and ambiguous distances rejected rather than
  guessed.
* **What the Lean layer does *not* remove.** It re-checks finitely many claims;
  the search that *found* the configurations is untouched by it. Thirty-four of
  its 174 theorems use `native_decide` (compiler-trusted), because the kernel
  would need hours for the two `2^21` circulant sweeps, the `3^12` colouring
  search, the `K29`/`K44`/`K54` multicolour witness counts, the clique-group
  recomputations of the larger circulant encodings and the group-table checks of
  the `certs/cayley` rows; every one of them is also
  recomputed by the Python verifier, and the two circulant sweeps are re-run from
  scratch by `--deep`. And the geometric statements
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
| **DRAT** | the standard proof format for unsatisfiability; stored for the circulant `unsat` rows and checked by `oplab drat` (RUP, RAT and deletions) |
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

## How to cite

Citing the repository is the only condition its licence asks for, so here is the
entry a bibliography wants.  It is generated from [CITATION.cff](CITATION.cff),
which is the file to edit: `python scripts/gen_citation.py` rewrites it, and the
test suite fails when the two disagree.

<!-- citation:begin (generated: scripts/gen_citation.py) -->
```bibtex
@software{open-problems-lab,
  author  = {maxime-fleury},
  title   = {{open-problems-lab: reproducible attacks and certificates for open problems in mathematics}},
  year    = {2026},
  version = {0.1.0},
  license = {CC-BY-4.0},
  url     = {https://github.com/maxime-fleury/open-problems-lab},
  note    = {Citing this repository is the only condition its licence asks for; the reference values it compares against are listed in docs/targets.md.}
}
```
<!-- citation:end -->

## Licence

**CC BY 4.0** — see [LICENSE](LICENSE), which is the canonical legal code with its
sha256 in [NOTICE](NOTICE).  Everything is permitted, including commercial use,
modification and redistribution, on one condition: the repository is cited, as
`maxime-fleury/open-problems-lab`.  [CITATION.cff](CITATION.cff) is the
machine-readable form of that citation, and NOTICE is the specification of the
manner of attribution the licence's section 3(a)(1) asks for.
