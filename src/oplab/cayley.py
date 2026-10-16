"""Translation-invariant colourings of ``K_n`` over every group we can name.

The published multicolour lower bounds come from *constructions*, and a
translation-invariant colouring of a **non-cyclic** group is a construction the
circulant sweep cannot see.  A Cayley colouring assigns a colour to each unordered
pair of distinct elements so that ``colour(g·x, g·y) = colour(x, y)`` for every
``g``: the colour is a function of the inversion class ``{d, d⁻¹}`` of the
difference ``d = x⁻¹·y``, so one variable per (class, colour) decides the whole
family — exactly the shape of the circulant encoding in
:mod:`oplab.multicolour`, which is the special case where the group is cyclic.

Three things keep this honest:

* a model is a genuine colouring of ``K_n``, so
  :func:`oplab.multicolour.verify_colouring` re-counts every forbidden clique
  from the expanded string — the claim is never taken from this module's solver;
* the tables are built from a *description* (family and parameters), not stored,
  so the same description rebuilds the group in the verifier and in Lean;
* every generated table is checked against the group axioms by
  :func:`verify_group`, which is what makes a hand-derived multiplication rule
  (dihedral, dicyclic, semidihedral) safe to use.

``UNSAT`` here is a statement about **that group's** Cayley colourings only: for
prime ``n`` the only such group is the cyclic one, so nothing is gained, while for
``n`` with a rich group structure (``96``, ``128``) the same bound is attacked
over a whole portfolio of constructions instead of one.  Whether any of them
holds a witness is a question for the search, not for this docstring.

A verdict is not a theorem, so ``unsat`` gets the same treatment here as in
:mod:`oplab.multicolour`: :func:`cayley_solve` takes a ``proof_path`` and the
solver writes its DRAT trace there, :func:`replay_proof` re-checks that trace
against the encoding rebuilt from the group *description* (no solver involved, via
:mod:`oplab.drat`) before anything is stored, and
:func:`oplab.verify.verify_cayley_multicolour` replays it again when it reads the
certificate back — pinned by two digests, and cross-checked by the external
``drat-trim`` (:mod:`scripts.drat_trim_check`).
"""

from __future__ import annotations

import itertools
import json
import lzma
import math
import os
import time

import numpy as np

from . import multicolour as MC

__all__ = [
    "abelian_groups",
    "cayley_solve",
    "cayley_obstruction",
    "repair",
    "replay_proof",
    "solve_inline",
    "CayleyInstance",
    "clique_class_sets",
    "group_from_description",
    "groups_of_order",
    "inversion_classes",
    "load_portfolio",
    "portfolio_signature",
    "product",
    "verify_group",
]


# --------------------------------------------------------------------------
# groups, built from a description
# --------------------------------------------------------------------------
def _partitions(total: int) -> list[tuple[int, ...]]:
    """Every partition of ``total`` as a non-increasing tuple of positive parts."""
    if total == 0:
        return [()]
    out: list[tuple[int, ...]] = []

    def walk(remaining: int, cap: int, prefix: tuple[int, ...]) -> None:
        if remaining == 0:
            out.append(prefix)
            return
        for part in range(min(remaining, cap), 0, -1):
            walk(remaining - part, part, prefix + (part,))

    walk(total, total, ())
    return out


def _factorise(n: int) -> list[tuple[int, int]]:
    factors: list[tuple[int, int]] = []
    d = 2
    while d * d <= n:
        exponent = 0
        while n % d == 0:
            n //= d
            exponent += 1
        if exponent:
            factors.append((d, exponent))
        d += 1
    if n > 1:
        factors.append((n, 1))
    return factors


def abelian_groups(n: int) -> list[list[int]]:
    """Every abelian group of order ``n``, as its invariant-factor list.

    ``Z_{f_1} x ... x Z_{f_d}`` with every ``f_i >= 2`` and ``f_{i+1} | f_i``, which
    is the classification theorem: one choice of partition per prime power.
    """
    if n == 1:
        return [[1]]
    choices: list[list[list[int]]] = []
    for prime, exponent in _factorise(n):
        per_prime = []
        for partition in _partitions(exponent):
            per_prime.append([prime ** part for part in partition])
        choices.append(per_prime)
    out: list[list[int]] = []
    for combo in itertools.product(*choices):
        factors: list[int] = []
        for piece in combo:
            factors.extend(piece)
        out.append(sorted(factors, reverse=True))
    return out


def _table_from_signature(signature: list[int], binary: bool = False):
    """Multiplication and inverse tables of ``Z_{f_1} x ... x Z_{f_d}``."""
    size = 1
    for f in signature:
        size *= f

    def digits(index: int) -> list[int]:
        out = []
        for f in signature:
            out.append(index % f)
            index //= f
        return out

    def index(values) -> int:
        out, stride = 0, 1
        for value, f in zip(values, signature):
            out += (value % f) * stride
            stride *= f
        return out

    table = [[0] * size for _ in range(size)]
    inverse = [0] * size
    for a in range(size):
        da = digits(a)
        inverse[a] = index([(-x) % f for x, f in zip(da, signature)])
        for b in range(size):
            db = digits(b)
            table[a][b] = index([(x + y) for x, y in zip(da, db)])
    return table, inverse


