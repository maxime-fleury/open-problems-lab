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

#: Seconds of DRAT replay a plain `verify` run will spend per certificate.  Each
#: proof-carrying certificate records how long its own replay took when it was
#: written (`replay_seconds`), so the cheap rows are re-derived on every run and
#: the expensive ones wait for `--deep` — instead of the whole suite being slow or
#: the expensive rows never being checked.
REPLAY_BUDGET_SECONDS = 45.0


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


def verify_cayley_multicolour(cert: dict, deep: bool = False, workers: int = 1,
                              base_dir=None) -> dict:
    """Verify a decision about the translation-invariant colourings of **one group**.

    Nothing in the payload is trusted except the *description* of the group: the
    table is rebuilt from it with :func:`oplab.cayley.group_from_description`, then
    checked against the group axioms (a description that is not a group is refused,
    not searched), the inversion classes and the encoding size are recomputed, and
    the stored per-class assignment is expanded into a colouring of all ``C(n, 2)``
    edges and re-counted by the exact clique counter.  The expanded string, if the
    payload carries one, has to agree with that expansion.

    ``sat`` is a witness and is decisive; ``obstructed`` re-derives the ``3 | n``
    argument by arithmetic.  The payload also carries the group's multiplication
    table, inverse list and clique-group counts; those are checked against the ones
    rebuilt from the description (as the axioms are), so the group the claims are
    about is never just the description's word, and the same data is what the Lean
    layer recomputes the encoding size from.

    ``unsat`` is accepted *only* as a proof-carrying row:
    the certificate has to record a DRAT trace, replayed here against this group's
    own encoding (``CayleyInstance`` for the declared description, not the circulant
    one — the clauses are different, and a trace from another family has neither the
    right variables nor the right clauses), and a row that claims ``unsat`` without
    one is refused rather than recorded as a verdict.  A trace whose replay is
    expensive may be left to ``--deep`` by its recorded ``replay_seconds``, but its
    digests are re-checked on every run, and every stored trace is cross-checked by
    the external ``drat-trim`` (:mod:`scripts.drat_trim_check`).
    """
    from . import cayley as CY
    from . import multicolour as MC

    payload = cert["payload"]
    description = dict(payload["group"])
    sizes = tuple(int(s) for s in payload["sizes"])
    status = payload.get("status")
    table, inverse = CY.group_from_description(description)
    # the description goes with the table so the check is the one that fits the
    # family: a `permutation` group is re-closed and compared (its table is the
    # multiplication of permutations, so associativity is inherited and the stored
    # copy is compared element by element below), while the named families get the
    # axioms re-derived over every triple
    axioms = CY.verify_group(table, inverse, description)
    if not axioms["ok"]:
        return {"ok": False, "reason": f"the declared group is not a group: {axioms['reason']}"}
    instance = CY.CayleyInstance(description, sizes)
    n = instance.n
    result: dict = {
        "ok": True,
        "checks": {
            "n": n,
            "sizes": list(sizes),
            "status": status,
            "family": description["family"],
            "group_order": n,
            "classes": len(instance.classes),
            "num_vars": instance.total_vars(),
            "num_clauses": instance.clause_count(),
        },
    }
    if status not in {"sat", "unsat", "obstructed", "unknown"}:
        return {"ok": False, "reason": f"unknown status {status!r}"}
    declared_vars, declared_clauses = payload.get("num_vars"), payload.get("num_clauses")
    if declared_vars is not None and int(declared_vars) != instance.total_vars():
        return {"ok": False,
                "reason": f"declared {declared_vars} variables, the encoding has "
                          f"{instance.total_vars()}"}
    if declared_clauses is not None and int(declared_clauses) != instance.clause_count():
        return {"ok": False,
                "reason": f"declared {declared_clauses} clauses, the encoding has "
                          f"{instance.clause_count()}"}
    if payload.get("classes") is not None and int(payload["classes"]) != len(instance.classes):
        return {"ok": False,
                "reason": f"declared {payload['classes']} classes, the group has "
                          f"{len(instance.classes)}"}
    # The group travels as data as well as as a description, because the Lean layer
    # recomputes the encoding from that data and cannot run this module.  The stored
    # copy is checked against the rebuilt one here, so the two can never disagree,
    # and a certificate without it is refused: the claims of this kind are about a
    # table, and the table is part of the claim.
    declared_table = payload.get("table")
    declared_inverse = payload.get("inverse")
    if declared_table is None or declared_inverse is None:
        return {"ok": False,
                "reason": ("the certificate does not carry the group's multiplication table "
                           "and inverse list, so its encoding cannot be recomputed outside "
                           "this verifier")}
    if [[int(x) for x in row] for row in declared_table] != [list(r) for r in instance.table]:
        return {"ok": False,
                "reason": ("the stored multiplication table is not the table of the declared "
                           "group")}
    if [int(x) for x in declared_inverse] != list(instance.inverse):
        return {"ok": False,
                "reason": "the stored inverse list is not the declared group's"}
    declared_groups = payload.get("clique_groups")
    expected_groups = {str(s): len(g) for s, g in instance.groups.items()}
    if declared_groups is None or {str(k): int(v) for k, v in declared_groups.items()} != expected_groups:
        return {"ok": False,
                "reason": (f"declared per-size clique-group counts {declared_groups} do not "
                           f"match the encoding's {expected_groups}")}

    obstruction = CY.cayley_obstruction(description, sizes)
    if status == "obstructed":
        if obstruction is None:
            return {"ok": False, "reason": f"K{n} {sizes} has no arithmetic obstruction"}
        classes, class_of = CY.inversion_classes(table, inverse)
        # the generic obstruction needs an element whose class is a single 3-class:
        # {e, g, g^2} must have all three differences in one class, by the table
        triple = list(obstruction["triangle"])
        edges = {class_of[table[inverse[u]][v]] for i, u in enumerate(triple)
                 for v in triple[i + 1:]}
        if len(edges) != 1:
            return {"ok": False,
                    "reason": f"the declared obstruction triangle is not monochromatic "
                              f"by arithmetic: its differences span {sorted(edges)}"}
        # the certificate has to name the triangle the arithmetic found: the *fact*
        # is that some element has order 3, and which one it is depends on how the
        # group was written down
        declared = payload.get("obstruction") or {}
        declared_triangle = [int(x) for x in declared.get("triangle", [])]
        if declared_triangle and declared_triangle != triple:
            return {"ok": False,
                    "reason": f"the declared obstruction triangle {declared_triangle} is "
                              f"not the one the arithmetic finds {triple}"}
        result["establishes"] = (
            f"no translation-invariant colouring of any group of order {n} avoids a "
            f"monochromatic K3 in a colour that forbids one (an element of order 3 "
            f"forces {obstruction['triangles']} monochromatic triangles, whichever "
            f"colour its class carries)"
        )
        return result

    if status == "unknown":
        result["establishes"] = None
        result["note"] = ("no verdict: the bounded run was stopped by its budget, so the "
                          "certificate records the encoding and the attempt, nothing else")
        return result

    if status == "unsat":
        # a solver's verdict about one group's family is only worth storing when it
        # is proof-carrying: the trace is what makes it a theorem, so there is none
        # of the "recorded as a verdict, not a theorem" middle ground the circulant
        # kind allows
        if obstruction is not None:
            return {"ok": False,
                    "reason": (f"K{n} with {sizes} is arithmetically obstructed (3 | n) in "
                               f"every group of that order, so it must be recorded as "
                               f"'obstructed', not as a solver verdict")}
        proof = payload.get("proof")
        if not proof:
            return {"ok": False,
                    "reason": ("an `unsat` row over a group is accepted only with a DRAT "
                               "trace: without one it is a solver verdict about this "
                               "group, not a theorem, and this kind stores no verdicts")}
        recorded_cost = float(proof.get("replay_seconds", 1e9))
        checked = _verify_stored_proof(n, sizes, proof, base_dir,
                                       replay=deep or recorded_cost <= REPLAY_BUDGET_SECONDS,
                                       instance=instance)
        result["checks"]["proof"] = checked
        if not checked["ok"]:
            result["ok"] = False
            result["reason"] = checked["reason"]
            return result
        over = description.get("name") or description["family"]
        if checked.get("replayed"):
            result["establishes"] = (
                f"no translation-invariant colouring over {over} (a group of order {n}) "
                f"avoids a monochromatic forbidden clique in every colour "
                f"(DRAT proof replayed, {checked['steps']} steps)"
            )
        else:
            result["establishes"] = (
                f"no translation-invariant colouring over {over} (a group of order {n}) "
                f"avoids a monochromatic forbidden clique in every colour "
                f"(DRAT proof on disk, digest re-checked; run with --deep to replay it)"
            )
        if deep:
            # the same bounded re-run the other kinds do: a `--deep` check has to see
            # the verdict reproduced, not just the trace replayed
            redo = CY.cayley_solve(description, sizes,
                                   seconds=max(60.0, float(payload.get("seconds", 60.0))))
            result["checks"]["deep_rerun_status"] = redo["status"]
            if redo["status"] != "unsat":
                result["ok"] = False
                result["reason"] = f"deep re-run returned {redo['status']!r}, not unsat"
        return result

    # status == "sat": the per-class assignment is the artifact
    assignment = payload.get("class_colors")
    if not isinstance(assignment, dict) or not assignment:
        return {"ok": False, "reason": "missing per-class colour assignment"}
    colours: dict[int, int] = {}
    for key, value in assignment.items():
        colours[int(key)] = int(value)
    expected_keys = set(instance.classes)
    if set(colours) != expected_keys:
        return {"ok": False,
                "reason": (f"the assignment covers {len(colours)} classes, the group has "
                           f"{len(expected_keys)} (missing "
                           f"{sorted(expected_keys - set(colours))[:5]}...)")}
    if any(not 0 <= c < len(sizes) for c in colours.values()):
        return {"ok": False, "reason": "a class carries a colour outside the instance"}
    colouring = instance.expand(colours)
    text = MC.serialize_colouring(colouring, instance.n)
    stored = payload.get("coloring")
    if stored is not None and stored != text:
        return {"ok": False,
                "reason": "the stored colouring string disagrees with the per-class assignment"}
    # every class really is one colour in the expanded colouring: that is what makes
    # this a translation-invariant object and not just an arbitrary clean colouring
    for x in range(instance.n):
        row = instance.table[instance.inverse[x]]
        for y in range(instance.n):
            if x != y:
                want = colours[instance.class_of[row[y]]]
                if int(colouring[x, y]) != want:
                    return {"ok": False, "reason": f"class structure broken at {(x, y)}"}
    counts = MC.mono_clique_counts(instance.n, sizes, colouring)
    result["checks"]["monochromatic_cliques"] = counts
    if any(c != 0 for c in counts):
        return {"ok": False, "reason": f"the stored colouring is not clean: {counts}"}
    claimed = cert["claims"].get("monochromatic_cliques")
    if claimed is not None and [int(c) for c in claimed] != counts:
        return {"ok": False, "reason": f"claimed counts {claimed} != recomputed {counts}"}
    name = description.get("name") or description["family"]
    result["establishes"] = (
        f"R{tuple(sizes)} > {n} via a translation-invariant witness over {name} "
        f"(a restriction of the colourings of K{n}: a witness is a witness)"
    )
    if deep:
        redo = CY.cayley_solve(description, sizes,
                               seconds=max(60.0, float(payload.get("seconds", 60.0))))
        result["checks"]["deep_rerun_status"] = redo["status"]
        if redo["status"] not in {"sat", "obstructed"}:
            return {"ok": False, "reason": f"deep re-run returned {redo['status']!r}, not sat"}
    return result


