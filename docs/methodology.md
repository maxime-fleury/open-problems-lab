# Methodology: how to make a claim about an open problem that holds up

The repository is built on one rule:

> **generation and verification are separate programs that never share state.**

A search may be as heuristic, randomised or desperate as you like, because
nothing it produces is believed. What is believed is what a *verifier* can
re-derive from the raw payload of a certificate, in a few seconds, from scratch.

## 1. Certificates

A certificate is a JSON file with five parts:

```json
{
  "schema_version": 1,
  "problem": "kissing",
  "title": "E8 root system: 240 kissing points in dimension 8",
  "payload": { "dim": 8, "points": [[...], ...] },
  "claims":  { "n_points": 240, "dim": 8, "max_dot": 0.5 },
  "provenance": { "generator": "...", "created": "2026-10-15", "tool": "..." },
  "payload_sha256": "…"
}
```

* `payload` is the *evidence*: coordinates, a colouring string, a point set.
* `claims` are the numbers the search wants to assert. They are never trusted;
  they are compared with what the verifier recomputes.
* `payload_sha256` makes hand-editing detectable: change one coordinate and the
  certificate fails before any mathematics runs.
* `verification` is written *by the verifier* (`oplab verify --write`) and is
  overwritten on every run, so it can never be forged by the search code.

`oplab verify` recomputes, depending on `problem`:

| `problem` | recomputed | establishes |
|---|---|---|
| `kissing` | unit norms; maximum pairwise dot product ≤ 1/2 | `tau(d) >= N` |
| `tammes` | unit norms; minimal angle | a valid configuration of `N` points |
| `spherical_search` | the reported maximum dot, and whether the `establishes_bound` flag is honest | `tau(d) >= N` only when the threshold is actually met |
| `ramsey` | parses the colouring string, re-counts monochromatic `K5` exactly | `R(5,5) > n` iff the count is zero |
| `unit_distance` | that the edges are *exactly* the unit-distance pairs, then computes the chromatic number by exact branch and bound | plane chromatic number `>= chi` |
| `circulant` | that the sweep covers **all** `2^(n/2)` circulant colourings, and re-checks each witness | `R(k,k) > n`, or the negative statement that no circulant witness exists |
| `circulant_multicolour` | `sat`: re-parse the stored colouring, check that it is constant on every difference class of `Z_n`, and re-count each colour's forbidden cliques; `obstructed`: re-derive the `3 ∣ n` arithmetic of the class `n/3`; `unsat`: the encoding size **and the replayed DRAT trace**; `unknown`: the encoding size, recomputed from the cliques themselves | `R(s_1, …, s_k) > n` (a witness), the arithmetic obstruction, or nothing |
| `cayley_multicolour` | the group is rebuilt from its description — a family's parameters, or the permutation generators of an imported library group, closed here — and checked against the stored table and the axioms (for the permutation family the table *is* the multiplication of a closed set of permutations, so the closure is re-derived and compared, and the associated invariants are re-counted on every load); then the classes, the clique groups and the encoding size are recomputed, the per-class assignment is expanded to all `C(n,2)` edges and re-counted; `obstructed`: the `3 ∣ n` argument over a group, with the element of order 3 *found in the table* and the declared triangle required to be that one; `unsat`: the encoding size **and the replayed DRAT trace**, against this group's CNF | `R(s_1, …, s_k) > n` over that group, the arithmetic obstruction, or *no translation-invariant colouring over that group is clean* (proof-carrying) |

A word on the *portfolio* a `cayley_multicolour` row is drawn from, because it is the
part of that kind which is not fully decided by this repository.  Two lists are
involved: the families `oplab.cayley.groups_of_order` builds, which are complete for
the abelian groups and one-per-family otherwise, and the complete list of an order
exported out of the GAP SmallGroups library (`data/smallgroups_<n>.json`, 231 groups
of order 96 and 2 328 of order 128).  In both cases the group a row is about is a
table this repository rebuilt, so every statement *about that group* is checked here;
what is the library's claim, and is quoted as such, is that the list is the
classification — at order 128 the invariant signature the loader recomputes leaves
462 of 1 050 classes holding more than one group, and a shared signature is necessary
but not sufficient for being isomorphic, so the repository does not pretend to have
proved pairwise non-isomorphism.  A screen over the complete portfolio is therefore
two statements at once: "these groups are empty" (ours, per table) and "these are all
the groups of that order" (the library's).  `RESULTS.md` and `docs/targets.md` say
which is which where it matters.

