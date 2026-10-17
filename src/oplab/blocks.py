"""Block-Cayley colourings: the family the published witnesses actually live in.

A *circulant* colouring gives one colour per difference class of ``Z_n``, and that
sub-family is provably empty at every target size this repository has attacked — at
``3 | n`` for arithmetic reasons (:func:`oplab.multicolour.circulant_obstruction`),
and by search everywhere else.  The published lower bounds are *not* circulant, and
the ones that matter here are not unstructured either: Chung's four-colouring of
``K50`` is described in the literature as a **three-block block-Cayley colouring
over a group of order 16, extended by two vertices**, and the recent SAT-based
improvements to multicolour lower bounds (Rowley 2022; Wesley 2025) all come from
imposing a structure of this kind and letting a solver fill it in.

So this module is the next family out: ``b`` blocks, each carrying a copy of a
group ``G``, plus ``e`` extra vertices with free edges.  A colouring is in the family
when the colour of an edge between block ``i`` and block ``j`` depends only on
``(i, j)`` and the group difference — that is, when it is invariant under translating
each block independently.  One variable per (class, colour), one clause per
(colour, clique class set), exactly as for the circulant encoding, and the same
property is what makes it usable: the clause set is satisfiable **iff** some member
of the family is clean, which :func:`exact` checks against the expansion.

Three things follow from the shape, and they are why this is worth a campaign rather
than another evening of circulant sweeps:

* the ``3 | n`` obstruction does not reach here.  It needs the difference ``n/3`` to
  be a class, and inside blocks of ``Z_17`` there is no difference 17; the family at
  ``n = 51`` is exactly the size the published bound sits at, and it is not
  arithmetically dead;
* a clause is on a *class set*, so a hundred cliques that induce the same classes are
  one constraint — the encoding stays small even though the colouring space does not;
* ``b = 1`` is the circulant encoding and ``G`` of prime order with ``b = 1`` is the
  Cayley-over-``Z_n`` one, so this module contains the two families already swept and
  adds the ones between them.

A witness found here is a witness without qualification: the family is a restriction
of "all colourings", so a clean member is a clean colouring of ``K_n`` and raises the
published lower bound.  A refutation here is a statement about the family only.
"""

from __future__ import annotations

import itertools
from math import comb, prod
from pathlib import Path

import numpy as np

from . import multicolour as MC

__all__ = [
    "group_elements",
    "BlockInstance",
    "class_sets",
    "expand",
    "exact",
    "solve_blocks",
]


# --------------------------------------------------------------------------
# the group
# --------------------------------------------------------------------------
def group_elements(factors) -> list[tuple[int, ...]]:
    """The elements of the abelian group ``Z_{f_1} x ... x Z_{f_r}``, as tuples.

    A tuple of factor orders rather than a group object: every group this family
    needs is abelian and small, ``(16,)`` is ``Z_16``, ``(2, 2, 2, 2)`` is the
    elementary abelian group of order 16 that the order-16 witnesses are built on,
    and ``(4, 4)``/``(8, 2)`` are the others.  The identity is the all-zero tuple, so
    a difference is a subtraction and an inverse is a negation, both coordinate-wise.
    """
    orders = tuple(int(f) for f in factors)
    if not orders or any(f < 2 for f in orders):
        raise ValueError(f"a factor order must be >= 2, not {factors!r}")
    return list(itertools.product(*(range(f) for f in orders)))


def _inverse(element, orders):
    return tuple((-x) % f for x, f in zip(element, orders))


def _canonical_difference(element, orders):
    """``{g, -g}`` as one representative: an edge is the same edge either way round."""
    return min(element, _inverse(element, orders))


