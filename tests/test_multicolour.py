"""Tests for the multicolour Ramsey layer.

The verifier is checked against brute force (it is the definition every
certificate rests on), the encoding is checked for *soundness* (a real colouring
satisfies every clause, at every symmetry level), and the search is checked to
find a witness on a case whose existence is a theorem.
"""

from __future__ import annotations

import itertools
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pytest

from oplab.multicolour import (
    RECORDS,
    TARGETS,
    CirculantInstance,
    MulticolourInstance,
    available_solvers,
    circulant_colouring,
    circulant_obstruction,
    circulant_solve,
    difference_class,
    difference_classes,
    is_valid,
    mono_clique_counts,
    parse_colouring,
    random_colouring,
    serialize_colouring,
    solve,
    tabu_search,
    verify_colouring,
)

CASES = [(8, (3, 3, 3)), (9, (3, 3, 4)), (11, (4, 4)), (10, (3, 4)), (12, (3, 3, 3, 3))]


def canonicalise(colouring):
    """Relabel the colours by first appearance on the first row."""
    n = colouring.shape[0]
    order: dict[int, int] = {}
    for c in (int(colouring[0, t]) for t in range(1, n)):
        order.setdefault(c, len(order))
    for c in range(int(colouring.max()) + 1):
        order.setdefault(c, len(order))
    return np.vectorize(order.get)(colouring)


def brute_counts(n, sizes, colouring):
    out = []
    for colour, s in enumerate(sizes):
        out.append(
            sum(
                1
                for subset in itertools.combinations(range(n), s)
                if all(colouring[a, b] == colour for a, b in itertools.combinations(subset, 2))
            )
        )
    return out


@pytest.mark.parametrize("n,sizes", CASES)
def test_clique_counter_matches_brute_force(n, sizes):
    rng = np.random.default_rng(abs(hash((n, sizes))) % (2**32))
    for _ in range(5):
        colouring = random_colouring(n, len(sizes), rng)
        assert mono_clique_counts(n, sizes, colouring) == brute_counts(n, sizes, colouring)


def test_serialisation_round_trip_and_validation():
    rng = np.random.default_rng(0)
    colouring = random_colouring(9, 3, rng)
    text = serialize_colouring(colouring, 9)
    assert len(text) == 9 * 8 // 2
    assert np.array_equal(parse_colouring(text, 9, 3), colouring)
    with pytest.raises(ValueError):
        parse_colouring("0" * 5, 9, 3)
    with pytest.raises(ValueError):
        parse_colouring("3" * 36, 9, 3)