def _dihedral(m: int):
    """``D_m`` of order ``2m``: ``r^i`` and ``s·r^i``, with ``s·r·s = r⁻¹``.

    From ``s·r^c·s = r^{-c}`` follow ``r^a·s = s·r^{-a}`` and so
    ``r^a·s·r^b = s·r^{b-a}``, ``s·r^a·r^b = s·r^{a+b}`` and
    ``s·r^a·s·r^b = r^{b-a}``; every reflection is its own inverse.
    """
    size = 2 * m
    table = [[0] * size for _ in range(size)]

    def label(rotation: int, reflection: bool) -> int:
        return m + (rotation % m) if reflection else (rotation % m)

    for a in range(m):
        for b in range(m):
            table[a][b] = label(a + b, False)
            table[a][label(b, True)] = label(b - a, True)
            table[label(a, True)][b] = label(a + b, True)
            table[label(a, True)][label(b, True)] = label(b - a, False)
    inverse = [0] * size
    for a in range(m):
        inverse[a] = label(-a, False)
        inverse[label(a, True)] = label(a, True)
    return table, inverse


def _dicyclic(m: int):
    """``Dic_m`` of order ``4m``: ``r^{2m} = 1``, ``s² = r^m``, ``s·r·s = r⁻¹``.

    Same relabelling as the dihedral family, but ``s² = r^m`` makes
    ``s·r^a·s·r^b = r^{m-a+b}`` and ``(s·r^a)^{-1} = s·r^{a+m}``; the quotient
    ``Dic_2 = Q_8`` is the smallest case where the difference matters.
    """
    order = 2 * m
    size = 2 * order
    table = [[0] * size for _ in range(size)]

    def label(rotation: int, reflection: bool) -> int:
        return order + (rotation % order) if reflection else (rotation % order)

    for a in range(order):
        for b in range(order):
            table[a][b] = label(a + b, False)
            table[a][label(b, True)] = label(b - a, True)
            table[label(a, True)][b] = label(a + b, True)
            table[label(a, True)][label(b, True)] = label(m - a + b, False)
    inverse = [0] * size
    for a in range(order):
        inverse[a] = label(-a, False)
        inverse[label(a, True)] = label(a + m, True)
    return table, inverse


def _semidihedral(m: int):
    """``SD_m`` of order ``2m``, ``m`` a power of two ``>= 8``: ``s·r·s = r^{m/2-1}``.

    With ``shift = m/2 - 1``, ``s·r^c·s = r^{shift·c}``, so ``r^a·s = s·r^{shift·a}``
    and the four products are ``r^{a+b}``, ``s·r^{shift·a + b}``, ``s·r^{a+b}`` and
    ``r^{shift·a + b}``; ``(s·r^a)^{-1} = s·r^{-shift·a}``.
    """
    if m < 8 or (m & (m - 1)) != 0:
        raise ValueError("the semidihedral family needs m = 2^k with k >= 3")
    size = 2 * m
    shift = m // 2 - 1
    table = [[0] * size for _ in range(size)]

    def label(rotation: int, reflection: bool) -> int:
        return m + (rotation % m) if reflection else (rotation % m)

    for a in range(m):
        for b in range(m):
            table[a][b] = label(a + b, False)
            table[a][label(b, True)] = label(shift * a + b, True)
            table[label(a, True)][b] = label(a + b, True)
            table[label(a, True)][label(b, True)] = label(shift * a + b, False)
    inverse = [0] * size
    for a in range(m):
        inverse[a] = label(-a, False)
        inverse[label(a, True)] = label(-shift * a, True)
    return table, inverse


def product(left: dict, right: dict):
    """The direct product of two described groups."""
    table_a, inverse_a = group_from_description(left)
    table_b, inverse_b = group_from_description(right)
    na, nb = len(table_a), len(table_b)
    size = na * nb
    table = [[0] * size for _ in range(size)]
    inverse = [0] * size
    for a in range(na):
        for b in range(nb):
            inverse[a * nb + b] = inverse_a[a] * nb + inverse_b[b]
            for c in range(na):
                for d in range(nb):
                    table[a * nb + b][c * nb + d] = table_a[a][c] * nb + table_b[b][d]
    return table, inverse


def _padded(generator) -> bytes:
    """A permutation as a 256-byte translate table, so composing two is one call.

    ``bytes.translate`` maps every byte through a 256-entry table, so two padded
    permutations compose with ``left.translate(right)`` — ``i ↦ right[left[i]]``,
    which is the product of the two as functions — with no Python-level loop.  The
    entries at or beyond the degree are the identity, which is harmless because a
    permutation's own entries are all below its degree.
    """
    degree = len(generator)
    return bytes(int(x) for x in generator) + bytes(range(degree, 256))


