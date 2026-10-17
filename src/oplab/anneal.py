"""Guided annealing over the class-set instances: steering instead of multiplicity.

:mod:`oplab.gputabu` answers the witness question with a population and a card, and it
is fast: 4 096 walks, 264 million class moves, 0.6 M flips per second.  It is also
*stuck* — on ``K50`` in the block-Cayley family it ends two monochromatic cliques away
from a colouring that is known to exist, and that is the measurement this module
answers.  More throughput was not the lever; the batched walk was never short of steps.

So this one steers, with three changes aimed at three specific failures:

* **penalty weights** (guided local search).  A class set that stays violated costs
  more every time the walk stalls, so the augmented cost pushes it out of the basin it
  is circling in instead of re-attacking the same two sets forever.
* **simulated annealing**: a worsening move is accepted with probability
  ``exp(-delta / T)``, with ``T`` falling geometrically and reheating on a stall.
  Measured on the calibration instance, cooling *lost* to a constant rule that never
  rejects (``reject=False`` is the default): at ``T`` around 0.3 the walk spends most
  of its steps refusing to move and ends further from the answer.  The schedule is kept
  because it is the method the campaign asked for, and because a search should be able
  to say which of its two rules it ran on.
* **Kempe chains**.  Pick two colours, take a connected component of the classes
  carrying them, and swap the two colours inside it.  That recolours a whole cluster in
  one step — the coordinated move no single-class step can make.  It is the one change
  that moved the calibration instance: 6 cliques left became 3 at ``kempe=0.005``.

The counter discipline is the same as in :mod:`oplab.gputabu` and is not decoration:
the cost is updated by the delta of the move just applied, so every ``recount_every``
steps the whole state is recounted from scratch and any disagreement is reported in
``recount_drift``.  The delta is one per recolour because the encoder dedupes the class
multiset of a clique — an isoceles triangle of ``Z_17`` is stored as the *two*-element
set ``{d, 2d}``, with ``set_need = 2`` — and the tests pin that invariant rather than
assume it.

**This module is not a decision procedure.**  ``best-effort`` means the walk ran out of
budget with that many monochromatic cliques left; it is not evidence that the family is
empty.  ``sat`` means the walk reached zero **and** the expanded colouring survived
:func:`oplab.multicolour.verify_colouring`; a witness that fails that check is
``sat-invalid``, a bug in this file.

:func:`partial` changes the encoding rather than the walk: a class may be left **blank**,
so a violation can be dissolved instead of recoloured, and the blank classes are then
handed to the engine through :func:`repair`.  Its ``partial`` status is not a colouring
and not a bound — it says zero violations with some classes uncoloured, which is a
statement about the state the walk reached and about nothing else.

The gate lives in ``scripts/anneal_hunt.py``: this search is only allowed to speak
about ``K51`` after it has rediscovered the *known* witness at ``K50`` from a random
start.  It has not, and ``RESULTS.md`` §9e records that instead of hiding it.
"""

from __future__ import annotations

import math
import time

import numpy as np

from . import multicolour as MC
from .gputabu import Problem

__all__ = ["anneal", "partial", "repair"]


def _engine_clauses(problem, A, free):
    """The sub-CNF for one neighbourhood: recolour ``free``, hold everything else.

    The encoding is the instance's own clause, restricted to the classes that are
    allowed to move.  A set whose frozen classes already avoid its forbidden colour is
    satisfied and contributes nothing; a set whose frozen classes are *all* on that
    colour keeps the free literals, so the engine still has to move one of them.  Every
    violated set has all of its classes free by construction, so its clause is never
    empty — ``None`` is returned instead of a sub-CNF that could not fix it.
    """
    g = problem
    k = g.k
    index = {int(p): i for i, p in enumerate(free)}

    def var(i, c):
        return (i + 1) * k + c + 1

    clauses = []
    for i in range(len(free)):
        clauses.append([var(i, c) for c in range(k)])
        for c in range(k):
            for other in range(c + 1, k):
                clauses.append([-var(i, c), -var(i, other)])

    free_arr = np.asarray(free, dtype=np.int64)
    affected = np.unique(g.inc[free_arr][g.inc_mask[free_arr]])
    for s in affected:
        members = [int(p) for p in g.set_cls[s] if p != g.nc]
        colour = int(g.set_col[s])
        clause = []
        satisfied = False
        for p in members:
            if p in index:
                # the clause is "some class of this set is *not* the forbidden colour",
                # so the literals are positive: (p takes c) for every c but ``colour``
                clause.extend(var(index[p], c) for c in range(k) if c != colour)
            elif int(A[p]) != colour:
                satisfied = True
                break
        if satisfied:
            continue
        if not clause:
            return None
        clauses.append(clause)
    return clauses, index, k


