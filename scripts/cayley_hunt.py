#!/usr/bin/env python3
"""Hunt for witnesses among translation-invariant colourings of *groups*.

The circulating sweep decides the cyclic case.  Every other group of order ``n``
gives a different family of constructions, and a witness in any of them is a
witness for the whole problem — a colouring of ``K_n`` with no monochromatic
forbidden clique, re-counted by :func:`oplab.multicolour.verify_colouring`, not by
this script's solver.

    python scripts/cayley_hunt.py 96:3,3,3,4 128:4,4,4 --seconds 300 --workers 12

A ``sat`` row is written out in full (the per-class assignment and the expanded
colouring string) because that is the artifact worth keeping; an ``unsat`` row is
a verdict about that single group; an ``unknown`` row is a spent budget.  The
scrip also checks the group axioms of every table it is about to search, so a
hand-derived family that is wrong fails loudly instead of quietly searching a
non-group.

Given ``--proof-dir`` (and ``--cert-dir``) the CDCL mode does more than report a
verdict: the solver writes its DRAT trace, this script replays that trace against
the group's own encoding with :func:`oplab.cayley.replay_proof` — no solver in the
loop — and only then stores a ``cayley_multicolour`` certificate, so an ``unsat``
row leaves this script as a theorem about that group instead of a verdict.  The
traces land in ``--proof-dir`` and are named after the group, and ``--cnf-dir``
exports the reduced CNF of every decided group beside them (the same clauses
``drat-trim`` is handed by ``scripts/drat_trim_check.py``, and the artifact to
point a full-strength solver at).
"""

from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from oplab import cayley as C  # noqa: E402
from oplab.verify import make_certificate, verify_certificate  # noqa: E402


def write_certificate(row: dict, out_dir: Path) -> Path:
    """Store a decided row as a `cayley_multicolour` certificate, after checking it.

    The file is only written if this repository's own verifier accepts it, so a
    certificate in ``certs/`` is never a solver's word: the group table, the classes,
    the encoding size and the colouring are all re-derived from the payload when it
    is read back, and for an ``unsat`` row the recorded DRAT trace is replayed
    against that group's encoding.  A witness is named after the target (there is one
    colouring to keep); a decision about a group is named after the group as well,
    because *which* group was decided is the whole content of the row.
    """
    sizes = list(row["sizes"])
    group = row["group"]
    status = row["status"]
    instance = C.CayleyInstance(group, sizes)
    payload = {
        "n": row["n"],
        "sizes": sizes,
        "status": status,
        "group": group,
        "classes": row["classes"],
        "num_vars": row["num_vars"],
        "num_clauses": row["num_clauses"],
        # the group as data, checked against the description when the row is read
        # back (and the object the Lean layer recomputes the encoding from)
        **instance.certificate_payload(),
    }
    if status == "sat":
        payload["class_colors"] = {str(k): int(v) for k, v in row["class_colors"].items()}
        payload["coloring"] = row["coloring"]
    if row.get("proof"):
        payload["proof"] = row["proof"]
    claims = {"n": row["n"], "sizes": sizes, "status": status}
    if status == "sat":
        claims["monochromatic_cliques"] = row["verified"]["monochromatic_cliques"]
    cert = make_certificate(
        "cayley_multicolour",
        f"K{row['n']} {sizes} over {group.get('name', group['family'])}: {status}",
        payload,
        claims,
        {"generator": f"scripts/cayley_hunt.py {row['n']}:{','.join(map(str, sizes))} "
                      f"--group {group.get('name')}",
         "created": time.strftime("%Y-%m-%d"),
         "solver": row.get("solver", "repair")},
    )
    check = verify_certificate(cert, base_dir=out_dir)
    if not check["ok"]:
        raise SystemExit(f"refusing to store a row that does not verify: {check['reason']}")
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"k{row['n']}_{'x'.join(map(str, sizes))}"
    if status != "sat":
        stem += f"_{group.get('name', group['family'])}"
    path = out_dir / f"{stem}.json"
    path.write_text(json.dumps(cert, indent=2) + "\n", encoding="utf-8")
    return path


