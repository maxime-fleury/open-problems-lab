"""Tests for the DRAT checker: it must accept real traces and reject everything else.

The checker is the trusted base of every proved `unsat` row, so it is held to the
standard a checker deserves rather than the standard a solver is held to:

* it accepts the traces the bundled CaDiCaL emits, including deletions and RAT
  steps (checked against the encoding the repository can rebuild);
* it accepts a *small* trace whose refutation is established independently of the
  solver — `K6` in the circulant encoding is unsatisfiable because `R(3,3) = 6`,
  which `lean/Oplab/Certs.lean` proves by exhaustion;
* it rejects traces that are truncated, that claim a clause the formula does not
  imply, or that name a literal outside the variable range;
* and `oplab verify` re-checks the *stored* traces of the certificates, so a trace
  edited on disk is caught at the level of the artifact, not just the rule.
"""

from __future__ import annotations

import json
import random
import shutil
from pathlib import Path

import pytest

from oplab import drat as DRAT
from oplab import multicolour as MC
from oplab.verify import payload_hash, verify_certificate

CERT_DIR = Path(__file__).resolve().parents[1] / "certs" / "circulant_multicolour"

needs_solver = pytest.mark.skipif(not MC.available_solvers(), reason="no bundled SAT solver")


def _proof_lines(n, sizes):
    from pysat.solvers import Cadical195

    instance = MC.CirculantInstance(n, sizes)
    with Cadical195(bootstrap_with=list(instance.clauses()), with_proof=True) as solver:
        assert solver.solve() is False
        return instance, solver.get_proof()


def test_dimacs_round_trip(tmp_path):
    clauses = [[1, -2], [2, 3], [-1, -3]]
    path = tmp_path / "tiny.cnf"
    path.write_text(DRAT.format_dimacs(4, clauses, comment="two of these"), encoding="ascii")
    num_vars, parsed = DRAT.parse_dimacs(path)
    assert num_vars == 4
    assert parsed == clauses


@needs_solver
def test_checker_accepts_a_real_trace_and_rejects_broken_ones():
    """The K6 circulant encoding is unsatisfiable, and the trace says so.

    `R(3,3) = 6` is a theorem about *all* colourings, so the circulant sub-family
    has no witness either: the checker's verdict here is cross-checked by Lean.
    """
    instance, lines = _proof_lines(6, (3, 3))
    result = DRAT.check_proof(instance.total_vars(), list(instance.clauses()), lines)
    assert result["ok"], result.get("reason")
    assert result["empty_clause_at"] == result["steps"]

    # the trace refutes the formula *before* its last lines (the solver deletes
    # clauses after the empty clause), so cutting the tail proves nothing: the test
    # would be vacuous.  Cut to just before the refutation instead.
    assert result["empty_clause_at"] < len(lines)
    stopped_early = lines[: result["empty_clause_at"] - 1]
    result = DRAT.check_proof(instance.total_vars(), list(instance.clauses()), stopped_early)
    assert not result["ok"] and "empty clause" in result["reason"]

    out_of_range = [f"{instance.total_vars() + 1} 0", *lines]
    result = DRAT.check_proof(instance.total_vars(), list(instance.clauses()), out_of_range)
    assert not result["ok"] and "outside" in result["reason"]


def test_checker_rejects_a_clause_the_formula_does_not_imply():
    """Both rules have to fail for a clause to be rejected; here both do.

    On `F = {(1 ∨ ¬2)}` the clause `(2)` is not RUP (assume `¬2`: `1 ∨ ¬2` is
    satisfied, nothing propagates) and not RAT on pivot `2` (resolving with
    `1 ∨ ¬2` gives `(1)`, and assuming `¬1` propagates `¬2` with no conflict).
    """
    clauses = [[1, -2]]
    result = DRAT.check_proof(2, clauses, ["2 0", "0"])
    assert not result["ok"] and "RUP" in result["reason"] and "RAT" in result["reason"]

    # a satisfiable formula cannot be refuted by any trace: there is no empty
    # clause to justify
    result = DRAT.check_proof(2, [[1, -2], [1, 2]], ["1 0", "0"])
    assert not result["ok"] and "step 2" in result["reason"]

    # ... and once the formula does imply the unit, the same opening step is RUP
    result = DRAT.check_proof(2, [[1, -2], [1, 2], [-1]], ["1 0", "0"])
    assert result["ok"], result.get("reason")


def _naive_propagate(formula, assumed):
    """Unit propagation by rescanning the whole formula until it settles.

    ``True`` means a conflict was derived.  This is the reference the watched
    engine is measured against; it is deliberately the slowest correct way to
    write the rule, and it shares no code with :mod:`oplab.drat`.
    """
    value: dict[int, bool] = {}
    for lit in assumed:
        var, sign = abs(lit), lit > 0
        if var in value and value[var] != sign:
            return True
        value[var] = sign
    changed = True
    while changed:
        changed = False
        for clause in formula:
            if any(value.get(abs(l)) == (l > 0) for l in clause):
                continue
            free = [l for l in clause if abs(l) not in value]
            if not free:
                return True
            if len(free) == 1:
                value[abs(free[0])] = free[0] > 0
                changed = True
    return False