def repair(problem: Problem, A, viol, rng, cap: int = 64, solver=None,
           seconds: float = 5.0, free=None) -> dict:
    """Let a CDCL engine recolour the neighbourhood around the violated sets.

    This is the move the local searches cannot make.  A walk that is two cliques from a
    witness is not short of better single moves — it is short of a *coordinated* one —
    so the classes of the violated sets are freed together with a random sample of the
    classes they touch, everything else is frozen, and the resulting sub-CNF is handed
    to the engine.  It is exact inside the neighbourhood, which is what makes the
    result trustworthy: every set that touches a free class appears in the sub-CNF, so
    **a satisfying assignment cannot create a violation anywhere**, and sets with no
    free class are untouched.  The repair therefore only ever lowers the count.

    ``A`` is updated in place.  Returns ``{"free", "solved", "seconds", "timeout"}``;
    ``solved`` is ``False`` when the neighbourhood is too small (the engine proved it
    unsatisfiable there), when the budget ran out, or when no engine is installed.
    ``solver`` is injectable so the encoding can be tested without one: it takes the
    clause list and the budget and returns a model, ``None`` for unsatisfiable, or
    ``"timeout"``.  ``free`` overrides the neighbourhood entirely — :func:`partial`
    hands in the blank classes, which is the case where the caller already knows which
    classes have to move.

    Every answer names the engine behind it (``engine``, and ``budget_enforced`` when a
    budget was given), because a verdict that cannot name its solver cannot be
    reproduced.  A bounded call is made on an engine whose interrupt works —
    :func:`_cdcl` picks one, and the docstring there records why CaDiCaL cannot be that
    engine: its ``interrupt`` raises, so a "bounded" call on it is not bounded at all.
    """
    started = time.time()
    g = problem
    if free is None:
        bad = np.flatnonzero(viol)
        if bad.size == 0:
            return {"free": 0, "solved": False, "seconds": 0.0}
        seed = np.unique(g.set_cls[bad][g.set_cls[bad] != g.nc]).astype(np.int64)
        near = np.unique(g.inc[seed][g.inc_mask[seed]])
        near = np.unique(g.set_cls[near][g.set_cls[near] != g.nc]).astype(np.int64)
        near = np.setdiff1d(near, seed)
        take = int(min(max(0, cap - seed.size), near.size))
        free = list(seed) + ([] if take == 0
                             else rng.choice(near, size=take, replace=False).tolist())
    else:
        free = [int(p) for p in free]
        if not free:
            return {"free": 0, "solved": False, "seconds": 0.0}
    built = _engine_clauses(g, A, free)
    if built is None:  # pragma: no cover - a violated set is free by construction
        return {"free": len(free), "solved": False, "seconds": time.time() - started}
    clauses, index, k = built
    if solver is None:
        solver = _cdcl(bounded=bool(seconds))
        if solver is None:
            return {"free": len(free), "solved": False, "seconds": time.time() - started,
                    "timeout": False, "engine": None,
                    "note": "no engine installed (python-sat)"}
    engine = getattr(solver, "engine", "injected")
    refused = {"free": len(free), "solved": False,
               "seconds": time.time() - started, "engine": engine}
    if seconds and not getattr(solver, "budget_enforced", True):
        refused["budget_enforced"] = False
        refused["note"] = (f"{engine} cannot be interrupted, so the {seconds:g} s budget "
                          f"was not enforced")
    model = solver(clauses, seconds)
    if model == "timeout":
        return {**refused, "timeout": True}
    if not model:
        return {**refused, "timeout": False}
    truth = set(model)
    for p, i in index.items():
        for c in range(k):
            if (i + 1) * k + c + 1 in truth:
                A[p] = c
                break
    return {**refused, "solved": True, "timeout": False}


