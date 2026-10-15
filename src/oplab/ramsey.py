"""Ramsey colourings, with an exact monochromatic-``K5`` certificate.

Target: ``R(5,5)``.  The published bounds are ``43 <= R(5,5) <= 46``; the lower
bound has stood since Exoo (1989), who gave a 2-colouring of ``K42`` with no
monochromatic ``K5``.  A single colouring of ``K43`` with no monochromatic
``K5`` would raise the bound to 44.

A colouring is serialised as a string of ``n*(n-1)/2`` characters, one per edge
in lexicographic order (``u < v``), ``'0'`` meaning red and ``'1'`` meaning
blue.  Verification (see ``oplab.verify``) re-derives the number of
monochromatic ``K5`` from that string alone.

The search is a tabu search over edge flips.  Evaluating a flip uses the fact
that the number of monochromatic ``K5`` through an edge ``uv`` of colour ``c``
equals the number of ``K4`` inside the ``c``-coloured common neighbourhood of
``u`` and ``v``, which makes each delta evaluation cheap.
"""

from __future__ import annotations

import random
import time

import numpy as np

__all__ = [
    "edges",
    "empty_coloring",
    "random_coloring",
    "blue_masks",
    "count_mono_k5",
    "count_mono_clique",
    "find_mono_k5",
    "delta_flip",
    "tabu_search",
    "from_edges",
    "to_edges",
    "colour_of",
    "serialize",
    "parse",
    "has_clique",
    "free_differences",
    "circulant_adjacency",
    "circulant_has_mono_clique",
    "circulant_search",
]


# --------------------------------------------------------------------------
# representation
# --------------------------------------------------------------------------
def edges(n: int) -> list[tuple[int, int]]:
    """All edges of ``K_n`` in lexicographic order (``u < v``)."""
    return [(u, v) for u in range(n) for v in range(u + 1, n)]


def empty_coloring(n: int) -> list[int]:
    """All-blue colouring: ``red[u]`` has no bit set."""
    return [0] * n


def random_coloring(n: int, rng: random.Random | np.random.Generator) -> list[int]:
    """Uniform random 2-colouring of ``K_n`` as red-adjacency bitmasks."""
    red = [0] * n
    for u, v in edges(n):
        if rng.random() < 0.5:
            red[u] |= 1 << v
            red[v] |= 1 << u
    return red


def blue_masks(red: list[int], n: int) -> list[int]:
    """Complementary colouring of ``red``, as bitmasks (no self-loops)."""
    full = (1 << n) - 1
    return [full & ~red[v] & ~(1 << v) for v in range(n)]


def from_edges(n: int, red_edges) -> list[int]:
    """Build red-adjacency bitmasks from an iterable of red edges."""
    red = [0] * n
    for u, v in red_edges:
        red[u] |= 1 << v
        red[v] |= 1 << u
    return red


def to_edges(red: list[int], n: int) -> list[tuple[int, int]]:
    return [(u, v) for u, v in edges(n) if (red[u] >> v) & 1]


def colour_of(red: list[int], u: int, v: int) -> int:
    """0 if edge ``uv`` is red, 1 if blue."""
    return 0 if (red[u] >> v) & 1 else 1


def serialize(red: list[int], n: int) -> str:
    """Serialise a colouring to the canonical ``'0'``/``'1'`` string."""
    return "".join("0" if (red[u] >> v) & 1 else "1" for u, v in edges(n))


def parse(coloring: str, n: int) -> list[int]:
    """Inverse of :func:`serialize`; raises ``ValueError`` on bad input."""
    coloring = coloring.strip()
    expected = n * (n - 1) // 2
    if len(coloring) != expected:
        raise ValueError(f"colouring of K{n} must have {expected} characters, got {len(coloring)}")
    if set(coloring) - {"0", "1"}:
        raise ValueError("colouring may only contain '0' and '1'")
    red = [0] * n
    for (u, v), ch in zip(edges(n), coloring):
        if ch == "0":
            red[u] |= 1 << v
            red[v] |= 1 << u
    return red


# --------------------------------------------------------------------------
# exact counts
# --------------------------------------------------------------------------
def count_cliques(adj: list[int], mask: int, k: int) -> int:
    """Number of ``k``-cliques of ``adj`` entirely inside ``mask``."""
    if mask.bit_count() < k:
        return 0
    if k <= 1:
        return mask.bit_count()
    total = 0
    remaining = mask
    while remaining:
        v = (remaining & -remaining).bit_length() - 1
        remaining &= remaining - 1
        higher = remaining  # only vertices greater than v are still present
        total += count_cliques(adj, higher & adj[v], k - 1)
    return total