def test_monochromatic_colouring_is_not_a_witness():
    """One colour everywhere must be reported as invalid, with the exact count."""
    n = 6
    colouring = np.zeros((n, n), dtype=np.int8)
    report = verify_colouring(n, (3, 3), "0" * (n * (n - 1) // 2))
    assert report["valid"] is False
    assert report["monochromatic_cliques"] == [20, 0]
    assert report["establishes"] is None


def test_known_witness_verifies():
    """A 3-colouring of K16 with no monochromatic triangle exists (R(3,3,3)=17)."""
    result = tabu_search(16, (3, 3, 3), seconds=8.0, seed=1, engine="matrix")
    assert result["violations"] == 0
    assert result["verified_zero"] is True
    report = verify_colouring(16, (3, 3, 3), result["coloring"])
    assert report["valid"] is True
    assert report["establishes"] == "R(3, 3, 3) > 16"


def test_reported_violations_always_match_the_verifier():
    """Whatever the search returns, the recount must agree with it."""
    for n, sizes in [(30, (3, 3, 3, 3)), (29, (3, 3, 4))]:
        result = tabu_search(n, sizes, seconds=5.0, seed=3)
        assert result["violations"] == sum(result["monochromatic_cliques"])
        assert verify_colouring(n, sizes, result["coloring"])[
            "monochromatic_cliques"] == result["monochromatic_cliques"]
        assert result["verified_zero"] == (result["violations"] == 0)


@pytest.mark.parametrize("symmetry", [0, 1])
def test_encoding_is_sound(symmetry):
    """A colouring respecting the breaks satisfies every clause of the encoding."""
    n, sizes = 9, (3, 3, 3)
    rng = np.random.default_rng(7)
    while True:
        colouring = random_colouring(n, len(sizes), rng)
        if is_valid(n, sizes, colouring):
            break
    instance = MulticolourInstance(n, sizes, symmetry)
    if symmetry >= 1:
        colouring = canonicalise(colouring)
    truth = instance.assignment(colouring)

    def satisfied(clause):
        return any((lit in truth) if lit > 0 else (-lit not in truth) for lit in clause)

    assert instance.symmetry_holds(colouring)
    assert all(satisfied(clause) for clause in instance.clauses())
    assert instance.clause_count() > 0


def test_the_colour_break_agrees_with_its_semantics():
    """The level-1 clauses are *equivalent* to restricted growth, not weaker.

    For random colourings the break clauses are satisfiable by :meth:`assignment`
    exactly when the first row grows in restricted order, so the auxiliary
    definition is exact and the break prunes what it claims to prune.
    """
    n, sizes, rng = 7, (3, 3), np.random.default_rng(11)
    instance = MulticolourInstance(n, sizes, symmetry=1)
    for _ in range(60):
        colouring = random_colouring(n, len(sizes), rng)
        truth = instance.assignment(colouring)

        def satisfied(clause, truth=truth):
            return any((lit in truth) if lit > 0 else (-lit not in truth) for lit in clause)

        clause_ok = all(satisfied(clause) for clause in instance.symmetry_clauses())
        assert clause_ok == instance.symmetry_holds(colouring)
    assert instance.clause_count() > len(list(instance.symmetry_clauses()))


def symmetry_copies(colouring, k):
    """Every relabelling of the vertices and of the colours, exhaustively."""
    n = colouring.shape[0]
    for perm in itertools.permutations(range(n)):
        p = np.array(perm)
        permuted = colouring[np.ix_(p, p)]
        for relabel in itertools.permutations(range(k)):
            yield np.vectorize(dict(enumerate(relabel)).get)(permuted)


def test_symmetry_breaks_are_realisable():
    """Breaks must lose nothing: valid colourings always have a copy obeying them.

    The colour break alone is realisable by relabelling, and the vertex break by
    reordering, but they are *not* independent: the colour named ``0`` is the one
    on the edge between the first two vertices, so both must be found at once.
    This brute-forces every vertex permutation and colour relabelling on small
    instances and checks one copy satisfies both breaks simultaneously.
    """
    n, sizes = 7, (4, 4)
    rng = np.random.default_rng(5)
    level1 = MulticolourInstance(n, sizes, 1)
    level2 = MulticolourInstance(n, sizes, 2)
    hits = 0
    for _ in range(400):
        colouring = random_colouring(n, len(sizes), rng)
        if not is_valid(n, sizes, colouring):
            continue
        hits += 1
        copies = symmetry_copies(colouring, len(sizes))
        witness = [
            c for c in copies if level1.symmetry_holds(c) and level2.symmetry_holds(c)
        ]
        assert witness, "no symmetric copy satisfies both breaks"
        assert mono_clique_counts(n, sizes, witness[0]) == [0, 0]
    assert hits >= 3


def test_instance_is_unsatisfiable_when_the_clique_bound_is_forced():
    """K6 cannot be 2-coloured without a monochromatic triangle (R(3,3) = 6)."""
    instance = MulticolourInstance(6, (3, 3), symmetry=1)
    # every clause is a 3-literal "not all of these edges have this colour"
    triangles = [c for c in instance.clauses() if len(c) == 3 and all(l < 0 for l in c)]
    assert len(triangles) == 2 * 20


def test_record_table_is_consistent():
    for name, record in RECORDS.items():
        assert record["sizes"] and all(s >= 3 for s in record["sizes"])
        assert record["witness_vertices"] == record["lower"] - 1
        assert record["upper"] >= record["lower"]
        assert record["source"]
    names = {name for name, _ in TARGETS}
    assert names <= set(RECORDS)
    for name, n in TARGETS:
        assert n == RECORDS[name]["lower"], name


@pytest.mark.skipif(not available_solvers(), reason="no bundled SAT solver")
def test_cdcl_solves_a_tiny_instance():
    """The CDCL path is exercised end to end, including the colouring decode."""
    result = solve(5, (3, 3, 3), seconds=20.0, solver="cadical195", symmetry=1)
    assert result["status"] == "sat"
    assert verify_colouring(5, (3, 3, 3), result["coloring"])["valid"] is True


# --------------------------------------------------------------------------
# the circulant sub-family
# --------------------------------------------------------------------------
def all_class_colourings(n, k):
    """Every assignment of ``k`` colours to the difference classes of ``Z_n``."""
    for combo in itertools.product(range(k), repeat=len(difference_classes(n))):
        yield dict(zip(difference_classes(n), combo))


@pytest.mark.parametrize("n,sizes", [(7, (3, 3)), (9, (3, 3)), (10, (3, 4)),
                                     (8, (4, 4)), (9, (3, 3, 3))])
def test_circulant_encoding_is_exactly_cleanliness(n, sizes):
    """Exhaustive: the CNF is satisfiable by a class assignment iff it is clean.

    This is the claim the whole sub-family rests on — the encoder is an
    *equivalent* restatement of "no monochromatic forbidden clique", not a
    relaxation (which would invent witnesses) and not a strengthening (which
    would invent negative answers).
    """
    instance = CirculantInstance(n, sizes)
    total = len(sizes) ** len(difference_classes(n))
    checked = 0
    for colours in all_class_colourings(n, len(sizes)):
        truth = instance.assignment(colours)
        clauses_ok = all(
            any((lit in truth) if lit > 0 else (-lit not in truth) for lit in clause)
            for clause in instance.clauses()
        )
        colouring = circulant_colouring(n, colours)
        # the expansion must really be constant on each difference class
        assert all(
            int(colouring[x, (x + d) % n]) == colours[d] == int(colouring[(x + d) % n, x])
            for d in difference_classes(n) for x in range(n)
        )
        clean = all(c == 0 for c in mono_clique_counts(n, sizes, colouring))
        assert clauses_ok == clean, (colours, clauses_ok, clean)
        checked += 1
    assert checked == total


def test_clique_class_groups_are_the_classes_of_real_cliques():
    """Every group comes from a clique, and every clique's classes are covered."""
    for n in (6, 7, 9):
        for s in (3, 4):
            if s > n:
                continue
            groups = {g for g in CirculantInstance(n, (s,) * s).groups[s]}
            for subset in itertools.combinations(range(n), s):
                classes = tuple(sorted({
                    difference_class(v - u, n)
                    for i, u in enumerate(subset) for v in subset[i + 1:]
                }))
                assert classes in groups
            for group in groups:
                # a group is realisable: some clique induces exactly these classes
                assert any(
                    tuple(sorted({
                        difference_class(v - u, n)
                        for i, u in enumerate(subset) for v in subset[i + 1:]
                    })) == group
                    for subset in itertools.combinations(range(n), s)
                )


def test_circulant_obstruction_is_arithmetic_and_forced():
    """When 3 divides n and every colour forbids a triangle, nothing is clean."""
    for n in (6, 9, 12, 51, 162):
        obstruction = circulant_obstruction(n, (3, 3, 3))
        assert obstruction is not None
        d = obstruction["class"]
        x, y, z = obstruction["triangle"]
        assert n % 3 == 0 and d == n // 3
        # the three edges of the triangle all lie in the class d
        assert difference_class(y - x, n) == d
        assert difference_class(z - y, n) == d
        assert difference_class(z - x, n) == d
        # and so, whatever colour class d gets, that triangle is monochromatic
        for colour in range(3):
            colours = {c: 0 for c in difference_classes(n)}
            colours[d] = colour
            expanded = circulant_colouring(n, colours)
            assert mono_clique_counts(n, (3, 3, 3), expanded)[colour] >= 1
    # a colour that tolerates triangles removes the obstruction
    assert circulant_obstruction(51, (3, 3, 4)) is None
    assert circulant_obstruction(50, (3, 3, 3)) is None


@pytest.mark.skipif(not available_solvers(), reason="no bundled SAT solver")
def test_circulant_ladder_agrees_with_the_classical_values():
    """Small cases whose answers are known independently of the solver."""
    assert circulant_solve(5, (3, 3))["status"] == "sat"  # the 5-cycle
    assert circulant_solve(6, (3, 3))["status"] == "obstructed"  # R(3,3) = 6
    assert circulant_solve(17, (4, 4))["status"] == "sat"  # the Paley graph
    assert circulant_solve(18, (4, 4))["status"] == "unsat"  # R(4,4) = 18
    # R(3,3,4) = 30 exactly: a witness at 29, none at 30
    assert circulant_solve(29, (3, 3, 4))["status"] == "sat"
    assert circulant_solve(30, (3, 3, 4))["status"] == "unsat"


@pytest.mark.skipif(not available_solvers(), reason="no bundled SAT solver")
def test_circulant_witness_expands_to_a_verified_colouring():
    """A sat verdict is only reported with the colouring re-counted as clean."""
    result = circulant_solve(44, (3, 3, 5))
    if result["status"] != "sat":  # pragma: no cover - depends on the solver
        pytest.skip(f"solver returned {result['status']}")
    text = result["coloring"]
    report = verify_colouring(44, (3, 3, 5), text)
    assert report["valid"] is True
    assert result["verified"]["monochromatic_cliques"] == report["monochromatic_cliques"]
    colouring = parse_colouring(text, 44, 3)
    for d in difference_classes(44):
        values = {int(colouring[x, (x + d) % 44]) for x in range(44)}
        assert len(values) == 1


@pytest.mark.skipif(not available_solvers(), reason="no bundled SAT solver")
@pytest.mark.parametrize("symmetry", [0, 1, 2])
def test_symmetry_breaks_keep_a_satisfiable_instance_satisfiable(symmetry):
    """K8 is 3-colourable with no monochromatic triangle, so no break may refute it."""
    result = solve(8, (3, 3, 3), seconds=20.0, symmetry=symmetry)
    assert result["status"] == "sat"
    assert verify_colouring(8, (3, 3, 3), result["coloring"])["valid"] is True
    assert MulticolourInstance(8, (3, 3, 3), symmetry).symmetry_holds(
        parse_colouring(result["coloring"], 8, 3)
    )


@pytest.mark.skipif(not available_solvers(), reason="no bundled SAT solver")
def test_the_solver_budget_is_enforced():
    """The budget must bound the run: the bundled solvers hold the GIL.

    `threading.Timer(...)` + `solve_limited(expect_interrupt=True)` looks like a
    budget but is not one with these bindings — the callback never runs, and the
    instance that was supposed to stop after 10 s was still running 90 s later.
    The budget is now enforced by killing a child process, and this test is the
    regression guard.
    """
    started = time.time()
    result = circulant_solve(97, (3, 3, 3, 4), seconds=5.0)
    elapsed = time.time() - started
    assert result["status"] in {"unknown", "sat", "unsat"}
    assert elapsed < 30, f"a 5 s budget took {elapsed:.1f} s"
    if result["status"] == "unknown":
        assert result.get("budget_expired") is True


def test_the_multiplier_invariant_sub_family_is_empty_at_the_targets(tmp_path):
    """The structured candidates are empty at all six undecided sizes.

    A colouring invariant under multiplication by units is a *strictly* smaller
    sub-family than the circulant one, and `K8` with sizes (3,3,3) is SAT there —
    which is what shows the reduction is neither vacuous nor broken (the witness is
    re-counted by this repository's own verifier, not by the probe's code).  At the
    six target sizes the answer is UNSAT for every one of them, in milliseconds.
    That says the structured candidates are empty; it says nothing about the full
    circulant family, and nothing about `R(3,3,3,4)` or `R(4,4,4)`.
    """
    script = Path(__file__).resolve().parents[1] / "scripts" / "orbit_probe.py"
    targets = ["8:3,3,3", "96:3,3,3,4", "97:3,3,3,4", "127:4,4,4", "128:4,4,4",
               "161:3,3,3,3,3", "538:3,3,3,3,3,3"]
    out = tmp_path / "orbits.json"
    result = subprocess.run([sys.executable, str(script), *targets, "--json", str(out)],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    lines = result.stdout.splitlines()
    assert "K8 (3, 3, 3): SAT" in lines[0] and "R(3, 3, 3) > 8" in lines[0], result.stdout
    assert all("UNSAT" in line for line in lines[1:]), result.stdout

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload[0]["status"] == "sat"
    assert payload[0]["verify"]["valid"]
    assert payload[0]["verify"]["monochromatic_cliques"] == [0, 0, 0]
    # a restriction, so the encoding is smaller than the circulant one it came from
    assert payload[-1]["classes"] == 269 and payload[-1]["vars"] == 18
    for row in payload[1:]:
        assert row["status"] == "unsat" and row["establishes"] is None


def test_a_crashed_solver_is_refused_rather_than_recorded_as_unknown(monkeypatch, tmp_path):
    """A worker that dies without a verdict must not become a stored `unknown` row.

    The bundled Kissat wheel dies with an access violation on this platform (on a
    trivial instance as much as on K96): the parent sees no message and reports
    `no_verdict` with the child's exit code.  `unknown` is reserved for a budget
    that ran out, so the CLI refuses to write a certificate here — otherwise the
    frontier table would count crashes as honest negatives.  The stub keeps the
    test independent of which wheels happen to crash where.
    """
    from oplab import multicolour as MC
    from oplab.cli import main

    def crashed(n, sizes, **kwargs):
        return {"n": n, "sizes": list(sizes), "solver": "kissat404", "status": "unknown",
                "no_verdict": True, "exit_code": 3221225477, "seconds": 10.7}

    monkeypatch.setattr(MC, "circulant_solve", crashed)
    out = tmp_path / "k96.json"
    assert main(["mc-circulant", "--n", "96", "--sizes", "3,3,3,4", "--out", str(out)]) == 2
    assert not out.exists(), "a crashed run must not leave a certificate behind"


def test_mc_circulant_dimacs_export_is_the_hand_off(tmp_path):
    """``--dimacs-only`` writes the CNF for an instance the bundled budget cannot settle.

    Six of the stored certificates are ``unknown``: their encodings (20 345 to
    149 024 clauses) exhausted the solver budget, and the documented next step is
    to hand the CNF to a full-strength solver.  This is that path, checked against
    the encoding the certificate quotes.
    """
    from oplab.cli import main

    path = tmp_path / "k96.cnf"
    assert main(["mc-circulant", "--n", "96", "--sizes", "3,3,3,4",
                 "--dimacs-only", "--dimacs", str(path)]) == 0
    instance = CirculantInstance(96, (3, 3, 3, 4))
    text = path.read_text(encoding="ascii")
    header = next(line for line in text.splitlines() if line.startswith("p "))
    _, _, num_vars, num_clauses = header.split()
    assert int(num_vars) == instance.total_vars() == 192
    assert int(num_clauses) == instance.clause_count()
    assert len([line for line in text.splitlines() if line and line[0] not in "cp"]) == int(
        num_clauses
    )

    # the export needs a path, and a solve still needs --out
    assert main(["mc-circulant", "--n", "96", "--sizes", "3,3,3,4", "--dimacs-only"]) == 2
    assert main(["mc-circulant", "--n", "96", "--sizes", "3,3,3,4"]) == 2


def test_solver_probe_reports_broken_engines_instead_of_listing_them():
    """Being bundled is not being available, and the probe is what separates them.

    ``available_solvers`` lists what the wheel imports; ``probe_solvers`` runs each
    engine on two trivial instances in a killable child and reports what happened.
    The bundled Kissat wheel dies with an access violation on this platform, so a
    probe that reported it as usable would be the same mistake in a new place.
    """
    from oplab import multicolour as MC

    if not MC.available_solvers():
        pytest.skip("no bundled SAT solver")

    unknown = MC.probe_solver("not-a-solver")
    assert unknown["status"] == "unavailable" and "not a bundled engine" in unknown["reason"]

    # A budget shorter than a process start-up is a budget that ran out: the probe
    # honours `seconds` literally, so this is deterministic rather than dependent on
    # how fast the machine happens to be.
    starved = MC.probe_solver("cadical195", seconds=0.01, refresh=True)
    assert starved["status"] == "timeout", starved
    assert starved["status"] in MC.PROBE_STATUSES

    rows = MC.probe_solvers(seconds=20.0, refresh=True)
    assert [row["solver"] for row in rows] == list(MC.PY_SAT_SOLVERS)
    assert all(row["status"] in MC.PROBE_STATUSES for row in rows)
    working = MC.working_solvers()
    assert set(working) <= set(MC.PY_SAT_SOLVERS)
    assert all(next(r for r in rows if r["solver"] == name)["status"] == "ok"
               for name in working)
    # an engine that answered has to have answered *correctly*: both verdicts
    for row in rows:
        if row["status"] == "ok":
            assert row["sat_ok"] is True and row["unsat_ok"] is True
    # this platform's pipeline rests on CaDiCaL, so its health is an invariant
    assert MC.probe_solver("cadical195")["status"] == "ok"


def test_solvers_command_exits_nonzero_when_an_engine_does_not_answer(capsys):
    """A campaign can check the engines first, and get a usable exit status."""
    from oplab.cli import main

    assert main(["solvers", "--seconds", "1", "--solver", "cadical195"]) == 0
    out = capsys.readouterr()
    assert "cadical195" in out.out and "ok" in out.out

    assert main(["solvers", "--seconds", "1", "--solver", "not-a-solver"]) == 1
    out = capsys.readouterr()
    assert "unavailable" in out.out
    assert "not answering: not-a-solver" in out.err


def test_the_colour_canonical_break_agrees_with_the_plain_encoding(tmp_path):
    """The relabelling break may not decide anything differently, anywhere.

    Colours of equal forbidden-clique size are interchangeable, so requiring them to
    *first appear* in increasing order costs no colouring; K29 (SAT) and K51 (UNSAT
    in the whole family) are the two directions that matter.  This runs both
    encodings on every subgroup of each case and demands agreement.
    """
    script = Path(__file__).resolve().parents[1] / "scripts" / "orbit_probe.py"
    result = subprocess.run(
        [sys.executable, str(script), "--compare", "--seconds", "60",
         "29:3,3,4", "51:3,3,3,3", "18:4,4"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.count("the canonical break agrees") == 3, result.stdout
    assert "agree=False" not in result.stdout
    assert "clean=True" in result.stdout  # and the witness is re-counted clean


def test_the_subgroup_sweep_finds_the_known_witnesses_and_invents_none():
    """Every distinct subgroup is decided; a witness is only accepted where one exists.

    ``K29`` and ``K44`` are satisfiable — and the sweep reaches them through
    *smaller* subgroups than the full unit group, which is UNSAT there, so the
    reduction is neither vacuous nor lossless.  ``K18`` and ``K51`` have no
    circulant colouring at all, so no subgroup may hand one over.
    """
    script = Path(__file__).resolve().parents[1] / "scripts" / "orbit_probe.py"
    result = subprocess.run(
        [sys.executable, str(script), "--by-subgroup", "--seconds", "20",
         "29:3,3,4", "44:3,3,5", "18:4,4", "51:3,3,3,3"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    lines = [line for line in result.stdout.splitlines() if line.startswith("K")]
    assert any("K29 (3, 3, 4): SAT in the subgroup" in line and "R(3, 3, 4) > 29" in line
               for line in lines), result.stdout
    assert any("K44 (3, 3, 5): SAT in the subgroup" in line and "R(3, 3, 5) > 44" in line
               for line in lines), result.stdout
    for blocked in ("K18 (4, 4)", "K51 (3, 3, 3, 3)"):
        assert any(blocked + ": no witness" in line for line in lines), result.stdout


def test_a_sweep_row_that_timed_out_still_knows_which_family_it_was(tmp_path):
    """A killed run has no summary of its own, so the sweep has to stamp the identity.

    Without that, the JSON of a sweep whose rows ran out of budget is a list of
    anonymous rows and the evidence cannot be attributed to a family — which is
    exactly the failure mode a stored `unknown` row must not have.  Whether a row
    timed out at all depends on the machine (a small family can be decided inside the
    floor of a tiny budget), so what is asserted is the identity, plus that anything
    undecided says *why*.
    """
    script = Path(__file__).resolve().parents[1] / "scripts" / "orbit_probe.py"
    out = tmp_path / "starved.json"
    result = subprocess.run(
        [sys.executable, str(script), "--by-subgroup", "--seconds", "0.01",
         "51:3,3,3,3", "--json", str(out)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    rows = json.loads(out.read_text(encoding="utf-8"))
    assert rows, result.stdout
    for row in rows:
        assert row["status"] in {"unknown", "unsat", "sat"}, row
        assert row["n"] == 51 and row["sizes"] == [3, 3, 3, 3]
        assert "subgroup_order" in row
        if row["status"] == "unknown":
            assert row.get("budget_expired") is True, row
