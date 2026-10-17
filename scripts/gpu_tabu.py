"""Batched tabu search on the GPU, over a block-Cayley family or the whole of K_n.

The SAT scripts answer "is there a clean member" with a decision procedure; this one
*searches* for a witness and says so when it has none.  It exists to test the one
hypothesis the SAT campaign cannot test cheaply: that a witness at the sizes where
Kissat returns `unknown` might be reachable by a heuristic that tries millions of
skeletons at once, without any claim about emptiness.

Every report carries ``search_only: true``.  ``best-effort`` means the walk ran out of
time with that many monochromatic cliques left; it is not evidence about the family,
and no bound may be read from it.  ``sat`` means a witness, expanded and re-counted by
the ordinary verifier.

    python scripts/gpu_tabu.py 51:3,3,3,3 --blocks 3 --group 17 --seconds 1200 \\
        --walks 4096 --pick-every 16 --out runs/block/gputabu_k51_b3_z17.json
    python scripts/gpu_tabu.py 51:3,3,3,3 --general --seconds 1200
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

from oplab import blocks as B  # noqa: E402
from oplab import gputabu as G  # noqa: E402


def parse_spec(text: str) -> tuple[int, tuple[int, ...]]:
    """``"51:3,3,3,3"`` -> ``(51, (3, 3, 3, 3))``, the same shape the SAT scripts take."""
    head, _, tail = text.partition(":")
    if not tail:
        raise SystemExit(f"expected n:s1,s2,... but got {text!r}")
    return int(head), tuple(int(s) for s in tail.split(","))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec", help="n:s1,s2,... e.g. 51:3,3,3,3")
    ap.add_argument("--blocks", type=int, default=1)
    ap.add_argument("--group", default=None, help="comma-separated factor orders, e.g. 2,2,2,2")
    ap.add_argument("--extras", type=int, default=0)
    ap.add_argument("--general", action="store_true", help="all colourings, not a family")
    ap.add_argument("--seconds", type=float, default=600.0)
    ap.add_argument("--walks", type=int, default=4096)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--tenure", type=int, default=12)
    ap.add_argument("--stale", type=int, default=20000)
    ap.add_argument("--pick-every", type=int, default=16,
                    help="refresh the attacked set from all violated sets every N steps")
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    if not G.available():
        print("no CUDA device: this script has nothing to do (the SAT path needs none)",
              file=sys.stderr)
        return 2
    n, sizes = parse_spec(args.spec)
    started = time.time()
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
            print(f"obstructed by arithmetic: {obstruction['reason']} — no search was run",
                  file=sys.stderr)
            report = {"n": n, "sizes": list(sizes), "status": "obstructed",
                      "obstruction": obstruction, "seconds": 0.0, "search_only": True}
            if args.out:
                Path(args.out).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            return 0

    report = G.tabu(problem, seconds=args.seconds, walks=args.walks, seed=args.seed,
                    tenure=args.tenure, stale=args.stale, pick_every=args.pick_every)
    report.update({"spec": args.spec, "family": family, "general": args.general,
                   "blocks": args.blocks, "group": args.group, "extras": args.extras,
                   "device_info": G.describe_device(),
                   "produced_by": "scripts/gpu_tabu.py " + " ".join(argv if argv is not None
                                                                   else sys.argv[1:]),
                   "wall_seconds": round(time.time() - started, 1)})
    print(f"{report['status']}: {report['violations']} violation(s) at best, "
          f"{report['steps']} steps, {report['flips']} flips in {report['seconds']} s "
          f"({report['flips_per_second']}/s, drift {report['recount_drift']})",
          file=sys.stderr)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(args.out)
    return 0 if report["status"] in ("sat", "best-effort", "obstructed") else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