def _proof_filename(n: int, sizes, group: dict) -> str:
    return f"k{n}_{'x'.join(map(str, sizes))}_{group.get('name', group['family'])}.bdrat.xz"


def _group_worker(conn, job: dict) -> None:  # pragma: no cover - child process
    """Solve one group inline, in a process the parent can kill."""
    try:
        if job.get("mode") == "repair":
            # the repair races its own budget, so it is given slightly less than the
            # parent's, and returns its best attempt instead of being killed
            result = C.repair(job["group"], job["sizes"],
                              seconds=max(1.0, job["seconds"] * 0.9), seed=job.get("seed", 0))
        else:
            result = C.solve_inline(job["group"], job["sizes"], job["solver"],
                                    job.get("proof_path"))
    except Exception as exc:
        result = {"status": "error", "reason": f"{exc.__class__.__name__}: {exc}"}
    # a row is about one instance whatever the engine made of it: the identity and
    # the size of the encoding travel with the row, so a refused, crashed or
    # budget-killed run still says what it searched, and the parent never has to
    # guess which job a row came from (the repair engine's summary and the CDCL
    # one's differ, and an error row has none)
    if job.get("n") is not None:
        result.setdefault("n", job["n"])
    if job.get("sizes") is not None:
        result.setdefault("sizes", list(job["sizes"]))
    if job.get("group") is not None:
        result.setdefault("group", job["group"])
    result["name"] = job["group"].get("name") or job["group"]["family"]
    try:
        conn.send(result)
    finally:
        conn.close()


def _run_batch(ctx, jobs: list[dict], seconds: float, solver: str) -> list[dict]:
    """Run one job per process, all at once, each with its own external budget.

    One process per group rather than a pool: a pooled worker is daemonic and may
    not spawn, and the only budget mechanism that actually bounds a bundled solver
    is a child the parent can kill.
    """
    handles = []
    for job in jobs:
        parent, child = ctx.Pipe(duplex=False)
        # the budget travels *with* the job as well: the repair engine races its own
        # clock (`seconds * 0.9`), so a child that is handed no budget cannot run at
        # all — it used to raise KeyError: 'seconds' instead of hunting
        proc = ctx.Process(target=_group_worker,
                           args=(child, {**job, "solver": solver, "seconds": seconds}),
                           daemon=False)
        started = time.time()
        proc.start()
        handles.append((job, proc, parent, started))
    def identity(status: str, **extra) -> dict:
        """A row for a run that leaves no summary of its own.

        The identity and the encoding size travel with it, because an anonymous row
        is not evidence, and a killed or crashed engine has nothing else to say
        about what it actually searched.
        """
        return {"name": job["group"]["name"], "group": job["group"],
                "status": status,
                **C.CayleyInstance(job["group"], job["sizes"]).summary(),
                "seconds": round(time.time() - started, 3), **extra}

    rows: list[dict] = []
    for job, proc, parent, started in handles:
        proc.join(max(0.0, seconds - (time.time() - started)))
        if proc.is_alive():
            proc.terminate()
            proc.join(10)
            if proc.is_alive() and hasattr(proc, "kill"):  # pragma: no cover - defensive
                proc.kill()
            parent.close()
            rows.append(identity("unknown", budget_expired=True))
            continue
        # an engine that dies *hard* — a segfault inside a bundled solver, say —
        # closes the pipe without sending anything, and reading it then raises:
        # a broken engine has to cost one row, not the rows already decided
        try:
            reported = parent.poll(10)
        except OSError:  # pragma: no cover - depends on the engine crashing
            reported = False
        if reported:
            try:
                row = parent.recv()
            except (EOFError, OSError):  # pragma: no cover - race with a dying child
                row = None
            parent.close()
            if row is None:
                row = identity("no_verdict", exit_code=proc.exitcode)
            else:
                row["group"] = job["group"]
                row["seconds"] = round(time.time() - started, 3)
            rows.append(row)
        else:
            parent.close()
            rows.append(identity("no_verdict", exit_code=proc.exitcode))
    if rows and all(row["status"] == "no_verdict" for row in rows):
        print("  every child died without a verdict: an engine that does not answer "
              "here is not a result — `oplab solvers` reports which ones do",
              file=sys.stderr, flush=True)
    return rows


