"""Unit-distance graphs and the Hadwiger-Nelson problem.

The chromatic number of the plane is known only to satisfy ``5 <= chi <= 7``.
Lower bounds come from finite unit-distance graphs: the Moser spindle (7
vertices, 4-chromatic, proved minimal) gives ``chi >= 4``, and the smallest
known 5-chromatic unit-distance graph has 509 vertices (Jaan Parts).  No
6-chromatic unit-distance graph is known at all, and finding one would push the
plane's chromatic number to 6.

Everything in this module is exact where the input is exact: a graph is
"unit distance" only if every edge has length 1 and every non-edge does not,
within a tolerance, and :func:`chromatic_number` is an exact branch-and-bound
DSATUR computation, not a heuristic.
"""

from __future__ import annotations

import random
import time

import numpy as np

__all__ = [
    "moser_spindle",
    "diamond",
    "regular_polygon",
    "adjacency_from_points",
    "is_unit_distance_graph",
    "chromatic_number",
    "dsatur_greedy",
    "max_clique_greedy",
    "bits",
    "grow_unit_distance_graph",
    "search_unit_distance",
]


# --------------------------------------------------------------------------
# classical configurations
# --------------------------------------------------------------------------
def diamond() -> np.ndarray:
    """The 4-vertex 3-chromatic unit distance graph ``K4 minus an edge``.

    Two equilateral triangles sharing an edge: the shared edge and all four
    remaining edges have length 1, and the two "tips" are at distance ``sqrt(3)``.
    """
    return np.array(
        [
            [0.0, 0.0],
            [1.0, 0.0],
            [0.5, np.sqrt(3.0) / 2.0],
            [0.5, -np.sqrt(3.0) / 2.0],
        ]
    )


def moser_spindle() -> np.ndarray:
    """The 7-vertex, 11-edge Moser spindle (the minimal 4-chromatic unit distance graph).

    Two 60/120-degree rhombi share one acute vertex ``O``; their other acute
    vertices ``P1`` and ``P2`` are one unit apart.  In any 3-colouring of a
    rhombus the two acute vertices have the same colour, so ``P1`` and ``P2``
    would share a colour, contradicting the unit edge between them: four colours
    are necessary.  Coordinates are analytic, so the configuration is exact
    up to floating point.
    """
    root3 = np.sqrt(3.0)
    O = np.array([0.0, 0.0])
    P1 = np.array([root3, 0.0])
    Vp = np.array([root3 / 2.0, 0.5])
    Vm = np.array([root3 / 2.0, -0.5])
    cos_t = 5.0 / 6.0  # |P1 - P2| = 1 with |OP2| = sqrt(3)
    sin_t = np.sqrt(11.0) / 6.0
    P2 = root3 * np.array([cos_t, sin_t])
    offset = np.array([-np.sqrt(11.0) / 6.0, 5.0 / 6.0]) / 2.0
    Wp = P2 / 2.0 + offset
    Wm = P2 / 2.0 - offset
    return np.array([O, P1, P2, Vp, Vm, Wp, Wm])


def regular_polygon(n: int) -> np.ndarray:
    """Vertices of a regular ``n``-gon (a unit-distance cycle)."""
    angles = 2.0 * np.pi * np.arange(n) / n
    return np.stack([np.cos(angles), np.sin(angles)], axis=1)


# --------------------------------------------------------------------------
# geometry -> graphs
# --------------------------------------------------------------------------
def bits(mask: int):
    """Iterate over the set bit indices of ``mask``."""
    while mask:
        v = (mask & -mask).bit_length() - 1
        mask &= mask - 1
        yield v


def adjacency_from_points(points: np.ndarray, tol: float = 1e-9) -> list[int]:
    """Bitmask adjacency of the unit-distance graph on ``points``.

    Every pair is classified by ``abs(dist - 1) <= tol``; distances in the
    ambiguous band ``|dist - 1| <= 50 * tol`` raise since a certificate must not
    depend on that choice.
    """
    points = np.asarray(points, dtype=float)
    n = len(points)
    adj = [0] * n
    for u in range(n):
        for v in range(u + 1, n):
            d = float(np.linalg.norm(points[u] - points[v]))
            if abs(d - 1.0) <= tol:
                adj[u] |= 1 << v
                adj[v] |= 1 << u
            elif abs(d - 1.0) <= 50.0 * tol:
                raise ValueError(
                    f"distance between points {u} and {v} is {d!r}, too close to 1 to classify"
                )
    return adj


