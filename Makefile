PYTHON ?= python
WORKERS ?= 8
LAKE ?= lake
GAP ?= gap
# where `make portfolio` leaves the raw JSONL the GAP export writes (gitignored:
# their digests are recorded in data/smallgroups_<n>.json, which is committed)
PORTFOLIO_RAW ?= data/gap

.PHONY: help install test verify verify-deep proof-store cross-check build clean repro report lean lean-certs lean-check cayley cayley-long cayley-anchors cayley-full portfolio replay-bench

help:
	@echo "make install      - editable install with dev + optional dependencies"
	@echo "make test         - run the test suite"
	@echo "make verify       - re-verify every certificate in certs/"
	@echo "make verify-deep  - also re-run the exhaustive circulant sweeps"
	@echo "make proof-store  - fail if a stored trace or its certificate moved off the manifest"
	@echo "make cross-check  - check every stored DRAT trace with the external drat-trim"
	@echo "make build        - regenerate the exact classical certificates"
	@echo "make repro        - full experiment run (hours -> minutes, see scripts/run_full.sh)"
	@echo "make cayley       - search the construction space: every group of order n, 300 s each"
	@echo "make cayley-long  - the same groups the 300 s round could not decide, one hour each"
	@echo "make portfolio    - export every group of order 96 and 128 from GAP's SmallGroups library"
	@echo "make cayley-full  - screen the complete portfolio, 20 s per group, 20 s is a screen not a proof"
	@echo "make replay-bench - time both replayers (in-repo and drat-trim) on every stored trace"
	@echo "make cayley-anchors - decide one non-cyclic group per anchor, with DRAT traces"
	@echo "make report       - markdown table of certificates"
	@echo "make lean         - build the Lean layer (re-checks every claim)"
	@echo "make lean-certs   - regenerate lean/Oplab/Certs.lean from certs/"
	@echo "make lean-check   - fail if lean/Oplab/Certs.lean is stale"
	@echo "make clean        - remove caches"

install:
	$(PYTHON) -m pip install -e ".[dev,opt]"

test:
	PYTHONPATH=src $(PYTHON) -m pytest tests -q

verify:
	PYTHONPATH=src $(PYTHON) -m oplab.cli verify certs

verify-deep:
	PYTHONPATH=src $(PYTHON) -m oplab.cli verify certs --deep --workers $(WORKERS)

# What the stores are supposed to contain.  A trace that is edited, dropped or
# quietly regenerated (with a freshly re-solved certificate to match) agrees with
# itself, so nothing else here would notice; the manifests are committed, so this
# target turns that into a failure unless the change is written down on purpose.
# One manifest per store: the circulant sub-family, and the group colourings.
proof-store:
	$(PYTHON) scripts/proof_manifest.py --check
	$(PYTHON) scripts/proof_manifest.py --certs certs/cayley --check

# The second opinion on the stored traces: drat-trim shares no code with
# oplab.drat, so it is the check that keeps a bug here from being permanent.
# Needs drat-trim on PATH (CI builds it from pinned commit scripts/drat-trim.pin,
# and hashes the source it compiled: `--source PATH --require-pin` does that here).
cross-check:
	$(PYTHON) scripts/drat_trim_check.py

build:
	PYTHONPATH=src bash -c 'for s in a2 icosahedron d4 d5 e6 e7 e8; do \
	  $(PYTHON) -m oplab.cli build --kind sphere --system $$s --out certs/sphere/$${s}_kissing.json; done'
	PYTHONPATH=src bash -c 'for g in diamond hexagon moser; do \
	  $(PYTHON) -m oplab.cli build --kind unit-distance --name $$g --out certs/unitdist/$$g.json; done'

repro:
	WORKERS=$(WORKERS) bash scripts/run_full.sh

report:
	PYTHONPATH=src $(PYTHON) -m oplab.cli report --path certs

