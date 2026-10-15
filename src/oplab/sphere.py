"""Spherical codes: the kissing-number problem and the Tammes problem.

Both problems live on the unit sphere ``S^{d-1}`` and both are stated purely in
terms of the Gram matrix of the point set, which makes them ideal for a repo
that only wants *checkable* claims:

* **kissing number** ``tau(d)``: the largest ``N`` such that ``N`` unit vectors
  ``x_1 .. x_N`` in ``R^d`` satisfy ``<x_i, x_j> <= 1/2`` for all ``i != j``.
  (``N`` unit spheres can touch a central unit sphere without overlapping.)
* **Tammes problem** in dimension 3: for a fixed ``N``, maximise the minimal
  angular separation between ``N`` points of ``S^2``.

A claimed configuration is a *certificate*: verifying it is an ``O(N^2)``
floating-point computation, nothing else.  Lower bounds therefore come from
constructions, which is exactly the regime where search does well.

Reference values used below (see ``oplab/references.py`` for sources):

* ``tau(5) = 40``  (D5 roots), ``tau(6) = 72`` (E6 roots), ``tau(7) = 126``
  (E7 roots), ``tau(8) = 240`` (E8 roots, exact; the only proved values among
  these are 1, 2, 3, 4, 8 and 24).
* Tammes best-known minimal angles on ``S^2`` for ``N = 15 .. 23`` come from
  N. J. A. Sloane's tables of best known packings ("putatively optimal").
"""

from __future__ import annotations

import time
from itertools import product

import numpy as np

__all__ = [
    "normalize",
    "project_to_span",
    "gram",
    "max_dot",
    "min_angle_deg",
    "min_angle_rad",
    "is_kissing_configuration",
    "root_system",
    "e8_roots",
    "e7_roots",
    "e6_roots",
    "d_roots",
    "random_points",
    "polish",
    "icosahedron",
    "smooth_max_dot",
    "lbfgs_polish",
    "descend",
    "search_min_max_dot",
    "search_parallel",
    "search_worker",
    "grow_to_n",
    "KISSING_THRESHOLD",
]

#: Two unit vectors in a kissing configuration must satisfy ``<x_i, x_j> <= 1/2``.
KISSING_THRESHOLD = 0.5


# --------------------------------------------------------------------------
# basic geometry
# --------------------------------------------------------------------------
def normalize(P: np.ndarray) -> np.ndarray:
    """Return ``P`` with every row scaled to unit length."""
    P = np.asarray(P, dtype=float)
    norms = np.linalg.norm(P, axis=1, keepdims=True)
    return P / norms


def gram(P: np.ndarray) -> np.ndarray:
    """Gram matrix ``P @ P.T``."""
    P = np.asarray(P, dtype=float)
    return P @ P.T


def max_dot(P: np.ndarray) -> float:
    """Largest pairwise dot product (``-inf`` for fewer than two points)."""
    P = np.asarray(P, dtype=float)
    if len(P) < 2:
        return float("-inf")
    G = gram(P)
    np.fill_diagonal(G, -np.inf)
    return float(G.max())


def min_angle_rad(P: np.ndarray) -> float:
    return float(np.arccos(np.clip(max_dot(P), -1.0, 1.0)))


def min_angle_deg(P: np.ndarray) -> float:
    return float(np.degrees(min_angle_rad(P)))


def is_kissing_configuration(P: np.ndarray, tol: float = 1e-9) -> bool:
    """True iff all rows are unit vectors and all pairwise dots are <= 1/2 + tol."""
    P = np.asarray(P, dtype=float)
    if P.ndim != 2 or len(P) == 0:
        return False
    if not np.allclose(np.linalg.norm(P, axis=1), 1.0, atol=1e-9):
        return False
    return max_dot(P) <= KISSING_THRESHOLD + tol


# --------------------------------------------------------------------------
# exact root systems (integer arithmetic -> reproducible configurations)
# --------------------------------------------------------------------------
def d_roots(d: int) -> np.ndarray:
    """Roots of the lattice ``D_d``: the ``2*d*(d-1)`` vectors ``+/- e_i +/- e_j``.

    For ``d = 5`` this is the classical 40-point kissing configuration.
    """
    rows = []
    for i in range(d):
        for j in range(i + 1, d):
            for si, sj in product((1, -1), repeat=2):
                v = np.zeros(d, dtype=np.int64)
                v[i], v[j] = si, sj
                rows.append(v)
    return np.array(rows, dtype=np.int64)


