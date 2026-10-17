"""Multicolour Ramsey colourings: encoding, exact verification, and search.

The 2-colour case lives in :mod:`oplab.ramsey` (``R(5,5)``); this module handles
``R(s_1, ..., s_k)`` — one forbidden clique size per colour.  The multicolour
numbers are the repository's best hope of a *record*, because several of their
lower bounds are decades old while the gap to the upper bound is wide:

===================  ==========  ==========  ==============================
Ramsey number        interval    witness     current lower-bound witness
===================  ==========  ==========  ==============================
``R(3,3,3,3)``       [51, 62]    ``K50``     Chung, 1973
``R(3,3,3,3,3)``     [162, 307]  ``K161``    Exoo, 1994
``R(4,4,4)``         [128, 229]  ``K127``    Hill & Irving, 1982
``R(3,3,3,4)``       [97, 149]   ``K96``     Exoo, c. 2005
``R(3,4,4)``         [55, 77]    ``K54``     Kreher, Li & Radziszowski, 1988
``R(3,3,5)``         [45, 57]    ``K44``     Kreher, Li & Radziszowski, 1988
``R(4,6)``           [36, 40]    ``K35``     Exoo, 2012
``R(5,5)``           [43, 46]    ``K42``     Exoo, 1989
===================  ==========  ==========  ==============================

A colouring of ``K_n`` with no monochromatic ``K_{s_c}`` in colour ``c`` proves
``R(s_1, ..., s_k) > n``: one vertex beyond the published witness is one step up
the table.  Everything this module can claim is a finite witness, so the claim is
checked by re-deriving the monochromatic cliques from the colouring string alone
(:func:`verify_colouring`), and in the Lean layer by the kernel.

Three engines, because the sub-problems behave very differently:

* :func:`tabu_search` — edge recolouring with exact, incrementally maintained
  deltas.  For an all-triangles instance the number of monochromatic triangles
  through an edge ``uv`` of colour ``c`` is the ``(u, v)`` entry of ``A_c @ A_c``,
  so a whole delta table costs one matrix product and a move is a rank-2 update.
  This is the engine that matters for the ``R_k(3)`` family.
* :func:`solve` — CDCL (CaDiCaL, Kissat, MapleSAT ...) over a one-hot CNF with
  sound symmetry breaking, for the instances a SAT solver likes.
* :func:`circulant_solve` — the *circulant* sub-family, decided exactly: one
  variable per difference class and colour, one clause per (colour,
  clique-class-set).  This is the only part of the multicolour frontier that is
  decided rather than sampled, and it is where the measured results are: no
  circulant witness exists at any of the target sizes the method settled (18 of
  the 24 instances stored in ``certs/circulant_multicolour/``; the other six
  returned ``unknown`` on a spent budget and claim nothing), and when ``3 | n``
  every all-triangle instance is obstructed by arithmetic alone
  (:func:`circulant_obstruction`).

The first two are heuristics.  A non-zero violation count is not a theorem, and a
zero count means exactly what the verifier re-derives from the colouring.  The
third is exact inside a sub-family, which is a restriction but not a relaxation;
its ``sat`` verdicts are witnesses, its ``obstructed`` verdicts are arithmetic,
and its ``unsat`` verdicts become theorems when ``proof_path`` is given: the
solver's DRAT trace is written out and checked by :mod:`oplab.drat` against the
same encoding, with no solver in the loop.
"""

from __future__ import annotations

import itertools
import json
import random
import subprocess
import tempfile
import time
from math import comb
from pathlib import Path

import numpy as np

from . import drat as DRAT
from . import tools

__all__ = [
    "RECORDS",
    "TARGETS",
    "edges",
    "edge_pairs",
    "parse_colouring",
    "serialize_colouring",
    "random_colouring",
    "adjacency_masks",
    "mono_clique_counts",
    "is_valid",
    "verify_colouring",
    "MulticolourInstance",
    "KissatBinary",
    "available_solvers",
    "solver_backing",
    "solver_class",
    "solve",
    "tabu_search",
    "circulant_solve",
    "CirculantInstance",
    "circulant_colouring",
    "circulant_obstruction",
    "clique_class_groups",
    "difference_class",
    "difference_classes",
    "stored_colouring",
]

# --------------------------------------------------------------------------
# the record table: what a witness has to beat
# --------------------------------------------------------------------------
#: ``name -> record``.  ``lower`` is the published best lower bound and
#: ``witness_vertices = lower - 1`` is the size of the colouring that witnesses
#: it; a colouring of ``K_lower`` would raise the bound to ``lower + 1``.
RECORDS: dict[str, dict] = {
    "R(3,3,3,3)": {
        "sizes": (3, 3, 3, 3),
        "lower": 51,
        "upper": 62,
        "witness_vertices": 50,
        "who": "F. R. K. Chung",
        "when": 1973,
        "source": "Chung (1973); Radziszowski, Small Ramsey Numbers, rev. 18 (2026)",
    },
    "R(3,3,3,3,3)": {
        "sizes": (3, 3, 3, 3, 3),
        "lower": 162,
        "upper": 307,
        "witness_vertices": 161,
        "who": "G. Exoo",
        "when": 1994,
        "source": "Exoo, Electron. J. Combin. 1 (1994) R8",
    },
    "R(3,3,3,3,3,3)": {
        "sizes": (3, 3, 3, 3, 3, 3),
        "lower": 538,
        "upper": 1838,
        "witness_vertices": 537,
        "who": "H. Fredricksen & M. M. Sweet",
        "when": 2000,
        "source": "Fredricksen & Sweet, Electron. J. Combin. 7 (2000) R32",
    },
    "R(4,4,4)": {
        "sizes": (4, 4, 4),
        "lower": 128,
        "upper": 229,
        "witness_vertices": 127,
        "who": "A. Hill & R. W. Irving",
        "when": 1982,
        "source": "Hill & Irving (1982); Boza, arXiv:2603.10851 (2026)",
    },
    "R(3,3,3,4)": {
        "sizes": (3, 3, 3, 4),
        "lower": 97,
        "upper": 149,
        "witness_vertices": 96,
        "who": "G. Exoo",
        "when": 2005,
        "source": "Radziszowski, Small Ramsey Numbers, rev. 18 (2026)",
    },
    "R(3,4,4)": {
        "sizes": (3, 4, 4),
        "lower": 55,
        "upper": 77,
        "witness_vertices": 54,
        "who": "D. R. Kreher, Z. Li & S. P. Radziszowski",
        "when": 1988,
        "source": "Kreher, Li & Radziszowski (1988)",
    },
    "R(3,3,4)": {
        "sizes": (3, 3, 4),
        "lower": 30,
        "upper": 30,
        "witness_vertices": 29,
        "who": "Codish, Frank, Itzhakov & Miller",
        "when": 2016,
        "source": "Codish et al. (2016) (exact value); Kreher, Li & Radziszowski (1988) "
                  "for the witness",
    },
    "R(3,3,5)": {
        "sizes": (3, 3, 5),
        "lower": 45,
        "upper": 57,
        "witness_vertices": 44,
        "who": "D. R. Kreher, Z. Li & S. P. Radziszowski",
        "when": 1988,
        "source": "Kreher, Li & Radziszowski (1988)",
    },
    "R(4,6)": {
        "sizes": (4, 6),
        "lower": 36,
        "upper": 40,
        "witness_vertices": 35,
        "who": "G. Exoo",
        "when": 2012,
        "source": "Exoo, Electron. J. Combin. 19 (2012) #P66",
    },
    "R(5,5)": {
        "sizes": (5, 5),
        "lower": 43,
        "upper": 46,
        "witness_vertices": 42,
        "who": "G. Exoo",
        "when": 1989,
        "source": "Exoo, J. Graph Theory 13 (1989) 97-98",
    },
}

#: Instances worth compute, cheapest-first: ``(name, n)`` where ``n`` is the first
#: size beyond the published witness, i.e. the new record if a colouring exists.
TARGETS: tuple[tuple[str, int], ...] = (
    ("R(3,3,3,3)", 51),
    ("R(4,6)", 36),
    ("R(3,3,3,4)", 97),
    ("R(3,4,4)", 55),
    ("R(3,3,5)", 45),
    ("R(4,4,4)", 128),
    ("R(3,3,3,3,3)", 162),
    ("R(5,5)", 43),
)