#: ``python-sat`` engines whose ``interrupt`` actually stops a search, best-first.
#: CaDiCaL is deliberately absent: ``Cadical195.interrupt`` raises
#: ``NotImplementedError`` *from the timer thread*, so ``solve_limited`` there runs to
#: completion and a "bounded" call is not bounded.  Measured on the ``K50`` plateau, a
#: repair given 2 s took 86 s, which is how this got found.
INTERRUPTIBLE_ENGINES = ("maplechrono", "glucose4", "minisat22")
_CLASS_NAMES = {"maplechrono": "MapleChrono", "glucose4": "Glucose4",
                "minisat22": "Minisat22", "cadical195": "Cadical195"}


def _cdcl(bounded: bool = False):
    """A ``python-sat`` solver as a clause-in/answer-out function, or ``None``.

    The budget matters: a repair is a sub-instance of the *same* problem, so on a
    neighbourhood that is nearly the whole instance the engine can be as slow as the
    full search (500 s at ``K50``).  A walk cannot wait for that, so the call is
    interrupted and reported as a timeout instead of silently hanging the campaign.

    ``bounded`` therefore picks an engine that can be interrupted (:data:`INTERRUPTIBLE_ENGINES`)
    instead of CaDiCaL, which cannot.  The unbounded path still prefers CaDiCaL, because
    when nothing has to be stopped it is the better engine.  The answer is otherwise the
    same one ``repair`` always gave: ``None`` for unsatisfiable, a model for satisfiable,
    and the function carries ``.engine`` and ``.budget_enforced`` so the caller can say
    which implementation produced the verdict.
    """
    try:
        import pysat.solvers as PS  # noqa: PLC0415 - optional dependency
    except Exception:  # pragma: no cover - depends on the installation
        return None
    import threading

    order = (INTERRUPTIBLE_ENGINES if bounded else ()) + ("cadical195",) + INTERRUPTIBLE_ENGINES
    for name in order:
        engine_class = getattr(PS, _CLASS_NAMES[name], None)
        if engine_class is not None:
            break
    else:  # pragma: no cover - depends on the installation
        return None

    def solve(clauses, seconds=None):
        engine = engine_class(bootstrap_with=clauses)
        timer = None
        try:
            if seconds:
                timer = threading.Timer(seconds, engine.interrupt)
                timer.daemon = True
                timer.start()
            if seconds and name in INTERRUPTIBLE_ENGINES:
                answer = engine.solve_limited(expect_interrupt=True)
            else:
                answer = engine.solve()
            if answer is None:
                return "timeout"
            return engine.get_model() if answer else None
        finally:
            if timer is not None:
                timer.cancel()
            engine.delete()

    solve.engine = name
    solve.budget_enforced = name in INTERRUPTIBLE_ENGINES
    return solve


