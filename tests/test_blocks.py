"""Tests for the block-Cayley family.

Three kinds of claim are checked here, and none of them needs a solver:

* the classes **partition** the edges of ``K_n`` — every edge is coloured by exactly
  one class, and the two ways of asking which one agree (``exact``), because an
  encoding that loses an edge or colours one twice is a different problem;
* the clause set is **exact** — a class assignment satisfies it *iff* its expansion is
  clean — checked by exhausting every assignment on instances small enough to exhaust,
  which is the only way to know the encoding is not merely implied by cleanliness;
* the family **contains** the two families already swept: with one block it is the
  circulant encoding, and it has to agree with it clause for clause on the cases where
  both can be written down.
"""

from __future__ import annotations

import itertools
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from oplab import blocks as B  # noqa: E402
from oplab import multicolour as MC  # noqa: E402


# --------------------------------------------------------------------------
# the partition, and the enumerations that rest on it
# --------------------------------------------------------------------------
@pytest.mark.parametrize("shape", [
    # n, sizes, blocks, group, extras
    (9, (3, 3), 3, (3,), 0),
    (18, (3, 3), 2, (9,), 0),
    (18, (3, 3), 3, (6,), 0),
    (18, (3, 3), 6, (3,), 0),
    (20, (3, 3), 3, (6,), 2),
    (18, (3, 3), 2, (3, 3), 0),
    (16, (3, 3), 4, (2, 2), 0),
    (6, (3, 3), 1, (6,), 0),
])
def test_the_classes_partition_every_edge_exactly_once(shape):
    """One class per edge, whichever way the class is asked for.

    The family is only well defined because the colour of an edge depends on its
    class; if two classes carried one edge they could disagree about it, and if some
    edge belonged to none the encoding would be about a different graph.
    """
    n, sizes, blocks, group, extras = shape
    instance = B.BlockInstance(n, sizes, blocks=blocks, group=group, extras=extras)
    report = B.exact(instance)
    assert report["partition"] is True, report
    assert report["edges_covered"] == report["edges"] == n * (n - 1) // 2
    assert report["edges_in_several_classes"] == 0
    assert report["edges_named_differently"] == 0


def test_the_group_structure_is_the_one_asked_for():
    """``(16,)`` is ``Z_16``; ``(2, 2, 2, 2)`` is the elementary abelian group.

    The order-16 witnesses in the literature are built on the elementary abelian
    group, so the two have to be different objects here — same order, different
    difference structure, and a different number of diagonal classes.
    """
    cyclic = B.BlockInstance(48, (3, 3), blocks=3, group=(16,), extras=0)
    elementary = B.BlockInstance(48, (3, 3), blocks=3, group=(2, 2, 2, 2), extras=0)
    assert len(cyclic.elements) == len(elementary.elements) == 16
    # Z_16 has 8 invertible differences up to sign, Z_2^4 has 15 self-inverse ones
    assert len([k for k in cyclic.classes if k[0] == "d"]) == 3 * 8
    assert len([k for k in elementary.classes if k[0] == "d"]) == 3 * 15
    # and the between-block classes are the group elements, in both
    assert len([k for k in cyclic.classes if k[0] == "b"]) == 3 * 16
    assert len(elementary.classes) == 3 * 15 + 3 * 16


def test_one_block_of_a_group_of_order_n_is_the_circulant_family():
    """The new family has to contain the old one, or it is a different problem.

    With ``b = 1`` there is nothing to have a class between, so the classes are the
    difference classes and the expansion is the circulant expansion — the same
    colouring, class for class, which is checked rather than asserted.
    """
    for n in (6, 7, 8, 15):
        sizes = (3, 3)
        block = B.BlockInstance(n, sizes, blocks=1, group=(n,))
        circulant = MC.CirculantInstance(n, sizes)
        assert [key[2][0] for key in block.classes] == list(circulant.classes)
        for assignment in itertools.product(range(2), repeat=len(block.classes)):
            per_class = {key: colour for key, colour in zip(block.classes, assignment)}
            here = MC.serialize_colouring(block.expand(per_class), n)
            there = MC.serialize_colouring(
                MC.circulant_colouring(n, {d: per_class[("d", 0, (d,))]
                                           for d in circulant.classes}), n)
            assert here == there, (n, assignment)


