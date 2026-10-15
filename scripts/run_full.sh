#!/usr/bin/env bash
# Reproduce every certificate committed in certs/.
#
#   bash scripts/run_full.sh            # ~20 minutes on 16 cores
#   WORKERS=4 bash scripts/run_full.sh  # fewer cores, same certificates
#
# Everything printed here is measured; RESULTS.md quotes this run.
set -euo pipefail

cd "$(dirname "$0")/.."
export PYTHONPATH=src
WORKERS="${WORKERS:-16}"
OUT=certs
mkdir -p runs certs/sphere certs/unitdist certs/attacks certs/circulant
LOG=runs/full_run.log
: > "$LOG"

step () { echo -e "\n=== $* ===" | tee -a "$LOG"; }
run () { echo "+ $*" | tee -a "$LOG"; "$@" 2>&1 | tee -a "$LOG"; }

# ---------------------------------------------------------------- exact builds
step "exact classical constructions (verified in CI)"
for system in a2 icosahedron d4 d5 e6 e7 e8; do
  run python -m oplab.cli build --kind sphere --system "$system" \
      --out "$OUT/sphere/${system}_kissing.json"
done
for g in diamond hexagon moser; do
  run python -m oplab.cli build --kind unit-distance --name "$g" \
      --out "$OUT/unitdist/${g}.json"
done

# ------------------------------------------------------- exhaustive circulant
step "exhaustive circulant sweeps (validated on two known Ramsey facts)"
run python -m oplab.cli circulant --n 5  --k 3 --workers 1  --out "$OUT/circulant/k5_k3.json"
run python -m oplab.cli circulant --n 6  --k 3 --workers 1  --out "$OUT/circulant/k6_k3.json"
run python -m oplab.cli circulant --n 17 --k 4 --workers 1  --out "$OUT/circulant/k17_k4.json"
run python -m oplab.cli circulant --n 18 --k 4 --workers 1  --out "$OUT/circulant/k18_k4.json"
run python -m oplab.cli circulant --n 42 --k 5 --workers "$WORKERS" --out "$OUT/circulant/k42_k5.json"
run python -m oplab.cli circulant --n 43 --k 5 --workers "$WORKERS" --out "$OUT/circulant/k43_k5.json"

# ----------------------------------------------------------------- unit-distance
step "unit-distance graph search (random growth by unit-circle intersections)"
run python -m oplab.cli search --target unitdist --n 11 --seconds 45 --start edge \
    --out "$OUT/attacks/unitdist_grow_edge.json"
run python -m oplab.cli search --target unitdist --n 12 --seconds 60 --start moser \
    --out "$OUT/attacks/unitdist_grow_moser.json"

# ----------------------------------------------------------------------- Ramsey
step "tabu search baselines on K42 and K43"
run python -m oplab.cli search --target ramsey --n 42 --seconds 150 --seed 1 \
    --out "$OUT/attacks/ramsey_k42_tabu.json"
run python -m oplab.cli search --target ramsey --n 43 --seconds 150 --seed 2 \
    --out "$OUT/attacks/ramsey_k43_tabu.json"

# ------------------------------------------------------------------- kissing
step "attempts to beat the classical kissing-number lower bounds"
for spec in "5 41" "6 73" "7 127"; do
  set -- $spec
  run python -m oplab.cli search --target kissing --dim "$1" --n "$2" --seconds 60 \
      --workers "$WORKERS" --seed 5 --out "$OUT/attacks/kissing_d$1_n$2.json"
done

# -------------------------------------------------------------------- Tammes
step "Tammes sweep on S^2 for N = 15..23 (published best known: Sloane)"
run python -m oplab.cli sweep --dim 3 --n-min 15 --n-max 23 --seconds 45 \
    --workers "$WORKERS" --seed 7 --out-dir "$OUT/attacks"

# --------------------------------------------------------------------- verify
step "verification of everything on disk"
run python -m oplab.cli verify "$OUT" --write
echo -e "\nAll certificates written under $OUT; log in $LOG"
