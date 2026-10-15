# Lean layer

A second, independent checker for the certificates in `../certs`.  Every finite
claim a certificate makes is turned into a Lean 4 theorem, so the same claim
`oplab verify` checks with Python is also checked by the Lean kernel — no SAT
solver, no floating point, and no Mathlib in the trusted base.

```bash
cd lean
lake build          # ~8 minutes: the two 2^21 circulant sweeps dominate
```

Toolchain: Lean `v4.35.0` (pinned by `lean-toolchain`), zero dependencies
(`lakefile.toml` declares a single library, `Oplab`).  Building is a plain
`lake build`; `lake exe` is not used.

```
lean/
  lean-toolchain      # pinned toolchain
  lakefile.toml       # single library: Oplab
  Oplab.lean          # library root, imports the three modules below
  Oplab/Basic.lean    # shared definitions: vectors, edge order, circulant colourings
  Oplab/Check.lean    # hand-written checkers (exact, kernel friendly)
  Oplab/Certs.lean    # GENERATED from certs/*.json — do not edit by hand
```

Regenerate `Oplab/Certs.lean` after any certificate changes:

```bash
python scripts/gen_lean_certs.py            # rewrite the file
python scripts/gen_lean_certs.py --check    # exit 1 if it is stale (used by CI)
```

## What is checked, and how

| Certificate family | Lean statement | Trusted base |
| --- | --- | --- |
| `certs/attacks/ramsey_k4?_tabu.json`, `certs/sat/k*` | `monoCount n k <colouring> = <claimed count>`; for clean colourings also `subsetMonoCount n k <colouring> = 0`, a second independent counter | kernel (`decide`) |
| `certs/circulant/k5_k3`, `k6_k3`, `k17_k4`, `k18_k4` | `cleanCirculantMasks n k 2^(n/2) = <claimed witness list>` — the exhaustive sweep, reproduced exactly | kernel (`decide`) |
| `certs/circulant/k42_k5`, `k43_k5` | same, over all `2^21` circulant colourings: the witness list must be empty | compiler (`native_decide`; the kernel would take hours) |
| `certs/sat/k6_k3_sym*.json` | `ramsey_R33_exhaustive : cleanMasks 6 3 (2^15) = []`, i.e. `R(3,3) <= 6` by exhaustion; the clean `K5` witnesses give `R(3,3) > 5`, so `R(3,3) = 6` | kernel (`decide`) |
| `certs/sat/k*` (encoding claims) | `edge_vars = C(n,2)`, `subset_clauses = 2*C(n,k)`, `num_clauses >= subset_clauses`, `num_vars >= edge_vars` | kernel (`decide`) |
| `certs/sphere/*`, `certs/attacks/tammes_*` | `allCosBelow num den <points> = true`: **every** pairwise cosine is at most `max_dot` rounded up at the 9th decimal; plus point count, dimension, pairwise distinctness and `|x|^2 = 1 ± 1e-9` | kernel (`decide`) |
| `certs/attacks/kissing_*` | `cosAtLeast num 10000 <p_i> <p_j> = true` for the pair that beats the threshold, i.e. machine-checked `establishes_bound = false` | kernel (`decide`) |
| `certs/unitdist/*`, `certs/attacks/unitdist_grow_*` | `unitEdges` (every stored edge is a unit distance up to `1e-9`) and `chromaticWitness n chi <colouring> <edges> = true`: an explicit proper `chi`-colouring plus an exhaustive proof that no `chi-1`-colouring exists | kernel (`decide`), except the `3^12` search of the Moser drawing which uses `native_decide` |

Counts: 108 theorems over 53 certificates; 103 are proved by `decide`
(kernel-checked), 5 by `native_decide` — the two `2^21` circulant sweeps, the two
`K42`/`K43` tabu counts and the `3^12` lower-bound colouring search of the Moser
drawing — each marked as such in its doc string.  Every one of the five is
also recomputed by the Python verifier.

## How floating point is handled

The JSON certificates store coordinates as decimal literals.  The generator
reads them exactly (as binary floats), scales them to integers by
`COORD_SCALE = 10^18` and compares them with **exact integer inequalities**:

* cosine bound `cos <= num/den` becomes `den^2 * <x,y>^2 <= num^2 * |x|^2 * |y|^2`
  (equivalent for positive dot products, no square roots, no division);
* unit distance becomes `| |a-b|^2 - s^2 | <= 1e-9 * s^2` with `s = 10^18`;
* unit norm becomes `| |x|^2 - s^2 | <= 1e-9 * s^2`.

The allowance (`1e-9` relative) is nine orders of magnitude above the round-off
of the stored literals (at most a few `1e-15`), and the cosine thresholds are
rounded *up* at the 9th decimal, so the Lean statements are about the stored
data itself.  Nothing in the layer depends on IEEE arithmetic.

## What is deliberately *not* claimed

* No statement is made about the *unrounded* configurations, only about the
  decimals as stored.
* The `K42`/`K43` SAT certificates record `status = unknown`; only their
  encoding sizes are proved.  No bound on `R(5,5)` is claimed there.
* The two `2^21` sweeps are compiler-trusted (`native_decide`).  They are also
  cross-checked against the Python sweep in `oplab.ramsey`, and both the Python
  and the Lean checker are cross-checked against each other on the small cases,
  where the kernel does the work.
* `monoCount` and `subsetMonoCount` are two implementations of the
  monochromatic-clique count; where the certificate is a *clean* colouring and
  there are at most 20000 subsets, both are stated, so a bug would have to be
  present in two different implementations to go unnoticed.
