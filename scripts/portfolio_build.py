#!/usr/bin/env python3
"""Turn a SmallGroups export into ``data/smallgroups_<n>.json``.

``scripts/gap_export_smallgroups.g`` writes one JSON object per line, straight from
GAP: a faithful permutation representation of ``SmallGroup(n, id)`` for every ``id``
of the order asked for, plus the invariants GAP computed for it.  Nothing in that
stream is trusted here.  Every group is rebuilt in Python — the generators are
closed under composition by :func:`oplab.cayley.group_from_description`, which
refuses a closure that is not of the declared order — and the invariants are
*re-counted* from the rebuilt table by :func:`oplab.cayley.portfolio_signature`.
A disagreement is a refusal, not a warning: the file this script writes is the
input to a sweep, and a sweep that searched a different group than it says is
worse than no sweep.

    gap -q -b -c 'order := 128;; out := "smallgroups_128_1.jsonl"; \\
                  first_id := 1;; last_id := 582;; \\
                  Read("scripts/gap_export_smallgroups.g"); QUIT;'
    python scripts/portfolio_build.py --jsonl smallgroups_128_1.jsonl \\
        --jsonl smallgroups_128_583.jsonl ... --out data/smallgroups_128.json

``--jsonl`` is repeatable: a long export is split over several processes, and the
parts have to tile the ids of the order exactly once — a gap or an overlap is a
refusal here, because the claim "this is every group of that order" is the one
thing the builder cannot re-derive as cheaply as it checks it.

What the file then claims, and what it does not: the *count* and the *labels* are
the library's (Besche–Eick–O'Brien, and GAP's `NrSmallGroups`), and the id of a row
is provenance — which entry of the library it is.  What this repository has checked
itself is that every row is a group of the order declared, that the invariants in
the file are the ones its table has, and that no two rows in the portfolio share
that invariant signature — reported below as the number of classes the signature
leaves ambiguous, because a signature is a necessary and not a sufficient condition
for non-isomorphism.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from oplab import cayley as C  # noqa: E402

INVARIANTS = ("orders", "classes", "center", "derived", "exponent", "abelian")


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def read_export(paths: list[Path]) -> tuple[dict, list[dict], list[dict]]:
    """The rows of one or more export parts, and where they came from.

    Every part carries a header naming the order, the count and the id range it
    covers; they have to agree on the order and the count, and the ranges have to
    tile ``1..n`` with no gap and no overlap, because that is the part of the claim
    the builder cannot check group by group afterwards.
    """
    header: dict | None = None
    parts: list[dict] = []
    rows: list[dict] = []
    for path in paths:
        part_header: dict | None = None
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError as exc:
                raise SystemExit(f"{path}:{number}: not JSON ({exc})")
            if part_header is None and "gap" in entry:
                part_header = entry
                continue
            rows.append(entry)
        if part_header is None:
            raise SystemExit(f"{path}: no header line (is this a GAP export?)")
        if header is None:
            header = part_header
        elif (part_header["order"], part_header["n"]) != (header["order"], header["n"]):
            raise SystemExit(f"{path}: order {part_header['order']} / {part_header['n']} groups "
                             f"does not match {paths[0].name}")
        parts.append({"file": path.name, "digest": _digest(path),
                      "first_id": int(part_header.get("first_id", 1)),
                      "last_id": int(part_header.get("last_id", part_header["n"])),
                      "rows": sum(1 for line in path.read_text(encoding="utf-8").splitlines()
                                  if line.strip()) - 1})
    assert header is not None
    covered: list[int] = []
    for part in parts:
        covered.extend(range(part["first_id"], part["last_id"] + 1))
    if sorted(covered) != list(range(1, int(header["n"]) + 1)):
        raise SystemExit(f"the parts do not tile 1..{header['n']}: they cover "
                         f"{len(covered)} ids, {len(set(covered))} of them distinct")
    if len(rows) != int(header["n"]):
        raise SystemExit(f"the parts carry {len(rows)} rows for {header['n']} groups")
    rows.sort(key=lambda entry: int(entry["id"]))
    return header, rows, parts


def check_rows(order: int, rows: list[dict]) -> tuple[list[dict], list[list[int]], int, int]:
    """Rebuild every group, re-count its invariants, and report the disagreements.

    Returns the rows, the ids sharing an invariant signature, the number of
    signature classes and the size of the largest one.
    """
    groups: list[dict] = []
    seen_ids: list[int] = []
    bad: list[str] = []
    signatures: dict[str, list[int]] = {}
    for index, entry in enumerate(rows):
        row_order, id_ = int(entry["order"]), int(entry["id"])
        if row_order != order:
            bad.append(f"row {index}: order {row_order}, expected {order}")
            continue
        name = f"SmallGroup({order},{id_})"
        description = {"family": "permutation",
                       "params": [order, [[int(x) for x in g] for g in entry["generators"]]],
                       "name": name, "id": id_}
        try:
            table, inverse = C.group_from_description(description)
        except ValueError as exc:
            bad.append(f"{name}: {exc}")
            continue
        if len(table) != order:
            bad.append(f"{name}: the table has order {len(table)}")
            continue
        found = C.portfolio_signature(table, inverse)
        declared = {key: entry[key] for key in INVARIANTS}
        for key in ("orders", "classes"):
            declared[key] = {str(k): int(v) for k, v in declared[key].items()}
        if found != declared:
            bad.append(f"{name}: the export declares {declared}, the table has {found}")
            continue
        key = json.dumps(found, sort_keys=True)
        signatures.setdefault(key, []).append(id_)
        seen_ids.append(id_)
        groups.append({"id": id_, "name": name, "degree": int(entry["degree"]),
                       "generators": description["params"][1], **found})
    if bad:
        for line in bad[:20]:
            print(f"  {line}", file=sys.stderr)
        raise SystemExit(f"{len(bad)} of {len(rows)} rows do not rebuild to the group they "
                         f"claim: refusing to write a portfolio")
    if sorted(seen_ids) != list(range(1, len(rows) + 1)):
        raise SystemExit(f"the ids are not 1..{len(rows)}")
    ambiguous = [sorted(v) for v in signatures.values() if len(v) > 1]
    return groups, ambiguous, len(signatures), max((len(v) for v in signatures.values()),
                                                  default=0)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--jsonl", action="append", required=True,
                        help="an export part written by the GAP script (repeatable)")
    parser.add_argument("--out", required=True, help="the portfolio to write")
    parser.add_argument("--xz", action="store_true",
                        help="also write <out>.xz, which load_portfolio reads directly")
    args = parser.parse_args(argv)

    sources = [Path(path) for path in args.jsonl]
    header, rows, parts = read_export(sources)
    order, declared_n = int(header["order"]), int(header["n"])
    started = time.time()
    groups, ambiguous, classes, largest = check_rows(order, rows)
    print(f"order {order}: {len(groups)} groups rebuilt and re-counted in "
          f"{time.time() - started:.1f} s; GAP {header['gap']} declares {declared_n}")
    if declared_n != len(groups):
        raise SystemExit(f"the export says {declared_n} groups, it carries {len(groups)}")
    print(f"  invariant signature: {classes} classes, {len(ambiguous)} ambiguous, "
          f"largest {largest} groups")
    for ids in ambiguous[:5]:
        print(f"    ids sharing a signature: {ids[:12]}{' ...' if len(ids) > 12 else ''}")

    payload = {
        "what": f"every group of order {order} in the GAP SmallGroups library, as faithful "
                f"permutation generators — the full portfolio for a Cayley sweep",
        "produced_by": "python scripts/portfolio_build.py "
                       + " ".join(f"--jsonl {path.name}" for path in sources)
                       + f" --out {Path(args.out).as_posix()}",
        "source": {
            "library": "GAP SmallGroups (Besche–Eick–O'Brien)",
            "gap_version": header["gap"],
            "gap_order": order,
            "nr_small_groups": declared_n,
            "export_script": "scripts/gap_export_smallgroups.g",
            "exports": parts,
            "exports_digest": "sha256:" + hashlib.sha256(
                "".join(part["digest"] for part in parts).encode("ascii")).hexdigest(),
        },
        "reading": (
            "`generators` are the images of 0..degree-1 under a faithful permutation "
            "representation, which `oplab.cayley`'s `permutation` family closes into the "
            "multiplication table; the invariants beside them were recomputed from that "
            "table when this file was written and are re-checked on every load, so no "
            "claim here rests on GAP: the id is provenance, the group is the table. "
            "`ambiguous` counts the signature classes that hold more than one group — "
            "sharing an invariant signature is necessary, not sufficient, for being "
            "isomorphic, so those classes are what the signature does not separate."
        ),
        "checks": {
            "groups": len(groups),
            "rebuilt_and_recounted": len(groups),
            "invariant_mismatches": 0,
            "signature_classes": classes,
            "ambiguous_signature_classes": ambiguous,
            "largest_signature_class": largest,
        },
        "order": order,
        "groups": groups,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=1) + "\n"
    out.write_text(text, encoding="utf-8")
    print(f"  wrote {out} ({len(text) / 1e6:.2f} MB)")
    if args.xz:
        import lzma
        compressed = out.parent / (out.name + ".xz")
        with lzma.open(compressed, "wt", encoding="utf-8", preset=6) as handle:
            handle.write(text)
        print(f"  wrote {compressed} ({compressed.stat().st_size / 1e6:.2f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
