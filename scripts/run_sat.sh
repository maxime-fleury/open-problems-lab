#!/usr/bin/env bash
# SAT campaign: the replacement for the pure tabu search on the Ramsey targets.
#
#   bash scripts/run_sat.sh                      # ~25 minutes
#   SHORT_BUDGET=120 bash scripts/run_sat.sh     # slower, more thorough
#
# What it produces:
#   * a symmetry-breaking ablation on cases whose answer is known
#     (K6/k=3 unsat, K17/k=4 sat, K18/k=4 unsat);
#   * where the solver stops finding colourings on the satisfiable side of k=5;
#   * measured encoding/ingestion costs for K42 and K43, plus DIMACS exports;
#   * time-boxed attempts on K42 and K43 that are recorded as *inconclusive*.
set -euo pipefail

cd "$(dirname "$0")/.."
export PYTHONPATH=src
OUT=certs/sat
SHORT="${SHORT_BUDGET:-60}"
LADDER="${LADDER_BUDGET:-90}"
mkdir -p "$OUT" runs dimacs
LOG=runs/sat_run.log
: > "$LOG"

run () { echo "+ $*" | tee -a "$LOG"; "$@" 2>&1 | tee -a "$LOG"; }

echo "=== 1. symmetry-breaking ablation on solved cases ===" | tee -a "$LOG"
for spec in "5 3 sat" "6 3 unsat" "17 4 sat" "18 4 unsat"; do
  set -- $spec
  for sym in 0 1 2 3; do
    run python -m oplab.cli sat --n "$1" --k "$2" --symmetry "$sym" --seconds "$SHORT" \
        --out "$OUT/k$1_k$2_sym$sym.json"
  done
done

echo "=== 2. satisfiable side of k=5: where does the solver stop finding colourings? ===" | tee -a "$LOG"
for n in 20 25 30; do
  run python -m oplab.cli sat --n "$n" --k 5 --symmetry 3 --seconds "$LADDER" \
      --out "$OUT/k${n}_k5_sym3.json"
done

echo "=== 3. clause-ingestion cost of the open instances ===" | tee -a "$LOG"
for n in 30 35 42 43; do
  run python -m oplab.cli sat --n "$n" --k 5 --symmetry 3 --benchmark-ingest
done

echo "=== 4. DIMACS exports (the portable artifact for CaDiCaL / Kissat) ===" | tee -a "$LOG"
run python -m oplab.cli sat --n 42 --k 5 --symmetry 3 --dimacs dimacs/k42_k5_sym3.cnf --dimacs-only
run python -m oplab.cli sat --n 43 --k 5 --symmetry 3 --dimacs dimacs/k43_k5_sym3.cnf --dimacs-only

echo "=== 5. the open cases, time-boxed ===" | tee -a "$LOG"
run python -m oplab.cli sat --n 42 --k 5 --symmetry 3 --seconds "$LADDER" --out "$OUT/k42_k5_sym3.json"
run python -m oplab.cli sat --n 43 --k 5 --symmetry 3 --seconds "$LADDER" --out "$OUT/k43_k5_sym3.json"

echo "=== 6. verification ===" | tee -a "$LOG"
run python -m oplab.cli verify "$OUT"
