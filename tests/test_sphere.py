import numpy as np
import pytest

from oplab import sphere as S

EXPECTED_SIZES = {
    "a2": 6,
    "icosahedron": 12,
    "d4": 24,
    "d5": 40,
    "e6": 72,
    "e7": 126,
    "e8": 240,
}


@pytest.mark.parametrize("name,size", sorted(EXPECTED_SIZES.items()))
def test_classical_constructions(name, size):
    P = S.root_system(name)
    assert len(P) == size
    assert P.shape[1] == {"a2": 2, "icosahedron": 3, "d4": 4, "d5": 5, "e6": 6, "e7": 7, "e8": 8}[name]
    assert np.allclose(np.linalg.norm(P, axis=1), 1.0, atol=1e-12)
    assert S.max_dot(P) <= S.KISSING_THRESHOLD + 1e-12
    assert S.is_kissing_configuration(P)


def test_root_counts_match_theory():
    # D_d has 2*d*(d-1) roots, E8 has 240, E7 = 126, E6 = 72.
    assert len(S.d_roots(5)) == 40
    assert len(S.d_roots(4)) == 24
    assert len(S.e8_roots()) == 240
    assert len(S.e7_roots()) == 126
    assert len(S.e6_roots()) == 72


def test_root_systems_are_exact_integer_arithmetic():
    # The kissing condition is <x_i, x_j> <= 1/2, i.e. (scaled) at most half the
    # squared norm.  For the integer root systems this is checked exactly.
    cases = [
        (S.d_roots(4), 2),
        (S.d_roots(5), 2),
        (S.e8_roots(), 8),
        (S.e7_roots(), 8),
        (S.e6_roots(), 8),
    ]
    for roots, norm2 in cases:
        assert roots.dtype.kind == "i", "root systems must be integer vectors"
        gram = roots @ roots.T
        assert (np.diag(gram) == norm2).all()
        np.fill_diagonal(gram, 0)
        assert gram.max() <= norm2 // 2


def test_projected_e6_and_e7_live_in_the_smallest_space():
    assert S.root_system("e6").shape == (72, 6)
    assert S.root_system("e7").shape == (126, 7)
    # Projection is an isometry on the span: the Gram matrix is preserved.
    e6 = S.e6_roots().astype(float)
    projected = S.root_system("e6")
    assert np.allclose(S.gram(S.normalize(projected)), S.gram(S.normalize(e6)), atol=1e-12)


def test_icosahedron_nearest_neighbour_angle():
    # Nearest neighbours of a regular icosahedron subtend arccos(1/sqrt(5)).
    P = S.icosahedron()
    assert S.max_dot(P) == pytest.approx(1.0 / np.sqrt(5.0), abs=1e-12)


def test_kissing_detection_rejects_bad_configurations():
    P = S.root_system("d5")
    assert S.is_kissing_configuration(P)
    nudged = P.copy()
    nudged[0] = nudged[1]  # duplicate a point -> dot product 1
    assert not S.is_kissing_configuration(nudged)
    assert not S.is_kissing_configuration(P * 2.0)  # not unit vectors


def test_search_improves_and_stays_valid():
    rng = np.random.default_rng(0)
    P0 = S.random_points(6, 3, rng)
    start = S.max_dot(P0)
    P, value = S.search_min_max_dot(P0, 1.0, rng, use_scipy=False)
    assert value < start
    assert value == pytest.approx(S.max_dot(P), abs=1e-12)
    assert value <= S.KISSING_THRESHOLD  # 6 points in R^3 fit comfortably


def test_search_min_max_dot_is_time_bounded():
    import time

    rng = np.random.default_rng(1)
    P0 = S.random_points(10, 3, rng)
    started = time.time()
    S.search_min_max_dot(P0, 0.5, rng, use_scipy=False)
    assert time.time() - started < 5.0


def test_grow_to_n_returns_requested_size():
    rng = np.random.default_rng(2)
    P, _ = S.grow_to_n(S.root_system("d5")[:5], 8, 0.5, rng, use_scipy=False)
    assert len(P) == 8
    assert np.allclose(np.linalg.norm(P, axis=1), 1.0, atol=1e-9)


def test_smooth_max_dot_bounds_the_true_maximum():
    rng = np.random.default_rng(3)
    P = S.random_points(8, 4, rng)
    assert S.smooth_max_dot(P, beta=100.0) >= S.max_dot(P) - 1e-9
    assert S.smooth_max_dot(P, beta=100.0) <= S.max_dot(P) + 0.2
