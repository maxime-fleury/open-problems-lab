"""The guided annealing: the counts it must not drift on, and the claims it may make.

Three things are checked, and none of them is speed.  First, the incremental state is
the ground truth or it is nothing: every move is applied through a delta, so the tests
recount from the assignment and demand agreement — including on the instance where a
class appears **twice** in a set (an isoceles triangle of ``Z_17``), which is exactly
the case a delta of "one" gets wrong.  Second, the statuses are honest: a run that ends
with violations left carries no colouring, a run whose witness fails the verifier is
``sat-invalid`` and not ``sat``.  Third, the gate in ``scripts/anneal_hunt.py`` really
refuses a target — a file that claims ``sat`` for another instance is not a pass.

These are CPU tests: unlike the GPU tabu, nothing here needs a card, so they always run.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from oplab import anneal as AN  # noqa: E402
from oplab import blocks as B  # noqa: E402
from oplab import gputabu as G  # noqa: E402
from oplab import multicolour as MC  # noqa: E402

import anneal_hunt  # noqa: E402
import partial_support  # noqa: E402


def _recount(problem, A):
    """``cnt`` and ``viol`` from an assignment, written out again on purpose."""
    pad = np.zeros(problem.nc + 1, dtype=np.int8)
    pad[:problem.nc] = A
    members = pad[problem.set_cls]
    valid = problem.set_cls != problem.nc
    cnt = np.zeros((problem.n_sets, problem.k), dtype=np.int8)
    for c in range(problem.k):
        cnt[:, c] = ((members == c) & valid).sum(axis=1)
    viol = cnt[np.arange(problem.n_sets), problem.set_col] == problem.set_need
    return cnt, viol


# --------------------------------------------------------------------------
# the counter: a delta is a claim about every set the move touched
# --------------------------------------------------------------------------
def test_the_short_sets_of_z17_still_count_right():
    """The one shape where a triangle can be isoceles, and the delta assumes it is deduped.

    In a block of ``Z_17`` the triangle ``{x, x+d, x+2d}`` has two of its edges in the
    class of ``d``, so its class set is the *two*-element ``{d, 2d}`` with
    ``set_need = 2`` — not a three-element set with a repeated class.  A recolour that
    assumes a multiplicity of two here is how the batched tabu shipped a counter that
    drifted only on this shape, so the invariant is asserted and then the counter is
    checked against a full recount.
    """
    instance = B.BlockInstance(51, (3, 3, 3, 3), blocks=3, group=(17,))
    problem = G.from_blocks(instance)

    short = 0
    for row, need in zip(problem.set_cls, problem.set_need):
        used = row[row != problem.nc]
        assert len(set(map(int, used))) == len(used), "a stored set repeats a class"
        short += int(len(used) < 3)
    assert short > 0, "this is the instance with the short (isoceles) sets"

    report = AN.anneal(problem, seconds=2.0, seed=0, recount_every=25)
    assert report["recount_drift"] == 0, "the incremental count disagreed with a recount"
    assert report["steps"] > 0


def test_the_state_after_a_kempe_swap_equals_a_recount():
    """A chain swap recolours a whole cluster; it is recounted, not cached."""
    instance = B.BlockInstance(8, (3, 3, 3), blocks=2, group=(2, 2))
    problem = G.from_blocks(instance)
    rng = np.random.default_rng(7)
    A = rng.integers(0, problem.k, size=problem.nc).astype(np.int8)
    cnt, viol = _recount(problem, A)

    swapped = AN._kempe_swap(A, cnt, viol, problem.inc, problem.inc_mask,
                             problem.set_cls, problem.set_col, problem.set_need,
                             problem.nc, problem.k, rng, cap=64)
    assert swapped >= 2, "the component should have held at least the start and a peer"

    truth_cnt, truth_viol = _recount(problem, A)
    assert np.array_equal(cnt, truth_cnt)
    assert np.array_equal(viol, truth_viol)



# --------------------------------------------------------------------------
# the repair: an exact move inside a frozen neighbourhood
# --------------------------------------------------------------------------
def _classes_of(problem, colouring):
    """The class assignment behind an expanded colouring (each class is one colour)."""
    instance = problem.edges_of
    return np.array([colouring[instance[p][0]] for p in range(problem.nc)], dtype=np.int8)


@pytest.mark.skipif(MC.solver_backing("cadical195") != "wheel",
                    reason="python-sat is not installed")
def test_a_repair_cannot_create_a_violation():
    """The sub-CNF covers every set a free class touches, so the count can only fall.

    The instance is ``K8`` at ``(3,3,3)`` — small enough to recount by hand, and
    satisfiable, so a perturbed witness has a repair to find.
    """
    instance = B.BlockInstance(8, (3, 3, 3), blocks=2, group=(2, 2))
    problem = G.from_blocks(instance)
    clean = AN.anneal(problem, seconds=10.0, seed=0)
    assert clean["status"] == "sat"
    A = _classes_of(problem, MC.parse_colouring(clean["coloring"], 8))
    _, viol = _recount(problem, A)
    assert not viol.any(), "the witness this starts from must be clean"

    rng = np.random.default_rng(3)
    q = int(rng.integers(problem.nc))
    A[q] = (A[q] + 1) % problem.k
    _, viol = _recount(problem, A)
    before = int(viol.sum())
    assert before >= 1, "the perturbation has to break something for this to test anything"

    outcome = AN.repair(problem, A, viol, rng, cap=problem.nc, seconds=10)
    assert outcome["solved"] is True and outcome["timeout"] is False
    _, after = _recount(problem, A)
    assert int(after.sum()) <= before, "a repair raised the count it was asked to lower"
    assert int(after.sum()) == 0


def test_a_repair_that_times_out_changes_nothing_and_says_so():
    """A budget that ran out is not a result: the assignment is left exactly as it was."""
    instance = B.BlockInstance(8, (3, 3, 3), blocks=2, group=(2, 2))
    problem = G.from_blocks(instance)
    rng = np.random.default_rng(0)
    A = rng.integers(0, problem.k, size=problem.nc).astype(np.int8)
    _, viol = _recount(problem, A)
    keep = A.copy()

    outcome = AN.repair(problem, A, viol, rng, cap=problem.nc,
                        solver=lambda clauses, seconds: "timeout")
    assert outcome["timeout"] is True and outcome["solved"] is False
    assert np.array_equal(A, keep)


def test_a_repair_without_an_engine_refuses_rather_than_improvising(monkeypatch):
    """No `python-sat` means no repair, and the report says which package is missing."""
    instance = B.BlockInstance(8, (3, 3, 3), blocks=2, group=(2, 2))
    problem = G.from_blocks(instance)
    rng = np.random.default_rng(0)
    A = rng.integers(0, problem.k, size=problem.nc).astype(np.int8)
    _, viol = _recount(problem, A)
    monkeypatch.setattr(AN, "_cdcl", lambda **kwargs: None)

    outcome = AN.repair(problem, A, viol, rng, cap=problem.nc)
    assert outcome["solved"] is False
    assert "python-sat" in outcome["note"]


# --------------------------------------------------------------------------
# the claims
# --------------------------------------------------------------------------
def test_a_witness_is_expanded_and_accepted_by_the_ordinary_verifier():
    """The positive path: a clean member of a family, counted again from the string."""
    instance = B.BlockInstance(8, (3, 3, 3), blocks=2, group=(2, 2))
    problem = G.from_blocks(instance)
    report = AN.anneal(problem, seconds=10.0, seed=0)

    assert report["status"] == "sat"
    assert report["violations"] == 0
    assert report["verify"]["valid"]
    assert len(report["coloring"]) == 8 * 7 // 2
    assert report["establishes"].startswith("R(3, 3, 3) > 8")


def test_an_instance_with_no_clean_colouring_never_reports_sat():
    """``R(3,3,3) = 17``: there is nothing to find, and a search may not imply otherwise.

    The report keeps the best count it reached and no colouring at all — ``best-effort``
    is a statement about this walk, and the test pins that it cannot be read as a
    refutation either: the status is not ``unsat`` and the family is not declared empty.
    """
    instance = B.BlockInstance(17, (3, 3, 3), blocks=1, group=(17,))
    problem = G.from_blocks(instance)
    report = AN.anneal(problem, seconds=2.0, seed=0)

    assert report["status"] == "best-effort"
    assert "coloring" not in report
    assert report["violations"] >= 1
    assert report["search_only"] is True


def test_a_witness_the_verifier_rejects_is_a_bug_and_not_a_result(monkeypatch):
    """``sat`` is never claimed on the walk's own word: the verifier has the last word."""
    instance = B.BlockInstance(8, (3, 3, 3), blocks=2, group=(2, 2))
    problem = G.from_blocks(instance)
    monkeypatch.setattr(AN.MC, "verify_colouring",
                        lambda n, sizes, text: {"valid": False, "reason": "planted"})
    report = AN.anneal(problem, seconds=10.0, seed=0)

    assert report["status"] == "sat-invalid"
    assert "establishes" not in report
    assert "bug in this module" in report["note"]


