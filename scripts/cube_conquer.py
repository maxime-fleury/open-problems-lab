#!/usr/bin/env python3
"""Decide one instance by cube-and-conquer: partition it, then refute each part.

A CDCL solver on a multicolour frontier instance spends a long budget and returns
``unknown`` (``certs/circulant_multicolour/`` records six of those).  The reason is
rarely the solver: it is that the instance is one huge search tree with no guidance
at the top.  Cube-and-conquer replaces the top of that tree with an explicit
look-ahead partition — Marijn Heule's ``march_cu`` — and then lets a fast CDCL
solver refute the leaves one by one::

    python scripts/cube_conquer.py 97:3,3,3,4 --depth 12 --budget 60 --workers 16 \\
        --out runs/cube_k97.json

What a run means is decided by two independent things, and both are reported:

* *the cover* — the cubes are checked to be a **complete decision tree**, by the
  trie test in :func:`cube_cover`: every internal node branches on exactly one
  variable, both ways, and every leaf is one of the cubes.  A cover with a hole in
  it says nothing, however many leaves were refuted, so this is checked here from
  the cube list itself rather than taken from the cuber's word — which is why a
  cube file that was filtered, truncated or written by hand becomes ``incomplete``
  instead of a refutation.
* *the leaves* — each cube is refuted (or satisfied) by the engine, one process per
  cube so that ``--budget`` is a real boundary, in parallel across ``--workers``.  A
  ``sat`` leaf is decoded with the repository's own instance class and re-counted by
  :func:`oplab.multicolour.verify_colouring` before it is called a witness; a
  witness that does not verify is a failure of this script, not a result.

The verdict says what was actually established:

``sat``
    A leaf with a model, decoded and verified: a colouring of ``K_n`` exists in the
    circulant family, and the ``witness.verify`` block is the re-count.
``refuted-cover``
    Every leaf was refuted and the cover closes: that CNF is unsatisfiable — as far
    as the engine's *verdicts* go, which is not a proof and is not reported as one.
    The honest next step is to re-refute the same leaves with an engine that emits
    a DRAT trace and replay it here, which turns the row into a theorem about the
    cover rather than a run of agreements.
``refuted-fragment``
    The same, for a cube list handed in with ``--cubes`` that is a fragment of a
    cover rather than one: every leaf in the file is refuted, which is a piece of
    the answer and is reported as a piece.
``incomplete``
    Some leaf is undecided (its budget ran out, or the engine said nothing) or the
    cover does not close.  Nothing is claimed, and the undecided cubes are written
    out for a second pass with a larger budget:

        python scripts/cube_conquer.py 97:3,3,3,4 --cubes runs/cube_k97_unresolved.icnf \\
            --budget 600 --out runs/cube_k97_resumed.json

A second pass is itself a *fragment*, so it cannot report the refutation the two
passes made together.  ``--combine`` is that step, and it is a check rather than a
sum: it reads the reports back, re-runs the cover test on the complete cube file,
re-reads every pass's rows from disk, and refuses the claim unless the leaves of
that cover are *exactly* the cubes the passes decided, each one refuted:

    python scripts/cube_conquer.py 97:3,3,3,4 --combine runs/cube_k97_d12.json \\
        runs/cube_k97_d12_pass2.json --out runs/cube_k97_cnc.json

Exit codes: 0 when a witness verified or a fragment/cover was refuted, 1 when a
witness failed verification, a worker misbehaved or two passes disagreed about a
leaf, 2 when the run is incomplete, the cover is open, or a tool is missing.
"""

from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from oplab import multicolour as MC  # noqa: E402
from oplab import tools  # noqa: E402

#: How a cube file marks a cube: ``march_cu`` writes ``a <lits> 0``, and an iCNF
#: written by hand or by another tool may write the literals bare.
CUBE_MARKER = "a "

#: The statuses that are answers about a leaf.  ``unknown`` is the absence of one — a
#: budget that ran out — so a later pass is free to have an opinion where an earlier
#: one had none, and only two answers that disagree are a contradiction.
VERDICTS = ("unsat", "sat")


# --------------------------------------------------------------------------
# cubes: reading them, writing them, and closing them
# --------------------------------------------------------------------------
def report_path(text) -> Path:
    """A path out of a report, as a path the machine reading the report can open.

    A report carries the paths of the machine that wrote it, and a Windows report
    writes backslashes: ``runs\\cube_k97_d12\\k97_d12.icnf`` is a single file *name*
    on Linux, so a committed report re-read anywhere — by ``--combine`` in CI, say —
    would look for a file that cannot exist.  Only separators are rewritten: an
    absolute Windows path stays one, because on another machine it names where the
    input was rather than something that can be re-read, and saying so is better
    than silently looking for ``D:/gen/...``.
    """
    text = str(text)
    if text.startswith("/"):
        return Path(text)
    return Path(text.replace("\\", "/"))


