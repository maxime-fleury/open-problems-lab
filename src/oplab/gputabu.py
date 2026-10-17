"""GPU tabu search over the same instances the SAT encoding decides.

The SAT campaign in :mod:`oplab.blocks` answers "does this family contain a clean
colouring" with a *decision* procedure: CDCL, which is sequential by nature and
gains nothing from a GPU (measured, see ``docs/methodology.md``).  The other half of
the problem is not a decision but a search — produce one clean colouring — and that
half is arithmetic on a big array: count, for a whole population of skeletons at
once, how many forbidden cliques are monochromatic, and flip the class that fixes
the most of them.  A modern card does that counting twenty to thirty times faster
than vectorised numpy and, more to the point, holds thousands of skeletons in flight
rather than sixteen.

This module is deliberately *not* a solver.  It never claims a refutation: a search
that ends with violations left has learned nothing about the family, and the report
says ``best-effort`` with the number it reached.  A search that reaches zero is only
half a claim — the class assignment is expanded to a colouring of ``K_n`` and handed
to :func:`oplab.multicolour.verify_colouring`, which re-counts it from scratch.  A
witness that fails that check is a bug in this file, and is reported as
``sat-invalid`` rather than as a result.

The walk is TABUCOL in a batched form: pick a violated class set, try every
(class, other colour) move out of it, take the one with the best immediate drop in
violations, forbid restoring the old colour for a short tenure.  Thousands of
independent skeletons run side by side, each with its own tabu list, and a skeleton
that stops improving is restarted from a random skin.  All state lives on the device
as dense arrays, and the step is incremental: the violation count moves by the delta
of the move just applied, and the next set to attack is one the move touched.

Geometry of the arrays, for a reader checking the index arithmetic::

    A       (W, nc)   int8   class -> colour, one row per walk
    cnt     (W, S, k) int8   how many classes of set s carry colour c
    set_cls (S, wmax) int32  the class indices of set s, padded with nc
    set_need(S,)      int32  |set s| — violated when cnt[s, own colour] == need
    set_col (S,)      int32  the colour whose clique size this set forbids
    inc     (nc, deg) int32  the sets a class belongs to
    inc_mask(nc, deg) bool   the padding of ``inc``

A set is violated when every class in it carries the colour it forbids, which is
exactly the clause of the CNF: the same instance, counted instead of proved.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np

from . import blocks as B
from . import multicolour as MC

__all__ = ["available", "Problem", "from_blocks", "from_general", "tabu", "describe_device"]


# --------------------------------------------------------------------------
# the device, when there is one
# --------------------------------------------------------------------------
def _torch():
    """torch, or a refusal that says what to install."""
    try:
        import torch  # noqa: PLC0415 - optional dependency, imported on use
    except Exception as exc:  # pragma: no cover - depends on the machine
        raise RuntimeError(
            "the GPU tabu search needs torch with CUDA "
            "(pip install torch --index-url https://download.pytorch.org/whl/cu124); "
            "every other command in this package works without it"
        ) from exc
    return torch


def available() -> bool:
    """Whether a CUDA device is usable right now."""
    try:
        import torch  # noqa: PLC0415
    except Exception:  # pragma: no cover - the common case off-GPU
        return False
    return bool(torch.cuda.is_available())


def describe_device() -> dict:
    """What :func:`tabu` would run on, in the shape the other reports use."""
    if not available():
        return {"available": False}
    torch = _torch()
    return {"available": True, "name": torch.cuda.get_device_name(0),
            "memory_mib": torch.cuda.get_device_properties(0).total_memory // (1 << 20),
            "torch": torch.__version__, "cuda": torch.version.cuda}


# --------------------------------------------------------------------------
# the instance, in the shape the batched walk wants
# --------------------------------------------------------------------------
@dataclass
class Problem:
    """A colouring instance as class sets: one clause per (colour, class set)."""

    n: int
    sizes: tuple
    k: int
    nc: int
    set_cls: np.ndarray
    set_need: np.ndarray
    set_col: np.ndarray
    inc: np.ndarray
    inc_mask: np.ndarray
    edges_of: dict

    @property
    def n_sets(self) -> int:
        return len(self.set_need)

    def describe(self) -> str:
        return (f"K_{self.n} {list(self.sizes)}: {self.nc} classes, "
                f"{self.n_sets} class sets")

    # -- expansion ---------------------------------------------------------
    def expand(self, assignment) -> np.ndarray:
        """The colouring of ``K_n`` a class assignment stands for."""
        assignment = np.asarray(assignment, dtype=np.int8)
        if assignment.shape != (self.nc,):
            raise ValueError(f"expected {self.nc} class colours, got {assignment.shape}")
        colouring = np.zeros((self.n, self.n), dtype=np.int8)
        for p, colour in enumerate(assignment):
            if not 0 <= colour < self.k:
                raise ValueError(f"class {p} carries colour {colour}, which is not one "
                                 f"of the {self.k}")
            for u, v in self.edges_of[p]:
                colouring[u, v] = colouring[v, u] = colour
        return colouring

    def serialize(self, assignment) -> str:
        return MC.serialize_colouring(self.expand(assignment), self.n)

    # -- the count, on the host, without the incremental state --------------
    def violations_host(self, assignment) -> int:
        """Monochromatic forbidden cliques, recomputed from the assignment.

        Independent of the device's incremental ``cnt``: it re-derives every set from
        the class colours, so a disagreement with :func:`tabu` is a bug in one of
        them.  It is also the check the tests use on instances small enough to
        enumerate.
        """
        assignment = np.asarray(assignment)
        total = 0
        for s in range(self.n_sets):
            colour = int(self.set_col[s])
            group = self.set_cls[s]
            if all(int(assignment[p]) == colour for p in group if p != self.nc):
                total += 1
        return total


def _pack(n, sizes, per_colour_sets, nc, edges_of) -> Problem:
    """Flatten per-colour class-set lists into the arrays the walk indexes."""
    sizes = tuple(sizes)
    k = len(sizes)
    width = max((len(g) for tables in per_colour_sets for g in tables), default=1)
    total = sum(len(t) for t in per_colour_sets)
    set_cls = np.full((total, width), nc, dtype=np.int32)
    set_need = np.zeros(total, dtype=np.int32)
    set_col = np.zeros(total, dtype=np.int32)
    offset = 0
    for colour, tables in enumerate(per_colour_sets):
        for i, group in enumerate(tables):
            set_cls[offset + i, :len(group)] = group
            set_need[offset + i] = len(group)
            set_col[offset + i] = colour
        offset += len(tables)
    degrees = np.zeros(nc, dtype=np.int64)
    for s in range(total):
        for p in set_cls[s]:
            if p != nc:
                degrees[p] += 1
    deg = int(degrees.max()) if nc else 0
    inc = np.zeros((nc, deg), dtype=np.int32)
    inc_mask = np.zeros((nc, deg), dtype=bool)
    fill = np.zeros(nc, dtype=np.int64)
    for s in range(total):
        for p in set_cls[s]:
            if p == nc:
                continue
            inc[p, fill[p]] = s
            inc_mask[p, fill[p]] = True
            fill[p] += 1
    return Problem(n=int(n), sizes=sizes, k=k, nc=int(nc), set_cls=set_cls,
                   set_need=set_need, set_col=set_col, inc=inc, inc_mask=inc_mask,
                   edges_of=edges_of)


def from_blocks(instance: B.BlockInstance) -> Problem:
    """The block-Cayley family as a :class:`Problem` — the same clauses as the CNF."""
    per_colour = []
    for s in instance.sizes:
        per_colour.append([tuple(instance._index[key] for key in group)
                           for group in instance.sets[s]])
    edges_of = {i: instance.edges_of[key] for i, key in enumerate(instance.classes)}
    return _pack(instance.n, instance.sizes, per_colour, len(instance.classes), edges_of)


def from_general(n: int, sizes) -> Problem:
    """Every colouring of ``K_n``: classes are edges, class sets are the cliques.

    The unrestricted instance, included because a search that cannot find a witness
    inside a family should be asked the same question without the family — and because
    the published witnesses at ``K29``/``K44`` are the calibration: if the walk cannot
    rediscover a colouring known to exist, a negative at ``K51`` means nothing.
    """
    import itertools

    sizes = tuple(sorted(int(s) for s in sizes))
    edges = [(i, j) for i in range(n) for j in range(i + 1, n)]
    index = {e: t for t, e in enumerate(edges)}
    per_colour = []
    for s in sizes:
        per_colour.append([tuple(index[e] for e in itertools.combinations(vertices, 2))
                           for vertices in itertools.combinations(range(n), s)])
    edges_of = {t: [e] for t, e in enumerate(edges)}
    return _pack(n, sizes, per_colour, len(edges), edges_of)


# --------------------------------------------------------------------------
# the walk
# --------------------------------------------------------------------------
def tabu(problem: Problem, seconds: float = 60.0, walks: int = 4096, seed: int = 0,
         tenure: int = 12, stale: int = 4000, device: str | None = None,
         report_every: float = 30.0, recount_every: int = 2000,
         pick_every: int = 0) -> dict:
    """Run batched tabu for ``seconds`` and report what the walks found.

    ``status`` is ``"sat"`` only when a walk reached zero violations **and** the
    expanded colouring survived :func:`oplab.multicolour.verify_colouring`;
    ``"sat-invalid"`` if a walk claimed zero and the verifier disagreed (a bug in this
    file, never a result); ``"best-effort"`` otherwise, with ``violations`` the
    smallest count any walk reached.  ``"best-effort"`` says nothing about whether a
    clean member exists — it is a statement about this walk, not about the family.

    The step is *incremental*, and that is what makes the population affordable: the
    violation count moves by the delta of the move just applied instead of being
    recounted, and the next set to attack is chosen from the sets the move touched
    rather than from all ``S`` of them.  A recount is still done every
    ``recount_every`` steps and any disagreement is reported in ``recount_drift`` —
    an incremental counter that silently drifts would make the whole search a
    fiction, so the drift is a measured quantity and the tests demand it be zero.
    """
    torch = _torch()
    if device is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
    dev = torch.device(device)
    gen = torch.Generator(device=dev).manual_seed(int(seed))
    g = problem
    W, S, k, nc = int(walks), g.n_sets, g.k, g.nc

    set_cls = torch.as_tensor(g.set_cls, device=dev)      # (S, wmax)
    set_need = torch.as_tensor(g.set_need, device=dev)    # (S,)
    set_col = torch.as_tensor(g.set_col, device=dev)      # (S,)
    inc = torch.as_tensor(g.inc, device=dev)              # (nc, deg)
    inc_mask = torch.as_tensor(g.inc_mask, device=dev)    # (nc, deg)
    width, deg = set_cls.shape[1], inc.shape[1]
    need_view = set_need.view(1, S)
    col_view = set_col.view(1, S, 1)
    # int8 copies, so that a comparison against the counts does not promote the whole
    # (W, width, deg, k) block to int32 twice per step
    need8 = set_need.to(torch.int8)
    col8 = set_col.to(torch.int8)
    colours = torch.arange(k, device=dev).view(1, 1, k)
    jitter = torch.empty((W, width * k), device=dev)

    def random_skins(rows):
        # ``nc`` colours plus one sentinel column: a class set shorter than ``wmax`` is
        # padded with the index ``nc``, so ``A[:, set_cls]`` has to be in bounds for it.
        # Without the extra column the gather reads one past the row — which is silent
        # for every row but the last, and a device-side assert for that one.
        skins = torch.randint(0, k, (rows, nc + 1), generator=gen, device=dev,
                              dtype=torch.int8)
        skins[:, nc] = 0
        return skins

    def counts_of(A, rows=None):
        """(rows, S, k) counts of each colour inside each set."""
        sub = A if rows is None else A[rows]
        members = sub[:, set_cls]
        valid = set_cls != nc
        out = torch.zeros((sub.shape[0], S, k), dtype=torch.int8, device=dev)
        for c in range(k):
            out[..., c] = ((members == c) & valid).sum(dim=2).to(torch.int8)
        return out

    def violated_full(A, rows=None):
        """Per-walk violation counts from scratch — the ground truth for the delta."""
        sub = A if rows is None else A[rows]
        members = sub[:, set_cls]
        valid = set_cls != nc
        own = ((members == set_col.view(1, S, 1)) & valid).sum(dim=2)
        return (own == need_view).sum(dim=1).to(torch.int32)

    def attackable(cnt_, ids):
        """Which of ``ids`` are violated right now: a set is violated when all of its
        classes carry the colour it forbids, that is when ``own == need``."""
        kk = ids.shape[1]
        cnt_i = cnt_.gather(1, ids.unsqueeze(-1).expand(ids.shape[0], kk, k))
        own = cnt_i.gather(2, set_col[ids].long().unsqueeze(-1)).squeeze(2)
        return own == set_need[ids]

    def pick_violated(cnt_, rows):
        """One violated set per row, uniformly, by a full scan (the rare path)."""
        sub = cnt_[rows]
        n_rows = sub.shape[0]
        own = sub.gather(2, col_view.expand(n_rows, S, 1)).squeeze(2)
        bad = own == need_view
        return torch.where(bad, torch.rand(n_rows, S, generator=gen, device=dev),
                           torch.full((n_rows, S), -1.0, device=dev)).argmax(dim=1)

    A = random_skins(W)
    cnt = counts_of(A)
    violations = violated_full(A)
    best = violations.clone()
    # a never-reset record: ``best`` is per walk and is reset when that walk restarts,
    # so the minimum over live walks can rise after a restart.  Reporting that as the
    # run's best would understate it — and, worse, would hide a witness found earlier.
    record = violations.min().clone()
    since = torch.zeros(W, dtype=torch.int32, device=dev)
    tabu_until = torch.zeros((W, nc, k), dtype=torch.int32, device=dev)
    big = torch.tensor(1 << 20, dtype=torch.int32, device=dev)
    walk_idx = torch.arange(W, device=dev)

    # the pool is the set of class sets the last move touched.  Seed it with the sets
    # of one randomly chosen violated set per walk, so every walk has somewhere to go.
    seed_set = pick_violated(cnt, walk_idx)
    first = set_cls[seed_set][:, 0].clamp(max=nc - 1)
    pool = inc.index_select(0, first)                          # (W, deg)
    pool_ok = inc_mask.index_select(0, first)

    steps = flips = drift = 0
    found = None
    history = []
    started = time.time()
    next_report = report_every
    while True:
        elapsed = time.time() - started
        if elapsed >= seconds:
            break
        if elapsed >= next_report:
            history.append({"t": round(elapsed, 1), "best": int(record),
                            "steps": steps, "flips": flips})
            next_report += report_every

        # -- the set to attack: a violated one the last move touched, with a periodic
        # refresh from all of them, so the walk is not locked into one neighbourhood
        if pick_every and steps % pick_every == 0:
            start = set_cls[pick_violated(cnt, walk_idx)][:, 0].clamp(max=nc - 1)
            pool = inc.index_select(0, start)
            pool_ok = inc_mask.index_select(0, start)
        live = attackable(cnt, pool) & pool_ok
        no_pool = ~live.any(dim=1)
        # one device sync per step instead of three: the three conditions that need a
        # host branch are reduced together, and only the one that fired is acted on
        fire = no_pool.any() | (best == 0).any() | (since >= stale).any()
        if bool(fire):
            if bool(no_pool.any()):
                rows = torch.nonzero(no_pool).squeeze(1)
                start = set_cls[pick_violated(cnt, rows)][:, 0].clamp(max=nc - 1)
                pool[rows] = inc.index_select(0, start)
                pool_ok[rows] = inc_mask.index_select(0, start)
                live = attackable(cnt, pool) & pool_ok

        score = torch.where(live, torch.rand(W, deg, generator=gen, device=dev),
                            torch.full((W, deg), -1.0, device=dev))
        chosen = pool.gather(1, score.argmax(dim=1).unsqueeze(1)).squeeze(1)   # (W,)
        members = set_cls[chosen]                                # (W, wmax)
        step_no = torch.tensor(steps, dtype=torch.int32, device=dev)

        # -- every (member, other colour) move in one block: the moves of all wmax
        # members of the chosen set are independent until the argmin, so computing
        # them together is what keeps the step to a few dozen kernels instead of
        # two hundred (the launches, not the arithmetic, were the bottleneck)
        p_all = members.clamp(max=nc - 1)                        # (W, width)
        alive = members != nc                                    # (W, width)
        ids = inc.index_select(0, p_all.reshape(-1)).view(W, width, deg)
        mask = inc_mask.index_select(0, p_all.reshape(-1)).view(W, width, deg)
        need_i = need8[ids.reshape(-1)].view(W, width, deg)
        col_i = col8[ids.reshape(-1)].view(W, width, deg)
        cnt_i = cnt.gather(1, ids.reshape(W, -1).unsqueeze(-1).expand(W, width * deg, k)) \
                   .view(W, width, deg, k)                       # (W, width, deg, k)
        old = A.gather(1, p_all)                                 # (W, width)
        old_i = cnt_i.gather(3, old.long().view(W, width, 1, 1).expand(W, width, deg, 1)) \
                       .squeeze(3)                               # (W, width, deg)
        left = ((old_i == need_i) & mask & (col_i == old.to(torch.int8).unsqueeze(-1))) \
            .sum(dim=2).to(torch.int32)                          # (W, width)
        gain = ((cnt_i == (need_i.unsqueeze(-1) - 1))
                & mask.unsqueeze(-1) & (col_i.unsqueeze(-1) == colours)) \
            .sum(dim=2).to(torch.int32)                          # (W, width, k)
        delta = gain - left.unsqueeze(-1)                        # (W, width, k)
        tabu_col = tabu_until.gather(1, p_all.long().unsqueeze(-1).expand(W, width, k))
        forbidden = tabu_col > step_no.view(1, 1, 1)
        # aspiration: a tabu move that clears the walk's last violations counts
        allowed = ~(forbidden & (delta + violations.view(W, 1, 1) > 0))
        other = old.long().unsqueeze(-1) != colours.long()
        legal = alive.unsqueeze(-1) & allowed & other
        # a walk can have every move tabu (with two colours there is only one choice), and
        # then it must still move: fall back to the best non-tabu-checked one.  Taking a
        # delta from a move that was *not* applied is how the counter would drift.
        loose = (alive.unsqueeze(-1) & other).reshape(W, -1)
        strict = legal.reshape(W, -1)
        usable = torch.where(strict.any(dim=1, keepdim=True), strict, loose)
        scored = torch.where(usable, delta.reshape(W, -1), big)
        # a random tie-break, so that equal deltas do not always pick member 0
        scored = scored.to(torch.float32) + jitter.uniform_(generator=gen) * 1e-3
        flat = scored.argmin(dim=1)
        best_j, best_c = torch.div(flat, k, rounding_mode="floor"), flat % k
        best_delta = delta.reshape(W, -1).gather(1, flat.unsqueeze(1)).squeeze(1)
        best_p = p_all.gather(1, best_j.unsqueeze(1)).squeeze(1)

        # -- apply the move, and take the touched sets as the next pool
        ids = inc.index_select(0, best_p)                         # (W, deg)
        mask = inc_mask.index_select(0, best_p)
        old = A.gather(1, best_p.unsqueeze(1)).squeeze(1)
        new = best_c
        delta_cnt = torch.zeros((W, deg, k), dtype=torch.int8, device=dev)
        lost = mask & (set_col[ids] == old.view(W, 1))
        gained = mask & (set_col[ids] == new.view(W, 1))
        delta_cnt.scatter_add_(2, old.long().view(W, 1, 1).expand(W, deg, 1),
                               -lost.to(torch.int8).unsqueeze(2))
        delta_cnt.scatter_add_(2, new.long().view(W, 1, 1).expand(W, deg, 1),
                               gained.to(torch.int8).unsqueeze(2))
        flat_idx = (walk_idx.view(W, 1, 1) * (S * k)
                    + ids.unsqueeze(2) * k + torch.arange(k, device=dev))
        cnt.view(-1).index_add_(0, flat_idx.reshape(-1), delta_cnt.reshape(-1))
        A = A.scatter(1, best_p.unsqueeze(1), new.unsqueeze(1).to(torch.int8))
        violations = violations + best_delta
        flips += W
        steps += 1

        # -- tenure, and the next pool starts from the set just attacked
        tabu_until.view(W, nc * k).scatter_(
            1, (best_p * k + old).view(W, 1),
            (step_no + tenure + torch.randint(0, 3, (W,), generator=gen, device=dev,
                                              dtype=torch.int32)).view(W, 1))
        pool, pool_ok = ids, mask
        pool[:, 0], pool_ok[:, 0] = chosen, True

        improved = violations < best
        best = torch.where(improved, violations, best)
        since = torch.where(improved, torch.zeros_like(since), since + 1)
        record = torch.minimum(record, violations.min())
        if bool((best == 0).any()):
            row = int(torch.nonzero(best == 0)[0][0])
            found = A[row][:nc].to("cpu").numpy().astype(np.int8)
            break

        # -- the incremental counter is a claim; check it rather than trust it
        if recount_every and steps % recount_every == 0:
            truth = violated_full(A)
            drift += int((truth != violations).sum())
            violations = truth
            best = torch.minimum(best, truth)
        stale_rows = since >= stale
        if bool(stale_rows.any()):
            n_stale = int(stale_rows.sum())
            A[stale_rows] = random_skins(n_stale)
            fresh = A[stale_rows]
            for c in range(k):
                cnt[stale_rows, :, c] = ((fresh[:, set_cls] == c) & (set_cls != nc)) \
                    .sum(dim=2).to(torch.int8)
            tabu_until[stale_rows] = 0
            violations[stale_rows] = violated_full(A, stale_rows)
            best[stale_rows] = violations[stale_rows]
            since[stale_rows] = 0
            start = set_cls[pick_violated(cnt, stale_rows)][:, 0].clamp(max=nc - 1)
            pool[stale_rows] = inc.index_select(0, start)
            pool_ok[stale_rows] = inc_mask.index_select(0, start)

    if dev.type == "cuda":
        torch.cuda.synchronize()
    elapsed = time.time() - started
    report = {
        "n": g.n, "sizes": list(g.sizes), "classes": nc, "class_sets": S,
        "walks": W, "steps": steps, "flips": flips, "seconds": round(elapsed, 3),
        "flips_per_second": round(flips / elapsed, 1) if elapsed else None,
        "violations": int(record), "history": history, "device": str(dev),
        "seed": int(seed), "tenure": tenure, "stale": stale,
        "recount_drift": drift, "search_only": True,
        "what": (f"batched tabu over {g.describe()} — a search, not a decision: "
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
        report["establishes"] = f"R{tuple(g.sizes)} > {g.n}, witness found by tabu"
    else:
        report["status"] = "sat-invalid"
        report["note"] = ("the walk reached zero but the verifier disagrees: a bug in "
                          "this module, not a result")
    return report