# --------------------------------------------------------------------------
# partial colourings: a blank class is absent, never a colour
# --------------------------------------------------------------------------
def test_the_partial_counter_agrees_with_the_complete_one_when_nothing_is_blank():
    """With no blanks the two counters must be the same function, not two opinions."""
    instance = B.BlockInstance(8, (3, 3, 3), blocks=2, group=(2, 2))
    problem = G.from_blocks(instance)
    rng = np.random.default_rng(5)
    for _ in range(5):
        A = rng.integers(0, problem.k, size=problem.nc).astype(np.int8)
        cnt, viol = AN._counts(problem, A)
        truth_cnt, truth_viol = _recount(problem, A)
        assert np.array_equal(cnt, truth_cnt)
        assert np.array_equal(viol, truth_viol)


def test_a_blank_class_is_masked_out_of_every_set_it_belongs_to():
    """The whole mechanism in one assertion: a blank class cannot colour a set.

    ``_counts`` pads the assignment with an extra slot so a blank index cannot be read
    as colour ``-1`` and silently join the count of whichever class is indexed last —
    the bug the complete-colouring counter would have.  Each set the blank class appears
    in is therefore counted over its other members only.
    """
    instance = B.BlockInstance(8, (3, 3, 3), blocks=2, group=(2, 2))
    problem = G.from_blocks(instance)
    rng = np.random.default_rng(0)
    A = rng.integers(0, problem.k, size=problem.nc).astype(np.int8)
    blank = problem.nc // 2
    A[blank] = AN.BLANK

    cnt, viol = AN._counts(problem, A)
    touched = problem.inc[blank][problem.inc_mask[blank]]
    assert touched.size > 0
    assert not viol[touched].any(), "a set with a blank class is not monochromatic"
    for s in touched:
        rest = [int(p) for p in problem.set_cls[s]
                if p != problem.nc and int(p) != blank]
        for c in range(problem.k):
            assert cnt[s, c] == sum(1 for p in rest if A[p] == c)