def e8_roots() -> np.ndarray:
    """The 240 roots of ``E8``, scaled by 2 so that all entries are integers.

    Family A: vectors with two entries ``+/-2`` and zeroes elsewhere (112).
    Family B: vectors ``(+/-1)^8`` with an even number of minus signs (128).

    Both families have squared norm 8, and every pairwise dot product is at most
    4 = 8/2, so normalising gives a valid kissing configuration.
    """
    rows = []
    for i in range(8):
        for j in range(i + 1, 8):
            for si, sj in product((2, -2), repeat=2):
                v = np.zeros(8, dtype=np.int64)
                v[i], v[j] = si, sj
                rows.append(v)
    for signs in product((1, -1), repeat=8):
        if signs.count(-1) % 2 == 0:
            rows.append(np.array(signs, dtype=np.int64))
    return np.array(rows, dtype=np.int64)


def _orthogonal_subset(roots: np.ndarray, root: np.ndarray) -> np.ndarray:
    keep = roots @ root == 0
    return roots[keep]


def e7_roots() -> np.ndarray:
    """The 126 roots of ``E7``: E8 roots orthogonal to a fixed root."""
    roots = e8_roots()
    return _orthogonal_subset(roots, roots[0])


def e6_roots() -> np.ndarray:
    """The 72 roots of ``E6``: E8 roots orthogonal to a pair of roots at 60 degrees.

    Inside the E8 root lattice, ``E6`` is the orthogonal complement of an
    ``A2`` subsystem (two roots with dot product ``+/-4`` in our scaling by 2).
    The first such pair is used, so the function is deterministic.

    Note that ``E6`` is *not* the orthogonal complement of a single root inside
    ``E7``: that gives the 60 roots of ``D6``, not the 72 roots of ``E6``.
    """
    roots = e8_roots()
    for i in range(len(roots)):
        dots = roots @ roots[i]
        for j in np.nonzero(np.abs(dots) == 4)[0]:
            if j <= i:
                continue
            keep = (dots == 0) & (roots @ roots[j] == 0)
            return roots[keep]
    raise RuntimeError("no A2 pair found inside E8")  # pragma: no cover


def icosahedron() -> np.ndarray:
    """The 12 vertices of the regular icosahedron (the kissing configuration in R^3).

    The vertices are the cyclic permutations of ``(0, +/-1, +/-phi)``; nearest
    neighbours are separated by ``arccos(1/sqrt(5)) = 63.43 deg``, well above
    the 60 degrees required by a kissing configuration.
    """
    phi = (1.0 + np.sqrt(5.0)) / 2.0
    pts = []
    for s1 in (1.0, -1.0):
        for s2 in (1.0, -1.0):
            signed = np.array([0.0, s1, s2 * phi])
            for shift in range(3):
                pts.append(np.roll(signed, shift))
    return normalize(np.array(pts, dtype=float))


def project_to_span(P: np.ndarray, tol: float = 1e-9) -> np.ndarray:
    """Return ``P`` in coordinates of the (orthonormal) basis of its own span.

    The ``E6`` and ``E7`` root systems are easiest to build inside ``R^8``, where
    they span proper subspaces of dimension 6 and 7.  Projecting onto the span
    is an isometry on that subspace, so all pairwise dot products and norms are
    preserved, while the configuration now lives in the smallest possible space.
    """
    P = np.asarray(P, dtype=float)
    _, singular_values, vt = np.linalg.svd(P, full_matrices=False)
    if singular_values[0] == 0:
        return P
    rank = int((singular_values > tol * singular_values[0]).sum())
    return normalize(P @ vt[:rank].T)


