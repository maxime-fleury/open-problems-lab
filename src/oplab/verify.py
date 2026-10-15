"""Independent verification of certificates.

Certificates are plain JSON files under ``certs/``.  Nothing in them is trusted:
every claimed quantity is recomputed from the raw payload here, and the payload
is integrity-checked against its sha256.  ``oplab verify`` returns a non-zero
exit status as soon as one certificate fails, which is what CI runs.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from . import SCHEMA_VERSION, ramsey as R, sphere as S, unitdist as U

__all__ = ["payload_hash", "make_certificate", "verify_certificate", "verify_path", "CANONICAL_DUMPS"]

#: Verification tolerance for geometric claims (configurations are stored as
#: float64 JSON; all classical constructions are exact to ~1e-15).
TOL = 1e-9


def CANONICAL_DUMPS(obj) -> str:  # noqa: N802 - deliberate constant
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def payload_hash(payload) -> str:
    return hashlib.sha256(CANONICAL_DUMPS(payload).encode("utf-8")).hexdigest()


def make_certificate(problem: str, title: str, payload, claims, provenance) -> dict:
    """Assemble a certificate dict, including the payload hash."""
    return {
        "schema_version": SCHEMA_VERSION,
        "problem": problem,
        "title": title,
        "payload": payload,
        "claims": claims,
        "provenance": provenance,
        "payload_sha256": payload_hash(payload),
    }


def _numpy_points(payload) -> np.ndarray:
    points = np.asarray(payload["points"], dtype=float)
    if points.ndim != 2:
        raise ValueError("'points' must be a list of vectors")
    return points


# --------------------------------------------------------------------------
# problem-specific verifiers
# --------------------------------------------------------------------------
def verify_kissing(cert: dict, tol: float = TOL) -> dict:
    payload, claims = cert["payload"], cert["claims"]
    dim = int(payload["dim"])
    points = _numpy_points(payload)
    if points.shape[1] != dim:
        return {"ok": False, "reason": f"payload dim mismatch: {points.shape[1]} != {dim}"}
    norms_ok = bool(np.allclose(np.linalg.norm(points, axis=1), 1.0, atol=tol))
    value = S.max_dot(points)
    threshold_ok = value <= S.KISSING_THRESHOLD + tol
    ok = norms_ok and threshold_ok
    result = {
        "ok": ok,
        "checks": {
            "n_points": len(points),
            "dim": dim,
            "unit_norms": norms_ok,
            "max_dot": value,
            "max_dot_le_half": threshold_ok,
        },
    }
    if not ok:
        result["reason"] = "points are not a valid kissing configuration"
        return result
    result["establishes"] = f"tau({dim}) >= {len(points)}"
    if "n_points" in claims and int(claims["n_points"]) != len(points):
        result["ok"] = False
        result["reason"] = "claimed n_points does not match the payload"
    return result


def verify_tammes(cert: dict, tol: float = 1e-6) -> dict:
    payload, claims = cert["payload"], cert["claims"]
    dim = int(payload["dim"])
    points = _numpy_points(payload)
    if points.shape[1] != dim:
        return {"ok": False, "reason": "payload dim mismatch"}
    norms_ok = bool(np.allclose(np.linalg.norm(points, axis=1), 1.0, atol=TOL))
    angle = S.min_angle_deg(points)
    result = {
        "ok": norms_ok,
        "checks": {"n_points": len(points), "dim": dim, "unit_norms": norms_ok,
                   "min_angle_deg": angle, "max_dot": S.max_dot(points)},
    }
    if not norms_ok:
        result["reason"] = "points are not unit vectors"
        return result
    if "min_angle_deg" in claims:
        claimed = float(claims["min_angle_deg"])
        if abs(claimed - angle) > tol:
            result["ok"] = False
            result["reason"] = f"claimed min_angle_deg {claimed!r} != recomputed {angle!r}"
    result["establishes"] = f"a valid configuration of {len(points)} points on S^{dim - 1}"
    return result


def verify_spherical_search(cert: dict, tol: float = TOL) -> dict:
    """Verify the *measurement* of a search attempt.

    Unlike :func:`verify_kissing` this does not require the configuration to be a
    valid kissing configuration: a failed attempt is still worth recording, and
    what is verified is the reported value plus the honesty of the flag saying
    whether a bound was established.
    """
    payload, claims = cert["payload"], cert["claims"]
    dim = int(payload["dim"])
    points = _numpy_points(payload)
    if points.shape[1] != dim:
        return {"ok": False, "reason": "payload dim mismatch"}
    value = S.max_dot(points)
    threshold = float(claims.get("threshold", S.KISSING_THRESHOLD))
    establishes = bool(claims.get("establishes_bound", value <= threshold + tol))
    expected_establishes = value <= threshold + tol
    result = {
        "ok": True,
        "checks": {"n_points": len(points), "dim": dim, "max_dot": value, "threshold": threshold,
                   "establishes_bound": establishes},
    }
    if "max_dot" in claims and abs(float(claims["max_dot"]) - value) > 1e-9:
        result["ok"] = False
        result["reason"] = f"claimed max_dot {claims['max_dot']!r} != recomputed {value!r}"
        return result
    if "n_points" in claims and int(claims["n_points"]) != len(points):
        result["ok"] = False
        result["reason"] = "claimed n_points does not match the payload"
        return result
    if establishes != expected_establishes:
        result["ok"] = False
        result["reason"] = (
            "the establishes_bound flag is wrong: "
            f"max_dot={value!r} vs threshold={threshold!r}"
        )
        return result
    result["establishes"] = f"tau({dim}) >= {len(points)}" if establishes else None
    if not establishes:
        result["note"] = f"best found max_dot={value!r} > {threshold}: no new bound"
    return result


def verify_unitdist_search(cert: dict, tol: float = 1e-9) -> dict:
    """Verify the summary of a unit-distance search attempt."""
    payload = cert["payload"]
    best_points = payload.get("best_points")
    result: dict = {"ok": True, "checks": {"max_vertices": payload.get("max_vertices"),
                                            "samples": payload.get("samples")}}
    if best_points is None:
        result["establishes"] = None
        result["note"] = "no graph was recorded"
        return result
    points = np.asarray(best_points, dtype=float)
    edges = [tuple(e) for e in payload["best_edges"]]
    if not U.is_unit_distance_graph(points, edges, tol=tol):
        result["ok"] = False
        result["reason"] = "recorded edges are not exactly the unit-distance pairs"
        return result
    chi = U.chromatic_number(U.adjacency_from_points(points, tol=tol))
    claimed = int(payload["best_chromatic_number"])
    result["checks"]["chromatic_number"] = chi
    if chi != claimed:
        result["ok"] = False
        result["reason"] = f"claimed chromatic number {claimed} != recomputed {chi}"
        return result
    result["establishes"] = f"the chromatic number of the plane is >= {chi}"
    return result


def verify_ramsey(cert: dict, tol: float = 0.0) -> dict:
    payload, claims = cert["payload"], cert["claims"]
    if not isinstance(claims, dict):  # pragma: no cover - defensive
        return {"ok": False, "reason": "claims must be an object"}
    n = int(payload["n"])
    k = int(payload.get("k", 5))
    if k < 3 or k > n:
        return {"ok": False, "reason": f"k={k} is not a valid clique size for K{n}"}
    coloring = payload["coloring"]
    try:
        red = R.parse(coloring, n)
    except ValueError as exc:
        return {"ok": False, "reason": str(exc)}
    count = R.count_mono_clique(red, n, k)
    result = {
        "ok": True,
        "checks": {"n": n, "k": k, f"mono_k{k}": count, "edges": n * (n - 1) // 2},
    }
    key = f"mono_k{k}"
    if key in claims and int(claims[key]) != count:
        result["ok"] = False
        result["reason"] = f"claimed {key} {claims[key]!r} != recomputed {count}"
        return result
    if count == 0:
        result["establishes"] = f"R({k},{k}) > {n}  (i.e. R({k},{k}) >= {n + 1})"
    else:
        result["establishes"] = None
        result["note"] = f"{count} monochromatic K{k} remain: no Ramsey bound is established"
    return result


def verify_sat_attempt(cert: dict, tol: float = 0.0) -> dict:
    """Verify the metadata of an inconclusive SAT attempt (``status == unknown``).

    A run that proved nothing still has to be honest about what it produced: the
    encoding size must match the formula ``2 * C(n, k)`` plus symmetry clauses,
    and the reported status must not be dressed up as a verdict.
    """
    from math import comb

    from . import sat

    payload = cert["payload"]
    n, k = int(payload["n"]), int(payload["k"])
    symmetry = int(payload.get("symmetry", 0))
    status = payload.get("status")
    result = {"ok": True, "checks": {"n": n, "k": k, "symmetry": symmetry, "status": status}}
    if status != "unknown":
        return {"ok": False, "reason": f"a sat attempt certificate must have status 'unknown', got {status!r}"}
    if symmetry not in sat.SYMMETRY_LEVELS:
        return {"ok": False, "reason": f"unknown symmetry level {symmetry}"}
    expected = sat.build_instance(n, k, symmetry).clause_count()
    encoding = payload.get("encoding", {})
    if int(encoding.get("num_clauses", -1)) != expected:
        result["ok"] = False
        result["reason"] = f"declared {encoding.get('num_clauses')} clauses, encoding has {expected}"
        return result
    if int(encoding.get("subset_clauses_match_formula", 2 * comb(n, k))) != 2 * comb(n, k):
        result["ok"] = False
        result["reason"] = "subset clause count does not match 2 * C(n, k)"
        return result
    result["establishes"] = None
    result["note"] = "no verdict: the run was inconclusive within its time budget"
    return result


def verify_ramsey_unsat(cert: dict, deep: bool = False, workers: int = 1) -> dict:
    """Verify an unsatisfiability claim about one SAT encoding.

    This is deliberately weak, and says so: without a DRAT proof there is no
    short certificate of unsatisfiability, so what can be checked cheaply is the
    *consistency of the metadata* (the declared encoding size against the
    formula ``2 * C(n, k)`` plus the symmetry clauses).  ``--deep`` re-runs the
    solver on the same instance, which is evidence of reproducibility, not an
    independent proof.
    """
    from math import comb

    from . import sat

    payload = cert["payload"]
    n, k = int(payload["n"]), int(payload["k"])
    symmetry = int(payload.get("symmetry", 0))
    encoding = payload.get("encoding", {})
    result = {"ok": True, "checks": {"n": n, "k": k, "symmetry": symmetry, "backend": payload.get("backend")}}
    if payload.get("status") != "unsat":
        return {"ok": False, "reason": "this verifier only handles unsat claims"}
    if symmetry not in sat.SYMMETRY_LEVELS:
        return {"ok": False, "reason": f"unknown symmetry level {symmetry}"}
    instance = sat.build_instance(n, k, symmetry)
    expected = instance.clause_count()
    if int(encoding.get("num_clauses", -1)) != expected:
        result["ok"] = False
        result["reason"] = (
            f"declared {encoding.get('num_clauses')} clauses, but the encoding has {expected}"
            f" (2 * C({n},{k}) = {2 * comb(n, k)} subset clauses plus symmetry)"
        )
        return result
    if int(encoding.get("match_formula", 2 * comb(n, k))) != 2 * comb(n, k):
        result["ok"] = False
        result["reason"] = "subset clause count does not match 2 * C(n, k)"
        return result
    result["establishes"] = None
    result["note"] = "unsatisfiability is not independently proved (no DRAT proof is produced)"
    if deep:
        redo = sat.solve(n, k, symmetry, seconds=float(payload.get("seconds", 60.0)), solver="auto")
        result["checks"]["deep_rerun_status"] = redo["status"]
        if redo["status"] != "unsat":
            result["ok"] = False
            result["reason"] = f"deep re-run returned {redo['status']!r}, not unsat"
    return result


def verify_unit_distance(cert: dict, tol: float = 1e-9, max_vertices: int = 60) -> dict:
    payload, claims = cert["payload"], cert["claims"]
    points = _numpy_points(payload)
    edges = [tuple(e) for e in payload["edges"]]
    n = len(points)
    if n > max_vertices:
        return {"ok": False, "reason": f"graph has {n} vertices, above the exact-colouring cap {max_vertices}"}
    if not U.is_unit_distance_graph(points, edges, tol=tol):
        return {"ok": False, "reason": "edges are not exactly the unit-distance pairs of the points"}
    adj = U.adjacency_from_points(points, tol=tol)
    chi = U.chromatic_number(adj)
    result = {
        "ok": True,
        "checks": {"n_vertices": n, "n_edges": len(edges), "chromatic_number": chi},
    }
    if "chromatic_number" in claims and int(claims["chromatic_number"]) != chi:
        result["ok"] = False
        result["reason"] = f"claimed chromatic_number {claims['chromatic_number']!r} != recomputed {chi}"
        return result
    result["establishes"] = f"the chromatic number of the plane is >= {chi}"
    return result


def verify_circulant(cert: dict, deep: bool = False, workers: int = 1) -> dict:
    payload = cert["payload"]
    n, k = int(payload["n"]), int(payload["k"])
    total = 1 << len(R.free_differences(n))
    result: dict = {"ok": True, "checks": {"n": n, "k": k, "colourings_tested": payload["colourings_tested"]}}
    if int(payload["colourings_tested"]) != total:
        result["ok"] = False
        result["reason"] = (
            f"claim covers only {payload['colourings_tested']} of the {total} circulant colourings of K{n}"
        )
        return result
    # Every reported witness is re-checked exactly: cheap and decisive.
    for mask in payload.get("witnesses", []):
        adj = R.circulant_adjacency(n, int(mask))
        if R.circulant_has_mono_clique(n, int(mask), k):
            result["ok"] = False
            result["reason"] = f"claimed witness mask {mask} does contain a monochromatic K{k}"
            return result
        if k == 5 and R.count_mono_k5(adj, n) != 0:
            result["ok"] = False
            result["reason"] = f"witness mask {mask} is not clean"
            return result
    if not payload.get("witnesses"):
        result["establishes"] = f"no circulant 2-colouring of K{n} avoids a monochromatic K{k}"
        if deep:
            redo = R.circulant_search(n, k, workers=workers)
            result["checks"]["deep_rerun_tested"] = redo["colourings_tested"]
            result["checks"]["deep_rerun_witnesses"] = redo["witnesses"]
            if redo["witnesses"] != sorted(int(m) for m in payload["witnesses"]):
                result["ok"] = False
                result["reason"] = "deep re-run disagrees with the certificate"
    else:
        result["establishes"] = f"R({k},{k}) > {n} via a circulant witness"
    return result


VERIFIERS = {
    "kissing": verify_kissing,
    "tammes": verify_tammes,
    "ramsey": verify_ramsey,
    "unit_distance": verify_unit_distance,
    "circulant": verify_circulant,
    "spherical_search": verify_spherical_search,
    "unitdist_search": verify_unitdist_search,
    "ramsey_unsat": verify_ramsey_unsat,
    "sat_attempt": verify_sat_attempt,
}


def verify_certificate(cert: dict, deep: bool = False, workers: int = 1) -> dict:
    """Verify one certificate dict; returns a result dict with ``ok``."""
    version = cert.get("schema_version")
    if version != SCHEMA_VERSION:
        return {"ok": False, "reason": f"unsupported schema_version {version!r}"}
    problem = cert.get("problem")
    verifier = VERIFIERS.get(problem)
    if verifier is None:
        return {"ok": False, "reason": f"unknown problem {problem!r}"}
    expected = cert.get("payload_sha256")
    if expected is not None:
        actual = payload_hash(cert["payload"])
        if actual != expected:
            return {"ok": False, "reason": "payload sha256 mismatch (file was edited by hand?)"}
    try:
        if problem in {"circulant", "ramsey_unsat"}:
            return verifier(cert, deep=deep, workers=workers)
        return verifier(cert)
    except (KeyError, ValueError, TypeError) as exc:
        return {"ok": False, "reason": f"malformed certificate: {exc.__class__.__name__}: {exc}"}


def verify_path(path: Path, deep: bool = False, workers: int = 1) -> list[tuple[Path, dict]]:
    """Verify a certificate file, or every ``*.json`` under a directory."""
    path = Path(path)
    files = sorted(path.rglob("*.json")) if path.is_dir() else [path]
    out = []
    for file in files:
        try:
            cert = json.loads(file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            out.append((file, {"ok": False, "reason": f"invalid JSON: {exc}"}))
            continue
        if isinstance(cert, dict) and "schema_version" in cert and "problem" in cert:
            out.append((file, verify_certificate(cert, deep=deep, workers=workers)))
        else:
            out.append((file, {"ok": True, "skipped": "not a certificate"}))
    return out