def _naive_check(num_vars, clauses, lines):
    """RUP/RAT/suppression checked the obvious way, with the same contract.

    It reports the same keys as :func:`oplab.drat.check_proof` (minus the timings),
    so the two can be compared step for step and not just verdict for verdict.
    """
    formula = [list(clause) for clause in clauses]
    added = deleted = missing_deletions = 0
    for step, line in enumerate(lines):
        kind, literals = DRAT._parse_step(line)
        if kind == "d":
            for i, clause in enumerate(formula):
                if sorted(clause) == sorted(literals):
                    del formula[i]
                    deleted += 1
                    break
            else:
                missing_deletions += 1
            continue
        if any(l == 0 or abs(l) > num_vars for l in literals):
            return {"ok": False, "reason": f"step {step + 1}: literal outside 1..{num_vars}",
                    "steps": step}
        ok = _naive_propagate(formula, [-l for l in literals])
        if not ok and literals:  # an empty clause has no pivot, so RAT cannot apply
            pivot, rest = literals[0], literals[1:]
            ok = True
            for clause in formula:
                if -pivot not in clause:
                    continue
                resolvent = list(rest) + [l for l in clause if l != -pivot]
                if any(-l in resolvent for l in resolvent):
                    continue
                if not _naive_propagate(formula, [-l for l in resolvent]):
                    ok = False
                    break
        if not ok:
            return {"ok": False, "steps": step, "reason": (
                f"step {step + 1}: clause {' '.join(map(str, literals))} 0 is neither "
                "RUP nor RAT against the formula built so far")}
        formula.append(list(literals))
        added += 1
        if not literals:
            return {"ok": True, "steps": step + 1, "added": added, "deleted": deleted,
                    "missing_deletions": missing_deletions, "empty_clause_at": step + 1}
    return {"ok": False, "reason": "the trace ends without deriving the empty clause",
            "steps": len(lines), "added": added, "deleted": deleted,
            "missing_deletions": missing_deletions}


def _random_clause(rng, num_vars, max_len=3):
    """A clause as a solver emits them: distinct variables, no repeated literal."""
    k = rng.randint(1, min(max_len, num_vars))
    return [v if rng.random() < 0.5 else -v for v in rng.sample(range(1, num_vars + 1), k)]


def _random_trace(rng, num_vars, clauses, steps):
    """A trace that is mostly legal RUP steps, with deletions and noise mixed in.

    When the assumption is refuted by propagation, its negation is a clause that
    RUP accepts, so the generated traces keep the engine in the propagation path
    instead of dying at the first step; the empty assumption is tried too, which
    ends a trace on the empty clause whenever the random formula is unsatisfiable.
    """
    lines: list[str] = []
    for _ in range(steps):
        roll = rng.random()
        if roll < 0.25:
            lines.append("d " + " ".join(map(str, _random_clause(rng, num_vars))) + " 0")
            continue
        if roll < 0.8:
            k = rng.randint(0, min(3, num_vars))
            assumption = [v if rng.random() < 0.5 else -v
                          for v in rng.sample(range(1, num_vars + 1), k)]
            if _naive_propagate(clauses, assumption):
                body = " ".join(map(str, [-l for l in assumption]))
                lines.append((body + " 0").strip())
                continue
        lines.append(" ".join(map(str, _random_clause(rng, num_vars))) + " 0")
    return lines


def test_watched_propagation_agrees_with_a_naive_reference():
    """The fast engine and the obvious one must agree case by case.

    Watching two literals per clause is an optimisation with a subtle failure
    mode: bugs in the bookkeeping do not produce wrong answers, they *lose*
    propagations, so a valid trace comes back as "neither RUP nor RAT".  Random
    formulas with random traces reach states a hand-written case does not — the
    corpus here catches, for instance, assignments leaking from one call into the
    next and unit bookkeeping that survives a deletion.  Both implementations must
    agree on the verdict, the rejection step and the step counts.

    The one mistake it does *not* reach on these small formulas is the one the
    fast path actually shipped with — a conflict ending a call in the middle of a
    watch list, whose remaining entries were dropped although the next call still
    needs them.  The regression for that is the stored solver traces replayed by
    `test_stored_traces_replay_and_are_the_proofs_the_certificates_claim` and by
    `tests/test_verify.py`, both of which fail on it (they did).
    """
    rng = random.Random(20261015)
    keys = ("ok", "steps", "added", "deleted", "missing_deletions", "empty_clause_at")
    accepted = rejected = 0
    for _ in range(1200):
        num_vars = rng.randint(2, 7)
        clauses = [_random_clause(rng, num_vars) for _ in range(rng.randint(2, 8))]
        lines = _random_trace(rng, num_vars, clauses, rng.randint(1, 12))
        fast = DRAT.check_proof(num_vars, clauses, lines)
        slow = _naive_check(num_vars, clauses, lines)
        assert fast["ok"] == slow["ok"], (clauses, lines, fast, slow)
        assert fast.get("reason") == slow.get("reason"), (clauses, lines, fast, slow)
        for key in keys:
            assert fast.get(key) == slow.get(key), (key, clauses, lines, fast, slow)
        accepted += fast["ok"]
        rejected += not fast["ok"]
    # the corpus has to contain both outcomes, or the agreement is vacuous
    assert accepted > 20 and rejected > 100, (accepted, rejected)