# The construction space, at the sizes that are still open.  ~35 minutes on 12 cores
# at the default budget; a witness would be stored as a `cayley_multicolour`
# certificate, and only after `verify` has accepted it (scripts/cayley_hunt.py).
# Adding `--proof-dir certs/cayley/proofs --cnf-dir dimacs` also stores the DRAT
# trace of every group the solver *decides*, replayed by `oplab.drat` first, so an
# `unsat` row becomes a theorem about that group instead of a verdict.
cayley:
	PYTHONPATH=src $(PYTHON) scripts/cayley_hunt.py 96:3,3,3,4 128:4,4,4 97:3,3,3,4 \
	  538:3,3,3,3,3,3 161:3,3,3,3,3 --seconds 300 --workers $(WORKERS) \
	  --json runs/cayley_sweep.json --cert-dir certs/cayley

# The rows the 300 s round left open, given an hour each: the three groups of
# order 128 and the eighteen of order 96.  A later round is folded into the sweep
# with scripts/sweep_merge.py, which keeps the superseded rows as history instead
# of editing them away — so "300 s said nothing, 3600 s decided it" is a visible
# diff and not a rewritten row.
#
# `--proof-dir`/`--cnf-dir` are deliberately absent: a trace from a refutation
# that took an hour is hundreds of megabytes and days of Python replay, which is
# not what a committed store can hold.  See `make replay-bench` for the measured
# envelope and RESULTS.md for what that rules out.
portfolio:
	@echo "exporting every group of order 96 (231) and 128 (2328) from GAP's SmallGroups library"
	mkdir -p $(PORTFOLIO_RAW)
	$(GAP) -q -b -c 'order := 96;; out := "$(PORTFOLIO_RAW)/smallgroups_96.jsonl"; Read("scripts/gap_export_smallgroups.g"); QUIT;'
	( $(GAP) -q -b -c 'order := 128;; first_id := 1;; last_id := 582;; out := "$(PORTFOLIO_RAW)/smallgroups_128_1.jsonl"; Read("scripts/gap_export_smallgroups.g"); QUIT;' & \
	  $(GAP) -q -b -c 'order := 128;; first_id := 583;; last_id := 1164;; out := "$(PORTFOLIO_RAW)/smallgroups_128_583.jsonl"; Read("scripts/gap_export_smallgroups.g"); QUIT;' & \
	  $(GAP) -q -b -c 'order := 128;; first_id := 1165;; last_id := 1746;; out := "$(PORTFOLIO_RAW)/smallgroups_128_1165.jsonl"; Read("scripts/gap_export_smallgroups.g"); QUIT;' & \
	  $(GAP) -q -b -c 'order := 128;; first_id := 1747;; last_id := 2328;; out := "$(PORTFOLIO_RAW)/smallgroups_128_1747.jsonl"; Read("scripts/gap_export_smallgroups.g"); QUIT;' & \
	  wait )
	$(PYTHON) scripts/portfolio_build.py --jsonl $(PORTFOLIO_RAW)/smallgroups_96.jsonl \
	  --out data/smallgroups_96.json
	$(PYTHON) scripts/portfolio_build.py \
	  --jsonl $(PORTFOLIO_RAW)/smallgroups_128_1.jsonl \
	  --jsonl $(PORTFOLIO_RAW)/smallgroups_128_583.jsonl \
	  --jsonl $(PORTFOLIO_RAW)/smallgroups_128_1165.jsonl \
	  --jsonl $(PORTFOLIO_RAW)/smallgroups_128_1747.jsonl \
	  --out data/smallgroups_128.json