Such a screen is recorded the way a trace is: what the round produced, keyed to what
it read.  `scripts/cayley_hunt.py --summary` writes the counts and one row per group —
the verdict, the encoding size it was reached on, the seconds it took — and names the
portfolio and its sha256 instead of copying thousands of generator lists into the run
file; a `sat` row is the exception and is stored whole, because a colouring is an
artifact the group it lives in does not contain.  Nothing is dropped that `load_portfolio`
does not already hold — and re-check — on the way back in.

The asymmetry is deliberate: a *positive* result (a construction) is verified in
milliseconds, while a *negative* result (an exhaustive sweep) is only as good as
its completeness argument. That is why `circulant` certificates must declare a
coverage count exactly equal to the size of the family, and why `--deep`
re-runs the entire sweep.

## 2. Two kinds of honest certificates

1. **Exact constructions.** Parameters come from integer arithmetic, so the
   numbers are exact up to floating-point representation: root systems
   (`d_roots`, `e8_roots`), the Moser spindle, the diamond. These are the
   certificates that a reader can check with a pocket calculator and that CI
   re-verifies on every push.
2. **Failed searches.** `spherical_search` and `unitdist_search` certificates
   record an attempt *including its failure*: the best value found, the number
   of samples, the seeds. They are verified for the honesty of their flag, not
   for a bound. Publishing the failures is what keeps the repository useful: a
   later run has a measured baseline to beat.
3. **Arithmetic negatives.** A third kind appeared with the multicolour work: a
   negative that is *proved*, not searched. If `3 ∣ n` and every colour forbids a
   triangle, then the class `n/3` of `Z_n` exists and the three edges of
   `{0, n/3, 2n/3}` all lie in it, so the colour that class receives is
   monochromatic on `n/3` triangles — **no** circulant colouring of `K_n` is
   clean, for any number of colours. The verifier recomputes the classes, and the
   Lean layer proves `diffClass n 0 (n/3) = n/3 ∧ …` per instance by `decide`, so     this is the only negative in the repository that needs neither an exhaustive
     sweep nor a solver verdict.  The other *proved* negatives are
     proof-carrying: all nine `unsat` rows of the circulant sub-family store a DRAT
     trace that `oplab.drat` replays — a solver narrowed the problem to a few
     hundred variables, and a 400-line checker settles it — and that the external
     `drat-trim` checks a second time.

## 2b. Every finite claim is restated in Lean

The verifier is itself Python, and a verifier can share a bug with the code that
produced the data (we hit exactly that: see §5). So the finite content of every
certificate is restated in Lean 4 by `scripts/gen_lean_certs.py`, in a different
language with different arithmetic, and re-checked by `lake build`:

* the monochromatic-clique count is stated **twice**, once by a bitmask
  recursion and once by subset enumeration, so a mistake would have to exist in
  two independent implementations;
* geometric claims become exact integer inequalities over the coordinates scaled
  by `10^18`, with an explicit `1e-9` allowance for the rounding of the stored
  decimals — the *statements* never mention a float;
* the exhaustive circulant sweeps are re-run as Lean computations, and the
  `R(3,3) = 6` companion case is proved by exhaustion over all `2^15`
  colourings of `K6`;
* the multicolour witnesses are re-counted one colour at a time by a third
  counter (`multiMonoCount`, a bitmask recursion) and, where the enumeration is
  cheap, by a fourth naive one (`multiSubsetMonoCount`), while the *encoding size*
  claimed by a `circulant_multicolour` certificate is recomputed from the cliques
  themselves by `cliqueClassGroups` instead of being trusted.