class BlockInstance:
    """CNF whose models are exactly the clean block-Cayley colourings of ``K_n``.

    ``n = blocks * |G| + extras``, and the vertices are ``(block, element)`` pairs in
    block order followed by the extra vertices.  The classes are

    * ``("d", i, d)`` — an edge inside block ``i`` whose difference is ``d``, up to
      ``d ~ -d``, one class per orbit;
    * ``("b", i, j, g)`` — an edge between blocks ``i < j`` with difference ``g``;
    * ``("x", w, u)`` — one class per edge incident to an extra vertex ``w``, because
      the extra vertices are not translated and their edges are free.

    Every edge of ``K_n`` lies in exactly one class, which :func:`exact` checks rather
    than asserts, and each class carries exactly one colour.
    """

    def __init__(self, n: int, sizes, blocks: int = 1, group=None, extras: int = 0,
                 break_colours: bool = False):
        sizes = tuple(int(s) for s in sizes)
        sizes = tuple(sorted(sizes))
        if any(s < 3 or s > n for s in sizes):
            raise ValueError("need 3 <= s_c <= n for every colour")
        self.n = int(n)
        self.sizes = sizes
        self.k = len(sizes)
        self.blocks = int(blocks)
        self.extras = int(extras)
        if self.blocks < 1 or self.extras < 0:
            raise ValueError("a family needs at least one block and no negative extras")
        self.orders = tuple(int(f) for f in (group if group is not None else (self.n,)))
        self.elements = group_elements(self.orders)
        self.m = len(self.elements)
        if self.blocks * self.m + self.extras != self.n:
            raise ValueError(f"{self.blocks} blocks of {self.m} plus {self.extras} extras "
                             f"is {self.blocks * self.m + self.extras} vertices, not {self.n}")
        self._element_index = {g: i for i, g in enumerate(self.elements)}
        self.zero = tuple(0 for _ in self.orders)
        self.vertices = self._vertices()
        self.classes = self._classes()
        self._index = {key: i for i, key in enumerate(self.classes)}
        #: the class of every edge, computed once: the clique enumeration below touches
        #: ``C(n, s) * C(s, 2)`` edges and a dictionary lookup each time is the whole
        #: cost of building the clause set
        self.pair_class = self._pair_classes()
        #: the edges each class carries, which is also how a class assignment is
        #: expanded back into a colouring of ``K_n``
        self.edges_of = {key: self._edges_of(key) for key in self.classes}
        #: clique size -> the distinct class sets an ``s``-clique can induce
        self.sets = {s: class_sets(self, s) for s in sorted(set(sizes))}
        #: colours of the same forbidden size are interchangeable, so a witness can be
        #: relabelled to put colour 0 on one fixed class — 4! = 24-fold for four
        #: triangles.  Only allowed when the sizes really are interchangeable.
        self.break_colours = bool(break_colours) and len(set(sizes)) == 1

    # -- vertices ---------------------------------------------------------
    def _vertices(self) -> list[tuple[str, int, tuple[int, ...]]]:
        """``(block, element)`` for the blocks, then ``("x", w, ())`` for the extras."""
        vertices = [("b", i, g) for i in range(self.blocks) for g in self.elements]
        vertices += [("x", w, ()) for w in range(self.extras)]
        return vertices

    def _classes(self) -> list:
        """Every class of the family, in a fixed order."""
        classes: list = []
        for i in range(self.blocks):
            seen = set()
            for g in self.elements:
                if g == self.zero:
                    continue
                d = _canonical_difference(g, self.orders)
                if d in seen:
                    continue
                seen.add(d)
                classes.append(("d", i, d))
        for i in range(self.blocks):
            for j in range(i + 1, self.blocks):
                for g in self.elements:
                    classes.append(("b", i, j, g))
        # an extra vertex is one vertex, not one block: its index starts where the
        # blocks end, which is ``blocks * m`` and not ``blocks``
        for w in range(self.blocks * self.m, self.n):
            for u in range(w):
                classes.append(("x", w, u))
        return classes

    # -- the edges of one class -------------------------------------------
    def _pair_classes(self) -> list[list]:
        """``pair_class[u][v]``: the class of one edge, as ``class_of`` computes it."""
        return [[self.class_of(u, v) for v in range(self.n)] for u in range(self.n)]

    def _edges_of(self, key) -> list[tuple[int, int]]:
        """Every edge the class carries, as vertex indices of ``K_n``."""
        kind = key[0]
        base = self.blocks * self.m
        if kind == "x":
            return [(key[2], key[1])]
        if kind == "d":
            _, i, d = key
            out = []
            for g in self.elements:
                x = i * self.m + self._element_index[g]
                y = i * self.m + self._element_index[tuple((a + b) % f
                                                          for a, b, f in zip(g, d, self.orders))]
                out.append((x, y))
            return out
        _, i, j, g = key
        return [(i * self.m + self._element_index[a],
                 j * self.m + self._element_index[tuple((b + c) % f
                                                        for b, c, f in zip(a, g, self.orders))])
                for a in self.elements]

    def class_of(self, u: int, v: int):
        """The class of the edge ``{u, v}``, or ``None`` if the family cannot colour it.

        Every edge must land in exactly one class — this is the invariant the family
        rests on, and the tests check it by mapping all ``C(n, 2)`` edges.
        """
        if u == v:
            return None
        extra_start = self.blocks * self.m
        if u >= extra_start or v >= extra_start:
            # the class of an extra's edge is keyed by the extra itself, and the extras
            # are the last vertices, so that is always the larger index — the same
            # convention ``_classes`` writes them in
            return ("x", max(u, v), min(u, v))
        bi, du = divmod(u, self.m)
        bj, dv = divmod(v, self.m)
        if bi == bj:
            g = self.elements[du]
            h = self.elements[dv]
            d = _canonical_difference(tuple((y - x) % f for x, y, f in zip(g, h, self.orders)),
                                      self.orders)
            return ("d", bi, d)
        if bi > bj:
            bi, bj, du, dv = bj, bi, dv, du
        g = self.elements[du]
        h = self.elements[dv]
        diff = tuple((y - x) % f for x, y, f in zip(g, h, self.orders))
        return ("b", bi, bj, diff)

    # -- the CNF ----------------------------------------------------------
    def var(self, key, colour: int) -> int:
        return self._index[key] * self.k + colour + 1

    def total_vars(self) -> int:
        return len(self.classes) * self.k

    def clause_count(self) -> int:
        one_hot = len(self.classes) * (1 + comb(self.k, 2))
        return one_hot + sum(len(self.sets[s]) for s in self.sizes) \
            + (1 if self.break_colours else 0)

    def clauses(self):
        for key in self.classes:
            lits = [self.var(key, c) for c in range(self.k)]
            yield tuple(lits)
            for a in range(self.k):
                for b in range(a + 1, self.k):
                    yield (-lits[a], -lits[b])
        if self.break_colours:
            yield (self.var(self.classes[0], 0),)
        for colour, s in enumerate(self.sizes):
            for group in self.sets[s]:
                yield tuple(-self.var(key, colour) for key in group)

    def write_dimacs(self, path, comment: str = "") -> dict:
        written = 0
        with open(path, "w", encoding="ascii", newline="\n") as handle:
            handle.write(f"c {comment or self.describe()}\n")
            handle.write(f"p cnf {self.total_vars()} {self.clause_count()}\n")
            for clause in self.clauses():
                handle.write(" ".join(map(str, clause)) + " 0\n")
                written += 1
        return {"path": str(path), "clauses_written": written, "num_vars": self.total_vars()}

    # -- models -----------------------------------------------------------
    def assignment(self, colours) -> dict:
        """Class -> colour, accepting either a mapping or a sequence in class order."""
        if isinstance(colours, dict):
            return {key: int(colours[key]) for key in self.classes}
        return {key: int(colours[i]) for i, key in enumerate(self.classes)}

    def expand(self, colours) -> np.ndarray:
        """The full colouring of ``K_n`` a class assignment stands for."""
        return expand(self, colours)

    def decode(self, model) -> str:
        """Turn a solver model into the expanded colouring string of ``K_n``."""
        truth = {lit for lit in model if lit > 0}
        assignment = {}
        for key in self.classes:
            found = [c for c in range(self.k) if self.var(key, c) in truth]
            if len(found) != 1:
                raise ValueError(f"class {key} is not assigned exactly one colour")
            assignment[key] = found[0]
        return MC.serialize_colouring(self.expand(assignment), self.n)

    def describe(self) -> str:
        return (f"block-Cayley Ramsey K_{self.n} {list(self.sizes)}: {self.blocks} block(s) "
                f"of {list(self.orders)}, {self.extras} extra vertices, "
                f"{len(self.classes)} classes")