def _kempe_swap(A, cnt, viol, inc, inc_mask, set_cls, set_col, set_need, nc, k,
                rng, cap):
    """Swap two colours on one connected component of the classes carrying them.

    The component is grown over the 2-section of the class sets: two classes are
    adjacent when they appear in the same set.  Every set incident to the component is
    recounted, so the caller never has to trust a delta across a swap.  Returns the
    number of classes swapped, so a step that did nothing can be charged as nothing.

    On these encodings ``k = 4`` colours and ``nc`` classes, so a swap is a genuine
    large move: it is the only step in this module that can fix several violations in
    different neighbourhoods at once.
    """
    a, b = rng.choice(k, size=2, replace=False)
    holders = np.flatnonzero((A == a) | (A == b))
    if holders.size == 0:  # pragma: no cover - one colour holds everything
        return 0
    start = int(holders[rng.integers(holders.size)])
    component = {start}
    frontier = [start]
    while frontier and len(component) < cap:
        p = frontier.pop()
        for s in inc[p][inc_mask[p]]:
            for q in set_cls[s]:
                if q == nc or q in component:
                    continue
                if A[q] == a or A[q] == b:
                    component.add(q)
                    frontier.append(q)
                    if len(component) >= cap:
                        break
            if len(component) >= cap:
                break
    if len(component) < 2:
        return 0
    nodes = np.fromiter(component, dtype=np.int64, count=len(component))
    A[nodes] = np.where(A[nodes] == a, b, a)
    affected = np.unique(inc[nodes][inc_mask[nodes]])
    pad = np.zeros(nc + 1, dtype=np.int8)
    pad[:nc] = A
    members = pad[set_cls[affected]]
    valid = set_cls[affected] != nc
    for c in range(k):
        cnt[affected, c] = ((members == c) & valid).sum(axis=1)
    viol[affected] = cnt[affected, set_col[affected]] == set_need[affected]
    return len(component)


