#!/usr/bin/env bash
# Reproduce every certificate committed in certs/.
#
#   bash scripts/run_full.sh            # ~25 minutes on 16 cores
#   WORKERS=4 bash scripts/run_full.sh  # fewer cores, same certificates
#
# Everything printed here is measured; RESULTS.md quotes this run.  The file names
# match `certificates.md`: `certs/<problem>/k<n>_<sizes joined by x>.json`.
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

# ------------------------------------------------------------- engine health
step "the bundled engines, probed rather than assumed"
# A wheel that imports and a wheel that answers are different things: the bundled
# Kissat dies on its first two-clause instance (exit 3221225477) and answers `sat`
# with an invalid model on a four-clause contradiction, so `kissat404` is only
# trusted when `oplab.tools` finds a real binary for it (see docs/tools.pin) — the
# table's `backing` column says which one answered.  This prints the table first,
# so a dead engine is visible before it takes a campaign slot; a non-zero exit is
# not fatal, because CaDiCaL — the engine every certificate here rests on — is
# reported separately.
run python -m oplab.cli solvers --seconds 20 || true

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

# ------------------------------------------- multicolour circulant sub-family
step "deciding the circulant sub-family of the multicolour frontier"
mkdir -p "$OUT/circulant_multicolour/proofs"
for spec in "5 3,3" "6 3,3" "17 4,4" "18 4,4" "29 3,3,4" "30 3,3,4" \
            "35 4,6" "36 4,6" "42 5,5" "43 5,5" \
            "44 3,3,5" "45 3,3,5" "50 3,3,3,3" "51 3,3,3,3" \
            "54 3,4,4" "55 3,4,4" "96 3,3,3,4" "97 3,3,3,4" \
            "127 4,4,4" "128 4,4,4" "161 3,3,3,3,3" "162 3,3,3,3,3" \
            "537 3,3,3,3,3,3" "538 3,3,3,3,3,3"; do
  set -- $spec
  tag="k$1_$(echo "$2" | tr , x)"
  # --proof writes a DRAT trace for the unsat rows and is ignored by the others;
  # the certificate records its digests, and the writing run replays it once.
  # `.bdrat.xz` is binary DRAT (the encoding drat-trim reads with -i) with xz
  # compression: the same proof, a quarter smaller than the text, and still the
  # artifact the external checker is handed.
  run python -m oplab.cli mc-circulant --n "$1" --sizes "$2" --seconds 120 \
      --proof "$OUT/circulant_multicolour/proofs/$tag.bdrat.xz" \
      --out "$OUT/circulant_multicolour/$tag.json"
done

# ------------------------------------------- DIMACS hand-off for the undecided
# Six of the certificates above come back `unknown`: their encodings (20 345 to
# 149 024 clauses) exhaust the bundled solver's budget.  They are exported here
# for a full-strength solver, which is the documented way to decide them.
step "DIMACS hand-off for the instances the bundled budget leaves undecided"
mkdir -p dimacs
for spec in "96 3,3,3,4" "97 3,3,3,4" "127 4,4,4" "128 4,4,4" \
            "161 3,3,3,3,3" "538 3,3,3,3,3,3"; do
  set -- $spec
  run python -m oplab.cli mc-circulant --n "$1" --sizes "$2" --dimacs-only \
      --dimacs "dimacs/k$1_$(echo "$2" | tr , x).cnf"
done

# ------------------------------------ translation-invariant over *any* group
# `mc-circulant` decides the cyclic case; these are the non-cyclic groups, one row
# per anchor, each `unsat` row proof-carrying: the solver writes its DRAT trace and
# `oplab cayley` replays it against that group's encoding before writing the
# certificate.  `K6` over `D3` needs no solver at all — `3 | n` decides it — and is
# stored as `obstructed`, which is the arithmetic theorem rather than a verdict.
step "translation-invariant colourings over non-cyclic groups (proof-carrying)"
mkdir -p "$OUT/cayley/proofs"
run python -m oplab.cli cayley --n 18 --sizes 4,4 --group D9 \
    --proof "$OUT/cayley/proofs/k18_4x4_D9.bdrat.xz" --out "$OUT/cayley/k18_4x4_D9.json"
run python -m oplab.cli cayley --n 18 --sizes 4,4 --group Z3xD3 \
    --proof "$OUT/cayley/proofs/k18_4x4_Z3xD3.bdrat.xz" --out "$OUT/cayley/k18_4x4_Z3xD3.json"
run python -m oplab.cli cayley --n 30 --sizes 3,3,4 --group D15 \
    --proof "$OUT/cayley/proofs/k30_3x3x4_D15.bdrat.xz" --out "$OUT/cayley/k30_3x3x4_D15.json"
run python -m oplab.cli cayley --n 6 --sizes 3,3 --group D3 \
    --out "$OUT/cayley/k6_3x3_D3.json"

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

# ------------------------------------------------------- re-pin the proof store
# The traces were just regenerated, so the manifest that pins them has to follow;
# writing it here is deliberate, and `make proof-store` is what fails if a later
# change to a trace or a certificate does not come with one.
step "re-pinning the stored proof stores"
run python scripts/proof_manifest.py --write
run python scripts/proof_manifest.py --certs "$OUT/cayley" --write

# ------------------------------------------------- cross-check with drat-trim
# The stored traces have now been replayed by oplab.drat, the checker this
# repository owns.  If the external checker is on PATH, check them again with it:
# CI does this in its own job, and "s VERIFIED" from a checker that knows nothing
# about this code is what keeps the circularity out of the proofs.
if command -v drat-trim >/dev/null 2>&1; then
  step "cross-checking every stored trace with drat-trim"
  run python scripts/drat_trim_check.py --drat-trim "$(command -v drat-trim)"
else
  echo "(drat-trim not on PATH: skipping the external cross-check; CI runs it)" | tee -a "$LOG"
fi

echo -e "\nAll certificates written under $OUT; log in $LOG"