def count_mono_clique(red: list[int], n: int, k: int = 5) -> int:
    """Exact number of monochromatic ``K_k`` in the colouring.

    Each clique is counted once, at its lowest-numbered vertex, which is what the
    ``~((1 << (v + 1)) - 1)`` mask enforces.
    """
    blue = blue_masks(red, n)
    total = 0
    for adj in (red, blue):
        for v in range(n):
            total += count_cliques(adj, adj[v] & ~((1 << (v + 1)) - 1), k - 1)
    return total


def count_mono_k5(red: list[int], n: int) -> int:
    """Exact number of monochromatic ``K5`` in the colouring."""
    return count_mono_clique(red, n, 5)


def find_mono_k5(red: list[int], n: int, limit: int | None = None) -> list[tuple[int, ...]]:
    """Enumerate monochromatic ``K5`` (up to ``limit`` of them, if given)."""
    blue = blue_masks(red, n)
    found: list[tuple[int, ...]] = []

    def rec(adj: list[int], mask: int, acc: list[int], k: int) -> bool:
        """Returns True when the enumeration limit has been reached."""
        if k == 1:
            for v in _bits(mask):
                found.append(tuple(acc + [v]))
                if limit is not None and len(found) >= limit:
                    return True
            return False
        remaining = mask
        while remaining:
            v = (remaining & -remaining).bit_length() - 1
            remaining &= remaining - 1
            if rec(adj, remaining & adj[v], acc + [v], k - 1):
                return True
        return False

    for adj in (red, blue):
        for v in range(n):
            if rec(adj, adj[v] & ~((1 << (v + 1)) - 1), [v], 4):
                return found
    return found


def has_clique(adj: list[int], mask: int, k: int) -> bool:
    """True iff ``adj`` contains a ``k``-clique inside ``mask`` (early exit)."""
    if mask.bit_count() < k:
        return False
    if k <= 1:
        return mask != 0
    remaining = mask
    while remaining:
        v = (remaining & -remaining).bit_length() - 1
        remaining &= remaining - 1
        if has_clique(adj, remaining & adj[v], k - 1):
            return True
    return False