def is_unit_distance_graph(points: np.ndarray, edges, tol: float = 1e-9) -> bool:
    """True iff the given edges are exactly the unit-distance pairs of ``points``."""
    points = np.asarray(points, dtype=float)
    n = len(points)
    if len({tuple(np.round(p, 12)) for p in points}) != n:
        return False
    wanted = {(min(u, v), max(u, v)) for u, v in edges}
    actual = {(u, v) for u in range(n) for v in range(u + 1, n)
              if abs(float(np.linalg.norm(points[u] - points[v])) - 1.0) <= tol}
    return wanted == actual


# --------------------------------------------------------------------------
# exact colouring
# --------------------------------------------------------------------------
def edges_of(adj: list[int]) -> list[tuple[int, int]]:
    return [(u, v) for u in range(len(adj)) for v in range(u + 1, len(adj)) if (adj[u] >> v) & 1]


def dsatur_greedy(adj: list[int]) -> int:
    """Upper bound on the chromatic number via greedy DSATUR."""
    n = len(adj)
    colors = [-1] * n
    neighbour_colors = [0] * n
    degrees = [adj[v].bit_count() for v in range(n)]
    for _ in range(n):
        v = max(
            (u for u in range(n) if colors[u] < 0),
            key=lambda u: (neighbour_colors[u].bit_count(), degrees[u]),
        )
        c = 0
        while (neighbour_colors[v] >> c) & 1:
            c += 1
        colors[v] = c
        for u in bits(adj[v]):
            if colors[u] < 0:
                neighbour_colors[u] |= 1 << c
    return max(colors) + 1


def max_clique_greedy(adj: list[int]) -> int:
    """Greedy (lower bound) clique number, used to prune the colouring search."""
    order = sorted(range(len(adj)), key=lambda v: -adj[v].bit_count())
    best = 1
    for v in order:
        clique = 1
        cand = adj[v]
        while cand:
            u = (cand & -cand).bit_length() - 1
            clique += 1
            cand &= adj[u]
        best = max(best, clique)
    return best


def chromatic_number(adj: list[int], upper_bound: int | None = None) -> int:
    """Exact chromatic number by branch and bound (DSATUR ordering)."""
    n = len(adj)
    if n == 0:
        return 0
    best = dsatur_greedy(adj)
    if upper_bound is not None:
        best = min(best, upper_bound)
    lower = max_clique_greedy(adj)
    if lower >= best:
        return best
    colors = [-1] * n
    neighbour_colors = [0] * n

    def recurse(colored: int, used: int) -> None:
        nonlocal best
        if colored == n:
            best = used
            return
        # Pruning: a partial colouring using ``used`` colours can only help if
        # ``used < best``; once ``used`` reaches ``best`` nothing better is left.
        # (Pruning at ``best - 1`` would discard exactly the improving colourings.)
        if used >= best:
            return
        v = -1
        key = None
        for u in range(n):
            if colors[u] < 0:
                candidate = (neighbour_colors[u].bit_count(), adj[u].bit_count())
                if key is None or candidate > key:
                    key, v = candidate, u
        for c in range(used):
            if (neighbour_colors[v] >> c) & 1:
                continue
            changed = []
            for u in bits(adj[v]):
                if colors[u] < 0 and not (neighbour_colors[u] >> c) & 1:
                    neighbour_colors[u] |= 1 << c
                    changed.append(u)
            colors[v] = c
            recurse(colored + 1, used)
            colors[v] = -1
            for u in changed:
                neighbour_colors[u] &= ~(1 << c)
        if used + 1 < best:
            # A fresh colour must be recorded in the neighbours' saturation sets
            # too, otherwise a later vertex could reuse it on an edge to ``v``.
            changed = []
            for u in bits(adj[v]):
                if colors[u] < 0 and not (neighbour_colors[u] >> used) & 1:
                    neighbour_colors[u] |= 1 << used
                    changed.append(u)
            colors[v] = used
            recurse(colored + 1, used + 1)
            colors[v] = -1
            for u in changed:
                neighbour_colors[u] &= ~(1 << used)

    recurse(0, 0)
    return best