def anneal(problem: Problem, seconds: float = 60.0, seed: int = 0, lam: float = 2.0,
           noise: float = 0.05, fan: int = 1, reject: bool = False, t0: float = 1.0,
           tmin: float = 0.1, stuck: int = 200, kempe: float = 0.005,
           kempe_max: int = 64, repair_cap: int = 0, repair_seconds: float = 5.0,
           recount_every: int = 2000,
           report_every: float = 10.0) -> dict:
    """Anneal for ``seconds`` and report what the walk found.

    ``lam`` is the weight of the penalty term in the augmented cost, ``noise`` the
    probability of taking a random move instead of the best-scoring one (the WalkSAT
    escape), ``fan`` how many violated sets are considered at once — one drawn at
    random is cheap but short-sighted, and near a solution taking all of them costs
    little and picks a move that is good globally —    ``stuck`` how many steps without a
    new record before the violated sets get a penalty bump and the temperature is
    reheated, ``reject`` whether the Metropolis rule is on at all (with ``False`` a
    worsening move is always taken, and the weights are what stop the cycling),
    ``kempe`` the per-step probability of a chain swap instead of a single-class move,
    and ``repair_cap`` the size of the neighbourhood handed to a CDCL engine on every
    stall (0 disables it) — see :func:`repair` for why that move can only lower the
    count.

    ``status`` follows :func:`oplab.gputabu.tabu`: ``sat`` only with a verified
    colouring, ``best-effort`` otherwise.
    """
    g = problem
    k, nc, S = int(g.k), int(g.nc), int(g.n_sets)
    set_cls, set_need, set_col = g.set_cls, g.set_need, g.set_col
    inc, inc_mask = g.inc, g.inc_mask
    deg = inc.shape[1]
    rng = np.random.default_rng(int(seed))
    colours = np.arange(k)
    all_sets = np.arange(S)

    def recount(A):
        """The whole state from an assignment — the ground truth for the delta."""
        pad = np.zeros(nc + 1, dtype=np.int8)
        pad[:nc] = A
        members = pad[set_cls]
        valid = set_cls != nc
        cnt = np.zeros((S, k), dtype=np.int8)
        for c in range(k):
            cnt[:, c] = ((members == c) & valid).sum(axis=1)
        viol = cnt[all_sets, set_col] == set_need
        return cnt, viol

    A = rng.integers(0, k, size=nc).astype(np.int8)
    cnt, viol = recount(A)
    total = int(viol.sum())
    weight = np.zeros(S, dtype=np.int32)
    record = total

    steps = drift = kempe_steps = repairs = repairs_solved = repairs_timeout = 0
    found = None
    history = []
    started = time.time()
    next_report = report_every
    since = 0

    def temperature(since_steps):
        """Geometric from ``t0`` to ``tmin`` across ``stuck`` steps, reheated on a bump."""
        if not reject:
            return math.inf
        frac = min(1.0, since_steps / max(1, stuck))
        return max(tmin, t0 * (tmin / t0) ** frac)

    while True:
        elapsed = time.time() - started
        if elapsed >= seconds:
            break
        if elapsed >= next_report:
            history.append({"t": round(elapsed, 1), "best": int(record),
                            "steps": steps, "violations": int(total)})
            next_report += report_every

        if kempe and rng.random() < kempe:
            if _kempe_swap(A, cnt, viol, inc, inc_mask, set_cls, set_col, set_need,
                           nc, k, rng, kempe_max):
                steps += 1
                kempe_steps += 1
                total = int(viol.sum())
                if total < record:
                    record, since = total, 0
                else:
                    since += 1
                if total == 0:
                    found = A.copy()
                    break
                continue

        # -- the sets to attack: up to ``fan`` violators, drawn at random.  One set is
        # cheap but myopic; near a solution there are only a handful left, so taking all
        # of them buys a global choice for very little.
        bad = np.flatnonzero(viol)
        if bad.size == 0:
            found = A.copy()
            break
        chosen = (bad if fan >= bad.size
                  else bad[rng.choice(bad.size, size=fan, replace=False)])
        members = np.unique(set_cls[chosen][set_cls[chosen] != nc])
        if members.size == 0:  # pragma: no cover - a set with no class is not a clause
            break

        # -- every (member, other colour) move of those sets, at once
        ids = inc[members].astype(np.int64)                  # (w, deg)
        msk = inc_mask[members]
        old = A[members].astype(np.int64)                    # (w,)
        col_s = set_col[ids].astype(np.int64)
        need_s = set_need[ids].astype(np.int64)
        # a class never appears twice in a stored set: the encoder dedupes the class
        # multiset of a clique, so an isoceles triangle of `Z_17` is the two-element set
        # {d, 2d} and ``set_need`` is the number of *distinct* classes.  That is why one
        # recolour moves a count by exactly one, and the test pins the invariant.
        cnt_old = cnt[ids, old[:, None]].astype(np.int64)    # (w, deg)
        lost = msk & (col_s == old[:, None]) & (cnt_old == need_s)
        n_lost = lost.sum(axis=1)
        w_lost = np.where(lost, weight[ids], 0).sum(axis=1)
        cnt_c = cnt[ids].astype(np.int64)                    # (w, deg, k)
        gain = (msk[..., None] & (col_s[..., None] == colours)
                & (cnt_c + 1 == need_s[..., None]))
        n_gain = gain.sum(axis=1)                            # (w, k)
        w_gain = np.where(gain, weight[ids][..., None], 0).sum(axis=1)
        delta = (n_gain - n_lost[:, None]) + lam * (w_gain - w_lost[:, None])
        delta[np.arange(members.size), old] = np.inf         # the colour it already has
        flat = int(np.argmin(delta))
        j, new = divmod(flat, k)
        if delta[j, new] == np.inf:  # pragma: no cover - k == 1 has no move at all
            steps += 1
            continue
        if rng.random() < noise:
            j = int(rng.integers(members.size))
            choices = colours[colours != old[j]]
            new = int(choices[rng.integers(choices.size)])
        d = float(delta[j, new])

        steps += 1
        if reject and d > 0 and rng.random() >= math.exp(-d / temperature(since)):
            since += 1
        else:
            p = int(members[j])
            touched = inc[p][inc_mask[p]]
            cnt[touched, old[j]] -= 1
            cnt[touched, new] += 1
            A[p] = new
            viol[touched] = cnt[touched, set_col[touched]] == set_need[touched]
            total += int(n_gain[j, new]) - int(n_lost[j])
            if total < record:
                record, since = total, 0
            else:
                since += 1
            if total == 0:
                found = A.copy()
                break

        # -- guided local search: a stall costs the sets that caused it, and the same
        # clock reheats the temperature.  A stall is also when a big coordinated move
        # is worth paying for: hand the neighbourhood to an engine.
        if since and since % stuck == 0:
            weight[np.flatnonzero(viol)] += 1
            since = 0
            if repair_cap:
                outcome = repair(g, A, viol, rng, cap=repair_cap,
                                 seconds=repair_seconds)
                repairs += 1
                if outcome["timeout"]:
                    repairs_timeout += 1
                if outcome["solved"]:
                    repairs_solved += 1
                    # exact inside the neighbourhood, so this is a recount and not an
                    # arithmetic step that could drift
                    cnt, viol = recount(A)
                    total = int(viol.sum())
                    if total < record:
                        record, since = total, 0
                    if total == 0:
                        found = A.copy()
                        break

        # -- the delta is a claim; check it rather than trust it
        if recount_every and steps % recount_every == 0:
            truth_cnt, truth_viol = recount(A)
            drift += int((truth_viol != viol).sum())
            cnt, viol = truth_cnt, truth_viol
            total = int(viol.sum())
            if total < record:
                record = total

    elapsed = time.time() - started
    report = {
        "n": g.n, "sizes": list(g.sizes), "classes": nc, "class_sets": S,
        "steps": steps, "seconds": round(elapsed, 3),
        "steps_per_second": round(steps / elapsed, 1) if elapsed else None,
        "violations": int(record), "history": history, "seed": int(seed),
        "search_only": True, "recount_drift": drift, "kempe_steps": kempe_steps,
        "repairs": repairs, "repairs_solved": repairs_solved, "repair_cap": repair_cap,
        "repairs_timeout": repairs_timeout, "repair_seconds": repair_seconds,
        "lam": lam, "noise": noise, "reject": reject, "t0": t0, "kempe": kempe,
        "fan": fan, "stuck": stuck,
        "what": (f"guided annealing over {g.describe()} — a search, not a decision: "
                 f"'best-effort' says nothing about whether the family is empty"),
    }
    if found is None:
        report["status"] = "best-effort"
        return report
    colouring = g.serialize(found)
    verify = MC.verify_colouring(g.n, g.sizes, colouring)
    report.update({"coloring": colouring, "verify": verify, "violations": 0})
    if verify.get("valid"):
        report["status"] = "sat"
        report["establishes"] = (f"R{tuple(g.sizes)} > {g.n}, witness found by "
                                 f"guided annealing")
    else:
        report["status"] = "sat-invalid"
        report["note"] = ("the walk reached zero but the verifier disagrees: a bug in "
                          "this module, not a result")
    return report


