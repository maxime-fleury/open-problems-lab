#!/usr/bin/env python3
"""Generate ``lean/Oplab/Certs.lean`` from the JSON certificates.

Every claim stored in ``certs/*.json`` that is a *finite* statement is turned
into a Lean theorem, so that the same claim ``oplab verify`` checks in Python is
also checked by the Lean kernel (``decide``) or by the Lean compiler
(``native_decide``, used only where the kernel would take minutes).

Conventions used by the generated file
--------------------------------------

* Geometric data (kissing/Tammes configurations, unit-distance drawings) is
  emitted as a ``def`` holding the stored decimal literals read as integers
  scaled by ``COORD_SCALE = 10**18``; each geometric theorem is then an exact
  integer inequality with an explicit rounding allowance (``COS_DEN = 10**9``
  for cosines, ``REL_TOL = 10**-9`` for unit distances and norms).  Nothing in
  the generated file depends on IEEE arithmetic.
* ``monoCount`` (bitmask recursion) and ``subsetMonoCount`` (subset
  enumeration) are independent implementations of the same count; both are
  stated whenever the naive one is cheap enough.
* Theorems whose statement is a sweep over ``2**21`` colourings, or an
  exhaustive colouring search with more than ``NATIVE_BUDGET`` assignments, are
  proved with ``native_decide`` and marked as such in their doc string.

Usage::

    python scripts/gen_lean_certs.py            # regenerate lean/Oplab/Certs.lean
    python scripts/gen_lean_certs.py --check    # fail if the file is stale
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import os
import sys
from fractions import Fraction

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CERTS = os.path.join(ROOT, "certs")
OUT = os.path.join(ROOT, "lean", "Oplab", "Certs.lean")

COORD_SCALE = 10**18  # coordinates are scaled to integers by this factor
COS_DEN = 10**9  # cosine thresholds are rationals with this denominator
REL_TOL = 10**-9  # rounding allowance for geometric quantities
NATIVE_BUDGET = 200_000  # enumeration size above which native_decide is used

NORM = COORD_SCALE**2
NORM_TOL = int(REL_TOL * NORM)
UNIT_TOL = int(REL_TOL * COORD_SCALE**2)


# --------------------------------------------------------------------------
# formatting helpers
# --------------------------------------------------------------------------
def ilist(v) -> str:
    return "[" + ", ".join(str(int(x)) for x in v) + "]"


def ipts(pts) -> str:
    return "[\n    " + ",\n    ".join(ilist(v) for v in pts) + "]"


def natlist(v) -> str:
    return "[" + ", ".join(str(int(x)) for x in v) + "]"


def pairs(es) -> str:
    return "[" + ", ".join(f"({int(a)}, {int(b)})" for a, b in es) + "]"


def cstr(s: str) -> str:
    return '"' + s + '".toList'


def rel(path: str) -> str:
    return os.path.relpath(path, ROOT).replace("\\", "/")


# --------------------------------------------------------------------------
# geometric helpers (all integer arithmetic)
# --------------------------------------------------------------------------
def scaled_int(c) -> int:
    """The stored decimal literal, truncated to `COORD_SCALE` as an integer."""
    return int(Fraction(*float(c).as_integer_ratio()) * COORD_SCALE)


def scaled(points):
    return [[scaled_int(c) for c in p] for p in points]


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def cosine(a, b) -> float:
    return dot(a, b) / math.sqrt(dot(a, a) * dot(b, b))


def worst_cosine(P):
    best = None
    for i, j in itertools.combinations(range(len(P)), 2):
        c = cosine(P[i], P[j])
        if best is None or c > best[0]:
            best = (c, i, j)
    return best


def proper_colouring(rows: int, es, k: int):
    """A proper `k`-colouring of the graph, or `None` (symmetry-pruned search)."""
    adj = [[] for _ in range(rows)]
    for a, b in es:
        adj[a].append(b)
        adj[b].append(a)
    col = [-1] * rows

    def bt(v: int, used: int) -> bool:
        if v == rows:
            return True
        for c in range(min(used + 1, k)):
            if all(col[u] != c for u in adj[v]):
                col[v] = c
                if bt(v + 1, max(used, c + 1)):
                    return True
                col[v] = -1
        return False

    return list(col) if bt(0, 0) else None


def exact_chromatic(rows: int, es):
    """Exact chromatic number of the stored graph, with a witness colouring."""
    for k in range(1, rows + 1):
        col = proper_colouring(rows, es, k)
        if col is not None:
            return k, col
    raise AssertionError("empty graph?")


# --------------------------------------------------------------------------
# emitter
# --------------------------------------------------------------------------
class File:
    def __init__(self) -> None:
        self.blocks: list[str] = []
        self.decide = 0
        self.native = 0
        self.notes: list[str] = []

    def add(self, text: str) -> None:
        self.blocks.append(text.rstrip() + "\n")

    def doc(self, comment: str) -> str:
        return "/-- " + comment + "\n-/\n"

    def define(self, name: str, ty: str, value: str, comment: str) -> None:
        self.add(self.doc(comment) + f"def {name} : {ty} :=\n  {value}\n")

    def theorem(self, name: str, statement: str, native: bool, comment: str) -> None:
        tag = "native_decide" if native else "decide"
        if native:
            self.native += 1
        else:
            self.decide += 1
        body = statement if len(statement) < 90 else "\n    " + statement
        self.add(self.doc(comment) + f"theorem {name} : {body} := by {tag}\n")


def name_of(path: str) -> str:
    relpath = os.path.relpath(path, CERTS).replace("\\", "/").replace(".json", "")
    return "cert_" + relpath.replace("/", "_").replace("-", "_")


def head_of(path: str, cert: dict) -> str:
    digest = cert.get("payload_sha256", "")[:16]
    return (
        f"Certificate `{rel(path)}` (payload `{digest}`): "
        + cert.get("title", "")[:140]
    )


# --------------------------------------------------------------------------
# per-problem emitters
# --------------------------------------------------------------------------
def emit_cos_bounded(f: File, path: str, cert: dict, points, extra_claims) -> None:
    """Kissing and Tammes certificates: an upper bound on all pairwise cosines."""
    name, head = name_of(path), head_of(path, cert)
    claims = cert["claims"]
    P = scaled(points)
    rows, dim = len(P), len(P[0])
    n_pairs = rows * (rows - 1) // 2
    claim = float(claims["max_dot"])
    num = int(Fraction(claim).limit_denominator(10**12) * COS_DEN) + 1
    worst, wi, wj = worst_cosine(P)
    assert worst <= num / COS_DEN, f"{path}: threshold too tight ({worst} > {num}/{COS_DEN})"
    f.define(
        f"{name}_points",
        "List (List Int)",
        ipts(P),
        f"Point coordinates of {rel(path)}, scaled by {COORD_SCALE} "
        f"({rows} points in dimension {dim}).",
    )
    f.theorem(
        f"{name}_cos",
        f"allCosBelow {num} {COS_DEN} {name}_points = true",
        False,
        f"{head}\n\nAll {n_pairs} pairwise cosines of the stored configuration are at "
        f"most `{num}/{COS_DEN}`.  The certificate stores `max_dot = {claim!r}`; the "
        f"threshold is rounded up at the 9th decimal and the worst computed cosine is "
        f"{worst:.15f} (pair {wi},{wj}), so the allowance is purely float round-off.",
    )
    shape = (
        f"({name}_points).length = {rows} ∧ "
        f"({name}_points).all (fun v => v.length == {dim}) = true ∧ "
        f"normsWithin {NORM} {NORM_TOL} {name}_points = true ∧ "
        f"distinctVectors {name}_points = true"
    )
    f.theorem(
        f"{name}_shape",
        shape,
        False,
        f"{head}\n\nShape of the stored configuration: {rows} pairwise distinct vectors "
        f"of dimension {dim}, each of squared norm within `1 ± 1e-9` of 1 (in scaled "
        f"integers: `{NORM} ± {NORM_TOL}`).  Together with the cosine bound this is a "
        f"valid packing up to the stated rounding allowance.",
    )
    for key in extra_claims:
        f.theorem(
            f"{name}_{key}",
            f"({name}_points).length = {int(claims[key])}",
            False,
            f"{head}\n\nPoint-count claim `{key} = {int(claims[key])}`.",
        )


def emit_spherical_failure(f: File, path: str, cert: dict) -> None:
    """Certificates that *fail* to establish a packing bound."""
    name, head = name_of(path), head_of(path, cert)
    claims = cert["claims"]
    P = scaled(cert["payload"]["points"])
    rows, dim = len(P), len(P[0])
    worst, wi, wj = worst_cosine(P)
    num = int(worst * 10**4)  # round the witness bound down: 4 decimals
    thresh = claims["threshold"]
    f.define(
        f"{name}_points",
        "List (List Int)",
        ipts(P),
        f"Point coordinates of {rel(path)}, scaled by {COORD_SCALE} "
        f"({rows} points in dimension {dim}).",
    )
    f.define(
        f"{name}_witness_a",
        "List Int",
        ilist(P[wi]),
        f"Point {wi} of {rel(path)}, the first point of the pair whose cosine beats "
        f"the threshold (scaled by {COORD_SCALE}).",
    )
    f.define(
        f"{name}_witness_b",
        "List Int",
        ilist(P[wj]),
        f"Point {wj} of {rel(path)}, the second point of that pair (scaled by "
        f"{COORD_SCALE}).",
    )
    f.theorem(
        f"{name}_witness",
        f"cosAtLeast {num} 10000 {name}_witness_a {name}_witness_b = true",
        False,
        f"{head}\n\nThe stored configuration is *not* a valid packing: points {wi} and "
        f"{wj} have cosine {worst:.15f} > {thresh}, hence `> {num}/10000 > 1/2`.  This "
        f"is the machine-checked content of `establishes_bound = false`, and it "
        f"independently confirms the claimed `max_dot = {claims['max_dot']!r}` as a "
        f"lower bound on the pairwise cosine maximum.",
    )
    f.theorem(
        f"{name}_shape",
        f"({name}_points).length = {rows} ∧ "
        f"({name}_points).all (fun v => v.length == {dim}) = true ∧ "
        f"distinctVectors {name}_points = true",
        False,
        f"{head}\n\nShape of the stored configuration: {rows} pairwise distinct vectors "
        f"of dimension {dim}.",
    )
    for key in ("n_points",):
        if key in claims:
            f.theorem(
                f"{name}_{key}",
                f"({name}_points).length = {int(claims[key])}",
                False,
                f"{head}\n\nPoint-count claim `{key} = {int(claims[key])}`.",
            )


def emit_unitdist(f: File, path: str, cert: dict) -> None:
    name, head = name_of(path), head_of(path, cert)
    payload, claims = cert["payload"], cert["claims"]
    points = payload.get("points") or payload.get("best_points")
    es = payload.get("edges") or payload.get("best_edges")
    es = [(int(a), int(b)) for a, b in es]
    P = scaled(points)
    rows = len(P)
    chi = None
    for key in ("chromatic_number", "best_chromatic_number"):
        if key in claims:
            chi = int(claims[key])
    f.define(
        f"{name}_points",
        "List (List Int)",
        ipts(P),
        f"Vertex coordinates of {rel(path)}, scaled by {COORD_SCALE}.",
    )
    f.define(
        f"{name}_edges",
        "List (Nat × Nat)",
        pairs(es),
        f"Edge list of {rel(path)} ({len(es)} edges on {rows} vertices).",
    )
    f.theorem(
        f"{name}_unit_edges",
        f"unitEdges {COORD_SCALE} {UNIT_TOL} {name}_points {name}_edges = true",
        False,
        f"{head}\n\nEvery stored edge really is of unit length up to `1e-9`: for each "
        f"edge `(i, j)` the exact integer condition "
        f"`| |p_i - p_j|^2 - s^2 | <= {UNIT_TOL}` holds, where `s = {COORD_SCALE}` is "
        f"the scale (so `s^2` is the squared unit).",
    )
    computed_chi, colouring = exact_chromatic(rows, es)
    if chi is not None:
        assert computed_chi == chi, (
            f"{path}: certificate claims chromatic number {chi}, brute force says "
            f"{computed_chi} for the stored edge set"
        )
    chi = computed_chi
    f.define(
        f"{name}_colouring",
        "List Nat",
        natlist(colouring),
        f"A proper {chi}-colouring of the {rows} vertices of {rel(path)}, found by "
        f"brute force in the generator (one colour per vertex, in vertex order).",
    )
    assignments = (chi - 1) ** rows
    native = assignments > NATIVE_BUDGET
    tail = ", with `native_decide`." if native else "."
    f.theorem(
        f"{name}_chromatic",
        f"chromaticWitness {rows} {chi} {name}_colouring {name}_edges = true",
        native,
        f"{head}\n\nThe stored graph has chromatic number exactly {chi}: the emitted "
        f"{chi}-colouring is proper on `{name}_edges`, and no proper "
        f"{chi - 1}-colouring exists — searched exhaustively over {rows}^{chi - 1} = "
        f"{assignments} colourings{tail}",
    )
    shape = f"({name}_points).length = {rows} ∧ ({name}_edges).length = {len(es)}"
    if "n_vertices" in claims:
        shape += f" ∧ ({name}_points).length = {int(claims['n_vertices'])}"
    if "n_edges" in claims:
        shape += f" ∧ ({name}_edges).length = {int(claims['n_edges'])}"
    f.theorem(
        f"{name}_shape",
        shape,
        False,
        f"{head}\n\nVertex and edge counts of the stored drawing ({rows} vertices, "
        f"{len(es)} edges) match the certificate claims.",
    )


def emit_ramsey(f: File, path: str, cert: dict) -> None:
    name, head = name_of(path), head_of(path, cert)
    payload, claims = cert["payload"], cert["claims"]
    n, k, s = int(payload["n"]), int(payload["k"]), payload["coloring"]
    assert len(s) == n * (n - 1) // 2, f"{path}: bad colouring length"
    key = next((c for c in claims if c.startswith("mono_k")), None)
    assert key is not None, f"{path}: no mono_k* claim"
    value = int(claims[key])
    native = n >= 40  # the tabu colourings: the kernel would need minutes
    f.define(
        f"{name}_coloring",
        "List Char",
        cstr(s),
        f"The 2-colouring of `K{n}` stored in {rel(path)} "
        f"(`'0'` = red, `'1'` = blue, one character per edge in lexicographic order).",
    )
    if value == 0:
        subsets = math.comb(n, k)
        if subsets <= 20_000:
            statement = (
                f"monoCount {n} {k} {name}_coloring = 0 ∧ "
                f"subsetMonoCount {n} {k} {name}_coloring = 0"
            )
            f.theorem(
                f"{name}_clean",
                statement,
                False,
                f"{head}\n\nThis colouring contains no monochromatic `K{k}`, checked "
                f"twice: by the bitmask counter `monoCount` and by the independent "
                f"subset enumeration `subsetMonoCount` over all {subsets} `{k}`-subsets "
                f"of the {n} vertices.  Equivalently `R({k},{k}) > {n}`.",
            )
        else:
            f.theorem(
                f"{name}_clean",
                f"monoCount {n} {k} {name}_coloring = 0",
                native,
                f"{head}\n\nThis colouring contains no monochromatic `K{k}` "
                f"(`monoCount = 0`); the subset-enumeration cross-check is skipped "
                f"because there are {subsets:,} `{k}`-subsets.  Equivalently "
                f"`R({k},{k}) > {n}`.",
            )
        return
    f.theorem(
        f"{name}_mono_count",
        f"monoCount {n} {k} {name}_coloring = {value}",
        native,
        f"{head}\n\nThe stored colouring of `K{n}` has exactly {value} monochromatic "
        f"`K{k}` — the value claimed by the certificate, reproduced by the bitmask "
        f"counter `monoCount`.  A non-zero count is what makes this an *attack* "
        f"certificate rather than a bound.",
    )


def emit_sat(f: File, path: str, cert: dict) -> None:
    name, head = name_of(path), head_of(path, cert)
    claims = cert["claims"]
    enc = claims.get("encoding", {})
    n = int(claims["n"])
    k = int(claims["k"]) if "k" in claims else (3 if "k3" in name else 4)
    edge_vars = int(enc["edge_vars"])
    subset = int(enc["subset_clauses_match_formula"])
    num_vars, num_clauses = int(enc["num_vars"]), int(enc["num_clauses"])
    status = claims.get("status")
    binom = " * ".join(str(n - i) for i in range(k))
    fact = math.factorial(k)
    f.theorem(
        f"{name}_encoding",
        f"{n} * ({n} - 1) / 2 = {edge_vars} ∧ "
        f"2 * ({binom} / {fact}) = {subset} ∧ "
        f"{subset} ≤ {num_clauses} ∧ {edge_vars} ≤ {num_vars}",
        False,
        f"{head}\n\nThe CNF sizes recorded in the certificate match the encoding "
        f"formulas: {edge_vars} edge variables = `C({n},2)`, {subset} subset clauses = "
        f"`2*C({n},{k})` (the symmetry-breaking clauses are added on top, so "
        f"{num_clauses} >= {subset}, and {num_vars} >= {edge_vars}).  The certificate "
        f"records `status = {status}`.",
    )


R33_THEOREM = """\
/-- Exhaustive Ramsey fact, which validates the `unsat` claims of the
`certs/sat/k6_k3_sym*.json` certificates: **every** 2-colouring of `K6` — all
`2^15 = 32768` of them, read as the low bits of the colouring mask — contains a
monochromatic triangle, i.e. `R(3,3) <= 6`.  Together with the clean `K5`
witnesses (`certs/circulant/k5_k3.json`, `certs/sat/k5_k3_sym*.json`, which give
`R(3,3) > 5`) this pins `R(3,3) = 6` with no solver and no SAT certificate in
the trusted base. -/
theorem ramsey_R33_exhaustive : cleanMasks 6 3 (2 ^ 15) = [] := by decide
"""


def emit_header(f: File) -> None:
    f.add(
        f"""\