def test_the_partial_search_finds_a_known_witness_and_the_verifier_accepts_it():
    """The positive control: ``K8`` at ``(3,3,3)`` has an answer and the walk finds one."""
    instance = B.BlockInstance(8, (3, 3, 3), blocks=2, group=(2, 2))
    problem = G.from_blocks(instance)
    report = AN.partial(problem, seconds=10.0, seed=0)

    assert report["status"] == "sat", report.get("note")
    assert report["violations"] == 0 and report["blanks"] == 0
    assert report["verify"]["valid"]
    assert report["establishes"].startswith("R(3, 3, 3) > 8")
    assert "partial-colouring search" in report["establishes"]


def test_a_partial_state_is_named_partial_and_carries_no_colouring():
    """``R(3,3) = 6``: there is nothing to fill, and the report must not imply there is.

    The walk can reach zero violations here only by leaving a class blank, and the engine
    refuses to put it back.  That is a *partial* state — not a colouring, not a bound —
    and the report says so in its own words and with no ``coloring`` key at all.  The walk
    keeps churning after that first clean state, so the run may end a step away from it:
    both endings are honest and the test pins the contract, not the last coin flip.
    """
    instance = B.BlockInstance(6, (3, 3), blocks=1, group=(6,))
    problem = G.from_blocks(instance)
    report = AN.partial(problem, seconds=5.0, seed=0, attempt_every=2000,
                        repair_seconds=2.0)

    assert report["status"] in ("partial", "best-effort"), report["status"]
    assert "coloring" not in report and "establishes" not in report
    assert report["support"] is None
    assert report["refused"], "the engine must have been asked and refused"
    assert "not a colouring" in report["what"]
    if report["status"] == "partial":
        assert report["violations"] == 0 and report["blanks"] >= 1


def test_the_reported_assignment_reproduces_the_state_it_measured():
    """A ``partial`` row is resumable: the assignment and the blanks agree on a recount."""
    instance = B.BlockInstance(6, (3, 3), blocks=1, group=(6,))
    problem = G.from_blocks(instance)
    report = AN.partial(problem, seconds=3.0, seed=0, attempt_every=2000,
                        repair_seconds=2.0)

    A = np.array(report["assignment"], dtype=np.int8)
    assert A.shape == (problem.nc,)
    cnt, viol = AN._counts(problem, A)
    assert int(viol.sum()) == report["violations"]
    assert int((A < 0).sum()) == report["blanks"] == len(report["blanks_at"])
    assert sorted(report["blanks_at"]) == [int(p) for p in np.flatnonzero(A < 0)]


@pytest.mark.skipif(MC.solver_backing("cadical195") != "wheel",
                    reason="python-sat is not installed")
def test_the_support_script_stops_at_the_first_satisfiable_blank_count():
    """The growth loop reports *where* re-insertion stops saying unsat, and stops there.

    The state here is a witness with two classes blanked, so the first row must be ``sat``
    — the loop's job on a healthy state is to say so immediately, not to keep growing.
    """
    instance = B.BlockInstance(8, (3, 3, 3), blocks=2, group=(2, 2))
    problem = G.from_blocks(instance)
    clean = AN.anneal(problem, seconds=10.0, seed=0)
    assert clean["status"] == "sat"
    A = _classes_of(problem, MC.parse_colouring(clean["coloring"], 8))
    blanked = [0, 1]
    A[blanked] = AN.BLANK

    args = argparse.Namespace(step=2, seed=0, repair_seconds=2.0)
    table = partial_support.grow(problem, {"assignment": A.tolist(), "blanks_at": blanked},
                                 args)
    assert len(table) == 1, table
    assert table[0][0] == 2 and table[0][1] == "sat"


