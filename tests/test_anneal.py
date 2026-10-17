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

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from oplab import anneal as AN  # noqa: E402
from oplab import blocks as B  # noqa: E402
from oplab import gputabu as G  # noqa: E402

import anneal_hunt  # noqa: E402


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
# the gate
# --------------------------------------------------------------------------
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
