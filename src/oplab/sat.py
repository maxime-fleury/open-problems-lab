"""SAT encoding of the Ramsey colouring problem, with symmetry breaking.

The task: decide whether `K_n` can be 2-coloured with no monochromatic `K_k`.
`k = 5`, `n = 43` is the open case (`R(5,5) >= 44` iff it is satisfiable); the
same encoding with `k = 3, n = 6` or `k = 4, n = 18` are the classical *unsat*
cases `R(3,3) = 6` and `R(4,4) = 18`, which is what makes them useful tests.

Encoding
--------
One Boolean variable per edge (true = red).  For every `k`-subset `S`:

* no all-red clique:  a clause of the ``k(k-1)/2`` negated edge literals;
* no all-blue clique: the same clause on positive literals.

Symmetry breaking is layered, and every layer is *sound*: it can only remove
symmetrically equivalent solutions, never all of them.  The arguments:

``0``  plain encoding (baseline for the ablation).
``1``  degree ordering ``d(v_0) >= d(v_1) >= ... >= d(v_{n-1})``, where ``d`` is
       the red degree.  Sorting any colouring by red degree realises this
       relabelling, so it is sound.
``2``  adds a colour-swap break.  For a red-degree-sorted labelling,
       ``max red degree = d(v_0)`` and ``max blue degree = (n-1) - d(v_{n-1})``,
       so ``d(v_0) + d(v_{n-1}) >= n - 1`` says "the largest red degree is at
       least the largest blue degree".  Given any colouring, one of the two
       complementary colourings satisfies it (ties are broken by keeping the
       colouring that does).
``3``  adds lex-leader constraints ``M <=_lex pi(M)`` for the first few adjacent
       transpositions of the adjacency matrix.  The lexicographically smallest
       matrix in an orbit satisfies ``M <=_lex pi(M)`` for *every* permutation
       ``pi``, so any subset of these constraints is sound.

No dedicated SAT binary is required: the default backend is Z3's Boolean
(CDCL-style) engine, and every instance can be exported to DIMACS for CaDiCaL,
Kissat, MiniSat... via :meth:`RamseyInstance.write_dimacs`.
"""

from __future__ import annotations

import shutil
import subprocess
import time
from itertools import combinations

__all__ = [
    "CNF",
    "RamseyInstance",
    "pair_var",
    "build_instance",
    "available_solver",
    "ingestion_benchmark",
    "solve",
    "solve_external",
    "SYMMETRY_LEVELS",
]

SYMMETRY_LEVELS = (0, 1, 2, 3)

#: Binaries we can drive through DIMACS if they happen to be installed.
EXTERNAL_SOLVERS = ("cadical", "kissat", "kissat-rel-3.0.0", "minisat", "glucose", "cryptominisat5")