# --------------------------------------------------------------------------
# partial colourings: a class may be blank, so the plateau can dissolve
# --------------------------------------------------------------------------
#: What a blank class is in the assignment array.  Not a colour: no set counts it, so a
#: set with a blank class is never monochromatic.
BLANK = -1


def _counts(problem: Problem, A):
    """``cnt`` and the violated mask of a *partial* assignment; ``-1`` means blank.

    The complete-colouring counter treats every entry as a colour, so a blank would be
    read as colour ``-1`` and quietly join the count of whichever class is indexed last.
    Here the blank classes are masked out of every set they touch, which is exactly the
    property the search exploits: an uncoloured class cannot make a set monochromatic.
    """
    g = problem
    coloured = np.zeros(g.nc + 1, dtype=bool)  # index g.nc is the padding slot
    coloured[:g.nc] = A >= 0
    pad = np.zeros(g.nc + 1, dtype=np.int8)
    pad[:g.nc] = np.where(A >= 0, A, 0)
    members = pad[g.set_cls]
    valid = coloured[g.set_cls]
    cnt = np.zeros((g.n_sets, g.k), dtype=np.int8)
    for c in range(g.k):
        cnt[:, c] = ((members == c) & valid).sum(axis=1)
    viol = cnt[np.arange(g.n_sets), g.set_col] == g.set_need
    return cnt, viol