# --------------------------------------------------------------------------
# exactness, by exhaustion
# --------------------------------------------------------------------------
def _satisfies(instance: B.BlockInstance, colours: dict) -> bool:
    """Whether a class assignment satisfies the clause set, evaluated directly.

    The truth set holds *literals*, both signs: a class assigned colour ``c`` makes
    ``+var(key, c)`` true and every ``-var(key, c')`` true as well.  Taking only the
    positive variables would call every negative clause false and make the check
    meaningless in the one direction that matters.
    """
    truth = set()
    for key in instance.classes:
        for colour in range(instance.k):
            literal = instance.var(key, colour)
            truth.add(literal if colours[key] == colour else -literal)
    return all(any(lit in truth for lit in clause) for clause in instance.clauses())


@pytest.mark.parametrize("shape", [
    # n, sizes, blocks, group, extras
    (5, (3, 3), 1, (5,), 0),          # the 5-cycle, and its dirty siblings
    (4, (3, 3), 2, (2,), 0),          # two blocks of Z_2
    (6, (3, 3, 3), 3, (2,), 0),       # three colours, three blocks of Z_2
    (5, (3, 3, 3), 1, (4,), 1),       # a block of Z_4 plus a free vertex
    (7, (4, 4), 1, (7,), 0),          # a forbidden K_4 rather than a triangle
])
def test_the_clause_set_is_satisfied_exactly_by_the_clean_colourings(shape):
    """Exhaustion is the only honest test of an equivalence claim.

    Every assignment of a colour to every class is enumerated and the CNF is evaluated
    on it directly; it is satisfiable exactly when the expanded colouring of ``K_n``
    has no monochromatic forbidden clique.  If a polarity or a class set were wrong,
    one of these assignments would disagree, and the failure names it.
    """
    n, sizes, blocks, group, extras = shape
    instance = B.BlockInstance(n, sizes, blocks=blocks, group=group, extras=extras)
    assert len(instance.classes) <= 9, "the exhaustion below has to stay finite"
    seen_sat = seen_unsat = 0
    for assignment in itertools.product(range(instance.k), repeat=len(instance.classes)):
        colours = dict(zip(instance.classes, assignment))
        expanded = instance.expand(colours)
        clean = MC.is_valid(n, sizes, expanded)
        assert _satisfies(instance, colours) == clean, (
            f"{shape}: assignment {colours} satisfies the clauses "
            f"{_satisfies(instance, colours)} but its expansion is clean {clean}")
        seen_sat += clean
        seen_unsat += not clean
    # a test where every assignment agrees because every assignment is clean (or none
    # is) would prove nothing, so require both sides to be represented
    assert seen_sat and seen_unsat, (shape, seen_sat, seen_unsat)


def test_the_colour_break_does_not_cost_a_colouring():
    """Colours of the same forbidden size are interchangeable, and that is checked.

    With four triangle colours, 4! = 24 relabellings of any witness exist, so fixing
    one class to colour 0 costs nothing — as long as the sizes really are equal.  The
    break is refused for ``(4, 6)``, where the two colours are not interchangeable.
    """
    equal = B.BlockInstance(5, (3, 3, 3), 1, (4,), 1, break_colours=True)
    assert equal.break_colours
    satisfying = [dict(zip(equal.classes, a))
                  for a in itertools.product(range(3), repeat=len(equal.classes))
                  if _satisfies(equal, dict(zip(equal.classes, a)))]
    plain = B.BlockInstance(5, (3, 3, 3), 1, (4,), 1, break_colours=False)
    assert satisfying and all(colours[equal.classes[0]] == 0 for colours in satisfying)
    assert any(c[plain.classes[0]] != 0 for c in
               [dict(zip(plain.classes, a))
                for a in itertools.product(range(3), repeat=len(plain.classes))
                if _satisfies(plain, dict(zip(plain.classes, a)))])

    mixed = B.BlockInstance(30, (4, 6), blocks=1, group=(30,), break_colours=True)
    assert mixed.break_colours is False


