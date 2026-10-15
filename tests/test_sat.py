"""Tests for the SAT encoder.

The primitives (``at_most``, ``at_least_k``, ``geq``, ``lex_leq``) are
cross-checked against the cardinality/lexicographic predicates they are supposed
to encode by enumerating every assignment of the original variables and asking a
solver whether the auxiliary variables can satisfy the constraints.  The Ramsey
verdicts are cross-checked against brute force (K5, K6 with ``k = 3``) and
against the theorems ``R(4,4) = 18`` (K17 satisfiable) — and, crucially, against
*soundness*: a satisfiable instance must stay satisfiable at every symmetry
level, since symmetry breaking may only remove equivalent solutions.
"""

import itertools

import pytest

from oplab import ramsey as R, sat as S

z3 = pytest.importorskip("z3", reason="the SAT backend is optional")

from oplab.sat import CNF  # noqa: E402


def satisfiable_under(cnf: CNF, fixed: dict[int, bool]) -> bool:
    """Can the auxiliary variables satisfy ``cnf`` given the fixed variables?"""
    solver = z3.Solver()
    booleans = [z3.Bool(f"v{i}") for i in range(1, cnf.num_vars + 1)]
    for var, value in fixed.items():
        solver.add(booleans[var - 1] if value else z3.Not(booleans[var - 1]))
    for clause in cnf.clauses:
        solver.add(z3.Or([booleans[l - 1] if l > 0 else z3.Not(booleans[-l - 1]) for l in clause]))
    return solver.check() == z3.sat


@pytest.mark.parametrize("m,k", [(3, 1), (4, 2), (4, 4), (5, 0), (5, 3)])
def test_at_most_matches_the_cardinality_predicate(m, k):
    cnf = CNF(m)
    cnf.at_most(list(range(1, m + 1)), k)
    for assignment in itertools.product([False, True], repeat=m):
        fixed = {i + 1: value for i, value in enumerate(assignment)}
        assert satisfiable_under(cnf, fixed) == (sum(assignment) <= k)


@pytest.mark.parametrize("m,k", [(3, 2), (4, 3), (5, 4), (5, 1)])
def test_at_least_k_matches_the_cardinality_predicate(m, k):
    cnf = CNF(m)
    cnf.at_least_k(list(range(1, m + 1)), k)
    for assignment in itertools.product([False, True], repeat=m):
        fixed = {i + 1: value for i, value in enumerate(assignment)}
        assert satisfiable_under(cnf, fixed) == (sum(assignment) >= k)


def test_at_least_k_counts_repeated_literals_with_weight_two():
    cnf = CNF(2)
    cnf.at_least_k([1, 1, 2], 2)  # x1 has weight 2
    assert not satisfiable_under(cnf, {1: False, 2: True})
    assert satisfiable_under(cnf, {1: True, 2: False})


def test_geq_is_a_sum_comparison():
    cnf = CNF(5)
    cnf.geq([1, 2, 3], [4, 5])
    for assignment in itertools.product([False, True], repeat=5):
        fixed = {i + 1: value for i, value in enumerate(assignment)}
        expected = sum(assignment[:3]) >= sum(assignment[3:])
        assert satisfiable_under(cnf, fixed) == expected


def test_lex_leq_matches_lexicographic_order_on_overlapping_variables():
    # Mimics the Ramsey use: the two lists share variables (permuted matrix rows).
    a = [1, 2, 3, 4]
    b = [2, 3, 4, 1]
    cnf = CNF(4)
    cnf.lex_leq(a, b)
    for assignment in itertools.product([False, True], repeat=4):
        fixed = {i + 1: value for i, value in enumerate(assignment)}
        left = [fixed[x] for x in a]
        right = [fixed[x] for x in b]
        assert satisfiable_under(cnf, fixed) == (left <= right)


def test_pair_var_is_a_bijection_onto_the_edges():
    n = 9
    vars_ = {S.pair_var(n, u, v) for u, v in itertools.combinations(range(n), 2)}
    assert vars_ == set(range(1, n * (n - 1) // 2 + 1))
    assert S.pair_var(n, 5, 2) == S.pair_var(n, 2, 5)
    with pytest.raises(ValueError):
        S.pair_var(n, 3, 3)


def test_clause_count_formula_matches_the_streamed_clauses():
    n, k, sym = 7, 3, 2
    instance = S.build_instance(n, k, sym)
    from math import comb

    assert instance.clause_count() == 2 * comb(n, k) + len(instance.cnf.clauses)
    assert sum(1 for _ in instance.clauses()) == instance.clause_count()


def brute_force_has_clean_colouring(n, k):
    for bits in range(1 << (n * (n - 1) // 2)):
        red = [0] * n
        for index, (u, v) in enumerate(itertools.combinations(range(n), 2)):
            if (bits >> index) & 1:
                red[u] |= 1 << v
                red[v] |= 1 << u
        if R.count_mono_clique(red, n, k) == 0:
            return True
    return False


def test_encoder_verdicts_match_brute_force_for_k3():
    # R(3,3) = 6: brute force settles K5 (sat) and K6 (unsat) independently.
    assert brute_force_has_clean_colouring(5, 3)
    assert not brute_force_has_clean_colouring(6, 3)
    for symmetry in S.SYMMETRY_LEVELS:
        sat_result = S.solve(5, 3, symmetry, seconds=30)
        assert sat_result["status"] == "sat", (symmetry, sat_result["status"])
        red = R.parse(sat_result["coloring"], 5)
        assert R.count_mono_clique(red, 5, 3) == 0
        assert S.solve(6, 3, symmetry, seconds=30)["status"] == "unsat"


def test_symmetry_breaking_is_sound_on_the_satisfiable_side():
    # R(4,4) = 18, so K17 has clean colourings; no symmetry level may cut them all.
    for symmetry in S.SYMMETRY_LEVELS:
        result = S.solve(17, 4, symmetry, seconds=60)
        assert result["status"] == "sat", (symmetry, result["status"])
        red = R.parse(result["coloring"], 17)
        assert R.count_mono_clique(red, 17, 4) == 0


def test_instance_metadata_is_honest_for_an_inconclusive_run():
    result = S.solve(6, 3, 0, seconds=5)
    assert result["encoding"]["edge_vars"] == 15
    assert result["encoding"]["subset_clauses_match_formula"] == 40
    assert result["status"] in {"sat", "unsat", "unknown"}


def test_dimacs_export_round_trip(tmp_path):
    instance = S.build_instance(6, 3, 1)
    path = tmp_path / "k6.cnf"
    info = instance.write_dimacs(path, comment="test")
    lines = [line for line in path.read_text().splitlines() if line and not line.startswith(("c", "p"))]
    assert len(lines) == info["clauses_written"] == instance.clause_count()
    header = next(line for line in path.read_text().splitlines() if line.startswith("p "))
    _, _, num_vars, num_clauses = header.split()
    assert int(num_vars) == instance.cnf.num_vars
    assert int(num_clauses) == instance.clause_count()


def test_ingestion_benchmark_reports_a_rate():
    bench = S.ingestion_benchmark(20, 5, 3, sample=2000)
    assert bench["clauses_sampled"] > 0
    assert bench["clauses_per_second"] > 0
    assert bench["clauses_total"] == S.build_instance(20, 5, 3).clause_count()


def test_unknown_symmetry_level_is_rejected():
    with pytest.raises(ValueError):
        S.build_instance(10, 4, 9)
    with pytest.raises(ValueError):
        S.build_instance(10, 11, 0)