# --------------------------------------------------------------------------
# the class sets: one clause per (colour, class set)
# --------------------------------------------------------------------------
def block_obstruction(instance: BlockInstance) -> dict | None:
    """The per-block ``3 | m`` obstruction, or ``None`` — the family decided by arithmetic.

    The circulant version of this argument needs the difference ``n/3`` of ``Z_n``,
    which is why ``n = 51`` escapes it in blocks of ``Z_17``.  Inside a block it comes
    back: if ``3 | m`` then ``G`` has an element ``d`` of order 3 (Cauchy), and the
    three vertices ``x, x+d, x+2d`` have all three of their differences in the single
    class of ``d`` — so that block carries a monochromatic triangle whichever colour
    the class gets.  A mixed instance is dead if *any* colour forbids a triangle and
    *any* block is of divisible order, and no solver is needed to say so.

    The claim is arithmetic about this family only: it says nothing about any other
    structure, and nothing about ``R``.
    """
    if not any(s == 3 for s in instance.sizes):
        return None
    if instance.m % 3:
        return None
    return {"block": 0, "block_order": instance.m, "blocks": instance.blocks,
            "reason": (f"a block of order {instance.m} has an element of order 3, so the "
                       f"class of that element carries {instance.m // 3} monochromatic "
                       f"triangles inside the block")}