# The screening round over the *complete* portfolio, which is the whole point of
# the export above: every group of order 96, then every group of order 128, one
# budget each.  It is a screening and not a hunt — 20 s will not settle the
# instances the 3600 s round left open — so it is run with `--keep-going`: a
# witness stops a hunt, and here the classification of the other 2 327 groups is
# part of the answer.  The K96 round is what found the witness in
# SmallGroup(96,87); `make cayley` and `make cayley-long` remain the rounds over
# the named families, and the three are folded together by scripts/sweep_merge.py.
#
# `--summary` writes each round as counts plus one row per group, naming the
# portfolio it searched by digest rather than repeating 2 328 generator lists —
# measured: 9.4 MB of rows against 855 kB.  A `sat` row is kept whole, because a
# colouring is an artifact the group does not contain.  What the two rounds say:
# K96 gives 3 witnesses in 519 s, and K128 gives 2 314 refutations, 14 groups still
# open in 893 s and no witness at the record size.
cayley-full:
	PYTHONPATH=src $(PYTHON) scripts/cayley_hunt.py 96:3,3,3,4 \
	  --portfolio data/smallgroups_96.json --seconds 20 --workers $(WORKERS) \
	  --keep-going --summary --json runs/cayley_full_k96.json
	PYTHONPATH=src $(PYTHON) scripts/cayley_hunt.py 128:4,4,4 \
	  --portfolio data/smallgroups_128.json --seconds 20 --workers $(WORKERS) \
	  --keep-going --summary --json runs/cayley_full_k128.json

cayley-long:
	PYTHONPATH=src $(PYTHON) scripts/cayley_hunt.py 128:4,4,4 --group cyclic --group D64 \
	  --group Z2xD32 --seconds 3600 --workers 3 \
	  --json runs/cayley_long_k128_cadical.json
	PYTHONPATH=src $(PYTHON) scripts/cayley_hunt.py 96:3,3,3,4 \
	  --group Z32xZ3 --group Z16xZ3xZ2 --group Z8xZ4xZ3 --group Z8xZ3xZ2xZ2 \
	  --group Z4xZ4xZ3xZ2 --group Z4xZ3xZ2xZ2xZ2 --group Z3xZ2xZ2xZ2xZ2xZ2 \
	  --group D48 --group Z2xD24 --group Z3xD16 --group Z3xDic8 --group Z4xD12 \
	  --group Z6xD8 --group Z8xD6 --group Z8xDic3 --group Z12xD4 --group Z12xDic2 \
	  --group Z16xD3 --seconds 3600 --workers 18 \
	  --json runs/cayley_long_k96.json

# Both replayers, timed on the same CNFs and the same stored traces.  The native
# column needs drat-trim: on PATH, or through the pinned build elsewhere
# (`--drat-trim "wsl -e /home/you/drat-trim/drat-trim" --wsl --source ...`).
replay-bench:
	$(PYTHON) scripts/replay_bench.py --json runs/replay_bench.json

# One group, one certificate: the anchors over the *non-cyclic* groups, with the
# traces that make their `unsat` rows theorems.  Deterministic and quick (seconds).
cayley-anchors:
	PYTHONPATH=src python -m oplab.cli cayley --n 18 --sizes 4,4 --group D9 \
	  --proof certs/cayley/proofs/k18_4x4_D9.bdrat.xz --out certs/cayley/k18_4x4_D9.json
	PYTHONPATH=src python -m oplab.cli cayley --n 18 --sizes 4,4 --group Z3xD3 \
	  --proof certs/cayley/proofs/k18_4x4_Z3xD3.bdrat.xz --out certs/cayley/k18_4x4_Z3xD3.json
	PYTHONPATH=src python -m oplab.cli cayley --n 30 --sizes 3,3,4 --group D15 \
	  --proof certs/cayley/proofs/k30_3x3x4_D15.bdrat.xz --out certs/cayley/k30_3x3x4_D15.json
	PYTHONPATH=src python -m oplab.cli cayley --n 6 --sizes 3,3 --group D3 \
	  --out certs/cayley/k6_3x3_D3.json

lean: lean-certs
	cd lean && $(LAKE) build

lean-certs:
	$(PYTHON) scripts/gen_lean_certs.py

lean-check:
	$(PYTHON) scripts/gen_lean_certs.py --check

clean:
	find . -name '__pycache__' -type d -prune -exec rm -rf {} +
	rm -rf .pytest_cache *.egg-info build dist
	rm -rf lean/.lake
