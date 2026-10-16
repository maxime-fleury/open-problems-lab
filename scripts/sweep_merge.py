#!/usr/bin/env python3
"""Fold a later round of group runs into `runs/cayley_sweep.json`, row by row.

The sweep in `runs/cayley_sweep.json` is the machine-readable record of what has
been decided over the **groups** of the undecided sizes, and it is quoted by name
in `RESULTS.md`.  A later round — the same groups with a much longer budget, say —
does not invalidate it: the earlier attempt is part of what was measured, and this
repository publishes the attempts that failed.  So a merge *supersedes* rows
rather than editing them away:

  * `rows` stays the current frontier, one row per (size, group): a recovered
    verdict replaces the `unknown` it grew out of;
  * `superseded` keeps the rows that were replaced, so "300 s told nothing, 3600 s
    decided it" both survive;
  * `rounds` names the file each later round came from, with the budget and the
    engine it was run at, so the numbers can be traced back to a raw run.

Nothing is merged on a guess: a later row must name a size/group pair the sweep
already has (a *new* group is a portfolio change, not a longer round, and belongs
in the sweep's own generation), and a row from the repair engine is refused —
the repair engine hunts a witness and reports no decision, so folding it into the
frontier row would replace a decision with an attempt.  Keep those in their own
file and quote them in prose.

    python scripts/sweep_merge.py runs/cayley_sweep.json runs/cayley_long_k96.json \
        runs/cayley_long_k128_cadical.json                      # dry run, prints the diff
    python scripts/sweep_merge.py runs/cayley_sweep.json ... --write

Exit codes: 0 when every later row was merged, 2 when a row had no counterpart or
came from the repair engine (both need a decision, not a silent skip).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


def key_of(row: dict) -> tuple:
    return (int(row["n"]), tuple(int(s) for s in row["sizes"]),
            (row.get("group") or {}).get("name"))


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def counts(rows) -> tuple[dict, list]:
    """The `totals` and `per_target` blocks, recomputed from the rows."""
    totals: dict[str, int] = {}
    per: dict[int, dict] = {}
    for row in rows:
        status = row["status"]
        totals[status] = totals.get(status, 0) + 1
        entry = per.setdefault(int(row["n"]), {
            "n": int(row["n"]), "sizes": list(row["sizes"]),
            "groups": {}, "group_count": 0})
        entry["groups"][status] = entry["groups"].get(status, 0) + 1
        entry["group_count"] += 1
    return totals, [per[n] for n in sorted(per)]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("sweep", help="the sweep to update")
    parser.add_argument("rounds", nargs="+", help="the later rounds, as JSON row lists")
    parser.add_argument("--write", action="store_true", help="rewrite the sweep in place")
    args = parser.parse_args(argv)

    sweep_path = Path(args.sweep)
    sweep = load(sweep_path)
    rows = sweep["rows"]
    # position, not the dict: two rows are `==` when their fields agree, and the
    # wrong one would be replaced
    index = {key_of(row): position for position, row in enumerate(rows)}
    superseded = sweep.setdefault("superseded", [])
    rounds = sweep.setdefault("rounds", [])

    merged = refused = 0
    for round_path_text in args.rounds:
        round_path = Path(round_path_text)
        later = load(round_path)
        recovered = 0
        for row in later:
            if "repair_moves" in row or row.get("best_violations") is not None:
                print(f"  refused {row.get('name')}: a repair row reports no decision "
                      f"(it hunts witnesses); keep it in {round_path.name} and quote it "
                      f"in prose", file=sys.stderr)
                refused += 1
                continue
            position = index.get(key_of(row))
            if position is None:
                print(f"  refused {row.get('name')} {row['n']}: the sweep has no such "
                      f"row, so this is a portfolio change rather than a longer round",
                      file=sys.stderr)
                refused += 1
                continue
            target = rows[position]
            if target is row:
                continue
            print(f"  {row['n']} {tuple(row['sizes'])} {row.get('name')}: "
                  f"{target['status']} ({target['seconds']:.0f} s) -> "
                  f"{row['status']} ({row['seconds']:.0f} s)")
            if row["status"] != target["status"]:
                recovered += 1
            superseded.append(target)
            rows[position] = row
            index[key_of(row)] = position
            merged += 1
        rounds.append({
            "file": round_path.name,
            "rows": len(later),
            "seconds": max((r["seconds"] for r in later), default=None),
            "statuses": sorted({r["status"] for r in later}),
            "decisions_changed": recovered,
        })

    sweep["totals"], sweep["per_target"] = counts(rows)
    sweep["snapshot"] = time.strftime("%Y-%m-%d")
    print(f"\n{merged} rows superseded ({len(superseded)} kept as history), "
          f"{refused} refused; frontier now {sweep['totals']}")
    if args.write:
        sweep_path.write_text(json.dumps(sweep, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {sweep_path}  (update `what`/`produced_by`/`reading` by hand: they "
              f"are prose about the rounds, and this script only recomputes the counts)")
    else:
        print("dry run: pass --write to update the sweep")
    return 0 if refused == 0 else 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
