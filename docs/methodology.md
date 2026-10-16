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
| `cayley_multicolour` | the group is rebuilt from its family/parameters and checked against the axioms, the stored table is checked against the rebuilt one, then the classes, the clique groups and the encoding size are recomputed, the per-class assignment is expanded to all `C(n,2)` edges and re-counted; `obstructed`: the `3 ∣ n` argument over a group; `unsat`: the encoding size **and the replayed DRAT trace**, against this group's CNF | `R(s_1, …, s_k) > n` over that group, the arithmetic obstruction, or *no translation-invariant colouring over that group is clean* (proof-carrying) |

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

## 6. Reproducing and extending

```bash
pip install -e ".[dev,opt]"      # numpy + pytest + scipy (optional polish)
python -m pytest tests -q
python -m oplab.cli verify certs --deep --workers 8
bash scripts/run_full.sh          # regenerates every certificate in certs/
```

To add a target: add a builder or search to a module, add a branch to
`verify.VERIFIERS` that recomputes the claim, add the certificate-producing
command to `scripts/run_full.sh`, and let CI re-verify it forever.
