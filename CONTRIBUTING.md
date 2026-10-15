# Contributing

The repository has one hard rule and one soft one.

**Hard rule: no unverifiable claim.** Any number that appears in a certificate
must be recomputable by `oplab.verify` from the payload alone, within the
tolerances documented in [docs/methodology.md](docs/methodology.md). If you add
a new kind of claim, add its verifier in the same pull request, and wire the
certificate into `scripts/run_full.sh` so it is regenerated and re-checked
forever.

**Soft rule: publish the failures.** A search that did not improve anything is
still a result if it is measured. Record the best value found, the seeds, the
number of samples, and the time budget; write it as a `*_search` certificate and
quote it in `RESULTS.md`. Do not delete a failed run because a later one looks
better.

## Symmetry breaking has its own rule

A symmetry-breaking constraint that is too strong removes *all* solutions of a
satisfiable instance, and the solver then reports `unsat` with no hint that
anything is wrong. So:

* every layer carries a soundness argument in its docstring;
* every new layer is validated on a **satisfiable** instance whose answer is known
  (`K17, k=4` and `K5, k=3` in `tests/test_sat.py`);
* new cardinality or lexicographic primitives are validated as *predicates* by
  enumerating every assignment of the original variables, not by observing that a
  solver returned something.

## Adding a target

1. Add the construction or search function to the relevant module
   (`sphere.py`, `ramsey.py`, `unitdist.py`), or create a new module if the
   problem is new.
2. Add a verifier to `oplab/verify.py` and register it in `VERIFIERS`. The
   verifier must re-derive the claim from the payload, never read `claims`.
3. Add tests: a positive test on a known-good artifact, a negative test that
   tampers with the payload or the claim, and — where a reference value exists —
   a cross-check against an independent brute-force implementation.
4. Add the command to `scripts/run_full.sh`.
5. Document the target in `docs/targets.md`: statement, verified status with a
   source, and what the winning artifact would be.

## Style

* Python 3.10+, `numpy` only (SciPy is optional and always guarded by
  `sphere.has_scipy()`).
* `snake_case` for functions, `CamelCase` only where a name is a proper noun.
  The word "colour"/"colouring" is used in the British spelling throughout the
  mathematics code; that is deliberate, not a typo.
* Every public function gets a docstring that says what is *computed* and, where
  relevant, what can go wrong.
* Keep the searches deterministic given a seed.

## Every new certificate gets regenerated into Lean

The finite claims of `certs/*.json` are mirrored as Lean theorems in
`lean/Oplab/Certs.lean`, which is generated and therefore never edited by hand:

```bash
make lean-certs     # regenerate lean/Oplab/Certs.lean from certs/
make lean           # build the Lean layer (re-proves every claim)
```

If you add or change a certificate, regenerate before committing; CI runs
`python scripts/gen_lean_certs.py --check` and fails on a stale file. If your
certificate claims something the generator does not yet know how to state (a new
`problem` kind), extend `scripts/gen_lean_certs.py` and add the checker it needs
to `lean/Oplab/Check.lean` — a claim that cannot be restated finitely in Lean
should say so in its own doc string.

## Checks before opening a pull request

```bash
python -m pytest tests -q
python -m oplab.cli verify certs --deep --workers 4
python scripts/gen_lean_certs.py --check
cd lean && lake build
```