What this buys: the trusted base for the finite claims is the Lean kernel (and,
for the four theorems marked `native_decide`, the Lean compiler, which the Python
sweeps independently cross-check). What it does not buy: any statement about the
*search* that produced the data, since the Lean layer only re-checks what the
certificate asserts. See [`lean/README.md`](../lean/README.md) for the full table
and the deliberate non-claims.

## 3. Tolerance discipline

* Configurations are stored as float64 JSON with 15 significant digits and
  checked with tolerance `1e-9`. Every classical construction is valid to
  `~1e-15`, so the tolerance is 6 orders of magnitude of slack — enough for
  platform differences, not enough to hide a wrong configuration.
* `unitdist.adjacency_from_points` refuses to classify a pair whose distance is
  within `1e-11..5e-7` of 1: a graph whose *edges* depend on a rounding choice
  is not a certificate.
* Tammes angles are compared with the published values at `1e-6` degrees, and
  the reported gaps in `RESULTS.md` are quoted to 5 decimals; no stronger claim
  is made than the arithmetic supports.

## 4. What the search code is allowed to be

The searches are ordinary heuristics and are described as such:

* `sphere.search_min_max_dot`: threshold descent (penalty on pairs closer than a
  target) with restarts, single-point coordinate descent, and an optional
  L-BFGS-B polish on a smooth surrogate of the maximum. It returns a *local*
  optimum. Multiple seeds and multiple processes are independent runs, not
  independent evidence.
* `ramsey.tabu_search`: edge-flip tabu search minimising the exact
  monochromatic-`K5` count, with delta evaluation (a flip changes only the
  cliques through the flipped edge). Its output is a *heuristic* statement: a
  non-zero count is not a theorem, and a zero count is only meaningful because
  the verifier re-counts it.
* `unitdist.search_unit_distance`: random growth of point sets by unit-circle
  intersections. It samples; it does not enumerate.
* `ramsey.circulant_search`: the only **exhaustive** search here. It enumerates
  every circulant colouring of `K_n` and exploits translation invariance to test
  only cliques through vertex 0. It is validated in the test suite against two
  facts that are known independently: the 5-cycle witnesses `R(3,3) > 5`, and
  the Paley graph on 17 vertices witnesses `R(4,4) > 17`; on the other side it
  correctly finds no witness at `n = 6` and `n = 18`.
* `multicolour.tabu_search`: the same idea for one forbidden clique size per
  colour, with two engines (exact matrix deltas, and bit-parallel masks that make
  an order of magnitude more moves per second). Measured, and published as a
  failure: it does not even find the *published* witnesses at `K50` (1973) or
  `K29` (1988).
* `multicolour.circulant_solve`: the second **decidable** search. It is *not*
  exhaustive over all colourings — only over the translation-invariant ones —
  but inside that family the question is an exact CNF, so the answer is a verdict
  rather than a local optimum. Its validation ladder is `K5`/`K6` (2 colours),
  `K17`/`K18` (Paley, and `R(4,4) = 18`), `K29`/`K30` (where `R(3,3,4) = 30`
  exactly: a witness at 29, none at 30, both recovered).

## 4b. Symmetry breaking must be proved sound, not assumed

The SAT engine (`oplab.sat`) is the clearest case of a rule that pays for
itself: a symmetry-breaking constraint that removes *all* solutions of a
satisfiable instance turns a SAT instance into a false UNSAT verdict, and the
solver will report it with complete confidence.  So every layer carries an
argument in the docstring, and the test suite checks the *soundness* direction
explicitly:

* `K17` with `k = 4` is satisfiable (`R(4,4) = 18`), so it must come back `sat` at
  every symmetry level, at every symmetry level of every future change;
* `K5` with `k = 3` is satisfiable (12 clean colourings by brute force) and must
  stay satisfiable;
* in the multicolour encoding, the break is proved *equivalent* to its semantics:
  on five small instances every class assignment is enumerated and the clause set
  is satisfiable exactly when the first row grows in restricted order — a break
  that is only *implied* would silently keep symmetric copies, and one that is
  stronger would silently remove solutions;
