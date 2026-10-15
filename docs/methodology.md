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
  colourings of `K6`.

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
* the cardinality and lexicographic primitives are cross-checked against the
  predicates they encode by enumerating every assignment of the original
  variables and asking a solver whether the auxiliary variables can satisfy the
  constraints.  An inverted polarity does not produce a slightly wrong answer; it
  produces a wrong *theorem*, so the primitives are tested as predicates, not as
  "the solver found something".

`ramsey_unsat` and `sat_attempt` certificates are treated accordingly: the
verifier checks the metadata and the honesty flag, never the verdict, and the
documentation says plainly that no DRAT proof is produced.

## 5. Failure modes we know about

* **Heuristic sampling bias.** `find_mono_k5` enumerates cliques in
  lexicographic order, so the tabu search sees a biased subset of the
  monochromatic cliques. This slows the search; it cannot make it wrong.
* **Local optima.** The sphere searches stop at local optima. A gap against a
  published record means "this search did not find it", never "it does not
  exist".
* **Float64 boundaries for kissing configurations.** A configuration with
  `max_dot = 0.5 + 3e-16` is accepted (tolerance) and reported with its value.
* **Not-yet-verified negatives.** Only `circulant` certificates carry an
  exhaustive negative claim. Nothing else in this repository claims a negative;
  `ramsey_unsat` in particular records a solver's verdict, not a proof.
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