def root_system(name: str) -> np.ndarray:
    """Unit configuration for a named classical kissing configuration.

    Supported names: ``a2`` (6 points, hexagonal), ``icosahedron`` (12),
    ``d4`` (24), ``d5`` (40), ``e6`` (72), ``e7`` (126), ``e8`` (240).
    Every one of them achieves ``max_dot = 1/2``.
    """
    name = name.lower()
    if name in {"a2", "hexagon"}:
        angles = np.arange(6) * np.pi / 3.0
        return np.stack([np.cos(angles), np.sin(angles)], axis=1)
    if name in {"icosahedron", "ico"}:
        return icosahedron()
    if name.startswith("d_") or (name.startswith("d") and name[1:].isdigit()):
        d = int(name.lstrip("d_"))
        return normalize(d_roots(d).astype(float))
    if name == "e6":
        return project_to_span(e6_roots().astype(float))
    if name == "e7":
        return project_to_span(e7_roots().astype(float))
    if name == "e8":
        return normalize(e8_roots().astype(float))
    raise ValueError(f"unknown root system: {name!r}")


# --------------------------------------------------------------------------
# local search
# --------------------------------------------------------------------------
def random_points(n: int, d: int, rng: np.random.Generator) -> np.ndarray:
    """``n`` independent uniform points of ``S^{d-1}``."""
    return normalize(rng.normal(size=(n, d)))





def smooth_max_dot(P: np.ndarray, beta: float = 100.0) -> float:
    """Log-sum-exp approximation of ``max_dot`` (differentiable everywhere)."""
    G = gram(P)
    np.fill_diagonal(G, -np.inf)
    m = float(G.max())
    return float(m + np.log(np.exp(beta * (G - m)).sum()) / beta)


def has_scipy() -> bool:
    try:  # pragma: no cover - trivial
        import scipy.optimize  # noqa: F401
    except Exception:  # pragma: no cover
        return False
    return True


def lbfgs_polish(
    P: np.ndarray,
    beta: float = 120.0,
    maxiter: int = 400,
    steps: int = 4,
) -> np.ndarray:
    """Polish a configuration with quasi-Newton descent on the smooth max.

    Uses ``scipy.optimize.minimize`` (L-BFGS-B) on ``smooth_max_dot``; the
    ``beta`` values are ramped up so that the minimiser tracks the true maximum
    rather than its smooth surrogate.  Returns the input unchanged when SciPy
    is unavailable or when the result is not an improvement.
    """
    if not has_scipy():
        return P
    from scipy.optimize import minimize

    P = normalize(P)
    n, d = P.shape
    best = P
    best_value = max_dot(P)
    for k in range(steps):
        b = beta * (4.0**k)

        def objective(x):
            return smooth_max_dot(normalize(x.reshape(n, d)), b)

        res = minimize(
            objective,
            best.ravel(),
            method="L-BFGS-B",
            options={"maxiter": maxiter, "ftol": 1e-14, "gtol": 1e-12},
        )
        candidate = normalize(res.x.reshape(n, d))
        value = max_dot(candidate)
        if value < best_value:
            best, best_value = candidate, value
    return best


def polish(P: np.ndarray, target: float, sweeps: int = 2, lr: float = 0.5) -> np.ndarray:
    """Coordinate descent: relax one point at a time against the others.

    Whole-set gradient descent stalls when many pairs are simultaneously at the
    barrier; moving single points is far better conditioned and squeezes the
    last digits of a configuration.
    """
    P = normalize(P)
    n = len(P)
    for _ in range(sweeps):
        for i in range(n):
            dots = P @ P[i]
            w = np.maximum(dots - target, 0.0)
            w[i] = 0.0
            if not w.any():
                continue
            x = P[i] - lr * (w @ P)
            norm = np.linalg.norm(x)
            if norm > 0:
                P[i] = x / norm
    return P


def descend(P: np.ndarray, target: float, steps: int, lr: float) -> np.ndarray:
    """Gradient descent on ``sum_{i<j} relu(<x_i,x_j> - target)^2`` on the sphere.

    The gradient of the penalty with respect to ``x_i`` is
    ``2 * sum_j relu(dot_ij - target) * x_j``; after each step the points are
    projected back onto the sphere by renormalisation.
    """
    P = normalize(P)
    for _ in range(steps):
        G = gram(P)
        np.fill_diagonal(G, -np.inf)
        A = np.maximum(G - target, 0.0)
        np.fill_diagonal(A, 0.0)
        if not A.any():
            break
        P = normalize(P - lr * (A @ P))
    return P


