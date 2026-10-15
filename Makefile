PYTHON ?= python
WORKERS ?= 8
LAKE ?= lake

.PHONY: help install test verify verify-deep build clean repro report lean lean-certs lean-check

help:
	@echo "make install      - editable install with dev + optional dependencies"
	@echo "make test         - run the test suite"
	@echo "make verify       - re-verify every certificate in certs/"
	@echo "make verify-deep  - also re-run the exhaustive circulant sweeps"
	@echo "make build        - regenerate the exact classical certificates"
	@echo "make repro        - full experiment run (hours -> minutes, see scripts/run_full.sh)"
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

build:
	PYTHONPATH=src bash -c 'for s in a2 icosahedron d4 d5 e6 e7 e8; do \
	  $(PYTHON) -m oplab.cli build --kind sphere --system $$s --out certs/sphere/$${s}_kissing.json; done'
	PYTHONPATH=src bash -c 'for g in diamond hexagon moser; do \
	  $(PYTHON) -m oplab.cli build --kind unit-distance --name $$g --out certs/unitdist/$$g.json; done'

repro:
	WORKERS=$(WORKERS) bash scripts/run_full.sh

report:
	PYTHONPATH=src $(PYTHON) -m oplab.cli report --path certs

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