* the multicolour break is also proved realisable: for valid colourings, brute
  force over all vertex permutations and colour relabellings finds a copy that
  satisfies both the colour break and the vertex-degree break simultaneously;
* the cardinality and lexicographic primitives are cross-checked against the
  predicates they encode by enumerating every assignment of the original
  variables and asking a solver whether the auxiliary variables can satisfy the
  constraints.  An inverted polarity does not produce a slightly wrong answer; it
  produces a wrong *theorem*, so the primitives are tested as predicates, not as
  "the solver found something".

`ramsey_unsat` and `sat_attempt` certificates are treated accordingly: the
verifier checks the metadata and the honesty flag, never the verdict, and the
documentation says plainly that no DRAT proof is produced for them.

The multicolour `unsat` rows are the exception, and the reason there are two proof
jobs in CI: nine circulant ones and three over a *group*
(`certs/cayley` — `D9`, `Z3xD3` at `K18`, `D15` at `K30`) store the solver's DRAT
trace next to the certificate, and [`oplab/drat.py`](../src/oplab/drat.py) — about
400 lines of RUP/RAT/deletion checking, no solver — replays it against the
encoding rebuilt from `(n, sizes)`, or, for the group rows, from the group
description: the two encodings differ clause by clause and a trace only fits the
family it was produced for. A trace is only stored after that replay has accepted it, and
the certificate records the digest of the canonical text, the sha256 of the bytes
on disk, the container, the step counts and how long the replay took.  The trace
itself is stored as **binary DRAT** (`name.bdrat.xz`: the `-i` encoding
`drat-trim` reads natively, under xz) — the same proof at about an eighth of its
ASCII size, and what the external checker is handed unchanged; the digest is the
sha256 of the canonical text, so it does not move when the container does.
A propagation that visits a clause only when one of its two watched literals
becomes false is what makes the nine replays cost 0.0 s to 694 s instead of hours;
every verification re-checks the digest, the trace itself is replayed when its
recorded cost is under 45 s, and `--deep` replays all nine (the two heaviest are
`K50`, 694 s, and `K55`, 80 s — that is why a plain `verify` only digests them).

A checker that writes a trace and then re-reads it with its own code proves
nothing on its own, so the stored traces are checked a second time by
[`scripts/drat_trim_check.py`](../scripts/drat_trim_check.py), which rebuilds
each CNF from its certificate and hands the pair to the external `drat-trim`
(Marijn Heule's checker, the reference implementation of the format, built at a
pinned commit by the CI job `drat-trim`). All nine verify there in about ten
seconds, including the two rows the Python replay leaves to `--deep`, and the
tampering test whose forged digest defeats the certificate's own sha256 check is
refused by `drat-trim` alone — which is the point of having it.  That checker is
pinned in `scripts/drat-trim.pin` (commit *and* the sha256 of `drat-trim.c`), and
the script refuses to report a verdict for any other source, so "verified by
drat-trim" names one specific program.

**A valid proof can still be the wrong one.**  Every check above is internal to the
certificate: the certificate records a digest, the trace matches it, both agree
tomorrow as well.  Nothing in that loop notices a *consistent* replacement —
re-solve the instance, get a different trace, write a fresh certificate with fresh
digests — and the reviewed artifact would be gone with every check still green.
A `MANIFEST.txt` per store (checked in, one line per stored trace, with the sha256
of the canonical text and of the bytes on disk, plus steps and size) closes that:
`scripts/proof_manifest.py --check` compares manifest, certificates and disk three
ways and fails by name on drift, and `--write` rewrites the manifest, so an
intentional regeneration shows up as a diff in review.  There are two of them
because there are two stores — `certs/circulant_multicolour/MANIFEST.txt` and
`certs/cayley/MANIFEST.txt` — and a manifest only speaks for its own directory.
`make proof-store` runs both checks, and so do CI and
`tests/test_proof_store.py`.

## 5. Failure modes we know about

* **Heuristic sampling bias.** `find_mono_k5` enumerates cliques in
  lexicographic order, so the tabu search sees a biased subset of the
  monochromatic cliques. This slows the search; it cannot make it wrong.