def read_cubes(path) -> list[list[int]]:
    """The cubes of a ``march_cu`` output, or of any DIMACS/iCNF cube file.

    A comment, a header or a solver's answer is not a cube; a cube is the literals
    before the trailing ``0``.  Reading defensively matters because this file is an
    *input*: a cube file that was edited is a cube file whose cover may not close,
    and :func:`cube_cover` is what catches that.
    """
    cubes: list[list[int]] = []
    for line in Path(path).read_text(encoding="ascii").splitlines():
        text = line.strip()
        if not text or text[0] in "cp":
            continue
        if text.startswith(CUBE_MARKER):
            text = text[len(CUBE_MARKER):]
        literals: list[int] = []
        for token in text.split():
            try:
                value = int(token)
            except ValueError:
                literals = []
                break
            if value == 0:
                break
            literals.append(value)
        if literals:
            cubes.append(literals)
    return cubes


def write_cubes(path, cubes: list[list[int]]) -> Path:
    """Write cubes in the ``march_cu`` shape, so a second pass can read them."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="ascii", newline="\n") as handle:
        for cube in cubes:
            handle.write(f"{CUBE_MARKER}{' '.join(map(str, cube))} 0\n")
    return path


def cube_cover(cubes: list[list[int]]) -> dict:
    """Whether a cube list is a *complete* decision tree.

    The leaves of a look-ahead tree are paths, so a list of them covers every
    assignment exactly when the trie over those paths is full: each internal node
    has two children, the same variable with opposite signs, every leaf is one of
    the cubes, and the cubes are all the same length.  A missing leaf, a cube that
    lists a variable twice, and two cubes that branch on different variables at the
    same depth all come back as ``complete: False`` with the reason — which is what
    stands between "every leaf I looked at was refuted" and "the instance is
    refuted".
    """
    result: dict = {"complete": False, "cubes": len(cubes), "leaves": 0, "depth": 0}
    if not cubes:
        return {**result, "reason": "there are no cubes"}
    result["depth"] = max(len(cube) for cube in cubes)
    root: dict = {}
    for cube in cubes:
        variables = [abs(literal) for literal in cube]
        if len(set(variables)) != len(variables):
            return {**result, "reason": f"a cube repeats a variable: {cube}"}
        if len(cube) != result["depth"]:
            return {**result, "reason": f"cubes of different lengths: {cube}"}
        node = root
        for literal in cube:
            node = node.setdefault(literal, {})
    stack = [root]
    while stack:
        node = stack.pop()
        if not node:
            result["leaves"] += 1
            continue
        children = set(node)
        if len(children) != 2 or -max(children) not in children:
            # a leaf was dropped, or two cubes disagree about the variable they branch
            # on: either way this is not a decision tree, and the count of complete
            # leaves found so far is the useful part of the complaint
            return {**result,
                    "reason": (f"a node does not branch on one variable, both ways: it has "
                               f"{len(children)} child(ren), and {result['leaves']} complete "
                               f"leaves were found")}
        stack.extend(node.values())
    result["complete"] = result["leaves"] == len(cubes) == 2 ** result["depth"]
    if not result["complete"]:
        return {**result, "reason": f"{result['leaves']} leaves for {len(cubes)} cubes "
                                    f"at depth {result['depth']}"}
    return result


# --------------------------------------------------------------------------
# the solver side
# --------------------------------------------------------------------------
def open_engine(engine: str, clauses, budget: float):
    """The engine behind a name, carrying the budget this script promises per cube.

    The binary Kissat takes its budget as a subprocess timeout, so ``--budget`` is a
    real per-cube boundary.  A ``python-sat`` wheel cannot take one — a solver holds
    the interpreter for the whole run — so for a wheel-backed engine the budget only
    applies to the whole shard, through ``--seconds``; ``--engine-backing`` exists to
    refuse that silently happening.
    """
    if engine == "kissat404" and MC.solver_backing(engine) == "binary":
        return MC.KissatBinary(bootstrap_with=clauses, timeout=budget)
    return MC.solver_class(engine)(bootstrap_with=clauses, use_timer=True)


def read_rows(rows_dir) -> list[dict]:
    """Every row a run left in a ``rows/`` directory, in shard order.

    The rows are the run's own record of what happened to each leaf, which is why
    :func:`combine_reports` reads them back from disk instead of trusting the
    summary a report carries.
    """
    rows: list[dict] = []
    for path in sorted(Path(rows_dir).glob("shard_*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _shard_worker(conn, job: dict) -> None:  # pragma: no cover - child process
    """Refute (or satisfy) the cubes of one shard.

    The parent may kill this process, so every cube is written out as soon as it is
    decided: a killed shard still leaves the rows it produced, and the parent never
    has to guess what happened to it.  The first ``sat`` sets the stop flag, so the
    other shards do not keep refuting leaves after a witness exists.
    """
    summary = {"shard": job["shard"], "cubes": len(job["cubes"]), "unsat": 0, "sat": 0,
               "unknown": 0, "error": 0, "seconds": 0.0}
    witness = None
    handle = open(job["rows"], "a", encoding="utf-8")
    # the clauses are *rebuilt* here rather than shipped: twenty-one thousand clauses
    # through a spawn pipe is a two-megabyte pickle per shard, and the parent pays for
    # it serially (measured: 64 cubes at a 5 s budget took 111 s of wall clock instead
    # of 45 s, almost all of it in that hand-off)
    clauses = [[int(literal) for literal in clause]
               for clause in MC.CirculantInstance(job["n"], job["sizes"]).clauses()]
    try:
        for index, cube in job["cubes"]:
            if job["stop"].is_set():
                break
            started = time.time()
            row = {"index": index, "cube": list(cube)}
            try:
                with open_engine(job["engine"], clauses, job["budget"]) as solver:
                    verdict = solver.solve(assumptions=cube)
                    row["solver_seconds"] = round(solver.time(), 3)
                    if verdict is True:
                        row["status"] = "sat"
                        row["model"] = list(solver.get_model())
                    elif verdict is False:
                        row["status"] = "unsat"
                    else:
                        row["status"] = "unknown"
                        row["note"] = getattr(solver, "note", "") or "no verdict"
            except Exception as exc:
                row["status"] = "error"
                row["note"] = f"{exc.__class__.__name__}: {exc}"
            row["seconds"] = round(time.time() - started, 3)
            summary[row["status"]] = summary.get(row["status"], 0) + 1
            summary["seconds"] = round(summary["seconds"] + row["seconds"], 3)
            handle.write(json.dumps(row) + "\n")
            handle.flush()
            if row["status"] == "sat":
                witness = row
                job["stop"].set()
                break
    finally:
        handle.close()
    try:
        conn.send({**summary, "witness": witness})
    finally:
        conn.close()


def run_shards(n: int, sizes, shards: list[list], engine: str, budget: float,
               rows_dir: Path, seconds: float | None = None) -> dict:
    """Solve every shard in its own process, all at once.

    One process per shard rather than a pool: pooled workers are daemonic and may
    not spawn, and the only mechanism that actually bounds an external engine is a
    child the parent can kill.  ``seconds`` is a whole-run ceiling shared by the
    shards; without it the ceiling is the sum of their own work.
    """
    ctx = mp.get_context("spawn")
    stop = ctx.Event()
    started = time.time()
    deadline = None if seconds is None else started + float(seconds)
    handles = []
    for number, cubes in enumerate(shards):
        if not cubes:
            continue
        parent, child = ctx.Pipe(duplex=False)
        job = {"shard": number, "cubes": cubes, "n": n, "sizes": list(sizes),
               "engine": engine, "budget": budget,
               "rows": str(rows_dir / f"shard_{number:03d}.jsonl"), "stop": stop}
        proc = ctx.Process(target=_shard_worker, args=(child, job), daemon=False)
        proc.start()
        handles.append({"shard": number, "process": proc, "pipe": parent})
    summaries = []
    for handle in handles:
        proc = handle["process"]
        remaining = None if deadline is None else max(0.0, deadline - time.time())
        proc.join(remaining)
        if proc.is_alive():
            proc.terminate()
            proc.join(10)
            if proc.is_alive() and hasattr(proc, "kill"):  # pragma: no cover - defensive
                proc.kill()
        sent = None
        if handle["pipe"].poll(10):
            try:
                sent = handle["pipe"].recv()
            except EOFError:  # pragma: no cover - defensive
                sent = None
        if sent is None:
            sent = {"shard": handle["shard"], "unreported": True}
        summaries.append({**sent, "killed": not sent.get("witness") and proc.exitcode not in (0, None)})
        handle["pipe"].close()
    return {"seconds": round(time.time() - started, 1), "summaries": summaries,
            "rows_dir": str(rows_dir)}


# --------------------------------------------------------------------------
# combining passes: a cover from one run, fragments from the rest
# --------------------------------------------------------------------------
def combine_reports(report_paths: list[str]) -> dict:
    """Several passes over one instance, read back as the one claim they add up to.

    A pass that resumes from the undecided leaves of a cover cannot report a
    refutation of the instance — its cube list is a fragment — and a cover that was
    only *partly* refuted cannot either.  Together they can, and this is the step
    that decides whether they do, by check rather than by arithmetic on the
    summaries: the complete cube file is re-read and re-tested as a decision tree,
    each pass's rows are re-read from disk, and the claim is refused unless those
    rows are exactly a refutation of every leaf of that cover.  A cube a pass
    decided that is *not* a leaf of the cover, and a leaf no pass decided, are each
    their own refusal — and so is one pass answering ``sat`` where another answered
    ``unsat``.  A pass that said nothing (a budget that ran out) is not a