def verify_circulant_multicolour(cert: dict, deep: bool = False, workers: int = 1,
                                 base_dir=None) -> dict:
    """Verify one decision about the *circulant* sub-family of a multicolour instance.

    Three kinds of payload, checked to three different standards:

    * ``sat`` — a witness, re-expanded from the stored string and re-counted by the
      exact clique counter, plus a check that the colouring really is circulant
      (constant on every difference class).  Decisive.
    * ``obstructed`` — the arithmetic fact that ``3 | n`` makes ``{0, n/3, 2n/3}``
      monochromatic in the colour of the class ``n // 3`` for *every* class
      assignment, checked here from scratch with no solver.
    * ``unsat`` — a verdict about the CNF, which becomes a theorem when the
      certificate carries a DRAT trace: the trace is replayed against the encoding
      rebuilt here, by :mod:`oplab.drat`, with no solver involved.  A certificate
      without a trace is checked only for its encoding size, and says so.  The
      digest of every stored trace is re-checked on every run, and the trace itself
      is replayed when its recorded cost is within
      :data:`REPLAY_BUDGET_SECONDS`, or always under ``--deep`` (which also
      re-runs the solver).  The same traces are cross-checked by the external
      ``drat-trim`` (:mod:`scripts.drat_trim_check`), so this replay is not their
      only judge.
    """
    from . import multicolour as MC

    payload = cert["payload"]
    n = int(payload["n"])
    sizes = tuple(int(s) for s in payload["sizes"])
    status = payload.get("status")
    instance = MC.CirculantInstance(n, sizes)
    result: dict = {
        "ok": True,
        "checks": {
            "n": n,
            "sizes": list(sizes),
            "status": status,
            "classes": len(instance.classes),
            "num_vars": instance.total_vars(),
            "num_clauses": instance.clause_count(),
        },
    }
    if status not in {"sat", "unsat", "obstructed", "unknown"}:
        return {"ok": False, "reason": f"unknown status {status!r}"}
    declared_vars = payload.get("num_vars")
    declared_clauses = payload.get("num_clauses")
    if declared_vars is not None and int(declared_vars) != instance.total_vars():
        result["ok"] = False
        result["reason"] = (
            f"declared {declared_vars} variables, the encoding has {instance.total_vars()}"
        )
        return result
    if declared_clauses is not None and int(declared_clauses) != instance.clause_count():
        result["ok"] = False
        result["reason"] = (
            f"declared {declared_clauses} clauses, the encoding has {instance.clause_count()}"
        )
        return result
    if dict(payload.get("clique_groups", {})) != {
        str(s): len(g) for s, g in instance.groups.items()
    }:
        result["ok"] = False
        result["reason"] = "declared per-size clique-group counts do not match the encoding"
        return result

    obstruction = MC.circulant_obstruction(n, sizes)
    if status == "obstructed":
        if obstruction is None:
            return {"ok": False, "reason": f"K{n} {sizes} has no arithmetic obstruction"}
        declared = payload.get("obstruction", {})
        expected = {"class": obstruction["class"], "triangle": list(obstruction["triangle"])}
        if int(declared.get("class", -1)) != expected["class"] or [
            int(x) for x in declared.get("triangle", [])
        ] != expected["triangle"]:
            result["ok"] = False
            result["reason"] = f"declared obstruction {declared} != the arithmetic one {expected}"
            return result
        d, x, y, z = expected["class"], *expected["triangle"]
        same = {MC.difference_class(y - x, n), MC.difference_class(z - y, n),
                MC.difference_class(z - x, n)}
        result["checks"]["obstruction_class"] = d
        if same != {d}:
            result["ok"] = False
            result["reason"] = f"the three edges of the declared triangle are not all class {d}"
            return result
        result["establishes"] = (
            f"no circulant colouring of K{n} avoids a monochromatic K3 in a colour "
            f"that forbids it (the class {d} forces {obstruction['triangles']} monochromatic "
            f"triangles, whichever colour it gets)"
        )
        return result

    if status == "sat":
        text = payload.get("coloring")
        if not isinstance(text, str) or len(text) != n * (n - 1) // 2:
            return {"ok": False, "reason": "missing or malformed colouring string"}
        colouring = MC.parse_colouring(text, n, k=len(sizes))
        for d in instance.classes:
            values = {int(colouring[x, (x + d) % n]) for x in range(n)}
            if len(values) != 1:
                result["ok"] = False
                result["reason"] = f"the colouring is not circulant: class {d} uses {sorted(values)}"
                return result
        counts = MC.mono_clique_counts(n, sizes, colouring)
        result["checks"]["monochromatic_cliques"] = counts
        if any(c != 0 for c in counts):
            result["ok"] = False
            result["reason"] = f"the stored colouring is not clean: {counts}"
            return result
        claimed = cert["claims"].get("monochromatic_cliques")
        if claimed is not None and [int(c) for c in claimed] != counts:
            result["ok"] = False
            result["reason"] = f"claimed counts {claimed} != recomputed {counts}"
            return result
        result["establishes"] = (
            f"R{tuple(sizes)} > {n} via a circulant witness "
            f"(the sub-family is a restriction: a witness is a witness)"
        )
        if deep:
            # the recorded `seconds` is the solver's own time (milliseconds for these
            # rows); a re-run needs a floor, or the budget expires before the solver
            # gets going and every deep check reports `unknown`
            redo = MC.circulant_solve(n, sizes, seconds=max(60.0, float(payload.get("seconds", 60.0))))
            result["checks"]["deep_rerun_status"] = redo["status"]
            if redo["status"] not in {"sat", "obstructed"}:
                result["ok"] = False
                result["reason"] = f"deep re-run returned {redo['status']!r}, not sat"
        return result

    if status == "unknown":
        # `unknown` means the budget ran out.  A worker that died without sending a
        # verdict is a different fact, and a certificate that records one must not be
        # read as a bounded attempt that simply came up empty.
        exit_code = payload.get("exit_code")
        if payload.get("no_verdict") or (exit_code is not None and int(exit_code) != 0):
            return {
                "ok": False,
                "reason": (
                    f"the solver produced no verdict (the worker exited with {exit_code}), "
                    f"which is a crash rather than an expired budget, so this row is not "
                    f"a bounded attempt and claims nothing"
                ),
            }
        result["establishes"] = None
        result["note"] = (
            "no verdict: the bounded run was stopped by its budget, so the certificate "
            "records the encoding and the attempt, nothing else"
        )
        if payload.get("budget_expired"):
            result["checks"]["budget_expired"] = True
        if deep:
            # the certificate claims nothing, so a bounded re-run only has to show
            # that the instance still exhausts a solver budget
            budget = min(20.0, float(payload.get("seconds", 20.0)))
            redo = MC.circulant_solve(n, sizes, seconds=budget)
            result["checks"]["deep_rerun_status"] = redo["status"]
            result["checks"]["deep_rerun_seconds"] = budget
        return result

    # status == "unsat"
    if obstruction is not None:
        result["ok"] = False
        result["reason"] = (
            f"K{n} with {sizes} is arithmetically obstructed (3 | n), so it must be "
            f"recorded as 'obstructed', not as a solver verdict"
        )
        return result
    proof = payload.get("proof")
    if proof is not None:
        recorded_cost = float(proof.get("replay_seconds", 1e9))
        checked = _verify_stored_proof(n, sizes, proof, base_dir,
                                       replay=deep or recorded_cost <= REPLAY_BUDGET_SECONDS)
        result["checks"]["proof"] = checked
        if not checked["ok"]:
            result["ok"] = False
            result["reason"] = checked["reason"]
            return result
        if checked.get("replayed"):
            result["establishes"] = (
                f"no circulant colouring of K{n} avoids a monochromatic forbidden "
                f"clique in every colour (DRAT proof replayed, {checked['steps']} steps)"
            )
        else:
            result["establishes"] = (
                f"no circulant colouring of K{n} avoids a monochromatic forbidden "
                f"clique in every colour (DRAT proof on disk, digest re-checked; "
                f"run with --deep to replay it)"
            )
    else:
        result["establishes"] = None
        result["note"] = (
            "no DRAT trace is stored for this row: it is a solver verdict about the "
            "circulant sub-family, not a theorem — see docs/methodology.md"
        )
    if deep:
        redo = MC.circulant_solve(n, sizes, seconds=max(60.0, float(payload.get("seconds", 60.0))))
        result["checks"]["deep_rerun_status"] = redo["status"]
        if redo["status"] != "unsat":
            result["ok"] = False
            result["reason"] = f"deep re-run returned {redo['status']!r}, not unsat"
    return result