* **Local optima.** The sphere searches stop at local optima. A gap against a
  published record means "this search did not find it", never "it does not
  exist".
* **Float64 boundaries for kissing configurations.** A configuration with
  `max_dot = 0.5 + 3e-16` is accepted (tolerance) and reported with its value.
* **Negatives of three different strengths.** `circulant` certificates carry an
  exhaustive negative claim; `circulant_multicolour` ones carry an arithmetic one
  (`3 ∣ n`), and all nine `unsat` rows there carry a DRAT trace that
  `oplab verify --deep` replays *and* that the `drat-trim` job cross-checks with
  an unrelated implementation. The three `unsat` rows of `certs/cayley` do the
  same over a **group**, which is a narrower statement — no bare verdicts are
  stored by that kind at all — and the same `--deep`/`drat-trim` pair judges them.
  The `ramsey_unsat` verdicts and the SAT engine
  produce no DRAT trace at all, so they are verdicts, not theorems; the two
  heaviest traces (`K50`, `K55`) are re-checked by digest in a plain `verify` and
  replayed by `--deep` and by `drat-trim`.
* **A decidable sub-family is still a sub-family.** "No *circulant* witness" is
  compatible with a witness existing (and it does, at `K50`, `K29`, `K35`, `K44`).
  The multicolour certificates say so in their own titles.
* **Symmetry breaking that is not re-tested.** If you add a layer, add a
  satisfiable instance to the soundness tests in the same commit — see §4b.

## 6. External engines: the repaired Kissat, and cube-and-conquer

Two jobs are done by a binary rather than by a Python binding, and the revisions
are pinned in [`docs/tools.pin`](tools.pin).  `oplab.tools` finds them — the
environment variable first (a whole command line, so a native build, a wrapper or
`wsl -e …` all name one), then the name on `PATH`, then a from-source build at
`$HOME/kissat/build/kissat` or `$HOME/march-cu/march_cu` inside WSL — and
`oplab solvers` reports which implementation answered.

### Why a binary: the bundled Kissat wheel is broken here, and not only by crashing

`python-sat` ships Kissat 4.0.4 inside `pysolvers.cp314-win_amd64.pyd`.  On this
platform that binding answers the first trivial instances and then fails, and the
second failure is the one that matters:

| instance | `cadical195` (wheel) | `kissat404` (wheel) | `kissat404` (binary) |
|---|---|---|---|
| `[[1]]` | `sat` | `sat` | `sat` |
| `[[1], [2]]` | `sat` | `sat` | `sat` |
| `[[1, 2], [-1]]` | `sat` | **access violation**, exit 3221225477 | `sat` |
| `[[1], [-1]]` | `unsat` | **access violation** | `unsat` |
| `[[1, 2], [-1, 2], [1, -2], [-1, -2]]` | `unsat` | **`sat`**, with a model that satisfies no clause | `unsat` |

A crash is visible; a `sat` that satisfies nothing is visible only once something
re-checks the model.  Nothing in Python repairs this — the fault is inside the
compiled binding — so version 4.0.4 is built from upstream and driven as a process
(`oplab.multicolour.KissatBinary`).  `_solver_class` resolves the name to one
implementation or the other, `solver_backing` says which, and every probe row
carries it, because a verdict that does not say which of two same-named engines
produced it cannot be reproduced.

The adapter refuses three things on purpose:

* `unsat` without the solver's own `s UNSATISFIABLE` — a signal, an empty output or
  a parse error is `None` (unknown) with the reason kept in `note`, which is
  exactly the case that used to be filed as a verdict;
* a model that does not satisfy the clauses it was given: `sat` is not taken on the
  solver's word, so an interface bug cannot invent a witness;
* `with_proof=True` (and `get_proof`): Kissat emits no DRAT trace, so a
  proof-carrying row has to come from an engine that does (CaDiCaL).

### cube-and-conquer: a partition, then a verdict per part