def colouring(adj: list[int]) -> list[int]:
    """A concrete proper colouring (greedy DSATUR), for certificate payloads."""
    n = len(adj)
    colors = [-1] * n
    neighbour_colors = [0] * n
    degrees = [adj[v].bit_count() for v in range(n)]
    for _ in range(n):
        v = max(
            (u for u in range(n) if colors[u] < 0),
            key=lambda u: (neighbour_colors[u].bit_count(), degrees[u]),
        )
        c = 0
        while (neighbour_colors[v] >> c) & 1:
            c += 1
        colors[v] = c
        for u in bits(adj[v]):
            if colors[u] < 0:
                neighbour_colors[u] |= 1 << c
    return colors


# --------------------------------------------------------------------------
# generator / search harness
# --------------------------------------------------------------------------
def grow_unit_distance_graph(
    rng: random.Random,
    max_vertices: int,
    tol: float = 1e-9,
    start: np.ndarray | None = None,
) -> np.ndarray:
    """Grow a unit-distance graph point by point.

    A new point is placed at an intersection of the unit circles around two
    existing points (the generic way unit-distance graphs grow), or at a random
    unit displacement of an existing point.  Returns the point set; the caller
    checks whether it is non-degenerate with :func:`adjacency_from_points`.
    """
    points = list(start) if start is not None else [np.array([0.0, 0.0]), np.array([1.0, 0.0])]
    while len(points) < max_vertices:
        mode = rng.random()
        if mode < 0.7 and len(points) >= 2:
            i, j = rng.sample(range(len(points)), 2)
            a, b = points[i], points[j]
            d = np.linalg.norm(b - a)
            if d <= tol or d > 2.0:
                continue
            mid = (a + b) / 2.0
            h = np.sqrt(max(0.0, 1.0 - (d / 2.0) ** 2))
            perp = np.array([-(b - a)[1], (b - a)[0]]) / d
            for sign in (1.0, -1.0):
                candidate = mid + sign * h * perp
                if all(np.linalg.norm(candidate - p) > tol for p in points):
                    points.append(candidate)
                    break
        else:
            i = rng.randrange(len(points))
            angle = rng.uniform(0.0, 2.0 * np.pi)
            candidate = points[i] + np.array([np.cos(angle), np.sin(angle)])
            if all(np.linalg.norm(candidate - p) > tol for p in points):
                points.append(candidate)
    return np.array(points)


def search_unit_distance(
    seconds: float,
    max_vertices: int = 12,
    seed: int = 0,
    tolerance: float = 1e-9,
    start: np.ndarray | None = None,
    on_result=None,
) -> dict:
    """Random search for high-chromatic unit-distance graphs.

    For every vertex count ``n`` up to ``max_vertices`` we sample random
    unit-distance graphs, compute the exact chromatic number and keep the best
    (and the corresponding graph).  The honest expected outcome is 4: the
    smallest known 5-chromatic unit-distance graph has 509 vertices, so nothing
    this search can generate reaches 5.
    """
    rng = random.Random(seed)
    deadline = time.time() + seconds
    if start is None:
        start = np.array([[0.0, 0.0], [1.0, 0.0]])
    else:
        start = np.asarray(start, dtype=float)
        if len(start) > max_vertices:
            raise ValueError("the seed graph already has more vertices than max_vertices")
    best_adj: list[int] = []
    best_points: np.ndarray | None = None
    best_chi = 0
    per_n: dict[int, int] = {}
    samples = 0
    while time.time() < deadline:
        points = grow_unit_distance_graph(rng, max_vertices, start=start)
        try:
            adj = adjacency_from_points(points, tol=tolerance)
        except ValueError:
            continue
        if any(adj[v].bit_count() == 0 for v in range(len(points))):
            continue  # isolated vertex: harmless but uninformative
        if not is_unit_distance_graph(points, edges_of(adj), tol=tolerance):
            continue  # keep only graphs a verifier will agree with
        samples += 1
        if samples % 8 == 0:  # exact colouring is the expensive part
            chi = chromatic_number(adj)
            n = len(points)
            per_n[n] = max(per_n.get(n, 0), chi)
            if chi > best_chi:
                best_chi, best_adj, best_points = chi, adj, points
                if on_result is not None:
                    on_result(chi, n)
    return {
        "best_chromatic_number": best_chi,
        "best_points": best_points.tolist() if best_points is not None else None,
        "best_edges": edges_of(best_adj) if best_adj else [],
        "samples": samples,
        "seconds": seconds,
        "max_vertices": max_vertices,
        "seed": seed,
        "start_vertices": len(start),
        "best_per_vertex_count": {str(k): v for k, v in sorted(per_n.items())},
    }