# --------------------------------------------------------------------------
# the budget: a bounded call that cannot be interrupted is not bounded
# --------------------------------------------------------------------------
@pytest.mark.skipif(MC.solver_backing("cadical195") != "wheel",
                    reason="python-sat is not installed")
def test_a_bounded_repair_really_is_bounded():
    """The bug this pins: CaDiCaL's ``interrupt`` raises, so the timer did nothing.

    Measured on the ``K50`` plateau, a repair given 2 s ran for 86 s and the run's
    ``repairs_timeout`` field could never have been non-zero.  A bounded call now picks an
    engine whose interrupt works, and this test hands it a pigeonhole formula — hard
    enough that a 0.3 s budget cannot possibly be enough — and demands the timeout is
    reported *and* arrives.
    """
    from pysat.examples.genhard import PHP

    solver = AN._cdcl(bounded=True)
    assert solver is not None
    assert solver.engine in AN.INTERRUPTIBLE_ENGINES
    assert solver.budget_enforced is True

    clauses = PHP(nof_holes=10).clauses
    started = time.time()
    assert solver(clauses, 0.3) == "timeout"
    assert time.time() - started < 10.0, "the budget was ignored"


@pytest.mark.skipif(MC.solver_backing("cadical195") != "wheel",
                    reason="python-sat is not installed")
def test_a_repair_says_which_engine_answered():
    """A verdict with no provenance cannot be reproduced: every repair names its engine."""
    instance = B.BlockInstance(8, (3, 3, 3), blocks=2, group=(2, 2))
    problem = G.from_blocks(instance)
    rng = np.random.default_rng(0)
    A = rng.integers(0, problem.k, size=problem.nc).astype(np.int8)
    _, viol = _recount(problem, A)
    outcome = AN.repair(problem, A, viol, rng, cap=4, seconds=5.0)
    assert outcome["engine"] == "maplechrono"
    assert outcome.get("budget_enforced", True) is True


# --------------------------------------------------------------------------
# the gate
# --------------------------------------------------------------------------
def test_the_driver_routes_the_partial_search():
    """``--partial`` must reach ``AN.partial``; a flag that falls through is decoration."""
    args = argparse.Namespace(partial=True, seconds=1.0, seed=0, blank_weight=1.0,
                              noise=0.05, repair_seconds=1.0, attempt_every=1000)
    instance = B.BlockInstance(8, (3, 3, 3), blocks=2, group=(2, 2))
    report = anneal_hunt.search(G.from_blocks(instance), args)
    assert report["blank_weight"] == 1.0
    assert "assignment" in report and "support" in report


def test_a_target_is_refused_until_the_gate_has_passed(tmp_path):
    """The driver's whole point: no gate, no run — and it says so with exit code 2."""
    gate = tmp_path / "gate.json"
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "anneal_hunt.py"), "51:3,3,3,3",
         "--blocks", "3", "--group", "17", "--seconds", "0.1", "--gate-file", str(gate)],
        capture_output=True, text=True)
    assert proc.returncode == 2, proc.stderr
    assert "refused" in proc.stderr
    assert not gate.exists(), "a refused run must not write a gate"


def test_a_gate_record_for_another_instance_is_not_a_pass(tmp_path):
    """A ``sat`` on a different instance cannot authorise the target."""
    gate = tmp_path / "gate.json"
    record = {"status": "sat", "verify": {"valid": True}, "gate_spec": dict(anneal_hunt.GATE_SPEC)}
    gate.write_text(json.dumps(record), encoding="utf-8")
    assert anneal_hunt.gate_record(gate) is not None

    record["gate_spec"] = {**record["gate_spec"], "n": 51}
    gate.write_text(json.dumps(record), encoding="utf-8")
    assert anneal_hunt.gate_record(gate) is None

    record["gate_spec"] = dict(anneal_hunt.GATE_SPEC)
    record["verify"] = {"valid": False}
    gate.write_text(json.dumps(record), encoding="utf-8")
    assert anneal_hunt.gate_record(gate) is None


@pytest.mark.parametrize("bad", ["", "not json", "{}"])
def test_a_missing_or_broken_gate_file_is_not_a_pass(tmp_path, bad):
    gate = tmp_path / "gate.json"
    gate.write_text(bad, encoding="utf-8")
    assert anneal_hunt.gate_record(gate) is None