A CDCL solver on the frontier instances spends a long budget and returns `unknown`,
not because the search is hard everywhere but because the *top* of the search tree
is unguided.  `scripts/cube_conquer.py` replaces that top with an explicit
look-ahead partition (`march_cu`), then runs one process per leaf, in parallel,
with a per-leaf budget — the boundary a wheel cannot give you, since a solver holds
the interpreter for its whole run:

```bash
python scripts/cube_conquer.py 97:3,3,3,4 --depth 12 --budget 60 --workers 16 \
    --engine kissat404 --engine-backing binary --out runs/cube_k97_d12.json
```

Two independent things decide what the run may claim.

**The cover is checked here, not taken from the cuber's word.**  A leaf list is a
complete decision tree exactly when the trie over the leaves is full: every internal
node branches on one variable, both ways, every leaf is one of the cubes, and the
cubes are all the same length (`cube_cover`).  With that, any assignment agrees with
exactly one leaf path — and a cube file that was filtered, truncated, hand-written
or is simply the *undecided* leaves of another run is reported as what it is.  That
is why `--cubes` (a resumption) can yield `refuted-fragment` and never
`refuted-cover` unless the list actually closes.

**A witness is decoded and re-counted by the repository's own code.**  A `sat` leaf
is decoded with the instance class and passed to `verify_colouring`; a model that
decodes but is not clean is a failure of the run (`sat-invalid`, exit 1), not a
result.  The driver counts nothing itself.

The verdicts, in the terms the report uses:

| verdict | what it means | exit |
|---|---|---|
| `sat` | a verified colouring was found — for the circulant family a witness is a witness, so it is also a colouring of `K_n` | 0 |
| `refuted-cover` | every leaf refuted **and** the cover closes: that CNF is unsatisfiable *as far as the engine's verdicts go* | 0 |
| `refuted-fragment` | every leaf of an input cube list refuted, where that list is a fragment of a cover | 0 |
| `refuted-by-cuber` | `march_cu` decided the instance itself while cubing (it is a solver too); its model is decoded and re-counted like any other | 0 |
| `incomplete` | some leaf undecided, or the cover does not close: nothing is claimed, and the undecided cubes are written out for a second pass with a larger `--budget` | 2 |

`refuted-cover` is a statement about the leaves' **verdicts**.  It becomes a theorem
only when each leaf's refutation is a replayed trace (CaDiCaL writes DRAT; the
in-repo checker replays it against that leaf's CNF), and the cover check above is
what makes the collection of leaf theorems a theorem about the instance.  Until
then the report says so in its own words, and so do the results.

### Combining passes: the claim no single run can make

A cover that a small budget only half refuted is not a refutation, and the pass
that finishes the job is a *fragment* — so neither report can say what the two did
together.  `--combine` is that step, and it is a check rather than an addition: it
re-reads the reports, re-runs the cover test on the complete cube file, re-reads
every pass's rows **from disk** (not from the summaries), and refuses the claim
unless the cover's leaves are exactly the cubes the passes decided, each one
refuted:

```bash
python scripts/cube_conquer.py 97:3,3,3,4 --combine runs/cube_k97_d12.json \
    runs/cube_k97_d12_pass2.json --out runs/cube_k97_cnc.json
```

Four refusals are worth knowing, because each one is a way a stack of reports can
look like an answer: a leaf no pass decided, a cube a pass decided that is **not** a
leaf of the cover, two passes about different instances (or different encodings of
one), and two passes returning *different verdicts* for one leaf (`conflict`, exit
1).  A budget that ran out is not a disagreement — being superseded is what a
second pass is for — so `unknown` never blocks the claim; only two answers do.
What comes out is the same report shape a run writes, with the passes it was built
from in `sources`, so the claim carries its own evidence.  `K97` at `(3,3,3,4)` is
the worked case: 4 096 leaves at depth 12, 4 000 refuted at 60 s per leaf and the
other 96 at 900 s, accepted by `--combine` as a refutation of that CNF as far as
verdicts go (RESULTS.md §9b).  The claim is committed with the rows it rests on, so
the `proofs` CI job re-reads the two passes the same way and fails if a row, a cube
file or a report stops adding up — the check runs no solver and takes seconds.