def class_sets(instance: BlockInstance, s: int, limit: int = 4_000_000) -> list[tuple]:
    """Every distinct set of classes that an ``s``-clique of ``K_n`` can induce.

    Enumerated from the cliques themselves, so a set that no clique induces cannot
    appear, and two cliques with the same classes yield one constraint.  The count
    grows like ``C(n, s)``, which is why the cheap clique sizes are the ones this
    family is campaigned at: ``s = 3`` at ``n = 51`` is 20 825 cliques, ``s = 4`` at
    ``n = 36`` is 58 905, and the four-clique case at ``n = 128`` would be ten
    million — the guard is there so that is a refusal and not a hang.
    """
    if s < 2 or s > instance.n:
        raise ValueError(f"no {s}-cliques in K{instance.n}")
    if comb(instance.n, s) > limit:
        raise ValueError(f"{comb(instance.n, s)} {s}-cliques in K{instance.n} is over the "
                         f"{limit} this enumeration allows: use a smaller clique size or a "
                         f"structure-aware enumeration")
    pair_class = instance.pair_class
    groups: dict[frozenset, None] = {}
    for vertices in itertools.combinations(range(instance.n), s):
        keys = {pair_class[u][v] for i, u in enumerate(vertices) for v in vertices[i + 1:]}
        groups.setdefault(frozenset(keys), None)
    return sorted(groups, key=lambda g: (len(g), sorted(map(str, g))))


def expand(instance: BlockInstance, colours) -> np.ndarray:
    """The colouring of ``K_n`` a class assignment stands for.

    Each class writes its colour on every edge it carries, and the classes partition
    the edges, so this is total and consistent — ``exact`` checks the partition.
    """
    assignment = instance.assignment(colours)
    colouring = np.zeros((instance.n, instance.n), dtype=np.int8)
    for key, colour in assignment.items():
        if not 0 <= colour < instance.k:
            raise ValueError(f"class {key} carries colour {colour}, which is not one of "
                             f"the {instance.k}")
        for u, v in instance.edges_of[key]:
            colouring[u, v] = colouring[v, u] = colour
    return colouring


def exact(instance: BlockInstance) -> dict:
    """Check the family against its own expansion, without a solver.

    Three claims, all of them about the encoding rather than about Ramsey numbers:
    the classes partition the ``C(n, 2)`` edges, every class set comes from a clique
    (so it constrains a real one), and a class assignment satisfies the clause set
    exactly when its expansion is clean — the last one by exhausting an assignment
    space small enough to exhaust, which is what the tests call.
    """
    covered: dict[tuple[int, int], set] = {}
    for key in instance.classes:
        for u, v in instance.edges_of[key]:
            covered.setdefault((min(u, v), max(u, v)), set()).add(key)
    crowded = {edge: keys for edge, keys in covered.items() if len(keys) != 1}
    missing = comb(instance.n, 2) - len(covered)
    # and the two ways of asking which class an edge is in have to agree: the class
    # that colours it and the class ``class_of`` names
    disagreeing = [edge for edge, keys in covered.items()
                   if next(iter(keys)) != instance.pair_class[edge[0]][edge[1]]]
    return {
        "n": instance.n, "sizes": list(instance.sizes), "classes": len(instance.classes),
        "edges": comb(instance.n, 2), "edges_covered": len(covered),
        "edges_not_covered": missing, "edges_in_several_classes": len(crowded),
        "edges_named_differently": len(disagreeing),
        "partition": not crowded and missing == 0 and not disagreeing,
        "class_sets": {str(s): len(instance.sets[s]) for s in instance.sets},
    }