def declared_instance(cert: dict):
    """The CNF a certificate's payload declares, **rebuilt** rather than read.

    Two kinds record DRAT traces and they encode different families: a
    ``circulant_multicolour`` row is one variable per (difference class, colour) of
    ``Z_n``, while a ``cayley_multicolour`` row is one per (inversion class, colour)
    of a *named group*, whose clauses are a different CNF altogether.  A trace only
    checks against the encoding it was produced for, so the family is chosen by the
    certificate's own ``problem`` field — which is what keeps a cyclic trace from
    being replayed against a dihedral encoding, and vice versa.  Returning the
    instance rather than a DIMACS path is deliberate: the CNF is the artifact, and a
    stale file on disk would not be the one the certificate describes.
    """
    from . import cayley as CY
    from . import multicolour as MC

    payload = cert["payload"]
    if cert.get("problem") == "cayley_multicolour":
        return CY.CayleyInstance(dict(payload["group"]),
                                 tuple(int(s) for s in payload["sizes"]))
    return MC.CirculantInstance(int(payload["n"]), tuple(int(s) for s in payload["sizes"]))


def _verify_stored_proof(n: int, sizes, proof: dict, base_dir, replay: bool,
                         instance=None) -> dict:
    """Check a certificate's DRAT trace: digests first, replay only when asked.

    Two digests are pinned, and they say different things: ``sha256`` is over the
    canonical *text* of the proof, so it survives re-encoding the trace as binary
    DRAT or re-compressing it, and ``file_sha256`` is over the bytes actually
    committed, so it notices a stored file that is not the one recorded even when
    it decodes to a proof with the same text.  The replay is what turns the
    ``unsat`` verdict into a theorem, and it costs milliseconds to minutes per row
    (the rows that carry a trace are recorded individually), which is why the
    expensive ones are left to ``--deep``.

    ``instance`` is the CNF the trace has to be a refutation of; by default it is
    the *circulant* encoding of ``(n, sizes)``, and the Cayley kind passes its own
    group's encoding instead — the clauses differ, so a trace only checks against
    the family it was produced for.
    """
    from . import drat as DRAT
    from . import multicolour as MC

    declared = proof.get("file")
    if not isinstance(declared, str) or not declared:
        return {"ok": False, "reason": "the recorded proof has no file name"}
    if base_dir is None:
        return {"ok": False, "reason": "a proof is recorded but no base directory was given"}
    path = Path(base_dir) / declared
    if not path.exists():
        return {"ok": False, "reason": f"the recorded proof {declared} is missing"}
    stored = hashlib.sha256(path.read_bytes()).hexdigest()
    recorded_file = proof.get("file_sha256")
    if recorded_file is not None and stored != recorded_file:
        return {"ok": False,
                "reason": f"the stored proof {declared} does not match its recorded file_sha256"}
    lines = DRAT.read_proof(path)
    digest = DRAT.proof_digest(lines)
    if digest != proof.get("sha256"):
        return {"ok": False, "reason": f"the proof {declared} does not match its recorded sha256"}
    out = {"ok": True, "file": declared, "sha256": digest, "file_sha256": stored,
           "steps": len(lines), "stored_bytes": path.stat().st_size, "replayed": False}
    if len(lines) != int(proof.get("steps", len(lines))):
        return {"ok": False, "reason": f"the proof has {len(lines)} steps, not {proof['steps']}"}
    if not replay:
        return out
    if instance is None:
        instance = MC.CirculantInstance(n, tuple(sizes))
    checked = DRAT.check_proof(instance.total_vars(), list(instance.clauses()), lines)
    out.update(replayed=True, added=checked.get("added"), deleted=checked.get("deleted"),
               seconds=round(float(checked.get("seconds", 0.0)), 2))
    if not checked["ok"]:
        return {"ok": False, "reason": f"the DRAT replay failed: {checked.get('reason')}",
                **{k: v for k, v in out.items() if k != "ok"}}
    out["steps"] = checked["steps"]
    return out