def search_min_max_dot(
    P0: np.ndarray,
    seconds: float,
    rng: np.random.Generator,
    lr: float = 0.3,
    chunk: int = 40,
    jitter: float = 0.02,
    on_improve=None,
    use_scipy: bool = True,
) -> tuple[np.ndarray, float]:
    """Minimise ``max_dot`` with a threshold-descent / restart loop.

    Returns ``(best_points, best_max_dot)``.  The loop is time-bounded and
    deterministic given ``rng``: every improvement is reported through
    ``on_improve(points, value)`` when that callback is given.
    """
    deadline = time.time() + seconds
    best = normalize(P0)
    best_value = max_dot(best)
    current = best
    if on_improve is not None:
        on_improve(best.copy(), best_value)

    while time.time() < deadline:
        # Aim strictly below the current best; the descent either reaches the
        # target (improvement) or stalls on a local barrier (restart/jitter).
        target = best_value - max(1e-9, 1e-4 * (1.0 + abs(best_value)))
        Q = normalize(current + rng.normal(scale=jitter, size=current.shape))
        Q = descend(Q, target, chunk, lr)
        Q = polish(Q, target, sweeps=1, lr=0.5)
        if use_scipy:
            Q = lbfgs_polish(Q, maxiter=120, steps=2)
        value = max_dot(Q)
        if value < best_value - 1e-12:
            best, best_value, current = Q, value, Q
            if on_improve is not None:
                on_improve(Q.copy(), value)
        elif value < max_dot(current) + 1e-12:
            # Accept a sideways/strictly-better move to keep exploring.
            current = Q
        else:
            # Hard restart: random configuration, or a jittered best.
            if rng.random() < 0.35:
                current = best
            else:
                current = random_points(len(best), best.shape[1], rng)
    return best, best_value


def search_worker(args: dict) -> dict:
    """Top-level worker used by :func:`search_parallel` (must be picklable)."""
    n = int(args["n"])
    d = int(args["dim"])
    seconds = float(args["seconds"])
    seed = int(args["seed"])
    start = args.get("start")
    rng = np.random.default_rng(seed)
    P0 = np.asarray(start, dtype=float) if start is not None else random_points(n, d, rng)
    if len(P0) < n:
        P0 = np.vstack([P0, random_points(n - len(P0), d, rng)])
    if len(P0) > n:
        P0 = P0[:n]
    P, value = search_min_max_dot(normalize(P0), seconds, rng, use_scipy=True)
    return {
        "n": n,
        "dim": d,
        "seed": seed,
        "max_dot": float(value),
        "min_angle_deg": min_angle_deg(P),
        "points": P.tolist(),
    }


def search_parallel(
    n: int,
    d: int,
    seconds: float,
    workers: int = 1,
    seed: int = 0,
    start: np.ndarray | None = None,
) -> dict:
    """Run independent searches in parallel; return the best configuration found.

    Every worker gets the full time budget, so wall-clock time stays close to
    ``seconds`` while the search effort scales with the number of cores.
    """
    jobs = [
        {"n": n, "dim": d, "seconds": seconds, "seed": seed + 7919 * i, "start": start}
        for i in range(max(1, workers))
    ]
    if len(jobs) == 1:
        best = search_worker(jobs[0])
        best["workers"] = 1
        best["worker_results"] = [{"seed": best["seed"], "max_dot": best["max_dot"]}]
        return best
    from concurrent.futures import ProcessPoolExecutor

    with ProcessPoolExecutor(max_workers=len(jobs)) as pool:
        results = list(pool.map(search_worker, jobs))
    best = min(results, key=lambda r: r["max_dot"])
    best["workers"] = len(jobs)
    best["worker_results"] = [{"seed": r["seed"], "max_dot": r["max_dot"]} for r in results]
    return best


def grow_to_n(
    start: np.ndarray,
    n: int,
    seconds: float,
    rng: np.random.Generator,
    **kwargs,
) -> tuple[np.ndarray, float]:
    """Optimise an ``n``-point configuration built from ``start`` plus new points.

    Extra points are inserted at random and the whole set is relaxed, so this is
    the natural way to attack "beat the record by one point" questions such as
    ``tau(5) >= 41``.
    """
    P = start
    while len(P) < n:
        extra = random_points(1, P.shape[1], rng)
        P = np.vstack([P, extra])
    return search_min_max_dot(normalize(P), seconds, rng, **kwargs)