def _record_decision(row: dict, proof_path: Path | None, cert_dir: Path | None,
                     cnf_dir: Path | None) -> None:
    """Replay a trace for an ``unsat`` row, and export the CNF it refutes.

    The trace comes from the solver, so it is worth nothing until this repository's
    own checker has replayed it against the encoding rebuilt here from the group
    description (:func:`oplab.cayley.replay_proof`): a partial trace from a killed
    run, or one produced for another group, is dropped with a warning instead of
    being attached to a certificate.  Whatever survives is stored beside the
    certificate, named relative to it, and the row is what
    :func:`write_certificate` then records.
    """
    group, sizes = row["group"], row["sizes"]
    if row["status"] != "unsat":
        return
    if proof_path is None and cnf_dir is None:
        row["note"] = "verdict without a DRAT trace: not a theorem, nothing stored"
        return
    if cnf_dir is not None:
        cnf = Path(cnf_dir) / f"k{row['n']}_{'x'.join(map(str, sizes))}_{group['name']}.cnf"
        cnf.parent.mkdir(parents=True, exist_ok=True)
        C.CayleyInstance(group, sizes).write_dimacs(
            cnf, comment=f"cayley multicolour Ramsey K_{row['n']} over {group['name']}"
        )
        row["cnf"] = str(cnf)
    if proof_path is None or not Path(proof_path).exists():
        row["note"] = "no DRAT trace was written, so this row stays a verdict"
        return
    checked = C.replay_proof(group, sizes, proof_path, base_dir=cert_dir)
    if not checked.pop("ok"):
        print(f"  {row['name']}: the emitted trace does not check "
              f"({checked.get('reason')}), so no proof is recorded", file=sys.stderr, flush=True)
        row["note"] = f"the emitted trace does not check: {checked.get('reason')}"
        return
    row["proof"] = checked