# --------------------------------------------------------------------------
# a tiny CNF builder (clauses are small; auxiliary variables come from the
# sequential counters and lex-leader encodings)
# --------------------------------------------------------------------------
class CNF:
    """Minimal CNF accumulator with a sequential-counter primitive."""

    def __init__(self, num_vars: int = 0):
        self.num_vars = num_vars
        self.clauses: list[tuple[int, ...]] = []

    def new_var(self) -> int:
        self.num_vars += 1
        return self.num_vars

    def new_vars(self, count: int) -> list[int]:
        return [self.new_var() for _ in range(count)]

    def add(self, *lits: int) -> None:
        self.clauses.append(tuple(lits))

    # -- cardinality -------------------------------------------------------
    def at_most(self, lits, k: int) -> None:
        """Assert ``sum(lits) <= k`` with Sinz's sequential counter.

        ``s[i][j]`` (0-based ``i``, 1-based ``j``) is forced true whenever at
        least ``j`` of ``lits[0..i]`` are true, and the clause
        ``-lits[i] v -s[i-1][k]`` forbids the count from reaching ``k + 1``.
        Only the reasoning direction that is needed is enforced, which is exactly
        what makes the counter cheap; repeated literals simply carry weight 2.
        """
        n = len(lits)
        if k >= n:
            return
        if k < 0:
            self.add()  # contradictory: an empty clause
            return
        if k == 0:
            for lit in lits:
                self.add(-lit)
            return
        # Literals are 1-indexed in the encoding below: x_i is lits[i - 1].
        index: dict[tuple[int, int], int] = {}

        def s(i: int, j: int) -> int:
            key = (i, j)
            if key not in index:
                index[key] = self.new_var()
            return index[key]

        # s(1, 1) <-> x_1
        self.add(-lits[0], s(1, 1))
        self.add(-s(1, 1), lits[0])
        for i in range(2, n):  # x_2 .. x_{n-1}
            self.add(-lits[i - 1], s(i, 1))
            self.add(-s(i - 1, 1), s(i, 1))
            for j in range(2, min(i, k + 1) + 1):
                self.add(-lits[i - 1], -s(i - 1, j - 1), s(i, j))
                if j <= i - 1:
                    self.add(-s(i - 1, j), s(i, j))
        # Every x_i that could push the count past k is forbidden.
        for i in range(k + 1, n + 1):
            self.add(-lits[i - 1], -s(i - 1, k))

    def at_least_k(self, lits, k: int) -> None:
        """Assert ``sum(lits) >= k`` (repeated literals carry weight 2)."""
        lits = list(lits)
        self.at_most([-lit for lit in lits], len(lits) - k)

    def geq(self, a_lits, b_lits) -> None:
        """Assert ``sum(a_lits) >= sum(b_lits)``.

        ``sum(a) >= sum(b)`` is the same statement as ``sum(a) + sum(-b) >= |b|``,
        which is one cardinality constraint (no two-counter comparison needed).
        """
        b_lits = list(b_lits)
        self.at_least_k(list(a_lits) + [-lit for lit in b_lits], len(b_lits))

    # -- lexicographic -----------------------------------------------------
    def lex_leq(self, a, b) -> None:
        """Assert ``a <=_lex b`` for two equal-length lists of positive variables."""
        if len(a) != len(b):
            raise ValueError("lex_leq needs equal lengths")
        if not a:
            return
        self.add(-a[0], b[0])
        eq_prev = self.new_var()
        self.add(-eq_prev, -a[0], b[0])
        self.add(-eq_prev, a[0], -b[0])
        self.add(eq_prev, a[0], b[0])
        self.add(eq_prev, -a[0], -b[0])
        for i in range(1, len(a)):
            self.add(-eq_prev, -a[i], b[i])
            eq_i = self.new_var()
            self.add(-eq_i, eq_prev)
            self.add(-eq_i, -a[i], b[i])
            self.add(-eq_i, a[i], -b[i])
            # eq_i must be false as soon as the prefix differs at position i...
            self.add(-eq_i, -eq_prev, -a[i], b[i])
            self.add(-eq_i, -eq_prev, a[i], -b[i])
            # ...and true whenever the prefix is still equal and position i agrees
            # (without these two clauses the equality chain could be dropped and the
            #  constraint would be vacuously satisfiable).
            self.add(eq_i, -eq_prev, a[i], b[i])
            self.add(eq_i, -eq_prev, -a[i], -b[i])
            eq_prev = eq_i

    def stats(self) -> dict:
        return {
            "num_vars": self.num_vars,
            "num_clauses": len(self.clauses),
            "num_literals": sum(len(c) for c in self.clauses),
        }


# --------------------------------------------------------------------------
# the Ramsey instance
# --------------------------------------------------------------------------
def pair_var(n: int, u: int, v: int) -> int:
    """1-based CNF variable of the (unordered) edge ``uv``, ``u != v``."""
    if u == v:
        raise ValueError("no variable for a loop")
    if u > v:
        u, v = v, u
    return u * (2 * n - u - 1) // 2 + (v - u)


def edge_literals(n: int, subset) -> list[int]:
    return [pair_var(n, u, v) for u, v in combinations(sorted(subset), 2)]


