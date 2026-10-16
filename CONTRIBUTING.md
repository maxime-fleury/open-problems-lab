# Contributing

The repository has three hard rules and the habits that go with them.

**Hard rule: no unverifiable claim.** Any number that appears in a certificate
must be recomputable by `oplab.verify` from the payload alone, within the
tolerances documented in [docs/methodology.md](docs/methodology.md). If you add
a new kind of claim, add its verifier in the same pull request, and wire the
certificate into `scripts/run_full.sh` so it is regenerated and re-checked
forever.

**Hard rule, proof-carrying rows: two checkers, one pinned.** A stored DRAT trace
is checked by `oplab.drat` (this repository's own ~300-line checker) *and* by the
external `drat-trim` — see `scripts/drat_trim_check.py`, which rebuilds each CNF
from its certificate, and the `drat-trim` CI job. When you add or regenerate a
trace, run both: the point of the second one is that it shares no code, and
therefore no bug, with the first. The checker itself is pinned, twice over, in
`scripts/drat-trim.pin`: the CI job checks out the commit it names and the script
refuses to report a verdict for a `drat-trim.c` whose sha256 is not the pinned
one. Moving that pin is a decision — re-run the cross-check over the whole store,
explain why in the pull request, and change the file in the same commit.

**Hard rule, pinned store.** A stored trace is pinned by a `MANIFEST.txt`, checked
in beside it and holding both the sha256 of the canonical proof text and the sha256
of the bytes on disk.  There is one per store, because a manifest only speaks for
its own directory: `certs/circulant_multicolour/MANIFEST.txt` (the circulant rows)
and `certs/cayley/MANIFEST.txt` (the translation-invariant rows over a group).  The
certificates agree with each other by construction, so a *regeneration* — a new
trace, a new certificate, digests that match — would otherwise pass every check
in the repository while replacing the artifact that was reviewed.  The manifest is
what turns that into a failure: after intentionally re-solving, run
`python scripts/proof_manifest.py --certs DIR --write` and commit the diff, so the
change in the store is visible in review.  `make proof-store` (and CI) run both
checks.

**Hard rule, imported data is checked, never trusted.**  A group that comes from
*somewhere else* — today, every group of order 96 or 128 out of GAP's SmallGroups
library (`make portfolio`, `data/smallgroups_<n>.json`) — is stored as the
generators of a faithful permutation representation, and everything the repository
says about it is derived here: `oplab.cayley.load_portfolio` closes the generators
into a multiplication table, refuses a closure whose order is not the one declared,
and re-counts the invariants the export declares (element orders, conjugacy-class
structure, centre, derived subgroup, exponent, abelianity) from that table.  The
`id` in a certificate is provenance — which entry of the library it is — and the
count and the labels are the library's claim; the group is the table.  If you add
an import of this kind, the same split applies: the builder (`scripts/portfolio_build.py`)
must refuse a row it cannot rebuild, must refuse parts that do not tile the ids
exactly once, and the loader must re-check on every load — a file that is read once
and trusted afterwards is a file that can rot.

**Hard rule, a longer round supersedes rather than overwrites.** Giving the same
instances a bigger budget is the normal way forward here, and the earlier attempt
is part of what was measured. Keep the new rows in their own `runs/*.json` file
and fold them in with `scripts/sweep_merge.py` (`make cayley-long` is the one
that round is made of today): the frontier takes the new row and the row it
replaced moves to `superseded`, so "300 s told nothing, 3600 s decided it" is one
diff with both halves still quotable. The prose about the round — `what`,
`produced_by`, `reading` in the sweep — is updated by hand, because the script
only recomputes the counts. A row from an engine that reports no *decision*, such
as the repair search, which hunts witnesses, is not merged at all: it stays in its
own file and is quoted as an attempt.

**Soft rule: publish the failures.** A search that did not improve anything is
still a result if it is measured. Record the best value found, the seeds, the
number of samples, and the time budget; write it as a `*_search` certificate and
quote it in `RESULTS.md`. Do not delete a failed run because a later one looks
better.

**Soft rule: measure before storing a trace.** The store is bounded by bytes,
not by the clock. The committed traces run 7.7 bytes per step (`K50`: 4.98 MB for
642 728 steps), and `scripts/replay_bench.py` (`make replay-bench`) times both
replayers on them: the in-repo checker at about a thousand steps a second, the
pinned `drat-trim` at roughly twenty-five times that. A refutation carried by an
hour of search is hundreds of megabytes, so its trace belongs outside the
repository, cited by its digests — not in a directory that is committed.

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
python scripts/proof_manifest.py --check   # the store is still the pinned one
python -m oplab.cli verify certs --deep --workers 4
python scripts/gen_lean_certs.py --check
python scripts/drat_trim_check.py          # needs drat-trim on PATH; CI builds it
cd lean && lake build
```

The cross-check is the one check whose tool is not in this repository: build
`drat-trim` from the commit in `scripts/drat-trim.pin`
(`gcc -O2 drat-trim.c -o drat-trim`) and put it on `PATH`, or point at a build
elsewhere with `--drat-trim PATH`. Add `--source PATH/TO/drat-trim.c --require-pin`
to check that it really is the pinned source, as CI does; without `--source` the
script looks for `drat-trim.c` next to the binary. `tests/test_drat_trim.py` runs
it when it is available there and skips when it is not, and
`tests/test_proof_store.py` covers the pin and the manifest without needing the
checker at all. On Windows the checker often lives inside WSL, and then the
command has to be a binary with the file arguments appended —
`--drat-trim 'wsl -e /home/you/drat-trim/drat-trim' --wsl` (with
`OPLAB_DRAT_TRIM="wsl -e /home/you/drat-trim/drat-trim" OPLAB_DRAT_TRIM_WSL=1` for
the test module). A `wsl -e bash -lc "cd ~/drat-trim && ./drat-trim"` form does
not work: bash takes the appended paths as `$0`, `$1`, … and the checker is then
started with no arguments. Passing a WSL-side path through Git Bash also needs
`MSYS_NO_PATHCONV=1`, otherwise `/home/you/...` is rewritten into a Windows path
that exists on neither side — and Git Bash converts the same value when it is in
`OPLAB_DRAT_TRIM_SOURCE`, so prefix that export too:

```bash
MSYS_NO_PATHCONV=1 OPLAB_DRAT_TRIM_SOURCE=/home/you/drat-trim/drat-trim.c \
  OPLAB_DRAT_TRIM="wsl -e /home/you/drat-trim/drat-trim" OPLAB_DRAT_TRIM_WSL=1 \
  python -m pytest tests/test_proof_store.py tests/test_drat_trim.py -q
```