def partial(problem: Problem, seconds: float = 60.0, seed: int = 0,
            blank_weight: float = 1.0, noise: float = 0.05,
            repair_seconds: float = 5.0, attempt_every: int = 2000,
            report_every: float = 10.0) -> dict:
    """Search partial colourings — a class may be **blank** — and re-insert them.

    Both searches before this one stall two or three cliques from a witness, and
    :func:`repair` measured why: there the violated classes have a one-hop neighbourhood
    of 159 classes of 190, so the neighbourhood that could fix them is the instance.
    Blanking changes the question instead of the neighbourhood.  An uncoloured class
    makes every set it belongs to non-monochromatic, so the walk can *dissolve* a
    violation it cannot satisfy, and hand the blank classes to the engine to be put back.

    The objective is one scalar, ``violations + blank_weight * blanks``, and it is
    minimised by min-conflicts: a violated set is attacked by recolouring one of its
    classes **or blanking it**, whichever is cheaper, and when no violation is left the
    walk tries to refill a random blank class, accepting the refill only when it costs
    nothing or by chance ``exp(-cost)``.  A witness is the global optimum, so the search
    can be run for as long as its budget allows without a separate stopping rule.

    Every ``attempt_every`` steps at zero violations, the blank classes go to
    :func:`repair`.  ``support`` in the report is the blank count at which that finally
    succeeded, ``refused`` the blank counts at which the engine said unsatisfiable, and
    ``min_blanks`` the fewest blanks the walk ever stood at with no violations — a lower
    bound on the support if nothing succeeded.

    ``status`` is ``"sat"`` only for a complete colouring the verifier accepts,
    ``"partial"`` for zero violations with classes still blank, and ``"best-effort"`` for
    violations left.  A partial state is **not** a colouring and the report says so by
    name: nothing here is evidence that the family is empty.
    """
    g = problem
    k, nc = int(g.k), int(g.nc)
    set_cls, set_need, set_col = g.set_cls, g.set_need, g.set_col
    inc, inc_mask = g.inc, g.inc_mask
    rng = np.random.default_rng(int(seed))

    A = rng.integers(0, k, size=nc).astype(np.int8)
    cnt, viol = _counts(g, A)

    def delta(p, target):
        """(violations, blanks) change when class ``p`` is set to ``target``."""
        touch = inc[p][inc_mask[p]]
        old = int(A[p])
        col_s = set_col[touch]
        need_s = set_need[touch]
        was = 0
        if old >= 0:
            was = int(((col_s == old) & (cnt[touch, old] == need_s)).sum())
        now = 0
        if target >= 0 and target != old:
            now = int(((col_s == target) & (cnt[touch, target] + 1 == need_s)).sum())
        return now - was, int(target < 0) - int(old < 0)

    def apply(p, target):
        old = int(A[p])
        touch = inc[p][inc_mask[p]]
        if old >= 0:
            cnt[touch, old] -= 1
        if target >= 0:
            cnt[touch, target] += 1
        A[p] = target
        viol[touch] = cnt[touch, set_col[touch]] == set_need[touch]

    def cheapest(p, targets):
        """The target with the lowest cost, or ``None`` when every target is excluded."""
        best = None
        for target in targets:
            if target == int(A[p]):
                continue
            dv, db = delta(int(p), target)
            score = dv + blank_weight * db
            if best is None or score < best[0]:
                best = (score, target)
        return best

    targets = list(range(k)) + [BLANK]  # every move a class can be given
    colours = list(range(k))
    steps = repairs = 0
    attempts: list[dict] = []
    refused: list[int] = []
    engines: list[str] = []
    history = []
    support = None
    min_blanks = None
    next_attempt = attempt_every
    started = time.time()
    next_report = report_every
    complete = False

    while True:
        now = time.time()
        elapsed = now - started
        if elapsed >= seconds:
            break
        if elapsed >= next_report:
            history.append({"t": round(elapsed, 1), "steps": steps,
                            "violations": int(viol.sum()), "blanks": int((A < 0).sum())})
            next_report += report_every
        if steps >= next_attempt:
            next_attempt = steps + attempt_every
            blanks_now = np.flatnonzero(A < 0)
            if blanks_now.size and not viol.any():
                min_blanks = int(blanks_now.size) if min_blanks is None else \
                    min(min_blanks, int(blanks_now.size))
                outcome = repair(g, A, viol, rng, free=blanks_now,
                                 seconds=min(repair_seconds, max(0.1, seconds - elapsed)))
                repairs += 1
                if outcome.get("engine"):
                    engines.append(outcome["engine"])
                verdict = "sat" if outcome["solved"] else (
                    "no-engine" if outcome.get("note", "").startswith("no engine")
                    else "timeout" if outcome.get("timeout") else "unsat")
                attempts.append({"steps": steps, "blanks": int(blanks_now.size),
                                 "verdict": verdict,
                                 "seconds": round(outcome["seconds"], 3)})
                if outcome["solved"]:
                    support = int(blanks_now.size)
                    cnt, viol = _counts(g, A)  # recount rather than trust the hand-off
                    break
                if verdict == "unsat":
                    refused.append(int(blanks_now.size))
                if verdict == "no-engine":
                    break
                cnt, viol = _counts(g, A)
        bad = np.flatnonzero(viol)
        if bad.size:
            s = int(bad[rng.integers(bad.size)])
            members = set_cls[s][set_cls[s] != g.nc]
            if rng.random() < noise:
                p = int(members[rng.integers(members.size)])
                options = [t for t in targets if t != int(A[p])]
                apply(p, options[int(rng.integers(len(options)))])
            else:
                # the cheapest move anywhere in the set, not only on one member
                best = None
                for p in members:
                    candidate = cheapest(int(p), targets)
                    if candidate is not None and (best is None or candidate[0] < best[0]):
                        best = (candidate[0], int(p), candidate[1])
                if best is None:  # pragma: no cover - k == 1 leaves no move at all
                    break
                apply(best[1], best[2])
        else:
            blanks = np.flatnonzero(A < 0)
            if blanks.size == 0:
                complete = True
                break
            min_blanks = int(blanks.size) if min_blanks is None else \
                min(min_blanks, int(blanks.size))
            p = int(blanks[rng.integers(blanks.size)])
            pick = cheapest(p, colours)
            if pick is None:  # pragma: no cover - a single colour leaves nothing to try
                break
            if pick[0] <= 0 or rng.random() < math.exp(-pick[0]):
                apply(p, pick[1])
        steps += 1

    elapsed = time.time() - started
    blanks = np.flatnonzero(A < 0)
    report = {
        "n": g.n, "sizes": list(g.sizes), "classes": nc, "class_sets": g.n_sets,
        "steps": steps, "seconds": round(elapsed, 3),
        "steps_per_second": round(steps / elapsed, 1) if elapsed else None,
        "violations": int(viol.sum()), "blanks": int(blanks.size), "repairs": repairs,
        "support": support, "refused": sorted(set(refused)),
        # the state itself, so a run can be resumed or grown without re-walking it;
        # ``-1`` is a blank class, and a partial state is not a colouring
        "assignment": [int(x) for x in A], "blanks_at": [int(p) for p in blanks],
        "min_blanks": min_blanks,
        "attempts": attempts, "engines": sorted(set(engines)), "history": history,
        "seed": int(seed), "blank_weight": blank_weight, "noise": noise,
        "search_only": True,
        "what": (f"partial-colouring search over {g.describe()} — 'partial' is not a "
                 f"colouring and says nothing about whether the family is empty"),
    }
    if complete and not viol.any():
        colouring = g.serialize(A)
        verify = MC.verify_colouring(g.n, g.sizes, colouring)
        report.update({"coloring": colouring, "verify": verify})
        if verify.get("valid"):
            report["status"] = "sat"
            report["establishes"] = (f"R{tuple(g.sizes)} > {g.n}, witness found by the "
                                     f"partial-colouring search")
        else:
            report["status"] = "sat-invalid"
            report["note"] = ("the walk ended complete but the verifier disagrees: a bug "
                              "in this module, not a result")
        return report
    report["status"] = "partial" if not viol.any() else "best-effort"
    if report["status"] == "partial":
        report["note"] = (f"{int(blanks.size)} classes left blank with no violations: "
                          f"the engine did not re-insert them")
    return report