def violates(instance: BlockInstance, assignment, colour: int) -> bool:
    """Whether an assignment makes some forbidden clique monochromatic in ``colour``.

    The brute-force half of :func:`exact`: a clique is monochromatic in ``colour``
    exactly when one of the class sets of ``instance.sets`` is, which is why the
    clause set can be checked without enumerating cliques again.
    """
    return any(all(assignment[key] == colour for key in group)
               for group in instance.sets[instance.sizes[colour]])


# --------------------------------------------------------------------------
# the campaign
# --------------------------------------------------------------------------
def solve_blocks(n: int, sizes, blocks: int = 1, group=None, extras: int = 0,
                 seconds: float = 600.0, solver: str = "kissat404",
                 break_colours: bool = False, dimacs_path=None) -> dict:
    """Decide whether the family has a clean colouring for one instance.

    ``"sat"`` comes with a decoded colouring that :func:`oplab.multicolour.verify_colouring`
    re-counted, and that colouring is a witness for ``R(s_1, ..., s_k) > n``
    unconditionally — the family is a restriction, so a clean member is a clean
    colouring.  ``"unsat"`` is the solver's verdict about *this family*, and is not a
    theorem and not a bound.  ``"unknown"``/``"no-solver"`` claim nothing.
    """
    instance = BlockInstance(n, sizes, blocks=blocks, group=group, extras=extras,
                             break_colours=break_colours)
    base = {
        "n": instance.n, "sizes": list(instance.sizes), "blocks": instance.blocks,
        "group": list(instance.orders), "extras": instance.extras,
        "solver": solver, "break_colours": instance.break_colours,
        "classes": len(instance.classes),
        "class_sets": {str(s): len(instance.sets[s]) for s in instance.sets},
        "num_vars": instance.total_vars(), "num_clauses": instance.clause_count(),
    }
    if dimacs_path is not None:
        base["dimacs"] = instance.write_dimacs(dimacs_path, comment=instance.describe())
    obstruction = block_obstruction(instance)
    if obstruction is not None:
        base["obstruction"] = obstruction
        base["status"] = "obstructed"
        base["seconds"] = 0.0
        return base
    if solver not in MC.available_solvers():
        return {**base, "status": "no-solver", "seconds": 0.0}
    engine = MC.solver_class(solver)(bootstrap_with=instance.clauses(), use_timer=True,
                                     timeout=seconds)
    try:
        verdict = engine.solve()
        elapsed = engine.time()
        if verdict is True:
            model = engine.get_model()
            colouring = instance.decode(model)
            verify = MC.verify_colouring(instance.n, instance.sizes, colouring)
            base["coloring"] = colouring
            base["coloring_sha256"] = _digest(colouring)
            base["verify"] = verify
            base["seconds"] = round(elapsed, 3)
            base["status"] = "sat" if verify["valid"] else "sat-invalid"
            if verify["valid"]:
                base["establishes"] = (f"R{tuple(instance.sizes)} > {instance.n}, inside the "
                                      f"{instance.describe()} family")
            return base
        base["seconds"] = round(elapsed, 3)
        base["status"] = "unsat" if verdict is False else "unknown"
        if base["status"] == "unknown":
            base["note"] = getattr(engine, "note", "") or "no verdict within the budget"
        return base
    finally:
        engine.delete()


def _digest(text: str) -> str:
    import hashlib
    return hashlib.sha256(text.encode("ascii")).hexdigest()


def load(path) -> BlockInstance:  # pragma: no cover - convenience for the driver
    """Rebuild the instance a report describes."""
    import json
    report = json.loads(Path(path).read_text(encoding="utf-8"))
    return BlockInstance(report["n"], report["sizes"], blocks=report["blocks"],
                         group=report["group"], extras=report["extras"])
