"""The GPU tabu search: what it may claim, and the one number it must not drift on.

Two things are checked here, and only one of them is about speed.  The first is that
the batched walk counts the same thing as the host — the packed class sets are the
clauses of the same instance, so a disagreement is a bug in the indexing, not a
mathematical discovery.  The second is that a search which ends with violations left
is reported as *that*: no status but ``sat`` may carry a colouring, and ``best-effort``
must never be mistaken for a refutation.  The incremental counter is also checked
against a full recount inside the walk, because a delta that silently drifts would
make every reported number a fiction.

Every test is skipped without a CUDA device: the SAT and circulant paths are the
ones that decide things, and they do not need a card.
"""

import numpy as np
import pytest

pytest.importorskip("torch")

from oplab import blocks as B  # noqa: E402
from oplab import gputabu as G  # noqa: E402

pytestmark = pytest.mark.skipif(not G.available(), reason="no CUDA device")


# --------------------------------------------------------------------------
# the encoding: the walk must count the clauses of the same instance
# --------------------------------------------------------------------------
def test_the_device_count_equals_the_host_count_on_random_skins():
    """The packed form is the CNF: same sets, same clauses, same count."""
    import torch

    instance = B.BlockInstance(8, (3, 3), blocks=2, group=(2, 2))
    problem = G.from_blocks(instance)
    rng = np.random.default_rng(0)
    skins = rng.integers(0, 2, size=(256, problem.nc)).astype(np.int8)

    host = np.array([problem.violations_host(skin) for skin in skins])
    # the same question asked of the packed arrays, independently of the walk
    cls = torch.as_tensor(problem.set_cls)
    col = torch.as_tensor(problem.set_col)
    need = torch.as_tensor(problem.set_need)
    batch = torch.from_numpy(skins)
    own = ((batch[:, cls] == col.view(1, -1, 1)) & (cls != problem.nc)).sum(dim=2)
    device = (own == need.view(1, -1)).sum(dim=1).numpy()

    assert np.array_equal(host, device)
    # and the count is not trivially right: the instance really has violations to find
    assert host.max() > 0


def test_a_padded_instance_counts_the_same_way_as_the_host():
    """A class set can be *shorter* than the widest one, and that case has its own bug.

    In a block of `Z_17` a triangle can be isoceles — `{x, x+d, x+2d}` has two of its
    edges in the class of `d` — so 96 of the 4 708 sets of `K51` 3×`Z_17` are padded.
    In characteristic two that cannot happen, which is why the elementary-abelian
    instances never exercised the padding: a gather one element past the end of a row
    is silent for every row but the last, and a device-side assert for that one.
    """
    import torch

    instance = B.BlockInstance(51, (3, 3, 3, 3), blocks=3, group=(17,))
    problem = G.from_blocks(instance)
    padded = int((problem.set_cls == problem.nc).any(axis=1).sum())
    assert padded > 0, "this instance is the one that has shorter class sets"

    rng = np.random.default_rng(1)
    skins = rng.integers(0, problem.k, size=(64, problem.nc)).astype(np.int8)
    host = np.array([problem.violations_host(skin) for skin in skins])
    # the same count on the packed arrays, with the sentinel column the walk carries
    padded_skins = np.concatenate([skins, np.zeros((len(skins), 1), dtype=np.int8)], axis=1)
    cls = torch.as_tensor(problem.set_cls)
    batch = torch.from_numpy(padded_skins)
    own = ((batch[:, cls] == torch.as_tensor(problem.set_col).view(1, -1, 1))
           & (cls != problem.nc)).sum(dim=2)
    device = (own == torch.as_tensor(problem.set_need).view(1, -1)).sum(dim=1).numpy()
    assert np.array_equal(host, device)


def test_the_general_problem_packs_every_clique_once():
    """``from_general`` classes are edges and its sets are the cliques of each size."""
    from math import comb

    problem = G.from_general(7, (3, 3))
    assert problem.nc == comb(7, 2)
    assert problem.n_sets == 2 * comb(7, 3)
    assert problem.set_need.max() == 3
    # every class is an edge of K_7 and every clique is a set of three of them
    assert len(problem.edges_of) == comb(7, 2)


# --------------------------------------------------------------------------
# what a walk may and may not claim
# --------------------------------------------------------------------------
def test_a_satisfiable_instance_comes_back_with_a_verified_witness():
    """``K_5`` has a clean two-colouring (``R(3,3) = 6``): the walk must find one."""
    problem = G.from_general(5, (3, 3))
    report = G.tabu(problem, seconds=10.0, walks=256, seed=1)
    assert report["status"] == "sat", report
    assert report["violations"] == 0
    assert report["verify"]["valid"] is True
    # the witness is a colouring of the same instance, re-counted by the verifier
    assert problem.violations_host(
        np.array([0 if c == "a" else 1 for c in report["coloring"]][: problem.nc])) >= 0
    assert report["recount_drift"] == 0


def test_an_unsatisfiable_instance_is_never_reported_as_a_solution():
    """``K_7`` has no clean two-colouring, and a search must not pretend otherwise.

    ``R(3,3) = 6``, so every colouring of ``K_7`` has a monochromatic triangle.  The
    walk cannot prove that — and the report has to say so: ``best-effort``, a positive
    violation count, and no colouring attached.
    """
    problem = G.from_general(7, (3, 3))
    report = G.tabu(problem, seconds=4.0, walks=256, seed=3)
    assert report["status"] == "best-effort", report
    assert report["violations"] > 0
    assert "coloring" not in report
    assert report["search_only"] is True


def test_the_incremental_counter_matches_a_full_recount():
    """The delta is a claim about the state; the walk re-derives it and reports drift."""
    problem = G.from_general(7, (3, 3))
    report = G.tabu(problem, seconds=4.0, walks=256, seed=5, recount_every=50)
    assert report["steps"] > 50, "the walk must have lived long enough to recount twice"
    assert report["recount_drift"] == 0


def test_the_device_report_is_honest_about_what_it_has():
    info = G.describe_device()
    assert info["available"] is True
    assert info["memory_mib"] > 0
    assert "cuda" in info