def hunt(n: int, sizes, seconds: float, workers: int, solver: str = "cadical195",
         only=None, mode: str = "cdcl", seed: int = 0, proof_dir=None, cnf_dir=None,
         cert_dir=None) -> list[dict]:
    groups = C.groups_of_order(n)
    if only:
        groups = [g for g in groups if g["name"] in only]
    if not groups:
        raise SystemExit(f"no groups of order {n} to search")
    rows: list[dict] = []
    for description in groups:
        table, inverse = C.group_from_description(description)
        check = C.verify_group(table, inverse)
        if not check["ok"]:
            raise SystemExit(f"{description['name']}: not a group ({check['reason']})")
        if len(table) != n:
            # the order travels with the job as `n`, and every row is identified by
            # it: a table of the wrong order would make those rows lie
            raise SystemExit(f"{description['name']}: the table has order {len(table)}, "
                             f"not {n}")
    print(f"K{n} {tuple(sizes)}: {len(groups)} groups "
          f"({', '.join(g['name'] for g in groups)}) x {seconds:.0f} s [{mode}]"
          + ("  [recording proofs]" if proof_dir else ""), flush=True)
    ctx = mp.get_context("spawn")
    pending = []
    for group in groups:
        job: dict = {"group": group, "sizes": list(sizes), "mode": mode, "seed": seed,
                     "n": n}
        if proof_dir and mode != "repair":
            # the child writes the trace straight to disk: it is the artifact the
            # parent then replays, and a name that says which group it is
            # worthwhile for is what keeps it from being mistaken for another row's
            path = Path(proof_dir) / _proof_filename(n, sizes, group)
            path.parent.mkdir(parents=True, exist_ok=True)
            job["proof_path"] = str(path)
            job["proof_file"] = path
        pending.append(job)
    while pending:
        batch, pending = pending[:workers], pending[workers:]
        found = False
        for job, result in zip(batch, _run_batch(ctx, batch, seconds, solver)):
            rows.append(result)
            proof_file = job.get("proof_file")
            if proof_file is not None and not Path(proof_file).exists():
                proof_file = None
            _record_decision(result, proof_file, Path(cert_dir) if cert_dir else None,
                             cnf_dir)
            print(f"  {result['name']:<14} {result['status']:<8} "
                  f"{result.get('num_vars', '-')} vars, {result['seconds']} s"
                  + (f"  -> {result['verified']['establishes']}" if result["status"] == "sat" else "")
                  + (f"  [proof {result['proof']['steps']} steps, "
                     f"{result['proof']['replay_seconds']} s replay]"
                     if result.get("proof") else "")
                  + (f"  <- {result['reason']}" if result.get("reason") else ""),
                  flush=True)
            found = found or result["status"] == "sat"
        if found:
            break
    sat = [r for r in rows if r["status"] == "sat"]
    if sat:
        print(f"K{n} {tuple(sizes)}: WITNESS over {sat[0]['name']} -> "
              f"{sat[0]['verified']['establishes']}", flush=True)
    else:
        counts: dict[str, int] = {}
        for row in rows:
            counts[row["status"]] = counts.get(row["status"], 0) + 1
        print(f"K{n} {tuple(sizes)}: no witness {counts}", flush=True)
    return rows


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("spec", nargs="+", help="targets as n:s1,s2,...")
    parser.add_argument("--seconds", type=float, default=300.0)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--solver", default="cadical195")
    parser.add_argument("--group", action="append", default=None,
                        help="search only this group (repeatable)")
    parser.add_argument("--mode", default="cdcl", choices=["cdcl", "repair"],
                        help="cdcl decides (and can prove); repair hunts for a witness")
    parser.add_argument("--json", default=None, help="write the rows here")
    parser.add_argument("--cert-dir", default=None,
                        help="store every decided row here, as a checked certificate")
    parser.add_argument("--proof-dir", default=None,
                        help="write the DRAT trace of each unsat row here, and replay "
                             "it before storing the certificate (needs --cert-dir)")
    parser.add_argument("--cnf-dir", default=None,
                        help="export the reduced CNF of every decided group here, for "
                             "a full-strength solver")
    args = parser.parse_args(argv)
    if args.proof_dir and not args.cert_dir:
        print("--proof-dir stores traces to be cited by certificates: give --cert-dir too",
              file=sys.stderr)
        return 2
    if args.proof_dir and args.mode == "repair":
        print("--proof-dir needs --mode cdcl: the repair engine produces no verdict to "
              "prove", file=sys.stderr)
        return 2

    results: list[dict] = []
    started = time.time()
    for spec in args.spec:
        n_text, _, sizes_text = spec.partition(":")
        if not sizes_text:
            print(f"{spec}: expected n:s1,s2,...", file=sys.stderr)
            return 2
        rows = hunt(int(n_text), tuple(int(s) for s in sizes_text.split(",")),
                    args.seconds, args.workers, args.solver, args.group, args.mode,
                    proof_dir=args.proof_dir, cnf_dir=args.cnf_dir,
                    cert_dir=args.cert_dir)
        results.extend(rows)
        if args.cert_dir:
            for row in rows:
                # a witness is stored on its own, and so is a proof-carrying `unsat`
                # row; an `unsat` row whose trace did not check, or was never
                # written, has nothing to store — and the verifier would refuse it
                if row["status"] == "sat" or (row["status"] == "unsat" and row.get("proof")):
                    print(f"  stored {write_certificate(row, Path(args.cert_dir))}", flush=True)
    if args.json:
        Path(args.json).write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\n{len(results)} group runs in {time.time() - started:.0f} s; "
          f"{sum(1 for r in results if r['status'] == 'sat')} witnesses", flush=True)
    return 0


if __name__ == "__main__":  # pragma: no cover - the children are spawned
    sys.exit(main())