### The GPU: a lever for witnesses, not for decisions

The two halves of this repository's work are not the same kind of computation, and the
GPU helps exactly one of them.

**Deciding** — "is this CNF satisfiable" — is CDCL: one lineage of decisions, clause
learning, restarts chosen from conflict history.  It is sequential by nature, there is
no credible GPU port, and the bottleneck is the shape of the search tree rather than
arithmetic throughput.  Every `unknown` in these results came from that engine, and a
card changes none of them: a factor of ten on a problem whose cost doubles per vertex
buys about one size class, and only if the hardness scales that gently.

**Finding a witness** — "produce one clean colouring" — is a different job, and it is
arithmetic: count, for many skeletons at once, how many forbidden cliques are
monochromatic.  That kernel is \(24\) to \(35\) times faster on the card than
vectorised numpy, and, more importantly, it runs thousands of independent skeletons in
flight instead of sixteen.

| instance | CPU (numpy) | GPU | gain |
|---|---|---|---|
| `K51` family 3×`Z_17` (75 classes) | 46–56 k evals/s | 1 130–1 640 k/s | ×24–29 |
| `K50` family 3×`Z_2^4`+2 (190 classes) | 12–17 k/s | 395–605 k/s | ×24–35 |
| `K51` general (1 275 edges, 20 825 triangles) | 9.5–10 k/s | ~200 k/s | ×20 |

The two paths were checked against each other rather than trusted: on 4 096 shared
skeletons the host count and the device count agree on all three instances.  The
timings measure a full recount, which is an upper bound on the cost of the incremental
step the walk actually takes.

`oplab.gputabu` is that walk — TABUCOL batched over a population, each skeleton with
its own tabu list, restarting when it stops improving — and it is explicitly *not* a
solver.  A run that ends with violations left reports `best-effort` and a count; it
never says `unsat`, because a heuristic has no way to know.  A run that reaches zero
expands the class assignment and hands it to `verify_colouring`; anything else is
reported as `sat-invalid`, which is a bug in the module and not a result.

The incremental counter is the part that had to be earned, not assumed.  The step moves
the violation count by the delta of the move just applied, so a delta taken from a move
that was *not* applied — a tabu move with no alternative, in an instance with only two
colours — silently corrupts every number downstream.  The walk therefore recounts from
scratch every `recount_every` steps and reports the disagreements in `recount_drift`;
the tests demand it be zero.  It found two real bugs: the delta of a move that was never
applied, and a gather one element past the end of a row, because a class set shorter
than the widest one is padded with an index `A` did not have a column for.  The second
is invisible on the elementary-abelian instances — in characteristic two a triangle
cannot be isoceles, so nothing is ever padded — and it aborts the device on `Z_17`,
where 96 of 4 708 sets are.

What it measures, honestly, is a ceiling rather than a promise: `K_5` and `K_29`
(two and four colours) are solved in seconds with verified witnesses, `K_44` general
stalls at 68 monochromatic cliques, and `K_50` inside the block-Cayley family — where
Kissat found a witness in 527 s — reaches **2** in ten minutes and stops there.  A
search that cannot close the instance it is calibrated on has not earned a claim about
the one above it.

```bash
pip install -e ".[gpu]"          # torch with CUDA; every other path works without it
python scripts/gpu_tabu.py 51:3,3,3,3 --blocks 3 --group 17 --seconds 1200 \
    --walks 4096 --pick-every 8 --out runs/block/gputabu_k51_b3_z17.json
python scripts/gpu_tabu.py 51:3,3,3,3 --general --seconds 1200
```

### Steering instead of multiplicity: `oplab.anneal`, and the gate

A second search exists because the first one's failure has two readings — the instance
is beyond local search here, or the walk was tuned badly — and one instrument cannot
tell them apart.  `oplab.anneal` runs on a CPU, over the same class-set instances (it
imports `gputabu.Problem`, so it cannot disagree about what a clause is), and changes
the three things a plateau responds to: **weights** on the violated sets, so guided
local search forces the walk off the sets it keeps re-attacking; **Metropolis
acceptance** with a geometric cooling and a reheat on stagnation (kept, measured, and
not the default: at `T` around 0.3 the walk mostly refuses to move); and **Kempe
chains**, which swap two colours on a connected component of the classes carrying them
and so recolour a cluster in one step.