def _permutation_group(order: int, generators):
    """``(table, inverse)`` of the group generated by ``generators`` (image lists).

    The elements *are* permutations and the product is composition, so the result
    is a subgroup of ``S_degree`` by construction: associativity is inherited and
    the only thing that can be wrong is the size.  A faithful representation of a
    group of order ``n`` closes to exactly ``n`` elements, and anything else raises
    here rather than producing a table for a group nobody asked about.

    This is how a group exported from the SmallGroups library enters the
    repository (see :func:`load_portfolio`): the generators are data, the table is
    rebuilt from them here and again in the verifier, and no algebra system is
    needed to check a claim about the group.
    """
    degrees = {len(g) for g in generators}
    if len(degrees) != 1:
        raise ValueError("the generators act on different numbers of points")
    if not generators:
        raise ValueError("a permutation description needs at least one generator")
    degree = degrees.pop()
    for generator in generators:
        if sorted(int(x) for x in generator) != list(range(degree)):
            raise ValueError("a generator is not a permutation of 0..degree-1")
    gens = [_padded(g) for g in generators]
    identity = _padded(range(degree))
    seen = {identity: 0}
    elements = [identity]
    frontier = [identity]
    while frontier:
        nxt = []
        for element in frontier:
            for gen in gens:
                product_element = element.translate(gen)
                if product_element not in seen:
                    seen[product_element] = len(elements)
                    elements.append(product_element)
                    nxt.append(product_element)
        frontier = nxt
    if len(elements) != order:
        raise ValueError(f"the generators close to a group of order {len(elements)}, "
                         f"not {order}")
    size = len(elements)
    table = [[0] * size for _ in range(size)]
    for a, left in enumerate(elements):
        row = table[a]
        for b, right in enumerate(elements):
            row[b] = seen[left.translate(right)]
    inverse = [0] * size
    for a in range(size):
        for b in range(size):
            if table[a][b] == 0:
                inverse[a] = b
                break
    return table, inverse


def group_from_description(description: dict):
    """``(table, inverse)`` for a description such as ``{"family": "dihedral", ...}``.

    The description is the whole group: the same dict rebuilds the same table
    here, in the solver's child process, and in the verifier.  The ``permutation``
    family closes a list of generators, which is how every group of an order the
    named families do not cover travels (:func:`load_portfolio`).
    """
    family = description["family"]
    params = description.get("params", [])
    if family == "abelian":
        return _table_from_signature(list(params))
    if family == "dihedral":
        return _dihedral(int(params[0]))
    if family == "dicyclic":
        return _dicyclic(int(params[0]))
    if family == "semidihedral":
        return _semidihedral(int(params[0]))
    if family == "product":
        return product(params[0], params[1])
    if family == "permutation":
        return _permutation_group(int(params[0]), params[1])
    raise ValueError(f"unknown group family: {family!r}")


def _describe(family: str, params, name: str | None = None) -> dict:
    return {"family": family, "params": list(params),
            "name": name or f"{family}{tuple(params)}"}