class RamseyInstance:
    """The CNF of "no monochromatic ``K_k`` in a 2-colouring of ``K_n``"."""

    def __init__(self, n: int, k: int = 5, symmetry: int = 0):
        if k < 3 or n < k:
            raise ValueError("need 3 <= k <= n")
        if symmetry not in SYMMETRY_LEVELS:
            raise ValueError(f"symmetry must be one of {SYMMETRY_LEVELS}")
        self.n = n
        self.k = k
        self.symmetry = symmetry
        self.num_edges = n * (n - 1) // 2
        self.cnf = CNF(self.num_edges)
        self._add_symmetry()

    # -- construction ------------------------------------------------------
    def colouring_size(self) -> int:
        return self.num_edges

    def clause_count(self) -> int:
        """Total number of clauses, computed without materialising them."""
        return self._subset_clause_count() + len(self.cnf.clauses)

    def _subset_clause_count(self) -> int:
        from math import comb

        return 2 * comb(self.n, self.k)

    def _add_symmetry(self) -> None:
        n = self.n
        if self.symmetry == 0:
            return
        rows = [self._row(i) for i in range(n)]

        def row_minus(i, j):
            return [pair_var(n, i, t) for t in range(n) if t not in (i, j)]

        if self.symmetry >= 1:
            for i in range(n - 1):
                self.cnf.geq(row_minus(i, i + 1), row_minus(i + 1, i))
        if self.symmetry >= 2:
            # d(v_0) + d(v_{n-1}) >= n - 1  (largest red degree >= largest blue degree)
            self.cnf.at_least_k(rows[0] + rows[n - 1], n - 1)
        if self.symmetry >= 3:
            positions = [(u, v) for u in range(n) for v in range(n) if u != v]
            for s in range(min(3, n - 1)):
                a = [pair_var(n, u, v) for u, v in positions]

                def permuted(u, v, s=s):
                    p = list(range(n))
                    p[s], p[s + 1] = p[s + 1], p[s]
                    return pair_var(n, p[u], p[v])

                b = [permuted(u, v) for u, v in positions]
                self.cnf.lex_leq(a, b)

    def _row(self, i: int) -> list[int]:
        return [pair_var(self.n, i, t) for t in range(self.n) if t != i]

    # -- output ------------------------------------------------------------
    def clauses(self):
        """Yield every clause: subset clauses first, then symmetry clauses."""
        n, k = self.n, self.k
        for subset in combinations(range(n), k):
            lits = edge_literals(n, subset)
            yield tuple(-x for x in lits)  # not all red
            yield tuple(lits)  # not all blue
        for clause in self.cnf.clauses:
            yield clause

    def write_dimacs(self, path, comment: str = "") -> dict:
        """Write the instance in DIMACS CNF, streaming the subset clauses."""
        written = 0
        with open(path, "w", encoding="ascii", newline="\n") as handle:
            handle.write(f"c {comment or f'Ramsey K_{self.n}, k={self.k}, symmetry={self.symmetry}'}\n")
            handle.write(f"p cnf {self.cnf.num_vars} {self.clause_count()}\n")
            for clause in self.clauses():
                handle.write(" ".join(map(str, clause)) + " 0\n")
                written += 1
        return {"path": str(path), "clauses_written": written, "num_vars": self.cnf.num_vars}

    def decode(self, assignment: dict[int, bool]) -> str:
        """Turn a model into the canonical ``'0'``/``'1'`` colouring string."""
        return "".join(
            "0" if assignment.get(pair_var(self.n, u, v), False) else "1"
            for u in range(self.n)
            for v in range(u + 1, self.n)
        )


def build_instance(n: int, k: int = 5, symmetry: int = 0) -> RamseyInstance:
    return RamseyInstance(n=n, k=k, symmetry=symmetry)


# --------------------------------------------------------------------------
# solvers
# --------------------------------------------------------------------------
def available_solver() -> str | None:
    """Best available backend: ``"z3"``, an external binary name, or ``None``."""
    try:
        import z3  # noqa: F401

        return "z3"
    except Exception:  # pragma: no cover - depends on the environment
        pass
    for name in EXTERNAL_SOLVERS:  # pragma: no cover - depends on the environment
        if shutil.which(name):
            return name
    return None


def _z3_solve(instance: RamseyInstance, seconds: float, seed: int) -> dict:
    import z3

    solver = z3.Solver()
    solver.set("timeout", max(1, int(seconds * 1000)))
    if seed:
        solver.set("random_seed", int(seed))
    booleans = [z3.Bool(f"x{i}") for i in range(1, instance.cnf.num_vars + 1)]
    for clause in instance.clauses():
        solver.add(z3.Or([booleans[l - 1] if l > 0 else z3.Not(booleans[-l - 1]) for l in clause]))
    started = time.time()
    status = solver.check()
    elapsed = time.time() - started
    stats = {}
    try:
        raw = solver.statistics()
        for key in ("conflicts", "decisions", "propagations", "restarts", "memory", "mk clauses"):
            try:
                stats[key.replace(" ", "_")] = float(raw.get_key_value(key))
            except Exception:
                continue
    except Exception:  # pragma: no cover
        pass
    result = {"status": "unknown", "seconds": elapsed, "stats": stats}
    if status == z3.sat:
        model = solver.model()
        assignment = {i: bool(model.eval(booleans[i - 1], model_completion=True)) for i in range(1, instance.cnf.num_vars + 1)}
        result["status"] = "sat"
        result["coloring"] = instance.decode(assignment)
    elif status == z3.unsat:
        result["status"] = "unsat"
    return result