# --------------------------------------------------------------------------
# circulant (translation-invariant) colourings: a fully enumerable family
# --------------------------------------------------------------------------
def free_differences(n: int) -> list[int]:
    """Representatives of the difference pairs ``{d, n-d}`` of ``Z_n``."""
    return list(range(1, n // 2 + 1))


def circulant_adjacency(n: int, mask: int) -> list[int]:
    """Red adjacency of the circulant colouring encoded by ``mask``.

    Bit ``i`` of ``mask`` (``0 <= i < len(free_differences(n))``) selects the
    difference ``i + 1``, and with it its inverse ``n - (i + 1)``, so the
    colouring is translation invariant by construction.  The adjacency of vertex
    ``v`` is then a rotation of the difference mask, computed with big integers.
    """
    base = 0
    for i, d in enumerate(free_differences(n)):
        if (mask >> i) & 1:
            base |= 1 << d
            base |= 1 << (n - d)
    full = (1 << n) - 1
    adj = []
    for v in range(n):
        adj.append(((base << v) | (base >> (n - v))) & full)
    return adj


def circulant_has_mono_clique(n: int, mask: int, k: int) -> bool:
    """True iff the circulant colouring has a monochromatic ``K_k``.

    Translation invariance means it is enough to look for cliques *containing
    vertex 0*: a monochromatic ``K_k`` anywhere translates to one through 0.
    """
    red = circulant_adjacency(n, mask)
    full = (1 << n) - 1
    blue = [full & ~red[v] & ~(1 << v) for v in range(n)]
    return has_clique(red, red[0], k - 1) or has_clique(blue, blue[0], k - 1)


def _circulant_chunk(args) -> dict:
    n, k, first, count = args
    witnesses = []
    for mask in range(first, first + count):
        if not circulant_has_mono_clique(n, mask, k):
            witnesses.append(mask)
    return {"tested": count, "found": witnesses}


def circulant_search(n: int, k: int = 5, workers: int = 1, chunk: int = 65536, progress=None) -> dict:
    """Exhaustively test every circulant 2-colouring of ``K_n`` for a mono ``K_k``.

    The family is small enough to enumerate completely: ``2^len(free_differences(n))``
    colourings.  A colouring with no monochromatic ``K_k`` proves ``R(k,k) > n``;
    finding none proves that no *circulant* witness exists for that bound, which
    is a genuine (if narrower) negative result.
    """
    total = 1 << len(free_differences(n))
    blocks = [(n, k, first, min(chunk, total - first)) for first in range(0, total, chunk)]
    tested = 0
    found: list[int] = []
    started = time.time()
    if workers <= 1:
        for block in blocks:
            res = _circulant_chunk(block)
            tested += res["tested"]
            found.extend(res["found"])
            if progress is not None:
                progress(tested, total)
    else:
        from concurrent.futures import ProcessPoolExecutor

        with ProcessPoolExecutor(max_workers=workers) as pool:
            for res in pool.map(_circulant_chunk, blocks):
                tested += res["tested"]
                found.extend(res["found"])
                if progress is not None:
                    progress(tested, total)
    return {
        "n": n,
        "k": k,
        "colourings_tested": tested,
        "witnesses": sorted(found),
        "seconds": time.time() - started,
        "workers": workers,
    }


def _bits(mask: int):
    while mask:
        v = (mask & -mask).bit_length() - 1
        mask &= mask - 1
        yield v


def delta_flip(red: list[int], blue: list[int], u: int, v: int) -> int:
    """Change in the number of monochromatic ``K5`` caused by flipping edge ``uv``.

    A monochromatic ``K5`` through ``uv`` is ``{u, v}`` plus a triangle inside
    the ``c``-coloured common neighbourhood of ``u`` and ``v``.  Flipping ``uv``
    destroys the old colour count and creates the new one; the common
    neighbourhoods themselves are unchanged by the flip.
    """
    keep = ~((1 << u) | (1 << v))
    common_red = red[u] & red[v] & keep
    common_blue = blue[u] & blue[v] & keep
    red_triangles = count_cliques(red, common_red, 3)
    blue_triangles = count_cliques(blue, common_blue, 3)
    if (red[u] >> v) & 1:  # red -> blue
        return blue_triangles - red_triangles
    return red_triangles - blue_triangles


def flip(red: list[int], u: int, v: int) -> None:
    """Flip edge ``uv`` in place."""
    red[u] ^= 1 << v
    red[v] ^= 1 << u


# --------------------------------------------------------------------------
# search
# --------------------------------------------------------------------------
def tabu_search(
    n: int,
    seconds: float,
    seed: int = 0,
    tenure: int = 12,
    sample_cliques: int = 8,
    random_moves: int = 10,
    restart_after: int = 400,
    on_improve=None,
) -> dict:
    """Tabu search over edge flips minimising ``count_mono_k5``.

    Returns a dict with the best colouring, its exact mono-``K5`` count and some
    run statistics.  This is a *heuristic*: a non-zero best count is not a
    theorem, and a zero count only proves what the verifier re-derives.
    """
    rng = random.Random(seed)
    deadline = time.time() + seconds
    red = random_coloring(n, rng)
    blue = blue_masks(red, n)
    current = count_mono_k5(red, n)
    best_red = list(red)
    best_count = current
    tabu: dict[tuple[int, int], int] = {}
    step = 0
    since_improvement = 0
    history = [(0, best_count)]

    while time.time() < deadline:
        step += 1
        cliques = find_mono_k5(red, n, limit=2000)
        candidates: set[tuple[int, int]] = set()
        if cliques:
            k = min(sample_cliques, len(cliques))
            for cl in rng.sample(cliques, k):
                for i in range(5):
                    for j in range(i + 1, 5):
                        candidates.add((cl[i], cl[j]))
        candidate_target = min(sample_cliques * 10 + random_moves, n * (n - 1) // 2)
        while len(candidates) < candidate_target:
            u = rng.randrange(n)
            v = rng.randrange(n)
            if u != v:
                candidates.add((min(u, v), max(u, v)))

        best_move = None
        best_delta = None
        for u, v in candidates:
            delta = delta_flip(red, blue, u, v)
            is_tabu = tabu.get((u, v), 0) > step
            if is_tabu and not (current + delta < best_count):
                continue
            if best_delta is None or delta < best_delta:
                best_delta, best_move = delta, (u, v)

        if best_move is None:  # everything is tabu: pick a random legal move
            u, v = rng.choice(sorted(candidates))
            best_delta = delta_flip(red, blue, u, v)
            best_move = (u, v)

        u, v = best_move
        flip(red, u, v)
        blue = blue_masks(red, n)
        current += best_delta
        tabu[(u, v)] = step + tenure
        tabu[(v, u)] = step + tenure

        if current < best_count:
            best_count, best_red = current, list(red)
            since_improvement = 0
            history.append((step, best_count))
            if on_improve is not None:
                on_improve(step, best_count)
        else:
            since_improvement += 1

        if since_improvement >= restart_after:
            # Restart from the incumbent with a random perturbation.
            red = list(best_red)
            for _ in range(1 + rng.randrange(n)):
                u, v = rng.choice(sorted(candidates))
                flip(red, u, v)
            blue = blue_masks(red, n)
            current = count_mono_k5(red, n)
            tabu.clear()
            since_improvement = 0

    return {
        "n": n,
        "coloring": serialize(best_red, n),
        "mono_k5": best_count,
        "steps": step,
        "seconds": seconds,
        "seed": seed,
        "history": history,
    }