disagreement: that is the case this exists for, and the verdict stands.

    What comes out is the same report shape a run writes, with the passes it was
    built from in ``sources`` — so the claim's evidence is in the artifact.
    """
    reports: list[dict] = []
    for path in report_paths:
        text = Path(path).read_text(encoding="utf-8")
        reports.append(json.loads(text))
    if not reports:
        return {"verdict": "incomplete", "establishes": "nothing: no report was given"}

    order, sizes = int(reports[0]["n"]), list(reports[0]["sizes"])
    report: dict = {
        "what": f"cube-and-conquer over the circulant instance K{order} {sizes}, "
                f"combined from {len(reports)} passes",
        "produced_by": "scripts/cube_conquer.py "
                       + " ".join(f"--combine {path}" for path in report_paths),
        "spec": f"{order}:{','.join(map(str, sizes))}",
        "n": order, "sizes": sizes,
        "sources": [],
    }
    #: how each pass would be named in the claim: the engine and the budget it was
    #: given, so the report says *how* the leaves were refuted and not only that they
    #: were
    pass_engine: list[str] = []
    cubes_by_pass: list[list[list[int]]] = []
    rows_by_pass: list[list[dict]] = []
    encoding = None
    for path, source in zip(report_paths, reports):
        if (int(source["n"]), list(source["sizes"])) != (order, sizes):
            return {**report, "verdict": "incomplete",
                    "establishes": f"nothing: {path} is about K{source['n']} "
                                   f"{list(source['sizes'])}, not K{order} {sizes}"}
        shape = source.get("encoding") or {}
        if encoding is None:
            encoding = shape
        elif (shape.get("num_vars"), shape.get("num_clauses")) != \
                (encoding.get("num_vars"), encoding.get("num_clauses")):
            return {**report, "verdict": "incomplete",
                    "establishes": f"nothing: {path} was run against a different encoding "
                                   f"({shape.get('num_vars')} variables, "
                                   f"{shape.get('num_clauses')} clauses) than "
                                   f"{report_paths[0]} ({encoding.get('num_vars')}, "
                                   f"{encoding.get('num_clauses')})"}
        cubing = source.get("cubing") or {}
        cube_file = cubing.get("cubes_file") or source.get("cubes_file") or ""
        cubes_by_pass.append(read_cubes(report_path(cube_file)) if cube_file else [])
        rows = read_rows(report_path(source["rows_dir"])) if source.get("rows_dir") else []
        rows_by_pass.append(rows)
        counts: dict[str, int] = {}
        for row in rows:
            counts[row["status"]] = counts.get(row["status"], 0) + 1
        engine = source.get("engine") or {}
        budget = engine.get("budget_seconds")
        pass_engine.append(f"{engine.get('name')} ({engine.get('backing')}) at "
                           f"{f'{budget:g} s' if budget is not None else 'no budget'} "
                           f"per leaf refuted {counts.get('unsat', 0)}")
        report["sources"].append({
            "report": path, "cubes_file": cube_file, "cubes": len(cubes_by_pass[-1]),
            "cover": cube_cover(cubes_by_pass[-1]), "engine": engine.get("name"),
            "backing": engine.get("backing"),
            "budget_seconds": engine.get("budget_seconds"),
            "counts": counts, "shard_seconds": source.get("shards"),
        })
    report["encoding"] = encoding or {}

    # the cover: the pass whose cube list is a decision tree over the instance.  A
    # resumed pass hands in a fragment and can never be it, which is exactly why its
    # own report cannot make this claim
    covers = [index for index, cubes in enumerate(cubes_by_pass)
              if cubes and cube_cover(cubes)["complete"]]
    if not covers:
        return {**report, "verdict": "incomplete",
                "establishes": "nothing: no pass handed in a cube list that closes, so there "
                               "is no cover for these leaves to be the leaves of"}
    cover_index = covers[0]
    cover_cubes = cubes_by_pass[cover_index]
    cover = cube_cover(cover_cubes)
    report["cover"] = cover
    report["cubes"] = len(cover_cubes)
    report["depth"] = cover["depth"]

    leaves = [tuple(cube) for cube in cover_cubes]
    leaf_set = set(leaves)
    decided: dict[tuple, tuple[str, str]] = {}   # cube -> (status, which pass said so)
    witness_rows: list[dict] = []
    stray: list[tuple] = []
    for path, cubes, rows in zip(report_paths, cubes_by_pass, rows_by_pass):
        for cube in cubes:
            if tuple(cube) not in leaf_set and tuple(cube) not in stray:
                stray.append(tuple(cube))
        for row in rows:
            key = tuple(row["cube"])
            status = row["status"]
            previous = decided.get(key)
            if status in VERDICTS:
                if previous is not None and previous[0] in VERDICTS and previous[0] != status:
                    # two verdicts about one leaf cannot both be right, and which pass
                    # is wrong is not for this script to guess
                    return {**report, "verdict": "conflict",
                            "establishes": f"nothing: {previous[1]} and {path} return different "
                                           f"verdicts for {list(key)} ({previous[0]} against "
                                           f"{status}), so the passes are not two views of "
                                           f"one instance"}
                decided[key] = (status, path)
                if status == "sat" and key in leaf_set:
                    witness_rows.append(row)
            elif previous is None:
                decided[key] = (status, path)
    if stray:
        return {**report, "verdict": "incomplete",
                "establishes": f"nothing: {len(stray)} cube(s) decided by a pass are not leaves "
                               f"of the cover (first: {list(stray[0])}), so the passes do not "
                               f"add up to a refutation of it"}

    counts: dict[str, int] = {}
    for status, _ in decided.values():
        counts[status] = counts.get(status, 0) + 1
    report["counts"] = counts
    report["decided"] = len(decided)
    unresolved = [cube for cube in leaves if decided.get(cube, ("missing", ""))[0] not in VERDICTS]
    report["unresolved"] = len(unresolved)
    report["errors"] = counts.get("error", 0)

    if witness_rows:
        instance = MC.CirculantInstance(order, tuple(sizes))
        first_row = min(witness_rows, key=lambda row: leaves.index(tuple(row["cube"])))
        _witness(report, instance, leaves.index(tuple(first_row["cube"])) + 1,
                 first_row["cube"], first_row["model"])
        return report
    if unresolved:
        report["verdict"] = "incomplete"
        report["establishes"] = (f"nothing: {len(unresolved)} of {len(cover_cubes)} leaves were "
                                 f"left undecided by every pass combined")
        return report

    report["verdict"] = "refuted-cover"
    report["establishes"] = (
        f"no colouring of K{order} in the circulant family: the {len(cover_cubes)} leaves of one "
        f"complete decision tree at depth {cover['depth']} are exactly the cubes the "
        f"{len(reports)} passes decided, and every one was refuted — "
        + "; ".join(pass_engine) +
        f".  These are solver verdicts and not proofs: re-refuting the same leaves with an "
        f"engine that emits a DRAT trace, and replaying them here, is what would make it a "
        f"theorem.")
    return report


# --------------------------------------------------------------------------
# the driver
# --------------------------------------------------------------------------
def parse_spec(text: str) -> tuple[int, tuple[int, ...]]:
    """``97:3,3,3,4`` as ``(97, (3, 3, 3, 4))`` — the spec shape the other scripts take."""
    if ":" not in text:
        raise SystemExit(f"expected N:s1,s2,... (e.g. 97:3,3,3,4), not {text!r}")
    order, _, sizes = text.partition(":")
    return int(order), tuple(int(part) for part in sizes.split(","))


def run_cuber(command, cnf: Path, cube_file: Path, depth: int) -> dict:
    """Run ``march_cu`` and report what it produced — or that it decided the instance.

    ``march_cu`` is a solver as well as a cuber: when it can decide the instance
    while cubing it prints a model and writes no cubes at all.  That is reported as
    what it is, model included, and the caller treats it like any other witness.
    """
    # a WSL command is a Linux process: it has to be *shown* the files
    target = tools.wsl_path if tools.is_wsl(command) else str
    args = [*command, target(cnf), "-d", str(depth), "-o", target(cube_file)]
    started = time.time()
    done = subprocess.run(args, capture_output=True, text=True)
    report = {"command": " ".join(args), "exit_code": done.returncode,
              "seconds": round(time.time() - started, 2), "cubes_file": str(cube_file)}
    model: list[int] = []
    verdict = ""
    for line in done.stdout.splitlines():
        if line.startswith("s "):
            verdict = line[2:].strip().upper()
        elif line.startswith("v "):
            for token in line[2:].split():
                try:
                    model.append(int(token))
                except ValueError:  # pragma: no cover - not part of the format
                    continue
    report["verdict"] = verdict
    report["cubes"] = len(read_cubes(cube_file)) if cube_file.exists() else 0
    if verdict == "SATISFIABLE" and model:
        report["model"] = model
    if done.returncode != 0 or not report["cubes"]:
        # march_cu reports a missing file or a bad option on stderr, and a run that
        # produced no cubes has to say why rather than look like a tiny instance
        tail = [line for line in [*done.stderr.splitlines(), *done.stdout.splitlines()]
                if line.strip() and not line.lstrip().startswith(("c", "*", "|"))]
        report["reason"] = tail[-1] if tail else f"exit {done.returncode}, no cubes"
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("spec", nargs="?", default=None,
                        help="the instance, as N:s1,s2,... (e.g. 97:3,3,3,4); optional with "
                             "--combine, and checked against the reports when it is given")
    parser.add_argument("--depth", type=int, default=12,
                        help="cut-off depth for march_cu's look-ahead (default: 12)")
    parser.add_argument("--budget", type=float, default=60.0,
                        help="seconds per cube, enforced per process (default: 60)")
    parser.add_argument("--workers", type=int, default=max(1, os.cpu_count() or 2),
                        help="shards to run at once (default: every core)")
    parser.add_argument("--seconds", type=float, default=None,
                        help="an overall ceiling; shards are killed when it passes")
    parser.add_argument("--engine", default="kissat404", choices=tuple(MC.PY_SAT_SOLVERS),
                        help="the engine that refutes the leaves (default: kissat404)")
    parser.add_argument("--engine-backing", default=None, choices=("binary", "wheel"),
                        help="refuse to run unless the engine is backed by this: the two "
                             "implementations of kissat404 are not interchangeable here")
    parser.add_argument("--kissat", default=None, help="the Kissat command to use")
    parser.add_argument("--march-cu", default=None, help="the march_cu command to use")
    parser.add_argument("--cubes", default=None,
                        help="solve an existing cube file instead of cubing again")
    parser.add_argument("--cubes-out", default=None, help="where to keep the cube file")
    parser.add_argument("--unresolved-out", default=None,
                        help="where to write the cubes a second pass should retry")
    parser.add_argument("--out", default=None, help="the JSON report to write")
    parser.add_argument("--workdir", default=None,
                        help="where the CNF, cube file and rows go (default: beside --out)")
    parser.add_argument("--dimacs", default=None, help="an existing CNF export to reuse")
    parser.add_argument("--combine", nargs="+", default=None, metavar="REPORT",
                        help="read two or more passes over one instance back as the claim "
                             "they add up to: the pass whose cube file closes is the cover, "
                             "every other pass must decide leaves of it, and every leaf must "
                             "be refuted.  Runs no solver and no cuber")
    args = parser.parse_args(argv)

    if args.combine:
        return _combine_main(args, parser)
    if not args.spec:
        parser.error("a spec (N:s1,s2,...) is required unless --combine is used")
    order, sizes = parse_spec(args.spec)
    instance = MC.CirculantInstance(order, sizes)
    if args.kissat:
        os.environ[tools.KISSAT_ENV] = args.kissat
    if args.march_cu:
        os.environ[tools.MARCH_CU_ENV] = args.march_cu
    backing = MC.solver_backing(args.engine)
    if args.engine_backing and backing != args.engine_backing:
        print(f"{args.engine} is backed by {backing}, not {args.engine_backing}: refusing to "
              f"run a campaign on an engine nobody asked for", file=sys.stderr)
        return 2

    out_path = Path(args.out or f"runs/cube_k{order}_{'x'.join(map(str, sizes))}.json")
    workdir = Path(args.workdir) if args.workdir else out_path.parent / out_path.stem
    workdir.mkdir(parents=True, exist_ok=True)
    report: dict = {
        "what": f"cube-and-conquer over the circulant instance K{order} {list(sizes)}",
        "produced_by": f"scripts/cube_conquer.py {args.spec} --depth {args.depth} "
                       f"--budget {args.budget:g} --workers {args.workers} "
                       f"--engine {args.engine}",
        "spec": args.spec, "n": order, "sizes": list(sizes),
        "encoding": {"num_vars": instance.total_vars(),
                     "num_clauses": instance.clause_count(),
                     "classes": len(instance.classes)},
        "engine": {
            "name": args.engine, "backing": backing,
            "command": (tools.describe(tools.kissat_command()) if args.engine == "kissat404"
                        else "python-sat"),
            "budget_seconds": args.budget,
            "budget_enforced_per_cube": backing == "binary",
        },
        "depth": args.depth,
    }

    # the CNF is *built* from the instance whenever it is not handed in, so the
    # leaves are refuted against the clauses a certificate would declare — and an
    # export that disagrees is refused rather than searched
    cnf = Path(args.dimacs) if args.dimacs else workdir / f"k{order}.cnf"
    if not cnf.exists():
        instance.write_dimacs(cnf, comment=f"circulant multicolour Ramsey K_{order}, "
                                           f"sizes={list(sizes)}")
    header = next((line for line in cnf.read_text(encoding="ascii").splitlines()
                   if line.startswith("p ")), "")
    expected = f"p cnf {instance.total_vars()} {instance.clause_count()}"
    if header.strip() != expected:
        print(f"{cnf}: {header.strip()!r} is not this instance's encoding ({expected!r})",
              file=sys.stderr)
        return 2
    report["cnf"] = cnf.as_posix()

    # ------------------------------------------------------------------ cubing
    resumed = bool(args.cubes)
    cube_file = Path(args.cubes) if resumed else \
        Path(args.cubes_out or workdir / f"k{order}_d{args.depth}.icnf")
    if resumed:
        if not cube_file.exists():
            print(f"{cube_file}: no such cube file", file=sys.stderr)
            return 2
        report["cubing"] = {"cubes_file": cube_file.as_posix(), "reused": True}
    else:
        command = tools.march_cu_command()
        if command is None:
            print(f"no march_cu: set {tools.MARCH_CU_ENV}, or build one as "
                  f"~/{tools.WSL_MARCH_CU} under WSL (docs/methodology.md)", file=sys.stderr)
            return 2
        cubing = run_cuber(command, cnf, cube_file, args.depth)
        report["cubing"] = {"tool": tools.describe(command), **cubing}
        if cubing["verdict"] == "UNSATISFIABLE":
            report["verdict"] = "refuted-by-cuber"
            report["establishes"] = ("march_cu refuted the instance while cubing: its own "
                                     "verdict, and no leaf search was run")
            _write_report(out_path, report)
            print(f"march_cu refuted K{order} {list(sizes)} while cubing: {out_path}")
            return 0
        if cubing["verdict"] == "SATISFIABLE" and cubing.get("model"):
            witness = _witness(report, instance, 0, [], cubing["model"])
            _write_report(out_path, report)
            print(report["witness"]["reading"] + f"\n{out_path}")
            return 0 if witness["verify"]["valid"] else 1
        if not cubing["cubes"]:
            print(f"march_cu produced no cubes ({cubing.get('reason', 'no reason given')})",
                  file=sys.stderr)
            return 2
    cubes = read_cubes(cube_file)
    cover = cube_cover(cubes)
    report["cubes"] = len(cubes)
    report["cover"] = cover

    # ------------------------------------------------------------------ leaves
    width = max(1, min(int(args.workers), len(cubes)))
    shards: list[list] = [[] for _ in range(width)]
    for position, cube in enumerate(cubes):
        shards[position % width].append((position + 1, cube))
    rows_dir = workdir / "rows"
    rows_dir.mkdir(parents=True, exist_ok=True)
    for stale in rows_dir.glob("shard_*.jsonl"):
        stale.unlink()
    run = run_shards(order, sizes, shards, args.engine, args.budget, rows_dir, args.seconds)
    report["shards"] = run["seconds"]
    report["workers"] = width
    # written as a POSIX path: a report is an artifact that gets committed, and one
    # that can only be re-read on the platform that wrote it is half a record
    report["rows_dir"] = Path(run["rows_dir"]).as_posix()
    report["shard_summaries"] = run["summaries"]

    rows = read_rows(rows_dir)
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    report["counts"] = counts
    report["decided"] = len(rows)
    worker_failures = [row for row in rows if row["status"] == "error"]
    report["errors"] = len(worker_failures)

    # the undecided cubes keep the order of the cube file (the rows do not: they are
    # written by whichever shard got to them), so the second pass reads the same list
    # the first one did, with the decided leaves taken out
    by_index = {position + 1: cube for position, cube in enumerate(cubes)}
    decided = {row["index"] for row in rows}
    undecided = {row["index"] for row in rows if row["status"] in ("unknown", "error")}
    undecided |= set(by_index) - decided
    unresolved = [by_index[index] for index in sorted(undecided) if index in by_index]
    report["unresolved"] = len(unresolved)
    if unresolved:
        path = Path(args.unresolved_out or workdir / f"k{order}_unresolved.icnf")
        report["unresolved_file"] = write_cubes(path, unresolved).as_posix()

    witness_rows = [row for row in rows if row["status"] == "sat"]
    if witness_rows:
        first = min(witness_rows, key=lambda row: row["index"])
        witness = _witness(report, instance, first["index"], first["cube"], first["model"])
        _write_report(out_path, report)
        if not witness["verify"]["valid"]:
            print(f"a model was found but does not verify: {witness['verify'].get('reason')}",
                  file=sys.stderr)
            return 1
        print(report["witness"]["reading"] + f"\n{out_path}")
        return 0
    if unresolved:
        report["verdict"] = "incomplete"
        report["establishes"] = (
            f"nothing: {len(unresolved)} of {len(cubes)} leaves are undecided"
            + ("" if cover["complete"] else " and the cover does not close")
            + ".  The undecided cubes are written out for a second pass with a larger budget.")
    elif not cover["complete"]:
        report["verdict"] = "refuted-fragment" if resumed else "incomplete"
        report["establishes"] = (
            f"every one of the {len(cubes)} leaves in {cube_file} was refuted by "
            f"{args.engine} ({backing}) — a fragment of a cover, not a cover, so it is a "
            f"piece of the answer and nothing more.  Each leaf is still a verdict and not "
            f"a proof."
            if resumed else
            f"nothing: every leaf in {cube_file} was refuted, but that list does not close "
            f"({cover['reason']}), so it is not a cover of the instance")
    else:
        report["verdict"] = "refuted-cover"
        report["establishes"] = (
            f"no colouring of K{order} in the circulant family: the {len(cubes)} leaves are a "
            f"complete decision tree and every one was refuted by {args.engine} ({backing}) — "
            f"solver verdicts, not proofs.  Re-refuting the same leaves with an engine that "
            f"emits a DRAT trace, and replaying them here, is what would make it a theorem.")
    _write_report(out_path, report)
    print(f"K{order} {list(sizes)}: {report['verdict']} "
          f"({report['decided']}/{len(cubes)} leaves decided, "
          f"cover {'complete' if cover['complete'] else 'open'}, "
          f"{report['shards']}s on {width} shards)\n{out_path}")
    return 0 if report["verdict"] in ("refuted-cover", "refuted-fragment") else 2


def _combine_main(args, parser) -> int:
    """``--combine``: read several passes back as one claim, and write it out.

    The claim is the one the passes make together, so the exit status follows it:
    a closed cover with every leaf refuted is a refutation of the instance's CNF, a
    verified witness is a colouring, and anything else is the refusal it is.
    """
    out_path = Path(args.out or "runs/cube_combined.json")
    report = combine_reports(args.combine)
    if args.spec:
        order, sizes = parse_spec(args.spec)
        if (order, tuple(sizes)) != (report["n"], tuple(report["sizes"])):
            parser.error(f"{args.spec} is not what the reports are about "
                         f"({report['n']}:{','.join(map(str, report['sizes']))})")
    _write_report(out_path, report)
    verdict = report["verdict"]
    if verdict == "sat":
        print(report["witness"]["reading"] + f"\n{out_path}")
        return 0
    if verdict == "sat-invalid":
        print(f"a model was found but does not verify: {report['witness']['verify'].get('reason')}",
              file=sys.stderr)
        return 1
    if verdict == "conflict":
        print(report["establishes"], file=sys.stderr)
        return 1
    if verdict != "refuted-cover":
        print(report["establishes"], file=sys.stderr)
        return 2
    print(f"{report['spec']}: {verdict} ({report['decided']}/{report['cubes']} leaves decided, "
          f"cover complete at depth {report['cover']['depth']}, "
          f"{len(report['sources'])} passes)\n{out_path}")
    return 0


def _witness(report: dict, instance, index: int, cube, model) -> dict:
    """Decode a model with the repository's own class and re-count it.

    A witness is an *artifact*: the colouring, the clique counts, and the leaf it
    came from.  The decoding is the instance's and the counting is
    :func:`oplab.multicolour.verify_colouring` — this script never counts anything
    itself.
    """
    colouring = instance.decode(model)
    verify = MC.verify_colouring(instance.n, instance.sizes, colouring)
    report["verdict"] = "sat" if verify["valid"] else "sat-invalid"
    report["witness"] = {
        "leaf": index, "cube": list(cube), "coloring": colouring, "verify": verify,
        "reading": (f"a circulant colouring of K{instance.n} with forbidden clique sizes "
                    f"{list(instance.sizes)} was found and re-counted: "
                    f"R{tuple(instance.sizes)} > {instance.n}"
                    if verify["valid"] else
                    f"the model decoded but does not verify: {verify.get('reason')}"),
    }
    if verify["valid"]:
        report["establishes"] = (
            f"R{tuple(instance.sizes)} > {instance.n}: the witness is a colouring of "
            f"K{instance.n} with no monochromatic clique of the sizes forbidden for their "
            f"colours, and it is a circulant one — a restriction, so it is also a colouring "
            f"of K{instance.n} outright")
    return report["witness"]


def _write_report(path: Path, report: dict) -> Path:
    """Write the report as JSON."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return path


if __name__ == "__main__":  # pragma: no cover - the script's own entry point
    raise SystemExit(main())