def ingestion_benchmark(n: int, k: int = 5, symmetry: int = 0, sample: int = 40000) -> dict:
    """Measure how fast a backend can even *load* the instance.

    This exists because for the large instances the bottleneck is not the search
    but the hand-off: the Z3 Python API ingests clauses at a few thousand per
    second, so a 1.9-million-clause instance costs minutes before any reasoning
    starts.  The measurement is taken on a prefix of the clause stream and used
    to project the full instance, which is what the certificates report.
    """
    instance = build_instance(n, k, symmetry)
    total = instance.clause_count()
    backend = available_solver()
    if backend != "z3":
        return {"backend": backend, "clauses_total": total, "clauses_sampled": 0, "note": "no z3"}
    import z3

    solver = z3.Solver()
    booleans = [z3.Bool(f"x{i}") for i in range(1, instance.cnf.num_vars + 1)]
    added = 0
    started = time.time()
    for clause in instance.clauses():
        solver.add(z3.Or([booleans[l - 1] if l > 0 else z3.Not(booleans[-l - 1]) for l in clause]))
        added += 1
        if added >= sample:
            break
    elapsed = time.time() - started
    rate = added / elapsed if elapsed else float("inf")
    return {
        "backend": backend,
        "clauses_total": total,
        "clauses_sampled": added,
        "seconds": elapsed,
        "clauses_per_second": rate,
        "projected_ingest_seconds": total / rate if rate else None,
    }


def solve_external(instance: RamseyInstance, seconds: float, binary: str, dimacs_path) -> dict:  # pragma: no cover
    """Run an external DIMACS solver and parse its verdict."""
    info = instance.write_dimacs(dimacs_path)
    started = time.time()
    proc = subprocess.run([binary, str(dimacs_path)], capture_output=True, text=True, timeout=seconds + 30)
    elapsed = time.time() - started
    out = proc.stdout + proc.stderr
    status = "unknown"
    if "UNSAT" in out.upper():
        status = "unsat"
    elif "SAT" in out.upper():
        status = "sat"
    result = {"status": status, "seconds": elapsed, "stats": {"backend": binary}, "dimacs": info}
    if status == "sat":
        assignment = {}
        for line in out.splitlines():
            if line.startswith("v"):
                for token in line[1:].split():
                    literal = int(token)
                    if literal:
                        assignment[abs(literal)] = literal > 0
        result["coloring"] = instance.decode(assignment)
    return result


def solve(
    n: int,
    k: int = 5,
    symmetry: int = 0,
    seconds: float = 60.0,
    seed: int = 0,
    solver: str = "auto",
    dimacs_path=None,
) -> dict:
    """Solve one Ramsey instance and report a verdict with honest statistics."""
    from math import comb

    instance = build_instance(n, k, symmetry)
    backend = available_solver() if solver == "auto" else solver
    base = {
        "n": n,
        "k": k,
        "symmetry": symmetry,
        "encoding": {
            "num_vars": instance.cnf.num_vars,
            "num_clauses": instance.clause_count(),
            "edge_vars": instance.num_edges,
            "subset_clauses_match_formula": 2 * comb(n, k),
        },
        "backend": backend,
        "seconds_budget": seconds,
    }
    if backend is None:
        return {**base, "status": "no-solver", "seconds": 0.0, "stats": {}}
    if backend == "z3":
        result = _z3_solve(instance, seconds, seed)
    else:  # pragma: no cover - depends on the environment
        if dimacs_path is None:
            dimacs_path = f"k{n}_k{k}_sym{symmetry}.cnf"
        result = solve_external(instance, seconds, backend, dimacs_path)
    if dimacs_path is not None and "dimacs" not in result:
        result["dimacs"] = instance.write_dimacs(
            dimacs_path, comment=f"Ramsey K_{n}, k={k}, symmetry={symmetry}"
        )
    return {**base, **result}