VERIFIERS = {
    "kissing": verify_kissing,
    "circulant_multicolour": verify_circulant_multicolour,
    "cayley_multicolour": verify_cayley_multicolour,
    "tammes": verify_tammes,
    "ramsey": verify_ramsey,
    "unit_distance": verify_unit_distance,
    "circulant": verify_circulant,
    "spherical_search": verify_spherical_search,
    "unitdist_search": verify_unitdist_search,
    "ramsey_unsat": verify_ramsey_unsat,
    "sat_attempt": verify_sat_attempt,
}


def verify_certificate(cert: dict, deep: bool = False, workers: int = 1, base_dir=None) -> dict:
    """Verify one certificate dict; returns a result dict with ``ok``.

    ``base_dir`` is the directory the certificate lives in; a proof-carrying
    certificate resolves its recorded trace relative to it.
    """
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
        if problem in {"circulant", "ramsey_unsat", "circulant_multicolour",
                       "cayley_multicolour"}:
            if problem in {"circulant_multicolour", "cayley_multicolour"}:
                return verifier(cert, deep=deep, workers=workers, base_dir=base_dir)
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
            out.append((file, verify_certificate(cert, deep=deep, workers=workers,
                                                 base_dir=file.parent)))
        else:
            out.append((file, {"ok": True, "skipped": "not a certificate"}))
    return out