CERT_DIR = Path(__file__).resolve().parents[2] / "certs" / "ramsey"


# --------------------------------------------------------------------------
# colouring representation
# --------------------------------------------------------------------------
def edges(n: int) -> list[tuple[int, int]]:
    """All edges of ``K_n`` in lexicographic order (``u < v``)."""
    return [(u, v) for u in range(n) for v in range(u + 1, n)]


def edge_pairs(n: int) -> tuple[np.ndarray, np.ndarray]:
    """Edge endpoints as parallel index arrays, lexicographic order."""
    return np.triu_indices(n, k=1)


def random_colouring(n: int, k: int, rng) -> np.ndarray:
    """Uniform random ``k``-colouring of ``K_n`` as an ``(n, n)`` int8 matrix."""
    upper = np.asarray(rng.integers(0, k, size=n * (n - 1) // 2), dtype=np.int8)
    colouring = np.zeros((n, n), dtype=np.int8)
    u, v = edge_pairs(n)
    colouring[u, v] = upper
    colouring[v, u] = upper
    return colouring


def parse_colouring(text: str, n: int, k: int | None = None) -> np.ndarray:
    """Turn a colouring string into an ``(n, n)`` colour matrix (colour indices).

    The string has one digit per edge in lexicographic order (``u < v``).
    """
    text = text.strip()
    m = n * (n - 1) // 2
    if len(text) != m:
        raise ValueError(f"a colouring of K{n} needs {m} digits, got {len(text)}")
    if not set(text) <= set("0123456789"):
        raise ValueError("a colouring may only contain digits")
    if k is None:
        k = max(int(d) for d in text) + 1
    if max(int(d) for d in text) >= k:
        raise ValueError("a colour index is out of range")
    colouring = np.zeros((n, n), dtype=np.int8)
    u, v = edge_pairs(n)
    colouring[u, v] = np.fromiter((int(d) for d in text), dtype=np.int8, count=m)
    colouring[v, u] = colouring[u, v]
    return colouring


def serialize_colouring(colouring: np.ndarray, n: int) -> str:
    """Inverse of :func:`parse_colouring`."""
    u, v = edge_pairs(n)
    return "".join(str(int(c)) for c in colouring[u, v])


def adjacency_masks(colouring: np.ndarray, n: int, colour: int) -> list[int]:
    """Per-vertex neighbour bitmasks of the edges of the given colour."""
    masks = [0] * n
    for u in range(n):
        row = colouring[u]
        m = 0
        for v in range(n):
            if v != u and row[v] == colour:
                m |= 1 << v
        masks[u] = m
    return masks


def _count_cliques(masks: list[int], mask: int, k: int) -> int:
    """``k``-cliques of the graph inside the vertex set ``mask`` (bits of ``mask`` are > any vertex already chosen)."""
    if mask.bit_count() < k:
        return 0
    if k <= 1:
        return mask.bit_count()
    total = 0
    remaining = mask
    while remaining:
        v = (remaining & -remaining).bit_length() - 1
        remaining &= remaining - 1
        total += _count_cliques(masks, remaining & masks[v], k - 1)
    return total


def mono_clique_counts(n: int, sizes, colouring: np.ndarray) -> list[int]:
    """Exact number of monochromatic forbidden cliques, one entry per colour.

    No search and no tolerance: this is a recount of the stored colouring, each
    clique counted once at its lowest-numbered vertex.
    """
    counts = []
    for colour, s in enumerate(sizes):
        masks = adjacency_masks(colouring, n, colour)
        total = 0
        for v in range(n):
            total += _count_cliques(masks, masks[v] & ~((1 << (v + 1)) - 1), s - 1)
        counts.append(total)
    return counts


def is_valid(n: int, sizes, colouring: np.ndarray) -> bool:
    """True iff the colouring has no monochromatic forbidden clique."""
    return all(c == 0 for c in mono_clique_counts(n, sizes, colouring))


def verify_colouring(n: int, sizes, text: str) -> dict:
    """Verify a stored colouring string and report what it establishes."""
    sizes = tuple(int(s) for s in sizes)
    colouring = parse_colouring(text, n, k=len(sizes))
    counts = mono_clique_counts(n, sizes, colouring)
    valid = all(c == 0 for c in counts)
    return {
        "n": n,
        "sizes": list(sizes),
        "monochromatic_cliques": counts,
        "valid": valid,
        "establishes": f"R{tuple(sizes)} > {n}" if valid else None,
    }


# --------------------------------------------------------------------------
# CDCL encoding: one-hot colour variables, one clause per forbidden clique
# --------------------------------------------------------------------------
class MulticolourInstance:
    """CNF of "no monochromatic ``K_{s_c}`` in colour ``c``" on ``K_n``.

    ``symmetry`` levels, each *sound* (it can only remove colourings
    symmetric to a kept one):

    ``0``  plain one-hot encoding.  ``k`` variables per edge, exactly one true;
           every ``s_c``-subset contributes one clause forbidding its edges from
           all sharing colour ``c``.  Clauses are small (triangles give size 3),
           which is what CDCL likes.
    ``1``  adds the restricted-growth condition on the edges out of vertex 0:
           scanning those edges in order, a colour may only be used if the next
           lower colour already appeared.  Renaming colours in order of first
           appearance realises this, so it is a sound colour symmetry break (a
           *sorted* first row would not be: a colour permutation cannot reorder
           the sequence).
    ``2``  also orders the vertices by their colour-0 degree, using the
           sequential counter in :class:`oplab.sat.CNF` for the comparisons.
           Sorting any colouring's vertices by that degree realises it.
    """

    def __init__(self, n: int, sizes, symmetry: int = 0):
        sizes = tuple(int(s) for s in sizes)
        if any(s < 3 or s > n for s in sizes):
            raise ValueError("need 3 <= s_c <= n for every colour")
        if symmetry not in (0, 1, 2):
            raise ValueError("symmetry must be 0, 1 or 2")
        self.n = n
        self.sizes = sizes
        self.symmetry = symmetry
        self.k = len(sizes)
        self.m = n * (n - 1) // 2
        self.num_vars = self.k * self.m
        self._index = {e: i for i, e in enumerate(edges(n))}
        self._extra: list[tuple[int, ...]] = []
        self._max_var = self.num_vars
        self._growth: list[list[int]] = []
        self._build_symmetry()

    # -- helpers -----------------------------------------------------------
    def var(self, colour: int, edge) -> int:
        u, v = edge if edge[0] < edge[1] else (edge[1], edge[0])
        return colour * self.m + self._index[(u, v)] + 1

    def new_var(self) -> int:
        self._max_var += 1
        return self._max_var

    def _row(self, i: int, colour: int = 0) -> list[int]:
        return [self.var(colour, (i, t)) for t in range(self.n) if t != i]

    def _build_symmetry(self) -> None:
        if self.symmetry == 0:
            return
        self._build_colour_break()
        if self.symmetry >= 2:
            self._build_vertex_break()

    def _build_colour_break(self) -> None:
        """Restricted growth along the edges out of vertex 0.

        ``P[t][c]`` (one auxiliary per first-row edge ``e_t``, colour ``c <= k-2``)
        means "colour ``c`` occurs on ``e_1 .. e_t``", and the constraint is
        ``colour(e_t) = c > 0  ==>  P[t-1][c-1]``: a colour may only be used once
        the next lower one has appeared.  Relabelling the colours in order of
        first appearance realises it for *any* colouring, so nothing valid is
        lost.  The three definitional clauses per auxiliary make ``P`` exact
        (it is a function of the first row), so the break actually prunes instead
        of being merely implied.
        """
        n, k = self.n, self.k
        if k < 2:
            return
        previous: list[int] | None = None
        for t, edge in enumerate(((0, t) for t in range(1, n)), start=1):
            row = [self.new_var() for _ in range(k - 1)]
            for c, aux in enumerate(row):
                x = self.var(c, edge)
                if previous is None:
                    self._extra.append((-aux, x))
                else:
                    self._extra.append((-aux, previous[c], x))  # aux -> prev or x
                    self._extra.append((-previous[c], aux))  # prev -> aux
                self._extra.append((-x, aux))  # x -> aux
            for c in range(1, k):
                if previous is None:
                    self._extra.append((-self.var(c, edge),))  # e_1 has colour 0
                else:
                    self._extra.append((-self.var(c, edge), previous[c - 1]))
            self._growth.append(row)
            previous = row

    def _build_vertex_break(self) -> None:
        """Order the vertices by colour-0 degree (non-increasing).

        Sorting the vertex labels by their number of colour-0 edges is a vertex
        permutation, hence a symmetry of the instance, and the comparisons are
        the sequential counters of :class:`oplab.sat.CNF`.
        """
        from .sat import CNF

        cnf = CNF(self._max_var)
        rows = [self._row(i) for i in range(self.n)]
        for i in range(self.n - 1):
            cnf.geq(rows[i], rows[i + 1])
        self._extra.extend(cnf.clauses)
        self._max_var = cnf.num_vars

    def clause_count(self) -> int:
        base = self.m * (1 + comb(self.k, 2)) + sum(comb(self.n, s) for s in self.sizes)
        return base + len(self._extra)

    def total_vars(self) -> int:
        return self._max_var

    def symmetry_clauses(self):
        """Just the break clauses, without the one-hot and clique clauses."""
        for clause in self._extra:
            yield tuple(clause)

    # -- what the symmetry breaks mean, and a model for the auxiliaries -----
    def symmetry_holds(self, colouring) -> bool:
        """The semantic content of the breaks, read off a colouring.

        For a colouring array this returns whether it already satisfies the
        breaks *as a colouring* (no relabelling or sorting applied): level 1 needs
        restricted growth on the first row, level 2 needs the colour-0 degrees to
        be non-increasing along the vertex order.
        """
        k = self.k
        first_row = [int(colouring[0, t]) for t in range(1, self.n)]
        if self.symmetry >= 1:
            if k >= 2 and first_row and first_row[0] != 0:
                return False
            for t, c in enumerate(first_row):
                if c > 0 and c - 1 not in first_row[:t]:
                    return False
        if self.symmetry >= 2:
            degrees = [sum(int(colouring[i, t]) == 0 for t in range(self.n) if t != i)
                       for i in range(self.n)]
            if any(degrees[i] < degrees[i + 1] for i in range(self.n - 1)):
                return False
        return True

    def assignment(self, colouring) -> set[int]:
        """The true literals of the level-1 encoding for one colouring.

        Edge variables follow the colouring and each auxiliary ``P[t][c]`` is set
        by its definition, so the result is a complete assignment of the level-1
        variables and can be tested clause by clause against
        :meth:`clauses`.  Only defined for ``symmetry <= 1``: at level 2 the
        counter auxiliaries come from :class:`oplab.sat.CNF` and are not exposed.
        """
        if self.symmetry > 1:
            raise ValueError("assignment() covers the level-1 encoding only")
        truth: set[int] = set()
        for c in range(self.k):
            for e in self._index:
                if int(colouring[e]) == c:
                    truth.add(self.var(c, e))
        for t, row in enumerate(self._growth, start=1):
            seen = {int(colouring[0, s]) for s in range(1, t + 1)}
            for c, aux in enumerate(row):
                if c in seen:
                    truth.add(aux)
        return truth

    # -- clause stream -----------------------------------------------------
    def clauses(self):
        """Yield every clause as a tuple of literals."""
        n, k, sizes = self.n, self.k, self.sizes
        for e in self._index:
            lits = [self.var(c, e) for c in range(k)]
            yield tuple(lits)
            for a in range(k):
                for b in range(a + 1, k):
                    yield (-lits[a], -lits[b])
        for colour, s in enumerate(sizes):
            for subset in itertools.combinations(range(n), s):
                yield tuple(-self.var(colour, pair) for pair in itertools.combinations(subset, 2))
        for clause in self._extra:
            yield tuple(clause)

    def write_dimacs(self, path, comment: str = "") -> dict:
        written = 0
        with open(path, "w", encoding="ascii", newline="\n") as handle:
            handle.write(f"c {comment or f'multicolour Ramsey K_{self.n} {self.sizes}'}\n")
            handle.write(f"p cnf {self.total_vars()} {self.clause_count()}\n")
            for clause in self.clauses():
                handle.write(" ".join(map(str, clause)) + " 0\n")
                written += 1
        return {"path": str(path), "clauses_written": written, "num_vars": self.total_vars()}

    def decode(self, model) -> str:
        """Turn a pysat model into a colouring string."""
        truth = {abs(lit) for lit in model if lit > 0}
        u, v = edge_pairs(self.n)
        colouring = np.zeros((self.n, self.n), dtype=np.int8)
        for c in range(self.k):
            base = c * self.m
            for i in range(self.m):
                if base + i + 1 in truth:
                    colouring[u[i], v[i]] = c
                    colouring[v[i], u[i]] = c
        return serialize_colouring(colouring, self.n)


# --------------------------------------------------------------------------
# CDCL driver
# --------------------------------------------------------------------------
#: Engines, best-first.  Five of these are solver classes bundled with
#: ``python-sat``; ``kissat404`` is either that wheel's Kissat — unusable on
#: Windows, see :func:`solver_backing` — or a real Kissat 4.0.4 process
#: (:class:`KissatBinary`), whichever this machine can run.  All of them are
#: native C++ code driven in a child process, so the hand-off cost that made the
#: Z3 route in :mod:`oplab.sat` hopeless does not apply here.
PY_SAT_SOLVERS = ("cadical195", "kissat404", "maplechrono", "maplecm", "glucose4", "minisat22")


def solver_backing(name: str) -> str:
    """Which implementation answers under an engine's name.

    ``"binary"`` for a real Kissat process (:data:`oplab.tools.KISSAT_ENV`, or a
    from-source build under WSL) and ``"wheel"`` for a ``python-sat`` binding —
    including the bundled Kissat 4.0.4 wheel, which on Windows segfaults on a
    two-clause instance and answers ``sat`` with an invalid model on a
    four-clause one — and ``"absent"`` for a name that no implementation here
    answers.  A verdict that does not say which of the three produced it cannot be
    reproduced, so every probe row carries this, and ``oplab solvers`` prints it.
    """
    if name == "kissat404" and tools.kissat_command() is not None:
        return "binary"
    if name not in PY_SAT_SOLVERS:
        return "absent"
    try:
        import pysat.solvers  # noqa: F401
    except Exception:  # pragma: no cover - depends on the environment
        return "absent"
    return "wheel"


def available_solvers() -> list[str]:
    """SAT engines this environment can *start*, best-first.

    Being listed is not evidence of health: a wheel import says nothing about what
    happens on the first clause.  On Windows the bundled Kissat wheel dies with an
    access violation on a two-clause instance and answers ``sat`` with an invalid
    model on a four-clause contradiction — and such a run is reported as
    :func:`_cdcl_with_budget`'s ``no_verdict`` result carrying the worker's exit
    code, the CLI refuses to write a certificate for it, and
    :func:`oplab.verify.verify_circulant_multicolour` refuses to read one, so a
    crash cannot be filed as a budget that expired.

    ``kissat404`` is listed when the ``pysat`` wheels import *or* when a real
    Kissat binary is reachable, because those are two different implementations
    and either one alone is enough to run it.

    Use :func:`probe_solvers` (or ``oplab solvers``) for health.
    """
    try:
        import pysat.solvers  # noqa: F401

        names = list(PY_SAT_SOLVERS)
    except Exception:
        names = []
    if "kissat404" not in names and tools.kissat_command() is not None:
        names.insert(1, "kissat404")
    return names


class KissatBinary:
    """A real Kissat process behind the ``pysat`` solver interface.

    The bundled wheel for the same version (4.0.4) is broken on this platform, and
    broken in the worst way: on ``[[1], [-1]]`` it dies with an access violation
    and on the four-clause contradiction it answers ``sat`` with a model that
    satisfies nothing, so a caller cannot even tell a crash from a verdict.  A
    binary built from upstream (:func:`oplab.tools.kissat_command`) is the same
    engine with an interface that works; this class offers the handful of methods
    the drivers here use — :meth:`add_clause`, :meth:`solve`, :meth:`get_model`,
    :meth:`time` — by handing the clauses over as DIMACS and reading the answer
    back.

    Three things it does *not* do, on purpose:

    * it never answers ``unsat`` unless the solver said so: a signal, an empty
      output or a parse error is ``None`` (unknown) with the reason kept in
      ``note``, because those are exactly the cases that used to be filed as a
      verdict;
    * it re-checks every model against the clauses it was given before answering
      ``sat``, and raises if the model leaves one unsatisfied — an interface bug
      here must not be able to invent a witness;
    * :meth:`get_proof` refuses, and ``with_proof=True`` is refused at
      construction: Kissat emits no DRAT trace, so a proof-carrying row has to
      come from an engine that does (``cadical195``).

    ``solve`` also takes ``assumptions``, which the binary protocol does not have
    natively: they are added as unit clauses, so a caller that fed cubes to a
    ``pysat`` solver can feed the same cubes here.
    """

    #: What asking for a trace means for this engine.
    NO_PROOF = "kissat emits no DRAT trace: use cadical195 for a proof-carrying row"

    def __init__(self, bootstrap_with=(), use_timer: bool = False,
                 with_proof: bool = False, timeout=None):
        if with_proof:
            raise NotImplementedError(self.NO_PROOF)
        self._clauses = [list(clause) for clause in bootstrap_with]
        self._model: list[int] = []
        self._seconds = 0.0
        self._timeout = timeout
        #: Why the last run gave no verdict, when it gave none.
        self.note = ""

    # -- the interface the drivers use -------------------------------------
    def add_clause(self, clause) -> "KissatBinary":
        self._clauses.append(list(clause))
        return self

    def add_clauses(self, clauses) -> "KissatBinary":
        for clause in clauses:
            self.add_clause(clause)
        return self

    def nof_vars(self) -> int:
        return max((abs(lit) for clause in self._clauses for lit in clause), default=0)

    def nof_clauses(self) -> int:
        return len(self._clauses)

    def _dimacs(self, clauses) -> str:
        """The clauses as a DIMACS document, with the header this run needs.

        The header is written from the clauses rather than remembered from the
        constructor, because ``solve`` may have added assumptions to them: a
        clause count that disagrees with the body is a parse error, not a
        suggestion.
        """
        header = (f"p cnf {max((abs(lit) for clause in clauses for lit in clause), default=0)} "
                  f"{len(clauses)}")
        return "\n".join([header, *(" ".join(map(str, clause)) + " 0" for clause in clauses)]) + "\n"

    @staticmethod
    def _unsatisfied(clauses, truth) -> int:
        """How many clauses a model leaves unsatisfied.

        ``truth`` is the model's own literals, signs included — a clause is
        satisfied when one of its literals appears in it verbatim.  Reading the
        model as a set of *variables* would call ``[[1, 2], [-1]]`` unsatisfied by
        ``-1 2``, which is exactly the clause ``-1`` being satisfied.
        """
        return sum(1 for clause in clauses if not any(lit in truth for lit in clause))

    def solve(self, assumptions=()):
        """Run Kissat on the clauses (plus ``assumptions`` as units).

        ``True`` with a model that has been checked against those clauses, ``False``
        only on the solver's own ``s UNSATISFIABLE``, and ``None`` with ``note``
        saying why when it gave no verdict at all.
        """
        command = tools.kissat_command()
        if command is None:
            raise RuntimeError(f"no Kissat binary: set {tools.KISSAT_ENV} "
                               f"(or build one as ~/{tools.WSL_KISSAT} under WSL)")
        clauses = [list(clause) for clause in self._clauses]
        clauses.extend([int(lit)] for lit in assumptions)
        started = time.time()
        with tempfile.NamedTemporaryFile("w", suffix=".cnf", encoding="ascii",
                                        newline="\n", delete=False) as handle:
            handle.write(self._dimacs(clauses))
            name = handle.name
        try:
            # a WSL command is a Linux process, so it has to be *shown* the file
            target = tools.wsl_path(name) if tools.is_wsl(command) else name
            argv = [*command, target]
            ceiling = self._timeout
            if ceiling is not None:
                # under WSL the ceiling is enforced *there*, so the process that is
                # killed is the solver and not the launcher: a killed launcher leaves
                # a Kissat running that holds the pipes open (measured: a 20 s budget
                # took 40 s to come back, per cube, with the orphan still working)
                wrapped = tools.bounded_wsl(command, ceiling)
                if wrapped is not None:
                    argv = [*wrapped, target]
                    ceiling = ceiling + 15.0  # this side stays the backstop
            try:
                done = subprocess.run(argv, capture_output=True, text=True, timeout=ceiling)
            except subprocess.TimeoutExpired:
                self.note = "the budget ran out: the run was cut off by its timeout"
                return None
        finally:
            Path(name).unlink(missing_ok=True)
            self._seconds = time.time() - started
        status, model = "", []
        for line in done.stdout.splitlines():
            if line.startswith("s "):
                status = line[2:].strip().upper()
            elif line.startswith("v "):
                for token in line[2:].split():
                    try:
                        model.append(int(token))
                    except ValueError:  # pragma: no cover - not part of the format
                        continue
        if status == "SATISFIABLE":
            unsatisfied = self._unsatisfied(clauses, set(model))
            if unsatisfied:
                raise RuntimeError(
                    f"kissat answered sat with a model that leaves {unsatisfied} of "
                    f"{len(clauses)} clauses unsatisfied")
            self._model = model
            self.note = ""
            return True
        if status == "UNSATISFIABLE":
            self.note = ""
            return False
        if done.returncode == 124:
            # the ceiling inside WSL reported itself: a spent budget, not a crash
            self.note = (f"the budget ran out: {tools.describe(argv)} was stopped at "
                         f"{float(self._timeout):g}s (exit 124)")
            return None
        reason = next((line.strip() for line in reversed(done.stderr.splitlines())
                       if line.strip()), "")
        self.note = (f"no verdict from {tools.describe(argv)}, exit {done.returncode}"
                     + (f": {reason}" if reason else ""))
        return None

    def get_model(self) -> list[int]:
        return list(self._model)

    def get_proof(self):
        raise NotImplementedError(self.NO_PROOF)

    def time(self) -> float:
        """Seconds the last :meth:`solve` took, writing the CNF included."""
        return self._seconds

    def delete(self) -> None:
        """Nothing is left open: each run writes its own file and removes it."""
        self._model = []

    def __enter__(self) -> "KissatBinary":
        return self

    def __exit__(self, *exception) -> bool:
        self.delete()
        return False


#: Health-check verdicts, in the order they are reported.
PROBE_STATUSES = ("ok", "wrong", "crashed", "timeout", "unavailable")

_solver_health: dict[str, dict] = {}


def _probe_worker(conn, name: str, seconds: float | None = None) -> None:  # pragma: no cover
    """Answer two instances whose verdicts are known, or report why not.

    ``[1]`` is satisfiable and ``[1],[-1]`` is not, so a solver that answers both
    correctly has shown it starts, parses, decides, and reports.  Anything else —
    a crash, a wrong verdict, a missing binary — is recorded as such.  The second
    of the two is also the instance the bundled Kissat wheel dies on, so a
    ``kissat404`` row here is a statement about which implementation answered.
    """
    out: dict = {"solver": name, "backend": solver_backing(name)}
    try:
        _solver_class(name)
    except Exception as exc:
        out.update(status="unavailable", reason=f"{exc.__class__.__name__}: {exc}")
        try:
            conn.send(out)
        finally:
            conn.close()
        return
    try:
        # the probe's own budget is handed to the engine where it can carry one, so
        # a wedged run finishes as a spent budget instead of leaving a process behind
        with _open_solver(name, [[1]], timeout=seconds) as solver:
            out["sat_ok"] = solver.solve() is True
        with _open_solver(name, [[1], [-1]], timeout=seconds) as solver:
            out["unsat_ok"] = solver.solve() is False
        out["status"] = "ok" if out["sat_ok"] and out["unsat_ok"] else "wrong"
    except Exception as exc:  # pragma: no cover - diagnostic path
        out.update(status="crashed", reason=f"{exc.__class__.__name__}: {exc}")
    try:
        conn.send(out)
    finally:
        conn.close()


def probe_solver(name: str, seconds: float = 10.0, refresh: bool = False) -> dict:
    """Test one bundled engine on two trivial instances, and report what happened.

    The run happens in a child process the parent can kill, so a dead or wedged
    binary is reported instead of hanging the caller: ``ok``, ``wrong`` (answered
    but not correctly), ``crashed``, ``timeout``, or ``unavailable`` (no such
    engine here).  Results are cached per process unless ``refresh`` is set.

    ``seconds`` is honoured literally rather than floored at some comfortable
    value: a caller who passes less than a process start-up gets ``timeout``,
    which is what such a budget means, and it is what makes the timeout branch
    testable instead of dependent on how loaded the machine is.
    """
    import multiprocessing as mp

    if not refresh and name in _solver_health:
        return _solver_health[name]
    if name not in PY_SAT_SOLVERS:
        verdict = {"solver": name, "status": "unavailable", "backend": solver_backing(name),
                   "reason": f"not a bundled engine: {name}"}
        _solver_health[name] = verdict
        return verdict
    ctx = mp.get_context("spawn")
    parent, child = ctx.Pipe(duplex=False)
    proc = ctx.Process(target=_probe_worker, args=(child, name, float(seconds)), daemon=True)
    started = time.time()
    proc.start()
    proc.join(max(0.0, float(seconds)))
    if proc.is_alive():
        proc.terminate()
        proc.join(10)
        if proc.is_alive() and hasattr(proc, "kill"):  # pragma: no cover - defensive
            proc.kill()
        parent.close()
        verdict = {"solver": name, "status": "timeout", "exit_code": None,
                   "seconds": round(time.time() - started, 3)}
    elif parent.poll(10):
        verdict = parent.recv()
        parent.close()
        verdict["seconds"] = round(time.time() - started, 3)
    else:
        parent.close()
        verdict = {"solver": name, "status": "crashed", "exit_code": proc.exitcode,
                   "reason": f"no verdict from the worker (exit {proc.exitcode})",
                   "seconds": round(time.time() - started, 3)}
    _solver_health[name] = verdict
    return verdict


def probe_solvers(seconds: float = 10.0, names=None, refresh: bool = False) -> list[dict]:
    """Health-check the bundled engines, in :data:`PY_SAT_SOLVERS` order."""
    return [probe_solver(name, seconds=seconds, refresh=refresh)
            for name in (PY_SAT_SOLVERS if names is None else tuple(names))]


def working_solvers(seconds: float = 10.0, refresh: bool = False) -> list[str]:
    """The bundled engines that actually answered a trivial run, best-first."""
    return [row["solver"] for row in probe_solvers(seconds=seconds, refresh=refresh)
            if row["status"] == "ok"]


def _open_solver(name: str, clauses, with_proof: bool = False, timeout=None):
    """Build an engine, handing it the budget when that engine can carry one.

    Only the binary Kissat can: the wheels take no timeout, because a solver holds
    the interpreter for its whole run.  Where the engine *can* carry one, giving it
    the budget is better than being killed — the child gets to report an expired
    budget instead of dying, and (under WSL) the process that is stopped is the
    solver, not the launcher, so nothing is left running behind it.
    """
    if name == "kissat404" and solver_backing(name) == "binary":
        return KissatBinary(bootstrap_with=clauses, with_proof=with_proof, timeout=timeout)
    return _solver_class(name)(bootstrap_with=clauses, use_timer=True, with_proof=with_proof)


def _cdcl_worker(conn, payload: dict) -> None:
    """Solve one instance in a child process and send the verdict back.

    The budget cannot be enforced from a thread: the bundled solvers hold the GIL
    for the whole run, so a `threading.Timer` never fires and an unresponsive
    instance would run forever (measured: a 10 s budget on the `K97` circulant
    instance was still running 90 s later).  A process that the parent can kill is
    the only mechanism that actually bounds the time — and an engine that can carry
    the budget itself is given a slightly smaller one, so it reports an expired
    budget instead of being killed mid-sentence.
    """
    try:
        n = int(payload["n"])
        sizes = tuple(payload["sizes"])
        proof_path = payload.get("proof_path")
        seconds = payload.get("seconds")
        if payload["kind"] == "circulant":
            instance = CirculantInstance(n, sizes)
        else:
            instance = MulticolourInstance(n, sizes, int(payload.get("symmetry", 0)))
        engine_budget = None if not seconds else max(1.0, float(seconds) * 0.85)
        with _open_solver(payload["solver"], instance.clauses(),
                          with_proof=bool(proof_path), timeout=engine_budget) as solver:
            verdict = solver.solve()
            solver_time = solver.time()
            out: dict = {"solver_time": solver_time}
            if verdict is True:
                text = instance.decode(solver.get_model())
                out.update(status="sat", coloring=text,
                           verified=verify_colouring(n, instance.sizes, text))
            elif verdict is False:
                out["status"] = "unsat"
                if proof_path:
                    # the trace is written here, in the child, and only its
                    # digest travels back: a K50 proof is ~30 MB of text
                    out["proof"] = DRAT.write_proof(proof_path, solver.get_proof() or [])
            else:
                out["status"] = "unknown"
    except Exception as exc:  # pragma: no cover - diagnostic path
        out = {"status": "error", "reason": f"{exc.__class__.__name__}: {exc}"}
    try:
        conn.send(out)
    finally:
        conn.close()


def _cdcl_with_budget(n: int, sizes, solver: str, seconds: float, kind: str,
                      symmetry: int = 0, proof_path=None) -> dict:
    """Run :func:`_cdcl_worker` with a hard, external time budget."""
    import multiprocessing as mp

    ctx = mp.get_context("spawn")
    parent, child = ctx.Pipe(duplex=False)
    proc = ctx.Process(target=_cdcl_worker,
                       args=(child, {"n": n, "sizes": list(sizes), "solver": solver,
                                     "kind": kind, "symmetry": symmetry, "seconds": seconds,
                                     "proof_path": str(proof_path) if proof_path else None}),
                       daemon=True)
    started = time.time()
    proc.start()
    proc.join(max(0.5, float(seconds)))
    if proc.is_alive():
        proc.terminate()
        proc.join(10)
        if proc.is_alive() and hasattr(proc, "kill"):  # pragma: no cover - defensive
            proc.kill()
        parent.close()
        return {"status": "unknown", "budget_expired": True,
                "seconds": time.time() - started}
    if parent.poll(10):
        out = parent.recv()
        parent.close()
        out["seconds"] = time.time() - started
        return out
    parent.close()
    return {"status": "unknown", "no_verdict": True, "exit_code": proc.exitcode,
            "seconds": time.time() - started}


def solver_class(name: str):
    """The class that answers under an engine's name, for a driver to build.

    ``solve`` and ``circulant_solve`` pick their engine themselves; a script that
    drives an engine directly — a cube-and-conquer run, say — needs the same
    choice, and :func:`solver_backing` is what says which of the two
    implementations of ``kissat404`` it is about to use.
    """
    return _solver_class(name)


def _solver_class(name: str):
    """The implementation behind an engine name.

    ``kissat404`` is backed by a real binary when there is one and by the bundled
    wheel otherwise — see :func:`solver_backing`, which is what tells the two
    apart in a report.
    """
    if name == "kissat404" and tools.kissat_command() is not None:
        return KissatBinary
    from pysat import solvers as ps

    table = {
        "cadical195": ps.Cadical195,
        "kissat404": ps.Kissat404,
        "maplechrono": ps.MapleChrono,
        "maplecm": ps.MapleCM,
        "glucose4": ps.Glucose4,
        "minisat22": ps.Minisat22,
    }
    return table[name]


def solve(
    n: int,
    sizes,
    seconds: float = 60.0,
    solver: str = "cadical195",
    symmetry: int = 0,
    dimacs_path=None,
    proof_path=None,
) -> dict:
    """Run a CDCL solver on a multicolour Ramsey instance.

    Returns the verdict (``"sat"``/``"unsat"``/``"unknown"``), the time, and for
    ``sat`` a colouring that has already been re-verified against the definition.
    ``unsat`` is the solver's verdict on that CNF; pass ``proof_path`` to have the
    DRAT trace written there, which :mod:`oplab.drat` then turns into a theorem.
    """
    instance = MulticolourInstance(n, sizes, symmetry)
    base = {
        "n": n,
        "sizes": list(instance.sizes),
        "solver": solver,
        "symmetry": symmetry,
        "num_vars": instance.total_vars(),
        "num_clauses": instance.clause_count(),
    }
    if solver not in available_solvers():
        return {**base, "status": "no-solver", "seconds": 0.0}
    verdict = _cdcl_with_budget(n, instance.sizes, solver, seconds, "multicolour", symmetry,
                                proof_path=proof_path)
    result = {**base, **verdict}
    if dimacs_path is not None:
        result["dimacs"] = instance.write_dimacs(dimacs_path)
    return result


# --------------------------------------------------------------------------
# local search
# --------------------------------------------------------------------------
def _remove_edge(A: np.ndarray, M: np.ndarray, c: int, iu: int, iv: int) -> None:
    """Delete edge ``(iu, iv)`` from colour ``c`` and update ``M = A_c @ A_c``.

    For ``A' = A - (e_u e_v^T + e_v e_u^T)`` we have

        ``A'^2 = A^2 - (col_u e_v^T + col_v e_u^T + e_v col_u^T + e_u col_v^T)
                 + (e_u e_u^T + e_v e_v^T)``,

    the last term because the two perturbation terms have disjoint supports.
    """
    col_u = A[c, :, iu].copy()
    col_v = A[c, :, iv].copy()
    M[c][:, iv] -= col_u
    M[c][:, iu] -= col_v
    M[c][iv, :] -= col_u
    M[c][iu, :] -= col_v
    M[c, iu, iu] += 1
    M[c, iv, iv] += 1
    A[c, iu, iv] = A[c, iv, iu] = 0


def _add_edge(A: np.ndarray, M: np.ndarray, c: int, iu: int, iv: int) -> None:
    """The mirror of :func:`_remove_edge`: add the edge and update ``M``."""
    col_u = A[c, :, iu].copy()
    col_v = A[c, :, iv].copy()
    M[c][:, iv] += col_u
    M[c][:, iu] += col_v
    M[c][iv, :] += col_u
    M[c][iu, :] += col_v
    M[c, iu, iu] += 1
    M[c, iv, iv] += 1
    A[c, iu, iv] = A[c, iv, iu] = 1


def _perturb(colouring: np.ndarray, fraction: float, rng, k: int) -> np.ndarray:
    """Recolour a random ``fraction`` of the edges, in place on a copy."""
    n = colouring.shape[0]
    u, v = edge_pairs(n)
    m = len(u)
    count = max(1, int(fraction * m))
    picks = rng.choice(m, size=count, replace=False)
    for i in picks:
        new_colour = int(rng.integers(0, k))
        colouring[u[i], v[i]] = colouring[v[i], u[i]] = new_colour
    return colouring


def _tabu_triangles(n: int, k: int, seconds: float, seed: int, tenure: int,
                    stagnation: int, on_improve=None, start=None) -> dict:
    """Tabu search for an all-triangles instance (exact incremental deltas).

    Each iteration evaluates *every* one-edge recolouring exactly — the delta of
    edge ``uv`` from colour ``c`` to ``c'`` is ``(A_{c'} A_{c'})_{uv} -
    (A_c A_c)_{uv}`` — and moves to the best one that is not tabu (tabu moves are
    still allowed when they beat the incumbent).  After ``stagnation`` stalled
    moves the incumbent is kicked rather than abandoned, and every other attempt
    restarts from a fresh random colouring.
    """
    rng = np.random.default_rng(seed)
    deadline = time.time() + seconds
    u, v = edge_pairs(n)
    m = len(u)
    idx = np.arange(m)
    BIG = np.int64(1) << 40
    best_total, best_text = None, None
    steps = 0
    attempts = 0
    incumbent = None

    while time.time() < deadline:
        attempts += 1
        if start is not None and attempts == 1:
            colouring = parse_colouring(start, n, k)
        elif incumbent is not None and attempts % 2 == 1:
            colouring = _perturb(incumbent.copy(), 0.03, rng, k)
        else:
            colouring = random_colouring(n, k, rng)
        A = np.zeros((k, n, n), dtype=np.int64)
        for c in range(k):
            A[c] = colouring == c
            np.fill_diagonal(A[c], 0)
        M = np.einsum("cij,cjk->cik", A, A)
        cur = colouring[u, v].astype(np.int64)
        total = int(M[cur, u, v].sum() // 3)
        tabu_until = np.zeros((n, n), dtype=np.int64)
        step = 0
        local_best = total
        local_best_text = serialize_colouring(colouring, n)
        since_improvement = 0

        while time.time() < deadline and since_improvement < stagnation:
            step += 1
            steps += 1
            delta = M[:, u, v] - M[cur, u, v][None, :]
            delta[cur, idx] = BIG
            blocked = tabu_until[u, v] > step
            if blocked.any():
                aspiration = total + delta < local_best
                delta = np.where(blocked[None, :], np.where(aspiration, delta, BIG), delta)
            new_c, e = divmod(int(np.argmin(delta)), m)
            if delta[new_c, e] >= BIG:
                break
            iu, iv = int(u[e]), int(v[e])
            old_c = int(cur[e])
            total += int(M[new_c, iu, iv] - M[old_c, iu, iv])
            _remove_edge(A, M, old_c, iu, iv)
            _add_edge(A, M, new_c, iu, iv)
            colouring[iu, iv] = colouring[iv, iu] = new_c
            cur[e] = new_c
            tabu_until[iu, iv] = tabu_until[iv, iu] = step + tenure + int(rng.integers(0, tenure + 1))
            if total < local_best:
                local_best = total
                local_best_text = serialize_colouring(colouring, n)
                since_improvement = 0
                if on_improve is not None:
                    on_improve(attempts, steps, local_best)
                if local_best == 0:
                    break
            else:
                since_improvement += 1

        if local_best == 0:
            counts = [0] * k
        else:
            counts = mono_clique_counts(n, (3,) * k, parse_colouring(local_best_text, n, k))
        if best_total is None or local_best < best_total:
            best_total, best_text = local_best, local_best_text
            verified = counts
        if best_total == 0:
            break
        incumbent = parse_colouring(best_text, n, k)
        if time.time() >= deadline:
            break

    return {
        "n": n,
        "sizes": [3] * k,
        "coloring": best_text,
        "violations": best_total,
        "monochromatic_cliques": verified,
        "steps": steps,
        "attempts": attempts,
        "seconds": seconds,
        "seed": seed,
        "verified_zero": best_total == 0,
    }


def _triangle_total(masks: list[list[int]], n: int, k: int) -> int:
    """Exact number of monochromatic triangles from per-colour bitmasks."""
    total = 0
    for c in range(k):
        rows = masks[c]
        for u in range(n):
            remaining = rows[u] & ~((1 << (u + 1)) - 1)
            while remaining:
                w = (remaining & -remaining).bit_length() - 1
                remaining &= remaining - 1
                total += (rows[w] & remaining).bit_count()
    return total


def _tabu_bits(n: int, k: int, seconds: float, seed: int, tenure: int = 10,
               focus: float = 0.9, kick: int = 40, restart: int = 120_000,
               on_improve=None, start=None, stagnation: int | None = None) -> dict:
    """Bit-parallel tabu search for an all-triangles instance.

    The delta of recolouring an edge ``uv`` from colour ``c`` to ``c'`` is
    ``|N_{c'}(u) & N_{c'}(v)| - |N_c(u) & N_c(v)|``, and a neighbourhood is a
    big-integer bitmask, so a move costs a few ``int.bit_count()`` calls and four
    mask updates.  That is one to two orders of magnitude more moves per second
    than the matrix engine, at the price of evaluating one edge at a time instead
    of the whole neighbourhood.  Most moves are aimed at an edge that still lies
    in a monochromatic triangle (``focus``); ``kick`` random recolourings shake
    the incumbent when it stalls, and a fresh random colouring is started after
    ``restart`` stalled moves.
    """
    rng = random.Random(seed)
    pairs = edges(n)
    m = len(pairs)
    ue = [e[0] for e in pairs]
    ve = [e[1] for e in pairs]
    popcount = int.bit_count
    deadline = time.time() + seconds
    stagnation = stagnation or 10 ** 9

    if start is not None:
        colouring = parse_colouring(start, n, k)
        cur0 = [int(colouring[ue[i], ve[i]]) for i in range(m)]
    else:
        cur0 = [rng.randrange(k) for _ in range(m)]

    def build(cur):
        masks = [[0] * n for _ in range(k)]
        for i in range(m):
            c = cur[i]
            masks[c][ue[i]] |= 1 << ve[i]
            masks[c][ve[i]] |= 1 << ue[i]
        return masks

    cur = list(cur0)
    masks = build(cur)
    total = _triangle_total(masks, n, k)
    best, best_cur = total, list(cur)
    tabu = [0] * m
    step = 0
    since = 0
    while time.time() < deadline:
        step += 1
        i = rng.randrange(m)
        if rng.random() < focus:
            for _ in range(24):
                c = cur[i]
                if (masks[c][ue[i]] & masks[c][ve[i]]).bit_count() > 0:
                    break
                i = rng.randrange(m)
        u, v = ue[i], ve[i]
        c = cur[i]
        base = (masks[c][u] & masks[c][v]).bit_count()
        best_d, best_c = None, None
        for c2 in range(k):
            if c2 == c:
                continue
            d = (masks[c2][u] & masks[c2][v]).bit_count() - base
            if tabu[i] > step and total + d >= best:
                continue
            if best_d is None or d < best_d or (d == best_d and rng.random() < 0.5):
                best_d, best_c = d, c2
        if best_c is None:
            continue
        total += best_d
        masks[c][u] &= ~(1 << v)
        masks[c][v] &= ~(1 << u)
        masks[best_c][u] |= 1 << v
        masks[best_c][v] |= 1 << u
        cur[i] = best_c
        tabu[i] = step + tenure + rng.randrange(tenure + 1)

        if total < best:
            best = total
            best_cur = list(cur)
            since = 0
            if on_improve is not None:
                on_improve(1, step, best)
            if best == 0:
                break
        elif since >= stagnation:
            break
        else:
            since += 1
            if since == kick:  # shake the incumbent
                cur = list(best_cur)
                masks = build(cur)
                total = best
                for _ in range(1 + rng.randrange(max(2, m // 20))):
                    i2 = rng.randrange(m)
                    c2 = cur[i2]
                    c3 = rng.randrange(k - 1)
                    if c3 >= c2:
                        c3 += 1
                    u2, v2 = ue[i2], ve[i2]
                    total += (masks[c3][u2] & masks[c3][v2]).bit_count() \
                        - (masks[c2][u2] & masks[c2][v2]).bit_count()
                    masks[c2][u2] &= ~(1 << v2)
                    masks[c2][v2] &= ~(1 << u2)
                    masks[c3][u2] |= 1 << v2
                    masks[c3][v2] |= 1 << u2
                    cur[i2] = c3
                since = 0
            elif since > restart:  # fresh restart
                cur = [rng.randrange(k) for _ in range(m)]
                masks = build(cur)
                total = _triangle_total(masks, n, k)
                since = 0

    text = serialize_colouring(parse_colouring(
        "".join(str(c) for c in best_cur), n, k), n)
    check = verify_colouring(n, (3,) * k, text)
    return {
        "n": n,
        "sizes": [3] * k,
        "coloring": text,
        "violations": int(sum(check["monochromatic_cliques"])),
        "monochromatic_cliques": check["monochromatic_cliques"],
        "steps": step,
        "attempts": 1,
        "seconds": seconds,
        "seed": seed,
        "verified_zero": check["valid"],
    }


def _tabu_general(n: int, sizes, seconds: float, seed: int, on_improve=None,
                  stagnation: int = 4000, start=None) -> dict:
    """Min-conflicts search for instances with cliques larger than a triangle.

    Exact violation counts are recomputed for a sampled move, which is slower
    than the triangle engine; it is the fallback for colours that forbid ``K_4``
    or larger.
    """
    rng = np.random.default_rng(seed)
    deadline = time.time() + seconds
    k = len(sizes)
    best_total, best_text, best_counts = None, None, None
    steps = 0
    attempts = 0

    while time.time() < deadline:
        attempts += 1
        colouring = start if (start is not None and attempts == 1) else random_colouring(n, k, rng)
        counts = mono_clique_counts(n, sizes, colouring)
        total = int(sum(counts))
        local_best = total
        local_best_text = serialize_colouring(colouring, n)
        since_improvement = 0

        while time.time() < deadline and since_improvement < stagnation:
            steps += 1
            move = _min_conflicts_move(n, sizes, colouring, counts, rng)
            if move is None:
                break
            a, b, new_c = move
            old_c = int(colouring[a, b])
            if old_c == new_c:
                colouring[a, b] = colouring[b, a] = int(rng.integers(0, k))
            else:
                colouring[a, b] = colouring[b, a] = new_c
            counts = mono_clique_counts(n, sizes, colouring)
            total = int(sum(counts))
            if total < local_best:
                local_best = total
                local_best_text = serialize_colouring(colouring, n)
                since_improvement = 0
                if on_improve is not None:
                    on_improve(attempts, steps, local_best)
                if local_best == 0:
                    break
            else:
                since_improvement += 1

        if best_total is None or local_best < best_total:
            best_total, best_text = local_best, local_best_text
            best_counts = mono_clique_counts(n, sizes, parse_colouring(best_text, n, k))
        if best_total == 0:
            break

    return {
        "n": n,
        "sizes": list(sizes),
        "coloring": best_text,
        "violations": best_total,
        "monochromatic_cliques": best_counts,
        "steps": steps,
        "attempts": attempts,
        "seconds": seconds,
        "seed": seed,
        "verified_zero": best_total == 0,
    }


def _min_conflicts_move(n: int, sizes, colouring: np.ndarray, counts, rng):
    """Recolour an edge inside a violated clique, preferring the free colour."""
    worst = int(np.argmax(counts))
    if counts[worst] == 0:
        return None
    s = sizes[worst]
    masks = adjacency_masks(colouring, n, worst)
    for _ in range(200):
        a = int(rng.integers(n))
        candidates = [b for b in range(n) if (masks[a] >> b) & 1]
        if len(candidates) < s - 1:
            continue
        chosen = [a] + [int(c) for c in rng.choice(candidates, size=s - 1, replace=False)]
        if all((masks[x] >> y) & 1 for x, y in itertools.combinations(chosen, 2)):
            pair = tuple(sorted(rng.choice(chosen, size=2, replace=False).tolist()))
            new_c = int(rng.integers(len(sizes) - 1))
            if new_c >= worst:
                new_c += 1
            return pair[0], pair[1], new_c
    a, b = (int(x) for x in rng.choice(n, size=2, replace=False))
    return a, b, int(rng.integers(len(sizes)))


def tabu_search(
    n: int,
    sizes,
    seconds: float = 60.0,
    seed: int = 0,
    tenure: int = 12,
    stagnation: int | None = None,
    on_improve=None,
    start: str | None = None,
    engine: str = "auto",
) -> dict:
    """Search for a multicolour Ramsey witness, minimising violations.

    ``start`` optionally seeds an attempt with a stored colouring string
    (extension search: keep a known witness and look for a colouring of one more
    vertex).  ``engine`` is ``"matrix"``, ``"bits"`` or ``"auto"``: the matrix
    engine evaluates the whole one-edge neighbourhood at every step and is the
    stronger per step, the bit-parallel engine makes one to two orders of
    magnitude more steps per second and wins on the large all-triangles
    instances.  The returned ``violations`` is the exact number of monochromatic
    forbidden cliques of the best colouring found; ``0`` is a witness, and it is
    only ever reported after :func:`verify_colouring` agrees.
    """
    sizes = tuple(int(s) for s in sizes)
    colouring = parse_colouring(start, n, len(sizes)) if start else None
    if all(s == 3 for s in sizes):
        if engine == "bits" or (engine == "auto" and n >= 96):
            return _tabu_bits(n, len(sizes), seconds, seed, tenure=tenure,
                              on_improve=on_improve, start=start, stagnation=stagnation)
        return _tabu_triangles(
            n, len(sizes), seconds, seed, tenure,
            stagnation or 200_000, on_improve, colouring,
        )
    return _tabu_general(n, sizes, seconds, seed, on_improve, stagnation or 4_000, colouring)


# --------------------------------------------------------------------------
# the circulant sub-family of the multicolour frontier
# --------------------------------------------------------------------------
# A *circulant* colouring assigns one colour to each difference class of ``Z_n``
# (``d`` and ``n - d`` are the same class), so it is described by ``n // 2``
# choices instead of ``C(n, 2)``.  What makes the sub-family worth deciding is
# that the question "is there a circulant witness here?" is a CNF with a few
# hundred variables and a few thousand clauses, which a CDCL solver answers in
# seconds — where the general instances (see :func:`solve`) defeat it entirely.
#
# A *positive* answer is a witness and therefore fully verifiable by
# :func:`verify_colouring`.  A *negative* answer is a solver verdict unless a DRAT
# trace was requested (``proof_path``), which makes it a theorem *about this
# encoding* — checked by :mod:`oplab.drat`, not by the solver.  One negative needs
# no solver at all: when ``3 | n`` and every colour forbids a triangle, the class
# ``n // 3`` is forced to make ``{0, n/3, 2n/3}`` monochromatic, so no circulant
# colouring is clean there and the verdict is arithmetic (:func:`circulant_obstruction`).
def difference_classes(n: int) -> list[int]:
    """The difference classes of ``Z_n``: ``1 .. n // 2`` (``n/2`` is self-inverse)."""
    return list(range(1, n // 2 + 1))


def difference_class(d: int, n: int) -> int:
    """Class of the difference ``d``, i.e. ``min(d mod n, -d mod n)``."""
    d %= n
    return min(d, n - d)


def circulant_colouring(n: int, colour_of_class) -> np.ndarray:
    """Expand a per-class colour assignment into a full ``(n, n)`` colouring."""
    colouring = np.zeros((n, n), dtype=np.int8)
    for d in difference_classes(n):
        c = int(colour_of_class[d])
        for x in range(n):
            colouring[x, (x + d) % n] = colouring[(x + d) % n, x] = c
    return colouring


def clique_class_groups(n: int, s: int) -> list[tuple[int, ...]]:
    """Every distinct set of edge classes that an ``s``-clique of ``K_n`` can use.

    A clique can be translated to contain vertex 0, so enumerating the ``s - 1``
    remaining vertices is complete.  Two cliques that share a class set yield the
    same constraint — "these classes are not all one colour" — so duplicates are
    dropped; a class set that no clique induces cannot appear, because every
    class set here comes from an actual clique.
    """
    if s < 2 or s > n:
        raise ValueError(f"no {s}-cliques in K{n}")
    groups: dict[tuple[int, ...], None] = {}
    for rest in itertools.combinations(range(1, n), s - 1):
        vertices = (0,) + rest
        classes = {difference_class(v - u, n)
                   for i, u in enumerate(vertices) for v in vertices[i + 1:]}
        groups.setdefault(tuple(sorted(classes)), None)
    return sorted(groups, key=lambda g: (len(g), g))


def circulant_obstruction(n: int, sizes) -> dict | None:
    """The unconditional ``3 | n`` obstruction, or ``None``.

    If ``3 | n`` and every colour forbids a triangle, then whichever colour the
    class ``n // 3`` gets, the ``n // 3`` triangles ``{x, x + n/3, x + 2n/3}``
    are monochromatic in that colour — every circulant colouring of ``K_n`` has a
    monochromatic triangle.  The claim is arithmetic and needs no search.
    """
    sizes = tuple(int(s) for s in sizes)
    if all(s == 3 for s in sizes) and n % 3 == 0:
        return {"class": n // 3, "triangle": (0, n // 3, 2 * n // 3), "triangles": n // 3}
    return None


class CirculantInstance:
    """CNF whose models are exactly the clean circulant colourings of ``K_n``.

    One variable per (difference class, colour), one-hot per class, and one clause
    per ``(colour, clique)`` pair: the classes of that clique may not all carry
    the forbidden colour.  Because a class-set clause is satisfied by *any* clique
    that induces it, the encoding is equivalent to cleanliness — not merely
    implied by it — which is what the test suite checks by exhausting every class
    assignment on a small ``n``.
    """

    def __init__(self, n: int, sizes):
        sizes = tuple(int(s) for s in sizes)
        if any(s < 3 or s > n for s in sizes):
            raise ValueError("need 3 <= s_c <= n for every colour")
        self.n = n
        self.sizes = sizes
        self.k = len(sizes)
        self.classes = difference_classes(n)
        self._index = {d: i for i, d in enumerate(self.classes)}
        #: clique size -> class sets, computed only for the sizes actually used
        self.groups = {s: clique_class_groups(n, s) for s in sorted(set(sizes))}

    def var(self, d: int, colour: int) -> int:
        return self._index[d] * self.k + colour + 1

    def total_vars(self) -> int:
        return len(self.classes) * self.k

    def clause_count(self) -> int:
        one_hot = len(self.classes) * (1 + comb(self.k, 2))
        return one_hot + sum(len(self.groups[s]) for s in self.sizes)

    def clauses(self):
        for d in self.classes:
            lits = [self.var(d, c) for c in range(self.k)]
            yield tuple(lits)
            for a in range(self.k):
                for b in range(a + 1, self.k):
                    yield (-lits[a], -lits[b])
        for colour, s in enumerate(self.sizes):
            for group in self.groups[s]:
                yield tuple(-self.var(d, colour) for d in group)

    def write_dimacs(self, path, comment: str = "") -> dict:
        written = 0
        with open(path, "w", encoding="ascii", newline="\n") as handle:
            handle.write(f"c {comment or f'circulant multicolour Ramsey K_{self.n} {self.sizes}'}\n")
            handle.write(f"p cnf {self.total_vars()} {self.clause_count()}\n")
            for clause in self.clauses():
                handle.write(" ".join(map(str, clause)) + " 0\n")
                written += 1
        return {"path": str(path), "clauses_written": written, "num_vars": self.total_vars()}

    def decode(self, model) -> str:
        """Turn a model into the expanded colouring string of ``K_n``."""
        truth = {lit for lit in model if lit > 0}
        assignment = {}
        for d in self.classes:
            found = [c for c in range(self.k) if self.var(d, c) in truth]
            if len(found) != 1:
                raise ValueError(f"class {d} is not assigned exactly one colour")
            assignment[d] = found[0]
        return serialize_colouring(circulant_colouring(self.n, assignment), self.n)

    def assignment(self, colours) -> set[int]:
        """The true literals of a per-class colour assignment (for clause tests)."""
        return {self.var(d, int(colours[d])) for d in self.classes}


def circulant_solve(n: int, sizes, seconds: float = 60.0, solver: str = "cadical195",
                    dimacs_path=None, proof_path=None) -> dict:
    """Decide whether a circulant witness exists for one multicolour instance.

    Statuses: ``"obstructed"`` (the ``3 | n`` obstruction above, decided by
    arithmetic), ``"sat"`` (a colouring that :func:`verify_colouring` re-counts as
    clean), ``"unsat"`` (the solver's verdict on the CNF — a statement about the
    circulant sub-family only, and not a proof), ``"unknown"`` or ``"no-solver"``.
    """
    instance = CirculantInstance(n, sizes)
    base = {
        "n": n,
        "sizes": list(instance.sizes),
        "solver": solver,
        "classes": len(instance.classes),
        "clique_groups": {str(s): len(instance.groups[s]) for s in instance.groups},
        "num_vars": instance.total_vars(),
        "num_clauses": instance.clause_count(),
    }
    obstruction = circulant_obstruction(n, instance.sizes)
    if obstruction is not None:
        base["obstruction"] = obstruction
        base["status"] = "obstructed"
        base["seconds"] = 0.0
        return base
    if solver not in available_solvers():
        return {**base, "status": "no-solver", "seconds": 0.0}
    result = {**base, **_cdcl_with_budget(n, instance.sizes, solver, seconds, "circulant",
                                          proof_path=proof_path)}
    if dimacs_path is not None:
        result["dimacs"] = instance.write_dimacs(dimacs_path)
    return result


# --------------------------------------------------------------------------
# stored witnesses
# --------------------------------------------------------------------------
def stored_colouring(name: str) -> str | None:
    """The colouring string of a stored witness in ``certs/ramsey/``, if any."""
    path = CERT_DIR / f"{name.replace(',', '_').replace('(', '').replace(')', '')}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8")).get("coloring")
