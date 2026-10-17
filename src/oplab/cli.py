"""Command line interface: ``oplab <command>``.

Commands
--------
``build``      exact classical constructions (root systems, classical graphs)
``search``     run one search and write a certificate
``sweep``      run a search for a range of sizes, with a comparison summary
``circulant``  exhaustive sweep of every circulant colouring of ``K_n``
``mc-circulant``  decide the circulant sub-family of a multicolour instance
``cayley``     decide the translation-invariant colourings of one named group
``solvers``    probe the bundled SAT engines and report who answers
``drat``       check a DRAT proof against a CNF, with no solver involved
``verify``     re-derive every claim in one certificate, a file or a directory
``report``     markdown table of the certificates on disk
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import time
from datetime import date
from pathlib import Path

import numpy as np

from . import (
    __version__,
    cayley as CY,
    drat as DRAT,
    multicolour as MC,
    ramsey as R,
    references as REF,
    sat as SAT,
    sphere as S,
    unitdist as U,
)
from .verify import declared_instance, make_certificate, verify_path


def _provenance(generator: str, **extra) -> dict:
    return {
        "generator": generator,
        "created": date.today().isoformat(),
        "tool": f"open-problems-lab {__version__}",
        "python": platform.python_version(),
        "machine": platform.node(),
        **extra,
    }


def _write(path: Path, cert: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cert, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {path}")


def _points_payload(P: np.ndarray) -> list[list[float]]:
    return [[float(round(x, 15)) for x in row] for row in np.asarray(P, dtype=float)]


# --------------------------------------------------------------------------
# build
# --------------------------------------------------------------------------
def cmd_build(args) -> int:
    if args.kind == "sphere":
        P = S.root_system(args.system)
        dim = P.shape[1]
        cert = make_certificate(
            "kissing",
            f"{args.system.upper()} root system: {len(P)} kissing points in dimension {dim}",
            {"dim": dim, "points": _points_payload(P)},
            {"n_points": len(P), "dim": dim, "max_dot": S.max_dot(P)},
            _provenance(f"oplab build --kind sphere --system {args.system}"),
        )
        _write(Path(args.out), cert)
    elif args.kind == "unit-distance":
        builders = {
            "moser": (U.moser_spindle, "Moser spindle (7 vertices, 11 edges, 4-chromatic)", 4),
            "diamond": (U.diamond, "diamond K4-e (4 vertices, 5 edges, 3-chromatic)", 3),
            "hexagon": (lambda: U.regular_polygon(6), "regular hexagon (6 vertices, 6 edges, 2-chromatic)", 2),
        }
        if args.name not in builders:
            print(f"unknown graph {args.name!r}; pick one of {sorted(builders)}", file=sys.stderr)
            return 2
        build, title, chi = builders[args.name]
        points = build()
        adj = U.adjacency_from_points(points)
        cert = make_certificate(
            "unit_distance",
            title,
            {"points": _points_payload(points), "edges": [list(e) for e in U.edges_of(adj)]},
            {"n_vertices": len(points), "n_edges": len(U.edges_of(adj)), "chromatic_number": chi},
            _provenance(f"oplab build --kind unit-distance --name {args.name}"),
        )
        _write(Path(args.out), cert)
    else:  # pragma: no cover - argparse restricts this
        print("unknown kind", file=sys.stderr)
        return 2
    return 0


# --------------------------------------------------------------------------
# search
# --------------------------------------------------------------------------
def cmd_search(args) -> int:
    if args.target == "kissing":
        return _search_sphere(args, threshold=S.KISSING_THRESHOLD)
    if args.target == "tammes":
        return _search_sphere(args, threshold=None)
    if args.target == "ramsey":
        res = R.tabu_search(args.n, args.seconds, seed=args.seed)
        cert = make_certificate(
            "ramsey",
            f"tabu search on K{args.n}: {res['mono_k5']} monochromatic K5 remaining",
            {"n": args.n, "k": 5, "coloring": res["coloring"]},
            {"n": args.n, "mono_k5": res["mono_k5"]},
            _provenance(
                f"oplab search --target ramsey --n {args.n}",
                steps=res["steps"],
                seed=args.seed,
                seconds=args.seconds,
                algorithm="edge-flip tabu search",
            ),
        )
        _write(Path(args.out), cert)
        print(f"best monochromatic K5 count = {res['mono_k5']} after {res['steps']} flips")
        return 0
    if args.target == "unitdist":
        seeds = {
            "edge": np.array([[0.0, 0.0], [1.0, 0.0]]),
            "diamond": U.diamond(),
            "moser": U.moser_spindle(),
        }
        res = U.search_unit_distance(
            args.seconds, max_vertices=args.n, seed=args.seed, start=seeds[args.start]
        )
        cert = make_certificate(
            "unitdist_search",
            f"unit-distance graphs grown from the {args.start} seed up to {args.n} vertices: "
            f"best chromatic number {res['best_chromatic_number']}",
            res,
            {"best_chromatic_number": res["best_chromatic_number"]},
            _provenance(
                f"oplab search --target unitdist --n {args.n} --start {args.start}",
                seed=args.seed,
                start=args.start,
            ),
        )
        _write(Path(args.out), cert)
        return 0
    print(f"unknown target {args.target!r}", file=sys.stderr)
    return 2


def _search_sphere(args, threshold: float | None) -> int:
    start = None
    if args.start_from:
        start = np.asarray(json.loads(Path(args.start_from).read_text())["payload"]["points"], dtype=float)
    res = S.search_parallel(
        n=args.n, d=args.dim, seconds=args.seconds, workers=args.workers, seed=args.seed, start=start
    )
    points = np.asarray(res["points"], dtype=float)
    value = res["max_dot"]
    if threshold is None:  # Tammes: every configuration is a valid measurement
        cert = make_certificate(
            "tammes",
            f"{args.n} points on S^{args.dim - 1}: minimal angle {S.min_angle_deg(points):.7f} degrees",
            {"dim": args.dim, "points": _points_payload(points)},
            {
                "n_points": args.n,
                "dim": args.dim,
                "min_angle_deg": S.min_angle_deg(points),
                "max_dot": value,
                "best_known_min_angle_deg": REF.TAMMES_S2_BEST_KNOWN_DEG.get(args.n)
                if args.dim == 3
                else None,
            },
            _provenance(
                f"oplab search --target tammes --dim {args.dim} --n {args.n}",
                seed=args.seed,
                seconds=args.seconds,
                workers=args.workers,
                worker_results=res.get("worker_results"),
            ),
        )
        _write(Path(args.out), cert)
        return 0
    establishes = value <= threshold + 1e-9
    if establishes:
        cert = make_certificate(
            "kissing",
            f"{args.n} kissing points in dimension {args.dim}",
            {"dim": args.dim, "points": _points_payload(points)},
            {"n_points": args.n, "dim": args.dim, "max_dot": value},
            _provenance(
                f"oplab search --target kissing --dim {args.dim} --n {args.n}",
                seed=args.seed,
                seconds=args.seconds,
                workers=args.workers,
            ),
        )
    else:
        cert = make_certificate(
            "spherical_search",
            f"attempt at {args.n} kissing points in dimension {args.dim}: failed (max dot {value:.6f} > 0.5)",
            {"dim": args.dim, "points": _points_payload(points)},
            {
                "n_points": args.n,
                "dim": args.dim,
                "max_dot": value,
                "threshold": threshold,
                "establishes_bound": establishes,
            },
            _provenance(
                f"oplab search --target kissing --dim {args.dim} --n {args.n}",
                seed=args.seed,
                seconds=args.seconds,
                workers=args.workers,
                worker_results=res.get("worker_results"),
            ),
        )
    _write(Path(args.out), cert)
    print(f"best max dot = {value:.12f} (threshold {threshold}) -> {'BOUND ESTABLISHED' if establishes else 'no bound'}")
    return 0


# --------------------------------------------------------------------------
# sweep
# --------------------------------------------------------------------------
def cmd_sweep(args) -> int:
    out_dir = Path(args.out_dir)
    summary = {"target": args.target, "dim": args.dim, "runs": []}
    for n in range(args.n_min, args.n_max + 1):
        res = S.search_parallel(
            n=n, d=args.dim, seconds=args.seconds, workers=args.workers, seed=args.seed + 13 * n
        )
        points = np.asarray(res["points"], dtype=float)
        angle = S.min_angle_deg(points)
        reference = REF.TAMMES_S2_BEST_KNOWN_DEG.get(n) if args.dim == 3 else None
        entry = {
            "n": n,
            "dim": args.dim,
            "min_angle_deg": angle,
            "max_dot": res["max_dot"],
            "best_known_min_angle_deg": reference,
            "gap_deg": None if reference is None else angle - reference,
            "seconds": args.seconds,
            "workers": args.workers,
        }
        summary["runs"].append(entry)
        cert = make_certificate(
            "tammes",
            f"{n} points on S^{args.dim - 1}: minimal angle {angle:.7f} degrees",
            {"dim": args.dim, "points": _points_payload(points)},
            {"n_points": n, "dim": args.dim, "min_angle_deg": angle, "max_dot": res["max_dot"],
             "best_known_min_angle_deg": reference},
            _provenance(f"oplab sweep --target tammes --dim {args.dim} --n {n}", seed=args.seed + 13 * n,
                        seconds=args.seconds, workers=args.workers),
        )
        _write(out_dir / f"tammes_d{args.dim}_n{n:03d}.json", cert)
        gap = entry["gap_deg"]
        print(f"  n={n:3d} min_angle={angle:.7f}"
              + (f"  ref={reference:.7f}  gap={gap:+.5f}" if reference else ""))
    _write(out_dir / f"sweep_d{args.dim}_summary.json", {"schema_version": 1, **summary})
    return 0


# --------------------------------------------------------------------------
# sat
# --------------------------------------------------------------------------
def cmd_sat(args) -> int:
    if not (args.dimacs_only or args.benchmark_ingest) and not args.out:
        print("--out is required unless --dimacs-only or --benchmark-ingest is used", file=sys.stderr)
        return 2
    if args.dimacs_only:
        if not args.dimacs:
            print("--dimacs-only needs --dimacs PATH", file=sys.stderr)
            return 2
        instance = SAT.build_instance(args.n, args.k, args.symmetry)
        started = time.time()
        info = instance.write_dimacs(args.dimacs, comment=f"Ramsey K_{args.n}, k={args.k}, symmetry={args.symmetry}")
        size = Path(args.dimacs).stat().st_size
        print(
            f"{args.dimacs}: {info['clauses_written']} clauses, {info['num_vars']} vars, "
            f"{size / 1e6:.1f} MB, written in {time.time() - started:.1f}s"
        )
        return 0
    if args.benchmark_ingest:
        bench = SAT.ingestion_benchmark(args.n, args.k, args.symmetry)
        print(json.dumps(bench, indent=2))
        return 0
    res = SAT.solve(
        n=args.n,
        k=args.k,
        symmetry=args.symmetry,
        seconds=args.seconds,
        seed=args.seed,
        solver=args.solver,
        dimacs_path=args.dimacs,
    )
    status = res["status"]
    title = f"SAT encoding of K{args.n}, k={args.k}, symmetry={args.symmetry}: {status}"
    if status == "sat":
        red = R.parse(res["coloring"], args.n)
        count = R.count_mono_clique(red, args.n, args.k)
        cert = make_certificate(
            "ramsey",
            f"SAT witness for K{args.n}, k={args.k} (symmetry {args.symmetry}): no monochromatic K{args.k}",
            {"n": args.n, "k": args.k, "coloring": res["coloring"]},
            {"n": args.n, f"mono_k{args.k}": count},
            _provenance(
                f"oplab sat --n {args.n} --k {args.k} --symmetry {args.symmetry}",
                backend=res["backend"],
                seconds=res["seconds"],
                solver_stats=res.get("stats"),
            ),
        )
        _write(Path(args.out), cert)
        print(f"SAT: witness with {count} monochromatic K{args.k} (0 means a valid witness)")
        return 0
    if status == "unsat":
        cert = make_certificate(
            "ramsey_unsat",
            f"unsatisfiable: no 2-colouring of K{args.n} avoids a monochromatic K{args.k}"
            f" (symmetry {args.symmetry}, backend {res['backend']})",
            res,
            {"n": args.n, "k": args.k, "status": "unsat", "encoding": res["encoding"]},
            _provenance(
                f"oplab sat --n {args.n} --k {args.k} --symmetry {args.symmetry}",
                backend=res["backend"],
                seconds=res["seconds"],
                solver_stats=res.get("stats"),
            ),
        )
        _write(Path(args.out), cert)
        print(f"UNSAT after {res['seconds']:.1f}s (no DRAT proof is produced)")
        return 0
    if status == "no-solver":
        print("no SAT backend available: install z3-solver or put cadical/kissat on PATH", file=sys.stderr)
        return 2
    cert = make_certificate(
        "sat_attempt",
        title,
        res,
        {"n": args.n, "k": args.k, "status": "unknown", "encoding": res["encoding"]},
        _provenance(
            f"oplab sat --n {args.n} --k {args.k} --symmetry {args.symmetry}",
            backend=res["backend"],
            seconds=res["seconds"],
            solver_stats=res.get("stats"),
        ),
    )
    _write(Path(args.out), cert)
    stats = res.get("stats") or {}
    extra = " ".join(f"{key}={value:g}" for key, value in stats.items())
    print(f"unknown after {res['seconds']:.1f}s ({extra})")
    return 0


# --------------------------------------------------------------------------
# circulant
# --------------------------------------------------------------------------
def cmd_circulant(args) -> int:
    def progress(done, total):
        print(f"  {done}/{total} circulant colourings tested ({100 * done / total:.1f}%)", flush=True)

    res = R.circulant_search(args.n, k=args.k, workers=args.workers, progress=progress if args.verbose else None)
    cert = make_certificate(
        "circulant",
        f"exhaustive circulant sweep of K{args.n} for monochromatic K{args.k}: "
        f"{len(res['witnesses'])} witness(es) among {res['colourings_tested']} colourings",
        {
            "n": args.n,
            "k": args.k,
            "colourings_tested": res["colourings_tested"],
            "witnesses": [int(w) for w in res["witnesses"]],
            "seconds": res["seconds"],
            "workers": args.workers,
        },
        {"colourings_tested": res["colourings_tested"], "witnesses": len(res["witnesses"])},
        _provenance(f"oplab circulant --n {args.n} --k {args.k}", workers=args.workers),
    )
    _write(Path(args.out), cert)
    if res["witnesses"] and args.k == 5:
        mask = int(res["witnesses"][0])
        red = R.circulant_adjacency(args.n, mask)
        witness_cert = make_certificate(
            "ramsey",
            f"circulant witness: R(5,5) > {args.n}",
            {"n": args.n, "k": 5, "coloring": R.serialize(red, args.n)},
            {"n": args.n, "mono_k5": 0},
            _provenance(f"oplab circulant --n {args.n} --k {args.k}", witness_mask=mask,
                        seconds=res["seconds"], workers=args.workers),
        )
        witness_path = Path(args.out).with_name(Path(args.out).stem + "_witness.json")
        _write(witness_path, witness_cert)
    return 0


def cmd_solvers(args) -> int:
    """Report which engines answer, instead of which ones import.

    A wheel that imports but dies on its first clause is not an available engine:
    it costs a campaign slot and, before the crash path was fixed, wrote a
    `no_verdict` row that looked like a spent budget.  Exit status is non-zero
    when any probed engine failed, so a campaign can check this first.

    The `backing` column says which implementation answered under an engine's
    name — a real binary, a `python-sat` wheel, or nothing here — because
    `kissat404` is the version, not the implementation, and only one of the two
    implementations of it survives a two-clause instance on Windows.
    """
    rows = MC.probe_solvers(seconds=args.seconds, names=args.solver or None)
    width = max(len(row["solver"]) for row in rows)
    print(f"{'engine'.ljust(width)}  status     seconds  backing  detail")
    for row in rows:
        if row["status"] == "ok":
            detail = f"sat={row.get('sat_ok')} unsat={row.get('unsat_ok')}"
        elif row.get("exit_code") is not None:
            detail = f"exit={row.get('exit_code')}"
        else:
            detail = ""
        print(f"{row['solver'].ljust(width)}  {row['status']:<9}  "
              f"{row.get('seconds', 0.0):>7.3f}  {row.get('backend', 'wheel'):<7}  "
              f"{row.get('reason') or detail}")
    broken = [row["solver"] for row in rows if row["status"] != "ok"]
    if broken:
        print(f"\nnot answering: {', '.join(broken)}", file=sys.stderr)
        return 1
    return 0


def cmd_mc_circulant(args) -> int:
    """Decide one multicolour instance inside the circulant sub-family."""
    sizes = tuple(int(s) for s in args.sizes.split(","))
    if not args.dimacs_only and not args.out:
        print("--out is required unless --dimacs-only is used", file=sys.stderr)
        return 2
    if args.dimacs_only:
        if not args.dimacs:
            print("--dimacs-only needs --dimacs PATH", file=sys.stderr)
            return 2
        instance = MC.CirculantInstance(args.n, sizes)
        started = time.time()
        info = instance.write_dimacs(
            args.dimacs,
            comment=f"circulant multicolour Ramsey K_{args.n}, sizes={list(sizes)}",
        )
        size = Path(args.dimacs).stat().st_size
        print(
            f"{args.dimacs}: {info['clauses_written']} clauses, {info['num_vars']} vars, "
            f"{size / 1e6:.1f} MB, written in {time.time() - started:.1f}s"
        )
        return 0
    res = MC.circulant_solve(
        args.n, sizes, seconds=args.seconds, solver=args.solver, dimacs_path=args.dimacs,
        proof_path=args.proof,
    )
    if res.get("no_verdict"):
        # the worker died without sending a verdict (this is how the Kissat wheel
        # fails on Windows, with an access violation).  That is not a spent budget
        # and not an experiment result, so no certificate is written: a stored
        # `unknown` row has to mean "the budget ran out", or the frontier table
        # would be recording crashes as negatives.
        print(f"{args.solver} produced no verdict: the worker exited with "
              f"{res.get('exit_code')} (a crash, not a spent budget). Nothing written; "
              f"try another engine, e.g. --solver cadical195", file=sys.stderr)
        return 2
    instance = MC.CirculantInstance(args.n, sizes)
    if res.get("proof") and args.proof:
        # A trace is stored only after this repository's own checker has accepted
        # it, and the certificate records how long that replay took — which is also
        # what lets `verify` decide whether to replay it again by default.
        proof_file = res["proof"]["file"]
        replayed = DRAT.check_proof(instance.total_vars(), list(instance.clauses()),
                                    DRAT.read_proof(proof_file))
        if not replayed["ok"]:
            print(f"{proof_file}: the emitted trace does not check: {replayed['reason']}",
                  file=sys.stderr)
            return 1
        res["proof"]["replay_seconds"] = round(float(replayed["seconds"]), 2)
        # the trace is stored next to the certificate and named relative to it, so
        # the pair moves together
        rel = os.path.relpath(proof_file, Path(args.out).parent).replace(os.sep, "/")
        res["proof"]["file"] = rel
    payload = {
        "n": args.n,
        "sizes": list(sizes),
        "status": res["status"],
        "classes": len(instance.classes),
        "num_vars": instance.total_vars(),
        "num_clauses": instance.clause_count(),
        "clique_groups": {str(s): len(g) for s, g in instance.groups.items()},
        "solver": args.solver,
        "seconds": res["seconds"],
    }
    if res.get("budget_expired"):
        # say *why* there is no verdict, instead of leaving it to be inferred
        payload["budget_expired"] = True
    if res["status"] == "sat":
        payload["coloring"] = res["coloring"]
    if "proof" in res:
        payload["proof"] = res["proof"]
    if "obstruction" in res:
        payload["obstruction"] = {
            "class": res["obstruction"]["class"],
            "triangle": list(res["obstruction"]["triangle"]),
            "triangles": res["obstruction"]["triangles"],
        }
    claims = {"n": args.n, "sizes": list(sizes), "status": res["status"]}
    if res["status"] == "sat":
        counts = res["verified"]["monochromatic_cliques"]
        claims["monochromatic_cliques"] = counts
        claims["establishes"] = f"R{tuple(sizes)} > {args.n}"
    cert = make_certificate(
        "circulant_multicolour",
        f"circulant sub-family of K{args.n} with forbidden clique sizes {list(sizes)}: "
        f"{res['status']}",
        payload,
        claims,
        _provenance(f"oplab mc-circulant --n {args.n} --sizes {args.sizes}",
                    solver=args.solver),
    )
    _write(Path(args.out), cert)
    return 0


# --------------------------------------------------------------------------
# the CAYLEY sub-family: translation invariant over a named group
# --------------------------------------------------------------------------
def cmd_cayley(args) -> int:
    """Decide one group's translation-invariant colourings, as a certificate.

    The group is *named*, not described: ``--list`` prints the portfolio
    ``cayley.groups_of_order`` builds, and ``--group`` picks one of those names, so a
    certificate can be reproduced from its command line without retyping a nested
    direct-product description (and so the family in the file is the one this
    module builds, not whatever the caller remembered).  ``--portfolio`` widens the
    list to *every* group of that order, read from a file exported out of the GAP
    SmallGroups library (``data/smallgroups_<n>.json``) and rebuilt and re-counted
    here, so a group the named families do not cover can be decided by name too.

    ``unsat`` is stored *with* its DRAT trace, replayed here by ``oplab.drat``
    before the certificate is written; that replay is what makes the row a theorem
    about one group rather than a solver verdict.
    """
    groups = CY.load_portfolio(args.portfolio) if args.portfolio \
        else CY.groups_of_order(args.n)
    if groups and int(groups[0]["params"][0]) != args.n:
        print(f"{args.portfolio} holds groups of order {groups[0]['params'][0]}, "
              f"not {args.n}", file=sys.stderr)
        return 2
    if not groups:
        print(f"no group of order {args.n} is buildable here", file=sys.stderr)
        return 2
    if args.list:
        for description in groups:
            params = description["params"]
            print(f"{description['name']:<14} {description['family']:<13} {params}")
        return 0
    if not args.sizes:
        print("--sizes is required (or --list)", file=sys.stderr)
        return 2
    names = ", ".join(description["name"] for description in groups)
    if len(names) > 400:
        names = f"{names[:397]}... ({len(groups)} groups)"
    if not args.group:
        print(f"--group is required (or --list).  Groups of order {args.n}: {names}",
              file=sys.stderr)
        return 2
    chosen = [d for d in groups if d["name"] == args.group]
    if not chosen:
        print(f"no group named {args.group!r} of order {args.n}.  Available: {names}",
              file=sys.stderr)
        return 2
    description = chosen[0]
    sizes = tuple(int(s) for s in args.sizes.split(","))
    if not args.dimacs_only and not args.out:
        print("--out is required unless --dimacs-only is used", file=sys.stderr)
        return 2
    if args.dimacs_only:
        if not args.dimacs:
            print("--dimacs-only needs --dimacs PATH", file=sys.stderr)
            return 2
        instance = CY.CayleyInstance(description, sizes)
        info = instance.write_dimacs(
            args.dimacs,
            comment=f"cayley multicolour Ramsey K_{args.n}, sizes={list(sizes)}, "
                    f"group={description['name']}",
        )
        size = Path(args.dimacs).stat().st_size
        print(f"{args.dimacs}: {info['clauses_written']} clauses, {info['num_vars']} vars, "
              f"{size / 1e6:.1f} MB")
        return 0

    res = CY.cayley_solve(description, sizes, seconds=args.seconds, solver=args.solver,
                          proof_path=args.proof, dimacs_path=args.dimacs)
    if res["status"] in {"no_verdict", "no-solver", "error"}:
        # the worker died without a verdict, or no engine is bundled: that is not a
        # spent budget and not an experiment result, so nothing is written — a
        # stored `unknown` row has to mean "the budget ran out"
        print(f"{res['status']}: {res.get('reason', 'no verdict from ' + args.solver)} "
              f"(nothing written)", file=sys.stderr)
        return 2
    instance = CY.CayleyInstance(description, sizes)
    if res.get("proof") and args.proof:
        # A trace is stored only after this repository's own checker has accepted it
        # against this group's encoding, and the certificate records how long that
        # replay took — which is also what lets `verify` decide whether to replay it
        # again by default (and `drat-trim` is the second opinion on it).
        checked = CY.replay_proof(description, sizes, args.proof, Path(args.out).parent)
        if not checked["ok"]:
            print(f"{args.proof}: the emitted trace does not check: {checked['reason']}",
                  file=sys.stderr)
            return 1
        res["proof"] = {key: value for key, value in checked.items() if key != "ok"}
    payload = {
        "n": args.n,
        "sizes": list(sizes),
        "status": res["status"],
        "group": description,
        "classes": len(instance.classes),
        "num_vars": instance.total_vars(),
        "num_clauses": instance.clause_count(),
        "solver": args.solver,
        "seconds": res["seconds"],
        # the group as data (table, inverse list, clique groups): checked against
        # the description by `verify`, and what the Lean layer recomputes from
        **instance.certificate_payload(),
    }
    if res.get("budget_expired"):
        payload["budget_expired"] = True
    if res["status"] == "sat":
        payload["class_colors"] = {str(k): int(v) for k, v in res["class_colors"].items()}
        payload["coloring"] = res["coloring"]
    if "proof" in res:
        payload["proof"] = res["proof"]
    if "obstruction" in res:
        payload["obstruction"] = {
            "class_order": res["obstruction"]["class_order"],
            "triangle": list(res["obstruction"]["triangle"]),
            "triangles": res["obstruction"]["triangles"],
        }
    claims = {"n": args.n, "sizes": list(sizes), "status": res["status"]}
    if res["status"] == "sat":
        claims["monochromatic_cliques"] = res["verified"]["monochromatic_cliques"]
        claims["establishes"] = f"R{tuple(sizes)} > {args.n}"
    cert = make_certificate(
        "cayley_multicolour",
        f"translation-invariant colourings over {description['name']} "
        f"(a group of order {args.n}), forbidden clique sizes {list(sizes)}: "
        f"{res['status']}",
        payload,
        claims,
        _provenance(f"oplab cayley --n {args.n} --sizes {args.sizes} "
                    f"--group {description['name']}", solver=args.solver),
    )
    _write(Path(args.out), cert)
    return 0


# --------------------------------------------------------------------------
# drat
# --------------------------------------------------------------------------
def cmd_drat(args) -> int:
    """Check a DRAT trace against a CNF.  No solver is started here.

    Either give the pair explicitly (``--cnf`` and ``--proof``) or point at a
    certificate that records one (``--cert``): the CNF is then rebuilt from the
    certificate's own payload, so the trace is checked against the encoding the
    repository can regenerate — the circulant one or the group's, whichever family
    the certificate declares — and not against a stale file.
    """
    if args.cert:
        cert = json.loads(Path(args.cert).read_text(encoding="utf-8"))
        recorded = cert.get("payload", {}).get("proof")
        if not recorded:
            print(f"{args.cert}: no DRAT trace is recorded", file=sys.stderr)
            return 1
        instance = declared_instance(cert)
        num_vars, clauses = instance.total_vars(), list(instance.clauses())
        proof_path = Path(args.cert).parent / recorded["file"]
    elif args.cnf and args.proof:
        num_vars, clauses = DRAT.parse_dimacs(args.cnf)
        proof_path = Path(args.proof)
    else:
        print("give --cnf and --proof, or --cert", file=sys.stderr)
        return 2

    if not proof_path.exists():
        print(f"{proof_path}: no such proof", file=sys.stderr)
        return 1
    lines = DRAT.read_proof(proof_path)
    result = DRAT.check_proof(num_vars, clauses, lines)
    verdict = "VERIFIED" if result["ok"] else "REJECTED"
    print(
        f"{verdict}  {proof_path}  [{len(clauses)} clauses, {num_vars} vars, "
        f"{result.get('steps', len(lines))} steps, "
        f"{result.get('seconds', 0.0):.2f}s]"
    )
    print(f"  sha256 {DRAT.proof_digest(lines)}")
    if not result["ok"]:
        print(f"  {result.get('reason')}", file=sys.stderr)
        return 1
    if result.get("missing_deletions"):
        print(f"  note: {result['missing_deletions']} deletion(s) named a clause not present")
    return 0


# --------------------------------------------------------------------------
# verify / report
# --------------------------------------------------------------------------
def cmd_verify(args) -> int:
    failures = 0
    checked = 0
    for path in args.paths:
        for file, result in verify_path(Path(path), deep=args.deep, workers=args.workers):
            if result.get("skipped"):
                continue
            checked += 1
            ok = result.get("ok")
            mark = "PASS" if ok else "FAIL"
            establishes = result.get("establishes")
            extra = f"  [{establishes}]" if establishes else ""
            note = "" if ok else f"  <- {result.get('reason')}"
            print(f"{mark}  {file}{extra}{note}")
            if not ok:
                failures += 1
            elif args.write:
                cert = json.loads(Path(file).read_text(encoding="utf-8"))
                cert["verification"] = {
                    "verified": True,
                    "checks": result.get("checks"),
                    "establishes": establishes,
                    "tool": f"open-problems-lab {__version__}",
                }
                Path(file).write_text(json.dumps(cert, indent=2) + "\n", encoding="utf-8")
    print(f"\n{checked - failures}/{checked} certificates verified")
    return 1 if failures else 0


def cmd_report(args) -> int:
    rows = []
    for file, result in verify_path(Path(args.path), deep=False):
        if result.get("skipped"):
            continue
        try:
            cert = json.loads(Path(file).read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        rows.append({
            "file": str(file),
            "problem": cert.get("problem", "?"),
            "title": cert.get("title", ""),
            "ok": "yes" if result.get("ok") else "NO",
            "establishes": result.get("establishes") or "",
        })
    print("| certificate | problem | verified | establishes |")
    print("|---|---|---|---|")
    for row in rows:
        print(f"| `{row['file']}` | {row['problem']} | {row['ok']} | {row['establishes']} |")
    return 0


# --------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="oplab", description=__doc__.splitlines()[0])
    parser.add_argument("--version", action="version", version=f"open-problems-lab {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("build", help="write an exact classical certificate")
    p.add_argument("--kind", required=True, choices=["sphere", "unit-distance"])
    p.add_argument("--system", default="e8", help="sphere: a2, icosahedron, d4, d5, e6, e7, e8")
    p.add_argument("--name", default="moser", choices=["moser", "diamond", "hexagon"])
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("search", help="run a search and write a certificate")
    p.add_argument("--target", required=True, choices=["kissing", "tammes", "ramsey", "unitdist"])
    p.add_argument("--dim", type=int, default=3)
    p.add_argument("--n", type=int, required=True, help="number of points / vertices")
    p.add_argument("--seconds", type=float, default=60.0)
    p.add_argument("--workers", type=int, default=1)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--start-from", default=None, help="certificate whose points seed the search")
    p.add_argument("--start", default="edge", choices=["edge", "diamond", "moser"],
                   help="unitdist: seed graph for the random growth")
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("sweep", help="Tammes sweep over a range of N")
    p.add_argument("--target", default="tammes", choices=["tammes"])
    p.add_argument("--dim", type=int, default=3)
    p.add_argument("--n-min", type=int, required=True)
    p.add_argument("--n-max", type=int, required=True)
    p.add_argument("--seconds", type=float, default=60.0)
    p.add_argument("--workers", type=int, default=1)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--out-dir", required=True)
    p.set_defaults(func=cmd_sweep)

    p = sub.add_parser("sat", help="SAT encoding of the Ramsey colouring problem")
    p.add_argument("--n", type=int, required=True)
    p.add_argument("--k", type=int, default=5, help="clique size to avoid (5 for R(5,5))")
    p.add_argument("--symmetry", type=int, default=0, choices=list(SAT.SYMMETRY_LEVELS))
    p.add_argument("--seconds", type=float, default=60.0)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--solver", default="auto", help="auto, z3, or an external DIMACS binary")
    p.add_argument("--dimacs", default=None, help="also export the instance to this DIMACS path")
    p.add_argument("--dimacs-only", action="store_true", help="only export DIMACS, do not solve")
    p.add_argument("--benchmark-ingest", action="store_true", help="measure clause ingestion speed")
    p.add_argument("--out", default=None, help="certificate path (required unless exporting only)")
    p.set_defaults(func=cmd_sat)

    p = sub.add_parser("circulant", help="exhaustive circulant sweep of K_n")
    p.add_argument("--n", type=int, required=True)
    p.add_argument("--k", type=int, default=5)
    p.add_argument("--workers", type=int, default=1)
    p.add_argument("--verbose", action="store_true")
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_circulant)

    p = sub.add_parser("mc-circulant", help="decide the circulant sub-family of a multicolour instance")
    p.add_argument("--n", type=int, required=True)
    p.add_argument("--sizes", required=True, help="forbidden clique size per colour, e.g. 3,3,5")
    p.add_argument("--seconds", type=float, default=300.0)
    p.add_argument("--solver", default="cadical195")
    p.add_argument("--dimacs", default=None, help="also export the instance to this DIMACS path")
    p.add_argument("--dimacs-only", action="store_true", help="only export DIMACS, do not solve")
    p.add_argument("--proof", default=None,
                   help="write the DRAT trace of an unsat run here; the name says "
                        "the container: .drat/.bdrat (binary DRAT), optionally "
                        ".gz or .xz")
    p.add_argument("--out", default=None, help="certificate path (required unless exporting only)")
    p.set_defaults(func=cmd_mc_circulant)

    p = sub.add_parser("cayley", help="decide one group's translation-invariant colourings")
    p.add_argument("--n", type=int, required=True, help="order of the group")
    p.add_argument("--sizes", default=None,
                   help="forbidden clique size per colour, e.g. 4,4 or 3,3,4 "
                        "(required unless --list)")
    p.add_argument("--group", default=None, help="which group of that order (see --list)")
    p.add_argument("--portfolio", default=None,
                   help="pick the group from an exported library instead of the named "
                        "families: data/smallgroups_<n>.json (see --list)")
    p.add_argument("--list", action="store_true", help="print the portfolio and exit")
    p.add_argument("--seconds", type=float, default=300.0)
    p.add_argument("--solver", default="cadical195")
    p.add_argument("--dimacs", default=None, help="also export the reduced CNF to this path")
    p.add_argument("--dimacs-only", action="store_true", help="only export the CNF, do not solve")
    p.add_argument("--proof", default=None,
                   help="write the DRAT trace of an unsat run here; the name says the "
                        "container: .drat/.bdrat (binary DRAT), optionally .gz or .xz")
    p.add_argument("--out", default=None, help="certificate path (required unless exporting only)")
    p.set_defaults(func=cmd_cayley)

    p = sub.add_parser("solvers", help="probe the bundled SAT engines and report who answers")
    p.add_argument("--seconds", type=float, default=10.0, help="budget per engine")
    p.add_argument("--solver", action="append", default=None,
                   help="probe only this engine (repeatable)")
    p.set_defaults(func=cmd_solvers)

    p = sub.add_parser("drat", help="check a DRAT proof against a CNF")
    p.add_argument("--cnf", default=None, help="DIMACS CNF the trace was produced from")
    p.add_argument("--proof", default=None,
                   help="DRAT trace to check; the name says the container: "
                        ".drat/.bdrat (binary DRAT), optionally .gz or .xz")
    p.add_argument("--cert", default=None,
                   help="a certificate that records the trace, instead of a CNF")
    p.set_defaults(func=cmd_drat)

    p = sub.add_parser("verify", help="verify certificates")
    p.add_argument("paths", nargs="+")
    p.add_argument("--deep", action="store_true", help="re-run exhaustive sweeps")
    p.add_argument("--workers", type=int, default=1)
    p.add_argument("--write", action="store_true", help="record the verification back into the file")
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("report", help="markdown table of certificates")
    p.add_argument("--path", default="certs")
    p.set_defaults(func=cmd_report)
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