def groups_of_order(n: int) -> list[dict]:
    """The group structures of order ``n`` this module can build.

    Complete for the *abelian* groups, then one entry per named non-abelian family
    (dihedral, dicyclic, semidihedral) and per direct product of one of those with
    a small abelian group.  That is a portfolio, not all groups of order ``n``:
    the point is to search constructions the circulant sweep cannot reach, and the
    docs say which families are in it.  :func:`load_portfolio` reads the *complete*
    list of one order when the SmallGroups library has been exported — the named
    families here are what remains when it has not.
    """
    out: list[dict] = []
    seen: set[str] = set()

    def add(family: str, params, name: str | None = None) -> None:
        description = _describe(family, params, name)
        key = f"{description['family']}{tuple(description['params'])}"
        if key in seen:
            return
        seen.add(key)
        out.append(description)

    for signature in abelian_groups(n):
        if len(signature) == 1:
            add("abelian", signature, "cyclic")
        else:
            add("abelian", signature, "x".join(f"Z{f}" for f in signature))
    if n % 2 == 0 and n >= 4:
        add("dihedral", [n // 2], f"D{n // 2}")
    if n % 4 == 0 and n >= 8:
        add("dicyclic", [n // 4], f"Dic{n // 4}")
    if n % 2 == 0 and (n // 2) >= 8 and ((n // 2) & (n // 2 - 1)) == 0:
        add("semidihedral", [n // 2], f"SD{n // 2}")
    # products of a non-abelian family with a small cyclic factor, which is where
    # the interesting mixed groups live
    factorisations: list[tuple[int, int]] = []
    for divisor in range(2, n):
        if n % divisor == 0:
            factorisations.append((divisor, n // divisor))
    for small, big in sorted(factorisations):
        if small > 16:
            continue
        for family in ("dihedral", "dicyclic"):
            if family == "dihedral" and big % 2 == 0 and big >= 4:
                add("product", [{"family": "abelian", "params": [small]},
                                {"family": family, "params": [big // 2]}],
                    f"Z{small}xD{big // 2}")
            if family == "dicyclic" and big % 4 == 0 and big >= 8:
                add("product", [{"family": "abelian", "params": [small]},
                                {"family": family, "params": [big // 4]}],
                    f"Z{small}xDic{big // 4}")
    return out


def verify_group(table, inverse, description: dict | None = None) -> dict:
    """Check the group axioms on a table: this is what validates the families.

    Closure is structural; the checks are identity, inverses and associativity,
    the last one over every triple (which is why it is used on the sizes this
    module builds and not on anything larger).

    A ``permutation`` description is checked *structurally* instead: its table is
    the multiplication of a closed set of permutations, so associativity is
    inherited from ``S_degree`` and the only thing that can be wrong is the order —
    which :func:`_permutation_group` refuses to build a table for.  Passing the
    description re-derives the closure and compares it with the table it was
    handed, so a caller that received a table from somewhere else cannot smuggle
    one past this check either.  It is the difference between a second on a
    portfolio of thousands and an hour: the cubic check stays for the families that
    need it.
    """
    if description is not None and description.get("family") == "permutation":
        params = description["params"]
        rebuilt, rebuilt_inverse = _permutation_group(int(params[0]), params[1])
        if [list(row) for row in rebuilt] != [list(row) for row in table]:
            return {"ok": False,
                    "reason": "the table is not the multiplication of the declared permutations"}
        if [int(x) for x in rebuilt_inverse] != [int(x) for x in inverse]:
            return {"ok": False,
                    "reason": "the inverse list is not the declared permutations'"}
        return {"ok": True, "order": len(rebuilt), "identity": 0,
                "method": "permutation closure"}
    n = len(table)
    if any(len(row) != n for row in table) or len(inverse) != n:
        return {"ok": False, "reason": "table is not square"}
    if any(not (0 <= value < n) for row in table for value in row):
        return {"ok": False, "reason": "a product left the group"}
    identity = [x for x in range(n) if all(table[x][y] == y and table[y][x] == y
                                           for y in range(n))]
    if len(identity) != 1:
        return {"ok": False, "reason": f"{len(identity)} identities, expected 1"}
    e = identity[0]
    for x in range(n):
        if table[x][inverse[x]] != e or table[inverse[x]][x] != e:
            return {"ok": False, "reason": f"bad inverse at {x}"}
    for a in range(n):
        row_a = table[a]
        for b in range(n):
            ab = row_a[b]
            for c in range(n):
                if table[ab][c] != table[a][table[b][c]]:
                    return {"ok": False, "reason": f"not associative at {(a, b, c)}"}
    return {"ok": True, "order": n, "identity": e}


# --------------------------------------------------------------------------
# a portfolio exported from the SmallGroups library
# --------------------------------------------------------------------------
def _subgroup_order(table, generators) -> int:
    """The order of the subgroup a finite table generates.

    The right closure of the set: multiplying by its elements is enough, because
    in a finite group the inverse of ``s`` is a positive power of ``s``.  Used for
    the derived subgroup, which is generated by the commutators.
    """
    n = len(table)
    identity = next(x for x in range(n) if all(table[x][y] == y for y in range(n)))
    gens = sorted(set(generators))
    seen = {identity}
    frontier = [identity]
    while frontier:
        nxt = []
        for element in frontier:
            for gen in gens:
                product_element = table[element][gen]
                if product_element not in seen:
                    seen.add(product_element)
                    nxt.append(product_element)
        frontier = nxt
    return len(seen)


def portfolio_signature(table, inverse) -> dict:
    """The invariants a table determines, recomputed from the table itself.

    Element orders, the conjugacy-class structure, the centre, the derived subgroup,
    the exponent and whether the group is abelian — all read off the multiplication,
    none of them taken on anyone's word.  ``classes`` counts conjugacy classes: the
    key is the order of the elements and the size of the class, which is
    ``n / |centralizer|``, the size being computable from the table without building
    the classes themselves.  This is what makes an exported portfolio checkable
    without the algebra system that produced it: the file says what the library
    found, this says what the table actually is, and :func:`load_portfolio` refuses
    a group when the two disagree.
    """
    n = len(table)
    identity = next(x for x in range(n) if all(table[x][y] == y for y in range(n)))
    orders: dict[int, int] = {}
    elements: dict[str, int] = {}
    center = 0
    exponent = 1
    for a in range(n):
        power, order = a, 1
        while power != identity:
            power = table[power][a]
            order += 1
        orders[order] = orders.get(order, 0) + 1
        exponent = exponent * order // math.gcd(exponent, order)
        centralizer = sum(1 for b in range(n) if table[a][b] == table[b][a])
        if centralizer == n:
            center += 1
        key = f"{order}:{n // centralizer}"
        elements[key] = elements.get(key, 0) + 1
    # every element of a class has that class's order and size, so dividing the
    # element count by the size of the class counts the classes
    classes = {key: count // int(key.split(":", 1)[1]) for key, count in elements.items()}
    commutators = [table[table[inverse[a]][inverse[b]]][table[a][b]]
                   for a in range(n) for b in range(n)]
    return {
        "orders": {str(order): orders[order] for order in sorted(orders)},
        "classes": {key: classes[key] for key in sorted(classes)},
        "center": center,
        "derived": _subgroup_order(table, commutators),
        "exponent": exponent,
        "abelian": center == n,
    }


def _read_json(path):
    """Read a JSON artifact, compressed (``.xz``) or not."""
    if str(path).endswith(".xz"):
        with lzma.open(path, "rt", encoding="utf-8") as handle:
            return json.load(handle)
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def load_portfolio(path, check: bool = True) -> list[dict]:
    """Read a ``data/smallgroups_<n>.json`` portfolio exported from the library.

    Every entry becomes the description this module already speaks — family
    ``permutation``, with the generators the file carries — so a group from the
    SmallGroups library is searched, certified and verified by exactly the code path
    the hand-derived families use, and checking a claim about it needs no GAP: the
    table is rebuilt by closing the permutations, and :func:`portfolio_signature`
    re-counts the invariants the export declares.  With ``check`` (the default) a
    disagreement is an error, so a file that was edited, truncated or exported for
    another order cannot quietly change what a sweep says it searched.
    """
    payload = _read_json(path)
    order = int(payload["order"])
    groups: list[dict] = []
    for entry in payload["groups"]:
        generators = [[int(x) for x in generator] for generator in entry["generators"]]
        description = {"family": "permutation", "params": [order, generators],
                       "name": entry["name"], "id": int(entry["id"])}
        if check:
            table, inverse = group_from_description(description)
            found = portfolio_signature(table, inverse)
            declared = {key: entry[key] for key in ("orders", "classes", "center",
                                                    "derived", "exponent", "abelian")}
            for key in ("orders", "classes"):
                declared[key] = {str(k): int(v) for k, v in declared[key].items()}
            if found != declared:
                raise ValueError(f"{description['name']}: the export declares {declared}, "
                                 f"the table has {found}")
        groups.append(description)
    return groups


# --------------------------------------------------------------------------
# the class structure, and the CNF over it
# --------------------------------------------------------------------------
def cayley_obstruction(description: dict, sizes) -> dict | None:
    """The ``3 | n`` obstruction, now for **every** group — not just the cyclic one.

    If ``3 | n`` and every colour forbids a triangle, then group theory alone
    produces a monochromatic triangle: Cauchy's theorem gives an element ``g`` of
    order 3, so ``{e, g, g²}`` is a triangle all of whose differences lie in the
    single class ``{g, g⁻¹} = {g, g²}``.  Whichever colour that class carries, the
    ``n/3`` translates ``{x, xg, xg²}`` are monochromatic in it, and no
    translation-invariant colouring of any group of order ``n`` is clean.  The
    cyclic case of :func:`oplab.multicolour.circulant_obstruction` is the special
    case, and this one is decided by arithmetic before any solver runs.

    The triangle is *found in the table*, not assumed to sit at the first three
    indices: which element has order 3 is a fact about the group, and in ``Z_96`` — or
    in any group imported from the library, where the numbering is the closure's — it
    is not the element written ``1``.  Declaring ``(0, 1, 2)`` there would name a
    triple that is not monochromatic, and the verifier refuses exactly that; this is
    the fix for a refusal it produced.
    """
    sizes = tuple(int(s) for s in sizes)
    table, _ = group_from_description(description)
    n = len(table)
    if not (all(s == 3 for s in sizes) and n % 3 == 0):
        return None
    identity = next(x for x in range(n) if all(table[x][y] == y for y in range(n)))
    for element in range(n):
        if element == identity:
            continue
        square = table[element][element]
        if table[square][element] == identity:
            return {"class_order": 3, "element": element,
                    "triangle": (identity, element, square), "triangles": n // 3}
    # 3 | n with no element of order 3 would contradict Cauchy's theorem
    return None


def inversion_classes(table, inverse):
    """The classes ``{d, d⁻¹}`` of the non-identity elements, and the class map.

    A translation-invariant colouring of the complete graph is a function of such
    a class: ``colour(x, y)`` and ``colour(y, x)`` are the same edge, and the
    difference ``x⁻¹y`` and its inverse ``y⁻¹x`` describe that same edge from the
    two ends.  Self-inverse elements are singleton classes.
    """
    n = len(table)
    class_of: dict[int, int] = {}
    for d in range(1, n):
        class_of[d] = min(d, inverse[d])
    classes = sorted(set(class_of.values()))
    return classes, class_of


def clique_class_sets(table, inverse, class_of, s: int) -> list[tuple[int, ...]]:
    """Every distinct set of classes an ``s``-clique can use.

    Translating a clique so that it contains the identity loses nothing (the
    colouring is translation invariant, and differences do not change), so
    enumerating the other ``s - 1`` vertices is complete.  Two cliques with the
    same class set give the same constraint — "these classes are not all one
    colour" — and dropping duplicates keeps the CNF small.
    """
    n = len(table)
    if s < 2 or s > n:
        raise ValueError(f"no {s}-cliques in K{n}")
    groups: dict[tuple[int, ...], None] = {}
    for rest in itertools.combinations(range(1, n), s - 1):
        vertices = (0,) + rest
        classes = set()
        for i, u in enumerate(vertices):
            row = table[inverse[u]]
            for v in vertices[i + 1:]:
                classes.add(class_of[row[v]])
        groups.setdefault(tuple(sorted(classes)), None)
    return sorted(groups, key=lambda g: (len(g), g))


class CayleyInstance:
    """CNF whose models are exactly the clean translation-invariant colourings.

    One variable per (class, colour), one-hot per class, one clause per
    (colour, clique class set): the classes of that clique may not all carry the
    forbidden colour.  Every model expands to a colouring of all ``C(n, 2)``
    edges, which is the string the ordinary verifier re-counts.
    """

    def __init__(self, description: dict, sizes):
        sizes = tuple(int(s) for s in sizes)
        if any(s < 3 or s > len(group_from_description(description)[0]) for s in sizes):
            raise ValueError("need 3 <= s_c <= n for every colour")
        self.description = description
        self.table, self.inverse = group_from_description(description)
        self.n = len(self.table)
        self.sizes = sizes
        self.k = len(sizes)
        self.classes, self.class_of = inversion_classes(self.table, self.inverse)
        self._index = {d: i for i, d in enumerate(self.classes)}
        self.groups = {s: clique_class_sets(self.table, self.inverse, self.class_of, s)
                       for s in sorted(set(sizes))}

    def var(self, d: int, colour: int) -> int:
        return self._index[d] * self.k + colour + 1

    def total_vars(self) -> int:
        return len(self.classes) * self.k

    def clause_count(self) -> int:
        one_hot = len(self.classes) * (1 + self.k * (self.k - 1) // 2)
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
            handle.write(f"c {comment or self.label()}\n")
            handle.write(f"p cnf {self.total_vars()} {self.clause_count()}\n")
            for clause in self.clauses():
                handle.write(" ".join(map(str, clause)) + " 0\n")
                written += 1
        return {"path": str(path), "clauses_written": written, "num_vars": self.total_vars()}

    # -- reading a model back ----------------------------------------------
    def class_colours_from_model(self, model) -> dict[int, int]:
        truth = {lit for lit in model if lit > 0}
        assignment = {}
        for d in self.classes:
            found = [c for c in range(self.k) if self.var(d, c) in truth]
            if len(found) != 1:
                raise ValueError(f"class {d} is not assigned exactly one colour")
            assignment[d] = found[0]
        return assignment

    def expand(self, colours: dict[int, int]) -> np.ndarray:
        """The ``(n, n)`` colouring matrix of a per-class assignment."""
        colouring = np.zeros((self.n, self.n), dtype=np.int8)
        for x in range(self.n):
            row = self.table[self.inverse[x]]
            for y in range(x + 1, self.n):
                colouring[x, y] = colours[self.class_of[row[y]]]
        return colouring + colouring.T

    def label(self) -> str:
        name = self.description.get("name") or self.description["family"]
        return f"cayley multicolour Ramsey K_{self.n} {self.sizes} over {name}"

    def certificate_payload(self) -> dict:
        """The group as *data*: its table, its inverse list, and the clique groups.

        A `cayley_multicolour` certificate carries the group explicitly rather than
        only its description, because the Lean layer has to recompute the same
        numbers from the same object and the Lean generator deliberately does not
        run this module (it is dependency-free, so it cannot import numpy).  The two
        copies cannot drift: :func:`oplab.verify.verify_cayley_multicolour` rebuilds
        the table from the description and checks the stored one against it, and the
        group axioms are checked on the rebuilt table, so a certificate is only ever
        judged on a table that really is the group its description names.
        """
        return {
            "table": [list(row) for row in self.table],
            "inverse": list(self.inverse),
            "clique_groups": {str(s): len(g) for s, g in self.groups.items()},
        }

    def summary(self) -> dict:
        """The identity of the instance, for a row or a certificate."""
        return {
            "n": self.n,
            "sizes": list(self.sizes),
            "group": self.description,
            "classes": len(self.classes),
            "self_inverse_classes": sum(1 for d in self.classes if self.inverse[d] == d),
            "num_vars": self.total_vars(),
            "num_clauses": self.clause_count(),
        }


def _expand_clean(instance: CayleyInstance, colours: dict[int, int]) -> str:
    """Expand a per-class assignment into the ``C(n, 2)`` colouring string.

    ``d = x⁻¹·y`` is the difference of the pair ``(x, y)``, and its class decides
    the colour; the inverse is read off the group table rather than assumed to be
    ``-d``, which is what lets a non-abelian group be coloured this way at all.
    """
    n = instance.n
    colouring = np.zeros((n, n), dtype=np.int8)
    for x in range(n):
        row = instance.table[instance.inverse[x]]
        for y in range(x + 1, n):
            colouring[x, y] = colours[instance.class_of[row[y]]]
    colouring = colouring + colouring.T
    return MC.serialize_colouring(colouring, n)


def solve_inline(description: dict, sizes, solver: str = "cadical195",
                 proof_path=None) -> dict:
    """Solve in the *current* process, with no budget of its own.

    Split out of the worker so a caller that already runs one process per group can
    call it directly: a pooled worker is daemonic, and a daemonic process is not
    allowed to spawn the child that enforces a time budget, so the two layers
    cannot be nested.  Whoever calls this is responsible for the budget.
    """
    sizes = tuple(int(s) for s in sizes)
    instance = CayleyInstance(description, sizes)
    solver_class = MC._solver_class(solver)
    with solver_class(bootstrap_with=list(instance.clauses()), use_timer=True,
                      with_proof=bool(proof_path)) as engine:
        verdict = engine.solve()
        out: dict = {**instance.summary(), "solver_time": engine.time()}
        if verdict is True:
            colours = instance.class_colours_from_model(engine.get_model())
            text = _expand_clean(instance, colours)
            out.update(status="sat", coloring=text,
                       class_colors={int(k): int(v) for k, v in colours.items()},
                       verified=MC.verify_colouring(instance.n, sizes, text))
        elif verdict is False:
            out["status"] = "unsat"
            if proof_path:
                out["proof"] = MC.DRAT.write_proof(proof_path, engine.get_proof() or [])
        else:
            out["status"] = "unknown"
    return out


def replay_proof(description: dict, sizes, proof_path, base_dir=None) -> dict:
    """Check a stored trace against one group's encoding, with no solver in the loop.

    The same check :func:`oplab.verify.verify_cayley_multicolour` makes when it reads
a certificate back, run *before* anything is stored: a trace a killed solver left
half-written, or one produced against a different group's encoding (the clauses
depend on the group, so a cyclic trace does not even have the right variables),
is refused here instead of being recorded as a theorem.

    Returns the metadata a certificate records — the canonical text digest, the
    digest of the stored bytes, the step counts, the stored size, and how long the
    replay took (which is what lets ``verify`` decide whether to replay it again by
    default) — plus ``ok``.  ``base_dir`` makes the recorded ``file`` relative to
    the certificate directory, so the pair moves together.  The trace is written
    once more, byte for byte identically, only to reuse
    :func:`oplab.drat.write_proof`'s measurement of what is on disk.
    """
    instance = CayleyInstance(description, sizes)
    lines = MC.DRAT.read_proof(proof_path)
    checked = MC.DRAT.check_proof(instance.total_vars(), list(instance.clauses()), lines)
    if not checked["ok"]:
        return {"ok": False, "replayed": True, "steps": len(lines),
                "reason": checked.get("reason", "the trace does not check"),
                "replay_seconds": round(float(checked.get("seconds", 0.0)), 2)}
    recorded = MC.DRAT.write_proof(proof_path, lines)
    recorded["replay_seconds"] = round(float(checked["seconds"]), 2)
    recorded["replayed"] = True
    if base_dir is not None:
        recorded["file"] = os.path.relpath(proof_path, base_dir).replace(os.sep, "/")
    return {"ok": True, **recorded}


def _solve_worker(conn, payload: dict) -> None:  # pragma: no cover - child process
    """Build the instance in a child, solve it, and send back the colouring."""
    try:
        out = solve_inline(payload["description"], tuple(payload["sizes"]),
                           payload["solver"], payload.get("proof_path"))
    except Exception as exc:  # pragma: no cover - diagnostic path
        out = {"status": "error", "reason": f"{exc.__class__.__name__}: {exc}"}
    try:
        conn.send(out)
    finally:
        conn.close()


def _clause_masks(instance: CayleyInstance):
    """The CNF as ``(colour, bitmask of the classes in the clause)``.

    A clause is violated exactly when its mask is contained in the mask of the
    classes carrying that colour, which is one big-int AND — cheap enough that a
    whole instance can be re-checked and, more usefully, that a single class moved
    by a local search only touches its own clauses.
    """
    index = {d: i for i, d in enumerate(instance.classes)}
    masks = []
    for colour, s in enumerate(instance.sizes):
        for group in instance.groups[s]:
            mask = 0
            for d in group:
                mask |= 1 << index[d]
            masks.append((colour, mask))
    return masks, index


def repair(description: dict, sizes, seconds: float = 60.0, seed: int = 0) -> dict:
    """Min-conflicts repair over the class assignment, with exact delta counts.

    CDCL is the right tool for a *proof* and a poor one for *finding* a witness in a
    structured instance: this walks the same family with one colour per class, keeps
    the set of violated clauses up to date, and only re-evaluates the clauses that
    contain the class it just recoloured.  A run that ends with violations left is
    reported as ``unknown`` with the best count it reached — a near miss is not a
    witness, and this module never pretends otherwise.  Whatever it does find goes
    through :func:`oplab.multicolour.verify_colouring` before it is called `sat`.
    """
    import random

    instance = CayleyInstance(description, sizes)
    masks, index = _clause_masks(instance)
    n_classes, k = len(instance.classes), instance.k
    rng = random.Random(seed)
    started = time.time()

    # per-class index of the clauses that contain it, so a move is local
    owners: list[list[int]] = [[] for _ in range(n_classes)]
    for cid, (_, mask) in enumerate(masks):
        bits = mask
        while bits:
            low = bits & -bits
            owners[low.bit_length() - 1].append(cid)
            bits ^= low

    best = None
    best_violations = None
    moves = 0
    while time.time() - started < seconds:
        assignment = [rng.randrange(k) for _ in range(n_classes)]
        colour_mask = [0] * k
        for i, c in enumerate(assignment):
            colour_mask[c] |= 1 << i
        violated = {cid for cid, (c, mask) in enumerate(masks) if (mask & colour_mask[c]) == mask}
        if not violated:
            best, best_violations = list(assignment), 0
            break
        stall = 0
        while violated and stall < 4000 and time.time() - started < seconds:
            cid = rng.choice(tuple(violated))
            colour, mask = masks[cid]
            bits = mask
            members = []
            while bits:
                low = bits & -bits
                members.append(low.bit_length() - 1)
                bits ^= low
            chosen, chosen_delta = None, None
            member = rng.choice(members)
            if rng.random() < 0.3:
                # a random kick out of the local minimum: pure min-conflicts walks
                # into the same plateau on these structured instances
                other = [c for c in range(k) if c != assignment[member]]
                chosen, chosen_delta = (member, rng.choice(other)), 0
            for i in ([member] if chosen is None else []):
                old = assignment[i]
                for c_next in range(k):
                    if c_next == old:
                        continue
                    delta = 0
                    for other in owners[i]:
                        oc, om = masks[other]
                        before = (om & colour_mask[oc]) == om
                        # the same clause after the move: bit i leaves `old`,
                        # enters `c_next`, and nothing else changes
                        after_mask = colour_mask[oc]
                        if oc == old:
                            after_mask &= ~(1 << i)
                        if oc == c_next:
                            after_mask |= 1 << i
                        delta += (1 if (om & after_mask) == om else 0) - (1 if before else 0)
                    if chosen_delta is None or delta < chosen_delta:
                        chosen, chosen_delta = (i, c_next), delta
            if chosen is None:
                break
            i, c_next = chosen
            colour_mask[assignment[i]] &= ~(1 << i)
            assignment[i] = c_next
            colour_mask[c_next] |= 1 << i
            for other in owners[i]:
                oc, om = masks[other]
                if (om & colour_mask[oc]) == om:
                    violated.add(other)
                else:
                    violated.discard(other)
            moves += 1
            stall += 1
        if best_violations is None or len(violated) < best_violations:
            best, best_violations = list(assignment), len(violated)
        if not violated:
            break

    base = instance.summary()
    base["seconds"] = round(time.time() - started, 3)
    base["moves"] = moves
    if best is not None and best_violations == 0:
        colours = {d: best[index[d]] for d in instance.classes}
        text = _expand_clean(instance, colours)
        return {**base, "status": "sat", "coloring": text, "class_colors": colours,
                "repair_moves": moves, "verified": MC.verify_colouring(instance.n, sizes, text)}
    return {**base, "status": "unknown", "best_violations": best_violations,
            "repair_moves": moves, "note": "a near miss is not a witness"}


def cayley_solve(description: dict, sizes, seconds: float = 60.0, solver: str = "cadical195",
                 proof_path=None, dimacs_path=None) -> dict:
    """Decide the translation-invariant colourings of one group.

    ``"sat"`` carries a colouring already re-counted by
    :func:`oplab.multicolour.verify_colouring`; ``"unsat"`` is the solver's verdict
    about *this group* and becomes a theorem only with ``proof_path``, whose trace
    :func:`replay_proof` then checks against this group's encoding (and which
    ``verify`` re-checks, and ``drat-trim`` cross-checks, when it is stored).
    """
    import multiprocessing as mp

    sizes = tuple(int(s) for s in sizes)
    instance = CayleyInstance(description, sizes)
    base = instance.summary()
    base["solver"] = solver
    if dimacs_path is not None:
        base["dimacs"] = instance.write_dimacs(dimacs_path)
    obstruction = cayley_obstruction(description, sizes)
    if obstruction is not None:
        return {**base, "status": "obstructed", "obstruction": obstruction, "seconds": 0.0}
    if solver not in MC.available_solvers():
        return {**base, "status": "no-solver", "seconds": 0.0}

    ctx = mp.get_context("spawn")
    parent, child = ctx.Pipe(duplex=False)
    proc = ctx.Process(target=_solve_worker,
                       args=(child, {"description": description, "sizes": list(sizes),
                                     "solver": solver,
                                     "proof_path": str(proof_path) if proof_path else None}),
                       daemon=True)
    started = time.time()
    proc.start()
    proc.join(max(0.0, float(seconds)))
    if proc.is_alive():
        proc.terminate()
        proc.join(10)
        if proc.is_alive() and hasattr(proc, "kill"):  # pragma: no cover - defensive
            proc.kill()
        parent.close()
        return {**base, "status": "unknown", "budget_expired": True,
                "seconds": round(time.time() - started, 3)}
    if parent.poll(10):
        out = parent.recv()
        parent.close()
        out["seconds"] = round(time.time() - started, 3)
        if out.get("class_colors") is not None:
            # keys are ints in the child and strings after pickling the dict of an
            # array-backed structure: normalise so a certificate can carry them
            out["class_colors"] = {int(k): int(v) for k, v in out["class_colors"].items()}
        return {**base, **out}
    parent.close()
    return {**base, "status": "no_verdict", "exit_code": proc.exitcode,
            "seconds": round(time.time() - started, 3)}
