#!/usr/bin/env python3
"""Search one block-Cayley shape for a clean colouring, and verify what it finds.

A *block-Cayley* colouring is invariant under translating each block of a group
independently: ``b`` blocks carrying ``|G|`` vertices each, plus ``e`` free extra
vertices, and the colour of an edge between two blocks depends only on the two blocks
and the group difference.  It is the family the published multicolour witnesses live
in — Chung's four-colouring of ``K50`` is a three-block block-Cayley colouring over a
group of order 16 with two extra vertices — and it is the family that escapes the
arithmetic obstruction which kills every *circulant* candidate at ``n = 51``
(``3 | 51``, and the obstruction needs a difference ``n/3`` that a block of ``Z_17``
does not have).

    python scripts/block_hunt.py 51:3,3,3,3 --blocks 3 --group 17 --seconds 900 \\
        --out runs/block_k51_z17.json

What a run establishes depends on the verdict, and the report says which:

``sat``
    The model was decoded with the instance's own class assignment and re-counted by
    :func:`oplab.multicolour.verify_colouring`; the colouring is stored in the report.
    A witness is a witness *without qualification*: the family restricts the search,
    not the statement, so a clean member is a clean colouring of ``K_n`` and
    ``R(s_1, ..., s_k) > n``.
``sat-invalid``
    A model decoded but does not re-count clean.  That is a failure of this script or
    of the encoding, not a result, and the exit status says so.
``unsat``
    The solver's verdict about **this shape**.  It is not a theorem (no DRAT trace is
    emitted here) and it bounds nothing: it says the family is empty, which is worth
    knowing and worth no bound.
``unknown``
    Nothing.  Keep the shape for a longer budget or a stronger engine.

Exit codes: 0 for a verified witness or a refutation of the family, 1 for a witness
that does not verify, 2 for an undecided run (or no engine).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from oplab import blocks as B  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("spec", help="the instance, as N:s1,s2,... (e.g. 51:3,3,3,3)")
    parser.add_argument("--blocks", type=int, default=1, help="blocks in the family")
    parser.add_argument("--group", default=None,
                        help="the group as cyclic factor orders, e.g. 17 or 2,2,2,2 "
                             "(default: one cyclic factor of the block order)")
    parser.add_argument("--extras", type=int, default=0,
                        help="free vertices after the blocks")
    parser.add_argument("--seconds", type=float, default=600.0, help="solver budget")
    parser.add_argument("--solver", default="kissat404", help="the engine (default: kissat404)")
    parser.add_argument("--break-colours", action="store_true",
                        help="fix one class to colour 0 when the forbidden sizes are all "
                             "equal, for the k! that colour relabelling would otherwise cost")
    parser.add_argument("--dimacs", default=None, help="keep the CNF as DIMACS")
    parser.add_argument("--out", default=None, help="the JSON report to write")
    args = parser.parse_args(argv)

    order, _, sizes = args.spec.partition(":")
    sizes = tuple(int(part) for part in sizes.split(","))
    group = tuple(int(part) for part in args.group.split(",")) if args.group else None
    n = int(order)

    report = B.solve_blocks(n, sizes, blocks=args.blocks, group=group, extras=args.extras,
                            seconds=args.seconds, solver=args.solver,
                            break_colours=args.break_colours, dimacs_path=args.dimacs)
    report["produced_by"] = (f"scripts/block_hunt.py {args.spec} --blocks {args.blocks} "
                            f"--group {','.join(map(str, group)) if group else 'default'} "
                            f"--extras {args.extras} --seconds {args.seconds:g} "
                            f"--solver {args.solver}"
                            + (" --break-colours" if args.break_colours else ""))
    report["what"] = (f"block-Cayley family for K{n} {list(sizes)}: {args.blocks} block(s), "
                      f"group {list(group) if group else 'cyclic'}, {args.extras} extras")

    out = Path(args.out or f"runs/block_k{n}_{args.blocks}x{args.extras}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    status = report["status"]
    verdict = (f"{status} in {report['seconds']:g} s "
               f"({report['num_vars']} vars, {report['num_clauses']} clauses, "
               f"{report['classes']} classes)")
    print(f"K{n} {list(sizes)} {report['what'].split(': ', 1)[1]}: {verdict}\n{out}")
    if status == "sat":
        assert report["verify"]["valid"] is True
        print(report["verify"]["establishes"])
        return 0
    if status == "sat-invalid":
        print(f"a model decoded but does not verify: {report['verify']}", file=sys.stderr)
        return 1
    if status == "unsat":
        print("every member of that shape is coloured with a forbidden clique — the family "
              "is empty, which is not a bound and not a theorem", file=sys.stderr)
        return 0
    print(f"nothing claimed: {report.get('note', 'no verdict')}", file=sys.stderr)
    return 2


if __name__ == "__main__":  # pragma: no cover - the script's entry point
    raise SystemExit(main())