def test_the_family_is_refused_when_it_does_not_add_up():
    """A shape whose blocks and extras do not cover ``n`` is a different graph."""
    with pytest.raises(ValueError):
        B.BlockInstance(51, (3, 3, 3, 3), blocks=3, group=(16,))
    with pytest.raises(ValueError):
        B.BlockInstance(51, (3, 3, 3, 3), blocks=3, group=(17,), extras=3)
    with pytest.raises(ValueError):
        B.group_elements((1,))
    # a clique size the enumeration cannot afford is refused rather than attempted
    instance = B.BlockInstance(40, (3, 3), blocks=5, group=(8,))
    with pytest.raises(ValueError, match="over the"):
        B.class_sets(instance, 8)


def test_a_block_of_divisible_order_is_dead_by_arithmetic():
    """The ``3 | m`` obstruction comes back inside a block, and it is per block.

    Cauchy gives an element ``d`` of order 3 in any group of order divisible by 3, and
    ``{x, x+d, x+2d}`` has all three differences in the class of ``d`` — so that block
    is monochromatic in whatever colour the class gets.  The three shapes that the
    campaign refuted in 0.2 s are exactly these, which is why they are refuted by
    arithmetic rather than by a solver.
    """
    for shape in [(51, (3, 3, 3, 3), 17, (3,), 0),
                  (51, (3, 3, 3, 3), 3, (15,), 6),
                  (51, (3, 3, 3, 3), 4, (12,), 3)]:
        n, sizes, blocks, group, extras = shape
        instance = B.BlockInstance(n, sizes, blocks=blocks, group=group, extras=extras)
        assert B.block_obstruction(instance) is not None, shape
        report = B.solve_blocks(n, sizes, blocks=blocks, group=group, extras=extras,
                                seconds=1.0)
        assert report["status"] == "obstructed" and report["seconds"] == 0.0
    # and the shapes that survive it are the ones whose blocks avoid a factor of 3
    for shape in [(51, (3, 3, 3, 3), 3, (17,), 0),
                  (51, (3, 3, 3, 3), 3, (2, 2, 2, 2), 3),
                  (51, (3, 3, 3, 3), 6, (8,), 3)]:
        n, sizes, blocks, group, extras = shape
        assert B.block_obstruction(B.BlockInstance(n, sizes, blocks=blocks, group=group,
                                                   extras=extras)) is None, shape
    # an instance whose colours do not all forbid a triangle is not reached by it
    mixed = B.BlockInstance(30, (4, 6), blocks=1, group=(30,))
    assert B.block_obstruction(mixed) is None


def test_the_obstruction_that_kills_every_circulant_candidate_here_does_not_apply():
    """``51 = 3 * 17`` is circulant-dead (difference 17) and block-alive.

    This is the whole reason the family is worth a campaign: the arithmetic
    obstruction needs ``n/3`` to be a class of ``Z_n``, and inside blocks of ``Z_17``
    that difference does not exist.  The instance is also small enough to be handed
    to a solver.
    """
    assert MC.circulant_obstruction(51, (3, 3, 3, 3)) is not None
    instance = B.BlockInstance(51, (3, 3, 3, 3), blocks=3, group=(17,))
    assert B.exact(instance)["partition"] is True
    assert len(instance.classes) == 75          # 3 blocks x 8 differences + 3 pairs x 17
    assert instance.total_vars() == 300
    assert instance.clause_count() == len(instance.classes) * 7 + 4 * len(instance.sets[3])
    assert instance.blocks * instance.m == 51
