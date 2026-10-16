"""Record hunt over the multicolour Ramsey frontier.

Runs the searches in :mod:`oplab.multicolour` across the target table in
``RECORDS`` and records, for every instance, the best colouring found and its
*exact* number of monochromatic forbidden cliques.  A violation count of zero is
a witness and therefore a record; anything else is an honest measured baseline,
which is what this repository publishes about searches that fail.

The known lower-bound witnesses are included on purpose (``K50`` for
``R(3,3,3,3)``, ``K29`` for ``R(3,3,4)``, ...): they are satisfiable, so a search
that cannot find one cannot be trusted to say anything about the instance one
vertex larger.

Usage::

    python scripts/hunt_records.py --seconds 1500 --workers 16 \
        --out runs/hunt_$(date +%Y%m%dT%H%M).jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from oplab.multicolour import RECORDS, parse_colouring, serialize_colouring, tabu_search  # noqa: E402

#: ``(label, name, n, engine, seed)``.  ``n == RECORDS[name]["lower"] - 1`` is the
#: published witness (a validation run); ``n == lower`` is the record attempt.
JOBS: list[tuple[str, str, int, str, int]] = (
    # validation: the 1973 witness for R(3,3,3,3) > 50 must be findable
    ("validation", "R(3,3,3,3)", 50, "matrix", 101),
    ("validation", "R(3,3,3,3)", 50, "matrix", 102),
    ("validation", "R(3,3,3,3)", 50, "matrix", 103),
    ("validation", "R(3,3,3,3)", 50, "matrix", 104),
    # the record: R(3,3,3,3) > 51 would make the bound 52 (published: 51, 1973)
    ("record", "R(3,3,3,3)", 51, "matrix", 201),
    ("record", "R(3,3,3,3)", 51, "matrix", 202),
    ("record", "R(3,3,3,3)", 51, "matrix", 203),
    ("record", "R(3,3,3,3)", 51, "matrix", 204),
    ("record", "R(3,3,3,3)", 51, "matrix", 205),
    ("record", "R(3,3,3,3)", 51, "matrix", 206),
    ("record", "R(3,3,3,3)", 51, "matrix", 207),
    ("record", "R(3,3,3,3)", 51, "matrix", 208),
    # the record: R(3,3,3,3,3) > 162 (published: 162, Exoo 1994)
    ("record", "R(3,3,3,3,3)", 162, "bits", 301),
    ("record", "R(3,3,3,3,3)", 162, "bits", 302),
    ("record", "R(3,3,3,3,3)", 162, "bits", 303),
    # validation of the general engine: R(3,3,4) > 29 is a theorem (1988/2016)
    ("validation", "R(3,3,4)", 29, "(n/a)", 401),
)


def run_job(job, seconds: float) -> dict:
    label, name, n, engine, seed = job
    record = RECORDS[name]
    sizes = record["sizes"]
    started = time.time()
    kwargs = {"seed": seed}
    if engine in ("matrix", "bits"):
        kwargs["engine"] = engine
    result = tabu_search(n, sizes, seconds=seconds, **kwargs)
    return {
        "label": label,
        "name": name,
        "sizes": list(sizes),
        "n": n,
        "published_lower": record["lower"],
        "published_witness_vertices": record["witness_vertices"],
        "would_establish": f"R{tuple(sizes)} > {n}" if n >= record["lower"] else None,
        "engine": engine,
        "seed": seed,
        "budget_seconds": seconds,
        "wall_seconds": time.time() - started,
        "violations": result["violations"],
        "monochromatic_cliques": result["monochromatic_cliques"],
        "steps": result["steps"],
        "attempts": result["attempts"],
        "witness": result["coloring"] if result["verified_zero"] else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=1500.0, help="budget per job")
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    out = Path(args.out) if args.out else ROOT / "runs" / f"hunt_{time.strftime('%Y%m%dT%H%M%S')}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    print(f"# {len(JOBS)} jobs, {args.seconds:.0f}s each, {args.workers} workers -> {out}", flush=True)

    with out.open("w", encoding="utf-8") as handle, ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(run_job, job, args.seconds): job for job in JOBS}
        for future in as_completed(futures):
            try:
                record = future.result()
            except Exception as exc:  # pragma: no cover - diagnostic path
                label, name, n, engine, seed = futures[future]
                record = {"label": label, "name": name, "n": n, "engine": engine,
                          "seed": seed, "error": repr(exc)}
            handle.write(json.dumps(record) + "\n")
            handle.flush()
            if "error" in record:
                print(f"  {record['name']} K{record['n']}: ERROR {record['error']}", flush=True)
            else:
                print(
                    f"  {record['label']:10s} {record['name']:12s} K{record['n']:<4d} "
                    f"engine={record['engine']:6s} seed={record['seed']:<4d} "
                    f"violations={record['violations']:<6d} steps={record['steps']:<9d} "
                    f"{record['wall_seconds']:.0f}s"
                    + ("  *** WITNESS ***" if record["witness"] else ""),
                    flush=True,
                )

    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines() if line.strip()]
    print("\n# best per instance")
    best: dict[str, dict] = {}
    for row in rows:
        if "error" in row:
            continue
        key = f"{row['name']} K{row['n']}"
        if key not in best or row["violations"] < best[key]["violations"]:
            best[key] = row
    for key, row in sorted(best.items()):
        print(f"  {key:26s} violations={row['violations']:<6d} "
              f"({'WITNESS - record' if row['witness'] else 'no witness'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