The counter discipline is the same and is what a new move set usually breaks.  A Kempe
swap recounts every set it touches instead of carrying a delta, and single moves are
checked by a full recount every 2 000 steps (`recount_drift`, zero in every run).  One
invariant is asserted rather than assumed: a stored class set never repeats a class,
because the encoder dedupes the class multiset of a clique, so the isoceles triangle
`{x, x+d, x+2d}` of `Z_17` is the two-element set `{d, 2d}` with `set_need = 2`.  A
delta of two there — which is what the multiplicity suggests — is wrong, and the test
pins it.

**The gate is the method, not a formality.**  `scripts/anneal_hunt.py` refuses every
spec except the calibration until a stored pass exists, and the pass is a real one: the
search must rediscover the *known* `K50` witness from a random start, on the same
instance and encoding.  A report for another instance is not a pass, a `sat` whose
verification failed is not a pass, and a missing file is a refusal with exit code 2.
The gate **failed**: four seeds, 120 s, 441–455 k class moves each, best 2–3
monochromatic cliques, flat from the second ten-second report.  So no `K51` run was made
with this tool, and `RESULTS.md` §9e says so instead of reporting a plateau as if it
were a measurement of the family.

**The repair move, and what it has to be trusted to do.**  A walk that is two cliques
from a witness is not short of better single moves; it is short of a coordinated one.
`oplab.anneal.repair` frees the classes of the violated sets plus a random sample of
their neighbours, freezes the rest, and hands the resulting sub-CNF to CaDiCaL.  Two
properties make the result usable rather than merely plausible: every set touched by a
free class appears in the sub-CNF, so **no model can create a violation**, and every set
with no free class is untouched — the repair can only lower the count.  The call is
budgeted (`repair_seconds`, `interrupt()` under the hood) because a neighbourhood that is
nearly the whole instance is nearly the whole search.  The tests check the property on a
perturbed witness, check that a timeout leaves the assignment exactly as it was, and
check that a machine without `python-sat` gets a refusal naming the package rather than
an improvised answer.  Measured on the `K50` plateau it changes nothing (1 207
sub-instances, 0 satisfiable) and costs 45 % of the steps, which is why it is off by
default; `RESULTS.md` §9f has the numbers and the geometry that explains them.

```bash
python scripts/anneal_hunt.py --gate --seconds 120 --seed 0
python scripts/anneal_hunt.py 51:3,3,3,3 --blocks 3 --group 17 --seconds 900  # refused
python scripts/anneal_hunt.py --gate --repair-cap 120 --repair-seconds 5      # with repair
```

## 7. Reproducing and extending

```bash
pip install -e ".[dev,opt]"      # numpy + pytest + scipy (optional polish)
pip install -e ".[solvers]"      # python-sat: the CDCL engines the campaigns drive
python -m pytest tests -q        # engine tests skip without them, they do not fail
python -m oplab.cli verify certs --deep --workers 8
bash scripts/run_full.sh          # regenerates every certificate in certs/

python -m oplab.cli solvers       # which engines answer here, and on what backing
# the two external tools (docs/tools.pin), then a cube-and-conquer run:
export OPLAB_KISSAT="wsl -e /home/me/kissat/build/kissat"
python scripts/cube_conquer.py 97:3,3,3,4 --depth 12 --budget 60 --workers 16
# then the undecided leaves at a larger budget, and both passes read as one claim:
python scripts/cube_conquer.py 97:3,3,3,4 --cubes <the unresolved file> --budget 900
python scripts/cube_conquer.py 97:3,3,3,4 --combine <pass 1 report> <pass 2 report>
```

To add a target: add a builder or search to a module, add a branch to
`verify.VERIFIERS` that recomputes the claim, add the certificate-producing
command to `scripts/run_full.sh`, and let CI re-verify it forever.