/-
  Generated by `scripts/gen_lean_certs.py` — do not edit by hand.

  One theorem per claim of `certs/*.json`, checked by the Lean kernel (`decide`)
  or, where marked, by the Lean compiler (`native_decide`, used only when the
  kernel would need minutes).

  Geometric data is emitted as integer coordinates scaled by
  `COORD_SCALE = {COORD_SCALE}`.  Cosine bounds are rationals with denominator
  `COS_DEN = {COS_DEN}` and are checked as the exact inequality
  `den^2 * <x,y>^2 <= num^2 * |x|^2 * |y|^2` (equivalent to `cos <= num/den` for
  positive dot products); unit distances as `| |a-b|^2 - s^2 | <= {UNIT_TOL}`
  with `s = {COORD_SCALE}`; norms as `| |x|^2 - s^2 | <= {NORM_TOL}`.  The
  allowance is `1e-9` in relative terms, while the round-off of the stored
  literals is at most a few `1e-15`, so the theorems bound the stored decimal
  data itself — no IEEE arithmetic is involved anywhere.
-/

import Oplab.Basic
import Oplab.Check

set_option maxRecDepth 1000000
set_option maxHeartbeats 4000000

namespace Oplab
"""
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="fail if the file is stale")
    ap.add_argument(
        "--only",
        default="",
        help="development helper: only emit certificates whose path contains one "
        "of these comma-separated substrings",
    )
    args = ap.parse_args()

    paths = sorted(
        os.path.join(dirpath, fn)
        for dirpath, _dirs, files in os.walk(CERTS)
        for fn in files
        if fn.endswith(".json")
    )
    f = File()
    emit_header(f)
    counts: dict[str, int] = {}
    for path in paths:
        with open(path, encoding="utf-8") as fh:
            cert = json.load(fh)
        problem = cert.get("problem")
        if problem is None:
            continue  # summary files are not certificates
        if args.only and not any(
            part in rel(path) for part in args.only.split(",") if part
        ):
            continue
        counts[problem] = counts.get(problem, 0) + 1
        if problem in ("kissing", "tammes"):
            emit_cos_bounded(f, path, cert, cert["payload"]["points"], ("n_points",))
        elif problem == "spherical_search":
            emit_spherical_failure(f, path, cert)
        elif problem in ("unit_distance", "unitdist_search"):
            emit_unitdist(f, path, cert)
        elif problem == "ramsey":
            emit_ramsey(f, path, cert)
        elif problem in ("sat_attempt", "ramsey_unsat"):
            emit_sat(f, path, cert)
        elif problem == "circulant":
            name, head = name_of(path), head_of(path, cert)
            payload, claims = cert["payload"], cert["claims"]
            n, k = int(payload["n"]), int(payload["k"])
            total = int(claims["colourings_tested"])
            witnesses = [int(w) for w in payload["witnesses"]]
            native = total > NATIVE_BUDGET
            f.theorem(
                f"{name}_witnesses",
                f"cleanCirculantMasks {n} {k} {total} = {natlist(witnesses)}",
                native,
                f"{head}\n\nExhaustive sweep of all {total} circulant "
                f"(translation-invariant) 2-colourings of `K{n}`: exactly the "
                f"difference masks {witnesses} are free of monochromatic `K{k}`, and "
                f"no others.  A witness proves `R({k},{k}) > {n}`; an empty list is the "
                f"negative result that no *circulant* colouring of `K{n}` avoids a "
                f"monochromatic `K{k}`"
                + (", checked with `native_decide`." if native else "."),
            )
            f.theorem(
                f"{name}_count",
                f"2 ^ {n // 2} = {total}",
                False,
                f"{head}\n\nThere are `2^(n/2) = 2^{n // 2}` circulant colourings of "
                f"`K{n}`, matching the `colourings_tested` claim of the certificate.",
            )
        else:
            raise AssertionError(f"unhandled problem {problem!r} in {path}")

    summary = "-- certificate files: " + ", ".join(
        f"{v} {k}" for k, v in sorted(counts.items())
    )
    text = (
        "\n".join(f.blocks)
        + "\n"
        + summary
        + "\n\n"
        + R33_THEOREM
        + "\nend Oplab\n"
    )

    only = bool(args.only)
    if args.check and not only:
        current = open(OUT, encoding="utf-8").read() if os.path.exists(OUT) else None
        if current != text:
            print("lean/Oplab/Certs.lean is stale; rerun scripts/gen_lean_certs.py")
            return 1
        print("lean/Oplab/Certs.lean is up to date")
        return 0

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    print(
        f"wrote {rel(OUT)}: {len(text.splitlines())} lines, {f.decide} decide, "
        f"{f.native} native_decide, {sum(counts.values())} certificates"
    )
    for note in f.notes:
        print("  note:", note)
    return 0


if __name__ == "__main__":
    sys.exit(main())
