import itertools
import random

import numpy as np
import pytest

from oplab import unitdist as U


def brute_force_chromatic_number(adj):
    """Straightforward backtracking reference implementation."""
    n = len(adj)
    for k in range(1, n + 1):
        colors = [-1] * n

        def rec(i):
            if i == n:
                return True
            for c in range(k):
                if all(colors[j] != c for j in range(i) if (adj[i] >> j) & 1):
                    colors[i] = c
                    if rec(i + 1):
                        return True
                    colors[i] = -1
            return False

        if rec(0):
            return k
    return n


def test_diamond():
    points = U.diamond()
    adj = U.adjacency_from_points(points)
    assert len(U.edges_of(adj)) == 5
    assert U.chromatic_number(adj) == 3
    assert U.is_unit_distance_graph(points, U.edges_of(adj))


def test_moser_spindle():
    points = U.moser_spindle()
    adj = U.adjacency_from_points(points)
    edges = U.edges_of(adj)
    assert len(points) == 7
    assert len(edges) == 11
    assert U.is_unit_distance_graph(points, edges)
    assert U.chromatic_number(adj) == 4
    # The spindle is 4-critical: dropping any edge makes it 3-colourable.
    for u, v in edges:
        reduced = list(adj)
        reduced[u] &= ~(1 << v)
        reduced[v] &= ~(1 << u)
        assert U.chromatic_number(reduced) == 3


def test_hexagon_is_two_chromatic():
    points = U.regular_polygon(6)
    adj = U.adjacency_from_points(points)
    assert len(U.edges_of(adj)) == 6
    assert U.chromatic_number(adj) == 2


@pytest.mark.parametrize("trial", range(12))
def test_chromatic_number_matches_brute_force(trial):
    rng = random.Random(trial)
    n = rng.randrange(4, 9)
    adj = [0] * n
    for u, v in itertools.combinations(range(n), 2):
        if rng.random() < 0.45:
            adj[u] |= 1 << v
            adj[v] |= 1 << u
    assert U.chromatic_number(adj) == brute_force_chromatic_number(adj)


def test_dsatur_greedy_is_an_upper_bound():
    rng = random.Random(7)
    for _ in range(10):
        n = rng.randrange(5, 14)
        adj = [0] * n
        for u, v in itertools.combinations(range(n), 2):
            if rng.random() < 0.4:
                adj[u] |= 1 << v
                adj[v] |= 1 << u
        assert U.dsatur_greedy(adj) >= U.chromatic_number(adj)
        assert U.max_clique_greedy(adj) <= U.chromatic_number(adj)


def test_ambiguous_distances_are_rejected():
    points = U.diamond().copy()
    # Push a unit edge into the grey band (tol < |d - 1| <= 50 * tol): the
    # classification of that pair would be a rounding decision, so it must raise.
    points[0] = points[0] + np.array([1e-8, 0.0])
    assert 1e-9 < abs(np.linalg.norm(points[0] - points[1]) - 1.0) <= 50 * 1e-9
    with pytest.raises(ValueError):
        U.adjacency_from_points(points)


def test_is_unit_distance_graph_rejects_wrong_edge_sets():
    points = U.moser_spindle()
    adj = U.adjacency_from_points(points)
    edges = U.edges_of(adj)
    assert U.is_unit_distance_graph(points, edges)
    # Dropping a real edge, or adding a genuine non-unit pair, must both fail.
    assert not U.is_unit_distance_graph(points, edges[:-1])
    n = len(points)
    non_edges = [(u, v) for u in range(n) for v in range(u + 1, n) if not (adj[u] >> v) & 1]
    assert non_edges, "the spindle is not complete"
    assert not U.is_unit_distance_graph(points, edges + [non_edges[0]])
    duplicated = points.copy()
    duplicated[1] = duplicated[0]
    assert not U.is_unit_distance_graph(duplicated, edges)


def test_random_growth_stays_a_unit_distance_graph():  # noqa: D103
    rng = random.Random(4)
    points = U.grow_unit_distance_graph(rng, 9)
    assert len(points) == 9
    adj = U.adjacency_from_points(points)
    assert U.is_unit_distance_graph(points, U.edges_of(adj))
    assert 1 <= U.chromatic_number(adj) <= 4