@needs_solver
def test_checker_validates_a_bigger_trace_with_deletions():
    """K30 is decided by a 1 179-step trace (567 additions, 612 deletions)."""
    instance, lines = _proof_lines(30, (3, 3, 4))
    result = DRAT.check_proof(instance.total_vars(), list(instance.clauses()), lines)
    assert result["ok"], result.get("reason")
    assert result["deleted"] > 0 and result["added"] > 0
    assert result["missing_deletions"] == 0


def test_stored_traces_replay_and_are_the_proofs_the_certificates_claim():
    """Every stored trace is replayed from scratch here where that is cheap.

    The traces are stored next to the certificates and pinned by sha256, so this
    test also pins the pairing: the file a certificate names is the file that
    proves it.  It is also the regression for the watched-literal propagation bug
    that shipped first: the K18 and K30 traces below came back "neither RUP nor
    RAT" until the entries a conflict left unexamined in a watch list were carried
    over to the next call, so a checker that loses propagations fails here.
    """
    certs = sorted(CERT_DIR.glob("*.json"))
    proven = []
    for path in certs:
        cert = json.loads(path.read_text(encoding="utf-8"))
        proof = cert["payload"].get("proof")
        if not proof:
            continue
        proven.append(cert)
        stored = path.parent / proof["file"]
        assert stored.exists(), f"{path.name} names {proof['file']}, which is missing"
        lines = DRAT.read_proof(stored)
        assert DRAT.proof_digest(lines) == proof["sha256"], path.name
        assert len(lines) == proof["steps"] and proof["added"] + proof["deleted"] == proof["steps"]
        assert "replay_seconds" in proof, path.name
    # every `unsat` row in the circulant sub-family carries its trace, and the same
    # count appears in RESULTS.md 9, the README table and the `proofs` CI job
    assert len(proven) == 9, [c["title"] for c in proven]
    # the two largest traces are the two whose replay is expensive enough that a
    # plain `verify` run only re-checks their digest; `--deep` and the `proofs` CI
    # job replay them (the sizes are what make that true, not this machine's speed)
    biggest = sorted(proven, key=lambda c: -int(c["payload"]["proof"]["stored_bytes"]))[:2]
    assert sorted(c["payload"]["n"] for c in biggest) == [50, 55], \
        [c["payload"]["n"] for c in biggest]

    for cert in proven:
        if float(cert["payload"]["proof"]["replay_seconds"]) > 5.0:
            continue  # the slow rows are replayed by --deep / oplab drat --cert
        result = verify_certificate(cert, deep=True, base_dir=CERT_DIR)
        assert result["ok"], result.get("reason")
        assert "DRAT proof replayed" in result["establishes"]


def test_an_edited_trace_is_caught_by_the_certificate(tmp_path):
    """Copy a certificate and its trace, edit the trace, and watch three layers catch it.

    A stored trace is pinned twice over — the sha256 of the canonical text and the
    sha256 of the file itself — and then replayed.  Each step below hands the next
    layer an edit the layer above it was built to accept, so the test says which
    one fires rather than only that something did.
    """
    source = CERT_DIR / "k30_3x3x4.json"
    cert = json.loads(source.read_text(encoding="utf-8"))
    proof = cert["payload"]["proof"]
    shutil.copy(source, tmp_path / source.name)
    lines = DRAT.read_proof(source.parent / proof["file"])
    lines.insert(1, "0")  # an early, unjustified empty clause
    stored_path = tmp_path / "proofs" / Path(proof["file"]).name
    stored = DRAT.write_proof(stored_path, lines)

    # 1. nothing else touched: the digest over the bytes notices first
    result = verify_certificate(cert, deep=True, base_dir=tmp_path)
    assert not result["ok"]
    assert "does not match its recorded file_sha256" in result["reason"]

    # 2. now the bytes are declared correct (and the certificate's own payload hash
    #    kept consistent), so the check moves to the digest over the canonical *text*
    #    of the proof, which the edit changed too
    forged = json.loads(source.read_text(encoding="utf-8"))
    forged["payload"]["proof"].update(
        {key: stored[key] for key in ("file_sha256", "stored_bytes")})
    forged["payload_sha256"] = payload_hash(forged["payload"])
    result = verify_certificate(forged, deep=True, base_dir=tmp_path)
    assert not result["ok"]
    assert "does not match its recorded sha256" in result["reason"]

    # 3. a full forgery — both digests, the sizes and the counts recomputed, and the
    #    payload hash to match — so only the replay is left to refuse the proof
    forged["payload"]["proof"].update(
        {key: stored[key] for key in
         ("sha256", "steps", "added", "deleted", "payload_bytes", "encoding")})
    forged["payload_sha256"] = payload_hash(forged["payload"])
    result = verify_certificate(forged, deep=True, base_dir=tmp_path)
    assert not result["ok"]
    assert "replay failed" in result["reason"]
