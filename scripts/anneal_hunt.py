"""Guided annealing for a witness, with a gate it has to pass first.

The batched tabu in ``scripts/gpu_tabu.py`` was allowed to speak about ``K51`` without
ever having found a colouring that was known to exist.  That is the mistake this script
exists to prevent: before any run on a target, the same search, with the same
parameters, must rediscover the **known** witness at ``K50`` in the block-Cayley family
(3 blocks of ``Z_2^4`` plus 2 extra vertices) from a random start.

    python scripts/anneal_hunt.py --gate --seconds 60 --seed 0
    python scripts/anneal_hunt.py 51:3,3,3,3 --blocks 3 --group 17 --seconds 900

The gate writes ``runs/anneal/gate_k50.json``.  Any other target refuses to run unless
that file records a ``sat`` on the same instance, so "we ran it anyway" is a deliberate
act and not an oversight.  Exit codes: 0 when the run did what was asked (a witness, or
an honest ``best-effort``), 1 when a witness was claimed and failed verification, 2
when the gate has not been passed, 3 when the instance is obstructed by arithmetic.

Every report carries ``search_only: true``.  ``best-effort`` means the walk ran out of
time with that many monochromatic cliques left; no bound may be read from it.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:  # pragma: no cover - script entry point
    sys.path.insert(0, str(ROOT / "src"))

from oplab import anneal as AN  # noqa: E402
from oplab import blocks as B  # noqa: E402
from oplab import gputabu as G  # noqa: E402

GATE_FILE = ROOT / "runs" / "anneal" / "gate_k50.json"
GATE_SPEC = {"n": 50, "sizes": [3, 3, 3, 3], "blocks": 3, "group": [2, 2, 2, 2],
             "extras": 2}


def parse_spec(text: str) -> tuple[int, tuple[int, ...]]:
    """``"51:3,3,3,3"`` -> ``(51, (3, 3, 3, 3))``, the shape the other scripts take."""
    head, _, tail = text.partition(":")
    if not tail:
        raise SystemExit(f"expected n:s1,s2,... but got {text!r}")
    return int(head), tuple(int(s) for s in tail.split(","))


def gate_problem() -> G.Problem:
    """The calibration instance: the family the published ``K50`` witness lives in."""
    instance = B.BlockInstance(GATE_SPEC["n"], tuple(GATE_SPEC["sizes"]),
                               blocks=GATE_SPEC["blocks"], group=tuple(GATE_SPEC["group"]),
                               extras=GATE_SPEC["extras"])
    return G.from_blocks(instance)


def gate_record(path: Path = GATE_FILE) -> dict | None:
    """The stored gate result, if it passed on this exact instance."""
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if record.get("status") != "sat" or not record.get("verify", {}).get("valid"):
        return None
    for key, value in GATE_SPEC.items():
        if record.get("gate_spec", {}).get(key) != value:
            return None
    return record


def _write(path: Path | None, report: dict) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def _line(report: dict) -> str:
    return (f"{report['status']}: {report['violations']} violation(s) at best, "
            f"{report['steps']} steps in {report['seconds']} s "
            f"({report['steps_per_second']}/s, drift {report['recount_drift']}, "
            f"kempe {report['kempe_steps']})")


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec", nargs="?", help="n:s1,s2,... e.g. 51:3,3,3,3")
    ap.add_argument("--gate", action="store_true",
                    help="run the K50 calibration and refuse everything else until it passes")
    ap.add_argument("--gate-file", default=str(GATE_FILE),
                    help="where the gate result is read from and written to")
    ap.add_argument("--blocks", type=int, default=1)
    ap.add_argument("--group", default=None, help="comma-separated factor orders")
    ap.add_argument("--extras", type=int, default=0)
    ap.add_argument("--general", action="store_true", help="all colourings, not a family")
    ap.add_argument("--seconds", type=float, default=60.0)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--lam", type=float, default=2.0)
    ap.add_argument("--noise", type=float, default=0.05)
    ap.add_argument("--fan", type=int, default=1)
    ap.add_argument("--reject", action="store_true",
                    help="turn the Metropolis rule on (measured worse here)")
    ap.add_argument("--t0", type=float, default=1.0)
    ap.add_argument("--tmin", type=float, default=0.1)
    ap.add_argument("--stuck", type=int, default=200)
    ap.add_argument("--kempe", type=float, default=0.005)
    ap.add_argument("--repair-cap", type=int, default=0,
                    help="classes freed for the CDCL repair on a stall (0 disables it)")
    ap.add_argument("--repair-seconds", type=float, default=5.0,
                    help="budget per repair: a sub-instance can be nearly the whole one")
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    gate_path = Path(args.gate_file)
    started = time.time()

    if args.gate:
        problem = gate_problem()
        report = AN.anneal(problem, seconds=args.seconds, seed=args.seed, lam=args.lam,
                           noise=args.noise, fan=args.fan, reject=args.reject,
                           t0=args.t0, tmin=args.tmin, stuck=args.stuck,
                           kempe=args.kempe, repair_cap=args.repair_cap,
                           repair_seconds=args.repair_seconds)
        report.update({"gate": "K50 in the block-Cayley family, from a random start",
                       "gate_spec": GATE_SPEC, "passed": report["status"] == "sat",
                       "produced_by": "scripts/anneal_hunt.py " + " ".join(argv)})
        _write(gate_path, report)
        _write(Path(args.out) if args.out else None, report)
        if report["status"] == "sat":
            print(f"gate passed: K50 witness verified in {report['seconds']} s")
            return 0
        print("gate FAILED: the search did not rediscover the known K50 witness "
              f"({report['violations']} violation(s) left); no target will run on it",
              file=sys.stderr)
        return 1

    if not args.spec:
        ap.error("give a spec, or --gate to run the calibration")

    passed = gate_record(gate_path)
    if passed is None:
        print(f"refused: no passed gate in {gate_path}.  Run `--gate` first; a search "
              f"that has not found a known witness is not allowed to comment on a "
              f"target (RESULTS.md 9e).", file=sys.stderr)
        return 2

    n, sizes = parse_spec(args.spec)
    if args.general:
        problem = G.from_general(n, sizes)
        family = None
    else:
        group = tuple(int(f) for f in args.group.split(",")) if args.group else None
        instance = B.BlockInstance(n, sizes, blocks=args.blocks, group=group,
                                   extras=args.extras)
        problem = G.from_blocks(instance)
        family = instance.describe()
        obstruction = B.block_obstruction(instance)
        if obstruction is not None:
            print(f"obstructed by arithmetic: {obstruction['reason']}; no search was run",
                  file=sys.stderr)
            report = {"n": n, "sizes": list(sizes), "status": "obstructed",
                      "obstruction": obstruction, "seconds": 0.0, "search_only": True}
            _write(Path(args.out) if args.out else None, report)
            return 3

    report = AN.anneal(problem, seconds=args.seconds, seed=args.seed, lam=args.lam,
                       noise=args.noise, fan=args.fan, reject=args.reject,
                       t0=args.t0, tmin=args.tmin, stuck=args.stuck, kempe=args.kempe,
                       repair_cap=args.repair_cap, repair_seconds=args.repair_seconds)
    report.update({"spec": args.spec, "family": family, "general": args.general,
                   "blocks": args.blocks, "group": args.group, "extras": args.extras,
                   "gate": {"file": str(gate_path),
                            "passed_at": passed.get("seconds"),
                            "violations_at_gate": passed.get("violations")},
                   "produced_by": "scripts/anneal_hunt.py " + " ".join(argv),
                   "wall_seconds": round(time.time() - started, 1)})
    print(_line(report), file=sys.stderr)
    _write(Path(args.out) if args.out else None, report)
    if args.out:
        print(args.out)
    return 0 if report["status"] in ("sat", "best-effort") else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
