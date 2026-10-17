"""How many blank classes a dead partial colouring needs before it can be filled.

``oplab.anneal.partial`` dissolves a plateau by leaving classes uncoloured.  The states it
reaches that way are not automatically repairable, and the useful question is not "is this
one repairable" but **how far the support goes**: grow the blank set from such a state, one
step at a time, asking ``anneal.repair`` to colour exactly the blank classes in, and see
where the answer turns from unsatisfiable to satisfiable.

The walk is run first (same flags as ``anneal_hunt.py``), and the growth starts from the
state it ended in — which must have zero violations, because otherwise a refusal could be
about the violations rather than about the extension.  Seeds are tried in order until one
ends clean, and the report says which.

    python scripts/partial_support.py 50:3,3,3,3 --blocks 3 --group 2,2,2,2 --extras 2 \\
        --seconds 12 --step 8 --repair-seconds 6 --out runs/anneal/partial_k50_support.json

The table is ``[blanks, verdict, seconds]`` with ``verdict`` one of ``sat``, ``unsat``,
``timeout``.  A row that says ``timeout`` is the honest end of the measurement when the
sub-instance has grown back into the full search; it is not evidence of anything.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:  # pragma: no cover - script entry point
    sys.path.insert(0, str(ROOT / "src"))
if str(ROOT / "scripts") not in sys.path:  # pragma: no cover - script entry point
    sys.path.insert(0, str(ROOT / "scripts"))

from oplab import anneal as AN  # noqa: E402
from oplab import blocks as B  # noqa: E402
from oplab import gputabu as G  # noqa: E402

import anneal_hunt  # noqa: E402


def clean_state(problem: G.Problem, args) -> dict:
    """Walk until a run ends with zero violations, and hand that report back."""
    for seed in range(args.seeds):
        report = AN.partial(problem, seconds=args.seconds, seed=seed,
                            blank_weight=args.blank_weight, noise=args.noise,
                            repair_seconds=args.repair_seconds,
                            attempt_every=args.attempt_every)
        if report["violations"] == 0 and report["blanks"] > 0:
            report["walk_seed"] = seed
            return report
        print(f"seed {seed}: ended at {report['violations']} violation(s) and "
              f"{report['blanks']} blank(s); not a state to grow from", file=sys.stderr)
    raise SystemExit("no seed ended with zero violations and some blanks: nothing to grow")


def grow(problem: G.Problem, report: dict, args) -> list:
    """Blank ``step`` more classes at a time until the engine stops saying unsat."""
    A0 = np.array(report["assignment"], dtype=np.int8)
    blank = {int(p) for p in report["blanks_at"]}
    rng = np.random.default_rng(args.seed)
    table = []
    while True:
        A = A0.copy()
        for p in blank:
            A[p] = AN.BLANK
        _, viol = AN._counts(problem, A)
        assert not viol.any(), "the state being grown must be clean"
        free = np.array(sorted(blank), dtype=np.int64)
        started = time.time()
        outcome = AN.repair(problem, A, viol, rng, free=free, seconds=args.repair_seconds)
        verdict = ("sat" if outcome["solved"]
                   else "timeout" if outcome.get("timeout") else "unsat")
        table.append([len(blank), verdict, round(time.time() - started, 3)])
        print(table[-1], file=sys.stderr)
        if verdict != "unsat" or len(blank) >= problem.nc:
            return table
        touch = np.unique(problem.inc[free][problem.inc_mask[free]])
        near = np.unique(problem.set_cls[touch][problem.set_cls[touch] != problem.nc])
        near = [int(p) for p in near if p not in blank]
        if not near:
            return table
        blank |= {int(p) for p in rng.choice(near, size=min(args.step, len(near)),
                                             replace=False)}


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec", help="n:s1,s2,... e.g. 50:3,3,3,3")
    ap.add_argument("--blocks", type=int, default=1)
    ap.add_argument("--group", default=None, help="comma-separated factor orders")
    ap.add_argument("--extras", type=int, default=0)
    ap.add_argument("--seconds", type=float, default=12.0, help="budget for the walk")
    ap.add_argument("--seeds", type=int, default=6, help="how many walks to try")
    ap.add_argument("--seed", type=int, default=0, help="seed of the growth itself")
    ap.add_argument("--step", type=int, default=8, help="classes blanked per round")
    ap.add_argument("--repair-seconds", type=float, default=6.0)
    ap.add_argument("--blank-weight", type=float, default=1.0)
    ap.add_argument("--noise", type=float, default=0.05)
    ap.add_argument("--attempt-every", type=int, default=20000)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    n, sizes = anneal_hunt.parse_spec(args.spec)
    group = tuple(int(f) for f in args.group.split(",")) if args.group else None
    instance = B.BlockInstance(n, sizes, blocks=args.blocks, group=group,
                               extras=args.extras)
    problem = G.from_blocks(instance)
    obstruction = B.block_obstruction(instance)
    if obstruction is not None:
        print(f"obstructed by arithmetic: {obstruction['reason']}; nothing to measure",
              file=sys.stderr)
        return 3

    report = clean_state(problem, args)
    table = grow(problem, report, args)
    out = {
        "n": n, "sizes": list(sizes), "family": instance.describe(),
        "classes": problem.nc, "class_sets": problem.n_sets,
        "walk": {k: report[k] for k in ("walk_seed", "steps", "seconds", "violations",
                                        "blanks", "support", "min_blanks", "refused")},
        "start_blanks": report["blanks"],
        "blank_weight": args.blank_weight, "step": args.step,
        "repair_seconds": args.repair_seconds, "seed": args.seed,
        "growth": table,
        "search_only": True,
        "what": (f"support growth from a clean partial state of {instance.describe()}: "
                 f"the blank count at which re-insertion first stops saying unsat"),
    }
    if args.out:
        path = Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
        print(args.out)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
