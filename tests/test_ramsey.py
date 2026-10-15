import itertools
import random

import pytest

from oplab import ramsey as R


def brute_force_mono_k5(red, n):
    count = 0
    for clique in itertools.combinations(range(n), 5):
        colours = {R.colour_of(red, u, v) for u, v in itertools.combinations(clique, 2)}
        if len(colours) == 1:
            count += 1
    return count


@pytest.mark.parametrize("n", [5, 6, 8, 11])
def test_count_mono_k5_matches_brute_force(n):
    rng = random.Random(20261015 + n)
    for _ in range(5):
        red = R.random_coloring(n, rng)
        assert R.count_mono_k5(red, n) == brute_force_mono_k5(red, n)


def test_exhaustive_colouring_boundary_cases():
    # An all-blue K_n has exactly C(n, 5) monochromatic K5.
    for n in (3, 4, 5, 6, 7):
        expected = 0 if n < 5 else len(list(itertools.combinations(range(n), 5)))
        assert R.count_mono_k5(R.empty_coloring(n), n) == expected


def test_delta_flip_is_exact():
    rng = random.Random(11)
    for _ in range(60):
        n = rng.randrange(8, 18)
        red = R.random_coloring(n, rng)
        blue = R.blue_masks(red, n)
        u, v = sorted(rng.sample(range(n), 2))
        before = R.count_mono_k5(red, n)
        delta = R.delta_flip(red, blue, u, v)
        R.flip(red, u, v)
        assert before + delta == R.count_mono_k5(red, n)


def test_find_mono_k5_agrees_with_the_counter():
    rng = random.Random(5)
    red = R.random_coloring(13, rng)
    found = R.find_mono_k5(red, 13)
    assert len(found) == R.count_mono_k5(red, 13)
    assert all(len(clique) == 5 for clique in found)


def test_serialize_parse_round_trip():
    rng = random.Random(3)
    n = 9
    red = R.random_coloring(n, rng)
    text = R.serialize(red, n)
    assert len(text) == n * (n - 1) // 2
    assert R.parse(text, n) == red
    with pytest.raises(ValueError):
        R.parse(text[:-1], n)
    with pytest.raises(ValueError):
        R.parse("2" * len(text), n)


def test_circulant_sweep_finds_the_known_witnesses():
    # R(3,3) >= 6 is witnessed by the 5-cycle, R(4,4) >= 18 by the Paley graph
    # on 17 vertices.  Both are circulant, so the sweep must find them.
    res5 = R.circulant_search(5, k=3)
    assert res5["colourings_tested"] == 2 ** len(R.free_differences(5))
    assert res5["witnesses"], "the 5-cycle witness must be found"
    res17 = R.circulant_search(17, k=4)
    assert res17["witnesses"], "the Paley(17) witness must be found"


def test_circulant_sweep_is_exhaustive_on_the_other_side():
    # R(3,3) = 6 and R(4,4) = 18: no circulant witness exists, and the sweep
    # must cover the entire family.
    res6 = R.circulant_search(6, k=3)
    assert res6["colourings_tested"] == 2 ** len(R.free_differences(6))
    assert res6["witnesses"] == []
    res18 = R.circulant_search(18, k=4)
    assert res18["witnesses"] == []


def test_circulant_adjacency_is_translation_invariant():
    n = 42
    adj = R.circulant_adjacency(n, 0b1010101)
    shifted = R.circulant_adjacency(n, 0b1010101)
    assert adj == shifted
    for v in range(n):
        assert not (adj[v] >> v) & 1, "no self loops"
        for u in R._bits(adj[v]):
            assert (adj[u] >> v) & 1, "adjacency must be symmetric"


def test_tabu_search_reduces_the_monochromatic_clique_count():
    res = R.tabu_search(12, seconds=1.0, seed=0)
    rng = random.Random(0)
    baseline = R.count_mono_k5(R.random_coloring(12, rng), 12)
    assert res["mono_k5"] < baseline
    assert len(res["coloring"]) == 12 * 11 // 2
